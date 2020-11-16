import http
import itertools as it
import logging

import aiohttp
import arrow


logger = logging.getLogger(__name__)


class RateLimit:
    def __init__(self, headers=None):
        self.limit = None
        self.left = None
        self.reset = arrow.Arrow.utcnow()
        if headers is not None:
            self.update(headers)

    def update(self, headers):
        self.limit = headers["X-Ratelimit-Limit"]
        self.left = headers["X-Ratelimit-Remaining"]
        self.reset = arrow.get(int(headers["X-Ratelimit-Reset"]))

    def __repr__(self):
        return "{}/{} until {}".format(self.left, self.limit, self.reset.format())


class GitHub(object):
    BASE_URL = "https://api.github.com"
    OBJECTS_PER_PAGE = 100

    def __init__(self, token, repo):
        self.__token = token
        self.session = self.make_session()
        self.ratelimit = RateLimit()
        self.repo = repo

    @property
    def default_headers(self):
        return {
            "Authorization": f"token {self.__token}",
            "Connection": "keep-alive",
        }

    def make_session(self):
        return aiohttp.ClientSession(headers=self.default_headers)

    async def call_method(self, path, query=None, data=None, session=None, method="get"):
        if session is None:
            session = self.session

        session_method = getattr(session, method)
        query = query or {}
        url = f"{self.BASE_URL}/{path}"

        async with session_method(url, params=query, data=data) as result:
            try:
                if result.status >= http.HTTPStatus.BAD_REQUEST:
                    result.raise_for_status()
                return await result.json()
            finally:
                self.ratelimit.update(result.headers)

    async def fetch(self, path, query=None, session=None):
        return await self.call_method(path=path, query=query, session=session, method="get")

    async def patch(self, path, query=None, data=None, session=None):
        return await self.call_method(path=path, query=query, data=data, session=session, method="patch")

    async def get_single_pull(self, pull_id, session=None):
        path = f"repos/{self.repo}/pulls/{pull_id}"
        try:
            return await self.fetch(path, session=session)
        except aiohttp.client_exceptions.ClientResponseError as exc:
            if exc.status == http.HTTPStatus.NOT_FOUND:
                return None

    async def update_single_issue(self, issue_id, session=None, body=None):
        path = f"repos/{self.repo}/issues/{issue_id}"
        return await self.patch(path, session=session, body=body or {})

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
