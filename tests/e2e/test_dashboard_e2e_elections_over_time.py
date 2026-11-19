"""The electors appointed and total popular vote page, ``/elections/over-time``, in a
browser (#562): charts C4 and C5 (#436, D100) and their companion table, all states only
since #562 (D107). No console error and no off-host request are asserted for every test
by ``conftest._browser_guard``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect

from explore import charts, components, labels
from tests.e2e.dashboard_pages import (
    C4,
    C5,
    NARROW_DESKTOP,
    OVER_TIME_ROWS,
    OVER_TIME_SUCCESS,
    PHONE_WIDTHS,
    PV_FIRST,
    RESOURCE_ERROR,
    UNAVAILABLE,
    WIDE_BREAKPOINT_PX,
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

#: How long a filter change is given to fire anything further after it settled. The

#: How long a redraw is given to fire anything further after it settled.
SETTLE_MS = 1000

# --- charts C4 and C5 (#436, D100) ---------------------------------------------------

#: Every text C4 or C5 draws that a reader reads (#558, D104): year ticks, value ticks,
#: both axes' titles, the band's labels and the key's entries; no bar or marker draws
#: text.
OVER_TIME_TEXTS = (
    ".xtick text",
    ".ytick text",
    ".annotation-text",
    ".g-xtitle text",
    ".g-ytitle text",
    ".legendtext",
)


def open_over_time(page: Page, query: str = "", *, width: int = 390) -> None:
    page.goto(f"/elections/over-time{query}")
    assert_rendered(page, OVER_TIME_SUCCESS, width=width)
    for chart in (C4, C5):
        page.locator(f"{chart} .main-svg").first.wait_for()
        page.locator(f"{chart} .xtick text").first.wait_for()


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_c4_and_c5_are_readable_at_phone_width(page: Page, width: int) -> None:
    """AC Phone width (#558, D104): year along the bottom with its sparse ticks apart,
    every tick, axis title, band label and key entry inside the width, none over
    another, no bar or marker text, and no sideways scroll, and a hover on each chart
    naming its year."""
    page.set_viewport_size({"width": width, "height": 844})
    open_over_time(page, width=width)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for chart in (C4, C5):
        assert_year_ticks_apart(page, chart)
        expect(page.locator(f"{chart} .bartext")).to_have_count(0)
        expect(page.locator(f"{chart} .textpoint")).to_have_count(0)
        drawn = [
            b
            for part in OVER_TIME_TEXTS
            for b in boxes(page, f"{chart} {part}")
            if b["w"] > 0 and b["text"]
        ]
        # Value ticks and both titles beside the year ticks.
        assert len(drawn) > len(year_ticks()) + 2, chart
        for i, a in enumerate(drawn):
            assert a["x"] >= 0 and a["x"] + a["w"] <= width, (chart, a)
            for b in drawn[i + 1 :]:
                assert not overlaps(a, b), (chart, a, b)
    for chart in (C4, C5):
        bar = f"{chart} .barlayer .point path >> nth=-1"
        assert_hover_names_year(page, chart, bar, served_years()[-1])


@pytest.mark.plotlyjs_fetches(1)
def test_c5_bands_the_years_before_the_window(page: Page) -> None:
    open_over_time(page)
    notes = [b["text"] for b in boxes(page, f"{C5} .annotation-text")]
    band = labels.C5_BEFORE_BAND.format(pv_year_min=PV_FIRST).replace("<br>", "")
    assert notes == [band]
    # Above the plot (#558, D104), never inside the band.
    (note,) = boxes(page, f"{C5} .annotation-text")
    (plot,) = boxes(page, f"{C5} .draglayer .nsewdrag")
    assert note["y"] + note["h"] <= plot["y"] + 1, (note, plot)
    expect(page.locator(f"{C5} .layer-below .shapelayer path")).to_have_count(1)


@pytest.mark.plotlyjs_fetches(1)
def test_c4_and_c5_redraw_on_a_theme_switch_with_no_request(page: Page) -> None:
    open_over_time(page)
    bars = [page.locator(f"{chart} .barlayer .point path").first for chart in (C4, C5)]
    light = [bar.evaluate("el => getComputedStyle(el).fill") for bar in bars]
    seen: list[str] = []
    page.on("request", lambda r: seen.append(urlsplit(r.url).path))
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    for bar, before in zip(bars, light, strict=True):
        expect(bar).not_to_have_css("fill", before)
        assert bar.evaluate("el => getComputedStyle(el).fill") == rgb(
            token(page, "--chart-1")
        )
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen


@pytest.mark.plotlyjs_fetches(1)
def test_no_state_control_and_an_old_state_key_changes_nothing(page: Page) -> None:
    """The one-state mode retired with #562 (D107): no dropdown on the page, and the
    old key draws the all-states bars."""
    open_over_time(page, "?state=GA")
    expect(page.locator(".dash-dropdown")).to_have_count(0)
    expect(page.locator(f"{C4} .chart-title")).to_have_text(labels.C4_TITLE)
    expect(page.locator(OVER_TIME_ROWS)).to_have_count(len(served_years()))


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="#496: the browser handles the fragment before Dash renders the chart",
)
@pytest.mark.plotlyjs_fetches(1)
def test_the_c4_fragment_scrolls_to_the_chart_after_dash_renders(page: Page) -> None:
    """Checked whether or not the C3 link ships (#436, owner): it does not, since the
    fragment does not land; #496 holds both."""
    page.goto("/elections/over-time#c4")
    assert_rendered(page, OVER_TIME_SUCCESS)
    page.locator(f"{C4} .main-svg").first.wait_for()
    page.wait_for_timeout(SETTLE_MS)
    # Landed: the fragment's target, the chart's figure, at the viewport's top
    # (#562's review, ge.5), scrolled past the heading, lede and section links above it.
    assert page.evaluate("scrollY") > 0
    top = page.evaluate("document.getElementById('c4').getBoundingClientRect().top")
    assert abs(top) <= 1, top


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_c4_and_c5_keep_their_text_and_table(page: Page) -> None:
    page.goto("/elections/over-time")
    assert_rendered(page, OVER_TIME_SUCCESS)
    memo = f"window.{charts.PLOTLYJS_MEMO}"
    page.wait_for_function(f"{memo} !== undefined")
    assert page.evaluate(f"async () => await {memo}") is False
    for chart, title, basis in (
        (C4, labels.C4_TITLE, labels.C4_BASIS),
        (C5, labels.C5_TITLE, labels.C5_BASIS),
    ):
        expect(page.locator(f"{chart} .chart-title")).to_have_text(title)
        expect(page.locator(f"{chart} figcaption")).to_contain_text(basis)
        expect(page.locator(f"{chart} figcaption a")).to_have_attribute(
            "href", "#elections-over-time-table"
        )
        expect(page.locator(f"{chart} .js-plotly-plot")).to_have_count(0)
    expect(page.locator(OVER_TIME_ROWS)).to_have_count(len(served_years()))


# --- the wide layout (#553, D102, D103) ----------------------------------------------

OVER_TIME_PAIR = "#elections-over-time-pair"
OVER_TIME_COLUMNS = f"{OVER_TIME_PAIR} > div"
HEADING_GAP_PX = 1.75 * 16


def open_at(page: Page, width: int) -> None:
    """``/elections/over-time`` at ``width``, with C4 and C5 drawn."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("/elections/over-time")
    page.locator(OVER_TIME_SUCCESS).wait_for()
    assert page.locator(UNAVAILABLE).count() == 0
    assert page.evaluate("innerWidth") == width
    for chart in (C4, C5):
        page.locator(f"{chart} .main-svg").first.wait_for()


def wait_charts_fill(page: Page) -> None:
    """C4's and C5's drawings each as wide as its box (#433's responsive check)."""
    page.wait_for_function(
        f"""() => [{C4!r}, {C5!r}].every(chart => {{
            const svg = document.querySelector(chart + " .main-svg");
            const box = document.querySelector(chart + " .chart-graph");
            return svg && Math.abs(svg.getBoundingClientRect().width
                - box.getBoundingClientRect().width) < 1;
        }})"""
    )


def side_by_side(left: dict[str, float], right: dict[str, float]) -> None:
    """Two equal columns, the first to the left of the second, their tops level."""
    assert left["right"] < right["left"], (left, right)
    assert abs(left["width"] - right["width"]) <= 1, (left, right)
    assert abs(left["top"] - right["top"]) <= 1, (left, right)


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", WIDE_WIDTHS)
def test_wide_c4_sits_beside_c5_with_their_table_below(page: Page, width: int) -> None:
    open_at(page, width)
    wait_charts_fill(page)
    left, right = rects(page, OVER_TIME_COLUMNS)
    side_by_side(left, right)
    for chart, column in ((C4, left), (C5, right)):
        graph = rect(page, f"{chart} .chart-graph")
        assert abs(graph["width"] - column["width"]) <= 1, (chart, graph, column)
        assert abs(graph["left"] - column["left"]) <= 1, (chart, graph, column)
    # The companion table's heading a section heading's gap below the taller column,
    # and its table across both columns.
    heading = rect(page, f"{OVER_TIME_PAIR} + h2")
    taller = max(left["bottom"], right["bottom"])
    assert heading["top"] - taller >= HEADING_GAP_PX - 1, (heading, taller)
    table = rect(page, ".table-scroll:has(#elections-over-time-table)")
    assert table["top"] > taller, (table, taller)
    assert abs(table["left"] - left["left"]) <= 1, (table, left)
    assert table["right"] >= right["right"] - 1, (table, right)



@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", [NARROW_DESKTOP, 390])
def test_narrow_the_pair_stacks_as_before(page: Page, width: int) -> None:
    open_at(page, width)
    left, right = rects(page, OVER_TIME_COLUMNS)
    assert right["top"] >= left["bottom"] - 0.5, (width, left, right)
    assert abs(left["left"] - right["left"]) <= 0.5, (width, left, right)
    assert rect(page, C4)["bottom"] <= rect(page, C5)["top"] + 0.5


@pytest.mark.plotlyjs_fetches(1)
def test_c4_and_c5_fill_their_columns_after_a_resize_across_the_breakpoint(
    page: Page,
) -> None:
    open_at(page, 1280)
    for width in (1280, NARROW_DESKTOP, 1280, 1850, 1280):
        page.set_viewport_size({"width": width, "height": 900})
        wait_charts_fill(page)
        left, right = rects(page, OVER_TIME_COLUMNS)
        # Side by side from the breakpoint, stacked below it, after every crossing.
        if width >= WIDE_BREAKPOINT_PX:
            side_by_side(left, right)
        else:
            assert right["top"] >= left["bottom"] - 0.5, (width, left, right)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", [*WIDE_WIDTHS, NARROW_DESKTOP, 390])
def test_every_width_keeps_order_measure_and_tables(page: Page, width: int) -> None:
    open_at(page, width)
    assert_layout_holds(page, OVER_TIME_SUCCESS, ("#elections-over-time-table",), width)
