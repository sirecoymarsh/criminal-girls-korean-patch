"""In a PC test-copy battle: wait for the first speech bubble, freeze it (KOR_BUBC[3]=3) and photograph look variants.
Variants: list of (name, size, halfwidth, strike). Shots work/shots/var_<name>.png"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402

VARIANTS = [("before", 11.0, 0.6363, 0.0), ("a_half", 11.0, 0.5, 0.0), ("b_bold", 11.0, 0.5, 0.5),
            ("c_bold12", 12.0, 0.5, 0.5)]
p = R.pid()
mods = P.modules(p)
dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
h = P.K.OpenProcess(0x0438, False, p)
S = P.syms()


def rd(a, n):
    b = ctypes.create_string_buffer(n)
    P.K.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, None)
    return b.raw


def setf(i, v):
    P.K.WriteProcessMemory(h, ctypes.c_void_p(dll + S["KOR_BUB"] + 4 * i), struct.pack("<f", v), 4, None)


def seti(sym, i, v):
    P.K.WriteProcessMemory(h, ctypes.c_void_p(dll + S[sym] + 4 * i), struct.pack("<I", v), 4, None)


shown0 = struct.unpack("<12I", rd(dll + S["KOR_SUBDBG"], 48))[10]
t0 = time.time()
while time.time() - t0 < 30:
    if struct.unpack("<12I", rd(dll + S["KOR_SUBDBG"], 48))[10] != shown0:
        break
    time.sleep(0.05)
seti("KOR_BUBC", 3, 3)  # freeze the line
gen = 1.0
for name, size, half, strike in VARIANTS:
    setf(0, size)
    setf(11, half)
    setf(12, strike)
    setf(13, gen)
    gen += 1.0
    time.sleep(0.4)
    R.shot(f"var_{name}")
seti("KOR_BUBC", 3, 0)
setf(0, 11.0)
setf(11, 0.5)
setf(12, 0.0)
setf(13, gen)
