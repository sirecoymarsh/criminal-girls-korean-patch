#!/usr/bin/env python3
"""Independently verify staged BSCR v2 injection bytes and semantic slots."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from bscr_common import (
    assert_diff_in_allowlist,
    build_expected_bytes,
    catalog_by_uid,
    discover_payloads,
    parse_bscr,
    read_json_rows,
    rebuild_allowlist_ranges,
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
DEFAULT_REPORT = PROJECT / "audit" / "bscr_v2_injection_verification.json"
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
    sources = discover_payloads(args.source_root)
    outputs = discover_payloads(args.output_root)
    catalog = catalog_by_uid(catalog_rows)
    translations = translation_by_uid(translation_rows)
    rows_by_file: dict[str, list[dict]] = collections.defaultdict(list)
    for row in catalog.values():
        rows_by_file[str(row["file"])].append(row)

    errors: list[dict] = []
    if not validation["pass"]:
        errors.append({"code": "translation_map_invalid", "error_count": validation["error_count"]})
    if set(sources) != set(outputs):
        errors.append({
            "code": "payload_set_mismatch",
            "missing_outputs": sorted(set(sources) - set(outputs)),
            "unexpected_outputs": sorted(set(outputs) - set(sources)),
        })

    file_reports: list[dict] = []
    verified_translations = 0
    for logical_name in sorted(set(sources) & set(outputs)):
        source = parse_bscr(sources[logical_name], logical_name)
        output = parse_bscr(outputs[logical_name], logical_name)
        file_catalog = sorted(
            rows_by_file.get(logical_name, []),
            key=lambda row: (int(row["segment_index"]), int(row["relative_offset"])),
        )
        expected, changes = build_expected_bytes(source, file_catalog, translations, runtime_codec)
        ranges = rebuild_allowlist_ranges(source)
        diff = assert_diff_in_allowlist(source.data, output.data, ranges)
        exact_expected = output.data == expected
        file_errors: list[str] = []
        if source.header != output.header:
            file_errors.append("header_changed")
        if len(source.data) != len(output.data):
            file_errors.append("size_changed")
        if source.data[: source.pool_start] != output.data[: output.pool_start]:
            file_errors.append("prefix_before_h4_changed")
        if not diff["pass"]:
            file_errors.append("diff_outside_allowlist")
        if not exact_expected:
            file_errors.append("output_not_exact_expected_bytes")

        if len(source.segments) != len(output.segments):
            file_errors.append("pool_segment_count_changed")
        loader_count = int(output.header[3])
        output_pushes = list(output.pushes())
        if any(push.segment_index is None or push.segment_index >= loader_count for push in output_pushes):
            file_errors.append("runtime_string_table_misses_push")
        for change in changes:
            uid = change["uid"]
            semantic_target = str(translations[uid]["target_ko"])
            runtime_target = runtime_codec.encode_text(semantic_target)
            target = runtime_target.encode("utf-8")
            new_relative = int(change["new_relative_offset"])
            segment = output.segment_by_relative_offset.get(new_relative)
            if segment is None or segment.raw != target:
                file_errors.append(f"semantic_segment_mismatch:{uid}")
            elif runtime_codec.decode_text(segment.text) != semantic_target:
                file_errors.append(f"runtime_surrogate_roundtrip_mismatch:{uid}")
        if file_errors:
            errors.append({"file": logical_name, "codes": file_errors})
        verified_translations += len(changes)
        file_reports.append({
            "file": logical_name,
            "source_sha256": source.sha256,
            "output_sha256": output.sha256,
            "byte_identical": source.data == output.data,
            "translation_count": len(changes),
            "pool_segment_count": len(output.segments),
            "runtime_loader_string_count": int(output.header[3]),
            "all_pushes_resolve_in_runtime_table": not any(
                push.segment_index is None or push.segment_index >= int(output.header[3])
                for push in output.pushes()
            ),
            "exact_expected_bytes": exact_expected,
            "diff": diff,
            "errors": file_errors,
        })

    empty_map = not translation_rows
    empty_roundtrip = (
        empty_map
        and not errors
        and all(item["byte_identical"] for item in file_reports)
        and len(file_reports) == len(sources)
    )
    result = {
        "schema": "criminal-girls.bscr-injection-verification.v2",
        "pass": not errors,
        "source_file_count": len(sources),
        "output_file_count": len(outputs),
        "verified_translation_count": verified_translations,
        "runtime_text_encoding": "utf8_former_character_glyph_slots",
        "font_report": str(args.font_report),
        "font_report_sha256": runtime_codec.font_report_sha256,
        "runtime_surrogate_slot_count": len(runtime_codec.char_to_former),
        "empty_map": empty_map,
        "empty_map_byte_identical_roundtrip": empty_roundtrip if empty_map else None,
        "error_count": len(errors),
        "errors": errors,
        "files": file_reports,
    }
    write_json(args.report, result)
    print(json.dumps({
        "pass": result["pass"],
        "source_file_count": len(sources),
        "output_file_count": len(outputs),
        "verified_translation_count": verified_translations,
        "empty_map": empty_map,
        "empty_map_byte_identical_roundtrip": result["empty_map_byte_identical_roundtrip"],
        "error_count": len(errors),
        "report": str(args.report),
    }, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
