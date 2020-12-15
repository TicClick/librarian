import asyncio
import logging

import discord
from discord.ext import commands

from librarian.discord.cogs import decorators
from librarian.discord import formatters

logger = logging.getLogger(__name__)


class System(commands.Cog):
    @decorators.command(name="status")
    async def report_status(self, ctx: commands.Context, *args):
        """
        system information. probably only interesting to the bot owner
        """

        async def routine_repr(r):
            status = await r.status()
            status_string = ", ".join(
                "{}={}".format(k, v)
                for k, v in sorted(status.items())
            )
            return "[{status}] {name}: {status_string}".format(
                status=" OK " if r.active else "DEAD",
                name=r.name,
                status_string=status_string if status_string else "{}"
            )

        statuses = await asyncio.gather(*map(routine_repr, ctx.bot.routines.values()))
        return await ctx.message.channel.send(content=formatters.codewrap(statuses))

    async def run_command(self, command):
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            out, err = await proc.communicate()
            logger.info("%r succeeded, stdout/stderr follow:", command)
            logger.info(out)

        except (Exception, BaseException):
            logger.exception("Failed to run %r", command)
            return None, None

        return proc.returncode, out.decode("utf-8")

    async def run_and_reply(self, message: discord.Message, command):
        command = list(map(str, command))
        logger.info("Running %r on behalf of %s #%s", command, message.author, message.author.id)
        rc, output = await self.run_command(command)
        if rc is None:
            return await message.channel.send(
                content="Failed to execute `{}` (logged the error, though)".format(" ".join(command))
            )

        if rc:
            return await message.channel.send(
                content="`{}` has died with return code {}".format(" ".join(command), rc)
            )

        return await message.channel.send(content=formatters.pretty_output(command, output))

    @decorators.public_command(name="disk")
    async def show_disk_status(self, ctx: commands.Context, *args):
        """
        amount of space consumed/free on a machine that hosts Librarian
        """

        await self.run_and_reply(ctx.message, ["/bin/df", "-Ph", "/"])
