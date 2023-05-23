import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Self, Sequence

import aiosqlite
import discord
import mediasub
from discord import File, ForumChannel, app_commands, ui
from discord.ext import tasks
from discord.utils import MISSING
from mediasub.models import AnimeSource, Chapter, Episode, MangaSource
from mediasub.models.base import NormalizedObject, Source

from constants import ANIME_CHANNEL, MANGA_CHANNEL
from database_patchs import patchs
from sources.animes import Gaze
from sources.scans import MangaScanDotWS, ScanFRDotOrg, ScanMangaVFDotWS, ScanVFDotNet
from utils import BraceMessage as __
from utils import chunker

logger = logging.getLogger(__name__)


manga_sources = [MangaScanDotWS(), ScanFRDotOrg(), ScanMangaVFDotWS(), ScanVFDotNet()]
anime_sources = [Gaze()]


class SourcesType(Enum):
    MANGA = "manga"  # mean scan
    ANIME = "anime"


@dataclass
class SourceGroup:
    type: SourcesType
    channel_id: int
    sources: list[Source]
    sources_all: list[Sequence[NormalizedObject]] = field(default_factory=list)
    webhook: discord.Webhook | None = None


class MangaBot(discord.AutoShardedClient):
    db: aiosqlite.Connection

    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)

        self.sources = [
            SourceGroup(
                SourcesType.MANGA,
                MANGA_CHANNEL,
                list(manga_sources),
            ),
            SourceGroup(SourcesType.ANIME, ANIME_CHANNEL, list(anime_sources)),
        ]
        self.mediasub = mediasub.MediaSub("data/history.sqlite")

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

        self.db = await aiosqlite.connect("data/db.sqlite")

        await self.init_db()
        await self.init_webhooks()
        await self.init_sources_cache()

    async def init_sources_cache(self):
        for source_group in self.sources:
            source_group.sources_all = [
                tuple(all) for all in await asyncio.gather(*(source.all() for source in source_group.sources))
            ]

    async def init_db(self):
        async with self.db.cursor() as cursor:
            sql = """
            CREATE TABLE IF NOT EXISTS subscription (
                user_id INTEGER,
                series_id TEXT,
                PRIMARY KEY (user_id, series_id)
            )
            """
            await cursor.execute(sql)

            sql = "CREATE TABLE IF NOT EXISTS database_patchs (version INTEGER)"
            await cursor.execute(sql)

            for patch in patchs:
                if await cursor.execute("SELECT version FROM database_patchs WHERE version = ?", (patch[0],)):
                    continue
                await patch[1]()
                await cursor.execute("INSERT INTO database_patchs VALUES (?)", (patch[0],))

    async def init_webhooks(self):
        for source in self.sources:
            try:
                channel = self.get_channel(source.channel_id) or await self.fetch_channel(source.channel_id)
            except (discord.NotFound, discord.Forbidden):
                logger.warning(__("A channel ID is invalid : {}", source.channel_id))
                continue
            if not isinstance(channel, ForumChannel):
                logger.warning(__("Channel with ID {} is not a Forum Channel !", source.channel_id))
                continue
            if not (webhooks := await channel.webhooks()):
                source.webhook = await channel.create_webhook(name="Manga notifier")
            else:
                source.webhook = webhooks[0]

    async def on_ready(self):
        logger.info(__("Logged on as {}!", self.user))

    def run(
        self,
        token: str,
        *,
        reconnect: bool = True,
        log_handler: logging.Handler | None = MISSING,
        log_formatter: logging.Formatter = MISSING,
        log_level: int = MISSING,
        root_logger: bool = False,
    ) -> None:
        async def runner():
            async def bot():
                async with self:
                    await self.start(token, reconnect=reconnect)

            await asyncio.gather(bot(), self.mediasub.start())

        if log_handler is not None:
            discord.utils.setup_logging(
                handler=log_handler,
                formatter=log_formatter,
                level=log_level,
                root=root_logger,
            )

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            # nothing to do here
            # `asyncio.run` handles the loop cleanup
            # and `self.start` closes all sockets and the HTTPClient instance.
            return


client = MangaBot()


@client.mediasub.sub_to(*manga_sources)
async def on_chapter(source: MangaSource, chapter: Chapter):
    await client.wait_until_ready()
    group = next(s for s in client.sources if s.type is SourcesType.MANGA)
    assert group.webhook is not None  # nosec B101

    sql = "SELECT user_id FROM subscription WHERE series_id = ?"
    async with client.db.cursor() as cursor:
        req = await cursor.execute(sql, (f"{SourcesType.MANGA.value}/{chapter.manga.normalized_name}",))
        results = await req.fetchall()
        if not results:
            return

    embed = discord.Embed(
        title=f"New chapter of {chapter.manga.name} !",
        description=f"**{chapter.manga.name}** - chapter {chapter.number}",
        url=chapter.url,
    )
    embed.add_field(name="Language", value=chapter.language or "unknown (probably french)", inline=True)
    embed.add_field(name="Chapter name", value=chapter.name, inline=True)
    embed.add_field(name="Source", value=source.name, inline=True)

    message = await group.webhook.send(
        embed=embed,
        thread_name=f"{chapter.manga.name} - chapter {chapter.number}",
        wait=True,
        content=", ".join(f"<@{user_id}>" for user_id, in results),
    )
    assert isinstance(message.channel, discord.PartialMessageable)  # nosec: B101

    for chunk in chunker(await source.get_pages(chapter), 10):
        imgs = await asyncio.gather(*(source.download(page) for page in chunk))
        files = [File(img[1], f"{chapter.number}-{img[0]}", spoiler=True) for img in imgs]
        await group.webhook.send(files=files, thread=message.channel)


@client.mediasub.sub_to(*anime_sources)
async def on_episode(source: AnimeSource, episode: Episode):
    await client.wait_until_ready()
    group = next(s for s in client.sources if s.type is SourcesType.ANIME)
    assert group.webhook is not None  # nosec: B101

    sql = "SELECT user_id FROM subscription WHERE series_id = ?"
    async with client.db.cursor() as cursor:
        req = await cursor.execute(sql, (f"{SourcesType.ANIME.value}/{episode.anime.normalized_name}",))
        results = await req.fetchall()
        if not results:
            return

    embed = discord.Embed(
        title=f"New chapter of {episode.anime.name} !",
        description=f"**{episode.anime.name}** - {episode.name}",
        url=episode.url,
    )
    embed.add_field(name="Language", value=episode.language or "unknown", inline=True)
    embed.add_field(name="Source", value=source.name, inline=True)

    await group.webhook.send(
        embed=embed,
        thread_name=f"{episode.anime.name} - {episode.name}",
        content=", ".join(f"<@{user_id}>" for user_id, in results),
    )


@client.tree.command()
@app_commands.rename(_type="type")
async def search(inter: discord.Interaction, _type: SourcesType, name: str):
    if ":::" not in name:
        return await inter.response.send_message("Please select a name in the list.")
    source_name, content_name = name.split(":::")

    source_group: SourceGroup = next((s for s in client.sources if s.type is _type))
    try:
        source, cache = next(
            (s, c) for (s, c) in zip(source_group.sources, source_group.sources_all) if s.name == source_name
        )
    except StopIteration:
        return await inter.response.send_message("An error occurred.")

    content = next((c for c in cache if c.display == content_name), None)
    if content is None:
        return await inter.response.send_message("An error occurred.")

    return await inter.response.send_message(
        f"{source.name} - {content.display}", view=SubscribeView(f"{_type.value}/{content.normalized_name}", inter)
    )


@search.autocomplete(name="name")
async def search_autocomplete(inter: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if inter.namespace.type is None:
        return [app_commands.Choice(name="Please first select a type", value="")]

    source_group: SourceGroup = next(s for s in client.sources if s.type is SourcesType(inter.namespace.type))

    normalized: list[str] = []
    results: list[tuple[Source, NormalizedObject]] = []
    for source, source_all in zip(source_group.sources, source_group.sources_all):
        if not source_all:
            continue

        for content in source_all:
            if content.normalized_name in normalized:
                continue
            if not current:
                continue
            if current.lower() not in content.display.lower():
                continue
            normalized.append(content.normalized_name)
            results.append((source, content))

    return [
        app_commands.Choice(name=result[1].display, value=f"{result[0].name}:::{result[1].display}")
        for result in results
    ][:25]


@tasks.loop(hours=1)
async def refresh_all():
    await client.init_sources_cache()


class SubscribeView(ui.View):
    def __init__(self, series_id: str, original_inter: discord.Interaction):
        self.series_id = series_id
        self.original_inter = original_inter
        super().__init__(timeout=180)

    @ui.button(label="Subscribe/Unsubscribe", style=discord.ButtonStyle.primary)
    async def toggle_subscription(self, inter: discord.Interaction, button: discord.ui.Button[Self]):
        del button  # unused
        async with client.db.cursor() as cursor:
            sql = """SELECT 1 FROM subscription WHERE user_id = ? AND series_id = ?"""
            req = await cursor.execute(sql, (inter.user.id, self.series_id))
            res = await req.fetchone()
            if res is not None:
                sql = """DELETE FROM subscription WHERE user_id = ? AND series_id = ?"""
                await cursor.execute(sql, (inter.user.id, self.series_id))
                await inter.response.send_message("You have been unsubscribed !", ephemeral=True)
            else:
                sql = """INSERT INTO subscription VALUES (?, ?)"""
                await cursor.execute(sql, (inter.user.id, self.series_id))
                await inter.response.send_message("You have been subscribed !", ephemeral=True)
        await client.db.commit()

    async def on_timeout(self):
        self.toggle_subscription.disabled = True
        await self.original_inter.edit_original_response(view=self)


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"], root_logger=True, log_level=logging.INFO)
