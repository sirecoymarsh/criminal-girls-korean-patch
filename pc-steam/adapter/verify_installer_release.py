#!/usr/bin/env python3
"""Independently verify the final transactional Korean patch release."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    package = root / "release/korean_patch_jp_final_v1"
    reports = root / "release/reports"
    candidate_qa = load(root / "staging/reports/final_candidate_qa.json")
    manifest_path = package / "manifest.json"
    manifest = load(manifest_path)
    build = load(reports / "installer_package_build.json")
    self_verify = load(reports / "installer_package_self_verification.json")
    builder_fixture = load(reports / "installer_builder_fixture.json")
    full_fixture = load(reports / "installer_full_fixture.json")
    matrix = load(reports / "installer_fixture_matrix.json")
    defender = load(reports / "defender_scan_korean_patch_jp_final_v1.json")

    expected = {"manifest.json", *(str(x["path"]).replace("\\", "/") for x in manifest["files"])}
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()}
    manifest_files_ok = True
    file_results = []
    for item in manifest["files"]:
        path = package / Path(str(item["path"]).replace("/", "\\"))
        present = path.is_file()
        size = path.stat().st_size if present else None
        digest = sha256(path) if present else None
        ok = present and size == int(item["size"]) and digest == str(item["sha256"]).lower()
        manifest_files_ok = manifest_files_ok and ok
        file_results.append({"path": item["path"], "size": size, "sha256": digest, "ok": ok})

    candidate = Path(candidate_qa["candidate"])
    payload = package / Path(str(manifest["payload"]["path"]).replace("/", "\\"))
    live_archive = args.live_game.resolve() / "data/data_jp.dat"
    live_hash = sha256(live_archive)
    live_size = live_archive.stat().st_size
    live_temps = sorted(p.name for p in live_archive.parent.glob(".cgko_*") if p.is_file())
    manifest_hash = sha256(manifest_path)
    payload_hash = sha256(payload)
    candidate_hash = sha256(candidate)
    matrix_cases = list(matrix.get("cases", []))

    checks = {
        "candidate_qa_pass": candidate_qa.get("status") == "PASS",
        "candidate_declared_not_installed": candidate_qa.get("installed_to_game") is False,
        "package_exact_allowlist": actual == expected and len(actual) == 8,
        "package_manifest_files_match": manifest_files_ok,
        "package_manifest_hash_bound": manifest_hash == build.get("manifest_sha256") == self_verify.get("manifest_sha256") == defender.get("manifest_sha256"),
        "payload_matches_candidate": payload_hash == candidate_hash == candidate_qa.get("candidate_sha256") == manifest["game"]["patched_sha256"],
        "payload_is_independent_copy": build.get("payload_link_mode") == "independent_copy" and build.get("payload_detached_from_candidate") is True and not payload.samefile(candidate),
        "powershell_51_self_verification": self_verify.get("status") == "PASS" and self_verify.get("exit_code") == 0 and all(self_verify.get("script_syntax", {}).values()),
        "independent_builder_fixture": builder_fixture.get("status") == "PASS" and builder_fixture.get("independent_file_id") is True and builder_fixture.get("fixture_removed") is True,
        "full_size_unicode_fixture": full_fixture.get("status") == "PASS" and full_fixture.get("original_unchanged") is True and full_fixture.get("fixed_restore_pass") is True and full_fixture.get("leftover_transaction_files") == 0,
        "tamper_recovery_matrix": matrix.get("status") == "PASS" and len(matrix_cases) == 7 and all(x.get("status") == "PASS" for x in matrix_cases) and matrix.get("leftover_transaction_files") == 0,
        "defender_scan_clean": defender.get("status") == "PASS" and defender.get("scan_exit_code") == 0 and defender.get("new_detection_count") == 0 and defender.get("scan_target_detection_count") == 0 and defender.get("source_unchanged") is True and defender.get("disposable_copy_unchanged") is True,
        "live_original_still_unchanged": live_size == manifest["game"]["baseline_size"] and live_hash == manifest["game"]["baseline_sha256"] and not live_temps,
        "semantic_source_is_japanese": manifest.get("semantic_source_language") == "ja-JP" and manifest.get("translation_model") == "Codex internal model",
    }
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "installed_to_game": False,
        "package": str(package),
        "package_file_count": len(actual),
        "manifest_sha256": manifest_hash,
        "payload_sha256": payload_hash,
        "payload_size": payload.stat().st_size,
        "payload_independent_from_candidate": not payload.samefile(candidate),
        "live_archive": str(live_archive),
        "live_size": live_size,
        "live_sha256": live_hash,
        "live_transaction_files": live_temps,
        "fixture_case_count": len(matrix_cases),
        "defender_signature_version": defender["defender"]["signature_version"],
        "defender_scan_target_detections": defender["scan_target_detection_count"],
        "checks": checks,
        "package_files": file_results,
        "source_reports": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in {
                "candidate_qa": root / "staging/reports/final_candidate_qa.json",
                "package_build": reports / "installer_package_build.json",
                "package_self_verification": reports / "installer_package_self_verification.json",
                "builder_fixture": reports / "installer_builder_fixture.json",
                "full_fixture": reports / "installer_full_fixture.json",
                "fixture_matrix": reports / "installer_fixture_matrix.json",
                "defender_scan": reports / "defender_scan_korean_patch_jp_final_v1.json",
            }.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())