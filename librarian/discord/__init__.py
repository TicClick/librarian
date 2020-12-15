from . import bot
from . import cogs

from .bot import Client  # noqa


LOGGERS = (
    bot.logger,
    cogs.pulls.logger,
    cogs.system.logger,
)
