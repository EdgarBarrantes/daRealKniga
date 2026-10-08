#!/usr/bin/env bash
# Installs realkniga into ./.venv and links the `realkniga` command into ~/.local/bin.
# System tools (installed separately): djvulibre (DjVu input) and tesseract-ocr or Docker.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
if [ "${GPU:-0}" = 1 ]; then
  # CUDA build of PaddlePaddle; see https://www.paddlepaddle.org.cn/install for other CUDA versions
  .venv/bin/pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
fi
.venv/bin/pip install -e ".[gui]"
mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/.venv/bin/realkniga" "$HOME/.local/bin/realkniga"
echo
.venv/bin/realkniga doctor || true
cat <<MSG

Installed. Run:  realkniga make <book.djvu | document.pdf | photo.jpg | photos-folder> --lang bul+eng   (or: realkniga gui)
(make sure ~/.local/bin is on your PATH)
Missing system tools?  Debian/Ubuntu:  sudo apt install djvulibre-bin tesseract-ocr
                       macOS:          brew install djvulibre tesseract
MSG
