from .hentaivnx import HentaivnxExtractor


class HentaivnrealExtractor(HentaivnxExtractor):
    domains = ["hentaivnreal"]
    referer = "https://www.hentaivnreal.com/"

    title_selector = ".page-info > h1 > a"
    thumb_selector = ".page-ava img"
    chapter_row_selector = "#chuong .listing tr"
    chapter_time_selector = "td + td"

    wait_selectors = [title_selector, chapter_row_selector]
    image_selector = "#image img"
