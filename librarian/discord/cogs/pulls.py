import logging

import arrow
import discord
from discord.ext import commands

from librarian.discord import (
    formatters,
    utils,
)
from librarian.discord.settings import custom

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
    @commands.command()
    async def count(self, ctx: commands.Context, *args):
        """
        list pull requests merged within a time span. works only when a language code is set for the channel

        .count: current month
        .count lastmonth: the last month
        .count <from> <to>: anything between these two. example: 2020-08 2020-10-01
        """

        settings = await ctx.bot.settings.get(ctx.message.channel.id)
        # TODO: use optional language code parameter
        language = settings.get(custom.Language.name)
        if language is None:
            reply = "no language set for this channel -- see `.help set` on how to do that"
            return await ctx.message.channel.send(content=reply)

        try:
            start_date, end_date = CountArgparser.parse(args)
        except ValueError:
            return await ctx.send_help(Pulls.count.name)

        pulls = ctx.bot.storage.pulls.count_merged(start_date=start_date.datetime, end_date=end_date.datetime)
        pulls = sorted(
            filter(lambda p: language.match(p.title), pulls),
            key=lambda p: p.merged_at
        )
        logger.debug(
            "Pulls for %s in [%s, %s): %s",
            language.code, start_date, end_date, " ".join(str(_.number) for _ in pulls)
        )

        date_range = "[{}, {}]".format(start_date.date(), end_date.date())
        msg = "{} pulls with `{}` language code merged during {}".format(len(pulls), language.code, date_range)

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
