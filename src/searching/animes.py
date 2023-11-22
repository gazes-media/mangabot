import asyncio
import logging
from collections.abc import Sequence
from typing import Iterable, TypeAlias

from discord.app_commands import Choice
from lunr.builder import Builder
from lunr.index import Index
from lunr.query import Query, QueryPresence
from lunr.stemmer import stemmer
from lunr.tokenizer import Tokenizer
from lunr.trimmer import trimmer

from constants import ANIME_CHANNEL
from sources.animes.base import Anime, AnimeSource
from utils import BraceMessage as __, hash_id

from .base import Researcher, RetrieveType

CacheType: TypeAlias = dict[AnimeSource, dict[str, Anime]]

logger = logging.getLogger(__name__)


class AnimeResearcher(Researcher[AnimeSource]):
    channel_id = ANIME_CHANNEL
    idx: Index

    def __init__(self, *sources: AnimeSource):
        super().__init__(*sources)
        self.cache: CacheType = {}

    async def refresh(self):
        _cache: list[Iterable[Anime]] = []
        tasks = [src.get_animes() for src in self.sources]
        for coroutine in asyncio.as_completed(tasks):
            try:
                _cache.append(await coroutine)
            except Exception as e:
                logger.error(f"Error while refreshing {type(self).__name__}.", exc_info=e)

        if not _cache:
            logger.warning(__("All sources unavailable or no sources for {}.", type(self).__name__))

        builder = Builder()
        builder.pipeline.add(trimmer)
        builder.search_pipeline.add(stemmer)
        builder.ref("id")
        builder.field("name", boost=3)
        default_keywords = dict[str, None]()
        for src in self.sources:
            for field_name, boost in src.search_fields.items():
                builder.field(field_name=field_name, boost=boost)
                default_keywords[field_name] = None

        self.cache = {s: {} for s in self.sources}
        tmp = set[str]()
        for i, animes in enumerate(_cache):
            for anime in animes:
                hashed = hash_id(anime.id)
                self.cache[self.sources[i]][hashed] = anime
                if anime.id not in tmp:
                    tmp.add(anime.id)
                    builder.add(
                        default_keywords | dict(id=hashed, name=anime.name, **(anime.search_keywords or {})),
                        dict(boost=anime.popularity or 1),
                    )

        self.idx = builder.build()

    async def search(self, query: str) -> Sequence[Choice[str]]:
        if len(query) < 3:
            return []

        query_obj = Query(self.idx.fields)
        for token in Tokenizer(query):
            query_obj.term(str(token), presence=QueryPresence.REQUIRED, wildcard=Query.WILDCARD_TRAILING)

        results = self.idx.query(query_obj)

        # the "tmp" variable is None or a tuple, and we use a tricky "or" with another walrus operator to set "anime"
        # to the Anime
        return [
            Choice(name=f"{anime.name[:80] + '…' * (len(anime.name) > 80)} ({anime.language})", value=anime.id)
            for res in results
            if (tmp := await self.retrieve(_hash=res["ref"])) and (anime := tmp[0])
        ][:25]

    def concat_contents(self, contents: list[Anime]) -> Anime:
        return contents[0]  # TODO(airo.pi_) if multiple sources

    async def retrieve(
        self, *, _id: str | None = None, _hash: str | None = None
    ) -> RetrieveType[Anime, AnimeSource] | None:
        if _hash is None:
            assert _id is not None
            _hash = hash_id(_id)

        sources: list[AnimeSource] = [s for s in self.sources if _hash in self.cache[s]]
        if not sources:
            return None

        contents: list[Anime] = [self.cache[s][_hash] for s in sources]

        return self.concat_contents(contents), tuple(zip(sources, contents))
