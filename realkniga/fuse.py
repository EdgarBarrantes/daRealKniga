"""Word-level fusion of Tesseract and PaddleOCR results.

Tesseract gives reliable word boxes and strong Cyrillic; PaddleOCR is strong on Latin/English
and on low-contrast text. Words are matched by position and the better reading is chosen
using lexicon look-ups (wordfreq) and Cyrillic/Latin look-alike rules. All coordinates are
page pixels with a top-left origin.
"""
import csv
import re
import unicodedata
from wordfreq import zipf_frequency

# lexicons used by known(); set by configure()
LEX = {"cyr": "bg", "lat": "en"}


def configure(langs):
    LEX["cyr"] = langs.cyr_lex or "bg"
    LEX["lat"] = langs.lat_lex or "en"

CYR = re.compile(r"[Ѐ-ӿ]")
LAT = re.compile(r"[A-Za-z]")
# Latin look-alikes -> Cyrillic and back
L2C = dict(zip("aeopcxykAEOPCXYKBHMTrun", "аеорсхукАЕОРСХУКВНМТгип"))
C2L = dict(zip("аеорсхукАЕОРСХУКВНМТ", "aeopcxykAEOPCXYKBHMT"))


def strip_acute(w):
    # stress marks: remove combining acute (keeps ѝ, which is precomposed U+045D)
    w = unicodedata.normalize("NFD", w).replace("́", "")
    w = unicodedata.normalize("NFC", w)
    return w.replace("й́", "и")


def script(w):
    c, l = len(CYR.findall(w)), len(LAT.findall(w))
    return "cyr" if c > l else "lat" if l > c else ("none" if c == 0 else "mix")


def clean(w, prefer=None):
    w = strip_acute(w)
    s = script(w)
    if prefer is None and s == "lat" and all(ch in L2C or not LAT.match(ch) for ch in w):
        # made only of letters that also exist in Cyrillic (xaoc, Mama): pick the known reading
        cw = "".join(L2C.get(ch, ch) for ch in w)
        if known(cw) and not known(w):
            return cw
    if s == "mix":
        s = prefer or "cyr"
    if s == "cyr":
        w = "".join(L2C.get(ch, ch) if LAT.match(ch) else ch for ch in w)
    elif s == "lat":
        w = "".join(C2L.get(ch, ch) if CYR.match(ch) else ch for ch in w)
    return w


def known(w):
    core = w.strip(".,;:!?\"'“”„«»()[]{}…–—-/*").lower().replace("’", "'")
    if not core:
        return False
    if core.isdigit():
        return True
    if re.search(r"\d", core) and has_letters(core) and not re.fullmatch(r"\d+(st|nd|rd|th)", core):
        return False
    parts = [p for p in core.split("-") if p]
    if not parts:
        return False
    for p in parts:
        if len(p) == 1:
            continue
        s = script(p)
        if s == "cyr":
            if zipf_frequency(p, LEX["cyr"]) < 1.5:
                return False
        elif s == "lat":
            if zipf_frequency(p, LEX["lat"]) <= 2.6:
                return False
        else:
            return False
    return True


def has_letters(w):
    return bool(CYR.search(w) or LAT.search(w))


AMBIG = {"r": "гт", "u": "иц", "n": "ип", "m": "тм", "b": "вб", "6": "б", "3": "з"}


def recover_cyr(w):
    """Latin/digit misread of a Cyrillic token -> best known Bulgarian reading, else None."""
    if script(w) != "lat":
        return None
    lead = re.match(r"^(\W*)(.*?)(\W*)$", w)
    pre, core, post = lead.groups()
    morph = (pre.endswith("-") or post.startswith("-")) and len(core) <= 3
    if not morph and known(w):
        return None
    if not core or any(not (ch in L2C or ch in AMBIG or ch == "-") for ch in core):
        return None
    opts = [""]
    for ch in core:
        if ch == "-":
            alts = "-"
        else:
            alts = AMBIG.get(ch.lower(), "") if ch.islower() or ch.isdigit() else ""
            alts = (alts + L2C.get(ch, "")) or ch
        opts = [o + a for o in opts for a in dict.fromkeys(alts)][:64]
    if morph:
        # suffix/ending under discussion, e.g. -ец, -и
        best = [o for o in opts if "ц" in o and core.strip("-").lower() == "eu"] or opts
        return pre + best[0] + post
    scored = [(zipf_frequency(o.lower(), LEX["cyr"]), o) for o in opts]
    f, o = max(scored)
    return pre + o + post if f >= 2.0 else None


def choose(t, p, line_script):
    r = _choose(t, p, line_script)
    return recover_cyr(r) or r


# Cyrillic letters that some typefaces make Tesseract confuse systematically (н/п/и, ш/щ, ь/ъ)
CYR_CONFUSE = {"н": "нпи", "п": "пни", "и": "ипн", "ь": "ьъ", "ъ": "ъь", "ш": "шщ", "щ": "щш"}


def repair_cyr(w):
    """Lower-case Cyrillic word -> a look-alike spelling that is a far more frequent word, else None.
    Capitalised words (names) and fragments such as '-ена' are left alone."""
    m = re.match(r"^([\"'„“«(\[]*)([^\W\d_]+)([.,;:!?…\"'”»)\]]*)$", w)
    if not m or script(m.group(2)) != "cyr" or not m.group(2).islower():
        return None
    pre, core, post = m.groups()
    low = core
    f0 = zipf_frequency(low, LEX["cyr"])
    if f0 >= 4.5:  # common word: leave it
        return None
    slots = [i for i, ch in enumerate(low) if ch in CYR_CONFUSE]
    if not slots or len(slots) > 8:
        return None
    opts = [low]
    for i in slots:
        opts = [o[:i] + a + o[i + 1:] for o in opts for a in CYR_CONFUSE[low[i]]][:2000]
    best, fb = None, f0
    for o in opts:
        f = zipf_frequency(o, LEX["cyr"])
        if f > fb:
            best, fb = o, f
    # unknown words need a 100x more frequent look-alike; rarer real words (па, пе) need 300x
    if best is None or fb < 2.5 or fb - f0 < (2.0 if f0 < 3.0 else 2.5):
        return None
    return pre + best + post


SENTENCE_END = re.compile(r"[.!?…]$|^[—–]$")


def _case_kind(core):
    if core.islower():
        return "lower"
    if core.isupper():
        return "upper" if len(core) > 1 else "title"
    if core[0].isupper() and core[1:].islower():
        return "title"
    return "mixed"


def _cased(core, kind):
    return {"lower": core.lower(), "upper": core.upper(), "title": core[:1].upper() + core[1:].lower()}[kind]


def resolve_case(lines):
    """Fix the letter case of Cyrillic words. Many capitals are only bigger lower-case letters
    (с/С, и/И, г/Г, в/В), so OCR misjudges case: 'МНОго', 'СИ' in the middle of a sentence,
    'Ги' after a hyphenated line break. Tesseract's reading is kept unless it is clearly wrong
    (mixed case, capitals inside normal text that the other engine ('alt') read in lower case,
    the continuation of a hyphenated word). Neither engine is reliable about a lone capital
    letter, so capitalised words (names, list items) are left alone, as are acronyms."""
    prev = None  # previous word on the page
    for line in lines:
        letters = [re.sub(r"[\W\d_]", "", w["t"]) for w in line]
        letters = [x for x in letters if len(x) > 1]
        caps_line = bool(letters) and sum(x.isupper() for x in letters) > len(letters) / 2
        for i, w in enumerate(line):
            alt = w.pop("alt", None)
            m = re.match(r"^(\W*)([^\W\d_]+)(\W*)$", w["t"])
            if m and script(m.group(2)) == "cyr" and len(m.group(2)) > 1:   # not initials (П.)
                pre, core, post = m.groups()
                fragment = "-" in pre                                  # grammar endings: -ен, -ът
                quoted = pre != "" and pre[-1] in "\"“„«"
                start = (prev is None or bool(SENTENCE_END.search(prev)) or quoted) and not fragment
                cont = False                               # second half of a word hyphenated at line end
                if i == 0 and prev and prev.endswith("-"):
                    head = re.sub(r"^\W+", "", prev[:-1])
                    cont = head.isalpha() and zipf_frequency((head + core).lower(), LEX["cyr"]) >= 1.0
                tk = _case_kind(core)
                ak = None
                if alt:
                    am = re.match(r"^\W*([^\W\d_]+)\W*$", alt)
                    if am and am.group(1).lower() == core.lower():
                        ak = _case_kind(am.group(1))
                want = None
                if cont and tk != "lower" and not caps_line:
                    want = "lower"
                elif tk == "mixed":
                    if ak == "upper" and caps_line:
                        want = "upper"
                    elif start or (core[0].isupper() and not fragment):
                        want = "title"   # mid-sentence this may be a name: keep the capital
                    else:
                        want = "lower"
                elif tk == "upper" and not caps_line and ak in ("lower", "title") and \
                        zipf_frequency(core.lower(), LEX["cyr"]) >= 3.5:      # not acronyms (БАН)
                    want = ak
                if want:
                    w["t"] = pre + _cased(core, want) + post
            prev = w["t"]
    return lines


def repair_page(lines, min_share=0.02, min_count=3):
    """Apply repair_cyr only on pages where the confusion is clearly systematic: a typeface
    problem shows up as many repairable words, while a page with one or two hits is more likely
    to contain rare real words."""
    fixes = [(w, r) for l in lines for w in l for r in [repair_cyr(w["t"])] if r]
    n = sum(len(l) for l in lines)
    if len(fixes) >= max(min_count, min_share * n):
        for w, r in fixes:
            w["t"] = r
    return lines


def _choose(t, p, line_script):
    """t: tesseract word, p: paddle word or None."""
    single = len(re.sub(r"\W", "", t)) == 1 and has_letters(t)
    if single and line_script in ("cyr", "lat"):
        # single ambiguous letters (а/a, е/e, о/o, с/c ...) follow the line's script
        base = p if (p and len(re.sub(r"\W", "", strip_acute(p))) == 1) else t
        return clean(base, line_script) if script(strip_acute(base)) in ("cyr", "lat", "mix") else base
    tc = clean(t)
    if p is None:
        return tc
    pc = clean(p)
    if tc == pc:
        return tc
    if tc.lower() == pc.lower() and script(tc) == "cyr":
        return tc  # case-only differences are settled by resolve_case() with sentence context
    if not (0.5 <= len(pc) / max(1, len(tc)) <= 2) and abs(len(pc) - len(tc)) > 1:
        return tc  # probably mismatched words
    letters_p = len(re.sub(r"[\W\d_]", "", pc))
    if not has_letters(tc):
        return pc if letters_p >= 2 and known(pc) else tc
    rc = recover_cyr(tc)
    if rc and line_script in ("cyr", "mix") and script(pc) == "lat":
        return rc
    kt, kp = known(tc), known(pc)
    if kt and not kp:
        return tc
    if kp and not kt:
        return pc
    st, sp = script(tc), script(pc)
    if sp == "cyr" and st == "lat":
        return pc
    if st == "lat" and sp == "lat":
        return pc
    return tc


def read_tess(path, scale):
    lines = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row["level"] != "5":
                continue
            txt = (row["text"] or "").strip()
            if not txt:
                continue
            key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
            x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
            lines.setdefault(key, []).append({
                "t": txt, "conf": float(row["conf"]),
                "box": [x * scale, y * scale, (x + w) * scale, (y + h) * scale]})
    return [lines[k] for k in sorted(lines)]


def paddle_words(pj, scale):
    """Split each paddle line into words with x-ranges proportional to character count."""
    out = []
    for txt, sc, (x0, y0, x1, y1) in zip(pj["texts"], pj["scores"], pj["boxes"]):
        txt = txt.strip()
        if not txt:
            continue
        n = len(txt)
        pos = 0
        for m in re.finditer(r"\S+", txt):
            a, b = m.start(), m.end()
            out.append({"t": m.group(), "score": sc, "used": False,
                        "box": [(x0 + (x1 - x0) * a / n) * scale, y0 * scale,
                                (x0 + (x1 - x0) * b / n) * scale, y1 * scale]})
    return out


def overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def match(tw, pws):
    tb = tw["box"]
    best, bestv = None, 0
    th = tb[3] - tb[1]
    tw_ = tb[2] - tb[0]
    for pw in pws:
        pb = pw["box"]
        if overlap((tb[1], tb[3]), (pb[1], pb[3])) < 0.5 * min(th, pb[3] - pb[1]):
            continue
        ox = overlap((tb[0], tb[2]), (pb[0], pb[2]))
        v = ox / max(1, max(tw_, pb[2] - pb[0]))
        if v > bestv:
            best, bestv = pw, v
    return best if bestv >= 0.4 else None


def context_pass(words):
    """Latin look-alike words (ce, Ha, e) surrounded by Cyrillic -> Cyrillic."""
    sc = [script(w["t"]) for w in words]
    for i, w in enumerate(words):
        nb = [sc[j] for j in (i - 1, i + 1) if 0 <= j < len(words)]
        if w["t"] == "6" and nb == ["cyr", "cyr"]:
            w["t"], sc[i] = "е", "cyr"  # bold "е" misread as 6
            continue
        if sc[i] != "lat":
            continue
        m = re.match(r"^(\W*)([A-Za-z-]+)(\W*)$", w["t"])
        if not m or any(ch not in L2C for ch in m.group(2) if ch != "-"):
            continue
        cyr = "".join(L2C.get(ch, ch) for ch in m.group(2))
        nb = [sc[j] for j in (i - 1, i + 1) if 0 <= j < len(words)]
        if nb.count("cyr") > nb.count("lat") and \
                zipf_frequency(cyr.lower(), LEX["cyr"]) > zipf_frequency(m.group(2).lower(), LEX["lat"]):
            w["t"] = m.group(1) + cyr + m.group(3)
            sc[i] = "cyr"


def tess_only_page(tlines, normalize):
    """No second engine: keep Tesseract words, drop symbol noise, optionally fix look-alikes."""
    lines = []
    for tl in tlines:
        ls = script(strip_acute("".join(w["t"] for w in tl)))
        words = [{"t": choose(w["t"], None, ls) if normalize else w["t"], "box": [round(v) for v in w["box"]]}
                 for w in tl if w["conf"] >= 20 or has_letters(w["t"])]
        if words:
            if normalize:
                context_pass(words)
            lines.append(words)
    return repair_page(resolve_case(lines)) if normalize else lines


def fuse_page(tlines, pws):
    lines = []
    for tl in tlines:
        lt = "".join(w["t"] for w in tl)
        ls = script(strip_acute(lt))
        words = []
        for tw in tl:
            pw = match(tw, pws)
            if pw:
                pw["used"] = True
            txt = choose(tw["t"], pw["t"] if pw else None, ls)
            # drop low-confidence tesseract noise (e.g. inside photos) that paddle didn't see
            if pw is None and tw["conf"] < 40 and not known(txt):
                continue
            word = {"t": txt, "box": [round(v) for v in tw["box"]]}
            if pw:
                word["alt"] = clean(pw["t"])
            words.append(word)
        if words:
            context_pass(words)
            lines.append(words)
    # text paddle found but tesseract missed entirely
    tboxes = [tw["box"] for tl in tlines for tw in tl]

    def covered(b):
        for t in tboxes:
            ix = overlap((b[0], b[2]), (t[0], t[2]))
            iy = overlap((b[1], b[3]), (t[1], t[3]))
            if ix * iy > 0.2 * min((b[2] - b[0]) * (b[3] - b[1]), (t[2] - t[0]) * (t[3] - t[1])):
                return True
        return False

    extra = {}
    for pw in pws:
        if pw["used"] or pw["score"] < 0.6 or len(re.sub(r"\W", "", pw["t"])) < 2:
            continue
        if covered(pw["box"]):
            continue
        key = round(pw["box"][1] / 20)
        extra.setdefault(key, []).append({"t": clean(pw["t"]), "box": [round(v) for v in pw["box"]]})
    for k in sorted(extra):
        ln = sorted(extra[k], key=lambda w: w["box"][0])
        y = ln[0]["box"][1]
        i = next((i for i, l in enumerate(lines) if l[0]["box"][1] > y), len(lines))
        lines.insert(i, ln)
    return repair_page(resolve_case(lines))
