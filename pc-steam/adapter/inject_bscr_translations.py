#!/usr/bin/env python3
"""Inject validated occurrence-specific Korean strings into staged BSCR payloads."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from bscr_common import (
    assert_diff_in_allowlist,
    atomic_write_bytes,
    build_expected_bytes,
    catalog_by_uid,
    discover_payloads,
    parse_bscr,
    read_json_rows,
    rebuild_allowlist_ranges,
    sha256_bytes,
    translation_by_uid,
    validate_translation_rows,
    write_json,
)
from runtime_text_codec import load_runtime_text_codec


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT / "extracted" / "map_scripts" / "jp" / "payloads"
DEFAULT_CATALOG = PROJECT / "translation" / "bscr_v2" / "occurrence_catalog.jsonl"
DEFAULT_MAP = PROJECT / "translation" / "bscr_v2" / "translation_map.jsonl"
DEFAULT_OUTPUT = PROJECT / "translation" / "bscr_v2" / "injected_payloads"
DEFAULT_REPORT = PROJECT / "audit" / "bscr_v2_injection.json"
DEFAULT_FONT_REPORT = PROJECT / "staging" / "korean_font_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--font-report", type=Path, default=DEFAULT_FONT_REPORT)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    runtime_codec = load_runtime_text_codec(args.font_report)

    catalog_rows = read_json_rows(args.catalog)
    translation_rows = read_json_rows(args.map_path)
    validation = validate_translation_rows(
        catalog_rows,
        translation_rows,
        require_complete=not args.allow_incomplete,
        runtime_codec=runtime_codec,
    )
    if not validation["pass"]:
        result = {
            "schema": "criminal-girls.bscr-injection.v2",
            "pass": False,
            "stage": "translation_map_validation",
            "validation": validation,
            "source_root": str(args.source_root),
            "output_root": str(args.output_root),
        }
        write_json(args.report, result)
        print(json.dumps({"pass": False, "stage": result["stage"], "errors": validation["error_count"]}, indent=2))
        return 1

    sources = discover_payloads(args.source_root)
    catalog = catalog_by_uid(catalog_rows)
    translations = translation_by_uid(translation_rows)
    rows_by_file: dict[str, list[dict]] = collections.defaultdict(list)
    for row in catalog.values():
        rows_by_file[str(row["file"])].append(row)
    unknown_catalog_files = sorted(set(rows_by_file) - set(sources))
    if unknown_catalog_files:
        raise ValueError(f"catalog refers to missing payloads: {unknown_catalog_files}")

    file_reports: list[dict] = []
    total_changes = 0
    for logical_name, source_path in sorted(sources.items()):
        parsed = parse_bscr(source_path, logical_name)
        file_catalog = sorted(
            rows_by_file.get(logical_name, []),
            key=lambda row: (int(row["segment_index"]), int(row["relative_offset"])),
        )
        for row in file_catalog:
            if row["original_file_sha256"] != parsed.sha256:
                raise ValueError(
                    f"{logical_name}: original hash mismatch: "
                    f"{parsed.sha256} != {row['original_file_sha256']}"
                )
        output, changes = build_expected_bytes(parsed, file_catalog, translations, runtime_codec)
        ranges = rebuild_allowlist_ranges(parsed)
        diff = assert_diff_in_allowlist(parsed.data, output, ranges)
        if not diff["pass"]:
            raise ValueError(f"{logical_name}: bytes outside translation allowlist changed")
        if output[: parsed.pool_start] != parsed.data[: parsed.pool_start]:
            raise ValueError(f"{logical_name}: prefix before h4 changed")
        output_path = args.output_root.joinpath(*Path(logical_name).parts)
        atomic_write_bytes(output_path, output)
        reparsed = parse_bscr(output_path, logical_name)
        if reparsed.header != parsed.header or len(reparsed.data) != len(parsed.data):
            raise ValueError(f"{logical_name}: structure changed after injection")
        if len(reparsed.segments) != len(parsed.segments):
            raise ValueError(f"{logical_name}: pool segment count changed after compact rebuild")
        runtime_pushes = list(reparsed.pushes())
        loader_count = int(reparsed.header[3])
        if any(push.segment_index is None or push.segment_index >= loader_count for push in runtime_pushes):
            raise ValueError(f"{logical_name}: runtime string-table lookup would miss a push")
        file_reports.append({
            "file": logical_name,
            "source": str(source_path),
            "output": str(output_path),
            "source_sha256": parsed.sha256,
            "output_sha256": sha256_bytes(output),
            "byte_identical": output == parsed.data,
            "translation_count": len(changes),
            "pool_segment_count": len(reparsed.segments),
            "runtime_loader_string_count": loader_count,
            "all_pushes_resolve_in_runtime_table": True,
            "diff": diff,
            "changes": changes,
        })
        total_changes += len(changes)

    empty_map = not translation_rows
    roundtrip_pass = (not empty_map) or all(item["byte_identical"] for item in file_reports)
    result = {
        "schema": "criminal-girls.bscr-injection.v2",
        "pass": roundtrip_pass,
        "source_root": str(args.source_root),
        "catalog": str(args.catalog),
        "translation_map": str(args.map_path),
        "runtime_text_encoding": "utf8_former_character_glyph_slots",
        "font_report": str(args.font_report),
        "font_report_sha256": runtime_codec.font_report_sha256,
        "runtime_surrogate_slot_count": len(runtime_codec.char_to_former),
        "output_root": str(args.output_root),
        "source_file_count": len(sources),
        "output_file_count": len(file_reports),
        "translation_count": total_changes,
        "empty_map": empty_map,
        "empty_map_byte_identical_roundtrip": roundtrip_pass if empty_map else None,
        "files": file_reports,
    }
    write_json(args.report, result)
    print(json.dumps({
        "pass": result["pass"],
        "file_count": len(file_reports),
        "translation_count": total_changes,
        "empty_map": empty_map,
        "empty_map_byte_identical_roundtrip": result["empty_map_byte_identical_roundtrip"],
        "report": str(args.report),
    }, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

