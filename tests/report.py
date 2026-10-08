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

def chart(run, lang="en"):
    """Horizontal grouped bars of misread words (lower is better), one group per sample."""
    tx = SITE_TEXT[lang]
    samples = list(run["samples"].items())
    titles = {name: sample_title(name, r, lang)[0] for name, r in samples}
    left = max(250, int(max(len(x) for x in titles.values()) * 7.7) + 26)
    W, right = 570 + left, 70
    # the summary line wraps in two when it's too long; the legend moves under it when the title
    # leaves no room beside it (rough text widths: these charts are made without a font engine)
    sub = re.sub(r"<[^>]+>", "", lead(run, lang))
    subs = [sub]
    if len(sub) * 6.9 > W - 48:
        cut = min((m.end() for m in re.finditer(r", | and | и | et ", sub)), key=lambda i: abs(i - len(sub) / 2))
        subs = [sub[:cut].rstrip(), sub[cut:].strip()]
    legend_x = W - right - 3 * 128 + 10
    legend_below = 24 + len(tx["chart_title"]) * 11.6 > legend_x - 16
    sub_y = [62 + 18 * i for i in range(len(subs))]
    legend_y = sub_y[-1] + 22 if legend_below else 27
    top = (legend_y + 40) if legend_below else 92 + 18 * (len(subs) - 1)
    bar, gap, group_gap = 15, 3, 26
    group_h = 3 * bar + 2 * gap
    H = top + len(samples) * (group_h + group_gap) + 52
    vmax = max(errors(s) for _, r in samples for s in r["systems"].values())
    vmax = max(0.05, (int(vmax * 100 / 5) + 1) * 5 / 100)          # round the axis up to 5 %
    scale = (W - left - right) / vmax
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" rx="14" fill="#ffffff" stroke="#d0d7de"/>',
         f'<text x="24" y="38" font-size="20" font-weight="700" fill="#1f2328">{escape(tx["chart_title"])}</text>']
    for y_, line in zip(sub_y, subs):
        o.append(f'<text x="24" y="{y_}" font-size="13.5" fill="#57606a">{escape(line)}</text>')
    # legend
    x = 24 if legend_below else legend_x
    for k in ("tesseract", "paddleocr", "darealkniga"):
        o.append(f'<rect x="{x}" y="{legend_y}" width="12" height="12" rx="2" fill="{COLORS[k]}"/>'
                 f'<text x="{x + 17}" y="{legend_y + 10.5}" font-size="12.5" fill="#1f2328">{escape(tx[k])}</text>')
        x += 150 if legend_below else 128
    # grid
    for t in range(0, int(round(vmax * 100)) + 1, 5):
        gx = left + t / 100 * scale
        o.append(f'<line x1="{gx:.1f}" y1="{top - 8}" x2="{gx:.1f}" y2="{H - 40}" stroke="#eaeef2"/>'
                 f'<text x="{gx:.1f}" y="{H - 22}" font-size="11.5" fill="#57606a" text-anchor="middle">{t}%</text>')
    y = top
    for name, r in samples:
        o.append(f'<text x="{left - 14}" y="{y + group_h / 2 - 2:.1f}" font-size="13.5" font-weight="600" '
                 f'fill="#1f2328" text-anchor="end">{escape(titles[name])}</text>'
                 f'<text x="{left - 14}" y="{y + group_h / 2 + 15:.1f}" font-size="11.5" fill="#57606a" '
                 f'text-anchor="end">{escape(name)} · {tx["words"].format(n=r["systems"]["darealkniga"]["words"])}'
                 f'{" · " + tx["exact"] if r.get("synthetic") else ""}</text>')
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

def site_section(run, lang="en"):
    """The benchmark part of a project page: summary, chart, table and examples, as HTML."""
    t = SITE_TEXT[lang]
    up = "" if lang == "en" else "../"
    chart_file = "benchmark.svg" if lang == "en" else f"benchmark-{lang}.svg"
    o = [START, f'<p class="lead">{lead(run, lang)}</p>',
         f'<img class="chart" src="{up}{chart_file}" alt="{escape(t["chart_alt"])}">',
         f'<div class="scroll"><table class="results"><thead><tr><th>{t["sample"]}</th><th>{t["tesseract"]}</th>'
         f'<th>{t["paddleocr"]}</th><th>daRealKniga</th></tr></thead><tbody>']
    for name, r in run["samples"].items():
        cells = []
        for k in ("tesseract", "paddleocr", "darealkniga"):
            sc = r["systems"].get(k)
            v = pct(sc["word_f1"], lang) if sc else "–"
            cells.append(f'<td class="num{" best" if k == "darealkniga" else ""}">{v}</td>')
        title, desc = sample_title(name, r, lang)
        o.append(f'<tr><td>{escape(title)}<small>{escape(desc)}</small></td>{"".join(cells)}</tr>')
    o.append(f'</tbody></table></div><p class="note">{t["note_accuracy"]}</p>')
    ex = pick_examples(run)
    if ex:
        b = lambda x: f'<b class="wrong">{x}</b>'
        o.append(f'<h3>{t["examples"]}</h3><div class="scroll"><table class="examples"><thead><tr>'
                 f'<th>{t["printed"]}</th><th>{t["tesseract"]}</th><th>{t["paddleocr"]}</th><th>daRealKniga</th>'
                 f'</tr></thead><tbody>')
        for e in ex:
            cells = [_mark(e.get(k), e["ref"], b, escape) for k in ("tesseract", "paddleocr", "darealkniga")]
            o.append(f'<tr><td>{escape(e["ref"])}</td>' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        o.append(f'</tbody></table></div><p class="note">{t["note_wrong"]}</p>')
    env = run.get("environment", {})
    o.append('<p class="note">' + t["measured"].format(
        date=run["date"], v=escape(env.get("darealkniga", "?")), t=escape(env.get("tesseract", "?")),
        p=escape(env.get("paddleocr", "?"))) + "</p>")
    o.append(END)
    return "\n".join(o)


def update_site(run):
    """Refresh the benchmark part of every project page, and the translated charts."""
    for lang, path in SITES.items():
        if lang != "en":
            with open(os.path.join(ROOT, "docs", f"benchmark-{lang}.svg"), "w", encoding="utf-8") as f:
                f.write(chart(run, lang))
        try:
            with open(path, encoding="utf-8") as f:
                s = f.read()
        except OSError:
            continue
        if START in s and END in s:
            s = s[:s.index(START)] + site_section(run, lang) + s[s.index(END) + len(END):]
            with open(path, "w", encoding="utf-8") as f:
                f.write(s)


def pct(x, lang):
    v = f"{100 * x:.1f}"
    return (v if lang == "en" else v.replace(".", ",")) + ("\u00a0%" if lang == "fr" else "%")


def times(v, lang):
    s = f"{v:.1f}"
    return s if lang == "en" else s.replace(".", ",")


def lead(run, lang="en"):
    """'daRealKniga misreads on average 2.2x fewer words than ...' in the page's language."""
    sm = summary(run)
    return SITE_TEXT[lang]["lead"].format(t=times(sm.get("tesseract", 0), lang), p=times(sm.get("paddleocr", 0), lang))


def sample_title(name, r, lang):
    if lang == "en":
        return r["title"], r["description"]
    return SAMPLE_TEXT[lang].get(name, (r["title"], r["description"]))


SITES = {lang: os.path.join(ROOT, "docs", *([] if lang == "en" else [lang]), "index.html")
         for lang in ("en", "ru", "bg", "fr")}

SITE_TEXT = {
    "en": dict(
        chart_title="Words misread (lower is better)", tesseract="Tesseract alone", paddleocr="PaddleOCR alone",
        darealkniga="daRealKniga", words="{n} words", exact="exact reference",
        lead="daRealKniga misreads on average <strong>{t}× fewer words</strong> than Tesseract alone and "
             "<strong>{p}× fewer words</strong> than PaddleOCR alone.",
        chart_alt="Words misread by Tesseract alone, PaddleOCR alone and daRealKniga, per sample (lower is better)",
        sample="Sample", printed="Printed", examples="Words plain OCR got wrong",
        note_accuracy="Word accuracy: the share of words read exactly right. A Latin letter in place of its "
                      "Cyrillic look-alike counts as an error, because the word can no longer be found by search.",
        note_wrong='<b class="wrong">Highlighted</b> letters come from the wrong alphabet: they look identical on '
                   "screen, but the word can't be searched.",
        measured="Measured {date} with daRealKniga {v}, Tesseract {t} and PaddleOCR {p}. All three read the same "
                 "page images with the same OCR models."),
    "ru": dict(
        chart_title="Ошибочно прочитанные слова (чем меньше, тем лучше)", tesseract="Только Tesseract",
        paddleocr="Только PaddleOCR", darealkniga="daRealKniga", words="слов: {n}", exact="точный эталон",
        lead="В среднем daRealKniga ошибается в словах <strong>в {t} раза реже</strong>, чем один Tesseract, и "
             "<strong>в {p} раза реже</strong>, чем один PaddleOCR.",
        chart_alt="Доля ошибочно прочитанных слов: только Tesseract, только PaddleOCR и daRealKniga по каждому "
                  "образцу (чем меньше, тем лучше)",
        sample="Образец", printed="Напечатано", examples="Слова, в которых ошибается обычный OCR",
        note_accuracy="Точность по словам: доля слов, прочитанных абсолютно верно. Латинская буква вместо похожей "
                      "кириллической считается ошибкой: такое слово уже не найти поиском.",
        note_wrong='<b class="wrong">Выделенные</b> буквы взяты из другого алфавита: на экране они выглядят так же, '
                   "но слово перестаёт находиться поиском.",
        measured="Измерено {date}: daRealKniga {v}, Tesseract {t}, PaddleOCR {p}. Все три читают одни и те же "
                 "изображения страниц одними и теми же моделями OCR."),
    "bg": dict(
        chart_title="Сгрешени думи (колкото по-малко, толкова по-добре)", tesseract="Само Tesseract",
        paddleocr="Само PaddleOCR", darealkniga="daRealKniga", words="думи: {n}", exact="точен еталон",
        lead="Средно daRealKniga греши в <strong>{t} пъти по-малко думи</strong> от самия Tesseract и в "
             "<strong>{p} пъти по-малко думи</strong> от самия PaddleOCR.",
        chart_alt="Дял на сгрешените думи: само Tesseract, само PaddleOCR и daRealKniga за всеки образец "
                  "(колкото по-малко, толкова по-добре)",
        sample="Образец", printed="Отпечатано", examples="Думи, които обикновеният OCR чете грешно",
        note_accuracy="Точност по думи: делът на думите, прочетени напълно вярно. Латинска буква на мястото на "
                      "подобна кирилска се брои за грешка, защото думата вече не може да се намери с търсене.",
        note_wrong='<b class="wrong">Отбелязаните</b> букви са от другата азбука: на екрана изглеждат същите, но '
                   "думата не може да се намери с търсене.",
        measured="Измерено на {date} с daRealKniga {v}, Tesseract {t} и PaddleOCR {p}. И трите четат едни и същи "
                 "изображения на страниците с едни и същи модели за OCR."),
    "fr": dict(
        chart_title="Mots mal lus (moins, c’est mieux)", tesseract="Tesseract seul", paddleocr="PaddleOCR seul",
        darealkniga="daRealKniga", words="{n} mots", exact="référence exacte",
        lead="En moyenne, daRealKniga lit mal <strong>{t} fois moins de mots</strong> que Tesseract seul et "
             "<strong>{p} fois moins</strong> que PaddleOCR seul.",
        chart_alt="Part des mots mal lus par Tesseract seul, PaddleOCR seul et daRealKniga, par échantillon "
                  "(moins, c’est mieux)",
        sample="Échantillon", printed="Imprimé", examples="Mots que l’OCR classique lit mal",
        note_accuracy="Précision par mot : la part des mots lus exactement. Une lettre latine à la place de son "
                      "sosie cyrillique compte comme une erreur, car le mot devient introuvable par la recherche.",
        note_wrong='Les lettres <b class="wrong">surlignées</b> viennent du mauvais alphabet : identiques à '
                   "l’écran, elles rendent le mot introuvable.",
        measured="Mesuré le {date} avec daRealKniga {v}, Tesseract {t} et PaddleOCR {p}. Les trois lisent les mêmes "
                 "images de pages avec les mêmes modèles d’OCR."),
}

SAMPLE_TEXT = {  # (title, description) of each benchmark sample on the translated pages
    "ru": {
        "mixed-bg": ("Страница учебника: болгарский + английский",
                     "синтетический скан страницы учебника: болгарский текст с английскими словами и предложениями"),
        "mixed-ru": ("Техническая страница: русский + английский",
                     "синтетический скан страницы руководства: русский текст с английскими терминами, командами и "
                     "названиями"),
        "photo-bg": ("Фото с телефона: болгарский + английский",
                     "синтетическое фото страницы путеводителя (изогнутой, в перспективе, при неровном свете): "
                     "болгарский текст с английскими названиями и фразами"),
        "djvu-ru": ("Русский роман, скан DjVu", "режим сканов DjVu, русская проза (Вазов, «Под игом», 1970)"),
        "pdf-ru": ("Русский роман, скан PDF",
                   "PDF того же издания (обрезанные плоские сканы); эталон — текстовый слой DjVu"),
        "pdf-bg": ("Болгарские стихи, PDF низкого разрешения",
                   "болгарская поэзия и проза, развороты 133 dpi (Вазов, «Събрани съчинения», т. 4, 1974); "
                   "в самом эталоне много ошибок OCR"),
    },
    "bg": {
        "mixed-bg": ("Страница от учебник: български + английски",
                     "синтетично сканиране на страница от учебник: български текст с английски думи и изречения"),
        "mixed-ru": ("Техническа страница: руски + английски",
                     "синтетично сканиране на страница от ръководство: руски текст с английски термини, команди и "
                     "имена"),
        "photo-bg": ("Снимка с телефон: български + английски",
                     "синтетична снимка на страница от пътеводител (извита, в перспектива, при неравна светлина): "
                     "български текст с английски имена и изрази"),
        "djvu-ru": ("Руски роман, сканиране в DjVu", "режим за DjVu сканирания, руска проза (Вазов, „Под игом“, 1970)"),
        "pdf-ru": ("Руски роман, сканиране в PDF",
                   "PDF от същото издание (изрязани плоски сканирания); еталонът е текстовият слой на DjVu"),
        "pdf-bg": ("Български стихове, PDF с ниска резолюция",
                   "българска поезия и проза, разгърнати страници при 133 dpi (Вазов, „Събрани съчинения“, т. 4, "
                   "1974); самият еталон съдържа много грешки от OCR"),
    },
    "fr": {
        "mixed-bg": ("Page de manuel : bulgare + anglais",
                     "scan synthétique d’une page de manuel de langue : du bulgare avec des mots et des phrases en "
                     "anglais"),
        "mixed-ru": ("Page technique : russe + anglais",
                     "scan synthétique d’une page de mode d’emploi : du russe avec des termes, des commandes et des "
                     "noms en anglais"),
        "photo-bg": ("Photo au téléphone : bulgare + anglais",
                     "photo synthétique d’une page de guide de voyage (courbée, en perspective, éclairage inégal) : "
                     "du bulgare avec des noms et des expressions en anglais"),
        "djvu-ru": ("Roman russe, scan DjVu", "mode scan DjVu, prose russe (Vazov, « Sous le joug », 1970)"),
        "pdf-ru": ("Roman russe, scan PDF",
                   "PDF de la même édition (scans à plat recadrés) ; référence : la couche texte du DjVu"),
        "pdf-bg": ("Poèmes bulgares, PDF basse résolution",
                   "poésie et prose bulgares, doubles pages à 133 dpi (Vazov, Œuvres, t. 4, 1974) ; la référence "
                   "contient elle-même beaucoup d’erreurs d’OCR"),
    },
}
