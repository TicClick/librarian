import json
import random

import aiohttp
from aiohttp import web
import pytest

from tests import utils


@pytest.fixture
def existing_pulls(authors, titles):
    res = []
    for number in range(1, 230):
        closed = random.random() < 0.8
        merged = random.random() < 0.9
        res.append(utils.make_pull(
            number,
            random.choice(authors),
            random.choice(titles),
            state="closed" if closed else "open",
            merged=closed and merged
        ))
    return res


@pytest.fixture
def get_routes(repo, existing_pulls):
    result = {}

    async def list_pulls(request: aiohttp.ClientRequest):
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
        result[pull_path] = utils.make_response(200, pull)

        issue_path = "/repos/{}/issues/{}".format(repo, pull["number"])
        result[issue_path] = utils.make_response(200, utils.as_issue(pull))

    pulls_path = "/repos/{}/pulls".format(repo)
    result[pulls_path] = list_pulls

    return result


@pytest.fixture
def mock_github(monkeypatch, aiohttp_client, loop, get_routes, gh_token):
    yield utils.make_github_instance(monkeypatch, aiohttp_client, loop, get_routes, gh_token)


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
def titles():
    return ["Test", "[RU] Test", "TEST PULL DO NOT MERGE", "[EN/RU] update", "blah", "[FR] another blah"]
