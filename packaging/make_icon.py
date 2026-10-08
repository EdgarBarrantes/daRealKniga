"""Draws the darealkniga icon (open book with text lines and a magnifier) -> darealkniga/data/icon.png"""
import os
from PIL import Image, ImageDraw, ImageFilter

S = 1024  # drawn large, downsampled for smooth edges


def main(out):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # rounded tile with a vertical gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    top, bot = (38, 70, 140), (20, 38, 84)
    for y in range(S):
        t = y / S
        gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=200, fill=255)
    im.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(im)
    # open book: two pages
    paper, ink = (250, 247, 238, 255), (60, 78, 120, 255)
    left = [(170, 300), (500, 340), (500, 800), (170, 760)]
    right = [(524, 340), (854, 300), (854, 760), (524, 800)]
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.polygon([(x + 10, y + 18) for x, y in left], fill=(0, 0, 0, 110))
    sd.polygon([(x + 10, y + 18) for x, y in right], fill=(0, 0, 0, 110))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    d.polygon(left, fill=paper)
    d.polygon(right, fill=paper)
    d.line([(512, 335), (512, 805)], fill=(200, 196, 185, 255), width=10)
    # text lines (Cyrillic-ish rhythm: uneven word lengths)
    for i in range(7):
        y = 395 + i * 52
        tilt = lambda x: y + (x - 170) * 40 / 330 * -1 + 40
        x = 210
        for w in ([70, 110, 55, 50], [120, 60, 95], [50, 90, 130], [100, 45, 80, 30],
                  [65, 130, 60], [90, 70, 100], [140, 80])[i]:
            if x + w > 470:
                break
            d.line([(x, tilt(x)), (x + w, tilt(x + w))], fill=ink, width=16)
            x += w + 22
    for i in range(4):
        y = 395 + i * 52
        tilt = lambda x: y + (x - 524) * 40 / 330
        d.line([(565, tilt(565)), (800 - i * 45, tilt(800 - i * 45))], fill=ink, width=16)
    # magnifier over the right page (search)
    cx, cy, r = 690, 650, 120
    d.ellipse([cx - r - 18, cy - r - 18, cx + r + 18, cy + r + 18], fill=(255, 196, 61, 255))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 251, 240, 255))
    d.line([(cx - 60, cy - 20), (cx + 60, cy - 20)], fill=ink, width=18)
    d.line([(cx - 60, cy + 30), (cx + 25, cy + 30)], fill=ink, width=18)
    d.line([(cx + 98, cy + 98), (cx + 210, cy + 210)], fill=(255, 196, 61, 255), width=56)
    d.ellipse([cx + 182, cy + 182, cx + 238, cy + 238], fill=(255, 196, 61, 255))
    im.resize((256, 256), Image.LANCZOS).save(out)


if __name__ == "__main__":
    main(os.path.join(os.path.dirname(__file__), "..", "darealkniga", "data", "icon.png"))
