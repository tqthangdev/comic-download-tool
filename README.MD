# Comic Download Tool

**Comic Download Tool** is a Python-based comic crawling and downloading desktop app built around a fully heuristic scraper — no per-site configuration needed. It handles chapter-list extraction, concurrent image downloads with retries, a SQLite-backed job queue, and a cross-platform PyQt6 GUI.

Prebuilt standalone builds (Windows / Linux) are published on [GitHub Releases](https://github.com/tqthangdev/comic-download-tool/releases) — no Python installation required.

## Installation

**Prerequisites:** Python 3.10+ and an Internet connection (for the initial Chromium download).

Use the built-in setup script to create a virtual environment (`.venv`), install dependencies, and set up Playwright Chromium:

**Linux / macOS:**

```bash
./setup.sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

### Setup Options

| Option | Windows equivalent | Description |
| :--- | :--- | :--- |
| `--skip-browsers` | `-SkipBrowsers` | Skip downloading Chromium (packages only) |
| `--no-venv` | `-NoVenv` | Install packages into `vendor/`, skip the venv |

### Manual Installation

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Running

* **Windows:** Double-click `start.bat`
* **Linux / macOS:** Run `./start.sh`

Or run directly from the virtual environment:

```bash
# Linux / macOS
.venv/bin/python run.py

# Windows
.venv\Scripts\python.exe run.py
```

## Configuration

Settings are stored in `data/config.json`, created automatically next to the app (both when running from source and in a built release):

| Option | Description |
| :--- | :--- |
| `max_workers` | Maximum number of crawler workers |
| `max_concurrent_downloads` | Maximum simultaneous image downloads |
| `download_retry` / `chapter_retry` | Retries for failed downloads/chapters |
| `request_timeout` | HTTP timeout in seconds |
| `download_thumb` | Save thumbnail when downloading |
| `language` | UI language (`vi` or `en`) |
| `user_agent` | Custom HTTP User-Agent |

## Build

**Linux / macOS:**

```bash
chmod +x build.sh
./build.sh
```

**Windows:**

```powershell
.\build.ps1
```
*(If execution is blocked: `Set-ExecutionPolicy -Scope Process Bypass` first)*

The build script sets up the environment, installs Playwright Chromium, packages the app with PyInstaller into `dist/ComicDownloadTool/`, and cleans up temp files.

## Disclaimer

This project is intended for educational and personal use. Respect target websites' terms of service, copyright laws, and rate limits. The author is not responsible for software misuse.
