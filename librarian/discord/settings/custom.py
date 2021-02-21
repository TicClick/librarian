import re

from librarian.discord.settings import base
from librarian.discord import languages


class StoreInPins(base.Bool):
    name = "store_in_pins"


class Language(base.String):
    name = "language"
    __whitelisted = frozenset((
        "en", "ar", "be", "bg", "cs", "da", "de", "gr", "es", "fi", "fr", "hu", "id", "it", "ja", "ko", "nl", "no",
        "pl", "pt", "pt-br", "ro", "ru", "sk", "sv", "th", "tr", "uk", "vi", "zh", "zh-tw",
    ))

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.__language = None

    def check(self):
        return super().check() and super().cast().lower() in self.__whitelisted

    def cast(self):
        return super().cast().lower()

    def __getattr__(self, name):
        if self.__language is None:
            if self.check():
                self.__language = languages.LanguageMeta.get(self.cast())
            else:
                raise ValueError("trying to access features of a non-existent language")
        return getattr(self.__language, name)


class ReviewerRole(base.Int):
    name = "reviewrole"
    __mask = re.compile(r"<@&(?P<id>\d+)>")

    def check(self):
        try:
            super().check()
            return True
        except ValueError:
            return self.__mask.match(self.value)

    def cast(self):
        try:
            return super().cast()
        except (TypeError, ValueError):
            return base.Int(self.__mask.match(self.value).group("id")).cast()
