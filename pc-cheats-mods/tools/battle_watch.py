"""In a PC test-copy battle: press a button periodically and photograph each new speech bubble.
usage: battle_watch.py <seconds> [button=o] [max_shots=8]
Prints per bubble: dispatcher character / corner / voice id, voice size/hash, matches; shots work/shots/bub_<n>.png"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402

secs = float(sys.argv[1])
btn = sys.argv[2] if len(sys.argv) > 2 else "o"
maxs = int(sys.argv[3]) if len(sys.argv) > 3 else 8
p = R.pid()
mods = P.modules(p)
dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
exe = next(v for k, v in mods.items() if k.endswith("steam_criminal.exe"))
h = P.K.OpenProcess(0x0438, False, p)
S = P.syms()


def rd(a, n):
    b = ctypes.create_string_buffer(n)
    P.K.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, None)
    return b.raw


def dbg():
    return struct.unpack("<12I", rd(dll + S["KOR_SUBDBG"], 48))


pad = dll + S["KOR_PAD_BUTTONS"]


def u32(a):
    return struct.unpack("<I", rd(a, 4))[0]


def battle_state():
    """party HP list, enemy (EXP, OP) base sums, battle manager EXP/OP sums"""
    bm = u32(exe + 0x5c8234 - 0x400000)
    if not bm:
        return None
    hp, mp, ex, op = [], [], 0, 0
    for k in range(16):
        u = u32(bm + 0x28 + 4 * k)
        if not u:
            continue
        side = rd(u + 0x18, 1)[0]
        if side == 1:
            hp.append(u32(u + 0xdc))
            mp.append(u32(u + 0xe4))
        else:
            m = u32(u + 0x1c8)
            if m:
                ex += u32(m + 0x54)
                op += u32(m + 0x58)
    return hp, ex, op, u32(bm + 0x160), u32(bm + 0x15c), mp


last_bs = None
enemy_sums = None
hp_min = None
mp_min = None
t0 = time.time()
last = dbg()
shots = 0
nextpress = 0.0
while time.time() - t0 < secs:
    now = time.time() - t0
    if btn != "none" and now >= nextpress:
        P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", R.PADB[btn]), 4, None)
        time.sleep(0.08)
        P.K.WriteProcessMemory(h, ctypes.c_void_p(pad), struct.pack("<I", 0), 4, None)
        nextpress = now + 0.6
    bs = battle_state()
    if bs:
        if bs[1] or bs[2]:
            enemy_sums = (bs[1], bs[2])
        if last_bs is None or bs[3] >= last_bs[3]:
            last_bs = bs
        m = min(bs[0]) if bs[0] else None
        hp_min = m if hp_min is None or (m is not None and m < hp_min) else hp_min
        mm = min(bs[5]) if bs[5] else None
        mp_min = mm if mp_min is None or (mm is not None and mm < mp_min) else mp_min
    d = dbg()
    if d[10] != last[10]:
        bm = struct.unpack("<I", rd(exe + 0x5c8234 - 0x400000, 4))[0]
        print(f"{now:5.1f}s bubble #{d[10]} chr={d[7]} corner={d[8]} voice={d[11]} size={d[5]} "
              f"calls={d[1]} ogg={d[2]} match={d[3]} disp={d[4]} bm={bm:08x}")
        if shots < maxs:
            time.sleep(0.25)
            R.shot(f"bub_{shots}")
            shots += 1
    last = d
    time.sleep(0.05)
d = dbg()
print("end: calls", d[1], "ogg", d[2], "match", d[3], "disp", d[4], "bubbles", d[10])
print("enemy base EXP/OP sums (last seen with enemies):", enemy_sums)
print("party MP min seen", mp_min, "| first bubble-to-end time", round(time.time() - t0, 1))
print("party HP min seen", hp_min, "| last battle state (party HP, enemy EXP sum, enemy OP sum, bm EXP, bm OP):", last_bs)
opt = rd(dll + S["OPT_V"], 16)
print("OPT_V", opt.hex(" "))
