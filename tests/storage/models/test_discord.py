import random

import librarian.storage as stg


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
