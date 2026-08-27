import asyncio
import aiohttp
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from core.utils import CONFIG
from core.logger import logger


class Downloader:

    def __init__(self, max_concurrent_downloads=None):
        self.session = None
        max_concurrent = max_concurrent_downloads or CONFIG["max_concurrent_downloads"]
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def set_session(self, session):
        self.session = session

    # Result of downloading one image
    OK = "ok"
    MISSING = "missing"
    FAILED = "failed"

    async def _download(self, url, path, referer=None, retry=None):
        if path.exists():
            return self.OK

        retry = retry or CONFIG["download_retry"]

        headers = {
            "User-Agent": CONFIG["user_agent"],
        }

        if referer:
            headers["Referer"] = referer

        last_error = None

        for attempt in range(retry):
            try:
                async with self._semaphore:  # limit concurrent requests
                    async with self.session.get(
                            url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=CONFIG["request_timeout"])
                    ) as r:
                        if r.status == 200:
                            data = await r.read()

                            # Write the file in an executor to avoid blocking the event loop
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(None, path.write_bytes, data)

                            return self.OK

                        # HTTP 404 means the image does not exist on the storage.
                        # This is a source data error, not a network error—retrying is useless.
                        if r.status == 404:
                            logger.warning(f"Image missing (HTTP 404): {url}")
                            return self.MISSING

                        last_error = f"HTTP {r.status}"

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(f"Download image attempt {attempt + 1} failed for {url} ({type(e).__name__}): {e}")

            # Sleep only between retries, not after the final attempt
            if attempt < retry - 1:
                await asyncio.sleep(1)

        logger.error(f"Download FAILED for URL: {url} — {last_error}")
        return self.FAILED

    async def download_batch(self, urls, save_path: Path, referer: str = None, progress=None):
        """Download a batch of images.

        Returns a tuple (failed_urls, missing_urls):
        - failed_urls: URLs that failed due to network/server errors after all retries.
        - missing_urls: URLs that returned HTTP 404 because the image is missing from the source.
        """
        save_path.mkdir(parents=True, exist_ok=True)

        total = len(urls)
        finished = 0
        failed_urls = []
        missing_urls = []

        async def task(index, url):
            nonlocal finished
            file = save_path / f"{index:04d}.jpg"
            result = await self._download(url, file, referer)

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
