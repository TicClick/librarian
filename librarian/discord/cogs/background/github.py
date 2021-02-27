import asyncio
import logging

import arrow
import aiohttp.client_exceptions
from discord.ext import tasks

from librarian import storage
from librarian.discord import formatters
from librarian.discord.settings import custom
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

    def __init__(self, bot, *args, **kwargs):
        super().__init__(bot, *args, **kwargs)
        self.assignee_login = bot.assignee_login

    async def update_pull_status(self, pull, channel_id, message_model):
        if pull.number <= self.CUTOFF_PULL_NUMBER:
            return None

        first_time = message_model is None
        channel_settings = self.bot.settings.get(channel_id)
        reviewer_role = channel_settings.get(custom.ReviewerRole.name)

        content = ""
        if reviewer_role:
            content = "{}, ".format(formatters.Highlighter.role(reviewer_role.cast()))
        content += channel_settings[custom.Language.name].random_highlight

        embed = formatters.PullFormatter.make_embed_for(pull, self.bot.github.repo)
        message = await self.bot.post_or_update(
            channel_id=channel_id, message_id=None if first_time else message_model.id,
            embed=embed, content=content
        )

        if message and channel_settings.get(custom.PinMessages.name).cast():
            if pull.state == formatters.PullState.CLOSED.name:
                await self.bot.unpin(message)
            else:
                await self.bot.pin(message)

        if not first_time or message is None:
            return None
        return storage.DiscordMessage(id=message.id, channel_id=channel_id, pull_number=pull.number)

    async def add_assignee(self, pulls):
        if not pulls or not self.assignee_login:
            return

        async with self.github.make_session() as aio_session:
            tasks = []
            for pull in pulls:
                if self.assignee_login in pull.assignees_logins + [pull.user_login]:
                    continue
                future = self.github.add_assignee(pull.number, self.assignee_login, session=aio_session)
                tasks.append(asyncio.create_task(future))
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

        if tasks:
            for pull, result in zip(pulls, results):
                # 404 also means that you have no write access to a repository
                if isinstance(result, Exception):
                    logger.error("%s: failed to add assignee for #%s: %s", self.name, pull.number, result)

    async def fetch_pulls(self, numbers):
        async with self.github.make_session() as aio_session:
            tasks = [
                asyncio.create_task(self.github.get_single_pull(number, aio_session))
                for number in numbers
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        ok = []
        for number, result in zip(numbers, results):
            if isinstance(result, Exception):
                logger.error("%s: couldn't fetch pull #%s: %s", self.name, number, result)
            else:
                ok.append(result)
        return ok

    @tasks.loop(seconds=INTERVAL)
    async def loop(self):
        try:
            live = {_["number"]: _ for _ in await self.github.pulls()}
            live_numbers = set(live.keys())
        except aiohttp.client_exceptions.ClientError as exc:
            logger.error("%s: failed to fetch open pulls: %s", self.name, exc)
            return

        cached = {_.number: _ for _ in self.storage.pulls.active_pulls()}
        cached_numbers = set(cached.keys())

        already_closed = cached_numbers - live_numbers
        new_open = live_numbers - cached_numbers
        updated = set()

        still_open = cached_numbers & live_numbers
        for p in live.values():
            pn = p["number"]
            if pn in still_open:
                if arrow.get(p["updated_at"]) > arrow.get(cached[pn].updated_at):
                    updated.add(pn)

        logger.info("%s: reported as open on GitHub: %s", self.name, sorted(live_numbers))
        logger.info("%s: reported as open by DB: %s", self.name, sorted(cached_numbers))
        logger.info(
            "%s: fetching %s (already closed), %s (new open), %s (updated)",
            self.name, sorted(already_closed), sorted(new_open), sorted(updated)
        )

        ok = await self.fetch_pulls(already_closed | new_open | updated)
        with self.storage.session_scope() as s:
            saved = self.storage.pulls.save_many_from_payload(ok, s=s)
            await self.sort_for_updates(saved)

    async def sort_for_updates(self, pulls):
        tasks, items = [], []
        for pull in pulls:
            for item in self.bot.settings.channels_by_language.values():
                language, channels = item.language, item.channels
                if language.match(pull.title):
                    messages = {_.channel_id: _ for _ in pull.discord_messages}
                    tasks.extend(
                        asyncio.create_task(self.update_pull_status(pull, channel_id, messages.get(channel_id)))
                        for channel_id in channels
                    )
                    items.extend((pull.number, channel_id) for channel_id in channels)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        new_messages = []
        for result, item in zip(results, items):
            if isinstance(result, Exception):
                logger.error(
                    "%s: failed to post an update for pull #%d in channel #%d: %s",
                    self.name, item[0], item[1], result
                )
            elif result is not None:
                new_messages.append(result)

        self.storage.discord.save_messages(*new_messages)

    async def status(self):
        return {}
