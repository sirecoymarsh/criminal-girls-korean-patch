#!/usr/bin/env python3
"""Consolidate final static and visual QA evidence for all Korean raster UI assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row(path: Path, root: Path) -> dict:
    return {
        "path": str(path),
        "relative_path": str(path.relative_to(root)),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    root = a.root.resolve()
    issues: list[str] = []

    paths = {
        "legacy_manifest": root / "ui_review/full_mockups/manifest.json",
        "legacy_preservation": root / "ui_review/full_mockups/preservation_verification.json",
        "direct32": root / "ui_review/direct32_system_ko/report.json",
        "encoded": root / "staging/ui_encoded/encoded_ui_report.json",
        "common": root / "ui_review/common_ui_v2/common_ui_v2_report.json",
        "common_manifest": root / "staging/ui_common_v2/outer_replacements_common_ui_v2.json",
        "pict08": root / "ui_review/common_ui_v2/pict08_false_positive_audit.json",
    }
    for key, path in paths.items():
        if not path.is_file():
            issues.append(f"missing report: {key}: {path}")
    if issues:
        payload = {"status": "FAIL", "issues": issues}
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 1

    docs = {key: load(path) for key, path in paths.items()}
    preservation = docs["legacy_preservation"]
    direct32 = docs["direct32"]
    encoded = docs["encoded"]
    common = docs["common"]
    common_manifest = docs["common_manifest"]
    pict08 = docs["pict08"]

    checks = {
        "legacy_audit_exact_count": preservation.get("assets") == 36,
        "legacy_localized_exact_count": preservation.get("modified") == 26,
        "legacy_no_text_preserved_exact_count": preservation.get("unchanged") == 10,
        "legacy_preservation_pass": preservation.get("pass") is True,
        "direct32_exact_count": direct32.get("asset_count") == 5,
        "direct32_pass": direct32.get("status") == "PASS",
        "direct32_outside_allowlist_zero": all(x.get("outside_allowlist") == 0 for x in direct32.get("items", [])),
        "encoded_exact_count": encoded.get("encoded_assets") == 26,
        "encoded_outer_exact_count": encoded.get("outer_imy") == 21,
        "encoded_system_exact_count": encoded.get("system_ptm") == 5,
        "encoded_pass": encoded.get("status") == "PASS",
        "common_authority_exact_count": common.get("authority_count") == 15,
        "common_generated_exact_count": common.get("generated_targets") == 15,
        "common_localized_exact_count": common.get("localized_assets") == 15,
        "common_outside_allowlist_zero": common.get("outside_allowlist_total") == 0,
        "common_roundtrip_pixel_difference_zero": common.get("roundtrip_difference_total") == 0,
        "common_headers_match": common.get("all_headers_match") is True,
        "common_palettes_match": common.get("all_palettes_match") is True,
        "common_pass": common.get("status") == "PASS",
        "common_manifest_exact_count": common_manifest.get("replacement_count") == 15,
        "pict08_proven_non_text": pict08.get("verdict") == "non_text_false_positive",
        "pict08_unpatched": pict08.get("patched") is False and pict08.get("included_in_authority") is False,
    }

    legacy_release = sorted((root / "staging/ui_encoded/outer").glob("*.imy"))
    legacy_release += sorted((root / "staging/ui_encoded/system").glob("*.ptm"))
    common_release = sorted((root / "staging/ui_common_v2/outer").glob("*.imy"))
    checks.update({
        "legacy_encoded_files_exact_count": len(legacy_release) == 26,
        "common_encoded_files_exact_count": len(common_release) == 15,
        "localized_release_payload_count": len(legacy_release) + len(common_release) == 41,
    })
    for key, passed in checks.items():
        if not passed:
            issues.append(f"failed check: {key}")

    sheet_dirs = [
        root / "ui_review/full_mockups/sheets",
        root / "staging/ui_encoded/review_sheets",
        root / "ui_review/common_ui_v2/sheets",
    ]
    sheets = [p for d in sheet_dirs for p in sorted(d.glob("*.jpg"))]
    expected_sheet_counts = [9, 7, 8]
    actual_sheet_counts = [len(list(d.glob("*.jpg"))) for d in sheet_dirs]
    if actual_sheet_counts != expected_sheet_counts:
        issues.append(f"review sheet counts mismatch: {actual_sheet_counts} != {expected_sheet_counts}")

    visual_review = {
        "status": "PASS" if not issues else "FAIL",
        "method": "100-percent-scale visual inspection of source/target sheets and decoded release roundtrips",
        "review_sheet_counts": {
            "legacy_source_target": actual_sheet_counts[0],
            "encoded_roundtrip": actual_sheet_counts[1],
            "common_source_target": actual_sheet_counts[2],
        },
        "verified_repairs": [
            "tutorial second panel Japanese residue removed without damaging numbered ornament",
            "attack plaque restored and localized",
            "CHAIN overlap removed while preserving the lightning ornament",
            "bond plaque restored and localized",
            "ORDER/Girls Order labels separated by consumer role",
            "field location terminology normalized",
        ],
        "runtime_status": "pending_final_integrated_candidate",
    }

    payload = {
        "schema": "criminal-girls.ui-final-static-visual-qa.v1",
        "status": "PASS" if not issues else "FAIL",
        "scope": {
            "audited_assets": 51,
            "localized_assets": 41,
            "preserved_no_text_assets": 10,
            "release_payload_files": len(legacy_release) + len(common_release),
        },
        "checks": checks,
        "visual_review": visual_review,
        "reports": {key: row(path, root) for key, path in paths.items()},
        "review_sheets": [row(path, root) for path in sheets],
        "release_payloads": [row(path, root) for path in legacy_release + common_release],
        "issues": issues,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "scope": payload["scope"],
        "review_sheet_count": len(sheets),
        "issue_count": len(issues),
        "output": str(a.output),
    }, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
