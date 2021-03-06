import random

import librarian.storage as stg
from librarian.discord.settings import custom


class TestDiscordMessages:
    def test__basic(self, storage, existing_pulls):
        n = random.randint(1, 100)
        storage.discord.save_messages(*(
            stg.DiscordMessage(
                id=msg_id,
                channel_id=random.randint(1, 1000),
                pull_number=pull["number"]
            )
            for msg_id, pull in zip(
                random.sample(range(1, 1000), n),
                random.sample(existing_pulls, n)
            )
        ))

        restored = storage.discord.messages_by_pull_numbers(*(_["number"] for _ in existing_pulls))
        assert len(restored) == n

    def test__delete_message(self, storage, existing_pulls):
        storage.discord.save_messages(
            stg.DiscordMessage(id=123, channel_id=456, pull_number=789)
        )
        assert storage.discord.messages_by_pull_numbers(789)
        storage.discord.delete_message(123, 456)
        assert not storage.discord.messages_by_pull_numbers(789)

    def test__delete_channel_messages(self, storage, existing_pulls):
        assert storage.discord.delete_channel_messages(123) == 0
        storage.discord.save_messages(*(
            stg.DiscordMessage(
                id=i,
                channel_id=123,
                pull_number=1
            )
            for i in range(10)
        ))
        storage.discord.save_messages(stg.DiscordMessage(id=15, channel_id=124, pull_number=1))

        assert len(storage.discord.messages_by_pull_numbers(1)) == 11
        assert storage.discord.delete_channel_messages(123) == 10
        assert len(storage.discord.messages_by_pull_numbers(1)) == 1


class TestDiscordUsers:
    def test__promote_one(self, storage):
        promoted = storage.discord.promote_users(1, 123)
        assert promoted == [123]

        new_promoted = storage.discord.promote_users(1, 123)
        assert not new_promoted

        promoted = storage.discord.custom_promoted_users(1)
        assert promoted == {123}

        assert not storage.discord.custom_promoted_users(9)

    def test__promote_many(self, storage):
        promoted = storage.discord.promote_users(1, 123, 1234, 12345)
        assert promoted == sorted([123, 1234, 12345])

        new_promoted = storage.discord.promote_users(1, 123, 12345, 123456)
        assert new_promoted == [123456]

        promoted = storage.discord.custom_promoted_users(1)
        assert promoted == {123, 1234, 12345, 123456}

    def test__demote_one(self, storage):
        storage.discord.promote_users(1, 123, 1234, 12345)
        current_promoted = storage.discord.custom_promoted_users(1)
        assert current_promoted == {123, 1234, 12345}

        demoted = storage.discord.demote_users(1, 123)
        assert demoted == [123]
        assert storage.discord.custom_promoted_users(1) == current_promoted - {123}

    def test__demote_many(self, storage):
        storage.discord.promote_users(1, 123, 1234, 12345)
        storage.discord.promote_users(1001, 123, 1234, 12345)
        current_promoted = storage.discord.custom_promoted_users(1)
        assert current_promoted == {123, 1234, 12345}

        demoted = storage.discord.demote_users(1, 123, 123005)
        assert demoted == [123]
        assert storage.discord.custom_promoted_users(1) == {1234, 12345}
        assert storage.discord.custom_promoted_users(1001) == {123, 1234, 12345}

        storage.discord.demote_users(1, 1234, 12345)
        assert not storage.discord.custom_promoted_users(1)
        assert storage.discord.custom_promoted_users(1001) == {123, 1234, 12345}


class TestDiscordChannels:
    def test__channel_settings(self, storage):
        assert not storage.discord.all_channels_settings()
        assert not storage.discord.load_channel_settings(1234)

        payload = (
            (12345, 1, {custom.PinMessages.name: True, "whatever-setting": "abc1234"}),
            (12346, 1, {"non": "sense", "1234": 5678, "910": [11, 12]}),
            (12347, 2, {}),
        )
        for i, (channel_id, guild_id, settings) in enumerate(payload):
            storage.discord.save_channel_settings(channel_id, guild_id, settings)
            item = storage.discord.load_channel_settings(channel_id)
            assert item.settings == settings
            assert item.id == channel_id
            assert item.guild_id == guild_id

            assert len(storage.discord.all_channels_settings()) == i + 1

        new_settings = {custom.PinMessages.name: False}
        storage.discord.save_channel_settings(12345, 1, new_settings)
        assert len(storage.discord.all_channels_settings()) == len(payload)
        assert storage.discord.load_channel_settings(12345).settings == new_settings
        storage.discord.save_channel_settings(12345, 1, {})
        assert storage.discord.load_channel_settings(12345).settings == {}

        for channel_id in (12345, 12346, 12347):
            storage.discord.delete_channel_settings(channel_id)
            assert storage.discord.load_channel_settings(channel_id) is None
        storage.discord.delete_channel_settings(12345)
