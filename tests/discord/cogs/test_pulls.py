import random

import arrow
import pytest

from librarian.discord import languages
from librarian.discord.cogs import pulls


def to_arrow(dt=None):
    return arrow.get(dt).floor("day")


class TestCountArgparser:
    def test__basic(self):
        parser = pulls.CountArgparser()

        for bad_args in (
            ["2020-01-01"],
            ["2020-01-02" "2020-01-04"],
            ["--from", "2020-01-05"],
            ["--to", "2020-01-05"],
        ):
            with pytest.raises(ValueError):
                parser.parse_args(bad_args)

        for args in (
            ["--from", "2020-01-01", "--to", "2021-01"],
            ["--to", "2021-05", "--from", "2020-01-01"],
            ["--language", "ru", "--to", "2021-05", "--from", "2020-01-01"],
            ["-l", "ru", "-t", "2021-05", "-f", "2020-01-01"],
        ):
            args = parser.parse_args(args)
            assert isinstance(args.from_, arrow.Arrow)
            assert isinstance(args.to, arrow.Arrow)


class TestPullsCog:
    @pytest.mark.freeze_time
    async def test__count(self, client, storage, existing_pulls, make_context, language_code):
        storage.pulls.save_many_from_payload(existing_pulls)
        merged_only = [_ for _ in existing_pulls if _["merged"]]

        def pick_any():
            pull = random.choice(merged_only)
            return to_arrow(pull["merged_at"]).strftime("%Y-%m-%d")

        def args_maker():
            for _ in range(10):
                yield ["--from", pick_any(), "--to", pick_any()]

        parser = pulls.CountArgparser()
        await client.settings.update(1, 2, ["language", language_code])
        for args in args_maker():
            # tested with TestCountArgparser.test__basic
            parsed_args = parser.parse_args(args)

            ctx = make_context()
            ctx.message.channel.id = 1
            ctx.message.channel.guild.id = 2
            Pulls = client.get_cog(pulls.Pulls.__name__)
            await Pulls.list(ctx, *args)

            for i, call in enumerate(ctx.message.channel.send.call_args_list):
                if i == 0:
                    assert call.kwargs["content"]
                if "embed" in call.kwargs:
                    assert call.kwargs["embed"].description

            first_message = ctx.message.channel.send.call_args_list[0].kwargs["content"]
            cnt = int(first_message.split(" ")[0])

            language = languages.LanguageMeta.get(language_code)
            merged = [
                _
                for _ in merged_only if
                (
                    parsed_args.from_ <= arrow.get(_["merged_at"]) < parsed_args.to and
                    language.match(_["title"])
                )
            ]
            assert len(merged) == cnt, (", ".join(_["merged_at"] for _ in merged), parsed_args.from_, parsed_args.to)

    @pytest.mark.parametrize(
        "args",
        [
            ["blah"],
            ["--from", "2020-01-01"],
            ["--to", "2020-01-01"],
            ["--from", "2020-01-01", "--to", "nonsense"],
        ]
    )
    async def test__bad_count(self, client, make_context, args, language_code):
        ctx = make_context()
        ctx.message.channel.id = 1
        ctx.message.channel.guild.id = 2
        await client.settings.update(1, 2, ["language", language_code])

        Pulls = client.get_cog(pulls.Pulls.__name__)
        await Pulls.list(ctx, *args)
        assert any(
            _ in ctx.message.channel.send.call_args[1]["content"]
            for _ in (
                "the following arguments are required",
                "invalid get value"
            )
        ), ctx.message.channel.send.call_args[1]["content"]
