"""Synthetic mixed-script test pages with an exact reference text.

Public scans with a correct text layer that mixes Cyrillic and Latin are hard to find (most
archive OCR is single-language), so these pages are rendered from known text instead,
typeset in PT Serif (a common Cyrillic book face) at 300 dpi. Two looks are produced:
- **scan** (render): a slight tilt, blur, paper tone, noise and JPEG compression.
- **phone photo** (photograph): the page lies curled and in perspective on a table, under
  uneven light with a shadow, at camera resolution with sensor noise.

The first line of each text file is set as a bold heading; every other line is a paragraph.
Receipts (layout "receipt") are set in a monospaced face instead, one printed row per line,
with tab-separated columns: the label on the left, then its values (see typeset_receipt).
Till receipts (layout "till") are narrow thermal-paper strips: faint, dotty print, the total
line in double height, crumpled and tilted on a table (see typeset_till and photograph_till).
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


def typeset_receipt(text, mono, size=30):
    """Clean greyscale receipt page: one row per line, columns separated by tabs. The label is
    left-aligned; a single value starts at a tab stop; a table row's values are right-aligned in
    evenly spaced columns over the right part of the page. Empty columns stay empty."""
    page = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(page)
    font = ImageFont.truetype(mono, size)
    right = W - MARGIN
    lead = int(size * 1.55)
    y = MARGIN
    for line in text.strip("\n").split("\n"):
        cols = line.split("\t")
        d.text((MARGIN, y), cols[0], font=font, fill=0)
        if len(cols) == 2:
            d.text((MARGIN + int(0.4 * (right - MARGIN)), y), cols[1], font=font, fill=0)
        elif len(cols) > 2:
            n = len(cols) - 1
            x0 = MARGIN + 0.42 * (right - MARGIN)
            for k, c in enumerate(cols[1:], 1):
                x1 = x0 + (right - x0) * k / n
                d.text((x1 - d.textlength(c, font=font), y), c, font=font, fill=0)
        y += lead
        if y > H - MARGIN:
            raise ValueError("text does not fit on the page")
    return page


TILL_W = 900   # 3 in at 300 dpi: 80 mm thermal paper


def typeset_till(text, mono, size=30):
    """Till receipt strip: one row per line; the label left, the last column right-aligned, a
    middle column (quantity x price) right-aligned before it. The total line (ОБЩА СУМА) is
    printed in double height and bold, as tills do."""
    lines = text.strip("\n").split("\n")
    font = ImageFont.truetype(mono, size)
    big = ImageFont.truetype(mono, int(size * 1.9))
    lead = int(size * 1.5)
    h = 120 + sum(2 * lead if l.startswith("ОБЩА СУМА") else lead for l in lines) + 120
    page = Image.new("L", (TILL_W, h), 255)
    d = ImageDraw.Draw(page)
    left, right, y = 40, TILL_W - 40, 120
    for line in lines:
        cols = line.split("\t")
        f = big if line.startswith("ОБЩА СУМА") else font
        if f is big:  # bold: the same text twice, a pixel apart
            for dx in (0, 2):
                d.text((left + dx, y), cols[0], font=f, fill=0)
                if len(cols) > 1:
                    d.text((right - d.textlength(cols[-1], font=f) + dx, y), cols[-1], font=f, fill=0)
            y += 2 * lead
            continue
        d.text((left, y), cols[0], font=f, fill=0)
        if len(cols) == 3:  # name, quantity x price, value: the middle one ends before the value
            d.text((right - d.textlength(cols[2], font=f) - 30 - d.textlength(cols[1], font=f), y),
                   cols[1], font=f, fill=0)
            d.text((right - d.textlength(cols[2], font=f), y), cols[2], font=f, fill=0)
        elif len(cols) == 2:
            d.text((right - d.textlength(cols[1], font=f), y), cols[1], font=f, fill=0)
        y += lead
    return page


def photograph_till(text, out, mono, _bold=None, seed=0, **_):
    """A till receipt as phones photograph them: thermal print (faint grey dots, fading to one
    side), crumpled, tilted by a few degrees, lying on a table under uneven light."""
    rng = np.random.default_rng(seed)
    page = np.asarray(typeset_till(text, mono)).astype(np.float32) / 255
    h, w = page.shape
    # thermal print: ink is grey, not black, made of dots, and fades towards the right
    ink = 1 - page
    dots = (rng.random((h, w)) > 0.18).astype(np.float32)
    fade = 0.55 + 0.25 * (1 - np.linspace(0, 1, w))[None, :]
    page = 1 - ink * dots * fade
    page = cv2.GaussianBlur(page, (0, 0), 0.8)
    # crumples: a smooth random displacement, and creases as faint shading
    def smooth(scale, amp):
        n = rng.normal(0, 1, (h // scale + 2, w // scale + 2)).astype(np.float32)
        return cv2.resize(n, (w, h), interpolation=cv2.INTER_CUBIC) * amp
    dx, dy = smooth(120, 6), smooth(120, 6)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    page = cv2.remap(page, xx + dx, yy + dy, cv2.INTER_LINEAR, borderValue=1.0)
    shade = 1 - 0.04 * np.abs(smooth(90, 1.0))
    paper = np.stack([page * 0.96, page * 0.94, page * 0.90], -1) * 255 * shade[..., None]
    # tilted, on a table
    CW, CH = w + 500, h + 400
    table = np.ones((CH, CW, 3), np.float32) * np.array([70, 62, 58], np.float32)
    table += rng.normal(0, 8, (CH, CW, 1)).astype(np.float32)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 2.5, 1.0)
    M[:, 2] += [250, 200]
    warped = cv2.warpAffine(paper, M, (CW, CH), flags=cv2.INTER_LINEAR, borderValue=0)
    mask = cv2.warpAffine(np.ones((h, w), np.float32), M, (CW, CH)) > 0.5
    img = np.where(mask[..., None], warped, table)
    gy, gx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    img = img * (1.05 - 0.3 * (gx / CW * 0.5 + gy / CH * 0.5))[..., None]
    img = cv2.GaussianBlur(img, (0, 0), 1.0) + rng.normal(0, 4, img.shape).astype(np.float32)
    img = cv2.resize(np.clip(img, 0, 255).astype(np.uint8), (CW * 2 // 3, CH * 2 // 3), interpolation=cv2.INTER_AREA)
    Image.fromarray(img).save(out, "JPEG", quality=85)
    return text


def _page(text, fonts, size, layout):
    regular, bold = fonts
    return typeset_receipt(text, regular) if layout == "receipt" else typeset(text, regular, bold, size)


def render(text, out, regular, bold, seed=0, size=40, layout="text"):
    """Typeset text and give it a scan look; JPEG at `out`. Returns the reference text."""
    rnd = random.Random(seed)
    page = _page(text, (regular, bold), size, layout)
    # scan look: tilt, soft focus, paper tone, noise, JPEG
    page = page.rotate(rnd.uniform(-0.6, 0.6), resample=Image.BICUBIC, fillcolor=255)
    page = page.filter(ImageFilter.GaussianBlur(0.9))
    a = np.asarray(page).astype(np.float32)
    a = 30 + a * (232 - 30) / 255                       # grey paper, dark grey ink
    a += np.random.default_rng(seed).normal(0, 7, a.shape)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(out, "JPEG", quality=80, dpi=(DPI, DPI))
    return text


def photograph(text, out, regular, bold, seed=0, size=40, layout="text"):
    """Typeset text and make it look like a phone photo of the page; JPEG at `out`."""
    rng = np.random.default_rng(seed)
    page = np.asarray(_page(text, (regular, bold), size, layout)).astype(np.float32) / 255
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
