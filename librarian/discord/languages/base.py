import random
import re


class LanguageMeta(type):
    code = "langcode"
    highlights = [
        "a new wiki article is just a click away:",
        "does that seem promising?",
        "please take a look",
        "there's a change waiting for reviews to happen:",
    ]

    __languages = {}

    def __new__(mcs, name, bases, attrs):
        cls = super().__new__(mcs, name, bases, attrs)
        if name != "Language":
            assert cls.code not in mcs.__languages, f"there's already a language class with the code {cls.code!r}"
            mcs.__languages[cls.code] = cls
        return cls

    @property
    def title_regex(mcs):
        if not hasattr(mcs, "__regex"):
            mcs.__regex = re.compile(r"^\[(\w+.?)?{}(.+)?\]".format(mcs.code.upper()))
        return mcs.__regex

    @property
    def random_highlight(mcs):
        return random.choice(mcs.HIGHLIGHTS)

    @classmethod
    def get(mcs, langcode):
        return mcs.__languages[langcode]


class Language(metaclass=LanguageMeta):
    pass
