#!/usr/bin/env python3
"""Patch hash-bound CP932 Japanese UI literals with Korean glyph-slot bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import pefile


TRUSTED_EXE_SHA256 = "d11a48646c212f6df29f778b2a1282aa30d62e4e61d8ecd8d3f8422e3ffa8c7d"
NAME_HELP_ICON_CALL_VAS = (0x49D2AE, 0x49D2C6, 0x49D2E0, 0x49D2FA, 0x49D317)
NAME_HELP_ICON_DRAW_VA = 0x4EAC90


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exact_c_string_offsets(data: bytes, raw: bytes, start: int, end: int) -> list[int]:
    result=[]
    pos=start
    while True:
        pos=data.find(raw, pos, end)
        if pos < 0:
            return result
        before_ok=pos == start or data[pos-1] == 0
        after=pos+len(raw)
        if before_ok and after < end and data[after] == 0:
            result.append(pos)
        pos += 1


def encode_target(text: str, slots: dict[str, int]) -> bytes:
    out=bytearray()
    for char in text:
        if ord(char) < 128:
            out.append(ord(char))
            continue
        try:
            out.extend(char.encode("cp932"))
            continue
        except UnicodeEncodeError:
            pass
        code=slots.get(char)
        if code is None:
            raise ValueError(f"font report has no Korean glyph slot for U+{ord(char):04X}")
        out.extend(code.to_bytes(2, "big"))
    return bytes(out)


def section_signature(pe: pefile.PE) -> list[dict]:
    return [
        {
            "name": s.Name.rstrip(b"\0").decode("ascii", "replace"),
            "virtual_address": s.VirtualAddress,
            "virtual_size": s.Misc_VirtualSize,
            "raw_offset": s.PointerToRawData,
            "raw_size": s.SizeOfRawData,
            "characteristics": s.Characteristics,
        }
        for s in pe.sections
    ]


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--translations", type=Path, required=True)
    ap.add_argument("--font-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args=ap.parse_args()

    original=args.exe.read_bytes()
    original_sha=sha256_bytes(original)
    if original_sha != TRUSTED_EXE_SHA256:
        raise ValueError(f"untrusted executable hash: {original_sha}")
    translations=json.loads(args.translations.read_text(encoding="utf-8-sig"))
    if not isinstance(translations, dict) or not translations or not all(isinstance(k,str) and isinstance(v,str) for k,v in translations.items()):
        raise ValueError("translations must be a non-empty string-to-string object")
    font_report=json.loads(args.font_report.read_text(encoding="utf-8-sig"))
    if not font_report.get("passed"):
        raise ValueError("font report did not pass")
    slots={row["char"]: int(row["sjis"],16) for row in font_report.get("repurposed_slots",[])}

    original_pe=pefile.PE(data=original, fast_load=False)
    rdata=next((s for s in original_pe.sections if s.Name.rstrip(b"\0") == b".rdata"), None)
    if rdata is None:
        raise ValueError(".rdata section missing")
    section_start=rdata.PointerToRawData
    section_end=section_start+rdata.SizeOfRawData
    image_base=original_pe.OPTIONAL_HEADER.ImageBase
    patched=bytearray(original)
    rows=[]
    all_allowlisted=set()
    suppressed_name_help_icon_calls=[]
    for call_va in NAME_HELP_ICON_CALL_VAS:
        call_offset = original_pe.get_offset_from_rva(call_va - image_base)
        if original[call_offset] != 0xE8:
            raise ValueError(f"name-help icon site is not CALL at {call_va:08X}")
        displacement = struct.unpack_from("<i", original, call_offset + 1)[0]
        target_va = call_va + 5 + displacement
        if target_va != NAME_HELP_ICON_DRAW_VA:
            raise ValueError(f"name-help icon CALL target mismatch at {call_va:08X}: {target_va:08X}")
        patched[call_offset:call_offset + 5] = b"\x90" * 5
        all_allowlisted.update(range(call_offset, call_offset + 5))
        suppressed_name_help_icon_calls.append({
            "call_va": call_va,
            "file_offset": call_offset,
            "original_target_va": target_va,
            "replacement": "NOP5",
        })

    for source,target in translations.items():
        source_raw=source.encode("cp932")
        offsets=exact_c_string_offsets(original,source_raw,section_start,section_end)
        if len(offsets) != 1:
            raise ValueError(f"expected one exact literal for {source!r}, found {offsets}")
        offset=offsets[0]
        source_end=offset+len(source_raw)
        next_nonzero=source_end+1
        while next_nonzero < section_end and original[next_nonzero] == 0:
            next_nonzero += 1
        capacity=next_nonzero-offset-1
        target_raw=encode_target(target,slots)
        if len(target_raw) > capacity:
            raise ValueError(f"target exceeds in-place allocation at {offset}: {len(target_raw)} > {capacity}")
        # Runtime gate: never consume apparent NUL padding after a C string.
        # These aligned tables contain zero bytes not proven to be string-owned;
        # expanding into them passed static scans but caused APPCRASH 0xC0000005.
        if len(target_raw) > len(source_raw):
            raise ValueError(
                f"runtime-safe in-place patch forbids expansion at {offset}: "
                f"{len(target_raw)} > original {len(source_raw)}"
            )
        if len(target_raw) > len(source_raw):
            for file_offset in range(source_end+1, offset+len(target_raw)+1):
                rva=rdata.VirtualAddress+(file_offset-section_start)
                va=image_base+rva
                needle=struct.pack("<I",va)
                refs=[]
                pos=0
                while True:
                    pos=original.find(needle,pos)
                    if pos < 0:
                        break
                    refs.append(pos)
                    pos += 1
                if refs:
                    raise ValueError(f"expanded padding byte has pointer references: {file_offset} {refs}")
        write_end=offset+max(len(source_raw),len(target_raw))+1
        patched[offset:write_end]=target_raw+b"\0"+b"\0"*(write_end-offset-len(target_raw)-1)
        changed=[i for i in range(offset,write_end) if original[i] != patched[i]]
        all_allowlisted.update(range(offset,write_end))
        rows.append({
            "offset":offset,
            "rva":rdata.VirtualAddress+(offset-section_start),
            "source_ja":source,
            "target_ko":target,
            "source_bytes":len(source_raw),
            "target_bytes":len(target_raw),
            "allocation_capacity":capacity,
            "changed_bytes":len(changed),
            "range":[offset,write_end],
        })

    changed_offsets=[i for i,(a,b) in enumerate(zip(original,patched)) if a != b]
    outside=[i for i in changed_offsets if i not in all_allowlisted]
    if outside:
        raise ValueError(f"changes outside allowlist: {outside[:20]}")
    patched_bytes=bytes(patched)
    patched_pe=pefile.PE(data=patched_bytes,fast_load=False)
    if section_signature(original_pe) != section_signature(patched_pe):
        raise ValueError("PE section layout changed")
    if original_pe.DOS_HEADER.e_lfanew != patched_pe.DOS_HEADER.e_lfanew:
        raise ValueError("PE header location changed")
    for source in translations:
        source_raw=source.encode("cp932")
        if exact_c_string_offsets(patched_bytes,source_raw,section_start,section_end):
            raise ValueError(f"Japanese source remains after patch: {source!r}")
    for row in suppressed_name_help_icon_calls:
        if patched_bytes[row["file_offset"]:row["file_offset"] + 5] != b"\x90" * 5:
            raise ValueError(f"name-help icon suppression verification failed: {row}")
    for row in rows:
        expected=encode_target(row["target_ko"],slots)
        actual=patched_bytes[row["offset"]:row["offset"]+len(expected)]
        if actual != expected or patched_bytes[row["offset"]+len(expected)] != 0:
            raise ValueError(f"target verification failed at {row['offset']}")

    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(patched_bytes)
    report={
        "status":"PASS",
        "source_exe":str(args.exe),
        "source_sha256":original_sha,
        "trusted_source_sha256":TRUSTED_EXE_SHA256,
        "translation_map":str(args.translations),
        "translation_map_sha256":sha256_bytes(args.translations.read_bytes()),
        "font_report":str(args.font_report),
        "font_report_sha256":sha256_bytes(args.font_report.read_bytes()),
        "output":str(args.output),
        "output_sha256":sha256_bytes(patched_bytes),
        "literal_count":len(rows),
        "changed_byte_count":len(changed_offsets),
        "outside_allowlist_count":len(outside),
        "pe_section_layout_match":True,
        "japanese_source_literal_remaining":0,
        "name_help_legend": "F1 한/영 / BS 삭제 / Enter 완료",
        "name_help_in_place_legend": "F1 한/영 / BS 삭제 / Enter 완료",
        "name_help_runtime_extension_pending": True,
        "suppressed_name_help_icon_call_count": len(suppressed_name_help_icon_calls),
        "suppressed_name_help_icon_calls": suppressed_name_help_icon_calls,
        "rows":rows,
    }
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "rows"},ensure_ascii=True,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
