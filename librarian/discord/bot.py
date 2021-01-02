import asyncio
import logging
import random
import re

import discord
from discord.ext import commands

from librarian.discord import formatters
from librarian.discord.cogs import (
    pulls,
    system,
)
from librarian.discord.cogs.background import (
    base,
    github as github_cogs,
)

logger = logging.getLogger(__name__)


GREETINGS = [
    "a new wiki article is just a click away:",
    u"время исправлять чужие ошибки:",
    u"вышла новая книга Владимира Сорокина:",
    u"на GitHub опять что-то перевели:",
    u"хороших выходных:",
    u"объясняем на карточках вместе с Медузой:",
    u"вот ещё кое-что:",
    u"пожалуйста, взгляните:",
    u"доставайте красные карандаши:",
    u"если некуда девать свободное время:",
    u"новый пулл-реквест на небосклоне:",
    u"у нас на один перевод больше:",
    u"произошло что-то интересное:",
    u"у вас одно новое сообщение:",
    u"перевод? перевод!",
    u"вам письмо от неанонимного доброжелателя:",
    u"здесь могла быть ваша реклама:",
    u"нужна помощь:",
    "`wiki.by_language('russian').inflight_translations += 1`",
]


class Client(commands.Bot):
    COMMAND_PREFIX = "."
    KILL_TIMEOUT = 10

    def __init__(
        self, *args, github=None, storage=None, assignee_login=None, title_regex=None,
        review_channel=None, review_role_id=None, store_in_pins=False,
        **kwargs
    ):
        self.github = github
        self.storage = storage

        self.review_channel = review_channel
        self.review_role_id = review_role_id
        self.title_regex = re.compile(title_regex)
        self.assignee_login = assignee_login
        self.store_in_pins = store_in_pins

        super().__init__(*args, command_prefix=self.COMMAND_PREFIX, **kwargs)

    def setup(self):
        self.add_cog(pulls.Pulls())
        self.add_cog(system.System())
        self.add_cog(github_cogs.FetchNewPulls(self))
        self.add_cog(github_cogs.MonitorPulls(self, assignee_login=self.assignee_login, title_regex=self.title_regex))

    async def start_routines(self):
        logger.debug("Starting cogs")
        await asyncio.gather(*(
            asyncio.create_task(cog.start())
            for _, cog in sorted(self.cogs.items()) if
            isinstance(cog, base.BackgroundCog)
        ))

    async def on_ready(self):
        logger.info("Logged in as %s #%s, starting routines", self.user, self.user.id)
        await self.start_routines()

    async def post_update(self, pull=None, channel_id=None, message_id=None):
        if isinstance(pull, int):
            pull = self.storage.pulls.by_number(pull)
        if pull is None:
            logger.warning("Can't post update: pull #%s not found", pull)
            return

        logger.debug("Update requested for pull #%s: message #%s of channel #%s", pull.number, message_id, channel_id)
        content = "<@&{}>, {}".format(self.review_role_id, random.choice(GREETINGS))
        embed = formatters.PullFormatter.make_embed_for(pull, self.github.repo)

        channel = self.get_channel(channel_id or self.review_channel)
        if channel is None:
            channel = await self.fetch_channel(channel_id or self.review_channel)

        if message_id is None:
            message = await channel.send(content=content, embed=embed)  # type: discord.Message
            logger.debug("New message created #%s", message.id)

        else:
            try:
                logger.debug("Reading existing message #%s", message_id)
                message = await channel.fetch_message(message_id)  # type: discord.Message

            except discord.NotFound:
                logger.error("Message #%s for pull #%s wasn't found", message_id, pull.number)
                return None, None

            else:
                logger.debug("Updating existing message #%s", message_id)
                await message.edit(embed=embed)

        if self.store_in_pins:
            try:
                if pull.state == formatters.PullState.CLOSED.name:
                    await message.unpin()
                elif not message.pinned:
                    await message.pin()
            except discord.DiscordException as exc:
                logger.error("Failed to pin/unpin the message #%s: %s", message.id, exc)

        return message.channel.id, message.id
