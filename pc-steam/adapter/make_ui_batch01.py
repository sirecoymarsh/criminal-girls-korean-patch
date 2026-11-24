#!/usr/bin/env python3
"""Create the first Korean UI review mockup from the decoded JP texture."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SOURCE = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko\ui_review\format_tests\punish_tutrial_0\punish_tutrial_0.pal00.bgra.png")
OUT_DIR = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko\ui_review\batches\batch_01")
FONT = Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf")


def font(size: int):
    return ImageFont.truetype(str(FONT), size=size)


def fit_font(draw: ImageDraw.ImageDraw, text: str, box, start_size: int, minimum: int = 18):
    x0, y0, x1, y1 = box
    for size in range(start_size, minimum - 1, -1):
        f = font(size)
        bbox = draw.multiline_textbbox((0, 0), text, font=f, spacing=max(4, size // 5))
        if bbox[2] - bbox[0] <= x1 - x0 and bbox[3] - bbox[1] <= y1 - y0:
            return f
    return font(minimum)


def centered(draw, box, text, fill, start_size, stroke_width=1, stroke_fill=(30, 0, 45, 255)):
    f = fit_font(draw, text, box, start_size)
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=f, stroke_width=stroke_width)
    x = x0 + ((x1 - x0) - (bbox[2] - bbox[0])) // 2
    y = y0 + ((y1 - y0) - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.text((x, y), text, font=f, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def text_panel(draw, interior, title, body):
    x0, y0, x1, y1 = interior
    draw.rounded_rectangle(interior, radius=10, fill=(4, 3, 7, 255))
    title_font = fit_font(draw, title, (x0 + 4, y0 + 3, x1 - 4, y0 + 48), 31)
    draw.text((x0 + 4, y0 + 2), title, font=title_font, fill=(246, 216, 124, 255), stroke_width=1, stroke_fill=(50, 30, 5, 255))
    body_box = (x0 + 25, y0 + 49, x1 - 8, y1 - 9)
    body_font = fit_font(draw, body, body_box, 31, 23)
    draw.multiline_text((body_box[0], body_box[1]), body, font=body_font, fill=(250, 250, 250, 255), spacing=max(5, body_font.size // 5), stroke_width=1, stroke_fill=(0, 0, 0, 255))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(SOURCE).convert("RGBA")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((0, 0, 735, 96), radius=12, fill=(81, 26, 85, 255))
    centered(draw, (18, 14, 715, 86), "스팽킹 벌주기", (255, 244, 255, 255), 34)

    draw.rounded_rectangle((750, 0, 1110, 114), radius=8, fill=(5, 3, 8, 255))
    centered(draw, (775, 8, 1085, 102), "남은 02회", (255, 255, 255, 255), 37)

    draw.rounded_rectangle((1130, 0, 1918, 98), radius=12, fill=(121, 43, 110, 255))
    centered(draw, (1150, 14, 1898, 86), "유혹을 때려 갱생시켜라!", (255, 246, 255, 255), 31)

    draw.rounded_rectangle((1430, 95, 1820, 225), radius=15, fill=(5, 3, 8, 255))
    centered(draw, (1450, 112, 1800, 210), "조작 설명", (255, 255, 255, 255), 40)

    text_panel(draw, (55, 110, 1035, 365), "① 벌주기 방에서는", "소녀들의 나쁜 마음이 적이 되어 나타납니다.\n제한 시간 안에 쓰러뜨려 소녀들을 갱생시키세요!")
    text_panel(draw, (55, 385, 1035, 640), "② 적을 쓰러뜨리는 법", "마우스를 클릭하면 채찍을 휘두릅니다.\n채찍으로 적을 연속해서 때려 쓰러뜨리세요.")
    text_panel(draw, (700, 730, 1860, 1055), "③ 색이 다른 적", "적은 빨강과 파랑, 두 종류로 나타납니다.\n빨간 적은 왼쪽 클릭으로, 파란 적은\n오른쪽 클릭으로 쓰러뜨리세요.")

    png = OUT_DIR / "punish_tutorial_0_ko_mockup.png"
    image.save(png, optimize=True)

    review = image.copy()
    review.thumbnail((1280, 726), Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", review.size, (24, 24, 28, 255))
    bg.alpha_composite(review)
    jpg = OUT_DIR / "punish_tutorial_0_ko_review.jpg"
    bg.convert("RGB").save(jpg, quality=88, optimize=True)
    print(png)
    print(jpg)


if __name__ == "__main__":
    main()
