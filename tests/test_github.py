import random

import arrow
import aiohttp.client_exceptions as aiohttp_excs
import pytest

import librarian.github


class TestBasics:
    async def ensure_headers(self, gh_token, repo):
        api = librarian.github.GitHub(gh_token, repo)
        external_session = api.make_session()

        for headers in (
            api.make_default_headers(gh_token),
            external_session._default_headers
        ):
            assert headers["Authorization"] == "token {}".format(gh_token)

    def test__ratelimit(self):
        sometime = arrow.get().floor("second").shift(years=100)
        payload = {
            librarian.github.RateLimit.HEADER_REMAINING: 456,
            librarian.github.RateLimit.HEADER_LIMIT: 123,
            librarian.github.RateLimit.HEADER_RESET: sometime.int_timestamp,
        }

        for headers in (None, payload):
            limit = librarian.github.RateLimit(headers)
            assert repr(limit)

            limit.update(payload)
            assert limit.left == 456
            assert limit.limit == 123
            assert limit.reset == sometime
            assert repr(limit)

    async def test__unpatched_client_headers(self, gh_token, repo):
        await self.ensure_headers(gh_token, repo)

    async def test__patched_client_headers(self, mock_github, gh_token, repo):
        await self.ensure_headers(gh_token, repo)


class TestInteraction:
    @pytest.mark.parametrize("outer_session", [True, False])
    async def test__get_single_object(self, mock_github, gh_token, repo, existing_pulls, outer_session):
        api = librarian.github.GitHub(gh_token, repo)
        session = api.make_session() if outer_session else None

        for pull in random.sample(existing_pulls, 5):
            data = await api.get_single_pull(pull["number"], session=session)
            assert data["number"] == pull["number"]
            assert data["user"] and data["user"]["login"]
            assert arrow.get(data["created_at"])

            data = await api.get_single_issue(pull["number"], session=session)
            assert data["number"] == pull["number"]
            assert "merged_at" not in data

    async def test__get_nonexistent_pulls_and_issues(self, mock_github, gh_token, repo, existing_pulls):
        api = librarian.github.GitHub(gh_token, repo)
        nonexistent = max(_["number"] for _ in existing_pulls) + 100
        assert await api.get_single_pull(nonexistent) is None
        assert await api.get_single_issue(nonexistent) is None

    async def test__get_single_anything__propagated_errors(self, mock_github, gh_token, repo, existing_pulls, mocker):
        api = librarian.github.GitHub(gh_token, repo)
        api.get = mocker.AsyncMock(
            side_effect=aiohttp_excs.ClientResponseError(request_info=None, history=None, status=500)
        )

        with pytest.raises(aiohttp_excs.ClientResponseError):
            await api.get_single_pull(10000)
        with pytest.raises(aiohttp_excs.ClientResponseError):
            await api.get_single_issue(12345)

    async def test__get_all_pulls(self, mock_github, gh_token, repo, existing_pulls, monkeypatch):
        api = librarian.github.GitHub(gh_token, repo)
        data = await api.pulls()
        assert data

        with monkeypatch.context() as m:
            m.setattr(api, "OBJECTS_PER_PAGE", 1)
            data2 = await api.pulls()
            assert len(data) == len(data2)
            for p1, p2 in zip(data, data2):
                assert p1 == p2

        data = await api.pulls(state="closed")
        assert all(
            _["state"] == "closed" and (
                _["merged_at"] is not None
                if _["merged"] else
                _["merged_at"] is None
            )
            for _ in data
        )

    async def test__unknown_method(self, gh_token, repo):
        api = librarian.github.GitHub(gh_token, repo)
        with pytest.raises(ValueError):
            await api.call_method("/test/", method="what")
