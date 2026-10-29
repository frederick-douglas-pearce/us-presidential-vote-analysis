"""The elections index in a browser, at a phone's width (#321).

The checks #306 ran by hand, in a throwaway script, before #321 filed them: a filter
change writes the URL, settles without a callback loop, survives back and forward and a
pasted link; the column-name list; and the year slider's labels not running together,
the defect that check found. No console error and no off-host request are asserted for
every test by ``conftest._browser_guard``.
"""

from __future__ import annotations

import itertools
import re
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import components, labels
from tests.e2e.dashboard_pages import (
    ELECTIONS_ROWS,
    ELECTIONS_SUCCESS,
    FILTER_OUTPUT,
    FIRST,
    GLOSSARY,
    LAST,
    MARKS,
    PROVENANCE,
    PV,
    PV_BOX,
    PV_FIRST,
    ROUTER_OUTPUT,
    UPDATE_PATH,
    assert_rendered,
    lower_thumb,
    row_years,
    search,
    years_shown,
)

pytestmark = pytest.mark.e2e

#: T1's columns, as pages/elections.py's ``FIELDS`` lists them.
FIELDS = ("year", "candidate_count", "has_popular_vote")

#: How long a filter change is given to fire anything further after it settled. The
#: one deliberate wait in the suite: a loop is caught by counting, not by timing.
SETTLE_MS = 1000


def url_pattern(query: str) -> re.Pattern[str]:
    return re.compile(re.escape(f"/elections{query}") + "$")


def check_pv(page: Page) -> None:
    page.locator(PV).get_by_role("option").click()


def assert_view(page: Page, *, year_from: int = FIRST, pv_only: bool = False) -> None:
    """The page shows exactly this view: URL, rows and both controls."""
    expect(page).to_have_url(url_pattern(search(year_from=year_from, pv_only=pv_only)))
    assert_rendered(page, ELECTIONS_SUCCESS)
    expected = years_shown(year_from=year_from, pv_only=pv_only)
    expect(page.locator(ELECTIONS_ROWS)).to_have_count(len(expected))
    assert row_years(page) == expected
    expect(lower_thumb(page)).to_have_attribute("aria-valuenow", str(year_from))
    if pv_only:
        expect(page.locator(PV_BOX)).to_be_checked()
    else:
        expect(page.locator(PV_BOX)).not_to_be_checked()


def test_the_unfiltered_index_lists_every_election(page: Page) -> None:
    page.goto("/elections")
    assert_view(page)
    expect(page.locator(f"{PROVENANCE} li")).to_have_count(len(components.SOURCES))


def test_the_column_name_list_names_each_column(page: Page) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    glossary = page.locator(GLOSSARY)
    glossary.locator("summary").click()
    expect(glossary.locator("dt")).to_have_text([labels.LABELS[f] for f in FIELDS])
    expect(glossary.locator("dd")).to_have_text(list(FIELDS))


def test_a_filter_change_writes_the_url_and_narrows_the_rows(page: Page) -> None:
    page.goto("/elections")
    assert_view(page)
    # One key per interaction: the router re-renders the slider, so it is located
    # afresh, and a held focus would not survive the first step. ArrowRight is one
    # step (a year); Dash 4's slider ignores End on the lower handle.
    lower_thumb(page).press("ArrowRight")
    assert_view(page, year_from=FIRST + 1)
    check_pv(page)
    assert_view(page, year_from=FIRST + 1, pv_only=True)


def test_one_filter_change_settles_without_a_callback_loop(page: Page) -> None:
    page.goto("/elections")
    assert_view(page)
    before = page.evaluate("history.length")
    outputs: list[str] = []

    def on_request(request: Request) -> None:
        if request.method == "POST" and urlsplit(request.url).path == UPDATE_PATH:
            body: Any = request.post_data_json
            outputs.append(body["output"])

    page.on("request", on_request)
    check_pv(page)
    assert_view(page, pv_only=True)
    page.wait_for_timeout(SETTLE_MS)
    assert outputs.count(FILTER_OUTPUT) == 1, outputs
    assert outputs.count(ROUTER_OUTPUT) == 1, outputs
    assert page.evaluate("history.length") == before + 1


def test_back_and_forward_restore_each_view(page: Page) -> None:
    page.goto("/elections")
    assert_view(page)
    check_pv(page)
    assert_view(page, pv_only=True)
    page.go_back()
    assert_view(page)
    page.go_forward()
    assert_view(page, pv_only=True)


def test_a_pasted_filtered_url_opens_that_view(page: Page) -> None:
    year_from = PV_FIRST
    page.goto(f"/elections{search(year_from=year_from, pv_only=True)}")
    assert_view(page, year_from=year_from, pv_only=True)


def test_the_year_slider_labels_do_not_overlap(page: Page) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    marks = page.locator(MARKS)
    # The count first, so a selector matching nothing cannot pass the overlap check.
    expect(marks).to_have_count(len(components.year_marks(FIRST, LAST)))
    boxes = [box for box in (m.bounding_box() for m in marks.all()) if box is not None]
    assert len(boxes) == marks.count()
    for a, b in itertools.combinations(boxes, 2):
        apart = (
            a["x"] + a["width"] <= b["x"]
            or b["x"] + b["width"] <= a["x"]
            or a["y"] + a["height"] <= b["y"]
            or b["y"] + b["height"] <= a["y"]
        )
        assert apart, f"slider labels overlap: {a} and {b}"
