"""The elections index in a browser, at a phone's width (#321); since #562 the list of
elections alone, with the section links to C2's page and C4 and C5's.

The checks #306 ran by hand, in a throwaway script, before #321 filed them: a filter
change writes the URL, settles without a callback loop, survives back and forward and a
pasted link; the column-name list; and the year slider's labels not running together,
the defect that check found. No console error and no off-host request are asserted for
every test by ``conftest._browser_guard``.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import components, labels
from tests.e2e.dashboard_pages import (
    ELECTIONS_ROWS,
    ELECTIONS_SECTIONS,
    ELECTIONS_SUCCESS,
    FIELDS,
    FILTER_OUTPUT,
    FIRST,
    GLOSSARY,
    LAST,
    MAJORITY_SUCCESS,
    MARKS,
    NARROW_DESKTOP,
    OVER_TIME_SUCCESS,
    PHONE_WIDTHS,
    PROVENANCE,
    PV,
    PV_BOX,
    PV_FIRST,
    ROUTER_OUTPUT,
    UNAVAILABLE,
    UPDATE_PATH,
    WIDE_WIDTHS,
    YEARS,
    assert_chunk_failure_stops,
    assert_layout_holds,
    assert_rendered,
    lower_thumb,
    rect,
    rects,
    row_years,
    search,
    served_years,
    watch_chunk_errors,
    years_shown,
)
from tests.e2e.test_dashboard_e2e_election import boxes, overlaps, rgb, token

pytestmark = pytest.mark.e2e

#: How long a filter change is given to fire anything further after it settled. The
#: one deliberate wait in the suite: a loop is caught by counting, not by timing.
SETTLE_MS = 1000

#: The least horizontal space between two slider labels on one line: labels that touch
#: read as one run-together number, the defect #306's check found.
MIN_LABEL_GAP_PX = 4


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
    expect(glossary).to_have_attribute("open", "")
    expect(glossary.locator("dt").first).to_be_visible()
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
    # The whole list, so a loop on any output, not only these two, is caught.
    assert Counter(outputs) == Counter([FILTER_OUTPUT, ROUTER_OUTPUT]), outputs
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


def test_the_year_slider_labels_keep_apart(page: Page) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    marks = page.locator(MARKS)
    # The count first, so a selector matching nothing cannot pass the overlap check.
    expect(marks).to_have_count(len(components.year_marks(FIRST, LAST)))
    boxes = [box for box in (m.bounding_box() for m in marks.all()) if box is not None]
    assert len(boxes) == marks.count()
    for a, b in itertools.combinations(boxes, 2):
        apart = (
            a["x"] + a["width"] + MIN_LABEL_GAP_PX <= b["x"]
            or b["x"] + b["width"] + MIN_LABEL_GAP_PX <= a["x"]
            or a["y"] + a["height"] <= b["y"]
            or b["y"] + b["height"] <= a["y"]
        )
        assert apart, f"slider labels closer than {MIN_LABEL_GAP_PX}px: {a} and {b}"


@pytest.mark.aborted_chunk("async-slider")
def test_a_failed_slider_chunk_stops_logging(page: Page) -> None:
    """#456, D089: with dcc's slider chunk refused, the elections index logs a bounded
    number of ``ChunkLoadError`` lines and stops (Dash 4.4.1 logged them without end),
    and its table still renders."""
    seen = watch_chunk_errors(page)
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_chunk_failure_stops(page, seen)


# --- the headline metrics (#437, D097) ------------------------------------------------

METRICS = "#elections-metrics"
METRIC_TEXTS = f"{METRICS} p, {METRICS} dt, {METRICS} dd"


#: Each view the legibility test lays out: the default, and a range before the
#: popular-vote years, whose popular-vote value is the longest value text the block
#: shows.
METRIC_VIEWS = {
    "": (
        "Showing 51 of 51 elections",
        "41.2 percentage points, over 51 elections (1824–2024)",
        "5.7 percentage points, over 13 elections (1976–2024)",
        2,  # the margin note and the different-elections note
    ),
    "?year_to=1900": (
        "Showing 20 of 51 elections",
        "33.9 percentage points, over 20 elections (1824–1900)",
        "No average: this dataset's popular-vote figures cover 1976–2024, not the "
        "years shown",
        1,  # the margin note only
    ),
}


@pytest.mark.parametrize("view", list(METRIC_VIEWS))
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_metrics_are_legible_at_390_px_in_both_themes(
    page: Page, theme: str, view: str
) -> None:
    """AC Rendering: the count, both averages and their notes inside 390 px with no
    sideways scroll and none over another, in each theme, in the text colors the
    theme's tokens name (each figure is labeled text, so nothing rests on color); for
    the default view and the one with the longest value text."""
    count, ec, pv, notes = METRIC_VIEWS[view]
    page.goto(f"/elections{view}")
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.locator(f"#{components.THEME_BUTTON_IDS[theme]}").click()
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    expect(page.locator("#elections-shown")).to_have_text(count)
    expect(page.locator(f"{METRICS} dt")).to_have_text(
        [labels.METRIC_LABELS["ec_margin_mean"], labels.METRIC_LABELS["pv_margin_mean"]]
    )
    expect(page.locator("#elections-ec-margin-mean")).to_have_text(ec)
    expect(page.locator("#elections-pv-margin-mean")).to_have_text(pv)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    shown = boxes(page, METRIC_TEXTS)
    # The count line, two terms, two values, and the notes.
    assert len(shown) == 1 + 2 + 2 + notes
    for i, a in enumerate(shown):
        assert a["x"] >= 0 and a["x"] + a["w"] <= 390, a
        for b in shown[i + 1 :]:
            assert not overlaps(a, b), (a, b)
    dd = page.locator("#elections-pv-margin-mean")
    assert dd.evaluate("el => getComputedStyle(el).color") == rgb(token(page, "--text"))
    note = page.locator(f"{METRICS} p.note").first
    assert note.evaluate("el => getComputedStyle(el).color") == rgb(
        token(page, "--text-secondary")
    )


def test_a_filter_change_updates_the_metrics(page: Page) -> None:
    page.goto("/elections")
    assert_view(page)
    check_pv(page)
    assert_view(page, pv_only=True)
    expect(page.locator("#elections-ec-margin-mean")).to_have_text(
        "33.5 percentage points, over 13 elections (1976–2024)"
    )
    expect(page.locator("#elections-shown")).to_have_text(
        f"Showing 13 of {len(served_years())} elections"
    )
    # Both averages now cover the same elections: only the margin note remains.
    expect(page.locator(f"{METRICS} p.note")).to_have_text([labels.MARGIN_NOTE])


# --- the wide layout (#553, D102, D103) ----------------------------------------------

LIST_PAIR = "#elections-list-pair"
LIST_COLUMNS = f"{LIST_PAIR} > div"
#: The page's one table since #562: T1.
TABLES = ("#elections-table",)


def open_at(page: Page, width: int) -> None:
    """``/elections`` at ``width``."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("/elections")
    page.locator(ELECTIONS_SUCCESS).wait_for()
    assert page.locator(UNAVAILABLE).count() == 0
    assert page.evaluate("innerWidth") == width


def side_by_side(left: dict[str, float], right: dict[str, float]) -> None:
    """Two equal columns, the first to the left of the second, their tops level."""
    assert left["right"] < right["left"], (left, right)
    assert abs(left["width"] - right["width"]) <= 1, (left, right)
    assert abs(left["top"] - right["top"]) <= 1, (left, right)


@pytest.mark.parametrize("width", WIDE_WIDTHS)
def test_wide_the_list_s_filters_sit_beside_the_count_and_averages(
    page: Page, width: int
) -> None:
    open_at(page, width)
    left, right = rects(page, LIST_COLUMNS)
    side_by_side(left, right)
    # The slider and the checkbox in the left column, the metrics in the right.
    for held, column in ((YEARS, left), (PV, left), ("#elections-metrics", right)):
        box = rect(page, held)
        assert column["left"] - 0.5 <= box["left"], (held, box, column)
        assert box["right"] <= column["right"] + 0.5, (held, box, column)
    # Each column's first child starts at the column's top, so the filters and the
    # count line start level: the margin reset reaches them (#553's review, r1.cr.1).
    firsts = rects(page, f"{LIST_COLUMNS} > :first-child")
    for first, column in zip(firsts, (left, right), strict=True):
        assert abs(first["top"] - column["top"]) <= 0.5, (first, column)
    # The visible content itself, whatever wraps it: the "Years" label and the count.
    label, count = rect(page, f"{LIST_PAIR} .filters .label"), rect(page, ".count")
    assert abs(label["top"] - count["top"]) <= 0.5, (label, count)
    # T1 below both columns.
    t1 = rect(page, ".table-scroll:has(#elections-table)")
    assert t1["top"] >= max(left["bottom"], right["bottom"]), (t1, left, right)
    assert abs(t1["left"] - left["left"]) <= 1, (t1, left)
    print(
        f"#553 list pair at {width} px: filters column"
        f" {left['bottom'] - left['top']:.0f} px, metrics column"
        f" {right['bottom'] - right['top']:.0f} px tall"
    )


@pytest.mark.parametrize("width", [NARROW_DESKTOP, 390])
def test_narrow_the_list_pair_stacks_as_before(page: Page, width: int) -> None:
    open_at(page, width)
    left, right = rects(page, LIST_COLUMNS)
    assert right["top"] >= left["bottom"] - 0.5, (width, left, right)
    assert abs(left["left"] - right["left"]) <= 0.5, (width, left, right)
    # The filters above the count, as the one column always had.
    assert rect(page, PV)["bottom"] <= rect(page, "#elections-metrics")["top"] + 0.5


@pytest.mark.parametrize("width", [*WIDE_WIDTHS, NARROW_DESKTOP, *PHONE_WIDTHS])
def test_every_width_keeps_order_measure_and_tables(page: Page, width: int) -> None:
    open_at(page, width)
    assert_layout_holds(page, ELECTIONS_SUCCESS, TABLES, width)


# --- the section links between the three elections pages (#562) ---------------------


@pytest.mark.plotlyjs_fetches(1)
def test_the_section_links_chain_client_side_and_back(page: Page) -> None:
    """D092's pattern: each link a client-side navigation, the current page marked,
    back and forward restoring each page."""
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.evaluate("window.__e2e_mark = 1")
    nav = page.locator(ELECTIONS_SECTIONS)
    expect(nav.locator("[aria-current=page]")).to_have_text(
        labels.SECTION_ELECTIONS_LIST
    )
    for name, path, success in (
        (labels.SECTION_MAJORITY, "/elections/majority", MAJORITY_SUCCESS),
        (labels.SECTION_OVER_TIME, "/elections/over-time", OVER_TIME_SUCCESS),
        (labels.SECTION_ELECTIONS_LIST, "/elections", ELECTIONS_SUCCESS),
    ):
        page.locator(ELECTIONS_SECTIONS).get_by_role("link", name=name).click()
        expect(page).to_have_url(re.compile(re.escape(path) + "$"))
        assert_rendered(page, success)
        expect(page.locator(f"{ELECTIONS_SECTIONS} [aria-current=page]")).to_have_text(
            name
        )
    page.go_back()
    expect(page).to_have_url(re.compile(r"/elections/over-time$"))
    assert_rendered(page, OVER_TIME_SUCCESS)
    assert page.evaluate("window.__e2e_mark") == 1  # no document load


def test_an_old_state_link_lands_on_the_state_page(page: Page) -> None:
    """AC3 in a browser: a document load of ``/elections?state=GA`` follows the 302
    to ``/state/GA`` once the roster is cached."""
    page.goto("/states")  # the picker reads the roster, as the index judges by
    page.locator("#states").wait_for()
    page.goto("/elections?state=GA")
    expect(page).to_have_url(re.compile(r"/state/GA$"))


# --- the year filters across the three elections pages (#596, D110) --------------------


@pytest.mark.plotlyjs_fetches(1)
def test_the_section_links_carry_the_filters_and_a_change_stays_on_the_page(
    page: Page,
) -> None:
    """#596 (D110): from a filtered list, each section link opens the other page with
    the same filters (client-side, no document load); a filter change there writes
    that page's URL with one callback and the router's render, never the list's
    (the architect's check of the shared ids), and back restores the view."""
    page.goto("/elections")
    assert_view(page)
    check_pv(page)
    assert_view(page, pv_only=True)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(ELECTIONS_SECTIONS).get_by_role(
        "link", name=labels.SECTION_MAJORITY
    ).click()
    expect(page).to_have_url(re.compile(r"/elections/majority\?pv=1$"))
    assert_rendered(page, MAJORITY_SUCCESS)
    expect(page.locator(f"{PV} input")).to_be_checked()
    outputs: list[str] = []

    def on_request(request: Request) -> None:
        if request.method == "POST" and urlsplit(request.url).path == UPDATE_PATH:
            body: Any = request.post_data_json
            outputs.append(body["output"])

    page.on("request", on_request)
    lower_thumb(page).press("ArrowRight")
    expect(page).to_have_url(
        re.compile(rf"/elections/majority\?pv=1&year_from={FIRST + 1}$")
    )
    assert_rendered(page, MAJORITY_SUCCESS)
    page.wait_for_timeout(SETTLE_MS)
    assert Counter(outputs) == Counter([FILTER_OUTPUT, ROUTER_OUTPUT]), outputs
    page.locator(ELECTIONS_SECTIONS).get_by_role(
        "link", name=labels.SECTION_OVER_TIME
    ).click()
    expect(page).to_have_url(
        re.compile(rf"/elections/over-time\?pv=1&year_from={FIRST + 1}$")
    )
    assert_rendered(page, OVER_TIME_SUCCESS)
    page.go_back()
    expect(page).to_have_url(
        re.compile(rf"/elections/majority\?pv=1&year_from={FIRST + 1}$")
    )
    page.go_back()
    expect(page).to_have_url(re.compile(r"/elections/majority\?pv=1$"))
    expect(page.locator(f"{PV} input")).to_be_checked()
    assert page.evaluate("window.__e2e_mark") == 1  # no document load
