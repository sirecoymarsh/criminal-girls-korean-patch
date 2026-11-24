"""Measure speech-bubble box and text ink rows in PC shots (1280x720).
usage: bub_measure.py <png...>   prints per found corner: box top/bottom, ink top/bottom, gaps"""
import sys
from PIL import Image

U = 720 / 272  # px per layout unit
CORNERS = {"TL": (98, 35, False), "TR": (382, 35, True), "BL": (98, 175, False), "BR": (382, 175, True)}


def runs(vals):
    best, cur, start = (0, 0, 0), 0, 0
    for i, v in enumerate(vals):
        if v:
            if not cur:
                start = i
            cur += 1
            if cur > best[0]:
                best = (cur, start, i)
        else:
            cur = 0
    return best


for path in sys.argv[1:]:
    im = Image.open(path).convert("L")
    px = im.load()
    out = []
    for name, (ax, ay, right) in CORNERS.items():
        # a thin column just inside the box edge (left boxes: right of the left edge; right boxes: left of the right edge)
        x = int((ax - 4 + 1.5) * U) if not right else int((ax + 4 - 1.5) * U)
        y0, y1 = int((ay - 12) * U), int((ay + 40) * U)
        col = [sum(px[x + d, y] for d in range(-2, 3)) / 5 for y in range(y0, y1)]
        n, s, e = runs([v < 22 for v in col])
        if n < int(14 * U):
            continue
        bt, bb = y0 + s, y0 + e
        xs = range(int((ax - 2) * U), int((ax + 2) * U)) if False else (range(x - int(170 * U) if right else x, x if right else x + int(170 * U)))
        ink = [y for y in range(bt, bb + 1) if max(px[xx, y] for xx in xs if 0 <= xx < 1280) > 200]
        if not ink:
            continue
        out.append(f"{name}: box {bt}-{bb} ink {ink[0]}-{ink[-1]} top {ink[0] - bt} bottom {bb - ink[-1]}")
    print(path.replace(chr(92), "/").split("/")[-1], " | ".join(out) or "no bubble found")
