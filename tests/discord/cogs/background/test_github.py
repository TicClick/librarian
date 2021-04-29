import collections
import random

import discord as discord_py
import discord.errors as discord_errors
import pytest

from librarian.storage.models import (
    discord,
    pull,
)
from librarian.discord import formatters
from librarian.discord.settings import custom
from librarian.discord.cogs.background import github


@pytest.fixture
def codes_by_titles(titles_by_codes):
    codes_by_titles = {}
    for k, v in titles_by_codes.items():
        for vv in v:
            codes_by_titles[vv] = k
    yield codes_by_titles


class TestUpdatePullStatus:
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


class TestSortForUpdates:
    exception_str = "unique exception"

    async def __sort_for_updates_prepare(
        self, client, storage, existing_pulls, mocker, codes_by_titles, channel_ids, guild_id,
        save_pull, pull_state, raise_exc=False
    ):
        monitor = github.MonitorPulls(client)

        def side_effect(channel_id, message_id, embed, content):
            if raise_exc:
                raise RuntimeError(self.exception_str)

            msg = mocker.Mock()
            msg.id = channel_id + 100
            msg.channel.id = channel_id
            return msg

        client.post_or_update = mocker.AsyncMock(side_effect=side_effect)
        client.pin = mocker.AsyncMock(side_effect=client.pin)
        client.unpin = mocker.AsyncMock(side_effect=client.unpin)

        monitor.update_pull_status = mocker.AsyncMock(side_effect=monitor.update_pull_status)

        p = next(iter(
            _
            for _ in existing_pulls if
            (
                codes_by_titles[_["title"]] and
                _["state"] == pull_state
            )
        ))
        language = custom.Language(codes_by_titles[p["title"]])

        for channel_id in channel_ids:
            await client.settings.update(channel_id, guild_id, [language.name, language.code])

        if save_pull:
            storage.pulls.save_from_payload(p)

        return p, monitor

    @pytest.mark.parametrize("raise_exc", [True, False])
    @pytest.mark.parametrize("pull_state", ["open", "closed"])
    @pytest.mark.parametrize("channel_ids", [[123], [123, 1234]])
    async def test__sort_for_updates__new_pull(
        self, client, storage, existing_pulls, mocker, codes_by_titles, channel_ids, pull_state, raise_exc
    ):
        guild_id = 1
        p, monitor = await self.__sort_for_updates_prepare(
            client, storage, existing_pulls, mocker, codes_by_titles, channel_ids, guild_id,
            save_pull=False, pull_state=pull_state, raise_exc=raise_exc
        )

        github.logger = mocker.Mock()

        with storage.session_scope():
            pp = pull.Pull(p)
            await monitor.sort_for_updates([pp])

        for (done, _), expected in zip(
            sorted(monitor.update_pull_status.call_args_list),
            sorted((pp, ch_id, None) for ch_id in channel_ids)
        ):
            assert done[0].number == expected[0].number
            assert done[1] == expected[1]
            assert done[2] is None

        if raise_exc:
            assert github.logger.error.called
        else:
            expected_len = len(channel_ids) if pull_state == "open" else 0
            assert len(storage.discord.messages_by_pull_numbers(pp.number)) == expected_len

    @pytest.mark.parametrize("pull_state", ["open", "closed"])
    @pytest.mark.parametrize("channel_ids", [[123], [123, 1234]])
    async def test__sort_for_updates__existing_pull(
        self, client, storage, existing_pulls, mocker, codes_by_titles, channel_ids, pull_state
    ):
        guild_id = 1
        p, monitor = await self.__sort_for_updates_prepare(
            client, storage, existing_pulls, mocker, codes_by_titles, channel_ids, guild_id,
            save_pull=True, pull_state=pull_state
        )

        pull_number = p["number"]
        msgs = {
            channel_id: discord.DiscordMessage(
                id=channel_id + 100, channel_id=channel_id, pull_number=pull_number
            )
            for channel_id in channel_ids
        }
        storage.discord.save_messages(*msgs.values())
        pp = storage.pulls.by_number(pull_number)
        await monitor.sort_for_updates([pp])

        for (done, _), expected in zip(
            sorted(monitor.update_pull_status.call_args_list),
            sorted((pp, ch_id, msgs[ch_id]) for ch_id in channel_ids)
        ):
            assert done[0].number == expected[0].number
            assert done[1] == expected[1]
            assert done[2].id == expected[2].id

    async def test__exception_handling_no_channel(
        self, client, storage, existing_pulls, mocker, codes_by_titles
    ):
        monitor = github.MonitorPulls(client)

        p = next(iter(
            _
            for _ in existing_pulls if
            (
                codes_by_titles[_["title"]] and
                _["state"] == "open"
            )
        ))
        language = custom.Language(codes_by_titles[p["title"]])
        await client.settings.update(123, 1234, [language.name, language.code])
        storage.pulls.save_from_payload(p)
        pp = storage.pulls.by_number(p["number"])

        response = collections.namedtuple("Response", "status reason")(404, "testing stuff")
        client.fetch_channel = mocker.AsyncMock(side_effect=discord_errors.NotFound(response, "error"))
        client.settings.reset = mocker.AsyncMock()
        client.storage.discord.delete_channel_messages = mocker.Mock()
        await monitor.sort_for_updates([pp])

        client.settings.reset.assert_called()
        client.storage.discord.delete_channel_messages.assert_called()
        args, _ = client.settings.reset.call_args
        assert args == (123,)
