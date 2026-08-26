# Comic Download Tool

**Comic Download Tool** is a Python-based comic crawling and downloading engine built around a heuristic scraper.

The project separates crawling, extraction, downloading, job management, and GUI components so that new comic websites can be integrated without modifying the core engine.

## Download

Prebuilt standalone builds are published as **GitHub Releases** — no Python or package installation required on the target machine.

### Get the latest build

1. Go to the [Releases](https://github.com/tqthangdev/comic-download-tool/releases) page.
2. Pick the newest release (tagged `v*`).
3. Download the executable file for your OS:
   * **`ComicDownloadTool.exe`** — Windows
   * **`ComicDownloadTool.AppImage`** — Linux
4. Run the application:
   * **Windows:** Double-click `ComicDownloadTool.exe`
   * **Linux:** Make it executable (`chmod +x ComicDownloadTool.AppImage`) and run `./ComicDownloadTool.AppImage`

> **No dependencies needed:** Each build bundles the app, Playwright's driver, and Chromium. It is fully self-contained.

### Building from source

If no release is available, you can build it yourself — see [Build](#build), or grab the build artifacts from the latest GitHub Actions workflow run.

## Features

* Heuristic scraper (no per-site configuration)
* Automatic comic/chapter crawling
* Concurrent downloading with retry mechanisms
* SQLite-based job queue and persistence
* Cross-platform desktop GUI
* Centralized logging
* Configurable worker and download limits

## Architecture

```text
Comic Download Tool
│
├── core/
│   ├── crawler.py          # Crawling logic
│   ├── downloader.py       # Image/file downloading
│   ├── engine.py           # Main engine orchestration
│   ├── job_manager.py      # Job queue and persistence
│   ├── logger.py           # Logging
│   ├── scraper.py          # Metadata + chapter-list + image heuristics
│   └── utils.py            # Shared utilities
│
├── gui/
│   ├── main_window.py      # Main application window
│   ├── queue_delegate.py   # Queue UI delegate
│   ├── ui_left.py          # Left-side UI
│   └── ui_right.py         # Right-side UI
│
├── assets/                 # Icons and UI images
├── data/jobs.db            # SQLite job database
├── logs/error.log          # Application error log
├── config.json             # Application configuration
├── requirements.txt        # Python dependencies
├── run.py                  # Application entry point
├── build.sh / build.ps1    # Build scripts (Linux/macOS / Windows)
├── setup.sh / setup.ps1    # Setup scripts (Linux/macOS / Windows)
└── start.sh / start.bat    # Launchers (Linux/macOS / Windows)
```

## Installation

**Prerequisites:** Python 3.10+ and Internet connection (for initial setup/Chromium download).

Use the built-in setup script to automatically create a virtual environment (`.venv`), install dependencies, and setup Playwright Chromium:

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

*Note for Windows: If Python is missing, `setup.ps1` automatically downloads a portable Python environment into `python/`.*

### Manual Installation

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Running

### Launcher (Recommended)

Double-click the launcher script for your OS. It auto-checks the environment and launches the app:

* **Windows:** Double-click `start.bat`
* **Linux / macOS:** Run `./start.sh`

### Manual Run

```bash
# Linux / macOS
.venv/bin/python run.py

# Windows
.venv\Scripts\python.exe run.py

# If installed with --no-venv
PYTHONPATH=vendor python run.py
```

## Configuration

Settings are stored in `config.json`.

```json
{
    "max_workers": 10,
    "max_concurrent_downloads": 10,
    "download_retry": 3,
    "chapter_retry": 2,
    "request_timeout": 30,
    "download_thumb": true,
    "language": "vi",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}
```

| Option | Description |
| :--- | :--- |
| `max_workers` | Maximum number of crawler workers |
| `max_concurrent_downloads` | Maximum simultaneous image downloads |
| `download_retry` / `chapter_retry` | Retries count for failed downloads/chapters |
| `request_timeout` | HTTP timeout in seconds |
| `download_thumb` | Save thumbnail when downloading |
| `language` | UI language (`vi` or `en`) |
| `user_agent` | Custom HTTP User-Agent |

## Build

### Linux / macOS

```bash
chmod +x build.sh
./build.sh
```

### Windows

```powershell
.\build.ps1
```
*(If execution is blocked: `Set-ExecutionPolicy -Scope Process Bypass` first)*

### Script Execution Flow

The build script automatically sets up the environment, installs Playwright Chromium, builds a PyInstaller `onedir` package in `dist/ComicDownloadTool/`, and cleans up temp files.

## Extraction System

Comic Download Tool uses a fully heuristic scraper (`core/scraper.py`):

- **Manga page (`scrape()`)**: Uses leaf-text grouping and regex heuristics to extract title, thumbnail, referer, and chapter list.
- **Chapter page (`find_chapter_images()`)**: Filters out UI junk (logos, ads) and extracts content image URLs.

```text
Website ──> core/scraper.py (heuristics) ──> Crawler ──> Job Manager ──> Downloader ──> Disk
```

### Tuning Heuristics

No site-specific configs are needed. To support sites with unusual markup, update generic rules in `core/scraper.py`:
* `find_chapters()` — chapter-list detection heuristics.
* `find_chapter_images()` — chapter image URL patterns.

## Database & Logs

* **SQLite DB:** `data/jobs.db` stores queued/processed jobs across restarts.
* **Logs:** `logs/error.log` contains detailed debug info for failed downloads or scraper errors.

## Development Workflow

```text
Test Scraper ──> Test Crawler ──> Test Downloader ──> Test Persistence ──> Test GUI ──> Build Executable
```

## Disclaimer

This project is intended for educational and personal use. Respect target websites' terms of service, copyright laws, and rate limits. The author is not responsible for software misuse.

## License

This project is licensed under the [MIT License](LICENSE).
