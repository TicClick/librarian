import asyncio
import concurrent.futures as futures
import datetime as dt
import logging
import random

import arrow
import discord

from librarian import github
from librarian import routine

logger = logging.getLogger(__name__)

THREADPOOL_CAPACITY = 5
KILL_TIMEOUT = 10

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


class Client(discord.Client):
    def __init__(self, *args, **kwargs):
        self.github = kwargs.pop("github")
        assignee_login = kwargs.pop("assignee_login")

        self.storage = kwargs.pop("storage")

        self.owner_id = kwargs.pop("owner_id")
        self.review_channel = kwargs.pop("review_channel")
        self.review_role_id = kwargs.pop("review_role_id")

        super().__init__(*args, **kwargs)

        self.threadpool = futures.ThreadPoolExecutor(max_workers=THREADPOOL_CAPACITY)
        self.routines = [
            routine.FetchGithubPulls(self),
            routine.MonitorGithubPulls(self, assignee_login),
        ]

        self.handlers = {
            "/count": self.count_pulls,
            "/status": self.report_status,
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
            not message.content.startswith("/")
        ):
            logger.debug("Message %s ignored", message.id)
            return
        
        tokens = message.content.split()
        command, args = tokens[0], tokens[1:]
        if command not in self.handlers:
            return

        async with message.channel.typing():
            await self.handlers[command](message, args)

    async def count_pulls(self, message: discord.Message, args):
        start_date = None
        end_date = arrow.Arrow.utcnow()
        if args:
            if len(args) == 1 and args[0] == "lastmonth":
                end_date = end_date.shift(days=-end_date.day)  # last month's last day
                start_date = end_date.replace(day=1)  # current/last month's first day
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
            return await message.channel.send(
                "usage:\n"
                "- `/count`: PRs merged in current month;\n"
                "- `/count lastmonth`: PRs merged in the last month"
                "- `/count 2020-08-30 2020-09-30`: PRs merged during [`2020-08-30`, `2020-09-30`]"
            )

        query_end_date = end_date.shift(days=1)
        pulls = self.storage.pulls.count_merged(start_date=start_date.date(), end_date=query_end_date.date())
        logger.debug("Pulls in [%s, %s): %s", start_date, query_end_date, " ".join(_.number for _ in pulls))

        msg = "{count} pulls merged during [`{start_date}`, `{end_date}`]".format(
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
        content = "my coroutines:"

        async def routine_repr(r):
            status = await r.status()
            status_string = ", ".join(
                "{}={}".format(k, v)
                for k, v in sorted(status.items())
            )
            return "{strike}`{name}`{strike}: `{status_string}`".format(
                name=r.name,
                strike="" if r.active else "~~",
                status_string=status_string if status_string else "{}",
                intermediate="" if r.active else "``",
            )

        embed = discord.Embed(
            description="\n".join([
                "- {}".format(await routine_repr(r))
                for r in self.routines
            ])
        )
        return await message.channel.send(content=content, embed=embed)

    async def post_update(self, pull=None, channel_id=None, message_id=None):
        logger.debug("Update requested for pull #%s: message #%s of channel #%s", pull.number, message_id, channel_id)
        content = "<@&{}>, {}".format(self.review_role_id, random.choice(GREETINGS))
        description = (
            f"author: {pull.user_login}\n"
            f"last update: {pull.updated_at.date()} at {pull.updated_at.time()} GMT"
        )
        embed = discord.Embed(
            title="#{} \"{}\" by {}".format(pull.number, pull.title, pull.user_login),
            description=description,
            url=pull.url_for(self.github.repo),
            color=COLORS.get(pull.real_state, "closed"),
        )
        embed.set_footer(
            text="{state} | {comments} review comment{comments_suffix} | {changed_files} file{changed_files_suffix} affected".format(
                state=pull.real_state.upper(),
                comments=pull.review_comments,
                comments_suffix="" if pull.review_comments == 1 else "s",
                changed_files=pull.changed_files,
                changed_files_suffix="" if pull.changed_files == 1 else "s",
            ),
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


class DummyClient(Client):
    async def run(self, *args, **kwargs):
        return await asyncio.sleep(86400)
