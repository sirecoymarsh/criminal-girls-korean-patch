#!/usr/bin/env python3
"""Audit the effective Japanese-based non-BSCR Korean translation map."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


SOURCE_FIELDS = (
    "source_id", "source_ja", "reference_en", "reference_variants",
    "occurrence_count", "lanes", "contexts", "context_truncated",
)
PRINTF_RE = re.compile(r"%(?:[0-9]+\$)?[-+#0 .'0-9*]*[A-Za-z%]")
DOLLAR_RE = re.compile(r"\$[0-9]+")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def has_kana(text: str) -> bool:
    return any(0x3040 <= ord(c) <= 0x30FF or 0x31F0 <= ord(c) <= 0x31FF for c in text)


def has_cjk(text: str) -> bool:
    return any(0x3400 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF for c in text)


def effective_text(row: dict) -> str | None:
    if row.get("status") == "review_complete":
        return row.get("reviewed_ko")
    if row.get("status") == "preserve":
        return row.get("source_ja")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("final", type=Path)
    ap.add_argument("baseline", type=Path)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()

    rows = read_jsonl(args.final)
    baseline = read_jsonl(args.baseline)
    catalog = read_jsonl(args.catalog)
    issues: list[dict] = []

    def add(row: dict | None, flag: str, detail=None) -> None:
        item = {"source_id": row.get("source_id") if row else None, "flag": flag}
        if detail is not None:
            item["detail"] = detail
        issues.append(item)

    ids = [r.get("source_id") for r in rows]
    if len(ids) != len(set(ids)):
        add(None, "duplicate_source_id")
    if len(rows) != len(baseline):
        add(None, "row_count_changed", [len(baseline), len(rows)])
    if ids != [r.get("source_id") for r in baseline]:
        add(None, "source_id_order_changed")
    baseline_by_id = {r["source_id"]: r for r in baseline}

    residue = []
    preserve_rows = []
    for row in rows:
        old = baseline_by_id.get(row.get("source_id"))
        if old is None:
            add(row, "unknown_source_id")
            continue
        changed = [name for name in SOURCE_FIELDS if row.get(name) != old.get(name)]
        if changed:
            add(row, "source_provenance_mutated", changed)

        status = row.get("status")
        target = effective_text(row)
        source = row.get("source_ja", "")
        if status not in {"review_complete", "preserve"}:
            add(row, "invalid_status", status)
            continue
        if not isinstance(target, str):
            add(row, "missing_effective_text")
            continue
        if status == "review_complete":
            if not target:
                add(row, "empty_translation")
            if row.get("review_source") != "Codex internal model":
                add(row, "review_model_mismatch", row.get("review_source"))
            accepted_review_passes = {
                "single_integrated_final_review_v2",
            }
            review_pass = str(row.get("review_pass", ""))
            if not (review_pass.startswith("jp_original_integrated_review") or review_pass in accepted_review_passes):
                add(row, "review_pass_mismatch", row.get("review_pass"))
            if row.get("semantic_source_language") != "ja-JP" or not row.get("jp_basis_verified"):
                add(row, "jp_basis_metadata_missing")
            if source.count("\n") != target.count("\n"):
                add(row, "newline_count_mismatch", [source.count("\n"), target.count("\n")])
            if Counter(PRINTF_RE.findall(source)) != Counter(PRINTF_RE.findall(target)):
                add(row, "printf_token_mismatch", [PRINTF_RE.findall(source), PRINTF_RE.findall(target)])
            if Counter(DOLLAR_RE.findall(source)) != Counter(DOLLAR_RE.findall(target)):
                add(row, "dollar_token_mismatch", [DOLLAR_RE.findall(source), DOLLAR_RE.findall(target)])
        else:
            preserve_rows.append({
                "source_id": row.get("source_id"), "source_ja": source,
                "reason": row.get("reason"), "lanes": row.get("lanes"),
            })
            if row.get("reviewed_ko") is not None:
                add(row, "preserve_has_translation")

        if "\uFFFD" in target:
            add(row, "replacement_character")
        if has_kana(target) or has_cjk(target):
            entry = {"source_id": row.get("source_id"), "status": status, "effective_text": target}
            residue.append(entry)
            add(row, "japanese_or_cjk_effective_residue", entry)

    catalog_sources = Counter(r.get("source_ja") for r in catalog)
    missing = [r.get("source_id") for r in rows if r.get("source_ja") not in catalog_sources]
    if missing:
        add(None, "sources_missing_from_catalog", missing)

    required_fixes = {
        "src_0720": "".join(map(chr, [0xBC84, 0xD37C])),
        "src_1058": "".join(map(chr, [0xC608, 0xBE44])),
    }
    by_id = {r.get("source_id"): r for r in rows}
    for source_id, expected in required_fixes.items():
        row = by_id.get(source_id)
        if row is None or row.get("status") != "review_complete" or row.get("reviewed_ko") != expected:
            add(row, "known_visible_placeholder_not_localized", expected)

    counts = Counter(r.get("status") for r in rows)
    flag_counts = Counter(i["flag"] for i in issues)
    report = {
        "status": "PASS" if not issues else "FAIL",
        "semantic_source_language": "Japanese (ja-JP)",
        "translation_model": "Codex internal model",
        "total_unique_strings": len(rows),
        "status_counts": dict(counts),
        "catalog_occurrences": len(catalog),
        "effective_japanese_or_cjk_residue_count": len(residue),
        "preserve_count": len(preserve_rows),
        "issue_count": len(issues),
        "issue_counts": dict(sorted(flag_counts.items())),
        "final_sha256": sha256(args.final),
        "baseline_sha256": sha256(args.baseline),
        "catalog_sha256": sha256(args.catalog),
        "preserves": preserve_rows,
        "residue": residue,
        "issues": issues,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"preserves", "residue", "issues"}}, ensure_ascii=True, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
