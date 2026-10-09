"""Native backend: the original crawler + aiohttp downloader, unchanged.

A thin adapter over ``Crawler.get_chapters`` and ``Engine.download_job`` so the
existing behaviour (progress strings, resume, PDF export, the cuutruyen/nhentai
special cases) stays exactly as it was. It is the reference implementation the
gallery-dl backend is measured against.
"""

from __future__ import annotations

from typing import Optional

from core.engines.base import (
    DELETED,
    DONE,
    DONE_WITH_MISSING,
    FAILED,
    JobOutcome,
    StoryMeta,
)
from core.scraping.scraper import get_referer


class NativeBackend:
    name = "native"

    def __init__(self, engine):
        self.engine = engine

    async def supports(self, url: str) -> bool:
        # The heuristics attempt every URL; probe() reports what came back.
        return True

    async def probe(self, url: str, site_id: Optional[str] = None) -> StoryMeta:
        data = await self.engine.crawler.get_chapters(url, site_id=site_id)
        return StoryMeta.from_dict(data)

    async def download(self, job, progress=None, cancel=None) -> JobOutcome:
        # `progress`/`cancel` are intentionally unused: download_job() already
        # drives engine.progress and checks engine.running, exactly as before.
        data = {
            "title": job.title,
            "thumb": job.thumb or "",
            "referer": job.referer or get_referer(job.url) or "",
            "chapters": job.chapters or [],
            "genres": self.engine._normalize_genres(job.genres),
        }

        result = await self.engine.download_job(job, data)

        if result == "deleted":
            return JobOutcome(status=DELETED)

        has_failed, has_missing, missing_details = result
        if has_failed:
            return JobOutcome(status=FAILED)
        if has_missing:
            return JobOutcome(
                status=DONE_WITH_MISSING, missing_details=missing_details
            )
        return JobOutcome(status=DONE)
