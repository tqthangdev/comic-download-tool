import asyncio
from typing import List

from core.scraper import scrape, scrape_from_html, find_chapter_images
from core.utils import resolve_ddg_proxy, CONFIG
from core.logger import logger

# Placeholder URLs (unrendered / lazy images) — not real content
PLACEHOLDER_PARTS = ("transparent", "placeholder", "loading", "spacer", "/assets/img/")


def _has_real_images(urls: List[str]) -> bool:
    """Return True if at least one URL is not a placeholder."""
    return any(
        not any(p in u.lower() for p in PLACEHOLDER_PARTS)
        for u in urls
    )


class Crawler:
    """Handles fetching HTML and extracting chapter images.

    The chapter list (title/thumb/chapters) comes from core/scraper.py via
    requests + BeautifulSoup heuristics. If a page renders its chapters with
    JS (requests finds none), fall back to Playwright headless to render the
    page, then scrape on the rendered HTML.
    """

    def __init__(self):
        self._http_session = None  # aiohttp session used by extract_images
        self._pw = None            # async_playwright context (lazy)

    def set_http_session(self, session):
        """Called by Engine to reuse a shared aiohttp session (avoids recreating one)."""
        self._http_session = session

    async def _render_html(self, url: str) -> str:
        """Render a URL with Playwright headless, returning the JS-executed HTML."""
        from playwright.async_api import async_playwright

        if self._pw is None:
            self._pw = await async_playwright().start()
        browser = await self._pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=CONFIG["request_timeout"] * 1000)
            await page.wait_for_timeout(1500)
            html = await page.content()
            await page.close()
            return html
        finally:
            await browser.close()

    async def get_chapters(self, url: str, retries: int = None):
        """Fetch title/thumb/referer/chapters via scraper.py (requests).

        If requests finds no chapters (JS-rendered page), fall back to
        Playwright headless rendering and scrape again on the rendered HTML.

        Runs in an executor because the scraper is synchronous (requests +
        BeautifulSoup), so it does not block the event loop (qasync shares the
        same loop as the GUI).
        """
        retries = retries if retries is not None else CONFIG["chapter_retry"]
        loop = asyncio.get_running_loop()
        last_error = None

        for attempt in range(retries + 1):
            try:
                data = await loop.run_in_executor(None, scrape, url)
                if data.get("chapters"):
                    return data
                # JS-rendered site: retry with Playwright
                html = await self._render_html(url)
                rendered = await loop.run_in_executor(None, scrape_from_html, html, url)
                if rendered.get("chapters"):
                    rendered.setdefault("referer", data.get("referer") or "")
                    return rendered
                return data
            except Exception as e:
                last_error = e
                logger.error(f"[get_chapters] Attempt {attempt + 1} failed: {e}")
                if attempt < retries:
                    await asyncio.sleep(0.5)
        raise last_error

    async def extract_images(self, url: str) -> List[str]:
        if self._http_session is None:
            raise RuntimeError("HTTP session not set. Call crawler.set_http_session(session) first.")

        async with self._http_session.get(url, timeout=CONFIG["request_timeout"]) as resp:
            html = await resp.text()

        loop = asyncio.get_running_loop()
        raw_srcs = await loop.run_in_executor(None, find_chapter_images, html, url)
        urls = [resolve_ddg_proxy(src) for src in raw_srcs]

        # If the page renders images with JS, the HTML fetched via aiohttp only
        # shows placeholders (transparent/loading...) -> fall back to Playwright
        # rendering and re-extract.
        if not _has_real_images(urls):
            try:
                rendered_html = await self._render_html(url)
                rendered = await loop.run_in_executor(
                    None, find_chapter_images, rendered_html, url
                )
                if _has_real_images(rendered):
                    urls = [resolve_ddg_proxy(src) for src in rendered]
            except Exception as e:
                logger.error(f"[extract_images] Playwright fallback failed for {url}: {e}")

        return urls

    async def close(self):
        """Stop the Playwright context if it was opened (JS-render fallback)."""
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception as e:
                logger.error(f"[close] Failed to stop Playwright: {e}")
            self._pw = None
