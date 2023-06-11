from collections.abc import Sequence

from cachetools import TTLCache
from discord.app_commands import Choice

from constants import WEBTOON_CHANNEL
from sources.webtoons import Webtoon, WebtoonSource

from .base import RetrieveType, SourceAggregator


class WebtoonAggregator(SourceAggregator[WebtoonSource]):
    channel_id = WEBTOON_CHANNEL

    def __init__(self, *sources: WebtoonSource):
        super().__init__(*sources)
        self.wt_source = sources[0]  # only one source
        self.cache: TTLCache[str, Webtoon] = TTLCache(maxsize=1000, ttl=300)

    async def search(self, query: str) -> Sequence[Choice[str]]:
        search_results = await self.wt_source.search(query)

        def cached_firsts():
            for i, element in enumerate(search_results):
                if i > 24:
                    break
                self.cache[element.id] = element
                yield element

        return [Choice(name=wt.name, value=wt.id) for wt in cached_firsts()]

    async def retrieve(
        self, *, _id: str | None = None, _hash: str | None = None
    ) -> RetrieveType[Webtoon, WebtoonSource] | None:
        if _id is None:
            assert _hash is not None
            _id = _hash

        if cached := self.cache.get(_id):
            return cached, ((self.wt_source, cached),)
        raise ValueError("Webtoon not found")
