"""Generate placeholder PWA icons.

These are stand-ins until the club has a real crest; replace the PNGs in
static/icons/ and this script becomes unnecessary. The development set in
static/icons/dev/ is amber and marked DEV, so an installed dev build is never
mistaken for production on a home screen; keep it distinct when the crest
arrives. Run with: python3 tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ICON_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"
PITCH = (11, 107, 58, 255)
AMBER = (180, 83, 9, 255)
WHITE = (255, 255, 255, 255)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def draw_icon(size, *, maskable, background=PITCH, label=None):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if maskable:
        # Maskable icons are cropped to whatever shape the launcher prefers, so
        # the background must bleed to the edges and the mark must stay inside
        # the centre 80% safe zone.
        draw.rectangle([0, 0, size, size], fill=background)
        text_size = int(size * 0.34)
    else:
        radius = int(size * 0.22)
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=background)
        text_size = int(size * 0.44)

    lines = [("FC", text_size)]
    if label:
        # Shrink FC to make room, and stack the label under it as one centred block.
        lines = [("FC", int(text_size * 0.8)), (label, int(text_size * 0.4))]
    gap = int(size * 0.04)

    fonts = [ImageFont.truetype(FONT_PATH, line_size) for _, line_size in lines]
    boxes = [draw.textbbox((0, 0), text, font=font) for (text, _), font in zip(lines, fonts)]
    block_height = sum(bottom - top for _, top, _, bottom in boxes) + gap * (len(lines) - 1)

    y = (size - block_height) / 2
    for (text, _), font, (left, top, right, bottom) in zip(lines, fonts, boxes):
        draw.text(((size - (right - left)) / 2 - left, y - top), text, font=font, fill=WHITE)
        y += bottom - top + gap
    return image


def write_set(directory, **style):
    directory.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        draw_icon(size, maskable=False, **style).save(directory / f"icon_{size}.png")
    draw_icon(512, maskable=True, **style).save(directory / "icon_maskable_512.png")


def main():
    write_set(ICON_DIR)
    write_set(ICON_DIR / "dev", background=AMBER, label="DEV")
    print(f"wrote 8 icons to {ICON_DIR} and {ICON_DIR / 'dev'}")


if __name__ == "__main__":
    main()
