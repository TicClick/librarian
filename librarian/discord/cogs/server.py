import logging

from discord.ext import commands

from librarian.discord import formatters
from librarian.discord.cogs import helpers

logger = logging.getLogger(__name__)


class Server(commands.Cog):
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

    @commands.command(name="promoted")
    async def list_promoted_users(self, ctx: commands.Context):
        allowed = await helpers.promoted_users(ctx)
        reply = "users that can edit settings: {}".format(formatters.UserFormatter.chain(allowed))
        return await ctx.message.channel.send(content=reply)
