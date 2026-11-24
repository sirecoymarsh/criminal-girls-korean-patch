\
#!/usr/bin/env python3
"""Encode Korean text through Unicode characters supported by the retail converter.

The retail UTF-8 text path replaces unsupported Hangul with ``?`` before FNT
lookup.  The font builder already replaces selected, otherwise-unused Japanese
glyph slots with Korean bitmaps.  Store the corresponding former Japanese
Unicode character so the unchanged converter selects the intended patched glyph.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeTextCodec:
    font_report: Path
    font_report_sha256: str
    char_to_former: dict[str, str]
    former_to_char: dict[str, str]

    def encode_text(self, text: str) -> str:
        collisions = sorted(set(text) & set(self.former_to_char))
        if collisions:
            rendered = ", ".join(f"U+{ord(char):04X}" for char in collisions[:8])
            raise ValueError(f"semantic text contains reserved runtime surrogate characters: {rendered}")
        return "".join(self.char_to_former.get(char, char) for char in text)

    def encode_bytes(self, text: str) -> bytes:
        return self.encode_text(text).encode("utf-8")

    def decode_text(self, text: str) -> str:
        return "".join(self.former_to_char.get(char, char) for char in text)

    def surrogate_count(self, text: str) -> int:
        return sum(char in self.char_to_former for char in text)


def load_runtime_text_codec(path: Path) -> RuntimeTextCodec:
    raw = path.read_bytes()
    report = json.loads(raw.decode("utf-8-sig"))
    if report.get("passed") is not True:
        raise ValueError(f"font report did not pass: {path}")
    rows = report.get("repurposed_slots")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"font report has no repurposed slots: {path}")

    char_to_former: dict[str, str] = {}
    former_to_char: dict[str, str] = {}
    for index, row in enumerate(rows):
        char = row.get("char")
        former = row.get("former_char")
        if not isinstance(char, str) or len(char) != 1:
            raise ValueError(f"invalid source character in repurposed slot {index}")
        if not isinstance(former, str) or len(former) != 1:
            raise ValueError(f"invalid former character in repurposed slot {index}")
        if char == former:
            raise ValueError(f"identity repurposed slot U+{ord(char):04X}")
        if char in char_to_former and char_to_former[char] != former:
            raise ValueError(f"conflicting runtime surrogate for U+{ord(char):04X}")
        if former in former_to_char and former_to_char[former] != char:
            raise ValueError(f"runtime surrogate U+{ord(former):04X} is not one-to-one")
        char_to_former[char] = former
        former_to_char[former] = char

    if set(char_to_former) & set(former_to_char):
        raise ValueError("runtime glyph sources overlap reserved surrogate characters")
    return RuntimeTextCodec(
        font_report=path,
        font_report_sha256=hashlib.sha256(raw).hexdigest(),
        char_to_former=char_to_former,
        former_to_char=former_to_char,
    )
