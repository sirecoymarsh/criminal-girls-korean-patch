#!/usr/bin/env python3
"""Independently aggregate the final v2 release, fixture, ZIP, and scan evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("live_game", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    package = root / "release/korean_patch_jp_final_v2"
    reports = root / "release/reports"
    qa = load(root / "audit/final_jp_candidate_v2.json")
    manifest_path = package / "manifest.json"
    manifest = load(manifest_path)
    zip_path = root / "release/CriminalGirlsInviteOnly_KoreanPatch_jp_final_v2.zip"
    extracted = root / "workspace/release_zip_extract_v2_20260813/CriminalGirlsInviteOnly_KoreanPatch_v2"
    candidate_data = Path(qa["candidate_data_jp"])
    candidate_exe = Path(qa["patched_exe"])
    live_game = args.live_game.resolve()

    report_names = [
        "installer_package_build_v2.json",
        "installer_full_fixture_v2.json",
        "installer_mixed_rejection_v2.json",
        "installer_recover_install_mixed_v2.json",
        "installer_recover_restore_mixed_v2.json",
        "installer_backup_tamper_rejection_v2.json",
        "installer_package_tamper_rejection_v2.json",
        "installer_process_guard_v2.json",
        "installer_nth_replacement_rollback_v2.json",
        "installer_unknown_baseline_rejection_v2.json",
        "installer_different_path_process_v2.json",
        "extracted_zip_install_restore_v2.json",
        "installer_idempotence_v2.json",
        "installer_unicode_powershell51_v2.json",
        "release_static_integrity_v2.json",
        "defender_scan_korean_patch_jp_final_v2.json",
        "defender_scan_patched_exe_v2.json",
        "release_zip_v2.json",
        "defender_scan_release_zip_v2.json",
        "release_zip_extraction_audit_v2.json",
        "defender_scan_extracted_zip_v2.json",
    ]
    loaded_reports = {name: load(reports / name) for name in report_names}

    expected_files = {"manifest.json", *[str(x["path"]).replace("\\", "/") for x in manifest["files"]]}
    actual_files = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()}
    file_results = []
    manifest_files_ok = True
    for item in manifest["files"]:
        path = package / str(item["path"])
        present = path.is_file()
        size = path.stat().st_size if present else None
        digest = sha256(path) if present else None
        ok = present and size == int(item["size"]) and digest == str(item["sha256"]).lower()
        manifest_files_ok &= ok
        file_results.append({"path": item["path"], "size": size, "sha256": digest, "ok": ok})

    targets = {str(x["id"]): x for x in manifest["game"]["targets"]}
    payload_data = package / targets["data_jp"]["payload_path"]
    payload_exe = package / targets["executable"]["payload_path"]
    extracted_data = extracted / targets["data_jp"]["payload_path"]
    extracted_exe = extracted / targets["executable"]["payload_path"]
    live_data = live_game / targets["data_jp"]["relative_path"]
    live_exe = live_game / targets["executable"]["relative_path"]

    with zipfile.ZipFile(zip_path, "r", allowZip64=True) as zf:
        zip_names = zf.namelist()

    checks = {
        "candidate_qa_pass": qa.get("status") == "PASS" and qa.get("installed_to_game") is False,
        "translation_contract": qa.get("language_contract") == "Japanese semantic source; Korean replaces Japanese slot; English archive unchanged",
        "all_supporting_reports_pass": all(r.get("status") == "PASS" for r in loaded_reports.values()),
        "manifest_schema_v2": manifest.get("schema") == "criminal-girls-invite-only.ko-patch.v2",
        "translation_model_internal": manifest.get("translation_model") == "Codex internal model",
        "package_exact_nine_file_allowlist": actual_files == expected_files and len(actual_files) == 9,
        "package_manifest_files_match": manifest_files_ok,
        "data_payload_matches_candidate": sha256(payload_data) == sha256(candidate_data) == qa["candidate_data_jp_sha256"],
        "exe_payload_matches_candidate": sha256(payload_exe) == sha256(candidate_exe) == qa["patched_exe_sha256"],
        "payloads_are_independent_copies": not os.path.samefile(payload_data, candidate_data) and not os.path.samefile(payload_exe, candidate_exe),
        "extracted_payloads_match": sha256(extracted_data) == sha256(payload_data) and sha256(extracted_exe) == sha256(payload_exe),
        "zip_hash_bound": sha256(zip_path) == loaded_reports["release_zip_v2.json"]["zip_sha256"] == loaded_reports["defender_scan_release_zip_v2.json"]["sha256"],
        "zip_exact_nine_members": len(zip_names) == 9 and all(name.startswith("CriminalGirlsInviteOnly_KoreanPatch_v2/") for name in zip_names),
        "live_original_data_unchanged": live_data.stat().st_size == int(targets["data_jp"]["baseline_size"]) and sha256(live_data) == targets["data_jp"]["baseline_sha256"],
        "live_original_exe_unchanged": live_exe.stat().st_size == int(targets["executable"]["baseline_size"]) and sha256(live_exe) == targets["executable"]["baseline_sha256"],
        "composition_static_pass": load(root / "audit/name_composition_verify_final_v2.json").get("status") == "PASS",
        "composition_patch_pass": load(root / "audit/name_composition_patch_final_v2.json").get("status") == "PASS",
        "ui_static_visual_qa_pass": load(root / "audit/ui_final_static_visual_qa.json").get("status") == "PASS",
        "runtime_font_pass": load(root / "staging/runtime_font_report.json").get("status") == "PASS",
        "runtime_launch_stable": load(root / "audit/runtime_composition_v10_launch_v2.json").get("status") == "PASS",
    }
    errors = [name for name, value in checks.items() if not value]
    zip_report = loaded_reports["release_zip_v2.json"]
    result = {
        "schema": "criminal-girls.installer-release-verification.v2",
        "status": "PASS" if not errors else "FAIL",
        "installed_to_original_game": False,
        "manual_runtime_review": "PENDING_USER_SCREEN_CONFIRMATION",
        "package": str(package),
        "package_file_count": len(actual_files),
        "manifest_sha256": sha256(manifest_path),
        "zip": str(zip_path),
        "zip_size": zip_path.stat().st_size,
        "zip_sha256": sha256(zip_path),
        "zip_member_count": len(zip_names),
        "data_payload": {"size": payload_data.stat().st_size, "sha256": sha256(payload_data), "independent": not os.path.samefile(payload_data, candidate_data)},
        "executable_payload": {"size": payload_exe.stat().st_size, "sha256": sha256(payload_exe), "independent": not os.path.samefile(payload_exe, candidate_exe)},
        "live_original": {
            "game_root": str(live_game),
            "data_sha256": sha256(live_data),
            "exe_sha256": sha256(live_exe),
        },
        "coverage": manifest["coverage"],
        "checks": checks,
        "errors": errors,
        "package_files": file_results,
        "reports": {name: {"path": str(reports / name), "sha256": sha256(reports / name)} for name in report_names},
        "zip_report_manifest_sha256": zip_report["package_manifest_sha256"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"package_files", "reports"}}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
