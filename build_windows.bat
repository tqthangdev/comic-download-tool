@echo off
REM ============================================================
REM  Build the Windows standalone app with PyInstaller
REM  Run this on a Windows machine from the project folder.
REM ============================================================
setlocal

cd /d "%~dp0"

echo [1/3] Creating virtual environment...
if not exist ".venv" (
    python -m venv .venv
    if errorlevel 1 goto :fallback
)

echo [2/3] Installing dependencies...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install PyInstaller -r requirements.txt
if errorlevel 1 goto :fail

echo [3/3] Building executable...
call .venv\Scripts\python.exe -m pyinstaller run.spec --noconfirm
if errorlevel 1 goto :fail

echo.
echo Build complete! Output folder:
echo   %cd%\dist\ComicDownloadTool\
echo Copy the WHOLE "ComicDownloadTool" folder when distributing.
goto :end

:fallback
echo [!] venv failed, trying --target install into vendor\ instead.
if not exist "vendor" mkdir "vendor"
python -m pip install --target vendor --upgrade pip 2>nul
python -m pip install --target vendor PyInstaller -r requirements.txt
if errorlevel 1 goto :fail
echo [*] Building with PYTHONPATH=vendor ...
set PYTHONPATH=vendor
python -m PyInstaller run.spec --noconfirm
if errorlevel 1 goto :fail
echo Build complete! See dist\ComicDownloadTool\
goto :end

:fail
echo.
echo [X] Build FAILED. See messages above.
exit /b 1

:end
endlocal