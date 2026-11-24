#!/usr/bin/env python3
"""Build authoritative occurrence-scoped BSCR v2 catalog and context packets."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from bscr_common import (
    DISPLAY_CONSUMERS,
    PUSH_OPCODE,
    align_records,
    discover_payloads,
    has_japanese,
    newline_signature,
    parse_bscr,
    protected_tokens,
    sha256_file,
    stable_uid,
    write_json,
    write_jsonl,
)


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_JP_ROOT = PROJECT / "extracted" / "map_scripts" / "jp" / "payloads"
DEFAULT_EN_ROOT = PROJECT / "extracted" / "map_scripts" / "en" / "payloads"
DEFAULT_OUTPUT = PROJECT / "translation" / "bscr_v2"
DEFAULT_AUDIT = PROJECT / "audit" / "bscr_v2_catalog.json"


def push_context(parsed) -> dict[int, list]:
    result: dict[int, list] = collections.defaultdict(list)
    for push in parsed.pushes():
        if push.segment_index is not None:
            result[push.segment_index].append(push)
    return result


def reference_for_pushes(en, alignment, jp_pushes: list) -> tuple[str, list[dict]]:
    variants: collections.Counter[str] = collections.Counter()
    evidence: list[dict] = []
    for push in jp_pushes:
        en_record_index = alignment.jp_to_en.get(push.record_index)
        if en_record_index is None:
            evidence.append({
                "jp_record_index": push.record_index,
                "en_record_index": None,
                "reference_en": "",
                "reason": "record_not_in_matching_block",
            })
            continue
        en_record = en.record(en_record_index)
        if en_record[:4] != PUSH_OPCODE:
            evidence.append({
                "jp_record_index": push.record_index,
                "en_record_index": en_record_index,
                "reference_en": "",
                "reason": "aligned_record_not_push",
            })
            continue
        operand = int.from_bytes(en_record[4:8], "little")
        segment = en.segment_by_relative_offset.get(operand)
        if segment is None:
            evidence.append({
                "jp_record_index": push.record_index,
                "en_record_index": en_record_index,
                "reference_en": "",
                "reason": "en_operand_not_segment_start",
            })
            continue
        variants[segment.text] += 1
        evidence.append({
            "jp_record_index": push.record_index,
            "en_record_index": en_record_index,
            "reference_en": segment.text,
            "en_segment_index": segment.index,
            "en_relative_offset": segment.relative_offset,
            "reason": "normalized_record_alignment",
        })
    reference = ""
    if variants:
        reference = sorted(variants.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return reference, evidence


def neighboring_japanese(segments, index: int, direction: int) -> str:
    cursor = index + direction
    while 0 <= cursor < len(segments):
        text = segments[cursor].text
        if has_japanese(text):
            return text
        cursor += direction
    return ""


def build(args: argparse.Namespace) -> dict:
    jp_paths = discover_payloads(args.jp_root)
    en_paths = discover_payloads(args.en_root)
    if set(jp_paths) != set(en_paths):
        missing_en = sorted(set(jp_paths) - set(en_paths))
        missing_jp = sorted(set(en_paths) - set(jp_paths))
        raise ValueError(f"JP/EN payload sets differ: missing_en={missing_en} missing_jp={missing_jp}")

    args.output.mkdir(parents=True, exist_ok=True)
    packet_root = args.output / "packets"
    packet_root.mkdir(parents=True, exist_ok=True)
    for stale_packet in packet_root.glob("packet_*.json"):
        stale_packet.unlink()

    catalog: list[dict] = []
    file_summaries: list[dict] = []
    classification_counts: collections.Counter[str] = collections.Counter()
    reference_counts: collections.Counter[str] = collections.Counter()
    seen_uids: set[str] = set()

    for logical_name in sorted(jp_paths):
        jp = parse_bscr(jp_paths[logical_name], logical_name)
        en = parse_bscr(en_paths[logical_name], logical_name)
        alignment = align_records(jp, en, autojunk=True)
        en_pushes = {push.record_index: push for push in en.pushes()}
        jp_refs = push_context(jp)
        file_candidate_count = 0
        for segment in jp.segments:
            if not has_japanese(segment.text):
                continue
            pushes = jp_refs.get(segment.index, [])
            if not pushes:
                # Unreferenced is not called a runtime candidate: there is no
                # consumer evidence at all. Referenced-unknown, however, is.
                continue
            roles = sorted({push.consumer_role for push in pushes if push.consumer_role})
            consumers = sorted({push.consumer_opcode for push in pushes if push.consumer_opcode})
            candidate_class = "display_known" if roles else "referenced_unknown"
            classification_counts[candidate_class] += 1

            uid = stable_uid(logical_name, segment)
            if uid in seen_uids:
                raise ValueError(f"duplicate stable uid {uid}")
            seen_uids.add(uid)
            reference_en, reference_evidence = reference_for_pushes(en, alignment, pushes)
            reference_counts["mapped" if reference_en else "unmapped"] += 1
            row = {
                "uid": uid,
                "file": logical_name,
                "segment_index": segment.index,
                "relative_offset": segment.relative_offset,
                "absolute_offset": segment.absolute_offset,
                "source_ja": segment.text,
                "source_sha256": segment.sha256,
                "source_utf8_bytes": segment.byte_length,
                "max_utf8_bytes": segment.byte_length,
                "protected_tokens": protected_tokens(segment.text),
                "newline_signature": newline_signature(segment.text),
                "original_file_sha256": jp.sha256,
                "candidate_class": candidate_class,
                "consumer_roles": roles,
                "consumer_opcodes": consumers,
                "push_record_indices": [push.record_index for push in pushes],
                "push_reference_count": len(pushes),
                "reference_en": reference_en,
                "reference_alignment": reference_evidence,
                "prev_ja": neighboring_japanese(jp.segments, segment.index, -1),
                "next_ja": neighboring_japanese(jp.segments, segment.index, +1),
                "status": "pending",
                "target_ko": "",
            }
            catalog.append(row)
            file_candidate_count += 1

        file_summaries.append({
            "file": logical_name,
            "jp_path": str(jp.path),
            "en_path": str(en.path),
            "jp_sha256": jp.sha256,
            "en_sha256": en.sha256,
            "pool_start_h4": jp.pool_start,
            "code_size_h5": jp.code_size,
            "code_start_h6": jp.code_start,
            "record_count_jp": jp.record_count,
            "record_count_en": en.record_count,
            "alignment": {
                "algorithm": "SequenceMatcher(normalized_16B_records)",
                "push_operand_normalization": "u32 at +4 set to 0 for opcode 1AF0F15A",
                "autojunk": alignment.autojunk,
                "ratio": alignment.ratio,
                "matching_blocks": alignment.matching_blocks,
                "matched_records": alignment.matched_records,
            },
            "candidate_count": file_candidate_count,
        })

    catalog.sort(key=lambda row: (row["file"], row["segment_index"], row["relative_offset"]))
    catalog_path = args.output / "occurrence_catalog.jsonl"
    write_jsonl(catalog_path, catalog)

    # Draft once per exact (Japanese source, aligned English reference) cluster.
    # Occurrence UIDs remain authoritative and are fanned out only after review.
    clusters_by_key: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for row in catalog:
        clusters_by_key[(row["source_ja"], row["reference_en"])].append(row)
    draft_units: list[dict] = []
    fanout_rows: list[dict] = []
    for cluster_number, (key, rows) in enumerate(
        sorted(
            clusters_by_key.items(),
            key=lambda item: (item[0][0], item[0][1]),
        ),
        1,
    ):
        source_ja, reference_en = key
        cluster_id = f"bscr2_c{cluster_number:05d}"
        contexts = []
        seen_contexts = set()
        for row in rows:
            context_key = (row["prev_ja"], row["next_ja"], row["file"])
            if context_key in seen_contexts:
                continue
            seen_contexts.add(context_key)
            contexts.append({
                "uid": row["uid"],
                "file": row["file"],
                "prev_ja": row["prev_ja"],
                "next_ja": row["next_ja"],
                "candidate_class": row["candidate_class"],
                "consumer_roles": row["consumer_roles"],
            })
            if len(contexts) >= args.context_samples:
                break
        source_caps = sorted({int(row["source_utf8_bytes"]) for row in rows})
        token_variants = {tuple(row["protected_tokens"]) for row in rows}
        newline_variants = {
            (int(row["newline_signature"]["lf"]), int(row["newline_signature"]["cr"]))
            for row in rows
        }
        conflict_reasons = []
        if len(token_variants) != 1:
            conflict_reasons.append("protected_token_variants")
        if len(newline_variants) != 1:
            conflict_reasons.append("newline_variants")
        if len(source_caps) != 1:
            conflict_reasons.append("byte_cap_variants")
        candidate_classes = sorted({row["candidate_class"] for row in rows})
        consumer_role_sets = {tuple(row["consumer_roles"]) for row in rows}
        if len(candidate_classes) != 1:
            conflict_reasons.append("mixed_candidate_classes")
        if len(consumer_role_sets) != 1:
            conflict_reasons.append("mixed_consumer_roles")
        unit = {
            "cluster_id": cluster_id,
            "source_ja": source_ja,
            "reference_en": reference_en,
            "occurrence_count": len(rows),
            "uids": [row["uid"] for row in rows],
            "max_utf8_bytes": min(source_caps),
            "protected_tokens": rows[0]["protected_tokens"],
            "newline_signature": rows[0]["newline_signature"],
            "candidate_classes": candidate_classes,
            "consumer_roles": sorted({role for row in rows for role in row["consumer_roles"]}),
            "context_samples": contexts,
            "occurrence_review_required": bool(conflict_reasons),
            "conflict_reasons": conflict_reasons,
            "status": "pending",
            "target_ko": "",
        }
        draft_units.append(unit)
        for row in rows:
            fanout_rows.append({
                "uid": row["uid"],
                "cluster_id": cluster_id,
                "file": row["file"],
                "segment_index": row["segment_index"],
                "relative_offset": row["relative_offset"],
                "source_sha256": row["source_sha256"],
                "original_file_sha256": row["original_file_sha256"],
            })
    draft_path = args.output / "draft_units.jsonl"
    fanout_path = args.output / "occurrence_fanout.jsonl"
    write_jsonl(draft_path, draft_units)
    fanout_rows.sort(key=lambda row: (row["file"], row["segment_index"], row["relative_offset"]))
    write_jsonl(fanout_path, fanout_rows)

    # Mixed display/consumer clusters cannot safely share one final verdict.
    # Emit every occurrence with full local context for a separate override pass.
    catalog_by_local_uid = {row["uid"]: row for row in catalog}
    review_clusters = []
    for unit in draft_units:
        if not unit["occurrence_review_required"]:
            continue
        occurrences = []
        for uid in unit["uids"]:
            row = catalog_by_local_uid[uid]
            occurrences.append({
                "uid": row["uid"],
                "file": row["file"],
                "segment_index": row["segment_index"],
                "relative_offset": row["relative_offset"],
                "absolute_offset": row["absolute_offset"],
                "source_ja": row["source_ja"],
                "source_sha256": row["source_sha256"],
                "source_utf8_bytes": row["source_utf8_bytes"],
                "max_utf8_bytes": row["max_utf8_bytes"],
                "protected_tokens": row["protected_tokens"],
                "newline_signature": row["newline_signature"],
                "original_file_sha256": row["original_file_sha256"],
                "candidate_class": row["candidate_class"],
                "consumer_roles": row["consumer_roles"],
                "consumer_opcodes": row["consumer_opcodes"],
                "push_record_indices": row["push_record_indices"],
                "reference_en": row["reference_en"],
                "reference_alignment": row["reference_alignment"],
                "prev_ja": row["prev_ja"],
                "next_ja": row["next_ja"],
                "status": "pending",
                "target_ko": "",
            })
        review_clusters.append({
            "cluster_id": unit["cluster_id"],
            "conflict_reasons": unit["conflict_reasons"],
            "source_ja": unit["source_ja"],
            "reference_en": unit["reference_en"],
            "occurrence_count": len(occurrences),
            "occurrences": occurrences,
        })
    review_path = args.output / "occurrence_review_packets.json"
    write_json(review_path, {
        "schema": "criminal-girls.bscr-occurrence-review-packets.v2",
        "policy": "Every occurrence requires an occurrence-specific result; cluster result is not final for these clusters.",
        "cluster_count": len(review_clusters),
        "occurrence_count": sum(item["occurrence_count"] for item in review_clusters),
        "clusters": review_clusters,
    })

    packets: list[dict] = []
    for start in range(0, len(draft_units), args.packet_size):
        entries = draft_units[start : start + args.packet_size]
        packet_number = len(packets) + 1
        name = f"packet_{packet_number:04d}.json"
        payload = {
            "schema": "criminal-girls.bscr-compact-draft-packet.v2",
            "packet_id": f"bscr_v2_{packet_number:04d}",
            "source_language": "ja",
            "target_language": "ko",
            "semantic_source": "Japanese BSCR",
            "reference_only": "paired English BSCR aligned by normalized records",
            "cluster_key": "exact (source_ja, reference_en)",
            "entry_count": len(entries),
            "entries": entries,
        }
        path = packet_root / name
        write_json(path, payload)
        packets.append({
            "packet": name,
            "packet_id": payload["packet_id"],
            "count": len(entries),
            "first_cluster_id": entries[0]["cluster_id"],
            "last_cluster_id": entries[-1]["cluster_id"],
            "sha256": sha256_file(path),
        })

    empty_map = args.output / "translation_map.empty.jsonl"
    write_jsonl(empty_map, [])
    manifest = {
        "schema": "criminal-girls.bscr-context-packets.v2",
        "catalog": catalog_path.name,
        "catalog_sha256": sha256_file(catalog_path),
        "draft_units": draft_path.name,
        "draft_units_sha256": sha256_file(draft_path),
        "occurrence_fanout": fanout_path.name,
        "occurrence_fanout_sha256": sha256_file(fanout_path),
        "occurrence_review_packets": review_path.name,
        "occurrence_review_packets_sha256": sha256_file(review_path),
        "empty_translation_map": empty_map.name,
        "empty_translation_map_sha256": sha256_file(empty_map),
        "packet_size": args.packet_size,
        "packet_count": len(packets),
        "candidate_count": len(catalog),
        "draft_unit_count": len(draft_units),
        "occurrence_review_cluster_count": len(review_clusters),
        "occurrence_review_occurrence_count": sum(item["occurrence_count"] for item in review_clusters),
        "packets": packets,
    }
    write_json(args.output / "packets_manifest.json", manifest)

    audit = {
        "schema": "criminal-girls.bscr-v2-catalog-audit.v2",
        "pass": len(jp_paths) == 54 and len(catalog) > 0,
        "facts": {
            "header_offset": 36,
            "h4": "UTF-8 NUL-separated string-pool start",
            "h5": "code size",
            "h6": "code start",
            "record_size": 16,
            "push_opcode_raw_hex": PUSH_OPCODE.hex(),
            "push_operand": "little-endian u32 pool-relative offset at record +4",
        },
        "file_count": len(jp_paths),
        "candidate_count": len(catalog),
        "draft_unit_count": len(draft_units),
        "cluster_key": "exact (source_ja, reference_en)",
        "candidate_class_counts": dict(sorted(classification_counts.items())),
        "english_reference_counts": dict(sorted(reference_counts.items())),
        "known_display_consumers": DISPLAY_CONSUMERS,
        "referenced_unknown_policy": "included as translation candidates; never auto-preserved",
        "unreferenced_policy": "not a candidate without a direct push reference",
        "files": file_summaries,
        "artifacts": {
            "catalog": str(catalog_path),
            "catalog_sha256": manifest["catalog_sha256"],
            "packets_manifest": str(args.output / "packets_manifest.json"),
        },
    }
    write_json(args.audit, audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jp-root", type=Path, default=DEFAULT_JP_ROOT)
    parser.add_argument("--en-root", type=Path, default=DEFAULT_EN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--packet-size", type=int, default=80)
    parser.add_argument("--context-samples", type=int, default=5)
    args = parser.parse_args()
    if args.packet_size <= 0:
        parser.error("--packet-size must be positive")
    if args.context_samples <= 0:
        parser.error("--context-samples must be positive")
    result = build(args)
    print(json.dumps({
        "pass": result["pass"],
        "file_count": result["file_count"],
        "candidate_count": result["candidate_count"],
        "draft_unit_count": result["draft_unit_count"],
        "candidate_class_counts": result["candidate_class_counts"],
        "audit": str(args.audit),
    }, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
