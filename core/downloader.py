import asyncio
from pathlib import Path
import aiohttp
from core.logger import logger
from core.scraper import get_referer
from core.utils import CONFIG


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

        # Use a simple lambda to write the file
        def _write():
            with open(path, "wb") as f:
                f.write(data)

        await loop.run_in_executor(None, _write)

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

                            # Move disk I/O OUTSIDE the Semaphore block
                            # Frees up the network connection slot immediately for the next URL
                            await self._write_file_async(path, data)
                            return self.OK

                        if r.status == 404:
                            logger.warning(f"Image missing (HTTP 404): {url}")
                            return self.MISSING

                        last_error = f"HTTP {r.status}"

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    f"Download image attempt {attempt + 1} failed for {url} ({type(e).__name__}): {e}"
                )
                url = url.replace(get_referer(url), referer)

            # Sleep between retries outside the Semaphore
            if attempt < retry - 1:
                await asyncio.sleep(1)

        logger.error(f"Download FAILED for URL: {url} — {last_error}")
        return self.FAILED

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
            file = save_path / f"{index:04d}.jpg"
            result = await self._download(url, file, referer)

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