import re

from librarian.discord.settings import base


class StoreInPins(base.Bool):
    name = "store_in_pins"


class Language(base.String):
    name = "language"
    __whitelisted = frozenset((
        "en", "ar", "be", "bg", "cs", "da", "de", "gr", "es", "fi", "fr", "hu", "id", "it", "ja", "ko", "nl", "no",
        "pl", "pt", "pt-br", "ro", "ru", "sk", "sv", "th", "tr", "uk", "vi", "zh", "zh-tw",
    ))

    def check(self):
        return super().check() and super().cast().lower() in self.__whitelisted

    def cast(self):
        return super().cast().lower()


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
