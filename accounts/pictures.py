"""Turning an uploaded photo into the small JPEG a profile shows.

Nothing a member uploads is ever served back as-is. Every upload is decoded
and drawn into a fresh image, which:

- strips EXIF, including the GPS location phones write into photos;
- means a file that only claims to be an image (an HTML or SVG page, say)
  never reaches another member's browser;
- keeps every picture small, square and the right way up.
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

SIZE = 256
QUALITY = 85

# Decoded size, checked before decoding. A tiny PNG can declare an enormous
# canvas (a "decompression bomb"), and Pillow would allocate all of it. 40
# megapixels is comfortably above any phone camera.
MAX_PIXELS = 40_000_000

ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def make_profile_jpeg(upload):
    """Return the JPEG bytes for an uploaded file, or raise ValidationError."""
    try:
        image = Image.open(upload)
        # Opening reads only the header, so the size is known before any
        # pixels are decoded.
        if image.format not in ACCEPTED_FORMATS:
            raise ValidationError("Use a JPEG, PNG, WebP or GIF image.")
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise ValidationError("That image is too large. Use one under 40 megapixels.")
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValidationError("That file isn't an image we can read. Use a JPEG or PNG.") from error

    # Phones store portrait photos sideways plus an EXIF note saying so;
    # applying the note here is what keeps faces upright once EXIF is gone.
    image = ImageOps.exif_transpose(image)

    # Transparent PNGs and GIFs get a white background rather than black.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")

    # Centre-crop to a square, then shrink.
    image = ImageOps.fit(image, (SIZE, SIZE), method=Image.Resampling.LANCZOS)

    out = BytesIO()
    image.save(out, format="JPEG", quality=QUALITY, optimize=True)
    return out.getvalue()
