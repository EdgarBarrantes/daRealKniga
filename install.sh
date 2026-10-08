#!/usr/bin/env bash
# Installs darealkniga into ./.venv and links the `darealkniga` command (and its short form
# `drk`) into ~/.local/bin.
# System tools (installed separately): djvulibre (DjVu input) and tesseract-ocr or Docker.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -e ".[gui]"
mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/.venv/bin/darealkniga" "$HOME/.local/bin/darealkniga"
ln -sf "$PWD/.venv/bin/drk" "$HOME/.local/bin/drk"
echo
.venv/bin/darealkniga doctor || true
cat <<MSG

Installed. Run:  darealkniga make <book.djvu | document.pdf | photo.jpg | photos-folder> --lang bul+eng   (or: darealkniga gui)
Short form, same command:  drk make book.pdf --lang bul
(make sure ~/.local/bin is on your PATH)
Missing system tools?  Debian/Ubuntu:  sudo apt install djvulibre-bin tesseract-ocr
                       macOS:          brew install djvulibre tesseract
MSG
