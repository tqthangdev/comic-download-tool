# run.spec
from pathlib import Path

import playwright

block_cipher = None

# PyInstaller is executed from the project root in GitHub Actions
BASE_DIR = Path.cwd()

# Locate the actual Playwright driver directory
PLAYWRIGHT_DRIVER_PATH = Path(playwright.__file__).parent / "driver"


a = Analysis(
    [str(BASE_DIR / "run.py")],
    pathex=[
        str(BASE_DIR),
    ],
    binaries=[],
    datas=[
        # Bundle the entire assets/ directory
        (
            str(BASE_DIR / "assets"),
            "assets",
        ),

        # Bundle config.json
        (
            str(BASE_DIR / "config.json"),
            ".",
        ),

        # Bundle the Playwright driver
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


pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)


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
    icon=str(BASE_DIR / "assets" / "icon.ico"),
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
    upx_exclude=[],
    name="ComicDownloadTool",
)