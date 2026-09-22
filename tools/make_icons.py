"""Generate placeholder PWA icons.

These are stand-ins until the club has a real crest; replace the PNGs in
static/icons/ and this script becomes unnecessary. Run with: python3
tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ICON_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"
PITCH = (11, 107, 58, 255)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def draw_icon(size, *, maskable):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if maskable:
        # Maskable icons are cropped to whatever shape the launcher prefers, so
        # the background must bleed to the edges and the mark must stay inside
        # the centre 80% safe zone.
        draw.rectangle([0, 0, size, size], fill=PITCH)
        text_size = int(size * 0.34)
    else:
        radius = int(size * 0.22)
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=PITCH)
        text_size = int(size * 0.44)

    font = ImageFont.truetype(FONT_PATH, text_size)
    left, top, right, bottom = draw.textbbox((0, 0), "FC", font=font)
    draw.text(
        ((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
        "FC",
        font=font,
        fill=(255, 255, 255, 255),
    )
    return image


def main():
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        draw_icon(size, maskable=False).save(ICON_DIR / f"icon_{size}.png")
    draw_icon(512, maskable=True).save(ICON_DIR / "icon_maskable_512.png")
    print(f"wrote 4 icons to {ICON_DIR}")


if __name__ == "__main__":
    main()
