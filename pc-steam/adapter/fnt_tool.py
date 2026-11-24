#!/usr/bin/env python3
"""Inspect and preview Criminal Girls fixed-cell bitmap FNT files."""

from __future__ import annotations

import argparse
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FntHeader:
    code_table_offset: int
    palette_bytes: int
    bitmap_bytes: int
    primary_code_bytes: int
    extra_metric_bytes: int
    version: int
    glyph_count: int
    cell_width: int
    cell_height: int
    bits_per_pixel: int

    @property
    def bitmap_offset(self) -> int:
        return 32 + self.palette_bytes


def parse_header(data: bytes) -> FntHeader:
    if len(data) < 32:
        raise ValueError("FNT header is truncated")
    a, palette, bitmap, codes, extra, version, packed, bpp = struct.unpack_from("<8I", data, 0)
    h = FntHeader(
        a,
        palette,
        bitmap,
        codes,
        extra,
        version,
        packed & 0xFFFF,
        (packed >> 16) & 0xFF,
        (packed >> 24) & 0xFF,
        bpp,
    )
    expected_bitmap = h.glyph_count * h.cell_width * h.cell_height * h.bits_per_pixel // 8
    if h.bitmap_bytes != expected_bitmap:
        raise ValueError(f"bitmap size mismatch: {h.bitmap_bytes} != {expected_bitmap}")
    if h.code_table_offset != h.bitmap_offset + h.bitmap_bytes:
        raise ValueError("code table does not immediately follow bitmap data")
    if h.primary_code_bytes != h.glyph_count * 2:
        raise ValueError("primary code table is not one uint16 per glyph")
    if h.code_table_offset + h.primary_code_bytes + h.extra_metric_bytes > len(data):
        raise ValueError("FNT tables exceed file size")
    return h


def unpack_indices(blob: bytes, bits_per_pixel: int, pixel_count: int, msb_first: bool) -> bytes:
    out = bytearray()
    if bits_per_pixel == 4:
        for value in blob:
            pair = (value >> 4, value & 15) if msb_first else (value & 15, value >> 4)
            out.extend(pair)
    elif bits_per_pixel == 2:
        shifts = (6, 4, 2, 0) if msb_first else (0, 2, 4, 6)
        for value in blob:
            out.extend((value >> shift) & 3 for shift in shifts)
    else:
        raise NotImplementedError(f"unsupported FNT bpp: {bits_per_pixel}")
    return bytes(out[:pixel_count])


def decode_palette(data: bytes, h: FntHeader) -> list[tuple[int, int, int, int]]:
    raw = data[32 : 32 + h.palette_bytes]
    count = 1 << h.bits_per_pixel
    if len(raw) < count * 4:
        raise ValueError("FNT palette is truncated")
    result = []
    for i in range(count):
        b, g, r, a = raw[i * 4 : i * 4 + 4]
        result.append((r, g, b, a))
    return result


def glyph_codes(data: bytes, h: FntHeader) -> list[int]:
    return list(struct.unpack_from(f"<{h.glyph_count}H", data, h.code_table_offset))


def code_label(value: int) -> str:
    raw = value.to_bytes(2, "big")
    try:
        char = raw.decode("cp932")
    except UnicodeDecodeError:
        char = "�"
    return f"{value:04X} {char}"


def glyph_rgba(data: bytes, h: FntHeader, index: int, msb_first: bool) -> bytes:
    pixels = h.cell_width * h.cell_height
    size = pixels * h.bits_per_pixel // 8
    start = h.bitmap_offset + index * size
    indices = unpack_indices(data[start : start + size], h.bits_per_pixel, pixels, msb_first)
    palette = decode_palette(data, h)
    out = bytearray(pixels * 4)
    for i, palette_index in enumerate(indices):
        out[i * 4 : i * 4 + 4] = bytes(palette[palette_index])
    return bytes(out)


def make_sheet(path: Path, output: Path, start: int, count: int, scale: int, msb_first: bool) -> None:
    from PIL import Image, ImageDraw, ImageFont

    data = path.read_bytes()
    h = parse_header(data)
    codes = glyph_codes(data, h)
    count = max(0, min(count, h.glyph_count - start))
    cols = 12
    label_h = 18
    tile_w = max(h.cell_width * scale, 74)
    tile_h = h.cell_height * scale + label_h
    rows = (count + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * tile_w, rows * tile_h), (28, 28, 32, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for n in range(count):
        index = start + n
        pixels = glyph_rgba(data, h, index, msb_first)
        glyph = Image.frombytes("RGBA", (h.cell_width, h.cell_height), pixels)
        glyph = glyph.resize((h.cell_width * scale, h.cell_height * scale), Image.Resampling.NEAREST)
        x = (n % cols) * tile_w + (tile_w - glyph.width) // 2
        y = (n // cols) * tile_h
        sheet.alpha_composite(glyph, (x, y))
        draw.text(((n % cols) * tile_w + 2, y + h.cell_height * scale), code_label(codes[index]), font=font, fill=(240, 240, 240, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_info = sub.add_parser("info")
    p_info.add_argument("input", type=Path)
    p_sheet = sub.add_parser("sheet")
    p_sheet.add_argument("input", type=Path)
    p_sheet.add_argument("output", type=Path)
    p_sheet.add_argument("--start", type=int, default=0)
    p_sheet.add_argument("--count", type=int, default=96)
    p_sheet.add_argument("--scale", type=int, default=4)
    p_sheet.add_argument("--lsb-first", action="store_true")
    args = parser.parse_args()
    if args.command == "info":
        data = args.input.read_bytes()
        h = parse_header(data)
        print(
            json.dumps(
                {
                    **asdict(h),
                    "file_size": len(data),
                    "trailing_bytes": len(data)
                    - h.code_table_offset
                    - h.primary_code_bytes
                    - h.extra_metric_bytes,
                    "first_codes": [code_label(x) for x in glyph_codes(data, h)[:16]],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        make_sheet(args.input, args.output, args.start, args.count, args.scale, not args.lsb_first)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
