"""Synthetic mixed-script test pages with an exact reference text.

Public scans with a correct text layer that mixes Cyrillic and Latin are hard to find (most
archive OCR is single-language), so these pages are rendered from known text instead,
typeset in PT Serif (a common Cyrillic book face) at 300 dpi. Two looks are produced:
- **scan** (render): a slight tilt, blur, paper tone, noise and JPEG compression.
- **phone photo** (photograph): the page lies curled and in perspective on a table, under
  uneven light with a shadow, at camera resolution with sensor noise.

The first line of each text file is set as a bold heading; every other line is a paragraph.
"""
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, DPI = 1650, 2400, 300   # 5.5 x 8 in
MARGIN = 150


def _wrap(draw, words, font, width):
    lines, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and draw.textlength(trial, font=font) > width:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def typeset(text, regular, bold, size=40):
    """Clean greyscale page (PIL, white paper, black ink)."""
    page = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(page)
    body = ImageFont.truetype(regular, size)
    head = ImageFont.truetype(bold, int(size * 1.25))
    width = W - 2 * MARGIN
    y = MARGIN
    lines = [l for l in text.strip().split("\n") if l.strip()]
    for i, para in enumerate(lines):
        font = head if i == 0 else body
        lead = int(font.size * 1.45)
        rows = _wrap(d, para.split(), font, width)
        for j, row in enumerate(rows):
            x = MARGIN + (int(size * 1.2) if i > 0 and j == 0 else 0)  # paragraph indent
            last = j == len(rows) - 1
            if last or i == 0:
                d.text((x, y), " ".join(row), font=font, fill=0)
            else:  # justified
                ws = [d.textlength(w, font=font) for w in row]
                gap = (MARGIN + width - x - sum(ws)) / max(1, len(row) - 1)
                for w, wl in zip(row, ws):
                    d.text((x, y), w, font=font, fill=0)
                    x += wl + gap
            y += lead
        y += int(size * (0.9 if i == 0 else 0.35))
        if y > H - MARGIN:
            raise ValueError("text does not fit on the page")
    return page


def render(text, out, regular, bold, seed=0, size=40):
    """Typeset text and give it a scan look; JPEG at `out`. Returns the reference text."""
    rnd = random.Random(seed)
    page = typeset(text, regular, bold, size)
    # scan look: tilt, soft focus, paper tone, noise, JPEG
    page = page.rotate(rnd.uniform(-0.6, 0.6), resample=Image.BICUBIC, fillcolor=255)
    page = page.filter(ImageFilter.GaussianBlur(0.9))
    a = np.asarray(page).astype(np.float32)
    a = 30 + a * (232 - 30) / 255                       # grey paper, dark grey ink
    a += np.random.default_rng(seed).normal(0, 7, a.shape)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(out, "JPEG", quality=80, dpi=(DPI, DPI))
    return text


def photograph(text, out, regular, bold, seed=0, size=40):
    """Typeset text and make it look like a phone photo of the page; JPEG at `out`."""
    rng = np.random.default_rng(seed)
    page = np.asarray(typeset(text, regular, bold, size)).astype(np.float32) / 255
    h, w = page.shape
    # the page bulges: lines curve near the top and bottom, more towards the spine (left)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bend = 40 * np.sin(np.pi * xx / w) * (1.2 - xx / w)
    map_y = yy - bend * (yy / h - 0.5) * 2
    map_x = xx + 10 * np.sin(np.pi * yy / h)
    page = cv2.remap(page, map_x, map_y, cv2.INTER_LINEAR, borderValue=1.0)
    paper = np.stack([page * 0.93 + 0.0, page * 0.90 + 0.0, page * 0.82 + 0.0], -1) * 255
    paper = np.where(page[..., None] > 0.5, paper, page[..., None] * 255 + 25)   # ink stays dark
    # on a table, in perspective
    CW, CH = 2200, 2900
    table = np.ones((CH, CW, 3), np.float32) * np.array([92, 70, 52], np.float32)
    table += rng.normal(0, 10, (CH, CW, 1)).astype(np.float32)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[300, 260], [1930, 330], [1990, 2660], [230, 2600]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(paper, M, (CW, CH), flags=cv2.INTER_LINEAR, borderValue=0)
    mask = cv2.warpPerspective(np.ones((h, w), np.float32), M, (CW, CH)) > 0.5
    img = np.where(mask[..., None], warped, table)
    # uneven light: brighter top-left, a soft shadow from the bottom-right
    gy, gx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    light = 1.1 - 0.5 * (gx / CW * 0.4 + gy / CH * 0.6)
    shadow = 1 - 0.4 * np.exp(-(((gx - CW * 0.95) / (CW * 0.3)) ** 2 + ((gy - CH * 0.9) / (CH * 0.25)) ** 2))
    img = img * (light * shadow)[..., None]
    # camera: slight defocus, sensor noise, JPEG
    img = cv2.GaussianBlur(img, (0, 0), 1.2)
    img = img + rng.normal(0, 5, img.shape).astype(np.float32)
    img = cv2.resize(np.clip(img, 0, 255).astype(np.uint8), (1500, 1977), interpolation=cv2.INTER_AREA)   # page ~210 dpi
    Image.fromarray(img).save(out, "JPEG", quality=85)
    return text
