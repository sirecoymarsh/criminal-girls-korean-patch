"""Walk until a battle starts, then photograph its first second (ss_<tag>_<i>.png at ~0.25 s steps)."""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402

tag = sys.argv[1]
p = R.pid()
mods = P.modules(p)
exe = next(v for k, v in mods.items() if k.endswith("steam_criminal.exe"))
dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
h = P.K.OpenProcess(0x0438, False, p)
pad = dll + P.syms()["KOR_PAD_BUTTONS"]


def bm():
    b = ctypes.create_string_buffer(4)
    P.K.ReadProcessMemory(h, ctypes.c_void_p(exe + 0x5c8234 - 0x400000), b, 4, None)
    return struct.unpack("<I", b.raw)[0]


b0 = bm()
t0 = time.time()
k = 0
while time.time() - t0 < 60 and bm() in (b0,):
    d = ("left", "right")[k % 2]
    P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", R.PADB[d]), 4, None)
    t1 = time.time()
    while time.time() - t1 < 3 and bm() == b0:
        time.sleep(0.05)
    k += 1
P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", 0), 4, None)
for i in range(6):
    R.shot(f"ss_{tag}_{i}")
