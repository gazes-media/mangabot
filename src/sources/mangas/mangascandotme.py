import re
from typing import Any, override

from .scanvfdotnet import InternalData, PageRaw, ScanVFDotNet


class MangaScanDotMe(ScanVFDotNet):
    name = "MangaScan"
    url = _base_url = "http://manga-scan.me/"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        base_url = self._base_url.rstrip("/")

        self._chapter_url_fmt = base_url + "/manga/{manga_name}/{chapter_nb}"
        self._images_url_fmt = base_url + "/uploads/manga/{manga_name}/chapters/{chapter_nb}/{page_image}"

        self._chapter_url_reg = re.compile(base_url + r"/manga/(?P<manga_name>[\w\-.]+)/(?P<number>\d+\.?\d*)")
        self._manga_url_reg = re.compile(base_url + r"/manga/(?P<manga_name>[\w\-.]+)")

        self.headers.update(
            {
                "Referer": self._base_url,
                "Authority": "scansmangas.me",
            }
        )

    def _get_page_url(self, internal: InternalData, chapter: str, page: PageRaw) -> str:
        del internal, chapter  # unused
        return page["page_image"]

    @override
    def _get_filename(self, page: PageRaw) -> str:
        return page["page_image"].split("/")[-1]
