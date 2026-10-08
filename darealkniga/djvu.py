"""DjVu input/output via DjVuLibre (ddjvu, djvused, djvudump)."""
import os
import re
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image

from .pdf import jpeg, g4

Image.MAX_IMAGE_PIXELS = None
BG_W = 860   # background layer width in pixels (~100 dpi, like DjVu's own background)
FG_W = 650   # foreground (ink colour) layer width


def check_tools():
    missing = [t for t in ("ddjvu", "djvused", "djvudump") if not shutil.which(t)]
    if missing:
        raise SystemExit(f"DjVuLibre tools missing ({', '.join(missing)}): install djvulibre-bin / djvulibre.")


def page_info(book):
    """-> [(W, H, dpi)] per page, in page order."""
    out = subprocess.run(["djvudump", book], capture_output=True, text=True, check=True).stdout
    pages = []
    for m in re.finditer(r"INFO \[\d+\]\s+DjVu (\d+)x(\d+), v\d+, (\d+) dpi", out):
        pages.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    n = int(subprocess.run(["djvused", "-e", "n", book], capture_output=True, text=True, check=True).stdout)
    if len(pages) != n:  # indirect documents: ask djvused per page
        pages = []
        for i in range(1, n + 1):
            s = subprocess.run(["djvused", "-e", f"select {i}; size", book], capture_output=True, text=True).stdout
            w, h = (int(x) for x in re.findall(r"\d+", s)[:2])
            pages.append((w, h, 300))
    return pages


def ddjvu(book, page, mode, fmt, sub=None, size=None, out=None):
    with tempfile.NamedTemporaryFile(suffix="." + fmt) as f:
        cmd = ["ddjvu", f"-format={fmt}", f"-mode={mode}", f"-page={page}"]
        if sub:
            cmd.append(f"-subsample={sub}")
        if size:
            cmd.append(f"-size={size[0]}x{size[1]}")
        subprocess.run(cmd + [book, out or f.name], check=True, capture_output=True)
        if out:
            return None
        im = Image.open(f.name)
        im.load()
        return im


def render_gray(job):
    """(book, page, w, h, out_path): page as greyscale PGM for OCR."""
    book, n, w, h, out = job
    tmp = out + ".part.pgm"
    subprocess.run(["ddjvu", "-format=pgm", f"-page={n}", f"-size={w}x{h}", book, tmp], check=True,
                   capture_output=True)
    os.replace(tmp, out)


def mrc_layers(job):
    """(book, page, W, H) -> PDF layers rebuilding the DjVu page: low-res background JPEG, plus the
    full-res 1-bit text mask carrying a low-res ink-colour JPEG (as SMask)."""
    book, n, W, H = job
    layers = []
    bg = ddjvu(book, n, "background", "ppm", max(1, round(W / BG_W)))
    layers.append(jpeg(bg, 45))
    try:
        mask = ddjvu(book, n, "mask", "pbm").convert("1")  # True = paper
    except subprocess.CalledProcessError:
        mask = None  # page without a bilevel layer
    if mask is not None and mask.size == (W, H):
        ink = ~np.asarray(mask)
        if ink.any():
            fg = np.asarray(ddjvu(book, n, "foreground", "ppm").convert("RGB")).astype(np.float64)
            f = max(1, round(W / FG_W))
            h, w = H // f, W // f
            k = ink[:h * f, :w * f].reshape(h, f, w, f)
            cnt = k.sum(axis=(1, 3))
            s = (fg[:h * f, :w * f] * ink[:h * f, :w * f, None]).reshape(h, f, w, f, 3).sum(axis=(1, 3))
            med = np.median(fg[ink], axis=0)
            tone = np.where(cnt[..., None] > 0, s / np.maximum(cnt, 1)[..., None], med)
            spec = jpeg(Image.fromarray(tone.clip(0, 255).astype(np.uint8)), 60)
            spec["smask"] = g4(mask)
            layers.append(spec)
    return layers


def _q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write(book, out, pages, dpis):
    """Copy book to out with a hidden text layer (page/line/word) and per-page dpi.
    pages: OCR page records in original page pixels; dpis: {page: dpi}."""
    script = []
    for n, d in sorted(dpis.items()):
        script.append(f"select {n}\nset-dpi {d}\n")
    for p in pages:
        W, H = p["W"], p["H"]
        lines = []
        for line in p["lines"]:
            ws = []
            for w in line:
                x0, y0, x1, y1 = w["box"]
                x0, x1 = max(0, min(x0, W)), max(0, min(x1, W))
                y0, y1 = max(0, min(y0, H)), max(0, min(y1, H))
                ws.append((x0, H - y1, x1, H - y0, w["t"]))
            lx0, ly0 = min(w[0] for w in ws), min(w[1] for w in ws)
            lx1, ly1 = max(w[2] for w in ws), max(w[3] for w in ws)
            words = " ".join(f"(word {a} {b} {c} {d} {_q(t)})" for a, b, c, d, t in ws)
            lines.append(f" (line {lx0} {ly0} {lx1} {ly1} {words})")
        script.append(f"select {p['page']}\nset-txt\n(page 0 0 {W} {H}\n" + "\n".join(lines) + ")\n.\n")
    tmp = out + ".part"
    sf = out + ".dsed"
    with open(sf, "w", encoding="utf-8") as f:
        f.write("".join(script))
    shutil.copyfile(book, tmp)
    try:
        subprocess.run(["djvused", "-f", sf, "-s", tmp], check=True)
        os.replace(tmp, out)
    finally:
        for p in (sf, tmp):
            if os.path.exists(p):
                os.remove(p)
