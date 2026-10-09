#!/usr/bin/env python3
"""Compare the two download engines for a set of URLs.

P1 (default) probes each URL with both engines and diffs the metadata.
P2/P3 (``--download``) downloads each URL with both engines into throwaway
folders and compares image counts / total bytes.

    python tools/engine_compare.py https://site/a https://site/b
    python tools/engine_compare.py --urls sites.txt --download --out report.md

Run from the project root so `core`/`gui` are importable.
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.net.crawler import Crawler                  # noqa: E402
from core.engines.gallerydl import GalleryDLBackend   # noqa: E402
from core.engines.native import NativeBackend         # noqa: E402


class _NativeHost:
    """Just enough of Engine for NativeBackend.probe (crawl only)."""

    def __init__(self):
        self.crawler = Crawler()


def read_urls(args) -> list:
    urls = list(args.urls or [])
    if args.url_file:
        for line in Path(args.url_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


async def probe_one(backend, url):
    started = time.monotonic()
    try:
        meta = await backend.probe(url)
    except Exception as e:  # noqa: BLE001 - reported in the table
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "secs": time.monotonic() - started}
    return {
        "ok": True,
        "title": meta.title,
        "genres": len(meta.genres),
        "chapters": len(meta.chapters),
        "secs": time.monotonic() - started,
    }


def image_stats(folder: Path):
    images = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in
              {".jpg", ".png", ".webp", ".gif", ".bmp", ".avif"}]
    return len(images), sum(p.stat().st_size for p in images)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="URLs to compare")
    parser.add_argument("--urls", dest="url_file", help="file with one URL per line")
    parser.add_argument("--download", action="store_true", help="also download with both engines")
    parser.add_argument("--out", help="write the Markdown report here")
    args = parser.parse_args()

    urls = read_urls(args)
    if not urls:
        parser.error("no URLs given (positional or --urls)")

    native = NativeBackend(_NativeHost())
    gallerydl = GalleryDLBackend()

    rows = []
    for url in urls:
        print(f"\n=== {url} ===")
        n = await probe_one(native, url)
        g = await probe_one(gallerydl, url)
        print(f"  native    : {n}")
        print(f"  gallery-dl: {g}")

        row = {"url": url, "native": n, "gallerydl": g}

        if args.download:
            for name, backend in (("native", native), ("gallerydl", gallerydl)):
                out = Path(tempfile.mkdtemp(prefix=f"cmp_{name}_"))
                try:
                    job = _fake_job(url, out, n if name == "native" else g)
                    started = time.monotonic()
                    outcome = await backend.download(job)
                    secs = time.monotonic() - started
                    count, size = image_stats(out)
                    row[name + "_dl"] = {
                        "status": getattr(outcome, "status", "?"),
                        "images": count, "bytes": size, "secs": secs,
                    }
                    print(f"  {name} download: {row[name + '_dl']}")
                except Exception as e:  # noqa: BLE001
                    row[name + "_dl"] = {"status": f"error: {e}"}
                finally:
                    shutil.rmtree(out, ignore_errors=True)

        rows.append(row)

    report = render(rows, args.download)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nReport written to {args.out}")
    else:
        print("\n" + report)
    return 0


def _fake_job(url, save_path, probed):
    import types
    return types.SimpleNamespace(
        url=url,
        site_id=None,
        title=probed.get("title", "") if probed.get("ok") else "",
        chapters=[{"title": "c", "url": url, "update_time": ""}]
        * max(1, probed.get("chapters", 1) if probed.get("ok") else 1),
        save_path=save_path,
        referer="",
        current_chap=1,
        engine=None,
    )


def render(rows, with_download: bool) -> str:
    lines = ["| Site | Engine | Probe | Chapters | Genres | Images | MB | Secs |",
             "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |"]
    for row in rows:
        domain = row["url"].split("/")[2] if "//" in row["url"] else row["url"]
        for name in ("native", "gallerydl"):
            probe = row[name]
            if not probe.get("ok"):
                lines.append(f"| {domain} | {name} | ❌ | — | — | — | — | {probe['secs']:.1f} |")
                continue
            dl = row.get(name + "_dl", {})
            images = dl.get("images", "—")
            mb = f"{dl.get('bytes', 0) / 1048576:.1f}" if dl else "—"
            secs = dl.get("secs", probe["secs"])
            lines.append(
                f"| {domain} | {name} | ✅ | {probe['chapters']} | {probe['genres']} "
                f"| {images} | {mb} | {secs:.1f} |"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
