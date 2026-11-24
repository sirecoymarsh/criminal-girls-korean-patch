#!/usr/bin/env python3
"""Encode approved Korean PNG mockups back to the game's IMY/PTM streams."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


ROOT = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
sys.path.insert(0, str(ROOT / "adapter"))
from imy_tool import decode_imy, direct_to_rgba, indexed_to_rgba, parse_header

AUDIT_MANIFEST = ROOT / "ui_review/full_audit/asset_manifest.json"
MOCKUP_MANIFEST = ROOT / "ui_review/full_mockups/manifest.json"
OUT = ROOT / "staging/ui_encoded"
PREVIEWS = OUT / "roundtrip_previews"
SHEETS = OUT / "review_sheets"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def compress_encode(raw: bytes, unit_size: int, row_bytes: int) -> tuple[bytes, int]:
    """Encode an IMY stream with native decoded-output back-references.

    All-literal streams decode in the Python verifier but overflow the retail
    game's practical compressed-stream buffers (4 MiB PTMs became 4.26 MiB and
    crashed at the first Korean surface). This encoder uses the four native
    0xC0..0xFF copy modes: previous unit, previous row, row+unit, row-unit.
    It never emits undocumented operations and verifies every result through
    the independent decoder before packaging.
    """
    if unit_size not in (2, 4) or len(raw) % unit_size:
        raise ValueError((unit_size, len(raw)))
    if row_bytes <= 0 or row_bytes % unit_size:
        raise ValueError((row_bytes, unit_size))

    flags = bytearray()
    payload = bytearray()
    raw_size = len(raw)
    distances = (unit_size, row_bytes, row_bytes + unit_size, row_bytes - unit_size)

    def best_copy(position: int) -> tuple[int, int]:
        best_units = 0
        best_index = 0
        for index, distance in enumerate(distances):
            if distance <= 0 or position < distance:
                continue
            units = 0
            while units < 16 and position + (units + 1) * unit_size <= raw_size:
                here = position + units * unit_size
                source = here - distance
                if raw[here : here + unit_size] != raw[source : source + unit_size]:
                    break
                units += 1
            if units > best_units:
                best_units = units
                best_index = index
        return best_units, best_index

    position = 0
    while position < raw_size:
        units, index = best_copy(position)
        if units >= 2:
            flags.append(0xC0 | (index << 4) | (units - 1))
            position += units * unit_size
            continue

        literal_start = position
        literal_units = 1
        position += unit_size
        while literal_units < 16 and position < raw_size:
            next_units, _ = best_copy(position)
            if next_units >= 2:
                break
            literal_units += 1
            position += unit_size
        flags.append(literal_units - 1)
        payload.extend(raw[literal_start:position])

    count = len(flags)
    count_field = struct.pack("<H", count) if count <= 0xFFFF else b"\0\0" + struct.pack("<I", count)
    return count_field + bytes(flags) + bytes(payload), count


def palette_rgba(source: bytes, palette_size: int) -> list[tuple[int, int, int, int]]:
    raw = source[32 : 32 + palette_size * 4]
    result = []
    for i in range(palette_size):
        b, g, r, a = raw[i * 4 : i * 4 + 4]
        result.append((r, g, b, a))
    return result


def nearest_palette_index(color: tuple[int, int, int, int], palette: list[tuple[int, int, int, int]]) -> int:
    r, g, b, a = color
    # Alpha is weighted because atlas transparency is semantically important.
    return min(
        range(len(palette)),
        key=lambda i: (palette[i][0] - r) ** 2
        + (palette[i][1] - g) ** 2
        + (palette[i][2] - b) ** 2
        + 4 * (palette[i][3] - a) ** 2,
    )


def encode_indexed(source: bytes, target: Image.Image) -> tuple[bytes, dict]:
    header, original_raw = decode_imy(source)
    if header.compression_type != 0x10 or not header.palette_size:
        raise ValueError("not an indexed IMY")
    if target.size != (header.stride, header.height):
        raise ValueError(f"size mismatch: {target.size} != {(header.stride, header.height)}")
    palette = palette_rgba(source, header.palette_size)
    original_rgba = indexed_to_rgba(
        original_raw, source[32 : 32 + header.palette_size * 4], "bgra", False
    )
    target_rgba = target.convert("RGBA").tobytes()
    target_colors = [tuple(target_rgba[i : i + 4]) for i in range(0, len(target_rgba), 4)]
    original_colors = [tuple(original_rgba[i : i + 4]) for i in range(0, len(original_rgba), 4)]
    exact = {}
    for i, c in enumerate(palette):
        exact.setdefault(c, i)
    cache: dict[tuple[int, int, int, int], int] = {}
    out = bytearray(len(original_raw))
    changed_pixels = 0
    abs_error = 0
    max_error = 0
    for i, (wanted, before) in enumerate(zip(target_colors, original_colors)):
        if wanted == before:
            idx = original_raw[i]
        else:
            changed_pixels += 1
            idx = exact.get(wanted)
            if idx is None:
                idx = cache.get(wanted)
                if idx is None:
                    idx = nearest_palette_index(wanted, palette)
                    cache[wanted] = idx
            actual = palette[idx]
            err = sum(abs(actual[c] - wanted[c]) for c in range(4))
            abs_error += err
            max_error = max(max_error, max(abs(actual[c] - wanted[c]) for c in range(4)))
        out[i] = idx
    stream, flag_count = compress_encode(bytes(out), 2, header.decoded_row_bytes)
    encoded = source[: 32 + header.palette_size * 4] + stream
    metrics = {
        "changed_pixels": changed_pixels,
        "mapped_unique_colors": len(cache),
        "mean_absolute_channel_error_changed": abs_error / (changed_pixels * 4) if changed_pixels else 0.0,
        "max_channel_error_changed": max_error,
        "flag_count": flag_count,
        "raw_size": len(out),
    }
    return encoded, metrics


def rgba_to_direct(color: tuple[int, int, int, int], layout: str) -> bytes:
    r, g, b, a = color
    if layout == "bgra":
        return bytes((b, g, r, a))
    if layout == "rgba":
        return bytes((r, g, b, a))
    if layout == "argb":
        return bytes((a, r, g, b))
    if layout == "abgr":
        return bytes((a, b, g, r))
    raise ValueError(layout)


def encode_direct32(source: bytes, target: Image.Image, layout: str = "bgra") -> tuple[bytes, dict]:
    header, original_raw = decode_imy(source)
    if header.compression_type != 0x12 or header.pixel_type != 0x20 or header.palette_size:
        raise ValueError("not a 32-bit direct-color PTM")
    size = (header.stride // 4, header.height)
    if target.size != size:
        raise ValueError(f"size mismatch: {target.size} != {size}")
    original_rgba = direct_to_rgba(original_raw, layout, False)
    target_rgba = target.convert("RGBA").tobytes()
    out = bytearray(original_raw)
    changed_pixels = 0
    for i in range(size[0] * size[1]):
        wanted = tuple(target_rgba[i * 4 : i * 4 + 4])
        before = tuple(original_rgba[i * 4 : i * 4 + 4])
        if wanted == before:
            continue
        changed_pixels += 1
        out[i * 4 : i * 4 + 4] = rgba_to_direct(wanted, layout)
    stream, flag_count = compress_encode(bytes(out), 4, header.decoded_row_bytes)
    encoded = source[:32] + stream
    metrics = {
        "changed_pixels": changed_pixels,
        "mean_absolute_channel_error_changed": 0.0,
        "max_channel_error_changed": 0,
        "flag_count": flag_count,
        "raw_size": len(out),
        "direct_layout": layout,
        "unit_size": 4,
    }
    return encoded, metrics


def decoded_preview(encoded: bytes) -> Image.Image:
    header, raw = decode_imy(encoded)
    if header.palette_size:
        rgba = indexed_to_rgba(raw, encoded[32 : 32 + header.palette_size * 4], "bgra", False)
        size = (header.stride, header.height)
    else:
        rgba = direct_to_rgba(raw, "bgra", False)
        size = (header.stride // 4, header.height)
    return Image.frombytes("RGBA", size, rgba)


def visual_error(target: Image.Image, actual: Image.Image) -> dict:
    target = target.convert("RGBA")
    diff = ImageChops.difference(target, actual)
    extrema = diff.getextrema()
    hist = diff.histogram()
    pixels = target.width * target.height
    total = 0
    for band in range(4):
        base = band * 256
        total += sum(value * hist[base + value] for value in range(256))
    return {
        "mean_absolute_channel_error_all": total / (pixels * 4),
        "max_channel_error_all": max(high for low, high in extrema),
    }


def make_sheets(items: list[dict]) -> None:
    SHEETS.mkdir(parents=True, exist_ok=True)
    for old in SHEETS.glob("encoded_ui_*.jpg"):
        old.unlink()
    font = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 18)
    for page_no, start in enumerate(range(0, len(items), 4), 1):
        subset = items[start : start + 4]
        cell_w, cell_h = 850, 470
        sheet = Image.new("RGB", (cell_w * 2, cell_h * len(subset)), (25, 25, 29))
        draw = ImageDraw.Draw(sheet)
        for row, item in enumerate(subset):
            for col, (tag, path) in enumerate((("PNG target", Path(item["target_png"])), ("encoded roundtrip", Path(item["roundtrip_preview"])))):
                im = Image.open(path).convert("RGBA")
                bg = Image.new("RGBA", im.size, (18, 18, 22, 255))
                bg.alpha_composite(im)
                bg.thumbnail((cell_w - 24, cell_h - 70), Image.Resampling.LANCZOS)
                x = col * cell_w + (cell_w - bg.width) // 2
                y = row * cell_h + 55 + (cell_h - 62 - bg.height) // 2
                sheet.paste(bg.convert("RGB"), (x, y))
                draw.text((col * cell_w + 12, row * cell_h + 10), f"{item['label']} - {tag}", font=font, fill=(245, 245, 248))
        sheet.save(SHEETS / f"encoded_ui_{page_no:02d}.jpg", quality=90, optimize=True)


def main() -> int:
    audit = json.loads(AUDIT_MANIFEST.read_text(encoding="utf-8"))
    mockups = json.loads(MOCKUP_MANIFEST.read_text(encoding="utf-8"))
    mock_by_label = {row["label"]: row for row in mockups}
    OUT.mkdir(parents=True, exist_ok=True)
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    items = []
    for row in audit:
        safe = row["label"].replace(".", "_")
        mock = mock_by_label[safe]
        if not mock["modified"]:
            continue
        source_path = Path(row["jp"])
        target_path = Path(mock["korean_preview"])
        source = source_path.read_bytes()
        target = Image.open(target_path).convert("RGBA")
        if row["kind"] == "outer_imy":
            encoded, metrics = encode_indexed(source, target)
            output = OUT / "outer" / row["label"]
        elif row["kind"] == "system_ptm":
            encoded, metrics = encode_direct32(source, target, "bgra")
            output = OUT / "system" / Path(row["jp"]).name
        else:
            raise ValueError(f"modified unsupported kind: {row['kind']}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
        header, raw = decode_imy(encoded)
        if len(raw) != header.decoded_size:
            raise AssertionError((len(raw), header.decoded_size))
        preview = decoded_preview(encoded)
        preview_path = PREVIEWS / f"{safe}.png"
        preview.save(preview_path, optimize=True)
        metrics.update(visual_error(target, preview))
        items.append({
            "label": row["label"],
            "kind": row["kind"],
            "source": str(source_path),
            "target_png": str(target_path),
            "output": str(output),
            "roundtrip_preview": str(preview_path),
            "source_sha256": sha256(source_path),
            "output_sha256": sha256(output),
            "output_size": output.stat().st_size,
            "metrics": metrics,
        })
    make_sheets(items)
    report = {
        "status": "PASS",
        "encoded_assets": len(items),
        "outer_imy": sum(i["kind"] == "outer_imy" for i in items),
        "system_ptm": sum(i["kind"] == "system_ptm" for i in items),
        "max_mean_absolute_channel_error_all": max(i["metrics"]["mean_absolute_channel_error_all"] for i in items),
        "max_channel_error_all": max(i["metrics"]["max_channel_error_all"] for i in items),
        "review_sheet_pages": math.ceil(len(items) / 4),
        "items": items,
    }
    (OUT / "encoded_ui_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False, indent=2))
    if len(items) != 26:
        raise SystemExit(f"expected 26 encoded assets, got {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
