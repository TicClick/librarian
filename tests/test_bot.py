import random

import arrow
import pytest

from librarian.discord.cogs import (
    pulls,
    system
)


def to_arrow(dt=None):
    return arrow.get(dt).floor("day")


class TestCount:
    @pytest.mark.freeze_time
    def test__date_range(self):
        today_end = arrow.get().ceil("day")
        this_month_beginning = today_end.floor("month")
        last_month_beginning = this_month_beginning.shift(months=-1)
        last_month_end = last_month_beginning.ceil("month")

        for args, start, end, expect_to_fail in (
            ([], this_month_beginning, today_end, False),
            ([pulls.CountArgparser.LAST_MONTH], last_month_beginning, last_month_end, False),
            (
                ["2020-01-01", "2021-01-01"],
                arrow.get("2020-01-01").floor("day"),
                arrow.get("2021-01-01").ceil("day"),
                False,
            ),
            (
                ["2030-01-01", "2020-01-01"],  # dates are swapped
                arrow.get("2020-01-01").floor("day"),
                arrow.get("2030-01-01").ceil("day"),
                False,
            ),
            (
                ["2020-01", "2020-05"],
                arrow.get("2020-01-01").floor("day"),
                arrow.get("2020-05-01").ceil("day"),
                False
            ),
            (["nonsense"], None, None, True),
            (["2020-01-01"], None, None, True),
        ):
            if expect_to_fail:
                with pytest.raises(ValueError):
                    pulls.CountArgparser.parse(args)
            else:
                parsed_start, parsed_end = pulls.CountArgparser.parse(args)
                assert start == parsed_start
                assert end == parsed_end


class TestDiscordCommands:
    @pytest.mark.freeze_time
    async def test__count(self, client, storage, existing_pulls, make_context):
        storage.pulls.save_many_from_payload(existing_pulls)
        merged_only = [_ for _ in existing_pulls if _["merged"]]

        def pick_any():
            pull = random.choice(merged_only)
            return to_arrow(pull["merged_at"]).strftime("%Y-%m-%d")

        def args_maker():
            yield []
            yield [pulls.CountArgparser.LAST_MONTH]
            for _ in range(10):
                yield [pick_any(), pick_any()]

            yield ["1900-01-01", "2000-01-01"]

        for args in args_maker():
            # tested with test__date_range
            start, end = pulls.CountArgparser.parse(args)

            ctx = make_context()
            Pulls = client.get_cog(pulls.Pulls.__name__)
            await Pulls.count(ctx, *args)

            for i, call in enumerate(ctx.message.channel.send.call_args_list):
                if i == 0:
                    assert call.kwargs["content"]
                if "embed" in call.kwargs:
                    assert call.kwargs["embed"].description

            first_message = ctx.message.channel.send.call_args_list[0].kwargs["content"]
            cnt = int(first_message.split(" ")[0])

            merged = [
                _
                for _ in merged_only if
                (
                    start <= arrow.get(_["merged_at"]) < end and
                    client.title_regex.match(_["title"])
                )
            ]
            assert len(merged) == cnt, (", ".join(_["merged_at"] for _ in merged), start, end)

    @pytest.mark.parametrize(
        "args",
        [
            ["blah"],
            [pulls.CountArgparser.LAST_MONTH, pulls.CountArgparser.LAST_MONTH],
            ["nonsense", "2020-01-01"],
            ["2020000+123-3", "2000-02-01"],
            ["2020-01-01", "2020-01-02", "2020-01-03"],
        ]
    )
    async def test__bad_count(self, client, make_context, args):
        ctx = make_context()
        Pulls = client.get_cog(pulls.Pulls.__name__)
        await Pulls.count(ctx, *args)
        assert ctx.send_help.call_args.args[0] == "count"

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
