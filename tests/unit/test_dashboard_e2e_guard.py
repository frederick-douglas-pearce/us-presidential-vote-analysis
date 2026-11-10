"""The e2e suite's browser guard, as logic (#432's acceptance gate): its checks run
after every browser test, so a guard weakened to pass everything would leave every
test green. ``guard_problems`` and ``chunk_problems`` in ``tests/e2e/conftest.py`` are
the whole of what the fixture asserts; these drive them without a browser, and drive
``assert_chunk_failure_stops`` (``tests/e2e/dashboard_pages.py``) on a fake page.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import (
    CHUNK_ERROR_BOUND,
    chart_page_patterns,
    chunk_problems,
    derived_fetch_problems,
    guard_problems,
    is_chunk,
    page_pattern,
)
from tests.e2e.dashboard_pages import (
    CHUNK_BARRIER,
    CHUNK_ERROR_PREFIX,
    CHUNK_QUIET_MS,
    RESOURCE_ERROR,
    assert_chunk_failure_stops,
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


def test_without_a_declared_count_the_exact_check_is_skipped() -> None:
    # #433: the derived bound below holds such a test's fetches instead.
    assert guard_problems([], 0, None, [], []) == []
    assert guard_problems([], 3, None, [], []) == []


ELECTION = page_pattern("/election/<year>")


def test_a_page_template_matches_its_paths() -> None:
    assert ELECTION.fullmatch("/election/2016")
    assert ELECTION.fullmatch("/election/1824/x")  # Dash's variable is greedy
    assert not ELECTION.fullmatch("/elections")
    assert not ELECTION.fullmatch("/election/")
    assert not ELECTION.fullmatch("/xelection/2016")
    assert page_pattern("/a.b/<v>").fullmatch("/a.b/1")
    assert not page_pattern("/a.b/<v>").fullmatch("/aXb/1")


def test_the_registry_derives_the_chart_pages() -> None:
    from explore import charts

    live = [row.page for row in charts.CHARTS.values() if not row.retired]
    assert live  # the premise: C1 (#433)
    assert [p.pattern for p in chart_page_patterns()] == [
        page_pattern(page).pattern for page in live
    ]
    assert any(p.fullmatch("/election/2016") for p in chart_page_patterns())


def test_a_retired_chart_s_page_is_not_a_chart_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 1 (GE5): only a live row's page counts."""
    from explore import charts

    monkeypatch.setattr(
        charts,
        "CHARTS",
        {
            "C1": charts.Chart("/live/<v>", "t"),
            "C2": charts.Chart("/retired/<v>", "t", retired=True),
        },
    )
    patterns = chart_page_patterns()
    assert [p.pattern for p in patterns] == [page_pattern("/live/<v>").pattern]
    assert derived_fetch_problems([(1, "/retired/1")], patterns) == [
        "plotly.js fetched by '/retired/1', which renders no chart"
    ]


def test_the_derived_bound() -> None:
    """#433, D091: at most one fetch per document, and only from a chart page."""
    assert derived_fetch_problems([], [ELECTION]) == []
    assert derived_fetch_problems([(1, "/election/2016")], [ELECTION]) == []
    # One per document: a reload or a new document may fetch again.
    assert (
        derived_fetch_problems([(1, "/election/2016"), (2, "/election/1824")], [ELECTION])
        == []
    )
    assert derived_fetch_problems(
        [(1, "/election/2016"), (1, "/election/2024")], [ELECTION]
    ) == ["plotly.js fetched twice by one document ('/election/2024')"]
    # A page with no chart fetches nothing.
    assert derived_fetch_problems([(1, "/elections")], [ELECTION]) == [
        "plotly.js fetched by '/elections', which renders no chart"
    ]
    assert derived_fetch_problems([(1, "/election/2016")], []) == [
        "plotly.js fetched by '/election/2016', which renders no chart"
    ]


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
    assert chunk_problems(None, 0, [CHUNK, RESOURCE_ERROR, "E"]) == (
        [],
        [CHUNK, RESOURCE_ERROR, "E"],
    )


def test_an_aborted_chunk_must_be_requested_and_fail_within_the_bound() -> None:
    ok = [CHUNK, CHUNK, RESOURCE_ERROR, "E"]
    assert chunk_problems("async-graph", 1, ok) == ([], ["E"])
    assert chunk_problems("async-graph", 0, [CHUNK])[0] == [
        "the async-graph chunk was never requested"
    ]
    assert chunk_problems("async-graph", 1, [RESOURCE_ERROR])[0] == [
        "the aborted async-graph chunk logged no ChunkLoadError"
    ]
    at_bound = [CHUNK] * CHUNK_ERROR_BOUND + [RESOURCE_ERROR]
    assert chunk_problems("async-graph", 1, at_bound) == ([], [])
    over = [CHUNK] * (CHUNK_ERROR_BOUND + 1) + [RESOURCE_ERROR]
    assert chunk_problems("async-graph", 1, over)[0] == [
        f"the aborted async-graph chunk logged {CHUNK_ERROR_BOUND + 1} "
        f"ChunkLoadError lines; at most {CHUNK_ERROR_BOUND} (D089)"
    ]


def test_each_aborted_request_explains_one_resource_error_and_no_more() -> None:
    # A bounded retry: two requests, two resource errors, passes.
    retry = [CHUNK, CHUNK, RESOURCE_ERROR, RESOURCE_ERROR]
    assert chunk_problems("async-graph", 2, retry) == ([], [])
    # A resource error no aborted request explains is left for the named check.
    assert chunk_problems("async-graph", 1, [CHUNK, RESOURCE_ERROR, RESOURCE_ERROR]) == (
        [],
        [RESOURCE_ERROR],
    )
    # An aborted request whose resource error never came is a problem.
    assert chunk_problems("async-graph", 2, [CHUNK, RESOURCE_ERROR])[0] == [
        "2 aborted async-graph requests but 1 resource errors"
    ]
    many = [CHUNK] + [RESOURCE_ERROR] * (CHUNK_ERROR_BOUND + 1)
    assert chunk_problems("async-graph", CHUNK_ERROR_BOUND + 1, many)[0] == [
        f"the async-graph chunk was requested {CHUNK_ERROR_BOUND + 1} times; "
        f"at most {CHUNK_ERROR_BOUND} (D089)"
    ]


def test_a_chunk_is_matched_by_its_file_on_the_app_s_host() -> None:
    base = "http://127.0.0.1:8050/_dash-component-suites/dash/dcc"
    assert is_chunk(f"{base}/async-graph.js?v=4.5.0&m=1", "async-graph")
    assert is_chunk(f"{base}/async-graph.v4_5_0m1.js", "async-graph")
    assert not is_chunk(f"{base}/async-graph-extra.js", "async-graph")
    assert not is_chunk(f"{base}/async-slider.js", "async-graph")
    assert not is_chunk(f"{base}/dash_core_components.js", "async-graph")
    assert not is_chunk("https://cdn.example/dash/dcc/async-graph.js", "async-graph")
    # Each part of the match is load-bearing (#456's acceptance gate): a file of the
    # same stem outside dcc, a source map, and a file named by its webpack id.
    html = "http://127.0.0.1:8050/_dash-component-suites/dash/html"
    assert not is_chunk(f"{html}/async-graph.js", "async-graph")
    assert not is_chunk(f"{base}/async-graph.js.map", "async-graph")
    assert not is_chunk(f"{base}/746.js", "async-graph")


LINE = f"{CHUNK_ERROR_PREFIX} 746 failed."


class FakeConsolePage:
    """Stands in for a Playwright page in ``assert_chunk_failure_stops``: a clock that
    only ``wait_for_timeout`` moves, ``ChunkLoadError`` lines arriving at scheduled
    times (ms), and ``held`` lines logged before the barrier but delivered only with
    it, as a console event in flight would be."""

    def __init__(self, seen: list[str], arrivals: list[int], held: int = 0) -> None:
        self.seen = seen
        self.arrivals = sorted(arrivals)
        self.held = held
        self.now = 0
        self.barriers = 0

    def wait_for_timeout(self, ms: int) -> None:
        self.now += ms
        while self.arrivals and self.arrivals[0] <= self.now:
            self.arrivals.pop(0)
            self.seen.append(LINE)

    @contextlib.contextmanager
    def expect_console_message(self, predicate: Callable[[Any], bool]) -> Iterator[None]:
        yield
        assert predicate(SimpleNamespace(text=CHUNK_BARRIER))
        self.barriers += 1
        self.seen.extend([LINE] * self.held)

    def evaluate(self, script: str) -> None:
        assert CHUNK_BARRIER in script


def run_stops(arrivals: list[int], held: int = 0) -> FakeConsolePage:
    seen: list[str] = []
    fake = FakeConsolePage(seen, arrivals, held)
    assert_chunk_failure_stops(cast(Page, fake), seen)
    return fake


def test_a_failure_that_stops_passes_after_a_full_quiet_window_and_a_barrier() -> None:
    fake = run_stops([100, 150])
    assert fake.now >= 150 + CHUNK_QUIET_MS
    assert fake.barriers == 1


def test_a_late_line_restarts_the_quiet_window() -> None:
    fake = run_stops([100, 1500])
    assert fake.now >= 1500 + CHUNK_QUIET_MS


def test_a_failure_that_keeps_logging_fails() -> None:
    with pytest.raises(AssertionError, match="kept coming for"):
        run_stops(list(range(100, 60_000, 500)))


def test_a_line_delivered_only_with_the_barrier_fails() -> None:
    with pytest.raises(AssertionError, match="kept coming: 1, then 2"):
        run_stops([100], held=1)


def test_a_failure_that_logs_nothing_fails() -> None:
    with pytest.raises(AssertionError, match="logged no ChunkLoadError"):
        run_stops([])
