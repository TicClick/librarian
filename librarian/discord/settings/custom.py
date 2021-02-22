import re

from librarian.discord.settings import base
from librarian.discord import languages


class PinMessages(base.Bool):
    """
    pin open translations until they're merged/closed.
    possible values: true/false
    """

    name = "pin-messages"


class Language(base.String):
    """
    pulls with this language code will be watched.
    possible values: anything from https://osu.ppy.sh/wiki/en/Article_styling_criteria/Formatting#locales
    """

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
    """
    a single role that will be highlighted on new pulls for chosen language.
    possible values: numeric identifier or mention
    """

    name = "reviewer-role"
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
