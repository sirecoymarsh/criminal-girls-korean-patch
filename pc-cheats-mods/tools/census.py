"""Read the draw-call census from the running PC test game (needs SaveDataFolder\\kor_census + kor_testpad).
usage: census.py reset            clear the table (next draw call)
       census.py dump [name]      print (id, caller VA, count, ecx, edx) and save to work\\census_<name>.txt
       census.py diff a b         callers present in dump b but not in dump a"""
import ctypes
import struct
import sys
from pathlib import Path

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402

NAMES = ["elem", "text", "widget", "ad420", "ad2d0", "d5fe0", "db3f0", "fbac0", "quad"]
WORK = Path(r"P:\AI\cg-battle-subs\pc\work")


def attach():
    p = R.pid()
    mods = P.modules(p)
    dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
    exe = next(v for k, v in mods.items() if k.endswith("steam_criminal.exe"))
    h = P.K.OpenProcess(0x0438, False, p)
    return h, dll, exe, P.syms()


def rd(h, a, n):
    b = ctypes.create_string_buffer(n)
    P.K.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, None)
    return b.raw


def main():
    cmd = sys.argv[1]
    if cmd == "diff":
        a = {l.split()[0] + l.split()[1] for l in (WORK / f"census_{sys.argv[2]}.txt").read_text().splitlines()}
        for l in (WORK / f"census_{sys.argv[3]}.txt").read_text().splitlines():
            if l.split()[0] + l.split()[1] not in a:
                print(l)
        return
    h, dll, exe, S = attach()
    if cmd == "reset":
        P.K.WriteProcessMemory(h, ctypes.c_void_p(dll + S["KOR_CENSUS_RESET"]), struct.pack("<I", 1), 4, None)
        print("reset; on mask", hex(struct.unpack("<I", rd(h, dll + S["KOR_CENSUS_ON"], 4))[0]))
        return
    n = struct.unpack("<I", rd(h, dll + S["KOR_CENSUS_N"], 4))[0]
    raw = rd(h, dll + S["KOR_CENSUS"], n * 24)
    delta = exe - 0x400000
    lines = []
    for i in range(n):
        idn, ret, cnt, ecx, edx, esi = struct.unpack_from("<6I", raw, i * 24)
        lines.append(f"{NAMES[idn]:7s} {ret - delta:08x} {cnt:7d} ecx={ecx:08x} edx={edx:08x} esi={esi:08x}")
    lines.sort()
    if len(sys.argv) > 2:
        (WORK / f"census_{sys.argv[2]}.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
