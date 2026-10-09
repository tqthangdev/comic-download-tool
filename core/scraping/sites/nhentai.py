"""nhentai.net galleries.

nhentai is a gallery site: a work is a single gallery of images with no chapter
list, and the reader is a JS SPA. The site exposes a documented public JSON API
(https://nhentai.net/api/v2/docs) that returns the gallery metadata plus every
page's path, so the app contract is built straight from it instead of scraping
the HTML.

A gallery maps to a single "chapter" whose URL is the gallery page; the chapter's
images are the gallery's pages, served from the image CDN
(``<image_server>/<page.path>``).
"""

from __future__ import annotations

import re
import sys
from typing import Optional
from urllib.parse import urlparse

import requests

from core.logger import logger
from core.utils import CONFIG

HOST = "nhentai.net"
API = f"https://{HOST}/api/v2"

_HEADERS = {
    "User-Agent": CONFIG["user_agent"],
    "Referer": f"https://{HOST}/",
}

# Used when /api/v2/cdn cannot be read; the pools are stable and interchangeable.
_DEFAULT_IMAGE_SERVERS = [f"https://i{n}.{HOST}" for n in range(1, 5)]
_DEFAULT_THUMB_SERVERS = [f"https://t{n}.{HOST}" for n in range(1, 5)]

_cdn_cache: Optional[dict] = None


def is_nhentai_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == HOST or host.endswith("." + HOST)


def gallery_id_from_url(url: str) -> Optional[str]:
    """The numeric gallery id from /g/<id> (also matches /g/<id>/<page>/)."""
    match = re.search(r"/g/(\d+)", url or "")
    return match.group(1) if match else None


def _cdn() -> dict:
    """The image/thumb server pools, cached for the process."""
    global _cdn_cache
    if _cdn_cache is not None:
        return _cdn_cache

    image_servers, thumb_servers = [], []
    try:
        resp = requests.get(
            f"{API}/cdn", headers=_HEADERS, timeout=CONFIG["request_timeout"]
        )
        resp.raise_for_status()
        data = resp.json()
        image_servers = data.get("image_servers") or []
        thumb_servers = data.get("thumb_servers") or []
    except Exception as e:
        logger.warning(f"[nhentai] CDN config unavailable, using defaults: {e}")

    _cdn_cache = {
        "image_servers": image_servers or _DEFAULT_IMAGE_SERVERS,
        "thumb_servers": thumb_servers or _DEFAULT_THUMB_SERVERS,
    }
    return _cdn_cache


def fetch_gallery(gallery_id, cookies=None, extra_headers=None) -> dict:
    """The gallery's metadata and page list, straight from the API."""
    headers = dict(_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    resp = requests.get(
        f"{API}/galleries/{gallery_id}",
        headers=headers,
        cookies=cookies,
        timeout=CONFIG["request_timeout"],
    )
    resp.raise_for_status()
    return resp.json()


def _page_urls(gallery: dict) -> list:
    base = _cdn()["image_servers"][0]
    return [
        f"{base}/{page['path']}"
        for page in (gallery.get("pages") or [])
        if page.get("path")
    ]


def _title(gallery: dict) -> str:
    title = gallery.get("title") or {}
    return (
        title.get("pretty") or title.get("english") or title.get("japanese") or ""
    ).strip()


def fetch_pages(gallery_url: str, cookies=None, extra_headers=None) -> list:
    """Every page's full-size image URL for the gallery (used by the downloader)."""
    gallery_id = gallery_id_from_url(gallery_url)
    if not gallery_id:
        raise ValueError(f"Not an nhentai gallery URL: {gallery_url}")
    return _page_urls(fetch_gallery(gallery_id, cookies, extra_headers))


def scrape(url, cookies=None, extra_headers=None, debug=False) -> dict:
    """Build the app contract for a gallery URL.

    The whole gallery is exposed as a single chapter (nhentai has no chapter
    list); the chapter's images come from ``fetch_pages``.
    """
    gallery_id = gallery_id_from_url(url)
    if not gallery_id:
        raise ValueError(f"Not an nhentai gallery URL: {url}")

    gallery = fetch_gallery(gallery_id, cookies=cookies, extra_headers=extra_headers)
    cdn = _cdn()

    cover = (gallery.get("cover") or {}).get("path") or ""
    thumb = f"{cdn['thumb_servers'][0]}/{cover}" if cover else ""
    title = _title(gallery)

    genres = [
        {
            "name": tag.get("name") or "",
            "slug": tag.get("slug") or "",
            "url": tag.get("url") or "",
        }
        for tag in (gallery.get("tags") or [])
    ]

    if debug:
        pages = gallery.get("pages") or []
        print(
            f"[debug] nhentai gallery {gallery_id}: {len(pages)} pages",
            file=sys.stderr,
        )

    return {
        "title": title,
        "thumb": thumb,
        "referer": f"https://{HOST}/",
        "genres": genres,
        "has_more_chapters": False,
        "chapters": [
            {
                "title": title or "Gallery",
                "url": f"https://{HOST}/g/{gallery_id}/",
                "update_time": "",
            }
        ],
    }
