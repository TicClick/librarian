import pytest

from librarian.storage import utils


class TestSessionDecorator:
    def test__required_session_keyword(self):
        with pytest.raises(RuntimeError) as exc:
            @utils.optional_session
            def dummy_function(b):
                pass

        assert "@optional_session" in str(exc) and "dummy_function" in str(exc)

    def test__external_session_passed(self):
        class Dummy:
            @utils.optional_session
            def method(self, s):
                return s

        assert Dummy().method(s=1234) == 1234

    def test__internal_session_made(self, mocker):
        internal_session = mocker.MagicMock()

        class Dummy:
            @utils.optional_session
            def method(self, s=None):
                assert s is not None
                return 12345

            def session_scope(self):
                return internal_session

        assert Dummy().method() == 12345
        internal_session.__enter__.assert_called()
        internal_session.__exit__.assert_called()
