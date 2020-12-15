from . import bot
from . import cogs

from .bot import Client  # noqa
from .cogs.background import (
    base,
    github,
)


LOGGERS = (
    bot.logger,
    cogs.pulls.logger,
    cogs.system.logger,
    base.logger,
    github.logger,
)
