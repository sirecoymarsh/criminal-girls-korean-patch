#!/usr/bin/env python3
"""Read-only inspector/extractor for Criminal Girls PS3FS_V1 archives.

The format used by the PC port starts with an 8-byte magic, a little-endian
64-bit entry count, and fixed 0x40-byte records:

    char name[0x30]; uint64 size; uint64 offset

This tool deliberately has no repack command.  Discovery must remain read-only
until a language contract and a proven round-trip builder exist.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath


MAGIC = b"PS3FS_V1"
HEADER = struct.Struct("<8sQ")
RECORD = struct.Struct("<48sQQ")


@dataclass(frozen=True)
class Entry:
    index: int
    name: str
    size: int
    offset: int

    @property
    def extension(self) -> str:
        return PurePosixPath(self.name.replace("\\", "/")).suffix.lower() or "<none>"


def read_entries(path: Path) -> tuple[list[Entry], dict]:
    file_size = path.stat().st_size
    with path.open("rb") as fp:
        raw = fp.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError("archive is shorter than the 16-byte header")
        magic, count = HEADER.unpack(raw)
        if magic != MAGIC:
            raise ValueError(f"unexpected magic {magic!r}")
        table_end = HEADER.size + count * RECORD.size
        if table_end > file_size:
            raise ValueError(f"entry table ends past EOF: {table_end} > {file_size}")

        entries: list[Entry] = []
        for index in range(count):
            raw = fp.read(RECORD.size)
            if len(raw) != RECORD.size:
                raise ValueError(f"short record at index {index}")
            raw_name, size, offset = RECORD.unpack(raw)
            name_bytes = raw_name.split(b"\0", 1)[0]
            try:
                name = name_bytes.decode("utf-8")
            except UnicodeDecodeError:
                name = name_bytes.decode("cp932", errors="surrogateescape")
            if not name:
                raise ValueError(f"empty name at entry {index}")
            if offset + size > file_size:
                raise ValueError(
                    f"entry {index} {name!r} extends past EOF: {offset}+{size}>{file_size}"
                )
            entries.append(Entry(index=index, name=name, size=size, offset=offset))

    first_offset = min((e.offset for e in entries), default=table_end)
    ordered_by_offset = all(
        entries[i].offset <= entries[i + 1].offset for i in range(len(entries) - 1)
    )
    overlap_count = 0
    prior_end = 0
    for entry in sorted(entries, key=lambda item: (item.offset, item.index)):
        if entry.offset < prior_end:
            overlap_count += 1
        prior_end = max(prior_end, entry.offset + entry.size)

    metadata = {
        "archive": str(path),
        "file_size": file_size,
        "magic": MAGIC.decode("ascii"),
        "entry_count": len(entries),
        "record_size": RECORD.size,
        "table_end": table_end,
        "first_payload_offset": first_offset,
        "table_padding_bytes": first_offset - table_end,
        "offsets_monotonic_in_table_order": ordered_by_offset,
        "overlap_count": overlap_count,
    }
    return entries, metadata


def summarize(entries: list[Entry]) -> dict:
    extensions = collections.Counter(entry.extension for entry in entries)
    names = collections.Counter(entry.name for entry in entries)
    duplicate_groups = {
        name: count for name, count in sorted(names.items()) if count > 1
    }
    alignments = collections.Counter()
    for entry in entries:
        if entry.offset % 0x800 == 0:
            alignments["0x800"] += 1
        elif entry.offset % 0x10 == 0:
            alignments["0x10"] += 1
        else:
            alignments["other"] += 1
    return {
        "extension_counts": dict(sorted(extensions.items(), key=lambda item: (-item[1], item[0]))),
        "duplicate_name_group_count": len(duplicate_groups),
        "duplicate_entry_count": sum(duplicate_groups.values()),
        "duplicate_names": duplicate_groups,
        "offset_alignment_buckets": dict(alignments),
        "largest_entries": [
            asdict(entry) for entry in sorted(entries, key=lambda item: item.size, reverse=True)[:30]
        ],
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_output_path(root: Path, entry: Entry, duplicate_count: int) -> Path:
    normalized = entry.name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe archive path {entry.name!r}")
    out = root.joinpath(*parts)
    resolved_root = root.resolve()
    resolved_parent = out.parent.resolve()
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise ValueError(f"path escapes extraction root: {entry.name!r}")
    if duplicate_count > 1:
        out = out.with_name(f"{out.name}.__entry_{entry.index:05d}")
    return out


def extract_entries(
    archive: Path,
    entries: list[Entry],
    root: Path,
    patterns: list[str],
    hash_payloads: bool,
) -> list[dict]:
    regexes = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    selected = [
        entry for entry in entries if not regexes or any(rx.search(entry.name) for rx in regexes)
    ]
    duplicate_counts = collections.Counter(entry.name for entry in selected)
    root.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with archive.open("rb") as src:
        for entry in selected:
            output = safe_output_path(root, entry, duplicate_counts[entry.name])
            output.parent.mkdir(parents=True, exist_ok=True)
            src.seek(entry.offset)
            remaining = entry.size
            digest = hashlib.sha256() if hash_payloads else None
            temp = output.with_name(output.name + ".tmp")
            with temp.open("wb") as dst:
                while remaining:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise IOError(f"short payload for {entry.name!r}")
                    dst.write(chunk)
                    if digest is not None:
                        digest.update(chunk)
                    remaining -= len(chunk)
            temp.replace(output)
            item = asdict(entry)
            item["output"] = str(output)
            if digest is not None:
                item["sha256"] = digest.hexdigest()
            results.append(item)
    return results


def compare_tables(left: Path, right: Path) -> dict:
    left_entries, left_meta = read_entries(left)
    right_entries, right_meta = read_entries(right)
    left_by_name: dict[str, list[Entry]] = collections.defaultdict(list)
    right_by_name: dict[str, list[Entry]] = collections.defaultdict(list)
    for entry in left_entries:
        left_by_name[entry.name].append(entry)
    for entry in right_entries:
        right_by_name[entry.name].append(entry)

    names = sorted(set(left_by_name) | set(right_by_name))
    only_left: list[str] = []
    only_right: list[str] = []
    count_mismatch: list[dict] = []
    size_mismatch: list[dict] = []
    for name in names:
        le = left_by_name.get(name, [])
        re_ = right_by_name.get(name, [])
        if not re_:
            only_left.append(name)
            continue
        if not le:
            only_right.append(name)
            continue
        if len(le) != len(re_):
            count_mismatch.append({"name": name, "left_count": len(le), "right_count": len(re_)})
        left_sizes = [entry.size for entry in le]
        right_sizes = [entry.size for entry in re_]
        if left_sizes != right_sizes:
            size_mismatch.append({"name": name, "left_sizes": left_sizes, "right_sizes": right_sizes})

    return {
        "left": left_meta,
        "right": right_meta,
        "only_left_count": len(only_left),
        "only_right_count": len(only_right),
        "count_mismatch_count": len(count_mismatch),
        "size_mismatch_count": len(size_mismatch),
        "only_left": only_left,
        "only_right": only_right,
        "count_mismatches": count_mismatch,
        "size_mismatches": size_mismatch,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="validate the table and write a manifest")
    inspect_parser.add_argument("archive", type=Path)
    inspect_parser.add_argument("--output", type=Path, required=True)

    compare_parser = sub.add_parser("compare", help="compare two archive tables by stable name")
    compare_parser.add_argument("left", type=Path)
    compare_parser.add_argument("right", type=Path)
    compare_parser.add_argument("--output", type=Path, required=True)

    extract_parser = sub.add_parser("extract", help="extract entries matching regex patterns")
    extract_parser.add_argument("archive", type=Path)
    extract_parser.add_argument("--root", type=Path, required=True)
    extract_parser.add_argument("--pattern", action="append", default=[])
    extract_parser.add_argument("--manifest", type=Path, required=True)
    extract_parser.add_argument("--no-hash", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        entries, metadata = read_entries(args.archive)
        payload = {"metadata": metadata, "summary": summarize(entries), "entries": [asdict(e) for e in entries]}
        write_json(args.output, payload)
        print(json.dumps({**metadata, **{k: v for k, v in payload["summary"].items() if k.endswith("count")}}, indent=2))
        return 0
    if args.command == "compare":
        payload = compare_tables(args.left, args.right)
        write_json(args.output, payload)
        print(json.dumps({k: v for k, v in payload.items() if k.endswith("count")}, indent=2))
        return 0
    if args.command == "extract":
        entries, metadata = read_entries(args.archive)
        extracted = extract_entries(args.archive, entries, args.root, args.pattern, not args.no_hash)
        write_json(args.manifest, {"archive": metadata, "patterns": args.pattern, "extracted": extracted})
        print(json.dumps({"selected_count": len(extracted), "root": str(args.root)}, indent=2))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
