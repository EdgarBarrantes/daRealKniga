"""Clean-up of photographed / scanned page images.

enhance():   flattened page photo -> fixed-size page image (grey, or colour for covers) and a
             soft mask of photo regions. Lighting is evened out by dividing by an estimate of the
             paper brightness, paper becomes white (hides bleed-through), ink gets deeper.
binarize():  grey page -> 1-bit ink mask at 2x resolution (Sauvola), for crisp text in the PDF.
"""
import cv2
import numpy as np


def background(ch):
    """Smooth paper-brightness estimate; dark regions larger than text (photos) are filled in
    from the surrounding paper so they don't get washed out. Also returns a soft photo mask."""
    h, w = ch.shape
    s = cv2.resize(ch, (w // 8, h // 8), interpolation=cv2.INTER_AREA)
    dil = cv2.dilate(s, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11)))
    ref = np.percentile(dil, 90)
    hole = (dil < 0.82 * ref).astype(np.uint8)
    hole = cv2.dilate(hole, np.ones((7, 7), np.uint8))
    filled = cv2.inpaint(np.clip(dil, 0, 255).astype(np.uint8), hole, 15, cv2.INPAINT_TELEA).astype(np.float32)
    filled = cv2.GaussianBlur(filled, (0, 0), 4)
    # photos: large dark regions (not text lines), feathered
    mean = cv2.blur(s, (15, 15))
    photo = (mean < 0.6 * ref).astype(np.uint8)
    photo = cv2.morphologyEx(photo, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    photo = cv2.morphologyEx(photo, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    photo = cv2.GaussianBlur(cv2.dilate(photo, np.ones((5, 5), np.uint8)).astype(np.float32), (0, 0), 2)
    return (cv2.resize(filled, (w, h), interpolation=cv2.INTER_CUBIC),
            np.clip(cv2.resize(photo, (w, h), interpolation=cv2.INTER_LINEAR), 0, 1))


def is_flat_scan(img):
    """True when paper reaches all four image edges (a cropped flat scan) rather than the page
    being surrounded by background or shadows (a photo). Such pages skip unwarping and edge trimming."""
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    h, w = g.shape
    s = cv2.resize(g, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA).astype(np.float32)
    h, w = s.shape
    paper = np.percentile(s[h // 4:3 * h // 4, w // 4:3 * w // 4], 90)
    b = max(2, int(0.03 * min(h, w)))
    strips = (s[:b], s[-b:], s[:, :b], s[:, -b:])
    return min(float((st > 0.75 * paper).mean()) for st in strips) >= 0.97


def is_colorful(img):
    small = cv2.resize(img, (img.shape[1] // 8, img.shape[0] // 8), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    return ((hsv[..., 1] > 115) & (hsv[..., 2] > 60)).mean() > 0.05


def sharpen(x, amount=0.5, sigma=1.2):
    return cv2.addWeighted(x, 1 + amount, cv2.GaussianBlur(x, (0, 0), sigma), -amount, 0)


def fit(a, size, trim=0.012):
    """Trim leftover page-edge shadows, then resize to the output page size (w, h)."""
    h, w = a.shape[:2]
    m = int(trim * w)
    a = a[m:h - m, m:w - m]
    interp = cv2.INTER_AREA if a.shape[0] > size[1] else cv2.INTER_CUBIC
    return cv2.resize(a, size, interpolation=interp)


def enhance(img, size, color="auto", trim=0.012):
    """img: RGB uint8. Returns (page, photo_mask or None, is_color). trim: share of each edge
    to cut off (leftover page-edge shadows in photos; use 0 for cropped scans)."""
    if color == "always" or (color == "auto" and is_colorful(img)):
        # cover-like page: white balance + gentle contrast only
        f = img.astype(np.float32)
        white = np.percentile(f.reshape(-1, 3), 99, axis=0)
        black = np.percentile(f.reshape(-1, 3), 0.5, axis=0)
        f = np.clip((f - black) / np.maximum(white - black, 1), 0, 1)
        return fit(sharpen((f * 255).astype(np.uint8), 0.4), size, trim), None, True
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    bg, photo = background(gray)
    norm = np.clip(gray / np.maximum(bg, 1), 0, 1.2)
    # text/paper: paper (>= 0.88) -> white, deepen ink
    text = np.clip((norm - 0.12) / 0.76, 0, 1) ** 1.15
    text = sharpen((text * 255).astype(np.uint8)).astype(np.float32) / 255
    # photos: gentle curve, no sharpening, soften the halftone screen
    pic = np.clip((norm - 0.03) / 0.9, 0, 1) ** 1.05
    pic = cv2.GaussianBlur(pic, (0, 0), 1.3)
    out = text * (1 - photo) + pic * photo
    page = fit((np.clip(out, 0, 1) * 255).astype(np.uint8), size, trim)
    mask = fit((photo * 255).astype(np.uint8), size, trim)
    return page, mask, False


def sauvola(g, win=81, k=0.25, r=128.0, min_area=40):
    """Adaptive binarisation: keeps faint/blurred strokes that a global threshold drops."""
    g = g.astype(np.float32)
    m = cv2.boxFilter(g, -1, (win, win))
    sd = np.sqrt(np.maximum(cv2.boxFilter(g * g, -1, (win, win)) - m * m, 0))
    t = m * (1 + k * (sd / r - 1))
    ink = ((g < np.minimum(t, 200)) | (g < 120)).astype(np.uint8)
    # drop specks much smaller than a full stop (paper texture, bleed-through)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    return keep[lab]


def rect_mask(m, min_area=4000, pad=12):
    """Photos and ornaments are rectangular: replace each region by its padded bounding box."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    out = np.zeros_like(m, dtype=bool)
    for x, y, w, h, area in stats[1:]:
        if area >= min_area:
            out[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad] = True
    return out


def binarize(gray, exclude=None):
    """Ink mask at 2x resolution (smooth glyph edges), optionally excluding photo regions."""
    H, W = gray.shape
    big = cv2.resize(gray, (2 * W, 2 * H), interpolation=cv2.INTER_CUBIC)
    ink = sauvola(big)
    if exclude is not None and exclude.any():
        ink &= ~cv2.resize(exclude.astype(np.uint8), (2 * W, 2 * H), interpolation=cv2.INTER_NEAREST).astype(bool)
    return ink
