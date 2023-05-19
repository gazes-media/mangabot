import re
from typing import Any, Iterable

import feedparser
from mediasub.models import Chapter, Page

from sources.scans.scanvfdotnet import PageRawData, ScanVFDotNet


class MangaScanDotWS(ScanVFDotNet):
    name = "manga-scan.ws"

    _base_url = "https://manga-scan.ws/"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._images_url = "https://scansmangas.me/scans/"
        self._link_scrap_reg = re.compile(
            rf"{self._base_url}manga/"
            r"(?P<manga_name>[\w\-.]+)/"
            r"(?P<chapter>(?P<number>\d+)(?:\.(?P<sub_number>\d+))?)"
        )
        self._manga_link_reg = re.compile(rf"{self._base_url}manga/(?P<manga_name>[\w\-.]+)")

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
