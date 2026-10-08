"""End-to-end accuracy tests: a few pages per sample, daRealKniga against plain Tesseract and
plain PaddleOCR (downloads ~40 MB once, a few minutes).

    pytest -m accuracy            # only these
    pytest -m "not accuracy"      # skip them
"""
import re
import shutil
import statistics
import subprocess

import pytest

import accuracy


pytestmark = pytest.mark.accuracy


def _needs(sample):
    if sample.source.endswith(".djvu") or (sample.reference or "").endswith(".djvu"):
        for t in ("djvused", "djvm", "djvutxt", "ddjvu"):
            if not shutil.which(t):
                pytest.skip(f"{t} not installed")
    keys = ["PT_Serif-Regular.ttf", "PT_Serif-Bold.ttf"] if sample.synthetic else \
        [sample.source] + ([sample.reference] if sample.reference else [])
    try:
        for k in keys:
            accuracy.fetch(k)
    except OSError as e:
        pytest.skip(f"sample data not available: {e}")


@pytest.mark.parametrize("sample", accuracy.SAMPLES, ids=lambda s: s.name)
def test_accuracy(sample, tmp_path):
    _needs(sample)
    systems, outputs, _, out = accuracy.run(sample, str(tmp_path))
    assert "pdf" in outputs, "no PDF written"
    accuracy.RESULTS.append((sample.name, systems))
    for ext, sc in outputs.items():
        assert sc["word_f1"] >= sample.min_word_f1, \
            f"{sample.name}/{ext}: word accuracy {sc['word_f1']:.1%} < {sample.min_word_f1:.0%}"
        assert sc["char_acc"] >= sample.min_char_acc, \
            f"{sample.name}/{ext}: char accuracy {sc['char_acc']:.1%} < {sample.min_char_acc:.0%}"
    # the point of the project: better than either engine on its own
    for other in ("tesseract", "paddleocr"):
        if other in systems:
            assert systems["darealkniga"]["word_f1"] >= systems[other]["word_f1"], \
                f"{sample.name}: daRealKniga {systems['darealkniga']['word_f1']:.1%} < {other} {systems[other]['word_f1']:.1%}"
    _check_pdf(f"{out}/{sample.name}.pdf", len(sample.pages))
    if "djvu" in outputs:
        _check_djvu(f"{out}/{sample.name}.djvu", len(sample.pages))


def _check_pdf(path, n):
    import pymupdf
    with pymupdf.open(path) as d:
        assert len(d) == n
        sizes = {(round(p.rect.width, 1), round(p.rect.height, 1)) for p in d}
        assert len(sizes) == 1, f"page sizes differ: {sizes}"
        for p in d:
            assert len(p.get_text().split()) > 20, f"page {p.number + 1} has (almost) no text"
            # every word of the text layer lies on the page (glyph ascent may poke out a little)
            r = p.rect
            for x0, y0, x1, y1, *_ in p.get_text("words"):
                assert -3 <= x0 and x1 <= r.width + 3 and -3 <= y0 and y1 <= r.height + 3, (x0, y0, x1, y1)


def _check_djvu(path, n):
    dump = subprocess.run(["djvudump", path], capture_output=True, text=True, check=True).stdout
    info = [(int(w), int(d)) for w, h, d in re.findall(r"INFO \[\d+\]\s+DjVu (\d+)x(\d+), v\d+, (\d+) dpi", dump)]
    assert len(info) == n
    widths = [w / d for w, d in info]
    assert max(widths) - min(widths) < 0.02 * statistics.median(widths), f"display widths differ: {widths}"
    for i in range(1, n + 1):
        txt = subprocess.run(["djvused", path, "-e", f"select {i}; print-pure-txt"],
                             capture_output=True, text=True, check=True).stdout
        assert len(txt.split()) > 20, f"DjVu page {i} has (almost) no text"
