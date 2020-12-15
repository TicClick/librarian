import asyncio
import logging
import random
import re

import discord
from discord.ext import commands

from librarian import routine
from librarian.discord.cogs import (
    pulls,
    system,
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

COLORS = {
    "open": 0x28a745,
    "draft": 0x6a737d,
    "closed": 0xd73a49,
    "merged": 0x6f42c1,
}

# https://github.com/primer/octicons
ICONS = {
    "open": "https://raw.githubusercontent.com/TicClick/librarian/main/media/check-circle-32.png",
    "draft": "https://raw.githubusercontent.com/TicClick/librarian/main/media/circle-32.png",
    "closed": "https://raw.githubusercontent.com/TicClick/librarian/main/media/circle-slash-32.png",
    "merged": "https://raw.githubusercontent.com/TicClick/librarian/main/media/check-circle-fill-32.png",
}


class HelpCommand(commands.DefaultHelpCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def interceptor(f):
            def add_line(line, *a, **kw):
                if self.no_category in line:
                    return
                return f(line, *a, **kw)
            return add_line

        self.paginator.add_line = interceptor(self.paginator.add_line)

    def get_ending_note(self, *_):
        pass


class Client(commands.Bot):
    COMMAND_PREFIX = "."
    KILL_TIMEOUT = 10

    def __init__(
        self, *args, github=None, storage=None, assignee_login=None, title_regex=None,
        owner_id=None, review_channel=None, review_role_id=None, store_in_pins=False,
        **kwargs
    ):
        self.github = github
        self.storage = storage

        self.owner_id = owner_id
        self.review_channel = review_channel
        self.review_role_id = review_role_id
        self.title_regex = re.compile(title_regex)
        self.store_in_pins = store_in_pins

        super().__init__(*args, command_prefix=self.COMMAND_PREFIX, help_command=HelpCommand(), **kwargs)

        self.routines = {
            r.name: r
            for r in (
                routine.FetchGithubPulls(self),
                routine.MonitorGithubPulls(self, assignee_login, self.title_regex),
            )
        }

    def setup(self):
        self.add_cog(pulls.PullCounter())
        self.add_cog(system.System())

    def start_routines(self):
        logger.debug("Starting routines: %s", ", ".join(self.routines.keys()))
        return [r.loop() for r in self.routines.values()]

    async def shutdown(self):
        logger.info("Shutting the client down")
        for r in self.routines.values():
            try:
                logger.info("Waiting on %s", r.name)
                await asyncio.wait_for(r.shutdown(), self.KILL_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error("%s has timed out during shutdown", r.name)

    async def on_ready(self):
        logger.info("Logged in as %s #%s", self.user, self.user.id)

    async def post_update(self, pull=None, channel_id=None, message_id=None):
        if isinstance(pull, int):
            pull = self.storage.pulls.by_number(pull)
        if pull is None:
            logger.warning("Can't post update: pull #%s not found", pull)
            return

        logger.debug("Update requested for pull #%s: message #%s of channel #%s", pull.number, message_id, channel_id)
        content = "<@&{}>, {}".format(self.review_role_id, random.choice(GREETINGS))
        description = (
            f"**author**: {pull.user_login}\n"
            f"**last update**: {pull.updated_at.date()} at {pull.updated_at.time()} GMT"
        )
        embed = discord.Embed(
            title="#{} {}".format(pull.number, pull.title),
            description=description,
            url=pull.url_for(self.github.repo),
            color=COLORS.get(pull.real_state, "closed"),
        )
        embed.set_footer(
            text=" | ".join((
                pull.real_state.upper(),
                "{comments} review comment{comments_suffix}".format(
                    comments=pull.review_comments,
                    comments_suffix="" if pull.review_comments == 1 else "s"
                ),
                "{changed_files} file{changed_files_suffix} affected".format(
                    changed_files=pull.changed_files,
                    changed_files_suffix="" if pull.changed_files == 1 else "s"
                )
            )),
            icon_url=ICONS.get(pull.real_state, "closed")
        )

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
                if pull.state == "closed":
                    await message.unpin()
                elif not message.pinned:
                    await message.pin()
            except discord.DiscordException as exc:
                logger.error("Failed to pin/unpin the message #%s: %s", message.id, exc)

        return message.channel.id, message.id
