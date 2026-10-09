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
pip install -e .
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
| `download_genres` | Save genres to a `genres.txt` file when downloading |
| `language` | UI language (`vi` or `en`) |
| `user_agent` | Custom HTTP User-Agent |
| `engine_default` | Download engine: `native` (default) or `gallerydl` |
| `engine_fallback` | Retry a job once on the other engine when one fails |
| `engine_overrides` | Per-domain engine, e.g. `{"example.com": "gallerydl"}` |
| `gallerydl` | gallery-dl settings (`executable`, `extra_args`, `sleep_request`, `retries`, `timeout`) |

## Download engines

Two engines can fetch a story. Pick one with the **Engine** dropdown (Auto / Native / gallery-dl); Auto follows `engine_default` and falls back to the other engine when a site is not supported.

| Engine | How it works | Sites |
| :--- | :--- | :--- |
| **native** (default) | Heuristic scraper + built-in aiohttp downloader (no per-site selectors), plus API special cases for cuutruyen.net and nhentai.net. | The Vietnamese comic sites this project was built for. |
| **gallery-dl** | Runs [gallery-dl](https://github.com/mikf/gallery-dl) as a separate process (optional extra). | The ~4900 extractors gallery-dl ships. |

Engine matrix (measured with `tools/engine_compare.py`):

| Site | native | gallery-dl |
| :--- | :---: | :---: |
| sayhentai.cx | ✅ | ❌ no extractor |
| nettruyen.gg | ✅ | ❌ no extractor |
| hentaivn / hentaivnreal.com | ✅ | ❌ no extractor |
| cmangax18 | ✅ | ❌ no extractor |
| cuutruyen.net (DRM) | ✅ | ❌ no extractor |
| nhentai.net | ✅ | ✅ |
| mangadex.org | — | ✅ |

> gallery-dl is a **secondary** engine: it does not cover the Vietnamese sites the native engine handles, so `engine_default` stays `native`. Its value is sites native cannot read, the automatic fallback, and per-domain `engine_overrides`.
>
> gallery-dl is licensed **GPL-2.0**. It is only ever executed (never imported in-process); a release build bundles it via the `gallerydl` optional extra.

## Build

Build a standalone onedir bundle (`dist/ComicDownloadTool/`) with the cross-platform build script:

```bash
python build.py
```

Run it with any Python 3.10+ interpreter — it creates or reuses the project `.venv`, installs the dependencies declared in `pyproject.toml`, downloads Playwright Chromium, and packages the app with PyInstaller.

| Option | Description |
| :--- | :--- |
| `--skip-browsers` | Reuse the Chromium already downloaded |
| `--name <name>` | Custom executable name (default `ComicDownloadTool`) |
| `--no-venv` | Build with the current interpreter instead of the project venv |

The whole `dist/ComicDownloadTool/` folder is the distributable unit — the executable plus `_internal/` (assets, `version.json`, Playwright driver and Chromium).

## Disclaimer

This project is intended for educational and personal use. Respect target websites' terms of service, copyright laws, and rate limits. The author is not responsible for software misuse.
