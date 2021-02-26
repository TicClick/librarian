from librarian.discord.cogs import server
from librarian.discord.settings import custom


class TestServerCog:
    async def test__promote(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner_id = 1234
        ctx.message.mentions = []

        ctx.message.author.id = 12
        await Server.promote_users(ctx)
        assert not storage.discord.custom_promoted_users(1)

        ctx.message.author.id = 1234
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
        ctx.message.channel.guild.owner_id = 1234
        ctx.message.mentions = []

        ctx.message.author.id = 12
        await Server.demote_users(ctx)

        ctx.message.author.id = 1234
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
        assert "**disabled** settings for" in ctx.kwargs()["content"]

    async def test__show_nonsense(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner_id = 1234

        assert not storage.discord.custom_promoted_users(1)
        await Server.show(ctx, "test")
        assert ctx.kwargs()["content"] == "unknown type test"

    async def test__show_promoted(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.guild.owner_id = 1234

        assert not storage.discord.custom_promoted_users(1)
        await Server.show(ctx, "promoted")
        assert ctx.kwargs()["content"] == "users that can edit settings: <@1234>"

        storage.discord.promote_users(1, 123, 12345)
        await Server.show(ctx, "promoted")
        assert all(
            tag in ctx.kwargs()["content"]
            for tag in ("<@123>", "<@1234>", "<@12345>")
        )

    async def test__show_settings(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.id = 123
        ctx.message.channel.guild.owner_id = 1234

        assert not client.settings._Registry__cache
        await Server.show(ctx, "settings")
        assert ctx.kwargs()["content"] == '```\n{\n  "' + custom.PinMessages.name + '": true\n}\n```'

        await client.settings.update(
            ctx.message.channel.id,
            ctx.message.channel.guild.id,
            [custom.ReviewerRole.name, "12345"]
        )
        await Server.show(ctx, "settings")
        assert ctx.kwargs()["content"] == (
            '```\n{\n  "' + custom.PinMessages.name + '": true,\n  "' +
            custom.ReviewerRole.name + '": 12345\n}\n```'
        )

    async def test__set_settings(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.id = 123
        ctx.message.channel.guild.owner_id = 1234

        assert not client.settings._Registry__cache
        await Server.set(
            ctx,
            custom.PinMessages.name, "true",
            custom.ReviewerRole.name, "12345",
            custom.Language.name, "TR"
        )
        assert ctx.kwargs()["content"] == "done"

        settings = await client.settings.get(ctx.message.channel.id)
        assert settings == {custom.PinMessages.name: True, custom.ReviewerRole.name: 12345, custom.Language.name: "tr"}

        for payload in (
            (custom.PinMessages.name, 1234),
            ("store_in_pinsssss", True),
            (),
            (custom.PinMessages.name,),
            (custom.PinMessages.name, custom.PinMessages.name),
        ):
            await Server.set(ctx, *payload)
            assert "input error" in ctx.kwargs()["content"]
            assert await client.settings.get(ctx.message.channel.id) == settings

    async def test__reset_settings(self, client, storage, make_context, mocker):
        Server = client.get_cog(server.Server.__name__)

        ctx = make_context()
        ctx.message.channel.guild.id = 1
        ctx.message.channel.id = 123
        ctx.message.channel.guild.owner_id = 1234

        assert not client.settings._Registry__cache
        await Server.set(
            ctx,
            custom.PinMessages.name, "true",
            custom.ReviewerRole.name, "12345",
            custom.Language.name, "TR"
        )
        assert ctx.kwargs()["content"] == "done"

        await Server.reset(ctx)
        assert ctx.kwargs()["content"] == "removed custom settings for this channel"
        assert await client.settings.get(ctx.message.channel.id) == client.settings.default_settings()
