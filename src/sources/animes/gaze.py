import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin

import feedparser
import httpx
from mediasub import SourceDown
from mediasub._logger import BraceMessage as __

from .base import Anime, AnimeSource, Episode

logger = logging.getLogger(__name__)


@dataclass
class AnimeInternal:
    id: int
    lang: str


class Gaze(AnimeSource):
    name = "Gaze"
    url = "https://deril-fr.github.io/"
    _base_url = "https://api.ketsuna.com/"

    _rss_url = urljoin(_base_url, "animes/rss")
    _all_url = urljoin(_base_url, "animes")
    _anime_url = "https://deril-fr.github.io/anime/{lang}/{anime_id}"
    _episode_url = "https://deril-fr.github.io/anime/{lang}/{anime_id}/episode/{episode}"

    _link_regex = re.compile(
        r"https://deril-fr.github.io/anime/(?P<lang>[^/]+)/(?P<anime_id>\d+)/episode/(?P<episode>\d+)"
    )

    search_fields = {"title_english": 2, "title_romanji": 2, "title_french": 2, "others": 1}

    def _get_episode_from_rss_item(self, item: Any) -> Episode:
        logger.debug(__("Extracting infos from : {}", item.link))

        link_match = self._link_regex.match(item.link)
        if not link_match:
            raise ValueError(f"Invalid link: {item.link}")

        anime = Anime(
            name=item.title,
            url=self._anime_url.format(lang=link_match["lang"], anime_id=link_match["anime_id"]),
            internal=AnimeInternal(id=int(link_match["anime_id"]), lang=link_match["lang"]),
        )

        return Episode(
            anime=anime,
            name=item.description,
            number=int(link_match["episode"]),
            language=link_match["lang"],
            url=item.link,
        )

    async def get_recent(self, limit: int = 25) -> Iterable[Episode]:
        try:
            res = await self.client.get(self._rss_url)
        except httpx.HTTPError as e:
            raise SourceDown(e) from e
        feed: Any = feedparser.parse(res.text)

        return (self._get_episode_from_rss_item(item) for item in feed.entries[:limit])

    def _get_anime_from_json(self, raw: Any) -> Anime:
        return Anime(
            name=raw["title"],
            url=self._anime_url.format(lang=raw["lang"], anime_id=raw["id"]),
            internal=AnimeInternal(id=raw["id"], lang=raw["lang"]),
            search_keywords={
                key: raw[key] for key in ("title_english", "title_romanji", "title_french", "others") if raw.get(key)
            },
            score=raw["score"],
            popularity=raw["popularity"],
            genres=raw["genres"],
            thumbnail=raw["url_image"],
            language=raw["lang"],
        )

    async def get_animes(self) -> Iterable[Anime]:
        res = await self.client.get(self._all_url)

        return (self._get_anime_from_json(raw) for raw in res.json())
