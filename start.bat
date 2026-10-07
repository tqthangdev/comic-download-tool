@echo off
rem ============================================================
rem  Click-to-run for Windows:
rem    - detect env (.venv or vendor\)
rem    - if nothing installed, run setup.ps1
rem    - patch nodriver UTF-8 bug (safe to run repeatedly)
rem    - then launch run.py
rem ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

set "PY="
set "PYTHONPATH="
set "ND_DIR="

call :detect
if defined PY goto :run

if not exist "pyproject.toml" (
    echo pyproject.toml not found in the project folder.
    echo Please run: powershell -ExecutionPolicy Bypass -File setup.ps1
    pause
    exit /b 1
)

echo Dependencies not installed. Installing (this may take a few minutes)...
powershell -ExecutionPolicy Bypass -File setup.ps1
if errorlevel 1 (
    echo Installation failed. Please run manually: powershell -ExecutionPolicy Bypass -File setup.ps1
    pause
    exit /b 1
)

call :detect
if not defined PY (
    echo Could not find an installed environment after setup.
    pause
    exit /b 1
)

:run
if defined ND_DIR if exist "lib\fix_nodriver.py" "%PY%" "lib\fix_nodriver.py" "%ND_DIR%"
"%PY%" run.py
if errorlevel 1 pause
endlocal
exit /b 0

:detect
if exist ".venv\Scripts\python.exe" goto :detect_venv
if exist "vendor" goto :detect_vendor
exit /b 0

:detect_venv
set "PY=.venv\Scripts\python.exe"
set "ND_DIR=.venv\Lib\site-packages\nodriver"
exit /b 0

:detect_vendor
set "PY=python"
if exist "python\python.exe" set "PY=python\python.exe"
set "PYTHONPATH=%CD%\vendor"
set "ND_DIR=vendor\nodriver"
exit /b 0