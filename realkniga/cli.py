"""Command line interface."""
import argparse
import os
import shutil
import subprocess
import sys

from . import __version__

EPILOG = """examples:
  realkniga make "Bulgarian for Beginners - Part 1.djvu" --lang bul+eng
  realkniga make book.pdf --lang bul --title "Под игото" --author "Иван Вазов"
  realkniga make phone-photos/ --lang rus --page-size 6x9
  realkniga make receipt.jpg --lang ukr+eng         # a single photo: receipt, letter, note
  realkniga make scans.pdf --unwarp never         # force: never flatten (default: detect per page)
  realkniga make book.djvu --pages 1-20           # quick trial on a few pages
  realkniga doctor                                # check that everything is installed
  realkniga gui                                   # open the graphical interface
"""


def build_parser():
    ap = argparse.ArgumentParser(prog="realkniga", description="realKniga: make scanned or photographed books, "
                                 "documents, receipts and notes searchable. Built for Slavic languages and English, "
                                 "including text that mixes Cyrillic and Latin script.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG)
    ap.add_argument("--version", action="version", version=f"realKniga {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("make", help="process a book or document", formatter_class=argparse.RawDescriptionHelpFormatter,
                       epilog=EPILOG)
    m.add_argument("input", help="a .djvu file, an image-only .pdf, a photo/scan (jpg, png, tif...), or a folder of them")
    m.add_argument("-l", "--lang", default="bul+eng",
                   help="Tesseract language codes joined by '+', main language first (default: bul+eng)")
    m.add_argument("-o", "--output", help="output folder (default: next to the input)")
    m.add_argument("--name", help="output file name without extension (default: '<input> (OCR)')")
    m.add_argument("--title", help="document title stored in the PDF")
    m.add_argument("--author", help="author stored in the PDF")
    m.add_argument("--mode", choices=["auto", "scan", "photo"], default="auto",
                   help="scan = keep the DjVu page images; photo = flatten and clean the images "
                        "(default: scan for .djvu, photo otherwise)")
    m.add_argument("--formats",
                   help="outputs to write, comma separated: pdf, djvu (DjVu input only), txt "
                        "(default: all that apply)")
    m.add_argument("--engine", choices=["auto", "tesseract", "fused"], default="auto",
                   help="fused = Tesseract + PaddleOCR merged word by word (slower, more accurate); "
                        "auto picks fused for Cyrillic languages, Tesseract otherwise (default: auto)")
    m.add_argument("--pages", help="only process these pages, e.g. 1-20,35 (for trials)")
    m.add_argument("--page-size", default="auto",
                   help="output page size in inches, e.g. 5.5x8.5 (default: auto)")
    m.add_argument("--page-width", type=float, default=5.5,
                   help="photo mode, automatic size: page width in inches; height follows the pages' "
                        "aspect ratio (default: 5.5)")
    m.add_argument("--color", choices=["auto", "never", "always"], default="auto",
                   help="photo mode: keep pages in colour (auto = only colourful pages such as covers)")
    m.add_argument("--unwarp", choices=["auto", "always", "never"], default="auto",
                   help="photo mode: flatten pages with UVDoc. auto = only pages that look like photos "
                        "(background or shadows around the page), not cropped flat scans (default: auto)")
    m.add_argument("--no-unwarp", dest="unwarp", action="store_const", const="never",
                   help="same as --unwarp never")
    m.add_argument("--no-normalize", dest="normalize", action="store_false",
                   help="scan mode: don't shrink pages stored at a much higher resolution than the rest")
    m.add_argument("--ocr-dpi", type=int, default=300, help="scan mode: max resolution for OCR (default: 300)")
    m.add_argument("-j", "--jobs", type=int, help="parallel jobs (default: number of CPUs)")
    m.add_argument("--paddle-workers", type=int, help="PaddleOCR processes (default: jobs/6)")
    m.add_argument("--unwarp-workers", type=int, help="UVDoc processes (default: jobs/6)")
    m.add_argument("--tesseract", choices=["auto", "local", "docker"], default="auto",
                   help="where to run Tesseract (default: local binary if present, else Docker)")
    m.add_argument("--tessdata", help="folder with .traineddata files (default: ~/.cache/realkniga/tessdata, "
                                      "tessdata_best models are downloaded on demand)")
    m.add_argument("--work", help="work folder for intermediate files (default: <output>/.realkniga/<name>)")
    m.add_argument("--cleanup", action="store_true", help="delete the work folder after success")

    sub.add_parser("doctor", help="check dependencies")
    g = sub.add_parser("gui", help="open the graphical interface")
    g.add_argument("input", nargs="?", help="book to open")
    g.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    return ap


def doctor():
    ok = True

    def row(name, good, detail=""):
        nonlocal ok
        ok &= bool(good) or name.startswith("(optional)")
        print(f"  [{'ok' if good else '--'}] {name}{': ' + detail if detail else ''}")

    print("realKniga", __version__, "| python", sys.version.split()[0])
    for mod in ("numpy", "cv2", "PIL", "pikepdf", "pymupdf", "wordfreq", "paddleocr", "paddle", "PySide6"):
        name = f"(optional) python module {mod} (interface)" if mod == "PySide6" else f"python module {mod}"
        try:
            __import__(mod)
            row(name, True)
        except Exception as e:  # noqa: BLE001
            row(name, False, str(e).splitlines()[0])
    for t in ("ddjvu", "djvused", "djvudump"):
        row(f"(optional) {t} (DjVu input)", shutil.which(t), "" if shutil.which(t) else "install djvulibre-bin")
    tess = shutil.which("tesseract")
    dock = shutil.which("docker")
    if tess:
        v = subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.split("\n")[0]
        row("tesseract (local)", True, v)
    else:
        row("(optional) tesseract (local)", False, "not found; Docker will be used")
    if not tess:
        d_ok = dock and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
        row("docker (for Tesseract)", d_ok, "" if d_ok else "install tesseract-ocr or Docker")
    from .ocr import tessdata_dir
    d = tessdata_dir()
    have = sorted(f[:-12] for f in os.listdir(d) if f.endswith(".traineddata"))
    row("(optional) tessdata cache", True, f"{d} [{', '.join(have) or 'empty; downloaded on first use'}]")
    print("all required pieces present" if ok else "some required pieces are missing")
    return 0 if ok else 1


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "doctor":
        sys.exit(doctor())
    if args.cmd == "gui":
        try:
            from .gui import main as gui_main
        except ImportError as e:
            sys.exit(f"the interface needs PySide6: pip install 'realkniga[gui]' ({e})")
        sys.exit(gui_main(([args.input] if args.input else []) + (["--smoke-test"] if args.smoke_test else [])))
    is_djvu = args.input.lower().endswith((".djvu", ".djv"))
    args.formats = {f.strip() for f in (args.formats or ("pdf,djvu,txt" if is_djvu else "pdf,txt")).split(",")
                    if f.strip()}
    bad = args.formats - {"pdf", "djvu", "txt"}
    if bad:
        sys.exit(f"unknown format(s): {', '.join(bad)}")
    if args.tesseract == "auto":
        args.tesseract = None
    if not os.path.exists(args.input):
        sys.exit(f"not found: {args.input}")
    mode = args.mode
    if mode == "auto":
        mode = "scan" if is_djvu else "photo"
    from . import pipeline
    if mode == "scan":
        if not is_djvu:
            sys.exit("scan mode needs a DjVu file; for PDFs or images use --mode photo ")
        pipeline.run_djvu(args)
    else:
        pipeline.run_photos(args)


if __name__ == "__main__":
    main()
