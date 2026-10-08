"""Language configuration: Tesseract codes -> lexicons (wordfreq) and PaddleOCR recognizers."""
from dataclasses import dataclass

# Tesseract code -> wordfreq code
CYRILLIC = {"bul": "bg", "rus": "ru", "ukr": "uk", "mkd": "mk", "srp": "sh", "bel": "ru"}
LATIN = {"eng": "en", "deu": "de", "fra": "fr", "spa": "es", "ita": "it", "por": "pt", "nld": "nl",
         "pol": "pl", "ces": "cs", "slk": "sk", "slv": "sl", "hrv": "sh", "bos": "sh", "srp_latn": "sh",
         "ron": "ro", "hun": "hu", "swe": "sv", "dan": "da", "nor": "nb", "fin": "fi", "tur": "tr",
         "lit": "lt", "lav": "lv", "cat": "ca", "ind": "id", "msa": "ms", "vie": "vi", "isl": "is"}


@dataclass
class Langs:
    tess: str            # e.g. "bul+eng"
    cyr_lex: str | None  # wordfreq code of the main Cyrillic language
    lat_lex: str | None  # wordfreq code of the main Latin-script language
    paddle_rec: str | None

    @property
    def cyrillic(self):
        return self.cyr_lex is not None


def parse(spec):
    codes = [c for c in spec.replace(",", "+").split("+") if c]
    cyr = next((CYRILLIC[c] for c in codes if c in CYRILLIC), None)
    lat = next((LATIN[c] for c in codes if c in LATIN), None)
    if cyr:
        rec = "cyrillic_PP-OCRv5_mobile_rec"
    elif lat and all(c == "eng" for c in codes):
        rec = "en_PP-OCRv5_mobile_rec"
    elif lat:
        rec = "latin_PP-OCRv5_mobile_rec"
    else:
        rec = None
    return Langs("+".join(codes), cyr, lat, rec)
