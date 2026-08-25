#!/usr/bin/env bash
# ============================================================
#  Auto installer for the Comic Download Tool (Linux / macOS)
#
#  Installs everything needed to run the app, all kept inside
#  the code folder:
#    1. Creates a virtual environment (.venv) — if the system
#       cannot create one it falls back to installing packages
#       into vendor/.
#    2. Installs the dependencies listed in requirements.txt.
#    3. Downloads Chromium for Playwright into ms-playwright/.
#
#  Usage:
#    ./setup.sh                # install everything
#    ./setup.sh --no-venv      # skip venv, install packages into vendor/
#    ./setup.sh --skip-browsers # skip downloading Chromium (packages only)
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PY=".venv/bin/python"
VEN=".venv"
VENDOR_DIR="vendor"
BROWSERS_DIR="ms-playwright"

NO_VENV=false
SKIP_BROWSERS=false
for arg in "$@"; do
    case "$arg" in
        --no-venv) NO_VENV=true ;;
        --skip-browsers) SKIP_BROWSERS=true ;;
        *) echo "Khong nhan dien duoc doi so: $arg"; echo "Huu ich: --no-venv, --skip-browsers"; exit 1 ;;
    esac
done

echo "============================================================"
echo "  Comic Download Tool - Auto Installer"
echo "============================================================"
echo
echo "Python: $($PYTHON_BIN --version 2>/dev/null || echo 'not found')"
echo "Hệ điều hành: $(uname -s)"

if [ ! -f "requirements.txt" ]; then
    echo
    echo "LOI: khong tim thay requirements.txt trong thu muc project."
    exit 1
fi

# ================= 1. VIRTUAL ENVIRONMENT =================
VENV_MODE="venv"
if [ "$NO_VENV" = true ]; then
    echo
    echo "[1/3] Bo qua tao venv (--no-venv), cai package vao thu muc vendor/."
    VENV_MODE="vendor"
else
    echo
    echo "[1/3] Tao virtual environment..."
    if ! "$PYTHON_BIN" -m venv "$VEN" 2>/dev/null || [ ! -x "$VENV_PY" ]; then
        echo "   Khong tao duoc venv -> Fallback: cai package vao thu muc vendor/ trong project."
        VENV_MODE="vendor"
    else
        echo "   Virtual environment da san sang: $VEN"
    fi
fi

PY="$PYTHON_BIN"
export PYTHONPATH=""
if [ "$VENV_MODE" = "venv" ]; then
    PY="$VENV_PY"
else
    mkdir -p "$VENDOR_DIR"
    export PYTHONPATH="$PWD/$VENDOR_DIR"
fi

# ================= 2. INSTALL DEPENDENCIES =================
echo
echo "[2/3] Cai dat dependencies..."
"$PY" -m pip install --upgrade pip
if [ "$VENV_MODE" = "vendor" ]; then
    "$PY" -m pip install --target "$VENDOR_DIR" -r requirements.txt
else
    "$PY" -m pip install -r requirements.txt
fi

# ================= 3. PLAYWRIGHT BROWSERS =================
if [ "$SKIP_BROWSERS" = true ]; then
    echo
    echo "[3/3] Bo qua tai Chromium (--skip-browsers)."
else
    echo
    echo "[3/3] Tai Chromium cho Playwright (co the mat vai phut)..."
    # Install Chromium into project/ms-playwright so the app always runs
    # from the code folder (portable), independent of the machine's cache.
    PLAYWRIGHT_BROWSERS_PATH="$PWD/$BROWSERS_DIR" "$PY" -m playwright install chromium
fi

# ================= DONE =================
echo
echo "============================================================"
echo "  Hoan tat! Chay app bang lenh:"
if [ "$VENV_MODE" = "venv" ]; then
    echo "    $PWD/.venv/bin/python run.py"
else
    echo "    PYTHONPATH=$PWD/$VENDOR_DIR $PYTHON_BIN run.py"
fi
echo "============================================================"