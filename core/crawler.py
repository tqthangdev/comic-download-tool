import asyncio
from functools import partial
from typing import List, Optional
from urllib.parse import urlparse

from core.scraper import (
    scrape,
    scrape_from_html,
    find_chapter_images,
    BotProtectionError,
)
from core.utils import resolve_ddg_proxy, CONFIG
from core.logger import logger
from core.auth import auth_manager
from core import stealth

# Placeholder URLs (unrendered / lazy images) — not real content
PLACEHOLDER_PARTS = ("transparent", "placeholder", "loading", "spacer", "/assets/img/")

# Chapter pages whose images are injected by a JS reader (lazy loaders, canvas
# readers) ship a marker container and build the pages after the page runs.
JS_READER_MARKERS = ("data-cipher-path", "chapter-img", "reader-root")


def _has_real_images(urls: List[str]) -> bool:
    """Return True if at least one URL is not a placeholder."""
    return any(
        not any(p in u.lower() for p in PLACEHOLDER_PARTS)
        for u in urls
    )


def _images_are_page_chrome(html: str, urls: List[str], base_url: str) -> bool:
    """True when the scraped images are the page's own furniture (logo, ads...)
    rather than the chapter's pages.

    A page that builds its images with JS leaves a reader container behind while
    serving the real pages from a CDN, so whatever the raw HTML does contain is
    served by the page's own host.
    """
    if not html or not urls:
        return False

    if not any(marker in html for marker in JS_READER_MARKERS):
        return False

    host = urlparse(base_url).netloc.lower()
    return all(urlparse(u).netloc.lower() == host for u in urls)


# Clicks every "load more" control tied to a chapter list, so a site that only
# renders the newest slice of chapters (e.g. nettruyen's hidden "Xem thêm")
# reveals the full list in the rendered DOM.
_CLICK_LOAD_MORE_JS = """
() => {
    const rx = /(view|load|see)[-_]?more|xem[-_]?them|loadmore/i;
    let clicked = 0;
    for (const el of document.querySelectorAll('a, button, span, div')) {
        const ident = (el.id || '') + ' ' + (el.className || '');
        if (rx.test(ident)) {
            try { el.click(); clicked++; } catch (e) {}
        }
    }
    return clicked;
}
"""


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

    async def _render_html(
        self,
        url: str,
        site_id: Optional[str] = None,
        expand_chapters: bool = False,
    ) -> str:
        """Render a URL with Playwright headless, returning the JS-executed HTML.

        If site_id is given, the authenticated cookies/headers from
        auth_manager are applied to the browser context before navigating,
        so JS-rendered pages that require login work too.

        expand_chapters: click chapter 'load more' controls after load so a
        partially rendered chapter list is expanded to the full one.
        """
        from playwright.async_api import async_playwright

        if self._pw is None:
            self._pw = await async_playwright().start()
        browser = await self._pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context()

            if site_id:
                cookies = auth_manager.get_cookies(site_id)
                if cookies:
                    domain = urlparse(url).netloc
                    await context.add_cookies([
                        {"name": name, "value": value, "domain": domain, "path": "/"}
                        for name, value in cookies.items()
                    ])
                headers = auth_manager.get_headers(site_id)
                if headers:
                    await context.set_extra_http_headers(headers)

            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=CONFIG["request_timeout"] * 1000)
            await page.wait_for_timeout(1500)
            if expand_chapters:
                await self._expand_chapters(page)
            html = await page.content()
            await page.close()
            return html
        finally:
            await browser.close()

    async def _expand_chapters(self, page):
        """Click chapter 'load more' controls until they stop growing the DOM."""
        count_js = "document.querySelectorAll('a').length"
        try:
            previous = await page.evaluate(count_js)
        except Exception:
            previous = 0
        for _ in range(6):
            clicked = await page.evaluate(_CLICK_LOAD_MORE_JS)
            if not clicked:
                break
            await page.wait_for_timeout(2000)
            try:
                current = await page.evaluate(count_js)
            except Exception:
                break
            if current <= previous:
                break
            previous = current

    async def get_chapters(self, url: str, retries: int = None, site_id: Optional[str] = None):
        """Fetch title/thumb/referer/chapters via scraper.py (requests).

        If requests finds no chapters (JS-rendered page) OR finds only a slice
        of them (a 'load more' chapter control is present), fall back to
        Playwright headless rendering (expanding the chapter list) and scrape
        again on the rendered HTML.

        site_id: pass through to both the requests-based scrape() call and
        the Playwright fallback so login cookies/headers are applied either
        way — the site is seen as logged-in whether or not it needs JS.

        Runs in an executor because the scraper is synchronous (requests +
        BeautifulSoup), so it does not block the event loop (qasync shares the
        same loop as the GUI).
        """
        retries = retries if retries is not None else CONFIG["chapter_retry"]
        loop = asyncio.get_running_loop()
        last_error = None

        cookies = auth_manager.get_cookies(site_id) if site_id else None
        extra_headers = auth_manager.get_headers(site_id) if site_id else None
        scrape_call = partial(scrape, url, cookies=cookies, extra_headers=extra_headers)

        for attempt in range(retries + 1):
            try:
                data = await loop.run_in_executor(None, scrape_call)
                chapters = data.get("chapters") or []

                # Complete list already: nothing to render.
                if chapters and not data.get("has_more_chapters"):
                    return data

                # No chapters (JS-rendered) or a truncated list behind a
                # "load more" control -> render and scrape the expanded DOM.
                html = await self._render_html(
                    url, site_id=site_id, expand_chapters=True
                )
                rendered = await loop.run_in_executor(None, scrape_from_html, html, url)
                rendered_chapters = rendered.get("chapters") or []

                best = rendered if len(rendered_chapters) > len(chapters) else data
                if best.get("chapters"):
                    best.setdefault("referer", data.get("referer") or "")
                return best
            except BotProtectionError:
                # The site refuses plain HTTP clients; the only way in is a real,
                # non-automated browser (nodriver) that can clear the challenge.
                if not stealth.is_available():
                    raise
                logger.info(f"[get_chapters] Cloudflare detected, trying stealth fallback: {url}")
                try:
                    html = await stealth.fetch_html(url)
                except Exception as e:
                    logger.error(f"[get_chapters] Stealth fallback failed for {url}: {e}")
                    raise
                rendered = await loop.run_in_executor(None, scrape_from_html, html, url)
                if rendered.get("chapters"):
                    return rendered
                raise
            except Exception as e:
                last_error = e
                logger.error(f"[get_chapters] Attempt {attempt + 1} failed: {e}")
                if attempt < retries:
                    await asyncio.sleep(0.5)
        raise last_error

    async def extract_images(self, url: str, site_id: Optional[str] = None) -> List[str]:
        from core import nhentai

        # nhentai serves a gallery's pages from its JSON API, not from the
        # chapter HTML, so bypass the heuristics for its URLs.
        if nhentai.is_nhentai_url(url):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, nhentai.fetch_pages, url)

        if self._http_session is None:
            raise RuntimeError("HTTP session not set. Call crawler.set_http_session(session) first.")

        cookies = dict(auth_manager.get_cookies(site_id) or {}) if site_id else {}
        headers = auth_manager.get_headers(site_id) if site_id else None

        # A challenge clearance is bound to the UA that earned it, so replay both
        # the captured User-Agent and its cookies for this host.
        clearance_headers = stealth.headers_for(url)
        if clearance_headers:
            headers = {**(headers or {}), **clearance_headers}
            cookies.update(stealth.cookies_for(url))

        async with self._http_session.get(
            url,
            timeout=CONFIG["request_timeout"],
            cookies=cookies or None,
            headers=headers,
        ) as resp:
            html = await resp.text()

        loop = asyncio.get_running_loop()
        raw_srcs = await loop.run_in_executor(None, find_chapter_images, html, url)
        urls = [resolve_ddg_proxy(src) for src in raw_srcs]

        # If the page renders images with JS, the HTML fetched via aiohttp only
        # shows placeholders (transparent/loading...) — or, on a JS reader, just
        # the page's own logo/ads — so fall back to Playwright rendering.
        if not _has_real_images(urls) or _images_are_page_chrome(html, urls, url):
            try:
                rendered_html = await self._render_html(url, site_id=site_id)
                rendered = await loop.run_in_executor(
                    None, find_chapter_images, rendered_html, url
                )
                if _has_real_images(rendered):
                    urls = [resolve_ddg_proxy(src) for src in rendered]
            except Exception as e:
                logger.error(f"[extract_images] Playwright fallback failed for {url}: {e}")

            # Still nothing real -> Playwright itself is being fingerprinted
            # and refused (Cloudflare). Try nodriver stealth as a last resort.
            if not _has_real_images(urls) and stealth.is_available():
                try:
                    stealth_html = await stealth.fetch_html(url)
                    stealth_urls = await loop.run_in_executor(
                        None, find_chapter_images, stealth_html, url
                    )
                    if _has_real_images(stealth_urls):
                        urls = [resolve_ddg_proxy(src) for src in stealth_urls]
                except Exception as e:
                    logger.error(f"[extract_images] Stealth fallback failed for {url}: {e}")

        return urls

    async def close(self):
        """Stop the Playwright context if it was opened (JS-render fallback)."""
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception as e:
                logger.error(f"[close] Failed to stop Playwright: {e}")
            self._pw = None

        from core import cuutruyen

        await cuutruyen.close_renderer()
