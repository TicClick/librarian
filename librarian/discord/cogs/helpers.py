from discord.ext import commands


def is_owner():
    def predicate(ctx):
        return ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)


async def promoted_users(ctx: commands.Context):
    return ctx.bot.storage.discord.custom_promoted_users(
        ctx.message.channel.guild.id
    )


def is_promoted():
    async def predicate(ctx):
        permissions = ctx.message.channel.permissions_for(ctx.message.author)
        return (
            ctx.message.author.id == ctx.message.channel.guild.owner_id or
            permissions.manage_guild or permissions.administrator or
            ctx.message.author.id in await promoted_users(ctx)
        )

    return commands.check(predicate)
