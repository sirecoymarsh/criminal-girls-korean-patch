#!/usr/bin/env python3
"""Build, encode, and statically verify the 16 audited common-UI assets.

The live F: install is never read or modified by this builder.  Every source is
the immutable extraction already recorded under extracted/ui_common_audit.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


ROOT = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
ADAPTER = ROOT / "adapter"
sys.path.insert(0, str(ADAPTER))

from imy_tool import decode_imy, indexed_to_rgba, parse_header  # noqa: E402
from build_encoded_ui import decode_imy as decode_imy_again  # noqa: E402
from build_encoded_ui import decoded_preview, encode_indexed  # noqa: E402


SRC = ROOT / "extracted/ui_common_audit/imy"
AUDIT_EXTRACT = ROOT / "audit/ui_common_candidates_extract.json"
REVIEW = ROOT / "ui_review/common_ui_v2"
ASSETS = REVIEW / "assets"
DESIGN = REVIEW / "design_previews"
ROUNDTRIP = REVIEW / "roundtrip"
SHEETS = REVIEW / "sheets"
STAGING = ROOT / "staging/ui_common_v2"
ENCODED = STAGING / "outer"
FONT_SANS = Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf")
FONT_SERIF = Path(r"C:\Windows\Fonts\NotoSerifKR-VF.ttf")


AUTHORITY = [
    {"asset": "bt_ui05.0000.imy", "source": ["GUARD", "ATTACK", "HEALING", "SPECIAL", "TARGET"], "target": ["방어", "공격", "회복", "특수", "대상"]},
    {"asset": "bt_ui_00.0001.imy", "source": ["CHAIN MP", "CHAINED", "CHAIN!", "EXTRA!"], "target": ["체인 MP", "체인", "체인!", "추가!"]},
    {"asset": "bt_ui_00.0002.imy", "source": ["ATTACK", "SPECIAL", "GUARD", "NONE", "HEALING", "ESCAPE", "SUPPORT", "SKILL", "DOWN"], "target": ["공격", "특수", "방어", "없음", "회복", "도주", "지원", "스킬", "다운"], "preserve": ["x1", "x2", "x3", "x4"]},
    {"asset": "ca_ui_00.0000.imy", "source": ["MENU", "REST", "MOTIVATE", "SHOP", "SAVE"], "target": ["메뉴", "휴식", "벌주기", "상점", "저장"]},
    {"asset": "ev_ui_00.0000.imy", "source": ["SKIP"], "target": ["스킵"]},
    {"asset": "go_ui.0000.imy", "source": ["GAME OVER"], "target": ["게임 오버"]},
    {"asset": "loti_ui08.imy", "source": ["古き記憶の園", "The garden of evil memory"], "target": ["옛 기억의 정원", "옛 기억의 정원"]},
    {"asset": "menu_tex00.imy", "source": ["MENU", "EXIT"], "target": ["메뉴", "나가기"], "preserve": ["CM"]},
    {"asset": "menu_tex03.imy", "source": ["REST", "MOTIVATE", "SHOP", "SAVE"], "target": ["휴식", "벌주기", "상점", "저장"], "preserve": ["HP", "MP"]},
    {"asset": "menu_tex05.imy", "source": ["ITEM", "FIELD", "STATUS", "PARTY", "SKILL"], "target": ["아이템", "필드", "상태", "파티", "스킬"], "preserve": ["HP", "MP"]},
    {"asset": "order_ui00.0000.imy", "source": ["GIRL'S ORDER", "GIRL'S ORDER CLEAR!"], "target": ["걸즈 오더", "걸즈 오더 클리어!"]},
    {"asset": "rest_ui.0000.imy", "source": ["HEALING..."], "target": ["회복 중…"]},
    {"asset": "st_ui01.0000.imy", "source": ["QUICK SAVE", "LOAD"], "target": ["빠른 저장", "불러오기"]},
    {"asset": "st_ui05.ptm.imy", "source": ["OK", "BACK", "USE KEY"], "target": ["확인", "뒤로", "열쇠 사용"]},
    {"asset": "title.0001.imy", "source": ["NEW GAME", "LOAD GAME", "CONTINUE", "OPTION", "ILLUST GALLERY", "PRESS START BUTTON"], "target": ["새 게임", "불러오기", "이어하기", "설정", "일러스트 갤러리", "시작 버튼을 누르세요"], "preserve": ["Live2D", "copyright", "???"]},
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def font(size: int, family: str = "sans", weight: int = 800) -> ImageFont.FreeTypeFont:
    path = FONT_SERIF if family == "serif" else FONT_SANS
    f = ImageFont.truetype(str(path), max(6, int(size)))
    f.set_variation_by_axes([max(100 if family == "sans" else 200, min(900, int(weight)))])
    return f


def source_image(data: bytes) -> Image.Image:
    h, raw = decode_imy(data)
    if not h.palette_size:
        raise ValueError("common UI v2 expects an indexed IMY")
    rgba = indexed_to_rgba(raw, data[32 : 32 + h.palette_size * 4], "bgra", False)
    return Image.frombytes("RGBA", (h.stride, h.height), rgba)


def palette_rgba(data: bytes) -> np.ndarray:
    h = parse_header(data)
    raw = np.frombuffer(data[32 : 32 + h.palette_size * 4], dtype=np.uint8).reshape(-1, 4)
    # Stored BGRA -> working RGBA.
    return raw[:, [2, 1, 0, 3]].copy()


def quantize_changed_to_source_palette(original: Image.Image, design: Image.Image, palette: np.ndarray) -> Image.Image:
    before = np.asarray(original.convert("RGBA"), dtype=np.uint8)
    wanted = np.asarray(design.convert("RGBA"), dtype=np.uint8)
    changed = np.any(before != wanted, axis=2)
    out = before.copy()
    if not changed.any():
        return Image.fromarray(out, "RGBA")
    colors, inverse = np.unique(wanted[changed].reshape(-1, 4), axis=0, return_inverse=True)
    c = colors.astype(np.int32)
    p = palette.astype(np.int32)
    dif = c[:, None, :] - p[None, :, :]
    dist = np.sum(dif[:, :, :3] ** 2, axis=2) + 4 * dif[:, :, 3] ** 2
    nearest = np.argmin(dist, axis=1)
    out[changed] = palette[nearest[inverse]]
    return Image.fromarray(out, "RGBA")


def clamp_box(box: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return max(0, x0), max(0, y0), min(size[0], x1), min(size[1], y1)


def clear_alpha(im: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Remove only sprite pixels in a tight text-only rectangle."""
    x0, y0, x1, y1 = clamp_box(box, im.size)
    a = np.array(im, dtype=np.uint8)
    region = a[y0:y1, x0:x1]
    mask = region[:, :, 3] > 0
    region[mask] = (0, 0, 0, 0)
    a[y0:y1, x0:x1] = region
    im.paste(Image.fromarray(a, "RGBA"))


def replace_bright_with_black(im: Image.Image, box: tuple[int, int, int, int], threshold: int = 125, dilate: int = 2) -> None:
    """Remove pale glyph strokes from an opaque black plaque without painting its face."""
    x0, y0, x1, y1 = clamp_box(box, im.size)
    a = np.array(im, dtype=np.uint8)
    crop = a[y0:y1, x0:x1].copy()
    rgb = crop[:, :, :3]
    core = ((np.max(rgb, axis=2) >= threshold) & (crop[:, :, 3] >= 80)).astype(np.uint8)
    if dilate:
        core = cv2.dilate(core, np.ones((dilate * 2 + 1, dilate * 2 + 1), np.uint8))
    crop[core > 0] = (0, 0, 0, 255)
    a[y0:y1, x0:x1] = crop
    im.paste(Image.fromarray(a, "RGBA"))


def inpaint_bright_label(
    im: Image.Image,
    box: tuple[int, int, int, int],
    *,
    dilate: int = 4,
    white: int = 205,
    yellow: bool = True,
    cyan: bool = False,
    band: np.ndarray | None = None,
) -> int:
    """Inpaint glyph cores and their immediate outline, never a whole rectangle."""
    x0, y0, x1, y1 = clamp_box(box, im.size)
    arr = np.array(im, dtype=np.uint8)
    crop = arr[y0:y1, x0:x1].copy()
    r, g, b, a = [crop[:, :, i] for i in range(4)]
    core = (r >= white) & (g >= white) & (b >= white) & (a >= 32)
    if yellow:
        core |= (r >= 170) & (g >= 95) & (b <= 170) & (a >= 32)
    if cyan:
        core |= (b >= 100) & (g >= 80) & (b >= r + 18) & (a >= 32)
    if band is not None:
        if band.shape != core.shape:
            raise ValueError((band.shape, core.shape))
        core &= band
    mask = core.astype(np.uint8) * 255
    if dilate:
        mask = cv2.dilate(mask, np.ones((dilate * 2 + 1, dilate * 2 + 1), np.uint8), iterations=1)
    if not mask.any():
        return 0
    for channel in range(4):
        crop[:, :, channel] = cv2.inpaint(crop[:, :, channel], mask, 3, cv2.INPAINT_TELEA)
    arr[y0:y1, x0:x1] = crop
    im.paste(Image.fromarray(arr, "RGBA"))
    return int(np.count_nonzero(mask))


def inpaint_pale_text_band(im: Image.Image, box: tuple[int, int, int, int], rel_y0: int, rel_y1: int, dilate: int = 6) -> int:
    """Inpaint pale glyph fills plus outline while retaining a bright plaque."""
    x0, y0, x1, y1 = clamp_box(box, im.size)
    arr = np.array(im, dtype=np.uint8)
    crop = arr[y0:y1, x0:x1].copy()
    r, g, b, a = [crop[:, :, i] for i in range(4)]
    core = (r > 225) & (g > 185) & (b > 50) & (a > 200)
    band = np.zeros(core.shape, dtype=bool)
    band[max(0, rel_y0):min(core.shape[0], rel_y1), :] = True
    mask = (core & band).astype(np.uint8) * 255
    if dilate:
        mask = cv2.dilate(mask, np.ones((dilate * 2 + 1, dilate * 2 + 1), np.uint8), iterations=1)
    for channel in range(4):
        crop[:, :, channel] = cv2.inpaint(crop[:, :, channel], mask, 3, cv2.INPAINT_TELEA)
    arr[y0:y1, x0:x1] = crop
    im.paste(Image.fromarray(arr, "RGBA"))
    return int(np.count_nonzero(mask))


def clear_largest_alpha_component(im: Image.Image, box: tuple[int, int, int, int]) -> int:
    """Clear one isolated glyph sprite without flooding adjacent atlas fragments."""
    x0, y0, x1, y1 = clamp_box(box, im.size)
    arr = np.array(im, dtype=np.uint8)
    crop = arr[y0:y1, x0:x1].copy()
    mask = (crop[:, :, 3] > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return 0
    component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    selected = labels == component
    crop[selected] = 0
    arr[y0:y1, x0:x1] = crop
    im.paste(Image.fromarray(arr, "RGBA"))
    return int(np.count_nonzero(selected))


def _gradient(size: tuple[int, int], top: tuple[int, int, int, int], bottom: tuple[int, int, int, int]) -> Image.Image:
    w, h = size
    if h <= 1:
        return Image.new("RGBA", size, top)
    a = np.empty((h, w, 4), dtype=np.uint8)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    for c in range(4):
        a[:, :, c] = np.round(top[c] * (1 - t) + bottom[c] * t).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def _render_text_mask(
    text: str,
    *,
    family: str,
    weight: int,
    max_size: int,
    min_size: int,
    box_size: tuple[int, int],
    shear: float = 0.0,
) -> tuple[Image.Image, int]:
    bw, bh = box_size
    chosen = min_size
    rendered: Image.Image | None = None
    for size in range(max_size, min_size - 1, -1):
        f = font(size, family, weight)
        d = ImageDraw.Draw(Image.new("L", (1, 1)))
        bb = d.textbbox((0, 0), text, font=f)
        tw, th = max(1, bb[2] - bb[0]), max(1, bb[3] - bb[1])
        pad = max(8, size // 5)
        mask = Image.new("L", (tw + pad * 2, th + pad * 2), 0)
        md = ImageDraw.Draw(mask)
        md.text((pad - bb[0], pad - bb[1]), text, font=f, fill=255)
        if shear:
            extra = int(abs(shear) * mask.height) + 8
            mask = mask.transform(
                (mask.width + extra, mask.height),
                Image.Transform.AFFINE,
                (1, shear, -shear * mask.height if shear > 0 else 0, 0, 1, 0),
                resample=Image.Resampling.BICUBIC,
            )
        bbox = mask.getbbox()
        if bbox:
            mask = mask.crop(bbox)
        if mask.width <= bw and mask.height <= bh:
            chosen, rendered = size, mask
            break
    if rendered is None:
        f = font(min_size, family, weight)
        d = ImageDraw.Draw(Image.new("L", (1, 1)))
        bb = d.textbbox((0, 0), text, font=f)
        rendered = Image.new("L", (max(1, bb[2] - bb[0] + 8), max(1, bb[3] - bb[1] + 8)), 0)
        ImageDraw.Draw(rendered).text((4 - bb[0], 4 - bb[1]), text, font=f, fill=255)
        if rendered.width > bw or rendered.height > bh:
            scale = min(bw / rendered.width, bh / rendered.height)
            rendered = rendered.resize((max(1, round(rendered.width * scale)), max(1, round(rendered.height * scale))), Image.Resampling.LANCZOS)
    return rendered, chosen


def draw_text(
    im: Image.Image,
    box: tuple[int, int, int, int],
    text: str,
    *,
    family: str = "sans",
    weight: int = 850,
    max_size: int = 54,
    min_size: int = 12,
    fill_top: tuple[int, int, int, int] = (255, 255, 255, 255),
    fill_bottom: tuple[int, int, int, int] | None = None,
    strokes: tuple[tuple[int, tuple[int, int, int, int]], ...] = (),
    shadow: tuple[int, int, int, tuple[int, int, int, int]] | None = None,
    shear: float = 0.0,
    align: str = "center",
    pad_x: int = 0,
) -> dict:
    x0, y0, x1, y1 = clamp_box(box, im.size)
    bw, bh = x1 - x0, y1 - y0
    mask, chosen = _render_text_mask(text, family=family, weight=weight, max_size=max_size, min_size=min_size, box_size=(bw - pad_x * 2, bh), shear=shear)
    if align == "left":
        px = x0 + pad_x
    elif align == "right":
        px = x1 - pad_x - mask.width
    else:
        px = x0 + (bw - mask.width) // 2
    py = y0 + (bh - mask.height) // 2
    full = Image.new("L", im.size, 0)
    full.paste(mask, (px, py), mask)
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    if shadow:
        dx, dy, radius, color = shadow
        sm = full.filter(ImageFilter.MaxFilter(radius * 2 + 1)) if radius else full
        shifted = Image.new("L", im.size, 0)
        shifted.paste(sm, (dx, dy))
        solid = Image.new("RGBA", im.size, color)
        layer.alpha_composite(Image.composite(solid, Image.new("RGBA", im.size), shifted))
    for radius, color in sorted(strokes, key=lambda row: row[0], reverse=True):
        sm = full.filter(ImageFilter.MaxFilter(radius * 2 + 1)) if radius else full
        solid = Image.new("RGBA", im.size, color)
        layer.alpha_composite(Image.composite(solid, Image.new("RGBA", im.size), sm))
    fill_bottom = fill_bottom or fill_top
    grad = _gradient(im.size, fill_top, fill_bottom)
    layer.alpha_composite(Image.composite(grad, Image.new("RGBA", im.size), full))
    im.alpha_composite(layer)
    return {"text": text, "box": list(box), "font_size": chosen, "family": family, "weight": weight, "actual_bbox": [px, py, px + mask.width, py + mask.height]}


def draw_rotated_text(
    im: Image.Image,
    origin: tuple[int, int],
    size: tuple[int, int],
    text: str,
    angle: float,
    **kwargs,
) -> dict:
    tmp = Image.new("RGBA", size, (0, 0, 0, 0))
    rec = draw_text(tmp, (0, 0, size[0], size[1]), text, **kwargs)
    rot = tmp.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    im.alpha_composite(rot, origin)
    rec.update({"rotation": angle, "origin": list(origin), "rotated_size": list(rot.size)})
    return rec


def allow_mask(size: tuple[int, int], boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    m = np.zeros((size[1], size[0]), dtype=bool)
    for box in boxes:
        x0, y0, x1, y1 = clamp_box(box, size)
        m[y0:y1, x0:x1] = True
    return m


def build_asset(name: str, original: Image.Image) -> tuple[Image.Image, list[tuple[int, int, int, int]], list[dict], str, list[str]]:
    im = original.copy()
    draws: list[dict] = []
    issues: list[str] = []
    status = "localized"

    if name == "bt_ui05.0000.imy":
        boxes = [(270,0,530,70),(270,60,530,130),(270,120,540,190),(270,185,540,255),(280,285,530,365)]
        for b in boxes[:4]: clear_alpha(im, b)
        inpaint_bright_label(im, boxes[4], dilate=3, white=165, yellow=False)
        for b, t in zip(boxes[:4], ["방어", "공격", "회복", "특수"]):
            draws.append(draw_text(im, b, t, family="serif", weight=780, max_size=46, fill_top=(255,255,255,255), fill_bottom=(228,228,235,255), strokes=((2,(20,10,25,255)),)))
        draws.append(draw_text(im, (295,292,515,358), "대상", family="serif", weight=780, max_size=43, fill_top=(255,255,255,255), fill_bottom=(235,231,222,255), strokes=((2,(32,18,5,255)),)))

    elif name == "bt_ui_00.0001.imy":
        boxes = [(438, 40, 700, 104), (818, 0, 1024, 110), (816, 105, 960, 178), (264, 224, 530, 292), (660, 176, 975, 282), (247, 394, 482, 488), (495, 382, 785, 500)]
        for index, b in enumerate(boxes):
            if index == 3:
                inpaint_pale_text_band(im, b, 24, 56, dilate=10)
            elif index == 4:
                clear_largest_alpha_component(im, b)
            else:
                inpaint_bright_label(im, b, dilate=5, white=195, yellow=True)
        styles = dict(family="sans", weight=900, shear=0.14, strokes=((5,(35,10,4,255)),(2,(255,191,20,255))), shadow=(4,4,3,(35,0,20,180)))
        draws.append(draw_text(im,(446,47,687,100),"체인 MP",max_size=43,fill_top=(255,255,250,255),fill_bottom=(255,206,32,255),**styles))
        draws.append(draw_text(im,(825,4,1020,102),"체인",max_size=72,fill_top=(255,255,255,255),fill_bottom=(255,177,40,255),**styles))
        draws.append(draw_text(im,(270,231,518,288),"체인 MP",max_size=43,fill_top=(255,255,246,255),fill_bottom=(255,193,15,255),**styles))
        draws.append(draw_text(im,(670,184,968,276),"체인",max_size=73,fill_top=(255,237,154,255),fill_bottom=(210,120,25,255),**styles))
        draws.append(draw_text(im,(257,402,475,484),"체인!",max_size=63,fill_top=(255,246,181,255),fill_bottom=(244,151,6,255),**styles))
        draws.append(draw_text(im,(505,390,780,496),"추가!",max_size=80,fill_top=(255,249,59,255),fill_bottom=(245,145,0,255),**styles))

    elif name == "bt_ui_00.0002.imy":
        boxes = [
            (0,0,270,78),(280,0,565,78),(574,0,826,78),(830,0,1024,78),
            (0,88,270,175),(280,88,565,175),(574,88,826,175),(830,88,1024,175),
            (0,180,318,270),(338,180,635,270),(630,180,950,270),
            (0,272,318,365),(338,272,635,365),(630,272,950,365),
            (0,376,205,475),(220,376,445,475),(442,376,670,475),
        ]
        for b in boxes: clear_alpha(im,b)
        active = dict(family="sans",weight=900,shear=0.13,max_size=66,min_size=25,fill_top=(255,255,255,255),fill_bottom=(235,235,238,255),strokes=((5,(50,6,10,255)),(2,(190,55,44,255))),shadow=(3,3,2,(0,0,0,180)))
        active_gold = dict(family="sans",weight=900,shear=0.13,max_size=66,min_size=25,fill_top=(255,251,188,255),fill_bottom=(188,112,24,255),strokes=((5,(35,18,5,255)),(2,(126,67,5,255))),shadow=(3,3,2,(0,0,0,180)))
        active_teal = dict(active); active_teal["strokes"] = ((5,(4,52,52,255)),(2,(24,171,167,255)))
        active_green = dict(active); active_green["strokes"] = ((5,(15,67,15,255)),(2,(50,150,45,255)))
        active_purple = dict(active); active_purple["strokes"] = ((5,(35,0,45,255)),(2,(90,18,95,255)))
        active_blue = dict(active); active_blue["strokes"] = ((5,(7,24,85,255)),(2,(35,60,206,255)))
        row1=[("공격",active),("특수",active_gold),("방어",active_teal),("없음",active)]
        row2=[("공격",active_gold),("특수",active_gold),("방어",active_gold),("없음",active_gold)]
        row3=[("회복",active_green),("도주",active_purple),("지원",active_blue)]
        row4=[("회복",active_gold),("도주",active_gold),("지원",active_gold)]
        row5=[("스킬",active),("스킬",active_gold),("다운",dict(active,strokes=((5,(15,15,18,255)),(2,(85,85,90,255)))))]
        for b,(t,s) in zip(boxes,row1+row2+row3+row4+row5): draws.append(draw_text(im,b,t,**s))

    elif name == "ca_ui_00.0000.imy":
        boxes=[(125,30,370,120),(500,0,665,45),(500,55,750,112),(500,120,675,175),(500,185,665,238)]
        for b in boxes: clear_alpha(im,b)
        draws.append(draw_text(im,boxes[0],"메뉴",family="sans",weight=900,max_size=53,fill_top=(255,252,150,255),fill_bottom=(255,184,38,255),strokes=((4,(22,5,30,255)),(2,(91,28,5,255)))))
        for b,t in zip(boxes[1:],["휴식","벌주기","상점","저장"]): draws.append(draw_text(im,b,t,family="sans",weight=900,max_size=50,fill_top=(255,255,255,255),fill_bottom=(232,232,235,255),strokes=((2,(18,12,24,255)),)))

    elif name == "ev_ui_00.0000.imy":
        boxes=[(135,274,245,315)]
        replace_bright_with_black(im,boxes[0],115,2)
        draws.append(draw_text(im,(130,270,245,318),"스킵",family="serif",weight=600,max_size=35,fill_top=(255,255,255,255),fill_bottom=(235,235,240,255),strokes=((1,(0,0,0,255)),)))

    elif name == "go_ui.0000.imy":
        boxes=[(0,0,450,256),(0,256,450,512)]
        for b in boxes: clear_alpha(im,b)
        dark=dict(family="sans",weight=900,max_size=112,min_size=50,shear=0.05,fill_top=(95,82,105,255),fill_bottom=(45,36,68,255),strokes=((5,(67,27,51,170)),),shadow=(5,5,3,(0,0,0,170)))
        vivid=dict(family="sans",weight=900,max_size=112,min_size=50,shear=0.05,fill_top=(234,41,92,255),fill_bottom=(127,30,105,255),strokes=((5,(82,14,56,255)),),shadow=(5,5,3,(0,0,0,180)))
        for off,sty in [(0,dark),(256,vivid)]:
            draws.append(draw_text(im,(8,off+5,440,off+125),"게임",**sty))
            draws.append(draw_text(im,(8,off+128,440,off+248),"오버",**sty))

    elif name == "loti_ui08.imy":
        boxes=[(850,175,1024,300),(375,425,510,600),(120,650,320,860),(365,610,650,870),(690,475,1024,825),(770,790,1024,1024),(20,900,730,990)]
        for b in boxes: clear_alpha(im,b)
        white=dict(family="serif",weight=900,fill_top=(255,255,255,255),fill_bottom=(226,226,235,255),strokes=((7,(5,5,8,225)),(3,(35,20,45,255))),shadow=(8,8,5,(0,0,0,170)))
        mag=dict(family="serif",weight=900,fill_top=(255,186,255,255),fill_bottom=(183,0,250,255),strokes=((8,(8,4,14,230)),(3,(62,20,76,255))),shadow=(9,9,6,(0,0,0,175)))
        draws.append(draw_text(im,(340,430,610,820),"옛",max_size=150,min_size=80,**white))
        draws.append(draw_text(im,(660,470,1020,820),"기억",max_size=145,min_size=75,**mag))
        draws.append(draw_text(im,(850,175,1020,300),"의",max_size=112,min_size=65,**white))
        draws.append(draw_text(im,(80,630,350,850),"정원",max_size=165,min_size=90,**mag))
        draws.append(draw_text(im,(24,900,720,990),"옛 기억의 정원",family="sans",weight=750,max_size=51,min_size=31,shear=0.08,align="left",pad_x=8,fill_top=(255,98,255,255),fill_bottom=(198,30,235,255),strokes=((3,(25,5,30,255)),),shadow=(3,3,2,(0,0,0,180))))

    elif name == "menu_tex00.imy":
        boxes=[(175,20,385,105),(800,450,900,600)]
        clear_alpha(im,boxes[0])
        clear_alpha(im,boxes[1])
        draws.append(draw_text(im,(185,24,380,100),"메뉴",family="sans",weight=900,max_size=52,fill_top=(255,255,165,255),fill_bottom=(255,181,30,255),strokes=((5,(20,5,23,255)),(2,(82,20,4,255)))))
        draws.append(draw_rotated_text(im,(805,455),(120,45),"나가기",-76,family="serif",weight=750,max_size=30,min_size=18,fill_top=(255,255,255,255),fill_bottom=(235,231,223,255),strokes=((2,(0,0,0,255)),)))

    elif name == "menu_tex03.imy":
        boxes=[]
        ys=[(10,67),(77,132),(142,198),(205,262)]
        for x0,x1 in [(0,252),(255,512)]: boxes += [(x0,y0,x1,y1) for y0,y1 in ys]
        for b in boxes: clear_alpha(im,b)
        labels=["휴식","벌주기","상점","저장"]
        for i,(y0,y1) in enumerate(ys):
            draws.append(draw_text(im,(0,y0,247,y1),labels[i],family="sans",weight=900,max_size=49,min_size=28,align="left",pad_x=5,fill_top=(255,255,255,255),fill_bottom=(229,229,233,255),strokes=((1,(15,10,20,255)),)))
            draws.append(draw_text(im,(260,y0,512,y1),labels[i],family="sans",weight=900,max_size=49,min_size=28,align="left",pad_x=6,fill_top=(255,238,0,255),fill_bottom=(222,199,0,255),strokes=((1,(52,43,0,255)),)))

    elif name == "menu_tex05.imy":
        boxes=[]; ys=[(10,67),(77,132),(142,198),(205,262)]
        for x0,x1 in [(0,252),(255,512)]: boxes += [(x0,y0,x1,y1) for y0,y1 in ys]
        boxes += [(306,248,472,320),(306,308,472,372)]
        for b in boxes: clear_alpha(im,b)
        labels=["아이템","필드","상태","파티"]
        for i,(y0,y1) in enumerate(ys):
            draws.append(draw_text(im,(0,y0,247,y1),labels[i],family="sans",weight=900,max_size=49,min_size=27,align="left",pad_x=5,fill_top=(255,255,255,255),fill_bottom=(229,229,233,255),strokes=((1,(15,10,20,255)),)))
            draws.append(draw_text(im,(260,y0,512,y1),labels[i],family="sans",weight=900,max_size=49,min_size=27,align="left",pad_x=6,fill_top=(255,238,0,255),fill_bottom=(222,199,0,255),strokes=((1,(52,43,0,255)),)))
        draws.append(draw_text(im,(310,252,470,318),"스킬",family="sans",weight=900,max_size=45,align="left",pad_x=3,fill_top=(255,255,255,255),fill_bottom=(230,230,234,255),strokes=((1,(10,8,15,255)),)))
        draws.append(draw_text(im,(310,312,470,370),"스킬",family="sans",weight=900,max_size=45,align="left",pad_x=3,fill_top=(255,238,0,255),fill_bottom=(222,199,0,255),strokes=((1,(52,43,0,255)),)))

    elif name == "order_ui00.0000.imy":
        boxes=[(390,10,700,235),(0,570,720,670),(0,665,390,770)]
        # Curved blue label: constrain removal to the actual diagonal label band.
        x0,y0,x1,y1=boxes[0]; yy,xx=np.mgrid[0:y1-y0,0:x1-x0]
        center=0.52*xx+12
        band=np.abs(yy-center)<38
        inpaint_bright_label(im,boxes[0],dilate=3,white=235,yellow=False,cyan=True,band=band)
        clear_alpha(im,boxes[1]); clear_alpha(im,boxes[2])
        draws.append(draw_rotated_text(im,(402,26),(205,56),"걸즈 오더",-27,family="sans",weight=850,max_size=30,min_size=18,fill_top=(93,246,245,255),fill_bottom=(39,103,230,255),strokes=((2,(13,20,66,255)),),shadow=(2,2,1,(0,0,0,170))))
        gold=dict(family="serif",weight=800,fill_top=(255,255,225,255),fill_bottom=(211,135,38,255),strokes=((3,(75,35,5,255)),(1,(255,231,160,255))),shadow=(4,4,2,(25,0,25,180)))
        draws.append(draw_text(im,(5,575,710,665),"걸즈 오더",max_size=72,min_size=40,align="left",pad_x=5,**gold))
        draws.append(draw_text(im,(5,670,385,765),"클리어!",max_size=76,min_size=42,align="left",pad_x=5,**gold))

    elif name == "rest_ui.0000.imy":
        boxes=[(0,388,475,512)]
        clear_alpha(im,boxes[0])
        draws.append(draw_text(im,(4,394,470,507),"회복 중…",family="sans",weight=900,max_size=82,min_size=45,shear=0.08,align="left",pad_x=6,fill_top=(54,255,93,255),fill_bottom=(23,231,226,255),strokes=((6,(0,0,0,255)),(2,(0,80,55,255))),shadow=(3,3,2,(0,0,0,190))))

    elif name == "st_ui01.0000.imy":
        boxes=[(0,565,290,635),(310,565,470,635)]
        for b in boxes: clear_alpha(im,b)
        style=dict(family="sans",weight=850,max_size=43,min_size=25,fill_top=(255,255,255,255),fill_bottom=(230,230,235,255),strokes=((2,(37,21,48,255)),),shadow=(3,3,2,(0,0,0,170)))
        draws.append(draw_text(im,(0,568,290,632),"빠른 저장",align="left",pad_x=2,**style))
        draws.append(draw_text(im,(310,568,470,632),"불러오기",align="left",pad_x=2,**style))

    elif name == "st_ui05.ptm.imy":
        boxes=[(115,210,210,262),(90,305,245,358),(250,375,490,428)]
        replace_bright_with_black(im,boxes[0],110,2); replace_bright_with_black(im,boxes[1],110,2)
        clear_alpha(im,boxes[2])
        draws.append(draw_text(im,(110,210,215,262),"확인",family="serif",weight=650,max_size=36,min_size=24,fill_top=(255,255,255,255),fill_bottom=(228,228,235,255),strokes=((1,(0,0,0,255)),)))
        draws.append(draw_text(im,(85,305,250,358),"뒤로",family="serif",weight=650,max_size=39,min_size=25,fill_top=(255,255,255,255),fill_bottom=(228,228,235,255),strokes=((1,(0,0,0,255)),)))
        draws.append(draw_text(im,(250,375,495,428),"열쇠 사용",family="sans",weight=850,max_size=41,min_size=25,fill_top=(255,255,255,255),fill_bottom=(232,232,235,255),strokes=((2,(24,12,30,255)),)))

    elif name == "title.0001.imy":
        boxes=[(0,500,350,560),(0,565,350,622),(0,630,350,682),(40,695,305,750),(0,755,520,812),(0,820,715,890)]
        for b in boxes: clear_alpha(im,b)
        style=dict(family="sans",weight=850,fill_top=(255,255,255,255),fill_bottom=(223,223,228,255),strokes=((2,(42,36,52,255)),),shadow=(3,3,1,(0,0,0,190)),align="left")
        specs=[((0,502,345,558),"새 게임",47,4),((0,568,345,620),"불러오기",46,4),((0,632,345,680),"이어하기",46,4),((42,697,303,748),"설정",49,6),((0,757,515,810),"일러스트 갤러리",45,3),((0,823,710,888),"시작 버튼을 누르세요",45,3)]
        for b,t,s,pad in specs: draws.append(draw_text(im,b,t,max_size=s,min_size=26,pad_x=pad,**style))

    else:
        raise KeyError(name)
    # Diff authorization follows the actual rendered glyph envelope as well as
    # the source-text removal rectangles.  This does not alter pixels; it makes
    # strokes, antialiasing and shadows auditable without widening a clear box.
    for rec in draws:
        margin = 18
        if "rotation" in rec:
            ox, oy = rec["origin"]
            rw, rh = rec["rotated_size"]
            boxes.append((ox-margin, oy-margin, ox+rw+margin, oy+rh+margin))
        else:
            x0, y0, x1, y1 = rec["actual_bbox"]
            boxes.append((x0-margin, y0-margin, x1+margin, y1+margin))
    return im, boxes, draws, status, issues


def checker(im: Image.Image, scale: float = 1.0) -> Image.Image:
    bg = Image.new("RGBA", im.size, (22,22,28,255)); d=ImageDraw.Draw(bg); tile=32
    for y in range(0,im.height,tile):
        for x in range(0,im.width,tile):
            if (x//tile+y//tile)%2: d.rectangle((x,y,x+tile-1,y+tile-1),fill=(35,35,43,255))
    bg.alpha_composite(im)
    if scale != 1.0:
        bg=bg.resize((max(1,round(bg.width*scale)),max(1,round(bg.height*scale))),Image.Resampling.LANCZOS)
    return bg.convert("RGB")


def make_contact_sheets(rows: list[dict]) -> list[str]:
    for p in SHEETS.glob("common_ui_v2_*.jpg"): p.unlink()
    labels_font=ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf",18)
    outputs=[]
    for page_no,start in enumerate(range(0,len(rows),2),1):
        subset=rows[start:start+2]; cell_w=720; cell_h=430
        sheet=Image.new("RGB",(cell_w*3,cell_h*len(subset)),(20,20,25));d=ImageDraw.Draw(sheet)
        for row_idx,row in enumerate(subset):
            for col,(tag,key) in enumerate((("JP source","source_preview"),("KO target","target_png"),("encoded roundtrip","roundtrip_png"))):
                im=checker(Image.open(row[key]).convert("RGBA")); im.thumbnail((cell_w-24,cell_h-62),Image.Resampling.LANCZOS)
                x=col*cell_w+(cell_w-im.width)//2;y=row_idx*cell_h+48+(cell_h-55-im.height)//2
                sheet.paste(im,(x,y));d.text((col*cell_w+10,row_idx*cell_h+10),f"{row['asset']} | {tag}",font=labels_font,fill=(245,245,248))
        p=SHEETS/f"common_ui_v2_{page_no:02d}.jpg";sheet.save(p,quality=91,optimize=True);outputs.append(str(p))
    return outputs


def main() -> int:
    for d in (ASSETS,DESIGN,ROUNDTRIP,SHEETS,ENCODED): d.mkdir(parents=True,exist_ok=True)
    authority_path=REVIEW/"authority_common_ui_15.json"
    authority_path.write_text(json.dumps({"source":"verified visible-text audit; pict08 false positive removed","count":len(AUTHORITY),"assets":AUTHORITY},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pict_path=SRC/"pict08.tpk.imy"
    pict_source=pict_path.read_bytes()
    pict_image=source_image(pict_source)
    pict_audit={
        "asset":pict_path.name,
        "verdict":"non_text_false_positive",
        "reason":"Visual and alpha inspection shows only the 1920x1088 group illustration; no END glyph or text sprite exists.",
        "canvas_size":list(pict_image.size),
        "alpha_bbox":list(pict_image.getchannel("A").getbbox() or ()),
        "source_sha256":sha256_bytes(pict_source),
        "included_in_authority":False,
        "patched":False,
    }
    (REVIEW/"pict08_false_positive_audit.json").write_text(json.dumps(pict_audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for stale in (
        REVIEW/"authority_common_ui_16.json",
        DESIGN/"pict08_tpk_imy__design.png",
        ASSETS/"pict08_tpk_imy__ko.png",
        ROUNDTRIP/"pict08_tpk_imy__roundtrip.png",
        ENCODED/"pict08.tpk.imy",
    ):
        if stale.exists():
            stale.unlink()
    extracted=json.loads(AUDIT_EXTRACT.read_text(encoding="utf-8"))["extracted"]
    by_name={row["name"]:row for row in extracted}
    rows=[]; replacements=[]
    for spec in AUTHORITY:
        name=spec["asset"]; src_path=SRC/name; source=src_path.read_bytes(); h=parse_header(source)
        original=source_image(source)
        design,boxes,draws,status,issues=build_asset(name,original)
        design_path=DESIGN/(name.replace(".","_")+"__design.png");design.save(design_path,optimize=True)
        target=quantize_changed_to_source_palette(original,design,palette_rgba(source))
        target_path=ASSETS/(name.replace(".","_")+"__ko.png");target.save(target_path,optimize=True)
        encoded,metrics=encode_indexed(source,target);out_path=ENCODED/name;out_path.parent.mkdir(parents=True,exist_ok=True);out_path.write_bytes(encoded)
        h2,raw2=decode_imy_again(encoded)
        if len(raw2)!=h2.decoded_size: raise AssertionError((name,len(raw2),h2.decoded_size))
        rt=decoded_preview(encoded);rt_path=ROUNDTRIP/(name.replace(".","_")+"__roundtrip.png");rt.save(rt_path,optimize=True)
        a=np.array(original);b=np.array(target);c=np.array(rt)
        changed=np.any(a!=b,axis=2); allowed=allow_mask(original.size,boxes); outside=int(np.count_nonzero(changed & ~allowed)); rt_diff=int(np.count_nonzero(np.any(b!=c,axis=2)))
        source_header=asdict(h); output_header=asdict(parse_header(encoded)); header_match=source_header==output_header
        palette_bytes=h.palette_size*4; palette_match=source[32:32+palette_bytes]==encoded[32:32+palette_bytes]
        if status=="localized" and not changed.any(): issues.append("localized asset produced no changed pixels")
        if outside: issues.append(f"{outside} changed pixels outside allowlist")
        if rt_diff: issues.append(f"{rt_diff} roundtrip pixels differ")
        if not header_match: issues.append("header changed")
        if not palette_match: issues.append("palette changed")
        verdict="PASS" if not issues else ("WAIVER" if status=="source_contradiction_preserved" and len(issues)==1 else "FAIL")
        entry=by_name[name]
        row={
            "asset":name,"status":status,"verdict":verdict,"source_index":entry["index"],"storage":"outer PS3FS entry (not nested)",
            "source_path":str(src_path),"source_preview":str(ROOT/"extracted/ui_common_audit/png"/f"{name[:-4]}.pal00.bgra.png"),
            "design_preview":str(design_path),"target_png":str(target_path),"encoded_output":str(out_path),"roundtrip_png":str(rt_path),
            "dimensions":list(original.size),"source_sha256":sha256_bytes(source),"target_png_sha256":sha256_file(target_path),"output_sha256":sha256_bytes(encoded),
            "source_size":len(source),"output_size":len(encoded),"allowlist_boxes":[list(x) for x in boxes],"changed_pixels":int(np.count_nonzero(changed)),
            "outside_allowlist":outside,"roundtrip_pixel_differences":rt_diff,"header_match":header_match,"palette_bytes_match":palette_match,
            "encode_metrics":metrics,"draws":draws,"issues":issues,
        }
        rows.append(row)
        replacements.append({"index":entry["index"],"name":name,"expected_source_sha256":entry["sha256"],"replacement_path":str(out_path),"replacement_sha256":sha256_bytes(encoded),"replacement_size":len(encoded),"structure":"outer_ps3fs_entry","status":status,"verdict":verdict})
        print(name,verdict,"changed",row["changed_pixels"],"outside",outside,"roundtrip",rt_diff)
    sheets=make_contact_sheets(rows)
    report={
        "status":"PASS" if all(r["verdict"]=="PASS" for r in rows) else "FAIL",
        "authority_count":len(AUTHORITY),"generated_targets":len(rows),"localized_assets":sum(r["status"]=="localized" for r in rows),
        "source_contradictions":sum(r["status"]=="source_contradiction_preserved" for r in rows),"failures":sum(r["verdict"]=="FAIL" for r in rows),
        "outside_allowlist_total":sum(r["outside_allowlist"] for r in rows),"roundtrip_difference_total":sum(r["roundtrip_pixel_differences"] for r in rows),
        "all_headers_match":all(r["header_match"] for r in rows),"all_palettes_match":all(r["palette_bytes_match"] for r in rows),
        "review_sheets":sheets,"rows":rows,
    }
    report_path=REVIEW/"common_ui_v2_report.json";report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    manifest={"status":report["status"],"baseline_archive":json.loads(AUDIT_EXTRACT.read_text(encoding="utf-8"))["archive"],"replacement_count":len(replacements),"localized_count":report["localized_assets"],"replacements":replacements}
    manifest_path=STAGING/"outer_replacements_common_ui_v2.json";manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary={k:v for k,v in report.items() if k!="rows"};print(json.dumps(summary,ensure_ascii=False,indent=2))
    if report["failures"] or report["outside_allowlist_total"] or report["roundtrip_difference_total"]: return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
