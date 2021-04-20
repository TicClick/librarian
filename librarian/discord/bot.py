import asyncio
import logging

import discord
import discord.errors
from discord.ext import commands
import discord.ext.commands.errors as commands_errors

from librarian.discord import errors
from librarian.discord.cogs import (
    pulls,
    server,
    system,
)
from librarian.discord.cogs.background import (
    base,
    github as github_cogs,
)
from librarian.discord.settings import registry

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

    async def _on_command_error_inner(self, ctx, exception):
        if isinstance(exception, commands_errors.CommandNotFound):
            return await ctx.message.channel.send(
                content="no such command `{}` -- try `{}help` instead".format(
                    ctx.invoked_with, self.COMMAND_PREFIX
                )
            )
        else:
            return await super().on_command_error(ctx, exception)

    async def on_command_error(self, ctx, exception):
        try:
            return await self._on_command_error_inner(ctx, exception)
        except discord.errors.DiscordException as new_exc:
            logger.info(
                "Failed to notify %r in #%d about the error %r: %s",
                ctx.message.author, ctx.message.channel.id, exception, new_exc
            )

    def setup(self):
        self.add_cog(pulls.Pulls())
        self.add_cog(system.System())
        self.add_cog(github_cogs.FetchNewPulls(self))
        self.add_cog(github_cogs.MonitorPulls(self))
        self.add_cog(server.Server())

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

    async def post_or_update(self, channel_id, message_id=None, content=None, embed=None):
        try:
            channel = self.get_channel(channel_id)
            if channel is None:
                channel = await self.fetch_channel(channel_id)
        except discord.errors.NotFound:
            raise errors.NoDiscordChannel(channel_id)

        if message_id is None:
            message = await channel.send(content=content, embed=embed)  # type: discord.Message
            logger.debug("New message #%s created in #%s", message.id, channel.id)
            return message

        else:
            message = None
            try:
                logger.debug("Reading/updating existing message #%s", message_id)
                message = await channel.fetch_message(message_id)  # type: discord.Message
            except discord.NotFound:
                logger.error("Message #%s wasn't found", message_id)
                self.storage.discord.delete_message(message_id, channel_id)
            else:
                await message.edit(embed=embed)
            finally:
                return message

    async def pin(self, message):
        if message.pinned:
            return
        try:
            await message.pin()
        except discord.DiscordException as exc:
            logger.error("Failed to pin the message #%s in #%s: %s", message.id, message.channel.id, exc)

    async def unpin(self, message):
        if not message.pinned:
            return
        try:
            await message.unpin()
        except discord.DiscordException as exc:
            logger.error("Failed to unpin the message #%s in #%s: %s", message.id, message.channel.id, exc)
