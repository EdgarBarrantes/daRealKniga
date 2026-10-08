"""Interface tests (offscreen; skipped when PySide6 is not installed)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
import shiboken6  # noqa: E402

from realkniga import gui  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    a.setStyleSheet(gui.STYLE)
    return a


@pytest.fixture
def window(app):
    """Windows are destroyed explicitly while Qt is alive; left to interpreter shutdown,
    PySide can crash at exit ('shared QObject was deleted directly')."""
    made = []

    def make(path):
        w = gui.Window(path)
        made.append(w)
        return w
    yield make
    for w in made:
        w.close()
        shiboken6.delete(w)


@pytest.fixture
def pdf_book(tmp_path):
    import pikepdf
    p = pikepdf.new()
    for _ in range(3):
        p.add_blank_page()
    f = tmp_path / "Under the Yoke.pdf"
    p.save(f)
    return str(f)


def test_window_builds_arguments(window, pdf_book, tmp_path):
    w = window(pdf_book)
    assert w.kind == "photo" and w.go.isEnabled()
    assert "3 pages" in w.in_desc.text()
    assert not w.f_djvu.isEnabled()          # DjVu output only for DjVu input
    w.lang.setCurrentIndex(w.lang.findData("rus"))
    w.author.setText("Иван Вазов")
    w.outdir.setText(str(tmp_path / "out"))
    w.pages.setText("1-2")
    a = w.build_args()
    assert a[0] == pdf_book
    assert a[a.index("--lang") + 1] == "rus"
    assert a[a.index("--formats") + 1] == "pdf,txt"
    assert a[a.index("--title") + 1] == "Under the Yoke"
    assert a[a.index("--author") + 1] == "Иван Вазов"
    assert a[a.index("--pages") + 1] == "1-2"
    assert "--cleanup" not in a


def test_custom_language_code(window, pdf_book):
    w = window(pdf_book)
    w.lang.setEditText("bul+rus+eng")
    assert w.lang_code() == "bul+rus+eng"


def test_rejects_unknown_input(tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(ValueError):
        gui.describe_input(str(tmp_path / "notes.txt"))
    with pytest.raises(ValueError):
        gui.describe_input(str(tmp_path))     # folder without images


def test_folder_of_photos(tmp_path):
    from PIL import Image
    for i in (1, 2, 10):
        Image.new("RGB", (20, 30), "white").save(tmp_path / f"p{i}.jpg")
    kind, desc = gui.describe_input(str(tmp_path))
    assert kind == "photo" and "3 page images" in desc
