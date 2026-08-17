# Comic Download Tool

**Comic Download Tool** is a Python-based comic crawling and downloading engine designed with a modular extractor architecture.

The project separates crawling, extraction, downloading, job management, and GUI components so that new comic websites can be integrated without modifying the core engine.

## Features

* Modular website extractor architecture
* Automatic comic/chapter crawling
* Concurrent downloading
* Download retry mechanism
* Chapter retry mechanism
* Job queue and job management
* SQLite-based job persistence
* GUI interface
* Centralized logging
* Configurable worker and download limits
* Extensible extractor registry
* Support for multiple comic sources

## Architecture

```text
Comic Download Tool
│
├── core/
│   ├── base_extractor.py   # Base extractor definitions
│   ├── crawler.py          # Crawling logic
│   ├── downloader.py       # Image/file downloading
│   ├── engine.py           # Main engine orchestration
│   ├── job_manager.py      # Job queue and persistence
│   ├── logger.py           # Logging
│   └── utils.py            # Shared utilities
│
├── extractors/
│   ├── base.py             # Extractor interface/base class
│   ├── registry.py         # Extractor registration
│   ├── hentaivnreal.py     # HentaiVNReal extractor
│   ├── hentaivnx.py        # HentaiVNX extractor
│   └── __init__.py
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
├── install.py              # Auto installer (venv + deps + Chromium)
├── requirements.txt        # Python dependencies
├── run.py                  # Application entry point
└── run.spec               # PyInstaller build specification
```

## Requirements

* Python 3.10+
* Windows / Linux
* Internet connection (required on first run to fetch dependencies and Chromium)

## Installation

The easiest way is to use the built-in auto installer. It creates a virtual
environment (with a fallback if your system does not support `venv`), installs
the dependencies from `requirements.txt`, and downloads Chromium for Playwright:

```bash
python install.py
```

Options:

| Option                  | Description                                          |
| ----------------------- | ---------------------------------------------------- |
| `--skip-browsers`       | Skip downloading Chromium (packages only)            |
| `--no-venv`             | Install directly into the current environment        |

Or install manually:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

> The project now ships `requirements.txt` (without pinned versions), so there
> is no need to generate one with `pip freeze`.

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

Run the application from the project root:

```bash
python run.py
```

On Windows:

```powershell
python .\run.py
```

If Playwright browsers are missing, install them with:

```bash
python run.py --install-browsers
```

## Extractor System

Comic Download Tool uses a modular extractor system.

Each supported website has its own extractor implementation:

```text
extractors/
├── base.py
├── registry.py
├── hentaivnreal.py
└── hentaivnx.py
```

The extractor is responsible for understanding the structure of a specific website, while the core engine handles the generic crawling and downloading workflow.

Conceptually:

```text
Website
   │
   ▼
Extractor
   │
   ├── Comic metadata
   ├── Chapter information
   └── Image URLs
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

This separation makes it possible to add support for another website without rewriting the downloader or job-management system.

## Adding a New Extractor

Create a new extractor under:

```text
extractors/
```

For example:

```text
extractors/example.py
```

The extractor should follow the interface defined by:

```text
extractors/base.py
```

Then register it through:

```text
extractors/registry.py
```

The exact implementation depends on the website being supported.

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
* Extractor errors
* Download failures
* Invalid image URLs
* Timeout errors
* Unexpected website changes

## Building a Standalone Executable

The project contains a PyInstaller specification:

```text
run.spec
```

Build the executable with:

```bash
pyinstaller run.spec
```

The generated build artifacts should not be committed to Git.

## Development

Recommended project workflow:

```text
1. Add/update extractor
        ↓
2. Test extraction
        ↓
3. Test chapter crawling
        ↓
4. Test image downloading
        ↓
5. Test job persistence
        ↓
6. Test GUI integration
        ↓
7. Build standalone executable
```

Keep website-specific logic inside `extractors/` whenever possible.

The `core/` package should remain independent from individual websites.

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

### Extractors

Contains website-specific implementations.

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
