from librarian.discord.languages import base


class UnspecifiedLanguage(base.Language):
    """
    Matches everything that don't match the "[LANGUAGE_CODE] PR title" format
    """

    code = "none"
    highlights = [""]

    @classmethod
    def match(cls, line):
        return not line.strip().startswith("[")


class EveryLanguage(base.Language):
    """
    Matches everything
    """

    code = "all"
    highlights = [""]

    @classmethod
    def match(cls, _):
        return True

    @property
    def random_highlight(self):
        return ""
