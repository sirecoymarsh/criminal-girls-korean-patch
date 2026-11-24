#!/usr/bin/env python3
"""Build a PIC x86 two-set Hangul physical-keyboard composition engine."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import pefile

# Prefer the project-local bundled runtime; the fallback supports the lightweight C worktree.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_TOOL_ROOT = PROJECT_ROOT / "tools" / "python"
if not REAL_TOOL_ROOT.exists():
    REAL_TOOL_ROOT = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko\tools\python")
if str(REAL_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(REAL_TOOL_ROOT))
from keystone import Ks, KS_ARCH_X86, KS_MODE_32  # noqa: E402

IMAGE_BASE = 0x400000
UPDATE_HOOK_VA = 0x49C220
UPDATE_RETURN_VA = 0x49C226
SELECT_HOOK_VA = 0x49C7B1
DELETE_HOOK_VA = 0x49C714
SELECT_RETURN_VA = 0x49C8E1
DELETE_RETURN_VA = 0x49C786
NAME_TABLE_VA = 0x53CF90
GET_ASYNC_KEY_STATE_IAT_VA = 0x5392BC
GAME_INPUT_CURRENT_VA = 0x5F5EFC
GAME_INPUT_REPEAT_VA = 0x5F5F00
LANGUAGE_MODE_VA = 0x5C9AAA
ENGLISH_SELECT_RETURN_VA = 0x49C870
ENGLISH_DELETE_RETURN_VA = 0x49C71D
UPDATE_EXPECTED = bytes.fromhex("558bec83ec44")
SELECT_EXPECTED = bytes.fromhex("803daa9a5c0000")
DELETE_EXPECTED = bytes.fromhex("8b45d48b8b")
SECTION_NAME = b".koinput"
STATE_SECTION_NAME = b".kostate"

UPDATE_OFF = 0x0000
COMPOSE_OFF = 0x1000
DELETE_ROUTINE_OFF = 0x1400
ASCII_APPEND_OFF = 0x1800
DELETE_OFF = 0x1C00
SELECT_OFF = 0x1E00
DATA_OFF = 0x2000
INPUT_OFF = DATA_OFF
STATE_OFF = 0x2300
KEY_STATE_LOCAL_OFF = 0x000
SHIFT_STATE_LOCAL_OFF = 0x100
ANY_KEY_DOWN_LOCAL_OFF = 0x101
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
FINALS = [""] + "\u3131 \u3132 \u3133 \u3134 \u3135 \u3136 \u3137 \u3139 \u313a \u313b \u313c \u313d \u313e \u313f \u3140 \u3141 \u3142 \u3144 \u3145 \u3146 \u3147 \u3148 \u314a \u314b \u314c \u314d \u314e".split()
COMPOUND_FINALS = "\u3133 \u3135 \u3136 \u313a \u313b \u313c \u313d \u313e \u313f \u3140 \u3144".split()
BASIC_CONSONANTS = "\u3131 \u3134 \u3137 \u3139 \u3141 \u3142 \u3145 \u3147 \u3148 \u314a \u314b \u314c \u314d \u314e".split()
BASIC_VOWELS = "\u314f \u3150 \u3151 \u3153 \u3154 \u3155 \u3157 \u315b \u315c \u3160 \u3161 \u3163".split()
SHIFT_INPUTS = "\u3132 \u3138 \u3143 \u3146 \u3149 \u3152 \u3156".split()
INPUT_JAMO = BASIC_CONSONANTS + BASIC_VOWELS + SHIFT_INPUTS
INPUT_COUNT = len(INPUT_JAMO)

L_INDEX = {ch: i for i, ch in enumerate(LEADS)}
V_INDEX = {ch: i for i, ch in enumerate(MEDIALS)}
T_INDEX = {ch: i for i, ch in enumerate(FINALS) if ch}
DOUBLE_INITIAL = {(a, a): b for a, b in zip("\u3131 \u3137 \u3142 \u3145 \u3148".split(), "\u3132 \u3138 \u3143 \u3146 \u3149".split())}
VOWEL_COMBINE = {
    ("\u3157", "\u314f"): "\u3158", ("\u3157", "\u3150"): "\u3159", ("\u3157", "\u3163"): "\u315a",
    ("\u315c", "\u3153"): "\u315d", ("\u315c", "\u3154"): "\u315e", ("\u315c", "\u3163"): "\u315f",
    ("\u3158", "\u3163"): "\u3159", ("\u315d", "\u3163"): "\u315e",
    ("\u3161", "\u3163"): "\u3162",
}
VOWEL_DECOMP = {"\u3158": "\u3157", "\u3159": "\u3157", "\u315a": "\u3157", "\u315d": "\u315c", "\u315e": "\u315c", "\u315f": "\u315c", "\u3162": "\u3161", "\u3152": "\u3151", "\u3156": "\u3155"}
FINAL_COMBINE = {
    ("\u3131", "\u3145"): "\u3133", ("\u3134", "\u3148"): "\u3135", ("\u3134", "\u314e"): "\u3136",
    ("\u3139", "\u3131"): "\u313a", ("\u3139", "\u3141"): "\u313b", ("\u3139", "\u3142"): "\u313c",
    ("\u3139", "\u3145"): "\u313d", ("\u3139", "\u314c"): "\u313e", ("\u3139", "\u314d"): "\u313f", ("\u3139", "\u314e"): "\u3140",
    ("\u3142", "\u3145"): "\u3144",
}
FINAL_SPLIT = {
    "\u3131": ("", "\u3131"), "\u3132": ("", "\u3132"), "\u3133": ("\u3131", "\u3145"), "\u3134": ("", "\u3134"),
    "\u3135": ("\u3134", "\u3148"), "\u3136": ("\u3134", "\u314e"), "\u3137": ("", "\u3137"), "\u3139": ("", "\u3139"),
    "\u313a": ("\u3139", "\u3131"), "\u313b": ("\u3139", "\u3141"), "\u313c": ("\u3139", "\u3142"), "\u313d": ("\u3139", "\u3145"),
    "\u313e": ("\u3139", "\u314c"), "\u313f": ("\u3139", "\u314d"), "\u3140": ("\u3139", "\u314e"), "\u3141": ("", "\u3141"),
    "\u3142": ("", "\u3142"), "\u3144": ("\u3142", "\u3145"), "\u3145": ("", "\u3145"), "\u3146": ("", "\u3146"),
    "\u3147": ("", "\u3147"), "\u3148": ("", "\u3148"), "\u314a": ("", "\u314a"), "\u314b": ("", "\u314b"),
    "\u314c": ("", "\u314c"), "\u314d": ("", "\u314d"), "\u314e": ("", "\u314e"),
}
JAMO_DECOMP = {
    "\u3132": "\u3131", "\u3138": "\u3137", "\u3143": "\u3142", "\u3146": "\u3145", "\u3149": "\u3148",
    "\u3133": "\u3131", "\u3135": "\u3134", "\u3136": "\u3134", "\u313a": "\u3139", "\u313b": "\u3139", "\u313c": "\u3139",
    "\u313d": "\u3139", "\u313e": "\u3139", "\u313f": "\u3139", "\u3140": "\u3139", "\u3144": "\u3142", **VOWEL_DECOMP,
}

# VK, normal Jamo, shifted Jamo.  This is the standard Korean two-set layout.
KEY_MAP = [
    (0x51, "\u3142", "\u3143"), (0x57, "\u3148", "\u3149"), (0x45, "\u3137", "\u3138"),
    (0x52, "\u3131", "\u3132"), (0x54, "\u3145", "\u3146"), (0x59, "\u315b", None),
    (0x55, "\u3155", None), (0x49, "\u3151", None), (0x4F, "\u3150", "\u3152"), (0x50, "\u3154", "\u3156"),
    (0x41, "\u3141", None), (0x53, "\u3134", None), (0x44, "\u3147", None), (0x46, "\u3139", None),
    (0x47, "\u314e", None), (0x48, "\u3157", None), (0x4A, "\u3153", None), (0x4B, "\u314f", None),
    (0x4C, "\u3163", None), (0x5A, "\u314b", None), (0x58, "\u314c", None), (0x43, "\u314a", None),
    (0x56, "\u314d", None), (0x42, "\u3160", None), (0x4E, "\u315c", None), (0x4D, "\u3161", None),
]


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


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


def compose(l: int, v: int, t: int = 0) -> str:
    return chr(0xAC00 + (l * 21 + v) * 28 + t)


def split_syllable(ch: str) -> tuple[int, int, int] | None:
    value = ord(ch) - 0xAC00
    if not 0 <= value < 11172:
        return None
    return value // 588, (value % 588) // 28, value % 28


def transition(current: str | None, incoming: str, supported: set[str]) -> tuple[str | None, str | None]:
    if current is None:
        return None, incoming
    parsed = split_syllable(current)
    if incoming in V_INDEX:
        if current in L_INDEX:
            result = compose(L_INDEX[current], V_INDEX[incoming])
            return (result, None) if result in supported else (None, incoming)
        if current in V_INDEX:
            result = VOWEL_COMBINE.get((current, incoming))
            return (result, None) if result in supported else (None, incoming)
        if parsed:
            l, v, t = parsed
            if t == 0:
                combined = VOWEL_COMBINE.get((MEDIALS[v], incoming))
                if combined:
                    result = compose(l, V_INDEX[combined])
                    if result in supported:
                        return result, None
                return None, incoming
            final = FINALS[t]
            remain, moved = FINAL_SPLIT.get(final, ("", final))
            if moved in L_INDEX:
                previous = compose(l, v, T_INDEX.get(remain, 0))
                following = compose(L_INDEX[moved], V_INDEX[incoming])
                if previous in supported and following in supported:
                    return previous, following
            return None, incoming
        return None, incoming
    if current in L_INDEX:
        doubled = DOUBLE_INITIAL.get((current, incoming))
        if doubled and doubled in supported:
            return doubled, None
        return None, incoming
    if parsed:
        l, v, t = parsed
        if t == 0 and incoming in T_INDEX:
            result = compose(l, v, T_INDEX[incoming])
            return (result, None) if result in supported else (None, incoming)
        if t:
            combined = FINAL_COMBINE.get((FINALS[t], incoming))
            if combined:
                result = compose(l, v, T_INDEX[combined])
                if result in supported:
                    return result, None
        return None, incoming
    return None, incoming


def decompose_char(ch: str, supported: set[str]) -> str | None:
    parsed = split_syllable(ch)
    if parsed:
        l, v, t = parsed
        if t:
            simpler = JAMO_DECOMP.get(FINALS[t])
            result = compose(l, v, T_INDEX.get(simpler, 0))
            return result if result in supported else None
        vowel = MEDIALS[v]
        if vowel in VOWEL_DECOMP:
            result = compose(l, V_INDEX[VOWEL_DECOMP[vowel]])
            return result if result in supported else None
        return LEADS[l]
    return JAMO_DECOMP.get(ch)


def build_tables(font_report: dict) -> tuple[dict, bytes, bytes, bytes, bytes]:
    slots = font_report.get("repurposed_slots", [])
    char_to_raw = {row["char"]: raw_word(int(row["sjis"], 16)) for row in slots}
    state_jamo = set(LEADS + MEDIALS + COMPOUND_FINALS)
    missing_input = [ch for ch in INPUT_JAMO if ch not in char_to_raw]
    if missing_input:
        raise ValueError(f"font report is missing input Jamo: {missing_input}")
    supported = {ch for ch in char_to_raw if split_syllable(ch) or ch in state_jamo}
    standard = []
    for cp in range(0xAC00, 0xD7A4):
        ch = chr(cp)
        try:
            if len(ch.encode("euc_kr")) == 2:
                standard.append(ch)
        except UnicodeEncodeError:
            pass
    missing_standard = [ch for ch in standard if ch not in supported]
    if missing_standard:
        raise ValueError(f"font report is missing {len(missing_standard)} Wansung syllables")
    state_chars = sorted(supported, key=ord)
    states: list[str | None] = [None] + state_chars
    state_index = [0] * 65536
    for index, ch in enumerate(state_chars, 1):
        state_index[char_to_raw[ch]] = index
    input_blob = struct.pack(f"<{INPUT_COUNT}H", *(char_to_raw[ch] for ch in INPUT_JAMO))
    state_blob = struct.pack("<65536H", *state_index)
    transition_words = []
    for current in states:
        for incoming in INPUT_JAMO:
            previous, new = transition(current, incoming, supported)
            transition_words.append((char_to_raw[previous] if previous else 0) | ((char_to_raw[new] if new else 0) << 16))
    transition_blob = struct.pack(f"<{len(transition_words)}I", *transition_words)
    decomp = [0] * 65536
    for ch in state_chars:
        simpler = decompose_char(ch, supported)
        if simpler:
            decomp[char_to_raw[ch]] = char_to_raw[simpler]
    decomp_blob = struct.pack("<65536H", *decomp)
    meta = {
        "slot_count": len(slots),
        "supported_composition_state_count": len(state_chars),
        "standard_wansung_count": len(standard),
        "direct_basic_jamo_count": len(BASIC_CONSONANTS) + len(BASIC_VOWELS),
        "direct_input_jamo_count": INPUT_COUNT,
        "transition_count": len(transition_words),
        "decomposition_entry_count": sum(bool(x) for x in decomp),
    }
    return meta, input_blob, state_blob, transition_blob, decomp_blob


def assemble(section_va: int, state_va: int, trans_off: int, decomp_off: int, force_japanese_name_mode: bool = False) -> dict[str, bytes]:
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    iat_delta = GET_ASYNC_KEY_STATE_IAT_VA - section_va
    current_delta = GAME_INPUT_CURRENT_VA - section_va
    repeat_delta = GAME_INPUT_REPEAT_VA - section_va
    language_delta = LANGUAGE_MODE_VA - section_va
    force_language = f"mov byte ptr [edi + {language_delta}], 1" if force_japanese_name_mode else ""
    mutable_delta = state_va - section_va
    key_state_off = mutable_delta + KEY_STATE_LOCAL_OFF
    shift_state_off = mutable_delta + SHIFT_STATE_LOCAL_OFF
    any_key_down_off = mutable_delta + ANY_KEY_DOWN_LOCAL_OFF
    input_mode_off = mutable_delta + INPUT_MODE_LOCAL_OFF
    input_index = {ch: i for i, ch in enumerate(INPUT_JAMO)}
    letter_blocks = []
    for number, (vk, normal, shifted) in enumerate(KEY_MAP):
        shifted_code = ""
        if shifted is not None:
            shifted_code = f"cmp byte ptr [edi + {shift_state_off}], 0\nje key_{number}_korean_input\nmov eax, {input_index[shifted]}"
        letter_blocks.append(f"""
            push {vk}
            call dword ptr [edi + {iat_delta}]
            test ax, ax
            jns key_{number}_up
            mov byte ptr [edi + {any_key_down_off}], 1
            cmp byte ptr [edi + {key_state_off + vk}], 0
            jne key_{number}_done
            mov byte ptr [edi + {key_state_off + vk}], 1
            cmp byte ptr [edi + {input_mode_off}], 0
            jne key_{number}_english
            mov eax, {input_index[normal]}
            {shifted_code}
          key_{number}_korean_input:
            call {section_va + COMPOSE_OFF}
            jmp key_{number}_done
          key_{number}_english:
            mov eax, {FULLWIDTH_LOWER_RAW[vk]}
            cmp byte ptr [edi + {shift_state_off}], 0
            je key_{number}_ascii_input
            mov eax, {FULLWIDTH_UPPER_RAW[vk]}
          key_{number}_ascii_input:
            call {section_va + ASCII_APPEND_OFF}
            jmp key_{number}_done
          key_{number}_up:
            mov byte ptr [edi + {key_state_off + vk}], 0
          key_{number}_done:
        """)
    digit_blocks = []
    for number, vk in enumerate(DIGIT_KEYS):
        digit_blocks.append(f"""
            push {vk}
            call dword ptr [edi + {iat_delta}]
            test ax, ax
            jns digit_{number}_up
            mov byte ptr [edi + {any_key_down_off}], 1
            cmp byte ptr [edi + {key_state_off + vk}], 0
            jne digit_{number}_done
            mov byte ptr [edi + {key_state_off + vk}], 1
            mov eax, {FULLWIDTH_DIGIT_RAW[vk]}
            call {section_va + ASCII_APPEND_OFF}
            jmp digit_{number}_done
          digit_{number}_up:
            mov byte ptr [edi + {key_state_off + vk}], 0
          digit_{number}_done:
        """)
    update_asm = f"""
        pushfd
        pushad
        call update_base
      update_base:
        pop edi
        sub edi, 7
        mov ebx, ecx
        {force_language}
        cmp byte ptr [edi + {language_delta}], 0
        je update_done
        mov byte ptr [edi + {any_key_down_off}], 0
        push 0x10
        call dword ptr [edi + {iat_delta}]
        test ax, ax
        jns shift_up
        mov byte ptr [edi + {shift_state_off}], 1
        jmp shift_done
      shift_up:
        mov byte ptr [edi + {shift_state_off}], 0
      shift_done:
        push {VK_HANGUL}
        call dword ptr [edi + {iat_delta}]
        test ax, 1
        jz hangul_mode_done
        mov byte ptr [edi + {any_key_down_off}], 1
        xor byte ptr [edi + {input_mode_off}], 1
      hangul_mode_done:
        push {VK_F1}
        call dword ptr [edi + {iat_delta}]
        test ax, ax
        jns f1_mode_up
        mov byte ptr [edi + {any_key_down_off}], 1
        cmp byte ptr [edi + {key_state_off + VK_F1}], 0
        jne f1_mode_done
        mov byte ptr [edi + {key_state_off + VK_F1}], 1
        xor byte ptr [edi + {input_mode_off}], 1
        jmp f1_mode_done
      f1_mode_up:
        mov byte ptr [edi + {key_state_off + VK_F1}], 0
      f1_mode_done:
        {''.join(letter_blocks)}
        {''.join(digit_blocks)}
        push 8
        call dword ptr [edi + {iat_delta}]
        test ax, ax
        jns backspace_up
        mov byte ptr [edi + {any_key_down_off}], 1
        cmp byte ptr [edi + {key_state_off + 8}], 0
        jne backspace_done
        mov byte ptr [edi + {key_state_off + 8}], 1
        call {section_va + DELETE_ROUTINE_OFF}
        jmp backspace_done
      backspace_up:
        mov byte ptr [edi + {key_state_off + 8}], 0
      backspace_done:
        cmp byte ptr [edi + {any_key_down_off}], 0
        je enter_key
        mov dword ptr [edi + {current_delta}], 0
        mov dword ptr [edi + {repeat_delta}], 0
      enter_key:
        push {VK_RETURN}
        call dword ptr [edi + {iat_delta}]
        test ax, ax
        jns update_done
        mov eax, dword ptr [edi + {current_delta}]
        and eax, 0xffdfffff
        or eax, 8
        mov dword ptr [edi + {current_delta}], eax
        mov eax, dword ptr [edi + {repeat_delta}]
        and eax, 0xffdfffff
        mov dword ptr [edi + {repeat_delta}], eax
      update_done:
        popad
        popfd
        push ebp
        mov ebp, esp
        sub esp, 0x44
        jmp {UPDATE_RETURN_VA}
    """
    compose_asm = f"""
        mov ecx, eax
        mov esi, dword ptr [ebx + 0x80]
        xor eax, eax
        test esi, esi
        jle compose_state
        movzx eax, word ptr [ebx + esi*2 + 0x5e]
        movzx eax, word ptr [edi + {STATE_OFF} + eax*2]
      compose_state:
        imul eax, eax, {INPUT_COUNT}
        add eax, ecx
        mov edx, dword ptr [edi + {trans_off} + eax*4]
        mov ecx, edx
        shr ecx, 16
        test cx, cx
        jz compose_replace
        cmp esi, {NAME_CAPACITY}
        jge compose_return
      compose_replace:
        test esi, esi
        jle compose_append
        test dx, dx
        jz compose_append
        mov word ptr [ebx + esi*2 + 0x5e], dx
      compose_append:
        mov edx, ecx
        test dx, dx
        jz compose_return
        mov word ptr [ebx + esi*2 + 0x60], dx
        inc esi
        mov dword ptr [ebx + 0x80], esi
        cmp esi, {NAME_CAPACITY}
        jge compose_return
        mov word ptr [ebx + esi*2 + 0x60], 0
      compose_return:
        ret
    """
    delete_routine_asm = f"""
        mov ecx, dword ptr [ebx + 0x80]
        test ecx, ecx
        jle delete_routine_return
        movzx eax, word ptr [ebx + ecx*2 + 0x5e]
        movzx edx, word ptr [edi + {decomp_off} + eax*2]
        test dx, dx
        jz delete_whole
        mov word ptr [ebx + ecx*2 + 0x5e], dx
        jmp delete_routine_return
      delete_whole:
        dec ecx
        mov dword ptr [ebx + 0x80], ecx
        mov word ptr [ebx + ecx*2 + 0x60], 0
      delete_routine_return:
        ret
    """
    ascii_append_asm = f"""
        mov esi, dword ptr [ebx + 0x80]
        cmp esi, {NAME_CAPACITY}
        jge ascii_append_return
        mov word ptr [ebx + esi*2 + 0x60], ax
        inc esi
        mov dword ptr [ebx + 0x80], esi
        cmp esi, {NAME_CAPACITY}
        jge ascii_append_return
        mov word ptr [ebx + esi*2 + 0x60], 0
      ascii_append_return:
        ret
    """
    delete_asm = f"""
        pushad
        call delete_base
      delete_base:
        pop edi
        sub edi, {DELETE_OFF + 6}
        {force_language}
        cmp byte ptr [edi + {language_delta}], 0
        je delete_english
        call {section_va + DELETE_ROUTINE_OFF}
        popad
        jmp {DELETE_RETURN_VA}
      delete_english:
        popad
        mov eax, dword ptr [ebp - 0x2c]
        mov ecx, dword ptr [ebx + 0x80]
        jmp {ENGLISH_DELETE_RETURN_VA}
    """
    select_asm = f"""
        call select_base
      select_base:
        pop edi
        sub edi, {SELECT_OFF + 5}
        {force_language}
        cmp dword ptr [ebx + 0x80], {NAME_CAPACITY}
        jge select_blocked
        cmp byte ptr [edi + {language_delta}], 0
        je select_english
        jmp {SELECT_HOOK_VA + len(SELECT_EXPECTED) + 6}
      select_english:
        jmp {ENGLISH_SELECT_RETURN_VA}
      select_blocked:
        jmp {SELECT_RETURN_VA}
    """
    specs = {
        "update": (update_asm, section_va + UPDATE_OFF),
        "compose": (compose_asm, section_va + COMPOSE_OFF),
        "delete_routine": (delete_routine_asm, section_va + DELETE_ROUTINE_OFF),
        "ascii_append": (ascii_append_asm, section_va + ASCII_APPEND_OFF),
        "delete": (delete_asm, section_va + DELETE_OFF),
        "select": (select_asm, section_va + SELECT_OFF),
    }
    return {name: bytes(ks.asm(text, addr=address)[0]) for name, (text, address) in specs.items()}


def patch_jump(data: bytearray, pe: pefile.PE, source_va: int, destination_va: int, expected: bytes) -> tuple[int, list[int]]:
    offset = pe.get_offset_from_rva(source_va - pe.OPTIONAL_HEADER.ImageBase)
    actual = bytes(data[offset:offset + len(expected)])
    if actual != expected:
        raise ValueError(f"hook source mismatch at {source_va:08X}: {actual.hex()} != {expected.hex()}")
    rel = destination_va - (source_va + 5)
    patch = b"\xE9" + struct.pack("<i", rel) + b"\x90" * (len(expected) - 5)
    data[offset:offset + len(expected)] = patch
    return offset, list(range(offset, offset + len(expected)))


def neutralize_overlapping_base_relocations(
    data: bytearray, pe: pefile.PE, source_va: int, patch_size: int
) -> list[dict]:
    """Turn stale HIGHLOW fixups inside a rewritten hook into ABSOLUTE padding.

    A rel32 JMP is position independent.  If the overwritten instruction used an
    absolute address, however, its old relocation entry would make the loader
    add the ASLR delta to bytes inside the new displacement and corrupt the
    target.
    """
    image_base = pe.OPTIONAL_HEADER.ImageBase
    start_rva = source_va - image_base
    end_rva = start_rva + patch_size
    disabled: list[dict] = []
    for block in pe.DIRECTORY_ENTRY_BASERELOC:
        entries_offset = block.struct.get_file_offset() + 8
        for index, entry in enumerate(block.entries):
            entry_offset = entries_offset + index * 2
            word = struct.unpack_from("<H", data, entry_offset)[0]
            reloc_type = word >> 12
            reloc_rva = block.struct.VirtualAddress + (word & 0x0FFF)
            if reloc_type == 3 and reloc_rva < end_rva and reloc_rva + 4 > start_rva:
                struct.pack_into("<H", data, entry_offset, word & 0x0FFF)
                disabled.append({
                    "rva": reloc_rva,
                    "va": image_base + reloc_rva,
                    "file_offset": entry_offset,
                    "type_before": 3,
                    "type_after": 0,
                    "reason": "overlaps position-independent rel32 hook",
                })
    return disabled


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--exe-report", type=Path, required=True)
    ap.add_argument("--font-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--force-japanese-name-mode", action="store_true", help="Runtime-QA only: force the Japanese two-byte name editor while the screen is active")
    args = ap.parse_args()
    source = args.exe.read_bytes()
    exe_report = json.loads(args.exe_report.read_text(encoding="utf-8-sig"))
    font_report = json.loads(args.font_report.read_text(encoding="utf-8-sig"))
    if exe_report.get("status") != "PASS" or exe_report.get("output_sha256") != sha256(source):
        raise ValueError("literal executable report does not authorize the input")
    if font_report.get("passed") is not True:
        raise ValueError("font report did not pass")
    if INPUT_COUNT != 33 or len(set(INPUT_JAMO)) != 33 or len(KEY_MAP) != 26:
        raise ValueError("two-set input table contract failed")
    pe = pefile.PE(data=source, fast_load=False)
    if pe.OPTIONAL_HEADER.ImageBase != IMAGE_BASE or pe.FILE_HEADER.NumberOfSections != 6:
        raise ValueError("unexpected PE image base or section count")
    if any(s.Name.rstrip(b"\0") in {SECTION_NAME, STATE_SECTION_NAME} for s in pe.sections):
        raise ValueError("Korean input sections already exist")
    section_table_end = pe.sections[-1].get_file_offset() + 40
    if section_table_end + 80 > pe.OPTIONAL_HEADER.SizeOfHeaders:
        raise ValueError("no room for two additional section headers")
    meta, input_blob, state_blob, trans_blob, decomp_blob = build_tables(font_report)
    help_blob = encode_runtime_text(NAME_HELP_TEXT, font_report) + b"\0"
    trans_off = align(STATE_OFF + len(state_blob), 16)
    decomp_off = align(trans_off + len(trans_blob), 16)
    help_off = align(decomp_off + len(decomp_blob), 16)
    code_virtual_size = help_off + len(help_blob)
    section_alignment = pe.OPTIONAL_HEADER.SectionAlignment
    file_alignment = pe.OPTIONAL_HEADER.FileAlignment
    section_rva = align(max(s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData) for s in pe.sections), section_alignment)
    section_va = pe.OPTIONAL_HEADER.ImageBase + section_rva
    state_section_rva = align(section_rva + max(code_virtual_size, align(code_virtual_size, file_alignment)), section_alignment)
    state_section_va = pe.OPTIONAL_HEADER.ImageBase + state_section_rva
    code = assemble(section_va, state_section_va, trans_off, decomp_off, args.force_japanese_name_mode)
    limits = {"update": COMPOSE_OFF, "compose": DELETE_ROUTINE_OFF, "delete_routine": ASCII_APPEND_OFF, "ascii_append": DELETE_OFF, "delete": SELECT_OFF, "select": DATA_OFF}
    offsets = {"update": UPDATE_OFF, "compose": COMPOSE_OFF, "delete_routine": DELETE_ROUTINE_OFF, "ascii_append": ASCII_APPEND_OFF, "delete": DELETE_OFF, "select": SELECT_OFF}
    for name, blob in code.items():
        if offsets[name] + len(blob) > limits[name]:
            raise ValueError(f"{name} code exceeds fixed layout: {len(blob)}")
    section = bytearray(code_virtual_size)
    for name, blob in code.items():
        section[offsets[name]:offsets[name] + len(blob)] = blob
    section[INPUT_OFF:INPUT_OFF + len(input_blob)] = input_blob
    section[STATE_OFF:STATE_OFF + len(state_blob)] = state_blob
    section[trans_off:trans_off + len(trans_blob)] = trans_blob
    section[decomp_off:decomp_off + len(decomp_blob)] = decomp_blob
    section[help_off:help_off + len(help_blob)] = help_blob
    mutable_state = bytes(MUTABLE_STATE_SIZE)
    raw_size = align(len(section), file_alignment)
    raw_pointer = align(len(source), file_alignment)
    state_raw_size = align(len(mutable_state), file_alignment)
    state_raw_pointer = raw_pointer + raw_size
    patched = bytearray(source)
    patched.extend(b"\0" * (raw_pointer - len(patched)))
    patched.extend(section)
    patched.extend(b"\0" * (raw_size - len(section)))
    if len(patched) != state_raw_pointer:
        raise ValueError("mutable-state raw pointer calculation failed")
    patched.extend(mutable_state)
    patched.extend(b"\0" * (state_raw_size - len(mutable_state)))
    header_offset = pe.sections[-1].get_file_offset() + 40
    patched[header_offset:header_offset + 40] = struct.pack("<8sIIIIIIHHI", SECTION_NAME, len(section), section_rva, raw_size, raw_pointer, 0, 0, 0, 0, 0x60000020)
    patched[header_offset + 40:header_offset + 80] = struct.pack("<8sIIIIIIHHI", STATE_SECTION_NAME, len(mutable_state), state_section_rva, state_raw_size, state_raw_pointer, 0, 0, 0, 0, 0xC0000040)
    struct.pack_into("<H", patched, pe.FILE_HEADER.get_field_absolute_offset("NumberOfSections"), 8)
    new_size_of_image = align(state_section_rva + len(mutable_state), section_alignment)
    struct.pack_into("<I", patched, pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfImage"), new_size_of_image)
    struct.pack_into("<I", patched, pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfCode"), pe.OPTIONAL_HEADER.SizeOfCode + raw_size)
    struct.pack_into("<I", patched, pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfInitializedData"), pe.OPTIONAL_HEADER.SizeOfInitializedData + state_raw_size)
    patched_pe = pefile.PE(data=bytes(patched), fast_load=False)
    hooks = []
    allow = []
    neutralized_relocations = []
    help_pointer_offset = patched_pe.get_offset_from_rva(NAME_HELP_POINTER_IMMEDIATE_VA - IMAGE_BASE)
    original_help_pointer = struct.unpack_from("<I", source, help_pointer_offset)[0]
    if original_help_pointer != NAME_HELP_ORIGINAL_TARGET_VA:
        raise ValueError(f"name-help source pointer mismatch: {original_help_pointer:08X}")
    help_pointer_rva = NAME_HELP_POINTER_IMMEDIATE_VA - IMAGE_BASE
    help_pointer_relocations = [
        entry for block in patched_pe.DIRECTORY_ENTRY_BASERELOC for entry in block.entries
        if entry.type == 3 and entry.rva == help_pointer_rva
    ]
    if len(help_pointer_relocations) != 1:
        raise ValueError(f"name-help HIGHLOW relocation count mismatch: {len(help_pointer_relocations)}")
    relocated_help_va = section_va + help_off
    struct.pack_into("<I", patched, help_pointer_offset, relocated_help_va)
    allow.extend(range(help_pointer_offset, help_pointer_offset + 4))
    for name, source_va, target_off, expected in (
        ("name_update_two_set", UPDATE_HOOK_VA, UPDATE_OFF, UPDATE_EXPECTED),
        ("delete_decompose", DELETE_HOOK_VA, DELETE_OFF, DELETE_EXPECTED),
        ("selector_six_character_gate", SELECT_HOOK_VA, SELECT_OFF, SELECT_EXPECTED),
    ):
        file_offset, changed = patch_jump(patched, patched_pe, source_va, section_va + target_off, expected)
        disabled = neutralize_overlapping_base_relocations(patched, patched_pe, source_va, len(expected))
        hooks.append({"name": name, "source_va": source_va, "source_file_offset": file_offset, "target_va": section_va + target_off, "original": expected.hex(), "patch_bytes": len(expected), "neutralized_relocations": disabled})
        neutralized_relocations.extend(disabled)
        allow.extend(changed)
        for row in disabled:
            allow.extend((row["file_offset"], row["file_offset"] + 1))
    output = bytes(patched)
    verify = pefile.PE(data=output, fast_load=False)
    new_section = next((s for s in verify.sections if s.Name.rstrip(b"\0") == SECTION_NAME), None)
    new_state_section = next((s for s in verify.sections if s.Name.rstrip(b"\0") == STATE_SECTION_NAME), None)
    if new_section is None or new_section.VirtualAddress != section_rva or new_section.PointerToRawData != raw_pointer or new_section.Characteristics != 0x60000020:
        raise ValueError("RX Korean input section verification failed")
    if new_state_section is None or new_state_section.VirtualAddress != state_section_rva or new_state_section.PointerToRawData != state_raw_pointer or new_state_section.Characteristics != 0xC0000040:
        raise ValueError("RW Korean input state section verification failed")
    verify_help_pointer_offset = verify.get_offset_from_rva(NAME_HELP_POINTER_IMMEDIATE_VA - IMAGE_BASE)
    if struct.unpack_from("<I", output, verify_help_pointer_offset)[0] != relocated_help_va:
        raise ValueError("relocated name-help pointer verification failed")
    verify_help_raw = output[new_section.PointerToRawData + help_off:new_section.PointerToRawData + help_off + len(help_blob)]
    if verify_help_raw != help_blob:
        raise ValueError("relocated name-help text verification failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema": "criminal-girls.two-set-name-input-patch.v8",
        "status": "PASS",
        "source_exe": str(args.exe),
        "source_exe_sha256": sha256(source),
        "literal_exe_report": str(args.exe_report),
        "literal_exe_report_sha256": sha256(args.exe_report.read_bytes()),
        "font_report": str(args.font_report),
        "font_report_sha256": sha256(args.font_report.read_bytes()),
        "output": str(args.output),
        "output_sha256": sha256(output),
        "source_section_count": 6,
        "output_section_count": 8,
        "section": {"name": SECTION_NAME.decode("ascii"), "rva": section_rva, "va": section_va, "virtual_size": len(section), "raw_pointer": raw_pointer, "raw_size": raw_size, "characteristics": "0x60000020", "position_independent": True, "relocations_required": 0},
        "state_section": {"name": STATE_SECTION_NAME.decode("ascii"), "rva": state_section_rva, "va": state_section_va, "virtual_size": len(mutable_state), "raw_pointer": state_raw_pointer, "raw_size": state_raw_size, "characteristics": "0xC0000040", "writable": True, "executable": False},
        "hooks": hooks,
        "code": {name + "_bytes": len(blob) for name, blob in code.items()},
        "tables": {**meta, "input_offset": INPUT_OFF, "state_index_offset": STATE_OFF, "transition_offset": trans_off, "decomposition_offset": decomp_off, "name_help_offset": help_off, "name_help_bytes": len(help_blob) - 1, "mutable_state_section_rva": state_section_rva, "key_state_local_offset": KEY_STATE_LOCAL_OFF, "shift_state_local_offset": SHIFT_STATE_LOCAL_OFF, "any_key_down_local_offset": ANY_KEY_DOWN_LOCAL_OFF, "input_mode_local_offset": INPUT_MODE_LOCAL_OFF, "input_bytes": len(input_blob), "state_index_bytes": len(state_blob), "transition_bytes": len(trans_blob), "decomposition_bytes": len(decomp_blob)},
        "name_help_text": NAME_HELP_TEXT,
        "name_help_legend": NAME_HELP_LEGEND,
        "name_help_pointer_immediate_va": f"0x{NAME_HELP_POINTER_IMMEDIATE_VA:08X}",
        "name_help_original_target_va": f"0x{NAME_HELP_ORIGINAL_TARGET_VA:08X}",
        "name_help_relocated_target_va": f"0x{relocated_help_va:08X}",
        "name_help_highlow_relocation_preserved": True,
        "enter_completion_enabled": True,
        "enter_select_command_bit_cleared": True,
        "enter_completion_command_bit_set": True,
        "mouse_click_japanese_input_preserved": True,
        "name_capacity": NAME_CAPACITY,
        "all_append_paths_six_character_capped": True,
        "input_method": "Hangul-key toggled Korean two-set plus CP932 fullwidth English/digits in the Japanese two-byte editor; original Japanese on-screen selector",
        "language_scope": "Direct Korean/English/digit input is limited to the Japanese two-byte editor; the original Japanese selector and English one-byte editor retain original paths",
        "hangul_english_toggle_vk": "0x15",
        "hangul_toggle_detection": "GetAsyncKeyState low-bit press event; no release latch",
        "fallback_toggle_vk": "0x70 (F1)",
        "initial_direct_input_mode": "korean",
        "direct_english_input": True,
        "direct_numeric_input": True,
        "english_numeric_storage": "CP932 fullwidth two-byte words with no embedded NUL",
        "english_letter_key_count": len(KEY_MAP),
        "numeric_key_count": len(DIGIT_KEYS),
        "original_q_key_action": "move input cursor left",
        "original_e_key_action": "move input cursor right",
        "q_e_game_commands_suppressed_while_direct_typing": True,
        "force_japanese_name_mode": args.force_japanese_name_mode,
        "visible_selector": "original Japanese hiragana/katakana selector",
        "selector_hook_installed": True,
        "selector_hook_purpose": "six-character capacity gate only",
        "original_japanese_selector_preserved": True,
        "keyboard_key_count": len(KEY_MAP),
        "shift_variant_count": len(SHIFT_INPUTS),
        "backspace_decomposes": True,
        "game_command_bits_suppressed_while_typing": True,
        "standard": "KS_X_1001_Wansung_2350",
        "pe_size_of_image": new_size_of_image,
        "source_bytes_preserved_except_headers_update_delete_selector_hooks_and_name_help_pointer": True,
        "neutralized_overlapping_base_relocations": neutralized_relocations,
        "aslr_hook_targets_stable": True,
        "allowlisted_changed_byte_count": len(set(allow)),
    }
    atomic_json(args.report, report)
    print(json.dumps({"status": report["status"], "output": str(args.output), "output_sha256": report["output_sha256"], "code": report["code"], "tables": report["tables"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())