import http
import itertools as it
import logging
import typing

import aiohttp
import arrow

logger = logging.getLogger(__name__)


class RateLimit:
    """
    Rate limit storage for GitHub API

    Extracts the values of X-Ratelimit-* headers from an HTTP response,
    according to https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting.
    Available values:

    - `limit`, max. number of requests within time span;
    - `left`, available requests;
    - `reset`, when API usage limit is refreshed.
    """

    HEADER_LIMIT = "X-Ratelimit-Limit"
    HEADER_REMAINING = "X-Ratelimit-Remaining"
    HEADER_RESET = "X-Ratelimit-Reset"

    def __init__(self, headers: typing.Dict[str, str] = None):
        self.limit: typing.Optional[int] = None
        self.left: typing.Optional[int] = None
        self.reset = arrow.Arrow.utcnow()
        if headers is not None:
            self.update(headers)

    def update(self, headers: typing.Mapping) -> None:
        """ Update current rate limits. """

        self.limit = headers.get(self.HEADER_LIMIT)
        self.left = headers.get(self.HEADER_REMAINING)
        timestamp = headers.get(self.HEADER_RESET)
        self.reset = arrow.get(int(timestamp)) if timestamp is not None else None

    def __repr__(self):
        reset_ts = self.reset.format() if self.reset is not None else None
        return "{}/{} until {}".format(self.left, self.limit, reset_ts)


class GitHub:
    """
    Asynchronous wrapper around GitHub REST API v3. So far, only token-based authorization is supported.
    Two kinds of interfaces are provided:

    1. A limited set of methods to query predefined endpoints, such as repos/<repo>/pulls/<number>.
    2. `call_method` for anything else that is not wrapped.

    It's possible to call the wrapper's methods directly without passing an instance of `aiohttp.ClientSession`.
    (it will be created automatically). However, it's advised to prepare a session beforehand to reduce the overhead
    for when there are multiple objects to fetch:

        api = GitHub("AQAD-mytoken", "someone/osu-wiki")
        with api.make_session() as s:
            data = asyncio.gather(
                api.get_single_pull(number, session=s)
                for number in range(2000, 2100)
            )
    """

    BASE_URL = "https://api.github.com"
    OBJECTS_PER_PAGE = 100  # the maximum GitHub can provide
    SESSION_METHODS = {"get", "options", "head", "post", "put", "batch", "delete"}

    def __init__(self, token: str, repo: str):
        """
        :param token: GitHub API token
        :param repo: repository name in `owner-name/repo-name` format
        """

        self.__token = token
        self.ratelimit = RateLimit()
        self.repo = repo

    @classmethod
    def make_default_headers(cls, token) -> typing.Dict[str, str]:
        """
        Create a default set of headers for GitHub API.
        These carry authorization data and keep the connection open for HTTP/1.1.
        :param token: GitHub API token
        """

        return {
            "Authorization": f"token {token}",
            "Connection": "keep-alive",
        }

    def make_session(self) -> aiohttp.ClientSession:
        """
        Create a default session for asynchronous connection with predefined auth and keep-alive headers.
        """

        return aiohttp.ClientSession(headers=self.make_default_headers(self.__token))

    async def call_method(
        self, path: str, query: dict = None, data: dict = None,
        session: aiohttp.ClientSession = None, method: str = "get"
    ) -> dict:
        """
        Perform HTTP request with optional query string and JSON payload,
        allowing it up to 300s to complete, and return JSON on success.
        Raise `aiohttp.client_exceptions.ClientResponseError` on 4xx and 5xx response codes.

        :param path: in-site path without domain name (for ex., "repos/someone/some-repo/pulls")
        :param query: a dict with query string parameters
        :param data: request body (must be a JSON-serializable dictionary)
        :param session: client session object
        :param method: HTTP verb (any case), one of: GET, OPTIONS, HEAD, POST, PUT, PATCH, DELETE.
        """

        method = method.lower()
        if method not in self.SESSION_METHODS:
            raise ValueError(f"Unknown HTTP verb {method.upper()}")

        inner_session = session is None
        if session is None:
            session = self.make_session()

        session_method = getattr(session, method.lower())
        query = query or {}
        url = f"{self.BASE_URL}/{path}"

        async with session_method(url, params=query, json=data) as result:
            try:
                if result.status >= http.HTTPStatus.BAD_REQUEST:
                    result.raise_for_status()
                return await result.json()
            finally:
                self.ratelimit.update(result.headers)
                if inner_session:
                    await session.close()

    async def get(
        self, path: str, query: dict = None, session: aiohttp.ClientSession = None
    ) -> typing.Optional[dict]:
        """ Perform GET HTTP request. """
        return await self.call_method(path=path, query=query, session=session, method="get")

    async def post(
        self, path: str, query: dict = None, data: dict = None,
        session: aiohttp.ClientSession = None
    ) -> typing.Optional[dict]:
        """ Perform POST HTTP request. """
        return await self.call_method(path=path, query=query, data=data, session=session, method="post")

    async def get_single_pull(
        self, pull_id: int, session: aiohttp.ClientSession = None
    ) -> typing.Optional[dict]:
        """
        Fetch the data about one pull from the repository. Because pulls are extended issues,
        some information is also accessible when reading a pull as an issue (see `get_single_issue`).
        """

        path = f"repos/{self.repo}/pulls/{pull_id}"
        try:
            return await self.get(path, session=session)
        except aiohttp.client_exceptions.ClientResponseError as exc:
            if exc.status == http.HTTPStatus.NOT_FOUND:
                return None
            raise exc

    async def get_single_issue(
        self, issue_id: int, session: aiohttp.ClientSession = None
    ) -> typing.Optional[dict]:
        """
        Fetch the data about one issue from the repository. Pulls may also be accessed through this method,
        although response is scarce -- use `get_single_pull` instead.
        """

        path = f"repos/{self.repo}/issues/{issue_id}"
        try:
            return await self.get(path, session=session)
        except aiohttp.client_exceptions.ClientResponseError as exc:
            if exc.status == http.HTTPStatus.NOT_FOUND:
                return None
            raise exc

    async def pulls(
        self, state: str = "open", direction: str = "asc", sort: str = "created", session: aiohttp.ClientSession = None
    ) -> typing.List[dict]:
        """
        List all pulls that fit given conditions, while iterating over their listing if it has multiple pages.

        :param state: pull state, one of: "open", "closed", "all"
        :param direction: sorting direction, "asc" for ascending, or "desc" for descending
        :param sort: name of a field to sort by, one of: "created", "updated", "popularity", "long-running".
            Refer to https://docs.github.com/en/rest/reference/pulls#list-pull-requests
        :param session: client session object
        """

        out: typing.List[dict] = []
        path = f"repos/{self.repo}/pulls"
        base_query = dict(state=state, sort=sort, direction=direction, per_page=self.OBJECTS_PER_PAGE)
        for page in it.count(1):
            query = dict(base_query)
            query["page"] = page
            pulls = await self.get(path, query, session=session)
            if not isinstance(pulls, list) or not pulls:
                break
            out.extend(pulls)

        return out
