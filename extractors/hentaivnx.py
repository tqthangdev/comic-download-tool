from .base import BaseExtractor


class HentaivnxExtractor(BaseExtractor):
    domains = ["hentaivnx"]
    referer = "https://www.hentaivnx.com/"

    title_selector = "#item-detail .title-detail"
    thumb_selector = "#item-detail .col-image img"
    chapter_row_selector = "#nt_listchapter .row"
    chapter_time_selector = ".col-xs-4"

    wait_selectors = [title_selector, chapter_row_selector]
    image_selector = ".reading-detail .page-chapter img"

    async def extract(self, page) -> dict:
        return await page.evaluate(
            """
            ({titleSel, thumbSel, rowSel, timeSel}) => {
                const title =
                    (document.querySelector(titleSel)?.innerText || "")
                    .replace(/\\s+/g, ' ')
                    .trim();
                const thumb = document.querySelector(thumbSel)?.src || "";
                const chapters = Array.from(document.querySelectorAll(rowSel))
                .map(row => {
                    const update_time = row.querySelector(timeSel)?.innerText.trim() || "";
                    const a = row.querySelector("a");
                    return {
                        title: (a?.innerText || "").replace(/\\s+/g, ' ').trim(),
                        url: a?.href || "",
                        update_time: update_time
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
                "timeSel": self.chapter_time_selector,
            },
        )
