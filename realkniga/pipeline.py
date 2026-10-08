"""The two book pipelines.

scan  (DjVu input): the page images are kept as they are. Pages are OCR'd and the DjVu gets a
      hidden text layer; a PDF is rebuilt from the DjVu layers. Every page gets the same size.
photo (folder of images or image PDF): pages are flattened (UVDoc), cleaned, resized to one page
      size, OCR'd and written to a compact PDF (1-bit text + greyscale photos, colour covers).

All intermediate results live in a work directory, one file per page, so an interrupted run
resumes where it stopped. Changing a setting invalidates only the stages that depend on it.
"""
import json
import os
import shutil
import statistics
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image

from . import djvu, enhance, fuse, langs as langs_mod, ocr, pdf, sources, textlayer, unwarp
from .util import Progress, log, warn, parse_pages, pool_map, read_json, write_json

PHOTO_DPI = 400  # resolution of cleaned page images


class Workspace:
    def __init__(self, root, input_path):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)
        st = os.stat(input_path)
        self.ident = {"input": os.path.abspath(input_path), "size": st.st_size, "mtime": int(st.st_mtime)}

    def stage(self, name, settings):
        """Directory for a stage; wiped if it was produced with different settings."""
        d = os.path.join(self.root, name)
        key = json.loads(json.dumps(dict(self.ident, **settings)))  # tuples -> lists, as stored
        f = os.path.join(d, ".settings.json")
        if os.path.exists(d) and (not os.path.exists(f) or read_json(f) != key):
            log(f"settings changed: redoing stage '{name}'")
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
        write_json(f, key)
        return d


def threads_jobs(cfg):
    return cfg.jobs or os.cpu_count() or 4


def _engine(cfg, lg):
    if getattr(cfg, "_engine", None):
        return cfg._engine
    e = cfg.engine
    if e == "auto":
        e = "fused" if lg.cyrillic and lg.paddle_rec else "tesseract"
    if e in ("fused", "paddle") and not lg.paddle_rec:
        warn(f"no PaddleOCR recogniser for '{lg.tess}'; using Tesseract only")
        e = "tesseract"
    if e == "fused" and not lg.cyrillic:
        warn("fusion rules are tuned for Cyrillic+Latin text; using Tesseract only")
        e = "tesseract"
    cfg._engine = e
    return e


def _ocr(cfg, ws, lg, items, ocr_settings):
    """items: [(page, image_path, dpi, W, H, scale)] -> OCR page records."""
    engine = _engine(cfg, lg)
    log(f"OCR engine: {engine} ({lg.tess})")
    jobs = threads_jobs(cfg)
    tdir = ws.stage("tess", dict(ocr_settings, langs=lg.tess))
    tess = {n: os.path.join(tdir, f"{n:04d}") for n, *_ in items}
    ocr.run_tesseract([(img, tess[n], dpi) for n, img, dpi, *_ in items], lg.tess, ws.root,
                      ocr.tessdata_dir(cfg.tessdata), jobs, cfg.tesseract)
    padd = {}
    if engine == "fused":
        pdir = ws.stage("paddle", dict(ocr_settings, rec=lg.paddle_rec))
        padd = {n: os.path.join(pdir, f"{n:04d}.json") for n, *_ in items}
        ocr.run_paddle([(img, padd[n]) for n, img, *_ in items], lg.paddle_rec,
                       cfg.paddle_workers or max(1, jobs // 6), jobs)
    fuse.configure(lg)
    return [textlayer.build_page(n, W, H, tess[n] + ".tsv", scale, lg, padd.get(n))
            for n, img, dpi, W, H, scale in items]


def _outputs(cfg, stem):
    out_dir = os.path.abspath(cfg.output or os.path.dirname(os.path.abspath(cfg.input)))
    os.makedirs(out_dir, exist_ok=True)
    name = cfg.name or f"{stem} (OCR)"
    return out_dir, name


def _finish(cfg, ws, pages, out_dir, name, written):
    txt = os.path.join(out_dir, name + ".txt")
    if "txt" in cfg.formats:
        textlayer.write_text(pages, txt)
        written.append(txt)
    write_json(os.path.join(ws.root, "ocr.json"), pages)
    log(f"recognised {textlayer.word_count(pages):,} words on {len(pages)} pages")
    empty = [p["page"] for p in pages if not p["lines"]]
    if empty:
        log(f"pages without text: {', '.join(map(str, empty[:30]))}{' ...' if len(empty) > 30 else ''}")
    for w in written:
        log(f"wrote {w} ({os.path.getsize(w) / 1e6:.1f} MB)")
    if cfg.cleanup:
        shutil.rmtree(ws.root)
        log("work directory removed")
    else:
        log(f"work files kept in {ws.root} (re-runs reuse them; --cleanup removes them)")


# ------------------------------------------------------------------ scan (DjVu)

def run_djvu(cfg):
    djvu.check_tools()
    book = os.path.abspath(cfg.input)
    stem = os.path.splitext(os.path.basename(book))[0]
    out_dir, name = _outputs(cfg, stem)
    ws = Workspace(cfg.work or os.path.join(out_dir, ".realkniga", stem), book)
    lg = langs_mod.parse(cfg.lang)
    info = djvu.page_info(book)
    sel = parse_pages(cfg.pages, len(info))
    log(f"{os.path.basename(book)}: {len(info)} pages, processing {len(sel)}")

    # Physical page sizes. Some scans contain pages stored at a much higher resolution but
    # labelled with the same dpi, which makes them display 2-4x larger: normalise their width.
    med_w = statistics.median(W for W, H, d in info)
    eff = {}
    for n, (W, H, d) in enumerate(info, 1):
        eff[n] = d * W / med_w if cfg.normalize and W > 1.3 * med_w else d
    size_in = {n: (W / eff[n], H / eff[n]) for n, (W, H, d) in enumerate(info, 1)}
    if cfg.page_size and cfg.page_size != "auto":
        bw, bh = parse_size(cfg.page_size)
    else:
        bw = round(statistics.median(w for w, h in size_in.values()), 2)
        bh = round(float(np.percentile([h for w, h in size_in.values()], 95)), 2)
    log(f"uniform page size: {bw:.2f} x {bh:.2f} in")

    # render greyscale pages for OCR (at most cfg.ocr_dpi)
    rdir = ws.stage("pages", {"ocr_dpi": cfg.ocr_dpi, "normalize": cfg.normalize})
    items, jobs = [], []
    for n in sel:
        W, H, d = info[n - 1]
        s = min(1.0, cfg.ocr_dpi / eff[n])
        w, h = max(1, round(W * s)), max(1, round(H * s))
        img = os.path.join(rdir, f"{n:04d}.pgm")
        items.append((n, img, round(eff[n] * s), W, H, W / w))
        if not os.path.exists(img):
            jobs.append((book, n, w, h, img))
    if jobs:
        pr = Progress("render pages", len(jobs))
        with ThreadPoolExecutor(threads_jobs(cfg)) as ex:
            for _ in ex.map(djvu.render_gray, jobs):
                pr.step()
        pr.close()

    pages = _ocr(cfg, ws, lg, items, {"ocr_dpi": cfg.ocr_dpi, "normalize": cfg.normalize})
    written = []
    if "djvu" in cfg.formats:
        out = os.path.join(out_dir, name + ".djvu")
        dpis = {n: max(1, round(W / bw)) for n, (W, H, d) in enumerate(info, 1)}
        log("writing DjVu text layer")
        djvu.write(book, out, pages, dpis)
        written.append(out)
    if "pdf" in cfg.formats:
        out = os.path.join(out_dir, name + ".pdf")
        layers = pool_map(djvu.mrc_layers, [(book, n, *info[n - 1][:2]) for n in sel],
                          threads_jobs(cfg), "PDF page images")
        log("assembling PDF")
        wr = pdf.Writer((bw * 72, bh * 72))
        for p, lay in zip(pages, layers):
            w_in, h_in = size_in[p["page"]]
            wr.add({"size": (w_in * 72, h_in * 72), "layers": lay}, p)
        wr.save(out, cfg.title or stem, cfg.author, _producer(cfg, lg))
        written.append(out)
    _finish(cfg, ws, pages, out_dir, name, written)


# ------------------------------------------------------------------ photo (images / image PDF)

def _is_flat(path):
    return enhance.is_flat_scan(cv2.imread(path, cv2.IMREAD_GRAYSCALE))


def _enhance_one(job):
    src, out, mask_out, size, color, trim = job
    img = cv2.cvtColor(cv2.imread(src, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    page, mask, colorful = enhance.enhance(img, size, color, trim)
    if colorful:
        cv2.imwrite(out + ".part.png", cv2.cvtColor(page, cv2.COLOR_RGB2BGR))
    else:
        cv2.imwrite(mask_out, mask)
        cv2.imwrite(out + ".part.png", page)
    os.replace(out + ".part.png", out)


def _photo_layers(job):
    """Cleaned page -> PDF layers: colour JPEG, or greyscale photo JPEG + 1-bit text stencil."""
    path, mask_path, quality = job
    im = Image.open(path)
    W, H = im.size
    if im.mode != "L":
        return [pdf.jpeg(im.convert("RGB"), quality["color"], allow_gray=False)]
    a = np.asarray(im)
    photo = enhance.rect_mask(np.asarray(Image.open(mask_path)) > 100) if os.path.exists(mask_path) \
        else np.zeros_like(a, dtype=bool)
    layers = []
    if photo.any():
        bg = np.where(photo, a, 255).astype(np.uint8)
        layers.append(pdf.jpeg(Image.fromarray(bg).resize((W // 2, H // 2), Image.LANCZOS), quality["photo"]))
    ink = enhance.binarize(a, photo)
    st = pdf.g4(Image.fromarray(~ink))  # True = paper
    st.update(kind="stencil", fill=0.08)
    layers.append(st)
    return layers


def parse_size(s):
    w, h = (float(x) for x in s.lower().replace("in", "").split("x"))
    return w, h


def run_photos(cfg):
    src = os.path.abspath(cfg.input)
    stem = os.path.basename(src.rstrip("/")) if os.path.isdir(src) else os.path.splitext(os.path.basename(src))[0]
    out_dir, name = _outputs(cfg, cfg.title or stem)
    ws = Workspace(cfg.work or os.path.join(out_dir, ".realkniga", stem), src)
    lg = langs_mod.parse(cfg.lang)
    total = sources.count(src)
    if not total:
        raise SystemExit(f"no page images found in {src}")
    sel = parse_pages(cfg.pages, total)
    log(f"{os.path.basename(src)}: {total} pages, processing {len(sel)}")
    jobs = threads_jobs(cfg)

    # 1. page images
    sdir = ws.stage("src", {})
    have = {os.path.splitext(f)[0]: os.path.join(sdir, f) for f in os.listdir(sdir) if not f.startswith(".")
            and ".part" not in f}
    need = [n for n in sel if f"{n:04d}" not in have]
    if need:
        pr = Progress("extract pages", len(need))
        with ThreadPoolExecutor(min(8, jobs)) as ex:
            for n, path in zip(need, ex.map(lambda n: sources.extract(src, n, os.path.join(sdir, f"{n:04d}")), need)):
                have[f"{n:04d}"] = path
                pr.step()
        pr.close()
    srcs = {n: have[f"{n:04d}"] for n in sel}

    # 2. flatten photos (UVDoc); cropped flat scans are left alone
    udir = ws.stage("unwarp", {"model": "UVDoc", "mode": cfg.unwarp})
    decided = os.path.join(udir, "photo_pages.json")
    is_photo = {int(k): v for k, v in read_json(decided).items()} if os.path.exists(decided) else {}
    todo = [n for n in sel if n not in is_photo]
    if cfg.unwarp != "auto":
        is_photo.update({n: cfg.unwarp == "always" for n in todo})
    elif todo:
        flags = pool_map(_is_flat, [srcs[n] for n in todo], jobs, "detect photos vs. flat scans")
        is_photo.update({n: not f for n, f in zip(todo, flags)})
    write_json(decided, {str(k): v for k, v in is_photo.items()})
    photos = [n for n in sel if is_photo[n]]
    if cfg.unwarp == "auto":
        log(f"{len(photos)} photographed page(s) to flatten, {len(sel) - len(photos)} flat scan(s)")
    flat = {n: os.path.join(udir, f"{n:04d}.png") if is_photo[n] else srcs[n] for n in sel}
    unwarp.run([(srcs[n], flat[n]) for n in photos], cfg.unwarp_workers or max(1, jobs // 6), jobs)

    # 3. page size
    if cfg.page_size and cfg.page_size != "auto":
        pw, ph = parse_size(cfg.page_size)
    else:
        ratios = []
        for n in sel[:: max(1, len(sel) // 40)]:
            with Image.open(flat[n]) as im:
                ratios.append(im.height / im.width)
        pw = cfg.page_width
        ph = round(pw * statistics.median(ratios) * 4) / 4  # nearest 1/4 inch
    size_px = (round(pw * PHOTO_DPI), round(ph * PHOTO_DPI))
    log(f"page size: {pw:g} x {ph:g} in ({size_px[0]}x{size_px[1]} px at {PHOTO_DPI} dpi)")

    # 4. clean up
    edir = ws.stage("clean", {"unwarp": cfg.unwarp, "size": size_px, "color": cfg.color, "v": 2})
    mdir = os.path.join(edir, "photo")
    os.makedirs(mdir, exist_ok=True)
    enh = {n: os.path.join(edir, f"{n:04d}.png") for n in sel}
    masks = {n: os.path.join(mdir, f"{n:04d}.png") for n in sel}
    pool_map(_enhance_one, [(flat[n], enh[n], masks[n], size_px, cfg.color, 0.012 if is_photo[n] else 0.0)
                            for n in sel if not os.path.exists(enh[n])],
             max(1, min(jobs, 8)), "clean up pages")

    # 5. OCR
    items = [(n, enh[n], PHOTO_DPI, size_px[0], size_px[1], 1.0) for n in sel]
    pages = _ocr(cfg, ws, lg, items, {"clean": read_json(os.path.join(edir, ".settings.json"))})

    # 6. PDF
    written = []
    if "pdf" in cfg.formats:
        out = os.path.join(out_dir, name + ".pdf")
        q = {"color": 88, "photo": 80}
        layers = pool_map(_photo_layers, [(enh[n], masks[n], q) for n in sel], max(1, min(jobs, 6)),
                          "PDF page images")
        log("assembling PDF")
        wr = pdf.Writer((pw * 72, ph * 72))
        for p, lay in zip(pages, layers):
            wr.add({"size": (pw * 72, ph * 72), "layers": lay}, p)
        wr.save(out, cfg.title or stem, cfg.author, _producer(cfg, lg))
        written.append(out)
    if "djvu" in cfg.formats:
        warn("DjVu output is only available for DjVu input; skipped")
    _finish(cfg, ws, pages, out_dir, name, written)


def _producer(cfg, lg):
    return f"realKniga; OCR: {_engine(cfg, lg)} ({lg.tess})"
