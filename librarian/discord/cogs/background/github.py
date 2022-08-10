import asyncio
import logging
import typing

import arrow
import aiohttp.client_exceptions
from discord.ext import tasks
from sqlalchemy import exc as sql_exc

from librarian import storage
from librarian import types
from librarian.discord import formatters, errors
from librarian.discord.settings import custom
from librarian.discord.cogs.background import base


logger = logging.getLogger(__name__)


class FetchNewPulls(base.BackgroundCog):
    """
    The routine which is used by the bot to discover new pull requests posted on GitHub.

    On the initial setup, the routine does regular polling; once GitHub is exhausted
    and it has reached the most recent known pull, falls back to less regular update attempts.
    The polling loop is considerate of GitHub API limits --
    the intervals are picked to not hurt other parts of the system, even considering the 5,000 requests/hour limit.
    """

    LAST_PULL = "last_pull"
    SHORT_INTERVAL = 3
    LONG_INTERVAL = 600

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_pull: typing.Optional[int] = None

    @tasks.loop(seconds=SHORT_INTERVAL)
    async def loop(self):
        """
        Attempt to fetch the not-yet-submitted pull. See the class' docstring for a brief description.
        """

        if self.last_pull is None:
            self.last_pull = self.storage.metadata.load_field(self.LAST_PULL)
            if self.last_pull is None:
                self.last_pull = 1

        logger.info("%s: starting from pull #%s", self.name, self.last_pull)
        try:
            pull_data = await self.github.get_single_pull(self.last_pull)
            if pull_data is not None:
                logger.info("%s: fetched pull #%s", self.name, self.last_pull)
                if pull_data["state"] == formatters.PullState.OPEN.name:
                    number = pull_data["number"]
                    if self.storage.pulls.by_number(number):
                        logger.info("%s: skipping open pull #%d (fetched already)", self.name, number)
                        self.last_pull += 1
                    else:
                        logger.info(
                            "%s: open pull #%d is not fetched by %s. going into slow mode",
                            self.name, number, MonitorPulls.name
                        )
                        self.loop.change_interval(seconds=self.LONG_INTERVAL)
                    return

                try:
                    self.storage.pulls.save_from_payload(pull_data, insert=True)
                except sql_exc.IntegrityError:  # fetched by MonitorPulls
                    pass
                self.last_pull += 1

            elif await self.github.get_single_issue(self.last_pull) is not None:
                logger.info("%s: found issue #%s instead of a pull", self.name, self.last_pull)
                self.last_pull += 1

            else:
                logger.info("%s: no unknown pulls? going into slow mode", self.name)
                self.loop.change_interval(seconds=self.LONG_INTERVAL)
                await asyncio.sleep(self.LONG_INTERVAL - self.SHORT_INTERVAL)

        except aiohttp.client_exceptions.ClientError as exc:
            logger.error("%s: failed to fetch pull #%s: %s", self.name, self.last_pull, exc)

    @loop.after_loop
    async def shutdown(self):
        """ Save the current progress to the database. """
        self.storage.metadata.save_field(self.LAST_PULL, self.last_pull)

    async def status(self):
        """ Returns the state of GitHub API rate limits. """
        return dict(
            last_pull=self.last_pull,
            requests_left=self.github.ratelimit.left,
            requests_limit=self.github.ratelimit.limit,
            requests_reset=self.github.ratelimit.reset.format(),
        )


class MonitorPulls(base.BackgroundCog):
    """
    The routine used by the bot to fetch PR updates and distribute them to the subscribers (Discord channels).

    Pull requests' status is cached in a local database. On every loop, all open pulls
    are fetched and compared against these that are cached as open. The following three sets of PRs are then queried:
    1. Pulls that are already closed, but recorded as open;
    2. Pulls that are open, but the database doesn't have them yet;
    3. Pulls that are open and known to the database, but have an update.

    After everything is downloaded, every channel receives an update for its language-specific pulls.
    Optionally, other actions are performed, such as pinning messages, notifying reviewers,
    setting someone an assignee (requires the person to be the repository team's member).
    """

    INTERVAL = 60

    def __init__(self, bot: types.Bot, *args, **kwargs):
        super().__init__(bot, *args, **kwargs)
        self.assignee_login = bot.assignee_login

    async def update_pull_status(
        self, pull: storage.models.pull.Pull, channel_id: int, message_model: typing.Optional[storage.DiscordMessage]
    ) -> None:
        """
        Post a status update for a pull in a given channel, optionally pinning it and highlighting the reviewers.
        If `message_model` is not supplied, post a new message.

        :param pull: the pull model used to craft a message
        :param channel_id: identifier of a Discord channel to make a post in
        :param message_model: an already existing message model with id, if available
        """

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

    async def fetch_pulls(self, numbers: typing.Set[int]) -> typing.List[dict]:
        """
        Fetch full data for a lot of pulls asynchronously in parallel.
        :param numbers: a list of pull numbers to fetch.
        """

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
                if result is None:
                    logger.error("%s: received None for a pull #%d during fetching", self.name, result)
                else:
                    ok.append(result)
        return ok

    @tasks.loop(seconds=INTERVAL)
    async def loop(self) -> None:
        """
        Sync the bot's state with GitHub. See the class' docstring for a brief description.
        """

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
        logger.info("%s: fetched %d pull(s) in total", self.name, len(ok))
        with self.storage.session_scope() as s:
            saved = self.storage.pulls.save_many_from_payload(ok, s=s)
            await self.sort_for_updates(saved)

    async def sort_for_updates(self, pulls: typing.List[storage.models.pull.Pull]) -> None:
        """
        Asynchronously post update messages in channels that have subscribed to certain languages, and save their ids.
        """

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
                await self.handle_update_exception(result, item)
            elif result is not None:
                new_messages.append(result)

        self.storage.discord.save_messages(*new_messages)

    async def handle_update_exception(self, exc: errors.LibrarianException, item: typing.Tuple[int, int]):
        if isinstance(exc, errors.NoDiscordChannel):
            await self.bot.settings.reset(exc.channel_id)
            self.storage.discord.delete_channel_messages(exc.channel_id)

    async def status(self) -> dict:
        # FIXME: make something useful here
        return {}
