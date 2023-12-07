import asyncio
import itertools
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Iterable
from urllib.parse import urljoin

import feedparser
import httpx
from async_lru import alru_cache
from mediasub import SourceDown
from mediasub.source import LastPullContext
from mediasub.utils import normalize

from sources import Content, Download, DownloadInProgress, DownloadUrl, ExtendedSource, Series
from utils import BraceMessage as __

logger = logging.getLogger(__name__)


@dataclass
class InternalData:
    id: int


class Gazes(ExtendedSource):
    name = "Gazes"  # type: ignore  # TODO
    url = "https://gazes.fr/"  # type: ignore  # TODO
    supports_download = True
    _base_url = "https://api.gazes.fr/anime/"

    _rss_url = urljoin(_base_url, "animes/rss")
    _seasons_url = urljoin(_base_url, "animes/seasons")
    _anime_url = "https://gazes.fr/anime/{anime_id}"
    _episode_url = "https://gazes.fr/anime/{anime_id}/episode/{episode}"

    _link_regex = re.compile(r"https://gazes.fr/anime/(?P<anime_id>\d+)/episode/(?P<episode>\d+)")

    _download_url_base = "https://animedl.airopi.dev"
    _download_invoke_url = _download_url_base + "/download/{anime_id}/{episode}/{lang}"

    search_fields = {"title_english": 2, "title_romanji": 2, "title_french": 2, "others": 1}

    def __init__(self):
        super().__init__()
        # cache[series_id][normalized(season)] -> InternalData
        self._cache: dict[str, dict[str, InternalData]] = {}
        # _conversions[ref] -> url
        self._conversions: dict[str, str]

    async def pull(self, last_pull_ctx: LastPullContext | None = None) -> Iterable[Content]:
        try:
            res = await self.client.get(self._rss_url)
        except httpx.HTTPError as e:
            raise SourceDown(e) from e
        feed: Any = feedparser.parse(res.text)

        async def parse(item: Any) -> Content:
            logger.debug(__("Extracting infos from : {}", item.link))

            link_match = self._link_regex.match(item.link)
            if not link_match:
                raise ValueError(f"Invalid link: {item.link}")

            anime_raw = await self._get_anime(int(link_match["anime_id"]))

            content = Content(
                type="anime",
                id_name=normalize(anime_raw["title"]),
                identifiers=(
                    normalize(item.title),  # title is the season name
                    str(link_match["episode"]),
                ),
                lang="vostfr",  # TODO: Add lang support
                fields={
                    "episode": link_match["episode"],
                    "season": item.title,
                    "url": item.link,
                },
            )

            return content

        return [await parse(item) for item in feed.entries[:25]]

    @alru_cache
    async def _fetch_seasons(self, lang: str | None = None) -> list[dict[str, Any]]:
        params = {}
        if lang is not None:
            params["lang"] = lang
        res = await self.client.get(self._seasons_url, params=params)
        if res.status_code != 200 or (raw := res.json())["success"] is False:
            raise SourceDown()
        return raw["data"]

    async def _fetch_anime(self, anime_id: str) -> dict[str, Any]:
        res = await self.client.get(self._seasons_url, params={"id": anime_id})
        if res.status_code != 200 or (raw := res.json())["success"] is False:
            raise SourceDown()
        return raw["data"][0]

    async def _get_anime(self, anime_id: int) -> dict[str, Any]:
        seasons = await self._fetch_seasons()
        return next(season for season in seasons if anime_id in season["ids"])

    async def get_all(self) -> Iterable[Series]:
        self._fetch_seasons.cache_clear()
        self._cache = {}
        raw_vf = await self._fetch_seasons("vf")
        raw_vostfr = await self._fetch_seasons("vostfr")

        def parse_raw(raw: dict[str, Any], lang: str) -> Series:
            seasons = self._cache.setdefault(normalize(raw["title"]), {})
            for season in raw["seasons"]:
                seasons[normalize(season["fiche"]["title"])] = InternalData(id=int(season["fiche"]["id"]))

            return Series(
                id_name=normalize(raw["title"]),
                name=raw["title"],
                aliases=[raw[field] for field in ("title_english", "title_romanji", "title_french") if raw.get(field)],
                genres=raw["genres"],
                thumbnail=raw.get("cover_url"),
                lang=lang,
                type="anime",
            )

        return itertools.chain(
            (parse_raw(raw, "vf") for raw in raw_vf),
            (parse_raw(raw, "vostfr") for raw in raw_vostfr),
        )

    async def download(self, ref: str) -> AsyncGenerator[Download, None]:
        print(ref)
        _, series_id, lang, season, episode = ref.split("/")
        internal_data = self._cache[series_id][season]

        url = self._download_invoke_url.format(anime_id=internal_data.id, episode=episode, lang=lang)
        response = await self.client.get(url)

        if response.status_code != 200:
            raise SourceDown()
        data = response.json()
        while data["status"] in ("started", "in_progress"):
            yield DownloadInProgress(data.get("progress") or 0, data.get("estimated_remaining_time"))
            await asyncio.sleep(2)
            response = await self.client.get(url)
            if response.status_code != 200:
                raise SourceDown()
            data = response.json()

        if data["status"] == "error":
            raise SourceDown()

        yield DownloadUrl(urljoin(self._download_url_base, data["result"]))
