"""Press a button repeatedly in the PC test copy until a battle starts (gd+0x20098 bit 22) or time runs out.
usage: advance.py <seconds> [button=o] [shot_every_s=15]
Prints the battle flag and saves shots work/shots/adv_<n>.png."""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402


def main():
    secs = float(sys.argv[1])
    btn = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "o"
    every = float(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else 15.0
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

    def in_battle():  # battle manager [0x5c9558]? use the screen: a battle object exists when [0x5c9698] != 0
        gd = struct.unpack("<I", rd(exe + 0x5c954c - 0x400000, 4))[0]
        bm = struct.unpack("<I", rd(exe + 0x5c8234 - 0x400000, 4))[0]  # battle manager (reward code 0x423ebf)
        return (1 << 31 if bm else 0) | ((struct.unpack("<I", rd(gd + 0x20098, 4))[0] if gd else 0) & 0x7FFFFFFF)

    pad = dll + S["KOR_PAD_BUTTONS"]
    vk = dll + S["KOR_VKEYS"]
    if "--ctrl" in sys.argv:  # hold Ctrl (skip) the whole time
        P.K.WriteProcessMemory(h, ctypes.c_void_p(vk), struct.pack("<i", 0x11), 4, None)
    bit = R.PADB[btn]
    t0 = time.time()
    last = -every
    n = 0
    prev = in_battle()
    print("battle flag at start:", prev)
    while time.time() - t0 < secs:
        cur = in_battle()
        if (cur ^ prev) & ~0x2000:
            print(f"flags {prev:08x} -> {cur:08x} at {time.time() - t0:.0f}s")
            prev = cur
            if (cur >> 31) and "--stop" in sys.argv:
                R.shot("adv_battle")
                P.K.WriteProcessMemory(h, ctypes.c_void_p(vk), struct.pack("<i", 0), 4, None)
                return
        P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", bit), 4, None)
        time.sleep(0.08)
        P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", 0), 4, None)
        time.sleep(0.17)
        if time.time() - t0 - last >= every:
            last = time.time() - t0
            R.shot(f"adv_{n}")
            n += 1
    print("no battle yet")
    P.K.WriteProcessMemory(h, ctypes.c_void_p(vk), struct.pack("<i", 0), 4, None)


if __name__ == "__main__":
    main()
