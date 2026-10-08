import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def pytest_terminal_summary(terminalreporter):
    import accuracy
    import report
    if not accuracy.RESULTS:
        return
    results = {name: {"systems": systems} for name, systems in accuracy.RESULTS}
    tr = terminalreporter
    tr.section("OCR accuracy: daRealKniga vs. plain Tesseract and plain PaddleOCR")
    for line in accuracy.table(results, report.load()).splitlines():
        tr.write_line(line)
    tr.write_line("word acc: share of words read right (order-independent); chars: 1 - edit distance / length. "
                  "Change is against benchmarks/results.json (update it with: python tests/accuracy.py --save).")
