"""Interface translations for the window (the command line stays in English).

Catalogs live in data/i18n/<code>.json and map each English interface string to its
translation. A string with a count, like "{n} page", maps to a list of plural forms in the
order of that language's plural rule (PLURALS below). Serbian Latin is not stored: it is
transliterated from the Serbian Cyrillic catalog. Missing strings fall back to English.
"""
import json
import unicodedata
from importlib import resources

# code, name in that language
NAMES = {
    "en": "English", "be": "Беларуская", "bg": "Български", "bs": "Bosanski", "ca": "Català", "cs": "Čeština",
    "da": "Dansk", "de": "Deutsch", "el": "Ελληνικά", "es": "Español", "et": "Eesti", "fi": "Suomi",
    "fr": "Français", "hr": "Hrvatski", "hu": "Magyar", "it": "Italiano", "lt": "Lietuvių", "lv": "Latviešu",
    "mk": "Македонски", "nb": "Norsk", "nl": "Nederlands", "pl": "Polski", "pt": "Português", "ro": "Română",
    "ru": "Русский", "sk": "Slovenčina", "sl": "Slovenščina", "sr": "Српски", "sr_Latn": "Srpski",
    "sv": "Svenska", "uk": "Українська",
}


def _sort_key(item):
    name = unicodedata.normalize("NFKD", item[1])
    return "".join(c for c in name if not unicodedata.combining(c)).casefold()


# sorted by their own names (Latin, then Greek, then Cyrillic), as language menus usually are
LANGUAGES = sorted(NAMES.items(), key=_sort_key)
CODES = [c for c, _ in LANGUAGES]
ALIASES = {"no": "nb", "nn": "nb"}

# the OCR language suggested on first start, from the interface language
DEFAULT_OCR = {"en": "bul+eng", "bg": "bul+eng", "ru": "rus+eng", "uk": "ukr+eng", "be": "bel", "mk": "mkd",
               "sr": "srp", "sr_Latn": "srp_latn", "hr": "hrv", "bs": "bos", "sl": "slv", "pl": "pol",
               "cs": "ces", "sk": "slk", "de": "deu", "fr": "fra", "es": "spa", "pt": "por", "it": "ita",
               "nl": "nld", "ca": "cat", "sv": "swe", "da": "dan", "nb": "nor", "fi": "fin", "et": "est",
               "el": "ell", "hu": "hun", "ro": "ron", "lt": "lit", "lv": "lav"}


def _east(n):  # Russian, Ukrainian, Belarusian, Serbian, Croatian, Bosnian: one, few, many
    if n % 10 == 1 and n % 100 != 11:
        return 0
    return 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2


def _one(n):  # most Germanic and Romance languages, Greek, Bulgarian, Hungarian, Finnish, Estonian
    return 0 if n == 1 else 1


PLURALS = {
    **{c: _one for c in ("en", "bg", "de", "es", "it", "nl", "ca", "sv", "da", "nb", "fi", "et", "el", "hu")},
    "fr": lambda n: 0 if n in (0, 1) else 1, "pt": lambda n: 0 if n in (0, 1) else 1,
    "ro": lambda n: 0 if n == 1 else 1 if n == 0 or 1 < n % 100 < 20 else 2,
    "lt": lambda n: 2 if 11 <= n % 100 <= 19 else 0 if n % 10 == 1 else 1 if n % 10 >= 2 else 2,
    "lv": lambda n: 0 if n % 10 == 0 or 11 <= n % 100 <= 19 else 1 if n % 10 == 1 else 2,  # zero, one, other
    "mk": lambda n: 0 if n % 10 == 1 and n % 100 != 11 else 1,
    "ru": _east, "uk": _east, "be": _east, "sr": _east, "sr_Latn": _east, "hr": _east, "bs": _east,
    "pl": lambda n: 0 if n == 1 else 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2,
    "cs": lambda n: 0 if n == 1 else 1 if 2 <= n <= 4 else 2,
    "sk": lambda n: 0 if n == 1 else 1 if 2 <= n <= 4 else 2,
    "sl": lambda n: {1: 0, 2: 1, 3: 2, 4: 2}.get(n % 100, 3),
}
NFORMS = {code: len({f(n) for n in range(200)}) for code, f in PLURALS.items()}

_SR_LATN = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџшАБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ",
                    ["a", "b", "v", "g", "d", "đ", "e", "ž", "z", "i", "j", "k", "l", "lj", "m", "n", "nj", "o",
                     "p", "r", "s", "t", "ć", "u", "f", "h", "c", "č", "dž", "š",
                     "A", "B", "V", "G", "D", "Đ", "E", "Ž", "Z", "I", "J", "K", "L", "Lj", "M", "N", "Nj", "O",
                     "P", "R", "S", "T", "Ć", "U", "F", "H", "C", "Č", "Dž", "Š"]))

_lang, _catalog = "en", {}


def to_latin(s):
    """Serbian Cyrillic -> Serbian Latin."""
    if isinstance(s, list):
        return [to_latin(x) for x in s]
    return "".join(_SR_LATN.get(c, c) for c in s)


def load(code):
    """The catalog for a language: {English: translation or [plural forms]}."""
    if code == "en":
        return {}
    if code == "sr_Latn":
        return {k: to_latin(v) for k, v in load("sr").items()}
    f = resources.files("darealkniga") / "data" / "i18n" / f"{code}.json"
    return json.loads(f.read_text(encoding="utf-8"))


def set_language(code):
    global _lang, _catalog
    code = code if code in CODES else "en"
    _lang, _catalog = code, load(code)
    return code


def language():
    return _lang


def match(preferred):
    """The first supported interface language in a list of locale names
    ("bg-BG", "sr-Latn-RS", "sr_RS@latin", "pl_PL.UTF-8"), else English."""
    for name in preferred:
        name = name.replace("-", "_").split(".")[0]
        parts = name.split("@")[0].split("_")
        base = parts[0].lower()
        if base == "sr":
            return "sr_Latn" if "Latn" in parts or name.endswith("@latin") else "sr"
        base = ALIASES.get(base, base)
        if base in CODES:
            return base
    return "en"


def tr(text, **kw):
    """Translate an interface string; keyword arguments fill its {placeholders}."""
    t = _catalog.get(text, text)
    if isinstance(t, list):
        t = t[-1]
    return t.format(**kw) if kw else t


def trn(singular, plural, n, **kw):
    """Translate a string with a count: trn("{n} page", "{n} pages", 12)."""
    forms = _catalog.get(singular)
    if isinstance(forms, list) and len(forms) == NFORMS.get(_lang, 2):
        t = forms[PLURALS[_lang](n)]
    else:
        t = singular if n == 1 else plural
    return t.format(n=number(n), **kw)


DOT_THOUSANDS = {"de", "nl", "da", "es", "it", "pt", "ro", "el", "ca", "hr", "bs", "sr", "sr_Latn", "sl", "mk"}


def number(n):
    """12345 -> "12,345" in English, "12.345" in German and others, "12\u00a0345" (no-break space) elsewhere."""
    s = f"{n:,}"
    return s if _lang == "en" else s.replace(",", "." if _lang in DOT_THOUSANDS else "\u00a0")
