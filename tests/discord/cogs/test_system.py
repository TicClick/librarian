import pytest

from librarian.discord.cogs import system


class TestSystemCog:
    async def test__report_status(self, client, make_context):
        ctx = make_context()
        system_cog = client.get_cog(system.System.__name__)
        await system_cog.report_status(ctx)
        assert ctx.kwargs()["content"]

    @pytest.mark.parametrize(
        ["cmdline", "rc", "out"],
        [
            (["/bin/echo", "-n", "test"], 0, "test"),
            (["/bin/sh", "-c", "false", "test"], 1, ""),
            (["/fail"], None, None),
        ]
    )
    async def test__run_command(self, client, cmdline, rc, out):
        system_cog = client.get_cog(system.System.__name__)
        returncode, output = await system_cog.run_command(cmdline)
        assert rc == returncode and output == out

    @pytest.mark.parametrize(
        ["cmdline", "success"],
        [
            (["/bin/echo", "-n", "test"], True),
            (["/bin/sh", "-c", "false", "test"], False),
            (["/fail"], None),
        ]
    )
    async def test__run_and_reply(self, client, make_context, cmdline, success):
        ctx = make_context()
        system_cog = client.get_cog(system.System.__name__)
        await system_cog.run_and_reply(ctx.message, cmdline)
        content = ctx.kwargs()["content"]

        if success is None:
            assert "Failed to execute" in content
        else:
            if success:
                assert "librarian@librarian" in content
            else:
                assert "has died with return code" in content

    async def test__show_disk_status(self, client, make_context):
        ctx = make_context()
        system_cog = client.get_cog(system.System.__name__)
        await system_cog.show_disk_status(ctx)

        content = ctx.kwargs()["content"]
        assert "librarian@librarian" in content and "/bin/df -Ph /" in content
