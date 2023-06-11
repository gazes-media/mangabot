from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TypeAlias

from discord.app_commands import Choice
from lunr.builder import Builder
from lunr.index import Index
from lunr.query import Query, QueryPresence
from lunr.stemmer import stemmer
from lunr.tokenizer import Tokenizer
from lunr.trimmer import trimmer

from constants import MANGA_CHANNEL
from sources.mangas.base import Manga, MangaSource
from utils import hash_id

from .base import RetrieveType, SourceAggregator

CacheType: TypeAlias = dict[MangaSource, dict[str, Manga]]


class MangaAggregator(SourceAggregator[MangaSource]):
    channel_id = MANGA_CHANNEL
    idx: Index

    def __init__(self, *sources: MangaSource):
        super().__init__(*sources)
        self.cache: CacheType = {}

    async def refresh(self):
        _cache: list[list[Manga]] = await asyncio.gather(*(src.get_mangas() for src in self.sources))

        builder = Builder()
        builder.pipeline.add(trimmer)
        builder.search_pipeline.add(stemmer)
        builder.ref("id")
        builder.field("name", boost=3)

        self.cache = {s: {} for s in self.sources}
        tmp = set[str]()
        for i, mangas in enumerate(_cache):
            for manga in mangas:
                hashed = hash_id(manga.id)
                self.cache[self.sources[i]][hashed] = manga
                if manga.id not in tmp:
                    tmp.add(manga.id)
                    builder.add(
                        dict(id=hashed, name=manga.name),
                    )

        self.idx = builder.build()

    async def search(self, query: str) -> Sequence[Choice[str]]:
        # TODO(airo.pi_): Manga search and Anime search are almost identical, so we should probably refactor this
        if len(query) < 3:
            return []

        query_obj = Query(self.idx.fields)
        for token in Tokenizer(query):
            query_obj.term(str(token), presence=QueryPresence.REQUIRED, wildcard=Query.WILDCARD_TRAILING)

        results = self.idx.query(query_obj)

        # the "tmp" variable is None or a tuple, and we use a tricky "or" with another walrus operator to set "anime"
        # to the Anime
        return [
            Choice(name=f"{manga.name[:90] + '…' * (len(manga.name) > 90)}", value=manga.id)
            for res in results
            if (tmp := await self.retrieve(_hash=res["ref"])) and (manga := tmp[0])
        ][:25]

    def concat_contents(self, contents: list[Manga]) -> Manga:
        return contents[0]

    async def retrieve(
        self, *, _id: str | None = None, _hash: str | None = None
    ) -> RetrieveType[Manga, MangaSource] | None:
        if _hash is None:
            assert _id is not None
            _hash = hash_id(_id)

        sources: list[MangaSource] = [s for s in self.sources if _hash in self.cache[s]]
        if not sources:
            return None

        contents: list[Manga] = [self.cache[s][_hash] for s in sources]

        return self.concat_contents(contents), tuple(zip(sources, contents))
