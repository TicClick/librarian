import logging

from discord.ext import tasks, commands

from librarian import types

logger = logging.getLogger(__name__)


class BackgroundCog(commands.Cog):
    """
    Base class for background routines that need to run periodically (seconds to minutes).

    Each BackgroundCog by default has access to the bot instance and its methods,
    as well as the underlying storage and APIs. On its own, it provides a brief insight
    into its status in form of a key-value dictionary, which needs to be tailored to the cog's role.

    Classes that inherit from BackgroundCog need to override its `loop()` routine
    and do meaningful work. Warning: if a routine performs a blocking operation (anything without the use of `await`),
    it blocks other routines, so make sure to switch the context regularly.
    """

    def __init__(self, bot: types.Bot, *args, **kwargs):
        self.bot = bot
        self.github = bot.github
        self.storage = bot.storage

        super().__init__(*args, **kwargs)

    @property
    def name(self) -> str:
        """ Routine name, defaults to its class' name. """

        return self.__class__.__name__

    async def start(self) -> None:
        """ The method that is called after the bot is online. """

        logger.debug("Cog {} is starting up".format(self.name))
        self.loop.start()

    @tasks.loop()
    async def loop(self) -> None:
        """
        The method which is called regularly with an overridable interval. The main routine's code goes here.

        Caveats:
        - Make sure to switch context regularly to not block other routines.
        - Define the loop interval using keywords like `seconds`, `minutes` or `hours`.
        - To implement the shutdown cleanup, add a method decorated with @loop.after_loop.
        """

        raise NotImplementedError()

    def cog_unload(self) -> None:
        """
        This method is called when the bot is stopping.
        To implement the actual shutdown cleanup, add a method decorated with @loop.after_loop.
        """

        logger.debug(f"Stopping cog {self.name}")
        self.loop.cancel()
        logger.debug(f"Cog {self.name} is stopped")

    async def status(self) -> dict:
        """
        This method is called when the bot receives the .status command.
        Override it to provide statistics or any useful runtime data you want to see at glance.
        """

        raise NotImplementedError()

    async def status_repr(self) -> str:
        """
        Pretty-printer for status() method, which turns a dictionary into a string of the following format:

            [ STATUS ] RoutineName: parameter1=value1, parameter2=value2, ...
        """

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
