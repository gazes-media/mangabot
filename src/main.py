from __future__ import annotations

import asyncio
import itertools
import logging
import os
from typing import Self, cast

import aiosqlite
import discord
import mediasub
from discord import ForumChannel, TextChannel, app_commands, ui
from discord.ext import tasks
from discord.utils import MISSING

from constants import SPAM_CHANNEL, SPREAD_CHANNEL
from database_patchs import patchs
from searcher import Searcher, SeriesInfos
from sources import (
    Content,
    Download,
    DownloadBytes,
    DownloadInProgress,
    DownloadUrl,
    ExtendedSource,
    Gazes,
    MangaScanDotMe,
    ScanMangaVFDotMe,
    ScanVFDotNet,
)
from utils import BraceMessage as __

logger = logging.getLogger(__name__)


class MangaBot(discord.AutoShardedClient):
    db: aiosqlite.Connection
    spam_channel: TextChannel
    spread_channel: ForumChannel
    sources: list[ExtendedSource] = [ScanVFDotNet(), Gazes(), MangaScanDotMe(), ScanMangaVFDotMe()]
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

        self.add_view(DownloadView())

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


def series_embed(series_infos: SeriesInfos) -> discord.Embed:
    embed = discord.Embed(
        title=series_infos.name[:80],
        description=series_infos.description or "No description",
    )
    embed.add_field(
        name="Genres",
        value=", ".join(series_infos.genres) or "No genres",
        inline=False,
    )

    if series_infos.thumbnail:
        embed.set_thumbnail(url=series_infos.thumbnail)

    return embed


def get_ref(inter: discord.Interaction) -> tuple[str, str, str, str]:
    if inter.message is None or not inter.message.embeds or not (ref := inter.message.embeds[0].footer.text):
        raise ValueError("Invalid message")
    series_type, series_id, lang, *_ = ref.split("/")
    return series_type, series_id, lang, ref


async def check_subscription(type: str, series: str, language: str):
    sql = "SELECT user_id FROM subscription WHERE type = ? AND series = ? AND language = ?"
    async with client.db.cursor() as cursor:
        req = await cursor.execute(sql, (type, series, language))
        return await req.fetchall()


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
    embed.set_footer(text=content.id)

    view = DownloadView()
    await client.spam_channel.send(embed=embed, view=view)

    if not (results := await check_subscription(content.type, content.id_name, content.lang)):
        return

    await client.spread_channel.create_thread(
        name=thread_name,
        embed=embed,
        view=view,
        content=", ".join(f"<@{user_id}>" for user_id, in results),
    )


@client.tree.command()
@app_commands.rename(name_id="name")
async def search(inter: discord.Interaction, name_id: str):
    series_infos = MangaBot.searcher.cache.get(name_id)
    if not series_infos:
        return await inter.response.send_message("No result found")

    embed = series_embed(series_infos)
    view = SubscriptionView(name_id, series_infos)
    await inter.response.send_message(embed=embed, view=view)


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


class DownloadView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Download", custom_id="download.download", style=discord.ButtonStyle.blurple)
    async def download(self, inter: discord.Interaction, button: ui.Button[Self]):
        del button  # unused
        content_type, series_name, language, ref = get_ref(inter)
        series = client.searcher.cache[series_name]

        providers_names = series.types[content_type][language]
        providers = [next(s for s in MangaBot.sources if s.name == name) for name in providers_names]
        providers = [p for p in providers if p.supports_download]

        if not providers:
            return await inter.response.send_message("No sources available for download.", ephemeral=True)

        await inter.response.send_message(
            view=SourceSelect(providers, ref),
            ephemeral=True,
        )

    @ui.button(label="Series", custom_id="download.view_series", style=discord.ButtonStyle.gray)
    async def series(self, inter: discord.Interaction, button: ui.Button[Self]):
        del button  # unused
        _, series_name, *_ = get_ref(inter)
        series_infos = client.searcher.cache[series_name]
        await inter.response.send_message(
            view=SubscriptionView(series_name, series_infos),
            embed=series_embed(series_infos),
            ephemeral=True,
        )


class SourceSelect(ui.View):
    def __init__(self, sources: list[ExtendedSource], ref: str):
        super().__init__()

        self.ref = ref
        for src in sources:
            self.select_type.add_option(label=src.name)

    @ui.select(cls=ui.Select, placeholder="Source")
    async def select_type(self, inter: discord.Interaction, select: ui.Select[Self]):
        await inter.response.defer(thinking=True, ephemeral=True)

        source_name = select.values[0]
        source = next(s for s in MangaBot.sources if s.name == source_name)

        try:
            tmp: list[Download] = []
            elements_type: type[Download] = DownloadBytes
            async for download in source.download(self.ref):
                match download:
                    case DownloadBytes():
                        tmp.append(download)
                        elements_type = DownloadBytes
                    case DownloadUrl():
                        tmp.append(download)
                        elements_type = DownloadUrl
                    case DownloadInProgress():
                        pass  # TODO: send progression
        except Exception as e:
            await inter.followup.send(f"Error: {e}. Please try with another source.", ephemeral=True)
            return

        sizes = {DownloadBytes: 10, DownloadUrl: 5}
        for chunk in itertools.batched(tmp, sizes[elements_type]):
            if elements_type is DownloadBytes:
                chunk = cast(list[DownloadBytes], chunk)
                await inter.followup.send(
                    files=[discord.File(d.data, filename=d.filename, spoiler=True) for d in chunk]
                )
            elif elements_type is DownloadUrl:
                chunk = cast(list[DownloadUrl], chunk)
                await inter.followup.send("\n".join(d.url for d in chunk))


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"], root_logger=True, log_level=logging.INFO)
