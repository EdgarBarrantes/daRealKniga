"""PDF writer: layered page images (JPEG + CCITT G4 masks) plus an invisible, searchable text layer.

The text layer uses the same trick as Tesseract's PDF renderer: a "glyphless" TrueType font
whose character codes are UTF-16 code units mapped 1:1 back to Unicode, every glyph 1/2 em
wide, drawn in render mode 3 (invisible) and stretched with Tz to cover each word's box.
"""
import io
import os
from importlib import resources

import numpy as np
import pikepdf
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
N = pikepdf.Name


# ------------------------------------------------------------- image encoders (run in workers)

def jpeg(im, quality, allow_gray=True):
    """-> spec dict. Near-grey RGB images are stored as greyscale."""
    if im.mode not in ("L", "RGB"):
        im = im.convert("RGB")
    if im.mode == "RGB" and allow_gray:
        a = np.asarray(im).astype(np.int16)
        if np.abs(a - a.mean(axis=2, keepdims=True)).max() < 12:
            im = im.convert("L")
    b = io.BytesIO()
    im.save(b, "JPEG", quality=quality, optimize=True)
    return {"kind": "jpeg", "data": b.getvalue(), "w": im.width, "h": im.height, "gray": im.mode == "L"}


def g4(mask):
    """1-bit PIL image -> raw CCITT G4 data (single strip)."""
    mask = mask.convert("1")
    b = io.BytesIO()
    mask.save(b, "TIFF", compression="group4", strip_size=2 ** 31 - 1)
    t = Image.open(io.BytesIO(b.getvalue()))
    off, cnt = t.tag_v2[273], t.tag_v2[279]
    assert len(off) == 1
    return {"kind": "g4", "data": b.getvalue()[off[0]:off[0] + cnt[0]], "w": mask.width, "h": mask.height}


# ------------------------------------------------------------- PDF objects

def _g4_parms(s):
    return pikepdf.Dictionary(K=-1, Columns=s["w"], Rows=s["h"])


def _image(pdf, s):
    if s["kind"] == "jpeg":
        d = dict(Type=N.XObject, Subtype=N.Image, Width=s["w"], Height=s["h"], BitsPerComponent=8,
                 ColorSpace=N.DeviceGray if s["gray"] else N.DeviceRGB, Filter=N.DCTDecode)
        if "smask" in s:  # tone shown only where the 1-bit mask is set
            m = s["smask"]
            d["SMask"] = pikepdf.Stream(pdf, m["data"], Type=N.XObject, Subtype=N.Image, Width=m["w"],
                                        Height=m["h"], BitsPerComponent=1, ColorSpace=N.DeviceGray,
                                        Filter=N.CCITTFaxDecode, DecodeParms=_g4_parms(m))
        return pikepdf.Stream(pdf, s["data"], **d)
    if s["kind"] == "stencil":  # 1 = ink, painted in the current fill colour
        return pikepdf.Stream(pdf, s["data"], Type=N.XObject, Subtype=N.Image, Width=s["w"], Height=s["h"],
                              BitsPerComponent=1, ImageMask=True, Filter=N.CCITTFaxDecode,
                              Decode=[1, 0], DecodeParms=_g4_parms(s))
    raise ValueError(s["kind"])


def glyphless_font(pdf):
    ttf = (resources.files("realkniga") / "data" / "glyphless.ttf").read_bytes()
    cid2gid = pdf.make_stream(b"\x00\x01" * 65536)
    cmap = pdf.make_stream(b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identify-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
1 beginbfrange
<0000> <FFFF> <0000>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end
""")
    desc = pdf.make_indirect(pikepdf.Dictionary(
        Type=N.FontDescriptor, FontName=N.GlyphLessFont, Flags=5, FontBBox=[0, 0, 500, 1000],
        ItalicAngle=0, Ascent=1000, Descent=0, CapHeight=1000, StemV=80, FontFile2=pdf.make_stream(ttf)))
    cid = pdf.make_indirect(pikepdf.Dictionary(
        Type=N.Font, Subtype=N.CIDFontType2, BaseFont=N.GlyphLessFont,
        CIDSystemInfo=pikepdf.Dictionary(Registry=pikepdf.String("Adobe"), Ordering=pikepdf.String("Identity"),
                                         Supplement=0),
        FontDescriptor=desc, DW=500, CIDToGIDMap=cid2gid))
    return pdf.make_indirect(pikepdf.Dictionary(
        Type=N.Font, Subtype=N.Type0, BaseFont=N.GlyphLessFont, Encoding=N("/Identity-H"),
        DescendantFonts=[cid], ToUnicode=cmap))


def text_ops(p, pw):
    """Invisible text for one page; p in pixel coordinates, page drawn pw points wide."""
    k = pw / p["W"]
    ph = p["H"] * k
    out = ["BT 3 Tr"]
    for line in p["lines"]:
        y0 = min(w["box"][1] for w in line) * k
        y1 = max(w["box"][3] for w in line) * k
        fs = max(1.0, y1 - y0)
        base = ph - y1 + (y1 - y0) * 0.15
        out.append(f"/T {fs:.2f} Tf")
        for i, w in enumerate(line):
            x0, x1 = w["box"][0] * k, w["box"][2] * k
            txt = w["t"] + (" " if i < len(line) - 1 else "")
            target = (x1 - x0) if i == len(line) - 1 else max(x1 - x0, line[i + 1]["box"][0] * k - x0)
            code = txt.encode("utf-16-be")
            natural = len(code) / 2 * 0.5 * fs
            tz = 100 * max(target, 0.5) / natural
            out.append(f"{tz:.2f} Tz 1 0 0 1 {x0:.2f} {base:.2f} Tm <{code.hex()}> Tj")
    out.append("ET")
    return "\n".join(out) + "\n"


class Writer:
    """Every page gets the same box (bw x bh pt); each page's content is scaled to fit and centred."""

    def __init__(self, box):
        self.pdf = pikepdf.new()
        self.font = glyphless_font(self.pdf)
        self.bw, self.bh = box

    def add(self, payload, ocr_page=None):
        """payload: {"size": (pw, ph) natural size in pt, "layers": [image spec (+ "fill" for stencils)]}"""
        pw, ph = payload["size"]
        res, ops = {}, []
        for i, s in enumerate(payload["layers"]):
            name = f"/I{i}"
            res[name] = _image(self.pdf, s)
            fill = f"{s['fill']:.3f} g " if s["kind"] == "stencil" else ""
            ops.append(f"q {fill}{pw:.3f} 0 0 {ph:.3f} 0 0 cm {name} Do Q")
        content = "\n".join(ops) + "\n"
        if ocr_page and ocr_page["lines"]:
            content += text_ops(ocr_page, pw)
        k = min(self.bw / pw, self.bh / ph)
        dx, dy = (self.bw - pw * k) / 2, (self.bh - ph * k) / 2
        content = f"q {k:.5f} 0 0 {k:.5f} {dx:.3f} {dy:.3f} cm\n{content}Q\n"
        self.pdf.pages.append(pikepdf.Page(pikepdf.Dictionary(
            Type=N.Page, MediaBox=[0, 0, round(self.bw, 3), round(self.bh, 3)],
            Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(res), Font=pikepdf.Dictionary(T=self.font)),
            Contents=self.pdf.make_stream(content.encode()))))

    def save(self, path, title=None, author=None, producer=None):
        with self.pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            if title:
                meta["dc:title"] = title
            if author:
                meta["dc:creator"] = [author]
        if title:
            self.pdf.docinfo["/Title"] = title
        if author:
            self.pdf.docinfo["/Author"] = author
        self.pdf.docinfo["/Producer"] = producer or "realKniga"
        tmp = path + ".part"
        self.pdf.save(tmp, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        os.replace(tmp, path)
