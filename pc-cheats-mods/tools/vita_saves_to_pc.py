"""Copy Vita saves (Vita3K savedata, decrypted) into a PC SaveDataFolder as save slots, the way the PC game writes them.

PC: SaveDataFolder\\save<slot>.dat = 0x1B818 bytes, the same bytes as Vita data000N.bin (11-23: the PC game loads
them and its own re-save keeps the format). saveInfo.dat (0x4000) = 30 slot entries of 0x210 + system data. The save
writer 0x4f2850 fills an entry with: +0x8 date "%d/%02d/%02d  %02d:%02d" (local time), +0x108 place text (Shift-JIS
with the Korean patch's kanji slots, e.g. "소녀 지옥 ４Ｆ●"), +0x208 0 (= used), +0x20a/+0x20c = words +4/+6 of the
save, +0x20e 1 if save+0x30 & 0x1000000 (cleared); and in the system data: +0x3f74 = 1 when cleared, +0x3f7c+i = 1
when save[0xd1f + i*0x2bfc] == 1 (i < 9). The load list draws the place from the save itself; the date comes from
the entry. The Vita system data (data0050.bin) is the PC system data from +0x3de4 (checked: same flags at
+0x190/+0x198.. = PC +0x3f74/+0x3f7c..), but its volumes use another scale — so only the flags above are set,
computed from the saves like the PC game does.

Dates and place come from the Vita SlotParam_<n>.bin (subtitle UTF-8, or UTF-16 in converted saves; modified time
at +780: u16 year, month, day, hour, minute). A subtitle that does not encode (e.g. English text of a converted
save) takes the place text of another slot.

usage: vita_saves_to_pc.py [--src <Vita savedata dir>] [--dst <PC SaveDataFolder>] [slots...]   (default 0 1 2)
Refuses to overwrite an existing PC save; backs up saveInfo.dat once (saveInfo.dat.before_vita)."""
import argparse
import json
import shutil
import struct
from pathlib import Path

SRC = Path(r"F:\AI\cg-subs-test\rt\Vita3KFS\ux0\user\00\savedata\PCSE00516")
DST = Path(r"Y:\AI\claude-work\cg-pc\game\SaveDataFolder")
FONT = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko\staging\korean_font_report.json")
SIZE = 0x1B818


def encoder():
    slots = {r["char"]: int(r["sjis"], 16)
             for r in json.loads(FONT.read_text(encoding="utf-8-sig"))["repurposed_slots"]}

    def enc(text):
        out = bytearray()
        for ch in text:
            if ord(ch) < 128:
                out.append(ord(ch))
                continue
            try:
                out += ch.encode("cp932")
                continue
            except UnicodeEncodeError:
                pass
            if ch not in slots:
                return None
            out += slots[ch].to_bytes(2, "big")
        return bytes(out)
    return enc


def slot_param(src, s):
    p = src / f"SlotParam_{s}.bin"
    if not p.exists():
        return None, None
    b = p.read_bytes()
    raw = b[68:196]
    if raw[1:2] == b"\0" and raw[:1] != b"\0":  # UTF-16 (converted saves)
        sub = raw.decode("utf-16-le", "replace").split("\0")[0]
        korean = False
    else:
        sub = raw.split(b"\0")[0].decode("utf-8", "replace")
        korean = any(ord(c) >= 0xAC00 for c in sub)
    y, mo, d, h, mi = struct.unpack_from("<5H", b, 780)
    date = f"{y}/{mo:02d}/{d:02d}  {h:02d}:{mi:02d}" if y else None
    return (sub if korean else None), date


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--dst", type=Path, default=DST)
    ap.add_argument("slots", nargs="*", type=int, default=[0, 1, 2])
    a = ap.parse_args()
    enc = encoder()
    info_p = a.dst / "saveInfo.dat"
    info = bytearray(info_p.read_bytes())
    assert len(info) == 0x4000
    for s in a.slots:
        if (a.dst / f"save{s}.dat").exists() or info[0x210 * s + 0x208] == 0:
            raise SystemExit(f"PC slot {s + 1} is in use — not overwriting")
    params = {s: slot_param(a.src, s) for s in a.slots}
    fallback = next((enc(p) for p, _ in params.values() if p and enc(p)), b"")
    bak = a.dst / "saveInfo.dat.before_vita"
    if not bak.exists():
        shutil.copy2(info_p, bak)
    for s in a.slots:
        d = (a.src / f"data{s:04d}.bin").read_bytes()
        if len(d) != SIZE:
            raise SystemExit(f"data{s:04d}.bin is {len(d)} bytes, not {SIZE}")
        place, date = params[s]
        ptext = (enc(place) if place else None) or fallback
        date = date or "2026/01/01  00:00"
        (a.dst / f"save{s}.dat").write_bytes(d)
        e = 0x210 * s
        info[e:e + 0x210] = bytes(0x210)
        info[e + 8:e + 8 + len(date)] = date.encode("ascii")
        info[e + 0x108:e + 0x108 + len(ptext)] = ptext
        info[e + 0x20a:e + 0x20c] = d[4:6]
        info[e + 0x20c:e + 0x20e] = d[6:8]
        if struct.unpack_from("<I", d, 0x30)[0] & 0x1000000:
            info[e + 0x20e] = 1
            info[0x3f74] = 1
        for i in range(9):
            if d[0xd1f + i * 0x2bfc] == 1:
                info[0x3f7c + i] = 1
        print(f"slot {s + 1} <- data{s:04d}.bin  {date}  place {ptext.hex()}  clear {info[e + 0x20e]}")
    info_p.write_bytes(info)
    print("saveInfo.dat updated (backup", bak.name + ")")


if __name__ == "__main__":
    main()
