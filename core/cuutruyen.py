"""cuutruyen.net chapter images.

The reader is a JS SPA and every manga page is DRM-protected: the served file is
a ``scrambled-*.jpg`` (horizontal strips in shuffled order) plus a per-page
``drm_data`` blob, so the raw files are unusable. The site descrambles them in
the browser with a wasm-bindgen module (``render_image``) that draws the fixed
image onto a canvas.

We reuse that exact module headlessly: load the site's glue chunk + wasm,
instantiate them, and call ``render_image(image, ctx2d, drm_data)`` for each
page, then export the canvas as JPEG. The scrambled files are fetched into the
page as same-origin blobs so the canvas stays exportable (no cross-origin taint).
"""

from __future__ import annotations

import asyncio
import base64
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from core.logger import logger
from core.utils import CONFIG

HOST = "cuutruyen.net"
API = f"https://{HOST}/api/v2"
# API media lives on storage-<x>.lrclib.net, but some of those hosts are dead
# (e.g. storage-ct no longer resolves). The SPA rewrites them to a live mirror.
LIVE_MEDIA_HOST = "storage-bravo.cuutruyen.net"

_REQ_HEADERS = {
    "User-Agent": CONFIG["user_agent"],
    "Referer": f"https://{HOST}/",
}

# wasm-bindgen glue, run inside the browser page. The glue chunk registers its
# modules through the webpack chunk global, so a fake `push` captures them.
_HARNESS_JS = r"""
window.__cudrm_init = async function (data) {
  let mods = null;
  const previous = globalThis["webpackChunkmanga4u_app"];
  globalThis["webpackChunkmanga4u_app"] = { push: (arr) => { mods = arr[1]; } };
  try { (0, eval)(data.chunkSrc); } finally { globalThis["webpackChunkmanga4u_app"] = previous; }
  if (!mods) throw new Error("cuudrm: no webpack modules captured");
  let factory = null;
  for (const id in mods) {
    try { if (typeof mods[id] === "function" && /render_image/.test(mods[id].toString())) { factory = mods[id]; break; } } catch (e) {}
  }
  if (!factory) throw new Error("cuudrm: glue module not found");
  const n = {};
  const req = () => ({});
  req.d = (target, defs) => { for (const k in defs) Object.defineProperty(target, k, { get: defs[k], enumerable: true, configurable: true }); };
  req.hmd = (t) => t;
  req.g = globalThis;
  factory({ exports: {} }, n, req);
  const imports = {};
  for (const k in data.importMap) {
    const fn = n[data.importMap[k]];
    if (typeof fn !== "function") throw new Error("cuudrm: missing glue fn " + data.importMap[k]);
    imports[k] = fn;
  }
  const wasmBytes = Uint8Array.from(atob(data.wasmB64), c => c.charCodeAt(0));
  const { instance } = await WebAssembly.instantiate(wasmBytes.buffer, { "./cuudrm_bg.js": imports });
  // The exported setter (e.g. `function i(t){r=t}`) receives the wasm instance.
  let setter = null;
  for (const k of Object.keys(n)) {
    let fn;
    try { fn = n[k]; } catch (e) { continue; }
    if (typeof fn !== "function") continue;
    const src = Function.prototype.toString.call(fn).replace(/\s+/g, "");
    if (/^function[A-Za-z0-9_$]*\([A-Za-z0-9_$]*\)\{[A-Za-z0-9_$]*=[A-Za-z0-9_$]*\}$/.test(src)) { setter = fn; break; }
  }
  if (!setter) throw new Error("cuudrm: instance setter export not found");
  setter(instance.exports);
  window.__cudrm = n;
  return true;
};

window.__cudrm_render = async function (p) {
  const G = window.__cudrm;
  const bytes = Uint8Array.from(atob(p.imageB64), c => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "image/jpeg" }));
  try {
    const img = new Image();
    img.src = url;
    if (img.decode) {
      await img.decode();
    } else {
      await new Promise((res, rej) => { img.onload = res; img.onerror = () => rej(new Error("cuudrm: image load failed")); });
    }
    const canvas = document.createElement("canvas");
    canvas.width = p.width;
    canvas.height = p.height;
    const ctx = canvas.getContext("2d");
    G.lv(img, ctx, p.drmData);
    return canvas.toDataURL("image/jpeg", 0.92);
  } finally {
    URL.revokeObjectURL(url);
  }
};
"""


def is_cuutruyen_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == HOST or host.endswith("." + HOST)


def _live_media(url: str) -> str:
    if url and urlparse(url).netloc.endswith("lrclib.net"):
        return re.sub(r"https?://[^/]+", f"https://{LIVE_MEDIA_HOST}", url)
    return url


def chapter_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/chapters/(\d+)", url or "")
    return match.group(1) if match else None


def fetch_pages(chapter_url: str, timeout: int = None) -> list:
    """Return the chapter's pages: [{image_url, drm_data, width, height}]."""
    chapter_id = chapter_id_from_url(chapter_url)
    if not chapter_id:
        raise ValueError(f"Not a cuutruyen chapter URL: {chapter_url}")

    resp = requests.get(
        f"{API}/chapters/{chapter_id}",
        headers=_REQ_HEADERS,
        timeout=timeout or CONFIG["request_timeout"],
    )
    resp.raise_for_status()
    data = resp.json().get("data") or {}

    return [
        {
            "image_url": _live_media(p.get("image_url") or ""),
            "drm_data": p.get("drm_data") or "",
            "width": p.get("width") or 0,
            "height": p.get("height") or 0,
        }
        for p in (data.get("pages") or [])
    ]


# ----------------------------------------------------------------------
# Discovery of the glue chunk + wasm (hashed filenames change on rebuild)
# ----------------------------------------------------------------------

_discovery = None


def _chunk_map(app_js: str) -> dict:
    match = re.search(r'\.u=\w+=>"js/"\+\w+\+"\."\+(\{[^}]*\})\[\w+\]', app_js)
    if not match:
        raise RuntimeError("cuutruyen: webpack chunk map not found")
    return dict(re.findall(r'(\d+):"([0-9a-f]+)"', match.group(1)))


def _discover() -> dict:
    """Locate the glue chunk (the one exporting render_image) and its wasm."""
    global _discovery
    if _discovery is not None:
        return _discovery

    index = requests.get(f"https://{HOST}/", headers=_REQ_HEADERS, timeout=20).text
    app_match = re.search(r'src="(/js/app\.[0-9a-f]+\.js)"', index)
    if not app_match:
        raise RuntimeError("cuutruyen: app.js not found")
    app_js = requests.get(f"https://{HOST}{app_match.group(1)}", headers=_REQ_HEADERS, timeout=30).text
    chunks = _chunk_map(app_js)

    def fetch_chunk(item):
        cid, chash = item
        try:
            text = requests.get(
                f"https://{HOST}/js/{cid}.{chash}.js", headers=_REQ_HEADERS, timeout=30
            ).text
        except requests.RequestException:
            return None
        return text if "render_image" in text else None

    found = None
    with ThreadPoolExecutor(max_workers=16) as pool:
        for src in pool.map(fetch_chunk, chunks.items()):
            if src:
                found = src
                break
    if not found:
        raise RuntimeError("cuutruyen: DRM glue chunk not found")

    import_section = re.search(r'"\./cuudrm_bg\.js":\{(.*?)\}\}', found, re.S)
    if not import_section:
        raise RuntimeError("cuutruyen: glue import map not found")
    import_map = dict(
        re.findall(r'([A-Za-z0-9_]+):\s*r\.([A-Za-z0-9_$]+)', import_section.group(1))
    )

    wasm_name = re.search(r'"([0-9a-f]{16})"', found)
    if not wasm_name:
        raise RuntimeError("cuutruyen: wasm module name not found")
    wasm = requests.get(
        f"https://{HOST}/{wasm_name.group(1)}.module.wasm", headers=_REQ_HEADERS, timeout=30
    ).content

    _discovery = {
        "chunk_src": found,
        "import_map": import_map,
        "wasm_b64": base64.b64encode(wasm).decode(),
    }
    logger.info(
        f"[cuutruyen] DRM module discovered ({len(import_map)} imports, "
        f"wasm {len(wasm)} bytes)"
    )
    return _discovery


# ----------------------------------------------------------------------
# Browser renderer (kept alive and reused across chapters)
# ----------------------------------------------------------------------

class _Renderer:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._data = None

    async def start(self):
        from playwright.async_api import async_playwright

        loop = asyncio.get_running_loop()
        self._data = await loop.run_in_executor(None, _discover)

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        page = await self._context.new_page()
        # Re-inject the harness on every navigation, so it survives a reload.
        await page.add_init_script(_HARNESS_JS)
        # The page must be on the cuutruyen origin: its sessionStorage holds a
        # per-session key the DRM wasm reads, and blob images stay same-origin
        # (so the canvas is exportable).
        await page.goto(
            f"https://{HOST}/",
            wait_until="domcontentloaded",
            timeout=max(CONFIG["request_timeout"], 45) * 1000,
        )
        for _ in range(30):
            try:
                if await page.evaluate(
                    "() => { try { return sessionStorage.length; } catch (e) { return 0; } }"
                ):
                    break
            except Exception:
                pass
            await page.wait_for_timeout(500)
        self._page = page
        await self._setup()

    async def _setup(self):
        """(Re)initialise the wasm module in the current document."""
        await self._page.evaluate(
            "d => window.__cudrm_init(d)",
            {
                "chunkSrc": self._data["chunk_src"],
                "importMap": self._data["import_map"],
                "wasmB64": self._data["wasm_b64"],
            },
        )

    async def _ensure_ready(self):
        """Re-init the wasm if the page navigated and lost it."""
        ready = await self._page.evaluate(
            "() => !!(window.__cudrm && typeof window.__cudrm.lv === 'function')"
        )
        if not ready:
            await self._setup()

    async def render(self, page_info: dict) -> bytes:
        loop = asyncio.get_running_loop()
        img = await loop.run_in_executor(None, self._fetch_image, page_info["image_url"])
        payload = {
            "imageB64": base64.b64encode(img).decode(),
            "drmData": page_info["drm_data"],
            "width": page_info["width"],
            "height": page_info["height"],
        }
        await self._ensure_ready()
        try:
            data_url = await self._page.evaluate("p => window.__cudrm_render(p)", payload)
        except Exception as e:
            # The page navigated while downloading -> re-init and retry once.
            if "__cudrm" not in str(e):
                raise
            await self._setup()
            data_url = await self._page.evaluate("p => window.__cudrm_render(p)", payload)
        return base64.b64decode(data_url.split(",", 1)[1])

    @staticmethod
    def _fetch_image(url: str) -> bytes:
        resp = requests.get(url, headers=_REQ_HEADERS, timeout=CONFIG["request_timeout"])
        resp.raise_for_status()
        return resp.content

    async def close(self):
        for obj in (self._browser, self._pw):
            try:
                if obj is self._browser and obj is not None:
                    await obj.close()
                elif obj is not None:
                    await obj.stop()
            except Exception:
                pass
        self._pw = self._browser = self._page = None


_renderer: Optional[_Renderer] = None
_renderer_lock = asyncio.Lock()


async def _get_renderer() -> _Renderer:
    global _renderer
    async with _renderer_lock:
        if _renderer is None:
            renderer = _Renderer()
            await renderer.start()
            _renderer = renderer
        return _renderer


async def close_renderer():
    global _renderer
    if _renderer is not None:
        await _renderer.close()
        _renderer = None


async def render_pages(pages: list, out_dir: Path, progress=None):
    """Render every page to ``<out_dir>/NNNN.jpg``.

    Returns (failed_urls, missing_urls) like Downloader.download_batch.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = await _get_renderer()

    total = len(pages)
    failed, missing = [], []
    for index, page_info in enumerate(pages):
        stem = out_dir / f"{index:04d}"
        if list(out_dir.glob(f"{stem.name}.*")):
            if progress:
                progress(index + 1, total)
            continue

        ok = False
        for attempt in range(CONFIG["download_retry"]):
            try:
                data = await renderer.render(page_info)
                (out_dir / f"{stem.name}.jpg").write_bytes(data)
                ok = True
                break
            except requests.HTTPError as e:
                status = getattr(e.response, "status_code", None)
                if status == 404:
                    missing.append(page_info["image_url"])
                    logger.warning(f"[cuutruyen] Page {index + 1} missing (HTTP 404)")
                    break
                last_error = f"HTTP {status}"
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
            if attempt < CONFIG["download_retry"] - 1:
                await asyncio.sleep(1)

        if not ok and page_info["image_url"] not in missing:
            failed.append(page_info["image_url"])
            logger.error(f"[cuutruyen] Page {index + 1} failed: {last_error}")

        if progress:
            progress(index + 1, total)

    return failed, missing
