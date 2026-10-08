#!/usr/bin/env bash
# Builds a self-contained realkniga AppImage plus a portable tarball of the same files:
#   dist/realkniga-<version>-x86_64.AppImage
#   dist/realkniga-<version>-x86_64.tar.gz
#   dist/SHA256SUMS
#
# Bundled: Python 3.12 (python-build-standalone), realkniga with PaddleOCR/UVDoc and the Qt
# interface, Tesseract 5 and the DjVuLibre tools. OCR models are downloaded on first use.
#
# Runs on Ubuntu 22.04 as root, so the result works on any distribution with glibc 2.35 or
# newer. Elsewhere, use packaging/build-in-docker.sh.
# Environment: VERSION (default: from pyproject.toml), REPO_URL (enables "Report a problem").
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${BUILD_DIR:-$ROOT/build}"
DIST="$ROOT/dist"
VERSION="${VERSION:-$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")}"
VERSION="${VERSION#v}"
NAME="realkniga-$VERSION-x86_64"

PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20260804/cpython-3.12.13%2B20260804-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_SHA="ce2c9c5df1b99a962a86d2f457656918ee5f01b2edea080db28416232a1fcb11"
LD_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/1-alpha-20251107-1/linuxdeploy-x86_64.AppImage"
LD_SHA="c20cd71e3a4e3b80c3483cef793cda3f4e990aca14014d23c544ca3ce1270b4d"
AIT_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
AIT_SHA="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

# xcb libraries Qt's X11 plugin needs, shipped as a fallback (see AppRun)
QT_EXTRA_LIBS="libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 libxcb-randr.so.0
  libxcb-render-util.so.0 libxcb-shape.so.0 libxcb-xinerama.so.0 libxcb-xkb.so.1 libxcb-util.so.1
  libxkbcommon-x11.so.0 libxkbcommon.so.0"
TOOLS="tesseract ddjvu djvused djvudump djvm djvutxt"

export DEBIAN_FRONTEND=noninteractive APPIMAGE_EXTRACT_AND_RUN=1
step() { printf '\n==> %s\n' "$*"; }
fetch() {  # url sha256 destination
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c --quiet -
}

step "build dependencies"
apt-get update -qq
apt-get install -y -qq --no-install-recommends ca-certificates curl file gnupg pigz \
  software-properties-common djvulibre-bin binutils \
  libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
  libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-util1 libxkbcommon-x11-0 libxkbcommon0 \
  libegl1 libgl1 libfontconfig1 libdbus-1-3 libglib2.0-0 >/dev/null
add-apt-repository -y ppa:alex-p/tesseract-ocr5 >/dev/null  # Tesseract 5 for Ubuntu 22.04
apt-get install -y -qq --no-install-recommends tesseract-ocr >/dev/null
tesseract --version | head -1

step "sources ($VERSION)"
rm -rf "$BUILD"
mkdir -p "$BUILD/src" "$DIST"
tar -C "$ROOT" --exclude=./.venv --exclude=./build --exclude=./dist --exclude=./.git \
  --exclude='*.egg-info' --exclude=__pycache__ -cf - . | tar -C "$BUILD/src" -xf -
SRC="$BUILD/src"
sed -i "s/^version = \".*\"/version = \"$VERSION\"/" "$SRC/pyproject.toml"
sed -i "s/^__version__ = \".*\"/__version__ = \"$VERSION\"/" "$SRC/realkniga/__init__.py"
if [ -n "${REPO_URL:-}" ]; then
  printf 'REPO_URL = "%s"\n' "$REPO_URL" > "$SRC/realkniga/_build.py"
fi

APPDIR="$BUILD/AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/qt-extra"

step "python + realkniga"
fetch "$PY_URL" "$PY_SHA" "$BUILD/python.tar.gz"
tar -C "$APPDIR/usr" -xzf "$BUILD/python.tar.gz"   # -> usr/python
PY="$APPDIR/usr/python/bin/python3"
"$PY" -m pip install -q --no-cache-dir --upgrade pip
"$PY" -m pip install -q --no-cache-dir "$SRC[gui]"
cat > "$APPDIR/usr/bin/realkniga" <<'EOS'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/../python/bin/python3" -m realkniga "$@"
EOS
chmod +x "$APPDIR/usr/bin/realkniga"

step "Qt fallback libraries"
for l in $QT_EXTRA_LIBS; do
  cp -L "/usr/lib/x86_64-linux-gnu/$l" "$APPDIR/usr/lib/qt-extra/"
done
QXCB="$(find "$APPDIR/usr/python" -name libqxcb.so | head -1)"
if LD_LIBRARY_PATH="$APPDIR/usr/lib/qt-extra" ldd "$QXCB" | grep "not found"; then
  echo "Qt xcb plugin has unresolved libraries" >&2
  exit 1
fi

step "Tesseract and DjVuLibre (linuxdeploy)"
fetch "$LD_URL" "$LD_SHA" "$BUILD/linuxdeploy"
chmod +x "$BUILD/linuxdeploy"
cp "$ROOT/packaging/realkniga.desktop" "$BUILD/realkniga.desktop"
cp "$SRC/realkniga/data/icon.png" "$BUILD/realkniga.png"
args=()
for t in $TOOLS; do args+=(--executable "$(command -v "$t")"); done
"$BUILD/linuxdeploy" --appdir "$APPDIR" "${args[@]}" \
  --desktop-file "$BUILD/realkniga.desktop" --icon-file "$BUILD/realkniga.png" >"$BUILD/linuxdeploy.log" 2>&1 \
  || { tail -40 "$BUILD/linuxdeploy.log"; exit 1; }
rm -f "$APPDIR/AppRun"
cp "$ROOT/packaging/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"

step "smoke tests"
"$APPDIR/AppRun" --version
"$APPDIR/AppRun" doctor
for t in $TOOLS; do  # bundled tools must resolve all libraries from the AppDir or the base system
  if ldd "$APPDIR/usr/bin/$t" | grep "not found"; then echo "$t: missing libraries" >&2; exit 1; fi
done
QT_QPA_PLATFORM=offscreen "$APPDIR/AppRun" gui --smoke-test

step "AppImage"
fetch "$AIT_URL" "$AIT_SHA" "$BUILD/appimagetool"
chmod +x "$BUILD/appimagetool"
rm -f "$DIST/$NAME.AppImage" "$DIST/$NAME.tar.gz"
ARCH=x86_64 VERSION="$VERSION" "$BUILD/appimagetool" --no-appstream "$APPDIR" "$DIST/$NAME.AppImage"

step "tarball"
tar -C "$BUILD" --transform "s,^AppDir,realkniga-$VERSION," -I pigz -cf "$DIST/$NAME.tar.gz" AppDir
(cd "$DIST" && sha256sum "$NAME.AppImage" "$NAME.tar.gz" > SHA256SUMS)

if [ -n "${HOST_UID:-}" ]; then
  chown -R "$HOST_UID:${HOST_GID:-$HOST_UID}" "$DIST" "$BUILD"
fi
step "done"
ls -lh "$DIST"
