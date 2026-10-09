"""Choose which backend handles a URL.

Priority: a per-domain ``engine_overrides`` entry wins, then ``engine_default``,
and — when ``engine_fallback`` is on — the other backend is offered as a second
choice (exactly once, see ``Engine._download_with_fallback``).
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

from core.engines.base import BOT_PROTECTED
from core.utils import CONFIG

NATIVE = "native"
GALLERYDL = "gallerydl"


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def configured_engine(url: str) -> str:
    """The engine chosen by config for this URL (before availability checks)."""
    domain = domain_of(url)
    for key, engine in (CONFIG.get("engine_overrides") or {}).items():
        override = str(key).lower().lstrip(".")
        if domain == override or domain.endswith("." + override):
            return engine
    return CONFIG.get("engine_default", NATIVE)


def candidates(url: str, available: Iterable[str], preferred: str = None) -> list:
    """Ordered backend names to try for ``url`` (primary first).

    ``preferred`` (a GUI override or the engine a job was previewed with) wins
    over the configured default; fallback to the other backend is still offered
    when ``engine_fallback`` is on.
    """
    available = list(available)
    if not available:
        return []

    primary = preferred or configured_engine(url)
    if primary not in available:
        primary = NATIVE if NATIVE in available else available[0]

    order = [primary]
    if CONFIG.get("engine_fallback", True):
        for name in (NATIVE, GALLERYDL):
            if name != primary and name in available:
                order.append(name)
    return order


def fallback_allowed(error_code: str, from_engine: str) -> bool:
    """Whether a failed job should be retried on the other backend.

    gallery-dl cannot reliably clear a Cloudflare managed challenge, so a native
    job that hit a bot wall is not retried on it (see the plan's fallback matrix).
    """
    if not CONFIG.get("engine_fallback", True):
        return False
    if from_engine == NATIVE and error_code == BOT_PROTECTED:
        return False
    return True
