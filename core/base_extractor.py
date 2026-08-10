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
    chapter_time_selector: str = None

    image_selector: str = None

    def matches(self, url: str) -> bool:
        return any(d in url for d in self.domains)

    @abstractmethod
    async def extract(self, page) -> dict:
        raise NotImplementedError

    def parse_images(self, html: str) -> List[str]:
        """Mặc định dùng image_selector. Site nào cần logic khác (data-src, regex...)
        thì override hẳn method này, không cần set image_selector."""
        if not self.image_selector:
            raise NotImplementedError(
                f"{self.__class__.__name__} chưa khai báo image_selector hoặc chưa override parse_images()"
            )
        soup = BeautifulSoup(html, "lxml")
        return [
            img["src"] for img in soup.select(self.image_selector)
            if img.get("src", "").startswith("http")
        ]
