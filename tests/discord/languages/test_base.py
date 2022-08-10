import re

import pytest

from librarian.discord.languages import base


class TestLanguages:
    def test__basics(self):
        class TestLanguage(base.Language):
            code = "hey"

        with pytest.raises(RuntimeError):
            class AnotherLanguage(base.Language):
                code = "hey"

        assert base.LanguageMeta.get("hey") is TestLanguage
        for code, language in base.LanguageMeta.all().items():
            for statement in language.highlights:
                assert isinstance(statement, str)
            assert language.random_highlight in language.highlights
            assert isinstance(language.title_regex, re.Pattern)

        fresh = base.LanguageMeta.get("nonsensical-language")
        assert fresh.code == "nonsensical-language"
        assert fresh.match("[nonsensical-language] TEST")
        assert sorted(fresh.highlights) == sorted(base.LanguageMeta.highlights)
        assert base.LanguageMeta.get("nonsensical-language") is fresh  # second lookup doesn't create a new class

    def test__matching(self):
        class FakeLanguage(base.Language):
            code = "not"
            greetings = [
                "g1", "g2"
            ]

        for title in (
            "[NOT] real",
            "[NOT|FAKE] realtest[teST]",
            "[GOOD/NOT/bad] test me",
            "[not] looking like a match, but it is",
        ):
            assert FakeLanguage.match(title)

        for poor_title in (
            "[EN] test",
            "Update ru.md",
            "NOT a drill",
            "[NOTE]lock",
        ):
            assert not FakeLanguage.match(poor_title)

    def test__whitespace_prefix(self):
        class FakeLanguage(base.Language):
            code = "sigh"

        assert FakeLanguage.match("   [SIGH] whitespace again")
