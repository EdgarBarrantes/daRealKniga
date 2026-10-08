"""Desktop interface (Qt / PySide6).

The window collects the settings, runs `darealkniga make` in a child process (so a crash or a
cancel never takes the window down), and turns its output into a progress bar and a log.
Its text is translated (see i18n.py); the log under Details stays in English.
"""
import os
import re
import signal
import subprocess
import sys
import time
from importlib import resources

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, Qt, QThread, QTimer, QTranslator, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from . import __version__, i18n
from .i18n import tr, trn
from .util import extend_path

# OCR languages: Slavic first; "+ English" for text that mixes Cyrillic and Latin
LANGUAGES = ["bul+eng", "bul", "rus+eng", "rus", "ukr+eng", "ukr", "bel", "mkd", "srp", "srp_latn", "hrv",
             "bos", "slv", "pol", "ces", "slk", "eng", "deu", "fra", "spa", "ita", "por", "nld", "cat", "swe",
             "dan", "nor", "fin", "est", "ell", "hun", "ron", "lit", "lav"]
LANGUAGE_NAMES = {
    "bul": "Bulgarian", "rus": "Russian", "ukr": "Ukrainian", "bel": "Belarusian", "mkd": "Macedonian",
    "srp": "Serbian (Cyrillic)", "srp_latn": "Serbian (Latin)", "hrv": "Croatian", "bos": "Bosnian",
    "slv": "Slovenian", "pol": "Polish", "ces": "Czech", "slk": "Slovak", "eng": "English", "deu": "German",
    "fra": "French", "spa": "Spanish", "ita": "Italian", "por": "Portuguese", "nld": "Dutch", "cat": "Catalan",
    "swe": "Swedish", "dan": "Danish", "nor": "Norwegian", "fin": "Finnish", "est": "Estonian", "ell": "Greek",
    "hun": "Hungarian", "ron": "Romanian", "lit": "Lithuanian", "lav": "Latvian",
}
STAGES = {  # progress labels from the pipeline -> friendly names
    "render pages": "Reading pages", "extract pages": "Reading pages",
    "detect photos vs. flat scans": "Looking at the pages", "unwarp (UVDoc)": "Flattening photographed pages",
    "clean up pages": "Cleaning up pages", "PDF page images": "Building the PDF",
}
# Qt's own strings (standard buttons, file dialogs) come from Qt's translations; for languages
# Qt has none for, use the closest one it has
QT_FALLBACK = {"be": "ru", "mk": "bg", "bs": "hr", "sr": "hr", "sr_Latn": "hr", "sl": "hr", "pt": "pt_BR",
               "nb": "nn"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}

STYLE = """
QFrame#card { border: 1px solid palette(mid); border-radius: 10px; }
QFrame#drop { border: 2px dashed palette(mid); border-radius: 10px; }
QFrame#drop[hover="true"] { border-color: palette(highlight); }
QLabel#title { font-size: 20pt; font-weight: 600; }
QComboBox#uiLang { padding: 2px 8px; }
QLabel#muted { color: palette(placeholder-text); }
QLabel#inputName { font-size: 12pt; font-weight: 600; }
QPushButton#primary { background: palette(highlight); color: palette(highlighted-text); font-weight: 600;
                      padding: 9px 22px; border-radius: 7px; border: none; }
QPushButton#primary:disabled { background: palette(mid); }
QProgressBar { border-radius: 5px; min-height: 10px; max-height: 10px; text-align: center; }
QProgressBar::chunk { border-radius: 5px; background: palette(highlight); }
"""


def data_path(name):
    return str(resources.files("darealkniga") / "data" / name)


def repo_url():
    try:
        from ._build import REPO_URL
        return REPO_URL
    except ImportError:
        return None


def describe_input(path):
    """-> (kind, short description) or raises ValueError."""
    if os.path.isdir(path):
        n = sum(1 for f in os.listdir(path) if os.path.splitext(f)[1].lower() in IMAGE_EXT)
        if not n:
            raise ValueError(tr("This folder contains no images (jpg, png, tif, webp)."))
        return "photo", trn("Folder of {n} page image", "Folder of {n} page images", n)
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return "photo", tr("Single photo or scan")
    if ext in (".djvu", ".djv"):
        try:
            n = subprocess.run(["djvused", "-e", "n", path], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            n = ""
        pages = f" · {trn('{n} page', '{n} pages', int(n))}" if n.isdigit() else ""
        return "djvu", tr("DjVu book") + pages
    if ext == ".pdf":
        try:
            import pymupdf
            with pymupdf.open(path) as d:
                n = len(d)
        except Exception:  # noqa: BLE001
            raise ValueError(tr("This PDF could not be opened."))
        return "photo", f"PDF · {trn('{n} page', '{n} pages', n)}"
    raise ValueError(tr("Choose a .djvu or .pdf file, a photo or scan (jpg, png, tif, webp), or a folder of them."))


def language_label(code):
    """"bul+eng" -> "Bulgarian + English  (bul+eng)", in the interface language."""
    return " + ".join(tr(LANGUAGE_NAMES[c]) for c in code.split("+")) + f"  ({code})"


_qt_translator = None


def install_qt_translations(code):
    """Load Qt's translations for its standard buttons and dialogs."""
    global _qt_translator
    app = QApplication.instance()
    if app is None:
        return
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if code == "en":
        return
    t = QTranslator(app)
    if t.load(f"qtbase_{QT_FALLBACK.get(code, code)}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(t)
        _qt_translator = t


def start_language(settings):
    """The interface language: DAREALKNIGA_UI_LANG, else the one picked last time, else the system's."""
    code = os.environ.get("DAREALKNIGA_UI_LANG") or settings.value("ui_lang") or \
        i18n.match(QLocale.system().uiLanguages())
    return i18n.set_language(code)


def kill_group(pgid):
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class Runner(QThread):
    """Runs `darealkniga make` and reports its output line by line."""
    line = Signal(str)
    progress = Signal(str, int, int)
    done = Signal(int, list)

    def __init__(self, args):
        super().__init__()
        self.args, self.proc, self.outputs, self.cancelled = args, None, [], False

    def run(self):
        # UTF-8 both ways: file names and log lines are often Cyrillic, and Windows pipes default
        # to a legacy code page
        env = dict(os.environ, DAREALKNIGA_PROGRESS="1", PYTHONUNBUFFERED="1", PYTHONUTF8="1",
                   PYTHONIOENCODING="utf-8")
        # its own process group, so cancelling also stops the OCR worker processes it starts
        group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                 if sys.platform == "win32" else {"start_new_session": True})
        self.proc = subprocess.Popen([sys.executable, "-m", "darealkniga", "make", *self.args],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env, bufsize=1, **group)
        for raw in self.proc.stdout:
            s = raw.rstrip("\n")
            if s.startswith("@@progress\t"):
                _, label, done, total = s.split("\t")
                self.progress.emit(label, int(done), int(total))
                continue
            if s.startswith("[darealkniga] wrote "):
                self.outputs.append(s[len("[darealkniga] wrote "):].rsplit(" (", 1)[0])
            self.line.emit(s)
        self.done.emit(self.proc.wait(), self.outputs)

    def cancel(self):
        """Stop the run and every process it started."""
        if not self.proc or self.proc.poll() is not None:
            return
        self.cancelled = True
        if sys.platform == "win32":
            # no gentle stop for windowless processes on Windows: end the whole tree now
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            return
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        # then force whatever is left in the group, even if the main process has already exited (a plain
        # function: a timer tied to this object would be dropped once the window lets go of it)
        QTimer.singleShot(4000, lambda pgid=self.proc.pid: kill_group(pgid))


class DropZone(QFrame):
    dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)

    def _hover(self, on):
        self.setProperty("hover", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hover(True)

    def dragLeaveEvent(self, e):
        self._hover(False)

    def dropEvent(self, e):
        self._hover(False)
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.dropped.emit(urls[0])


def card():
    f = QFrame()
    f.setObjectName("card")
    return f


class Window(QMainWindow):
    def __init__(self, initial=None):
        super().__init__()
        self.settings = QSettings("darealkniga", "darealkniga")
        self.input, self.kind, self.runner, self.outputs = None, None, None, []
        self.t0 = 0
        self.status = lambda: tr("Choose a document to begin.")
        self.setWindowTitle("daRealKniga")
        self.setWindowIcon(QIcon(data_path("icon.png")))
        self.setAcceptDrops(True)
        self.resize(760, 720)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.build()
        if initial:
            self.set_input(initial)

    def build(self):
        """Create every widget in the current interface language (again after a language switch)."""
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(14)
        self.setCentralWidget(root)

        # header
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(data_path("icon.png")).scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(logo, 0, Qt.AlignTop)
        tl = QVBoxLayout()
        t = QLabel("daRealKniga")
        t.setObjectName("title")
        sub = QLabel(tr("Make books, documents, receipts and notes searchable. Cyrillic, Latin, or both."))
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        tl.addWidget(t)
        tl.addWidget(sub)
        head.addLayout(tl, 1)
        self.ui_lang = QComboBox()
        self.ui_lang.setObjectName("uiLang")
        for code, name in i18n.LANGUAGES:
            self.ui_lang.addItem(name, code)
        self.ui_lang.setCurrentIndex(self.ui_lang.findData(i18n.language()))
        self.ui_lang.setToolTip(tr("Interface language"))
        self.ui_lang.setAccessibleName(tr("Interface language"))
        # switch after the signal returns: switching rebuilds (and deletes) this combo box
        self.ui_lang.currentIndexChanged.connect(lambda _: QTimer.singleShot(0, self.switch_language))
        head.addWidget(self.ui_lang, 0, Qt.AlignTop)
        lay.addLayout(head)

        # 1. input
        self.drop = DropZone()
        self.drop.dropped.connect(self.set_input)
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(18, 16, 18, 16)
        self.in_name = QLabel(tr("Drop a document here"))
        self.in_name.setObjectName("inputName")
        self.in_name.setWordWrap(True)
        self.in_desc = QLabel(tr("A DjVu or PDF file, a photo or scan, or a folder of photos"))
        self.in_desc.setObjectName("muted")
        self.in_desc.setWordWrap(True)
        btns = QHBoxLayout()
        b1 = QPushButton(tr("Choose file…"))
        b1.clicked.connect(self.pick_file)
        b2 = QPushButton(tr("Choose folder…"))
        b2.clicked.connect(self.pick_folder)
        btns.addWidget(b1)
        btns.addWidget(b2)
        btns.addStretch()
        dl.addWidget(self.in_name)
        dl.addWidget(self.in_desc)
        dl.addSpacing(6)
        dl.addLayout(btns)
        lay.addWidget(self.drop)

        # 2. settings
        sc = card()
        form = QFormLayout(sc)
        form.setContentsMargins(18, 14, 18, 14)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.lang = QComboBox()
        self.lang.setEditable(True)
        self.lang.setInsertPolicy(QComboBox.NoInsert)
        for code in LANGUAGES:
            self.lang.addItem(language_label(code), code)
        self.lang.setToolTip(tr("Main language first. You can also type Tesseract codes, e.g. bul+rus+eng"))
        last = self.settings.value("lang", i18n.DEFAULT_OCR.get(i18n.language(), "bul+eng"))
        i = self.lang.findData(last)
        self.lang.setCurrentIndex(i) if i >= 0 else self.lang.setEditText(last)
        form.addRow(tr("Text language"), self.lang)
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr("optional, stored in the PDF"))
        form.addRow(tr("Title"), self.title)
        self.author = QLineEdit()
        self.author.setPlaceholderText(tr("optional"))
        form.addRow(tr("Author"), self.author)
        out = QHBoxLayout()
        self.outdir = QLineEdit()
        self.outdir.setPlaceholderText(tr("same folder as the input"))
        ob = QPushButton(tr("Browse…"))
        ob.clicked.connect(self.pick_outdir)
        out.addWidget(self.outdir, 1)
        out.addWidget(ob)
        form.addRow(tr("Save to"), out)
        fm = QHBoxLayout()
        self.f_pdf = QCheckBox("PDF")
        self.f_djvu = QCheckBox("DjVu")
        self.f_txt = QCheckBox(tr("Plain text"))
        for c in (self.f_pdf, self.f_djvu, self.f_txt):
            c.setChecked(True)
            fm.addWidget(c)
        self.f_djvu.setToolTip(tr("Only for DjVu books: the original file with a hidden text layer"))
        fm.addStretch()
        form.addRow(tr("Create"), fm)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText(tr("all pages   (e.g. 1-20 for a quick trial)"))
        form.addRow(tr("Pages"), self.pages)

        self.adv_btn = QToolButton()
        self.adv_btn.setText(tr("Advanced settings"))
        self.adv_btn.setCheckable(True)
        self.adv_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.adv_btn.setArrowType(Qt.RightArrow)
        self.adv_btn.setAutoRaise(True)
        self.adv_btn.toggled.connect(self.toggle_advanced)
        form.addRow("", self.adv_btn)
        self.adv = QWidget()
        af = QFormLayout(self.adv)
        af.setContentsMargins(0, 0, 0, 0)
        af.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.engine = self._combo([(tr("Automatic (best for the language)"), "auto"),
                                   (tr("Tesseract only (faster)"), "tesseract"),
                                   (tr("Tesseract + PaddleOCR (most accurate)"), "fused")])
        af.addRow(tr("OCR engine"), self.engine)
        self.page_size = QLineEdit()
        self.page_size.setPlaceholderText(tr("automatic   (or width x height in inches, e.g. 5.5x8.5)"))
        af.addRow(tr("Page size"), self.page_size)
        self.color = self._combo([(tr("Colour for covers and colour pages only"), "auto"),
                                  (tr("Greyscale everything"), "never"), (tr("Keep every page in colour"), "always")])
        af.addRow(tr("Colour"), self.color)
        self.unwarp = self._combo([(tr("Automatic (only photographed pages)"), "auto"), (tr("Always"), "always"),
                                   (tr("Never (flat scans)"), "never")])
        af.addRow(tr("Flatten pages"), self.unwarp)
        self.jobs = QSpinBox()
        self.jobs.setRange(0, 256)
        self.jobs.setSpecialValueText(trn("automatic ({n} CPU)", "automatic ({n} CPUs)", os.cpu_count() or 1))
        af.addRow(tr("Parallel jobs"), self.jobs)
        self.cleanup = QCheckBox(tr("Delete intermediate files when finished"))
        self.cleanup.setToolTip(tr("Kept by default so an interrupted or repeated run can resume quickly"))
        af.addRow("", self.cleanup)
        self.adv.setVisible(False)
        form.addRow(self.adv)
        lay.addWidget(sc)
        self.settings_card = sc

        # 3. run
        rc = card()
        rl = QGridLayout(rc)
        rl.setContentsMargins(18, 14, 18, 14)
        self.go = QPushButton(tr("Make searchable"))
        self.go.setObjectName("primary")
        self.go.setEnabled(False)
        self.go.clicked.connect(self.start)
        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel)
        self.stage = QLabel(self.status())
        self.stage.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.clock = QLabel("")
        self.clock.setObjectName("muted")
        rl.addWidget(self.stage, 0, 0)
        rl.addWidget(self.clock, 0, 1, Qt.AlignRight)
        rl.addWidget(self.bar, 1, 0, 1, 2)
        bl = QHBoxLayout()
        self.open_pdf = QPushButton(tr("Open PDF"))
        self.open_pdf.clicked.connect(lambda: self.open_output(".pdf"))
        self.open_dir = QPushButton(tr("Show in folder"))
        self.open_dir.clicked.connect(self.show_folder)
        for b in (self.open_pdf, self.open_dir):
            b.setVisible(False)
            bl.addWidget(b)
        bl.addStretch()
        bl.addWidget(self.cancel_btn)
        bl.addWidget(self.go)
        rl.addLayout(bl, 2, 0, 1, 2)
        lay.addWidget(rc)

        # log
        lh = QHBoxLayout()
        self.log_btn = QToolButton()
        self.log_btn.setText(tr("Details"))
        self.log_btn.setCheckable(True)
        self.log_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.log_btn.setArrowType(Qt.RightArrow)
        self.log_btn.setAutoRaise(True)
        self.log_btn.toggled.connect(self.toggle_log)
        lh.addWidget(self.log_btn)
        lh.addStretch()
        self.copy_btn = QPushButton(tr("Copy log"))
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.log.toPlainText()))
        lh.addWidget(self.copy_btn)
        url = repo_url()
        if url:
            rep = QPushButton(tr("Report a problem…"))
            rep.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url + "/issues/new/choose")))
            lh.addWidget(rep)
        lay.addLayout(lh)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.log.setMaximumBlockCount(5000)
        self.log.setVisible(False)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.log, 1)
        self.spacer = QWidget()
        self.spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.spacer, 1)
        foot = QLabel(f"daRealKniga {__version__} · {tr('да = yes, книга = book')} · "
                      "Tesseract, PaddleOCR, UVDoc, DjVuLibre")
        foot.setObjectName("muted")
        foot.setAlignment(Qt.AlignCenter)
        foot.setWordWrap(True)
        lay.addWidget(foot)

    # ---------------------------------------------------------------- language
    def switch_language(self):
        code = self.ui_lang.currentData()
        if self.runner or code == i18n.language():
            return
        keep = self.state()
        i18n.set_language(code)
        install_qt_translations(code)
        self.settings.setValue("ui_lang", code)
        self.build()
        self.restore(keep)

    def state(self):
        """Everything the person has entered or chosen, to carry over a language switch."""
        return {
            "lang": self.lang_code(), "title": self.title.text(), "author": self.author.text(),
            "outdir": self.outdir.text(), "pages": self.pages.text(), "page_size": self.page_size.text(),
            "formats": [c.isChecked() for c in (self.f_pdf, self.f_djvu, self.f_txt)],
            "advanced": self.adv_btn.isChecked(), "engine": self.engine.currentIndex(),
            "color": self.color.currentIndex(), "unwarp": self.unwarp.currentIndex(), "jobs": self.jobs.value(),
            "cleanup": self.cleanup.isChecked(), "log": self.log.toPlainText(), "log_open": self.log_btn.isChecked(),
            "bar": (self.bar.minimum(), self.bar.maximum(), self.bar.value()), "clock": self.clock.text(),
            "opened": [b.isVisible() for b in (self.open_pdf, self.open_dir)],
        }

    def restore(self, s):
        status = self.status
        if self.input:
            self.set_input(self.input)
        i = self.lang.findData(s["lang"])
        self.lang.setCurrentIndex(i) if i >= 0 else self.lang.setEditText(s["lang"])
        for w in ("title", "author", "outdir", "pages", "page_size"):
            getattr(self, w).setText(s[w])
        for c, on in zip((self.f_pdf, self.f_djvu, self.f_txt), s["formats"]):
            c.setChecked(on)
        self.adv_btn.setChecked(s["advanced"])
        for w in ("engine", "color", "unwarp"):
            getattr(self, w).setCurrentIndex(s[w])
        self.jobs.setValue(s["jobs"])
        self.cleanup.setChecked(s["cleanup"])
        self.log.setPlainText(s["log"])
        self.log_btn.setChecked(s["log_open"])
        self.bar.setRange(*s["bar"][:2])
        self.bar.setValue(s["bar"][2])
        self.clock.setText(s["clock"])
        for b, on in zip((self.open_pdf, self.open_dir), s["opened"]):
            b.setVisible(on)
        self.set_status(status)

    def set_status(self, fn):
        """Show a status line; `fn` makes the text, so it can be made again in another language."""
        self.status = fn
        self.stage.setText(fn())

    # ---------------------------------------------------------------- helpers
    def _combo(self, items):
        c = QComboBox()
        for name, val in items:
            c.addItem(name, val)
        return c

    def toggle_advanced(self, on):
        self.adv.setVisible(on)
        self.adv_btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)

    def toggle_log(self, on):
        self.log.setVisible(on)
        self.spacer.setVisible(not on)
        self.log_btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)

    def dragEnterEvent(self, e):
        self.drop.dragEnterEvent(e)

    def dropEvent(self, e):
        self.drop.dropEvent(e)

    def pick_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, tr("Choose a document"), self.settings.value("lastdir", os.path.expanduser("~")),
            f"{tr('Documents')} (*.djvu *.djv *.pdf *.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp);;"
            f"{tr('All files')} (*)")
        if f:
            self.set_input(f)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("Choose the folder with the page photos"),
                                             self.settings.value("lastdir", os.path.expanduser("~")))
        if d:
            self.set_input(d)

    def pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, tr("Save the results to"),
                                             self.outdir.text() or self.settings.value("lastdir", os.path.expanduser("~")))
        if d:
            self.outdir.setText(d)

    def set_input(self, path):
        if self.runner:
            return
        path = os.path.abspath(path)
        try:
            kind, desc = describe_input(path)
        except ValueError as e:
            QMessageBox.warning(self, "daRealKniga", str(e))
            return
        self.input, self.kind = path, kind
        self.settings.setValue("lastdir", os.path.dirname(path.rstrip("/")))
        self.in_name.setText(os.path.basename(path.rstrip("/")))
        hint = (tr("The page images are kept as they are; a text layer is added.")
                if kind == "djvu" else tr("Pages are flattened, cleaned and made searchable."))
        self.in_desc.setText(f"{desc} — {hint}")
        self.f_djvu.setEnabled(kind == "djvu")
        self.f_djvu.setChecked(kind == "djvu")
        if not self.title.text():
            self.title.setText(os.path.splitext(os.path.basename(path.rstrip("/")))[0])
        self.go.setEnabled(True)
        self.set_status(lambda: tr("Ready."))
        for b in (self.open_pdf, self.open_dir):
            b.setVisible(False)

    def lang_code(self):
        i = self.lang.currentIndex()
        if i >= 0 and self.lang.currentText() == self.lang.itemText(i):
            return self.lang.itemData(i)
        return self.lang.currentText().strip().split()[0] if self.lang.currentText().strip() else "bul+eng"

    def build_args(self):
        fmts = [f for f, c in (("pdf", self.f_pdf), ("djvu", self.f_djvu), ("txt", self.f_txt))
                if c.isChecked() and c.isEnabled()]
        if not fmts:
            raise ValueError(tr("Choose at least one thing to create (PDF, DjVu or plain text)."))
        a = [self.input, "--lang", self.lang_code(), "--formats", ",".join(fmts),
             "--engine", self.engine.currentData(), "--color", self.color.currentData(),
             "--unwarp", self.unwarp.currentData()]
        for flag, w in (("--title", self.title), ("--author", self.author), ("--output", self.outdir),
                        ("--pages", self.pages), ("--page-size", self.page_size)):
            if w.text().strip():
                a += [flag, w.text().strip()]
        if self.jobs.value():
            a += ["--jobs", str(self.jobs.value())]
        if self.cleanup.isChecked():
            a.append("--cleanup")
        return a

    # ---------------------------------------------------------------- running
    def start(self):
        try:
            args = self.build_args()
        except ValueError as e:
            QMessageBox.warning(self, "daRealKniga", str(e))
            return
        self.settings.setValue("lang", self.lang_code())
        self.log.clear()
        self.log.appendPlainText("$ darealkniga make " + " ".join(f'"{x}"' if " " in x else x for x in args))
        self.outputs = []
        self.runner = Runner(args)
        self.runner.line.connect(self.on_line)
        self.runner.progress.connect(self.on_progress)
        self.runner.done.connect(self.on_done)
        self.set_running(True)
        self.set_status(lambda: tr("Starting… The first run downloads the OCR models."))
        self.bar.setRange(0, 0)
        self.t0 = time.time()
        self.timer.start(1000)
        self.runner.start()

    def set_running(self, on):
        self.go.setVisible(not on)
        self.cancel_btn.setVisible(on)
        self.cancel_btn.setEnabled(True)
        self.drop.setEnabled(not on)
        self.settings_card.setEnabled(not on)
        self.ui_lang.setEnabled(not on)
        for b in (self.open_pdf, self.open_dir):
            b.setVisible(False)

    def tick(self):
        s = int(time.time() - self.t0)
        self.clock.setText(f"{s // 60}:{s % 60:02d}")

    def on_line(self, s):
        self.log.appendPlainText(s)
        if s.startswith("[darealkniga] OCR engine"):
            self.set_status(lambda: tr("Recognising text…"))
        elif s.startswith("[darealkniga] assembling PDF"):
            self.set_status(lambda: tr("Saving the PDF…"))
            self.bar.setRange(0, 0)
        elif s.startswith("[darealkniga] writing DjVu"):
            self.set_status(lambda: tr("Saving the DjVu…"))
            self.bar.setRange(0, 0)

    def on_progress(self, label, done, total):
        def text():
            name = STAGES.get(label)
            if name is not None:
                name = tr(name)
            else:
                name = tr("Recognising text") + (" (Tesseract)" if label.startswith("tesseract") else
                                                 " (PaddleOCR)" if label.startswith("paddle") else "")
            return tr("{stage}: {done} of {total}", stage=name, done=done, total=total)
        self.set_status(text)
        self.bar.setRange(0, max(1, total))
        self.bar.setValue(done)

    def cancel(self):
        if self.runner:
            self.cancel_btn.setEnabled(False)
            self.set_status(lambda: tr("Stopping…"))
            self.runner.cancel()

    def on_done(self, code, outputs):
        self.timer.stop()
        self.runner.wait()
        cancelled = self.runner.cancelled
        self.runner = None
        self.set_running(False)
        self.bar.setRange(0, 1)
        self.outputs = outputs
        if code == 0:
            self.bar.setValue(1)
            # "[darealkniga] recognised 12,345 words on 212 pages"
            m = next((re.search(r"recognised ([\d,]+) words on (\d+) pages", l)
                      for l in reversed(self.log.toPlainText().splitlines()) if "recognised" in l), None)
            if m:
                words, pages = int(m.group(1).replace(",", "")), int(m.group(2))
                self.set_status(lambda: tr("Done. Pages: {pages}. Words recognised: {words}.",
                                           pages=i18n.number(pages), words=i18n.number(words)))
            else:
                self.set_status(lambda: tr("Done."))
            self.open_pdf.setVisible(any(o.endswith(".pdf") for o in outputs))
            self.open_dir.setVisible(bool(outputs))
        elif cancelled:
            self.bar.setValue(0)
            self.set_status(lambda: tr("Cancelled. Starting again resumes where it stopped."))
        else:
            self.bar.setValue(0)
            self.set_status(lambda: tr("Something went wrong. See Details."))
            self.log_btn.setChecked(True)

    def open_output(self, ext):
        f = next((o for o in self.outputs if o.endswith(ext)), None)
        if f:
            QDesktopServices.openUrl(QUrl.fromLocalFile(f))

    def show_folder(self):
        if self.outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.outputs[0])))

    def closeEvent(self, e):
        if self.runner:
            box = QMessageBox(QMessageBox.Question, "daRealKniga",
                              tr("A document is being processed. Stop it and quit?"), parent=self)
            stop = box.addButton(tr("Stop and quit"), QMessageBox.AcceptRole)
            box.addButton(tr("Cancel"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not stop:
                e.ignore()
                return
            self.runner.cancel()
            self.runner.wait(6000)
        e.accept()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    smoke = "--smoke-test" in argv
    argv = [a for a in argv if a != "--smoke-test"]
    extend_path()
    QApplication.setApplicationName("darealkniga")
    QApplication.setDesktopFileName("darealkniga")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyleSheet(STYLE)
    install_qt_translations(start_language(QSettings("darealkniga", "darealkniga")))
    w = Window(argv[0] if argv else None)
    w.show()
    if smoke:  # used by the AppImage build: create the window, render it, quit
        app.processEvents()
        out = os.environ.get("DAREALKNIGA_SCREENSHOT")
        if out:
            w.grab().save(out)
        print("gui ok", flush=True)
        rc = 0
    else:
        rc = app.exec()
    # destroy the window while Qt is still alive; left to interpreter shutdown, the
    # destruction order is undefined and can segfault
    import shiboken6
    shiboken6.delete(w)
    return rc


if __name__ == "__main__":
    sys.exit(main())
