"""Page flattening with UVDoc (PaddleX TextImageUnwarping): straightens curled lines, removes
perspective and crops the photo to the page."""
import os

import numpy as np
from PIL import Image

from .util import imread, pool_map

_MODEL = None


def _init(threads):
    global _MODEL
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ["OMP_NUM_THREADS"] = str(threads)
    from paddleocr import TextImageUnwarping
    _MODEL = TextImageUnwarping(model_name="UVDoc")


def _one(job):
    src, dst = job
    # the image itself, not its path: Paddle opens files with OpenCV, which fails on non-ASCII paths on Windows
    a = np.asarray(_MODEL.predict(imread(src))[0]["doctr_img"]).clip(0, 255).astype(np.uint8)  # already RGB
    Image.fromarray(a).save(dst + ".part.png")
    os.replace(dst + ".part.png", dst)


def run(jobs, workers, threads_total):
    """jobs: [(src_image, dst_png)]"""
    todo = [j for j in jobs if not os.path.exists(j[1])]
    if todo:
        workers = max(1, min(workers, len(todo)))
        pool_map(_one, todo, workers, "unwarp (UVDoc)", initializer=_init,
                 initargs=(max(1, threads_total // workers),), spawn=True)
