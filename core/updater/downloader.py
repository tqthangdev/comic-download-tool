"""
core/updater/downloader.py

Streams a release asset into the update folder, reporting progress and cleaning
up after itself when something goes wrong.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import requests

CHUNK_BYTES = 256 * 1024
# (connect, read) timeouts: a release package is large, so reads get room.
TIMEOUT = (15, 60)


class DownloadError(Exception):
    """The package could not be downloaded."""


def download_asset(
    url: str,
    dest: Path,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    """Download `url` to `dest`; returns `dest`.

    progress: called with (bytes_done, bytes_total) — total is 0 when the server
    does not report a length. A partial file is removed on failure or cancel.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")

    try:
        with requests.get(url, stream=True, timeout=TIMEOUT) as resp:
            if resp.status_code != 200:
                raise DownloadError(f"HTTP {resp.status_code}")

            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(CHUNK_BYTES):
                    if cancel and cancel():
                        raise DownloadError("cancelled")
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except requests.RequestException as e:
        tmp.unlink(missing_ok=True)
        raise DownloadError(type(e).__name__) from e
    except DownloadError:
        tmp.unlink(missing_ok=True)
        raise
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise DownloadError(str(e)) from e

    tmp.replace(dest)
    return dest
