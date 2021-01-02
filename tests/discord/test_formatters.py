from urllib import parse

from librarian import storage
from librarian.discord import formatters


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
