import asyncio
import itertools as it
import logging

import arrow
import aiohttp.client_exceptions
from discord.ext import tasks

from librarian import storage
from librarian.discord.cogs.background import base

logger = logging.getLogger(__name__)


class FetchNewPulls(base.BackgroundCog):
    LAST_PULL = "last_pull"
    SHORT_INTERVAL = 3
    LONG_INTERVAL = 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_pull = None

    def fetched(self, pull_number):
        if self.last_pull is None:
            return False
        return pull_number <= self.last_pull

    @tasks.loop(seconds=SHORT_INTERVAL)
    async def loop(self):
        if self.last_pull is None:
            self.last_pull = self.storage.metadata.load_field(self.LAST_PULL)
            if self.last_pull is None:
                self.last_pull = 1

        logger.info("%s: starting from pull #%s", self.name, self.last_pull)
        try:
            pull_data = await self.github.get_single_pull(self.last_pull)
            if pull_data is not None:
                logger.info("%s: fetched pull #%s", self.name, self.last_pull)
                self.storage.pulls.save_from_payload(pull_data, insert=True)
                self.last_pull += 1

            elif await self.github.get_single_issue(self.last_pull) is not None:
                logger.info("%s: found issue #%s instead of a pull", self.name, self.last_pull)
                self.last_pull += 1

            else:
                logger.info("%s: no unknown pulls? setting interval to %d from now on", self.name, self.LONG_INTERVAL)
                self.loop.change_interval(seconds=self.LONG_INTERVAL)

        except aiohttp.client_exceptions.ClientError as exc:
            logger.error("%s: failed to fetch pull #%s: %s", self.name, self.last_pull, exc)

    @loop.after_loop
    async def shutdown(self):
        self.storage.metadata.save_field(self.LAST_PULL, self.last_pull)

    async def status(self):
        return dict(
            last_pull=self.last_pull,
            requests_left=self.github.ratelimit.left,
            requests_limit=self.github.ratelimit.limit,
            requests_reset=self.github.ratelimit.reset.format(),
        )


class MonitorPulls(base.BackgroundCog):
    INTERVAL = 60
    CUTOFF_PULL_NUMBER = 4450

    def __init__(self, bot, assignee_login=None, title_regex=None, *args, **kwargs):
        super().__init__(bot, *args, **kwargs)
        self.assignee_login = assignee_login
        self.title_regex = title_regex

    async def act_on_pulls(self, pulls):
        logger.info("%s: wanting to act on %d pulls: %s", self.name, len(pulls), sorted(_.number for _ in pulls))
        await self.add_assignee([_ for _ in pulls if _.user_login != self.assignee_login])

        messages = {
            pull.number: pull.discord_messages[0] if pull.discord_messages else None
            for pull in pulls if
            pull.number > self.CUTOFF_PULL_NUMBER
        }
        await self.update_messages(pulls, messages)

    async def update_messages(self, pulls, messages):
        logger.info(
            "%s: updating Discord messages for %d pulls: %s",
            self.name, len(pulls), sorted(_.number for _ in pulls)
        )
        new_messages = []
        for pull in pulls:
            message = messages.get(pull.number)
            channel_id, message_id = None, None
            if message is not None:
                channel_id = message.channel_id
                message_id = message.id
            new_channel_id, new_message_id = await self.bot.post_update(pull, channel_id, message_id)
            if message_id is None:
                new_messages.append(storage.DiscordMessage(
                    id=new_message_id,
                    channel_id=new_channel_id,
                    pull_number=pull.number
                ))
        self.storage.discord_messages.save(*new_messages)

    async def add_assignee(self, pulls):
        if not pulls:
            return

        logger.info(
            "%s: setting assignee for %d pulls: %s",
            self.name, len(pulls), sorted(_.number for _ in pulls)
        )
        async with self.github.make_session() as aio_session:
            tasks = []
            for pull in pulls:
                future = self.github.add_assignee(pull.number, self.assignee_login, session=aio_session)
                tasks.append(asyncio.create_task(future))
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for pull, result in zip(pulls, results):
            # 404 also means that you have no write access to a repository
            if isinstance(result, Exception):
                logger.error("%s: failed to add assignee for #%s: %s", self.name, pull.number, result)

    @tasks.loop(seconds=INTERVAL)
    async def loop(self):
        try:
            pulls = await self.github.pulls()
            logger.info(
                "%s: fetched incomplete details for %d pulls: %s",
                self.name, len(pulls), sorted(_["number"] for _ in pulls)
            )
        except aiohttp.client_exceptions.ClientError as exc:
            logger.error("%s: failed to fetch open pulls: %s", self.name, exc)
            return

        with self.storage.pulls.session_scope() as db_session:
            cached_active_pulls = {
                _.number: _
                for _ in self.storage.pulls.active_pulls(s=db_session)
            }
            logger.info(
                "%s: DB reports %d active pulls: %s",
                self.name, len(cached_active_pulls), sorted(cached_active_pulls.keys())
            )

        def open_pulls_numbers(cutoff_by_update=True):
            fetcher = self.bot.get_cog(FetchNewPulls.__name__)
            for p in pulls:
                pn = p["number"]
                # new pulls should always be added from FetchGithubPulls, unless they are reopened
                if pn not in cached_active_pulls:
                    if fetcher.fetched(pn):
                        yield pn
                    continue

                if (
                    cutoff_by_update and
                    arrow.get(p["updated_at"]) <= arrow.get(cached_active_pulls[pn].updated_at)
                ):
                    continue

                yield pn

        # fetch requests that are cached as not closed, but actually ARE closed
        closed_pulls = (
            set(cached_active_pulls.keys()) -
            set(open_pulls_numbers(cutoff_by_update=False))
        )
        logger.info(
            "%s: %d stale PR(s) (already closed): %s",
            self.name, len(closed_pulls), sorted(closed_pulls)
        )

        pulls_to_actualize = set(open_pulls_numbers())
        all_to_fetch = sorted(it.chain(pulls_to_actualize, closed_pulls))
        logger.info(
            "%s: %d open pulls to actualize, %d closed pulls listed as open in DB",
            self.name, len(pulls_to_actualize), len(closed_pulls)
        )

        async with self.github.make_session() as aio_session:
            tasks = []
            for number in all_to_fetch:
                tasks.append(asyncio.create_task(self.github.get_single_pull(number, aio_session)))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            results = {pull_id: result for pull_id, result in zip(all_to_fetch, results)}
        logger.info("%s: fetching done", self.name)

        with self.storage.pulls.session_scope() as db_session:
            to_save = []
            for pull_id, result in results.items():
                if isinstance(result, dict):
                    to_save.append(result)
                elif isinstance(result, Exception):
                    logger.error("%s: couldn't fetch pull #%s: %s", self.name, pull_id, result)

            logger.info(
                "%s: saving %d pulls to DB: %s",
                self.name, len(to_save), sorted([_["number"] for _ in to_save])
            )
            saved = self.storage.pulls.save_many_from_payload(to_save, s=db_session)
            saved_numbers = {_.number for _ in saved}

        def worth_updating():
            for pull in saved:
                if self.title_regex.match(pull.title) and pull.number in all_to_fetch:
                    yield pull

            for pull in cached_active_pulls.values():
                if (
                    self.title_regex.match(pull.title) and
                    pull.number not in saved_numbers and
                    not pull.discord_messages
                ):
                    yield pull

        await self.act_on_pulls(list(worth_updating()))

    async def status(self):
        return {}
