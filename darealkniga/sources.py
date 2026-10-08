"""Page images from a single photo/scan, a folder of them, or an image-only PDF."""
import os
import shutil

from PIL import Image, ImageOps

from .util import natural_key

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp", ".heic"}


def list_images(folder):
    files = [f for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in IMAGE_EXT and not f.startswith(".")]
    return [os.path.join(folder, f) for f in sorted(files, key=natural_key)]


def is_image(path):
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in IMAGE_EXT


def count(src):
    if os.path.isdir(src):
        return len(list_images(src))
    if is_image(src):
        return 1
    import pymupdf as fitz
    with fitz.open(src) as doc:
        return len(doc)


def extract(src, n, dst_base):
    """Write page n (1-based) of src to dst_base + ext; returns the path written."""
    if os.path.isdir(src):
        return _from_file(list_images(src)[n - 1], dst_base)
    if is_image(src):
        return _from_file(src, dst_base)
    return _from_pdf(src, n, dst_base)


def _from_file(f, dst_base):
    im = Image.open(f)
    ext = os.path.splitext(f)[1].lower()
    orient = im.getexif().get(0x0112, 1)
    if ext in (".jpg", ".jpeg", ".png") and orient == 1 and im.mode in ("RGB", "L"):
        dst = dst_base + (".jpg" if ext != ".png" else ".png")
        shutil.copyfile(f, dst + ".part")
    else:  # apply EXIF rotation / unusual formats -> PNG
        dst = dst_base + ".png"
        ImageOps.exif_transpose(im).convert("RGB").save(dst + ".part", "PNG")
    os.replace(dst + ".part", dst)
    return dst


def _from_pdf(src, n, dst_base):
    """Keep the original JPEG bytes when a page is one upright full-page JPEG; otherwise render
    the page at the resolution of its largest image (or 300 dpi)."""
    import pymupdf as fitz
    with fitz.open(src) as doc:
        page = doc[n - 1]
        infos = [i for i in page.get_image_info(xrefs=True) if i.get("xref")]
        big = max(infos, key=lambda i: i["width"] * i["height"], default=None)
        if big:
            a, b, c, d, _, _ = big["transform"]
            x0, y0, x1, y1 = big["bbox"]
            pr = page.rect
            covers = (x1 - x0) * (y1 - y0) >= 0.85 * pr.width * pr.height
            upright = abs(b) < 1e-6 and abs(c) < 1e-6 and a > 0 and d > 0 and page.rotation == 0
            if covers and upright:
                x = doc.extract_image(big["xref"])
                if x["ext"] in ("jpeg", "jpg") and x.get("cs-name", "DeviceRGB") in ("DeviceRGB", "DeviceGray") \
                        and not x.get("smask"):
                    dst = dst_base + ".jpg"
                    with open(dst + ".part", "wb") as f:
                        f.write(x["image"])
                    os.replace(dst + ".part", dst)
                    return dst
            zoom = max(1.0, big["width"] / max(1.0, (x1 - x0)))
        else:
            zoom = 300 / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
        dst = dst_base + ".png"
        pix.save(dst + ".part.png")
        os.replace(dst + ".part.png", dst)
        return dst
