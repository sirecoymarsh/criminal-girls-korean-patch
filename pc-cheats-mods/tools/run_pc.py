"""Launch the PC test copy (Y:\\AI\\claude-work\\cg-pc\\game) windowed on the left monitor without taking focus.
usage: run_pc.py launch | shot <name> | keys "<seq>" [shot] | close | log
keys: Enter Esc X Z C V Up Down Left Right Space BackSpace Tab, KEY:hold_ms, wait:ms (PostMessage, no focus change)"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

sys.path.insert(0, r"P:\AI\touka-ps2-kr\work\codex_watch\host")
import hostlib  # noqa: E402

GAME = Path(r"Y:\AI\claude-work\cg-pc\game")
EXE = GAME / "steam_criminal.exe"
OUT = Path(r"P:\AI\cg-battle-subs\pc\work\shots")
U = ctypes.windll.user32
KEYS = {"Enter": (0x0D, 0x1C, 0), "Esc": (0x1B, 0x01, 0), "X": (0x58, 0x2D, 0), "Z": (0x5A, 0x2C, 0),
        "C": (0x43, 0x2E, 0), "V": (0x56, 0x2F, 0), "Space": (0x20, 0x39, 0), "BackSpace": (0x08, 0x0E, 0),
        "Tab": (0x09, 0x0F, 0), "Up": (0x26, 0x48, 1), "Down": (0x28, 0x50, 1), "Left": (0x25, 0x4B, 1),
        "Right": (0x27, 0x4D, 1), "A": (0x41, 0x1E, 0), "S": (0x53, 0x1F, 0), "D": (0x44, 0x20, 0),
        "Q": (0x51, 0x10, 0), "W": (0x57, 0x11, 0), "E": (0x45, 0x12, 0)}


def pid():
    p = hostlib.pids_of(str(GAME), "steam_criminal.exe")
    return p[0] if p else None


def windows(p):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        q = wt.DWORD()
        U.GetWindowThreadProcessId(h, ctypes.byref(q))
        if q.value == p and U.IsWindowVisible(h):
            r = wt.RECT()
            U.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 200:
                out.append(h)
        return True

    U.EnumWindows(cb, 0)
    return out


def nv_events():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='nvlddmkm'} -ErrorAction SilentlyContinue | Measure-Object).Count"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def launch():
    print("nvlddmkm events before:", nv_events())
    si = subprocess.STARTUPINFO()
    si.dwFlags = 1  # STARTF_USESHOWWINDOW
    si.wShowWindow = 4  # SW_SHOWNOACTIVATE
    fg = U.GetForegroundWindow()
    subprocess.Popen([str(EXE)], cwd=str(GAME), startupinfo=si)
    t0 = time.time()
    h = None
    while time.time() - t0 < 40:
        p = pid()
        if p:
            ws = windows(p)
            if ws:
                h = ws[0]
                break
        time.sleep(0.2)
    if not h:
        print("no window")
        return
    # keep it on its own (primary) monitor — moving it to another monitor lost the D3D9 device — and put it
    # under every other window without activating it; we look at it only through the in-process capture
    r = wt.RECT()
    U.GetWindowRect(h, ctypes.byref(r))
    w, hh = r.right - r.left, r.bottom - r.top
    U.SetWindowPos(h, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_BOTTOM, NOSIZE|NOMOVE|NOACTIVATE
    # never activated -> the game waits for WM_ACTIVATEAPP(TRUE) before it renders; tell it (focus is not moved)
    for _ in range(3):
        time.sleep(1.0)
        U.PostMessageW(game_hwnd() or h, 0x001C, 1, 0)
    if fg and U.GetForegroundWindow() != fg:
        U.SetForegroundWindow(fg)
    print("pid", pid(), "hwnd", h, "size", w, hh)
    log = GAME / "SaveDataFolder" / "kor_hook.log"
    print("hook log:", log.read_text().strip() if log.exists() else "(none)")


def post_key(h, name, hold=90):
    vk, sc, ext = KEYS[name]
    lp = 1 | (sc << 16) | (ext << 24)
    U.PostMessageW(h, 0x0100, vk, lp)
    time.sleep(hold / 1000)
    U.PostMessageW(h, 0x0101, vk, lp | (1 << 30) | (1 << 31))


def game_hwnd():
    """the game's own window (not the internal 'D3DProxyWindow')"""
    for h in windows(pid()):
        c = ctypes.create_unicode_buffer(64)
        U.GetClassNameW(h, c, 64)
        if c.value != "D3DProxyWindow":
            return h
    return None


def shot(name):
    """In-process back-buffer capture by the proxy DLL (capture.c): request file -> kor_shot.bmp -> png"""
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    req = GAME / "SaveDataFolder" / "kor_shot.req"
    bmp = GAME / "SaveDataFolder" / "kor_shot.bmp"
    if bmp.exists():
        bmp.unlink()
    req.write_bytes(b"1")
    t0 = time.time()
    while req.exists() and time.time() - t0 < 5:
        time.sleep(0.05)
    if not bmp.exists():
        print("no capture (game not presenting?)")
        return False
    Image.open(bmp).convert("RGB").save(OUT / f"{name}.png")
    print("shot", OUT / f"{name}.png")
    return True


def shot_screen(name):
    """Screen pixels of the game's client area — ONLY when the game window is on top at 25 sample points
    (PrintWindow returns blank for this D3D9 window). If anything else covers it, nothing is captured."""
    from PIL import ImageGrab
    OUT.mkdir(parents=True, exist_ok=True)
    U.SetProcessDPIAware()
    h = game_hwnd()
    r = wt.RECT()
    U.GetClientRect(h, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    U.ClientToScreen(h, ctypes.byref(pt))
    w, hh = r.right, r.bottom
    U.WindowFromPoint.argtypes = [wt.POINT]
    U.GetAncestor.restype = wt.HWND
    for i in range(5):
        for j in range(5):
            p = wt.POINT(pt.x + 4 + (w - 8) * i // 4, pt.y + 4 + (hh - 8) * j // 4)
            top = U.WindowFromPoint(p)
            if U.GetAncestor(top, 2) != h and top != h:  # GA_ROOT
                print("NOT captured: another window covers the game at", (p.x, p.y))
                return False
    im = ImageGrab.grab(bbox=(pt.x, pt.y, pt.x + w, pt.y + hh), all_screens=True)
    im.save(OUT / f"{name}.png")
    print("shot", OUT / f"{name}.png", (pt.x, pt.y, w, hh))
    return True


# PC raw pad bits at 0x5f5ef8 (0x465f90 maps them to the Vita-layout game bits):
# dpad 0x10/0x20/0x40/0x80, bit20 tri (0x1000), bit21 circle (0x2000), bit22 cross (0x4000), bit23 square (0x8000)
PADB = {"select": 0x1, "start": 0x8, "up": 0x10, "right": 0x20, "down": 0x40, "left": 0x80, "l": 0x10000,
        "r": 0x20000, "tri": 0x100000, "o": 0x200000, "x": 0x400000, "sq": 0x800000}


def pad(seq):
    import struct
    import probe as P
    p = pid()
    mods = P.modules(p)
    dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
    S = P.syms()
    h = P.K.OpenProcess(0x0438, False, p)
    addr = dll + S["KOR_PAD_BUTTONS"]

    def put(v):
        P.K.WriteProcessMemory(h, ctypes.c_void_p(addr), struct.pack("<I", v), 4, None)

    for tok in seq.split():
        if tok.startswith("wait:"):
            time.sleep(int(tok[5:]) / 1000)
            continue
        names, _, ms = tok.partition(":")
        v = 0
        for n in names.split("+"):
            v |= PADB[n]
        put(v)
        time.sleep((int(ms) if ms else 120) / 1000)
        put(0)
        time.sleep(0.12)


def main():
    cmd = sys.argv[1]
    if cmd == "launch":
        launch()
    elif cmd == "shot":
        shot(sys.argv[2])
    elif cmd == "keys":
        h = windows(pid())[0]
        for tok in sys.argv[2].split():
            if tok.startswith("wait:"):
                time.sleep(int(tok[5:]) / 1000)
                continue
            k, _, ms = tok.partition(":")
            post_key(h, k, int(ms) if ms else 90)
        if len(sys.argv) > 3:
            shot(sys.argv[3])
    elif cmd == "pad":  # test pad (needs SaveDataFolder\kor_testpad at launch): pad "a:120 wait:400 down ..." [shot]
        pad(sys.argv[2])
        if len(sys.argv) > 3:
            shot(sys.argv[3])
    elif cmd == "mouse":  # mouse <x> <y> [click] [shot]  (client px; test copy passes only marked messages)
        h = game_hwnd()
        x, y = int(sys.argv[2]), int(sys.argv[3])
        lp = (y << 16) | (x & 0xFFFF)
        import struct
        import probe as P
        p = pid()
        mods = P.modules(p)
        dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
        hp = P.K.OpenProcess(0x0438, False, p)
        P.K.WriteProcessMemory(hp, ctypes.c_void_p(dll + P.syms()["KOR_MOUSE"]), struct.pack("<2i", x, y), 8, None)
        U.PostMessageW(h, 0x00FF, 0, 0x4B4F5200)  # WM_INPUT, test handle: the DLL answers "mouse moved"
        time.sleep(0.25)
        rest = sys.argv[4:]
        if rest and rest[0] == "click":
            U.PostMessageW(h, 0x0201, 0x4001, lp)
            time.sleep(0.12)
            U.PostMessageW(h, 0x0202, 0x4000, lp)
            time.sleep(0.4)
            rest = rest[1:]
        if rest:
            shot(rest[0])
    elif cmd == "vkey":  # vkey "0x0D:150 wait:500 ..." [shot]  (test copy: GetAsyncKeyState sees these keys held)
        import struct
        import probe as P
        p = pid()
        mods = P.modules(p)
        dll = next(v for k, v in mods.items() if k.endswith(r"cg-pc\game\xinput1_3.dll"))
        hp = P.K.OpenProcess(0x0438, False, p)
        a = dll + P.syms()["KOR_VKEYS"]
        for tok in sys.argv[2].split():
            if tok.startswith("wait:"):
                time.sleep(int(tok[5:]) / 1000)
                continue
            k, _, ms = tok.partition(":")
            P.K.WriteProcessMemory(hp, ctypes.c_void_p(a), struct.pack("<i", int(k, 0)), 4, None)
            time.sleep((int(ms) if ms else 120) / 1000)
            P.K.WriteProcessMemory(hp, ctypes.c_void_p(a), struct.pack("<i", 0), 4, None)
            time.sleep(0.12)
        if len(sys.argv) > 3:
            shot(sys.argv[3])
    elif cmd == "close":
        p = pid()
        if p:
            for h in windows(p):
                U.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(3)
            if pid():
                subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True)
        print("closed; nvlddmkm events:", nv_events())
    elif cmd == "log":
        print((GAME / "SaveDataFolder" / "kor_hook.log").read_text())


if __name__ == "__main__":
    main()
