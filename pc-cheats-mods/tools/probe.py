"""Read / write proxy-DLL globals in the running PC test game (Y:\\AI\\claude-work\\cg-pc\\game).
usage: probe.py [sym ...]            print u32 values (default: KOR_HOOKS KOR_CAP_STATE OPT_V(16 bytes))
       probe.py set OPT_V <index> <byte>
       probe.py mem <addr_hex> <len_hex>   read process memory at a runtime address
       probe.py exe <va_hex> <len_hex>  read the exe at a static VA (moved by ASLR)"""
import ctypes
import re
import struct
import sys
from ctypes import wintypes as wt

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import run_pc as R  # noqa: E402

K = ctypes.windll.kernel32
MAP = r"P:\AI\cg-battle-subs\pc\build\xinput1_3.map"


class ME(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("id", wt.DWORD), ("pid", wt.DWORD), ("g", wt.DWORD), ("p", wt.DWORD),
                ("base", ctypes.c_void_p), ("size", wt.DWORD), ("h", wt.HMODULE), ("name", ctypes.c_char * 256),
                ("path", ctypes.c_char * 260)]


def modules(p):
    s = K.CreateToolhelp32Snapshot(0x8 | 0x10, p)
    e = ME()
    e.dwSize = ctypes.sizeof(ME)
    ok = K.Module32First(s, ctypes.byref(e))
    out = {}
    while ok:
        out[e.path.decode(errors="replace").lower()] = e.base
        ok = K.Module32Next(s, ctypes.byref(e))
    K.CloseHandle(s)
    return out


def syms():
    out = {}
    for l in open(MAP, encoding="utf-8", errors="replace"):
        m = re.match(r"\s*[0-9a-f]{4}:[0-9a-f]{8}\s+_(\w+)\s+([0-9a-f]{16})", l)
        if m:
            out[m.group(1)] = int(m.group(2), 16) - 0x10000000
    return out


def main():
    p = R.pid()
    mods = modules(p)
    dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
    exe = next(v for k, v in mods.items() if k.endswith("steam_criminal.exe"))
    h = K.OpenProcess(0x0438, False, p)
    S = syms()

    def rd(a, n):
        b = ctypes.create_string_buffer(n)
        K.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, None)
        return b.raw

    if len(sys.argv) > 1 and sys.argv[1] == "set":
        a = dll + S[sys.argv[2]] + int(sys.argv[3])
        K.WriteProcessMemory(h, ctypes.c_void_p(a), bytes([int(sys.argv[4], 0)]), 1, None)
        print("set", sys.argv[2], sys.argv[3], "=", rd(a, 1).hex())
        return
    if len(sys.argv) > 1 and sys.argv[1] == "poke":  # poke <addr_hex> <hexbytes>
        a = int(sys.argv[2], 16)
        K.WriteProcessMemory(h, ctypes.c_void_p(a), bytes.fromhex(sys.argv[3]), len(sys.argv[3]) // 2, None)
        print("poke", hex(a), rd(a, len(sys.argv[3]) // 2).hex())
        return
    if len(sys.argv) > 1 and sys.argv[1] == "seti":  # seti <SYM> <index> <int>
        a = dll + S[sys.argv[2]] + 4 * int(sys.argv[3])
        K.WriteProcessMemory(h, ctypes.c_void_p(a), struct.pack("<i", int(sys.argv[4], 0)), 4, None)
        print("seti", sys.argv[2], sys.argv[3], struct.unpack("<i", rd(a, 4))[0])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "setf":  # setf <SYM> <index> <float>
        a = dll + S[sys.argv[2]] + 4 * int(sys.argv[3])
        K.WriteProcessMemory(h, ctypes.c_void_p(a), struct.pack("<f", float(sys.argv[4])), 4, None)
        print("setf", sys.argv[2], sys.argv[3], struct.unpack("<f", rd(a, 4))[0])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "words":  # words <SYM> <count>
        n = int(sys.argv[3])
        print(sys.argv[2], " ".join(f"{x:08x}" for x in struct.unpack(f"<{n}I", rd(dll + S[sys.argv[2]], 4 * n))))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "mem":
        a = int(sys.argv[2], 16)
        b = rd(a, int(sys.argv[3], 16))
        for i in range(0, len(b), 16):
            w = struct.unpack_from("<4I", b + bytes(16), i)
            print(f"{a + i:08x}: " + b[i:i + 16].hex(" ") + "  " + " ".join(f"{x:08x}" for x in w))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "exe":
        a = exe + int(sys.argv[2], 16) - 0x400000
        b = rd(a, int(sys.argv[3], 16))
        for i in range(0, len(b), 16):
            print(f"{int(sys.argv[2], 16) + i:08x}: " + b[i:i + 16].hex(" "))
        return
    print("dll", hex(dll), "exe", hex(exe))
    for n in (sys.argv[1:] or ["KOR_HOOKS", "KOR_CAP_STATE"]):
        print(n, hex(struct.unpack("<I", rd(dll + S[n], 4))[0]))
    print("OPT_V", rd(dll + S["OPT_V"], 16).hex(" "))


if __name__ == "__main__":
    main()
