import asyncio
import logging

import discord
from discord.ext import commands

from librarian.discord import (
    formatters,
    languages,
)
from librarian.discord.cogs import (
    pulls,
    server,
    system,
)
from librarian.discord.cogs.background import (
    base,
    github as github_cogs,
)
from librarian.discord.settings import (
    custom,
    registry,
)

logger = logging.getLogger(__name__)


class Client(commands.Bot):
    COMMAND_PREFIX = "."
    KILL_TIMEOUT = 10

    def __init__(
        self, *args, github=None, storage=None, assignee_login=None,
        **kwargs
    ):
        self.github = github
        self.storage = storage
        self.assignee_login = assignee_login
        self.settings = registry.Registry(self.storage.discord)

        super().__init__(*args, command_prefix=self.COMMAND_PREFIX, **kwargs)

    def setup(self):
        self.add_cog(pulls.Pulls())
        self.add_cog(system.System())
        self.add_cog(github_cogs.FetchNewPulls(self))
        self.add_cog(github_cogs.MonitorPulls(self))
        self.add_cog(server.Server(self))

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

        channel_settings = self.settings[channel_id]
        content = ""
        reviewer_role = channel_settings.get(custom.ReviewerRole)
        if reviewer_role:
            content = "{}, ".format(formatters.Highlighter.role(reviewer_role))

        # FIXME: store language object in there somehow
        language = languages.LanguageMeta.get(channel_settings[custom.Language.name])
        content += language.random_highlight
        embed = formatters.PullFormatter.make_embed_for(pull, self.github.repo)

        channel = self.get_channel(channel_id)
        if channel is None:
            channel = await self.fetch_channel(channel_id)

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

        if channel_settings.get(custom.StoreInPins.name):
            try:
                if pull.state == formatters.PullState.CLOSED.name:
                    await message.unpin()
                elif not message.pinned:
                    await message.pin()
            except discord.DiscordException as exc:
                logger.error("Failed to pin/unpin the message #%s: %s", message.id, exc)

        return message.channel.id, message.id
