import asyncio
import collections
import inspect
import itertools
import textwrap

from librarian.discord import languages
from librarian.discord.settings import (
    base,
    custom,
)


LanguageEntry = collections.namedtuple("LanguageEntry", "language channels")


class ChannelCache(dict):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.__lock = asyncio.Lock()

    def add_channel(self, channel_id, code):
        if code is None:
            return
        if code not in self:
            self[code] = LanguageEntry(language=languages.LanguageMeta.get(code), channels=set())
        self[code].channels.add(channel_id)

    def discard_channel(self, channel_id, code):
        if code is None:
            return
        if code in self:
            self[code].channels.discard(channel_id)
            if not self[code].channels:
                del self[code]

    async def update_channel_language(self, channel_id, previous_code, present_code):
        async with self.__lock:
            self.discard_channel(channel_id, previous_code)
            self.add_channel(channel_id, present_code)


class Registry:
    KNOWN_SETTINGS = {
        item.name: item
        for _, item in inspect.getmembers(
            custom,
            predicate=lambda cls: inspect.isclass(cls) and issubclass(cls, base.BaseSetting)
        )
    }

    def __init__(self, helper):
        self.__lock = asyncio.Lock()
        self.__cache = collections.defaultdict(self.default_settings)
        self.channels_by_language = ChannelCache()
        self.helper = helper

        for channel in self.helper.all_channels_settings():
            self.__cache[channel.id] = channel.settings
            try:
                language_code = channel.settings[custom.Language.name]
                self.channels_by_language.add_channel(channel.id, language_code)
            except KeyError:
                pass  # skip a channel if it has no language settings yet

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
        async with self.__lock:
            channel_settings = self.__cache[channel_id]
            updated = {}
            settings = list(self.wrap(args))
            for setting in settings:
                casted = setting.cast()
                if channel_settings.get(setting.name) != casted:
                    updated[setting.name] = casted

            if updated:
                try:
                    await self.channels_by_language.update_channel_language(
                        channel_id,
                        channel_settings.get(custom.Language.name),
                        updated[custom.Language.name]
                    )
                except KeyError:  # no update happened
                    pass

                channel_settings.update(updated)
                self.__cache[channel_id] = channel_settings
                self.helper.save_channel_settings(channel_id, guild_id, channel_settings)
                return settings

            return []

    async def reset(self, channel_id):
        async with self.__lock:
            if channel_id in self.__cache:
                try:
                    self.channels_by_language.discard_channel(
                        channel_id,
                        self.__cache[channel_id][custom.Language.name]
                    )
                except KeyError:
                    pass
                self.helper.delete_channel_settings(channel_id)
                del self.__cache[channel_id]

    async def get(self, channel_id):
        async with self.__lock:
            return self.__cache[channel_id]


SettingHelp = collections.namedtuple("SettingHelp", "name trivia rest")


def parameters_docs():
    for _, cls in sorted(Registry.KNOWN_SETTINGS.items()):
        if cls.__doc__ is None:
            yield SettingHelp(cls.name, "no documentation", [])
        else:
            doc = textwrap.dedent(cls.__doc__).strip().splitlines()
            yield SettingHelp(cls.name, doc[0], doc[1:])


def parameters_combined_docs():
    for item in parameters_docs():
        yield "- {}: {}".format(item.name, item.trivia)
        padding = " " * 4
        for line in item.rest:
            yield padding + line
