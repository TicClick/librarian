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
        owner_id=None, review_channel=None, review_role_id=None,
        **kwargs
    ):
        self.github = github
        self.storage = storage

        self.owner_id = owner_id
        self.review_channel = review_channel
        self.review_role_id = review_role_id
        self.title_regex = re.compile(title_regex)

        super().__init__(*args, **kwargs)

        self.routines = [
            routine.FetchGithubPulls(self),
            routine.MonitorGithubPulls(self, assignee_login, self.title_regex),
        ]

        self.handlers = {
            ".count": self.count_pulls,
            ".status": self.report_status,
            ".disk": self.show_disk_status,
            ".help": self.print_help,
        }

        logger.debug("Handlers: %s", ", ".join(self.handlers.keys()))

    def start_routines(self):
        logger.debug("Starting routines: %s", ", ".join(r.name for r in self.routines))
        return [r.loop() for r in self.routines]

    async def shutdown(self):
        logger.info("Shutting down the bot")
        for r in self.routines:
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

    async def count_pulls(self, message: discord.Message, args):
        """
        pull requests merged within a time span

        .count: within the current month
        .count <month>: use lastmonth, or date like 2020-09
        .count <from> <to>: use two dates, for example, 2020-08-30 and 2020-09-30
        """

        start_date = None
        end_date = arrow.Arrow.utcnow()
        if args:
            if len(args) == 1:
                if args[0] == "lastmonth":
                    end_date = end_date.shift(days=-end_date.day)  # last month's last day
                    start_date = end_date.replace(day=1)  # current/last month's first day
                else:
                    try:
                        start_date = arrow.get(args[0])
                        end_date = start_date.shift(months=1, days=-1)
                    except ValueError:
                        pass
            else:
                if len(args) == 2:
                    try:
                        start_date = arrow.get(args[0])
                        end_date = arrow.get(args[1])
                    except ValueError:
                        pass

        else:
            start_date = end_date.replace(day=1)  # current/last month's first day

        if start_date is None:
            return await self.print_help(message, ".count")

        query_end_date = end_date.shift(days=1)
        pulls = self.storage.pulls.count_merged(start_date=start_date.date(), end_date=query_end_date.date())
        print(len(pulls))
        pulls = sorted(
            filter(lambda p: self.title_regex.match(p.title), pulls),
            key=lambda p: p.number
        )
        logger.debug(
            "Pulls in [%s, %s): %s",
            start_date, query_end_date, " ".join(str(_.number) for _ in pulls)
        )

        msg = "{count} pulls merged during [{start_date}, {end_date}]".format(
            count=len(pulls),
            start_date=start_date.date(),
            end_date=end_date.date()
        )

        if not pulls:
            return await message.channel.send(msg)

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

        statuses = await asyncio.gather(*map(routine_repr, self.routines))
        return await message.channel.send(content=codewrap(statuses))

    async def post_update(self, pull=None, channel_id=None, message_id=None):
        logger.debug("Update requested for pull #%s: message #%s of channel #%s", pull.number, message_id, channel_id)
        content = "<@&{}>, {}".format(self.review_role_id, random.choice(GREETINGS))
        description = (
            f"**author:** {pull.user_login}\n"
            f"last update: {pull.updated_at.date()} at {pull.updated_at.time()} GMT"
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
            icon_url="https://github.githubassets.com/favicons/favicon.png"
        )

        channel = self.get_channel(channel_id or self.review_channel)
        if message_id is None:
            message = await channel.send(content=content, embed=embed)
            logger.debug("New message created #%s", message.id)
            return message.channel.id, message.id

        else:
            try:
                logger.debug("Reading existing message #%s", message_id)
                message = await channel.fetch_message(message_id)

            except discord.NotFound:
                logger.error("Message #%s for pull #%s wasn't found", message_id, pull.number)
                return None, None

            else:
                logger.debug("Updating existing message #%s", message_id)
                await message.edit(embed=embed)
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


class DummyClient(Client):
    async def run(self, *args, **kwargs):
        return await asyncio.sleep(86400)
