"""Makes docs/demo.gif: a phone photo goes in, a clean searchable PDF comes out, compared with plain OCR.

Everything shown is real: the window is recorded while it processes the benchmark's phone-photo
sample (tests/samples/photo_bg.txt), the search runs on the PDF it writes, and the comparison
uses plain Tesseract's actual output on the same photo.

    python packaging/make_demo.py            # needs the [gui,test] extras, and Tesseract or Docker
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DAREALKNIGA_UI_LANG"] = "en"

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = os.path.join(ROOT, "docs", "demo.gif")
W, H = 960, 760          # canvas
BAR = 84                 # caption bar height
INK, MUTED, BRAND = (31, 35, 40), (87, 96, 106), (43, 79, 151)
BAD_BG, BAD_INK = (255, 220, 218), (176, 32, 32)


def font(size, bold=False):
    names = (["OpenSans-Semibold.ttf", "OpenSans-SemiBold.ttf", "DejaVuSans-Bold.ttf"] if bold else
             ["OpenSans-Regular.ttf", "DejaVuSans.ttf"])
    for d in ("/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.local/share/fonts"),
              "/Library/Fonts", "C:\\Windows\\Fonts"):
        for root, _, files in os.walk(d):
            for n in names:
                if n in files:
                    return ImageFont.truetype(os.path.join(root, n), size)
    import accuracy
    return ImageFont.truetype(accuracy.fetch("PT_Serif-Bold.ttf" if bold else "PT_Serif-Regular.ttf"), size)


def canvas(step, title, sub=""):
    im = Image.new("RGB", (W, H), (246, 248, 250))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, BAR], fill=BRAND)
    d.ellipse([24, 20, 68, 64], fill=(255, 255, 255))
    d.text((46, 42), str(step), font=font(26, True), fill=BRAND, anchor="mm")
    d.text((86, 18 if sub else 42), title, font=font(27, True), fill=(255, 255, 255),
           anchor="la" if sub else "lm")
    if sub:
        d.text((86, 54), sub, font=font(17), fill=(214, 224, 245))
    return im


def fit(img, box_w, box_h):
    s = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def paste_center(im, img, top=BAR + 16, shadow=True):
    x, y = (W - img.width) // 2, top + (H - top - 16 - img.height) // 2
    if shadow:
        ImageDraw.Draw(im).rounded_rectangle([x - 1, y - 1, x + img.width, y + img.height], 4, outline=(208, 215, 222))
    im.paste(img, (x, y))
    return x, y


# ---------------------------------------------------------------- inputs

def prepare(work):
    """The benchmark's phone photo and plain Tesseract's reading of it."""
    import accuracy
    from darealkniga import fuse, langs, ocr
    sample = next(s for s in accuracy.SAMPLES if s.name == "photo-bg")
    for f in ("PT_Serif-Regular.ttf", "PT_Serif-Bold.ttf"):
        accuracy.fetch(f)
    photo = os.path.join(work, "plovdiv-photo.jpg")
    os.replace(accuracy.cut(sample, work), photo)
    lg = langs.parse(sample.lang)
    base = os.path.join(work, "plain")
    ocr.run_tesseract([(photo, base, 300)], lg.tess, work, ocr.tessdata_dir(), os.cpu_count() or 4)
    plain = "\n".join(" ".join(w["t"] for w in line) for line in fuse.read_tess(base + ".tsv", 1.0))
    return photo, plain, accuracy.reference(sample), sample.lang


def record(photo, lang, outdir):
    """Drives the real window on the photo; returns (frames, output pdf, output text)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from darealkniga import gui
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(gui.STYLE)
    shots = []

    def grab(w):
        q = w.grab().toImage()
        b = q.constBits()
        img = Image.frombuffer("RGBA", (q.width(), q.height()), bytes(b), "raw", "BGRA", 0, 1)
        return img.convert("RGB")

    empty = gui.Window()
    empty.show()
    app.processEvents()
    shots.append(("empty", grab(empty)))
    empty.close()
    w = gui.Window(photo)
    w.lang.setCurrentIndex(w.lang.findData(lang))
    w.outdir.setText(outdir)
    w.show()
    app.processEvents()
    shots.append(("loaded", grab(w)))
    w.start()

    def tick():
        app.processEvents()
        shots.append((w.stage.text(), grab(w)))
        if w.runner is None:
            app.quit()
    t = QTimer()
    t.timeout.connect(tick)
    t.start(250)
    app.exec()
    t.stop()
    app.processEvents()
    shots.append(("done", grab(w)))
    pdf = next(o for o in w.outputs if o.endswith(".pdf"))
    txt = next(o for o in w.outputs if o.endswith(".txt"))
    import shiboken6
    for x in (empty, w):
        shiboken6.delete(x)
    return shots, pdf, open(txt, encoding="utf-8").read()


# ---------------------------------------------------------------- scenes

def scene_photo(photo):
    im = canvas(1, "A phone photo of a page", "Curled, shadowed, Bulgarian with English mixed in")
    paste_center(im, fit(Image.open(photo).convert("RGB"), W - 80, H - BAR - 40))
    return [(im, 2300)]


def scene_window(shots, photo):
    frames = []
    empty = dict(shots)["empty"]
    win_w, win_h = empty.size
    # drag the photo onto the window
    thumb = fit(Image.open(photo).convert("RGB"), 110, 145)
    for i in range(8):
        im = canvas(2, "Drop it into daRealKniga", "Or choose a file, a PDF, a DjVu book or a folder of photos")
        x, y = paste_center(im, fit(empty, W - 80, H - BAR - 32))
        k = i / 7
        tx = int((W - 150) * (1 - k) + (x + 260) * k)
        ty = int((H - 200) * (1 - k) + (y + 150) * k)
        ImageDraw.Draw(im).rectangle([tx - 3, ty - 3, tx + thumb.width + 2, ty + thumb.height + 2], fill=(255, 255, 255),
                                     outline=(140, 150, 160))
        im.paste(thumb, (tx, ty))
        frames.append((im, 900 if i == 0 else 90))
    seen = set()
    run = [(k, s) for k, s in shots if k not in ("empty",)]
    picked = []
    for k, s in run:  # one frame per distinct status, plus the last
        key = re.sub(r"\d+ of \d+", "", k) if k != "done" else k
        if key not in seen:
            seen.add(key)
            picked.append((k, s))
    for k, s in picked:
        im = canvas(2, "Drop it into daRealKniga", "It flattens the page, cleans it up and reads the text")
        paste_center(im, fit(s, W - 80, H - BAR - 32))
        frames.append((im, 2600 if k == "done" else 1300 if k == "loaded" else 450))
    return frames


def scene_search(pdf):
    import pymupdf
    doc = pymupdf.open(pdf)
    page = doc[0]
    zoom = (H - BAR - 40) / page.rect.height
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    base = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    frames = []
    title, sub = "Out comes a clean PDF", "Text you can search, select and copy, in both alphabets"
    text = " ".join(page.get_text().split()).lower()
    for query in ("Пловдив", "Old Town"):
        hits = page.search_for(query)            # one box per line: a match across a line break has two
        count = text.count(query.lower())
        for n in range(1, len(query) + 1):
            frames.append((_search_frame(base, title, sub, query[:n], [], 0, zoom), 70))
        frames.append((_search_frame(base, title, sub, query, hits, count, zoom), 1800))
    return frames


def _search_frame(base, title, sub, typed, hits, count, zoom):
    im = canvas(3, title, sub)
    page = base.copy().convert("RGBA")
    over = Image.new("RGBA", page.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    for r in hits:
        od.rectangle([r.x0 * zoom - 2, r.y0 * zoom - 1, r.x1 * zoom + 2, r.y1 * zoom + 1], fill=(255, 196, 0, 120),
                     outline=(230, 150, 0, 255), width=2)
    page = Image.alpha_composite(page, over).convert("RGB")
    x, y = (W - page.width - 254) // 2, BAR + 20   # page on the left, search box to its right
    ImageDraw.Draw(im).rounded_rectangle([x - 1, y - 1, x + page.width, y + page.height], 4, outline=(208, 215, 222))
    im.paste(page, (x, y))
    # search box
    d = ImageDraw.Draw(im)
    bx, by, bw = x + page.width + 24, BAR + 40, 230
    d.rounded_rectangle([bx, by, bx + bw, by + 48], 10, fill=(255, 255, 255), outline=(140, 150, 160), width=2)
    d.ellipse([bx + 14, by + 13, bx + 30, by + 29], outline=MUTED, width=3)
    d.line([bx + 28, by + 27, bx + 36, by + 35], fill=MUTED, width=3)
    d.text((bx + 46, by + 24), typed, font=font(22), fill=INK, anchor="lm")
    if count:
        d.text((bx + 4, by + 64), f"{count} match{'es' if count != 1 else ''} found", font=font(19, True),
               fill=(26, 127, 55))
    return im


def _wrong(words, ref):
    """Words of an OCR reading that aren't in the reference (as they're printed)."""
    norm = lambda w: re.sub(r"^[^\w]+|[^\w]+$", "", w).lower()
    pool = {}
    for r in ref.split():
        pool[norm(r)] = pool.get(norm(r), 0) + 1
    out = []
    for w in words:
        k = norm(w)
        if k and pool.get(k, 0) > 0:
            pool[k] -= 1
            out.append(False)
        else:
            out.append(bool(k))
    return out


def _panel(im, x, y, w, h, title, score, text, ref, good):
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([x, y, x + w, y + h], 14, fill=(255, 255, 255), outline=(208, 215, 222), width=2)
    d.text((x + 22, y + 16), title, font=font(25, True), fill=BRAND if good else INK)
    d.text((x + 22, y + 52), score, font=font(19, True), fill=(26, 127, 55) if good else BAD_INK)
    words = text.split()
    bad = _wrong(words, ref)
    f = font(19)
    cx, cy, lh = x + 22, y + 96, 31
    for word, b in zip(words, bad):
        ww = d.textlength(word, font=f)
        if cx + ww > x + w - 22:
            cx, cy = x + 22, cy + lh
            if cy > y + h - 40:
                break
        if b:
            d.rounded_rectangle([cx - 3, cy - 2, cx + ww + 3, cy + 25], 4, fill=BAD_BG)
        d.text((cx, cy), word, font=f, fill=BAD_INK if b else INK)
        cx += ww + d.textlength(" ", font=f)


def scene_compare(plain, ours, ref, scores):
    im = canvas(4, "Plain OCR vs daRealKniga, same photo", "Misread words in red: wrong letters, wrong alphabet, wrong order")
    take = lambda t: " ".join(t.split()[:62])
    pw, ph = (W - 72) // 2, H - BAR - 92
    _panel(im, 24, BAR + 24, pw, ph, "Tesseract alone", f"{scores['tesseract']:.0%} words right", take(plain), ref,
           False)
    _panel(im, 48 + pw, BAR + 24, pw, ph, "daRealKniga", f"{scores['darealkniga']:.0%} words right", take(ours),
           ref, True)
    ImageDraw.Draw(im).text((W // 2, H - 34), "Same OCR models underneath. The difference: page cleanup, "
                            "two engines combined, and corrections.", font=font(16), fill=MUTED, anchor="mm")
    return [(im, 5200)]


SCALE = 0.84   # drawn at 960x760 for crisp text, saved at about 806x638


def save_gif(frames, path):
    size = (round(W * SCALE), round(H * SCALE))
    imgs = [f.resize(size, Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=192, dither=Image.NONE)
            for f, _ in frames]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=[d for _, d in frames], loop=0,
                 optimize=True, disposal=1)


def main():
    import json
    scores = {k: v["word_f1"] for k, v in
              json.load(open(os.path.join(ROOT, "benchmarks", "results.json"), encoding="utf-8"))
              ["samples"]["photo-bg"]["systems"].items()}
    with tempfile.TemporaryDirectory() as work:
        photo, plain, ref, lang = prepare(work)
        os.environ["XDG_CONFIG_HOME"] = os.path.join(work, "config")   # don't touch the real window settings
        shots, pdf, ours = record(photo, lang, os.path.join(work, "out"))
        frames = scene_photo(photo) + scene_window(shots, photo) + scene_search(pdf) + \
            scene_compare(plain, ours, ref, scores)
        save_gif(frames, OUT)
    print(f"wrote {OUT}: {len(frames)} frames, {os.path.getsize(OUT) / 1e6:.1f} MB, "
          f"{sum(d for _, d in frames) / 1000:.1f} s")


if __name__ == "__main__":
    main()
