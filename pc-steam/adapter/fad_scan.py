#!/usr/bin/env python3
"""Inventory YKCMP_V1 streams and gaps inside Criminal Girls FAD files."""

from __future__ import annotations

import argparse
import json
import mmap
import struct
from pathlib import Path


MAGIC = b"YKCMP_V1"
YK_HEADER = struct.Struct("<8sIII")


def scan(path: Path) -> dict:
    file_size = path.stat().st_size
    streams: list[dict] = []
    with path.open("rb") as src, mmap.mmap(src.fileno(), 0, access=mmap.ACCESS_READ) as data:
        cursor = 0
        while True:
            offset = data.find(MAGIC, cursor)
            if offset < 0:
                break
            if offset + YK_HEADER.size > file_size:
                streams.append({"offset": offset, "error": "truncated_header"})
                break
            _, unknown, compressed_size, decompressed_size = YK_HEADER.unpack_from(data, offset)
            next_magic = data.find(MAGIC, offset + len(MAGIC))
            candidate_payload_end = offset + YK_HEADER.size + compressed_size
            candidate_total_end = offset + compressed_size
            streams.append({
                "index": len(streams),
                "offset": offset,
                "unknown": unknown,
                "compressed_size_field": compressed_size,
                "decompressed_size": decompressed_size,
                "payload_end_if_excluding_header": candidate_payload_end,
                "stream_end_if_including_header": candidate_total_end,
                "next_magic_offset": next_magic if next_magic >= 0 else None,
                "distance_to_next_magic": next_magic - offset if next_magic >= 0 else None,
            })
            cursor = offset + len(MAGIC)

    exact_excluding = 0
    exact_including = 0
    for stream in streams:
        next_offset = stream.get("next_magic_offset")
        if next_offset is None:
            continue
        if stream["payload_end_if_excluding_header"] == next_offset:
            exact_excluding += 1
        if stream["stream_end_if_including_header"] == next_offset:
            exact_including += 1
    return {
        "schema": "criminal-girls.fad-ycmp-inventory.v1",
        "path": str(path),
        "file_size": file_size,
        "stream_count": len(streams),
        "first_stream_offset": streams[0]["offset"] if streams else None,
        "last_stream_offset": streams[-1]["offset"] if streams else None,
        "exact_next_magic_if_compressed_size_excludes_header": exact_excluding,
        "exact_next_magic_if_compressed_size_includes_header": exact_including,
        "streams": streams,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = scan(args.path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({key: payload[key] for key in payload if key != "streams"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
