import json
import re
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from mediasub.models import Chapter, Page

from sources.scans.mangascandotws import MangaScanDotWS


class ScanFRDotOrg(MangaScanDotWS):
    name = "www.scan-fr.org"

    _base_url = "https://www.scan-fr.org/"
    _rss_url = urljoin(_base_url, "feed")
    _images_url = "https://opfrcdn.xyz/uploads/manga/"
    _search_url = urljoin(_base_url, "search")

    _link_scrap_reg = re.compile(
        r"https://www.scan-fr.org/manga/"
        r"(?P<manga_name>[\w\-.]+)/"
        r"(?P<chapter>(?P<number>\d+)(?:\.(?P<sub_number>\d+))?)"
    )

    async def _get_pages(self, chapter: Chapter) -> Iterable[Page]:
        soup = BeautifulSoup((await self.client.get(chapter.url)).text, features="html.parser")
        script = soup.select_one("body > script:nth-child(10)")

        if not script:
            raise ValueError("Error when looking for the script tag. URL: {}", chapter.url)

        match = self._script_extract_reg.search(script.text)
        if not match:
            raise ValueError("Error when looking for the script content. URL: {}", chapter.url)

        return [self._page_from_raw(chapter, page) for page in json.loads(match.group(1))]
