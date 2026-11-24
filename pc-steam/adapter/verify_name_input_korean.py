#!/usr/bin/env python3
"""Verify original Japanese selector tables and the localized name-entry controls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


IN_PLACE_HELP_LEGEND = "F1 한/영 / BS 삭제 / Enter 완료"
RUNTIME_HELP_TARGET = "F1 한/영　Backspace 삭제　Click 일어 입력　Enter 완료"
RUNTIME_HELP_LEGEND = "F1 한/영 / Backspace 삭제 / Click 일어 입력 / Enter 완료"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def runtime_decode(raw: bytes, inverse_slots: dict[int, str]) -> str:
    out = []
    i = 0
    while i < len(raw):
        lead = raw[i]
        if lead < 0x80:
            out.append(chr(lead))
            i += 1
            continue
        if i + 1 >= len(raw):
            raise ValueError("truncated two-byte runtime code")
        code = (lead << 8) | raw[i + 1]
        if code in inverse_slots:
            out.append(inverse_slots[code])
        else:
            out.append(raw[i:i + 2].decode("cp932"))
        i += 2
    return "".join(out)


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original-exe", type=Path, required=True)
    ap.add_argument("--patched-exe", type=Path, required=True)
    ap.add_argument("--font-report", type=Path, required=True)
    ap.add_argument("--map-report", type=Path, required=True)
    ap.add_argument("--exe-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    original = args.original_exe.read_bytes()
    patched = args.patched_exe.read_bytes()
    font = json.loads(args.font_report.read_text(encoding="utf-8-sig"))
    mapping = json.loads(args.map_report.read_text(encoding="utf-8-sig"))
    exe_report = json.loads(args.exe_report.read_text(encoding="utf-8-sig"))
    inverse = {int(row["sjis"], 16): row["char"] for row in font["repurposed_slots"]}
    patch_rows = {row["offset"]: row for row in exe_report["rows"]}

    required_map = {
        "schema": "criminal-girls.name-input-korean.v6",
        "status": "PASS",
        "selector_mode": "original_japanese",
        "selector_preserved_table_count": 3,
        "translated_control_label_count": 1,
        "grid_bytes_preserved": True,
        "keyboard_key_count": 26,
        "direct_input_jamo_count": 33,
        "composition_state_jamo_count": 51,
        "target_ko": RUNTIME_HELP_TARGET,
        "name_help_legend": RUNTIME_HELP_LEGEND,
        "in_place_help_legend": IN_PLACE_HELP_LEGEND,
        "runtime_help_target": RUNTIME_HELP_TARGET,
        "runtime_help_relocated": True,
        "completion_label": "완료",
        "completion_key": "Enter",
        "japanese_input_method": "mouse_click",
        "max_name_characters": 6,
        "expected_suppressed_name_help_icon_call_count": 5,
    }
    mismatches = {key: (mapping.get(key), value) for key, value in required_map.items() if mapping.get(key) != value}
    if mismatches:
        raise ValueError(f"name-input map authority mismatch: {mismatches}")
    if exe_report.get("status") != "PASS" or exe_report.get("outside_allowlist_count") != 0:
        raise ValueError("executable patch authority did not pass")
    if exe_report.get("suppressed_name_help_icon_call_count") != 5:
        raise ValueError("obsolete name-help icon calls were not all suppressed")
    if exe_report.get("name_help_legend") != IN_PLACE_HELP_LEGEND:
        raise ValueError("direct-input name-help legend mismatch")

    selector_checks = []
    control_checks = []
    for row in mapping["rows"]:
        offset = int(row["offset"])
        if row.get("preserved_original_japanese") is True:
            byte_count = int(row["source_bytes"])
            original_raw = original[offset:offset + byte_count]
            patched_raw = patched[offset:offset + byte_count]
            decoded = patched_raw.decode("cp932")
            if sha256(original_raw) != row["source_sha256"]:
                raise ValueError(f"selector source hash mismatch at {offset}")
            if original_raw != patched_raw or decoded != row["source_ja"]:
                raise ValueError(f"original Japanese selector bytes changed at {offset}")
            if original[offset + byte_count] != 0 or patched[offset + byte_count] != 0:
                raise ValueError(f"selector NUL terminator mismatch at {offset}")
            if offset in patch_rows:
                raise ValueError(f"selector unexpectedly appears in executable translation patch rows at {offset}")
            selector_checks.append({
                "name": row["name"],
                "offset": offset,
                "source_bytes": byte_count,
                "decoded_original_japanese": decoded,
                "byte_identical_to_original": True,
                "nul_terminated": True,
            })
            continue

        if row.get("name") != "name_input_controls":
            raise ValueError(f"unexpected name-input row: {row.get('name')}")
        patch_row = patch_rows.get(offset)
        if patch_row is None:
            raise ValueError(f"missing localized control patch row at {offset}")
        source_bytes = int(patch_row["source_bytes"])
        target_bytes = int(patch_row["target_bytes"])
        raw = patched[offset:offset + target_bytes]
        decoded = runtime_decode(raw, inverse)
        if decoded != row["target_ko"] or len(decoded) != row["target_chars"]:
            raise ValueError(f"localized name controls decode mismatch at {offset}")
        if patched[offset + target_bytes] != 0:
            raise ValueError(f"localized name controls are not NUL-terminated at {offset}")
        control_checks.append({
            "name": row["name"],
            "offset": offset,
            "source_bytes": source_bytes,
            "target_bytes": target_bytes,
            "decoded_target_ko": decoded,
            "shape_preserved": len(decoded) == row["target_chars"],
            "nul_terminated": True,
            "original_range_changed": original[offset:offset + source_bytes] != raw,
        })

    if len(selector_checks) != 3 or len(control_checks) != 1:
        raise ValueError(f"name-input surface count mismatch: selector={len(selector_checks)}, controls={len(control_checks)}")

    report = {
        "schema": "criminal-girls.name-input-runtime-static.v6",
        "status": "PASS",
        "original_exe": str(args.original_exe),
        "original_exe_sha256": sha256(original),
        "patched_exe": str(args.patched_exe),
        "patched_exe_sha256": sha256(patched),
        "font_report_sha256": sha256(args.font_report.read_bytes()),
        "map_report_sha256": sha256(args.map_report.read_bytes()),
        "exe_patch_report_sha256": sha256(args.exe_report.read_bytes()),
        "verified_original_japanese_selector_table_count": len(selector_checks),
        "verified_localized_control_label_count": len(control_checks),
        "original_japanese_selector_tables_preserved": True,
        "selector_mode": "original_japanese",
        "visible_basic_selector_jamo_count": 0,
        "composition_state_jamo_count": mapping["composition_state_jamo_count"],
        "direct_two_set_keyboard_key_count": mapping["keyboard_key_count"],
        "direct_input_jamo_count": mapping["direct_input_jamo_count"],
        "original_byte_allocations_preserved": True,
        "localized_controls_runtime_decode_to_exact_korean": True,
        "name_help_in_place_legend": IN_PLACE_HELP_LEGEND,
        "name_help_runtime_legend": RUNTIME_HELP_LEGEND,
        "runtime_help_extension_pending_composition_patch": True,
        "completion_label": "완료",
        "completion_key": "Enter",
        "japanese_input_method": "mouse_click",
        "max_name_characters": 6,
        "obsolete_name_help_icons_suppressed": True,
        "direct_input_help_legend_pass": True,
        "all_surfaces_nul_terminated": True,
        "outside_executable_allowlist_count": 0,
        "selector_checks": selector_checks,
        "control_checks": control_checks,
    }
    atomic_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"selector_checks", "control_checks"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
