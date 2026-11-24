"""Read / set the field encounter countdown [[0x667324]+0x168] in the PC test copy.  usage: enc.py [value]"""
import ctypes
import struct
import sys

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402

p = R.pid()
exe = next(v for k, v in P.modules(p).items() if k.endswith("steam_criminal.exe"))
h = P.K.OpenProcess(0x0438, False, p)


def rd(a, n):
    b = ctypes.create_string_buffer(n)
    P.K.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, None)
    return b.raw


base = struct.unpack("<I", rd(exe + 0x667324 - 0x400000, 4))[0]
print("field", hex(base), "countdown", struct.unpack("<i", rd(base + 0x168, 4))[0] if base else None)
if base and len(sys.argv) > 1:
    P.K.WriteProcessMemory(h, ctypes.c_void_p(base + 0x168), struct.pack("<i", int(sys.argv[1])), 4, None)
    print("set", struct.unpack("<i", rd(base + 0x168, 4))[0])
