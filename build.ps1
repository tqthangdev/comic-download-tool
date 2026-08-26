$ErrorActionPreference = "Stop"

$PROJECT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $PROJECT_DIR

$VENV = Join-Path $PROJECT_DIR ".venv"
$PYTHON = Join-Path $VENV "Scripts\python.exe"

Write-Host "=========================================="
Write-Host " ComicDownloadTool - Windows ONEDIR Build"
Write-Host "=========================================="

# ==========================================
# VENV
# ==========================================

if (!(Test-Path $PYTHON)) {
    Write-Host "=== Creating venv ==="
    python -m venv $VENV
}

Write-Host ""
Write-Host "=== Python ==="
& $PYTHON --version

# ==========================================
# DEPENDENCIES
# ==========================================

Write-Host ""
Write-Host "=== Installing dependencies ==="

& $PYTHON -m pip install -r requirements.txt
& $PYTHON -m pip install pyinstaller

# ==========================================
# PLAYWRIGHT
# ==========================================

Write-Host ""
Write-Host "=== Installing Playwright Chromium ==="

& $PYTHON -m playwright install chromium

# ==========================================
# VERIFY
# ==========================================

Write-Host ""
Write-Host "=== Verify project ==="

if (!(Test-Path "run.py")) {
    throw "run.py was not found."
}

if (!(Test-Path "data\config.json")) {
    throw "data\config.json was not found."
}

if (!(Test-Path "assets\icon.ico")) {
    throw "assets\icon.ico was not found."
}

# ==========================================
# CLEAN OLD BUILD
# ==========================================

Write-Host ""
Write-Host "=== Cleaning previous build ==="

Remove-Item `
    "build" `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    "dist" `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    "run.spec" `
    -Force `
    -ErrorAction SilentlyContinue

# ==========================================
# CREATE SPEC
# ==========================================

Write-Host ""
Write-Host "=== Creating PyInstaller spec ==="

@"
from pathlib import Path
import os
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
        str(BASE_DIR / "data" / "config.json"),
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
    Path(os.environ["LOCALAPPDATA"])
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

    name="ComicDownloadTool",
)
"@ | Set-Content -Path "run.spec" -Encoding UTF8

# ==========================================
# BUILD ONEDIR
# ==========================================

Write-Host ""
Write-Host "=== Building ONEDIR ==="

& $PYTHON -m PyInstaller `
    run.spec `
    --noconfirm `
    --clean

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

# ==========================================
# VERIFY
# ==========================================

Write-Host ""
Write-Host "=== Verify build ==="

$EXE = "dist\ComicDownloadTool\ComicDownloadTool.exe"

if (!(Test-Path $EXE)) {
    throw "Build failed: ComicDownloadTool.exe was not created."
}

# ==========================================
# CLEAN BUILD FILES
# ==========================================

Write-Host ""
Write-Host "=== Removing temporary files ==="

Remove-Item `
    "build" `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    "run.spec" `
    -Force `
    -ErrorAction SilentlyContinue

# ==========================================
# RESULT
# ==========================================

Write-Host ""
Write-Host "=========================================="
Write-Host " Build successful"
Write-Host "=========================================="

$SIZE = (
    Get-ChildItem `
        "dist\ComicDownloadTool" `
        -Recurse `
        -File |
    Measure-Object Length -Sum
).Sum

Write-Host "Build size: $([math]::Round($SIZE / 1MB, 2)) MB"

Write-Host ""
Write-Host "Output:"
Write-Host "$PROJECT_DIR\dist\ComicDownloadTool\"