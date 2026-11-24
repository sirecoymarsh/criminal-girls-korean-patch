#!/usr/bin/env python3
"""Inspect and decode NIS IMY-compressed indexed texture streams.

Independent Python port of the documented MIT-licensed decoder in
ProgSys/pg_disatools. Sources are read-only; output goes to a separate path.
"""

from __future__ import annotations

import argparse
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImyHeader:
    magic: int
    compressed_data_start: int
    block_count: int
    stride: int
    compression_type: int
    pixel_type: int
    height: int
    palette_size: int
    zero0: int
    zero1: int
    zero2: int
    zero3: int

    @property
    def decoded_unit_bytes(self) -> int:
        # 0x10 indexed streams are decoded by the game's 16-bit copier;
        # 0x12/pixel_type 0x20 PTMs are 32-bit direct-color streams.
        return 4 if self.compression_type == 0x12 and self.pixel_type == 0x20 else 2

    @property
    def decoded_size(self) -> int:
        return self.stride * self.height

    @property
    def decoded_row_bytes(self) -> int:
        return self.stride

    @property
    def palette_bytes(self) -> int:
        return self.palette_size * 4

    @property
    def palette_count(self) -> int:
        if self.palette_size == 0:
            return 0
        unit = self.palette_size * 4
        return 1 if self.palette_bytes >= unit else 0


def parse_header(data: bytes) -> ImyHeader:
    if len(data) < 32:
        raise ValueError("IMY header is truncated")
    header = ImyHeader(*struct.unpack_from("<IHHHBBHHIIII", data, 0))
    if header.magic != 0x00594D49:
        raise ValueError(f"bad IMY magic: 0x{header.magic:08X}")
    if header.stride == 0 or header.height == 0:
        raise ValueError("zero-sized IMY")
    # This field is not a reliable byte offset in all game PTMs (for example,
    # if_emo01.ptm stores 0x2420 in a much smaller valid stream). Decoding is
    # anchored by the fixed header/palette/flag layout instead.
    return header


def decode_imy(data: bytes) -> tuple[ImyHeader, bytes]:
    h = parse_header(data)
    if (h.compression_type >> 4) != 1:
        raise NotImplementedError(
            f"only the game's 0x1x IMY streams are supported, got 0x{h.compression_type:02X}"
        )

    flags_offset = 32 + h.palette_size * 4
    flag_count = struct.unpack_from("<H", data, flags_offset)[0]
    if flag_count == 0:
        # Large streams use an extended 32-bit flag count after the zero marker.
        flag_count = struct.unpack_from("<I", data, flags_offset + 2)[0]
        flags_start = flags_offset + 6
    else:
        flags_start = flags_offset + 2
    flags_end = flags_start + flag_count
    if flags_end > len(data):
        raise ValueError("IMY flag table exceeds file size")

    data_pos = flags_end
    out = bytearray()
    row_bytes = h.decoded_row_bytes
    unit = h.decoded_unit_bytes
    back_table = (unit, row_bytes, row_bytes + unit, row_bytes - unit)
    for op in data[flags_start:flags_end]:
        if len(out) >= h.decoded_size:
            break
        if op & 0xF0:
            if (op & 0xC0) == 0xC0:
                distance = back_table[(op & 0x30) >> 4]
                count = ((op & 0x0F) + 1) * unit
                if distance <= 0:
                    raise ValueError(
                        f"invalid decoded back-reference distance {distance} at output {len(out)}"
                    )
                for _ in range(count):
                    source_index = len(out) - distance
                    if source_index < 0:
                        # 0x12 direct-color PTMs encode transparent top padding
                        # by referencing the zero-initialized previous scanline.
                        if h.compression_type != 0x12:
                            raise ValueError(
                                f"invalid decoded back-reference distance {distance} at output {len(out)}"
                            )
                        out.append(0)
                    else:
                        out.append(out[source_index])
            else:
                distance = (op - 0x10) * unit + unit
                source_pos = data_pos - distance
                if source_pos < flags_end or source_pos + unit > len(data):
                    raise ValueError(
                        f"invalid compressed back-reference at source {data_pos}, distance {distance}"
                    )
                out.extend(data[source_pos : source_pos + unit])
        else:
            count = (op + 1) * unit
            if data_pos + count > len(data):
                raise ValueError("IMY literal run exceeds file size")
            out.extend(data[data_pos : data_pos + count])
            data_pos += count

    if len(out) < h.decoded_size:
        raise ValueError(f"decoded stream is short: {len(out)} < {h.decoded_size}")
    return h, bytes(out[: h.decoded_size])


def indexed_to_rgba(raw: bytes, palette: bytes, layout: str, force_opaque: bool) -> bytes:
    if len(palette) != 1024:
        raise ValueError(f"expected a 1024-byte palette, got {len(palette)}")
    rgba = bytearray(len(raw) * 4)
    for i, index in enumerate(raw):
        c0, c1, c2, c3 = palette[index * 4 : index * 4 + 4]
        if layout == "bgra":
            channels = (c2, c1, c0, c3)
        elif layout == "rgba":
            channels = (c0, c1, c2, c3)
        elif layout == "argb":
            channels = (c1, c2, c3, c0)
        elif layout == "abgr":
            channels = (c3, c2, c1, c0)
        else:
            raise ValueError(f"unknown palette layout: {layout}")
        if force_opaque:
            channels = (*channels[:3], 255)
        rgba[i * 4 : i * 4 + 4] = bytes(channels)
    return bytes(rgba)


def rgba4444_to_rgba(raw: bytes, force_opaque: bool) -> bytes:
    if len(raw) % 2:
        raise ValueError(f"RGBA4444 stream is not 16-bit aligned: {len(raw)}")
    rgba = bytearray(len(raw) * 2)
    for pixel_index in range(len(raw) // 2):
        value = struct.unpack_from("<H", raw, pixel_index * 2)[0]
        r = (value & 0xF) * 17
        g = ((value >> 4) & 0xF) * 17
        b = ((value >> 8) & 0xF) * 17
        a = 255 if force_opaque else ((value >> 12) & 0xF) * 17
        rgba[pixel_index * 4 : pixel_index * 4 + 4] = bytes((r, g, b, a))
    return bytes(rgba)


def direct_to_rgba(raw: bytes, layout: str, force_opaque: bool) -> bytes:
    if len(raw) % 4:
        raise ValueError(f"direct-color stream is not 32-bit aligned: {len(raw)}")
    rgba = bytearray(len(raw))
    for i in range(0, len(raw), 4):
        c0, c1, c2, c3 = raw[i : i + 4]
        if layout == "bgra":
            channels = (c2, c1, c0, c3)
        elif layout == "rgba":
            channels = (c0, c1, c2, c3)
        elif layout == "argb":
            channels = (c1, c2, c3, c0)
        elif layout == "abgr":
            channels = (c3, c2, c1, c0)
        else:
            raise ValueError(f"unknown direct-color layout: {layout}")
        if force_opaque:
            channels = (*channels[:3], 255)
        rgba[i : i + 4] = bytes(channels)
    return bytes(rgba)


def command_info(path: Path) -> None:
    header = parse_header(path.read_bytes())
    print(json.dumps({**asdict(header), "palette_count": header.palette_count}, ensure_ascii=False, indent=2))


def command_decode(
    path: Path,
    raw_out: Path | None,
    preview_dir: Path | None,
    layouts: list[str],
    palette_indices: list[int],
) -> None:
    source = path.read_bytes()
    header, raw = decode_imy(source)
    if raw_out:
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        raw_out.write_bytes(raw)
    if preview_dir:
        from PIL import Image

        preview_dir.mkdir(parents=True, exist_ok=True)
        if header.palette_size:
            for palette_index in palette_indices:
                if palette_index < 0 or palette_index >= header.palette_count:
                    raise ValueError(
                        f"palette {palette_index} out of range; file has {header.palette_count} palettes"
                    )
                start = 32 + palette_index * header.palette_size * 4
                palette = source[start : start + header.palette_size * 4]
                for layout in layouts:
                    for opaque in (False, True):
                        pixels = indexed_to_rgba(raw, palette, layout, opaque)
                        image = Image.frombytes("RGBA", (header.stride, header.height), pixels)
                        suffix = ".opaque" if opaque else ""
                        image.save(preview_dir / f"{path.stem}.pal{palette_index:02d}.{layout}{suffix}.png")
        else:
            if header.compression_type == 0x12 and header.pixel_type == 0x20 and header.stride % 4 == 0:
                size = (header.stride // 4, header.height)
                for layout in layouts:
                    for opaque in (False, True):
                        pixels = direct_to_rgba(raw, layout, opaque)
                        image = Image.frombytes("RGBA", size, pixels)
                        suffix = ".opaque" if opaque else ""
                        image.save(preview_dir / f"{path.stem}.direct32.{layout}{suffix}.png")
            else:
                raise NotImplementedError(
                    f"unsupported direct-color IMY: compression=0x{header.compression_type:02X}, "
                    f"pixel_type=0x{header.pixel_type:02X}, stride={header.stride}"
                )
    print(
        json.dumps(
            {
                **asdict(header),
                "palette_count": header.palette_count,
                "source": str(path),
                "raw_out": str(raw_out) if raw_out else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_info = sub.add_parser("info")
    p_info.add_argument("input", type=Path)
    p_dec = sub.add_parser("decode")
    p_dec.add_argument("input", type=Path)
    p_dec.add_argument("--raw-out", type=Path)
    p_dec.add_argument("--preview-dir", type=Path)
    p_dec.add_argument(
        "--layout",
        action="append",
        choices=("bgra", "rgba", "argb", "abgr"),
        dest="layouts",
    )
    p_dec.add_argument("--palette", type=int, action="append", dest="palettes")
    args = parser.parse_args()
    if args.command == "info":
        command_info(args.input)
    else:
        command_decode(
            args.input,
            args.raw_out,
            args.preview_dir,
            args.layouts or ["bgra", "rgba", "argb", "abgr"],
            args.palettes or [0],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
