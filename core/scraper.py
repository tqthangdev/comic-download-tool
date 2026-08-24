#!/usr/bin/env python3
"""
Manga Selector Finder / Scraper
--------------------------------
Input : manga page URL
Output: {
    "title": ...,
    "thumb": ...,
    "referer": ...,
    "chapters": [
        {"title": "Chapter 12", "url": "...", "update_time": "2 days ago"},
        ...
    ]
}

Usage:
    python core/scraper.py "https://example.com/manga/some-title"
    python core/scraper.py "https://example.com/manga/some-title" --json out.json
    python core/scraper.py "https://example.com/manga/some-title" --debug
"""

import argparse
import json
import re
import sys
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup, NavigableString

from core.utils import CONFIG

HEADERS = {
    "User-Agent": CONFIG["user_agent"],
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

CHAPTER_REGEX = re.compile(r"\b(chapter|chương|chap|ch\.?)\s*[:\-]?\s*\d+(\.\d+)?", re.IGNORECASE)
# Some sites (e.g. cmangax18) navigate chapters via onclick instead of <a href>
ONCLICK_URL_RE = re.compile(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
DATE_REGEX = re.compile(
    r"(\d{1,2}[/\-.]\d{1,2}([/\-.]\d{2,4})?)"
    r"|(\d+\s?(phút|giờ|ngày|tuần|tháng|năm)\s?trước)"
    r"|(\d+\s?(min|hour|day|week|month|year)s?\s?ago)"
    r"|(hôm nay|hôm qua|vừa xong|today|yesterday|just now)"
    r"|((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s?\d{1,2})",
    re.IGNORECASE,
)
SKIP_TAGS = {"script", "style", "head", "noscript", "template", "svg"}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def get_referer(url: str) -> str:
    """Get the referer (origin) from a URL, e.g. https://example.com/a/b -> https://example.com"""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def fetch_soup(url: str, timeout: int = 15) -> BeautifulSoup:
    headers = dict(HEADERS)
    referer = get_referer(url)
    if referer:
        headers["Referer"] = referer
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return BeautifulSoup(resp.text, "lxml")


def is_leaf(tag) -> bool:
    """A leaf: no element children (text-only), and not a skip tag."""
    if tag.name in SKIP_TAGS:
        return False
    for child in tag.children:
        if not isinstance(child, NavigableString) and child.name is not None:
            return False
    return True


def leaf_text(tag) -> str:
    return tag.get_text(strip=True)


def get_element_url(tag, base_url):
    """Walk up from tag: return the URL from the closest enclosing <a href>,
    or from an onclick="location.href='...'" attribute (used by some sites
    instead of an <a> link). Returns "" when none is found."""
    curr = tag
    while curr is not None and getattr(curr, "name", None) != "html":
        if curr.name == "a" and curr.get("href"):
            return urljoin(base_url, curr["href"])
        onclick = curr.get("onclick") or ""
        m = ONCLICK_URL_RE.search(onclick)
        if m:
            return urljoin(base_url, m.group(1))
        curr = curr.parent
    return ""


# ----------------------------------------------------------------------
# 1. Title
# ----------------------------------------------------------------------

def find_title(soup: BeautifulSoup, thumb_img) -> str:
    # Priority: h1 matching og:title (use og:title as an anchor to pick the
    # right h1, but do not return og:title directly) > first h1 > <title> tag >
    # thumb alt
    og = soup.find("meta", property="og:title")
    og_content = og.get("content", "").strip() if og and og.get("content") else ""

    h1_tags = soup.find_all("h1")

    if og_content:
        for h1 in h1_tags:
            text = h1.get_text(strip=True)
            if text and text in og_content:
                return text

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)

    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)

    if thumb_img is not None and thumb_img.get("alt", "").strip():
        return thumb_img["alt"].strip()

    return ""


# ----------------------------------------------------------------------
# 2. Thumbnail
# ----------------------------------------------------------------------

def find_thumb(soup: BeautifulSoup, base_url: str):
    # Priority: og:image meta > img[class/id*=thumb/cover] > .thumb img/.cover img > first <img>
    og = soup.find("meta", property="og:image")
    if og and og.get("content", "").strip():
        return {"url": urljoin(base_url, og["content"].strip()), "element": None}

    candidates = soup.select(
        'img[class*="thumb"], img[class*="cover"], img[id*="thumb"], img[id*="cover"], '
        ".thumb img, .cover img"
    )
    img = candidates[0] if candidates else soup.find("img")

    if img is None:
        return {"url": "", "element": None}

    src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
    return {"url": urljoin(base_url, src) if src else "", "element": img}


# ----------------------------------------------------------------------
# 3. Chapters (leaf-based grouping)
# ----------------------------------------------------------------------

def find_chapter_leaves(soup: BeautifulSoup):
    leaves = []
    for tag in soup.find_all(True):
        if not is_leaf(tag):
            continue
        text = leaf_text(tag)
        if 0 < len(text) < 100 and CHAPTER_REGEX.search(text):
            leaves.append(tag)
    return leaves


def group_key(tag):
    parent_name = tag.parent.name if tag.parent else ""
    return f"{tag.name}>{parent_name}"


def pick_best_group(leaves):
    groups = {}
    for tag in leaves:
        groups.setdefault(group_key(tag), []).append(tag)
    if not groups:
        return []
    # A real chapter list has mostly DISTINCT labels (Chapter 1, 2, 3...),
    # while junk noise (reading history, comment mentions) repeats the same
    # label many times. Rank by distinct-label ratio first so a 10-item junk
    # group of repeated "Chapter 7" does not beat an 8-item real 0..7 list.
    def rank(g):
        texts = {leaf_text(t) for t in g}
        return (len(texts) / len(g), len(g))
    candidates = [g for g in groups.values() if len(g) >= 3 and len({leaf_text(t) for t in g}) >= 2]
    if candidates:
        return max(candidates, key=rank)
    # Fallback: single-leaf stories, or nothing the ranking could separate
    best = max(groups.values(), key=len)
    # Prefer groups with >= 2 leaves (recurring pattern). If only a single leaf
    # matches the regex (a story with just one chapter), still accept it instead
    # of returning an empty result.
    return best if len(best) >= 2 else (best if len(best) == 1 else [])


def find_common_ancestor(elements):
    """Find the deepest common ancestor of a list of elements."""
    if not elements:
        return None
    chains = []
    for el in elements:
        chain = list(el.parents)
        chain.reverse()  # root -> ... -> direct parent
        chain.append(el)
        chains.append(chain)
    common = None
    for group in zip(*chains):
        first = group[0]
        if all(t is first for t in group):
            common = first
        else:
            break
    return common


def find_row(chapter_leaf, thumb_img):
    """
    Walk up from chapter_leaf, looking for a repeating ancestor (>=2 siblings
    with the SAME tag AND SAME class) to use as the 'row' scope.

    Skip <td>/<th> because inside a <table> cells always repeat per COLUMN
    (>=2 td in every <tr>), not per data row.

    Also compare class (not just tag): many sites use <div class="item-name">
    and <div class="item-time"> as two child columns of <div class="item"> -
    both are 'div' tags, so comparing tag only would stop too early at the
    item-name level (it has one other div sibling - item-time). Requiring a
    matching class is what counts as a real repeating record.
    """
    SKIP_STOP_TAGS = {"td", "th"}
    curr = chapter_leaf
    steps = 0
    while curr is not None and getattr(curr, "name", None) not in ("html", None) and steps < 8:
        parent = curr.parent
        if parent is not None and curr.name not in SKIP_STOP_TAGS:
            curr_classes = curr.get("class") or []
            same_siblings = [
                s for s in parent.find_all(curr.name, recursive=False)
                if (s.get("class") or []) == curr_classes
            ]
            if len(same_siblings) >= 2:
                return curr
        curr = parent
        steps += 1
    return chapter_leaf.parent or chapter_leaf


def find_all_date_leaves(soup: BeautifulSoup):
    """Scan the WHOLE document (equivalent to document.querySelectorAll('*')),
    collecting every leaf matching DATE_REGEX exactly once."""
    leaves = []
    for tag in soup.find_all(True):
        if not is_leaf(tag):
            continue
        text = leaf_text(tag)
        if 0 < len(text) < 50 and DATE_REGEX.search(text):
            leaves.append(tag)
    return leaves


def find_time_in_row(row, chapter_leaf, all_date_leaves):
    """Filter all_date_leaves (already scanned over the whole document) down to
    those contained inside row (containment check), instead of re-querying per row."""
    matches = []
    for tag in all_date_leaves:
        if tag is chapter_leaf:
            continue
        # a tag is inside row <=> row is one of the tag's ancestors
        if row in tag.parents or tag is row:
            matches.append(leaf_text(tag))
    return matches


def expand_to_full_pattern(regex_group, soup):
    """
    regex_group is only used to DETERMINE the pattern (tag + class of the
    chapter leaf). Then grab ALL elements matching that pattern inside the
    shared container, regardless of whether their text matches CHAPTER_REGEX
    (e.g. '8.4: ...' missing the 'Chapter'/'Chap' prefix must still count as a chapter).
    """
    if not regex_group:
        return []

    sample = regex_group[0]
    tag_name = sample.name
    classes = sample.get("class") or []

    container = find_common_ancestor(regex_group)
    if container is None:
        return regex_group

    if classes:
        candidates = container.find_all(tag_name, class_=classes)
    else:
        parent_tag = sample.parent.name if sample.parent else None
        candidates = [
            t for t in container.find_all(tag_name)
            if t.parent is not None and t.parent.name == parent_tag
        ]

    # Keep only real leaves (no element children) that have text
    result = [t for t in candidates if is_leaf(t) and leaf_text(t)]
    return result if len(result) >= len(regex_group) else regex_group


def _is_same_story(url: str, base_url: str) -> bool:
    """True if url points to a chapter of the SAME story as base_url.

    A real story chapter has an href starting with the story path (base path),
    e.g. base = https://site/truyen/abc -> chapter = https://site/truyen/abc/xyz.
    Related/recommended links pointing to another /truyen/<other>/... are dropped.

    Compare after unquote: base_url may stay URL-encoded (%E5%B1%88...) while
    the in-page href uses decoded characters (屈服...) - normalize before the
    prefix check, otherwise real chapters get wrongly filtered out.

    Some sites (e.g. cmangax18) use album URLs like /album/<slug>-<albumid>
    while chapters live under /album/<slug>/... - so also try the base with the
    trailing numeric segment stripped.
    """
    url = unquote(url)
    base = unquote(base_url).rstrip("/")
    if url.startswith(base + "/"):
        return True
    stripped = re.sub(r"-\d+$", "", base)
    return bool(stripped) and stripped != base and url.startswith(stripped + "/")


NAV_BUTTON_TEXTS = {
    "đọc từ đầu", "đọc mới nhất", "đọc tiếp", "xem online", "xem trước",
    "read first", "read latest", "first", "latest", "read now", "read",
}


def _chapter_text(a) -> str:
    """Extract the 'chapter name' text from inside an <a>: prefer a child that
    looks like a title (text-ellipsis, letters, short), fall back to the full <a> text."""
    # Prefer child elements whose class suggests a title
    for sel in (".text-ellipsis", ".name", ".chapter-title", ".chap-name", ".title"):
        el = a.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    # Fallback: the shortest text leaf containing letters (skip view counts/stats)
    leaf_texts = []
    for el in a.find_all(True):
        if el.find_all(True):
            continue  # not a leaf
        text = el.get_text(strip=True)
        if text and any(ch.isalpha() for ch in text):
            leaf_texts.append(text)
    if leaf_texts:
        return min(leaf_texts, key=len)
    return a.get_text(strip=True)


def _links_same_story(soup: BeautifulSoup, base_url: str) -> list:
    """Scan every element with a link (<a href> or onclick navigation), keep
    those on the same base path as the current story, together with the chapter
    name text. Used as a fallback when the regex finds no chapters."""
    result = []
    seen = set()
    anchors = list(soup.find_all(href=True)) + list(soup.find_all(onclick=True))
    for el in anchors:
        if el in seen:
            continue
        seen.add(el)
        url = get_element_url(el, base_url)
        if not url or not _is_same_story(url, base_url):
            continue
        text = _chapter_text(el)
        if not text:
            continue
        # Filter navigation buttons ('read first'/'read latest'...) — not chapters
        if text.strip().lower() in NAV_BUTTON_TEXTS:
            continue
        result.append({"text": text, "url": url, "element": el})
    return result


def find_chapters(soup: BeautifulSoup, base_url: str, thumb_img):
    leaves = find_chapter_leaves(soup)
    regex_group = pick_best_group(leaves)
    full_group = expand_to_full_pattern(regex_group, soup)
    all_date_leaves = find_all_date_leaves(soup)  # scan the document once for all dates

    # Drop related/recommended: keep only leaves whose link shares the story base path.
    # (e.g. damconuong: 6 'Chapter N' leaves all point to other stories -> dropped.)
    same_story = []
    for leaf in full_group:
        url = get_element_url(leaf, base_url)
        if url and _is_same_story(url, base_url):
            same_story.append(leaf)

    # Fallback: regex finds no real chapter (chapter names without a
    # 'Chapter/Chap' prefix, e.g. damconuong) -> scan every <a> on the base path.
    if not same_story:
        candidates = _links_same_story(soup, base_url)
        # Drop navigation buttons ('read first'/'read latest') pointing at the same chapter
        chapters = []
        seen_urls = set()
        for c in candidates:
            url = c["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            row = find_row(c["element"], thumb_img)
            update_times = find_time_in_row(row, c["element"], all_date_leaves)
            chapters.append({
                "name": c["text"],
                "url": url,
                "update_time": update_times[0] if update_times else None,
            })
        return chapters

    chapters = []
    seen_urls = set()

    for leaf in same_story:
        name = leaf_text(leaf)
        url = get_element_url(leaf, base_url)

        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        row = find_row(leaf, thumb_img)
        update_times = find_time_in_row(row, leaf, all_date_leaves)

        # Skip a chapter that has no URL: this is usually 'noise' from other widgets
        # on the page (reading history, suggestions...) that share the same tag+class
        # as real chapters but are not inside any <a href> -> unusable.
        if not url:
            continue

        chapters.append({
            "name": name,
            "url": url,
            "update_time": update_times[0] if update_times else None,
        })

    return chapters


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def _extract_from_soup(soup: BeautifulSoup, base_url: str, debug: bool = False) -> dict:
    """Main pipeline: run the heuristics on the soup and return the exact
    contract the app consumes (engine + GUI):
        {"title", "thumb", "referer", "chapters": [{"title", "url", "update_time"}]}
    update_time is always a string (None -> "").
    """
    thumb = find_thumb(soup, base_url)
    title = find_title(soup, thumb["element"])
    chapters = find_chapters(soup, base_url, thumb["element"])

    result = {
        "title": title,
        "thumb": thumb["url"],
        "referer": get_referer(base_url),
        "chapters": [
            {
                "title": c["name"],
                "url": c["url"],
                "update_time": c["update_time"] or "",
            }
            for c in chapters
        ],
    }

    if debug:
        print(f"[debug] title source elements found: {bool(title)}", file=sys.stderr)
        print(f"[debug] thumb candidates found: {thumb['element'] is not None}", file=sys.stderr)
        print(f"[debug] chapter leaves matched: {len(chapters)}", file=sys.stderr)

    return result


def scrape_from_html(html: str, url: str, debug: bool = False) -> dict:
    """Network-free entry point: run the pipeline on an already-fetched HTML
    string (used for Playwright's page.content() or offline dumps)."""
    soup = BeautifulSoup(html, "lxml")
    return _extract_from_soup(soup, url, debug)


def scrape(url: str, debug: bool = False) -> dict:
    return _extract_from_soup(fetch_soup(url), url, debug)


# ----------------------------------------------------------------------
# 4. Chapter images (heuristic — replaces image_selector)
# ----------------------------------------------------------------------

# Class/pattern marking JUNK images (logo, icon, ad, avatar...) to be removed
BAD_IMG_CLASS_PARTS = (
    "logo", "icon", "avatar", "banner", "ad-", "ads", "advert", "social",
    "share", "emoji", "sponsor", "watermark", "placeholder",
)
BAD_IMG_URL_PARTS = (
    "logo", "icon", "avatar", "banner", "/ads/", "advert", "sponsor",
    "placeholder", "emoji",
)
# URL pattern suggesting content images (manga/comic CDN)
GOOD_IMG_URL_PARTS = (
    "/manga-images/", "/images/data/", "/chapters/", "/chapter/", "/comics/",
    "/storage/chapter", "/content/images/",
)


def _img_src(img) -> str:
    """Get the real src of an <img>, preferring data-src (lazy-load) over src.
    Drop data:image placeholders (lazy images not yet loaded)."""
    src = (
        img.get("data-src")
        or img.get("data-original")
        or img.get("data-lazy-src")
        or img.get("src")
        or ""
    ).strip()
    if src.startswith("data:"):
        return ""
    return src


def find_chapter_images(html: str, base_url: str) -> list:
    """Heuristic to detect chapter images from a chapter page's HTML.

    No image_selector needed: scan every <img>, filter junk images
    (logo/icon/ads/avatar by class + URL), prefer manga CDN URL patterns,
    dedupe by absolute URL. Returns a list of image URLs (already urljoined)."""
    soup = BeautifulSoup(html, "lxml")
    urls = []
    seen = set()

    for img in soup.find_all("img"):
        src = _img_src(img)
        if not src:
            continue
        url = urljoin(base_url, src)

        # Drop junk images by class
        classes = " ".join(img.get("class") or []).lower()
        if any(part in classes for part in BAD_IMG_CLASS_PARTS):
            continue
        # Drop junk images by URL
        if any(part in url.lower() for part in BAD_IMG_URL_PARTS):
            continue
        # Drop non-http(s) images (e.g. data:, javascript:)
        if not url.startswith(("http://", "https://")):
            continue

        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    # If there is a clear content URL pattern, keep only that group (filtering out
    # decorative/CDN logo images that slipped in). Otherwise keep all already-filtered.
    good = [u for u in urls if any(part in u.lower() for part in GOOD_IMG_URL_PARTS)]
    return good if good else urls


def main():
    parser = argparse.ArgumentParser(description="Extract manga info (thumb, title, chapters) from a URL.")
    parser.add_argument("url", help="Manga page URL")
    parser.add_argument("--json", dest="json_out", help="Path to save JSON output", default=None)
    parser.add_argument("--debug", action="store_true", help="Print debug info to stderr")
    args = parser.parse_args()

    if not urlparse(args.url).scheme:
        print("URL must include a scheme, e.g. https://example.com/...", file=sys.stderr)
        sys.exit(1)

    try:
        data = scrape(args.url, debug=args.debug)
    except requests.RequestException as e:
        print(f"Error loading page: {e}", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(data, ensure_ascii=False, indent=2)
    print(output)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n[Saved result to {args.json_out}]", file=sys.stderr)


if __name__ == "__main__":
    main()