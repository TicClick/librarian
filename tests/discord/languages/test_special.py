import re

import pytest

from librarian.discord.languages import base, special


class TestLanguages:
    def test__matching__unspecified_language(self):
        assert base.LanguageMeta.get("none") is special.UnspecifiedLanguage
        for good_title in (
            "Update OWC2022",
            "Update dependencies",
            "   Some spaces! Wow",
            "\"Special\" pull request",
        ):
            assert special.UnspecifiedLanguage.match(good_title)

        for bad_title in (
            "[EN] Update OWC2022",
            "[TEST] Update dependencies",
            "[EN/RU] Test",
        ):
            assert not special.UnspecifiedLanguage.match(bad_title), bad_title

    def test__matching__every_language(self):
        assert base.LanguageMeta.get("all") is special.EveryLanguage
        for any_title in (
            "Update OWC2022",
            "[RU] Update OWC2023",
            "[RU/EN] Update OWC2024",
            "     Spa   ces",
            "\"Rhythm Games from Outer Space\" (Short 1992)", 
        ):
            assert special.EveryLanguage.match(any_title)
