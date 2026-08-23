import asyncio
from typing import List

from core.scraper import scrape, find_chapter_images
from core.utils import resolve_ddg_proxy, CONFIG
from core.logger import logger


class Crawler:
    """Crawler giờ chỉ lo việc lấy HTML + trích ảnh chapter.

    Danh sách chapter (title/thumb/chapters) lấy qua core/scraper.py
    (requests + BeautifulSoup heuristic) — không còn Playwright cho phần này.
    """

    def __init__(self):
        self._http_session = None  # aiohttp session dùng cho extract_images

    def set_http_session(self, session):
        """Gọi từ Engine, dùng chung session đã có sẵn (đỡ tạo mới)."""
        self._http_session = session

    async def get_chapters(self, url: str, retries: int = None):
        """Lấy title/thumb/referer/chapters bằng scraper.py (requests).

        Chạy trong executor vì scraper là đồng bộ (requests + BeautifulSoup),
        tránh block event loop (qasync dùng chung loop với GUI).
        """
        retries = retries if retries is not None else CONFIG["chapter_retry"]
        loop = asyncio.get_running_loop()
        last_error = None

        for attempt in range(retries + 1):
            try:
                return await loop.run_in_executor(None, scrape, url)
            except Exception as e:
                last_error = e
                logger.error(f"[get_chapters] Attempt {attempt + 1} failed: {e}")
                if attempt < retries:
                    await asyncio.sleep(0.5)
        raise last_error

    async def extract_images(self, url: str) -> List[str]:
        if self._http_session is None:
            raise RuntimeError("HTTP session chưa được set. Gọi crawler.set_http_session(session) trước.")

        async with self._http_session.get(url, timeout=CONFIG["request_timeout"]) as resp:
            html = await resp.text()

        loop = asyncio.get_running_loop()
        raw_srcs = await loop.run_in_executor(None, find_chapter_images, html, url)

        return [resolve_ddg_proxy(src) for src in raw_srcs]

    async def close(self):
        """Playwright đã không còn dùng cho get_chapters nữa — không còn gì để dọn."""
        return
