#!/usr/bin/env python3
"""Template-preserving repacker for Criminal Girls PS3FS_V1 and DSARCIDX archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path

SECTOR = 512
PS3_MAGIC = b"PS3FS_V1"
DS_MAGIC = b"DSARCIDX"
PS3_HEADER = struct.Struct("<8sQ")
PS3_RECORD = struct.Struct("<48sQQ")
DS_HEADER = struct.Struct("<8sII")
DS_RECORD = struct.Struct("<40sII")


@dataclass(frozen=True)
class Entry:
    index: int
    name: str
    size: int
    offset: int
    record_pos: int
    size_pos: int
    offset_pos: int
    file_id: int | None = None


def decode_name(raw: bytes) -> str:
    value = raw.split(b"\0", 1)[0]
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("cp932", errors="surrogateescape")


def slot_size(size: int) -> int:
    # The original packer always reserves one more 0x200 sector, even when
    # the payload size is already an exact multiple of 0x200.
    return (size // SECTOR + 1) * SECTOR


def physical_groups(entries: list[Entry]) -> list[list[Entry]]:
    """Return physical payloads, coalescing table entries that alias one slot."""
    by_offset: dict[int, list[Entry]] = {}
    for entry in entries:
        by_offset.setdefault(entry.offset, []).append(entry)
    groups = [sorted(by_offset[offset], key=lambda e: e.index) for offset in sorted(by_offset)]
    for group in groups:
        sizes = {entry.size for entry in group}
        if len(sizes) != 1:
            raise ValueError(
                f"aliased entries at {group[0].offset} disagree on size: "
                f"{[(entry.index, entry.size) for entry in group]}"
            )
    return groups


def parse_template(path: Path, fmt: str) -> tuple[list[Entry], int, bytes]:
    file_size = path.stat().st_size
    with path.open("rb") as f:
        if fmt == "ps3fs":
            raw = f.read(PS3_HEADER.size)
            magic, count = PS3_HEADER.unpack(raw)
            if magic != PS3_MAGIC:
                raise ValueError(f"unexpected PS3FS magic {magic!r}")
            entries = []
            for i in range(count):
                pos = PS3_HEADER.size + i * PS3_RECORD.size
                rec = f.read(PS3_RECORD.size)
                raw_name, size, offset = PS3_RECORD.unpack(rec)
                entries.append(Entry(i, decode_name(raw_name), size, offset, pos, pos + 48, pos + 56))
        else:
            raw = f.read(DS_HEADER.size)
            magic, count, _reserved = DS_HEADER.unpack(raw)
            if magic != DS_MAGIC:
                raise ValueError(f"unexpected DSARCIDX magic {magic!r}")
            ids_raw = f.read(count * 2)
            ids = struct.unpack(f"<{count}H", ids_raw) if count else ()
            record_start = (f.tell() + 3) & ~3
            f.seek(record_start)
            entries = []
            for i in range(count):
                pos = record_start + i * DS_RECORD.size
                rec = f.read(DS_RECORD.size)
                raw_name, size, offset = DS_RECORD.unpack(rec)
                entries.append(Entry(i, decode_name(raw_name), size, offset, pos, pos + 40, pos + 44, ids[i]))
        first_payload = min((e.offset for e in entries), default=f.tell())
        f.seek(0)
        prefix = f.read(first_payload)
    if not entries:
        return entries, first_payload, prefix
    physical = physical_groups(entries)
    if physical[0][0].offset != first_payload:
        raise ValueError("first payload offset mismatch")
    for current, nxt in zip(physical, physical[1:]):
        representative = current[0]
        expected = representative.offset + slot_size(representative.size)
        if nxt[0].offset != expected:
            raise ValueError(
                f"unexpected slot layout after {representative.index}:{representative.name}: "
                f"{nxt[0].offset} != {expected}"
            )
    representative = physical[-1][0]
    expected_size = representative.offset + slot_size(representative.size)
    if expected_size != file_size:
        raise ValueError(f"unexpected archive tail: {file_size} != {expected_size}")
    return entries, first_payload, prefix


def read_replacements(path: Path | None, entries: list[Entry]) -> dict[int, Path]:
    if path is None:
        return {}
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    items = doc.get("replacements", doc if isinstance(doc, list) else [])
    result: dict[int, Path] = {}
    for item in items:
        index = int(item["index"])
        if index < 0 or index >= len(entries):
            raise ValueError(f"replacement index out of range: {index}")
        expected_name = item.get("expected_name")
        if expected_name is not None and entries[index].name != expected_name:
            raise ValueError(
                f"replacement name mismatch at {index}: "
                f"{entries[index].name!r} != {expected_name!r}"
            )
        replacement = Path(item["path"])
        if not replacement.is_file():
            raise FileNotFoundError(replacement)
        if index in result:
            raise ValueError(f"duplicate replacement index: {index}")
        result[index] = replacement
    return result


def copy_n(src, dst, count: int, hasher=None) -> None:
    remaining = count
    while remaining:
        chunk = src.read(min(8 * 1024 * 1024, remaining))
        if not chunk:
            raise IOError(f"short read with {remaining} bytes remaining")
        dst.write(chunk)
        if hasher is not None:
            hasher.update(chunk)
        remaining -= len(chunk)


def hash_range(path: Path, offset: int, size: int) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        f.seek(offset)
        remaining = size
        while remaining:
            chunk = f.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                raise IOError("short range while hashing")
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def repack(template: Path, output: Path, fmt: str, manifest: Path | None) -> dict:
    entries, first_payload, prefix = parse_template(template, fmt)
    replacements = read_replacements(manifest, entries)
    groups = physical_groups(entries)

    group_payloads: list[tuple[list[Entry], Path | None, int]] = []
    new_sizes: dict[int, int] = {}
    for group in groups:
        replaced = [entry for entry in group if entry.index in replacements]
        payload: Path | None = None
        size = group[0].size
        if replaced:
            if len(group) > 1 and len(replaced) != len(group):
                raise ValueError(
                    "partial replacement of aliased payload is unsafe: "
                    f"{[(entry.index, entry.name) for entry in group]}"
                )
            payload = replacements[replaced[0].index]
            size = payload.stat().st_size
            expected_hash = sha256(payload)
            for entry in replaced[1:]:
                candidate = replacements[entry.index]
                if candidate.stat().st_size != size or sha256(candidate) != expected_hash:
                    raise ValueError(
                        "aliased entries require byte-identical replacements: "
                        f"{[(item.index, item.name) for item in group]}"
                    )
        for entry in group:
            new_sizes[entry.index] = size
        group_payloads.append((group, payload, size))

    new_offsets: dict[int, int] = {}
    cursor = first_payload
    for group, _payload, size in group_payloads:
        for entry in group:
            new_offsets[entry.index] = cursor
        cursor += slot_size(size)

    updated_prefix = bytearray(prefix)
    for entry in entries:
        if fmt == "ps3fs":
            struct.pack_into("<Q", updated_prefix, entry.size_pos, new_sizes[entry.index])
            struct.pack_into("<Q", updated_prefix, entry.offset_pos, new_offsets[entry.index])
        else:
            if new_sizes[entry.index] > 0xFFFFFFFF or new_offsets[entry.index] > 0xFFFFFFFF:
                raise ValueError("DSARCIDX 32-bit size/offset overflow")
            struct.pack_into("<I", updated_prefix, entry.size_pos, new_sizes[entry.index])
            struct.pack_into("<I", updated_prefix, entry.offset_pos, new_offsets[entry.index])

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    with template.open("rb") as original, temp.open("wb") as dst:
        dst.write(updated_prefix)
        for group, payload, size in group_payloads:
            representative = group[0]
            if dst.tell() != new_offsets[representative.index]:
                raise AssertionError((dst.tell(), new_offsets[representative.index]))
            if payload is not None:
                with payload.open("rb") as rep:
                    copy_n(rep, dst, size)
                dst.write(b"\0" * (slot_size(size) - size))
            else:
                original.seek(representative.offset)
                # Preserve the physical payload and its original padding once,
                # regardless of how many table records alias this slot.
                copy_n(original, dst, slot_size(representative.size))
        if dst.tell() != cursor:
            raise AssertionError((dst.tell(), cursor))
        dst.flush()
        os.fsync(dst.fileno())
    temp.replace(output)

    out_entries, out_first, _ = parse_template(output, fmt)
    if len(out_entries) != len(entries) or out_first != first_payload:
        raise ValueError("rebuilt archive structure mismatch")
    verified = []
    for index, rep_path in sorted(replacements.items()):
        out_entry = out_entries[index]
        expected_hash = sha256(rep_path)
        actual_hash = hash_range(output, out_entry.offset, out_entry.size)
        if expected_hash != actual_hash:
            raise ValueError(f"replacement payload verification failed: {index}")
        verified.append(
            {"index": index, "name": out_entry.name, "size": out_entry.size, "sha256": actual_hash}
        )
    alias_groups = [
        {
            "offset": group[0].offset,
            "size": group[0].size,
            "indices": [entry.index for entry in group],
            "names": [entry.name for entry in group],
        }
        for group in groups
        if len(group) > 1
    ]
    result = {
        "format": fmt,
        "template": str(template),
        "output": str(output),
        "entry_count": len(entries),
        "physical_payload_count": len(groups),
        "alias_groups": alias_groups,
        "replacement_count": len(replacements),
        "first_payload_offset": first_payload,
        "output_size": output.stat().st_size,
        "verified_replacements": verified,
    }
    if not replacements:
        result["template_sha256"] = sha256(template)
        result["output_sha256"] = sha256(output)
        result["byte_identical"] = result["template_sha256"] == result["output_sha256"]
        if not result["byte_identical"]:
            raise ValueError("no-change rebuild is not byte-identical")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("format", choices=["ps3fs", "dsarcidx"])
    ap.add_argument("template", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--replacements", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    a = ap.parse_args()
    result = repack(a.template, a.output, a.format, a.replacements)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
