import json
import logging

import discord as discord_py
from discord.ext import commands
from librarian import discord

from librarian.discord import formatters
from librarian.discord.cogs import helpers
from librarian.discord.settings import custom, registry

logger = logging.getLogger(__name__)


class Server(commands.Cog):
    SETTINGS_INDENT = 2

    def __init__(self):
        super().__init__()
        self.set.help += "".join(
            "\n  {}".format(line)
            for line in registry.parameters_combined_docs()
        )

    @commands.command(name="promote")
    @helpers.is_promoted()
    async def promote_users(self, ctx: commands.Context):
        """
        allow users to change the bot's settings or promote others.
        always available to the server's owner and managers

        usage:
            .promote @Nickname @AnotherNickname
        """

        helper = ctx.bot.storage.discord
        if ctx.message.mentions:
            promoted = helper.promote_users(ctx.message.channel.guild.id, *[_.id for _ in ctx.message.mentions])
            if promoted:
                reply = "enabled settings for {}".format(formatters.Highlighter.chain_users(promoted))
            else:
                reply = "all mentioned users are already promoted"
            return await ctx.message.channel.send(content=reply)

        return await ctx.message.channel.send(content="incorrect format; mention users instead")

    @commands.command(name="demote")
    @helpers.is_promoted()
    async def demote_users(self, ctx: commands.Context):
        """
        disallow users to change the bot's settings or promote others.
        the server's owner and managers are always promoted

        usage:
            .demote @Nickname @AnotherNickname
        """

        helper = ctx.bot.storage.discord
        if ctx.message.mentions:
            demoted = helper.demote_users(ctx.message.channel.guild.id, *[_.id for _ in ctx.message.mentions])
            if demoted:
                reply = "**disabled** settings for {}".format(
                    formatters.Highlighter.chain_users(demoted)
                )
            else:
                reply = "none of mentioned users had access"
            return await ctx.message.channel.send(content=reply)

        return await ctx.message.channel.send(content="incorrect format; mention users instead")

    @commands.command(name="show")
    async def show(self, ctx: commands.Context, *args):
        """
        print different things

        usage:
            .show <thing type>

        examples:
            .show promoted: list users that can change settings (besides admins/managers)
            .show settings: current channel settings
        """

        if not args or len(args) > 1:
            return await ctx.send_help(Server.show.name)

        entity = args[0]
        reply = f"unknown category `{entity}` -- see `.help show`"

        if entity == "promoted":
            allowed = await helpers.promoted_users(ctx)
            reply = (
                "users that can edit settings:\n"
                "- default: server admins and managers"
            )
            if allowed:
                reply += "\n- custom: {}".format(formatters.Highlighter.chain_users(allowed))

        elif entity == "settings":
            settings = ctx.bot.settings.get(ctx.message.channel.id, raw=True)
            reply = formatters.codewrap(json.dumps(settings, indent=self.SETTINGS_INDENT))

        return await ctx.message.channel.send(content=reply)

    # the final docstring for this command is generated automatically
    @commands.command(name="set")
    @helpers.is_promoted()
    async def set(self, ctx: commands.Context, *args):
        """
        change translation-related settings

        usage:
            .set setting-name setting-value ...

        example:
            .set language ru reviewer-role 12345

        known settings:
        """

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
        """
        IMMEDIATELY reset settings and promoted users for this channel,
        effectively disabling all pings and GitHub-related subscriptions

        usage:
            .reset
        """

        await ctx.bot.settings.reset(ctx.message.channel.id)
        reply = "removed custom settings for this channel"
        return await ctx.message.channel.send(content=reply)

    @commands.command(name="fetch")
    @helpers.is_promoted()
    async def fetch(self, ctx: commands.Context):
        """
        repost missing open pulls for current channel's language from GitHub

        usage:
            .fetch
        """

        channel_id = ctx.message.channel.id
        language = ctx.bot.settings.get(channel_id).get(custom.Language.name)
        if language is None:
            content = "no language set for this channel (see `.set help`)"
            return await ctx.message.channel.send(content=content)

        # FIXME: put update_pull_status somewhere else
        monitor = ctx.bot.get_cog("MonitorPulls")
        messages = []
        for pull in ctx.bot.storage.pulls.active_pulls():
            message_exists = any(
                _.channel_id == channel_id
                for _ in (pull.discord_messages or [])
            )
            if language.match(pull.title) and not message_exists:
                try:
                    messages.append(await monitor.update_pull_status(pull, channel_id, None))
                except discord_py.DiscordException as exc:
                    logger.error(
                        "%s: Failed to post a new message for pull #%d in channel #%d: %s",
                        self.name, pull.number, channel_id, exc
                    )

        if messages:
            ctx.bot.storage.discord.save_messages(*messages)
        await ctx.message.channel.send(content=f"fetched {len(messages)} pull(s)")
