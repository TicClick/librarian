import itertools
import json
import random

from aiohttp import web
import pytest

import librarian.discord
import librarian.github
import librarian.storage

from tests import utils


@pytest.fixture
def existing_pulls(authors, titles_by_codes):
    res = []
    titles = list(itertools.chain(*titles_by_codes.values()))
    for number in range(1, 300):
        closed = random.random() < 0.8
        merged = random.random() < 0.9
        draft = random.random() < 0.3
        assignees = set(
            random.choice(authors)
            for _ in range(3)
            if random.random() < 0.3
        )
        res.append(utils.make_pull(
            number,
            random.choice(authors),
            random.choice(titles),
            assignees=assignees,
            state="closed" if closed else "open",
            merged=closed and merged and not draft,
            draft=draft,
        ))
    return res


def make_get_routes(repo, existing_pulls, unstable=False):
    result = {}

    async def list_pulls(request: web.Request):
        if unstable:
            return web.Response(status=200, text="", content_type="application/json")

        pulls = existing_pulls
        q = request.url.query
        if q.get("sort", "created") == "created":
            pulls.sort(key=lambda p: p["created_at"])

        limit = int(q.get("per_page", 30))
        offset = (int(q.get("page", 1)) - 1) * limit
        data = [p for p in pulls if p["state"] == q.get("state", "open")]

        return web.Response(
            status=200,
            text=json.dumps(data[offset: offset + limit]),
            content_type="application/json"
        )

    for pull in existing_pulls:
        pull_path = "/repos/{}/pulls/{}".format(repo, pull["number"])
        issue_path = "/repos/{}/issues/{}".format(repo, pull["number"])

        if unstable and random.random() >= 0.5:
            code = random.choice([500, 501, 502])
            result[pull_path] = utils.make_response(code, {})
            result[issue_path] = utils.make_response(code, {})
        else:
            result[pull_path] = utils.make_response(200, pull)
            result[issue_path] = utils.make_response(200, utils.as_issue(pull))

    pulls_path = "/repos/{}/pulls".format(repo)
    result[pulls_path] = list_pulls

    return result


@pytest.fixture
def get_routes(repo, existing_pulls):
    yield make_get_routes(repo, existing_pulls)


@pytest.fixture
def unstable_get_routes(repo, existing_pulls):
    yield make_get_routes(repo, existing_pulls, unstable=True)


@pytest.fixture
def post_routes(repo, existing_pulls):
    result = {}

    def make_handler(pull):
        async def add_assignee(request: web.Request):
            data = json.loads(await request.content.read())
            reply = utils.as_issue(pull)
            if data and data["assignees"]:
                reply = utils.with_assignees(reply, data["assignees"])
            return web.Response(status=201, text=json.dumps(reply), content_type="application/json")

        return add_assignee

    for pull in existing_pulls:
        pull_path = "/repos/{}/issues/{}/assignees".format(repo, pull["number"])
        result[pull_path] = make_handler(pull)

    return result


@pytest.fixture
def mock_github(monkeypatch, aiohttp_client, loop, get_routes, post_routes, gh_token):
    yield utils.make_github_instance(monkeypatch, aiohttp_client, loop, get_routes, post_routes, gh_token)


@pytest.fixture
def mock_unstable_github(monkeypatch, aiohttp_client, loop, unstable_get_routes, post_routes, gh_token):
    yield utils.make_github_instance(monkeypatch, aiohttp_client, loop, unstable_get_routes, post_routes, gh_token)


@pytest.fixture
def gh_token():
    return "AQAD-0xCOFFEE"


@pytest.fixture
def repo():
    return "test-owner/test-repo"


@pytest.fixture
def authors():
    return ["abc", "def", "ghi", "jkl"]


@pytest.fixture
def titles_by_codes():
    return {
        "ru": ["[RU] Test", "[EN/RU] update"],
        None: ["TEST PULL DO NOT MERGE"],
        "en": ["[EN/RU] update"],
        "pl": ["[PL] blah"],
        "fr": ["[FR] another blah"],
    }


@pytest.fixture
def language_code():
    return "ru"


@pytest.fixture
def runtime(tmpdir):
    yield tmpdir


@pytest.fixture
def dbpath(tmpdir):
    yield str(tmpdir / "sqlite.db")


@pytest.fixture
def storage(dbpath):
    yield librarian.storage.Storage(dbpath)


@pytest.fixture
def client(mock_github, storage, repo, gh_token, assignee_login):
    bot = librarian.discord.Client(
        github=librarian.github.GitHub(token=gh_token, repo=repo),
        storage=storage,
        assignee_login=assignee_login,
    )
    bot.setup()
    yield bot


@pytest.fixture
def make_context(client, mocker):
    def inner():
        channel = mocker.Mock()
        channel.guild = mocker.Mock()
        channel.send = mocker.AsyncMock()

        msg = mocker.Mock()
        msg.channel = channel
        msg.author = mocker.Mock()

        ctx = mocker.Mock()
        ctx.configure_mock(**{
            "bot": client,
            "message": msg,
            "send_help": mocker.AsyncMock(),
            "args": lambda: msg.channel.send.call_args.args,
            "kwargs": lambda: msg.channel.send.call_args.kwargs,
        })
        return ctx

    return inner


@pytest.fixture
def assignee_login():
    return "assignee-login"
