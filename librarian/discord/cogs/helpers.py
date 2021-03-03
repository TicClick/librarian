from discord.ext import commands


def is_owner() -> commands.Command:
    """
    Decorator for bot commands that need to be accessible only by the bot's owner.
    Should precede @commands.command() in the decoration chain.
    """

    def predicate(ctx: commands.Context):
        return ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)


async def promoted_users(ctx: commands.Context) -> set:
    """ Fetch a list of identifiers of users that are allowed to change the bot's settings in a channel. """

    return ctx.bot.storage.discord.custom_promoted_users(
        ctx.message.channel.guild.id
    )


def is_promoted() -> commands.Command:
    """
    Decorator for bot commands that need to be accessible only by a set of trusted people.
    The "trusted people" are the server's owner, server managers, and users promoted by the .promote command.
    """

    async def predicate(ctx: commands.Context):
        permissions = ctx.message.channel.permissions_for(ctx.message.author)
        return (
            ctx.message.author.id == ctx.message.channel.guild.owner_id or
            permissions.manage_guild or permissions.administrator or
            ctx.message.author.id in await promoted_users(ctx)
        )

    return commands.check(predicate)
