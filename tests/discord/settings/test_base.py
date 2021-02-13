import pytest

from librarian.discord.settings import base


class TestBaseSettings:
    @pytest.mark.parametrize(
        ["checker", "good", "bad"],
        [
            (
                base.Bool,
                ["0", "1", "true", "True", "TRue", "false", "FALse", "False"],
                [0, 1, 2, True, False, "2", None, "nonsense"]
            ),
            (
                base.String,
                ["1", "100" * 30, "0", "\ntest       "],
                ["", " ", "\n", "\t", 0.1, 0]
            ),
            (
                base.Int,
                [0, -10, 1, "1", "1" * 1000, int("1" * 1000)],
                [2.3, None, "False"]
            )
        ]
    )
    def test__check(self, checker, good, bad):
        for val in good:
            assert checker(val).check()
        for val in bad:
            assert not checker(val).check()

    def test__casts(self, bool_casts, string_casts, int_casts):
        for cls, cases in (
            (base.Bool, bool_casts),
            (base.String, string_casts),
            (base.Int, int_casts),
        ):
            for in_, out in cases:
                instance = cls(in_)
                assert instance.check() and instance.cast() == out
