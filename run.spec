# run.spec
from pathlib import Path

import playwright


# ==========================================
# PATHS
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
PLAYWRIGHT_DRIVER_PATH = Path(playwright.__file__).parent / "driver"

block_cipher = None


# ==========================================
# ANALYSIS
# ==========================================

a = Analysis(
    [str(BASE_DIR / "run.py")],
    pathex=[
        str(BASE_DIR),
    ],
    binaries=[],
    datas=[
        # Bundle toàn bộ assets/ vào:
        # dist/ComicDownloadTool/assets/
        (
            str(BASE_DIR / "assets"),
            "assets",
        ),

        # Bundle config.json vào root output
        (
            str(BASE_DIR / "config.json"),
            ".",
        ),

        # Bundle Playwright Python driver
        (
            str(PLAYWRIGHT_DRIVER_PATH),
            "playwright/driver",
        ),
    ],
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


# ==========================================
# PYZ
# ==========================================

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)


# ==========================================
# EXECUTABLE
# ==========================================

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ComicDownloadTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,

    # Windows executable icon
    icon=str(BASE_DIR / "assets" / "icon.ico"),

    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)


# ==========================================
# COLLECT
# ==========================================

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ComicDownloadTool",
)