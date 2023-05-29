from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, AsyncIterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from mediasub import Source
from mediasub.utils import normalize


@dataclass(kw_only=True)
class WebtoonInternal:
    fetched: bool = False
    url_name: str | None = None


@dataclass(kw_only=True)
class Webtoon:
    eid: int
    name: str
    author: str
    likes: str | None = None
    genre: str
    category: str | None
    url: str
    thumbnail: str | None = None
    description: str | None = None

    internal: WebtoonInternal = field(repr=False, default_factory=WebtoonInternal)

    @property
    def id(self) -> str:
        return f"WEBTOON/{self.eid}"


@dataclass(kw_only=True)
class WebtoonEpisode:
    webtoon: Webtoon
    name: str
    number: int
    language: str | None
    url: str

    internal: Any = None

    def __post_init__(self):
        self.db_identifier = f"{normalize(self.webtoon.name)}/{self.number}"


class WebtoonSource(Source["WebtoonEpisode"]):
    name = "Webtoons"
    url = _base_url = "https://www.webtoons.com/"

    _cookies = {"pagGDPR": "true"}

    _webtoon_odl_url_ft = urljoin(_base_url, "/episodeList?titleNo={eid}")
    _canva_old_url_ft = urljoin(_base_url, "/challenge/episodeList?titleNo={eid}")

    _webtoon_viewer_url_ft = urljoin(_base_url, "/fr/{category}/{url_name}/anything/viewer")
    _webtoon_url_reg = re.compile(
        "".join((_base_url, r"fr/(?P<category>[a-z]+)/(?P<url_name>[a-z0-9-]+)/list\?title_no=(?P<eid>[0-9]+)"))
    )

    async def get_recent(self, limit: int = 25) -> Iterable[WebtoonEpisode]:
        return []

    async def search(self, query: str) -> list[Webtoon]:
        results: list[Webtoon] = []
        full_url = f"https://www.webtoons.com/fr/search?keyword={query}"
        req = await self.client.get(full_url, cookies=self._cookies)
        soup = BeautifulSoup(req.content, features="lxml")

        originals = soup.find("ul", {"class": "card_lst"})
        if originals is not None:
            for item in originals.findAll("li"):  # type: ignore
                eid = int(item.a["href"].split("?")[-1].split("=")[-1])  # type: ignore
                name = str(item.find("p", {"class": "subj"}).getText())  # type: ignore
                author = str(item.find("p", {"class": "author"}).getText())  # type: ignore
                likes = str(item.find("em", {"class": "grade_num"}).getText())  # type: ignore
                genre = str(item.find("span", {"class": "genre"}).getText())  # type: ignore
                results.append(
                    Webtoon(
                        name=name,
                        url=self._webtoon_odl_url_ft.format(eid=eid),
                        eid=eid,
                        author=author,
                        likes=likes,
                        genre=genre,
                        category=None,
                    )
                )

        canvas = soup.find("div", {"class": "challenge_lst"})
        if canvas is not None and canvas.ul is not None:  # type: ignore
            canvas = canvas.ul  # type: ignore
            for item in canvas.findAll("li"):  # type: ignore
                eid = int(item.a["href"].split("?")[-1].split("=")[-1])  # type: ignore
                name = str(item.find("p", {"class": "subj"}).getText())  # type: ignore
                author = str(item.find("p", {"class": "author"}).getText())  # type: ignore
                genre = str(item.find("p", {"class": "genre"}).getText())  # type: ignore
                results.append(
                    Webtoon(
                        name=name,
                        url=self._canva_old_url_ft.format(eid=eid),
                        eid=eid,
                        author=author,
                        genre=genre,
                        category="challenge",
                    )
                )

        return results

    async def _fetch_webtoon(self, webtoon: Webtoon) -> None:
        if not webtoon.internal.fetched:
            res = await self.client.get(webtoon.url, cookies=self._cookies, follow_redirects=True)
            url = str(res.url)
            print(url)
            match = self._webtoon_url_reg.match(url)
            if not match:
                raise ValueError(f"Invalid webtoon url: {webtoon.url}")

            webtoon.url = url
            webtoon.category = match.group("category")

            webtoon.internal.url_name = match.group("url_name")
            webtoon.internal.fetched = True

    async def _get_images_urls(self, webtoon: Webtoon, episode_number: int) -> AsyncIterable[str]:
        await self._fetch_webtoon(webtoon)

        res = await self.client.get(
            self._webtoon_viewer_url_ft.format(category=webtoon.category, url_name=webtoon.internal.url_name),
            cookies=self._cookies,
            params={"title_no": webtoon.eid, "episode_no": episode_number},
            follow_redirects=True,
        )

        soup = BeautifulSoup(res.content, features="lxml")
        content = soup.find("div", {"id": "content"})
        imagelist = content.find("div", {"id": "_imageList"})  # type: ignore

        if imagelist is not None:
            for img in imagelist.findAll("img", {"class": "_images"}):  # type: ignore
                yield img["data-url"]

    async def get_images(self, webtoon: Webtoon, episode_number: int) -> AsyncIterable[io.BytesIO]:
        async for img_url in self._get_images_urls(webtoon, episode_number):
            res = await self.client.get(
                img_url,
                cookies=self._cookies,
                follow_redirects=True,
                headers={
                    "Referer": self._webtoon_viewer_url_ft.format(
                        category=webtoon.category, url_name=webtoon.internal.url_name
                    )
                },
            )
            yield io.BytesIO(res.content)
