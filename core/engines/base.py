"""Backend interface shared by the native engine and gallery-dl.

A backend owns the two things the app used to hard-code in ``core.engine``:

* ``probe(url)``    -> the story metadata used for the chapter preview (Flow A)
* ``download(job)`` -> crawling the chapters and writing the images (Flow C)

The native backend wraps the existing crawler + aiohttp downloader so its
behaviour is unchanged; the gallery-dl backend shells out to gallery-dl.
``core.engines.selector`` decides which one a job uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, runtime_checkable

# Outcomes, matching the statuses the native engine already uses.
DONE = "done"
DONE_WITH_MISSING = "done_with_missing"
FAILED = "failed"
DELETED = "deleted"

# Stable error codes the selector and the UI can branch on.
UNSUPPORTED = "unsupported"          # no extractor / heuristics found nothing
AUTH = "auth"                        # login required or session expired
BOT_PROTECTED = "bot_protected"      # Cloudflare / bot wall
CANCELLED = "cancelled"              # user paused/aborted mid-download


class BackendError(Exception):
    """A backend could not complete an operation."""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


@dataclass
class StoryMeta:
    """Normalized story metadata — the exact shape the GUI/tree consumes."""

    title: str = ""
    thumb: str = ""
    referer: str = ""
    genres: list = field(default_factory=list)
    chapters: list = field(default_factory=list)  # [{title, url, update_time}]

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "StoryMeta":
        data = data or {}
        return cls(
            title=data.get("title") or "",
            thumb=data.get("thumb") or "",
            referer=data.get("referer") or "",
            genres=data.get("genres") or [],
            chapters=data.get("chapters") or [],
        )

    def as_dict(self) -> dict:
        """The dict the existing engine/GUI code expects."""
        return {
            "title": self.title,
            "thumb": self.thumb,
            "referer": self.referer,
            "genres": self.genres,
            "chapters": self.chapters,
        }


@dataclass
class JobOutcome:
    """Result of downloading one job."""

    status: str = DONE
    missing_details: dict = field(default_factory=dict)
    # Image counts (for logging / the engine-compare tool).
    ok: int = 0
    missing: int = 0
    failed: int = 0


ProgressCallback = Callable[[int, int], None]   # (done, total)
CancelCheck = Callable[[], bool]                # True => stop


@runtime_checkable
class DownloadBackend(Protocol):
    name: str

    async def supports(self, url: str) -> bool:
        """True when this backend can handle ``url`` at all (cheap check)."""
        ...

    async def probe(self, url: str, site_id: Optional[str] = None) -> StoryMeta:
        """Story metadata + chapter list, for the preview."""
        ...

    async def download(
        self,
        job,
        progress: Optional[ProgressCallback] = None,
        cancel: Optional[CancelCheck] = None,
    ) -> JobOutcome:
        """Download every chapter of ``job`` into its save_path."""
        ...
