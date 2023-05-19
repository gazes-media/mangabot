import json
from typing import Any, Iterable

from bs4 import BeautifulSoup
from mediasub.models import Chapter, Page

from sources.scans.mangascandotws import MangaScanDotWS


class ScanFRDotOrg(MangaScanDotWS):
    name = "www.scan-fr.org"
    _base_url = "https://www.scan-fr.org/"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._images_url = "https://opfrcdn.xyz/uploads/manga/"

    async def _get_pages(self, chapter: Chapter) -> Iterable[Page]:
        soup = BeautifulSoup((await self.client.get(chapter.url)).text, features="html.parser")
        script = soup.select_one("body > script:nth-child(10)")

        if not script:
            raise ValueError("Error when looking for the script tag. URL: {}", chapter.url)

        match = self._script_extract_reg.search(script.text)
        if not match:
            raise ValueError("Error when looking for the script content. URL: {}", chapter.url)

        return [self._page_from_raw(chapter, page) for page in json.loads(match.group(1))]
