from discord.ext import commands


def command(*args, **kwargs):
    async def is_owner(ctx: commands.Context):
        return await ctx.bot.is_owner(ctx.author)

    return commands.command(*args, **kwargs, checks=[is_owner])


def public_command(*args, **kwargs):
    return commands.command(*args, **kwargs)
