import io
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Iterable, Literal

from mediasub.source import PullSource

type Download = DownloadBytes | DownloadInProgress | DownloadUrl


@dataclass(kw_only=True)
class Series:
    id_name: str
    name: str
    # season: str | None = None
    aliases: list[str] = field(default_factory=list)
    popularity: int | None = None
    description: str | None = None
    thumbnail: str | None = None
    genres: list[str] = field(default_factory=list)
    lang: str
    type: Literal["anime", "manga"]

    @property
    def ref(self) -> str:
        return f"{self.type}/{self.id_name}/{self.lang}"


@dataclass(kw_only=True)
class Content:
    type: Literal["anime", "manga"]
    id_name: str
    lang: str
    identifiers: tuple[str, ...]

    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return "/".join((self.type, self.id_name, self.lang) + self.identifiers)

    @property
    def sub_id(self) -> str:
        return f"{self.type}/{self.id_name}/{self.lang}"


class ExtendedSource(PullSource):
    supports_download: bool = False

    @abstractmethod
    async def get_all(self) -> Iterable[Series]:
        ...

    async def download(self, ref: str) -> AsyncGenerator[Download, None]:
        raise NotImplementedError()
        yield


@dataclass
class DownloadBytes:
    data: io.BytesIO
    filename: str


@dataclass
class DownloadInProgress:
    progression: int


@dataclass
class DownloadUrl:
    url: str


from .animes import Gazes as Gazes
from .mangas import MangaScanDotMe as MangaScanDotMe, ScanMangaVFDotMe as ScanMangaVFDotMe, ScanVFDotNet as ScanVFDotNet
from .news import Melty as Melty
