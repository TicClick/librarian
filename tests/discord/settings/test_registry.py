import pytest

from librarian.discord.settings import (
    base,
    custom,
    registry,
)


class TestChannelCache:
    def test__channel_add(self, loop):
        cache = registry.ChannelCache()
        assert not cache

        en, ru = map(custom.Language, ("en", "ru"))
        with pytest.raises(KeyError):
            cache["en"]

        cache.add_channel(1, ru)
        cache.add_channel(2, ru)
        cache.add_channel(2, en)

        assert set(cache.keys()) == {"en", "ru"}
        assert cache["en"].channels == {2}
        assert cache["ru"].channels == {1, 2}
        assert cache["ru"].language.random_highlight

        cache.add_channel(1, None)
        assert None not in cache

    def test__channel_discard(self, loop):
        cache = registry.ChannelCache()
        en, ru, ja = map(custom.Language, ("en", "ru", "ja"))
        cache.add_channel(1, ru)
        cache.add_channel(2, ru)
        cache.add_channel(2, en)

        cache.discard_channel(1, ja)
        cache.discard_channel(1, None)
        cache.discard_channel(3, None)

        assert set(cache.keys()) == {"en", "ru"}

        cache.discard_channel(1, ru)
        assert "ru" in cache and cache["ru"].channels == {2}
        cache.discard_channel(2, ru)
        assert cache["en"].channels == {2}
        cache.discard_channel(2, en)
        assert not cache

    async def test__channel_update(self, loop):
        cache = registry.ChannelCache()
        await cache.update_channel_language(1, None, None)
        assert not cache

        en, ru, jp = map(custom.Language, ("en", "ru", "jp"))
        await cache.update_channel_language(1, ru, en)
        assert set(cache.keys()) == {"en"} and cache["en"].channels == {1}

        await cache.update_channel_language(1, en, ru)
        assert set(cache.keys()) == {"ru"} and cache["ru"].channels == {1}


class TestRegistry:
    def test__properties(self):
        assert registry.Registry.KNOWN_SETTINGS == {
            _.name: _
            for _ in (custom.PinMessages, custom.Language, custom.ReviewerRole)
        }

        assert registry.Registry.default_settings() == {
            custom.PinMessages.name: True
        }

    async def test__init(self, storage, mocker):
        r = registry.Registry(storage.discord)
        assert not r._Registry__cache
        assert await r.get(12345) == r.default_settings() == {custom.PinMessages.name: True}

        dummy = {custom.PinMessages.name: False, "language": "ru"}
        storage.discord.save_channel_settings(12345, 67890, dummy)

        rr = registry.Registry(storage.discord)
        assert 12345 in rr.channels_by_language["ru"].channels
        storage.session_scope = mocker.Mock()
        storage.discord.session_scope = mocker.Mock()
        storage.discord.load_channel_settings = mocker.Mock()

        assert await rr.get(12345) == dummy
        assert not storage.session_scope.called
        assert not storage.discord.session_scope.called
        assert not storage.discord.load_channel_settings.called

    async def test__wrap(self, storage):
        r = registry.Registry(storage.discord)

        for expected_error, payload in (
            ("empty sequence", []),
            ("incorrect sequence", ["test", "setting", "and-one-more"]),
            ("unknown setting", ["unknown", 1234]),
            ("unknown setting", [1234, 1234]),
            ("incorrect value abc for setting {}".format(custom.PinMessages.name), [custom.PinMessages.name, "abc"])
        ):
            with pytest.raises(ValueError) as exc:
                list(r.wrap(payload))
            assert expected_error in str(exc.value)

        payload = [
            custom.PinMessages.name, "True",
            custom.Language.name, "RU",
            custom.ReviewerRole.name, "<@&1234>",
        ]
        expected_result = [custom.PinMessages(True), custom.Language("ru"), custom.ReviewerRole(1234)]
        wrapped_payload = list(r.wrap(payload))
        assert len(wrapped_payload) == len(expected_result)
        for expected, wrapped in zip(expected_result, wrapped_payload):
            assert isinstance(wrapped, base.BaseSetting)
            assert wrapped.__class__ == expected.__class__
            assert wrapped.cast() == expected.cast()

    async def test__update(self, storage, mocker):
        r = registry.Registry(storage.discord)
        storage.discord.save_channel_settings = mocker.Mock(side_effect=storage.discord.save_channel_settings)
        storage.discord.load_channel_settings = mocker.Mock(side_effect=storage.discord.load_channel_settings)

        await r.update(1234, 1, [custom.PinMessages.name, "True"])
        assert not storage.discord.save_channel_settings.called  # defaults should be skipped
        assert not storage.discord.load_channel_settings.called

        await r.update(1234, 1, [custom.PinMessages.name, "False"])
        assert storage.discord.save_channel_settings.called
        assert await r.get(1234) == {custom.PinMessages.name: False}
        assert not storage.discord.load_channel_settings.called

        storage.discord.save_channel_settings.reset_mock()
        await r.update(1234, 1, [custom.PinMessages.name, "False"])
        assert not storage.discord.save_channel_settings.called

        await r.update(1234, 1, [custom.Language.name, "ru"])
        assert storage.discord.save_channel_settings.called
        assert await r.get(1234) == {custom.PinMessages.name: False, custom.Language.name: "ru"}

        for payload in (
            ["dummy", "setting"],
            [],
            [custom.PinMessages.name, 9023],
        ):
            with pytest.raises(ValueError):
                await r.update(1234, 1, payload)

        with pytest.raises(ValueError):
            await r.update(911, 1, [custom.Language.name, "ru", "nonsense", "1234", custom.PinMessages.name, False])
        assert await r.get(911) == r.default_settings()

        assert 1234 in r.channels_by_language["ru"].channels
        await r.update(1234, 1, [custom.Language.name, "en"])
        assert list(r.channels_by_language.keys()) == ["en"]
        assert 1234 in r.channels_by_language["en"].channels

    async def test__reset(self, storage, mocker):
        r = registry.Registry(storage.discord)
        await r.reset(1234)

        dummy = {custom.PinMessages.name: False, custom.Language.name: "ru"}
        storage.discord.save_channel_settings(12345, 67890, dummy)

        rr = registry.Registry(storage.discord)
        assert await rr.get(12345) == dummy
        assert 12345 in rr.channels_by_language["ru"].channels

        await rr.reset(12345)
        assert await rr.get(12345) == rr.default_settings()
        assert storage.discord.load_channel_settings(12345) is None
        assert "ru" not in rr.channels_by_language
