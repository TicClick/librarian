import pytest


@pytest.fixture
def bool_casts():
    return [
        ("0", False),
        ("1", True),
        ("true", True),
        ("True", True),
        ("TRue", True),
        ("false", False),
        ("FALse", False),
        ("False", False),
    ]


@pytest.fixture
def string_casts():
    return [
        ("1", "1"),
        ("100" * 30, "100" * 30),
        ("0", "0"),
        ("\ntest       ", "test"),
        ("some  string", "some  string"),
    ]


@pytest.fixture
def int_casts():
    return [
        (0, 0),
        (-10, -10),
        (1, 1),
        ("1", 1),
        ("1" * 1000, int("1" * 1000)),
        (int("1" * 1000), int("1" * 1000)),
    ]
