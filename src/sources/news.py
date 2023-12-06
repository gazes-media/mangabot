from dataclasses import dataclass
from typing import Any, Iterable, override

import feedparser
import httpx
from mediasub import SourceDown
from mediasub.source import LastPullContext, PullSource


@dataclass
class News:
    author: str
    title: str
    link: str
    description: str
    image_url: str | None
    id: str


class Melty(PullSource):
    name = "Melty"  # type: ignore  # TODO
    url = "https://www.melty.fr/"  # type: ignore  # TODO

    _rss_url = "https://www.melty.fr/comics-mangas/feed"

    headers = httpx.Headers({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"})

    @override
    async def pull(self, last_pull_ctx: LastPullContext | None = None) -> Iterable[News]:
        try:
            res = await self.client.get(self._rss_url, headers=self.headers)
        except httpx.HTTPError as e:
            raise SourceDown(e) from e

        feed: Any = feedparser.parse(res.text)

        def parse(item: Any) -> News:
            image_url: None | str = None
            if item.media_content and item.media_content[0]["medium"] == "image":
                image_url = item.media_content[0]["url"]
            return News(
                author=item.author,
                title=item.title,
                link=item.link,
                description=item.summary,
                image_url=image_url,
                id=item.id,
            )

        return [parse(item) for item in feed.entries]
