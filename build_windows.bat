@echo off
REM ============================================================
REM  Build Windows standalone app with PyInstaller
REM  Run this .bat from the project folder.
REM ============================================================

setlocal EnableExtensions

cd /d "%~dp0"

echo.
echo ============================================================
echo   ComicDownloadTool - Windows Build
echo ============================================================
echo.

REM ------------------------------------------------------------
REM 1. Check Python (download a portable one if missing)
REM ------------------------------------------------------------
echo [1/4] Checking Python...

set "PY_BUILDER="
where python >nul 2>&1
if not errorlevel 1 set "PY_BUILDER=python"

if not defined PY_BUILDER (
    where py >nul 2>&1
    if not errorlevel 1 set "PY_BUILDER=py"
)

if not defined PY_BUILDER (
    if exist "python\python.exe" (
        echo [*] No system Python, using project-local python\python.exe
        set "PY_BUILDER=python\python.exe"
    )
)

if not defined PY_BUILDER (
    echo [*] Python not found. Downloading portable Python via wget...
    echo     (requires Windows 10+ wget, else curl is used)
    if not exist "python" mkdir python

    where wget >nul 2>&1
    if not errorlevel 1 (
        wget -O python\python-embed.zip https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip
    ) else (
        where curl >nul 2>&1
        if not errorlevel 1 (
            curl -L -o python\python-embed.zip https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip
        ) else (
            echo [X] Neither wget nor curl found. Cannot download Python.
            goto :fail
        )
    )
    if errorlevel 1 (
        echo [X] Failed to download Python.
        goto :fail
    )

    echo [*] Extracting...
    powershell -NoProfile -Command "Expand-Archive -Force 'python\python-embed.zip' 'python'"
    if errorlevel 1 goto :fail
    del python\python-embed.zip

    if not exist "python\python.exe" (
        echo [X] Python extraction failed.
        goto :fail
    )

    echo [*] Enabling 'import site' for embedded Python...
    for %%f in (python\python*._pth) do (
        powershell -NoProfile -Command "(Get-Content '%%f') -replace '#import site','import site' | Set-Content '%%f'"
    )

    echo [*] Bootstrapping pip...
    python\python.exe -m ensurepip --upgrade
    if errorlevel 1 goto :fail

    echo [*] Using project-local python\python.exe
    set "PY_BUILDER=python\python.exe"
)

set "PY_BASE=%PY_BUILDER%"
%PY_BASE% --version
if errorlevel 1 goto :fail

REM ------------------------------------------------------------
REM 2. Create virtual environment
REM ------------------------------------------------------------
echo.
echo [2/4] Checking virtual environment...

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...

    %PY_BASE% -m venv .venv
    if errorlevel 1 (
        echo [!] Failed to create virtual environment.
        goto :fallback
    )
) else (
    echo [*] Virtual environment already exists.
)

set "PYTHON=.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [!] Virtual environment is invalid.
    goto :fallback
)

echo [*] Python:
"%PYTHON%" --version

REM ------------------------------------------------------------
REM 3. Install dependencies
REM ------------------------------------------------------------
echo.
echo [3/4] Installing dependencies...

"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] Failed to install requirements.txt
    goto :fail
)

"%PYTHON%" -m pip install PyInstaller
if errorlevel 1 (
    echo [X] Failed to install PyInstaller
    goto :fail
)

REM ------------------------------------------------------------
REM 4. Build
REM ------------------------------------------------------------
echo.
echo [4/4] Building executable...

"%PYTHON%" -m PyInstaller run.spec --noconfirm
if errorlevel 1 (
    echo [X] PyInstaller build failed.
    goto :fail
)

echo.
echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo.
echo Output:
echo   %cd%\dist\ComicDownloadTool\
echo.
echo Copy the WHOLE ComicDownloadTool folder when distributing.
echo.

goto :end


REM ============================================================
REM Fallback: install dependencies into vendor
REM ============================================================
:fallback

echo.
echo ============================================================
echo   FALLBACK BUILD
echo ============================================================
echo.

echo [!] Virtual environment could not be used.
echo [*] Trying vendor\ installation instead...

if not exist "vendor" (
    mkdir vendor
)

%PY_BASE% -m pip install --target vendor -r requirements.txt
if errorlevel 1 (
    echo [X] Failed to install requirements into vendor\
    goto :fail
)

%PY_BASE% -m pip install --target vendor PyInstaller
if errorlevel 1 (
    echo [X] Failed to install PyInstaller into vendor\
    goto :fail
)

set "PYTHONPATH=%cd%\vendor"

echo [*] Building with vendor\ dependencies...

%PY_BASE% -m PyInstaller run.spec --noconfirm
if errorlevel 1 (
    echo [X] PyInstaller build failed.
    goto :fail
)

echo.
echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo.
echo Output:
echo   %cd%\dist\ComicDownloadTool\
echo.

goto :end


REM ============================================================
REM Failure
REM ============================================================
:fail

echo.
echo ============================================================
echo   BUILD FAILED
echo ============================================================
echo.
echo Check the error messages above.
echo.

exit /b 1


:end

endlocal
exit /b 0