"""Small shared helpers: logging, progress, page ranges, atomic writes, process pools."""
import json
import multiprocessing as mp
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed


# where Tesseract and DjVuLibre usually live when they are not on PATH (a macOS app started from
# the Finder doesn't see Homebrew's PATH; the Windows installers don't add themselves to it)
EXTRA_PATHS = {
    "darwin": ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"],
    "win32": [r"C:\Program Files\Tesseract-OCR", r"C:\Program Files (x86)\Tesseract-OCR",
              r"C:\Program Files (x86)\DjVuLibre", r"C:\Program Files\DjVuLibre"],
}


def extend_path():
    """Append the usual install folders of the external tools to PATH, if they exist."""
    have = os.environ.get("PATH", "").split(os.pathsep)
    extra = [d for d in EXTRA_PATHS.get(sys.platform, []) if os.path.isdir(d) and d not in have]
    if extra:
        os.environ["PATH"] = os.pathsep.join(have + extra)


def imread(path, flags=1):
    """cv2.imread for any file name: OpenCV can't open non-ASCII paths on Windows (1 = colour, 0 = grey)."""
    import cv2
    import numpy as np
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)


def imwrite(path, img):
    """cv2.imwrite for any file name (see imread)."""
    import cv2
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".png", img)
    if not ok:
        raise OSError(f"could not encode {path}")
    buf.tofile(path)


def log(msg):
    print(f"[darealkniga] {msg}", flush=True)


def warn(msg):
    print(f"[darealkniga] warning: {msg}", file=sys.stderr, flush=True)


class Progress:
    """One-line progress counter (redraws in a terminal, prints every ~10% otherwise).
    With DAREALKNIGA_PROGRESS=1 every update is printed as a tab-separated line for the GUI:
    @@progress<TAB>label<TAB>done<TAB>total"""

    def __init__(self, label, total):
        self.label, self.total, self.done = label, total, 0
        self.t0 = time.time()
        self.tty = sys.stdout.isatty()
        self.machine = os.environ.get("DAREALKNIGA_PROGRESS") == "1"
        self._last = -1
        self._draw()

    def step(self, n=1):
        self.done += n
        self._draw()

    def set(self, done):
        self.done = done
        self._draw()

    def _draw(self):
        if self.machine:
            print(f"@@progress\t{self.label}\t{self.done}\t{self.total}", flush=True)
            return
        pct = 100 * self.done // max(1, self.total)
        if not self.tty and pct // 10 == self._last // 10 and self.done != self.total:
            return
        self._last = pct
        el = time.time() - self.t0
        eta = ""
        if 0 < self.done < self.total:
            eta = f", ~{fmt_time(el / self.done * (self.total - self.done))} left"
        line = f"  {self.label}: {self.done}/{self.total} ({pct}%{eta})"
        print(("\r" + line + "\033[K") if self.tty else line, end="" if self.tty else "\n", flush=True)

    def close(self):
        if self.tty and not self.machine:
            print(flush=True)
        log(f"{self.label}: done in {fmt_time(time.time() - self.t0)}")


def fmt_time(s):
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def parse_pages(spec, n):
    """'1-10,15,20-' -> sorted list of 1-based page numbers within 1..n."""
    if not spec:
        return list(range(1, n + 1))
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a else 1
            b = int(b) if b else n
            out.update(range(a, b + 1))
        else:
            out.add(int(part))
    return sorted(p for p in out if 1 <= p <= n)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def pool_map(fn, items, jobs, label, initializer=None, initargs=(), spawn=False):
    """Run fn over items in worker processes with a progress line; returns results in input order."""
    items = list(items)
    if not items:
        return []
    jobs = max(1, min(jobs, len(items)))
    # fork is fast and safe on Linux; Windows has no fork and macOS can crash with it
    ctx = mp.get_context("fork" if sys.platform.startswith("linux") and not spawn else "spawn")
    pr = Progress(label, len(items))
    res = [None] * len(items)
    with ProcessPoolExecutor(jobs, mp_context=ctx, initializer=initializer, initargs=initargs) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for f in as_completed(futs):
            res[futs[f]] = f.result()
            pr.step()
    pr.close()
    return res
