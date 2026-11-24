#!/usr/bin/env python3
"""Validate/fan out BSCR v2 translation results by immutable occurrence UID."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bscr_common import (
    BscrError,
    catalog_by_uid,
    read_json_rows,
    validate_pool_expansion_evidence,
    validate_preserve_evidence,
    validate_translation_rows,
    write_json,
    write_jsonl,
)

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PROJECT / "translation" / "bscr_v2" / "occurrence_catalog.jsonl"
DEFAULT_MAP = PROJECT / "translation" / "bscr_v2" / "translation_map.jsonl"
DEFAULT_DRAFT_UNITS = PROJECT / "translation" / "bscr_v2" / "draft_units.jsonl"
DEFAULT_FANOUT = PROJECT / "translation" / "bscr_v2" / "occurrence_fanout.jsonl"
DEFAULT_REVIEW_PACKETS = PROJECT / "translation" / "bscr_v2" / "occurrence_review_packets.json"
DEFAULT_REPORT = PROJECT / "audit" / "bscr_v2_translation_map_validation.json"


def load_cluster_results(root: Path) -> list[dict]:
    if root.is_file():
        return read_json_rows(root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    rows: list[dict] = []
    for path in sorted(root.glob("*.json")) + sorted(root.glob("*.jsonl")):
        rows.extend(read_json_rows(path))
    return rows


def validate_clusters(draft_units: list[dict], result_rows: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    source = {row["cluster_id"]: row for row in draft_units}
    if len(source) != len(draft_units):
        raise BscrError("duplicate cluster_id in draft units")
    results: dict[str, dict] = {}
    errors: list[dict] = []
    for row in result_rows:
        cluster_id = row.get("cluster_id")
        if not isinstance(cluster_id, str) or not cluster_id:
            errors.append({"code": "missing_cluster_id"})
            continue
        if cluster_id in results:
            errors.append({"cluster_id": cluster_id, "code": "duplicate_cluster_result"})
            continue
        unit = source.get(cluster_id)
        if unit is None:
            errors.append({"cluster_id": cluster_id, "code": "unknown_cluster_id"})
            continue
        for field in ("source_ja", "reference_en"):
            if row.get(field) != unit.get(field):
                errors.append({"cluster_id": cluster_id, "code": "cluster_immutable_mismatch", "field": field})
        status = row.get("status")
        target = row.get("target_ko", "")
        if status not in {"pending", "translated", "preserve"}:
            errors.append({"cluster_id": cluster_id, "code": "invalid_cluster_status", "actual": status})
        if not isinstance(target, str):
            errors.append({"cluster_id": cluster_id, "code": "cluster_target_not_string"})
        elif status == "pending" and target:
            errors.append({"cluster_id": cluster_id, "code": "pending_cluster_has_target"})
        elif status == "translated" and not target:
            errors.append({"cluster_id": cluster_id, "code": "empty_cluster_translation"})
        elif status == "translated":
            cap = int(unit.get("max_utf8_bytes", 0))
            actual = len(target.encode("utf-8"))
            if actual > cap:
                for detail in validate_pool_expansion_evidence(
                    row.get("pool_expansion_evidence"), source_cap=cap, actual_size=actual
                ):
                    errors.append({
                        "cluster_id": cluster_id,
                        "code": "unproven_cluster_pool_expansion",
                        "detail": detail,
                    })
            elif row.get("pool_expansion_evidence") is not None:
                errors.append({
                    "cluster_id": cluster_id,
                    "code": "unnecessary_cluster_pool_expansion_evidence",
                })
        elif status == "preserve":
            if target:
                errors.append({"cluster_id": cluster_id, "code": "preserve_cluster_has_target"})
            for detail in validate_preserve_evidence(row.get("preserve_evidence")):
                errors.append({"cluster_id": cluster_id, "code": "unproven_cluster_preserve", "detail": detail})
        if unit.get("occurrence_review_required") and status in {"translated", "preserve"}:
            errors.append({
                "cluster_id": cluster_id,
                "code": "cluster_requires_occurrence_review",
                "reasons": unit.get("conflict_reasons", []),
            })
        results[cluster_id] = row
    return results, errors



def review_required_uids(path: Path) -> dict[str, str]:
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    clusters = doc.get("clusters", [])
    result: dict[str, str] = {}
    for cluster in clusters:
        cluster_id = cluster.get("cluster_id")
        for occurrence in cluster.get("occurrences", []):
            uid = occurrence.get("uid")
            if not isinstance(uid, str) or not isinstance(cluster_id, str):
                raise BscrError("invalid occurrence review packet identity")
            if uid in result:
                raise BscrError(f"duplicate review uid {uid}")
            result[uid] = cluster_id
    return result


def validate_occurrence_overrides(
    override_rows: list[dict], catalog: dict[str, dict], required: dict[str, str]
) -> tuple[dict[str, dict], list[dict]]:
    overrides: dict[str, dict] = {}
    errors: list[dict] = []
    immutable_fields = (
        "file", "segment_index", "relative_offset", "source_ja",
        "source_sha256", "source_utf8_bytes", "original_file_sha256",
    )
    for row in override_rows:
        uid = row.get("uid")
        if not isinstance(uid, str) or not uid:
            errors.append({"code": "missing_override_uid"})
            continue
        if uid in overrides:
            errors.append({"uid": uid, "code": "duplicate_occurrence_override"})
            continue
        source = catalog.get(uid)
        if source is None:
            errors.append({"uid": uid, "code": "unknown_override_uid"})
            continue
        if uid not in required:
            errors.append({"uid": uid, "code": "override_not_required"})
        for field in immutable_fields:
            if row.get(field) != source.get(field):
                errors.append({"uid": uid, "code": "override_immutable_mismatch", "field": field})
        if row.get("translation_cluster_id", required.get(uid)) != required.get(uid):
            errors.append({"uid": uid, "code": "override_cluster_mismatch"})
        overrides[uid] = row
    return overrides, errors

def fanout_clusters(args, catalog_rows: list[dict]) -> tuple[list[dict], dict]:
    draft_units = read_json_rows(args.draft_units)
    fanout_rows = read_json_rows(args.fanout_index)
    result_rows = load_cluster_results(args.clusters)
    results, errors = validate_clusters(draft_units, result_rows)
    catalog = catalog_by_uid(catalog_rows)
    required_overrides = review_required_uids(args.occurrence_review_packets)
    override_rows = load_cluster_results(args.occurrence_overrides) if args.occurrence_overrides else []
    overrides, override_errors = validate_occurrence_overrides(override_rows, catalog, required_overrides)
    errors.extend(override_errors)
    review_cluster_ids = set(required_overrides.values())
    if review_cluster_ids:
        covered_cluster_ids = {required_overrides[uid] for uid in required_overrides if uid in overrides}
        errors = [
            error for error in errors
            if not (
                error.get("code") == "cluster_requires_occurrence_review"
                and error.get("cluster_id") in covered_cluster_ids
            )
        ]
    fanout_by_uid = {row["uid"]: row for row in fanout_rows}
    if len(fanout_by_uid) != len(fanout_rows):
        errors.append({"code": "duplicate_uid_in_fanout_index"})
    if set(fanout_by_uid) != set(catalog):
        errors.append({
            "code": "fanout_uid_set_mismatch",
            "missing": sorted(set(catalog) - set(fanout_by_uid))[:100],
            "unexpected": sorted(set(fanout_by_uid) - set(catalog))[:100],
        })
    output: list[dict] = []
    status_counts: dict[str, int] = {}
    immutable_fields = (
        "uid", "file", "segment_index", "relative_offset", "source_ja",
        "source_sha256", "source_utf8_bytes", "original_file_sha256",
    )
    for uid, catalog_row in catalog.items():
        cluster_id = fanout_by_uid.get(uid, {}).get("cluster_id")
        cluster_result = results.get(cluster_id)
        occurrence_override = overrides.get(uid)
        row = {field: catalog_row[field] for field in immutable_fields}
        if uid in required_overrides:
            # Mixed clusters are never finalized by cluster fan-out.  A reviewed
            # occurrence-specific result is mandatory for a complete map.
            if occurrence_override is None:
                row.update(status="pending", target_ko="")
                row["translation_cluster_id"] = cluster_id
                row["occurrence_review_required"] = True
            else:
                status = occurrence_override["status"]
                row.update(status=status, target_ko=occurrence_override.get("target_ko", ""))
                if status == "preserve":
                    row["preserve_evidence"] = occurrence_override.get("preserve_evidence")
                if status == "translated" and occurrence_override.get("pool_expansion_evidence") is not None:
                    row["pool_expansion_evidence"] = occurrence_override.get("pool_expansion_evidence")
                row["translation_cluster_id"] = cluster_id
                row["occurrence_review_override"] = True
        elif cluster_result is None:
            row.update(status="pending", target_ko="")
        else:
            status = cluster_result["status"]
            row.update(status=status, target_ko=cluster_result.get("target_ko", ""))
            if status == "preserve":
                row["preserve_evidence"] = cluster_result.get("preserve_evidence")
            if status == "translated" and cluster_result.get("pool_expansion_evidence") is not None:
                row["pool_expansion_evidence"] = cluster_result.get("pool_expansion_evidence")
            row["translation_cluster_id"] = cluster_id
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        output.append(row)
    output.sort(key=lambda row: (row["file"], row["segment_index"], row["relative_offset"]))
    if errors:
        raise BscrError(json.dumps({"cluster_errors": errors[:100]}, ensure_ascii=False))
    write_jsonl(args.map_path, output)
    return output, {
        "cluster_result_count": len(result_rows),
        "resolved_cluster_count": len(results),
        "fanout_row_count": len(output),
        "fanout_status_counts": status_counts,
        "occurrence_review_required_count": len(required_overrides),
        "occurrence_override_result_count": len(overrides),
        "missing_occurrence_override_count": len(set(required_overrides) - set(overrides)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--expect-empty", action="store_true", help="require a zero-row map (round-trip gate)")
    parser.add_argument("--clusters", type=Path, help="cluster result JSON/JSONL file or directory to fan out")
    parser.add_argument("--draft-units", type=Path, default=DEFAULT_DRAFT_UNITS)
    parser.add_argument("--fanout-index", type=Path, default=DEFAULT_FANOUT)
    parser.add_argument("--occurrence-review-packets", type=Path, default=DEFAULT_REVIEW_PACKETS)
    parser.add_argument("--occurrence-overrides", type=Path, help="reviewed occurrence-specific result JSON/JSONL file or directory")
    args = parser.parse_args()

    catalog = read_json_rows(args.catalog)
    fanout_report = None
    if args.clusters:
        translations, fanout_report = fanout_clusters(args, catalog)
    else:
        translations = read_json_rows(args.map_path)
    result = validate_translation_rows(catalog, translations, require_complete=not args.allow_incomplete)
    if args.expect_empty and translations:
        result["errors"].append({"code": "map_not_empty", "actual_rows": len(translations)})
        result["error_count"] = len(result["errors"])
        result["pass"] = False
    result.update({
        "schema": "criminal-girls.bscr-translation-map-validation.v2",
        "catalog": str(args.catalog),
        "translation_map": str(args.map_path),
        "fanout": fanout_report,
    })
    write_json(args.report, result)
    print(json.dumps({
        "pass": result["pass"],
        "catalog_count": result["catalog_count"],
        "translation_row_count": result["translation_row_count"],
        "status_counts": result["status_counts"],
        "error_count": result["error_count"],
        "fanout": fanout_report,
        "report": str(args.report),
    }, ensure_ascii=False, indent=2))
    if not result["pass"]:
        for issue in result["errors"][:20]:
            print(json.dumps(issue, ensure_ascii=False))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
