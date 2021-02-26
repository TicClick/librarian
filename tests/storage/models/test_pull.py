import random

import arrow
import pytest

import librarian.storage as stg
from librarian.storage.models import pull as pull_model

from tests import utils


class TestPulls:
    MAX_PULLS = 20

    def compare_pull(self, pull, payload, blacklist=None):
        blacklist = set(blacklist or [])

        for k in set(pull.DIRECT_KEYS) - blacklist:
            v = getattr(pull, k)
            original_v = payload[k]
            if k in pull.DATETIME_KEYS:
                v = arrow.get(v).floor("second")
                original_v = arrow.get(original_v).floor("second")

            assert v == original_v

        for k in set(pull.NESTED_KEYS) - blacklist:
            assert getattr(pull, k) == pull.read_nested(payload, k)

    @pytest.mark.freeze_time
    def test__obj(self, existing_pulls):
        for p in existing_pulls:
            pull = stg.Pull(p)
            self.compare_pull(pull, p)

            updated_p = dict(p)
            updated_p["id"] = 1234567890
            updated_p["user"] = utils.user("nonexistent")
            updated_p["title"] = "[INVALIDCODE] Title"

            pull.update(updated_p)
            self.compare_pull(pull, updated_p, blacklist=("id",))
            assert pull.id != updated_p["id"]

            self.compare_pull(pull, pull.as_dict(nested=True))
            self.compare_pull(pull, stg.Pull(pull.as_dict(nested=True)).as_dict(nested=True))

    def test__save(self, storage, existing_pulls, mocker):
        count = 0
        storage.pulls.save = mocker.Mock(side_effect=storage.pulls.save)
        mocker.patch.object(pull_model.PullHelper, "save", side_effect=pull_model.PullHelper.save)
        with storage.session_scope() as session:
            add_object = mocker.patch.object(session, "add", side_effect=session.add)
            for p in random.sample(existing_pulls, self.MAX_PULLS):
                storage.pulls.save_from_payload(p, s=session)
                storage.pulls.save.assert_called()
                count += 1

                session.commit()
                assert session.query(stg.Pull).filter(stg.Pull.number == p["number"]).count() == 1

                saved_pull = storage.pulls.by_number(p["number"], s=session)
                assert saved_pull
                if p["assignees"]:
                    assert set(_["login"] for _ in p["assignees"]) == set(saved_pull.assignees_logins)

                duplicate = dict(p)
                duplicate["title"] = "title-has-changed"

                add_object.reset_mock()
                storage.pulls.save_from_payload(duplicate, s=session, insert=True)
                add_object.assert_not_called()

                storage.pulls.save_from_payload(duplicate, s=session, insert=False)

                updated_pull = session.query(stg.Pull).filter(stg.Pull.number == p["number"]).first()
                assert updated_pull.title == duplicate["title"]

        with storage.session_scope() as s:
            assert s.query(stg.Pull).filter().count() == count
            assert storage.pulls.by_number(1234567, s=session) is None

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
                sorted(_.number for _ in storage.pulls.active_pulls(s=s)),
                sorted(_["number"] for _ in existing_pulls if _["state"] != "closed")
            ):
                assert stored_number == existing_number
