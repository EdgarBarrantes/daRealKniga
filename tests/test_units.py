"""Fast unit tests (no downloads, no OCR engines)."""
import numpy as np
import pikepdf
import pytest
from PIL import Image

from darealkniga import enhance, fuse, i18n, langs, pdf, receipt, textlayer
from darealkniga.util import natural_key, parse_pages

import accuracy


@pytest.fixture(autouse=True)
def bulgarian():
    fuse.configure(langs.parse("bul+eng"))


def test_parse_pages():
    assert parse_pages("1-3,7,9-", 10) == [1, 2, 3, 7, 9, 10]
    assert parse_pages(None, 3) == [1, 2, 3]
    assert parse_pages("0,5,99", 6) == [5]


def test_natural_sort():
    assert sorted(["p10.jpg", "p2.jpg", "p1.jpg"], key=natural_key) == ["p1.jpg", "p2.jpg", "p10.jpg"]


def test_langs():
    lg = langs.parse("bul+eng")
    assert (lg.cyr_lex, lg.lat_lex, lg.paddle_rec) == ("bg", "en", "cyrillic_PP-OCRv5_mobile_rec")
    assert langs.parse("eng").paddle_rec == "en_PP-OCRv5_mobile_rec"
    assert not langs.parse("deu").cyrillic


@pytest.mark.parametrize("word,expected", [
    ("xaoc", "хаос"),        # Latin look-alikes inside a Bulgarian word
    ("Mама", "Мама"),        # mixed scripts
    ("ка́к", "как"),          # stress mark removed
    ("house", "house"),      # real English word untouched
])
def test_clean(word, expected):
    assert fuse.clean(word) == expected


def test_choose_prefers_known_reading():
    assert fuse.choose("ce", "се", "cyr") == "се"
    assert fuse.choose("Bulgarian", "Bulgarian", "lat") == "Bulgarian"


@pytest.mark.parametrize("t, p, expected", [
    ("0105111658", "0105111058", "0105111058"),   # same number, one digit differs: PaddleOCR
    ("02.08.", "02.08.2026", "02.08.2026"),       # Tesseract cut the number short
    ("1.9558", "=1.95583", "1.95583"),            # stray mark before PaddleOCR's number
    ("163", "349", "163"),                        # a neighbouring number, not the same one
    ("1125671110", "СТАНЦИОННА", "1125671110"),   # PaddleOCR's word is not a number
    (":0,97733", "Дневна:0,12927Нощна:0,07733", "0,07733"),  # a number inside PaddleOCR's glued words
    ("0,12927", "Дневна:0,12927Нощна:0,07733", "0,12927"),
    ("2026", "за08/2026", "2026"),                # embedded numbers must match closely
    ("69.26", "69.26", "69.26"),
])
def test_choose_numbers_prefer_paddle(t, p, expected):
    # on receipts PaddleOCR reads digits far more reliably than Tesseract
    assert fuse.choose(t, p, "cyr") == expected


def test_fuse_keeps_paddle_numbers_tesseract_missed():
    """Tesseract read one tall box over two table rows ('163') and missed the next columns;
    PaddleOCR's confident numbers must not be dropped as 'covered' by that box."""
    tw = lambda t, b: {"t": t, "conf": 95.0, "box": b}
    pw = lambda t, b: {"t": t, "score": 1.0, "used": False, "box": b}
    tlines = [[tw("Нощна", [258, 1049, 336, 1071]), tw("3456", [1121, 1050, 1182, 1070]),
               tw("3619", [1250, 1051, 1309, 1071]), tw("163", [1425, 1022, 1469, 1073]),
               tw("0.0", [1650, 1022, 1960, 1080])]]
    pws = [pw("Нощна", [251, 1043, 341, 1076]), pw("3619", [1244, 1046, 1314, 1075]),
           pw("349", [1418, 1012, 1474, 1040]), pw("163", [1418, 1046, 1474, 1077]),
           pw("0.04103", [1673, 1045, 1794, 1078]), pw("6.68", [1878, 1047, 1949, 1080])]
    words = [w["t"] for l in fuse.fuse_page(tlines, pws) for w in l]
    for n in ("349", "0.04103", "6.68"):
        assert n in words
    assert words.count("163") == 1


def test_fuse_finds_the_same_number_on_the_line():
    """PaddleOCR's word positions are estimates: the matched word can be a neighbour
    ('СТАНЦИОННА'), while the same number sits elsewhere on the line."""
    tw = lambda t, b: {"t": t, "conf": 95.0, "box": b}
    pw = lambda t, b: {"t": t, "score": 1.0, "used": False, "box": b}
    tlines = [[tw("електромер", [100, 300, 260, 322]), tw("1125671110", [420, 300, 600, 322])]]
    pws = [pw("електромер", [100, 300, 260, 322]), pw("СТАНЦИОННА", [430, 296, 610, 318]),
           pw("1125071110189987", [400, 286, 700, 312])]
    words = [w["t"] for l in fuse.fuse_page(tlines, pws) for w in l]
    assert "1125071110189987" in words and "1125671110" not in words


def test_repair_cyr():
    assert fuse.repair_cyr("пещо") == "нещо"
    assert fuse.repair_cyr("Пешо") is None          # capitalised: probably a name
    assert fuse.repair_cyr("-ена") is None          # grammar fragment
    assert fuse.repair_cyr("пет") is None           # common word


def test_repair_page_needs_systematic_errors():
    one = [[{"t": "пещо", "box": [0, 0, 1, 1]}] + [{"t": "дума", "box": [0, 0, 1, 1]}] * 40]
    fuse.repair_page(one)
    assert one[0][0]["t"] == "пещо"  # a single hit is not enough
    many = [[{"t": w, "box": [0, 0, 1, 1]} for w in ["пещо", "пещо", "пещо", "дума", "дума"]]]
    fuse.repair_page(many)
    assert [w["t"] for w in many[0][:3]] == ["нещо"] * 3


def _line(*ws, alts=None):
    alts = alts or {}
    return [{"t": w, "box": [0, 0, 1, 1], **({"alt": alts[w]} if w in alts else {})} for w in ws]


def test_resolve_case():
    lines = [_line("Той", "казва", "МНОго", "неща", "за", "СИ", "живот", "и", "обла-", alts={"СИ": "си"}),
             _line("Ги.", "Още", "ДА", "има", "БЗНС"),
             _line("ГЛАВА", "ПЪРВА", "НАЧАЛО")]
    fuse.resolve_case(lines)
    words = [w["t"] for l in lines for w in l]
    assert words[2] == "Много"            # mixed case normalised (initial capital kept: could be a name)
    assert words[5] == "си"               # capitals mid-sentence, other engine read lower case
    assert words[9] == "ги."              # continues a hyphenated word
    assert words[10] == "Още"             # line start kept
    assert "БЗНС" in words                # acronym kept (no evidence against it)
    assert words[-3:] == ["ГЛАВА", "ПЪРВА", "НАЧАЛО"]   # all-caps heading kept
    assert all("alt" not in w for l in lines for w in l)


def test_write_text_joins_hyphens(tmp_path):
    page = {"lines": [[{"t": "Лич-"}], [{"t": "ността"}, {"t": "е"}], [{"t": "Б-"}], [{"t": "Г"}]]}
    f = tmp_path / "t.txt"
    textlayer.write_text([page, page], str(f))
    t = f.read_text(encoding="utf-8")
    assert t.split("\f")[0] == "Личността\nе\nБ-\nГ\n"
    assert t.count("\f") == 1


def test_rows_join_label_and_value():
    """Receipts: Tesseract reads the label column and the value column as separate blocks;
    rows put each printed row back on one line, left to right, top to bottom."""
    w = lambda t, x0, y0, x1, y1: {"t": t, "box": [x0, y0, x1, y1]}
    lines = [[w("Дневна", 10, 100, 80, 120)], [w("Нощна", 10, 130, 70, 150)],
             [w("32.45", 400, 102, 450, 121)], [w("6.68", 400, 131, 440, 151)],
             [w("Сума", 10, 200, 60, 220), w("общо", 65, 200, 110, 220)], [w("69.26", 400, 198, 450, 218)]]
    rows = textlayer.rows(lines)
    assert [[x["t"] for x in r] for r in rows] == [["Дневна", "32.45"], ["Нощна", "6.68"], ["Сума", "общо", "69.26"]]


def test_rows_follow_tilted_lines():
    """A tilted photo: each printed row drops 18 px from left to right (more than half a line
    height), so rows must follow the line pieces rather than the page's horizontal."""
    w = lambda t, x0, y0: {"t": t, "box": [x0, y0, x0 + 60, y0 + 20]}
    lines = [[w("Дневна", 10, 100), w("02.08.2026", 80, 103)], [w("Нощна", 10, 130), w("02.08.2026", 80, 133)],
             [w("6141", 300, 112), w("32.45", 380, 118)], [w("3456", 300, 142), w("6.68", 380, 148)]]
    rows = textlayer.rows(lines)
    assert [[x["t"] for x in r] for r in rows] == [["Дневна", "02.08.2026", "6141", "32.45"],
                                                    ["Нощна", "02.08.2026", "3456", "6.68"]]


def test_rows_follow_the_page_tilt_across_wide_gaps():
    """Labels on the left, values far right: over 900 px a 3% tilt drops 27 px, closer to the
    next row's label (30 px down) than to its own. The tilt measured from the line pieces
    themselves tells where each row continues."""
    def piece(words, y):  # words: [(text, x0)], 3% tilt
        return [{"t": t, "box": [x, y + 0.03 * x, x + 60, y + 0.03 * x + 20]} for t, x in words]
    lines = [piece([("Достъп", 10), ("/високо", 80), ("напрежение/", 150)], 100),
             piece([("Пренос", 10), ("/високо", 80), ("напрежение/", 150)], 130),
             piece([("0.00801", 820), ("4.11", 900)], 100), piece([("0.00499", 820), ("2.55", 900)], 130)]
    rows = textlayer.rows(lines)
    assert [[x["t"] for x in r] for r in rows] == [["Достъп", "/високо", "напрежение/", "0.00801", "4.11"],
                                                    ["Пренос", "/високо", "напрежение/", "0.00499", "2.55"]]


def test_write_text_rows(tmp_path):
    w = lambda t, x0, y0: {"t": t, "box": [x0, y0, x0 + 40, y0 + 20]}
    page = {"lines": [[w("Сума", 10, 100)], [w("69.26", 300, 101)]]}
    f = tmp_path / "t.txt"
    textlayer.write_text([page], str(f), rows=True)
    assert f.read_text(encoding="utf-8") == "Сума 69.26\n"
    textlayer.write_text([page], str(f))
    assert f.read_text(encoding="utf-8") == "Сума\n69.26\n"


def test_pdf_text_layer_roundtrip(tmp_path):
    """Invisible text must be extractable, searchable and lie on top of its word box."""
    import pymupdf
    W, H = 1000, 1400
    img = Image.new("L", (W, H), 255)
    page = {"page": 1, "W": W, "H": H, "lines": [
        [{"t": "Здравей,", "box": [100, 100, 400, 160]}, {"t": "свят!", "box": [430, 100, 600, 160]}],
        [{"t": "Hello", "box": [100, 300, 300, 360]}]]}
    wr = pdf.Writer((400, 600))
    wr.add({"size": (500, 700), "layers": [pdf.jpeg(img, 50)]}, page)
    out = str(tmp_path / "t.pdf")
    wr.save(out, "Заглавие", "Автор")
    with pymupdf.open(out) as d:
        p = d[0]
        assert p.rect.width == 400 and p.rect.height == 600
        assert p.get_text().split() == ["Здравей,", "свят!", "Hello"]
        hit = p.search_for("свят")[0]
        k = min(400 / 500, 600 / 700) * 500 / W  # pixels -> points
        dx = (400 - 500 * min(400 / 500, 600 / 700)) / 2
        assert abs(hit.x0 - (dx + 430 * k)) < 3
        assert d.metadata["title"] == "Заглавие"


def test_g4_stencil_decodes(tmp_path):
    ink = np.zeros((64, 64), bool)
    ink[10:20, 10:50] = True
    st = pdf.g4(Image.fromarray(~ink))
    st.update(kind="stencil", fill=0.0)
    wr = pdf.Writer((64, 64))
    wr.add({"size": (64, 64), "layers": [st]})
    out = str(tmp_path / "s.pdf")
    wr.save(out)
    import pymupdf
    with pymupdf.open(out) as d:
        a = np.frombuffer(d[0].get_pixmap(colorspace=pymupdf.csGRAY).samples, np.uint8).reshape(64, 64)
    assert a[15, 30] < 50 and a[40, 30] > 200  # ink painted, paper left white


def test_enhance_whitens_paper_and_keeps_ink():
    rng = np.random.default_rng(0)
    h, w = 1600, 1100
    yy, xx = np.mgrid[0:h, 0:w]
    paper = 150 + 60 * xx / w                       # uneven lighting, yellowish grey
    img = np.repeat(paper[..., None], 3, axis=2)
    img[400:430, 200:900] = 40                       # a "line of text"
    img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    page, mask, colour = enhance.enhance(img, (550, 800))
    assert not colour and page.shape == (800, 550)
    assert np.median(page) > 240                     # paper is white everywhere
    assert page[205:212, 150:400].mean() < 90        # text stays dark


def test_flat_scan_detection():
    page = np.full((800, 600, 3), 235, np.uint8)
    page[100:110, 50:550] = 30                       # a line of text
    assert enhance.is_flat_scan(page)
    photo = np.full((900, 700, 3), 60, np.uint8)     # dark table around the page
    photo[50:850, 60:640] = 230
    assert not enhance.is_flat_scan(photo)


def test_score_metrics():
    s = accuracy.score("Мама мия ри-\nбата днес", "мама мие рибата днес")
    assert s["words"] == 4 and s["word_recall"] == pytest.approx(0.75)
    assert 0.9 < s["char_acc"] < 1


# ---------------------------------------------------------------- interface translations

def _ui_strings():
    """Every string the window passes to tr() / trn(), read from the source."""
    import ast
    import os
    src = os.path.join(os.path.dirname(i18n.__file__), "gui.py")      # read, not imported: no Qt needed
    tree = ast.parse(open(src, encoding="utf-8").read())
    plain, counted = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in ("LANGUAGE_NAMES", "STAGES"):
            plain |= set(ast.literal_eval(node.value).values())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            if node.func.id == "tr":
                plain.add(node.args[0].value)
            elif node.func.id == "trn":
                counted.add(node.args[0].value)
    return plain, counted


@pytest.mark.parametrize("code", [c for c in i18n.CODES if c != "en"])
def test_catalog_complete(code):
    import string
    plain, counted = _ui_strings()
    cat = i18n.load(code)
    assert plain | counted <= set(cat), f"{code}: missing {sorted((plain | counted) - set(cat))}"
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
    for key in plain:
        assert isinstance(cat[key], str) and fields(cat[key]) == fields(key), (code, key)
    for key in counted:
        forms = cat[key]
        assert isinstance(forms, list) and len(forms) == i18n.NFORMS[code], (code, key)
        assert all(fields(f) == fields(key) for f in forms), (code, key)


def test_plural_rules():
    try:
        i18n.set_language("ru")
        assert [i18n.trn("{n} page", "{n} pages", n) for n in (1, 3, 5, 11, 21, 22, 112)] == \
            ["1 страница", "3 страницы", "5 страниц", "11 страниц", "21 страница", "22 страницы", "112 страниц"]
        i18n.set_language("pl")
        assert [i18n.trn("{n} page", "{n} pages", n) for n in (1, 2, 5, 22, 25)] == \
            ["1 strona", "2 strony", "5 stron", "22 strony", "25 stron"]
        i18n.set_language("sl")
        assert [i18n.trn("{n} page", "{n} pages", n) for n in (1, 2, 3, 5, 101)] == \
            ["1 stran", "2 strani", "3 strani", "5 strani", "101 stran"]
        i18n.set_language("ro")
        assert [i18n.trn("{n} page", "{n} pages", n) for n in (1, 2, 19, 20, 101)] == \
            ["1 pagină", "2 pagini", "19 pagini", "20 de pagini", "101 de pagini"]
        i18n.set_language("lt")
        assert [i18n.trn("{n} page", "{n} pages", n) for n in (1, 2, 10, 11, 21)] == \
            ["1 puslapis", "2 puslapiai", "10 puslapių", "11 puslapių", "21 puslapis"]
        i18n.set_language("fr")
        assert [i18n.trn("{n} page", "{n} pages", n) for n in (0, 1, 2)] == ["0 page", "1 page", "2 pages"]
        assert i18n.number(12345) == "12\u00a0345"
        i18n.set_language("de")
        assert i18n.number(12345) == "12.345"
        i18n.set_language("sr_Latn")
        assert i18n.tr("Ready.") == "Spremno." and i18n.tr("Choose folder…") == "Izaberi fasciklu…"
    finally:
        i18n.set_language("en")
    assert i18n.trn("{n} page", "{n} pages", 1) == "1 page" and i18n.number(12345) == "12,345"


def test_language_from_locale():
    assert i18n.match(["bg-BG", "en-US"]) == "bg"
    assert i18n.match(["ja-JP", "pl-PL"]) == "pl"
    assert i18n.match(["sr-Latn-RS"]) == "sr_Latn"
    assert i18n.match(["sr_RS@latin"]) == "sr_Latn"
    assert i18n.match(["sr-RS"]) == "sr"
    assert i18n.match(["uk_UA.UTF-8"]) == "uk"
    assert i18n.match(["nn-NO"]) == "nb" and i18n.match(["pt-BR"]) == "pt" and i18n.match(["de-AT"]) == "de"
    assert i18n.match(["ja-JP"]) == "en"
    assert i18n.set_language("xx") == "en"


def test_worker_processes_spawn():
    """Windows and macOS start worker processes with spawn (no fork); results keep their order."""
    from darealkniga.util import pool_map
    assert pool_map(abs, [-3, 2, -1], 2, "abs", spawn=True) == [3, 2, 1]


def test_main_module_is_guarded():
    """Spawned workers re-import __main__; running `python -m darealkniga` must not start again there."""
    import os
    src = open(os.path.join(os.path.dirname(i18n.__file__), "__main__.py"), encoding="utf-8").read()
    assert 'if __name__ == "__main__":' in src


@pytest.mark.parametrize("out, major", [("tesseract 5.3.4\n leptonica-1.82.0", 5),
                                        ("tesseract v5.5.3.20260724\n leptonica-1.85.0", 5),
                                        ("tesseract 3.05.02", 3), ("something else", None)])
def test_tesseract_version(monkeypatch, out, major):
    """Windows builds print 'tesseract v5.5.3...': still a local Tesseract 5, not a reason to use Docker."""
    import subprocess
    from darealkniga import ocr
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(ocr.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out, stderr=""))
    assert ocr.tesseract_version() == major
    if major and major >= 4:
        assert ocr.tesseract_backend() == "local"


def test_receipt_terms_fixed_by_one_letter():
    """Receipt profile: the few terms every receipt prints, misread by one letter, are put right;
    real words, other forms of a term and numbers are left alone."""
    fixes = {"ОЕЩА": "ОБЩА", "УБША": "ОБЩА", "ЕБРО": "ЕВРО", "CYMA:": "СУМА:", "#CYMA/AMT": "#СУМА/AMT",
             "KAPTU": "КАРТИ", "ОЕWА": "ОБЩА", "МАГА3ИН": "МАГАЗИН", "Олератор": "Оператор", "3AAC": "ЗДДС",
             "YHII:": "УНП:", "EHK:": "ЕИК:"}
    for wrong, right in fixes.items():
        assert receipt.fix_word(wrong) == right, wrong
    for kept in ("разписки:", "КАРТИ", "Шумен", "бихте", "ПЕПСИ", "2.92=", "0.218", "BG127585839"):
        assert receipt.fix_word(kept) == kept


def test_receipt_rows_join_split_decimals_and_mark_vat_group():
    w = lambda t, x: {"t": t, "box": [x, 0, x + 50, 20]}
    row = receipt.fix_row([w("ОЕЩА", 0), w("СУМА", 60), w("ЕБРО", 120), w("28.", 300), w("52", 350)])
    assert [x["t"] for x in row] == ["ОБЩА", "СУМА", "ЕВРО", "28.52"]
    row = receipt.fix_row([w("1", 0), w("бр", 20), w("×", 40), w("1.65=", 60), w("1.65", 120), w("6", 180)])
    assert [x["t"] for x in row][-2:] == ["1.65", "Б"]
    row = receipt.fix_row([w("ПОМЕЛО", 0), w("6", 100)])  # not after a price: kept
    assert [x["t"] for x in row] == ["ПОМЕЛО", "6"]


def test_paddle_page_words_follow_slanted_lines():
    """PaddleOCR's line boxes are upright; its polygons follow the tilt. Words take their height
    from the polygon, so rows() can measure the tilt of a photographed receipt and keep a far-right
    total on its label's row instead of the row below."""
    pj = {"texts": ["ОБЩА СУМА ЕВРО", "ДЕБ.КАРТА", "6.22"], "scores": [0.9, 0.9, 1.0],
          "boxes": [[40, 917, 700, 1000], [43, 963, 269, 1032], [969, 966, 1155, 1024]],
          "polys": [[[40, 917], [700, 950], [697, 1000], [37, 967]],
                    [[47, 963], [269, 974], [265, 1024], [43, 1013]],
                    [[971, 966], [1155, 975], [1153, 1024], [969, 1017]]]}
    rows = textlayer.rows(fuse.paddle_page(pj, 1.0))
    assert [[x["t"] for x in r] for r in rows] == [["ОБЩА", "СУМА", "ЕВРО", "6.22"], ["ДЕБ.КАРТА"]]


def test_bulgarian_letters_from_a_multilingual_model():
    """ь only before о, no ы, no Latin v inside Cyrillic words: Bulgarian spelling settles what
    PaddleOCR's multi-language Cyrillic model writes."""
    assert fuse.bulgarian_letters("Достьп") == "Достъп"
    assert fuse.bulgarian_letters("Даньчна") == "Данъчна"
    assert fuse.bulgarian_letters("ТРЫНЧЕВ") == "ТРЪНЧЕВ"
    assert fuse.bulgarian_letters("Днеvна") == "Дневна"
    for kept in ("шофьор", "Гьоте", "EUR/kWh", "Vivacom", "2.92"):
        assert fuse.bulgarian_letters(kept) == kept
