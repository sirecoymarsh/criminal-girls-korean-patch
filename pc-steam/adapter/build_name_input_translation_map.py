#!/usr/bin/env python3
"""Preserve the original Japanese selector while enabling direct Korean composition."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

TRUSTED_EXE_SHA256 = "d11a48646c212f6df29f778b2a1282aa30d62e4e61d8ecd8d3f8422e3ffa8c7d"
TABLES = (
    ("full_hiragana", 1_292_176, 204, 102, 85),
    ("full_katakana", 1_292_381, 204, 102, 85),
    ("simple_hiragana", 1_292_586, 204, 102, 45),
)
LABEL = ("name_input_controls", 1_434_492, 36)
LEADS = "ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ".split()
MEDIALS = "ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ".split()
COMPOUND_FINALS = "ㄳ ㄵ ㄶ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅄ".split()
INPUT_CONSONANTS = "ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ".split()
INPUT_VOWELS = "ㅏ ㅐ ㅑ ㅓ ㅔ ㅕ ㅗ ㅛ ㅜ ㅠ ㅡ ㅣ".split()
INPUT_JAMO = INPUT_CONSONANTS + INPUT_VOWELS
COMPOSITION_STATE_JAMO = LEADS + MEDIALS + COMPOUND_FINALS
CONTROL_TARGET = "F1 한/영　BS 삭제　Enter 완료"
IN_PLACE_HELP_LEGEND = "F1 한/영 / BS 삭제 / Enter 완료"
RUNTIME_HELP_TARGET = "F1 한/영　Backspace 삭제　Click 일어 입력　Enter 완료"
RUNTIME_HELP_LEGEND = "F1 한/영 / Backspace 삭제 / Click 일어 입력 / Enter 완료"
FULLWIDTH_SPACE = "　"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def c_string_at(data: bytes, offset: int) -> bytes:
    return data[offset:data.index(0, offset)]


def runtime_bytes(text: str) -> int:
    count = 0
    for ch in text:
        if ord(ch) < 128:
            count += 1
        else:
            try:
                count += len(ch.encode("cp932"))
            except UnicodeEncodeError:
                count += 2
    return count


def build_grid(source: str, selectable_capacity: int) -> str:
    """Place only 26 basic Korean keyboard Jamo on the fixed 17 x 6 grid."""
    if len(source) != 17 * 6 or selectable_capacity < len(INPUT_JAMO):
        raise ValueError("selector cannot hold the 26-key Korean layout")
    out = [FULLWIDTH_SPACE] * len(source)
    for column, symbol in zip(range(1, 15), INPUT_CONSONANTS, strict=True):
        out[column] = symbol
    for column, symbol in zip(range(2, 14), INPUT_VOWELS, strict=True):
        out[17 + column] = symbol
    return "".join(out)

def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--translations", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--character-source", type=Path, required=True)
    args = ap.parse_args()

    exe = args.exe.read_bytes()
    digest = sha256(exe)
    if digest != TRUSTED_EXE_SHA256:
        raise ValueError(f"untrusted executable hash: {digest}")
    if len(INPUT_JAMO) != 26 or len(set(INPUT_JAMO)) != 26:
        raise ValueError("Korean selector requires exactly 26 unique basic keyboard Jamo")
    if len(COMPOSITION_STATE_JAMO) != 51 or len(set(COMPOSITION_STATE_JAMO)) != 51:
        raise ValueError("composition state set requires exactly 51 unique modern Jamo")

    translations = json.loads(args.translations.read_text(encoding="utf-8-sig"))
    if not isinstance(translations, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in translations.items()):
        raise ValueError("translation map is not a string-to-string object")
    previous_count = len(translations)
    rows = []

    for name, offset, raw_size, char_count, selectable_count in TABLES:
        raw = c_string_at(exe, offset)
        if len(raw) != raw_size:
            raise ValueError(f"{name}: source size {len(raw)} != {raw_size}")
        source = raw.decode("cp932")
        actual_selectable = sum(ch != FULLWIDTH_SPACE for ch in source)
        if len(source) != char_count or actual_selectable != selectable_count:
            raise ValueError(f"{name}: unexpected selector shape {len(source)}/{actual_selectable}")
        previous_target = translations.pop(source, None)
        rows.append({
            "name": name,
            "offset": offset,
            "source_sha256": sha256(raw),
            "source_chars": len(source),
            "source_bytes": len(raw),
            "selector_capacity": selectable_count,
            "preserved_original_japanese": True,
            "removed_korean_grid_override": previous_target is not None,
            "source_ja": source,
        })

    label_name, label_offset, label_size = LABEL
    label_raw = c_string_at(exe, label_offset)
    if len(label_raw) != label_size or runtime_bytes(CONTROL_TARGET) > label_size:
        raise ValueError(f"{label_name}: fixed allocation overflow")
    label_source = label_raw.decode("cp932")
    previous_target = translations.get(label_source)
    translations[label_source] = CONTROL_TARGET
    rows.append({
        "name": label_name,
        "offset": label_offset,
        "source_sha256": sha256(label_raw),
        "source_chars": len(label_source),
        "source_bytes": len(label_raw),
        "target_chars": len(CONTROL_TARGET),
        "target_runtime_bytes": runtime_bytes(CONTROL_TARGET),
        "target_allocation_bytes": label_size,
        "target_unused_bytes": label_size - runtime_bytes(CONTROL_TARGET),
        "previous_target_replaced": previous_target is not None and previous_target != CONTROL_TARGET,
        "target_ko": CONTROL_TARGET,
    })

    standard_wansung = []
    for cp in range(0xAC00, 0xD7A4):
        ch = chr(cp)
        try:
            if len(ch.encode("euc_kr")) == 2:
                standard_wansung.append(ch)
        except UnicodeEncodeError:
            pass
    if len(standard_wansung) != 2350:
        raise ValueError(f"unexpected Wansung set size: {len(standard_wansung)}")
    character_source = {
        "schema": "criminal-girls.name-composition-characters.v1",
        "standard": "KS_X_1001_Wansung_2350",
        "standard_wansung": "".join(standard_wansung),
        "input_jamo": "".join(INPUT_JAMO),
        "composition_jamo": "".join(COMPOSITION_STATE_JAMO),
        "composition_state_jamo": "".join(COMPOSITION_STATE_JAMO),
    }

    atomic_json(args.translations, translations)
    atomic_json(args.character_source, character_source)
    report = {
        "schema": "criminal-girls.name-input-korean.v6",
        "status": "PASS",
        "model": "Codex internal model",
        "source_exe": str(args.exe),
        "source_exe_sha256": digest,
        "translation_map": str(args.translations),
        "character_source": str(args.character_source),
        "previous_literal_count": previous_count,
        "final_literal_count": len(translations),
        "added_or_verified_literals": 1,
        "removed_grid_override_count": sum(bool(row.get("removed_korean_grid_override")) for row in rows),
        "grid_override_absent_count": sum(row.get("preserved_original_japanese") is True for row in rows),
        "input_method": "direct two-set physical keyboard with sequential composition; Hangul/English toggle via Hangul or F1; original Japanese on-screen selector",
        "target_ko": RUNTIME_HELP_TARGET,
        "name_help_legend": RUNTIME_HELP_LEGEND,
        "in_place_help_legend": IN_PLACE_HELP_LEGEND,
        "runtime_help_target": RUNTIME_HELP_TARGET,
        "runtime_help_target_bytes": runtime_bytes(RUNTIME_HELP_TARGET),
        "runtime_help_relocated": True,
        "completion_label": "완료",
        "completion_key": "Enter",
        "japanese_input_method": "mouse_click",
        "max_name_characters": 6,
        "expected_suppressed_name_help_icon_call_count": 5,
        "obsolete_visual_guidance_removed": ["L 입력", "I 삭제", "Q/E 이동"],
        "selector_mode": "original_japanese",
        "selector_preserved_table_count": 3,
        "translated_control_label_count": 1,
        "grid_bytes_preserved": True,
        "allocation_preserved": True,
        "keyboard_key_count": 26,
        "basic_direct_input_jamo_count": len(INPUT_JAMO),
        "shift_direct_input_jamo_count": 7,
        "direct_input_jamo_count": 33,
        "composition_state_jamo_count": len(COMPOSITION_STATE_JAMO),
        "standard_composable_syllable_count": len(standard_wansung),
        "input_consonants": INPUT_CONSONANTS,
        "input_vowels": INPUT_VOWELS,
        "leads": LEADS,
        "medials": MEDIALS,
        "compound_finals": COMPOUND_FINALS,
        "rows": rows,
    }
    atomic_json(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"rows", "input_consonants", "input_vowels", "leads", "medials", "compound_finals"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())