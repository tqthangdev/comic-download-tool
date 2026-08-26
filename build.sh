#!/usr/bin/env bash

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

VENV="$PROJECT_DIR/.venv"
PYTHON="$VENV/bin/python"

echo "=========================================="
echo " ComicDownloadTool - Linux ONEDIR Build"
echo "=========================================="

# ==========================================
# VENV
# ==========================================

if [ ! -x "$PYTHON" ]; then
    echo "=== Creating venv ==="
    python -m venv "$VENV"
fi

echo
echo "=== Python ==="
"$PYTHON" --version

# ==========================================
# DEPENDENCIES
# ==========================================

echo
echo "=== Installing dependencies ==="

"$PYTHON" -m pip install -r requirements.txt
"$PYTHON" -m pip install pyinstaller

# ==========================================
# PLAYWRIGHT
# ==========================================

echo
echo "=== Installing Playwright Chromium ==="

"$PYTHON" -m playwright install chromium

# ==========================================
# VERIFY
# ==========================================

echo
echo "=== Verify project ==="

test -f run.py
test -f config.json
test -f assets/icon.png

# ==========================================
# CLEAN OLD BUILD
# ==========================================

echo
echo "=== Cleaning previous build ==="

rm -rf \
    "$PROJECT_DIR/build" \
    "$PROJECT_DIR/dist" \
    "$PROJECT_DIR/run.spec"

# ==========================================
# CREATE SPEC
# ==========================================

echo
echo "=== Creating PyInstaller spec ==="

cat > run.spec <<'EOF'
from pathlib import Path
import playwright

block_cipher = None

BASE_DIR = Path(SPECPATH)

PLAYWRIGHT_DRIVER_PATH = (
    Path(playwright.__file__).parent / "driver"
)

datas = [
    (
        str(BASE_DIR / "assets"),
        "assets",
    ),
    (
        str(BASE_DIR / "config.json"),
        ".",
    ),
    (
        str(PLAYWRIGHT_DRIVER_PATH),
        "playwright/driver",
    ),
]

# ==========================================
# PLAYWRIGHT CHROMIUM
# ==========================================

browser_path = (
    Path.home()
    / ".cache"
    / "ms-playwright"
)

for browser_dir in browser_path.glob("chromium-*"):
    if browser_dir.is_dir():
        datas.append(
            (
                str(browser_dir),
                "ms-playwright/" + browser_dir.name,
            )
        )

# ==========================================
# ANALYSIS
# ==========================================

a = Analysis(
    [str(BASE_DIR / "run.py")],

    pathex=[
        str(BASE_DIR),
    ],

    binaries=[],

    datas=datas,

    hiddenimports=[
        "playwright.async_api",
        "playwright.__main__",
        "qasync",
        "aiohttp",
        "bs4",
        "lxml",
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],

    win_no_prefer_redirects=False,
    win_private_assemblies=False,

    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,

    exclude_binaries=True,

    name="ComicDownloadTool",

    debug=False,
    bootloader_ignore_signals=False,

    strip=False,
    upx=True,

    console=False,

    icon=None,

    disable_windowed_traceback=False,
    argv_emulation=False,

    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,

    strip=False,
    upx=True,

    name="ComicDownloadTool",
)
EOF

# ==========================================
# BUILD ONEDIR
# ==========================================

echo
echo "=== Building ONEDIR ==="

"$PYTHON" -m PyInstaller \
    run.spec \
    --noconfirm \
    --clean

# ==========================================
# VERIFY
# ==========================================

echo
echo "=== Verify build ==="

if [ ! -f "$PROJECT_DIR/dist/ComicDownloadTool/ComicDownloadTool" ]; then
    echo "ERROR: Build failed."
    exit 1
fi

# ==========================================
# CLEAN BUILD FILES
# ==========================================

echo
echo "=== Removing temporary files ==="

rm -rf \
    "$PROJECT_DIR/build" \
    "$PROJECT_DIR/run.spec"

# ==========================================
# RESULT
# ==========================================

echo
echo "=========================================="
echo " Build successful"
echo "=========================================="

du -sh "$PROJECT_DIR/dist/ComicDownloadTool"

echo
echo "Output:"
echo "$PROJECT_DIR/dist/ComicDownloadTool/"