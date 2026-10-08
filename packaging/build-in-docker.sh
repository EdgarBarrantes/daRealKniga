#!/usr/bin/env bash
# Builds the AppImage and tarball inside a clean Ubuntu 22.04 container (needs only Docker).
#   packaging/build-in-docker.sh            -> dist/darealkniga-<version>-x86_64.AppImage (+ .tar.gz)
#   VERSION=1.2.3 packaging/build-in-docker.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm \
  -e VERSION="${VERSION:-}" -e REPO_URL="${REPO_URL:-}" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$ROOT:/work" -w /work ubuntu:22.04 bash packaging/build-appimage.sh
