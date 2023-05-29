from __future__ import annotations

import io
from abc import abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

from mediasub import Source
from mediasub.utils import normalize
from typing_extensions import Any, TypeVar

RawT = TypeVar("RawT", default=Any)


@dataclass(kw_only=True)
class Manga:
    name: str
    url: str
    thumbnail: str | None = None
    description: str | None = None

    internal: Any = field(repr=False, default=None)

    @property
    def id(self) -> str:
        return f"MANGA/{normalize(self.name)}"


@dataclass(kw_only=True)
class Chapter:
    manga: Manga
    name: str
    number: int
    language: str | None
    url: str
    sub_number: int | None = None  # for special chapters

    internal: Any = field(repr=False, default=None)

    def __post_init__(self):
        self.db_identifier = (
            f"{normalize(self.manga.name)}/{self.number}{f'.{self.sub_number}' if self.sub_number else ''}"
        )


@dataclass(kw_only=True)
class Page:
    chapter: Chapter
    number: int
    url: str

    internal: Any = field(repr=False, default=None)


class MangaSource(Source["Chapter"]):
    @abstractmethod
    async def search(self, query: str) -> Iterable[Manga]:
        pass

    @abstractmethod
    async def get_mangas(self) -> Iterable[Manga]:
        pass

    @abstractmethod
    async def get_chapters(self, manga: Manga) -> Iterable[Chapter]:
        pass

    @abstractmethod
    async def get_pages(self, chapter: Chapter) -> Iterable[Page]:
        pass

    @abstractmethod
    async def download_page(self, page: Page) -> tuple[str, io.BytesIO]:
        pass
