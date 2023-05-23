import io
import json
import logging
import re
from typing import Any, Iterable, TypedDict
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup, Tag
from mediasub._logger import BraceMessage as __
from mediasub.models import Chapter, Manga, MangaSource, Page

logger = logging.getLogger(__name__)


class MangaRawData(TypedDict):
    name: str


class ChapterRawData(TypedDict):
    internal_ref: str


class PageRawData(TypedDict):
    filename: str


class ScanVFDotNet(MangaSource):
    name = "www.scan-vf.net"
    _base_url = "https://www.scan-vf.net/"

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
            raw_data=MangaRawData(name=url_match["manga_name"]),
        )

        sub_number_raw = url_match["sub_number"]
        return Chapter(
            language=item.content[0].language,
            manga=manga,
            name=item.summary,
            url=item.link,
            number=int(url_match["number"]),
            sub_number=int(sub_number_raw) if sub_number_raw else None,
            raw_data=ChapterRawData(internal_ref=url_match["chapter"]),
        )

    async def _get_recent(self, limit: int, before: int | None = None) -> Iterable[Chapter]:
        if before is None:
            before = 0
        res = await self.client.get(self._rss_url)
        feed: Any = feedparser.parse(res.text)

        return (self._get_chapter_from_rss_item(item) for item in feed.entries[before : limit + before])

    async def _search(self, query: str) -> list[Manga]:
        results = await self.client.get(self._search_url, params={"query": query})
        return [
            Manga(
                name=result["value"],
                url=urljoin(self._base_url, result["data"]),
                raw_data={
                    "name": result["data"],
                },
            )
            for result in results.json()["suggestions"]
        ]

    def _page_from_raw(self, chapter: Chapter, raw: dict[str, Any]) -> Page:
        manga_raw: MangaRawData = chapter.manga.raw_data
        chapter_raw: ChapterRawData = chapter.raw_data

        url = urljoin(
            self._images_url, "/".join((manga_raw["name"], "chapters", chapter_raw["internal_ref"], raw["page_image"]))
        )
        return Page(
            chapter=chapter,
            number=int(raw["page_slug"]),
            url=url,
            raw_data=PageRawData(filename=raw["page_image"]),
        )

    async def _get_pages(self, chapter: Chapter) -> Iterable[Page]:
        soup = BeautifulSoup((await self.client.get(chapter.url)).text, features="html.parser")
        script = soup.select_one("body > div.container-fluid > script")

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

        return Chapter(
            manga=manga,
            name=name_soup.text,
            number=int(url_match.group("number")),
            language=None,
            url=url_soup.attrs["href"],
            sub_number=int(v) if (v := url_match.group("sub_number")) else None,
            raw_data=ChapterRawData(internal_ref=url_match.group("chapter")),
        )

    async def _get_chapters(self, manga: Manga) -> list[Chapter]:
        res = await self.client.get(manga.url)
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
            raw_data=MangaRawData(name=match["manga_name"]),
        )

    async def _all(self) -> Iterable[Manga]:
        res = await self.client.get(self._all_url)
        soup = BeautifulSoup(res.text, features="html.parser")
        mangas_tag = soup.select("li > a")
        return (self._manga_from_tag(manga) for manga in mangas_tag)

    async def _download(self, target: Page) -> tuple[str, io.BytesIO]:
        result = await self.client.get(target.url)
        return target.raw_data["filename"], io.BytesIO(result.content)
