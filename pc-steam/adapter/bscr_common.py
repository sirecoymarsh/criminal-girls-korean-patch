#!/usr/bin/env python3
"""Shared, strict BSCR primitives for the Criminal Girls Korean patch.

The format facts used here are deliberately narrow and evidence-backed:

* seven little-endian u32 header values begin at 0x24;
* h4 is the UTF-8/NUL string-pool start;
* h5 is the byte size of the instruction stream;
* h6 is the instruction-stream start;
* every instruction record is 16 bytes;
* raw opcode bytes ``1a f0 f1 5a`` push a pool-relative u32 operand.

Nothing in this module writes a live game file.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from runtime_text_codec import RuntimeTextCodec


HEADER_OFFSET = 0x24
HEADER_STRUCT = struct.Struct("<7I")
RECORD_SIZE = 16
PUSH_OPCODE = bytes.fromhex("1af0f15a")
PUSH_OPERAND_OFFSET = 4
PUSH_OPERAND_SIZE = 4

# These are the only consumers previously established by direct record tracing.
# Unknown consumers are candidates too; this table is descriptive, not a filter.
DISPLAY_CONSUMERS = {
    "823cf35a": "choice",
    "826ef35a": "message",
}

JAPANESE_RE = re.compile(
    "["
    "\u3040-\u30ff"       # hiragana and katakana
    "\u3400-\u4dbf"       # CJK extension A
    "\u4e00-\u9fff"       # CJK unified ideographs
    "\uf900-\ufaff"       # CJK compatibility ideographs
    "\uff66-\uff9d"       # half-width katakana
    "\u3005\u3006\u303b" # iteration/ideographic marks
    "]"
)

# Token equality is multiplicity-sensitive.  The expression intentionally
# covers the control forms observed in this project and common format/markup
# forms, without treating ordinary punctuation as a token.
TOKEN_RE = re.compile(
    r"\$[0-9]+"
    r"|%(?:[-+ #0]*\d*(?:\.\d+)?[A-Za-z%])"
    r"|\\[A-Za-z][A-Za-z0-9_]*"
    r"|\{[^{}\r\n]+\}"
    r"|<[^<>\r\n]+>"
)

ALLOWED_PRESERVE_EVIDENCE_KINDS = {
    "proven_lookup_key",
    "proven_internal_identifier",
    "engine_control_literal",
    "runtime_required_literal",
    "not_user_visible_by_consumer_trace",
}


class BscrError(ValueError):
    """Raised when a BSCR invariant is not satisfied."""


@dataclass(frozen=True)
class Segment:
    index: int
    relative_offset: int
    absolute_offset: int
    raw: bytes
    text: str

    @property
    def byte_length(self) -> int:
        return len(self.raw)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


@dataclass(frozen=True)
class PushReference:
    record_index: int
    record_offset: int
    operand: int
    segment_index: int | None
    consumer_opcode: str | None
    consumer_role: str | None


@dataclass
class BscrFile:
    path: Path
    logical_name: str
    data: bytes
    header: tuple[int, int, int, int, int, int, int]
    segments: list[Segment]
    segment_by_relative_offset: dict[int, Segment]

    @property
    def pool_start(self) -> int:
        return self.header[4]

    @property
    def code_size(self) -> int:
        return self.header[5]

    @property
    def code_start(self) -> int:
        return self.header[6]

    @property
    def record_count(self) -> int:
        return self.code_size // RECORD_SIZE

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def record(self, index: int) -> bytes:
        if index < 0 or index >= self.record_count:
            raise IndexError(index)
        start = self.code_start + index * RECORD_SIZE
        return self.data[start : start + RECORD_SIZE]

    def records(self) -> list[bytes]:
        start = self.code_start
        return [
            self.data[start + i * RECORD_SIZE : start + (i + 1) * RECORD_SIZE]
            for i in range(self.record_count)
        ]

    def pushes(self) -> Iterator[PushReference]:
        for index in range(self.record_count):
            record = self.record(index)
            if record[:4] != PUSH_OPCODE:
                continue
            operand = struct.unpack_from("<I", record, PUSH_OPERAND_OFFSET)[0]
            segment = self.segment_by_relative_offset.get(operand)
            consumer_opcode = None
            consumer_role = None
            if index + 1 < self.record_count:
                consumer_opcode = self.record(index + 1)[:4].hex()
                consumer_role = DISPLAY_CONSUMERS.get(consumer_opcode)
            yield PushReference(
                record_index=index,
                record_offset=self.code_start + index * RECORD_SIZE,
                operand=operand,
                segment_index=segment.index if segment else None,
                consumer_opcode=consumer_opcode,
                consumer_role=consumer_role,
            )


@dataclass(frozen=True)
class Alignment:
    jp_to_en: dict[int, int]
    matching_blocks: int
    matched_records: int
    jp_records: int
    en_records: int
    ratio: float
    autojunk: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def write_json(path: Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def read_json_rows(path: Path) -> list[dict]:
    """Read a JSON list/document or JSONL translation/catalog file."""
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig") as stream:
        first = ""
        while True:
            char = stream.read(1)
            if not char:
                return []
            if not char.isspace():
                first = char
                break
        stream.seek(0)
        if first in "[{":
            # A JSONL row also begins with '{'.  Try one complete JSON document
            # first, then fall back to one-object-per-line.
            raw = stream.read()
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError:
                rows = []
                for line_number, line in enumerate(raw.splitlines(), 1):
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise BscrError(f"{path}:{line_number}: JSONL row is not an object")
                    rows.append(value)
                return rows
            if isinstance(doc, list):
                rows = doc
            elif isinstance(doc, dict):
                if "entries" in doc:
                    rows = doc["entries"]
                elif "rows" in doc:
                    rows = doc["rows"]
                else:
                    # A one-line JSONL map with exactly one object is also a
                    # valid complete JSON document. Treat it as one row.
                    rows = [doc]
            else:
                raise BscrError(f"unsupported JSON root in {path}")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise BscrError(f"entries are not an object list in {path}")
            return list(rows)
        raise BscrError(f"unsupported JSON/JSONL prefix {first!r} in {path}")
    raise AssertionError("unreachable")


def parse_bscr(path: Path, logical_name: str | None = None) -> BscrFile:
    data = path.read_bytes()
    if len(data) < HEADER_OFFSET + HEADER_STRUCT.size:
        raise BscrError(f"{path}: short BSCR header")
    if data[:4] != b"bscr":
        raise BscrError(f"{path}: unexpected magic {data[:4]!r}")
    header = HEADER_STRUCT.unpack_from(data, HEADER_OFFSET)
    declared_size, _h1, _h2, _h3, pool_start, code_size, code_start = header
    if declared_size != len(data):
        raise BscrError(f"{path}: h0 size {declared_size} != file size {len(data)}")
    if not (HEADER_OFFSET + HEADER_STRUCT.size <= pool_start <= code_start <= len(data)):
        raise BscrError(
            f"{path}: invalid h4/h6 bounds pool={pool_start} code={code_start} size={len(data)}"
        )
    if code_size % RECORD_SIZE:
        raise BscrError(f"{path}: h5 code size {code_size} is not divisible by 16")
    if code_start + code_size != len(data):
        raise BscrError(
            f"{path}: h6+h5 {code_start + code_size} != file size {len(data)}"
        )

    pool = data[pool_start:code_start]
    segments: list[Segment] = []
    by_offset: dict[int, Segment] = {}
    cursor = 0
    while cursor < len(pool):
        end = pool.find(b"\0", cursor)
        if end < 0:
            raise BscrError(f"{path}: unterminated UTF-8 pool segment at +0x{cursor:x}")
        raw = pool[cursor:end]
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise BscrError(
                f"{path}: invalid UTF-8 pool segment at +0x{cursor:x}: {exc}"
            ) from exc
        segment = Segment(
            index=len(segments),
            relative_offset=cursor,
            absolute_offset=pool_start + cursor,
            raw=raw,
            text=text,
        )
        segments.append(segment)
        by_offset[cursor] = segment
        cursor = end + 1
    if cursor != len(pool):
        raise BscrError(f"{path}: string pool parse did not end at h6")

    return BscrFile(
        path=path,
        logical_name=(logical_name or path.name).replace("\\", "/"),
        data=data,
        header=header,
        segments=segments,
        segment_by_relative_offset=by_offset,
    )


def discover_payloads(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    result: dict[str, Path] = {}
    for path in sorted(root.rglob("*.0000")):
        key = path.relative_to(root).as_posix()
        if key in result:
            raise BscrError(f"duplicate logical payload name {key}")
        result[key] = path
    if not result:
        raise BscrError(f"no *.0000 BSCR payloads below {root}")
    return result


def normalized_record(record: bytes) -> bytes:
    if len(record) != RECORD_SIZE:
        raise BscrError(f"record length {len(record)} != 16")
    if record[:4] != PUSH_OPCODE:
        return record
    return record[:PUSH_OPERAND_OFFSET] + b"\0" * PUSH_OPERAND_SIZE + record[8:]


def align_records(jp: BscrFile, en: BscrFile, *, autojunk: bool = True) -> Alignment:
    """Align two instruction streams after zeroing every push operand."""
    jp_records = [normalized_record(record) for record in jp.records()]
    en_records = [normalized_record(record) for record in en.records()]
    matcher = SequenceMatcher(None, jp_records, en_records, autojunk=autojunk)
    blocks = matcher.get_matching_blocks()
    mapping: dict[int, int] = {}
    for block in blocks:
        for delta in range(block.size):
            mapping[block.a + delta] = block.b + delta
    return Alignment(
        jp_to_en=mapping,
        matching_blocks=max(0, len(blocks) - 1),
        matched_records=sum(block.size for block in blocks),
        jp_records=len(jp_records),
        en_records=len(en_records),
        ratio=matcher.ratio(),
        autojunk=autojunk,
    )


def has_japanese(text: str) -> bool:
    return bool(JAPANESE_RE.search(text))


def protected_tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def newline_signature(text: str) -> dict[str, int]:
    return {"lf": text.count("\n"), "cr": text.count("\r")}


def stable_uid(logical_name: str, segment: Segment) -> str:
    """Build an occurrence-specific UID tied to immutable source bytes."""
    source_tag = hashlib.sha256(segment.raw).hexdigest()[:16]
    normalized_name = logical_name.replace(chr(92), "/")
    return (
        f"bscr2:{normalized_name}"
        f"::seg{segment.index:05d}::rel{segment.relative_offset:08x}::sha{source_tag}"
    )


def catalog_by_uid(rows: Sequence[Mapping[str, object]]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        uid = row.get("uid")
        if not isinstance(uid, str) or not uid:
            raise BscrError("catalog row has no non-empty uid")
        if uid in result:
            raise BscrError(f"duplicate catalog uid {uid}")
        result[uid] = dict(row)
    return result


def translation_by_uid(rows: Sequence[Mapping[str, object]]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        uid = row.get("uid")
        if not isinstance(uid, str) or not uid:
            raise BscrError("translation row has no non-empty uid")
        if uid in result:
            raise BscrError(f"duplicate translation uid {uid}")
        result[uid] = dict(row)
    return result


def validate_pool_expansion_evidence(
    evidence: object, *, source_cap: int, actual_size: int
) -> list[str]:
    """Require explicit proof before one segment borrows compacted pool slack."""
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["pool_expansion_evidence must be an object"]
    if evidence.get("kind") != "compacted_pool_slack":
        errors.append("pool_expansion_evidence.kind must be compacted_pool_slack")
    for field in ("artifact", "detail"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            errors.append(f"pool_expansion_evidence.{field} must be a non-empty string")
    if evidence.get("source_utf8_bytes") != source_cap:
        errors.append("pool_expansion_evidence.source_utf8_bytes does not match source cap")
    if evidence.get("target_utf8_bytes") != actual_size:
        errors.append("pool_expansion_evidence.target_utf8_bytes does not match encoded target")
    return errors


def validate_preserve_evidence(evidence: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["preserve_evidence must be an object"]
    kind = evidence.get("kind")
    if kind not in ALLOWED_PRESERVE_EVIDENCE_KINDS:
        errors.append(
            "preserve_evidence.kind must be one of "
            + ", ".join(sorted(ALLOWED_PRESERVE_EVIDENCE_KINDS))
        )
    for field in ("artifact", "detail"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            errors.append(f"preserve_evidence.{field} must be a non-empty string")
    return errors


def validate_translation_rows(
    catalog_rows: Sequence[Mapping[str, object]],
    translation_rows: Sequence[Mapping[str, object]],
    *,
    require_complete: bool,
    runtime_codec: RuntimeTextCodec | None = None,
) -> dict:
    """Validate immutable identity plus translation/preserve constraints."""
    catalog = catalog_by_uid(catalog_rows)
    translations = translation_by_uid(translation_rows)
    errors: list[dict] = []
    warnings: list[dict] = []
    status_counts: collections.Counter[str] = collections.Counter()

    unknown = sorted(set(translations) - set(catalog))
    for uid in unknown:
        errors.append({"uid": uid, "code": "unknown_uid", "detail": "not in catalog"})

    immutable_fields = (
        "file",
        "segment_index",
        "relative_offset",
        "source_ja",
        "source_sha256",
        "source_utf8_bytes",
        "original_file_sha256",
    )
    for uid, source in catalog.items():
        row = translations.get(uid)
        if row is None:
            status_counts["missing"] += 1
            if require_complete:
                errors.append({"uid": uid, "code": "missing_translation_row"})
            continue
        for field in immutable_fields:
            if field not in row:
                errors.append({"uid": uid, "code": "missing_immutable_field", "field": field})
            elif row[field] != source.get(field):
                errors.append(
                    {
                        "uid": uid,
                        "code": "immutable_field_mismatch",
                        "field": field,
                        "expected": source.get(field),
                        "actual": row[field],
                    }
                )

        status = row.get("status", "pending")
        if status not in {"pending", "translated", "preserve"}:
            errors.append({"uid": uid, "code": "invalid_status", "actual": status})
            continue
        status_counts[str(status)] += 1
        target = row.get("target_ko", "")
        if not isinstance(target, str):
            errors.append({"uid": uid, "code": "target_not_string"})
            continue

        if status == "pending":
            if target:
                errors.append({"uid": uid, "code": "pending_has_target"})
            if require_complete:
                errors.append({"uid": uid, "code": "pending_not_allowed_in_complete_map"})
            continue

        if status == "preserve":
            if target:
                errors.append({"uid": uid, "code": "preserve_has_target"})
            for detail in validate_preserve_evidence(row.get("preserve_evidence")):
                errors.append({"uid": uid, "code": "unproven_preserve", "detail": detail})
            continue

        # translated
        if not target:
            errors.append({"uid": uid, "code": "empty_translation"})
            continue
        if "\0" in target:
            errors.append({"uid": uid, "code": "nul_in_translation"})
        source_text = str(source["source_ja"])
        source_tokens = collections.Counter(protected_tokens(source_text))
        target_tokens = collections.Counter(protected_tokens(target))
        if source_tokens != target_tokens:
            errors.append(
                {
                    "uid": uid,
                    "code": "protected_token_mismatch",
                    "expected": dict(source_tokens),
                    "actual": dict(target_tokens),
                }
            )
        source_newlines = newline_signature(source_text)
        target_newlines = newline_signature(target)
        if source_newlines != target_newlines:
            errors.append(
                {
                    "uid": uid,
                    "code": "newline_mismatch",
                    "expected": source_newlines,
                    "actual": target_newlines,
                }
            )
        runtime_target = runtime_codec.encode_text(target) if runtime_codec else target
        target_size = len(runtime_target.encode("utf-8"))
        cap = int(source["source_utf8_bytes"])
        if target_size > cap:
            expansion_errors = validate_pool_expansion_evidence(
                row.get("pool_expansion_evidence"),
                source_cap=cap,
                actual_size=target_size,
            )
            if expansion_errors:
                errors.append(
                    {
                        "uid": uid,
                        "code": "unproven_pool_expansion",
                        "cap": cap,
                        "actual": target_size,
                        "details": expansion_errors,
                    }
                )
        elif row.get("pool_expansion_evidence") is not None:
            errors.append({"uid": uid, "code": "unnecessary_pool_expansion_evidence"})
        if has_japanese(target):
            errors.append({"uid": uid, "code": "japanese_residue_in_translation"})

    return {
        "catalog_count": len(catalog),
        "translation_row_count": len(translations),
        "require_complete": require_complete,
        "status_counts": dict(sorted(status_counts.items())),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "pass": not errors,
    }


def rebuild_allowlist_ranges(source: BscrFile) -> list[tuple[int, int]]:
    """Return the exact structural ranges a compact pool rebuild may edit."""
    ranges = [(source.pool_start, source.code_start)]
    ranges.extend(
        (
            push.record_offset + PUSH_OPERAND_OFFSET,
            push.record_offset + PUSH_OPERAND_OFFSET + PUSH_OPERAND_SIZE,
        )
        for push in source.pushes()
    )
    return ranges


def build_expected_bytes(
    source: BscrFile,
    catalog_rows: Sequence[Mapping[str, object]],
    translation_rows: Mapping[str, Mapping[str, object]],
    runtime_codec: RuntimeTextCodec | None = None,
) -> tuple[bytes, list[dict]]:
    """Rebuild the pool without embedded NUL padding and relocate all string pushes.

    The runtime constructs a fixed-size offset-to-pointer table from the first h3
    NUL-terminated pool segments. Padding a shorter translation with NUL bytes
    therefore creates fake empty segments, consumes that table early, and makes a
    later 0x1A push fail to resolve.  We compact every real segment, preserve the
    original pool byte size by putting all slack in one unreferenced trailing
    alignment segment beyond h3, and rewrite every 0x1A operand to the new offset.
    """
    by_segment: dict[int, tuple[str, bytes, Mapping[str, object]]] = {}
    changes: list[dict] = []
    for catalog_row in catalog_rows:
        uid = str(catalog_row["uid"])
        row = translation_rows.get(uid)
        if row is None or row.get("status", "pending") != "translated":
            continue
        if catalog_row["file"] != source.logical_name:
            raise BscrError(f"{uid}: catalog file does not match {source.logical_name}")
        relative = int(catalog_row["relative_offset"])
        segment = source.segment_by_relative_offset.get(relative)
        if segment is None:
            raise BscrError(f"{uid}: source segment missing at relative offset 0x{relative:x}")
        if segment.index != int(catalog_row["segment_index"]):
            raise BscrError(f"{uid}: source segment index mismatch")
        raw_source = str(catalog_row["source_ja"]).encode("utf-8")
        cap = int(catalog_row["source_utf8_bytes"])
        if raw_source != segment.raw or len(raw_source) != cap:
            raise BscrError(f"{uid}: source bytes do not match catalog")
        semantic_target = str(row["target_ko"])
        runtime_target = runtime_codec.encode_text(semantic_target) if runtime_codec else semantic_target
        target = runtime_target.encode("utf-8")
        if len(target) > cap:
            expansion_errors = validate_pool_expansion_evidence(
                row.get("pool_expansion_evidence"),
                source_cap=cap,
                actual_size=len(target),
            )
            if expansion_errors:
                raise BscrError(
                    f"{uid}: target exceeds source byte cap without valid compacted-pool proof: "
                    + "; ".join(expansion_errors)
                )
        prior = by_segment.get(segment.index)
        if prior is not None and prior[1] != target:
            raise BscrError(f"{uid}: conflicting translations for segment {segment.index}")
        by_segment[segment.index] = (uid, target, catalog_row)

    pushes = list(source.pushes())
    invalid_pushes = [push for push in pushes if push.segment_index is None]
    if invalid_pushes:
        first = invalid_pushes[0]
        raise BscrError(
            f"{source.logical_name}: push record {first.record_index} refers to "
            f"unknown pool offset 0x{first.operand:x}"
        )
    referenced_indices = {int(push.segment_index) for push in pushes}
    loader_string_count = int(source.header[3])
    trailing_reservoirs = [
        segment
        for segment in source.segments
        if segment.index >= loader_string_count
        and segment.index not in referenced_indices
        and not segment.raw
        and segment.index not in by_segment
    ]
    if not trailing_reservoirs:
        raise BscrError(f"{source.logical_name}: no empty unreferenced segment beyond h3 for pool slack")
    reservoir = trailing_reservoirs[-1]

    rebuilt_raws = [
        by_segment.get(segment.index, ("", segment.raw, {}))[1]
        for segment in source.segments
    ]
    compact_size = sum(len(raw) + 1 for raw in rebuilt_raws)
    original_pool_size = source.code_start - source.pool_start
    slack = original_pool_size - compact_size
    if slack < 0:
        raise BscrError(f"{source.logical_name}: compact pool exceeds original size by {-slack} bytes")
    rebuilt_raws[reservoir.index] += b" " * slack

    new_offsets: list[int] = []
    pool_parts: list[bytes] = []
    cursor = 0
    for raw in rebuilt_raws:
        new_offsets.append(cursor)
        pool_parts.append(raw + b"\0")
        cursor += len(raw) + 1
    rebuilt_pool = b"".join(pool_parts)
    if len(rebuilt_pool) != original_pool_size:
        raise BscrError(f"{source.logical_name}: rebuilt pool size mismatch")

    output = bytearray(source.data)
    output[source.pool_start : source.code_start] = rebuilt_pool
    for push in pushes:
        assert push.segment_index is not None
        struct.pack_into(
            "<I",
            output,
            push.record_offset + PUSH_OPERAND_OFFSET,
            new_offsets[push.segment_index],
        )

    for segment_index, (uid, target, catalog_row) in sorted(by_segment.items()):
        segment = source.segments[segment_index]
        new_relative = new_offsets[segment_index]
        changes.append(
            {
                "uid": uid,
                "file": source.logical_name,
                "segment_index": segment_index,
                "old_relative_offset": segment.relative_offset,
                "new_relative_offset": new_relative,
                "source_absolute_start": segment.absolute_offset,
                "absolute_start": source.pool_start + new_relative,
                "absolute_end_exclusive": source.pool_start + new_relative + len(target),
                "source_bytes": len(segment.raw),
                "target_bytes": len(target),
                "pool_expansion_bytes": max(0, len(target) - len(segment.raw)),
                "pool_expansion_evidence": translation_rows[uid].get("pool_expansion_evidence"),
                "semantic_target_utf8_bytes": len(str(translation_rows[uid]["target_ko"]).encode("utf-8")),
                "runtime_surrogate_character_count": (
                    runtime_codec.surrogate_count(str(translation_rows[uid]["target_ko"]))
                    if runtime_codec else 0
                ),
                "pool_slack_bytes": slack,
                "slack_reservoir_segment_index": reservoir.index,
            }
        )

    # Runtime-loader invariant: every push must resolve inside its fixed h3 table.
    for push in pushes:
        assert push.segment_index is not None
        if push.segment_index >= loader_string_count:
            raise BscrError(
                f"{source.logical_name}: pushed segment {push.segment_index} is outside h3={loader_string_count}"
            )
    return bytes(output), changes


def byte_diff_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise BscrError(f"size mismatch {len(before)} != {len(after)}")
    return [index for index, (left, right) in enumerate(zip(before, after)) if left != right]


def assert_diff_in_allowlist(
    before: bytes,
    after: bytes,
    ranges: Sequence[tuple[int, int]],
) -> dict:
    diffs = byte_diff_offsets(before, after)
    unexpected = [
        offset
        for offset in diffs
        if not any(start <= offset < end for start, end in ranges)
    ]
    return {
        "changed_byte_count": len(diffs),
        "unexpected_byte_count": len(unexpected),
        "first_unexpected_offsets": unexpected[:32],
        "pass": not unexpected,
    }
