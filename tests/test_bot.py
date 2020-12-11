import random
import textwrap

import arrow
import pytest

import librarian.discord_bot as bot


def to_arrow(dt=None):
    return arrow.get(dt).floor("day")


def datetime_testcases():
    today = to_arrow()
    first_day = today.floor("month")
    return(
        # from start of month to today
        (None, None, first_day, today.ceil("day"), False),
        # all previous month
        (None, "lastmonth", first_day.shift(months=-1), first_day.shift(months=-1).ceil("month"), False),
        # treated as 2015-01, hence the same as above
        ("2015-01-21", None, to_arrow("2015-01-01"), to_arrow("2015-01-31").ceil("day"), False),
        # just 4 days (April 1st, 2nd, 3rd, 4th)
        ("2014-01-01", "2014-01-04", to_arrow("2014-01-01"), to_arrow("2014-01-04").ceil("day"), False),
        # whole April
        ("2020-04", None, to_arrow("2020-04-01"), to_arrow("2020-04-30").ceil("day"), False),
        # two dates. full range
        ("2020-04", "2031-01", to_arrow("2020-04-01"), to_arrow("2031-01-01").ceil("day"), False),
        # typo
        (None, "lastmoth", None, None, True),
        # can't have only the end date, must be a flaw in logic of a command parser
        (None, "2015-01-01", None, None, True),
        # gibberish
        ("malformed", "2020-01-01", None, None, True),
        # gibberish
        ("2020-010334", "whatever", None, None, True),
    )


@pytest.fixture
def make_message(mocker):
    def inner():
        msg = mocker.Mock()
        msg.configure_mock(**{
            "channel.send": mocker.AsyncMock(),
            "args": lambda: msg.channel.send.call_args.args,
            "kwargs": lambda: msg.channel.send.call_args.kwargs,
        })
        return msg

    return inner


class TestCount:
    @pytest.mark.parametrize(
        ["start_date", "end_date", "expected_start", "expected_end", "fail"], datetime_testcases()
    )
    def test__date_range(self, start_date, end_date, expected_start, expected_end, fail):
        if fail:
            with pytest.raises(ValueError):
                bot.Client.parse_count_range(start_date, end_date)
        else:
            start, end = bot.Client.parse_count_range(start_date, end_date)
            assert start == expected_start
            assert end == expected_end

    async def test__count(self, client, storage, existing_pulls, make_message):
        merged_only = [_ for _ in existing_pulls if _["merged"]]

        def pick_any():
            pull = random.choice(merged_only)
            return to_arrow(pull["merged_at"]).strftime("%Y-%m-%d")

        storage.pulls.save_many_from_payload(existing_pulls)

        # good dates
        for _ in range(100):
            start_date = None if random.random() < 0.3 else pick_any()
            if start_date is None:
                end_date = None if random.random() < 0.7 else "lastmonth"
            else:
                end_date = None if random.random() < 0.5 else pick_any()

            if None not in (start_date, end_date) and start_date > end_date:
                start_date, end_date = end_date, start_date

            msg = make_message()
            args = [_ for _ in (start_date, end_date) if _ is not None]
            await client.count_pulls(msg, args)
            assert msg.kwargs()
            cnt = int(msg.kwargs()["content"].split(" ")[0])

            start, end = client.parse_count_range(start_date, end_date)
            merged = [
                _
                for _ in merged_only if
                (
                    start <= arrow.get(_["merged_at"]) < end and
                    client.title_regex.match(_["title"])
                )
            ]
            assert len(merged) == cnt, (", ".join(_["merged_at"] for _ in merged), str(start), str(end))

        # gibberish dates
        for start, end in (
            ("poor", "data"),
            (None, "firstmonth"),
            (None, "2020-01-01"),
        ):
            msg = make_message()
            await client.count_pulls(msg, [start, end])
            assert msg.kwargs()["content"] == bot.codewrap(textwrap.dedent(bot.Client.count_pulls.__doc__))

    async def test__report_status(self, client, make_message):
        msg = make_message()
        await client.report_status(msg, [])
        assert msg.kwargs()["content"]
