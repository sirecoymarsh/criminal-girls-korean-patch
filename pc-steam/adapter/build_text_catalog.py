#!/usr/bin/env python3
"""Build a stable Japanese/English text catalog for Criminal Girls."""

from __future__ import annotations

import argparse
import json
import struct
import unicodedata
from dataclasses import dataclass
from pathlib import Path


KEY_SIZE = 28
KEY_RECORD_SIZE = 4 + KEY_SIZE


@dataclass(frozen=True)
class KeyedValue:
    index: int
    key: str
    offset: int
    span_size: int
    raw_value: bytes
    kind: str
    text: str | None


def decode_key(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii")


def classify_value(key: str, raw_span: bytes) -> tuple[str, str | None, bytes]:
    value = raw_span.rstrip(b"\0")
    if key.endswith("_NUM") or key.endswith("TBL[]"):
        return "binary", None, value
    if not value:
        return "empty", "", value
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return "binary", None, value
    if "\0" in text:
        return "binary", None, value
    meaningful = [ch for ch in text if unicodedata.category(ch)[0] not in {"C", "Z"}]
    if not meaningful:
        return "binary", None, value
    return "text", text, value


def parse_keyed(path: Path) -> tuple[list[KeyedValue], dict]:
    blob = path.read_bytes()
    if len(blob) < 4:
        raise ValueError(f"short keyed table: {path}")
    count = struct.unpack_from("<I", blob, 0)[0]
    table_end = 4 + count * KEY_RECORD_SIZE
    if table_end > len(blob):
        raise ValueError(f"record table exceeds file: {path}")
    records: list[tuple[int, str, int]] = []
    for index in range(count):
        pos = 4 + index * KEY_RECORD_SIZE
        offset = struct.unpack_from("<I", blob, pos)[0]
        key = decode_key(blob[pos + 4 : pos + KEY_RECORD_SIZE])
        records.append((index, key, offset))
    offsets = sorted({offset for _, _, offset in records})
    if offsets and offsets[0] < table_end:
        raise ValueError(f"value overlaps key table: {path}")
    offset_end = {
        offset: offsets[i + 1] if i + 1 < len(offsets) else len(blob)
        for i, offset in enumerate(offsets)
    }
    values: list[KeyedValue] = []
    for index, key, offset in records:
        end = offset_end[offset]
        if offset > end or end > len(blob):
            raise ValueError(f"bad value range for {key!r}: {path}")
        span = blob[offset:end]
        kind, text, raw_value = classify_value(key, span)
        values.append(KeyedValue(index, key, offset, len(span), raw_value, kind, text))
    return values, {
        "path": str(path),
        "file_size": len(blob),
        "record_count": count,
        "table_end": table_end,
        "text_count": sum(value.kind in {"text", "empty"} for value in values),
        "binary_count": sum(value.kind == "binary" for value in values),
    }


def parse_unkeyed(path: Path) -> tuple[list[str], dict]:
    blob = path.read_bytes()
    if len(blob) < 4:
        raise ValueError(f"short UTF8 table: {path}")
    body_size = struct.unpack_from("<I", blob, 0)[0]
    body_end = 4 + body_size
    if body_end > len(blob):
        raise ValueError(f"declared body exceeds file: {path}")
    body = blob[4:body_end]
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid UTF-8 body in {path}: {error}") from error
    strings = decoded.split("\0")
    while strings and strings[-1] == "":
        strings.pop()
    padding = blob[body_end:]
    return strings, {
        "path": str(path),
        "file_size": len(blob),
        "body_size": body_size,
        "padding_size": len(padding),
        "padding_all_zero": not any(padding),
        "string_count": len(strings),
    }


def add_neighbors(entries: list[dict]) -> None:
    for index, entry in enumerate(entries):
        if index:
            entry["previous_source_ja"] = entries[index - 1]["source_ja"]
        if index + 1 < len(entries):
            entry["next_source_ja"] = entries[index + 1]["source_ja"]


def keyed_pair_entries(lane: str, rel: str, jp_path: Path, en_path: Path, issues: list[dict]) -> tuple[list[dict], dict]:
    jp_values, jp_meta = parse_keyed(jp_path)
    en_values, en_meta = parse_keyed(en_path)
    jp_map = {value.key: value for value in jp_values}
    en_map = {value.key: value for value in en_values}
    if list(jp_map) != list(en_map):
        issues.append({"type": "key_order_mismatch", "lane": lane, "file": rel})
    entries: list[dict] = []
    for value in jp_values:
        reference = en_map.get(value.key)
        if reference is None:
            issues.append({"type": "missing_english_key", "lane": lane, "file": rel, "key": value.key})
            continue
        if value.kind not in {"text", "empty"}:
            continue
        if reference.kind not in {"text", "empty"}:
            issues.append({"type": "reference_not_text", "lane": lane, "file": rel, "key": value.key})
        entries.append({
            "uid": f"{lane}::{rel}::{value.key}",
            "lane": lane,
            "file": rel,
            "record_index": value.index,
            "key": value.key,
            "source_ja": value.text or "",
            "reference_en": reference.text if reference and reference.text is not None else "",
            "source_offset": value.offset,
            "source_span_size": value.span_size,
            "source_value_hex": value.raw_value.hex(),
        })
    add_neighbors(entries)
    return entries, {"jp": jp_meta, "en": en_meta}


def build_catalog(args) -> tuple[list[dict], dict]:
    entries: list[dict] = []
    issues: list[dict] = []
    sources: list[dict] = []

    jp_files = sorted(args.field_jp.rglob("*.dat"))
    for jp_path in jp_files:
        rel = jp_path.relative_to(args.field_jp).as_posix()
        en_path = args.field_en.joinpath(*Path(rel).parts)
        if not en_path.is_file():
            issues.append({"type": "missing_english_file", "lane": "field_message", "file": rel})
            continue
        file_entries, meta = keyed_pair_entries("field_message", rel, jp_path, en_path, issues)
        entries.extend(file_entries)
        sources.append({"lane": "field_message", "file": rel, **meta})

    sys_entries, sys_meta = keyed_pair_entries(
        "system_text",
        args.system_jp.name,
        args.system_jp,
        args.system_en,
        issues,
    )
    entries.extend(sys_entries)
    sources.append({"lane": "system_text", "file": args.system_jp.name, **sys_meta})

    for jp_path in sorted(args.battle_jp.glob("*.utf8")):
        en_path = args.battle_en / jp_path.name
        if not en_path.is_file():
            issues.append({"type": "missing_english_file", "lane": "battle_text", "file": jp_path.name})
            continue
        jp_strings, jp_meta = parse_unkeyed(jp_path)
        en_strings, en_meta = parse_unkeyed(en_path)
        if len(jp_strings) != len(en_strings):
            issues.append({
                "type": "string_count_mismatch",
                "lane": "battle_text",
                "file": jp_path.name,
                "jp_count": len(jp_strings),
                "en_count": len(en_strings),
            })
        file_entries: list[dict] = []
        for index, source in enumerate(jp_strings):
            file_entries.append({
                "uid": f"battle_text::{jp_path.name}::{index:04d}",
                "lane": "battle_text",
                "file": jp_path.name,
                "record_index": index,
                "source_ja": source,
                "reference_en": en_strings[index] if index < len(en_strings) else "",
            })
        add_neighbors(file_entries)
        entries.extend(file_entries)
        sources.append({"lane": "battle_text", "file": jp_path.name, "jp": jp_meta, "en": en_meta})

    uids = [entry["uid"] for entry in entries]
    if len(set(uids)) != len(uids):
        issues.append({"type": "duplicate_uid", "duplicate_count": len(uids) - len(set(uids))})
    summary = {
        "schema": "criminal-girls.contextual-text-catalog-summary.v1",
        "entry_count": len(entries),
        "lane_counts": {
            lane: sum(entry["lane"] == lane for entry in entries)
            for lane in sorted({entry["lane"] for entry in entries})
        },
        "source_file_count": len(sources),
        "japanese_character_count": sum(len(entry["source_ja"]) for entry in entries),
        "english_reference_character_count": sum(len(entry["reference_en"]) for entry in entries),
        "issue_count": len(issues),
        "issues": issues,
        "sources": sources,
    }
    return entries, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-jp", type=Path, required=True)
    parser.add_argument("--field-en", type=Path, required=True)
    parser.add_argument("--system-jp", type=Path, required=True)
    parser.add_argument("--system-en", type=Path, required=True)
    parser.add_argument("--battle-jp", type=Path, required=True)
    parser.add_argument("--battle-en", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    entries, summary = build_catalog(args)
    args.catalog.parent.mkdir(parents=True, exist_ok=True)
    temp_catalog = args.catalog.with_name(args.catalog.name + ".tmp")
    with temp_catalog.open("w", encoding="utf-8", newline="\n") as dst:
        for entry in entries:
            dst.write(json.dumps(entry, ensure_ascii=False) + "\n")
    temp_catalog.replace(args.catalog)
    temp_summary = args.summary.with_name(args.summary.name + ".tmp")
    temp_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_summary.replace(args.summary)
    print(json.dumps({key: summary[key] for key in summary if key not in {"issues", "sources"}}, ensure_ascii=False, indent=2))
    return 0 if not summary["issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
