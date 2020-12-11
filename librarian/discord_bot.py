import asyncio
import logging
import random
import re
import textwrap

import arrow
import discord

from librarian import routine


logger = logging.getLogger(__name__)

KILL_TIMEOUT = 10
COMMAND_PREFIX = "."

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


def codewrap(obj):
    def inner():
        yield "```"
        if isinstance(obj, (str, bytes)):
            yield obj
        elif hasattr(obj, "__iter__"):
            for elem in obj:
                yield str(elem)
        yield "```"

    return "\n".join(inner())


class Client(discord.Client):
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

        super().__init__(*args, **kwargs)

        self.routines = {
            r.name: r
            for r in (
                routine.FetchGithubPulls(self),
                routine.MonitorGithubPulls(self, assignee_login, self.title_regex),
            )
        }

        self.handlers = {
            ".count": self.count_pulls,
            ".status": self.report_status,
            ".disk": self.show_disk_status,
            ".help": self.print_help,
        }

        logger.debug("Handlers: %s", ", ".join(self.handlers.keys()))

    def start_routines(self):
        logger.debug("Starting routines: %s", ", ".join(self.routines.keys()))
        return [r.loop() for r in self.routines.values()]

    async def shutdown(self):
        logger.info("Shutting down the bot")
        for r in self.routines.values():
            try:
                logger.info("Waiting on %s", r.name)
                await asyncio.wait_for(r.shutdown(), KILL_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error("%s has timed out during shutdown", r.name)

    async def on_ready(self):
        logger.info("Logged in as %s #%s", self.user, self.user.id)

    async def on_message(self, message: discord.Message):
        logger.debug("Message #%s from %s #%s", message.id, message.author, message.author.id)
        if (
            message.author == self.user or
            (self.owner_id is not None and message.author.id != self.owner_id) or
            not message.content.startswith(COMMAND_PREFIX)
        ):
            logger.debug("Message #%s ignored", message.id)
            return

        tokens = message.content.split()
        command, args = tokens[0], tokens[1:]
        if command not in self.handlers:
            return

        async with message.channel.typing():
            await self.handlers[command](message, args)

    @staticmethod
    def parse_count_range(start_date, end_date):
        today = arrow.Arrow.utcnow().floor("day")

        if start_date is None:
            if end_date is None:
                return today.floor("month"), today.ceil("day")

            if end_date == "lastmonth":
                first_day = today.shift(months=-1).floor("month")
                return first_day, first_day.ceil("month")

            raise ValueError("Logic error: can't use end_date without start_date")

        if end_date is None:
            start_date = arrow.get(start_date).floor("month")
            return start_date, start_date.ceil("month")

        return arrow.get(start_date).floor("day"), arrow.get(end_date).ceil("day")

    async def count_pulls(self, message: discord.Message, args):
        """
        pull requests merged within a time span

        .count: within the current month
        .count <month>: use lastmonth, or date like 2020-09
        .count <from> <to>: use two dates, for example, 2020-08-30 and 2020-09-30
        """

        if not args:
            start_date, end_date = None, None
        elif len(args) == 1:
            if args[0] == "lastmonth":
                start_date, end_date = [None, args[0]]
            else:
                start_date, end_date = [args[0], None]
        else:
            start_date, end_date = args[:2]

        try:
            start_date, end_date = self.parse_count_range(start_date, end_date)
        except ValueError:
            return await self.print_help(message, ".count")

        pulls = self.storage.pulls.count_merged(start_date=start_date.datetime, end_date=end_date.datetime)
        pulls = sorted(
            filter(lambda p: self.title_regex.match(p.title), pulls),
            key=lambda p: p.number
        )
        logger.debug(
            "Pulls in [%s, %s): %s",
            start_date, end_date, " ".join(str(_.number) for _ in pulls)
        )

        msg = "{count} pulls merged during [{start_date}, {end_date}]".format(
            count=len(pulls),
            start_date=start_date.date(),
            end_date=end_date.date()
        )

        if not pulls:
            return await message.channel.send(content=msg)

        def pull_repr(pull):
            return "`{merged_at}`: [{title}]({url}) by {author}".format(
                title=pull.title,
                url=pull.url_for(self.github.repo),
                author=pull.user_login,
                merged_at=pull.merged_at.date(),
            )

        embed = discord.Embed(
            description="\n".join((
                "- {}".format(pull_repr(pull))
                for pull in pulls
            ))
        )
        embed.set_footer(text="{} total".format(len(pulls)))
        return await message.channel.send(content=msg, embed=embed)

    async def report_status(self, message: discord.Message, args):
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

        statuses = await asyncio.gather(*map(routine_repr, self.routines.values()))
        return await message.channel.send(content=codewrap(statuses))

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
            return None

        return codewrap((
            "librarian@librarian:~$ {}".format(" ".join(command)),
            out.decode("utf-8")
        ))

    async def run_and_reply(self, message: discord.Message, command):
        command = list(map(str, command))
        logger.info("Running %r on behalf of %s #%s", command, message.author, message.author.id)
        content = await self.run_command(command)
        if content is None:
            content = "Failed to execute `{}` (logged the error, though)".format(" ".join(command))
        await message.channel.send(content=content)

    async def show_disk_status(self, message: discord.Message, args):
        """
        amount of space consumed/free on a machine that hosts Librarian
        """

        await self.run_and_reply(message, ["/bin/df", "-Ph", "/"])

    async def print_help(self, message: discord.Message, args):
        """
        bot usage instructions

        .help: list commands and their synopsis
        .help <command>: specific info about <command>
        """

        reply = None
        command = None
        if isinstance(args, str):
            command = args
        elif args:
            command = args[0]
        else:
            command = None

        if command is None:
            reply = codewrap((
                "{}: {}".format(command, func.__doc__.strip().splitlines()[0])
                for command, func in sorted(self.handlers.items())
            ))
        else:
            if not command.startswith(COMMAND_PREFIX):
                command = COMMAND_PREFIX + command

            if command not in self.handlers:
                reply = "unknown command `.{}` -- try plain `.help` instead".format(command)
            else:
                reply = codewrap(textwrap.dedent(self.handlers[command].__doc__))

        await message.channel.send(content=reply)
