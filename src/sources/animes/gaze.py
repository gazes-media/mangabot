import itertools
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin

import feedparser
import httpx
from async_lru import alru_cache
from mediasub import SourceDown
from mediasub.source import LastPollContext
from mediasub.utils import normalize

from sources import Content, ExtendedSource, Series
from utils import BraceMessage as __

logger = logging.getLogger(__name__)


@dataclass
class AnimeInternal:
    id: int
    lang: str | None = None


class Gazes(ExtendedSource):
    name = "Gazes"  # type: ignore  # TODO
    url = "https://gazes.fr/"  # type: ignore  # TODO
    _base_url = "https://api.gazes.fr/anime/"

    _rss_url = urljoin(_base_url, "animes/rss")
    _seasons_url = urljoin(_base_url, "animes/seasons")
    _anime_url = "https://gazes.fr/anime/{anime_id}"
    _episode_url = "https://gazes.fr/anime/{anime_id}/episode/{episode}"

    _link_regex = re.compile(r"https://gazes.fr/anime/(?P<anime_id>\d+)/episode/(?P<episode>\d+)")

    search_fields = {"title_english": 2, "title_romanji": 2, "title_french": 2, "others": 1}

    async def poll(self, last_poll_ctx: LastPollContext | None = None) -> Iterable[Content]:
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
                    normalize(item.title),
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
        raw_vf = await self._fetch_seasons("vf")
        raw_vostfr = await self._fetch_seasons("vostfr")

        def parse_raw(raw: dict[str, Any], lang: str) -> Series:
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
