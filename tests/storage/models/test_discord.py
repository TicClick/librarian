import random

import librarian.storage as stg


class TestDiscordMessages:
    def test__save(self, storage, existing_pulls):
        n = random.randint(1, 100)
        storage.discord_messages.save(*(
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

        restored = storage.discord_messages.by_pull_numbers(*(_["number"] for _ in existing_pulls))
        assert len(restored) == n
