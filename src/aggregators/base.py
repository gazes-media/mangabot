from abc import ABC, abstractmethod
from collections.abc import Sequence
from logging import getLogger
from typing import Generic, Protocol, TypeVar

import discord
from discord.app_commands import Choice

S = TypeVar("S")


logger = getLogger(__name__)


class Content(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def thumbnail(self) -> str | None:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def description(self) -> str | None:
        ...


class SourceAggregator(ABC, Generic[S]):
    webhook: discord.Webhook
    channel: discord.ForumChannel
    channel_id: int

    def __init__(self, *sources: S):
        self.sources: tuple[S] = sources

    async def setup(self, client: discord.Client):
        channel = client.get_channel(self.channel_id) or await client.fetch_channel(self.channel_id)

        if not isinstance(channel, discord.ForumChannel):
            raise ValueError(f"Channel with ID {self.channel_id} is not a Forum Channel !")

        self.channel = channel
        if not (webhooks := await channel.webhooks()):
            self.webhook = await channel.create_webhook(name="Manga notifier")
        else:
            self.webhook = webhooks[0]

    async def refresh(self):
        """This function will be called every x time if a cache is needed."""
        pass

    @abstractmethod
    async def search(self, query: str) -> Sequence[Choice]:
        ...

    @abstractmethod
    async def retrieve(self, _id: str) -> tuple[Content, Sequence[tuple[S, Content]]]:
        ...
