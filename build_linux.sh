#!/usr/bin/env bash
# ============================================================
#  Build the Linux standalone app with PyInstaller
#  Run this on a Linux machine from the project folder.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[1/3] Creating virtual environment..."
if [ ! -d ".venv" ]; then
    "$PYTHON_BIN" -m venv .venv
fi

# Fallback nếu venv không tạo được / không hoạt động
if ! .venv/bin/python --version >/dev/null 2>&1; then
    echo "[!] venv failed, trying --target install into vendor/ instead."
    mkdir -p vendor
    "$PYTHON_BIN" -m pip install --target vendor --upgrade pip
    "$PYTHON_BIN" -m pip install --target vendor PyInstaller -r requirements.txt
    echo "[*] Building with PYTHONPATH=vendor ..."
    PYTHONPATH=vendor "$PYTHON_BIN" -m PyInstaller run.spec --noconfirm
    echo
    echo "Build complete! See dist/ComicDownloadTool/"
    exit 0
fi

echo "[2/3] Installing dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install PyInstaller -r requirements.txt

echo "[3/3] Building executable..."
.venv/bin/python -m PyInstaller run.spec --noconfirm

echo
echo "Build complete! Output folder:"
echo "  $(pwd)/dist/ComicDownloadTool/"
echo "Copy the WHOLE 'ComicDownloadTool' folder when distributing."