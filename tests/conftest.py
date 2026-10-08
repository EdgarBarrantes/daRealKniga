import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def pytest_terminal_summary(terminalreporter):
    from accuracy import HEADER, RESULTS, fmt_row
    if not RESULTS:
        return
    tr = terminalreporter
    tr.section("OCR accuracy vs. the books' original text layers")
    tr.write_line(HEADER)
    for name, ext, sc in RESULTS:
        tr.write_line(fmt_row(name, ext, sc))
    tr.write_line("word F1/recall/precision: share of words matching the reference, order-independent; "
                  "chars: 1 - character edit distance / length, in reading order.")
