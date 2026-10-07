# ============================================================
#  Auto installer for the Comic Download Tool (Windows)
#
#  Usage:
#    powershell -ExecutionPolicy Bypass -File setup.ps1
#    powershell -ExecutionPolicy Bypass -File setup.ps1 -NoVenv
#    powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipBrowsers
# ============================================================
param(
    [switch]$NoVenv,
    [switch]$SkipBrowsers
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Write-Step($title) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  $title"
    Write-Host "============================================================"
}

$VENV_DIR     = Join-Path $PSScriptRoot ".venv"
$VENDOR_DIR   = Join-Path $PSScriptRoot "vendor"
$BROWSERS_DIR = Join-Path $PSScriptRoot "ms-playwright"
$PYTHON_DIR   = Join-Path $PSScriptRoot "python"
$FixScript    = Join-Path $PSScriptRoot "lib\fix_nodriver.py"

# Try running a python command with the given args; returns $true if it works
function Test-Python($exe, $pyArgs) {
    try {
        $null = & $exe @pyArgs --version 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

# ================= 0. FIND PYTHON =================
Write-Step "Finding Python..."
$PythonExe  = $null
$PythonArgs = @()

# Use python from PATH; if missing, try "py -3" (newest installed version)
if (Get-Command python -ErrorAction SilentlyContinue) {
    if (Test-Python "python" @()) { $PythonExe = "python" }
}
if (-not $PythonExe -and (Get-Command py -ErrorAction SilentlyContinue)) {
    if (Test-Python "py" @("-3")) { $PythonExe = "py"; $PythonArgs = @("-3") }
}
if ($PythonExe) {
    $verText = & $PythonExe @PythonArgs --version
    Write-Host "  Using Python: $verText"
}

# No Python found -> download the embeddable build
if (-not $PythonExe) {
    if (-not (Test-Path (Join-Path $PYTHON_DIR "python.exe"))) {
        Write-Host "  Python not found. Downloading Python embeddable..."
        New-Item -ItemType Directory -Force -Path $PYTHON_DIR | Out-Null
        $zip = Join-Path $PYTHON_DIR "python-embed.zip"
        $url = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
        Invoke-WebRequest -Uri $url -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath $PYTHON_DIR -Force
        Remove-Item $zip -Force

        Get-ChildItem -Path $PYTHON_DIR -Filter "python*._pth" | ForEach-Object {
            $content = Get-Content $_.FullName
            $content = $content -replace '#import site', 'import site'
            Set-Content -Path $_.FullName -Value $content
        }

        Write-Host "  Installing pip for the embeddable Python..."
        & (Join-Path $PYTHON_DIR "python.exe") -m ensurepip --upgrade
    } else {
        Write-Host "  Using embeddable Python at $PYTHON_DIR"
    }
    $PythonExe  = Join-Path $PYTHON_DIR "python.exe"
    $PythonArgs = @()
}

if (-not (Test-Path (Join-Path $PSScriptRoot "pyproject.toml"))) {
    Write-Host ""
    Write-Host "ERROR: pyproject.toml was not found in the project folder."
    exit 1
}

# ================= 1. VIRTUAL ENVIRONMENT =================
$VenvMode = "venv"
if ($NoVenv) {
    Write-Step "[1/3] Skipping venv (-NoVenv), installing packages into vendor/."
    $VenvMode = "vendor"
} else {
    Write-Step "[1/3] Creating virtual environment..."
    & $PythonExe @PythonArgs -m venv $VENV_DIR
    $VENV_PY = Join-Path $VENV_DIR "Scripts\python.exe"
    if (Test-Path $VENV_PY) {
        Write-Host "  Virtual environment ready: $VENV_DIR"
    } else {
        Write-Host "  Could not create venv -> Falling back to installing packages into the project's vendor/ folder."
        $VenvMode = "vendor"
    }
}

if ($VenvMode -eq "venv") {
    $PythonExe  = Join-Path $VENV_DIR "Scripts\python.exe"
    $PythonArgs = @()
    $NodriverDir = Join-Path $VENV_DIR "Lib\site-packages\nodriver"
} else {
    New-Item -ItemType Directory -Force -Path $VENDOR_DIR | Out-Null
    $NodriverDir = Join-Path $VENDOR_DIR "nodriver"
}

# ================= 2. INSTALL DEPENDENCIES =================
Write-Step "[2/3] Installing dependencies..."
& $PythonExe @PythonArgs -m pip install --upgrade pip
if ($VenvMode -eq "vendor") {
    & $PythonExe @PythonArgs -m pip install --target $VENDOR_DIR .
} else {
    & $PythonExe @PythonArgs -m pip install -e .
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ---- Fix nodriver's UTF-8 bug (cdp/network.py contains latin-1 bytes) ----
if (Test-Path $FixScript) {
    Write-Host "  Patching nodriver UTF-8 encoding..."
    & $PythonExe @PythonArgs $FixScript $NodriverDir
} else {
    Write-Host "  Warning: $FixScript not found, skipping nodriver patch."
}

# ================= 3. PLAYWRIGHT BROWSERS =================
if ($SkipBrowsers) {
    Write-Step "[3/3] Skipping Chromium download (-SkipBrowsers)."
} else {
    Write-Step "[3/3] Downloading Chromium for Playwright (this may take a few minutes)..."
    $env:PLAYWRIGHT_BROWSERS_PATH = $BROWSERS_DIR
    if ($VenvMode -eq "vendor") { $env:PYTHONPATH = $VENDOR_DIR }
    & $PythonExe @PythonArgs -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# ================= DONE =================
Write-Host ""
Write-Host "============================================================"
Write-Host "  Done! Run the app with start.bat or:"
if ($VenvMode -eq "venv") {
    Write-Host "    $VENV_DIR\Scripts\python.exe run.py"
} else {
    Write-Host "    `$env:PYTHONPATH='$VENDOR_DIR'; $PythonExe run.py"
}
Write-Host "============================================================"
