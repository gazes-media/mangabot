import re
from typing import Any

from .scanvfdotnet import ScanVFDotNet


class MangaScanDotMe(ScanVFDotNet):
    name = "MangaScan"
    url = _base_url = "http://manga-scan.me/"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        # self._images_url = "https://scansmangas.me/scans/"
        self._link_scrap_reg = re.compile(rf"{self._base_url}manga/(?P<manga_name>[\w\-.]+)/(?P<number>\d+(?:\.\d+)?)")
        self._manga_link_reg = re.compile(rf"{self._base_url}manga/(?P<manga_name>[\w\-.]+)")

    # def _page_from_raw(self, chapter: Chapter, raw: dict[str, Any]) -> Page:
    #     url = raw["page_image"]
    #     return Page(
    #         chapter=chapter,
    #         number=int(raw["page_slug"]),
    #         url=url,
    #         internal=PageInternal(filename=raw["page_image"].split("/")[-1]),
    #     )
