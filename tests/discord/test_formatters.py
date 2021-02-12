import collections
from urllib import parse

from librarian import storage
from librarian.discord import formatters


class TestOutput:
    def test__basic(self):
        assert formatters.codewrap("words") == "```\nwords\n```"
        assert formatters.codewrap((1, False, None, 'a')) == "```\n1\nFalse\nNone\na\n```"

        output = formatters.pretty_output(["./a.out", "test"], "Segmentation fault")
        assert output.startswith("```\nlibrarian@librarian")
        assert output == "```\nlibrarian@librarian:~$ ./a.out test\nSegmentation fault\n```"


class TestPull:
    def test__basic(self, existing_pulls, repo):
        for p in existing_pulls:
            pull = storage.Pull(p)
            pull_url = parse.urlparse(formatters.PullFormatter.url_for(pull, repo)).geturl()
            assert pull_url == "https://github.com/{}/pull/{}".format(repo, pull.number)

            real_state = formatters.PullState.real_state(pull)
            if p["merged"]:
                assert real_state == formatters.PullState.MERGED and pull.state == "closed"
            elif p["draft"]:
                expected = formatters.PullState.CLOSED if pull.state == "closed" else formatters.PullState.DRAFT
                assert pull.state != "draft" and real_state == expected
            else:
                assert real_state == formatters.PullState.by_name(p["state"])


class TestUser:
    def test__basic(self):
        assert formatters.UserFormatter.chain((1, 2)) == "<@1>, <@2>"
        assert formatters.UserFormatter.chain((1, 2, 3), separator=" | ") == "<@1> | <@2> | <@3>"

        user_cls = collections.namedtuple("User", "id name")
        users = [user_cls(1, "test"), user_cls(2, "user")]
        assert formatters.UserFormatter.chain(users) == "<@1>, <@2>"
