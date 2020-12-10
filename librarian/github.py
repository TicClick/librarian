import http
import itertools as it
import logging

import aiohttp
import arrow


logger = logging.getLogger(__name__)


class RateLimit:
    HEADER_LIMIT = "X-Ratelimit-Limit"
    HEADER_REMAINING = "X-Ratelimit-Remaining"
    HEADER_RESET = "X-Ratelimit-Reset"

    def __init__(self, headers=None):
        self.limit = None
        self.left = None
        self.reset = arrow.Arrow.utcnow()
        if headers is not None:
            self.update(headers)

    def update(self, headers):
        self.limit = headers.get(self.HEADER_LIMIT)
        self.left = headers.get(self.HEADER_REMAINING)
        timestamp = headers.get(self.HEADER_RESET)
        self.reset = arrow.get(int(timestamp)) if timestamp is not None else None

    def __repr__(self):
        reset_ts = self.reset.format() if self.reset is not None else None
        return "{}/{} until {}".format(self.left, self.limit, reset_ts)


class GitHub(object):
    BASE_URL = "https://api.github.com"
    OBJECTS_PER_PAGE = 100

    def __init__(self, token, repo):
        self.__token = token
        self.ratelimit = RateLimit()
        self.repo = repo

    @classmethod
    def make_default_headers(cls, token):
        return {
            "Authorization": f"token {token}",
            "Connection": "keep-alive",
        }

    def make_session(self):
        return aiohttp.ClientSession(headers=self.make_default_headers(self.__token))

    async def call_method(self, path, query=None, data=None, session=None, method="get"):
        if session is None:
            session = self.make_session()

        session_method = getattr(session, method)
        query = query or {}
        url = f"{self.BASE_URL}/{path}"

        async with session_method(url, params=query, json=data) as result:
            try:
                if result.status >= http.HTTPStatus.BAD_REQUEST:
                    result.raise_for_status()
                return await result.json()
            finally:
                self.ratelimit.update(result.headers)

    async def fetch(self, path, query=None, session=None):
        return await self.call_method(path=path, query=query, session=session, method="get")

    async def post(self, path, query=None, data=None, session=None):
        return await self.call_method(path=path, query=query, data=data, session=session, method="post")

    async def get_single_pull(self, pull_id, session=None):
        path = f"repos/{self.repo}/pulls/{pull_id}"
        try:
            return await self.fetch(path, session=session)
        except aiohttp.client_exceptions.ClientResponseError as exc:
            if exc.status == http.HTTPStatus.NOT_FOUND:
                return None

    async def add_assignee(self, issue_id, assignee, session=None):
        path = f"repos/{self.repo}/issues/{issue_id}/assignees"
        data = {"assignees": [assignee]}
        return await self.post(path, session=session, data=data)

    async def get_single_issue(self, issue_id, session=None):
        path = f"repos/{self.repo}/issues/{issue_id}"
        try:
            return await self.fetch(path, session=session)
        except aiohttp.client_exceptions.ClientResponseError as exc:
            if exc.status == http.HTTPStatus.NOT_FOUND:
                return None

    async def pulls(self, state="open", direction="asc", sort="created", session=None):
        out = []
        path = f"repos/{self.repo}/pulls"
        base_query = dict(state=state, sort=sort, direction=direction, per_page=self.OBJECTS_PER_PAGE)
        for page in it.count(1):
            query = dict(base_query)
            query["page"] = page
            pulls = await self.fetch(path, query, session=session)
            if not isinstance(pulls, list) or not pulls:
                break
            out.extend(pulls)

        return out
