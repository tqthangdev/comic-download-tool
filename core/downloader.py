import asyncio
from pathlib import Path

import aiohttp

from core.logger import logger
from core.scraper import get_referer
from core.utils import CONFIG


CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
}


def guess_ext(url: str, content_type: str = None) -> str:
    """Determine the file extension: prefer a valid image extension found in
    the URL, fall back to the response's Content-Type, default to .jpg."""
    url_ext = Path(url.split("?")[0]).suffix.lower()
    if url_ext in CONTENT_TYPE_EXT.values():
        return url_ext

    if content_type:
        content_type = content_type.split(";")[0].strip().lower()
        if content_type in CONTENT_TYPE_EXT:
            return CONTENT_TYPE_EXT[content_type]

    return ".jpg"


class Downloader:
    def __init__(self, max_concurrent_downloads=None):
        self.session = None
        max_concurrent = (
            max_concurrent_downloads or CONFIG["max_concurrent_downloads"]
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def set_session(self, session):
        self.session = session

    # Result of downloading one image
    OK = "ok"
    MISSING = "missing"
    FAILED = "failed"

    async def _write_file_async(self, path: Path, data: bytes):
        """Write files without blocking the Event Loop by using traditional binary file I/O."""
        loop = asyncio.get_running_loop()

        def _write():
            with open(path, "wb") as f:
                f.write(data)

        await loop.run_in_executor(None, _write)

    async def _download(self, url, stem_path: Path, referer=None, retry=None):
        """Download an image to stem_path with the correct extension.
        stem_path should NOT include an extension (e.g. save_path / "0001").
        Returns (status, ext) where ext is None if not OK.
        """
        # Skip if a file with this stem already exists, regardless of extension
        existing = list(stem_path.parent.glob(f"{stem_path.name}.*"))
        if existing:
            return self.OK, existing[0].suffix

        retry = retry or CONFIG["download_retry"]
        headers = {
            "User-Agent": CONFIG["user_agent"],
        }
        if referer:
            headers["Referer"] = referer

        last_error = None

        for attempt in range(retry):
            try:
                # Wrap the Semaphore ONLY around the HTTP request & data retrieval
                # Releases the Semaphore immediately when the network operation completes (avoids holding a slot while sleeping during retries)
                async with self._semaphore:
                    async with self.session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(
                            total=CONFIG["request_timeout"]
                        ),
                    ) as r:

                        if r.status == 200:
                            data = await r.read()
                            content_type = r.headers.get("Content-Type")
                            ext = guess_ext(url, content_type)
                            final_path = stem_path.with_suffix(ext)

                            # Move disk I/O OUTSIDE the Semaphore block
                            # Frees up the network connection slot immediately for the next URL
                            await self._write_file_async(final_path, data)
                            return self.OK, ext

                        if r.status == 404:
                            logger.warning(f"Image missing (HTTP 404): {url}")
                            return self.MISSING, None

                        last_error = f"HTTP {r.status}"

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    f"Download image attempt {attempt + 1} failed for {url} ({type(e).__name__}): {e}"
                )
                if referer:
                    try:
                        current_referer = get_referer(url)
                        if current_referer:
                            url = url.replace(current_referer, referer)
                    except Exception as e2:
                        logger.warning(
                            f"Failed to rewrite referer for {url}: {type(e2).__name__}: {e2}"
                        )

            # Sleep between retries outside the Semaphore
            if attempt < retry - 1:
                await asyncio.sleep(1)

        logger.error(f"Download FAILED for URL: {url} — {last_error}")
        return self.FAILED, None

    async def download_batch(
        self, urls, save_path: Path, referer: str = None, progress=None
    ):
        save_path.mkdir(parents=True, exist_ok=True)

        total = len(urls)
        finished = 0
        failed_urls = []
        missing_urls = []

        # Lock to protect the finished counter and list when multiple coroutines write to them concurrently
        lock = asyncio.Lock()

        async def task(index, url):
            nonlocal finished
            stem_path = save_path / f"{index:04d}"  # no extension yet
            result, _ext = await self._download(url, stem_path, referer)

            async with lock:
                if result == self.MISSING:
                    missing_urls.append(url)
                elif result == self.FAILED:
                    failed_urls.append(url)

                finished += 1
                if progress:
                    progress(finished, total)

        tasks = [task(i, url) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)

        return failed_urls, missing_urls