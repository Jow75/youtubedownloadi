"""
Generate the Universal Media Downloader app icon.
=================================================
Draws a clean download glyph (arrow into a tray) on a violet->cyan rounded
square and writes a multi-resolution Windows icon + a PNG. No external image
needed — just PIL. Re-run after tweaking to regenerate:

    python make_icon.py
"""

import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
S = 1024  # master resolution

VIOLET = (124, 108, 255)
CYAN = (34, 211, 238)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build():
    os.makedirs(ASSETS, exist_ok=True)

    # 1) Diagonal violet -> cyan gradient.
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            px[x, y] = _lerp(VIOLET, CYAN, (x + y) / (2 * (S - 1)))

    # 2) Rounded-square mask -> app-icon silhouette.
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                           radius=int(S * 0.225), fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)

    # 3) Soft inner highlight (top-left) for a little depth.
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([int(-S * 0.25), int(-S * 0.35),
                                  int(S * 0.85), int(S * 0.55)],
                                 fill=(255, 255, 255, 46))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.06))
    icon = Image.alpha_composite(icon, Image.composite(
        glow, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

    # 4) White download glyph (drop shadow + shape).
    cx = S // 2
    stem = [cx - 66, int(S * 0.25), cx + 66, int(S * 0.54)]
    head = [(cx - 212, int(S * 0.47)), (cx + 212, int(S * 0.47)),
            (cx, int(S * 0.71))]
    tray = [cx - 232, int(S * 0.77), cx + 232, int(S * 0.86)]

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    ds.rounded_rectangle(stem, radius=66, fill=(0, 0, 0, 90))
    ds.polygon(head, fill=(0, 0, 0, 90))
    ds.rounded_rectangle(tray, radius=46, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    shadow = Image.composite(shadow, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask)
    icon = Image.alpha_composite(icon, ImageChops_offset(shadow, 0, 16))

    dd = ImageDraw.Draw(icon)
    white = (255, 255, 255, 255)
    dd.rounded_rectangle(stem, radius=66, fill=white)
    dd.polygon(head, fill=white)
    dd.rounded_rectangle(tray, radius=46, fill=white)

    # 5) Export PNG + multi-size ICO.
    png_path = os.path.join(ASSETS, "umd.png")
    ico_path = os.path.join(ASSETS, "umd.ico")
    icon.save(png_path)
    icon.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                               (64, 64), (128, 128), (256, 256)])
    print("wrote", png_path)
    print("wrote", ico_path)


def ImageChops_offset(img, dx, dy):
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy))
    return out


if __name__ == "__main__":
    build()
