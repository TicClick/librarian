import arrow
import pytest

import librarian.github


async def test__headers(mock_github, gh_token, repo):
    api = librarian.github.GitHub(gh_token, repo)
    external_session = api.make_session()

    for headers in (
        api.make_default_headers(gh_token),
        external_session._default_headers
    ):
        assert headers["Authorization"] == "token {}".format(gh_token)


@pytest.mark.parametrize("outer_session", [True, False])
async def test__get_single_object(mock_github, gh_token, repo, existing_pulls, outer_session):
    api = librarian.github.GitHub(gh_token, repo)
    session = api.make_session() if outer_session else None

    for pull in existing_pulls:
        data = await api.get_single_pull(pull["number"], session=session)
        assert data["number"] == pull["number"]
        assert data["user"] and data["user"]["login"]
        assert arrow.get(data["created_at"])

        data = await api.get_single_issue(pull["number"], session=session)
        assert data["number"] == pull["number"]
        assert "merged_at" not in data

    nonexistent = max(_["number"] for _ in existing_pulls) + 100

    assert await api.get_single_pull(nonexistent, session=session) is None
    assert await api.get_single_issue(nonexistent, session=session) is None


async def test__get_all_pulls(mock_github, gh_token, repo, existing_pulls, monkeypatch):
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
