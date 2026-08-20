// ==UserScript==
// @name         Manga Selector Detector
// @namespace    manga-selector-detector
// @version      1.1.0
// @description  Tự nhận diện trang đọc truyện tranh (manga) và gợi ý CSS selector (thumbnail, title, chapter list, update time, image) dưới dạng JSON entry cho extractor.json.
// @author       you
// @match        *://*/*
// @run-at       document-idle
// @grant        GM_setClipboard
// @noframes
// ==/UserScript==

(function () {
  'use strict';

  /* =========================================================
   * BƯỚC 1: HEURISTIC NHẬN DIỆN "ĐÂY CÓ PHẢI TRANG MANGA KHÔNG"
   * =======================================================*/

  const MANGA_KEYWORDS = [
    'manga', 'comic', 'truyện tranh', 'truyen tranh', 'đọc truyện',
    'doc truyen', 'chapter', 'chương', 'chuong', 'webtoon', 'manhwa', 'manhua'
  ];

  function scoreText(text) {
    if (!text) return 0;
    const t = text.toLowerCase();
    let score = 0;
    for (const kw of MANGA_KEYWORDS) {
      if (t.includes(kw)) score += 1;
    }
    return score;
  }

  function isMangaSite() {
    let score = 0;

    // 1. Title + meta keywords/description
    score += scoreText(document.title) * 2;
    const metaKw = document.querySelector('meta[name="keywords"]');
    const metaDesc = document.querySelector('meta[name="description"]');
    score += scoreText(metaKw?.content);
    score += scoreText(metaDesc?.content);

    // 2. URL
    score += scoreText(location.href);

    // 3. Cấu trúc DOM: có phần tử id/class chứa "chapter"/"chuong"/"chương" không
    const structuralHits = document.querySelectorAll(
      '[class*="chapter" i], [id*="chapter" i], [class*="chuong" i], [id*="chuong" i]'
    );
    score += Math.min(structuralHits.length, 5);

    // 4. Có nhiều thẻ <img> xếp dọc liên tiếp trong 1 container (kiểu trang đọc truyện)
    const containers = document.querySelectorAll('div, main, section');
    for (const c of containers) {
      const imgs = c.querySelectorAll(':scope > img, :scope > p > img, :scope > div > img');
      if (imgs.length >= 5) {
        score += 3;
        break;
      }
    }

    return score >= 4; // ngưỡng, có thể tinh chỉnh
  }

  if (!isMangaSite()) {
    return; // không phải trang manga -> script im lặng, không làm gì cả
  }

  /* =========================================================
   * PHÂN LOẠI TRANG: trang đọc chapter hay trang tổng quan?
   * =======================================================*/

  const STORAGE_KEY = 'msd_image_selector'; // lưu image_selector theo domain

  function detectReadingPage() {
    // Trang đọc chapter: có container chứa nhiều ảnh xếp dọc (>4)
    const containers = document.querySelectorAll('div, main, section');
    for (const c of containers) {
      const imgs = c.querySelectorAll(':scope > img, :scope > p > img, :scope > div > img');
      if (imgs.length >= 5) return true;
    }
    return false;
  }

  function detectImageSelector() {
    // Container chứa nhiều ảnh nhất (xếp dọc) -> chính là khung đọc
    let best = null;
    const containers = document.querySelectorAll('div, main, section');
    for (const c of containers) {
      const imgs = c.querySelectorAll(':scope > img, :scope > p > img, :scope > div > img');
      if (imgs.length >= 5 && (!best || imgs.length > best.count)) {
        best = { container: c, count: imgs.length, imgs };
      }
    }
    if (!best) return null;

    // Gợi ý theo cấu trúc: ưu tiên "img" trực tiếp trong container,
    // giữ nguyên dạng img trần nếu nó là con trực tiếp hoặc trong p/div.
    const containerSel = cssPath(best.container);
    const direct = best.container.querySelectorAll(':scope > img');
    if (direct.length >= 5) {
      return { selector: `${containerSel} > img`, sample: direct[0]?.src, count: direct.length };
    }
    const inP = best.container.querySelectorAll(':scope > p > img');
    if (inP.length >= 5) {
      return { selector: `${containerSel} > p > img`, sample: inP[0]?.src, count: inP.length };
    }
    const inDiv = best.container.querySelectorAll(':scope > div > img');
    if (inDiv.length >= 5) {
      return { selector: `${containerSel} > div > img`, sample: inDiv[0]?.src, count: inDiv.length };
    }
    return { selector: `${containerSel} img`, sample: best.imgs[0]?.src, count: best.count };
  }

  const isReading = detectReadingPage();

  if (isReading) {
    // Trang đọc chapter: chỉ detect image_selector rồi lưu lại, không hiện panel
    const imgSel = detectImageSelector();
    if (imgSel) {
      const store = {};
      try { store[location.hostname] = imgSel; } catch (e) { /* ignore */ }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
      console.log('[Manga Selector Detector] image_selector:', imgSel.selector);
    }
    return;
  }

  // Trang tổng quan: đọc image_selector đã lưu (nếu có) cho domain hiện tại
  let savedImageSelector = null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const store = JSON.parse(raw);
      savedImageSelector = store[location.hostname] || null;
    }
  } catch (e) { /* ignore */ }

  /* =========================================================
   * BƯỚC 2: DÒ SELECTOR Ở TRANG TỔNG QUAN (OVERVIEW / DETAIL PAGE)
   * =======================================================*/

  function cssPath(el) {
    if (!(el instanceof Element)) return '';
    const escape = (s) => CSS.escape(s);
    const parts = [];
    while (el && el.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
      let selector = el.tagName.toLowerCase();
      if (el.id) {
        selector += '#' + escape(el.id);
        parts.unshift(selector);
        break;
      } else if (el.className && typeof el.className === 'string') {
        const cls = el.className.trim().split(/\s+/).slice(0, 2)
          .map((c) => '.' + escape(c))
          .join('');
        if (cls) selector += cls;
      }
      parts.unshift(selector);
      el = el.parentElement;
    }
    return parts.join(' > ');
  }

  // ---- Title ----
  function detectTitle() {
    const candidates = [
      'h1', '.title', '.page-info h1', '.series-title', '[itemprop="name"]',
      'meta[property=\'og:title\']'
    ];
    for (const sel of candidates) {
      const el = document.querySelector(sel);
      if (el) {
        const text = el.content || el.textContent.trim();
        if (text && text.length > 2) {
          return { selector: sel.startsWith('meta') ? sel : cssPath(el), sample: text.slice(0, 80) };
        }
      }
    }
    return null;
  }

  // ---- Thumbnail ----
  function detectThumb() {
    const og = document.querySelector('meta[property=\'og:image\']');
    if (og?.content) return { selector: 'meta[property=\'og:image\']', sample: og.content };

    const candidates = ['.page-ava img', '.cover img', '.thumb img', '.series-cover img'];
    for (const sel of candidates) {
      const el = document.querySelector(sel);
      if (el?.src) return { selector: cssPath(el), sample: el.src };
    }
    return null;
  }

  // ---- Chapter list (tìm container có nhiều dòng lặp lại chứa từ "chương/chapter/ch.") ----
  function detectChapterRows() {
    const linkRegex = /chapter|chương|chuong|ch\.?\s?\d+/i;
    const groups = new Map(); // parentSelector -> [rows]

    // Ưu tiên thẻ <a> có href trỏ tới chapter (row chuẩn)
    const links = document.querySelectorAll('a[href]');
    for (const row of links) {
      const text = (row.innerText || row.textContent || '').replace(/\s+/g, ' ').trim();
      const href = row.getAttribute('href') || '';
      if (
        text.length > 0 && text.length < 120 &&
        linkRegex.test(text) && linkRegex.test(href)
      ) {
        const parent = row.parentElement;
        if (!parent) continue;
        const key = cssPath(parent);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(row);
      }
    }

    // Chọn nhóm có nhiều dòng lặp lại nhất (>=2) và có sample text chứa chapter
    let best = null;
    for (const [key, els] of groups.entries()) {
      if (els.length >= 2 && (!best || els.length > best.count)) {
        best = { key, count: els.length, sampleEl: els[0], tag: els[0].tagName.toLowerCase() };
      }
    }

    // Fallback: quét tr/li/div nếu không tìm thấy nhóm <a>
    if (!best) {
      const rows = document.querySelectorAll('tr, li, div');
      for (const row of rows) {
        const text = row.textContent.trim();
        if (text.length > 0 && text.length < 120 && linkRegex.test(text)) {
          const parent = row.parentElement;
          if (!parent) continue;
          const key = cssPath(parent);
          if (!groups.has(key)) groups.set(key, []);
          groups.get(key).push(row);
        }
      }
      for (const [key, els] of groups.entries()) {
        if (els.length >= 2 && (!best || els.length > best.count)) {
          best = { key, count: els.length, sampleEl: els[0], tag: els[0].tagName.toLowerCase() };
        }
      }
    }

    if (!best) return null;

    // rút gọn selector: "parentSelector tagname"
    const rowSelector = `${best.key} ${best.tag}`;
    return {
      selector: rowSelector,
      sample: best.sampleEl.textContent.trim().slice(0, 80),
      count: best.count
    };
  }

  // ---- Update time (trong 1 chapter row, tìm phần tử chứa ngày tháng / "x ago" / "trước") ----
  function detectChapterTime(rowSelector) {
    if (!rowSelector) return null;
    let rows;
    try {
      rows = document.querySelectorAll(rowSelector);
    } catch (e) {
      return null;
    }
    if (!rows.length) return null;

    const dateRegex = /(\d{1,2}[\/\-.]\d{1,2}([\/\-.]\d{2,4})?)|(\d+\s?(phút|giờ|ngày|tháng|năm)\s?trước)|(\d+\s?(min|hour|day|month|year)s?\s?ago)/i;

    // Ưu tiên phần tử "anh em kế tiếp" (td + td, span kế bên...)
    const siblingCandidates = ['td + td', 'span + span', '.chapter-time', '.time', '.update-time'];
    for (const row of rows) {
      for (const sel of siblingCandidates) {
        const el = row.querySelector(sel);
        if (el && dateRegex.test(el.textContent)) {
          // update_time_selector query toàn cục -> phải là selector đầy đủ, ghép với rowSelector
          return { selector: `${rowSelector} ${sel}`, sample: el.textContent.trim() };
        }
      }
    }

    // fallback: quét toàn bộ con cháu của mọi row, chọn leaf có text ngày giờ
    for (const row of rows) {
      const all = row.querySelectorAll('*');
      for (const el of all) {
        if (el.children.length === 0 && dateRegex.test(el.textContent)) {
          const leaf = cssPath(el).split(' > ').slice(-1)[0];
          return { selector: `${rowSelector} ${leaf}`, sample: el.textContent.trim() };
        }
      }
    }
    return null;
  }

  const result = {
    title: detectTitle(),
    thumb: detectThumb(),
    chapterRows: detectChapterRows(),
    image: savedImageSelector,
  };
  result.chapterTime = detectChapterTime(result.chapterRows?.selector);

  /* =========================================================
   * BƯỚC 3: HIỂN THỊ PANEL KẾT QUẢ + NÚT COPY DẠNG JSON
   * =======================================================*/

  function buildJsonSnippet() {
    const domain = location.hostname.replace(/^www\./, '').split('.')[0];
    const entry = {
      name: domain,
      domains: [domain],
      referer: `${location.origin}/`,
      title_selector: result.title?.selector ?? '/* TODO */',
      thumb_selector: result.thumb?.selector ?? '/* TODO */',
      chapter_row_selector: result.chapterRows?.selector ?? '/* TODO */',
      update_time_selector: result.chapterTime?.selector ?? '/* TODO */',
      wait_selectors: [],
      image_selector: result.image?.selector ?? '/* TODO: mở 1 chapter để tự detect */',
    };
    if (result.title?.selector && result.chapterRows?.selector) {
      entry.wait_selectors = [result.title.selector, result.chapterRows.selector];
    }
    return JSON.stringify(entry, null, 2);
  }

  function renderPanel() {
    const panel = document.createElement('div');
    panel.style.cssText = `
      position: fixed; bottom: 16px; right: 16px; z-index: 999999;
      width: 340px; max-height: 70vh; overflow: auto;
      background: #1e1e1e; color: #eee; font: 12px/1.4 monospace;
      border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,.4);
      padding: 12px;
    `;

    const rowHtml = (label, data) => `
      <div style="margin-bottom:8px;">
        <b style="color:#8ab4f8;">${label}</b><br>
        <code style="word-break:break-all;">${data?.selector ?? '(không tìm thấy)'}</code><br>
        <span style="color:#999;">${data?.sample ? '→ ' + escapeHtml(data.sample) : ''}</span>
      </div>`;

    function escapeHtml(str) {
      return String(str).replace(/[&<>"']/g, (m) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[m]));
    }

    panel.innerHTML = `
      <div style="font-weight:bold;color:#fff;margin-bottom:8px;">
        🔍 Manga Selector Detector
      </div>
      ${rowHtml('title_selector', result.title)}
      ${rowHtml('thumb_selector', result.thumb)}
      ${rowHtml('chapter_row_selector', result.chapterRows)}
      ${rowHtml('update_time_selector', result.chapterTime)}
      ${rowHtml('image_selector', result.image)}
      <div style="margin-bottom:8px;color:#999;">
        ${result.image ? '' : '💡 image_selector: mở 1 chapter bất kỳ rồi quay lại trang này.'}
      </div>
      <button id="msd-copy-btn" style="
        margin-top:6px; padding:6px 10px; background:#8ab4f8; color:#000;
        border:none; border-radius:4px; cursor:pointer; font-weight:bold;">
        Copy JSON entry
      </button>
      <button id="msd-close-btn" style="
        margin-top:6px; margin-left:6px; padding:6px 10px; background:#444; color:#fff;
        border:none; border-radius:4px; cursor:pointer;">
        Đóng
      </button>
    `;

    document.body.appendChild(panel);

    panel.querySelector('#msd-copy-btn').addEventListener('click', () => {
      const snippet = buildJsonSnippet();
      if (typeof GM_setClipboard === 'function') {
        GM_setClipboard(snippet);
      } else {
        navigator.clipboard.writeText(snippet);
      }
      const btn = panel.querySelector('#msd-copy-btn');
      btn.textContent = 'Đã copy ✓';
      setTimeout(() => (btn.textContent = 'Copy JSON entry'), 1500);
    });

    panel.querySelector('#msd-close-btn').addEventListener('click', () => panel.remove());
  }

  renderPanel();
})();