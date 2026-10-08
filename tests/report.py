"""Saving benchmark results and turning them into the README's chart, table and examples.

benchmarks/results.json  the latest full run (what every new run is compared against)
benchmarks/history.csv   one row per run, sample and system, for tracking over time
docs/benchmark.svg       the chart shown in the README
README.md                the section between the benchmark markers is regenerated
"""
import csv
import datetime
import json
import os
import re
import subprocess
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_JSON = os.path.join(ROOT, "benchmarks", "results.json")
HISTORY_CSV = os.path.join(ROOT, "benchmarks", "history.csv")
CHART = os.path.join(ROOT, "docs", "benchmark.svg")
README = os.path.join(ROOT, "README.md")
SITE = os.path.join(ROOT, "docs", "index.html")
START, END = "<!-- benchmark:start -->", "<!-- benchmark:end -->"

LABELS = {"tesseract": "Tesseract alone", "paddleocr": "PaddleOCR alone", "darealkniga": "daRealKniga"}
COLORS = {"tesseract": "#a3abb5", "paddleocr": "#8cb8d9", "darealkniga": "#2b4f97"}


def load():
    try:
        with open(RESULTS_JSON, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _environment():
    env = {}
    try:
        from importlib.metadata import version
        import darealkniga
        env["darealkniga"] = darealkniga.__version__
        for p in ("paddleocr", "paddlepaddle"):
            env[p] = version(p)
        from darealkniga import ocr
        if ocr.tesseract_backend(None) == "local":
            v = subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.split()
        else:
            v = subprocess.run(["docker", "run", "--rm", ocr.DOCKER_IMAGE, "tesseract", "--version"],
                               capture_output=True, text=True).stdout.split()
        env["tesseract"] = v[1] if len(v) > 1 else "?"
    except Exception:  # noqa: BLE001  (informational only)
        pass
    return env


def _commit():
    r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", "darealkniga"],
                           capture_output=True, text=True).stdout.strip()
    return (r.stdout.strip() or "unknown") + ("+changes" if dirty else "")


def save(results):
    run = {"date": datetime.date.today().isoformat(), "commit": _commit(), "environment": _environment(),
           "samples": results}
    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    new = not os.path.exists(HISTORY_CSV)
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "commit", "darealkniga", "sample", "system", "words", "word_acc", "char_acc"])
        for name, r in results.items():
            for system, s in r["systems"].items():
                w.writerow([run["date"], run["commit"], run["environment"].get("darealkniga", ""), name, system,
                            s["words"], f"{s['word_f1']:.4f}", f"{s['char_acc']:.4f}"])
    with open(CHART, "w", encoding="utf-8") as f:
        f.write(chart(run))
    update_readme(run)
    update_site(run)


# ------------------------------------------------------------------ summary numbers

def errors(s):
    return 1 - s["word_f1"]


def summary(run):
    """Average word-error ratios over the samples: how many times fewer words daRealKniga misreads."""
    out = {}
    for other in ("tesseract", "paddleocr"):
        pairs = [(errors(r["systems"][other]), errors(r["systems"]["darealkniga"]))
                 for r in run["samples"].values() if other in r["systems"]]
        if pairs:
            a, b = sum(p[0] for p in pairs) / len(pairs), sum(p[1] for p in pairs) / len(pairs)
            out[other] = a / max(b, 1e-6)
    return out


# ------------------------------------------------------------------ chart

def chart(run):
    """Horizontal grouped bars of misread words (lower is better), one group per sample."""
    samples = list(run["samples"].items())
    W, left, right, top = 820, 250, 70, 92
    bar, gap, group_gap = 15, 3, 26
    group_h = 3 * bar + 2 * gap
    H = top + len(samples) * (group_h + group_gap) + 52
    vmax = max(errors(s) for _, r in samples for s in r["systems"].values())
    vmax = max(0.05, (int(vmax * 100 / 5) + 1) * 5 / 100)          # round the axis up to 5 %
    scale = (W - left - right) / vmax
    sm = summary(run)
    sub = " and ".join(f"{v:.1f}× fewer words than {LABELS[k]}" for k, v in sm.items())
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" rx="14" fill="#ffffff" stroke="#d0d7de"/>',
         f'<text x="24" y="38" font-size="20" font-weight="700" fill="#1f2328">Words misread (lower is better)</text>',
         f'<text x="24" y="62" font-size="13.5" fill="#57606a">daRealKniga misreads on average {escape(sub)}.</text>']
    # legend
    x = W - right - 3 * 128 + 10
    for k in ("tesseract", "paddleocr", "darealkniga"):
        o.append(f'<rect x="{x}" y="27" width="12" height="12" rx="2" fill="{COLORS[k]}"/>'
                 f'<text x="{x + 17}" y="37.5" font-size="12.5" fill="#1f2328">{LABELS[k]}</text>')
        x += 128
    # grid
    for t in range(0, int(round(vmax * 100)) + 1, 5):
        gx = left + t / 100 * scale
        o.append(f'<line x1="{gx:.1f}" y1="{top - 8}" x2="{gx:.1f}" y2="{H - 40}" stroke="#eaeef2"/>'
                 f'<text x="{gx:.1f}" y="{H - 22}" font-size="11.5" fill="#57606a" text-anchor="middle">{t}%</text>')
    y = top
    for name, r in samples:
        o.append(f'<text x="{left - 14}" y="{y + group_h / 2 - 2:.1f}" font-size="13.5" font-weight="600" '
                 f'fill="#1f2328" text-anchor="end">{escape(r["title"])}</text>'
                 f'<text x="{left - 14}" y="{y + group_h / 2 + 15:.1f}" font-size="11.5" fill="#57606a" '
                 f'text-anchor="end">{escape(name)} · {r["systems"]["darealkniga"]["words"]} words'
                 f'{" · exact reference" if r.get("synthetic") else ""}</text>')
        for k in ("tesseract", "paddleocr", "darealkniga"):
            s = r["systems"].get(k)
            if s:
                w = max(1.5, errors(s) * scale)
                bold = ' font-weight="700"' if k == "darealkniga" else ""
                o.append(f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{bar}" rx="3" fill="{COLORS[k]}"/>'
                         f'<text x="{left + w + 6:.1f}" y="{y + bar - 3.5}" font-size="12"{bold} '
                         f'fill="#1f2328">{100 * errors(s):.1f}%</text>')
            y += bar + gap
        y += group_gap - gap
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ------------------------------------------------------------------ README

def _mark(word, ref, bold=lambda s: f"**{s}**", esc=lambda s: s):
    """A reading for the examples table: letters from the wrong alphabet in bold (they look
    identical on screen), and a check mark when the reading is right."""
    if word is None:
        return "–"
    if word.lower() == ref.lower():
        return f"{esc(word)} ✓"
    def alpha(ch):
        return "cyr" if "\u0400" <= ch <= "\u04ff" else "lat" if ch.isascii() and ch.isalpha() else None
    want = {alpha(c) for c in ref if alpha(c)}
    if len(want) != 1:
        return esc(word)
    want = want.pop()
    out, cur, bad = [], "", None
    for c in word:
        b = alpha(c) is not None and alpha(c) != want
        if b != bad and cur:
            out.append(bold(esc(cur)) if bad else esc(cur))
            cur = ""
        cur += c
        bad = b
    if cur:
        out.append(bold(esc(cur)) if bad else esc(cur))
    return "".join(out)


def pick_examples(run):
    """Up to 12 distinct words plain OCR got wrong and daRealKniga got right: first those both
    engines got wrong (only the combination reads them), then alphabet mix-ups."""
    ex = [e for r in run["samples"].values() for e in r.get("fixes", [])]

    def order(e):
        paddle_ok = bool(e.get("paddleocr")) and e["paddleocr"].lower() == e["ref"].lower()
        mixed = bool(re.search(r"[A-Za-z]", e["ref"]) or re.search(r"[A-Za-z]", e["tesseract"]))
        return (paddle_ok, not mixed)
    seen, uniq = set(), []
    for e in sorted(ex, key=order):
        if e["ref"].lower() not in seen:
            seen.add(e["ref"].lower())
            uniq.append(e)
    both = [e for e in uniq if not order(e)[0]][:7]
    mixed = [e for e in uniq if e not in both and not order(e)[1]][:5]
    return both + mixed


def readme_section(run):
    sm = summary(run)
    lines = [START, "", "![Words misread by Tesseract alone, PaddleOCR alone and daRealKniga](docs/benchmark.svg)", ""]
    if sm:
        parts = [f"**{v:.1f}× fewer words** than {LABELS[k]}" for k, v in sm.items()]
        lines += [f"Across the samples, daRealKniga misreads on average {' and '.join(parts)}. "
                  "All three read the same original page images with the same OCR models; the difference is "
                  "daRealKniga's page cleanup, the combination of both engines and its corrections.", ""]
    lines += ["| Sample | Words | Tesseract alone | PaddleOCR alone | **daRealKniga** |", "|---|---:|---:|---:|---:|"]
    for name, r in run["samples"].items():
        cells = []
        for k in ("tesseract", "paddleocr", "darealkniga"):
            s = r["systems"].get(k)
            v = f"{100 * s['word_f1']:.1f}%" if s else "–"
            cells.append(f"**{v}**" if k == "darealkniga" else v)
        lines.append(f"| {r['title']} <br><sub>{r['description']}</sub> | {r['systems']['darealkniga']['words']} | "
                     + " | ".join(cells) + " |")
    lines += ["", "<sub>Word accuracy: the share of words read exactly right (letter case aside; a Latin "
              "letter in place of its Cyrillic look-alike counts as an error, because it breaks search). "
              "Synthetic pages have an exact reference; for real scans the reference is the book's existing "
              "text layer, itself OCR, so those numbers measure agreement.</sub>", ""]
    ex = pick_examples(run)
    if ex:
        lines += ["<details><summary><b>Examples: words plain OCR got wrong and daRealKniga got right</b></summary>",
                  "", "| Printed | Tesseract alone | PaddleOCR alone | daRealKniga |", "|---|---|---|---|"]
        for e in ex:
            p = e.get("paddleocr")
            lines.append(f"| {e['ref']} | {_mark(e['tesseract'], e['ref'])} | {_mark(p, e['ref'])} | "
                         f"{_mark(e['darealkniga'], e['ref'])} |")
        lines += ["", "<sub>**Bold** letters come from the wrong alphabet: they look identical on screen but "
                  "make the word unsearchable.</sub>", "", "</details>", ""]
    env = run.get("environment", {})
    lines += [f"<sub>Last run {run['date']} · daRealKniga {env.get('darealkniga', '?')} · "
              f"Tesseract {env.get('tesseract', '?')} · PaddleOCR {env.get('paddleocr', '?')}. "
              "Reproduce with `python tests/accuracy.py --save`; see [Tests](#tests).</sub>", "", END]
    return "\n".join(lines)


def update_readme(run):
    with open(README, encoding="utf-8") as f:
        s = f.read()
    sec = readme_section(run)
    if START in s and END in s:
        s = s[:s.index(START)] + sec + s[s.index(END) + len(END):]
    else:
        raise RuntimeError(f"README.md has no {START} … {END} markers")
    with open(README, "w", encoding="utf-8") as f:
        f.write(s)


# ------------------------------------------------------------------ project page (docs/index.html)

def site_section(run):
    """The benchmark part of the project page: summary, table and examples, as HTML."""
    sm = summary(run)
    o = [START]
    if sm:
        parts = [f"<strong>{v:.1f}&times; fewer words</strong> than {escape(LABELS[k])}" for k, v in sm.items()]
        o.append(f'<p class="lead">daRealKniga misreads on average {" and ".join(parts)}.</p>')
    o.append('<img class="chart" src="benchmark.svg" alt="Words misread by Tesseract alone, PaddleOCR alone '
             'and daRealKniga, per sample (lower is better)">')
    o.append('<div class="scroll"><table class="results"><thead><tr><th>Sample</th><th>Tesseract alone</th>'
             '<th>PaddleOCR alone</th><th>daRealKniga</th></tr></thead><tbody>')
    for r in run["samples"].values():
        cells = []
        for k in ("tesseract", "paddleocr", "darealkniga"):
            s = r["systems"].get(k)
            v = f"{100 * s['word_f1']:.1f}%" if s else "–"
            cells.append(f'<td class="num{" best" if k == "darealkniga" else ""}">{v}</td>')
        o.append(f'<tr><td>{escape(r["title"])}<small>{escape(r["description"])}</small></td>{"".join(cells)}</tr>')
    o.append("</tbody></table></div>")
    o.append('<p class="note">Word accuracy: the share of words read exactly right. A Latin letter in place of '
             'its Cyrillic look-alike counts as an error, because the word can no longer be found by search.</p>')
    ex = pick_examples(run)
    if ex:
        b = lambda s: f'<b class="wrong">{s}</b>'
        o.append('<h3>Words plain OCR got wrong</h3><div class="scroll"><table class="examples"><thead><tr>'
                 '<th>Printed</th><th>Tesseract alone</th><th>PaddleOCR alone</th><th>daRealKniga</th></tr></thead>'
                 '<tbody>')
        for e in ex:
            cells = [_mark(e[k] if k != "paddleocr" else e.get(k), e["ref"], b, escape)
                     for k in ("tesseract", "paddleocr", "darealkniga")]
            o.append(f'<tr><td>{escape(e["ref"])}</td>' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        o.append('</tbody></table></div><p class="note"><b class="wrong">Highlighted</b> letters come from the '
                 'wrong alphabet: they look identical on screen, but the word can\'t be searched.</p>')
    env = run.get("environment", {})
    o.append(f'<p class="note">Measured {run["date"]} with daRealKniga {escape(env.get("darealkniga", "?"))}, '
             f'Tesseract {escape(env.get("tesseract", "?"))} and PaddleOCR {escape(env.get("paddleocr", "?"))}. '
             'All three read the same page images with the same OCR models.</p>')
    o.append(END)
    return "\n".join(o)


def update_site(run):
    try:
        with open(SITE, encoding="utf-8") as f:
            s = f.read()
    except OSError:
        return
    if START in s and END in s:
        s = s[:s.index(START)] + site_section(run) + s[s.index(END) + len(END):]
        with open(SITE, "w", encoding="utf-8") as f:
            f.write(s)
