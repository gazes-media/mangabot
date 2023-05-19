import re
from typing import Any, Iterable
from urllib.parse import urljoin

import feedparser
from mediasub.models import Chapter, Page

from sources.scans.scanvfdotnet import PageRawData, ScanVFDotNet


class MangaScanDotWS(ScanVFDotNet):
    name = "manga-scan.ws"

    _base_url = "https://manga-scan.ws/"
    _rss_url = urljoin(_base_url, "feed")
    _images_url = "https://scansmangas.me/scans/"
    _search_url = urljoin(_base_url, "search")

    _link_scrap_reg = re.compile(
        r"https://manga-scan\.ws/manga/"
        r"(?P<manga_name>[\w\-.]+)/"
        r"(?P<chapter>(?P<number>\d+)(?:\.(?P<sub_number>\d+))?)"
    )

    async def _get_recent(self, limit: int, before: int | None = None) -> Iterable[Chapter]:
        if before is None:
            before = 0
        feed: Any = feedparser.parse(self._rss_url)

        return (self._get_chapter_from_rss_item(item) for item in feed.entries[before : limit + before])

    def _page_from_raw(self, chapter: Chapter, raw: dict[str, Any]) -> Page:
        url = raw["page_image"]
        return Page(
            chapter=chapter,
            number=int(raw["page_slug"]),
            url=url,
            raw_data=PageRawData(filename=raw["page_image"].split("/")[-1]),
        )
