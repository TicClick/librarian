import abc
import asyncio
import itertools as it
import logging
import re
import time

import arrow
import aiohttp.client_exceptions

from librarian import storage


logger = logging.getLogger(__name__)


class Routine(metaclass=abc.ABCMeta):
    @abc.abstractproperty
    def interval(self):
        return 60

    @property
    def name(self):
        return self.__class__.__name__

    def __init__(self, discord):
        self.discord = discord
        self.github = discord.github
        self.storage = discord.storage

        self.stop_event = asyncio.Event()
        self.active = False

    async def continue_after_sleep(self, duration):
        try:
            if duration > 0:
                await asyncio.wait_for(self.stop_event.wait(), duration)
        except asyncio.TimeoutError:
            pass
        return self.stop_event.is_set()

    async def loop(self):
        sleep_for = 0
        self.active = True
        try:
            while True:
                if await self.continue_after_sleep(sleep_for):
                    logger.info("%s: shutdown requested", self.name)
                    return await self.shutdown()
                    logger.info("%s: shutdown complete", self.name)

                logger.info("%s: tick started", self.name)
                now = time.time()
                await self.run()

                spent = time.time() - now
                sleep_for = max(0, self.interval - spent)
                logger.info(
                    "%s: tick ended; spent %.2fs, will sleep for %.2fs",
                    self.name, spent, sleep_for
                )

        except (Exception, BaseException):
            logger.exception("%s: forcibly stopped:", self.name)

        finally:
            self.active = False

    @abc.abstractmethod
    async def shutdown(self):
        pass

    @abc.abstractmethod
    async def run(self):
        pass

    @abc.abstractmethod
    async def status(self):
        pass


class FetchGithubPulls(Routine):
    interval = 5
    slow_interval = 60
    last_pull_field = "last_pull"

    def __init__(self, discord):
        super().__init__(discord)
        self.last_pull = None

    async def run(self):
        if self.last_pull is None:
            self.last_pull = self.storage.metadata.load_field(self.last_pull_field)
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
                logger.info("%s: no unknown pulls? setting interval to %d", self.name, self.slow_interval)
                self.interval = self.slow_interval

        except aiohttp.client_exceptions.ClientError as exc:
            logger.error("%s: failed to fetch pull #%s: %s", self.name, self.last_pull, exc)

    async def shutdown(self):
        self.storage.metadata.save_field(self.last_pull_field, self.last_pull)

    async def status(self):
        return dict(
            last_pull=self.last_pull,
            requests_left=self.github.ratelimit.left,
            requests_limit=self.github.ratelimit.limit,
            requests_reset=self.github.ratelimit.reset.format(),
        )


class MonitorGithubPulls(Routine):
    interval = 60
    title_regex = re.compile(r"^\[(\w+.?)?RU(.+)?\]")

    def __init__(self, discord, assignee_login):
        super().__init__(discord)
        self.assignee_login = assignee_login

    async def act_on_pulls(self, pulls):
        logger.info("%s: wanting to act on %d pulls: %s", self.name, len(pulls), sorted(_["number"] for _ in pulls))

        def filter_pulls():
            for pull in pulls:
                if self.assignee_login == pull["user"]["login"]:
                    continue

                if self.assignee_login not in [
                    assignee["login"]
                    for assignee in pull["assignees"]
                ]:
                    yield pull

        await self.add_assignee(list(filter_pulls()))

        messages = {
            m.pull_number: m
            for m in self.storage.discord_messages.by_pull_numbers(*[_["number"] for _ in pulls])
            if m.pull_number > 4450  # the bot was started roughly that PR's appearance
        }
        await self.update_messages(pulls, messages)

    async def update_messages(self, pulls, messages):
        logger.info(
            "%s: updating Discord messages for %d pulls: %s",
            self.name, len(pulls), sorted(_["number"] for _ in pulls)
        )
        new_messages = []
        for pull in pulls:
            message = messages.get(pull["number"])
            channel_id, message_id = None, None
            if message is not None:
                channel_id = message.channel_id
                message_id = message.id
            new_channel_id, new_message_id = await self.discord.post_update(storage.Pull(pull), channel_id, message_id)
            if message_id is None:
                new_messages.append(storage.DiscordMessage(
                    id=new_message_id,
                    channel_id=new_channel_id,
                    pull_number=pull["number"]
                ))
        self.storage.discord_messages.save(*new_messages)

    async def add_assignee(self, pulls):
        if not pulls:
            return

        logger.info(
            "%s: setting assignee for %d pulls: %s",
            self.name, len(pulls), sorted(_["number"] for _ in pulls)
        )
        async with self.github.make_session() as aio_session:
            tasks = []
            for pull in pulls:
                new_assignees = [assignee["login"] for assignee in pull["assignees"]]
                logger.info(
                    "%s: new assignees for #%s = %s + %s",
                    self.name, pull["number"], new_assignees, self.assignee_login
                )
                new_assignees.append(self.assignee_login)
                future = self.github.update_single_issue(
                    pull["number"],
                    session=aio_session,
                    body={
                        "assignees": new_assignees
                    }
                )
                tasks.append(asyncio.create_task(future))
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for pull, result in zip(pulls, results):
            if isinstance(result, Exception):
                logger.error("%s: failed to set assignee for #%s: %s", self.name, pull["number"], result)

    async def run(self):
        try:
            pulls = await self.github.pulls()
        except aiohttp.client_exceptions.ClientError as exc:
            logger.error("%s: failed to fetch open pulls: %s", self.name, exc)
            return

        logger.info(
            "%s: fetched %d pulls: %s",
            self.name, len(pulls), sorted(_["number"] for _ in pulls)
        )

        with self.storage.pulls.session_scope() as db_session:
            cached_active_pulls = {
                _.number: _
                for _ in self.storage.pulls.active_pulls(db_session)
            }
        logger.info(
            "%s: DB reports %d active pulls: %s",
            self.name, len(cached_active_pulls), sorted(cached_active_pulls.keys())
        )

        def open_pulls():
            for p in pulls:
                if p["number"] not in cached_active_pulls:
                    continue
                if arrow.get(p["updated_at"]) > arrow.get(cached_active_pulls[p["number"]].updated_at):
                    yield p

        open_pulls_numbers = {_["number"] for _ in open_pulls()}

        # fetch requests that are cached as not closed, but actually ARE closed
        closed_pulls = set(cached_active_pulls.keys()) - open_pulls_numbers
        logger.info(
            "%s: %d stale PR(s) (already closed): %s",
            self.name, len(closed_pulls), sorted(closed_pulls)
        )

        all_to_fetch = sorted(it.chain(open_pulls_numbers, closed_pulls))
        logger.info(
            "%s: fetching %d open + %d cached pulls",
            self.name, len(open_pulls_numbers), len(closed_pulls)
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
            self.storage.pulls.save_many_from_payload(to_save)

        def worth_updating():
            for pull_id, result in results.items():
                if (
                    isinstance(result, dict) and
                    result["number"] in open_pulls_numbers and
                    self.title_regex.match(result["title"])
                ):
                    yield result

        await self.act_on_pulls(list(worth_updating()))

    async def status(self):
        return {}

    async def shutdown(self):
        pass
