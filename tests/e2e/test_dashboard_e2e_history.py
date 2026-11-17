"""Browser tests of the state history's and the candidate page's wide layout (#545,
D102): from 76rem a year control keeps a row of its own at the 42rem measure
(``.filter-own-row``) and the dropdown filters share the row below it
(``.filter-row``); below 76rem each page is the one column it always was.

The rules are pinned in ``TestLayoutRules`` (``tests/unit/test_dashboard_theme.py``)
and the markup in each page's ``TestWideLayout``; these check what Chromium draws.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e.dashboard_pages import (
    CANDIDATE_SUCCESS,
    FILTER_MAX_PX,
    FILTER_MIN_PX,
    MEASURE_PX,
    NARROW_DESKTOP,
    STATE_SUCCESS,
    UNAVAILABLE,
    WIDE_WIDTHS,
    rect,
    rects,
)

pytestmark = pytest.mark.e2e

STATE_PATH = "/state/GA"
CANDIDATE_PATH = "/candidate/andrew-jackson"
#: Each page's success marker and its tables, which must be on it before their scroll
#: is checked: T4 and T7 on the state page, T5 on the candidate page.
PAGES = {
    STATE_PATH: (STATE_SUCCESS, ("#state-history", "#state-per-capita")),
    CANDIDATE_PATH: (CANDIDATE_SUCCESS, ("#candidate-history",)),
}
#: Each page's year control itself: the slider by its id, the pills' radio group.
CONTROLS = {STATE_PATH: "#state-years", CANDIDATE_PATH: "#candidate-year"}
#: Each page's dropdown filters, in source order.
DROPDOWNS = {
    STATE_PATH: ("#state-candidate", "#state-pv-status"),
    CANDIDATE_PATH: ("#candidate-state",),
}


def open_at(page: Page, path: str, width: int) -> str:
    """``path`` rendered from data at ``width``; returns its success marker."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(path)
    success = PAGES[path][0]
    page.locator(success).wait_for()
    assert page.locator(UNAVAILABLE).count() == 0
    assert page.evaluate("innerWidth") == width
    return success


def own_row(page: Page, success: str) -> dict[str, float]:
    return rect(page, f"{success} .filters > .filter-own-row")


def dropdown_filters(page: Page, path: str) -> list[dict[str, float]]:
    """The box of each dropdown filter, in source order, located by its control."""
    success = PAGES[path][0]
    return [
        rect(page, f"{success} .filters > .filter:has({control})")
        for control in DROPDOWNS[path]
    ]


@pytest.mark.parametrize("width", WIDE_WIDTHS)
@pytest.mark.parametrize("path", [STATE_PATH, CANDIDATE_PATH])
def test_wide_the_year_control_has_its_own_row_and_the_dropdowns_follow(
    page: Page, path: str, width: int
) -> None:
    success = open_at(page, path, width)
    own = own_row(page, success)
    box = rect(page, f"{success} .filters")
    # The box takes the whole row, and everything it holds keeps the measure.
    assert abs(own["width"] - box["width"]) <= 0.5, (own, box)
    held = rects(page, f"{success} .filters > .filter-own-row > *")
    assert held and all(h["width"] <= MEASURE_PX + 0.5 for h in held), held
    # The control itself reaches the measure; its label would not prove it, since the
    # state page's label is a block and always the measure wide.
    control = rect(page, f"{success} .filter-own-row {CONTROLS[path]}")
    assert abs(control["width"] - MEASURE_PX) <= 0.5, control
    found = dropdown_filters(page, path)
    # One row below the year control, left to right in source order.
    assert {round(f["top"]) for f in found} == {round(found[0]["top"])}, found
    assert found[0]["top"] >= own["bottom"] - 0.5, (own, found)
    assert abs(found[0]["left"] - own["left"]) <= 0.5, (own, found)
    for a, b in zip(found, found[1:], strict=False):
        assert a["right"] < b["left"], found
    for f in found:
        assert FILTER_MIN_PX - 0.5 <= f["width"] <= FILTER_MAX_PX + 0.5, found
    # The first table starts below the filters.
    table = rect(page, f".table-scroll:has({PAGES[path][1][0]})")
    assert table["top"] >= max(f["bottom"] for f in found)


@pytest.mark.parametrize("width", [390, NARROW_DESKTOP])
@pytest.mark.parametrize("path", [STATE_PATH, CANDIDATE_PATH])
def test_narrow_the_filters_stack_as_before(
    page: Page, path: str, width: int
) -> None:
    success = open_at(page, path, width)
    box = rect(page, f"{success} .filters")
    found = rects(page, f"{success} .filters > .filter")
    assert len(found) == 1 + len(DROPDOWNS[path])
    for a, b in zip(found, found[1:], strict=False):
        assert b["top"] >= a["bottom"] - 0.5, (width, found)
        assert abs(a["left"] - b["left"]) <= 0.5, (width, found)
    # Each dropdown fills the filters box, as it did before the filter row.
    for f in dropdown_filters(page, path):
        assert abs(f["width"] - box["width"]) <= 0.5, (width, f, box)


@pytest.mark.parametrize("width", [*WIDE_WIDTHS, NARROW_DESKTOP, 390])
@pytest.mark.parametrize("path", [STATE_PATH, CANDIDATE_PATH])
def test_every_width_keeps_order_measure_and_tables(
    page: Page, path: str, width: int
) -> None:
    """At every width: no box is reordered and none has a positive tab index; every
    paragraph, chart caption and party-notes item is within the 42rem measure; the
    page never scrolls sideways; and from about 1280 px no table does either."""
    success = open_at(page, path, width)
    tables = PAGES[path][1]
    found = page.evaluate(
        f"""() => {{
            const root = document.querySelector("{success}");
            const all = [...root.querySelectorAll("*")];
            const reordered = all.filter(el => {{
                const s = getComputedStyle(el);
                return s.order !== "0" || /reverse/.test(s.flexDirection)
                    || s.gridRowStart !== "auto" || s.gridColumnStart !== "auto";
            }}).map(el => el.id || el.className || el.tagName);
            const tabbed = all.filter(el => el.tabIndex > 0)
                .map(el => el.id || el.tagName);
            const text = [...document.querySelectorAll(
                "main p, main figcaption, main .party-notes li")];
            const wide = text
                .filter(el => el.getBoundingClientRect().width > {MEASURE_PX} + 0.5)
                .map(el => el.tagName + ": " + el.textContent.slice(0, 40));
            const tables = {list(tables)!r}.map(id => {{
                const box = document.querySelector(`.table-scroll:has(${{id}})`);
                return box && box.scrollWidth <= box.clientWidth + 1;
            }});
            return {{reordered, tabbed, wide, texts: text.length, tables,
                     page: document.documentElement.scrollWidth <= innerWidth}};
        }}"""
    )
    assert found["reordered"] == [], found
    assert found["tabbed"] == [], found
    assert found["texts"] > 0 and found["wide"] == [], found
    assert found["page"], found
    assert None not in found["tables"], found  # every table is there
    if width >= 1280:
        assert all(found["tables"]), found
