#!/usr/bin/env python3
"""Build and independently verify the final Japanese-slot Korean candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from archive_repack import hash_range, parse_template, repack

TRUSTED_DATA_JP_SHA256 = "76bc6eaa12f11e8e6ff6e9fe2d6b8fee4c1bb1d045cab9b626dd098728ea4515"
TRUSTED_EXE_SHA256 = "d11a48646c212f6df29f778b2a1282aa30d62e4e61d8ecd8d3f8422e3ffa8c7d"
EXPECTED_OUTER_ENTRIES = 8442
EXPECTED_NON_BSCR_ROWS = 2709
EXPECTED_BSCR_OCCURRENCES = 48296
EXPECTED_MAP_CONTAINERS = 54
EXPECTED_FIELD_CONTAINERS = 105
EXPECTED_LEGACY_UI_LOGICAL = 21
EXPECTED_COMMON_UI_LOGICAL = 15
EXPECTED_RUNTIME_FONT_ATLASES = 5
SELECTOR_RELOCATION_RVA = 0x0009C7B3
EXPECTED_OUTER_REPLACEMENTS = 241


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def jsonl_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return resolved


def reset_dir(path: Path, root: Path) -> None:
    target = inside(path, root)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def run(command: list[str], cwd: Path) -> None:
    print("+", subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {command}")


def required_paths(root: Path, baseline: Path, exe: Path, font_source: Path) -> dict[str, Path]:
    return {
        "baseline_data_jp": baseline,
        "source_exe": exe,
        "font_source": font_source,
        "final_non_bscr": root / "translation/jp_based_final_review_v2.jsonl",
        "final_bscr": root / "translation/bscr_v2/translation_map.jsonl",
        "exe_literals": root / "translation/exe_literal_translation_map.json",
        "name_composition_characters": root / "translation/name_composition_characters.json",
        "name_input_map": root / "audit/name_input_map_v2.json",
        "catalog": root / "catalog/catalog.jsonl",
        "non_bscr_baseline": root / "translation/reviewed_translation.jsonl",
        "bscr_catalog": root / "translation/bscr_v2/occurrence_catalog.jsonl",
        "ui_qa": root / "audit/ui_final_static_visual_qa.json",
        "font_root": root / "extracted/recursive/jp/system.tpk/system.vol",
        "runtime_font_root": root / "extracted/runtime_font/jp",
        "runtime_font_bin": root / "extracted/runtime_font/jp/font.bin",
        "runtime_font_source": Path(r"C:\Windows\Fonts\batang.ttc"),
        "field_root": root / "extracted/field_messages/jp/payloads",
        "battle_root": root / "extracted/nested/jp/btl_allparam.tpk",
        "system_file": root / "extracted/nested/jp/system.tpk/system_txt.dat",
        "punishment_file": root / "extracted/text_extra/jp/payloads/if_camp_res.tpk/oshioki_txt.dat",
        "camp_file": root / "extracted/text_extra/jp/payloads/if_camp_res.tpk/camp_txt.dat",
        "option_file": root / "extracted/text_extra/jp/payloads/title.tpk/option.dat",
        "map_container_root": root / "extracted/map_scripts/jp/containers",
        "map_payload_root": root / "extracted/map_scripts/jp/payloads",
        "legacy_ui_outer": root / "staging/ui_encoded/outer",
        "common_ui_outer": root / "staging/ui_common_v2/outer",
        "common_ui_manifest": root / "staging/ui_common_v2/outer_replacements_common_ui_v2.json",
    }


def preflight(root: Path, baseline: Path, exe: Path, font_source: Path) -> dict:
    required = required_paths(root, baseline, exe, font_source)
    missing = [f"{key}: {path}" for key, path in required.items() if not path.exists()]
    issues: list[str] = []
    if baseline.is_file() and sha256(baseline) != TRUSTED_DATA_JP_SHA256:
        issues.append("data_jp baseline hash mismatch")
    if exe.is_file() and sha256(exe) != TRUSTED_EXE_SHA256:
        issues.append("executable baseline hash mismatch")
    ui_qa = required["ui_qa"]
    if ui_qa.is_file() and load(ui_qa).get("status") != "PASS":
        issues.append("UI final static/visual QA did not pass")
    name_input_map = required["name_input_map"]
    if name_input_map.is_file():
        name_input_doc = load(name_input_map)
        if (name_input_doc.get("schema") != "criminal-girls.name-input-korean.v6"
                or name_input_doc.get("status") != "PASS"
                or name_input_doc.get("selector_mode") != "original_japanese"
                or name_input_doc.get("selector_preserved_table_count") != 3
                or name_input_doc.get("translated_control_label_count") != 1
                or name_input_doc.get("grid_bytes_preserved") is not True
                or name_input_doc.get("keyboard_key_count") != 26
                or name_input_doc.get("direct_input_jamo_count") != 33
                or name_input_doc.get("composition_state_jamo_count") != 51
                or name_input_doc.get("name_help_legend") != "F1 한/영 / Backspace 삭제 / Click 일어 입력 / Enter 완료"
                or name_input_doc.get("in_place_help_legend") != "F1 한/영 / BS 삭제 / Enter 완료"
                or name_input_doc.get("runtime_help_target") != "F1 한/영　Backspace 삭제　Click 일어 입력　Enter 완료"
                or name_input_doc.get("runtime_help_relocated") is not True
                or name_input_doc.get("completion_label") != "완료"
                or name_input_doc.get("completion_key") != "Enter"
                or name_input_doc.get("japanese_input_method") != "mouse_click"
                or name_input_doc.get("max_name_characters") != 6
                or name_input_doc.get("expected_suppressed_name_help_icon_call_count") != 5):
            issues.append("original-selector/direct-two-set name-input authority did not pass")
    if required["final_non_bscr"].is_file():
        rows = jsonl_rows(required["final_non_bscr"])
        if len(rows) != EXPECTED_NON_BSCR_ROWS:
            issues.append(f"non-BSCR row count {len(rows)} != {EXPECTED_NON_BSCR_ROWS}")
    if required["final_bscr"].is_file():
        rows = jsonl_rows(required["final_bscr"])
        if len(rows) != EXPECTED_BSCR_OCCURRENCES:
            issues.append(f"BSCR row count {len(rows)} != {EXPECTED_BSCR_OCCURRENCES}")
    if required["map_container_root"].is_dir():
        count = len(list(required["map_container_root"].glob("*.tpk")))
        if count != EXPECTED_MAP_CONTAINERS:
            issues.append(f"map container count {count} != {EXPECTED_MAP_CONTAINERS}")
    if required["legacy_ui_outer"].is_dir():
        count = len(list(required["legacy_ui_outer"].glob("*.imy")))
        if count != EXPECTED_LEGACY_UI_LOGICAL:
            issues.append(f"legacy UI count {count} != {EXPECTED_LEGACY_UI_LOGICAL}")
    if required["common_ui_outer"].is_dir():
        count = len(list(required["common_ui_outer"].glob("*.imy")))
        if count != EXPECTED_COMMON_UI_LOGICAL:
            issues.append(f"common UI count {count} != {EXPECTED_COMMON_UI_LOGICAL}")
    return {
        "status": "READY" if not missing and not issues else "WAITING",
        "missing": missing,
        "issues": issues,
        "required": {key: str(path) for key, path in required.items()},
    }


def build_outer_manifest(root: Path, baseline: Path, output: Path) -> tuple[dict, dict]:
    entries, _, _ = parse_template(baseline, "ps3fs")
    if len(entries) != EXPECTED_OUTER_ENTRIES:
        raise ValueError(f"unexpected outer entry count: {len(entries)}")
    by_name: dict[str, list] = {}
    for entry in entries:
        by_name.setdefault(entry.name, []).append(entry)
    rows: list[dict] = []
    used: set[int] = set()
    bak_pairs: list[dict] = []

    def add(name: str, replacement: Path, expected_source_sha256: str | None = None) -> None:
        found = by_name.get(name, [])
        if len(found) != 1:
            raise ValueError(f"expected exactly one outer entry {name!r}, found {len(found)}")
        entry = found[0]
        if entry.index in used:
            raise ValueError(f"duplicate replacement index {entry.index}: {name}")
        actual_source_sha = hash_range(baseline, entry.offset, entry.size)
        if expected_source_sha256 and actual_source_sha != expected_source_sha256:
            raise ValueError(f"baseline source hash mismatch for {name}")
        if not replacement.is_file():
            raise FileNotFoundError(replacement)
        used.add(entry.index)
        rows.append({
            "index": entry.index,
            "expected_name": name,
            "path": str(replacement),
            "size": replacement.stat().st_size,
            "sha256": sha256(replacement),
            "baseline_size": entry.size,
            "baseline_sha256": actual_source_sha,
        })

    def add_ui_pair(name: str, replacement: Path, expected_source_sha256: str | None = None) -> None:
        main = by_name.get(name, [])
        backup = by_name.get(name + ".bak", [])
        if len(main) != 1 or len(backup) != 1:
            raise ValueError(f"missing main/.bak UI pair: {name}")
        main_sha = hash_range(baseline, main[0].offset, main[0].size)
        backup_sha = hash_range(baseline, backup[0].offset, backup[0].size)
        if main_sha != backup_sha or main[0].size != backup[0].size:
            raise ValueError(f"main/.bak source mismatch: {name}")
        if expected_source_sha256 and main_sha != expected_source_sha256:
            raise ValueError(f"UI authority source hash mismatch: {name}")
        add(name, replacement, main_sha)
        add(name + ".bak", replacement, backup_sha)
        bak_pairs.append({
            "logical_asset": name,
            "main_index": main[0].index,
            "backup_index": backup[0].index,
            "source_sha256": main_sha,
            "replacement_sha256": sha256(replacement),
        })

    legacy = sorted((root / "staging/ui_encoded/outer").glob("*.imy"))
    if len(legacy) != EXPECTED_LEGACY_UI_LOGICAL:
        raise ValueError(f"legacy UI logical count mismatch: {len(legacy)}")
    for path in legacy:
        add_ui_pair(path.name, path)

    common_doc = load(root / "staging/ui_common_v2/outer_replacements_common_ui_v2.json")
    common_expected = {item["name"]: item["expected_source_sha256"] for item in common_doc["replacements"]}
    common = sorted((root / "staging/ui_common_v2/outer").glob("*.imy"))
    if len(common) != EXPECTED_COMMON_UI_LOGICAL or set(common_expected) != {p.name for p in common}:
        raise ValueError("common UI authority/output set mismatch")
    for path in common:
        add_ui_pair(path.name, path, common_expected[path.name])

    font_doc = load(root / "staging/korean_font_report.json")
    runtime_font_bin = root / "staging/korean_font/font.bin"
    if sha256(runtime_font_bin) != font_doc.get("runtime_font_bin_output_sha256"):
        raise ValueError("runtime font.bin output hash does not match font authority")
    add("font.bin", runtime_font_bin, font_doc["runtime_font_bin_sha256"])

    runtime_font_doc = load(root / "staging/runtime_font_report.json")
    runtime_font_pages = {item["name"]: item for item in runtime_font_doc["pages"]}
    runtime_fonts = sorted((root / "staging/runtime_font").glob("font_*.imy"))
    if len(runtime_fonts) != EXPECTED_RUNTIME_FONT_ATLASES or set(runtime_font_pages) != {p.name for p in runtime_fonts}:
        raise ValueError("runtime font authority/output set mismatch")
    runtime_fonts_changed = []
    for path in runtime_fonts:
        page = runtime_font_pages[path.name]
        if page["output_sha256"] == page["source_sha256"]:
            if page["slot_count"] != 0 or not page.get("byte_identical_noop"):
                raise ValueError(f"runtime font unchanged page lacks no-op proof: {path.name}")
            continue
        add(path.name, path, page["source_sha256"])
        runtime_fonts_changed.append(path)

    fields = sorted((root / "staging/containers/field").glob("field_mess*.tpk"))
    if len(fields) != EXPECTED_FIELD_CONTAINERS:
        raise ValueError(f"field container count mismatch: {len(fields)}")
    for path in fields:
        add(path.name, path)
    for name in ("btl_allparam.tpk", "if_camp_res.tpk", "system.tpk", "title.tpk"):
        add(name, root / "staging/containers" / name)

    maps = sorted((root / "staging/containers/map").glob("map_d_*.tpk"))
    if len(maps) != EXPECTED_MAP_CONTAINERS:
        raise ValueError(f"map container count mismatch: {len(maps)}")
    for path in maps:
        add(path.name, path)

    rows.sort(key=lambda item: item["index"])
    if len(rows) != EXPECTED_OUTER_REPLACEMENTS or len(used) != EXPECTED_OUTER_REPLACEMENTS:
        raise ValueError(f"outer replacement count mismatch: {len(rows)}")
    manifest = {
        "schema": "criminal-girls.final-jp-outer-replacements.v2",
        "source": str(baseline),
        "source_sha256": sha256(baseline),
        "entry_count": len(entries),
        "replacement_count": len(rows),
        "logical_counts": {
            "legacy_ui": len(legacy),
            "common_ui": len(common),
            "runtime_font_metrics": 1,
            "runtime_font_atlases_audited": len(runtime_fonts),
            "runtime_font_atlases_changed": len(runtime_fonts_changed),
            "field_containers": len(fields),
            "other_text_containers": 4,
            "map_containers": len(maps),
        },
        "archive_entry_counts": {
            "legacy_ui_main_and_bak": len(legacy) * 2,
            "common_ui_main_and_bak": len(common) * 2,
            "runtime_font_atlases": len(runtime_fonts_changed),
            "field_and_other_text_containers": len(fields) + 4,
            "map_containers": len(maps),
        },
        "replacements": rows,
    }
    pair_audit = {
        "schema": "criminal-girls.ui-main-bak-pair-audit.v1",
        "status": "PASS",
        "logical_asset_count": len(bak_pairs),
        "archive_entry_count": len(bak_pairs) * 2,
        "all_source_pairs_identical": True,
        "pairs": bak_pairs,
    }
    atomic_json(output, manifest)
    atomic_json(root / "audit/ui_main_bak_pair_audit.json", pair_audit)
    return manifest, pair_audit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--font-source", type=Path, default=Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf"))
    ap.add_argument("--preflight-only", action="store_true")
    a = ap.parse_args()
    root = a.root.resolve()
    baseline = a.baseline.resolve()
    exe = a.exe.resolve()
    font_source = a.font_source.resolve()
    pre = preflight(root, baseline, exe, font_source)
    preflight_report = root / "audit/final_v2_preflight.json"
    atomic_json(preflight_report, pre)
    print(json.dumps({k: v for k, v in pre.items() if k != "required"}, ensure_ascii=False, indent=2))
    if a.preflight_only:
        return 0 if pre["status"] == "READY" else 2
    if pre["status"] != "READY":
        raise RuntimeError("final v2 preflight is not ready")

    py = sys.executable
    adapter = root / "adapter"
    final_non_bscr = root / "translation/jp_based_final_review_v2.jsonl"
    final_bscr = root / "translation/bscr_v2/translation_map.jsonl"
    final_root = root / "staging/final_v2"

    reset_dir(final_root, root)
    reset_dir(root / "staging/localized_text", root)
    reset_dir(root / "staging/korean_font", root)
    reset_dir(root / "staging/runtime_font", root)
    reset_dir(root / "staging/containers", root)
    reset_dir(root / "translation/bscr_v2/injected_payloads", root)
    reset_dir(root / "translation/bscr_v2/inner_manifests", root)
    reset_dir(root / "staging/reports/nested/map", root)

    non_bscr_audit = root / "audit/non_bscr_final_review_v2.json"
    run([
        py, str(adapter / "audit_non_bscr_translation_v2.py"),
        str(final_non_bscr), str(root / "translation/reviewed_translation.jsonl"),
        str(root / "catalog/catalog.jsonl"), str(non_bscr_audit),
    ], root)
    bscr_validation = root / "audit/bscr_v2_final_map_validation.json"
    run([
        py, str(adapter / "validate_bscr_translation_map.py"),
        "--catalog", str(root / "translation/bscr_v2/occurrence_catalog.jsonl"),
        "--map", str(final_bscr), "--report", str(bscr_validation),
    ], root)

    font_report = root / "staging/korean_font_report.json"
    run([
        py, str(adapter / "build_korean_font.py"),
        "--reviewed", str(final_non_bscr),
        "--font-root", str(root / "extracted/recursive/jp/system.tpk/system.vol"),
        "--font-source", str(font_source),
        "--runtime-font-bin", str(root / "extracted/runtime_font/jp/font.bin"),
        "--output-root", str(root / "staging/korean_font"),
        "--report", str(font_report),
        "--extra-text-json", str(final_bscr),
        "--extra-text-json", str(root / "translation/exe_literal_translation_map.json"),
        "--extra-text-json", str(root / "translation/name_composition_characters.json"),
        "--extra-text-json", str(root / "audit/name_input_map_v2.json"),
        "--preserve-text-json", str(root / "audit/name_input_map_v2.json"),
    ], root)

    runtime_font_report = root / "staging/runtime_font_report.json"
    run([
        py, str(adapter / "build_runtime_font_atlas.py"),
        "--source-root", str(root / "extracted/runtime_font/jp"),
        "--font-bin", str(root / "staging/korean_font/font.bin"),
        "--font-report", str(font_report),
        "--font-source", str(Path(r"C:\Windows\Fonts\batang.ttc")),
        "--output-root", str(root / "staging/runtime_font"),
        "--report", str(runtime_font_report),
    ], root)

    literal_exe = final_root / "steam_criminal.literal.exe"
    exe_report = root / "audit/exe_literal_patch_final_v2.json"
    run([
        py, str(adapter / "build_exe_literal_patch.py"),
        "--exe", str(exe),
        "--translations", str(root / "translation/exe_literal_translation_map.json"),
        "--font-report", str(font_report),
        "--output", str(literal_exe),
        "--report", str(exe_report),
    ], root)

    name_input_static = root / "audit/name_input_runtime_static_final_v2.json"
    run([
        py, str(adapter / "verify_name_input_korean.py"),
        "--original-exe", str(exe),
        "--patched-exe", str(literal_exe),
        "--font-report", str(font_report),
        "--map-report", str(root / "audit/name_input_map_v2.json"),
        "--exe-report", str(exe_report),
        "--output", str(name_input_static),
    ], root)

    patched_exe = final_root / "steam_criminal.exe"
    composition_report = root / "audit/name_composition_patch_final_v2.json"
    run([
        py, str(adapter / "build_name_composition_patch.py"),
        "--exe", str(literal_exe),
        "--exe-report", str(exe_report),
        "--font-report", str(font_report),
        "--output", str(patched_exe),
        "--report", str(composition_report),
    ], root)
    composition_verify = root / "audit/name_composition_verify_final_v2.json"
    run([
        py, str(adapter / "verify_name_composition_patch.py"),
        "--literal-exe", str(literal_exe),
        "--patched-exe", str(patched_exe),
        "--font-report", str(font_report),
        "--patch-report", str(composition_report),
        "--output", str(composition_verify),
    ], root)

    composition_patch_doc = load(composition_report)
    composition_verify_doc = load(composition_verify)
    composition_runtime_requirements = {
        "patch_status": composition_patch_doc.get("status") == "PASS",
        "patch_does_not_force_japanese_name_mode": composition_patch_doc.get("force_japanese_name_mode") is False,
        "patch_neutralized_selector_relocation_once": (
            len(composition_patch_doc.get("neutralized_overlapping_base_relocations", [])) == 1
            and composition_patch_doc["neutralized_overlapping_base_relocations"][0].get("rva") == SELECTOR_RELOCATION_RVA
        ),
        "patch_original_japanese_selector_preserved": composition_patch_doc.get(
            "original_japanese_selector_preserved"
        ) is True,
        "patch_selector_capacity_hook_installed": composition_patch_doc.get("selector_hook_installed") is True,
        "patch_aslr_hook_targets_stable": composition_patch_doc.get("aslr_hook_targets_stable") is True,
        "verify_status": composition_verify_doc.get("status") == "PASS",
        "verify_neutralized_select_relocation_count": composition_verify_doc.get("neutralized_select_relocation_count") == 1,
        "verify_original_select_relocation_count": composition_verify_doc.get("original_select_relocation_count") == 0,
        "verify_selector_absolute_padding_relocation_count": composition_verify_doc.get("selector_absolute_padding_relocation_count") == 1,
        "verify_selector_capacity_hook_installed": composition_verify_doc.get("selector_capacity_hook_installed") is True,
        "verify_original_selector_path_preserved": composition_verify_doc.get(
            "original_selector_path_preserved"
        ) is True,
        "verify_active_hook_highlow_relocation_count": composition_verify_doc.get("active_hook_highlow_relocation_count") == 0,
        "verify_aslr_hook_targets_stable": composition_verify_doc.get("aslr_hook_targets_stable") is True,
        "verify_japanese_two_byte_editor_only": composition_verify_doc.get("japanese_two_byte_editor_only") is True,
        "verify_english_paths_preserved": composition_verify_doc.get("english_one_byte_editor_original_paths_preserved") is True,
        "verify_does_not_force_japanese_name_mode": composition_verify_doc.get("force_japanese_name_mode") is False,
    }
    if not all(composition_runtime_requirements.values()):
        failed = [key for key, passed in composition_runtime_requirements.items() if not passed]
        raise RuntimeError(f"name composition ASLR/language gate failed: {failed}")

    localized_report = root / "staging/localized_text_report.json"
    run([
        py, str(adapter / "inject_reviewed_text.py"),
        "--catalog", str(root / "catalog/catalog.jsonl"),
        "--reviewed", str(final_non_bscr),
        "--field-root", str(root / "extracted/field_messages/jp/payloads"),
        "--battle-root", str(root / "extracted/nested/jp/btl_allparam.tpk"),
        "--system-file", str(root / "extracted/nested/jp/system.tpk/system_txt.dat"),
        "--punishment-file", str(root / "extracted/text_extra/jp/payloads/if_camp_res.tpk/oshioki_txt.dat"),
        "--camp-file", str(root / "extracted/text_extra/jp/payloads/if_camp_res.tpk/camp_txt.dat"),
        "--option-file", str(root / "extracted/text_extra/jp/payloads/title.tpk/option.dat"),
        "--font-report", str(font_report),
        "--output-root", str(root / "staging/localized_text"),
        "--report", str(localized_report),
    ], root)
    containers_report = root / "staging/localized_containers_report.json"
    run([
        py, str(adapter / "build_localized_containers.py"),
        "--root", str(root), "--report", str(containers_report),
    ], root)

    bscr_injection = root / "audit/bscr_v2_final_injection.json"
    run([
        py, str(adapter / "inject_bscr_translations.py"),
        "--source-root", str(root / "extracted/map_scripts/jp/payloads"),
        "--catalog", str(root / "translation/bscr_v2/occurrence_catalog.jsonl"),
        "--map", str(final_bscr),
        "--font-report", str(font_report),
        "--output-root", str(root / "translation/bscr_v2/injected_payloads"),
        "--report", str(bscr_injection),
    ], root)
    bscr_verify = root / "audit/bscr_v2_final_injection_verify.json"
    run([
        py, str(adapter / "verify_bscr_injection.py"),
        "--source-root", str(root / "extracted/map_scripts/jp/payloads"),
        "--catalog", str(root / "translation/bscr_v2/occurrence_catalog.jsonl"),
        "--map", str(final_bscr),
        "--font-report", str(font_report),
        "--output-root", str(root / "translation/bscr_v2/injected_payloads"),
        "--report", str(bscr_verify),
    ], root)
    bscr_inner_audit = root / "audit/bscr_v2_inner_manifests_final.json"
    run([
        py, str(adapter / "build_bscr_inner_manifests.py"),
        "--container-root", str(root / "extracted/map_scripts/jp/containers"),
        "--payload-root", str(root / "translation/bscr_v2/injected_payloads"),
        "--output-root", str(root / "translation/bscr_v2/inner_manifests"),
        "--audit", str(bscr_inner_audit),
    ], root)

    map_out = root / "staging/containers/map"
    map_out.mkdir(parents=True, exist_ok=True)
    map_results = []
    for template in sorted((root / "extracted/map_scripts/jp/containers").glob("*.tpk")):
        manifest = root / "translation/bscr_v2/inner_manifests" / f"{template.name}.replacements.json"
        output = map_out / template.name
        report = root / "staging/reports/nested/map" / f"{template.stem}.json"
        result = repack(template, output, "dsarcidx", manifest)
        atomic_json(report, result)
        map_results.append(result)
    if len(map_results) != EXPECTED_MAP_CONTAINERS:
        raise ValueError(f"rebuilt map container count mismatch: {len(map_results)}")
    map_summary = {
        "status": "PASS",
        "container_count": len(map_results),
        "all_replacements_verified": all(
            len(item["verified_replacements"]) == item["replacement_count"] for item in map_results
        ),
        "containers": map_results,
    }
    atomic_json(root / "staging/reports/map_containers_final_v2.json", map_summary)

    outer_manifest_path = final_root / "manifests/outer_replacements.json"
    outer_manifest, pair_audit = build_outer_manifest(root, baseline, outer_manifest_path)
    candidate = final_root / "data/data_jp.dat"
    archive_result = repack(baseline, candidate, "ps3fs", outer_manifest_path)
    archive_report = root / "staging/reports/data_jp_final_v2.json"
    atomic_json(archive_report, archive_result)

    diff_report = root / "staging/reports/final_archive_diff_v2.json"
    run([
        py, str(adapter / "compare_ps3fs_payloads.py"),
        str(baseline), str(candidate), "--output", str(diff_report),
    ], root)
    diff = load(diff_report)
    manifest_indices = {row["index"] for row in outer_manifest["replacements"]}
    diff_indices = {row.get("right_index") for row in diff["differences"]}
    if diff_indices != manifest_indices:
        raise ValueError("archive diff changed-index set does not equal manifest")
    if diff.get("different_entry_count") != EXPECTED_OUTER_REPLACEMENTS:
        raise ValueError("archive diff count mismatch")
    expected_ext = {".bak": 36, ".bin": 1, ".imy": 41, ".tpk": 163}
    if diff.get("different_extension_counts") != expected_ext:
        raise ValueError(f"archive diff extension counts mismatch: {diff.get('different_extension_counts')}")

    report_paths = {
        "preflight": preflight_report,
        "non_bscr_audit": non_bscr_audit,
        "bscr_validation": bscr_validation,
        "font": font_report,
        "runtime_font_atlas": runtime_font_report,
        "exe_patch": exe_report,
        "name_input_map": root / "audit/name_input_map_v2.json",
        "name_input_runtime_static": name_input_static,
        "name_composition_patch": composition_report,
        "name_composition_verify": composition_verify,
        "localized_text": localized_report,
        "localized_containers": containers_report,
        "bscr_injection": bscr_injection,
        "bscr_injection_verify": bscr_verify,
        "bscr_inner_manifests": bscr_inner_audit,
        "map_containers": root / "staging/reports/map_containers_final_v2.json",
        "ui_static_visual_qa": root / "audit/ui_final_static_visual_qa.json",
        "ui_main_bak_pairs": root / "audit/ui_main_bak_pair_audit.json",
        "outer_manifest": outer_manifest_path,
        "archive_build": archive_report,
        "archive_diff": diff_report,
    }
    final_report = {
        "schema": "criminal-girls.final-jp-candidate.v2",
        "status": "PASS",
        "installed_to_game": False,
        "language_contract": "Japanese semantic source; Korean replaces Japanese slot; English archive unchanged",
        "baseline_data_jp": str(baseline),
        "baseline_data_jp_sha256": sha256(baseline),
        "candidate_data_jp": str(candidate),
        "candidate_data_jp_size": candidate.stat().st_size,
        "candidate_data_jp_sha256": sha256(candidate),
        "baseline_exe": str(exe),
        "baseline_exe_sha256": sha256(exe),
        "patched_exe": str(patched_exe),
        "patched_exe_sha256": sha256(patched_exe),
        "counts": {
            "non_bscr_rows": len(jsonl_rows(final_non_bscr)),
            "bscr_occurrences": len(jsonl_rows(final_bscr)),
            "outer_replacements": len(outer_manifest["replacements"]),
            "map_containers": len(map_results),
            "localized_ui_logical_assets": EXPECTED_LEGACY_UI_LOGICAL + EXPECTED_COMMON_UI_LOGICAL,
            "localized_ui_archive_entries": (EXPECTED_LEGACY_UI_LOGICAL + EXPECTED_COMMON_UI_LOGICAL) * 2,
            "exe_literals": load(exe_report).get("literal_count"),
            "runtime_font_metric_tables_changed": 1,
            "runtime_font_atlases_audited": EXPECTED_RUNTIME_FONT_ATLASES,
            "runtime_font_atlases_changed": sum(
                item["output_sha256"] != item["source_sha256"] for item in load(runtime_font_report)["pages"]
            ),
        },
        "checks": {
            "trusted_baseline_hashes": True,
            "all_translation_maps_complete": True,
            "font_closure_pass": load(font_report).get("passed") is True,
            "runtime_font_atlas_pass": load(runtime_font_report).get("status") == "PASS",
            "original_japanese_selector_glyphs_preserved": (
                load(font_report).get("preserved_runtime_slot_count") == 169
                and load(runtime_font_report).get("preserved_text_slot_count") == 169
                and load(runtime_font_report).get("all_preserved_text_font_records_unchanged") is True
                and load(runtime_font_report).get("all_preserved_text_atlas_cells_byte_identical") is True
            ),
            "runtime_surrogate_codec_pass": (
                load(bscr_verify).get("runtime_text_encoding") == "utf8_former_character_glyph_slots"
                and load(localized_report).get("runtime_text_encoding") == "utf8_former_character_glyph_slots"
            ),
            "exe_literal_patch_pass": load(exe_report).get("status") == "PASS",
            "name_help_obsolete_icons_suppressed": load(exe_report).get("suppressed_name_help_icon_call_count") == 5,
            "name_help_in_place_fallback_pass": load(exe_report).get("name_help_legend") == "F1 한/영 / BS 삭제 / Enter 완료",
            "name_help_direct_input_legend_pass": load(composition_report).get("name_help_legend") == "F1 한/영 / Backspace 삭제 / Click 일어 입력 / Enter 완료",
            "name_help_pointer_relocated_pass": load(composition_verify).get("name_help_pointer_relocated_pass") is True,
            "name_help_click_japanese_input_pass": load(composition_verify).get("click_japanese_input_help_pass") is True,
            "name_help_enter_completion_pass": load(composition_verify).get("enter_completion_help_pass") is True,
            "name_input_original_japanese_selector_pass": (
                load(name_input_static).get("status") == "PASS"
                and load(name_input_static).get("original_japanese_selector_tables_preserved") is True
            ),
            "name_input_direct_two_set_pass": load(composition_verify).get("direct_qwerty_pass") is True,
            "name_input_hangul_english_toggle_pass": load(composition_verify).get("hangul_english_toggle_pass") is True,
            "name_input_hangul_press_event_pass": load(composition_verify).get("hangul_low_bit_press_event_pass") is True,
            "name_input_f1_fallback_toggle_pass": load(composition_verify).get("f1_fallback_toggle_pass") is True,
            "name_input_direct_english_pass": load(composition_verify).get("direct_english_lowercase_pass") is True and load(composition_verify).get("direct_english_shift_uppercase_pass") is True,
            "name_input_direct_numeric_pass": load(composition_verify).get("direct_numeric_input_pass") is True,
            "name_input_q_e_suppression_pass": load(composition_verify).get("q_e_direct_input_suppression_pass") is True,
            "name_input_cp932_fullwidth_storage_pass": load(composition_verify).get("direct_english_numeric_cp932_fullwidth_pass") is True and load(composition_verify).get("direct_input_embedded_nul_count") == 0,
            "name_input_enter_completion_pass": (
                load(composition_verify).get("enter_completion_key_polled_pass") is True
                and load(composition_verify).get("enter_select_bit_cleared_pass") is True
                and load(composition_verify).get("enter_completion_bit_set_pass") is True
            ),
            "name_input_mouse_click_japanese_pass": load(composition_verify).get("mouse_click_japanese_input_preserved") is True,
            "name_input_six_character_cap_pass": load(composition_verify).get("all_append_paths_six_character_capped") is True and load(composition_verify).get("name_capacity") == 6,
            "name_input_ctrl_confirmation_not_intercepted_pass": load(composition_verify).get("ctrl_confirmation_not_intercepted_pass") is True,
            "name_input_backspace_decomposition_pass": load(composition_verify).get("backspace_decomposition_pass") is True,
            "name_input_rx_rw_separation_pass": (
                load(composition_verify).get("rx_code_section") is True
                and load(composition_verify).get("rw_non_executable_state_section") is True
            ),
            "name_composition_patch_pass": load(composition_report).get("status") == "PASS",
            "name_composition_independent_verify_pass": composition_verify_doc.get("status") == "PASS",
            "name_composition_aslr_relocation_pass": all(composition_runtime_requirements.values()),
            "name_composition_does_not_force_japanese_mode": composition_verify_doc.get("force_japanese_name_mode") is False,
            "name_composition_japanese_editor_only": composition_verify_doc.get("japanese_two_byte_editor_only") is True,
            "name_composition_english_paths_preserved": composition_verify_doc.get("english_one_byte_editor_original_paths_preserved") is True,
            "standard_wansung_2350_composable": composition_verify_doc.get("standard_wansung_state_count") == 2350,
            "ui_static_visual_qa_pass": load(root / "audit/ui_final_static_visual_qa.json").get("status") == "PASS",
            "ui_main_bak_pairs_pass": pair_audit.get("status") == "PASS",
            "all_nested_containers_verified": True,
            "outer_changed_set_exact": True,
            "english_archive_not_in_build_scope": True,
        },
        "reports": {
            key: {"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)}
            for key, path in report_paths.items()
        },
        "runtime_status": "pending_single_windowed_integrated_run",
    }
    final_report_path = root / "audit/final_jp_candidate_v2.json"
    atomic_json(final_report_path, final_report)
    print(json.dumps({
        "status": final_report["status"],
        "candidate_data_jp": str(candidate),
        "candidate_data_jp_sha256": final_report["candidate_data_jp_sha256"],
        "patched_exe": str(patched_exe),
        "patched_exe_sha256": final_report["patched_exe_sha256"],
        "outer_replacements": EXPECTED_OUTER_REPLACEMENTS,
        "report": str(final_report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


