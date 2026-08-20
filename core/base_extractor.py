from abc import ABC, abstractmethod
from typing import Iterable, List
from bs4 import BeautifulSoup


class BaseExtractor(ABC):
    domains: Iterable[str] = ()
    wait_selectors: Iterable[str] = ()

    referer: str = None

    title_selector: str = None
    thumb_selector: str = None
    chapter_row_selector: str = None
    update_time_selector: str = None

    image_selector: str = None

    def matches(self, url: str) -> bool:
        return any(d in url for d in self.domains)

    @abstractmethod
    async def extract(self, page) -> dict:
        raise NotImplementedError

    def parse_images(self, html: str) -> List[str]:
        """Mặc định dùng image_selector. Ưu tiên data-src (lazy-load), fallback src.
        Site nào cần logic khác (regex...) thì override hẳn method này."""
        if not self.image_selector:
            raise NotImplementedError(
                f"{self.__class__.__name__} chưa khai báo image_selector hoặc chưa override parse_images()"
            )
        soup = BeautifulSoup(html, "lxml")
        urls = []
        for img in soup.select(self.image_selector):
            url = img.get("data-src") or img.get("data-original") or img.get("src") or ""
            url = url.strip()
            if url.startswith("http"):
                urls.append(url)
        return urls
