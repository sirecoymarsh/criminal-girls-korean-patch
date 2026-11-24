"""Walk in the PC test copy (hold a direction) and report when the battle manager [0x5c8234] appears.
usage: walk.py <seconds> <dir...>   e.g. walk.py 60 down up   (alternates every 3 s)"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402

p = R.pid()
mods = P.modules(p)
exe = next(v for k, v in mods.items() if k.endswith("steam_criminal.exe"))
dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
h = P.K.OpenProcess(0x0438, False, p)
S = P.syms()


def rd(a, n):
    b = ctypes.create_string_buffer(n)
    P.K.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, None)
    return b.raw


def u32(a):
    return struct.unpack("<I", rd(a, 4))[0]


pad = dll + S["KOR_PAD_BUTTONS"]
dirs = sys.argv[2:] or ["down"]
t0 = time.time()
k = 0
bm0 = u32(exe + 0x5c8234 - 0x400000)
gd = u32(exe + 0x5c954c - 0x400000)
print("bm", hex(bm0), "flags", hex(u32(gd + 0x20098)))
while time.time() - t0 < float(sys.argv[1]):
    d = dirs[k % len(dirs)]
    P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", R.PADB[d]), 4, None)
    t1 = time.time()
    while time.time() - t1 < 3:
        bm = u32(exe + 0x5c8234 - 0x400000)
        if bm != bm0:
            P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", 0), 4, None)
            print(f"bm {bm0:08x} -> {bm:08x} at {time.time() - t0:.1f}s flags {u32(gd + 0x20098):08x}")
            R.shot("walk_bm")
            sys.exit(0)
        time.sleep(0.1)
    k += 1
P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", 0), 4, None)
print("no change; flags", hex(u32(gd + 0x20098)))
R.shot("walk_end")
