# Comic Download Tool

**Comic Download Tool** is a Python-based comic crawling and downloading engine built around a heuristic scraper.

The project separates crawling, extraction, downloading, job management, and GUI components so that new comic websites can be integrated without modifying the core engine.

## Features

* Heuristic scraper (no per-site configuration)
* Automatic comic/chapter crawling
* Concurrent downloading
* Download retry mechanism
* Chapter retry mechanism
* Job queue and job management
* SQLite-based job persistence
* GUI interface
* Centralized logging
* Configurable worker and download limits
* Support for multiple comic sources

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
├── assets/
│   └── loading.gif
│
├── data/
│   └── jobs.db             # SQLite job database
│
├── logs/
│   └── error.log           # Application error log
│
├── config.json             # Application configuration
├── requirements.txt        # Python dependencies
├── run.py                  # Application entry point
├── run.spec               # PyInstaller build specification
├── setup.sh                # Auto installer (Linux / macOS)
├── setup.ps1               # Auto installer (Windows)
├── start.sh                # Click-to-run launcher (Linux / macOS)
└── start.bat               # Click-to-run launcher (Windows)
```

## Requirements

* Python 3.10+
* Windows / Linux
* Internet connection (required on first run to fetch dependencies and Chromium)

## Installation

The easiest way is to use the built-in setup script. It creates a virtual
environment (with a fallback that installs packages into the project's `vendor/`
folder if your system does not support `venv`), installs the dependencies from
`requirements.txt`, and downloads Chromium for Playwright into the project's
`ms-playwright/` folder — everything stays inside the project directory.

**Linux / macOS:**

```bash
./setup.sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

Options (both scripts share the same behaviour):

| Option                | Windows equivalent | Description                                              |
| --------------------- | ------------------ | -------------------------------------------------------- |
| `--skip-browsers`     | `-SkipBrowsers`    | Skip downloading Chromium (packages only)                |
| `--no-venv`           | `-NoVenv`          | Install packages into `vendor/`, skip the venv           |

On Windows, if Python is not installed, `setup.ps1` automatically downloads a
portable, embeddable Python into the project's `python/` folder and uses that.

Or install manually:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

> The project ships `requirements.txt` (without pinned versions), so there is
> no need to generate one with `pip freeze`.

## Configuration

Application settings are stored in `config.json`.

Example:

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

### Configuration options

| Option                     | Description                              |
| -------------------------- | ---------------------------------------- |
| `max_workers`              | Maximum number of crawler/engine workers |
| `max_concurrent_downloads` | Maximum number of simultaneous downloads |
| `download_retry`           | Number of retries for failed downloads   |
| `chapter_retry`            | Number of retries for failed chapters    |
| `request_timeout`          | HTTP request timeout in seconds          |
| `download_thumb`           | Whether to save thumbnail when downloading |
| `language`                 | UI language (`vi` or `en`)               |
| `user_agent`               | HTTP User-Agent used for requests        |

Adjust concurrency carefully. A higher value does not always mean faster downloads and may cause unnecessary load on the target website.

## Running

### Easiest way: launcher

Double-click the launcher for your operating system. It checks the environment
(`.venv` or `vendor/`), installs anything missing, and then starts the app:

* **Windows** — double-click `start.bat`
* **Linux / macOS** — run `start.sh`

> Linux note: most desktops (XFCE/Thunar, GNOME Files, …) open `.sh` files in a
> text editor by default instead of running them. If double-clicking does not
> work, open a terminal in the project folder and run:
>
> ```bash
> ./start.sh
> ```
>
> or right-click `start.sh` in the file manager and choose **Run**.

### Run manually

From the project root, after installing with `setup.sh` / `setup.ps1`:

On Linux / macOS:

```bash
.venv/bin/python run.py
```

On Windows:

```powershell
.venv\Scripts\python.exe run.py
```

Or, if you installed with `--no-venv` (packages live in `vendor/`):

```bash
PYTHONPATH=vendor python run.py
```

## Extraction System

Comic Download Tool uses a fully heuristic scraper (`core/scraper.py`) —
no per-site configuration is needed:

- **Manga page** (`scrape()`): fetches the page and uses BeautifulSoup
  heuristics (leaf-text grouping, regex chapter/date detection, base-path
  filtering) to extract title, thumbnail, referer, and the chapter list
  (`title` / `url` / `update_time`).
- **Chapter page** (`find_chapter_images()`): scans all `<img>` elements,
  filters out junk (logos, icons, ads, avatars — by class and URL patterns),
  and keeps the content images (CDN path patterns like `/manga-images/`,
  `/images/data/`).

Conceptually:

```text
Website
   │
   ▼
core/scraper.py  (heuristics)
   │
   ├── Manga page   → title, thumb, referer, chapter list
   ├── Chapter page → image URLs
   │
   ▼
Crawler
   │
   ▼
Job Manager
   │
   ▼
Downloader
   │
   ▼
Local Storage
```

Chapter lists are persisted in the job database (as JSON), so queued or
resumed jobs do not need to re-crawl the manga page.

## Adding a New Website

No configuration is required. If a new site uses unusual markup, tune the
heuristics in `core/scraper.py`:

- `find_chapters()` — chapter-list detection (leaf grouping + base-path filter)
- `find_chapter_images()` — chapter-page image detection (junk filtering +
  content URL patterns)

The heuristics are shared across all sites; per-site special cases should be
added as generic patterns, not hardcoded selectors.

## Job Database

Jobs are persisted using SQLite.

The database is located at:

```text
data/jobs.db
```

This allows queued or previously processed jobs to survive application restarts.

Temporary SQLite files such as:

```text
jobs.db-journal
```

should not be committed to Git.

## Logging

Application errors are written to:

```text
logs/error.log
```

Logs are useful when diagnosing:

* Network failures
* Scraper heuristics failing to find chapters/images
* Download failures
* Invalid image URLs
* Timeout errors
* Unexpected website changes

## Building a Standalone Executable

The project contains a PyInstaller specification:

```text
run.spec
```

PyInstaller is **not cross-platform**: you must build on the same OS that
will run the executable.

> **Note:** the built package includes Playwright's **driver** but not the
> browser. Chromium must be bundled into the output folder (see below) so the
> app can run on machines that do not have Playwright installed globally.

**Linux / macOS** — after running `./setup.sh`, build from the project root:

```bash
.venv/bin/python -m PyInstaller run.spec --noconfirm
```

Then bundle Chromium into the output folder so the app is self-contained:

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/dist/ComicDownloadTool/ms-playwright" \
    .venv/bin/python -m playwright install chromium
```

Output: `dist/ComicDownloadTool/`.

**Windows** — after running `setup.ps1`, build from the project root (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m PyInstaller run.spec --noconfirm
```

Then bundle Chromium into the output folder:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH="$PWD\dist\ComicDownloadTool\ms-playwright"
.\.venv\Scripts\python.exe -m playwright install chromium
```

Output: `dist\ComicDownloadTool\`.

Alternatively, the **GitHub Actions workflow (`.github/workflows/build.yml`)**
does all of this automatically: it builds on both Linux and Windows, bundles
Chromium into each output folder, uploads the artifacts, and — when a `v*`
tag is pushed — creates a GitHub Release containing the `.tar.gz` (Linux) and
`.zip` (Windows) archives.

When distributing, copy the **entire** output folder (`ComicDownloadTool/`),
not just the executable. On first run the app looks for a portable
`ms-playwright/` folder next to the executable, otherwise it falls back to the
system-default Chromium location.

The generated build artifacts should not be committed to Git.

## Development

Recommended project workflow:

```text
1. Test scraping a manga page (core/scraper.py)
        ↓
2. Test chapter crawling
        ↓
3. Test image downloading
        ↓
4. Test job persistence
        ↓
5. Test GUI integration
        ↓
6. Build standalone executable
```

The `core/` package remains independent from individual websites; all
scraping heuristics live in `core/scraper.py`.

## Project Structure

The project follows a layered architecture:

### Core

Contains the engine's generic functionality:

* Crawling
* Downloading
* Job management
* Logging
* Utilities
* Engine orchestration

### Scraper

Contains the heuristic extraction logic (`core/scraper.py`) shared by all
comic sources — no website-specific code lives here; patterns are generic.

### GUI

Contains the desktop interface and queue visualization.

### Data

Contains persistent runtime data such as the SQLite job database.

### Assets

Contains application resources used by the GUI.

## Git

Runtime files, local databases, IDE configuration, logs, Python caches, and build artifacts should not be committed.

See `.gitignore` for the complete list.

## Disclaimer

This project is intended for educational and personal use.

Only download and store content that you have the right to access and download. Respect the target websites' terms of service, robots policies where applicable, copyright laws, and applicable local regulations.

The project author is not responsible for misuse of the software.

## License

Add an appropriate license before publishing the project publicly.

For example:

```text
MIT License
```

or another license that matches the intended distribution terms.
