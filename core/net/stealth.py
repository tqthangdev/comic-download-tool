"""
core/stealth.py — nodriver fallback, used ONLY when Cloudflare blocks the normal path.

Rules:
  * It does not change the existing flow. scraper/crawler/downloader behave exactly
    as before; this module is only called once `BotProtectionError` has been raised.
  * nodriver runs on its own thread with its own event loop (qasync + subprocess is
    fragile on Windows), and results are bridged back to the Qt loop via
    asyncio.wrap_future.
  * After the challenge is cleared, the cookies (cf_clearance) and the User-Agent
    are cached per domain so aiohttp can reuse them — no browser per image.
    NOTE: cf_clearance is bound to the IP *and* the User-Agent, so the exact UA that
    solved the challenge must be replayed or the cookie is rejected immediately.

Install:  pip install nodriver
"""

from __future__ import annotations

import asyncio
import os
import platform
import threading
import time
from dataclasses import dataclass, field
from glob import glob
from typing import Dict, Optional
from urllib.parse import urlparse

from core.logger import logger
from core.utils import BASE_DIR, CONFIG

try:
    import nodriver as uc
except ImportError:  # nodriver is an optional dependency
    uc = None


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def _cfg(key: str, default):
    return CONFIG.get(key, default)


# Markers of a page that is still on the challenge screen (not cleared yet)
_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "challenge-platform",
    "cf_chl_opt",
    "attention required",
    "checking your browser",
    "verify you are human",
)

_CLEARANCE_TTL = 30 * 60  # seconds; cf_clearance usually lives longer, this is conservative


class StealthUnavailable(RuntimeError):
    """nodriver is not installed, or no Chrome/Chromium was found."""


@dataclass
class Clearance:
    cookies: Dict[str, str] = field(default_factory=dict)
    user_agent: str = ""
    created: float = field(default_factory=time.time)

    @property
    def expired(self) -> bool:
        return time.time() - self.created > _CLEARANCE_TTL

    def as_headers(self) -> Dict[str, str]:
        """Headers to attach to aiohttp/requests for this clearance.

        Only the User-Agent: the cookies must go through the client's own cookie
        jar (aiohttp `cookies=` / requests `cookies=`), because a hand-built
        `Cookie` header collides with it.
        """
        if self.user_agent:
            return {"User-Agent": self.user_agent}
        return {}


# --------------------------------------------------------------------------- #
# Locate a Chrome/Chromium binary
# --------------------------------------------------------------------------- #

def _find_browser() -> Optional[str]:
    """Prefer real Chrome (better fingerprint), fall back to Playwright's Chromium."""
    explicit = _cfg("stealth_browser_path", "")
    if explicit and os.path.exists(explicit):
        return explicit

    system = platform.system()
    candidates = []
    if system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
    for c in candidates:
        if c and os.path.exists(c):
            return c

    # Fallback: the portable Chromium Playwright already downloaded (ms-playwright/).
    # The folder is chrome-linux64/chrome-win64 on newer builds but chrome-linux/
    # chrome-win on older ones, so try both layouts.
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), str(BASE_DIR / "ms-playwright")]
    layouts = {
        "Windows": (
            "chromium-*/chrome-win64/chrome.exe",
            "chromium-*/chrome-win/chrome.exe",
        ),
        "Darwin": (
            "chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        ),
    }
    patterns = layouts.get(system, (
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-linux/chrome",
    ))
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for pattern in patterns:
            hits = sorted(glob(os.path.join(root, pattern)))
            if hits:
                return hits[-1]
    return None


# --------------------------------------------------------------------------- #
# Runner: its own event loop on its own thread
# --------------------------------------------------------------------------- #

class _Runner:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._guard = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._guard:
            if self._loop and self._thread and self._thread.is_alive():
                return self._loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=self._serve, args=(loop,), name="stealth-loop", daemon=True
            )
            thread.start()
            self._loop, self._thread = loop, thread
            return loop

    @staticmethod
    def _serve(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    async def call(self, coro):
        """Run a coroutine on the stealth loop, awaited from the Qt loop."""
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return await asyncio.wrap_future(fut)

    def shutdown(self) -> None:
        with self._guard:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = self._thread = None


_runner = _Runner()


# --------------------------------------------------------------------------- #
# Browser singleton (lives on the stealth loop)
# --------------------------------------------------------------------------- #

_browser = None
_browser_lock: Optional[asyncio.Lock] = None
_domain_locks: Dict[str, asyncio.Lock] = {}
_clearances: Dict[str, Clearance] = {}


def _lock_for(domain: str) -> asyncio.Lock:
    """Two jobs on the same domain should not open a challenge at the same time."""
    lock = _domain_locks.get(domain)
    if lock is None:
        lock = _domain_locks[domain] = asyncio.Lock()
    return lock


async def _get_browser():
    global _browser, _browser_lock
    if _browser_lock is None:
        _browser_lock = asyncio.Lock()
    async with _browser_lock:
        if _browser is not None:
            return _browser
        if uc is None:
            raise StealthUnavailable("nodriver is not installed (pip install nodriver)")
        exe = _find_browser()
        if not exe:
            raise StealthUnavailable("No Chrome/Chromium found on this machine")

        args = [
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1280,900",
        ]

        if bool(_cfg("stealth_hide_window", True)):
            args.append("--window-position=-32000,-32000")

        # headless=False clears the challenge far more reliably; let the user turn it off.
        headless = bool(_cfg("stealth_headless", False))
        profile = str(BASE_DIR / "data" / "stealth_profile")
        os.makedirs(profile, exist_ok=True)

        logger.info("stealth: starting nodriver (%s, headless=%s)", exe, headless)
        _browser = await uc.start(
            headless=headless,
            browser_executable_path=exe,
            browser_args=args,
            user_data_dir=profile,  # keep cookies between runs
        )
        return _browser


def _cookie_domain_matches(cookie_domain: str, domain: str) -> bool:
    """True when a cookie's domain applies to `domain` (same host or a parent of it)."""
    cd = (cookie_domain or "").lstrip(".").lower()
    host = domain.lower()
    return bool(cd) and (host == cd or host.endswith("." + cd))


async def _harvest(browser, domain: str) -> Clearance:
    cookies: Dict[str, str] = {}
    try:
        for c in await browser.cookies.get_all():
            if _cookie_domain_matches(getattr(c, "domain", ""), domain):
                cookies[c.name] = c.value
    except Exception as exc:  # the cookie API differs between nodriver versions
        logger.warning("stealth: could not read cookies: %s", exc)
    return Clearance(cookies=cookies, user_agent=_LAST_UA.get(domain, ""))


_LAST_UA: Dict[str, str] = {}


async def _fetch(url: str, wait_selector: Optional[str] = None) -> str:
    """Open a URL with nodriver, wait out the challenge, return the rendered HTML."""
    domain = urlparse(url).netloc
    timeout = float(_cfg("stealth_timeout", 45))

    async with _lock_for(domain):
        browser = await _get_browser()
        page = await browser.get(url)
        deadline = time.time() + timeout
        html = ""

        while time.time() < deadline:
            await asyncio.sleep(1.5)
            try:
                html = await page.get_content()
            except Exception:
                continue
            low = html.lower()
            if not any(m in low for m in _CHALLENGE_MARKERS) and len(html) > 2000:
                break

        # The browser's real UA -> aiohttp must replay exactly this one
        try:
            ua = await page.evaluate("navigator.userAgent")
            if isinstance(ua, str) and ua:
                _LAST_UA[domain] = ua
        except Exception:
            pass

        if wait_selector:
            try:
                await page.select(wait_selector, timeout=5)
                html = await page.get_content()
            except Exception:
                pass

        _clearances[domain] = await _harvest(browser, domain)

        try:
            await page.close()
        except Exception:
            pass

        low = html.lower()
        if any(m in low for m in _CHALLENGE_MARKERS):
            raise TimeoutError("stealth: challenge not cleared within %.0fs" % timeout)
        return html


async def _close() -> None:
    global _browser
    if _browser is not None:
        try:
            _browser.stop()
        except Exception:
            pass
        _browser = None


# --------------------------------------------------------------------------- #
# Public API — called from the Qt loop
# --------------------------------------------------------------------------- #

def is_enabled() -> bool:
    return bool(_cfg("stealth_enabled", True)) and uc is not None


def is_available() -> bool:
    return is_enabled() and _find_browser() is not None


async def fetch_html(url: str, wait_selector: Optional[str] = None) -> str:
    """Fetch the HTML of a Cloudflare-blocked page. Raises StealthUnavailable/TimeoutError."""
    if not is_enabled():
        raise StealthUnavailable("stealth is disabled or nodriver is not installed")
    return await _runner.call(_fetch(url, wait_selector))


def clearance_for(url: str) -> Optional[Clearance]:
    """Cookies + UA captured for this domain, if still valid."""
    c = _clearances.get(urlparse(url).netloc)
    if c and not c.expired and c.cookies:
        return c
    return None


def headers_for(url: str) -> Dict[str, str]:
    """Headers to attach to aiohttp/requests ({} if no clearance yet)."""
    c = clearance_for(url)
    return c.as_headers() if c else {}


def cookies_for(url: str) -> Dict[str, str]:
    """Clearance cookies for the domain ({} if none/already expired)."""
    c = clearance_for(url)
    return dict(c.cookies) if c else {}


async def shutdown() -> None:
    """Called when the app exits (MainWindow.closeEvent)."""
    if uc is None:
        return
    try:
        await _runner.call(_close())
    except Exception:
        pass
    _runner.shutdown()