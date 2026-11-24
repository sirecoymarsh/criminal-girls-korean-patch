#!/usr/bin/env python3
"""Inspect and extract the DSARCIDX containers used by Criminal Girls."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath


MAGIC = b"DSARCIDX"
HEADER = struct.Struct("<8sII")
RECORD = struct.Struct("<40sII")


@dataclass(frozen=True)
class Entry:
    index: int
    file_id: int
    name: str
    size: int
    offset: int

    @property
    def extension(self) -> str:
        return PurePosixPath(self.name.replace("\\", "/")).suffix.lower() or "<none>"


def decode_name(raw: bytes) -> str:
    value = raw.split(b"\0", 1)[0]
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("cp932", errors="surrogateescape")


def read_entries(path: Path) -> tuple[list[Entry], dict]:
    file_size = path.stat().st_size
    with path.open("rb") as src:
        raw = src.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError("short DSARCIDX header")
        magic, count, reserved = HEADER.unpack(raw)
        if magic != MAGIC:
            raise ValueError(f"unexpected magic {magic!r}")
        ids_raw = src.read(count * 2)
        if len(ids_raw) != count * 2:
            raise ValueError("short DSARCIDX file-id table")
        ids = list(struct.unpack(f"<{count}H", ids_raw)) if count else []
        record_table_offset = (src.tell() + 3) & ~3
        src.seek(record_table_offset)
        table_end = record_table_offset + count * RECORD.size
        if table_end > file_size:
            raise ValueError("DSARCIDX record table ends past EOF")

        entries: list[Entry] = []
        for index in range(count):
            raw = src.read(RECORD.size)
            if len(raw) != RECORD.size:
                raise ValueError(f"short record at index {index}")
            raw_name, size, offset = RECORD.unpack(raw)
            name = decode_name(raw_name)
            if not name:
                raise ValueError(f"empty name at index {index}")
            if offset + size > file_size:
                raise ValueError(f"entry {index} {name!r} extends past EOF")
            entries.append(Entry(index, ids[index], name, size, offset))

    first_payload = min((entry.offset for entry in entries), default=table_end)
    overlaps = 0
    prior_end = 0
    for entry in sorted(entries, key=lambda item: (item.offset, item.index)):
        if entry.offset < prior_end:
            overlaps += 1
        prior_end = max(prior_end, entry.offset + entry.size)
    metadata = {
        "archive": str(path),
        "file_size": file_size,
        "magic": MAGIC.decode("ascii"),
        "entry_count": count,
        "reserved": reserved,
        "record_table_offset": record_table_offset,
        "record_size": RECORD.size,
        "table_end": table_end,
        "first_payload_offset": first_payload,
        "table_padding_bytes": first_payload - table_end,
        "overlap_count": overlaps,
        "offsets_monotonic_in_table_order": all(
            entries[i].offset <= entries[i + 1].offset for i in range(len(entries) - 1)
        ),
    }
    return entries, metadata


def summarize(entries: list[Entry]) -> dict:
    extensions = collections.Counter(entry.extension for entry in entries)
    names = collections.Counter(entry.name for entry in entries)
    duplicates = {name: count for name, count in sorted(names.items()) if count > 1}
    return {
        "extension_counts": dict(sorted(extensions.items(), key=lambda item: (-item[1], item[0]))),
        "duplicate_name_group_count": len(duplicates),
        "duplicate_entry_count": sum(duplicates.values()),
        "duplicate_names": duplicates,
        "largest_entries": [
            asdict(entry) for entry in sorted(entries, key=lambda item: item.size, reverse=True)[:30]
        ],
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_path(root: Path, entry: Entry, duplicate_count: int) -> Path:
    parts = PurePosixPath(entry.name.replace("\\", "/")).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe path {entry.name!r}")
    output = root.joinpath(*parts)
    resolved_root = root.resolve()
    resolved_parent = output.parent.resolve()
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise ValueError(f"path escapes output root: {entry.name!r}")
    if duplicate_count > 1:
        output = output.with_name(f"{output.name}.__entry_{entry.index:05d}")
    return output


def extract(
    archive: Path,
    entries: list[Entry],
    root: Path,
    patterns: list[str],
) -> list[dict]:
    regexes = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    selected = [
        entry for entry in entries if not regexes or any(rx.search(entry.name) for rx in regexes)
    ]
    counts = collections.Counter(entry.name for entry in selected)
    root.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with archive.open("rb") as src:
        for entry in selected:
            output = safe_path(root, entry, counts[entry.name])
            output.parent.mkdir(parents=True, exist_ok=True)
            src.seek(entry.offset)
            remaining = entry.size
            digest = hashlib.sha256()
            temp = output.with_name(output.name + ".tmp")
            with temp.open("wb") as dst:
                while remaining:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise IOError(f"short payload for {entry.name!r}")
                    dst.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
            temp.replace(output)
            item = asdict(entry)
            item.update(output=str(output), sha256=digest.hexdigest())
            results.append(item)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("archive", type=Path)
    inspect_parser.add_argument("--output", type=Path, required=True)
    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("archive", type=Path)
    extract_parser.add_argument("--root", type=Path, required=True)
    extract_parser.add_argument("--pattern", action="append", default=[])
    extract_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    entries, metadata = read_entries(args.archive)
    if args.command == "inspect":
        payload = {"metadata": metadata, "summary": summarize(entries), "entries": [asdict(e) for e in entries]}
        write_json(args.output, payload)
        print(json.dumps({**metadata, "extensions": payload["summary"]["extension_counts"]}, indent=2))
        return 0
    results = extract(args.archive, entries, args.root, args.pattern)
    write_json(args.manifest, {"archive": metadata, "patterns": args.pattern, "extracted": results})
    print(json.dumps({"selected_count": len(results), "root": str(args.root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
