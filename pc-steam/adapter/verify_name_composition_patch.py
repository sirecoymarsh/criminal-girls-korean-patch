#!/usr/bin/env python3
"""Verify direct two-set Hangul input while preserving the original Japanese selector path."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_EDI

CODE_SECTION_NAME = b".koinput"
STATE_SECTION_NAME = b".kostate"
UPDATE_HOOK_VA = 0x49C220
UPDATE_RETURN_VA = 0x49C226
SELECT_HOOK_VA = 0x49C7B1
SELECT_EXPECTED = bytes.fromhex("803daa9a5c0000")
DELETE_HOOK_VA = 0x49C714
SELECT_RETURN_VA = 0x49C8E1
DELETE_RETURN_VA = 0x49C786
GET_ASYNC_KEY_STATE_IAT_VA = 0x5392BC
GAME_INPUT_CURRENT_VA = 0x5F5EFC
GAME_INPUT_REPEAT_VA = 0x5F5F00
LANGUAGE_MODE_VA = 0x5C9AAA
ENGLISH_SELECT_RETURN_VA = 0x49C870
ENGLISH_DELETE_RETURN_VA = 0x49C71D
UPDATE_OFF = 0x0000
COMPOSE_OFF = 0x1000
DELETE_ROUTINE_OFF = 0x1400
ASCII_APPEND_OFF = 0x1800
DELETE_OFF = 0x1C00
SELECT_OFF = 0x1E00
INPUT_MODE_LOCAL_OFF = 0x102
MUTABLE_STATE_SIZE = 0x103
VK_HANGUL = 0x15
VK_F1 = 0x70
VK_RETURN = 0x0D
DIGIT_KEYS = list(range(0x30, 0x3A))
NAME_CAPACITY = 6
NAME_HELP_POINTER_IMMEDIATE_VA = 0x49D352
NAME_HELP_ORIGINAL_TARGET_VA = 0x55FB7C
NAME_HELP_TEXT = "F1 한/영　Backspace 삭제　Click 일어 입력　Enter 완료"
NAME_HELP_LEGEND = "F1 한/영 / Backspace 삭제 / Click 일어 입력 / Enter 완료"


def fullwidth_raw_word(ch: str) -> int:
    encoded = ch.encode("cp932")
    if len(encoded) != 2 or 0 in encoded:
        raise ValueError(f"not a non-NUL CP932 fullwidth character: {ch!r}")
    return (encoded[1] << 8) | encoded[0]


FULLWIDTH_UPPER_RAW = {0x41 + i: fullwidth_raw_word(chr(0xFF21 + i)) for i in range(26)}
FULLWIDTH_LOWER_RAW = {0x41 + i: fullwidth_raw_word(chr(0xFF41 + i)) for i in range(26)}
FULLWIDTH_DIGIT_RAW = {0x30 + i: fullwidth_raw_word(chr(0xFF10 + i)) for i in range(10)}

LEADS = "\u3131 \u3132 \u3134 \u3137 \u3138 \u3139 \u3141 \u3142 \u3143 \u3145 \u3146 \u3147 \u3148 \u3149 \u314a \u314b \u314c \u314d \u314e".split()
MEDIALS = "\u314f \u3150 \u3151 \u3152 \u3153 \u3154 \u3155 \u3156 \u3157 \u3158 \u3159 \u315a \u315b \u315c \u315d \u315e \u315f \u3160 \u3161 \u3162 \u3163".split()
COMPOUND_FINALS = "\u3133 \u3135 \u3136 \u313a \u313b \u313c \u313d \u313e \u313f \u3140 \u3144".split()
BASIC_CONSONANTS = "\u3131 \u3134 \u3137 \u3139 \u3141 \u3142 \u3145 \u3147 \u3148 \u314a \u314b \u314c \u314d \u314e".split()
BASIC_VOWELS = "\u314f \u3150 \u3151 \u3153 \u3154 \u3155 \u3157 \u315b \u315c \u3160 \u3161 \u3163".split()
SHIFT_INPUTS = "\u3132 \u3138 \u3143 \u3146 \u3149 \u3152 \u3156".split()
INPUT_JAMO = BASIC_CONSONANTS + BASIC_VOWELS + SHIFT_INPUTS
KEY_MAP = [
    (0x51, "\u3142", "\u3143"), (0x57, "\u3148", "\u3149"), (0x45, "\u3137", "\u3138"),
    (0x52, "\u3131", "\u3132"), (0x54, "\u3145", "\u3146"), (0x59, "\u315b", None),
    (0x55, "\u3155", None), (0x49, "\u3151", None), (0x4F, "\u3150", "\u3152"), (0x50, "\u3154", "\u3156"),
    (0x41, "\u3141", None), (0x53, "\u3134", None), (0x44, "\u3147", None), (0x46, "\u3139", None),
    (0x47, "\u314e", None), (0x48, "\u3157", None), (0x4A, "\u3153", None), (0x4B, "\u314f", None),
    (0x4C, "\u3163", None), (0x5A, "\u314b", None), (0x58, "\u314c", None), (0x43, "\u314a", None),
    (0x56, "\u314d", None), (0x42, "\u3160", None), (0x4E, "\u315c", None), (0x4D, "\u3161", None),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_word(sjis: int) -> int:
    return ((sjis & 0xFF) << 8) | (sjis >> 8)


def encode_runtime_text(text: str, font_report: dict) -> bytes:
    slots = {row["char"]: int(row["sjis"], 16) for row in font_report.get("repurposed_slots", [])}
    out = bytearray()
    for ch in text:
        if ord(ch) < 0x80:
            out.append(ord(ch))
            continue
        try:
            out.extend(ch.encode("cp932"))
            continue
        except UnicodeEncodeError:
            pass
        code = slots.get(ch)
        if code is None:
            raise ValueError(f"font report has no runtime glyph slot for U+{ord(ch):04X}")
        out.extend(code.to_bytes(2, "big"))
    if 0 in out:
        raise ValueError("runtime help text contains an embedded NUL byte")
    return bytes(out)


def rel_target(data: bytes, offset: int, source_va: int) -> int:
    if data[offset] != 0xE9:
        raise ValueError(f"hook at {source_va:08X} is not E9")
    return source_va + 5 + struct.unpack_from("<i", data, offset + 1)[0]


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def disassemble(md: Cs, raw: bytes, offset: int, length: int, base_va: int):
    return list(md.disasm(raw[offset:offset + length], base_va + offset))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--literal-exe", type=Path, required=True)
    ap.add_argument("--patched-exe", type=Path, required=True)
    ap.add_argument("--font-report", type=Path, required=True)
    ap.add_argument("--patch-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    literal = args.literal_exe.read_bytes()
    patched = args.patched_exe.read_bytes()
    font = json.loads(args.font_report.read_text(encoding="utf-8-sig"))
    authority = json.loads(args.patch_report.read_text(encoding="utf-8-sig"))
    if authority.get("schema") != "criminal-girls.two-set-name-input-patch.v8" or authority.get("status") != "PASS":
        raise ValueError("unexpected patch authority schema or status")
    if authority.get("source_exe_sha256") != sha256(literal) or authority.get("output_sha256") != sha256(patched):
        raise ValueError("patch authority hashes do not match inputs")
    if authority.get("font_report_sha256") != sha256(args.font_report.read_bytes()) or font.get("passed") is not True:
        raise ValueError("font authority does not match or did not pass")
    if len(INPUT_JAMO) != 33 or len(set(INPUT_JAMO)) != 33 or len(KEY_MAP) != 26:
        raise ValueError("two-set verifier input contract failed")

    before = pefile.PE(data=literal, fast_load=False)
    after = pefile.PE(data=patched, fast_load=False)
    code_section = next((s for s in after.sections if s.Name.rstrip(b"\0") == CODE_SECTION_NAME), None)
    state_section = next((s for s in after.sections if s.Name.rstrip(b"\0") == STATE_SECTION_NAME), None)
    if before.FILE_HEADER.NumberOfSections != 6 or after.FILE_HEADER.NumberOfSections != 8 or code_section is None or state_section is None:
        raise ValueError("PE section-count/name contract failed")
    if code_section.Characteristics != 0x60000020 or state_section.Characteristics != 0xC0000040:
        raise ValueError("RX-code/RW-state protection contract failed")
    if code_section.Characteristics & 0x80000000 or not state_section.Characteristics & 0x80000000 or state_section.Characteristics & 0x20000000:
        raise ValueError("writable/executable separation failed")
    if state_section.Misc_VirtualSize < MUTABLE_STATE_SIZE:
        raise ValueError("mutable state section is too small")
    state_raw = patched[state_section.PointerToRawData:state_section.PointerToRawData + state_section.Misc_VirtualSize]
    if any(state_raw):
        raise ValueError("mutable state section is not zero-initialized")

    allowed: set[int] = set()
    for field, size in (("NumberOfSections", 2),):
        start = before.FILE_HEADER.get_field_absolute_offset(field)
        allowed.update(range(start, start + size))
    for field in ("SizeOfCode", "SizeOfInitializedData", "SizeOfImage"):
        start = before.OPTIONAL_HEADER.get_field_absolute_offset(field)
        allowed.update(range(start, start + 4))
    header_start = before.sections[-1].get_file_offset() + 40
    allowed.update(range(header_start, header_start + 80))
    neutralized = authority.get("neutralized_overlapping_base_relocations")
    expected_select_reloc_rva = SELECT_HOOK_VA - before.OPTIONAL_HEADER.ImageBase + 2
    if not isinstance(neutralized, list) or len(neutralized) != 1:
        raise ValueError(f"selector hook must neutralize exactly one overlapping HIGHLOW relocation: {neutralized}")
    neutralized_select = neutralized[0]
    if (neutralized_select.get("rva") != expected_select_reloc_rva
            or neutralized_select.get("type_before") != 3
            or neutralized_select.get("type_after") != 0):
        raise ValueError(f"unexpected selector relocation neutralization: {neutralized_select}")
    allowed.update((neutralized_select["file_offset"], neutralized_select["file_offset"] + 1))
    select_offset_before = before.get_offset_from_rva(SELECT_HOOK_VA - before.OPTIONAL_HEADER.ImageBase)
    if literal[select_offset_before:select_offset_before + len(SELECT_EXPECTED)] != SELECT_EXPECTED:
        raise ValueError("literal executable does not contain the trusted original selector instruction")
    def matching_select_relocations(pe, reloc_type):
        return [
            entry
            for block in pe.DIRECTORY_ENTRY_BASERELOC
            for entry in block.entries
            if entry.type == reloc_type and entry.rva == expected_select_reloc_rva
        ]
    original_select_relocations = matching_select_relocations(before, 3)
    patched_select_relocations = matching_select_relocations(after, 3)
    patched_select_absolute_padding = matching_select_relocations(after, 0)
    if len(original_select_relocations) != 1 or patched_select_relocations or len(patched_select_absolute_padding) != 1:
        raise ValueError(
            "selector relocation was not converted from one HIGHLOW to one ABSOLUTE padding entry: "
            f"before={len(original_select_relocations)}, after_highlow={len(patched_select_relocations)}, "
            f"after_absolute={len(patched_select_absolute_padding)}"
        )
    code_va = after.OPTIONAL_HEADER.ImageBase + code_section.VirtualAddress
    state_va = after.OPTIONAL_HEADER.ImageBase + state_section.VirtualAddress
    help_off = int(authority["tables"]["name_help_offset"])
    expected_help_blob = encode_runtime_text(NAME_HELP_TEXT, font) + b"\0"
    if authority.get("name_help_text") != NAME_HELP_TEXT or authority.get("name_help_legend") != NAME_HELP_LEGEND:
        raise ValueError("name-help authority text mismatch")
    if authority["tables"].get("name_help_bytes") != len(expected_help_blob) - 1:
        raise ValueError("name-help authority byte count mismatch")
    help_pointer_offset_before = before.get_offset_from_rva(NAME_HELP_POINTER_IMMEDIATE_VA - before.OPTIONAL_HEADER.ImageBase)
    help_pointer_offset_after = after.get_offset_from_rva(NAME_HELP_POINTER_IMMEDIATE_VA - after.OPTIONAL_HEADER.ImageBase)
    if struct.unpack_from("<I", literal, help_pointer_offset_before)[0] != NAME_HELP_ORIGINAL_TARGET_VA:
        raise ValueError("literal name-help pointer source mismatch")
    relocated_help_va = code_va + help_off
    if struct.unpack_from("<I", patched, help_pointer_offset_after)[0] != relocated_help_va:
        raise ValueError("patched name-help pointer target mismatch")
    allowed.update(range(help_pointer_offset_after, help_pointer_offset_after + 4))
    help_blob = patched[code_section.PointerToRawData + help_off:code_section.PointerToRawData + help_off + len(expected_help_blob)]
    if help_blob != expected_help_blob:
        raise ValueError("relocated name-help string bytes or NUL mismatch")
    help_pointer_rva = NAME_HELP_POINTER_IMMEDIATE_VA - before.OPTIONAL_HEADER.ImageBase
    def matching_help_relocations(pe):
        return [entry for block in pe.DIRECTORY_ENTRY_BASERELOC for entry in block.entries if entry.type == 3 and entry.rva == help_pointer_rva]
    if len(matching_help_relocations(before)) != 1 or len(matching_help_relocations(after)) != 1:
        raise ValueError("name-help HIGHLOW relocation was not preserved exactly once")
    for delta in (0, -0x210000, 0x1000000, 0x30000000):
        if ((struct.unpack_from("<I", patched, help_pointer_offset_after)[0] + delta) & 0xFFFFFFFF) != ((relocated_help_va + delta) & 0xFFFFFFFF):
            raise ValueError(f"name-help ASLR simulation failed for delta {delta:+#x}")
    hook_specs = (
        ("update", UPDATE_HOOK_VA, code_va + UPDATE_OFF, 6),
        ("delete", DELETE_HOOK_VA, code_va + DELETE_OFF, 5),
        ("select", SELECT_HOOK_VA, code_va + SELECT_OFF, 7),
    )
    hook_targets = {}
    for name, va, expected, size in hook_specs:
        offset = after.get_offset_from_rva(va - after.OPTIONAL_HEADER.ImageBase)
        allowed.update(range(offset, offset + size))
        actual = rel_target(patched, offset, va)
        if actual != expected:
            raise ValueError(f"{name} hook target mismatch: {actual:08X} != {expected:08X}")
        if size == 6 and patched[offset + 5] != 0x90:
            raise ValueError("update hook does not NOP the sixth prologue byte")
        hook_targets[name] = f"0x{actual:08X}"
    active_hook_relocations = []
    hook_ranges = [(va - after.OPTIONAL_HEADER.ImageBase, va - after.OPTIONAL_HEADER.ImageBase + size, name) for name, va, _, size in hook_specs]
    for block in after.DIRECTORY_ENTRY_BASERELOC:
        for entry in block.entries:
            if entry.type != 3:
                continue
            for start_rva, end_rva, name in hook_ranges:
                if entry.rva < end_rva and entry.rva + 4 > start_rva:
                    active_hook_relocations.append({"hook": name, "rva": entry.rva, "type": entry.type})
    if active_hook_relocations:
        raise ValueError(f"active HIGHLOW relocations still overlap rel32 hooks: {active_hook_relocations}")
    aslr_deltas = (0, -0x210000, 0x1000000, 0x30000000)
    for name, va, expected, _ in hook_specs:
        offset = after.get_offset_from_rva(va - after.OPTIONAL_HEADER.ImageBase)
        disp = struct.unpack_from("<i", patched, offset + 1)[0]
        for delta in aslr_deltas:
            actual = (va + delta + 5 + disp) & 0xFFFFFFFF
            wanted = (expected + delta) & 0xFFFFFFFF
            if actual != wanted:
                raise ValueError(f"{name} ASLR simulation failed for delta {delta:+#x}: {actual:08X} != {wanted:08X}")
    changed_old = [i for i, (a, b) in enumerate(zip(literal, patched[:len(literal)])) if a != b]
    outside = [i for i in changed_old if i not in allowed]
    if outside:
        raise ValueError(f"old-image changes outside allowlist: {outside[:20]}")

    raw = patched[code_section.PointerToRawData:code_section.PointerToRawData + code_section.Misc_VirtualSize]
    tables = authority["tables"]
    input_off = tables["input_offset"]
    state_off = tables["state_index_offset"]
    trans_off = tables["transition_offset"]
    decomp_off = tables["decomposition_offset"]
    state_count = tables["supported_composition_state_count"] + 1
    input_words = list(struct.unpack_from(f"<{len(INPUT_JAMO)}H", raw, input_off))
    state_index = struct.unpack_from("<65536H", raw, state_off)
    transition_count = state_count * len(INPUT_JAMO)
    transitions = struct.unpack_from(f"<{transition_count}I", raw, trans_off)
    decomp = struct.unpack_from("<65536H", raw, decomp_off)
    if transition_count != tables["transition_count"]:
        raise ValueError("transition count differs from authority")

    char_to_raw = {row["char"]: raw_word(int(row["sjis"], 16)) for row in font["repurposed_slots"]}
    raw_to_char = {value: key for key, value in char_to_raw.items()}
    if input_words != [char_to_raw[ch] for ch in INPUT_JAMO]:
        raise ValueError("input Jamo table differs from font mapping")
    standard = []
    for cp in range(0xAC00, 0xD7A4):
        ch = chr(cp)
        try:
            if len(ch.encode("euc_kr")) == 2:
                standard.append(ch)
        except UnicodeEncodeError:
            pass
    missing_standard = [ch for ch in standard if state_index[char_to_raw[ch]] == 0]
    if missing_standard:
        raise ValueError(f"Wansung states missing: {len(missing_standard)}")

    input_index = {ch: i for i, ch in enumerate(INPUT_JAMO)}
    def apply(text: list[str], incoming: str, capacity: int = 6) -> list[str]:
        current_raw = char_to_raw[text[-1]] if text else 0
        state = state_index[current_raw]
        word = transitions[state * len(INPUT_JAMO) + input_index[incoming]]
        previous_raw = word & 0xFFFF
        new_raw = word >> 16
        if new_raw and len(text) >= capacity:
            return text
        if text and previous_raw:
            text[-1] = raw_to_char[previous_raw]
        if new_raw:
            text.append(raw_to_char[new_raw])
        return text

    def type_jamo(sequence: str, capacity: int = 6) -> str:
        text: list[str] = []
        for incoming in sequence:
            apply(text, incoming, capacity)
        return "".join(text)

    key_lookup = {chr(vk).lower(): (normal, shifted) for vk, normal, shifted in KEY_MAP}
    def type_keys(keys: str, capacity: int = 6) -> str:
        sequence = []
        for key in keys:
            normal, shifted = key_lookup[key.lower()]
            sequence.append(shifted if key.isupper() and shifted else normal)
        return type_jamo("".join(sequence), capacity)

    jamo_traces = {
        "basic": ("\u3131\u314f\u3134\u314f\u3137\u314f", "\uac00\ub098\ub2e4"),
        "name": ("\u314e\u3157\u3147\u3131\u3163\u3139\u3137\u3157\u3147", "\ud64d\uae38\ub3d9"),
        "compound_final": ("\u3131\u314f\u3142\u3145", "\uac12"),
        "compound_vowel": ("\u3131\u3157\u314f", "\uacfc"),
        "review_name": ("\u3148\u3153\u3134\u3131\u314f\u3147\u3131\u3157\u3147\u315c", "\uc804\uac15\uace0\uc6b0"),
    }
    key_traces = {
        "rkskek": "\uac00\ub098\ub2e4",
        "ghdrlfehd": "\ud64d\uae38\ub3d9",
        "rkqt": "\uac12",
        "rhk": "\uacfc",
        "Rk": "\uae4c",
        "rhkl": "\uad18",
        "dlT": "\uc788",
    }
    trace_results = []
    for name, (sequence, expected) in jamo_traces.items():
        actual = type_jamo(sequence)
        if actual != expected:
            raise ValueError(f"Jamo trace {name}: {actual!r} != {expected!r}")
        trace_results.append({"kind": "jamo", "name": name, "input": sequence, "actual": actual})
    for keys, expected in key_traces.items():
        actual = type_keys(keys)
        if actual != expected:
            raise ValueError(f"key trace {keys}: {actual!r} != {expected!r}")
        trace_results.append({"kind": "two_set_keys", "input": keys, "actual": actual})

    def delete_once(text: list[str]) -> None:
        if not text:
            return
        replacement = decomp[char_to_raw[text[-1]]]
        if replacement:
            text[-1] = raw_to_char[replacement]
        else:
            text.pop()

    delete_text = list(type_keys("rkqt"))
    delete_trace = ["".join(delete_text)]
    while delete_text:
        delete_once(delete_text)
        delete_trace.append("".join(delete_text))
    expected_delete = ["\uac12", "\uac11", "\uac00", "\u3131", ""]
    if delete_trace != expected_delete:
        raise ValueError(f"delete trace mismatch: {delete_trace}")
    full = list("\uac00\ub098\ub2e4\ub77c\ub9c8\uac04")
    apply(full, "\u314f", 6)
    if "".join(full) != "\uac00\ub098\ub2e4\ub77c\ub9c8\uac04":
        raise ValueError("capacity guard mutated a full buffer during final transfer")

    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    code_lengths = authority["code"]
    regions = {
        "update": (UPDATE_OFF, code_lengths["update_bytes"]),
        "compose": (COMPOSE_OFF, code_lengths["compose_bytes"]),
        "delete_routine": (DELETE_ROUTINE_OFF, code_lengths["delete_routine_bytes"]),
        "ascii_append": (ASCII_APPEND_OFF, code_lengths["ascii_append_bytes"]),
        "delete": (DELETE_OFF, code_lengths["delete_bytes"]),
        "select": (SELECT_OFF, code_lengths["select_bytes"]),
    }
    decoded = {name: disassemble(md, raw, off, length, code_va) for name, (off, length) in regions.items()}
    position_dependent_memory = []
    for name, instructions in decoded.items():
        for ins in instructions:
            for operand in ins.operands:
                if operand.type == X86_OP_MEM and operand.mem.base == 0 and operand.mem.index == 0 and operand.mem.disp:
                    position_dependent_memory.append({"region": name, "address": ins.address, "instruction": f"{ins.mnemonic} {ins.op_str}"})
    if position_dependent_memory:
        raise ValueError(f"absolute memory operands found: {position_dependent_memory}")

    update = decoded["update"]
    prefix = [(ins.mnemonic, ins.op_str) for ins in update[:6]]
    if not (prefix[0][0] in {"pushfd", "pushf"} and prefix[1][0] in {"pushal", "pushad"} and prefix[2][0] == "call" and prefix[3] == ("pop", "edi") and prefix[4] == ("sub", "edi, 7") and prefix[5] == ("mov", "ebx, ecx")):
        raise ValueError(f"update PIC/prologue prefix mismatch: {prefix}")
    update_tail = [(ins.mnemonic, ins.op_str) for ins in update[-5:]]
    if update_tail[-4:-1] != [("push", "ebp"), ("mov", "ebp, esp"), ("sub", "esp, 0x44")] or update[-1].mnemonic != "jmp" or update[-1].operands[0].imm != UPDATE_RETURN_VA:
        raise ValueError(f"update original-prologue replay mismatch: {update_tail}")

    iat_delta = GET_ASYNC_KEY_STATE_IAT_VA - code_va
    async_calls = []
    memory_disps = set()
    for ins in update:
        for operand in ins.operands:
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_EDI:
                memory_disps.add(operand.mem.disp)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_MEM:
            mem = ins.operands[0].mem
            if mem.base == X86_REG_EDI and mem.disp == iat_delta:
                async_calls.append(ins.address)
    expected_async_call_count = 1 + 1 + 1 + len(KEY_MAP) + len(DIGIT_KEYS) + 1 + 1
    if len(async_calls) != expected_async_call_count:
        raise ValueError(f"GetAsyncKeyState call count mismatch: {len(async_calls)} != {expected_async_call_count}")
    async_vks = []
    for index, ins in enumerate(update):
        if ins.address not in async_calls:
            continue
        if index == 0 or update[index - 1].mnemonic != "push" or update[index - 1].operands[0].type != X86_OP_IMM:
            raise ValueError(f"GetAsyncKeyState call has no immediate VK push at {ins.address:#x}")
        async_vks.append(update[index - 1].operands[0].imm)
    expected_async_vks = [0x10, VK_HANGUL, VK_F1, *[vk for vk, _, _ in KEY_MAP], *DIGIT_KEYS, 8, VK_RETURN]
    if async_vks != expected_async_vks:
        raise ValueError(f"polled virtual-key order mismatch: {async_vks} != {expected_async_vks}")
    if 0x11 in async_vks:
        raise ValueError("Ctrl confirmation key is intercepted by the direct-input hook")
    mutable_delta = state_va - code_va
    input_mode_disp = mutable_delta + INPUT_MODE_LOCAL_OFF
    expected_state_disps = (
        {mutable_delta + vk for vk, _, _ in KEY_MAP}
        | {mutable_delta + vk for vk in DIGIT_KEYS}
        | {mutable_delta + VK_F1, mutable_delta + 8, mutable_delta + 0x100, mutable_delta + 0x101, input_mode_disp}
    )
    if not expected_state_disps.issubset(memory_disps):
        raise ValueError(f"mutable key-state displacements missing: {sorted(expected_state_disps - memory_disps)}")
    mode_toggles = [
        ins for ins in update
        if ins.mnemonic == "xor"
        and any(op.type == X86_OP_MEM and op.mem.base == X86_REG_EDI and op.mem.disp == input_mode_disp for op in ins.operands)
        and ins.op_str.endswith(", 1")
    ]
    if len(mode_toggles) != 2:
        raise ValueError(f"Hangul/English input-mode toggle count mismatch: {len(mode_toggles)}")
    hangul_call_index = async_vks.index(VK_HANGUL)
    hangul_call_address = async_calls[hangul_call_index]
    hangul_ins_index = next(i for i, ins in enumerate(update) if ins.address == hangul_call_address)
    hangul_window = update[hangul_ins_index + 1:hangul_ins_index + 4]
    hangul_low_bit_test = any(ins.mnemonic == "test" and ins.op_str in {"ax, 1", "eax, 1"} for ins in hangul_window)
    if not hangul_low_bit_test:
        raise ValueError("Hangul toggle does not use the press-event low bit")
    direct_calls = [
        ins.operands[0].imm for ins in update
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM
    ]
    compose_call_count = direct_calls.count(code_va + COMPOSE_OFF)
    ascii_call_count = direct_calls.count(code_va + ASCII_APPEND_OFF)
    if compose_call_count != len(KEY_MAP) or ascii_call_count != len(KEY_MAP) + len(DIGIT_KEYS):
        raise ValueError(
            f"direct input call fanout mismatch: compose={compose_call_count}, ascii={ascii_call_count}"
        )
    expected_fullwidth_words = set(FULLWIDTH_UPPER_RAW.values()) | set(FULLWIDTH_LOWER_RAW.values()) | set(FULLWIDTH_DIGIT_RAW.values())
    update_immediates = {
        ins.operands[1].imm & 0xFFFFFFFF
        for ins in update
        if ins.mnemonic == "mov" and len(ins.operands) == 2
        and ins.operands[0].type == X86_OP_REG and ins.operands[1].type == X86_OP_IMM
    }
    missing_fullwidth_words = sorted(expected_fullwidth_words - update_immediates)
    if missing_fullwidth_words:
        raise ValueError(f"fullwidth CP932 direct-input immediates missing: {missing_fullwidth_words[:10]}")
    nul_bearing_fullwidth_words = [word for word in expected_fullwidth_words if (word & 0xFF) == 0 or (word >> 8) == 0]
    if nul_bearing_fullwidth_words:
        raise ValueError(f"direct-input word contains an embedded NUL byte: {nul_bearing_fullwidth_words}")
    for disp in (GAME_INPUT_CURRENT_VA - code_va, GAME_INPUT_REPEAT_VA - code_va):
        if disp not in memory_disps:
            raise ValueError(f"game-command suppression displacement missing: {disp}")

    language_delta = LANGUAGE_MODE_VA - code_va
    force_japanese = authority.get("force_japanese_name_mode") is True
    for name in ("update", "delete", "select"):
        instructions = decoded[name]
        language_refs = [
            ins for ins in instructions
            if any(op.type == X86_OP_MEM and op.mem.base == X86_REG_EDI and op.mem.disp == language_delta for op in ins.operands)
        ]
        if not any(ins.mnemonic == "cmp" for ins in language_refs):
            raise ValueError(f"{name} does not guard on the Japanese two-byte editor flag")
        forced_writes = [ins for ins in language_refs if ins.mnemonic == "mov" and ins.op_str.endswith(", 1")]
        if bool(forced_writes) != force_japanese:
            raise ValueError(f"{name} force-language writes do not match authority")

    for name, expected_sub in (("delete", DELETE_OFF + 6),):
        ins = decoded[name]
        if len(ins) < 4 or ins[0].mnemonic not in {"pushal", "pushad"} or ins[1].mnemonic != "call" or (ins[2].mnemonic, ins[2].op_str) != ("pop", "edi") or (ins[3].mnemonic, ins[3].op_str) != ("sub", f"edi, 0x{expected_sub:x}"):
            raise ValueError(f"{name} PIC base mismatch")
    delete_jump_targets = {
        ins.operands[0].imm for ins in decoded["delete"]
        if ins.mnemonic == "jmp" and ins.operands and ins.operands[0].type == X86_OP_IMM
    }
    if not {DELETE_RETURN_VA, ENGLISH_DELETE_RETURN_VA}.issubset(delete_jump_targets):
        raise ValueError(f"delete Korean/English return targets missing: {delete_jump_targets}")
    delete_ops = [(ins.mnemonic, ins.op_str) for ins in decoded["delete"]]
    if ("mov", "eax, dword ptr [ebp - 0x2c]") not in delete_ops or ("mov", "ecx, dword ptr [ebx + 0x80]") not in delete_ops:
        raise ValueError("English delete path does not replay the overwritten original instructions")

    compose = decoded["compose"]
    cap_cmp_index = next((i for i, ins in enumerate(compose) if ins.mnemonic == "cmp" and ins.op_str == f"esi, {NAME_CAPACITY}"), None)
    last_write_index = next((i for i, ins in enumerate(compose) if ins.mnemonic == "mov" and "[ebx + esi*2 + 0x5e]" in ins.op_str), None)
    if cap_cmp_index is None or last_write_index is None or cap_cmp_index >= last_write_index:
        raise ValueError("compose capacity guard is not before replacement write")
    ascii_append = decoded["ascii_append"]
    ascii_cap_cmp_index = next((i for i, ins in enumerate(ascii_append) if ins.mnemonic == "cmp" and ins.op_str == f"esi, {NAME_CAPACITY}"), None)
    ascii_write_index = next((i for i, ins in enumerate(ascii_append) if ins.mnemonic == "mov" and "[ebx + esi*2 + 0x60]" in ins.op_str and ins.op_str.endswith(", ax")), None)
    if ascii_cap_cmp_index is None or ascii_write_index is None or ascii_cap_cmp_index >= ascii_write_index:
        raise ValueError("ASCII capacity guard is not before append write")

    select = decoded["select"]
    select_ops = [(ins.mnemonic, ins.op_str) for ins in select]
    if select_ops[:3] != [("call", f"0x{code_va + SELECT_OFF + 5:x}"), ("pop", "edi"), ("sub", f"edi, 0x{SELECT_OFF + 5:x}")]:
        raise ValueError(f"selector capacity-hook PIC prefix mismatch: {select_ops[:3]}")
    select_cap_index = next((i for i, ins in enumerate(select) if ins.mnemonic == "cmp" and ins.op_str == f"dword ptr [ebx + 0x80], {NAME_CAPACITY}"), None)
    select_language_index = next((i for i, ins in enumerate(select) if ins.mnemonic == "cmp" and "[edi" in ins.op_str), None)
    select_jump_targets = {
        ins.operands[0].imm for ins in select
        if ins.mnemonic == "jmp" and ins.operands and ins.operands[0].type == X86_OP_IMM
    }
    if select_cap_index is None or select_language_index is None or select_cap_index >= select_language_index:
        raise ValueError("selector six-character gate is missing or occurs after the language branch")
    if not {SELECT_HOOK_VA + len(SELECT_EXPECTED) + 6, ENGLISH_SELECT_RETURN_VA, SELECT_RETURN_VA}.issubset(select_jump_targets):
        raise ValueError(f"selector original-body/block return targets missing: {select_jump_targets}")

    enter_call_index = async_vks.index(VK_RETURN)
    enter_call_address = async_calls[enter_call_index]
    enter_ins_index = next(i for i, ins in enumerate(update) if ins.address == enter_call_address)
    enter_tail = update[enter_ins_index + 1:]
    enter_immediates = [
        (ins.mnemonic, ins.operands[1].imm & 0xFFFFFFFF)
        for ins in enter_tail
        if ins.mnemonic in {"and", "or"} and len(ins.operands) == 2 and ins.operands[1].type == X86_OP_IMM
    ]
    if enter_immediates.count(("and", 0xFFDFFFFF)) != 2 or enter_immediates.count(("or", 8)) != 1:
        raise ValueError(f"Enter select-to-complete bit transform mismatch: {enter_immediates}")
    enter_memory_disps = {
        op.mem.disp for ins in enter_tail for op in ins.operands
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_EDI
    }
    if not {GAME_INPUT_CURRENT_VA - code_va, GAME_INPUT_REPEAT_VA - code_va}.issubset(enter_memory_disps):
        raise ValueError("Enter transform does not update both current/repeat game-command words")

    def append_ascii(text: list[str], value: str, capacity: int = 6) -> None:
        if len(text) < capacity:
            text.append(value)

    english_lower = []
    for ch in "ａｂｃｑｅｚ":
        append_ascii(english_lower, ch)
    english_shifted = []
    for ch in "ＡｂＣ":
        append_ascii(english_shifted, ch)
    numeric = []
    for ch in "０１２３４５":
        append_ascii(numeric, ch)
    mixed = list(type_keys("als"))
    for ch in "Ｑｅ１２":
        append_ascii(mixed, ch)
    if "".join(english_lower) != "ａｂｃｑｅｚ" or "".join(english_shifted) != "ＡｂＣ":
        raise ValueError("direct fullwidth English input model failed")
    if "".join(numeric) != "０１２３４５":
        raise ValueError("direct fullwidth numeric input model failed")
    if "".join(mixed) != "민Ｑｅ１２":
        raise ValueError(f"mixed Korean/English/numeric model failed: {''.join(mixed)!r}")
    ascii_full = list("ａｂｃｄｅｆ")
    append_ascii(ascii_full, "７")
    if "".join(ascii_full) != "ａｂｃｄｅｆ":
        raise ValueError("fullwidth direct-input capacity guard mutated a full buffer")

    report = {
        "schema": "criminal-girls.two-set-name-input-verification.v8",
        "status": "PASS",
        "literal_exe_sha256": sha256(literal),
        "patched_exe_sha256": sha256(patched),
        "font_report_sha256": sha256(args.font_report.read_bytes()),
        "patch_report_sha256": sha256(args.patch_report.read_bytes()),
        "section_count_before": 6,
        "section_count_after": 8,
        "rx_code_section": True,
        "rw_non_executable_state_section": True,
        "old_image_changed_byte_count": len(changed_old),
        "old_image_outside_allowlist_count": len(outside),
        "neutralized_select_relocation_count": len(neutralized),
        "original_select_relocation_count": len(patched_select_relocations),
        "selector_absolute_padding_relocation_count": len(patched_select_absolute_padding),
        "selector_capacity_hook_installed": True,
        "original_selector_body_path_preserved": True,
        "original_selector_path_preserved": True,
        "active_hook_highlow_relocation_count": len(active_hook_relocations),
        "aslr_simulation_deltas": list(aslr_deltas),
        "aslr_hook_targets_stable": True,
        "hook_targets": hook_targets,
        "position_dependent_memory_operand_count": 0,
        "get_async_key_state_call_count": len(async_calls),
        "keyboard_key_count": len(KEY_MAP),
        "english_letter_key_count": len(KEY_MAP),
        "numeric_key_count": len(DIGIT_KEYS),
        "direct_input_jamo_count": len(INPUT_JAMO),
        "hangul_english_toggle_vk": "0x15",
        "input_mode_initial_korean": True,
        "visible_basic_selector_jamo_count": 0,
        "visible_selector_mode": "original_japanese",
        "standard_wansung_state_count": len(standard),
        "transition_count": transition_count,
        "decomposition_entry_count": sum(bool(x) for x in decomp),
        "trace_results": trace_results,
        "delete_trace": delete_trace,
        "capacity_guard_pass": True,
        "direct_qwerty_pass": True,
        "hangul_english_toggle_pass": True,
        "hangul_low_bit_press_event_pass": True,
        "f1_fallback_toggle_pass": True,
        "direct_english_lowercase_pass": True,
        "direct_english_shift_uppercase_pass": True,
        "direct_numeric_input_pass": True,
        "direct_english_numeric_cp932_fullwidth_pass": True,
        "direct_input_embedded_nul_count": 0,
        "ctrl_confirmation_not_intercepted_pass": True,
        "enter_completion_key_polled_pass": True,
        "enter_select_bit_cleared_pass": True,
        "enter_completion_bit_set_pass": True,
        "mouse_click_japanese_input_preserved": True,
        "all_append_paths_six_character_capped": True,
        "name_capacity": NAME_CAPACITY,
        "name_help_text": NAME_HELP_TEXT,
        "name_help_legend": NAME_HELP_LEGEND,
        "name_help_pointer_relocated_pass": True,
        "name_help_nul_terminated_pass": True,
        "name_help_highlow_relocation_preserved": True,
        "name_help_aslr_simulation_pass": True,
        "click_japanese_input_help_pass": True,
        "enter_completion_help_pass": True,
        "q_e_direct_input_suppression_pass": True,
        "shift_double_jamo_pass": True,
        "sequential_compound_vowel_final_pass": True,
        "backspace_decomposition_pass": True,
        "game_command_suppression_present": True,
        "japanese_two_byte_editor_only": True,
        "english_one_byte_editor_original_paths_preserved": True,
        "force_japanese_name_mode": force_japanese,
    }
    atomic_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())