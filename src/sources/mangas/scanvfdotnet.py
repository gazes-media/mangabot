import io
import json
import logging
import re
import typing
from typing import Any, AsyncGenerator, Iterable, TypedDict

import feedparser
import httpx
from bs4 import BeautifulSoup, Tag
from httpx._types import QueryParamTypes, URLTypes
from mediasub import SourceDown
from mediasub._logger import BraceMessage as __
from mediasub.source import LastPullContext
from mediasub.utils import normalize

from sources import Content, DownloadBytes, ExtendedSource, Series

logger = logging.getLogger(__name__)


class PageRaw(TypedDict):
    page_slug: str
    page_image: str


class InternalData(TypedDict):
    url: str
    manga_name: str


class ScanVFDotNet(ExtendedSource):
    name = "ScanVF"  # type: ignore  # TODO
    url = _base_url = "https://www.scan-vf.net/"  # type: ignore  # TODO
    supports_download = True

    _script_selector = "body > div.container-fluid > script"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._cache: dict[str, InternalData] = {}

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

        self._script_extract_reg = re.compile(r"var pages = (\[.+\])", re.MULTILINE)

        base_url = self._base_url.rstrip("/")
        self._all_url = base_url + "/changeMangaList?type=text"
        self._rss_url = base_url + "/feed"

        self._chapter_url_fmt = base_url + "/{manga_name}/chapitre-{chapter_nb}"
        self._images_url_fmt = base_url + "/uploads/manga/{manga_name}/chapters/chapitre-{chapter_nb}/{page_image}"

        self._chapter_url_reg = re.compile(base_url + r"/(?P<manga_name>[\w\-.]+)/chapitre-(?P<number>\d+\.?\d*)")
        self._manga_url_reg = re.compile(base_url + r"/(?P<manga_name>[\w\-.]+)")

        self._title_scrap_reg = re.compile(r"(?P<manga_name>[^#]+) #\d+")

    async def _get(self, url: URLTypes, *, params: QueryParamTypes | None = None) -> httpx.Response:
        try:
            return await self.client.get(url, params=params, headers=self.headers)
        except httpx.HTTPError as e:
            raise SourceDown(e) from e

    @typing.override
    async def pull(self, last_pull_ctx: LastPullContext | None = None) -> Iterable[Content]:
        res = await self._get(self._rss_url)
        feed: Any = feedparser.parse(res.text)

        async def parse(item: Any) -> Content:
            logger.debug(__("Extracting infos from : {}", item.link))

            # for user-friendly informations
            title_match = self._title_scrap_reg.match(item.title)
            if not title_match:
                raise ValueError(__("Error when matching the title : {}", item.title))

            # for url-friendly informations
            url_match = self._chapter_url_reg.search(item.link)
            if not url_match:
                raise ValueError(__("Error when matching the url : {}", item.link))

            return Content(
                type="manga",
                id_name=normalize(title_match["manga_name"]),
                identifiers=(url_match["number"],),
                lang="fr",
                fields={
                    "chapter_nb": url_match["number"],
                    "url": item.link,
                    "chapter_name": item.summary,
                },
            )

        return [await parse(item) for item in feed.entries[:25]]

    @typing.override
    async def get_all(self) -> Iterable[Series]:
        self._cache.clear()

        res = await self._get(self._all_url)
        soup = BeautifulSoup(res.text, features="html.parser")
        mangas_tag = soup.select("li > a")

        def parse_tag(tag: Tag) -> Series:
            name_tag = tag.select_one("h6")
            match = self._manga_url_reg.match(tag.attrs["href"])
            assert match is not None  # nosec: B101
            assert name_tag is not None  # nosec: B101

            series = Series(
                id_name=normalize(name_tag.text),
                name=name_tag.text,
                lang="fr",
                type="manga",
            )
            self._cache[series.ref] = {
                "url": tag.attrs["href"],
                "manga_name": match["manga_name"],
            }
            return series

        return (parse_tag(tag) for tag in mangas_tag)

    @typing.override
    async def download(self, ref: str) -> AsyncGenerator[DownloadBytes, None]:
        *manga_ref, chapter = ref.split("/")
        internal: InternalData | None = self._cache.get("/".join(manga_ref))

        if internal is None:
            raise ValueError(f"Unknown manga {'/'.join(manga_ref)}")  # TODO: better error

        chapter_url = self._chapter_url_fmt.format(manga_name=internal["manga_name"], chapter_nb=chapter)
        raw_pages = await self._get_pages_raw(chapter_url)
        for page in raw_pages:
            filename = self._get_filename(page)
            page_url = self._get_page_url(internal, chapter, page)
            yield DownloadBytes(
                data=await self._download_page(page_url),
                filename=filename,
            )

    async def _get_pages_raw(self, chapter_url: str) -> Iterable[PageRaw]:
        soup = BeautifulSoup((await self.client.get(chapter_url)).text, features="html.parser")
        script = soup.select_one(self._script_selector)

        if not script:
            raise ValueError(f"Error when looking for the script tag. URL: {chapter_url}")

        match = self._script_extract_reg.search(script.text)
        if not match:
            raise ValueError(f"Error when looking for the script content. URL: {chapter_url}")

        return json.loads(match.group(1))

    async def _download_page(self, page_url: str) -> io.BytesIO:
        result = await self._get(page_url)
        return io.BytesIO(result.content)

    def _get_page_url(self, internal: InternalData, chapter: str, page: PageRaw) -> str:
        return self._images_url_fmt.format(
            manga_name=internal["manga_name"], chapter_nb=chapter, page_image=page["page_image"]
        )

    def _get_filename(self, page: PageRaw) -> str:
        return page["page_image"]
