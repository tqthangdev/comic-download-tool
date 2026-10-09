# Architecture & Flows

How the app is put together and what happens on each user action.
See `README.MD` for installation/usage; this file is the internal map.

---

## 1. Directory structure

```
comic-download-tool/
├── run.py                  # Entry point: Qt + qasync bootstrap, wires Engine into MainWindow
├── start.sh / start.bat    # Click-to-run launchers (auto-install if needed, then run.py)
├── setup.sh / setup.ps1    # One-command installer: .venv (or vendor/), deps, Playwright Chromium
├── build.py                # Cross-platform PyInstaller build -> dist/ (generates run.spec)
├── pyproject.toml          # Dependencies / packaging metadata (single source of truth)
├── README.MD
├── flow.md                 # (this file)
│
├── core/                   # Non-GUI logic, grouped by role
│   ├── utils.py            # CONFIG, path helpers, safe_filename, link-file parsing
│   ├── i18n.py             # vi/en strings (tr())
│   ├── logger.py           # Logging -> logs/<date>.log
│   ├── net/                # Network layer
│   │   ├── crawler.py      #   Async wrapper around scraper + Playwright fallback
│   │   ├── downloader.py   #   Concurrent image downloader (aiohttp)
│   │   └── stealth.py      #   nodriver stealth fallback (Cloudflare clearance)
│   ├── scraping/           # Reading a story
│   │   ├── scraper.py      #   Heuristics: title/thumb/genres/chapters + chapter images
│   │   └── sites/          #   Per-site special cases (own JSON API)
│   │       ├── cuutruyen.py#     cuutruyen.net API + DRM (wasm) image rendering
│   │       └── nhentai.py  #     nhentai.net gallery API (one gallery = one chapter)
│   ├── engines/            # Download backends (native heuristic vs gallery-dl)
│   │   ├── base.py         #   DownloadBackend interface, StoryMeta, JobOutcome, BackendError
│   │   ├── native.py       #   Wraps crawler + aiohttp downloader (unchanged behaviour)
│   │   ├── gallerydl.py    #   gallery-dl subprocess backend + normalize_layout()
│   │   ├── gallerydl_conf.py #  gallery-dl config + cookies.txt generation
│   │   └── selector.py     #   Picks a backend (default / engine_overrides / fallback)
│   ├── jobs/               # Job orchestration
│   │   ├── engine.py       #   Worker pool, job orchestration, download loop
│   │   └── job_manager.py  #   SQLite persistence (jobs.db) + Job dataclass
│   ├── export/
│   │   └── pdf.py          #   Chapter -> PDF export
│   ├── updater/            # GitHub-release updater (check / download / verify / apply)
│   └── auth/               # Optional login support (config-driven)
│       ├── base.py         # AuthHandler interface, AuthResult, AuthError
│       ├── manager.py      # auth_manager: register/login/restore, site_id lookup
│       ├── config_sites.py # Builds handlers from sites_config.json
│       ├── session_store.py# Saves/loads cookies+headers to data/sessions/<site>.json
│       └── sites_config.json  # Per-site login config
│
├── gui/                    # PyQt6 UI
│   ├── main_window.py      # MainWindow: paste/load/add/start, restore, shutdown, messages
│   ├── panels/             #   Main-window panels
│   │   ├── ui_left.py      #     LeftPanel (URL, mode, engine, path, preview) + Config/Help/About
│   │   ├── ui_right.py     #     RightPanel (queue list, start/pause/resume/clear buttons)
│   │   └── queue_delegate.py #   Queue row painting (progress, engine tag, trash button)
│   ├── dialogs/            #   Modal dialogs
│   │   ├── add_jobs_dialog.py  # Progress modal while importing links from a file
│   │   ├── restore_dialog.py   # Progress modal while restoring the previous session
│   │   ├── login_dialog.py     # Login prompt (prompt_login)
│   │   └── version_dialog.py   # Version/update modal
│   ├── cursor_utils.py     # Pointer/forbidden cursors (QSS cannot set cursor)
│   └── theme.py            # ALL QSS lives here (_resolve_assets() makes urls absolute)
│
├── assets/                 # Icons and UI chrome
│   ├── app/                #   icon.png / icon.ico (window + executable icon)
│   ├── controls/           #   checkbox/radio/trash SVGs
│   └── spinners/           #   spin-*.svg, loading.gif
├── data/                   # Runtime state (created next to the app; db/json are gitignored)
│   ├── config.json         # User settings
│   ├── jobs.db             # SQLite queue/history
│   ├── gallerydl/          # gallery-dl backend temp/resume cache
│   └── sessions/<site>.json# Persisted login sessions
├── logs/<date>.log
├── ms-playwright/          # Portable Chromium when not installed at the default path
├── vendor/                 # Packages when installed with --no-venv
├── tools/                  # Dev scripts (engine_compare.py, fix_nodriver.py)
├── dist/                   # PyInstaller output
└── .github/workflows/build.yml
```

---

## 2. Runtime paths

| Path | Where it lives | Purpose |
| :--- | :--- | :--- |
| `BASE_DIR` | executable folder when frozen, project root in dev (`core/utils.py`) | Root for writable data |
| `DATA_DIR` | `BASE_DIR/data` | config, DB, sessions |
| `logs/` | `BASE_DIR/logs` | `YYYY-MM-DD.log` (ERROR+) |
| `ms-playwright/` | project/exe folder | Portable Chromium (only used if none at Playwright's default path) |

Playwright browser resolution happens once at startup in `run.py`:
if Chromium already exists at Playwright's default cache it is used as-is, otherwise
`PLAYWRIGHT_BROWSERS_PATH` is pointed at the portable `ms-playwright/` folder.

---

## 3. Startup

```
start.sh / start.bat
      └─> venv? vendor? install if missing
            └─> run.py
                  ├─ _setup_playwright_browsers_path()
                  ├─ QApplication + qasync QEventLoop
                  ├─ ThreadPoolExecutor(max_workers + max_concurrent_downloads + 8)
                  │     (crawling + file I/O + previews share this pool)
                  ├─ Engine(max_workers)      # worker pool + aiohttp session (created on Start)
                  └─ MainWindow(engine).show()
                        └─ QTimer(100ms) -> RestoreDialog -> _restore_session()
```

---

## 4. Flow A — Paste a URL → chapter preview

```
paste (or URL field changed)
   └─ on_paste_url
        ├─ validate scheme (http/https)
        ├─ if "Auto add to queue" is ON and a previous story is loaded -> add_queue() for it
        └─ on_load_chapters(url)
             ├─ site_id = auth_manager.site_id_for_url(url)     # config-driven (core/auth)
             │    └─ if the site needs login and we are not -> prompt_login()
             ├─ override = LeftPanel engine combo (Auto / Native / gallery-dl)
             ├─ meta, engine_used = engine.probe(url, site_id, engine=override)
             │    └─ selector picks the backend (see "Engines"); native = crawler.get_chapters
             │    ├─ scraper.scrape(url)  -> requests + BeautifulSoup heuristics
             │    │      raise BotProtectionError  # Cloudflare bot wall (403/503)
             │    │      or  {"title","thumb","referer","genres","chapters","has_more_chapters"}
             │    ├─ if no chapters OR has_more_chapters:      # JS page / "load more"
             │    │      render with Playwright headless -> scrape_from_html()
             │    ├─ return the result with the most chapters
             │    └─ if the chosen backend finds nothing -> try the other (fallback)
             └─ GUI: set title, load thumbnail (requests, 5s), fill chapter tree
```

**Cloudflare / bot wall.** Many sites sit behind Cloudflare's managed challenge. A plain
HTTP client gets `403`/`503` (challenge interstitial or "Attention Required"), and
Playwright's own browser is fingerprinted and refused too. `scraper._looks_like_bot_wall()`
detects this (status + `Server: cloudflare` / `cf-mitigated` / challenge markers in the body)
and raises `BotProtectionError`. `crawler.get_chapters` re-raises it immediately (no retries,
no rendering) and `MainWindow` shows a dedicated message: *this link is not supported yet —
the site uses Cloudflare bot protection*. Supporting these sites would require a
non-automated browser session; that work is **not** in the current code.

---

## 5. Flow B — Add to queue

Manual mode:

```
add_queue()
  ├─ save_path = <path input>/<safe_filename(title)>
  ├─ Job(url, title, save_path, chapters, referer, thumb, genres, site_id)
  └─ engine.add_job(job)
       ├─ existing row in DB? -> keep resume point (current_chap),
       │                         adopt CURRENT input path (update_save_path),
       │                         fill in missing chapters/thumb/genres
       ├─ status running/waiting -> "already_running" / "already_queued"
       ├─ status paused/done     -> requeue ("resume")
       └─ otherwise              -> INSERT + put on asyncio.Queue ("queued")
```

Auto mode (import from a link file):

```
add_jobs_from_file(path)
  ├─ parse_link_file()          # validation: size, binary sniff, encoding, url pattern
  ├─ pass 1: detect site per link, ask login ONCE per site
  └─ pass 2: crawl concurrently (Semaphore(max_workers)), then add_job per link
             with an AddJobsDialog progress modal
```

Chapters/thumb/referer/genres are stored in the DB, so a queued, paused or restored job
never has to re-crawl the story page.

---

## 6. Flow C — Start → worker → download

```
start_engine() / toggle_resume_engine()
  ├─ queue empty? -> notify
  ├─ save path exists? -> warn otherwise
  ├─ engine.sync_paths(current input path)   # changed folder wins over the stored one
  └─ engine.start() -> _run_workers()
        ├─ one aiohttp.ClientSession (unlimited pool connector) shared by
        │     crawler.extract_images() and downloader
        ├─ N worker() tasks  (N = CONFIG["max_workers"])
        └─ per job:
              ├─ deleted while queued? -> skip
              ├─ site needs login and session invalid -> pause + emit login_required
              ├─ backend = selector.pick(url, job.engine)   # native | gallerydl
              ├─ no chapters yet? -> backend.probe()
              └─ backend.download()   # native = download_job (unchanged); gallerydl = subprocess
                    ├─ (native) _download_thumb() -> thumb.<ext>, _save_genres() -> genres.txt
                    ├─ (native) for each chapter (oldest -> newest), resume at current_chap:
                    │     ├─ extract_images(chapter_url)
                    │     ├─ chapter folder = "<index:04d> - <safe title>"
                    │     ├─ already complete (verify_chapter)? -> skip
                    │     └─ download_batch() -> 0000.jpg, 0001.jpg, ...
                    │         progress "Downloading...(i/total): n%"
                    └─ (gallerydl) run gallery-dl into a temp dir, then normalize_layout()
                        into the same "<index:04d> - <chapter>" / "NNNN.<ext>" layout
              ├─ a backend error / empty result -> fall back once to the other engine
              ├─ (job.engine column records what actually ran; fallback flagged in DB)
              ├─ failures?            -> status "failed"
              ├─ missing images?      -> status "done_with_missing"
              └─ otherwise            -> status "done", resume point cleared
```

A finished job clears its resume point on purpose: re-adding the story later runs a full
pass from chapter 1 again, and `verify_chapter` re-downloads whatever is missing on disk
(e.g. a chapter folder the user deleted). Resuming only applies to jobs that were
interrupted (`paused` / `running` / `failed`).

`_download_thumb` / `_save_genres` are idempotent (they check for the concrete file/dir
they produce), so re-running a job completes whatever is still missing.

---

## 7. Flow D — Chapter images

```
crawler.extract_images(chapter_url)
  ├─ aiohttp GET (login cookies/headers applied when site_id is set)
  ├─ scraper.find_chapter_images(html)
  │     ├─ scan all <img>, drop junk (logo/icon/avatar/banner/ad, comment widgets, emoji buttons)
  │     ├─ prefer known comic CDN paths, else keep the dominant same-directory group
  │     └─ resolve DuckDuckGo image proxies to the original URL
  └─ if every URL is a placeholder (transparent/loading/spacer) -> render with
     Playwright headless and re-extract (JS/lazy-loading pages)
        └─ downloader.download_batch()
              ├─ Semaphore(max_concurrent_downloads) shared app-wide
              ├─ per image: retries (download_retry), 404 -> "missing", else "failed"
              └─ extension from URL or Content-Type
```

**Special case — cuutruyen.net** (`core/scraping/sites/cuutruyen.py`): a Vue SPA with a public JSON API
and DRM-scrambled images. It bypasses the heuristics entirely:
chapters come from `/api/v2/mangas/<id>/chapters`, and each page is descrambled by running
the site's own wasm module (`render_image`) inside a browser page, then saved.

**Special case — nhentai.net** (`core/scraping/sites/nhentai.py`): a gallery site, not a chapter site — a
work is a single gallery of images and the reader is a JS SPA, so `scraper.scrape` returns no
chapters via the HTML heuristics. Both metadata and the page list come from the public JSON
API (`/api/v2/galleries/<id>` and `/api/v2/cdn`), and the whole gallery is exposed as **one
chapter** (`scraper.scrape` branch). `crawler.extract_images` short-circuits nhentai URLs to
`nhentai.fetch_pages`, which returns `<image_server>/<page.path>` for every page — plain
images, so the normal `download_batch` path downloads them (no DRM renderer, no engine branch).

---

## 8. Flow E — Pause / resume / restore

```
Pause  -> engine.stop(): running jobs -> "paused", re-queued, workers cancelled
Resume -> requeue + engine.start() (save path re-applied from the input)
Restore (at startup, RestoreDialog)
       -> get_restorable_jobs(): every row whose status != "done" (waiting/paused/
          running/failed/done_with_missing), oldest first
          -> optionally re-based onto the current path input, status -> "waiting", queued
```

---

## 9. Flow F — Login & sessions (optional, config-driven)

Sites that need a login are declared in `core/auth/sites_config.json` (not committed with
real credentials). `auth_manager` builds a handler per site:

* `site_id_for_url()` maps a pasted URL to a site id by domain.
* `login()` performs the site's flow and stores cookies (+ any auth headers/tokens).
* `session_store` persists them to `data/sessions/<site>.json` so a restart does not require
  re-login; `crawler`, `downloader` and the GUI replay cookies/headers on every request.
* If a queued job's session expires, the engine pauses it and emits `login_required`;
  the GUI prompts, then resumes the job automatically.

---

## 10. Flow G — Auto shutdown

```
engine.finished
   └─ shutdown checkbox ON and every queued job finished?
        └─ confirmation dialog with a countdown (QSettings "shutdown_delay")
             └─ _shutdown_system(): Windows `shutdown /s /t 5`,
                Linux `systemctl poweroff` (fallback `shutdown -h now`)
```

---

## 11. Scraper heuristics (quick reference)

All site-agnostic — there are no per-site selectors to maintain. (Two hosts skip these
heuristics and read their own JSON API instead: cuutruyen.net and nhentai.net — see Flow D.)

| Field | Strategy |
| :--- | :--- |
| `title` | First `<h1>` whose text appears in `og:title` (og:title is the anchor, never returned as-is). Fallbacks: first `<h1>`, `<title>` tag, thumb `alt`. |
| `thumb` | `og:image` (unless logo/icon), else `img[class*=thumb/cover]`, `.thumb img`, first `<img>`. |
| `chapters` | Leaves matching `Chapter/Chap/Chương N` → pick the best group (distinct-label ratio) → expand to the full tag+class pattern in the shared container → keep only links on the story's own base path. If the regex finds nothing (or far fewer than the link scan), scan every `<a>`/`onclick` on the base path, dropping nav buttons (`Đọc từ đầu`, `Đọc mới nhất`, `Xem Online`, …). `has_more_chapters` flags a "load more" control so the crawler can expand it. |
| `genres` | Find the non-link "Thể loại"/"Genre" label and keep the links that follow it (the group with the fewest matches wins, so a site-wide menu never beats the story's own list). Sites with no such label return no genres. |
| images | See Flow D. |

---

## 12. Database

`data/jobs.db`, one table, `url` is the primary key:

| Column | Notes |
| :--- | :--- |
| `url` | primary key |
| `title`, `save_path` | display + output folder |
| `status` | `waiting` / `running` / `paused` / `failed` / `done` / `done_with_missing` |
| `current_chap` | resume point (1-based index into the chapter list); NULL for finished jobs so re-adding does a full pass |
| `chapters` | JSON `[{title, url, update_time}]` — avoids re-crawling |
| `thumb`, `referer`, `genres`, `site_id` | preview data needed by the download phase |
| `engine` | backend used/preferred: `native` / `gallerydl` (NULL = selector default) |
| `engine_fallback_used` | 1 when the job was retried on the other engine |
| `engine_error` | last backend error (debug / tooltip) |

Writes from the async hot path go through `a*` wrappers (`aupdate_*`, `adelete`) so SQLite
never blocks the Qt event loop; a `threading.Lock` guards the shared connection.

---

## 13. Engines (native vs gallery-dl)

Two download backends implement `core/engines/base.py`'s `DownloadBackend`
(`probe` for the preview, `download` for the queue). `core/engines/selector.py` chooses:

* **native** (`core/engines/native.py`) — wraps `Crawler.get_chapters` + `Engine.download_job`.
  Behaviour is unchanged; it is the reference implementation.
* **gallerydl** (`core/engines/gallerydl.py`) — runs gallery-dl as a subprocess (never imported
  in-process, so its GPL-2.0 licence stays at arm's length). `probe` = `--simulate --dump-json`
  normalised into `StoryMeta`; `download` = run into a per-job temp dir, poll the file count for
  progress, then `normalize_layout()` renames into the native `NNNN - <chapter>` / `NNNN.<ext>`
  layout. Cancelling terminates the subprocess.

Selection order (config `data/config.json`): a per-domain `engine_overrides` entry →
`engine_default` → the GUI's Engine combo override. When `engine_fallback` is on, a backend that
errors or finds nothing is retried **once** on the other one (except a Cloudflare bot wall, which
gallery-dl cannot clear either). The combo and `engine_default` values are `native` / `gallerydl`;
`engine_overrides` maps a domain, e.g. `{"example.com": "gallerydl"}`.

`tools/engine_compare.py` runs the A/B report (plan P1–P3) and prints a Markdown table.

> **Still to do:** run the P0–P6 test matrix site by site and confirm layout/resume for
> chaptered (manga) extractors before any change to `engine_default`.

---

## 14. Build & release

`build.py` (cross-platform) enters the project `.venv`, installs the dependencies declared in
`pyproject.toml` (including the `gallerydl` extra, so gallery-dl is bundled), patches nodriver,
downloads Playwright Chromium, generates `run.spec` on the
fly (per-OS Chromium path + Linux GUI-library excludes), and runs
`python -m PyInstaller run.spec --noconfirm`, producing `dist/ComicDownloadTool/` (onedir).
The spec collects `gallery_dl` (submodules + data) when it is installed; a frozen build runs it
by re-executing the app as a `--gallery-dl-worker` child (run.py), so nothing GPL is imported in
the GUI process. `gallerydl.executable` in config points at a standalone binary instead when set.
On Linux it then deletes the host GUI libraries that slipped into `_internal/`. The whole
folder is the distributable unit — the executable plus `_internal/` (assets, config, Playwright
driver + Chromium).

CI (`.github/workflows/build.yml`) runs on `v*` tags or manual dispatch, builds on
`ubuntu-latest` + `windows-latest` via `python build.py`, verifies the executable exists, zips
the output, and uploads an artifact. On a tag it also downloads both artifacts and publishes a
GitHub Release.

