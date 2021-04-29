from discord import message
from discord.ext import commands

from librarian import github as gh
from librarian import storage as stg


class Bot(commands.Bot):
    storage: stg.Storage
    github: gh.GitHub


class Context(commands.Context):
    message: message.Message
    bot: Bot
