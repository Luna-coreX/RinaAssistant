# -*- coding: utf-8 -*-
"""
Build the program's icon from the brand's logo.

    python tools/make_icon.py            write assets/brand/rina.ico
    python tools/make_icon.py --check    compare without rewriting

The source is `assets/brand/logo.webp`, the same file the product page's
icons are cut from (`tools/brand.py` in the site's repository), and the two
squares are the ones measured there: the sphere alone, and the sphere with
its ring and small moon.

- **16–48 px — the sphere alone.** That is the page's favicon, and at these
  sizes the ring is a smudge around the sphere.
- **64–256 px — with the ring.** The page's large icon; the ring reads, and
  cut off by the square it would look broken.

**The glow is faded out before the edge of the square.** Cut straight from
the logo, the sphere's glow reaches the corners, and on a light taskbar or
in Explorer a faint square shows round the icon. A round mask takes the
alpha to nothing a little inside the edge.

**Small sizes are bitmaps, large ones PNG.** Windows reads PNG inside an
icon for every size, but not everything that loads an icon is Windows'
own loader — the tray's `System.Drawing.Icon` among them — and a bitmap is
what every loader has read since the first icon file. 256 px as a bitmap
would be a quarter of a megabyte of nothing; PNG there is the norm.
"""
import io
import os
import struct
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "assets", "brand", "logo.webp")
TARGET = os.path.join(ROOT, "assets", "brand", "rina.ico")

#: Measured once from the logo's alpha (the site's `tools/brand.py`).
SPHERE = (128, 82, 624, 578)
EMBLEM = (76, 28, 676, 628)

#: The sizes Windows asks for: 100–200 % scaling of the small and large
#: icons, the taskbar's 24/40, and Explorer's 256.
SMALL = (16, 20, 24, 32, 40, 48)
LARGE = (64, 96, 128, 256)


def masked(image, inner, outer):
    """
    The image with its alpha faded to nothing between two radii.

    The radii are fractions of the side: full alpha inside `inner`, none
    beyond `outer`, a straight fade between.
    """
    side = image.width
    centre = (side - 1) / 2
    mask = Image.new("L", (side, side), 0)
    pixels = mask.load()
    for y in range(side):
        for x in range(side):
            r = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5 / side
            if r <= inner:
                pixels[x, y] = 255
            elif r < outer:
                pixels[x, y] = round(255 * (outer - r) / (outer - inner))
    out = image.copy()
    out.putalpha(ImageChops.multiply(image.split()[3], mask))
    return out


def bitmap_entry(image):
    """An icon frame as a 32-bit DIB: header, BGRA bottom-up, AND mask."""
    side = image.width
    header = struct.pack("<IiiHHIIiiII", 40, side, side * 2, 1, 32, 0,
                         0, 0, 0, 0, 0)
    rows = []
    for y in reversed(range(side)):
        row = image.crop((0, y, side, y + 1)).tobytes("raw", "BGRA")
        rows.append(row)
    # The AND mask is all zeroes: the alpha already says what is seen.
    stride = ((side + 31) // 32) * 4
    return header + b"".join(rows) + bytes(stride * side)


def png_entry(image):
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def build():
    logo = Image.open(SOURCE).convert("RGBA")
    sphere = masked(logo.crop(SPHERE), 0.44, 0.50)
    emblem = masked(logo.crop(EMBLEM), 0.47, 0.50)

    frames = []
    for side in SMALL:
        frames.append((side, bitmap_entry(sphere.resize((side, side), Image.LANCZOS))))
    for side in LARGE:
        frames.append((side, png_entry(emblem.resize((side, side), Image.LANCZOS))))

    head = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(head) + 16 * len(frames)
    entries, blobs = [], []
    for side, blob in frames:
        entries.append(struct.pack("<BBBBHHII", side % 256, side % 256, 0, 0,
                                   1, 32, len(blob), offset))
        blobs.append(blob)
        offset += len(blob)
    return head + b"".join(entries) + b"".join(blobs)


def main(argv):
    built = build()
    if "--check" in argv:
        same = os.path.isfile(TARGET) and open(TARGET, "rb").read() == built
        print("значок совпадает с исходником" if same
              else "значок разошёлся с исходником: python tools/make_icon.py")
        return 0 if same else 1
    with open(TARGET, "wb") as handle:
        handle.write(built)
    print(f"записан: {os.path.relpath(TARGET, ROOT)} "
          f"({len(built) // 1024} КБ, {len(SMALL) + len(LARGE)} размеров)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
