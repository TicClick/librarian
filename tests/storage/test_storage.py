import inspect
import random

import pytest

import librarian.storage as stg
from librarian.storage import base


class TestBasics:
    def test__init(self, storage):
        models = inspect.getmembers(stg, predicate=lambda cls: inspect.isclass(cls) and issubclass(cls, base.Base))
        assert models
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
