import hashlib
import itertools as it
import json
import random

from aiohttp import web
from aiohttp import test_utils
import arrow

import librarian.github


def make_id(data):
    return int(hashlib.md5(bytes(str(data), "latin1")).hexdigest()[-8:], base=16)


def make_date(since=None):
    return arrow.get(
        year=2020, month=random.randint(1, 12), day=random.randint(1, 28),
        hour=random.randint(0, 23), minute=random.randint(0, 59), second=random.randint(0, 59)
    )


def to_github_date(datetime):
    return datetime.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_pull(number, author, title, state, assignees, merged, draft):
    created_at = make_date()
    updated_at = created_at.shift(hours=2)
    return {
        "id": make_id(number),
        "number": number,
        "state": state,
        "locked": False,
        "title": title,
        "user": user(author),
        "labels": [],
        "assignees": [user(assignee) for assignee in assignees],
        "created_at": to_github_date(created_at),
        "updated_at": to_github_date(updated_at),
        "closed_at": to_github_date(updated_at) if state == "closed" else None,
        "merged_at": to_github_date(updated_at) if merged else None,
        "draft": draft,
        "merged": merged,
        "commits": random.randint(0, 100),
        "review_comments": random.randint(0, 100),
        "changed_files": random.randint(0, 10),
    }


def as_issue(pull):
    issue = dict(pull)
    for extra in ("merged", "merged_at", "draft", "review_comments", "changed_files"):
        issue.pop(extra)
    return issue


def user(login):
    return {"login": login, "id": make_id(login)}


def make_response(status, data):
    async def response(request):
        return web.Response(status=status, text=json.dumps(data), content_type="application/json")
    return response


def make_github_instance(monkeypatch, aiohttp_client, loop, get_routes, gh_token):
    app = web.Application()
    for path, handler in get_routes.items():
        app.router.add_get(path, handler)

    api = loop.run_until_complete(
        aiohttp_client(
            app,
            headers=librarian.github.GitHub.make_default_headers(gh_token)
        )
    )

    def session_maker(_):
        return test_utils.TestClient(
            api.server,
            loop=loop,
            headers=librarian.github.GitHub.make_default_headers(gh_token)
        ).session

    monkeypatch.setattr(librarian.github.GitHub, "make_session", session_maker)
    monkeypatch.setattr(librarian.github.GitHub, "BASE_URL", api.make_url(""))

    return app
