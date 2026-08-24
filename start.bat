@echo off
rem ============================================================
rem  Click-to-run for Windows:
rem    - detect env (.venv or vendor\)
rem    - if nothing installed, run install.py
rem    - then launch run.py
rem ============================================================
setlocal EnableExtensions EnableDelayedExpansion
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

    REM Neu may chua co python thi tai mot ban embeddable (portable) bang wget
    set "PY_RUN=python"
    echo Dang kiem tra Python...
    python --version >nul 2>&1
    if errorlevel 1 (
        if not exist "python\python.exe" (
            echo May chua co Python. Dang tai Python bang wget...
            if not exist "python" mkdir python

            where wget >nul 2>&1
            if not errorlevel 1 (
                wget -O python\python-embed.zip https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip
            ) else (
                where curl >nul 2>&1
                if not errorlevel 1 (
                    curl -L -o python\python-embed.zip https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip
                ) else (
                    echo Cai dat that bai: khong co wget/curl de tai Python.
                    pause
                    exit /b 1
                )
            )
            if errorlevel 1 (
                echo Tai Python that bai.
                pause
                exit /b 1
            )

            echo Giai nen Python...
            powershell -NoProfile -Command "Expand-Archive -Force 'python\python-embed.zip' 'python'"
            if errorlevel 1 (
                echo Giai nen Python that bai.
                pause
                exit /b 1
            )
            del python\python-embed.zip

            echo Bat 'import site' cho Python embeddable...
            for %%f in (python\python*._pth) do (
                powershell -NoProfile -Command "(Get-Content '%%f') -replace '#import site','import site' | Set-Content '%%f'"
            )

            echo Cai pip cho Python...
            python\python.exe -m ensurepip --upgrade
            if errorlevel 1 (
                echo Cai pip that bai.
                pause
                exit /b 1
            )
            set "PY_RUN=python\python.exe"
        )
        echo Da su dung Python de cai dat.
    )

    echo Chua cai dependencies. Dang cai dat (co the mat vai phut)...
    !PY_RUN! install.py
    if errorlevel 1 (
        echo Cai dat that bai. Hay chay thu cong: python install.py
        pause
        exit /b 1
    )
    if exist ".venv\Scripts\python.exe" (
        set "PY=.venv\Scripts\python.exe"
    ) else if exist "python\python.exe" (
        set "PY=python\python.exe"
    ) else (
        set "PY=python"
        set "PYTHONPATH=%CD%\vendor"
    )
)

"%PY%" run.py
if errorlevel 1 pause
endlocal