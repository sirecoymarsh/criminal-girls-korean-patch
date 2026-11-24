#!/usr/bin/env python3
"""Build the complete structured-text catalog, including camp/punishment data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_text_catalog import build_catalog, keyed_pair_entries


def write_outputs(entries: list[dict], summary: dict, catalog: Path, summary_path: Path) -> None:
    uids = [entry["uid"] for entry in entries]
    if len(set(uids)) != len(uids):
        summary["issues"].append({"type": "duplicate_uid", "duplicate_count": len(uids) - len(set(uids))})
    summary.update({
        "schema": "criminal-girls.contextual-text-catalog-summary.v2",
        "entry_count": len(entries),
        "lane_counts": {
            lane: sum(entry["lane"] == lane for entry in entries)
            for lane in sorted({entry["lane"] for entry in entries})
        },
        "source_file_count": len(summary["sources"]),
        "japanese_character_count": sum(len(entry["source_ja"]) for entry in entries),
        "english_reference_character_count": sum(len(entry["reference_en"]) for entry in entries),
        "issue_count": len(summary["issues"]),
    })
    catalog.parent.mkdir(parents=True, exist_ok=True)
    temp_catalog = catalog.with_name(catalog.name + ".tmp")
    with temp_catalog.open("w", encoding="utf-8", newline="\n") as dst:
        for entry in entries:
            dst.write(json.dumps(entry, ensure_ascii=False) + "\n")
    temp_catalog.replace(catalog)
    temp_summary = summary_path.with_name(summary_path.name + ".tmp")
    temp_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_summary.replace(summary_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-jp", type=Path, required=True)
    parser.add_argument("--field-en", type=Path, required=True)
    parser.add_argument("--system-jp", type=Path, required=True)
    parser.add_argument("--system-en", type=Path, required=True)
    parser.add_argument("--battle-jp", type=Path, required=True)
    parser.add_argument("--battle-en", type=Path, required=True)
    parser.add_argument("--punishment-jp", type=Path, required=True)
    parser.add_argument("--punishment-en", type=Path, required=True)
    parser.add_argument("--camp-jp", type=Path, required=True)
    parser.add_argument("--camp-en", type=Path, required=True)
    parser.add_argument("--option-jp", type=Path, required=True)
    parser.add_argument("--option-en", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    entries, summary = build_catalog(args)
    extras = [
        ("punishment_text", "oshioki_txt.dat", args.punishment_jp, args.punishment_en),
        ("camp_text", "camp_txt.dat", args.camp_jp, args.camp_en),
        ("title_option_text", "option.dat", args.option_jp, args.option_en),
    ]
    for lane, rel, jp_path, en_path in extras:
        new_entries, meta = keyed_pair_entries(lane, rel, jp_path, en_path, summary["issues"])
        entries.extend(new_entries)
        summary["sources"].append({"lane": lane, "file": rel, **meta})

    write_outputs(entries, summary, args.catalog, args.summary)
    print(json.dumps({key: summary[key] for key in summary if key not in {"issues", "sources"}}, ensure_ascii=False, indent=2))
    return 0 if not summary["issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
