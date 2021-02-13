from librarian.discord.cogs import helpers


class TestHelpers:
    async def test__allowed_users(self, storage, make_context):
        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner.id = 1234

        assert await helpers.promoted_users(ctx) == {1234}

        storage.discord.promote_users(1, 123, 12345)
        max_allowed = await helpers.promoted_users(ctx)
        assert max_allowed == {123, 1234, 12345}

        storage.discord.demote_users(1, 12345)
        assert await helpers.promoted_users(ctx) == {123, 1234}

        storage.discord.demote_users(1, *max_allowed)
        assert await helpers.promoted_users(ctx) == {1234}
