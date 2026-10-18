"""Receipt fixes, applied to the rows of a receipt profile page.

Receipts repeat a small vocabulary in large or condensed print (ОБЩА СУМА ЕВРО, ДЕБИТНА КАРТА,
ФИСКАЛЕН БОН) that general dictionaries don't settle, and print numbers in ways that OCR splits
or glues. These fixes are deliberately narrow:
- a word one letter away from a receipt term (and not itself a known word) becomes the term;
- a decimal split by a space in wide print ("28. 52") is joined;
- the VAT group letter after a price, read as a digit or a Latin letter ("1.65 6"), becomes Б.
Digits inside numbers are never changed.
"""
import re

from . import fuse

# Bulgarian receipt terms, upper case. Three-letter ones only by exact look-alike folding.
TERMS = [
    "ОБЩА", "СУМА", "ЕВРО", "КАРТА", "КАРТИ", "ДЕБИТНА", "ДЕБИТНИ", "КРЕДИТНА", "КРЕДИТНИ", "ФИСКАЛЕН",
    "МЕЖДИННА", "ПОКУПКА", "АРТИКУЛ", "АРТИКУЛА", "ОТСТЪПКА", "РЕСТО", "БРОЙ", "БАНКА", "ОПЕРАТОР",
    "КАСИЕР", "ПЛАЩАНЕ", "РАЗПИСКА", "ПОДПИС", "МАГАЗИН", "СТОКИ", "ХРАНИТЕЛНИ", "БЛАГОДАРИМ",
]
# short terms by pattern on the folded word: EMK, ENK, ЕHK for ЕИК; YHII, YHP for УНП; 3AAC, 3ADC for ЗДДС
SHORT = {"ЕИК": r"Е[ИНПМI]К", "УНП": r"УН(П|Р|II|IІ|ИИ)", "ЗДДС": r"З[ДАОD0]{2}С"}
PRICE = re.compile(r"^-?\d+[.,]\d{2}$")
VAT_MISREAD = {"6", "5", "b", "б", "Б"}
FOLD_MORE = str.maketrans("36UNW", "ЗБИПШ")  # upper-case look-alikes L2C leaves (KAPTU, YHN, ОЕWА)
VOWELS = set("АЕИОУЪЮЯ")


def _fold(core):
    """Latin and digit look-alikes -> Cyrillic, upper case: the spelling terms are compared in."""
    return "".join(fuse.L2C.get(ch, ch) for ch in core).upper().translate(FOLD_MORE)


def _cased(term, like):
    if like.isupper() or not any(ch.isalpha() for ch in like):
        return term
    if like[:1].isupper():
        return term[:1] + term[1:].lower()
    return term.lower()


def _fix_core(core):
    if len(core) < 3 or not re.search(r"[^\W\d_]", core) or re.search(r"[0-24-57-9]", core):
        return core
    folded = _fold(core)
    for term, pattern in SHORT.items():
        if re.fullmatch(pattern, folded):
            return _cased(term, core)
    if len(core) < 4 or fuse.known(core):
        return core
    if folded in TERMS:
        return _cased(folded, core)
    near = []
    for term in TERMS:
        a, b = term.replace("Щ", "Ш"), folded.replace("Щ", "Ш")  # Ш and Щ: one shape to OCR
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        # one letter off, but not an ending vowel: that is another form of the word (разписки)
        if len(a) == len(b) and len(diff) <= 1 and not (
                diff and diff[0] == len(a) - 1 and a[-1] in VOWELS and b[-1] in VOWELS):
            near.append(term)
    return _cased(near[0], core) if len(near) == 1 else core


def fix_word(w):
    """Receipt terms misread by one letter -> the term, in the word's case. Each letter run of a
    compound (#CYMA/AMT, ДЕБ.КАРТА) is looked at on its own; other words stay as they are."""
    return re.sub(r"\w+", lambda m: _fix_core(m.group()), w)


def fix_row(words):
    """words: one row, left to right ({"t", "box"}). Returns the fixed row (words may merge)."""
    out = []
    for w in words:
        t = w["t"]
        if out and re.fullmatch(r"\d+[.,]", out[-1]["t"]) and re.fullmatch(r"\d{2}", t):
            prev = out[-1]  # wide print: "28." + "52"
            prev["t"] += t
            prev["box"] = [prev["box"][0], min(prev["box"][1], w["box"][1]), w["box"][2], max(prev["box"][3], w["box"][3])]
            continue
        out.append(dict(w, t=fix_word(t)))
    if len(out) >= 2 and PRICE.match(out[-2]["t"]) and out[-1]["t"] in VAT_MISREAD:
        out[-1]["t"] = "Б"  # the VAT group letter closing a price row
    return out
