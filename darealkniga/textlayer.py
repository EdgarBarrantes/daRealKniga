"""OCR results -> page word lists (ocr.json) and plain-text export.

Page record: {"page": n, "W": width_px, "H": height_px, "lines": [[{"t": text, "box": [x0,y0,x1,y1]}]]}
with boxes in the page image's pixel space (top-left origin).
"""
import json
import os
import re

from . import fuse


def paddle_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_page(n, W, H, tsv, scale, langs, paddle=None):
    tl = fuse.read_tess(tsv, scale)
    if paddle is not None:
        lines = fuse.fuse_page(tl, fuse.paddle_words(paddle_json(paddle), scale))
    else:
        lines = fuse.tess_only_page(tl, normalize=langs.cyrillic)
    return {"page": n, "W": W, "H": H, "lines": lines}


def write_text(pages, path):
    """UTF-8 text, one form feed per page; words hyphenated across line ends are re-joined."""
    with open(path, "w", encoding="utf-8") as f:
        for i, p in enumerate(pages):
            if i:
                f.write("\f")
            lines = [" ".join(w["t"] for w in l) for l in p["lines"]]
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
