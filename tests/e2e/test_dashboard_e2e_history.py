"""Browser tests of the state history's, the state's people per electoral vote page's
(#559) and the candidate page's wide layout (#545, D102): from 76rem a year control
keeps a row of its own at the 42rem measure (``.filter-own-row``) and the dropdown
filters share the row below it (``.filter-row``); below 76rem each page is the one
column it always was. And a state's two pages as one client-side chain (#559, D105):
the section links move between them carrying the year range, with the URL, tab and
marks following, and back and forward; an unserved state or an unknown section reads
as not found. And chart C7 on the state history (#560, D106): readable at phone width
with the year along the bottom, redrawn on a theme switch with no request, and its
title, caption and table left when plotly.js cannot load.

The rules are pinned in ``TestLayoutRules`` (``tests/unit/test_dashboard_theme.py``)
and the markup in each page's ``TestWideLayout``; these check what Chromium draws.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

import explore.app  # noqa: F401  (registers the pages, whose ids the tests read)
from explore import charts, components, labels, state_view
from tests.e2e.dashboard_pages import (
    CANDIDATE_SUCCESS,
    FILTER_MAX_PX,
    FILTER_MIN_PX,
    MEASURE_PX,
    NARROW_DESKTOP,
    PHONE_WIDTHS,
    RESOURCE_ERROR,
    STATE_PER_CAPITA_SUCCESS,
    STATE_SUCCESS,
    UNAVAILABLE,
    WIDE_WIDTHS,
    assert_hover_names_year,
    assert_layout_holds,
    assert_rendered,
    assert_year_ticks_apart,
    rect,
    rects,
    served_years,
    year_ticks,
)
from tests.e2e.test_dashboard_e2e_election import boxes, overlaps, rgb, token

pytestmark = pytest.mark.e2e

STATE_PATH = "/state/GA"
PER_CAPITA_PATH = "/state/GA/per-capita"
CANDIDATE_PATH = "/candidate/andrew-jackson"
#: Each page's success marker and its tables, which must be on it before their scroll
#: is checked, the table its filters narrow first: T4 on the state history, then C7's
#: companion table above its filters (#560); T7 on its per-capita page (#559); T5 on
#: the candidate page.
PAGES = {
    STATE_PATH: (STATE_SUCCESS, ("#state-history", "#state-electors")),
    PER_CAPITA_PATH: (STATE_PER_CAPITA_SUCCESS, ("#state-per-capita",)),
    CANDIDATE_PATH: (CANDIDATE_SUCCESS, ("#candidate-history",)),
}
#: Each page's year control itself: the slider by its id, the pills' radio group.
CONTROLS = {
    STATE_PATH: "#state-years",
    PER_CAPITA_PATH: "#state-per-capita-years",
    CANDIDATE_PATH: "#candidate-year",
}
#: Each page's dropdown filters, in source order: none on the per-capita page.
DROPDOWNS = {
    STATE_PATH: ("#state-candidate", "#state-pv-status"),
    PER_CAPITA_PATH: (),
    CANDIDATE_PATH: ("#candidate-state",),
}


def open_at(page: Page, path: str, width: int) -> str:
    """``path`` rendered from data at ``width``; returns its success marker. On the
    state history it waits for C7 to be drawn too (#560): the chart mounts after
    plotly.js loads, above the filters, so a measurement taken before then can see
    them move by the chart's height."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(path)
    success = PAGES[path][0]
    page.locator(success).wait_for()
    assert page.locator(UNAVAILABLE).count() == 0
    assert page.evaluate("innerWidth") == width
    if path == STATE_PATH:
        page.locator(f"{C7} .main-svg").first.wait_for()
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


@pytest.mark.parametrize("width", WIDE_WIDTHS)
def test_wide_the_per_capita_page_s_year_control_has_its_own_row_above_t7(
    page: Page, width: int
) -> None:
    """The per-capita page's one filter (#559), in the history page's rules (#545):
    the slider's box takes the row, what it holds keeps the measure, and T7 starts
    below it."""
    success = open_at(page, PER_CAPITA_PATH, width)
    own = own_row(page, success)
    box = rect(page, f"{success} .filters")
    assert abs(own["width"] - box["width"]) <= 0.5, (own, box)
    held = rects(page, f"{success} .filters > .filter-own-row > *")
    assert held and all(h["width"] <= MEASURE_PX + 0.5 for h in held), held
    control = rect(page, f"{success} .filter-own-row {CONTROLS[PER_CAPITA_PATH]}")
    assert abs(control["width"] - MEASURE_PX) <= 0.5, control
    table = rect(page, f".table-scroll:has({PAGES[PER_CAPITA_PATH][1][0]})")
    assert table["top"] >= own["bottom"]


@pytest.mark.parametrize("width", [390, NARROW_DESKTOP])
@pytest.mark.parametrize("path", [STATE_PATH, PER_CAPITA_PATH, CANDIDATE_PATH])
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
@pytest.mark.parametrize("path", [STATE_PATH, PER_CAPITA_PATH, CANDIDATE_PATH])
def test_every_width_keeps_order_measure_and_tables(
    page: Page, path: str, width: int
) -> None:
    """At every width: no box is reordered and none has a positive tab index; every
    paragraph, chart caption and party-notes item is within the 42rem measure; the
    page never scrolls sideways; and from about 1280 px no table does either."""
    success = open_at(page, path, width)
    assert_layout_holds(page, success, PAGES[path][1], width)


# --- a state's two pages as one chain (#559, D105) -------------------------------------

#: Each state page's path suffix, success marker and tab title before the site title.
STATE_PAGES = {
    state_view.HISTORY: (STATE_SUCCESS, "GA — state history"),
    state_view.PER_CAPITA: (STATE_PER_CAPITA_SUCCESS, "GA — people per electoral vote"),
}


def assert_state_page(page: Page, section: str, search: str) -> None:
    """GA's page ``section`` with exactly ``search``: its URL, success marker, tab,
    the section mark on it and the link to the other carrying ``search``, and the
    site navigation marking States (#448)."""
    success, title = STATE_PAGES[section]
    expect(page).to_have_url(
        re.compile(re.escape(f"{state_view.path('GA', section)}{search}") + "$")
    )
    page.locator(success).wait_for()
    assert page.locator(UNAVAILABLE).count() == 0
    expect(page).to_have_title(re.compile("^" + re.escape(title) + " — "))
    nav = page.get_by_role("navigation", name=labels.STATE_SECTIONS_LABEL)
    expect(nav).to_have_count(1)
    expect(nav.locator('[aria-current="page"]')).to_have_text(
        state_view.SECTION_TEXT[section]
    )
    (other,) = [s for s in state_view.SECTIONS if s != section]
    link = nav.get_by_role("link")
    expect(link).to_have_count(1)
    expect(link).to_have_text(state_view.SECTION_TEXT[other])
    expect(link).to_have_attribute("href", f"{state_view.path('GA', other)}{search}")
    expect(page.locator(f"#{components.SITE_NAV_ID} [aria-current=true]")).to_have_text(
        labels.NAV_STATES
    )


def test_a_state_s_two_pages_are_one_client_side_chain_keeping_the_year_range(
    page: Page,
) -> None:
    """#559: from a filtered history, the section link opens the per-capita page with
    the year range only (the candidate filter dropped, D105), showing T7 and not T4;
    the link back carries the range; back and forward follow, with no document load
    in between."""
    page.goto(f"{STATE_PATH}?year_from=1860&year_to=1900&candidate=horatio-seymour")
    page.locator(STATE_SUCCESS).wait_for()
    expect(page.locator("#state-per-capita")).to_have_count(0)
    page.evaluate("window.__e2e_mark = 1")
    nav = page.get_by_role("navigation", name=labels.STATE_SECTIONS_LABEL)
    nav.get_by_role("link", name=labels.SECTION_PER_CAPITA).click()
    ranged = "?year_from=1860&year_to=1900"
    assert_state_page(page, state_view.PER_CAPITA, ranged)
    expect(page.locator("#state-history")).to_have_count(0)
    # T7 narrowed to the range: 1860 to 1900 is eleven elections.
    expect(page.locator("#state-per-capita tbody tr")).to_have_count(11)
    nav.get_by_role("link", name=labels.SECTION_STATE_HISTORY).click()
    assert_state_page(page, state_view.HISTORY, ranged)
    page.go_back()
    assert_state_page(page, state_view.PER_CAPITA, ranged)
    page.go_forward()
    assert_state_page(page, state_view.HISTORY, ranged)
    assert page.evaluate("window.__e2e_mark") == 1  # no document load in between


@pytest.mark.parametrize(
    ("path", "not_found"),
    [
        ("/state/ZZ/per-capita", "#state-per-capita-not-found"),
        ("/state/GA/x", "#state-not-found"),
    ],
)
def test_an_unserved_state_or_an_unknown_section_reads_as_not_found(
    page: Page, path: str, not_found: str
) -> None:
    """Reached client-side from the history page, so the document's status (200 or
    404, by whether the roster is cached yet) does not enter: the router's render is
    what is checked. Neither success marker, no section links."""
    page.goto(STATE_PATH)
    page.locator(STATE_SUCCESS).wait_for()
    page.evaluate(
        "path => { window.history.pushState({}, '', path);"
        " window.dispatchEvent(new CustomEvent('_dashprivate_pushstate')); }",
        path,
    )
    page.locator(not_found).wait_for()
    expect(page.get_by_role("heading", level=1)).to_have_text(
        labels.STATE_NOT_FOUND_HEADING
    )
    for marker in (STATE_SUCCESS, STATE_PER_CAPITA_SUCCESS):
        expect(page.locator(marker)).to_have_count(0)
    expect(
        page.get_by_role("navigation", name=labels.STATE_SECTIONS_LABEL)
    ).to_have_count(0)


# --- chart C7 (#560, D106) -------------------------------------------------------

C7 = f"#{charts.dom_id('C7')}"
#: Every text C7 draws: ticks, axis titles and the key's entries.
C7_TEXTS = (
    ".xtick text",
    ".ytick text",
    ".g-xtitle text",
    ".g-ytitle text",
    ".legendtext",
)
#: How long a test waits for a request that should not come (as on the charts page).
SETTLE_MS = 500


def open_c7(page: Page, query: str = "", *, width: int = 390) -> None:
    page.goto(f"{STATE_PATH}{query}")
    assert_rendered(page, STATE_SUCCESS, width=width)
    page.locator(f"{C7} .main-svg").first.wait_for()
    page.locator(f"{C7} .xtick text").first.wait_for()


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_c7_is_readable_at_phone_width(page: Page, width: int) -> None:
    """#560's AC6 (#558, D104): the year along the bottom with its sparse ticks apart,
    every tick, axis title and key entry inside the width and none over another, no bar
    or marker text, no sideways scroll, and a hover naming its year."""
    page.set_viewport_size({"width": width, "height": 844})
    open_c7(page, width=width)
    title = labels.C4_TITLE_STATE.format(state="Georgia")
    expect(page.locator(f"{C7} .chart-title")).to_have_text(title)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert_year_ticks_apart(page, C7)
    expect(page.locator(f"{C7} .bartext")).to_have_count(0)
    expect(page.locator(f"{C7} .textpoint")).to_have_count(0)
    drawn = [
        b
        for part in C7_TEXTS
        for b in boxes(page, f"{C7} {part}")
        if b["w"] > 0 and b["text"]
    ]
    found = [b["text"] for b in drawn]
    assert found.count(labels.C4_VALUE_AXIS) == 1
    assert found.count(labels.LABELS["year"]) == 1
    # Georgia took no part in 1864: the key names that marker.
    assert labels.C4_NO_ELECTORS_TOOK_NO_PART in found
    assert len(drawn) > len(year_ticks()) + 2
    for i, a in enumerate(drawn):
        assert a["x"] >= 0 and a["x"] + a["w"] <= width, a
        for b in drawn[i + 1 :]:
            assert not overlaps(a, b), (a, b)
    bar = f"{C7} .barlayer .point path >> nth=-1"
    assert_hover_names_year(page, C7, bar, served_years()[-1])


@pytest.mark.plotlyjs_fetches(1)
def test_c7_ignores_the_filters(page: Page) -> None:
    """D093(a): the page's filters narrow T4, never C7 or its table."""
    open_c7(page, "?year_from=1900&candidate=jimmy-carter")
    ticks = [b["text"] for b in boxes(page, f"{C7} .xtick text")]
    assert ticks == year_ticks()
    rows = page.locator("#state-electors tbody tr")
    expect(rows).to_have_count(len(served_years()))


@pytest.mark.plotlyjs_fetches(1)
def test_c7_redraws_on_a_theme_switch_with_no_reload_or_request(page: Page) -> None:
    open_c7(page)
    bar = page.locator(f"{C7} .barlayer .point path").first
    light = bar.evaluate("el => getComputedStyle(el).fill")
    assert light == rgb(token(page, "--chart-ec"))
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    expect(bar).not_to_have_css("fill", light)
    assert bar.evaluate("el => getComputedStyle(el).fill") == rgb(
        token(page, "--chart-ec")
    )
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_c7_s_title_caption_and_table_render(
    page: Page,
) -> None:
    page.goto(STATE_PATH)
    assert_rendered(page, STATE_SUCCESS)
    memo = f"window.{charts.PLOTLYJS_MEMO}"
    page.wait_for_function(f"{memo} !== undefined")
    assert page.evaluate(f"async () => await {memo}") is False
    title = labels.C4_TITLE_STATE.format(state="Georgia")
    expect(page.locator(f"{C7} .chart-title")).to_have_text(title)
    expect(page.locator(f"{C7} figcaption")).to_contain_text(labels.C7_FILTERS_NOTE)
    expect(page.locator(f"{C7} figcaption a")).to_have_attribute(
        "href", "#state-electors"
    )
    rows = page.locator("#state-electors tbody tr")
    expect(rows).to_have_count(len(served_years()))
    expect(page.locator("#state-history")).to_be_visible()
