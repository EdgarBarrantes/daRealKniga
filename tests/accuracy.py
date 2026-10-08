"""OCR accuracy benchmark against books that already carry a good text layer.

Each sample is a few pages cut from a public book on the Internet Archive. The original text
layer is kept aside as the reference and the sample is processed by realkniga without it.
The text read back from realkniga's outputs is then scored against the reference.

The reference is itself OCR, from ABBYY or Tesseract, and has some errors. Scores therefore
measure agreement, and they understate realkniga's true accuracy a little.

Run standalone for a quick report:  python tests/accuracy.py [--check] [sample-name ...]
  --check             exit with an error when a sample scores below its minimum
  REALKNIGA_CMD=...   command to test instead of this checkout, e.g. a built AppImage:
                      REALKNIGA_CMD="./realkniga-x86_64.AppImage" python tests/accuracy.py --check
"""
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

RESULTS = []  # (sample, format, scores), collected by the tests for the summary table
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "realkniga", "testdata")


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
}


@dataclass
class Sample:
    name: str
    source: str            # key in SOURCES
    pages: list            # 1-based pages of the source
    lang: str
    args: list = field(default_factory=list)
    reference: str = None  # take the reference text from another source with the same page numbering
    min_word_f1: float = 0.0
    min_char_acc: float = 0.0
    description: str = ""


SAMPLES = [
    Sample("djvu-ru", "podigom.djvu", [40, 41, 42, 100], "rus",
           min_word_f1=0.93, min_char_acc=0.97,
           description="DjVu scan mode, Russian prose (Вазов, Под игом)"),
    Sample("pdf-ru", "podigom.pdf", [40, 41, 42, 100], "rus", reference="podigom.djvu",
           min_word_f1=0.93, min_char_acc=0.97,
           description="PDF photo mode on cropped flat scans, Russian prose; reference = DjVu text layer"),
    Sample("pdf-bg", "vazov4.pdf", [21, 41, 61], "bul",
           min_word_f1=0.85, min_char_acc=0.80,
           description="PDF photo mode, Bulgarian poetry and prose in low-resolution two-page spreads (Вазов, т. 4)"),
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


def cut(sample, workdir):
    """Write the sample's pages, without their text layer, to workdir; returns the path."""
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

def words(text):
    t = unicodedata.normalize("NFD", text)
    t = t.replace("́", "").replace("̀", "")  # stress marks
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"[¬­-]\s*\n\s*(?=[^\W\d_])", "", t)  # words hyphenated across lines
    t = t.lower().replace("ё", "е")
    return re.findall(r"[^\W\d_]+|\d+", t)


def score(ref_text, hyp_text):
    """-> dict of percentages. word_f1/recall/precision ignore word order (robust to column order);
    char_acc = 1 - character edit distance / reference length, in reading order."""
    r, h = words(ref_text), words(hyp_text)
    common = sum((Counter(r) & Counter(h)).values())
    rec = common / max(1, len(r))
    prec = common / max(1, len(h))
    f1 = 2 * rec * prec / max(1e-9, rec + prec)
    rs, hs = " ".join(r), " ".join(h)
    char = max(0.0, 1 - Levenshtein.distance(rs, hs) / max(1, len(rs)))
    return {"words": len(r), "word_recall": rec, "word_precision": prec, "word_f1": f1, "char_acc": char}


# ------------------------------------------------------------------ run

def run(sample, workdir):
    """Process a sample with realkniga and score every output format. -> {format: scores}"""
    inp = cut(sample, workdir)
    ref_src = fetch(sample.reference or sample.source)
    ref = "\n".join(page_texts(ref_src, sample.pages))
    out = os.path.join(workdir, "out")
    base = shlex.split(os.environ["REALKNIGA_CMD"]) if os.environ.get("REALKNIGA_CMD") else \
        [sys.executable, "-m", "realkniga"]
    cmd = [*base, "make", inp, "--lang", sample.lang, "-o", out,
           "--name", sample.name, "--work", os.path.join(workdir, "work"), *sample.args]
    subprocess.run(cmd, check=True)
    results = {}
    for ext in ("pdf", "djvu", "txt"):
        f = os.path.join(out, f"{sample.name}.{ext}")
        if not os.path.exists(f):
            continue
        if ext == "txt":
            hyp = open(f, encoding="utf-8").read()
        else:
            hyp = "\n".join(page_texts(f, range(1, len(sample.pages) + 1)))
        results[ext] = score(ref, hyp)
    return results, out


def fmt_row(name, ext, s):
    return (f"{name:<9} {ext:<5} {s['words']:>6} {100 * s['word_f1']:>7.1f}% {100 * s['word_recall']:>7.1f}% "
            f"{100 * s['word_precision']:>7.1f}% {100 * s['char_acc']:>7.1f}%")


HEADER = f"{'sample':<9} {'out':<5} {'words':>6} {'word F1':>8} {'recall':>8} {'precis.':>8} {'chars':>8}"


if __name__ == "__main__":
    import tempfile
    check = "--check" in sys.argv
    want = {a for a in sys.argv[1:] if not a.startswith("--")}
    rows, failed = [], []
    for s in SAMPLES:
        if want and s.name not in want:
            continue
        with tempfile.TemporaryDirectory() as d:
            res, _ = run(s, d)
        for ext, sc in res.items():
            rows.append(fmt_row(s.name, ext, sc))
            if sc["word_f1"] < s.min_word_f1 or sc["char_acc"] < s.min_char_acc:
                failed.append(f"{s.name}/{ext}")
    print("\n" + HEADER)
    print("\n".join(rows))
    if failed:
        print(f"\nbelow minimum: {', '.join(failed)}")
    sys.exit(1 if check and failed else 0)
