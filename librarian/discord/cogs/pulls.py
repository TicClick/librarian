import logging

import arrow
import discord
from discord.ext import commands

from librarian.discord import (
    formatters,
    utils,
)
from librarian.discord.cogs import decorators

logger = logging.getLogger(__name__)


class CountArgparser:
    LAST_MONTH = "lastmonth"

    @classmethod
    def today_end(cls):
        return arrow.get().ceil("day")

    @classmethod
    def last_month_end(cls):
        return cls.today_end().shift(months=-1).ceil("month")

    @classmethod
    def parse(cls, args):
        if not args:
            end_date = cls.today_end()
            return end_date.floor("month"), end_date

        if len(args) == 1 and args[0] == cls.LAST_MONTH:
            end_date = cls.last_month_end()
            return end_date.floor("month"), end_date

        if len(args) == 2:
            start_date = arrow.get(args[0])
            end_date = arrow.get(args[1])
            if start_date > end_date:
                start_date, end_date = end_date, start_date

            return start_date.floor("day"), end_date.ceil("day")

        raise ValueError(f"Incorrect arguments {args}")


class Pulls(commands.Cog):
    @decorators.public_command()
    async def count(self, ctx: commands.Context, *args):
        """
        pull requests merged within a time span

        .count: current month
        .count lastmonth: the last month
        .count <from> <to>: anything between these two. example: 2020-08 2020-10-01
        """

        try:
            start_date, end_date = CountArgparser.parse(args)
        except ValueError:
            return await ctx.send_help(Pulls.count.name)

        pulls = ctx.bot.storage.pulls.count_merged(start_date=start_date.datetime, end_date=end_date.datetime)
        pulls = sorted(
            filter(lambda p: ctx.bot.language.title_regex.match(p.title), pulls),
            key=lambda p: p.merged_at
        )
        logger.debug(
            "Interesting pulls in [%s, %s): %s",
            start_date, end_date, " ".join(str(_.number) for _ in pulls)
        )

        date_range = "[{}, {}]".format(start_date.date(), end_date.date())
        msg = "{} pulls merged during {}".format(len(pulls), date_range)

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
