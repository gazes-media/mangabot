from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable

from mediasub import Source
from mediasub.utils import normalize


class AnimeSource(Source["Episode"]):
    @abstractmethod
    async def get_animes(self) -> Iterable[Anime]:
        ...


@dataclass(kw_only=True)
class Anime:
    name: str
    url: str
    thumbnail: str | None = None
    description: str | None = None

    internal: Any = field(repr=False, default=None)

    @property
    def id(self) -> str:
        return f"ANIME/{normalize(self.name)}"


@dataclass(kw_only=True)
class Episode:
    anime: Anime
    name: str
    number: int
    language: str | None
    url: str
    sub_number: int | None = None  # for special episodes

    internal: Any = field(repr=False, default=None)

    def __post_init__(self):
        self.db_identifier = (
            f"{normalize(self.anime.name)}/{self.number}{f'.{self.sub_number}' if self.sub_number else ''}"
        )
