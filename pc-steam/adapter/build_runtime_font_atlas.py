#!/usr/bin/env python3
"""Replace repurposed outer dialogue-font atlas cells with Korean Batang glyphs."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
sys.path.insert(0, str(ROOT / "adapter"))
from build_encoded_ui import compress_encode
from imy_tool import decode_imy, parse_header

FONT_COUNT = 2850
PAGE_COUNT = 5
COLS = 36
ROWS = 18
CELL_WIDTH = 56
CELL_HEIGHT = 56
GLYPHS_PER_PAGE = COLS * ROWS
GLYPH_WIDTH = 48
GLYPH_HEIGHT = 48
LOGICAL_GLYPH_SIZE = 24


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_font_bin(path: Path) -> list[tuple[int, int, int]]:
    data = path.read_bytes()
    if len(data) < 4:
        raise ValueError("font.bin is truncated")
    count = struct.unpack_from("<I", data, 0)[0]
    if count != FONT_COUNT or len(data) != 4 + count * 4:
        raise ValueError(f"unexpected font.bin layout: {count} records, {len(data)} bytes")
    records = [struct.unpack_from("<HBB", data, 4 + index * 4) for index in range(count)]
    if [row[0] for row in records] != sorted(row[0] for row in records):
        raise ValueError("font.bin code table is not ascending")
    return records


def load_font(path: Path) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), LOGICAL_GLYPH_SIZE, index=0)
    try:
        font.set_variation_by_name("Regular")
    except OSError:
        pass
    return font


def render_alpha(character: str, font: ImageFont.FreeTypeFont) -> np.ndarray:
    logical = Image.new("L", (LOGICAL_GLYPH_SIZE, LOGICAL_GLYPH_SIZE), 0)
    draw = ImageDraw.Draw(logical)
    bbox = font.getbbox(character, anchor="lt")
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    if width > LOGICAL_GLYPH_SIZE or height > LOGICAL_GLYPH_SIZE:
        raise ValueError(f"glyph does not fit logical cell: {character!r}: {bbox}")
    x = (LOGICAL_GLYPH_SIZE - width) // 2 - bbox[0]
    y = (LOGICAL_GLYPH_SIZE - height) // 2 - bbox[1]
    draw.text((x, y), character, font=font, fill=255, anchor="lt")
    physical = logical.resize((GLYPH_WIDTH, GLYPH_HEIGHT), Image.Resampling.NEAREST)
    return np.asarray(physical, dtype=np.uint8)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--font-bin", type=Path, required=True)
    ap.add_argument("--font-report", type=Path, required=True)
    ap.add_argument("--font-source", type=Path, required=True)
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    records = parse_font_bin(args.font_bin)
    record_by_code = {code: (index, metric0, metric1) for index, (code, metric0, metric1) in enumerate(records)}
    report = json.loads(args.font_report.read_text(encoding="utf-8-sig"))
    if report.get("passed") is not True:
        raise ValueError("input font report did not pass")
    slots = report.get("repurposed_slots")
    preserved_slots = report.get("preserved_runtime_slots")
    if not isinstance(preserved_slots,list) or len(preserved_slots)!=int(report.get("preserved_runtime_slot_count",-1)):
        raise ValueError("preserved selector slot list is incomplete")
    if not isinstance(slots, list) or len(slots) != int(report.get("custom_character_count", -1)):
        raise ValueError("repurposed slot list is incomplete")

    normalized = []
    seen_codes = set()
    seen_indices = set()
    for row in slots:
        char = row["char"]
        code = int(row["sjis"], 16)
        if code not in record_by_code:
            raise ValueError(f"runtime font.bin does not contain slot {code:04X}")
        index, metric0, metric1 = record_by_code[code]
        if index != int(row.get("runtime_font_index", -1)):
            raise ValueError(f"runtime font index mismatch for {code:04X}: {index}")
        if metric1 != 48 or metric0 > 2:
            raise ValueError(f"slot is not a full-width runtime glyph: {code:04X}: {metric0},{metric1}")
        if code in seen_codes or index in seen_indices:
            raise ValueError(f"duplicate runtime font slot {code:04X}")
        seen_codes.add(code)
        seen_indices.add(index)
        normalized.append((char, code, index, metric0, metric1))

    repurposed_codes=seen_codes.copy()
    preserved_by_page={}
    for row in preserved_slots:
        code=int(row["sjis"],16)
        if code in repurposed_codes:
            raise ValueError(f"preserved selector slot is repurposed: {code:04X}")
        if code not in record_by_code:
            raise ValueError(f"preserved selector slot missing from font.bin: {code:04X}")
        index,metric0,metric1=record_by_code[code]
        if index!=int(row["runtime_font_index"]) or (metric0,metric1)!=(int(row["metric0"]),int(row["metric1"])):
            raise ValueError(f"preserved selector font.bin record changed: {code:04X}")
        preserved_by_page.setdefault(index//GLYPHS_PER_PAGE,[]).append((row["char"],code,index))

    font = load_font(args.font_source)
    rendered = {char: render_alpha(char, font) for char, *_ in normalized}
    args.output_root.mkdir(parents=True, exist_ok=True)
    page_reports = []
    preview_rows = []
    preserved_cell_checks=[]
    for page in range(PAGE_COUNT):
        source_path = args.source_root / f"font_{page:02d}.imy"
        source = source_path.read_bytes()
        header, original_raw = decode_imy(source)
        if (
            header.compression_type != 0x10
            or header.pixel_type != 0x0C
            or header.palette_size != 0
            or header.stride != 4096
            or header.height != 1024
            or header.decoded_unit_bytes != 2
        ):
            raise ValueError(f"unexpected runtime font IMY header: {source_path}: {header}")
        before = np.frombuffer(original_raw, dtype="<u2").reshape(header.height, header.stride // 2)
        after = before.copy()
        allowed = np.zeros(before.shape, dtype=bool)
        page_slots = [row for row in normalized if row[2] // GLYPHS_PER_PAGE == page]
        for char, code, index, metric0, metric1 in page_slots:
            cell = index % GLYPHS_PER_PAGE
            x = (cell % COLS) * CELL_WIDTH
            y = (cell // COLS) * CELL_HEIGHT
            allowed[y : y + CELL_HEIGHT, x : x + CELL_WIDTH] = True
            cell_pixels = after[y : y + CELL_HEIGHT, x : x + CELL_WIDTH]
            cell_pixels[:, :] = 0x0FFF
            alpha = rendered[char]
            alpha4 = ((alpha.astype(np.uint16) + 8) // 17) & 0xF
            cell_pixels[:GLYPH_HEIGHT, :GLYPH_WIDTH] = 0x0FFF | (alpha4 << 12)
            if len(preview_rows) < 120:
                preview_rows.append((char, code, alpha.copy()))
        changed = before != after
        outside = np.count_nonzero(changed & ~allowed)
        if outside:
            raise ValueError(f"{source_path.name}: {outside} pixels changed outside assigned cells")
        for char,code,index in preserved_by_page.get(page,[]):
            cell=index%GLYPHS_PER_PAGE
            x=(cell%COLS)*CELL_WIDTH
            y=(cell//COLS)*CELL_HEIGHT
            before_cell=before[y:y+CELL_HEIGHT,x:x+CELL_WIDTH]
            after_cell=after[y:y+CELL_HEIGHT,x:x+CELL_WIDTH]
            identical=bool(np.array_equal(before_cell,after_cell))
            if not identical:
                raise ValueError(f"preserved selector atlas cell changed: {char!r}/{code:04X}")
            preserved_cell_checks.append({
                "char":char,
                "sjis":f"{code:04X}",
                "runtime_font_index":index,
                "page":page,
                "cell":cell,
                "source_cell_sha256":sha256_bytes(before_cell.astype("<u2",copy=False).tobytes()),
                "output_cell_sha256":sha256_bytes(after_cell.astype("<u2",copy=False).tobytes()),
                "byte_identical":True,
            })
        raw = after.astype("<u2", copy=False).tobytes()
        if page_slots:
            stream, flag_count = compress_encode(raw, 2, header.decoded_row_bytes)
            encoded = source[:32] + stream
        else:
            flag_count = None
            encoded = source
        decoded_header, decoded_raw = decode_imy(encoded)
        if decoded_header != header or decoded_raw != raw:
            raise ValueError(f"{source_path.name}: encoded roundtrip mismatch")
        output = args.output_root / source_path.name
        output.write_bytes(encoded)
        page_reports.append({
            "name": source_path.name,
            "source": str(source_path),
            "output": str(output),
            "source_size": len(source),
            "output_size": len(encoded),
            "source_sha256": sha256_bytes(source),
            "output_sha256": sha256_bytes(encoded),
            "slot_count": len(page_slots),
            "changed_pixel_count": int(np.count_nonzero(changed)),
            "changed_outside_assigned_cells": int(outside),
            "flag_count": flag_count,
            "decoded_roundtrip_exact": True,
            "header_preserved": True,
            "byte_identical_noop": not page_slots and encoded == source,
        })

    preview = Image.new("RGBA", (20 * CELL_WIDTH, 6 * CELL_HEIGHT), (16, 16, 16, 255))
    draw = ImageDraw.Draw(preview)
    for position, (char, code, alpha) in enumerate(preview_rows[:120]):
        x = (position % 20) * CELL_WIDTH
        y = (position // 20) * CELL_HEIGHT
        glyph = Image.new("RGBA", (GLYPH_WIDTH, GLYPH_HEIGHT), (255, 255, 255, 0))
        glyph.putalpha(Image.fromarray(alpha, "L"))
        preview.alpha_composite(glyph, (x, y))
        draw.rectangle((x, y, x + CELL_WIDTH - 1, y + CELL_HEIGHT - 1), outline=(55, 55, 55, 255))
    preview_path = args.output_root / "runtime_font_preview.png"
    preview.save(preview_path)

    result = {
        "schema": "criminal-girls.runtime-font-atlas.v1",
        "status": "PASS",
        "source_root": str(args.source_root),
        "font_bin": str(args.font_bin),
        "font_bin_sha256": sha256_bytes(args.font_bin.read_bytes()),
        "font_source": str(args.font_source),
        "font_source_sha256": sha256_bytes(args.font_source.read_bytes()),
        "font_report": str(args.font_report),
        "font_report_sha256": sha256_bytes(args.font_report.read_bytes()),
        "geometry": {
            "page_count": PAGE_COUNT,
            "columns": COLS,
            "rows": ROWS,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "glyph_width": GLYPH_WIDTH,
            "glyph_height": GLYPH_HEIGHT,
            "glyphs_per_page": GLYPHS_PER_PAGE,
        },
        "slot_count": len(normalized),
        "preserved_text_slot_count":len(preserved_cell_checks),
        "all_preserved_text_font_records_unchanged":True,
        "all_preserved_text_atlas_cells_byte_identical":True,
        "preserved_text_cell_checks":preserved_cell_checks,
        "all_slots_present_in_font_bin": True,
        "all_slots_full_width": True,
        "all_headers_preserved": True,
        "all_decoded_roundtrips_exact": True,
        "all_changes_inside_assigned_cells": True,
        "preview": str(preview_path),
        "pages": page_reports,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"pages", "preserved_text_cell_checks"}}, ensure_ascii=True, indent=2))
    print(json.dumps({"pages": page_reports}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
