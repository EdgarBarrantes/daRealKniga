"""OCR accuracy benchmark: daRealKniga against plain Tesseract and plain PaddleOCR.

Each sample is a few pages with a known reference text:
- **Real scans.** Pages cut from public books on the Internet Archive that already carry a
  good text layer. The layer is removed before processing and kept as the reference. These
  references are OCR themselves, so their scores measure agreement.
- **Synthetic mixed-script pages.** Bulgarian or Russian text full of English words, rendered
  like a scan (see synthetic.py). Their reference is exact.

Every sample is read three ways, all on the same original page images:
- `tesseract`: plain Tesseract. Same models (tessdata_best) and page segmentation as
  daRealKniga, but no image cleanup, no second engine and no corrections.
- `paddleocr`: plain PaddleOCR PP-OCRv5. Same models as daRealKniga.
- `darealkniga`: the full pipeline. The text is read back from its PDF, DjVu and TXT outputs.

Usage:  python tests/accuracy.py [sample ...] [--save] [--check] [--no-baselines]
  --save          store the results in benchmarks/ and refresh the README chart and table
  --check         exit with an error when daRealKniga scores below a sample's minimum
  --no-baselines  only run daRealKniga (e.g. against an AppImage, see DAREALKNIGA_CMD)
  DAREALKNIGA_CMD= command to test instead of this checkout, e.g. a built AppImage
Every run prints the change against the last saved results.
"""
import difflib
import glob
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz.distance import Levenshtein

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []  # (sample, system/output, scores), collected by the tests for the summary table
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "darealkniga", "testdata")
SYSTEMS = ("tesseract", "paddleocr", "darealkniga")


@dataclass
class Source:
    url: str
    sha256: str
    file: str


SOURCES = {
    # Иван Вазов, "Под игом" (Russian translation), Библиотека всемирной литературы т. 70, 1970.
    # DjVu with a high-quality hidden text layer; the PDF scan of the same edition.
    "podigom.djvu": Source("https://archive.org/download/bvl-tom-70/bvl-tom-70.djvu",
                           "30bb56fe094d250757be0edcbadb7237acf44740709ebb5e33f11106984f3024", "podigom.djvu"),
    "podigom.pdf": Source("https://archive.org/download/bvl-tom-70/bvl-tom-70.pdf",
                          "17c205b40b2354f2c9003d8467914d7ca15219b267338fd9ec7171506b3ccc29", "podigom.pdf"),
    # Иван Вазов, Събрани съчинения, том 4 (1974). Bulgarian; text PDF, scanned as two-page spreads.
    "vazov4.pdf": Source("https://archive.org/download/4_20260711/"
                         "%D0%A1%D1%8A%D0%B1%D1%80%D0%B0%D0%BD%D0%B8%20%D0%A1%D1%8A%D1%87%D0%B8%D0%BD%D0%B5%D0%BD%D0%B8%D1%8F"
                         "%20%D0%A2%D0%BE%D0%BC%204%20%D0%98%D0%B2%D0%B0%D0%BD%20%D0%92%D0%B0%D0%B7%D0%BE%D0%B2_text.pdf",
                         "ad861d79a157b8225ebe23f232652099b7fd10ad052ab8a8e3bfc827d9ebb135", "vazov4.pdf"),
    # PT Serif (ParaType, SIL Open Font License), used to typeset the synthetic pages
    "PT_Serif-Regular.ttf": Source("https://github.com/google/fonts/raw/main/ofl/ptserif/PT_Serif-Web-Regular.ttf",
                                   "a4951fade06ff8f09b7673aa81ffb65a8cd409e24d3289a6dc670bc4dda2557a",
                                   "PT_Serif-Regular.ttf"),
    "PT_Serif-Bold.ttf": Source("https://github.com/google/fonts/raw/main/ofl/ptserif/PT_Serif-Web-Bold.ttf",
                                "038ba7336bd7ea14f12ad155bed51a4345cac5153275d521dec3ba04021c526e",
                                "PT_Serif-Bold.ttf"),
}


@dataclass
class Sample:
    name: str
    source: str            # key in SOURCES, or "synthetic[-photo]:<text file in tests/samples>"
    pages: list            # 1-based pages of the source
    lang: str
    title: str             # short label for the chart
    args: list = field(default_factory=list)
    reference: str = None  # take the reference text from another source with the same page numbering
    min_word_f1: float = 0.0
    min_char_acc: float = 0.0
    description: str = ""

    @property
    def synthetic(self):
        return self.source.startswith("synthetic")


SAMPLES = [
    Sample("mixed-bg", "synthetic:mixed_bg.txt", [1], "bul+eng", "Bulgarian + English textbook page",
           min_word_f1=0.97, min_char_acc=0.97,
           description="synthetic scan of a language-textbook page: Bulgarian with English words and sentences"),
    Sample("mixed-ru", "synthetic:mixed_ru.txt", [1], "rus+eng", "Russian + English technical page",
           min_word_f1=0.95, min_char_acc=0.95,
           description="synthetic scan of a manual page: Russian with English terms, commands and names"),
    Sample("photo-bg", "synthetic-photo:photo_bg.txt", [1], "bul+eng", "Phone photo, Bulgarian + English",
           min_word_f1=0.93, min_char_acc=0.95,
           description="synthetic phone photo of a travel-guide page (curled, in perspective, uneven light): "
                       "Bulgarian with English names and phrases"),
    Sample("djvu-ru", "podigom.djvu", [40, 41, 42, 100], "rus", "Russian novel, DjVu scan",
           min_word_f1=0.93, min_char_acc=0.97,
           description="DjVu scan mode, Russian prose (Вазов, Под игом, 1970)"),
    Sample("pdf-ru", "podigom.pdf", [40, 41, 42, 100], "rus", "Russian novel, PDF scan", reference="podigom.djvu",
           min_word_f1=0.93, min_char_acc=0.97,
           description="PDF of the same edition (cropped flat scans); reference = the DjVu text layer"),
    Sample("pdf-bg", "vazov4.pdf", [21, 41, 61], "bul", "Bulgarian poems, low-res PDF",
           min_word_f1=0.85, min_char_acc=0.80,
           description="Bulgarian poetry and prose, 133 dpi two-page spreads (Вазов, Събрани съчинения т. 4, 1974); "
                       "the reference has many OCR errors of its own"),
]


# ------------------------------------------------------------------ data

def fetch(key):
    s = SOURCES[key]
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, s.file)
    if not os.path.exists(path):
        print(f"downloading {s.url}", file=sys.stderr)
        with urllib.request.urlopen(s.url) as r, open(path + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(path + ".part", path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    if h.hexdigest() != s.sha256:
        raise RuntimeError(f"{path}: checksum mismatch (file changed upstream?); delete it to re-download")
    return path


def page_texts(path, pages):
    """Hidden text of the given pages of a DjVu or PDF file."""
    if path.endswith(".djvu"):
        return [subprocess.run(["djvused", path, "-e", f"select {n}; print-pure-txt"],
                               capture_output=True, text=True, check=True).stdout for n in pages]
    import pymupdf
    with pymupdf.open(path) as d:
        return [d[n - 1].get_text() for n in pages]


def reference(sample):
    if sample.synthetic:
        with open(os.path.join(HERE, "samples", sample.source.split(":", 1)[1]), encoding="utf-8") as f:
            return f.read()
    return "\n".join(page_texts(fetch(sample.reference or sample.source), sample.pages))


def cut(sample, workdir):
    """Write the sample's pages, without any text layer, to workdir; returns the path."""
    if sample.synthetic:
        import synthetic
        out = os.path.join(workdir, sample.name + ".jpg")
        make = synthetic.photograph if sample.source.startswith("synthetic-photo:") else synthetic.render
        make(reference(sample), out, fetch("PT_Serif-Regular.ttf"), fetch("PT_Serif-Bold.ttf"), seed=7)
        return out
    src = fetch(sample.source)
    if src.endswith(".djvu"):
        out = os.path.join(workdir, sample.name + ".djvu")
        parts = []
        for n in sample.pages:
            p = os.path.join(workdir, f"_p{n}.djvu")
            subprocess.run(["djvused", src, "-e", f"select {n}; save-page-with {p}"], check=True)
            parts.append(p)
        subprocess.run(["djvm", "-c", out] + parts, check=True)
        subprocess.run(["djvused", out, "-e", "remove-txt", "-s"], check=True)
        for p in parts:
            os.remove(p)
        assert not subprocess.run(["djvutxt", out], capture_output=True, text=True).stdout.strip()
        return out
    import pikepdf
    out = os.path.join(workdir, sample.name + ".pdf")
    with pikepdf.open(src) as pdf:
        new = pikepdf.new()
        for n in sample.pages:
            new.pages.append(pdf.pages[n - 1])
        new.save(out)
    return out


# ------------------------------------------------------------------ metrics

def words(text, lower=True):
    """Word tokens. Case-insensitive, but a Latin letter in place of its Cyrillic twin (or the
    other way round) still makes a different word: that is exactly the error searches suffer from."""
    t = unicodedata.normalize("NFD", text)
    t = t.replace("́", "").replace("̀", "")  # stress marks
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"[¬­-]\s*\n\s*(?=[^\W\d_])", "", t)  # words hyphenated across lines
    t = t.replace("ё", "е").replace("Ё", "Е")
    if lower:
        t = t.lower()
    return re.findall(r"[^\W\d_]+|\d+", t)


def score(ref_text, hyp_text):
    """-> word_f1/recall/precision (word order ignored: robust to column order) and
    char_acc = 1 - character edit distance / reference length, in reading order."""
    r, h = words(ref_text), words(hyp_text)
    common = sum((Counter(r) & Counter(h)).values())
    rec = common / max(1, len(r))
    prec = common / max(1, len(h))
    f1 = 2 * rec * prec / max(1e-9, rec + prec)
    rs, hs = " ".join(r), " ".join(h)
    char = max(0.0, 1 - Levenshtein.distance(rs, hs) / max(1, len(rs)))
    return {"words": len(r), "word_recall": rec, "word_precision": prec, "word_f1": f1, "char_acc": char}


def _align(ref, hyp):
    """ref index -> hyp token (original case) for one-to-one aligned words."""
    rl, hl = [w.lower() for w in ref], [w.lower() for w in hyp]
    out = {}
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, rl, hl, autojunk=False).get_opcodes():
        if op in ("equal", "replace") and a2 - a1 == b2 - b1:
            for k in range(a2 - a1):
                out[a1 + k] = hyp[b1 + k]
    return out


def fixes(ref_text, hyps, limit=12):
    """Words plain Tesseract got wrong and daRealKniga got right: [{ref, tesseract, paddleocr, darealkniga}]."""
    ref = words(ref_text, lower=False)
    al = {k: _align(ref, words(v, lower=False)) for k, v in hyps.items()}
    out, seen = [], set()
    for i, w in enumerate(ref):
        t, rk = al["tesseract"].get(i), al["darealkniga"].get(i)
        if t is None or rk is None or t.lower() == w.lower() or rk.lower() != w.lower() or w.lower() in seen:
            continue
        seen.add(w.lower())
        out.append({"ref": w, "tesseract": t, "paddleocr": al.get("paddleocr", {}).get(i), "darealkniga": rk})
    # mixed-script confusions first: they are the point of the exercise
    out.sort(key=lambda e: not _script_mix(e["tesseract"], e["ref"]))
    return out[:limit]


def _script_mix(hyp, ref):
    cyr = lambda s: bool(re.search(r"[Ѐ-ӿ]", s))
    lat = lambda s: bool(re.search(r"[A-Za-z]", s))
    return (cyr(hyp) and lat(hyp)) or (cyr(hyp) != cyr(ref)) or (lat(hyp) != lat(ref))


# ------------------------------------------------------------------ run

def _plain_engines(sample, workdir, images):
    """Plain Tesseract and plain PaddleOCR on the original page images -> {system: text}."""
    try:
        from darealkniga import fuse, langs, ocr
    except ImportError:
        return {}
    lg = langs.parse(sample.lang)
    bdir = os.path.join(workdir, "plain")
    os.makedirs(bdir, exist_ok=True)
    jobs = os.cpu_count() or 4
    tess = [(img, os.path.join(bdir, f"t{i:04d}"), 300) for i, img in enumerate(images, 1)]
    ocr.run_tesseract(tess, lg.tess, workdir, ocr.tessdata_dir(), jobs)
    out = {"tesseract": "\n".join("\n".join(" ".join(w["t"] for w in line) for line in fuse.read_tess(t + ".tsv", 1.0))
                                  for _, t, _ in tess)}
    rec = lg.paddle_rec or "en_PP-OCRv5_mobile_rec"
    pad = [(img, os.path.join(bdir, f"p{i:04d}.json")) for i, img in enumerate(images, 1)]
    ocr.run_paddle(pad, rec, max(1, jobs // 6), jobs)
    import json
    out["paddleocr"] = "\n".join("\n".join(json.load(open(p, encoding="utf-8"))["texts"]) for _, p in pad)
    return out


def run(sample, workdir, baselines=True):
    """-> ({system: scores}, {output format: scores}, fixes, output folder).
    `darealkniga` in the first dict is the PDF output."""
    inp = cut(sample, workdir)
    ref = reference(sample)
    out = os.path.join(workdir, "out")
    work = os.path.join(workdir, "work")
    base = shlex.split(os.environ["DAREALKNIGA_CMD"]) if os.environ.get("DAREALKNIGA_CMD") else \
        [sys.executable, "-m", "darealkniga"]
    subprocess.run([*base, "make", inp, "--lang", sample.lang, "-o", out, "--name", sample.name,
                    "--work", work, *sample.args], check=True)
    outputs, texts = {}, {}
    for ext in ("pdf", "djvu", "txt"):
        f = os.path.join(out, f"{sample.name}.{ext}")
        if os.path.exists(f):
            texts[ext] = open(f, encoding="utf-8").read() if ext == "txt" else \
                "\n".join(page_texts(f, range(1, len(sample.pages) + 1)))
            outputs[ext] = score(ref, texts[ext])
    systems = {"darealkniga": outputs["pdf"]}
    found = []
    if baselines:
        # the same page images daRealKniga started from: rendered DjVu pages, or the original photos/scans
        images = sorted(glob.glob(os.path.join(work, "pages", "*.pgm"))) or \
            sorted(f for f in glob.glob(os.path.join(work, "src", "*")) if not os.path.basename(f).startswith("."))
        plain = _plain_engines(sample, workdir, images)
        for k, v in plain.items():
            systems[k] = score(ref, v)
        if plain:
            found = fixes(ref, {**plain, "darealkniga": texts["pdf"]})
    return systems, outputs, found, out


# ------------------------------------------------------------------ report

def fmt(x):
    return f"{100 * x:5.1f}%"


def table(results, saved=None):
    lines = [f"{'sample':<9} {'system':<11} {'words':>6} {'word acc':>9} {'chars':>7}   change vs saved"]
    for name, r in results.items():
        for system in SYSTEMS:
            s = r["systems"].get(system)
            if not s:
                continue
            delta = ""
            old = (saved or {}).get("samples", {}).get(name, {}).get("systems", {}).get(system)
            if old:
                dw, dc = s["word_f1"] - old["word_f1"], s["char_acc"] - old["char_acc"]
                delta = f"{100 * dw:+5.1f} / {100 * dc:+5.1f}" if abs(dw) + abs(dc) > 0.0005 else "  same"
            lines.append(f"{name:<9} {system:<11} {s['words']:>6} {fmt(s['word_f1']):>9} {fmt(s['char_acc']):>7}   {delta}")
    return "\n".join(lines)


def main(argv):
    import tempfile
    import report
    flags = {a for a in argv if a.startswith("--")}
    want = [a for a in argv if not a.startswith("--")]
    results, failed = {}, []
    for s in SAMPLES:
        if want and s.name not in want:
            continue
        with tempfile.TemporaryDirectory() as d:
            systems, outputs, found, _ = run(s, d, baselines="--no-baselines" not in flags)
        results[s.name] = {"title": s.title, "description": s.description, "lang": s.lang,
                           "pages": len(s.pages), "synthetic": s.synthetic,
                           "systems": systems, "outputs": outputs, "fixes": found}
        for ext, sc in outputs.items():
            if sc["word_f1"] < s.min_word_f1 or sc["char_acc"] < s.min_char_acc:
                failed.append(f"{s.name}/{ext}")
    saved = report.load()
    print("\n" + table(results, saved))
    if failed:
        print(f"\nbelow minimum: {', '.join(failed)}")
    if "--save" in flags:
        if want or "--no-baselines" in flags:
            sys.exit("--save needs a full run: all samples, with baselines")
        report.save(results)
        print(f"\nsaved to {os.path.relpath(report.RESULTS_JSON)}, history and README updated")
    return 1 if "--check" in flags and failed else 0


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main(sys.argv[1:]))
