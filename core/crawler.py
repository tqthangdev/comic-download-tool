import asyncio
from typing import List
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from core.utils import resolve_ddg_proxy
from extractors import get_extractor
from core.utils import CONFIG
from core.logger import logger

BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
BLOCKED_DOMAINS = [
    "googlesyndication.com", "doubleclick.net",
    "google-analytics.com", "googletagmanager.com",
    "api.country.is",
]


class Crawler:

    def __init__(self):
        self.browser = None
        self.context = None
        self.playwright = None
        self._chapters_page = None
        self._chapters_lock = asyncio.Lock()
        self._http_session = None  # aiohttp session dùng cho extract_images

    def set_http_session(self, session):
        """Gọi từ Engine, dùng chung session đã có sẵn (đỡ tạo mới)."""
        self._http_session = session

    async def _init(self):
        if not self.browser:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)

        if not self.context:
            self.context = await self.browser.new_context()
            await self.context.route("**/*", self._block_resources)

    @staticmethod
    async def _block_resources(route):
        req = route.request
        url = req.url
        if req.resource_type in BLOCKED_RESOURCE_TYPES or any(d in url for d in BLOCKED_DOMAINS):
            await route.abort()
        else:
            await route.continue_()

    async def get_chapters(self, url: str, retries: int = None):
        retries = retries if retries is not None else CONFIG["chapter_retry"]
        await self._init()
        extractor = get_extractor(url)

        async with self._chapters_lock:
            last_error = None
            for attempt in range(retries + 1):
                try:
                    if self._chapters_page is None or self._chapters_page.is_closed():
                        self._chapters_page = await self.context.new_page()
                    page = self._chapters_page

                    await page.goto(url, wait_until="commit", timeout=CONFIG["request_timeout"] * 1000)
                    for sel in extractor.wait_selectors:
                        await page.wait_for_selector(sel, timeout=(CONFIG["request_timeout"] / 2) * 1000)

                    data = await extractor.extract(page)
                    return data

                except Exception as e:
                    last_error = e
                    logger.error(f"[get_chapters] Attempt {attempt + 1} failed: {e}")
                    try:
                        if self._chapters_page and not self._chapters_page.is_closed():
                            await self._chapters_page.close()
                    except Exception:
                        pass
                    self._chapters_page = None
                    if attempt < retries:
                        await asyncio.sleep(0.5)
            raise last_error

    async def extract_images(self, url: str) -> List[str]:
        if self._http_session is None:
            raise RuntimeError("HTTP session chưa được set. Gọi crawler.set_http_session(session) trước.")

        extractor = get_extractor(url)

        async with self._http_session.get(url, timeout=CONFIG["request_timeout"]) as resp:
            html = await resp.text()

        loop = asyncio.get_running_loop()
        raw_srcs = await loop.run_in_executor(None, extractor.parse_images, html)

        return [resolve_ddg_proxy(src) for src in raw_srcs]

    async def close(self):
        if self._chapters_page and not self._chapters_page.is_closed():
            await self._chapters_page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
