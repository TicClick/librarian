import json
import logging

from discord.ext import commands

from librarian.discord import formatters
from librarian.discord.cogs import helpers

logger = logging.getLogger(__name__)


class Server(commands.Cog):
    SETTINGS_INDENT = 2

    @commands.command(name="promote")
    @helpers.is_promoted()
    async def promote_users(self, ctx: commands.Context):
        helper = ctx.bot.storage.discord
        if ctx.message.mentions:
            promoted = helper.promote_users(ctx.message.channel.guild.id, *[_.id for _ in ctx.message.mentions])
            if promoted:
                reply = "{} can change my settings on the server".format(formatters.UserFormatter.chain(promoted))
            else:
                reply = "all mentioned users are already promoted"
            return await ctx.message.channel.send(content=reply)

        return await ctx.message.channel.send(content="incorrect format; mention users instead")

    @commands.command(name="demote")
    @helpers.is_promoted()
    async def demote_users(self, ctx: commands.Context):
        helper = ctx.bot.storage.discord
        if ctx.message.mentions:
            demoted = helper.demote_users(ctx.message.channel.guild.id, *[_.id for _ in ctx.message.mentions])
            if demoted:
                reply = "{} can **not** change my settings on the server".format(
                    formatters.UserFormatter.chain(demoted)
                )
            else:
                reply = "none of mentioned users had access"
            return await ctx.message.channel.send(content=reply)

        return await ctx.message.channel.send(content="incorrect format; mention users instead")

    @commands.command(name="show")
    async def show(self, ctx: commands.Context, *args):
        if not args or len(args) > 1:
            return await ctx.send_help(Server.show.name)

        entity = args[0]
        reply = f"unknown type {entity}"

        if entity == "promoted":
            allowed = await helpers.promoted_users(ctx)
            reply = "users that can edit settings: {}".format(formatters.UserFormatter.chain(allowed))

        elif entity == "settings":
            settings = await ctx.bot.settings.get(ctx.message.channel.id)
            reply = formatters.codewrap(json.dumps(settings, indent=self.SETTINGS_INDENT))

        return await ctx.message.channel.send(content=reply)

    @commands.command(name="set")
    @helpers.is_promoted()
    async def set(self, ctx: commands.Context, *args):
        try:
            await ctx.bot.settings.update(
                ctx.message.channel.id, ctx.message.channel.guild.id, args
            )
            return await ctx.message.channel.send(content="done")
        except ValueError as e:
            reply = f"input error: {e}. try `.help {Server.set.name}` instead"
            return await ctx.message.channel.send(content=reply)
        except Exception:
            logger.exception(f"Failed to process {ctx.message.content} from user #{ctx.message.author.id}")
            reply = "unexpected error, can't do that. ask the bot's owner to investigate"
            return await ctx.message.channel.send(content=reply)

    @commands.command(name="reset")
    @helpers.is_promoted()
    async def reset(self, ctx: commands.Context):
        await ctx.bot.settings.reset(ctx.message.channel.id)
        reply = "removed custom settings for this channel"
        return await ctx.message.channel.send(content=reply)
