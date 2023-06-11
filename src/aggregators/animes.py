import asyncio
from collections.abc import Sequence
from typing import TypeAlias

from discord.app_commands import Choice
from lunr.builder import Builder
from lunr.index import Index
from lunr.stemmer import stemmer
from lunr.trimmer import trimmer

from constants import ANIME_CHANNEL
from sources.animes.base import Anime, AnimeSource

from .base import SourceAggregator

CacheT: TypeAlias = dict[AnimeSource, dict[str, Anime]]


class AnimeAggregator(SourceAggregator[AnimeSource]):
    channel_id = ANIME_CHANNEL

    def __init__(self, *sources: AnimeSource):
        super().__init__(*sources)
        self.idx: Index | None = None
        self.cache: CacheT = {}

    async def refresh(self):
        _cache: list[list[Anime]] = await asyncio.gather(*(src.get_animes() for src in self.sources))

        builder = Builder()
        builder.pipeline.add(trimmer)
        builder.search_pipeline.add(stemmer)
        builder.ref("id")
        builder.field("name", boost=3)
        builder.field("search_keywords", boost=2)

        self.cache = {s: {} for s in self.sources}
        tmp = set[str]()
        for i, animes in enumerate(_cache):
            for anime in animes:
                self.cache[self.sources[i]][anime.id] = anime
                if anime.id not in tmp:
                    tmp.add(anime.id)
                    builder.add(
                        dict(id=anime.id, name=anime.name, search_keywords=anime.search_keywords),
                        dict(boost=max(anime.popularity, 1)),
                    )

        self.idx = builder.build()

    async def search(self, query: str) -> Sequence[Anime]:
        results: list[tuple[Anime, int]]
        if len(query) < 3:
            return []

        results = self.idx.search(query)

        return [
            Choice(name=f"{anime.name[:80] + '…' * (len(anime.name) > 80)} ({anime.language})", value=anime.id)
            for res in results
            if (anime := (await self.retrieve(res["ref"]))[0]) or True
        ][:25]

    def concat_contents(self, contents: list[Anime]) -> Anime:
        return contents[0]  # TODO(airo.pi_) if multiple sources

    async def retrieve(self, _id: str) -> tuple[Anime, Sequence[tuple[AnimeSource, Anime]]]:
        sources: list[AnimeSource] = [s for s in self.sources if _id in self.cache[s]]
        contents: list[Anime] = [self.cache[s][_id] for s in sources]

        return self.concat_contents(contents), tuple(zip(sources, contents))
