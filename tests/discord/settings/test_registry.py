import pytest

from librarian.discord.settings import (
    base,
    custom,
    registry,
)


class TestRegistry:
    def test__properties(self):
        assert registry.Registry.KNOWN_SETTINGS == {
            _.name: _
            for _ in (custom.StoreInPins, custom.Language, custom.ReviewerRole)
        }

        assert registry.Registry.default_settings() == {
            "store_in_pins": True
        }

    async def test__init(self, storage, mocker):
        r = registry.Registry(storage.discord)
        assert not r._Registry__cache
        assert await r.get(12345) == r.default_settings() == {"store_in_pins": True}

        dummy = {"store_in_pins": False, "language": "ru"}
        storage.discord.save_channel_settings(12345, 67890, dummy)

        rr = registry.Registry(storage.discord)
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
            ("incorrect value abc for setting store_in_pins", ["store_in_pins", "abc"])
        ):
            with pytest.raises(ValueError) as exc:
                list(r.wrap(payload))
            assert expected_error in str(exc.value)

        payload = [
            "store_in_pins", "True",
            "language", "RU",
            "reviewrole", "<@&1234>",
        ]
        expected_result = [custom.StoreInPins(True), custom.Language("ru"), custom.ReviewerRole(1234)]
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

        await r.update(1234, 1, ["store_in_pins", "True"])
        assert not storage.discord.save_channel_settings.called  # defaults should be skipped
        assert not storage.discord.load_channel_settings.called

        await r.update(1234, 1, ["store_in_pins", "False"])
        assert storage.discord.save_channel_settings.called
        assert await r.get(1234) == {"store_in_pins": False}
        assert not storage.discord.load_channel_settings.called

        storage.discord.save_channel_settings.reset_mock()
        await r.update(1234, 1, ["store_in_pins", "False"])
        assert not storage.discord.save_channel_settings.called

        await r.update(1234, 1, ["language", "ru"])
        assert storage.discord.save_channel_settings.called
        assert await r.get(1234) == {"store_in_pins": False, "language": "ru"}

        for payload in (
            ["dummy", "setting"],
            [],
            ["store_in_pins", 9023],
        ):
            with pytest.raises(ValueError):
                await r.update(1234, 1, payload)

    async def test__reset(self, storage, mocker):
        r = registry.Registry(storage.discord)
        await r.reset(1234)

        dummy = {"store_in_pins": False, "language": "ru"}
        storage.discord.save_channel_settings(12345, 67890, dummy)

        rr = registry.Registry(storage.discord)
        assert await rr.get(12345) == dummy

        await rr.reset(12345)
        assert await rr.get(12345) == rr.default_settings()
        assert storage.discord.load_channel_settings(12345) is None
