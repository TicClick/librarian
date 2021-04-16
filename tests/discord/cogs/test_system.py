import asyncio
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

    async def test__show_version_failsafe(self, client, make_context, mocker):
        ctx = make_context()
        system_cog = client.get_cog(system.System.__name__)

        # fail to spawn the process
        asyncio.create_subprocess_exec = mocker.AsyncMock(side_effect=RuntimeError)
        await system_cog.show_version(ctx)

        content = ctx.kwargs()["content"]
        assert content == "unknown version (failed to run `git log`)"

        # the process spawns, but fails
        asyncio.create_subprocess_exec = mocker.AsyncMock()
        asyncio.create_subprocess_exec.communicate = mocker.AsyncMock(return_value=(1, ""))
        await system_cog.show_version(ctx)

        content = ctx.kwargs()["content"]
        assert content == "unknown version (failed to run `git log`)"

    async def test__show_version_with_or_without_tag(self, client, make_context, mocker):
        ctx = make_context()
        system_cog = client.get_cog(system.System.__name__)

        for git_tag_rc, git_tag_out, expected_tag in (
            (0, b"v1.2.3", "v1.2.3"),
            (1, b"failed something", "None"),
        ):
            def side_effect(*command, **kws):
                rc = {"log": 0, "tag": git_tag_rc}[command[1]]
                out = {"log": b"1234abcd 2021-04-16", "tag": git_tag_out}[command[1]]

                return mocker.AsyncMock(
                    communicate=mocker.AsyncMock(return_value=(out, None)),
                    returncode=rc
                )

            asyncio.create_subprocess_exec = mocker.AsyncMock(side_effect=side_effect)
            await system_cog.show_version(ctx)

            content = ctx.kwargs()["content"]
            assert content == "```\ntag: {}\nlast commit: 1234abcd (2021-04-16)\n```".format(
                expected_tag
            )
