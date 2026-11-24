"""x86 scan helpers for the PC steam_criminal.exe (32-bit, image base 0x400000, read-only).
usage:
  x86scan.py grep <regex> [lo hi]          linear-sweep .text, print matching instructions (va: mnemonic ops)
  x86scan.py dis <va> [count]              disassemble from va
  x86scan.py str <text>                    find a string (ascii) and the code that pushes/moves its address
  x86scan.py refs <va>                     find instructions whose operands contain the immediate va
"""
import re
import struct
import sys
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_32, Cs

EXE = Path(r"F:\DOWN\Criminal.Girls.Invite.Only\Criminal.Girls.Invite.Only\Criminal Girls Invite Only\steam_criminal.exe")
CACHE = Path(r"Y:\AI\claude-work\cg-pc\text_dis.txt")


def load():
    b = EXE.read_bytes()
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    nsec = struct.unpack_from("<H", b, pe + 6)[0]
    opt = pe + 24
    optsz = struct.unpack_from("<H", b, pe + 20)[0]
    base = struct.unpack_from("<I", b, opt + 28)[0]
    secs = []
    for i in range(nsec):
        o = opt + optsz + i * 40
        name = b[o:o + 8].rstrip(b"\0").decode()
        vs, va, rs, ra = struct.unpack_from("<IIII", b, o + 8)
        secs.append((name, base + va, vs, ra, rs))
    return b, base, secs


B, BASE, SECS = load()


def read(va, n):
    for name, sva, vs, ra, rs in SECS:
        if sva <= va < sva + max(vs, rs):
            o = ra + (va - sva)
            return B[o:o + n]
    raise KeyError(hex(va))


def text_lines():
    if CACHE.exists() and CACHE.stat().st_mtime > EXE.stat().st_mtime:
        return CACHE.read_text(encoding="utf-8").splitlines()
    name, sva, vs, ra, rs = next(s for s in SECS if s[0] == ".text")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    code = B[ra:ra + vs]
    lines = [f"{i.address:#x}: {i.mnemonic} {i.op_str}" for i in md.disasm(code, sva)]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text("\n".join(lines), encoding="utf-8")
    return lines


def main():
    cmd = sys.argv[1]
    if cmd == "grep":
        pat = re.compile(sys.argv[2])
        lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0
        hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else 1 << 32
        for l in text_lines():
            if pat.search(l):
                va = int(l.split(":")[0], 16)
                if lo <= va < hi:
                    print(l)
    elif cmd == "dis":
        va = int(sys.argv[2], 16)
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for k, i in enumerate(md.disasm(read(va, n * 8), va)):
            if k >= n:
                break
            print(f"{i.address:#x}: {i.mnemonic} {i.op_str}")
    elif cmd == "str":
        s = sys.argv[2].encode()
        i = B.find(s)
        while i >= 0:
            for name, sva, vs, ra, rs in SECS:
                if ra <= i < ra + rs:
                    va = sva + (i - ra)
                    print("string", repr(B[i:i + 40]), "at", hex(va), name)
                    for l in text_lines():
                        if f"{va:#x}" in l:
                            print("   ", l)
            i = B.find(s, i + 1)
    elif cmd == "refs":
        v = sys.argv[2].lower()
        for l in text_lines():
            if v in l:
                print(l)


if __name__ == "__main__":
    main()
