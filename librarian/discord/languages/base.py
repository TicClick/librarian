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
            if cls.code in mcs.__languages:
                raise RuntimeError(f"there's already a language class with the code {cls.code!r}")
            mcs.__languages[cls.code] = cls
        return cls

    @property
    def title_regex(mcs):
        if not hasattr(mcs, "__regex"):
            mask = r"""
                ^\[
                ({lang_pattern}{sep_pattern})*
                {lang}
                ({sep_pattern}{lang_pattern})*
                \]
            """.format(
                lang_pattern=r"[-a-zA-Z]+",
                sep_pattern=r"[|\\\/]",
                lang=mcs.code.upper()
            )
            mcs.__regex = re.compile(mask, re.IGNORECASE | re.VERBOSE)

        return mcs.__regex

    @property
    def random_highlight(mcs):
        return random.choice(mcs.highlights)

    @classmethod
    def get(mcs, langcode):
        return mcs.__languages[langcode]

    @classmethod
    def all(mcs):
        return mcs.__languages


class Language(metaclass=LanguageMeta):
    pass
