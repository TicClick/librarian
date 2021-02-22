import pytest

from librarian.discord.settings import (
    base,
    custom
)


class TestCustomSettings:
    def test__basic(self):
        for cls in (custom.PinMessages, custom.Language, custom.ReviewerRole):
            assert issubclass(cls, base.BaseSetting)
            assert cls.name is not None and cls.name == cls.name.lower()

    def test__store_in_pins(self, bool_casts):
        for in_, out in bool_casts:
            instance = custom.PinMessages(in_)
            assert instance.check() and instance.cast() == out

    def test__language(self):
        for val in ["ru", "RU", "      en", "PT-br"]:
            instance = custom.Language(val)
            assert instance.check() and instance.cast() == val.strip().lower()
            assert instance.random_highlight
            assert instance.match("[{}] TEST TITLE".format(val.strip().upper()))

        for val in ["russian", "ID-JP", 123, "nonsense"]:
            assert not custom.Language(val).check()
            with pytest.raises(ValueError) as e:
                custom.Language(val).match("[DOES NOT] compute")
            assert "non-existent language" in str(e)

    def test__reviewer_role(self):
        for val in ["123", "<@&1234>", 12345678901234567890]:
            instance = custom.ReviewerRole(val)
            assert instance.check()
            casted = instance.cast()
            assert casted and isinstance(casted, int)
