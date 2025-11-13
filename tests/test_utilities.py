from unittest.mock import patch

from doyles_sdk._utilities import Doyles, NoOp


def test__module__():
    assert Doyles.__module__ == "doyles_sdk._utilities"


def test_guard_exit_call():
    import sys

    assert Doyles.guard_exit_call(sys.exit, 22) == 22
    assert Doyles.guard_exit_call(sys.exit, "ERROR") == "ERROR"
    assert Doyles.guard_exit_call(sys.exit) is None


def test_get_login():
    # Mock input() and getpass.getpass() to return predetermined values
    with (
        patch("builtins.input", return_value="username"),
        patch("getpass.getpass", return_value="password"),
    ):
        assert Doyles.get_login() == ("username", "password")


def test_keys_to_str():
    assert Doyles.keys_to_str({NoOp: "value", NoOp(): "value"}) == {
        "<class 'doyles_sdk._utilities.NoOp'>": "value",
        "<NoOp>": "value",
    }
    assert Doyles.keys_to_str([{NoOp: "value"}, {NoOp(): "value"}]) == [
        {"<class 'doyles_sdk._utilities.NoOp'>": "value"},
        {"<NoOp>": "value"},
    ]


def test_noop():
    assert Doyles.noop() is None
    assert Doyles.noop(1, 2) is None
    assert Doyles.noop(1, 2, kw="abc") is None


def test_NoOp():
    assert Doyles.noop == NoOp()
    this = NoOp()
    that = NoOp()
    assert this == that


def test_nullif():
    assert Doyles.nullif("xyz", "xyz") is None
    assert Doyles.nullif("", "") is None
    assert Doyles.nullif("abc", "") == "abc"
    assert Doyles.nullif(None, "") is None


def test_pretty_dict():
    assert (
        Doyles.pretty_dict(
            {
                "Outer1": {
                    "Inner1": "vInner1",
                    "Inner2": "vInner2",
                    "Inner3": {"Key1": "vKey1", "Key2": NoOp, "Key3": NoOp()},
                },
                "Outer2": "vOuter2",
            }
        )
        == '{\n    "Outer1": {\n        "Inner1": "vInner1",\n        "Inner2": "vInner2",\n        "Inner3": {\n            "Key1": "vKey1",\n            "Key2": <class \'doyles_sdk._utilities.NoOp\'>,\n            "Key3": <NoOp>\n        }\n    },\n    "Outer2": "vOuter2"\n}'
    )
    assert Doyles.pretty_dict({"Key": {}}) == '{\n    "Key": {}\n}'


def test_safe_join():
    assert Doyles.safe_join(["a", 2, "c"], ",") == "a,2,c"
    assert Doyles.safe_join([42, 27, 19], "-") == "42-27-19"
    assert Doyles.safe_join(("x", 99, "y"), ":") == "x:99:y"
    assert Doyles.safe_join("abc", ",") == "abc"
    assert Doyles.safe_join(42, ",") == "42"

    # ignore_none tests
    assert Doyles.safe_join([1, None, 3], ",") == "1,None,3"
    assert Doyles.safe_join([1, None, 3], ",", ignore_none=True) == "1,3"


def test_sort_dict():
    assert Doyles.sort_dict(
        {"X": {1: 234, "x": "xvalue", "X": "Xvalue"}, "a": "value"}
    ) == {
        "X": {
            1: 234,
            "X": "Xvalue",
            "x": "xvalue",
        },
        "a": "value",
    }


def test_url_quote():
    assert Doyles.url_quote("abc") == "abc"
    assert Doyles.url_quote("abc%20") == "abc%20"
    assert Doyles.url_quote("abc ") == "abc%20"

    # test strip
    assert Doyles.url_quote(" abc%20", strip=True) == "abc"
    assert Doyles.url_quote(" abc ", strip=True) == "abc"
