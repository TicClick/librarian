import asyncio
import logging

import discord
from discord.ext import commands

from librarian.discord import formatters
from librarian.discord.cogs import decorators
from librarian.discord.cogs.background import base

logger = logging.getLogger(__name__)


class Server(commands.Cog):
    async def allowed_users(self, ctx: commands.Context):
        helper = ctx.bot.storage.discord
        guild = ctx.message.channel.guild
        return helper.custom_promoted_users(guild.id) | {guild.owner.id}

    @decorators.public_command(name="promote")
    async def promote_users(self, ctx: commands.Context):
        if ctx.message.author.id not in await self.allowed_users(ctx):
            return await ctx.message.channel.send(content="you aren't allowed to promote users")

        helper = ctx.bot.storage.discord
        if ctx.message.mentions:
            promoted = helper.promote_users(ctx.message.channel.guild.id, *[_.id for _ in ctx.message.mentions])
            if promoted:
                reply = "{} can change my settings on the server".format(formatters.UserFormatter.chain(promoted))
            else:
                reply = "all mentioned users are already promoted"
            return await ctx.message.channel.send(content=reply)

        return await ctx.message.channel.send(content="incorrect format; mention users instead")

    @decorators.public_command(name="demote")
    async def demote_users(self, ctx: commands.Context, *args):
        if ctx.message.author.id not in await self.allowed_users(ctx):
            return await ctx.message.channel.send(content="you aren't allowed to demote users")

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

    @decorators.public_command(name="promoted")
    async def list_promoted_users(self, ctx: commands.Context, *args):
        allowed = await self.allowed_users(ctx)
        reply = "users that can edit settings: {}".format(formatters.UserFormatter.chain(allowed))
        return await ctx.message.channel.send(content=reply)
