"""The e2e suite's browser guard, as logic (#432's acceptance gate): its checks run
after every browser test, so a guard weakened to pass everything would leave every
test green. ``guard_problems`` and ``chunk_problems`` in ``tests/e2e/conftest.py`` are
the whole of what the fixture asserts; these drive them without a browser.
"""

from __future__ import annotations

from tests.e2e.conftest import (
    CHUNK_ERROR_BOUND,
    chunk_problems,
    guard_problems,
    is_chunk,
)


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
    assert guard_problems([], 0, 0, ["E"], ["E"]) == []
    assert guard_problems([], 0, 0, ["E", "E"], ["E"]) == [
        "console errors: {'E': 2}; expected exactly: {'E': 1}"
    ]
    assert guard_problems([], 0, 0, [], ["E"]) == [
        "console errors: {}; expected exactly: {'E': 1}"
    ]
    assert guard_problems([], 0, 0, ["other"], []) == [
        "console errors: {'other': 1}; expected exactly: {}"
    ]


def test_a_named_error_repeated_fails_as_a_loop_would() -> None:
    # #452: no form of the marker excuses a repeat; a loop's errors all count.
    assert guard_problems([], 0, 0, ["E"] * 3, ["E"]) == [
        "console errors: {'E': 3}; expected exactly: {'E': 1}"
    ]
    assert guard_problems([], 0, 0, ["E", "E"], ["E", "E"]) == []


CHUNK = "ChunkLoadError: Loading chunk 746 failed."


def test_without_the_chunk_marker_every_error_is_left_to_the_named_check() -> None:
    assert chunk_problems(None, 0, [CHUNK, "E"]) == ([], [CHUNK, "E"])


def test_an_aborted_chunk_must_be_requested_and_fail_within_the_bound() -> None:
    ok = [CHUNK] * 2 + ["E"]
    assert chunk_problems("async-graph", 1, ok) == ([], ["E"])
    assert chunk_problems("async-graph", 0, ok)[0] == [
        "the async-graph chunk was never requested"
    ]
    assert chunk_problems("async-graph", 1, ["E"])[0] == [
        "the aborted async-graph chunk logged no ChunkLoadError"
    ]
    at_bound = [CHUNK] * CHUNK_ERROR_BOUND
    assert chunk_problems("async-graph", 1, at_bound) == ([], [])
    over = [CHUNK] * (CHUNK_ERROR_BOUND + 1)
    assert chunk_problems("async-graph", 1, over)[0] == [
        f"the aborted async-graph chunk logged {CHUNK_ERROR_BOUND + 1} "
        f"ChunkLoadError lines; at most {CHUNK_ERROR_BOUND} (D089)"
    ]


def test_a_chunk_is_matched_by_its_file_on_the_app_s_host() -> None:
    base = "http://127.0.0.1:8050/_dash-component-suites/dash/dcc"
    assert is_chunk(f"{base}/async-graph.js?v=4.5.0&m=1", "async-graph")
    assert is_chunk(f"{base}/async-graph.v4_5_0m1.js", "async-graph")
    assert not is_chunk(f"{base}/async-graph-extra.js", "async-graph")
    assert not is_chunk(f"{base}/async-slider.js", "async-graph")
    assert not is_chunk(f"{base}/dash_core_components.js", "async-graph")
    assert not is_chunk("https://cdn.example/dash/dcc/async-graph.js", "async-graph")
