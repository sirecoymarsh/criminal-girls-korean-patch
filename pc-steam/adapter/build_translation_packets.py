#!/usr/bin/env python3
"""Deduplicate the source catalog and create deterministic first-draft packets."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

JP_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
PLACEHOLDERS = {"dummy", "ダミー", "予備", "バッファ"}


def classify(source: str) -> tuple[str, str]:
    if not source:
        return "preserve", "empty"
    if source in PLACEHOLDERS:
        return "preserve", "development_placeholder"
    if not JP_RE.search(source):
        return "preserve", "non_japanese_literal"
    return "pending_draft", "translate"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.catalog.read_text(encoding="utf-8").splitlines() if line.strip()]
    grouped: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for row in rows:
        source = row["source_ja"]
        if source not in grouped:
            order.append(source)
        grouped[source].append(row)

    unique_rows = []
    for i, source in enumerate(order, 1):
        occurrences = grouped[source]
        status, reason = classify(source)
        references = []
        for row in occurrences:
            value = row.get("reference_en", "")
            if value not in references:
                references.append(value)
        unique_rows.append(
            {
                "source_id": f"src_{i:04d}",
                "source_ja": source,
                "reference_en": references[0] if references else "",
                "reference_variants": references[1:],
                "draft_ko": source if status == "preserve" else "",
                "status": status,
                "reason": reason,
                "occurrence_count": len(occurrences),
                "lanes": sorted({row["lane"] for row in occurrences}),
                "contexts": [
                    {
                        "uid": row["uid"],
                        "file": row["file"],
                        "record_index": row.get("record_index"),
                        "key": row.get("key"),
                        "next_source_ja": row.get("next_source_ja", ""),
                    }
                    for row in occurrences[:12]
                ],
                "context_truncated": len(occurrences) > 12,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in unique_rows), encoding="utf-8"
    )
    args.batch_dir.mkdir(parents=True, exist_ok=True)
    pending = [row for row in unique_rows if row["status"] == "pending_draft"]
    for old in args.batch_dir.glob("draft_packet_*.jsonl"):
        old.unlink()
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        path = args.batch_dir / f"draft_packet_{start // args.batch_size + 1:03d}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in batch), encoding="utf-8")

    summary = {
        "source_catalog_entries": len(rows),
        "unique_sources": len(unique_rows),
        "pending_draft": len(pending),
        "preserved": len(unique_rows) - len(pending),
        "batch_size": args.batch_size,
        "batch_count": (len(pending) + args.batch_size - 1) // args.batch_size,
        "policy": "Codex internal model only; finish all draft packets before the single integrated review pass.",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
