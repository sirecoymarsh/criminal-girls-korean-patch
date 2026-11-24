#!/usr/bin/env python3
"""Cross-check the staged final archive against all localization build reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("baseline", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    root = args.root
    issues: list[str] = []

    paths = {
        "translation_qa": root / "translation/jp_original_review/jp_final_qa.json",
        "translation_summary": root / "translation/jp_original_review/jp_review_summary.json",
        "text_injection": root / "staging/localized_text_report.json",
        "font": root / "staging/korean_font_report.json",
        "containers": root / "staging/localized_containers_report.json",
        "ui_encoder": root / "staging/ui_encoded/encoded_ui_report.json",
        "ui_preservation": root / "ui_review/full_mockups/preservation_verification.json",
        "outer_manifest": root / "staging/manifests/outer_replacements_jp_final.json",
        "archive_build": root / "staging/reports/data_jp_jp_final.json",
        "archive_diff": root / "staging/reports/final_archive_diff_jp_final.json",
    }
    for name, path in paths.items():
        if not path.is_file():
            issues.append(f"missing report: {name}: {path}")
    if not args.baseline.is_file():
        issues.append(f"missing baseline: {args.baseline}")
    if not args.candidate.is_file():
        issues.append(f"missing candidate: {args.candidate}")
    if issues:
        payload = {"status": "FAIL", "issues": issues}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 1

    data = {name: load(path) for name, path in paths.items()}
    manifest_items = data["outer_manifest"]["replacements"]
    manifest_by_index = {item["index"]: item for item in manifest_items}
    if len(manifest_items) != 151 or len(manifest_by_index) != 151:
        issues.append("outer manifest must contain 151 unique indices")

    diff = data["archive_diff"]
    diff_by_index = {item.get("right_index"): item for item in diff["differences"]}
    if set(diff_by_index) != set(manifest_by_index):
        issues.append("archive diff indices do not exactly match the outer manifest")
    for index, item in manifest_by_index.items():
        d = diff_by_index.get(index)
        if d and d.get("name") != item["expected_name"]:
            issues.append(f"entry name mismatch at {index}")
        p = Path(item["path"])
        if not p.is_file():
            issues.append(f"missing replacement payload: {p}")
            continue
        actual_size = p.stat().st_size
        actual_hash = sha256(p)
        if actual_size != item.get("size") or actual_hash != item.get("sha256"):
            issues.append(f"replacement provenance mismatch: {index}: {p}")

    build = data["archive_build"]
    verified = {item["index"]: item for item in build["verified_replacements"]}
    if set(verified) != set(manifest_by_index):
        issues.append("archive builder verification set does not match manifest")
    for index, item in manifest_by_index.items():
        got = verified.get(index)
        if got and (got["name"] != item["expected_name"] or got["sha256"] != item["sha256"]):
            issues.append(f"archive payload verification mismatch: {index}")

    checks = {
        "translation_qa_pass": data["translation_qa"].get("status") == "PASS" and data["translation_qa"].get("issue_count") == 0,
        "translation_unique_count": data["translation_qa"].get("total_unique_strings") == 2709,
        "translation_reviewed_count": data["translation_qa"].get("review_complete") == 2637,
        "translation_preserve_count": data["translation_qa"].get("preserve") == 72,
        "translated_occurrence_count": data["text_injection"].get("translated_occurrences") == 9153,
        "localized_output_file_count": data["text_injection"].get("output_file_count") == 241,
        "font_pass": data["font"].get("passed") is True and not data["font"].get("unsupported"),
        "container_pass": data["containers"].get("all_replacements_verified") is True and data["containers"].get("container_count") == 110,
        "ui_encoder_pass": data["ui_encoder"].get("status") == "PASS" and data["ui_encoder"].get("encoded_assets") == 26,
        "ui_preservation_pass": data["ui_preservation"].get("pass") is True and data["ui_preservation"].get("assets") == 36,
        "archive_entry_count": build.get("entry_count") == 8442 and diff.get("left_entry_count") == 8442 and diff.get("right_entry_count") == 8442,
        "archive_exact_changed_set": diff.get("different_entry_count") == 151 and diff.get("identical_entry_count") == 8291,
        "archive_extension_counts": diff.get("different_extension_counts") == {".tpk": 109, ".bak": 21, ".imy": 21},
        "archive_builder_verified": len(build.get("verified_replacements", [])) == 151,
        "candidate_size_matches_report": args.candidate.stat().st_size == build.get("output_size"),
    }
    for name, passed in checks.items():
        if not passed:
            issues.append(f"failed check: {name}")

    baseline_hash = sha256(args.baseline)
    candidate_hash = sha256(args.candidate)
    if baseline_hash != data["outer_manifest"].get("baseline_sha256"):
        issues.append("baseline SHA-256 mismatch")

    payload = {
        "status": "PASS" if not issues else "FAIL",
        "installed_to_game": False,
        "baseline": str(args.baseline),
        "baseline_size": args.baseline.stat().st_size,
        "baseline_sha256": baseline_hash,
        "candidate": str(args.candidate),
        "candidate_size": args.candidate.stat().st_size,
        "candidate_sha256": candidate_hash,
        "checks": checks,
        "issues": issues,
        "report_sha256": {name: sha256(path) for name, path in paths.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k not in {"checks", "issues", "report_sha256"}}, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": checks, "issue_count": len(issues)}, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
