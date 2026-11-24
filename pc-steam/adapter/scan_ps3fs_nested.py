#!/usr/bin/env python3
"""Scan every DSARCIDX container embedded in a PS3FS_V1 archive."""

from __future__ import annotations

import argparse
import collections
import json
import struct
from pathlib import Path, PurePosixPath


PS3_HEADER = struct.Struct("<8sQ")
PS3_RECORD = struct.Struct("<48sQQ")
DS_HEADER = struct.Struct("<8sII")
DS_RECORD = struct.Struct("<40sII")


def decode_name(raw: bytes) -> str:
    value = raw.split(b"\0", 1)[0]
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("cp932", errors="surrogateescape")


def extension(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).suffix.lower() or "<none>"


def scan(path: Path) -> dict:
    file_size = path.stat().st_size
    containers: list[dict] = []
    failures: list[dict] = []
    inner_extensions: collections.Counter[str] = collections.Counter()
    with path.open("rb") as src:
        magic, count = PS3_HEADER.unpack(src.read(PS3_HEADER.size))
        if magic != b"PS3FS_V1":
            raise ValueError(f"unexpected outer magic {magic!r}")
        outer_entries: list[tuple[int, str, int, int]] = []
        for index in range(count):
            raw_name, size, offset = PS3_RECORD.unpack(src.read(PS3_RECORD.size))
            outer_entries.append((index, decode_name(raw_name), size, offset))

        for outer_index, outer_name, outer_size, outer_offset in outer_entries:
            if outer_size < DS_HEADER.size:
                continue
            src.seek(outer_offset)
            header = src.read(DS_HEADER.size)
            if len(header) != DS_HEADER.size or header[:8] != b"DSARCIDX":
                continue
            try:
                _, inner_count, reserved = DS_HEADER.unpack(header)
                ids_raw = src.read(inner_count * 2)
                if len(ids_raw) != inner_count * 2:
                    raise ValueError("short file-id table")
                ids = struct.unpack(f"<{inner_count}H", ids_raw) if inner_count else ()
                relative_records = ((DS_HEADER.size + inner_count * 2 + 3) & ~3)
                records_end = relative_records + inner_count * DS_RECORD.size
                if records_end > outer_size:
                    raise ValueError("record table exceeds outer payload")
                src.seek(outer_offset + relative_records)
                inner_entries: list[dict] = []
                for inner_index in range(inner_count):
                    raw_name, size, offset = DS_RECORD.unpack(src.read(DS_RECORD.size))
                    name = decode_name(raw_name)
                    if not name:
                        raise ValueError(f"empty inner name at index {inner_index}")
                    if offset + size > outer_size:
                        raise ValueError(f"inner payload exceeds container at index {inner_index}")
                    ext = extension(name)
                    inner_extensions[ext] += 1
                    inner_entries.append({
                        "index": inner_index,
                        "file_id": ids[inner_index],
                        "name": name,
                        "extension": ext,
                        "size": size,
                        "offset": offset,
                    })
                containers.append({
                    "outer_index": outer_index,
                    "name": outer_name,
                    "extension": extension(outer_name),
                    "size": outer_size,
                    "offset": outer_offset,
                    "reserved": reserved,
                    "inner_count": inner_count,
                    "inner_entries": inner_entries,
                })
            except (ValueError, struct.error) as error:
                failures.append({
                    "outer_index": outer_index,
                    "name": outer_name,
                    "size": outer_size,
                    "offset": outer_offset,
                    "error": str(error),
                })

    utf8_containers = []
    for container in containers:
        utf8_entries = [entry for entry in container["inner_entries"] if entry["extension"] == ".utf8"]
        if utf8_entries:
            utf8_containers.append({
                "outer_index": container["outer_index"],
                "name": container["name"],
                "size": container["size"],
                "utf8_count": len(utf8_entries),
                "utf8_bytes": sum(entry["size"] for entry in utf8_entries),
                "utf8_names": [entry["name"] for entry in utf8_entries],
            })
    return {
        "schema": "criminal-girls.nested-dsarcidx-inventory.v1",
        "archive": str(path),
        "archive_size": file_size,
        "outer_entry_count": count,
        "dsarcidx_container_count": len(containers),
        "scan_failure_count": len(failures),
        "inner_extension_counts": dict(sorted(inner_extensions.items(), key=lambda item: (-item[1], item[0]))),
        "utf8_container_count": len(utf8_containers),
        "utf8_entry_count": sum(item["utf8_count"] for item in utf8_containers),
        "utf8_payload_bytes": sum(item["utf8_bytes"] for item in utf8_containers),
        "utf8_containers": utf8_containers,
        "failures": failures,
        "containers": containers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = scan(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({
        key: payload[key]
        for key in (
            "outer_entry_count",
            "dsarcidx_container_count",
            "scan_failure_count",
            "utf8_container_count",
            "utf8_entry_count",
            "utf8_payload_bytes",
            "inner_extension_counts",
        )
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
