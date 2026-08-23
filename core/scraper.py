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
        {"title": "Chapter 12", "url": "...", "update_time": "2 ngày trước"},
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

CHAPTER_REGEX = re.compile(r"\b(chapter|chương|chap|ch\.?)\s*[:\-]?\s*\d+(\.\d+)?", re.IGNORECASE)
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
    """Lấy referer (origin) từ URL, vd https://example.com/a/b -> https://example.com"""
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


def find_nearest_link(tag):
    """Walk up from tag to find the closest enclosing <a href>."""
    curr = tag
    while curr is not None and getattr(curr, "name", None) != "html":
        if curr.name == "a" and curr.get("href"):
            return curr
        curr = curr.parent
    return None


# ----------------------------------------------------------------------
# 1. Title
# ----------------------------------------------------------------------

def find_title(soup: BeautifulSoup, thumb_img) -> str:
    # Priority: h1 khớp với og:title (dùng og:title làm mốc để chọn đúng h1,
    # không return trực tiếp og:title) > h1 đầu tiên > <title> tag > thumb alt
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
    best = max(groups.values(), key=len)
    # Ưu tiên nhóm >= 2 (pattern lặp lại). Nếu chỉ có 1 leaf duy nhất khớp
    # regex (truyện chỉ có 1 chapter), vẫn chấp nhận nó thay vì trả rỗng.
    return best if len(best) >= 2 else (best if len(best) == 1 else [])


def find_common_ancestor(elements):
    """Tìm ancestor chung gần nhất (sâu nhất) của một danh sách phần tử."""
    if not elements:
        return None
    chains = []
    for el in elements:
        chain = list(el.parents)
        chain.reverse()  # root -> ... -> parent trực tiếp
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
    Từ chapter_leaf leo dần lên, tìm ancestor lặp lại (>=2 sibling CÙNG tag
    VÀ CÙNG class) để dùng làm scope 'row'.

    Bỏ qua <td>/<th> vì trong <table>, các ô luôn lặp lại theo CỘT (>=2 td
    trong mọi <tr>) chứ không phải theo dòng dữ liệu.

    So thêm class (không chỉ tag): nhiều site dùng <div class="item-name">
    và <div class="item-time"> làm 2 cột con của <div class="item"> - cả
    hai đều là tag 'div' nên nếu chỉ so tag sẽ dừng nhầm ngay ở cấp
    item-name (vì nó có 1 sibling div khác - item-time). Yêu cầu class
    trùng nhau mới tính là "bản ghi lặp lại" thật sự.
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
    """Quét TOÀN BỘ document (tương đương document.querySelectorAll('*')),
    lấy mọi leaf khớp DATE_REGEX một lần duy nhất."""
    leaves = []
    for tag in soup.find_all(True):
        if not is_leaf(tag):
            continue
        text = leaf_text(tag)
        if 0 < len(text) < 50 and DATE_REGEX.search(text):
            leaves.append(tag)
    return leaves


def find_time_in_row(row, chapter_leaf, all_date_leaves):
    """Lọc trong all_date_leaves (đã quét * toàn document) những cái nằm
    bên trong row (containment check), thay vì tự query lại theo row."""
    matches = []
    for tag in all_date_leaves:
        if tag is chapter_leaf:
            continue
        # tag nằm trong row <=> row là một trong các ancestor của tag
        if row in tag.parents or tag is row:
            matches.append(leaf_text(tag))
    return matches


def expand_to_full_pattern(regex_group, soup):
    """
    regex_group chỉ dùng để XÁC ĐỊNH pattern (tag + class của leaf chapter).
    Sau đó lấy TOÀN BỘ phần tử khớp pattern đó trong container chung,
    bất kể text có khớp CHAPTER_REGEX hay không (vd '8.4: ...' thiếu tiền tố
    'Chapter'/'Chap' vẫn phải được tính là 1 chapter).
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

    # Chỉ giữ leaf thật sự (không có element con) và có text
    result = [t for t in candidates if is_leaf(t) and leaf_text(t)]
    return result if len(result) >= len(regex_group) else regex_group


def _is_same_story(url: str, base_url: str) -> bool:
    """True nếu url trỏ vào chapter của CÙNG truyện với base_url.

    Chapter thật của truyện có href bắt đầu bằng đường dẫn truyện (base path),
    vd base = https://site/truyen/abc -> chapter = https://site/truyen/abc/xyz.
    Các link related/recommended trỏ sang /truyen/<truyen-khac>/... -> loại.

    So sánh sau khi unquote: base_url có thể giữ dạng URL-encoded (%E5%B1%88...)
    trong khi href trong trang dùng ký tự decode (屈服...) — phải chuẩn hóa
    trước khi so prefix, không thì chapter thật bị loại nhầm.
    """
    base = unquote(base_url).rstrip("/")
    return unquote(url).startswith(base + "/")


NAV_BUTTON_TEXTS = {
    "đọc từ đầu", "đọc mới nhất", "đọc tiếp", "xem online", "xem trước",
    "read first", "read latest", "first", "latest", "read now", "read",
}


def _chapter_text(a) -> str:
    """Lấy text 'tên chapter' từ trong thẻ <a>: ưu tiên phần tử con có vẻ là
    tiêu đề (text-ellipsis, có chữ cái, ngắn), fallback toàn bộ text của <a>."""
    # Ưu tiên các phần tử con có class gợi ý tiêu đề
    for sel in (".text-ellipsis", ".name", ".chapter-title", ".chap-name", ".title"):
        el = a.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    # Fallback: text leaf ngắn nhất có chữ cái (bỏ view count/số thống kê)
    leaf_texts = []
    for el in a.find_all(True):
        if el.find_all(True):
            continue  # không phải leaf
        text = el.get_text(strip=True)
        if text and any(ch.isalpha() for ch in text):
            leaf_texts.append(text)
    if leaf_texts:
        return min(leaf_texts, key=len)
    return a.get_text(strip=True)


def _links_same_story(soup: BeautifulSoup, base_url: str) -> list:
    """Quét toàn bộ <a href>, giữ link cùng base path với truyện hiện tại,
    kèm text tên chapter. Dùng làm fallback khi regex không tìm được chapter."""
    result = []
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"])
        if not _is_same_story(url, base_url):
            continue
        text = _chapter_text(a)
        if not text:
            continue
        # Lọc nút điều hướng ('Đọc từ đầu'/'Đọc mới nhất'...) — không phải chapter
        if text.strip().lower() in NAV_BUTTON_TEXTS:
            continue
        result.append({"text": text, "url": url, "element": a})
    return result


def find_chapters(soup: BeautifulSoup, base_url: str, thumb_img):
    leaves = find_chapter_leaves(soup)
    regex_group = pick_best_group(leaves)
    full_group = expand_to_full_pattern(regex_group, soup)
    all_date_leaves = find_all_date_leaves(soup)  # quét * một lần cho toàn document

    # Lọc bỏ related/recommended: chỉ giữ leaf có link cùng base path với truyện.
    # (VD damconuong: 6 leaf 'Chapter N' đều trỏ sang truyện khác -> loại hết.)
    same_story = []
    for leaf in full_group:
        link = find_nearest_link(leaf)
        url = urljoin(base_url, link["href"]) if link is not None else ""
        if url and _is_same_story(url, base_url):
            same_story.append(leaf)

    # Fallback: regex không ra chapter thật (tên chapter không có tiền tố
    # 'Chapter/Chap', vd damconuong) -> quét mọi <a> cùng base path.
    if not same_story:
        candidates = _links_same_story(soup, base_url)
        # Lọc bỏ các nút điều hướng 'Đọc từ đầu'/'Đọc mới nhất' trỏ trùng chapter
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
        link = find_nearest_link(leaf)
        url = urljoin(base_url, link["href"]) if link is not None else ""

        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        row = find_row(leaf, thumb_img)
        update_times = find_time_in_row(row, leaf, all_date_leaves)

        # Bỏ qua chapter không có URL: đây thường là "nhiễu" từ các widget
        # khác trên trang (lịch sử đọc, đề xuất...) dùng chung tag+class
        # với chapter thật nhưng không nằm trong <a href> nào -> không dùng được.
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
    """Pipeline chính: chạy các heuristic trên soup, trả về đúng contract
    mà app tiêu thụ (engine + GUI):
        {"title", "thumb", "referer", "chapters": [{"title", "url", "update_time"}]}
    update_time luôn là string (None -> "").
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
    """Entry không network: chạy pipeline trên HTML string đã lấy sẵn
    (dùng cho page.content() của Playwright hoặc dump offline)."""
    soup = BeautifulSoup(html, "lxml")
    return _extract_from_soup(soup, url, debug)


def scrape(url: str, debug: bool = False) -> dict:
    return _extract_from_soup(fetch_soup(url), url, debug)


# ----------------------------------------------------------------------
# 4. Chapter images (heuristic — thay cho image_selector)
# ----------------------------------------------------------------------

# Class/pattern đánh dấu ảnh RÁC (logo, icon, quảng cáo, avatar...) — loại bỏ
BAD_IMG_CLASS_PARTS = (
    "logo", "icon", "avatar", "banner", "ad-", "ads", "advert", "social",
    "share", "emoji", "sponsor", "watermark", "placeholder",
)
BAD_IMG_URL_PARTS = (
    "logo", "icon", "avatar", "banner", "/ads/", "advert", "sponsor",
    "placeholder", "emoji",
)
# Pattern URL gợi ý ảnh nội dung chapter (CDN chuyên cho manga/comic)
GOOD_IMG_URL_PARTS = (
    "/manga-images/", "/images/data/", "/chapters/", "/chapter/", "/comics/",
    "/storage/chapter", "/content/images/",
)


def _img_src(img) -> str:
    """Lấy src thật của <img>, ưu tiên data-src (lazy-load) rồi src.
    Bỏ data:image placeholder (ảnh lazy chưa nạp)."""
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
    """Heuristic nhận diện ảnh chapter từ HTML trang chapter.

    Không cần image_selector: quét toàn bộ <img>, lọc ảnh rác
    (logo/icon/ads/avatar theo class + URL), ưu tiên pattern URL CDN manga,
    dedupe theo URL tuyệt đối. Trả list URL ảnh (đã urljoin)."""
    soup = BeautifulSoup(html, "lxml")
    urls = []
    seen = set()

    for img in soup.find_all("img"):
        src = _img_src(img)
        if not src:
            continue
        url = urljoin(base_url, src)

        # Bỏ ảnh rác theo class
        classes = " ".join(img.get("class") or []).lower()
        if any(part in classes for part in BAD_IMG_CLASS_PARTS):
            continue
        # Bỏ ảnh rác theo URL
        if any(part in url.lower() for part in BAD_IMG_URL_PARTS):
            continue
        # Bỏ ảnh không phải http(s) (vd data:, javascript:)
        if not url.startswith(("http://", "https://")):
            continue

        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    # Nếu có pattern URL nội dung rõ ràng -> chỉ giữ nhóm đó (loại ảnh trang
    # trí/logo CDN lẫn vào). Ngược lại giữ tất cả đã lọc rác.
    good = [u for u in urls if any(part in u.lower() for part in GOOD_IMG_URL_PARTS)]
    return good if good else urls


def main():
    parser = argparse.ArgumentParser(description="Extract manga info (thumb, title, chapters) from a URL.")
    parser.add_argument("url", help="Manga page URL")
    parser.add_argument("--json", dest="json_out", help="Path to save JSON output", default=None)
    parser.add_argument("--debug", action="store_true", help="Print debug info to stderr")
    args = parser.parse_args()

    if not urlparse(args.url).scheme:
        print("URL phải bao gồm scheme, vd: https://example.com/...", file=sys.stderr)
        sys.exit(1)

    try:
        data = scrape(args.url, debug=args.debug)
    except requests.RequestException as e:
        print(f"Lỗi khi tải trang: {e}", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(data, ensure_ascii=False, indent=2)
    print(output)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n[Đã lưu kết quả vào {args.json_out}]", file=sys.stderr)


if __name__ == "__main__":
    main()