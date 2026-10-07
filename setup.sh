#!/usr/bin/env bash
# ============================================================
#  Auto installer for the Comic Download Tool (Linux / macOS)
#
#  Installs everything needed to run the app, all kept inside
#  the code folder:
#    1. Creates a virtual environment (.venv) — if the system
#       cannot create one it falls back to installing packages
#       into vendor/.
#    2. Installs the dependencies listed in pyproject.toml.
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
        *) echo "Unknown argument: $arg"; echo "Valid options: --no-venv, --skip-browsers"; exit 1 ;;
    esac
done

echo "============================================================"
echo "  Comic Download Tool - Auto Installer"
echo "============================================================"
echo
echo "Python: $($PYTHON_BIN --version 2>/dev/null || echo 'not found')"
echo "OS: $(uname -s)"

if [ ! -f "pyproject.toml" ]; then
    echo
    echo "ERROR: pyproject.toml was not found in the project folder."
    exit 1
fi

# ================= 1. VIRTUAL ENVIRONMENT =================
VENV_MODE="venv"
if [ "$NO_VENV" = true ]; then
    echo
    echo "[1/3] Skipping venv (--no-venv), installing packages into vendor/."
    VENV_MODE="vendor"
else
    echo
    echo "[1/3] Creating virtual environment..."
    if ! "$PYTHON_BIN" -m venv "$VEN" 2>/dev/null || [ ! -x "$VENV_PY" ]; then
        echo "   Could not create venv -> Falling back to installing packages into the project's vendor/ folder."
        VENV_MODE="vendor"
    else
        echo "   Virtual environment ready: $VEN"
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
echo "[2/3] Installing dependencies..."
"$PY" -m pip install --upgrade pip
if [ "$VENV_MODE" = "vendor" ]; then
    "$PY" -m pip install --target "$VENDOR_DIR" .
else
    "$PY" -m pip install -e .
fi

# ---- Fix nodriver's UTF-8 bug (cdp/network.py contains latin-1 bytes) ----
# We cannot import nodriver to locate it (that import is the failure), so use
# sysconfig to resolve the venv's site-packages; vendor mode points at vendor/.
FIX_SCRIPT="$PWD/lib/fix_nodriver.py"
if [ "$VENV_MODE" = "vendor" ]; then
    NODRIVER_DIR="$PWD/$VENDOR_DIR/nodriver"
else
    NODRIVER_DIR="$("$PY" -c "import sysconfig, os; print(os.path.join(sysconfig.get_paths()['purelib'], 'nodriver'))")"
fi
if [ -f "$FIX_SCRIPT" ]; then
    echo "  Patching nodriver UTF-8 encoding..."
    "$PY" "$FIX_SCRIPT" "$NODRIVER_DIR"
else
    echo "  Warning: $FIX_SCRIPT not found, skipping nodriver patch."
fi

# ================= 3. PLAYWRIGHT BROWSERS =================
if [ "$SKIP_BROWSERS" = true ]; then
    echo
    echo "[3/3] Skipping Chromium download (--skip-browsers)."
else
    echo
    echo "[3/3] Downloading Chromium for Playwright (this may take a few minutes)..."
    # Install Chromium into project/ms-playwright so the app always runs
    # from the code folder (portable), independent of the machine's cache.
    PLAYWRIGHT_BROWSERS_PATH="$PWD/$BROWSERS_DIR" "$PY" -m playwright install chromium
fi

# ================= DONE =================
echo
echo "============================================================"
echo "  Done! Run the app with:"
if [ "$VENV_MODE" = "venv" ]; then
    echo "    $PWD/.venv/bin/python run.py"
else
    echo "    PYTHONPATH=$PWD/$VENDOR_DIR $PYTHON_BIN run.py"
fi
echo "============================================================"
