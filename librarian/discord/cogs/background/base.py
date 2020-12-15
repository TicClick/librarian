import logging

from discord.ext import tasks, commands

logger = logging.getLogger(__name__)


class BackgroundCog(commands.Cog):
    def __init__(self, bot, *args, **kwargs):
        self.bot = bot
        self.github = bot.github
        self.storage = bot.storage

        super().__init__(*args, **kwargs)

    @property
    def name(self):
        return self.__class__.__name__

    async def start(self):
        logger.debug("Cog {} is running".format(self.name))
        self.loop.start()

    @tasks.loop()
    async def loop(self):
        raise NotImplementedError()

    def cog_unload(self):
        logger.debug(f"Stopping cog {self.name}")
        self.loop.cancel()
        logger.debug(f"Cog {self.name} is stopped")

    async def status(self):
        raise NotImplementedError()

    async def status_repr(self):
        status = await self.status()
        status_string = ", ".join(
            "{}={}".format(k, v)
            for k, v in sorted(status.items())
        )
        return "[{status}] {name}: {status_string}".format(
            status=" OK " if self.loop.is_running() else "DEAD",
            name=self.name,
            status_string=status_string if status_string else "{}"
        )
