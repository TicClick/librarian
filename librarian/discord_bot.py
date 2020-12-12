import asyncio
import logging
import random
import re

import arrow
import discord
from discord.ext import commands

from librarian import routine
from librarian import utils


logger = logging.getLogger(__name__)


GREETINGS = [
    "a new wiki article is just a click away:",
    u"время исправлять чужие ошибки:",
    u"вышла новая книга Владимира Сорокина:",
    u"на GitHub опять что-то перевели:",
    u"хороших выходных:",
    u"объясняем на карточках вместе с Медузой:",
    u"вот ещё кое-что:",
    u"пожалуйста, взгляните:",
    u"доставайте красные карандаши:",
    u"если некуда девать свободное время:",
    u"новый пулл-реквест на небосклоне:",
    u"у нас на один перевод больше:",
    u"произошло что-то интересное:",
    u"у вас одно новое сообщение:",
    u"перевод? перевод!",
    u"вам письмо от неанонимного доброжелателя:",
    u"здесь могла быть ваша реклама:",
    u"нужна помощь:",
    "`wiki.by_language('russian').inflight_translations += 1`",
]

COLORS = {
    "open": 0x28a745,
    "draft": 0x6a737d,
    "closed": 0xd73a49,
    "merged": 0x6f42c1,
}

# https://github.com/primer/octicons
ICONS = {
    "open": "https://raw.githubusercontent.com/TicClick/librarian/main/media/check-circle-32.png",
    "draft": "https://raw.githubusercontent.com/TicClick/librarian/main/media/circle-32.png",
    "closed": "https://raw.githubusercontent.com/TicClick/librarian/main/media/circle-slash-32.png",
    "merged": "https://raw.githubusercontent.com/TicClick/librarian/main/media/check-circle-fill-32.png",
}


class PullCountParser:
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


class Client(commands.Bot):
    COMMAND_PREFIX = "."
    KILL_TIMEOUT = 10

    def __init__(
        self, *args, github=None, storage=None, assignee_login=None, title_regex=None,
        owner_id=None, review_channel=None, review_role_id=None, store_in_pins=False,
        **kwargs
    ):
        self.github = github
        self.storage = storage

        self.owner_id = owner_id
        self.review_channel = review_channel
        self.review_role_id = review_role_id
        self.title_regex = re.compile(title_regex)
        self.store_in_pins = store_in_pins

        super().__init__(*args, command_prefix=self.COMMAND_PREFIX, **kwargs)

        self.routines = {
            r.name: r
            for r in (
                routine.FetchGithubPulls(self),
                routine.MonitorGithubPulls(self, assignee_login, self.title_regex),
            )
        }

    def setup(self):
        self.add_command(count_pulls)
        self.add_command(report_status)
        self.add_command(show_disk_status)

        help_cmd = self.get_command("help")
        help_cmd.help = help_cmd.help.lower()

    def start_routines(self):
        logger.debug("Starting routines: %s", ", ".join(self.routines.keys()))
        return [r.loop() for r in self.routines.values()]

    async def shutdown(self):
        logger.info("Shutting down the bot")
        for r in self.routines.values():
            try:
                logger.info("Waiting on %s", r.name)
                await asyncio.wait_for(r.shutdown(), self.KILL_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error("%s has timed out during shutdown", r.name)

    async def on_ready(self):
        logger.info("Logged in as %s #%s", self.user, self.user.id)

    async def post_update(self, pull=None, channel_id=None, message_id=None):
        if isinstance(pull, int):
            pull = self.storage.pulls.by_number(pull)
        if pull is None:
            logger.warning("Can't post update: pull #%s not found", pull)
            return

        logger.debug("Update requested for pull #%s: message #%s of channel #%s", pull.number, message_id, channel_id)
        content = "<@&{}>, {}".format(self.review_role_id, random.choice(GREETINGS))
        description = (
            f"**author**: {pull.user_login}\n"
            f"**last update**: {pull.updated_at.date()} at {pull.updated_at.time()} GMT"
        )
        embed = discord.Embed(
            title="#{} {}".format(pull.number, pull.title),
            description=description,
            url=pull.url_for(self.github.repo),
            color=COLORS.get(pull.real_state, "closed"),
        )
        embed.set_footer(
            text=" | ".join((
                pull.real_state.upper(),
                "{comments} review comment{comments_suffix}".format(
                    comments=pull.review_comments,
                    comments_suffix="" if pull.review_comments == 1 else "s"
                ),
                "{changed_files} file{changed_files_suffix} affected".format(
                    changed_files=pull.changed_files,
                    changed_files_suffix="" if pull.changed_files == 1 else "s"
                )
            )),
            icon_url=ICONS.get(pull.real_state, "closed")
        )

        channel = self.get_channel(channel_id or self.review_channel)
        if channel is None:
            channel = await self.fetch_channel(channel_id or self.review_channel)

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

        if self.store_in_pins:
            try:
                if pull.state == "closed":
                    await message.unpin()
                elif not message.pinned:
                    await message.pin()
            except discord.DiscordException as exc:
                logger.error("Failed to pin/unpin the message #%s: %s", message.id, exc)

        return message.channel.id, message.id

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

        return await message.channel.send(content=utils.pretty_output(command, output))


def command(*args, **kwargs):
    async def is_owner(ctx: commands.Context):
        return await ctx.bot.is_owner(ctx.author)

    return commands.command(*args, **kwargs, checks=[is_owner])


def public_command(*args, **kwargs):
    return commands.command(*args, **kwargs)


@public_command(name="count")
async def count_pulls(ctx: commands.Context, *args):
    """
    pull requests merged within a time span

    .count: within the current month
    .count <month>: use lastmonth, or date like 2020-09
    .count <from> <to>: use two dates, for example, 2020-08-30 and 2020-09-30
    """

    try:
        start_date, end_date = PullCountParser.parse(args)
    except ValueError:
        return await ctx.send_help(count_pulls.name)

    pulls = ctx.bot.storage.pulls.count_merged(start_date=start_date.datetime, end_date=end_date.datetime)
    pulls = sorted(
        filter(lambda p: ctx.bot.title_regex.match(p.title), pulls),
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
        for pull in pulls:
            yield "- {}".format(pull.rich_repr(ctx.bot.github.repo))

    pages = list(utils.iterator(transform_pulls()))
    for i, page in enumerate(pages):
        embed = discord.Embed(description=page)
        embed.set_footer(text=f"{i + 1}/{len(pages)}")
        content = None if i else msg
        await ctx.message.channel.send(content=content, embed=embed)


@command(name="status")
async def report_status(ctx: commands.Context, *args):
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
    return await ctx.message.channel.send(content=utils.codewrap(statuses))


@public_command(name="disk")
async def show_disk_status(ctx: commands.Context, *args):
    """
    amount of space consumed/free on a machine that hosts Librarian
    """

    await ctx.bot.run_and_reply(ctx.message, ["/bin/df", "-Ph", "/"])
