#!/usr/bin/env python3
"""Byte-compare corresponding payloads in two PS3FS_V1 archives."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


HEADER = struct.Struct("<8sQ")
RECORD = struct.Struct("<48sQQ")


@dataclass(frozen=True)
class Entry:
    index: int
    occurrence: int
    name: str
    size: int
    offset: int


def decode_name(raw: bytes) -> str:
    value = raw.split(b"\0", 1)[0]
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("cp932", errors="surrogateescape")


def read_table(path: Path) -> list[Entry]:
    with path.open("rb") as src:
        magic, count = HEADER.unpack(src.read(HEADER.size))
        if magic != b"PS3FS_V1":
            raise ValueError(f"unexpected magic in {path}: {magic!r}")
        occurrences: collections.Counter[str] = collections.Counter()
        entries: list[Entry] = []
        for index in range(count):
            raw_name, size, offset = RECORD.unpack(src.read(RECORD.size))
            name = decode_name(raw_name)
            occurrence = occurrences[name]
            occurrences[name] += 1
            entries.append(Entry(index, occurrence, name, size, offset))
    return entries


def digest_payload(src, entry: Entry, chunk_size: int) -> str:
    src.seek(entry.offset)
    digest = hashlib.sha256()
    remaining = entry.size
    while remaining:
        block = src.read(min(chunk_size, remaining))
        if not block:
            raise IOError(f"short read for {entry.name!r}")
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-mib", type=int, default=4)
    args = parser.parse_args()
    chunk_size = args.chunk_mib * 1024 * 1024

    left_entries = read_table(args.left)
    right_entries = read_table(args.right)
    left_map = {(e.name, e.occurrence): e for e in left_entries}
    right_map = {(e.name, e.occurrence): e for e in right_entries}
    keys = sorted(set(left_map) | set(right_map))
    differences: list[dict] = []
    identical_count = 0
    with args.left.open("rb") as left_src, args.right.open("rb") as right_src:
        for name, occurrence in keys:
            left = left_map.get((name, occurrence))
            right = right_map.get((name, occurrence))
            if left is None or right is None:
                differences.append({
                    "name": name,
                    "occurrence": occurrence,
                    "reason": "missing_side",
                    "left": left.__dict__ if left else None,
                    "right": right.__dict__ if right else None,
                })
                continue
            left_hash = digest_payload(left_src, left, chunk_size)
            right_hash = digest_payload(right_src, right, chunk_size)
            if left_hash == right_hash:
                identical_count += 1
                continue
            differences.append({
                "name": name,
                "occurrence": occurrence,
                "extension": PurePosixPath(name.replace("\\", "/")).suffix.lower() or "<none>",
                "reason": "size_and_payload" if left.size != right.size else "payload",
                "left_index": left.index,
                "right_index": right.index,
                "left_size": left.size,
                "right_size": right.size,
                "left_sha256": left_hash,
                "right_sha256": right_hash,
            })

    ext_counts = collections.Counter(item.get("extension", "<missing>") for item in differences)
    payload = {
        "schema": "criminal-girls.ps3fs-payload-diff.v1",
        "left": str(args.left),
        "right": str(args.right),
        "left_entry_count": len(left_entries),
        "right_entry_count": len(right_entries),
        "identical_entry_count": identical_count,
        "different_entry_count": len(differences),
        "different_extension_counts": dict(sorted(ext_counts.items(), key=lambda item: (-item[1], item[0]))),
        "differences": differences,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({key: value for key, value in payload.items() if key not in {"differences", "left", "right", "schema"}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
