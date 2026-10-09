"""Generate a gallery-dl configuration + cookie file for one job.

gallery-dl is only ever driven as a subprocess, so nothing here imports it; we
just produce a JSON config and (when the site needs a login) a Netscape
``cookies.txt`` from the session the app already holds.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from core.auth import auth_manager
from core.utils import CONFIG, DATA_DIR

# Config/cookie files for in-flight jobs live here (wiped by the backend).
WORK_DIR = DATA_DIR / "gallerydl"


def _settings() -> dict:
    return CONFIG.get("gallerydl") or {}


def build_config(
    save_path: Path,
    *,
    cookies_path: Optional[Path] = None,
    sleep_request: Optional[float] = None,
    retries: Optional[int] = None,
    timeout: Optional[int] = None,
) -> dict:
    """The gallery-dl config for one job.

    ``filename`` numbers files from 0 (``{num|int - 1:>04}``) so the on-disk
    layout already looks like the native one; ``normalize_layout`` only has to
    deal with the chapter folder name.
    """
    settings = _settings()
    retries = retries if retries is not None else settings.get("retries", 4)
    timeout = timeout if timeout is not None else settings.get("timeout", 30)
    sleep_request = (
        sleep_request if sleep_request is not None
        else settings.get("sleep_request", 0.5)
    )

    config = {
        "extractor": {
            "base-directory": str(save_path),
            "filename": "{num|int - 1:>04}.{extension}",
            "sleep-request": sleep_request,
            "retries": retries,
            "timeout": timeout,
            # Resume: leave files already on disk alone and keep going.
            "skip": True,
        },
        "downloader": {
            "retries": retries,
            "timeout": timeout,
        },
        # No per-file console spam; progress is tracked from the file system.
        "output": {"mode": "null"},
    }

    if cookies_path is not None:
        config["extractor"]["cookies"] = str(cookies_path)

    return config


def write_config(config: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def write_cookies(cookies: dict, domain: str, path: Path) -> Optional[Path]:
    """Write a {name: value} cookie dict as a Netscape cookies.txt."""
    if not cookies or not domain:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    expires = int(time.time()) + 365 * 24 * 3600
    lines = ["# Netscape HTTP Cookie File"]
    for name, value in cookies.items():
        lines.append(
            "\t".join([domain, "TRUE", "/", "TRUE", str(expires), str(name), str(value)])
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def export_session(site_id: str, domain: str, path: Path) -> Optional[Path]:
    """Export the app's stored login for ``site_id`` as a cookies.txt.

    Returns None when the site is public (no session) or has no cookies — a
    handful of sites authenticate with a header instead, which gallery-dl cannot
    replay, so those simply run unauthenticated.
    """
    if not site_id:
        return None
    try:
        cookies = auth_manager.get_cookies(site_id)
    except KeyError:
        return None
    return write_cookies(cookies, domain, path)
