import collections as cs

import discord


def codewrap(obj):
    def inner():
        yield "```"
        if isinstance(obj, (str, bytes)):
            yield obj
        elif hasattr(obj, "__iter__"):
            for elem in obj:
                yield str(elem)
        yield "```"

    return "\n".join(inner())


def pretty_output(cmd, output):
    return codewrap((
        "librarian@librarian:~$ {}".format(" ".join(cmd)),
        output
    ))


_State = cs.namedtuple("PullState", "name color icon")


# icons taken from https://github.com/primer/octicons
class PullState:
    OPEN = _State(
        "open", 0x28a745, "https://raw.githubusercontent.com/TicClick/librarian/main/media/check-circle-32.png"
    )
    DRAFT = _State(
        "draft", 0x6a737d, "https://raw.githubusercontent.com/TicClick/librarian/main/media/circle-32.png"
    )
    CLOSED = _State(
        "closed", 0xd73a49, "https://raw.githubusercontent.com/TicClick/librarian/main/media/circle-slash-32.png"
    )
    MERGED = _State(
        "merged", 0x6f42c1, "https://raw.githubusercontent.com/TicClick/librarian/main/media/check-circle-fill-32.png"
    )

    @staticmethod
    def real_state(pull) -> _State:
        """ Display a pull's state as seen on GitHub. """
        if pull.merged:
            return PullState.MERGED
        if pull.draft and pull.state != PullState.CLOSED.name:
            return PullState.DRAFT
        return PullState.by_name(pull.state)

    @classmethod
    def by_name(cls, name):
        return getattr(cls, name.upper())


class PullFormatter:
    @staticmethod
    def url_for(pull, repo: str) -> str:
        return f"https://github.com/{repo}/pull/{pull.number}"

    @staticmethod
    def rich_repr(pull, repo: str) -> str:
        """ Pull representation for messages sent out via Discord. """
        return "#{no} [{title}]({url}) by {author} ({merged_at})".format(
            no=pull.number,
            title=pull.title,
            url=PullFormatter.url_for(pull, repo),
            author=pull.user_login,
            merged_at=pull.merged_at.date(),
        )

    @staticmethod
    def make_embed_for(pull, repo):
        description = (
            f"**author**: {pull.user_login}\n"
            f"**last update**: {pull.updated_at.date()} at {pull.updated_at.time()} GMT"
        )
        state = PullState.real_state(pull)

        embed = discord.Embed(
            title="#{} {}".format(pull.number, pull.title),
            description=description,
            url=PullFormatter.url_for(pull, repo),
            color=state.color,
        )
        embed.set_footer(
            text=" | ".join((
                state.name.upper(),
                "{comments} review comment{comments_suffix}".format(
                    comments=pull.review_comments,
                    comments_suffix="" if pull.review_comments == 1 else "s"
                ),
                "{changed_files} file{changed_files_suffix} affected".format(
                    changed_files=pull.changed_files,
                    changed_files_suffix="" if pull.changed_files == 1 else "s"
                )
            )),
            icon_url=state.icon
        )
        return embed
