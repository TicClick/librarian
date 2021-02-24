import random

import discord as discord_py
import pytest

from librarian.storage.models import (
    discord,
    pull,
)
from librarian.discord import formatters
from librarian.discord.settings import custom
from librarian.discord.cogs.background import github


class TestMonitorPulls:
    SAMPLE_SZ = 30

    async def test__fetch_pulls(self, client, existing_pulls, mock_unstable_github, mocker):
        github.logger = mocker.Mock()
        monitor = github.MonitorPulls(client)
        sampled = random.sample(existing_pulls, self.SAMPLE_SZ)

        results = await monitor.fetch_pulls(set(_["number"] for _ in sampled))
        for r in results:
            assert isinstance(r, dict), results
        if len(results) < len(sampled):
            assert github.logger.error.called

    async def test__update_pull_status__before_cutoff(self, client, existing_pulls, mocker):
        monitor = github.MonitorPulls(client)
        monitor.CUTOFF_PULL_NUMBER = max(_["number"] for _ in existing_pulls) + 100
        monitor.bot.post_update = mocker.Mock()

        monitor.update_pull_status(pull.Pull(existing_pulls[0]), 1, None)
        assert not monitor.bot.post_update.called

    @pytest.mark.parametrize("pin_message", [True, False])
    @pytest.mark.parametrize("reviewer_specified", [True, False])
    @pytest.mark.parametrize("pull_state", [formatters.PullState.OPEN.name, formatters.PullState.CLOSED.name])
    @pytest.mark.parametrize("is_message_pinned", [True, False])
    @pytest.mark.parametrize("is_new_message", [True, False])
    async def test__update_pull_status(
        self, client, existing_pulls, mocker, storage, language_code,
        reviewer_specified, pin_message, is_new_message, is_message_pinned, pull_state
    ):
        monitor = github.MonitorPulls(client)
        monitor.CUTOFF_PULL_NUMBER = 0
        p = pull.Pull(next(iter(_ for _ in existing_pulls if _["state"] == pull_state)))

        channel_id = 123
        message_id = 1234
        guild_id = 1
        reviewer_role = 12345

        if not is_new_message:
            message_model = discord.DiscordMessage(
                id=message_id, channel_id=channel_id, pull_number=p.number
            )
            storage.discord.save_messages(message_model)
        else:
            message_model = None

        settings = [custom.Language.name, language_code]
        if reviewer_specified:
            settings += [custom.ReviewerRole.name, reviewer_role]
        if pin_message:
            settings += [custom.PinMessages.name, pin_message]
        await client.settings.update(channel_id, guild_id, settings)

        message = mocker.Mock(
            id=message_id,
            pin=mocker.AsyncMock(),
            unpin=mocker.AsyncMock(),
            pinned=not is_new_message and is_message_pinned,
        )
        client.post_or_update = mocker.AsyncMock(return_value=message)
        client.pin = mocker.AsyncMock(side_effect=client.pin)
        client.unpin = mocker.AsyncMock(side_effect=client.unpin)

        formatters.PullFormatter.make_embed_for = mocker.Mock(
            side_effect=formatters.PullFormatter.make_embed_for
        )

        returned_message_model = await monitor.update_pull_status(
            p, channel_id, message_model=message_model
        )

        assert client.post_or_update.called
        post_kws = client.post_or_update.call_args.kwargs

        if message_model is None:
            assert post_kws["message_id"] is None

        if reviewer_specified:
            assert post_kws["content"].startswith("<@&{}>, ".format(reviewer_role))

        assert any(
            post_kws["content"].endswith(hl)
            for hl in custom.Language(language_code).highlights
        )

        assert formatters.PullFormatter.make_embed_for.called
        assert isinstance(post_kws["embed"], discord_py.Embed)

        if pull_state == formatters.PullState.OPEN.name:
            if pin_message:
                assert client.pin.called

            if message.pinned:
                assert not message.pin.called

            assert not message.unpin.called
            assert not client.unpin.called
        else:
            if pin_message:
                assert client.unpin.called
                if message.pinned:
                    assert message.unpin.called

            assert not message.pin.called
            assert not client.pin.called

        if is_new_message:
            assert isinstance(returned_message_model, discord.DiscordMessage)
            assert returned_message_model.id == message.id
        else:
            assert returned_message_model is None

    async def test__sort_for_updates(self):
        raise NotImplementedError()

    async def test__loop(self):
        raise NotImplementedError()
