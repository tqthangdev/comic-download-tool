"""gallery-dl backend: drive gallery-dl as a subprocess.

gallery-dl (GPL-2.0) is never imported in-process — only executed — which keeps
it at arm's length from the app and lets a hang be killed cleanly. Two jobs:

* ``probe``    — ``--simulate --dump-json`` gives the metadata + file list, which
                 is normalized into the app's ``StoryMeta``.
* ``download`` — run gallery-dl into a per-job temp folder (so resume/skip
                 works), then ``normalize_layout`` moves the result into the
                 native ``NNNN - <chapter>`` / ``NNNN.<ext>`` layout.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from core.engines import gallerydl_conf
from core.net.downloader import CONTENT_TYPE_EXT
from core.engines.base import (
    AUTH,
    BOT_PROTECTED,
    CANCELLED,
    DONE,
    DONE_WITH_MISSING,
    FAILED,
    UNSUPPORTED,
    BackendError,
    JobOutcome,
    StoryMeta,
)
from core.logger import logger
from core.scraping.scraper import get_referer
from core.utils import CONFIG, safe_filename

# gallery-dl --dump-json record kinds: [2, dir_meta], [3, url, file_meta].
FOLDER_CODE = 2
FILE_CODE = 3

POLL_SECONDS = 1.0
IMAGE_EXTS = set(CONTENT_TYPE_EXT.values())

# Fields an extractor may use to mark which chapter a file belongs to.
CHAPTER_KEYS = ("chapter", "chapter_id", "volume", "book", "book_id")


# ----------------------------------------------------------------------
# Locating / invoking gallery-dl
# ----------------------------------------------------------------------

def _settings() -> dict:
    return CONFIG.get("gallerydl") or {}


def command_prefix() -> list:
    """The argv prefix that runs gallery-dl on this machine.

    A configured ``gallerydl.executable`` (a standalone binary) always wins.
    A frozen build re-runs this very executable as a ``--gallery-dl-worker``
    child (see run.py), which keeps gallery-dl out of process. From source the
    venv interpreter runs ``python -m gallery_dl``.
    """
    explicit = (_settings().get("executable") or "").strip()
    if explicit:
        return [explicit]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--gallery-dl-worker"]
    return [sys.executable, "-m", "gallery_dl"]


def available() -> bool:
    """True when gallery-dl can actually be executed.

    In a frozen build this is only True when gallery-dl was bundled (build.py);
    from source it means the optional extra is installed in the venv.
    """
    if not _settings().get("enabled", True):
        return False

    explicit = (_settings().get("executable") or "").strip()
    if explicit:
        return Path(explicit).exists()
    return importlib.util.find_spec("gallery_dl") is not None


def _extra_args() -> list:
    args = _settings().get("extra_args") or []
    return [str(a) for a in args]


def _work_dir(url: str) -> Path:
    """Persistent per-job download folder (kept so `skip` gives resume)."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    path = gallerydl_conf.WORK_DIR / "jobs" / digest
    path.mkdir(parents=True, exist_ok=True)
    return path


def _classify_failure(text: str) -> str:
    """Map gallery-dl stderr onto a stable error code."""
    lowered = (text or "").lower()
    if "no suitable extractor" in lowered or "unsupported url" in lowered:
        return UNSUPPORTED
    if "403" in lowered or "cloudflare" in lowered or "captcha" in lowered:
        return BOT_PROTECTED
    if "401" in lowered or "unauthorized" in lowered or "login" in lowered:
        return AUTH
    return ""


# ----------------------------------------------------------------------
# Metadata normalization (gallery-dl -> StoryMeta)
# ----------------------------------------------------------------------

def _chapter_key(meta: dict) -> str:
    for key in CHAPTER_KEYS:
        value = meta.get(key)
        if value not in (None, ""):
            return f"{key}:{value}"
    return ""


def _chapter_title(meta: dict, key: str) -> str:
    for field in ("chapter", "chapter_name", "title"):
        value = meta.get(field)
        if value:
            return str(value)
    return key.split(":", 1)[1] if ":" in key else (key or "Gallery")


def parse_records(stdout: str) -> tuple:
    """Split ``--dump-json`` output into (directory_metadata, [(url, meta)])."""
    try:
        entries = json.loads(stdout)
    except ValueError as e:
        raise BackendError("gallery-dl returned no JSON", UNSUPPORTED) from e

    directory, files = {}, []
    for entry in entries:
        if not isinstance(entry, list) or not entry:
            continue
        code = entry[0]
        if code == FOLDER_CODE and len(entry) >= 2 and isinstance(entry[1], dict):
            directory.update(entry[1])
        elif code == FILE_CODE and len(entry) >= 3 and isinstance(entry[2], dict):
            files.append((entry[1], entry[2]))

    return directory, files


def normalize_metadata(url: str, stdout: str) -> StoryMeta:
    """Turn gallery-dl's dump-json into the app's StoryMeta.

    Files are grouped by their chapter key; a gallery without one becomes a
    single chapter, matching the native engine's convention.
    """
    directory, files = parse_records(stdout)
    if not files:
        raise BackendError("gallery-dl found no downloadable items", UNSUPPORTED)

    title = (directory.get("title") or files[0][1].get("title") or "").strip()
    thumb = directory.get("cover") or directory.get("thumbnail") or ""
    genres = list(
        dict.fromkeys(directory.get("tags") or files[0][1].get("tags") or [])
    )

    chapters, seen = [], {}
    for file_url, meta in files:
        key = _chapter_key(meta)
        if key not in seen:
            seen[key] = {
                "title": _chapter_title(meta, key) if key else (title or "Gallery"),
                # Synthetic URL: the gallery-dl backend downloads by story URL,
                # so a chapter URL is only an identifier for the queue/DB.
                "url": f"gallerydl:{hashlib.sha1((url + key).encode('utf-8')).hexdigest()[:16]}",
                "update_time": "",
            }
            chapters.append(seen[key])

    return StoryMeta(
        title=title,
        thumb=thumb,
        referer=get_referer(url),
        genres=genres,
        chapters=chapters,
    )


# ----------------------------------------------------------------------
# Layout normalization (gallery-dl output -> native layout)
# ----------------------------------------------------------------------

def _images_in(folder: Path) -> list:
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def _collect_groups(source: Path) -> list:
    """(name, [image files]) groups: per subfolder, or the flat top level.

    gallery-dl writes chapter subfolders for manga extractors and flat files
    for galleries, so handle both.
    """
    subdirs = [
        d for d in sorted(source.iterdir())
        if d.is_dir() and _images_in(d)
    ]
    groups = [(d.name, _images_in(d)) for d in subdirs]

    flat = [
        p for p in sorted(source.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    if flat:
        groups.append(("", flat))

    return groups


def normalize_layout(source: Path, target: Path, chapter_titles=None) -> int:
    """Move gallery-dl's output into ``target`` as ``NNNN - <chapter>`` folders.

    ``chapter_titles`` (from the probe) names each folder the way the native
    engine does; otherwise gallery-dl's own subfolder name is used. Idempotent:
    a chapter folder that already holds at least as many images is left
    untouched (this is what makes resume a no-op). Returns chapters written.
    """
    groups = _collect_groups(source)
    chapter_titles = chapter_titles or []
    written = 0

    for index, (name, files) in enumerate(groups, 1):
        title = ""
        if index <= len(chapter_titles):
            title = chapter_titles[index - 1] or ""
        label = safe_filename(title) or safe_filename(name) or f"Chapter {index}"
        folder = target / f"{index:04d} - {label}"

        existing = _images_in(folder) if folder.exists() else []
        if existing and len(existing) >= len(files):
            continue

        folder.mkdir(parents=True, exist_ok=True)
        for file_index, src in enumerate(files):
            ext = src.suffix.lower()
            dst = folder / f"{file_index:04d}{ext}"
            if dst.exists():
                continue
            try:
                shutil.move(str(src), str(dst))
            except (OSError, shutil.Error) as e:
                logger.warning(f"[gallerydl] cannot move {src} -> {dst}: {e}")
        written += 1

    return written


# ----------------------------------------------------------------------
# Backend
# ----------------------------------------------------------------------

class GalleryDLBackend:
    name = "gallerydl"

    def __init__(self, engine=None):
        self.engine = engine

    async def supports(self, url: str) -> bool:
        return available()

    async def _run_json(self, url: str, site_id: Optional[str]) -> str:
        """Run ``--simulate --dump-json`` and return stdout."""
        work = _work_dir(url)
        cookies = gallerydl_conf.export_session(
            site_id, urlparse(url).netloc, work / "cookies.txt"
        )
        conf = gallerydl_conf.build_config(work, cookies_path=cookies)
        conf_path = gallerydl_conf.write_config(conf, work / "config.json")

        args = command_prefix() + [
            "--config", str(conf_path),
            "--simulate", "--dump-json",
            *_extra_args(),
            url,
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            message = stderr.decode("utf-8", "replace")
            raise BackendError(
                message.strip() or "gallery-dl failed",
                _classify_failure(message),
            )
        return stdout.decode("utf-8", "replace")

    async def probe(self, url: str, site_id: Optional[str] = None) -> StoryMeta:
        stdout = await self._run_json(url, site_id)
        return normalize_metadata(url, stdout)

    async def download(self, job, progress=None, cancel=None) -> JobOutcome:
        work = _work_dir(job.url)
        cookies = gallerydl_conf.export_session(
            job.site_id, urlparse(job.url).netloc, work / "cookies.txt"
        )
        conf = gallerydl_conf.build_config(work, cookies_path=cookies)
        conf_path = gallerydl_conf.write_config(conf, work / "config.json")

        args = command_prefix() + [
            "--config", str(conf_path),
            *_extra_args(),
            job.url,
        ]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        expected = len(job.chapters or []) or 1
        cancelled = False
        last_done = -1
        stderr_chunks = []

        # Drain stderr in the background so a chatty run cannot fill the pipe.
        async def _drain():
            stderr_chunks.append((await proc.stderr.read()).decode("utf-8", "replace"))

        drain_task = asyncio.ensure_future(_drain())

        try:
            while proc.returncode is None:
                if cancel and cancel():
                    cancelled = True
                    proc.terminate()
                    break
                try:
                    await asyncio.wait_for(proc.wait(), timeout=POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                if progress:
                    done = min(len(_collect_groups(work)), expected)
                    if done != last_done:
                        last_done = done
                        progress(done, expected)
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
            await drain_task

        stderr_text = "".join(stderr_chunks)

        if cancelled:
            return JobOutcome(status=CANCELLED)

        # gallery-dl failed outright (nothing usable on disk)?
        if proc.returncode != 0 and not _collect_groups(work):
            raise BackendError(
                stderr_text.strip() or f"gallery-dl exited {proc.returncode}",
                _classify_failure(stderr_text),
            )

        job.save_path.mkdir(parents=True, exist_ok=True)
        titles = [c.get("title") for c in (job.chapters or [])]
        normalize_layout(work, job.save_path, titles)

        # Success is measured by what is on disk, not by how much this run moved:
        # a re-run where the chapter folders were already complete writes nothing.
        downloaded = sum(
            len(_images_in(folder))
            for folder in job.save_path.iterdir()
            if folder.is_dir()
        )
        if downloaded == 0:
            return JobOutcome(status=FAILED)

        status = DONE if proc.returncode == 0 else DONE_WITH_MISSING
        return JobOutcome(status=status, ok=downloaded)
