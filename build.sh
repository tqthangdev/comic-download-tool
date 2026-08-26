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
    python3 -m venv "$VENV"
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
    hooksconfig=[],
    runtime_hooks=[],

    # Do not bundle system GUI libraries.
    # Linux Qt/GTK/Wayland/X11 libraries must
    # come from the target system.
    excludes=[
        "libxkbcommon",
        "libwayland-client",
        "libwayland-cursor",
        "libwayland-egl",
        "libX11",
        "libX11-xcb",
        "libxcb",
    ],

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
# REMOVE SYSTEM GUI LIBRARIES
# ==========================================

echo
echo "=== Removing bundled system GUI libraries ==="

INTERNAL_DIR="$PROJECT_DIR/dist/ComicDownloadTool/_internal"

rm -f \
    "$INTERNAL_DIR"/libxkbcommon.so.* \
    "$INTERNAL_DIR"/libwayland-client.so.* \
    "$INTERNAL_DIR"/libwayland-cursor.so.* \
    "$INTERNAL_DIR"/libwayland-egl.so.* \
    "$INTERNAL_DIR"/libX11.so.* \
    "$INTERNAL_DIR"/libX11-xcb.so.* \
    "$INTERNAL_DIR"/libxcb*.so.*

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
# VERIFY PLAYWRIGHT
# ==========================================

echo
echo "=== Verify Playwright Chromium ==="

CHROMIUM_COUNT=$(
    find "$INTERNAL_DIR/ms-playwright" \
        -type f \
        -name chrome \
        2>/dev/null |
    wc -l
)

if [ "$CHROMIUM_COUNT" -eq 0 ]; then
    echo "ERROR: Playwright Chromium was not bundled."
    exit 1
fi

echo "Chromium executable(s): $CHROMIUM_COUNT"

# ==========================================
# VERIFY SYSTEM GUI LIBRARIES
# ==========================================

echo
echo "=== Verify bundled system GUI libraries ==="

if find "$INTERNAL_DIR" -maxdepth 1 -type f \
    \( \
        -name 'libxkbcommon.so.*' \
        -o -name 'libwayland-client.so.*' \
        -o -name 'libwayland-cursor.so.*' \
        -o -name 'libwayland-egl.so.*' \
        -o -name 'libX11.so.*' \
        -o -name 'libX11-xcb.so.*' \
        -o -name 'libxcb*.so.*' \
    \) \
    | grep -q .; then

    echo "ERROR: System GUI libraries are still bundled:"
    find "$INTERNAL_DIR" -maxdepth 1 -type f \
        \( \
            -name 'libxkbcommon.so.*' \
            -o -name 'libwayland-client.so.*' \
            -o -name 'libwayland-cursor.so.*' \
            -o -name 'libwayland-egl.so.*' \
            -o -name 'libX11.so.*' \
            -o -name 'libX11-xcb.so.*' \
            -o -name 'libxcb*.so.*' \
        \)
    exit 1
fi

echo "OK: No system GUI libraries bundled."

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