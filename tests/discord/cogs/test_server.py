from librarian.discord.cogs import server


class TestServerCog:
    async def test__allowed_users(self, client, storage, make_context):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner.id = 1234

        assert await Server.allowed_users(ctx) == {1234}

        storage.discord.promote_users(1, 123, 12345)
        max_allowed = await Server.allowed_users(ctx)
        assert max_allowed == {123, 1234, 12345}

        storage.discord.demote_users(1, 12345)
        assert await Server.allowed_users(ctx) == {123, 1234}

        storage.discord.demote_users(1, *max_allowed)
        assert await Server.allowed_users(ctx) == {1234}

    async def test__promote(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner.id = 1234

        ctx.message.author.id = 12
        await Server.promote_users(ctx)
        assert not storage.discord.custom_promoted_users(1)
        assert "you aren't allowed" in ctx.kwargs()["content"]

        ctx.message.author.id = 1234
        ctx.message.mentions = []
        await Server.promote_users(ctx)
        assert not storage.discord.custom_promoted_users(1)
        assert "incorrect format" in ctx.kwargs()["content"]

        ctx.message.mentions = [mocker.Mock(id=12), mocker.Mock(id=12345)]
        await Server.promote_users(ctx)
        assert storage.discord.custom_promoted_users(1) == {12345, 12}
        assert all(
            tag in ctx.kwargs()["content"]
            for tag in ("<@12>", "<@12345>")
        )

        await Server.promote_users(ctx)
        assert ctx.kwargs()["content"] == "all mentioned users are already promoted"

    async def test__demote(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner.id = 1234

        ctx.message.author.id = 12
        await Server.demote_users(ctx)
        assert "you aren't allowed" in ctx.kwargs()["content"]

        ctx.message.author.id = 1234
        ctx.message.mentions = []
        await Server.demote_users(ctx)
        assert "incorrect format" in ctx.kwargs()["content"]

        ctx.message.mentions = [mocker.Mock(id=12), mocker.Mock(id=12345)]
        await Server.demote_users(ctx)
        assert ctx.kwargs()["content"] == "none of mentioned users had access"

        await Server.promote_users(ctx)
        assert storage.discord.custom_promoted_users(1) == {12345, 12}
        ctx.message.mentions.append(mocker.Mock(id=91))
        await Server.demote_users(ctx)
        assert not storage.discord.custom_promoted_users(1)

        assert all(
            tag in ctx.kwargs()["content"]
            for tag in ("<@12>", "<@12345>")
        )
        assert "<@91>" not in ctx.kwargs()["content"]
        assert "can **not** change my settings on the server" in ctx.kwargs()["content"]

    async def test__list_promoted(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner.id = 1234

        assert not storage.discord.custom_promoted_users(1)
        await Server.list_promoted_users(ctx)
        assert ctx.kwargs()["content"] == "users that can edit settings: <@1234>"

        storage.discord.promote_users(1, 123, 12345)
        await Server.list_promoted_users(ctx)
        assert all(
            tag in ctx.kwargs()["content"]
            for tag in ("<@123>", "<@1234>", "<@12345>")
        )
