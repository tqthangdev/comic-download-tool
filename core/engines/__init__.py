"""Download engine backends.

Two backends implement the same thin interface:

* ``native``    — the original heuristic crawler + aiohttp downloader
                  (``core.engines.native``), behaviour unchanged.
* ``gallerydl`` — shells out to gallery-dl (``core.engines.gallerydl``).

``core.engines.selector`` decides which one a job uses (config default, per-site
override, or automatic fallback), so the engine/GUI never pick directly.
"""

from core.engines.base import (
    AUTH,
    BOT_PROTECTED,
    CANCELLED,
    DELETED,
    DONE,
    DONE_WITH_MISSING,
    FAILED,
    UNSUPPORTED,
    BackendError,
    DownloadBackend,
    JobOutcome,
    StoryMeta,
)
from core.engines.native import NativeBackend

__all__ = [
    "AUTH",
    "BOT_PROTECTED",
    "CANCELLED",
    "DELETED",
    "DONE",
    "DONE_WITH_MISSING",
    "FAILED",
    "UNSUPPORTED",
    "BackendError",
    "DownloadBackend",
    "JobOutcome",
    "StoryMeta",
    "NativeBackend",
]
