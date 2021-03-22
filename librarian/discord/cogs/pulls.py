import argparse
import logging
import typing

import arrow
import discord
from discord.ext import commands

from librarian.discord import (
    formatters,
    utils,
)
from librarian.discord.settings import custom

logger = logging.getLogger(__name__)


class CountArgparser(argparse.ArgumentParser):
    """
    Argument parser for the Pulls cog. Acceptable arguments: --from, --to, --language
    (each argument has a short form, like -l for --language).
    Unlike the default argparse.ArgumentParser, raises `ValueError` instead of `SystemExit` on parsing error.
    """

    def __init__(self):
        super().__init__()
        self.add_argument("-f", "--from", dest="from_", help="start date (inclusive)", required=True, type=arrow.get)
        self.add_argument("-t", "--to", dest="to", help="end date (exclusive)", required=True, type=arrow.get)
        self.add_argument("-l", "--lang", "--language", dest="language", help="language code")

    def error(self, message: str):
        raise ValueError(message)


class Pulls(commands.Cog):
    """
    The cog that includes a group of pull-related commands. See the individual methods and their descriptions.
    """

    def __init__(self):
        super().__init__()
        self.parser = CountArgparser()

    @commands.command()
    async def list(self, ctx: commands.Context, *args: tuple):
        """
        list pull requests merged within a time span

        usage:
            .list --from <date> --to <date> --language <code>

        examples:
            .list --from 2021-01-01 --to 2021-01-31 --language ru
            .list -f 2020-01 -t 2020-02 -l ru
        """

        try:
            args = self.parser.parse_args(args)
        except ValueError as exc:
            return await ctx.message.channel.send(content=str(exc))

        if args.language is None:
            settings = ctx.bot.settings.get(ctx.message.channel.id)
            language = settings.get(custom.Language.name)
            if language is None:
                reply = "need to add --language code or have the language set for this channel"
                return await ctx.message.channel.send(content=reply)
            args.language = language
        else:
            args.language = custom.Language(args.language)

        pulls = ctx.bot.storage.pulls.count_merged(start_date=args.from_.datetime, end_date=args.to.datetime)
        pulls = sorted(
            filter(lambda p: args.language.match(p.title), pulls),
            key=lambda p: p.merged_at
        )
        logger.debug(
            "Pulls for %s in [%s, %s): %s",
            args.language.code, args.from_.datetime, args.to.datetime, " ".join(str(_.number) for _ in pulls)
        )

        date_range = "[{}, {}]".format(args.from_.date(), args.to.date())
        msg = "{} pulls with `{}` language code merged during {}".format(len(pulls), args.language.code, date_range)

        if not pulls:
            return await ctx.message.channel.send(content=msg)

        def transform_pulls():
            for p in pulls:
                yield "- {}".format(formatters.PullFormatter.rich_repr(p, ctx.bot.github.repo))

        pages = list(utils.iterator(transform_pulls()))
        for i, page in enumerate(pages):
            embed = discord.Embed(description=page)
            embed.set_footer(text=f"{i + 1}/{len(pages)}")
            content = None if i else msg
            await ctx.message.channel.send(content=content, embed=embed)
