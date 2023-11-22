import logging
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process, utils

from sources import ExtendedSource

logger = logging.getLogger(__name__)


type CacheT = dict[str, SeriesInfos]


@dataclass(kw_only=True)
class SeriesInfos:
    name: str
    description: str | None = None
    thumbnail: str | None = None
    popularity: list[int] = field(default_factory=list)
    types: dict[str, set[str]] = field(default_factory=dict)
    genres: set[str] = field(default_factory=set)
    aliases: set[str] = field(default_factory=set)


class Searcher:
    def __init__(self, *sources: ExtendedSource):
        self.sources = sources
        self._cache: CacheT | None = None

    @property
    def cache(self) -> CacheT:
        if self._cache is None:
            raise RuntimeError("Cache not built")
        return self._cache

    async def build_cache(self) -> None:
        self._cache = {}

        for src in self.sources:
            try:
                result = await src.get_all()
            except Exception as e:
                logger.warning(f"Error while getting all elements of {src.name}", exc_info=e)
                continue

            for element in result:
                series_infos = self._cache.setdefault(element.id_name, SeriesInfos(name=element.name))

                if series_infos.description is None:
                    series_infos.description = element.description
                if series_infos.thumbnail is None:
                    series_infos.thumbnail = element.thumbnail

                if element.popularity:
                    series_infos.popularity.append(element.popularity)

                series_infos.genres.update(element.genres)
                series_infos.types.setdefault(element.type, set()).add(element.lang)
                series_infos.aliases.update(element.aliases)

    async def search(self, query: str) -> list[tuple[str, SeriesInfos]]:
        backref: dict[int, int] = {}

        def iter_aliases():
            incr = 0
            for i, value in enumerate(self.cache.values()):
                backref[incr] = i
                incr += 1
                yield value.name

                for alias in value.aliases:
                    backref[incr] = i
                    incr += 1
                    yield alias

        result: list[tuple[str, float, int]] = process.extract(
            query, list(iter_aliases()), scorer=fuzz.WRatio, processor=utils.default_process, limit=25
        )

        ids = dict.fromkeys(backref[r[2]] for r in result)
        tmp = tuple(self.cache.items())
        filtered = (tmp[i] for i in ids)

        return [(key, value) for (key, value) in filtered]
