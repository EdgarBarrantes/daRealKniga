"""OCR engines.

Tesseract runs either from a local binary or inside a small Docker image (built on demand);
both use tessdata_best models downloaded to a cache directory. PaddleOCR runs in a pool of
worker processes, each holding its own model instance.
"""
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from importlib import resources

from .util import Progress, log, write_json, pool_map

TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/{}.traineddata"
DOCKER_IMAGE = "darealkniga-tesseract:1"


def tessdata_dir(override=None):
    d = override or os.environ.get("DAREALKNIGA_TESSDATA") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "darealkniga", "tessdata")
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)


def ensure_tessdata(langs, d):
    for code in langs.split("+"):
        dst = os.path.join(d, code + ".traineddata")
        if os.path.exists(dst):
            continue
        log(f"downloading Tesseract model '{code}' (tessdata_best)")
        tmp = dst + ".part"
        with urllib.request.urlopen(TESSDATA_URL.format(code)) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, dst)


def tesseract_backend(prefer=None):
    """'local' if a tesseract binary (v4+) is on PATH, else 'docker'."""
    if prefer in ("local", "docker"):
        return prefer
    if shutil.which("tesseract"):
        out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout
        try:
            if int(out.split()[1].split(".")[0]) >= 4:
                return "local"
        except (IndexError, ValueError):
            pass
    if shutil.which("docker"):
        return "docker"
    raise SystemExit("Tesseract not found: install tesseract-ocr (v4+) or Docker.")


def ensure_docker_image():
    if subprocess.run(["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True).returncode == 0:
        return
    log(f"building Docker image {DOCKER_IMAGE} (one-time)")
    ctx = resources.files("darealkniga") / "data"
    subprocess.run(["docker", "build", "-t", DOCKER_IMAGE, "-f", str(ctx / "Dockerfile.tesseract"), str(ctx)],
                   check=True)


RUN_SH = """#!/bin/sh
# $1 image  $2 output base  $3 dpi
tesseract --tessdata-dir "$TESSDATA" "$1" "$2.part" -l "$LANGS" --psm 3 --dpi "$3" \\
  -c tessedit_create_tsv=1 -c tessedit_create_txt=0 >/dev/null 2>&1 && mv "$2.part.tsv" "$2.tsv"
"""


def run_tesseract(jobs, langs, workdir, tessdata, threads, backend=None):
    """jobs: [(image_path, out_base, dpi)] with all paths inside workdir. Writes out_base + '.tsv'."""
    todo = [j for j in jobs if not os.path.exists(j[1] + ".tsv")]
    if not todo:
        return
    ensure_tessdata(langs, tessdata)
    backend = tesseract_backend(backend)
    workdir = os.path.abspath(workdir)
    script = os.path.join(workdir, "tesseract.sh")
    with open(script, "w") as f:
        f.write(RUN_SH)
    pr = Progress(f"tesseract ({backend})", len(todo))
    if backend == "local":
        env = dict(os.environ, OMP_THREAD_LIMIT="1", TESSDATA=tessdata, LANGS=langs)

        def one(j):
            subprocess.run(["sh", script, j[0], j[1], str(j[2])], env=env)
            return j

        with ThreadPoolExecutor(threads) as ex:
            for _ in ex.map(one, todo):
                pr.step()
    else:
        ensure_docker_image()
        rel = lambda p: "/w/" + os.path.relpath(os.path.abspath(p), workdir)
        lst = os.path.join(workdir, "tesseract.jobs")
        with open(lst, "w") as f:
            for img, out, dpi in todo:
                f.write(f"{rel(img)} {rel(out)} {dpi}\n")
        cmd = ["docker", "run", "--rm", "-u", f"{os.getuid()}:{os.getgid()}",
               "-e", "OMP_THREAD_LIMIT=1", "-e", "TESSDATA=/tessdata", "-e", f"LANGS={langs}",
               "-v", f"{workdir}:/w", "-v", f"{tessdata}:/tessdata:ro", DOCKER_IMAGE,
               "sh", "-c", f"xargs -P {threads} -L 1 sh /w/tesseract.sh < /w/tesseract.jobs"]
        proc = subprocess.Popen(cmd)
        while proc.poll() is None:
            time.sleep(2)
            pr.set(sum(os.path.exists(o + ".tsv") for _, o, _ in todo))
        if proc.returncode:
            raise SystemExit(f"tesseract container failed (exit {proc.returncode})")
        pr.set(sum(os.path.exists(o + ".tsv") for _, o, _ in todo))
    pr.close()
    missing = [j[0] for j in todo if not os.path.exists(j[1] + ".tsv")]
    if missing:
        raise SystemExit(f"tesseract produced no output for {len(missing)} page(s), e.g. {missing[0]}")


# ---------------------------------------------------------------- PaddleOCR

_PADDLE = None


def _paddle_init(rec, threads):
    global _PADDLE
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCR
    _PADDLE = PaddleOCR(text_detection_model_name="PP-OCRv5_mobile_det", text_recognition_model_name=rec,
                        use_doc_orientation_classify=False, use_doc_unwarping=False,
                        use_textline_orientation=False, text_det_limit_side_len=3400,
                        text_det_limit_type="max", cpu_threads=threads)


def _paddle_one(job):
    img, out = job
    r = _PADDLE.predict(img)[0].json["res"]
    write_json(out, {"texts": r["rec_texts"], "scores": [float(s) for s in r["rec_scores"]],
                     "boxes": [list(map(int, b)) for b in r["rec_boxes"]]})


def run_paddle(jobs, rec, workers, threads_total):
    """jobs: [(image_path, out_json)]."""
    todo = [j for j in jobs if not os.path.exists(j[1])]
    if not todo:
        return
    workers = max(1, min(workers, len(todo)))
    pool_map(_paddle_one, todo, workers, f"paddleocr ({rec})", initializer=_paddle_init,
             initargs=(rec, max(1, threads_total // workers)), spawn=True)
