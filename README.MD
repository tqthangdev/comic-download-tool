# Comic Download Tool

**Comic Download Tool** is a Python-based comic crawling and downloading engine built around a heuristic scraper.

The project separates crawling, extraction, downloading, job management, and GUI components so that new comic websites can be integrated without modifying the core engine.

## Download

Prebuilt standalone builds are published as **GitHub Releases** — no Python or package installation required on the target machine.

### Get the latest build

1. Go to the [Releases](https://github.com/tqthangdev/comic-download-tool/releases) page.
2. Pick the newest release (tagged `v*`).
3. Download the build for your OS:
   * **`ComicDownloadTool-linux.zip`** — Linux
   * **`ComicDownloadTool-windows.zip`** — Windows
4. Extract the ZIP archive.
5. Run the application:
   * **Windows:** Run `ComicDownloadTool.exe`
   * **Linux:** Run `./ComicDownloadTool`

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
* Login support for sites that require authentication (config-driven)

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
│   ├── utils.py            # Shared utilities
│   └── auth/               # Login support (config-driven)
│       ├── base.py             # AuthHandler interface + AuthError/AuthResult
│       ├── manager.py          # AuthManager (register/login/session cache)
│       ├── config_sites.py     # ConfigSiteAuth driven by sites_config.json
│       ├── session_store.py    # Persist/restore session cookies
│       └── sites_config.json   # Declare login-required sites
│
├── gui/
│   ├── main_window.py      # Main application window
│   ├── login_dialog.py     # Login dialog for authenticated sites
│   ├── queue_delegate.py   # Queue UI delegate
│   ├── ui_left.py          # Left-side UI
│   └── ui_right.py         # Right-side UI
│
├── assets/                 # Icons and UI images
├── data/                   # App data next to the app (config.json, jobs.db, sessions/)
├── logs/error.log          # Application error log
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

Settings are stored in `config.json`, created automatically inside `data/` right next to the app (both when running from source and in a built release).

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

## Login / Authentication

Some sites require a login to read or download content (locked/premium chapters). The app detects this via the URL's domain, prompts for credentials, and uses the authenticated session for crawling and image downloads.

### Declaring a login-required site

Sites are declared in `core/auth/sites_config.json`. Each key is a `site_id`, and `AuthManager` auto-registers all entries on startup:

```json
{
  "damconuong": {
    "type": "form",
    "domains": ["damconuong.uno"],
    "login_url": "https://damconuong.uno/login",
    "check_url": "https://damconuong.uno/my/profile",
    "username_field": "email",
    "password_field": "password",
    "csrf": true,
    "verify_ssl": false
  }
}
```

| Field | Description |
| :--- | :--- |
| `type` | Login flow: `form` (URL-encoded POST), `json` (JSON POST, token from response), or `basic` (HTTP Basic). Default `form`. |
| `domains` | Domain(s) used to auto-detect which site a pasted URL belongs to. |
| `login_url` | Endpoint that receives the credentials. |
| `check_url` | URL whose response status tells whether the session is still logged in (default expects `200`). |
| `username_field` / `password_field` | Names of the credential form/JSON fields. |
| `extra_form` | Optional extra fields sent with the login request; `{username}` is replaced with the typed username. |
| `csrf` | When `true`, the login page is fetched first and a CSRF token (`_token`/`_csrf`/...) is submitted alongside the credentials. |
| `verify_ssl` | Set `false` for sites with a self-signed/untrusted certificate. |

### How it works

1. When a URL is pasted, the app looks up the URL's host against every registered site's `domains`.
2. If the site needs login and no valid session exists, a login dialog (`gui/login_dialog.py`) asks for the account credentials.
3. On success, the authenticated session's cookies/headers are reused for chapter crawling and image downloads (requests, aiohttp, and Playwright).
4. Sessions are persisted to `data/sessions/<site_id>.json`, so you don't have to log in again on the next launch. If a session expires mid-download, the affected job is paused and the login dialog is re-shown.

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

## Data Storage

The app stores its data next to where it is run, so running a build from any folder keeps its settings, jobs, and logs self-contained in that folder:

* **`data/config.json`** — application configuration (auto-created).
* **`data/jobs.db`** — SQLite database storing queued/processed jobs across restarts.
* **`data/sessions/`** — saved authenticated sessions (one JSON file per site) so logins persist across runs.
* **`logs/error.log`** — detailed info for failed downloads or scraper errors.

## Development Workflow

```text
Test Scraper ──> Test Crawler ──> Test Downloader ──> Test Persistence ──> Test GUI ──> Build Executable
```

## Disclaimer

This project is intended for educational and personal use. Respect target websites' terms of service, copyright laws, and rate limits. The author is not responsible for software misuse.

## License

This project is licensed under the [MIT License](LICENSE).
