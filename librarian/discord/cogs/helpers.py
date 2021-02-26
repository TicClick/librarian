from discord.ext import commands


def is_owner():
    def predicate(ctx):
        return ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)


async def promoted_users(ctx: commands.Context):
    guild = ctx.message.channel.guild
    return ctx.bot.storage.discord.custom_promoted_users(guild.id) | {guild.owner_id}


def is_promoted():
    async def predicate(ctx):
        return ctx.message.author.id in await promoted_users(ctx)
    return commands.check(predicate)
