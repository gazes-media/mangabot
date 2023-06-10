import asyncio
import logging
import os
from typing import Literal

import aiosqlite
import discord
import mediasub
from discord import File, TextChannel, app_commands, ui
from discord.ext import tasks
from discord.utils import MISSING

from aggregators import AnimeAggregator, MangaAggregator, WebtoonAggregator
from constants import SPAM_CHANNEL
from database_patchs import patchs
from sources.animes import AnimeSource, Episode, Gaze
from sources.mangas import Chapter, MangaScanDotWS, MangaSource, ScanFRDotOrg, ScanMangaVFDotWS, ScanVFDotNet
from sources.webtoons.webtoon import WebtoonEpisode, WebtoonSource
from utils import BraceMessage as __
from utils import chunker

logger = logging.getLogger(__name__)


class MangaBot(discord.AutoShardedClient):
    db: aiosqlite.Connection
    spam_channel: TextChannel
    manga_aggregate = MangaAggregator(MangaScanDotWS(), ScanFRDotOrg(), ScanMangaVFDotWS(), ScanVFDotNet())
    anime_aggregate = AnimeAggregator(Gaze())
    webtoon_aggregate = WebtoonAggregator(WebtoonSource())

    aggregates = [manga_aggregate, anime_aggregate, webtoon_aggregate]

    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)

        self.mediasub = mediasub.MediaSub("data/history.sqlite")

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

        self.db = await aiosqlite.connect("data/db.sqlite")

        await self.init_db()
        await self.refresh_aggregates()

        for agg in self.aggregates:
            await agg.setup(self)

        self.spam_channel = self.get_channel(SPAM_CHANNEL) or await self.fetch_channel(SPAM_CHANNEL)

    async def refresh_aggregates(self):
        for agg in self.aggregates:
            await agg.refresh()

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


async def check_subscription(_id: str):
    sql = "SELECT user_id FROM subscription WHERE series_id = ?"
    async with client.db.cursor() as cursor:
        req = await cursor.execute(sql, (_id,))
        return await req.fetchall()


@client.mediasub.sub_to(*client.manga_aggregate.sources)
async def on_chapter(source: MangaSource, chapter: Chapter):
    await client.wait_until_ready()

    embed = discord.Embed(
        title=f"New chapter of {chapter.manga.name} !",
        description=f"**{chapter.manga.name}** - chapter {chapter.number}",
        url=chapter.url,
    )
    embed.add_field(name="Language", value=chapter.language or "unknown (probably french)", inline=True)
    embed.add_field(name="Chapter name", value=chapter.name, inline=True)
    embed.add_field(name="Source", value=source.name, inline=True)

    await client.spam_channel.send(embed=embed, view=SubscribeView(chapter.manga.id))

    if not (results := await check_subscription(chapter.manga.id)):
        return

    message = await client.manga_aggregate.channel.create_thread(
        name=f"{chapter.manga.name[:80]} - chapter {chapter.number}",
        embed=embed,
        content=", ".join(f"<@{user_id}>" for user_id, in results),
        view=SubscribeView(chapter.manga.id),
    )

    for chunk in chunker(await source.get_pages(chapter), 10):
        imgs = await asyncio.gather(*(source.download_page(page) for page in chunk))
        files = [File(img[1], f"{chapter.number}-{img[0]}", spoiler=True) for img in imgs]
        await client.manga_aggregate.webhook.send(files=files, thread=message.thread)


@client.mediasub.sub_to(*client.anime_aggregate.sources)
async def on_episode(source: AnimeSource, episode: Episode):
    await client.wait_until_ready()

    embed = discord.Embed(
        title=f"New chapter of {episode.anime.name} !",
        description=f"**{episode.anime.name[:80]}** - episode {episode.number}",
        url=episode.url,
    )
    embed.add_field(name="Language", value=episode.language or "unknown", inline=True)
    embed.add_field(name="Source", value=source.name, inline=True)

    await client.spam_channel.send(embed=embed, view=SubscribeView(episode.anime.id))

    if not (results := await check_subscription(episode.anime.id)):
        return

    await client.anime_aggregate.channel.create_thread(
        name=f"{episode.anime.name[:50]} - {episode.name}",
        embed=embed,
        content=", ".join(f"<@{user_id}>" for user_id, in results),
        view=SubscribeView(episode.anime.id),
    )


@client.mediasub.sub_to(*client.webtoon_aggregate.sources)
async def on_webtoon(source: WebtoonSource, episode: WebtoonEpisode):
    await client.wait_until_ready()

    embed = discord.Embed(
        title=f"New episode of {episode.webtoon.name} !",
        description=f"**{episode.webtoon.name[:80]}** - episode {episode.number}",
        url=episode.url,
    )
    embed.add_field(name="Language", value=episode.language or "unknown", inline=True)
    embed.add_field(name="Source", value=source.name, inline=True)

    await client.spam_channel.send(embed=embed, view=SubscribeView(episode.webtoon.id))

    if not (results := await check_subscription(episode.webtoon.id)):
        return

    await client.anime_aggregate.channel.create_thread(
        name=f"{episode.webtoon.name[:50]} - {episode.name}",
        embed=embed,
        content=", ".join(f"<@{user_id}>" for user_id, in results),
        view=SubscribeView(episode.webtoon.id),
    )


dial = {
    "manga": client.manga_aggregate,
    "anime": client.anime_aggregate,
    "webtoon": client.webtoon_aggregate,
}


@client.tree.command()
@app_commands.rename(_type="type", _id="name")
async def search(inter: discord.Interaction, _type: Literal["manga", "anime", "webtoon"], _id: str):
    aggregate = dial[_type]
    content, sources = await aggregate.retrieve(_id)

    embed = discord.Embed(
        title=content.name[:80],
        description=content.description,
    )
    embed.add_field(name="Sources", value="\n".join(f"[{src.name}]({ct.url})" for src, ct in sources), inline=False)

    if content.thumbnail:
        embed.set_thumbnail(url=content.thumbnail)

    await inter.response.send_message(embed=embed, view=SubscribeView(content.id))


@search.autocomplete(name="_id")
async def search_autocomplete(inter: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if inter.namespace.type is None:
        return [app_commands.Choice(name="Please first select a type", value="")]

    aggregate = dial[inter.namespace.type]
    results = await aggregate.search(current)

    return [app_commands.Choice(name=result.name, value=result.id) for result in results]


@client.tree.command()
async def get_status(inter: discord.Interaction) -> None:
    tmp: list[str] = []
    for aggregate in client.aggregates:
        for src in aggregate.sources:
            tmp.append(f"[{src.name}]({src.url}) : {src.status.value}")
    embed = discord.Embed(title="Sources status :", description="\n".join(tmp))
    await inter.response.send_message(embed=embed)


@tasks.loop(hours=1)
async def refresh_all():
    await client.refresh_aggregates()


@client.event
async def on_interaction(inter: discord.Interaction):
    if inter.type != discord.InteractionType.component:
        return
    if inter.data["component_type"] != discord.ComponentType.button.value:
        return
    if not inter.data["custom_id"].startswith("toggle_subscription"):
        return

    # keep only text behind toggle_subscription
    series_id = inter.data["custom_id"][len("toggle_subscription::") :]
    print(series_id)
    async with client.db.cursor() as cursor:
        sql = """SELECT 1 FROM subscription WHERE user_id = ? AND series_id = ?"""
        req = await cursor.execute(sql, (inter.user.id, series_id))
        res = await req.fetchone()
        if res is not None:
            sql = """DELETE FROM subscription WHERE user_id = ? AND series_id = ?"""
            await cursor.execute(sql, (inter.user.id, series_id))
            await inter.response.send_message("You have been unsubscribed !", ephemeral=True)
        else:
            sql = """INSERT INTO subscription VALUES (?, ?)"""
            await cursor.execute(sql, (inter.user.id, series_id))
            await inter.response.send_message("You have been subscribed !", ephemeral=True)
    await client.db.commit()


class SubscribeView(ui.View):
    def __init__(self, series_id: str):
        super().__init__(timeout=0)
        button = ui.Button(
            label="Subscribe/Unsubscribe",
            style=discord.ButtonStyle.primary,
            custom_id=f"toggle_subscription::{series_id}",
        )
        self.add_item(button)


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"], root_logger=True, log_level=logging.INFO)
