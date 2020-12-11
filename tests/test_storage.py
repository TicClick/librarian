import inspect
import random
from urllib import parse

import arrow
import pytest

import librarian.storage as stg

from tests import utils


class TestBasics:
    def test__init(self, storage):
        models = inspect.getmembers(stg, predicate=lambda cls: isinstance(cls, stg.Base))
        for _, model in models:
            assert storage.engine.has_table(model.__tablename__)

    def test__no_commit(self, storage, existing_pulls, mocker):
        def faulty_commit():
            raise OSError("No space left on device")

        session = storage.make_session()
        mocker.patch.object(session, "commit", faulty_commit)
        mocker.patch.object(session, "close", side_effect=session.close)

        def faulty_session_maker():
            return session

        mocker.patch.object(storage, "make_session", faulty_session_maker)
        with pytest.raises(OSError):
            storage.pulls.save_from_payload(random.choice(existing_pulls))

        session.close.assert_called()
        assert session.query(stg.Pull).count() == 0


class TestPulls:
    def compare_pull(self, pull, payload, blacklist=None):
        blacklist = set(blacklist or [])

        for k in set(pull.DIRECT_KEYS) - blacklist:
            v = getattr(pull, k)
            original_v = payload[k]
            if k in pull.DATETIME_KEYS:
                v = arrow.get(v).replace(microsecond=0)
                original_v = arrow.get(original_v).replace(microsecond=0)

            assert v == original_v

        for k in set(pull.NESTED_KEYS) - blacklist:
            assert getattr(pull, k) == pull.read_nested(payload, k)

    def test__obj(self, existing_pulls, repo):
        for p in existing_pulls:
            pull = stg.Pull(p)
            self.compare_pull(pull, p)

            pull_url = parse.urlparse(pull.url_for(repo)).geturl()
            assert pull_url == "https://github.com/{}/pull/{}".format(repo, pull.number)

            updated_p = dict(p)
            updated_p["id"] = 1234567890
            updated_p["user"] = utils.user("nonexistent")
            updated_p["title"] = "[INVALIDCODE] Title"

            pull.update(updated_p)
            self.compare_pull(pull, updated_p, blacklist=("id",))
            assert pull.id != updated_p["id"]

            if p["merged"]:
                assert pull.real_state == "merged" and pull.state == "closed"
            elif p["draft"]:
                assert pull.state != "draft" and (pull.real_state == "draft" if pull.state != "closed" else "closed")
            else:
                assert pull.real_state == p["state"]

            self.compare_pull(pull, pull.as_dict(nested=True))
            self.compare_pull(pull, stg.Pull(pull.as_dict(nested=True)).as_dict(nested=True))

    def test__save(self, storage, existing_pulls, mocker):
        count = 0
        storage.pulls.save = mocker.Mock(side_effect=storage.pulls.save)
        mocker.patch.object(stg.PullHelper, "save", side_effect=stg.PullHelper.save)
        with storage.session_scope() as s:
            add_object = mocker.patch.object(s, "add", side_effect=s.add)
            for i, p in enumerate(existing_pulls):
                storage.pulls.save_from_payload(p)
                storage.pulls.save.assert_called()
                count += 1

                assert s.query(stg.Pull).filter(stg.Pull.number == p["number"]).count() == 1
                assert storage.pulls.by_number(p["number"])

                duplicate = dict(p)
                duplicate["title"] = "title-has-changed"

                add_object.reset_mock()
                storage.pulls.save_from_payload(duplicate, insert=True)
                add_object.assert_not_called()

                storage.pulls.save_from_payload(duplicate, insert=False)
                updated_pull = s.query(stg.Pull).filter(stg.Pull.number == p["number"]).first()
                assert updated_pull.title == duplicate["title"]

        with storage.session_scope() as s:
            assert s.query(stg.Pull).filter().count() == count

        assert storage.pulls.by_number(1234567) is None

    def test__save_many(self, storage, existing_pulls):
        n = len(existing_pulls)
        first = existing_pulls[:int(n/3)]
        second = existing_pulls[len(first): len(first) * 2]
        third = existing_pulls[len(first) * 2:]

        with storage.session_scope() as s:
            assert s.query(stg.Pull).count() == 0
            storage.pulls.save_many_from_payload(first)
            assert s.query(stg.Pull).count() == len(first)

        new_title = "[EN] {}".format(TestPulls.test__save_many.__name__)
        new_author = TestPulls.__name__
        with storage.session_scope() as s:
            for pull in first:
                pull["title"] = new_title
                pull["user"]["login"] = new_author

            storage.pulls.save_many_from_payload(first)
            assert s.query(stg.Pull).count() == len(first)

            pulls = s.query(stg.Pull).all()
            assert all(
                pull.title == new_title and pull.user_login == new_author
                for pull in pulls
            )

        with storage.session_scope() as s:
            storage.pulls.save_many_from_payload(second)
            assert s.query(stg.Pull).count() == len(first) + len(second)

        new_title_2 = "[RU] Add {} (#2)".format(TestPulls.test__save_many.__name__)
        for pull in third:
            pull["title"] = new_title

        numbers = [_["number"] for _ in third]
        with storage.session_scope() as s:
            storage.pulls.save_many_from_payload(existing_pulls)
            assert s.query(stg.Pull).count() == len(existing_pulls)

            pulls = s.query(stg.Pull).filter(stg.Pull.id.in_(numbers)).all()
            assert all(pull.title == new_title_2 for pull in pulls)

    def test__remove(self, storage, existing_pulls):
        with storage.session_scope() as s:
            assert s.query(stg.Pull).count() == 0
            storage.pulls.remove(random.choice(existing_pulls)["number"])

            for pull in existing_pulls[:10]:
                storage.pulls.save_from_payload(pull)
            assert s.query(stg.Pull).count() == 10

            for pull in existing_pulls[:10]:
                storage.pulls.remove(pull["number"])
            assert s.query(stg.Pull).count() == 0

    def test__count_merged(self, storage, existing_pulls):
        storage.pulls.save_many_from_payload(existing_pulls)
        merged = sorted(
            (_ for _ in existing_pulls if _["merged"]),
            key=lambda k: k["merged_at"]
        )

        start_date = arrow.get(merged[0]["merged_at"]).datetime
        for i, pull in enumerate(merged):
            end_date = arrow.get(merged[i]["merged_at"]).datetime
            from_storage = storage.pulls.count_merged(start_date, end_date)
            assert len(from_storage) == i + 1

    def test__active_pulls(self, storage, existing_pulls):
        storage.pulls.save_many_from_payload(existing_pulls)
        with storage.session_scope() as s:
            for stored_number, existing_number in zip(
                sorted(_.number for _ in storage.pulls.active_pulls(s)),
                sorted(_["number"] for _ in existing_pulls if _["state"] != "closed")
            ):
                assert stored_number == existing_number


class TestMetadata:
    def test__basic(self, storage):
        m = storage.metadata
        assert m.load() == {}
        assert m.load_field("blah") is None

        for data_piece in (1, 2.3, "blah", {"nested": {"dict": "ionary"}}, ["test"], [["test"]]):
            m.save_field("blah", data_piece)
            assert m.load() == {"blah": data_piece}
            assert m.load_field("blah") == data_piece

        m.save({})
        assert m.load() == {}
        m.save({1: 2, 3: 4})
        assert m.load() == {1: 2, 3: 4}


class TestDiscordMessages:
    def test__save(self, storage, existing_pulls):
        n = random.randint(1, 100)
        storage.discord_messages.save(*(
            stg.DiscordMessage(
                id=msg_id,
                channel_id=random.randint(1, 1000),
                pull_number=pull["number"]
            )
            for msg_id, pull in zip(
                random.sample(range(1, 1000), n),
                random.sample(existing_pulls, n)
            )
        ))

        restored = storage.discord_messages.by_pull_numbers(*(_["number"] for _ in existing_pulls))
        assert len(restored) == n
