import io
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup, Tag
from httpx._types import QueryParamTypes, URLTypes
from mediasub import SourceDown
from mediasub._logger import BraceMessage as __

from .base import Chapter, Manga, MangaSource, Page

logger = logging.getLogger(__name__)


@dataclass
class MangaInternal:
    name: str


@dataclass
class ChapterInternal:
    ref: str


@dataclass
class PageInternal:
    filename: str


class ScanVFDotNet(MangaSource):
    name = "ScanVF"
    url = _base_url = "https://www.scan-vf.net/"

    _script_selector = "body > div.container-fluid > script"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._rss_url = urljoin(self._base_url, "feed")
        self._all_url = urljoin(self._base_url, "changeMangaList?type=text")
        self._images_url = urljoin(self._base_url, "uploads/manga/")
        self._search_url = urljoin(self._base_url, "search")

        self._script_extract_reg = re.compile(r"var pages = (\[.+\])", re.MULTILINE)
        self._link_scrap_reg = re.compile(
            f"{self._base_url}"
            r"(?P<manga_name>[\w\-.]+)/"
            r"(?P<chapter>chapitre-(?P<number>\d+)(?:\.(?P<sub_number>\d+))?)"
        )
        self._manga_link_reg = re.compile(rf"{self._base_url}(?P<manga_name>[\w\-.]+)")
        self._title_scrap_reg = re.compile(r"(?P<manga_name>[^#]+) #(?P<chapter>\d+)")

    async def _get(self, url: URLTypes, *, params: QueryParamTypes | None = None) -> httpx.Response:
        try:
            return await self.client.get(url, params=params)
        except httpx.HTTPError as e:
            raise SourceDown(e) from e

    def _get_chapter_from_rss_item(self, item: Any) -> Chapter:
        logger.debug(__("Extracting infos from : {}", item.link))

        # for user-friendly informations
        title_match = self._title_scrap_reg.match(item.title)
        if not title_match:
            raise ValueError(__("Error when reading the title : {}", item.title))

        # for url-friendly informations
        url_match = self._link_scrap_reg.search(item.link)
        if not url_match:
            raise ValueError(__("Error when reading the content : {}", item.content))

        manga = Manga(
            name=title_match["manga_name"],
            url=self._base_url + url_match["manga_name"],
            internal=MangaInternal(name=url_match["manga_name"]),
        )

        sub_number_raw = url_match["sub_number"]
        return Chapter(
            manga=manga,
            name=item.summary,
            number=int(url_match["number"]),
            language=item.content[0].language,
            url=item.link,
            sub_number=int(sub_number_raw) if sub_number_raw else None,
            internal=ChapterInternal(ref=url_match["chapter"]),
        )

    async def get_recent(self, limit: int = 25) -> Iterable[Chapter]:
        res = await self._get(self._rss_url)
        feed: Any = feedparser.parse(res.text)

        return (self._get_chapter_from_rss_item(item) for item in feed.entries[:limit])

    async def search(self, query: str) -> list[Manga]:
        results = await self._get(self._search_url, params={"query": query})

        return [
            Manga(
                name=result["value"],
                url=urljoin(self._base_url, result["data"]),
                internal=MangaInternal(name=result["data"]),
            )
            for result in results.json()["suggestions"]
        ]

    def _page_from_raw(self, chapter: Chapter, raw: dict[str, Any]) -> Page:
        url = urljoin(
            self._images_url,
            "/".join((chapter.manga.internal.name, "chapters", chapter.internal.ref, raw["page_image"])),
        )
        return Page(
            chapter=chapter,
            number=int(raw["page_slug"]),
            url=url,
            internal=PageInternal(filename=raw["page_image"]),
        )

    async def get_pages(self, chapter: Chapter) -> Iterable[Page]:
        soup = BeautifulSoup((await self.client.get(chapter.url)).text, features="html.parser")
        script = soup.select_one(self._script_selector)

        if not script:
            raise ValueError(f"Error when looking for the script tag. URL: {chapter.url}")

        match = self._script_extract_reg.search(script.text)
        if not match:
            raise ValueError(f"Error when looking for the script content. URL: {chapter.url}")

        return [self._page_from_raw(chapter, page) for page in json.loads(match.group(1))]

    def _chapter_from_tag(self, manga: Manga, chapter: Tag) -> Chapter:
        name_soup = chapter.select_one("em")
        url_soup = chapter.select_one("a")
        if name_soup is None or url_soup is None:
            raise ValueError("Error while parsing chapter from soup.")

        url = url_soup.attrs["href"]
        url_match = self._link_scrap_reg.match(url)

        if url_match is None:
            raise ValueError("Error while parsing chapter from soup.")

        raw_sub_number = url_match.group("sub_number")
        return Chapter(
            manga=manga,
            name=name_soup.text,
            number=int(url_match.group("number")),
            language=None,
            url=url_soup.attrs["href"],
            sub_number=int(raw_sub_number) if raw_sub_number else None,
            internal=ChapterInternal(ref=url_match.group("chapter")),
        )

    async def get_chapters(self, manga: Manga) -> list[Chapter]:
        res = await self._get(manga.url)
        soup = BeautifulSoup(res.text, features="html.parser")
        chapters = soup.select("body > div.wrapper > div > div:nth-child(1) > div > div:nth-child(7) > div > ul > li")
        chapters = [self._chapter_from_tag(manga, chapter) for chapter in chapters]
        return chapters

    def _manga_from_tag(self, tag: Tag) -> Manga:
        name_tag = tag.select_one("h6")
        assert name_tag is not None  # nosec: B101
        url = tag.attrs["href"]

        match = self._manga_link_reg.match(url)
        assert match is not None  # nosec: B101

        return Manga(
            name=name_tag.text,
            url=url,
            internal=MangaInternal(name=match["manga_name"]),
        )

    async def get_mangas(self) -> Iterable[Manga]:
        res = await self._get(self._all_url)
        soup = BeautifulSoup(res.text, features="html.parser")
        mangas_tag = soup.select("li > a")
        return (self._manga_from_tag(manga) for manga in mangas_tag)

    async def download_page(self, page: Page) -> tuple[str, io.BytesIO]:
        result = await self._get(page.url)
        return page.internal.filename, io.BytesIO(result.content)
