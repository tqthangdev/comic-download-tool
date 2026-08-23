@echo off
rem ============================================================
rem  Click-to-run for Windows:
rem    - detect env (.venv or vendor\)
rem    - if nothing installed, run install.py
rem    - then launch run.py
rem ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PY="

set "PYTHONPATH="

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
)

if not defined PY if exist "vendor" (
    set "PY=python"
    set "PYTHONPATH=%CD%\vendor"
)

if not defined PY (
    if not exist "requirements.txt" (
        echo Kho^ng tim thay requirements.txt trong thu muc project.
        echo Hay chay: python install.py
        pause
        exit /b 1
    )
    echo Chua cai dependencies. Dang cai dat (co the mat vai phut)...
    python install.py
    if errorlevel 1 (
        echo Cai dat that bai. Hay chay thu cong: python install.py
        pause
        exit /b 1
    )
    if exist ".venv\Scripts\python.exe" (
        set "PY=.venv\Scripts\python.exe"
    ) else (
        set "PY=python"
        set "PYTHONPATH=%CD%\vendor"
    )
)

"%PY%" run.py
if errorlevel 1 pause
endlocal