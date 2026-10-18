"""OCR results -> page word lists (ocr.json) and plain-text export.

Page record: {"page": n, "W": width_px, "H": height_px, "lines": [[{"t": text, "box": [x0,y0,x1,y1]}]]}
with boxes in the page image's pixel space (top-left origin).
"""
import json
import os
import re

from . import fuse, receipt


def paddle_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_page(n, W, H, tsv, scale, langs, paddle=None):
    if tsv is None:  # PaddleOCR only (receipt profile)
        return {"page": n, "W": W, "H": H, "lines": fuse.paddle_page(paddle_json(paddle), scale),
                "profile": "receipt"}
    tl = fuse.read_tess(tsv, scale)
    if paddle is not None:
        lines = fuse.fuse_page(tl, fuse.paddle_words(paddle_json(paddle), scale))
    else:
        lines = fuse.tess_only_page(tl, normalize=langs.cyrillic)
    return {"page": n, "W": W, "H": H, "lines": lines}


def rows(lines):
    """Words regrouped into printed rows, left to right, top to bottom. For receipts, forms and
    tables, where Tesseract reads a column of labels and a column of values as separate blocks.
    Photos are rarely level, so rows follow the line pieces: left to right, each piece joins the
    row whose last word, to its left, continues at the height of the piece's first word (within
    half a word height), following the page's tilt as measured on the pieces themselves."""
    def mid(w):
        return (w["box"][1] + w["box"][3]) / 2

    def cx(w):
        return (w["box"][0] + w["box"][2]) / 2

    def height(w):
        return w["box"][3] - w["box"][1]

    pieces = sorted((sorted(l, key=lambda w: w["box"][0]) for l in lines if l), key=lambda p: p[0]["box"][0])
    slopes = sorted((mid(p[-1]) - mid(p[0])) / (cx(p[-1]) - cx(p[0])) for p in pieces
                    if len(p) >= 2 and cx(p[-1]) - cx(p[0]) > 2 * height(p[0]))
    tilt = slopes[len(slopes) // 2] if slopes else 0.0
    out = []
    for p in pieces:
        first = p[0]
        best, miss = None, None
        for row in out:
            last = row[-1]
            if first["box"][0] - last["box"][2] < -0.5 * height(first):
                continue
            d = abs(mid(first) - mid(last) - tilt * (cx(first) - cx(last)))
            if d < 0.5 * min(height(first), height(last)) and (miss is None or d < miss):
                best, miss = row, d
        if best is None:
            out.append(list(p))
        else:
            best.extend(p)
    return sorted(out, key=lambda r: mid(r[0]))


_rows = rows  # write_text's argument of the same name hides it


def write_text(pages, path, rows=False):
    """UTF-8 text, one form feed per page; words hyphenated across line ends are re-joined.
    rows: one line per printed row (see rows()) instead of Tesseract's reading order."""
    with open(path, "w", encoding="utf-8") as f:
        for i, p in enumerate(pages):
            if i:
                f.write("\f")
            groups = _rows(p["lines"]) if rows else p["lines"]
            if rows and p.get("profile") == "receipt":
                groups = [receipt.fix_row(r) for r in groups]
            lines = [" ".join(w["t"] for w in l) for l in groups]
            out = []
            for l in lines:
                if out and re.search(r"\w-$", out[-1]) and l[:1].islower():
                    head, _, rest = l.partition(" ")
                    out[-1] = out[-1][:-1] + head
                    if rest:
                        out.append(rest)
                else:
                    out.append(l)
            f.write("\n".join(out) + "\n")


def word_count(pages):
    return sum(len(l) for p in pages for l in p["lines"])

