"""The e2e suite's browser guard, as logic (#432's acceptance gate): its checks run
after every browser test, so a guard weakened to pass everything would leave every
test green. ``guard_problems`` in ``tests/e2e/conftest.py`` is the whole of what the
fixture asserts; these drive it without a browser.
"""

from __future__ import annotations

from tests.e2e.conftest import guard_problems


def test_a_clean_test_passes() -> None:
    assert guard_problems([], 0, 0, [], []) == []


def test_a_request_off_the_loopback_host_fails() -> None:
    assert guard_problems(["https://x.example/"], 0, 0, [], []) == [
        "requests off the loopback host: ['https://x.example/']"
    ]


def test_the_plotlyjs_fetch_count_must_match_exactly() -> None:
    assert guard_problems([], 1, 1, [], []) == []
    assert guard_problems([], 1, 0, [], []) == ["plotly.js fetched 1 times; expected 0"]
    assert guard_problems([], 0, 1, [], []) == ["plotly.js fetched 0 times; expected 1"]
    assert guard_problems([], 2, 1, [], []) == ["plotly.js fetched 2 times; expected 1"]


def test_a_named_error_occurs_exactly_as_often_as_named() -> None:
    assert guard_problems([], 0, 0, ["E"], [("E", False)]) == []
    assert guard_problems([], 0, 0, ["E", "E"], [("E", False)]) == [
        "console errors: {'E': 2}; expected exactly: {'E': 1}"
    ]
    assert guard_problems([], 0, 0, [], [("E", False)]) == [
        "console errors: {}; expected exactly: {'E': 1}"
    ]
    assert guard_problems([], 0, 0, ["other"], []) == [
        "console errors: {'other': 1}; expected exactly: {}"
    ]


def test_a_repeating_error_must_occur_at_least_once() -> None:
    assert guard_problems([], 0, 0, ["Event"] * 3, [("Event", True)]) == []
    assert guard_problems([], 0, 0, ["Event"], [("Event", True)]) == []
    assert guard_problems([], 0, 0, [], [("Event", True)]) == [
        "console errors that never occurred: ['Event']"
    ]
    # A repeating name excuses only its own text.
    assert guard_problems([], 0, 0, ["Event", "other"], [("Event", True)]) == [
        "console errors: {'other': 1}; expected exactly: {}"
    ]
