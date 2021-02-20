import asyncio
import collections
import inspect
import itertools

from librarian.discord.settings import (
    base,
    custom,
)


class Registry:
    KNOWN_SETTINGS = {
        item.name: item
        for _, item in inspect.getmembers(
            custom,
            predicate=lambda cls: inspect.isclass(cls) and issubclass(cls, base.BaseSetting))
    }

    def __init__(self, helper):
        self.__lock = asyncio.Lock()
        self.__cache = collections.defaultdict(self.default_settings)
        self.helper = helper
        for channel in self.helper.all_channels_settings():
            self.__cache[channel.id] = channel.settings

    @classmethod
    def default_settings(cls):
        return {
            custom.StoreInPins.name: True,
        }

    def wrap(self, tokens):
        if not tokens:
            raise ValueError("empty sequence")
        if len(tokens) % 2 != 0:
            raise ValueError("incorrect sequence (should be <key1> <value1> <key2> <value2> ...)")

        for k, v in zip(
            itertools.islice(tokens, 0, len(tokens), 2),
            itertools.islice(tokens, 1, len(tokens), 2)
        ):
            try:
                wrapper = self.KNOWN_SETTINGS[k](v)
                if not wrapper.check():
                    raise ValueError(f"incorrect value {v} for setting {k}")
                yield wrapper
            except KeyError:
                raise ValueError(f"unknown setting {k}")
            except (TypeError, ValueError):
                raise

    async def update(self, channel_id, guild_id, args):
        updated = False
        async with self.__lock:
            for setting in self.wrap(args):
                casted = setting.cast()
                channel_settings = self.__cache[channel_id]
                if channel_settings.get(setting.name) != casted:
                    channel_settings[setting.name] = casted
                    updated = True

            if updated:
                self.helper.save_channel_settings(channel_id, guild_id, channel_settings)

    async def reset(self, channel_id):
        async with self.__lock:
            if channel_id in self.__cache:
                self.helper.delete_channel_settings(channel_id)
                del self.__cache[channel_id]

    async def get(self, channel_id):
        async with self.__lock:
            return self.__cache[channel_id]
