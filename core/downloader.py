import asyncio
import aiohttp
from pathlib import Path

from core.utils import CONFIG
from core.logger import logger


class Downloader:

    def __init__(self, max_concurrent_downloads=None):
        self.session = None
        max_concurrent = max_concurrent_downloads or CONFIG["max_concurrent_downloads"]
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def set_session(self, session):
        self.session = session

    async def _download(self, url, path, referer=None, retry=None):
        if path.exists():
            return True

        retry = retry or CONFIG["download_retry"]

        headers = {
            "User-Agent": CONFIG["user_agent"],
        }

        if referer:
            headers["Referer"] = referer

        for attempt in range(retry):
            try:
                async with self._semaphore:  # giới hạn số request đồng thời
                    async with self.session.get(
                            url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=CONFIG["request_timeout"])
                    ) as r:
                        if r.status == 200:
                            data = await r.read()

                            # Ghi file trong executor để không block event loop
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(None, path.write_bytes, data)

                            return True

            except Exception as e:
                logger.warning(f"Download image attempt {attempt + 1} failed for {url} ({type(e).__name__}): {e}")

            await asyncio.sleep(1)

        logger.error(f"Download FAILED for URL: {url}")
        return False

    async def download_batch(self, urls, save_path: Path, referer: str = None, progress=None):
        save_path.mkdir(parents=True, exist_ok=True)

        total = len(urls)
        finished = 0
        failed_urls = []

        async def task(index, url):
            nonlocal finished
            file = save_path / f"{index:04d}.jpg"
            ok = await self._download(url, file, referer)

            if not ok:
                failed_urls.append(url)

            finished += 1
            if progress:
                progress(finished, total)

        tasks = [task(i, url) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)

        return failed_urls
