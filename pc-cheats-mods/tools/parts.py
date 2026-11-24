"""Dump the parts of a widget (PC settings UI) in the running test game.
usage: parts.py <widget_addr_hex> [verbose]
A widget keeps its parts at [w+0xcc] (count [w+0xc8]); a part p has hidden flag [p+0xb], state [p+0x50],
vertices [p+0x44] (24-byte vertices: x y z colour u v), grid dims [p+0x54] (w*h cells of 6 vertices) or one
4-vertex strip."""
import ctypes
import struct
import sys

sys.path.insert(0, r"P:\AI\cg-battle-subs\pc\tools")
import probe as P  # noqa: E402
import run_pc as R  # noqa: E402


def main():
    p = R.pid()
    h = P.K.OpenProcess(0x0438, False, p)

    def rd(a, n):
        b = ctypes.create_string_buffer(n)
        P.K.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, None)
        return b.raw

    def u32(a):
        return struct.unpack("<I", rd(a, 4))[0]

    w = int(sys.argv[1], 16)
    n, arr = u32(w + 0xc8), u32(w + 0xcc)
    print(f"widget {w:08x}: {n} parts at {arr:08x}")
    for i in range(n):
        q = u32(arr + 4 * i)
        hdr = rd(q, 0x70)
        hidden, st, vx, grid = hdr[0xb], u32(q + 0x50), u32(q + 0x44), u32(q + 0x54)
        if grid:
            gw, gh = struct.unpack("<2I", rd(grid, 8))
            nv = gw * gh * 6
        else:
            gw = gh = 0
            nv = 4
        vs = [struct.unpack_from("<3fI2f", rd(vx, nv * 24), k * 24) for k in range(nv)] if vx else []
        xs = [v[0] for v in vs]
        ys = [v[1] for v in vs]
        rng = f"x {min(xs):7.1f}..{max(xs):7.1f} y {min(ys):7.1f}..{max(ys):7.1f}" if vs else "-"
        col = f"{vs[0][3]:08x}" if vs else "-"
        name = rd(q + 0x58, 16).split(b"\0")[0]
        print(f"{i:3d} part {q:08x} hid {hidden} st {st:08x} grid {gw}x{gh} {rng} col {col} "
              f"uv {vs[0][4]:.3f},{vs[0][5]:.3f}" if vs else f"{i:3d} part {q:08x} hid {hidden} -", name)
        if len(sys.argv) > 2:
            print("    ", hdr.hex(" "))


if __name__ == "__main__":
    main()
