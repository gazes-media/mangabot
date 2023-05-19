import logging
import re
from typing import Any, Iterable, TypedDict
from urllib.parse import urljoin

import feedparser
from mediasub._logger import BraceMessage as __
from mediasub.models import Anime, AnimeSource, Episode

logger = logging.getLogger(__name__)


class AnimeRawData(TypedDict):
    id: int
    lang: str


class EpisodeRawData(TypedDict):
    pass


class GazeSource(AnimeSource):
    name = "gaze"

    _base_url = "https://api.ketsuna.com/"
    _rss_url = urljoin(_base_url, "animes/rss")
    _all_url = urljoin(_base_url, "animes")
    _anime_url = "https://deril-fr.github.io/anime/{lang}/{anime_id}"
    _episode_url = "https://deril-fr.github.io/anime/{lang}/{anime_id}/episode/{episode}"

    _link_regex = re.compile(
        r"https://deril-fr\.github\.io/anime/(?P<lang>[^/]+)/(?P<anime_id>\d+)/episode/(<?P<episode>\d+)"
    )

    def _get_episode_from_rss_item(self, item: Any) -> Episode:
        logger.debug(__("Extracting infos from : {}", item.link))

        link_match = self._link_regex.match(item.link)
        if not link_match:
            raise ValueError(f"Invalid link: {item.link}")

        anime = Anime(
            name=item.title,
            url=self._anime_url.format(lang=link_match["lang"], anime_id=link_match["anime_id"]),
            raw_data=AnimeRawData(id=int(link_match["anime_id"]), lang=link_match["lang"]),
        )

        return Episode(
            anime=anime,
            name=item.description,
            number=int(link_match["episode"]),
            language=link_match["lang"],
            url=item.link,
        )

    async def _get_recent(self, limit: int, before: int | None = None) -> Iterable[Episode]:
        if before is None:
            before = 0
        feed: Any = feedparser.parse(self._rss_url)

        return (self._get_episode_from_rss_item(item) for item in feed.entries[before : limit + before])

    async def _search(self, query: str) -> Iterable[Anime]:
        raise NotImplementedError

    def _get_anime_from_json(self, raw: Any) -> Anime:
        return Anime(
            name=raw["title"],
            url=self._anime_url.format(lang=raw["lang"], anime_id=raw["id"]),
            raw_data=AnimeRawData(id=raw["id"], lang=raw["lang"]),
        )

    async def _all(self) -> Iterable[Anime]:
        res = await self.client.get(self._all_url)

        return (self._get_anime_from_json(raw) for raw in res.json())

    async def _get_episodes(self, anime: Anime) -> Iterable[Episode]:
        raise NotImplementedError
