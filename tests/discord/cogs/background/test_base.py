import pytest

from librarian.discord.cogs.background import base


class TestBackgroundBaseCog:
    def test__basic(self, client):
        cog = base.BackgroundCog(client)
        assert cog.github
        assert cog.storage

        assert cog.name == "BackgroundCog"

    async def test__loop(self, client, mocker):
        cog = base.BackgroundCog(client)
        logger = mocker.Mock()
        base.logger = logger

        with pytest.raises(NotImplementedError):
            await cog.loop()

        with mocker.patch.context_manager(cog, "loop"):
            await cog.start()
            cog.loop.start.assert_called()

            cog.cog_unload()
            logger.debug.assert_called()
            cog.loop.cancel.assert_called()

    @pytest.mark.parametrize(
        ["is_running", "status"],
        [
            (True, "[ OK ]"),
            (False, "[DEAD]"),
        ]
    )
    async def test__status(self, client, mocker, is_running, status):
        cog = base.BackgroundCog(client)
        with pytest.raises(NotImplementedError):
            await cog.status()

        cog.status = mocker.AsyncMock(return_value={"abc": 123})
        cog.loop.is_running = mocker.Mock(return_value=is_running)
        status_repr = await cog.status_repr()
        assert status_repr == status + " BackgroundCog: abc=123"
