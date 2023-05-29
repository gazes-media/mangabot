import asyncio
from collections.abc import Sequence
from itertools import chain
from typing import TypeAlias

from thefuzz import process

from constants import MANGA_CHANNEL
from sources.mangas.base import Manga, MangaSource

from .base import SourceAggregator

CacheT: TypeAlias = dict[MangaSource, tuple[Manga, ...]]


class MangaAggregator(SourceAggregator[MangaSource]):
    channel_id = MANGA_CHANNEL

    def __init__(self, *sources: MangaSource):
        super().__init__(*sources)
        self.cache: CacheT = {s: tuple() for s in sources}

    async def refresh(self):
        cache = await asyncio.gather(*(src.get_mangas() for src in self.sources))
        self.cache = {src: tuple(available) for src, available in zip(self.sources, cache)}

    async def search(self, query: str) -> Sequence[Manga]:
        tmp = set[str]()

        def without_duplicates():
            for element in chain(*self.cache.values()):
                if element.id not in tmp:
                    tmp.add(element.id)
                yield element

        def processor(entry: str | Manga) -> str:
            if isinstance(entry, str):
                return entry
            return entry.name

        if query == "":
            iterable = without_duplicates()
            results: list[tuple[Manga, int]] = [(e, 0) for _ in range(25) if (e := next(iterable, None)) is not None]
        else:
            results = process.extract(query, without_duplicates(), processor=processor, limit=25)

        return [res[0] for res in results]

    def concat_contents(self, contents: list[Manga]) -> Manga:
        return contents[0]

    async def retrieve(self, _id: str) -> tuple[Manga, Sequence[tuple[MangaSource, Manga]]]:
        sources: list[MangaSource] = []
        contents: list[Manga] = []

        for source in self.sources:
            if content := next((manga for manga in self.cache[source] if manga.id == _id), None):
                contents.append(content)
                sources.append(source)
        return self.concat_contents(contents), tuple(zip(sources, contents))
