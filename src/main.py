from __future__ import annotations

import asyncio
import logging
import os
from typing import Self

import aiosqlite
import discord
import mediasub
from discord import ForumChannel, TextChannel, app_commands, ui
from discord.ext import tasks
from discord.utils import MISSING

from constants import SPAM_CHANNEL, SPREAD_CHANNEL
from database_patchs import patchs
from searcher import Searcher, SeriesInfos
from sources import Content, ExtendedSource, Gazes, MangaScanDotMe, ScanMangaVFDotMe, ScanVFDotNet
from utils import BraceMessage as __

logger = logging.getLogger(__name__)


class MangaBot(discord.AutoShardedClient):
    db: aiosqlite.Connection
    spam_channel: TextChannel
    spread_channel: ForumChannel
    sources = [Gazes(), ScanVFDotNet(), MangaScanDotMe(), ScanMangaVFDotMe()]
    searcher = Searcher(*sources)

    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)

        self.mediasub = mediasub.MediaSub("data/history.sqlite")
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

        self.db = await aiosqlite.connect("data/db.sqlite")

        await self.init_db()
        await self.searcher.build_cache()

        tmp = self.get_channel(SPAM_CHANNEL) or await self.fetch_channel(SPAM_CHANNEL)
        if not isinstance(tmp, TextChannel):
            raise TypeError("SPAM_CHANNEL is not a TextChannel")
        self.spam_channel = tmp

        tmp = self.get_channel(SPREAD_CHANNEL) or await self.fetch_channel(SPREAD_CHANNEL)
        if not isinstance(tmp, ForumChannel):
            raise TypeError("SPREAD_CHANNEL is not a ForumChannel")
        self.spread_channel = tmp

    async def init_db(self):
        async with self.db.cursor() as cursor:
            sql = """
            CREATE TABLE IF NOT EXISTS subscription (
                user_id INTEGER,
                type TEXT,
                series TEXT,
                language TEXT,
                PRIMARY KEY (user_id, series, language, type)
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


async def check_subscription(type: str, series: str, language: str):
    sql = "SELECT user_id FROM subscription WHERE type = ? AND series = ? AND language = ?"
    async with client.db.cursor() as cursor:
        req = await cursor.execute(sql, (type, series, language))
        return await req.fetchall()


#     if not (results := await check_subscription(chapter.manga.id)):
#         return

#     message = await client.manga_researcher.channel.create_thread(
#         name=f"{chapter.manga.name[:80]} - chapter {chapter.number}",
#         embed=embed,
#         content=", ".join(f"<@{user_id}>" for user_id, in results),
#         view=SubscribeView(chapter.manga.id),
#     )

#     for chunk in chunker(await source.get_pages(chapter), 10):
#         imgs = await asyncio.gather(*(source.download_page(page) for page in chunk))
#         files = [File(img[1], f"{chapter.number}-{img[0]}", spoiler=True) for img in imgs]
#         await client.manga_researcher.webhook.send(files=files, thread=message.thread)


@client.mediasub.sub_to(*MangaBot.sources)
async def on_content(src: ExtendedSource, content: Content):
    await client.wait_until_ready()

    series = MangaBot.searcher.cache[content.id_name]

    match content.type:
        case "manga":
            embed = discord.Embed(
                title=f"New chapter of {series.name} !",
                description=f"**{content.fields['chapter_name'][:80]}** ({content.fields['chapter_nb']})",
                url=content.fields["url"],
            )

            thread_name = f"{series.name[:50]} - {content.fields['chapter_name']}"
        case "anime":
            embed = discord.Embed(
                title=f"New episode of {series.name} !",
                url=content.fields["url"],
            )
            embed.add_field(name="Season", value=content.fields["season"], inline=True)
            embed.add_field(name="Episode", value=content.fields["episode"], inline=True)

            thread_name = f"{series.name[:50]} - {content.fields['season'][:50]} - episode {content.fields['episode']}"

    if series.thumbnail:
        embed.set_thumbnail(url=series.thumbnail)
    embed.add_field(name="Language", value=content.lang, inline=True)
    embed.add_field(name="Source", value=src.name, inline=True)

    await client.spam_channel.send(embed=embed)

    if not (results := await check_subscription(content.type, content.id_name, content.lang)):
        return

    await client.spread_channel.create_thread(
        name=thread_name,
        embed=embed,
        content=", ".join(f"<@{user_id}>" for user_id, in results),
    )


# @client.mediasub.sub_to(*client.webtoon_researcher.sources)
# async def on_webtoon(source: WebtoonSource, episode: WebtoonEpisode):
#     await client.wait_until_ready()

#     embed = discord.Embed(
#         title=f"New episode of {episode.webtoon.name} !",
#         description=f"**{episode.webtoon.name[:80]}** - episode {episode.number}",
#         url=episode.url,
#     )
#     embed.add_field(name="Language", value=episode.language or "unknown", inline=True)
#     embed.add_field(name="Source", value=source.name, inline=True)

#     await client.spam_channel.send(embed=embed, view=SubscribeView(episode.webtoon.id))

#     if not (results := await check_subscription(episode.webtoon.id)):
#         return

#     await client.anime_researcher.channel.create_thread(
#         name=f"{episode.webtoon.name[:50]} - {episode.name}",
#         embed=embed,
#         content=", ".join(f"<@{user_id}>" for user_id, in results),
#         view=SubscribeView(episode.webtoon.id),
#     )


# dial = {
#     # "manga": client.manga_researcher,
#     "anime": client.anime_researcher,
#     # "webtoon": client.webtoon_researcher,
# }


@client.tree.command()
@app_commands.rename(name_id="name")
async def search(inter: discord.Interaction, name_id: str):
    result = MangaBot.searcher.cache.get(name_id)
    if not result:
        return await inter.response.send_message("No result found")

    embed = discord.Embed(
        title=result.name[:80],
        description=result.description or "No description",
    )
    embed.add_field(
        name="Genres",
        value=", ".join(result.genres) or "No genres",
        inline=False,
    )

    if result.thumbnail:
        embed.set_thumbnail(url=result.thumbnail)

    await inter.response.send_message(embed=embed, view=SubscriptionView(name_id, result))


@search.autocomplete(name="name_id")
async def search_autocomplete(inter: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return list(
        app_commands.Choice(name=e.name, value=id_name) for id_name, e in await MangaBot.searcher.search(current)
    )[:25]


@client.tree.command()
async def get_status(inter: discord.Interaction) -> None:
    tmp: list[str] = []
    for src in MangaBot.sources:
        tmp.append(f"[{src.name}]({src.url}) : {src.status.value}")
    embed = discord.Embed(title="Sources status :", description="\n".join(tmp))
    await inter.response.send_message(embed=embed)


@client.tree.command()
async def get_subscriptions(inter: discord.Interaction) -> None:
    sql = """SELECT series, language, type FROM subscription WHERE user_id = ?"""

    req = await client.db.execute(sql, (inter.user.id,))
    res = await req.fetchall()

    embed = discord.Embed(title="Your subscriptions :")
    for series, language, type_ in res:
        content = MangaBot.searcher.cache.get(series)
        if not content:
            continue
        embed.add_field(name=content.name, value=f"{language} - {type_}")

    await inter.response.send_message(embed=embed)


@tasks.loop(hours=1)
async def refresh_all():
    await MangaBot.searcher.build_cache()


# @client.event
# async def on_interaction(inter: discord.Interaction):
#     if inter.type != discord.InteractionType.component:
#         return

#     data: MessageComponentInteractionData = inter.data  # type: ignore
#     if data["component_type"] != discord.ComponentType.button.value:
#         return
#     if not data["custom_id"].startswith("toggle_subscription"):
#         return

#     # keep only text behind toggle_subscription
#     _, series_type, series_hash = data["custom_id"].split("::")
#     async with client.db.cursor() as cursor:
#         sql = """SELECT 1 FROM subscription WHERE user_id = ? AND series_hash = ?"""
#         req = await cursor.execute(sql, (inter.user.id, series_hash))
#         res = await req.fetchone()
#         if res is not None:
#             sql = """DELETE FROM subscription WHERE user_id = ? AND series_hash = ?"""
#             await cursor.execute(sql, (inter.user.id, series_hash))
#             await inter.response.send_message("You have been unsubscribed !", ephemeral=True)
#         else:
#             sql = """INSERT INTO subscription VALUES (?, ?, ?)"""
#             await cursor.execute(sql, (inter.user.id, series_hash, series_type))
#             await inter.response.send_message("You have been subscribed !", ephemeral=True)
#     await client.db.commit()


class SubscriptionView(ui.View):
    def __init__(self, series_id: str, series_infos: SeriesInfos):
        super().__init__(timeout=0)
        self.series_id = series_id
        self.series_infos = series_infos

    @ui.button(label="Subscribe", style=discord.ButtonStyle.primary)
    async def subscribe(self, inter: discord.Interaction, button: ui.Button[Self]):
        return await inter.response.send_message(
            view=SubscriptionTypeView(self.series_id, self.series_infos), ephemeral=True
        )

    @ui.button(label="Unsubscribe", style=discord.ButtonStyle.danger)
    async def unsubscribe(self, inter: discord.Interaction, button: ui.Button[Self]):
        sql = """DELETE FROM subscription WHERE user_id = ? AND series = ?"""
        await client.db.execute(sql, (inter.user.id, self.series_id))
        await client.db.commit()
        await inter.response.send_message("You have been unsubscribed (from all, because la flemme)!", ephemeral=True)


class SubscriptionTypeView(ui.View):
    def __init__(self, series_id: str, series_infos: SeriesInfos):
        super().__init__(timeout=0)
        self.series_id = series_id
        self.series_infos = series_infos

        for type in series_infos.types:
            self.select_type.add_option(label=type)

    @ui.select(cls=ui.Select, placeholder="Type")
    async def select_type(self, inter: discord.Interaction, select: ui.Select[Self]):
        await inter.response.send_message(
            view=SubscriptionLangView(self.series_id, self.series_infos, select.values[0]), ephemeral=True
        )


class SubscriptionLangView(ui.View):
    def __init__(self, series_id: str, series_infos: SeriesInfos, type: str):
        super().__init__(timeout=0)

        self.series_id = series_id
        self.series_infos = series_infos
        self.type = type

        for lang in series_infos.types[type]:
            self.select_lang.add_option(label=lang)

    @ui.select(cls=ui.Select, placeholder="Language")
    async def select_lang(self, inter: discord.Interaction, select: ui.Select[Self]):
        async with client.db.cursor() as cursor:
            sql = """INSERT INTO subscription VALUES (?, ?, ?, ?)"""
            await cursor.execute(sql, (inter.user.id, self.type, self.series_id, select.values[0]))
            await client.db.commit()
        await inter.response.send_message("You have been subscribed !", ephemeral=True)


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"], root_logger=True, log_level=logging.INFO)
