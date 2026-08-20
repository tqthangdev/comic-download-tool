from core.base_extractor import BaseExtractor

__all__ = ["BaseExtractor", "ConfigExtractor"]


class ConfigExtractor(BaseExtractor):
    """Extractor generic cấu hình qua extractor.json.

    Toàn bộ selector được truyền vào từ config, không hardcode theo site.
    """

    def __init__(self, config: dict):
        self.name = config.get("name", "")
        self.domains = config.get("domains", [])
        self.referer = config.get("referer")

        self.title_selector = config.get("title_selector")
        self.thumb_selector = config.get("thumb_selector")
        self.chapter_row_selector = config.get("chapter_row_selector")
        self.update_time_selector = config.get("update_time_selector")
        self.image_selector = config.get("image_selector")
        self.wait_selectors = config.get("wait_selectors") or []

    async def extract(self, page) -> dict:
        return await page.evaluate(
            """
            ({titleSel, thumbSel, rowSel, updateTimeSel}) => {
                const title =
                    (document.querySelector(titleSel)?.innerText || "")
                    .replace(/\\s+/g, ' ')
                    .trim();
                const el = document.querySelector(thumbSel);
                const thumb = el?.src || el?.content || "";
                const times = updateTimeSel
                    ? Array.from(document.querySelectorAll(updateTimeSel))
                        .map(el => el.innerText.trim() || "")
                    : [];
                const chapters = Array.from(document.querySelectorAll(rowSel))
                .map((row, i) => {
                    const a = row.querySelector("a");
                    return {
                        title: (a?.innerText || "").replace(/\\s+/g, ' ').trim(),
                        url: a?.href || "",
                        update_time: times[i] || ""
                    };
                })
                .filter(x => x.title && x.url);
                return { title, thumb, chapters };
            }
            """,
            {
                "titleSel": self.title_selector,
                "thumbSel": self.thumb_selector,
                "rowSel": self.chapter_row_selector,
                "updateTimeSel": self.update_time_selector,
            },
        )
