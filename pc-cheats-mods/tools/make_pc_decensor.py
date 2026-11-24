"""Build data\\kor_decensor.dat for the PC (Steam) game from the Vita "CGIO - Mod + Decensor" DATA.DAT.

What the Vita mod changes, carried over (checked 11-23):
  * 99 *.model.json — the PC originals are byte-identical to the Vita originals -> the mod versions are used as is
    (they point at *_lm.imy textures, and some lower stages use the next stage's .moc/.mtn)
  * 37 new textures (36 *_lm.imy + lm_inv.imy) — Vita 0xAC (Morton-swizzled indexed IMY, 512x512) -> PC 0x10 (linear, same codec, all-literal)
  * the pink censor fog = texture stream 9 of anm0000.fad (PC: 2048x2048 BGRA) -> fully transparent, written in
    place as a short YKCMP stream padded to the old size (a patch inside the PC entry, not a whole new file)
  (the mod's own UI art — ca_ui_00.0000.imy, if_camp_res.tpk, system.tpk, _anm0000.fad streams — is not carried.)

File: 'KDCN0003', u32 n_files, u32 n_patches, then n_files x {name[48], u32 size, u32 off}, n_patches x {name[48],
u32 entry size (the PC file it fits), u32 rel (offset inside that entry), u32 len, u32 off}, then the data.
Offsets are from the file start; names <= 39 bytes.
The proxy DLL (pc/src/decensor.c) adds/replaces the files in the game's archive table and serves the patches.

usage: make_pc_decensor.py --mod <Vita mod DATA.DAT> --vita <Vita original DATA.DAT> --pc <PC data_jp.dat>
                          [--pc-en <PC data_en.dat>] --out <kor_decensor.dat>
(the DLL turns on the patch whose entry size matches the archive the game opened)
"""
import argparse
import dataclasses
import hashlib
import re
import struct
import sys
from pathlib import Path

import numpy as np  # noqa: F401  (load before tools/ goes on the path: tools/dis.py shadows the stdlib)

sys.path.insert(0, r"P:\AI\cg-battle-subs\tools")
sys.path.insert(0, r"P:\AI\Codex\projects\criminal-girls-invite-only-vita-ko\adapter")
import vita_imy_tool as vimy  # noqa: E402
import ykcmp  # noqa: E402
from gen_tables import ps3fs_entries  # noqa: E402

MAGIC = b"KDCN0003"


def read(path: Path, entries: dict, name: str) -> bytes:
    e = entries[name]
    with path.open("rb") as f:
        f.seek(e.offset)
        return f.read(e.size)


def vita_lm_to_pc(data: bytes) -> bytes:
    h = vimy.parse_header(data)
    if h.compression_type != 0xAC:
        raise ValueError(f"not a Vita 0xAC IMY (0x{h.compression_type:02X})")
    stored = vimy.decode_stream(data, h)
    linear = vimy.unswizzle(stored, h.stride, h.height)
    stream, _ = vimy.literal_encode(linear)
    head = bytearray(data[:32])
    head[10] = 0x10  # compression type: PC linear
    pal = bytearray(data[32:32 + h.palette_size * 4])
    pal[0::4], pal[2::4] = pal[2::4], pal[0::4]  # Vita palette RGBA -> PC BGRA (checked on the originals, 11-23)
    out = bytes(head) + bytes(pal) + stream
    # check: decodes back to the same pixels (same codec; the PC header differs only in the compression byte)
    h2 = dataclasses.replace(h, compression_type=0x10)
    if vimy.decode_stream(out, h2) != linear:
        raise ValueError("round trip failed")
    return out


def pc_pixels(data: bytes) -> bytes:
    """PC 0x10 IMY -> BGRA bytes per pixel"""
    h = dataclasses.replace(vimy.Header(*vimy.HEADER.unpack_from(data, 0)))
    idx = vimy.decode_stream(data, h)
    pal = data[32:32 + h.palette_size * 4]
    return b"".join(pal[i * 4:i * 4 + 4] for i in idx)


def selftest(vita: Path, O: dict, pc: Path, P: dict, names):
    """converting the Vita ORIGINAL texture must give the PC original's pixels exactly"""
    n_ok = 0
    for base in names:
        if base not in O or base not in P:
            continue
        if pc_pixels(vita_lm_to_pc(read(vita, O, base))) != pc_pixels(read(pc, P, base)):
            raise SystemExit(f"selftest: {base} converted from Vita differs from the PC original")
        n_ok += 1
    if not n_ok:
        raise SystemExit("selftest: no pairs")
    return n_ok


def zero_payload(raw_size: int) -> bytes:
    """YKCMP method-4 payload for raw_size zero bytes: 4096 literal zeros, then non-overlapping copies (514 bytes
    from 4096 back)."""
    out = bytearray()
    lit = min(4096, raw_size)
    for i in range(0, lit, 127):
        n = min(127, lit - i)
        out.append(n)
        out += bytes(n)
    done = lit
    while done < raw_size:
        n = min(514, raw_size - done)
        if n < 3:  # too short for a copy: literal
            out.append(n)
            out += bytes(n)
            done += n
            continue
        v = n - 3
        tag = 224 + (v >> 4)
        packed = ((v & 15) << 12) | (4096 - 1)
        out += bytes([tag, packed >> 8, packed & 255])
        done += n
    return bytes(out)


def fog_patch(fad: bytes):
    ss = ykcmp.streams(fad)
    off, total, raw = ss[9]
    w, h, pal, typ = struct.unpack_from("<4H", fad, off - 24)
    if (w, h, pal) != (2048, 2048, 0) or raw != w * h * 4:
        raise SystemExit(f"anm0000.fad stream 9 is not the 2048x2048 fog texture ({w}x{h} pal {pal} raw {raw})")
    payload = zero_payload(raw)
    cap = total - 20
    if len(payload) > cap:
        raise SystemExit(f"transparent payload {len(payload)} > capacity {cap}")
    region = payload + bytes(cap - len(payload))
    if ykcmp.decode(region, raw) != bytes(raw):
        raise SystemExit("transparent stream does not decode to zeros")
    return len(fad), off + 20, region


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", type=Path, required=True)
    ap.add_argument("--vita", type=Path, required=True)
    ap.add_argument("--pc", type=Path, required=True)
    ap.add_argument("--pc-en", type=Path, help="data_en.dat (its anm0000.fad differs: a second fog patch)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    M = {e.name: e for e in ps3fs_entries(a.mod)}
    O = {e.name: e for e in ps3fs_entries(a.vita)}
    P = {e.name: e for e in ps3fs_entries(a.pc)}
    files, patches, skipped = [], [], []
    for name in sorted(M):
        if not name.endswith(".model.json") or name not in P:
            continue
        m = read(a.mod, M, name)
        p = read(a.pc, P, name)
        if m == p:
            continue
        if name not in O or read(a.vita, O, name) != p:  # PC differs from the Vita original: don't guess
            skipped.append(name)
            continue
        files.append((name, m))
    lm = sorted(n for n in set(M) - set(O) if n.endswith(".imy"))  # the mod's new textures (incl. lm_inv.imy)
    if any(n in P for n in lm):
        raise SystemExit(f"a new mod texture already exists on PC: {[n for n in lm if n in P]}")
    n_ok = selftest(a.vita, O, a.pc, P, [n.replace("_lm.imy", ".imy") for n in lm])
    print(f"selftest: {n_ok} Vita originals convert to exactly the PC originals")
    for name in lm:
        files.append((name, vita_lm_to_pc(read(a.mod, M, name))))
    have = set(P) | {n for n, _ in files}
    missing = set()
    for name, data in files:
        if name.endswith(".model.json"):
            for ref in re.findall(rb'"([^"]+\.(?:moc|mtn|imy|json|ogg|exp\.json|physics\.json))"', data):
                if ref.decode().lower() not in have and ref.decode().lower() in M:  # (missing on Vita too = ok)
                    missing.add((name, ref.decode()))
    if missing:
        raise SystemExit(f"model.json references not found: {sorted(missing)[:10]}")
    esize, rel, region = fog_patch(read(a.pc, P, "anm0000.fad"))
    patches.append(("anm0000.fad", esize, rel, region))
    if a.pc_en:
        Pe = {e.name: e for e in ps3fs_entries(a.pc_en)}
        if any(read(a.pc_en, Pe, n) != read(a.pc, P, n) for n, _ in files if n.endswith(".model.json")):
            raise SystemExit("data_en.dat model.json differ from data_jp.dat")
        esize_en, rel_en, region_en = fog_patch(read(a.pc_en, Pe, "anm0000.fad"))
        if esize_en == esize:
            raise SystemExit("data_en.dat anm0000.fad has the same size as data_jp.dat's: the DLL could not tell them apart")
        patches.append(("anm0000.fad", esize_en, rel_en, region_en))

    head = MAGIC + struct.pack("<II", len(files), len(patches))
    if any(len(n.encode()) > 39 for n, _ in files):
        raise SystemExit("name longer than 39 bytes")
    table_size = len(head) + len(files) * 56 + len(patches) * 64
    blob = bytearray()
    ftab, ptab = bytearray(), bytearray()
    for name, data in files:
        ftab += name.encode().ljust(48, b"\0") + struct.pack("<II", len(data), table_size + len(blob))
        blob += data
        blob += bytes((-len(blob)) % 16)
    for name, es, r, data in patches:
        ptab += name.encode().ljust(48, b"\0") + struct.pack("<IIII", es, r, len(data), table_size + len(blob))
        blob += data
        blob += bytes((-len(blob)) % 16)
    out = head + bytes(ftab) + bytes(ptab) + bytes(blob)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(out)
    print(f"files {len(files)} (model.json {len(files) - len(lm)}, textures {len(lm)}), patches {len(patches)}, "
          f"skipped {len(skipped)} {skipped[:5]}")
    print(f"wrote {a.out} {len(out)} bytes sha256 {hashlib.sha256(out).hexdigest()[:8].upper()}")


if __name__ == "__main__":
    main()
