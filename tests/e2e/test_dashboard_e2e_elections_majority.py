"""The Electoral College majority page, ``/elections/majority``, in a browser (#562):
chart C2 (#434, D096) and its companion table, on their own page since #562 (D107).
No console error and no off-host request are asserted for every test by
``conftest._browser_guard``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import charts, components, elections_view, labels
from tests.e2e.dashboard_pages import (
    C2,
    COVERAGE,
    LEADER_ROWS,
    MAJORITY_SUCCESS,
    NARROW_DESKTOP,
    PHONE_WIDTHS,
    RESOURCE_ERROR,
    WIDE_WIDTHS,
    assert_hover_names_year,
    assert_layout_holds,
    assert_rendered,
    assert_year_ticks_apart,
    recorded,
    rect,
    served_years,
)
from tests.e2e.test_dashboard_e2e_election import boxes, overlaps, rgb, token
from tests.e2e.test_dashboard_e2e_elections_over_time import assert_band_label_inside

pytestmark = pytest.mark.e2e

#: How long a filter change is given to fire anything further after it settled. The

#: How long a redraw is given to fire anything further after it settled.
SETTLE_MS = 1000

# --- chart C2 (#434, D096) ------------------------------------------------------------

#: C2's drawn texts (#558, D104): its year ticks along the bottom, its share ticks, both
#: axes' titles, the band labels and the key's entries (the majority line's among them
#: since #596); no point draws text.
C2_CHART_TEXTS = ", ".join(
    f"{C2} {part}"
    for part in (
        ".xtick text",
        ".ytick text",
        ".g-xtitle text",
        ".g-ytitle text",
        ".annotation-text",
        ".legendtext",
    )
)
#: C2's traces by their stable identity (#596's architect review: the trace's ``uid``,
#: which plotly.js writes into its class), never by their place in the drawing order,
#: which a filter changes; on the recorded N1 every one is drawn.
C2_TRACE = f"{C2} .scatterlayer .trace.trace{{}} .points path"
C2_TRIANGLES = C2_TRACE.format("c2pv")
C2_CROSSBARS = C2_TRACE.format("c2hybrid")
C2_POINTS = C2_TRACE.format("c2ec")
C2_STRIP = C2_TRACE.format("c2pvstrip")
#: Every mark C2 draws, the strip's included.
C2_MARKS = f"{C2} .scatterlayer .points path"
_N1 = recorded("/v1/elections/summary")
#: The recorded years with a popular-vote share drawn, and those the strip marks.
PV_YEARS = sorted(
    row["year"]
    for row in recorded("/v1/elections")["data"]
    if row["has_popular_vote"]
)
DIFFERENT = sorted(item["year"] for item in _N1["elections"] if item["pv_flip"] is True)


def open_c2(page: Page, query: str = "", *, width: int = 390) -> None:
    page.goto(f"/elections/majority{query}")
    assert_rendered(page, MAJORITY_SUCCESS, width=width)
    page.locator(f"{C2} .main-svg").first.wait_for()
    page.locator(f"{C2} .xtick text").first.wait_for()


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_c2_is_readable_at_phone_width(page: Page, width: int) -> None:
    """AC Phone width (#558, D104; #564, D108): year along the bottom, its sparse ticks
    apart, every text (the band's label and the key's entries included) inside the
    width and none over another, the majority line named in the key (#596, D110: no
    label in the plot), no sideways scroll; one circle per served year, a
    triangle and a crossbar per popular-vote year, a strip mark per disagreement, no
    mark text, and hovers on a circle, a triangle, a crossbar and a strip mark naming
    their year. Since #593 (D109): the band's label inside its band and the key above
    the plot."""
    page.set_viewport_size({"width": width, "height": 844})
    open_c2(page, width=width)
    expect(page.locator(f"{C2} .chart-title")).to_have_text(labels.C2_TITLE)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert_year_ticks_apart(page, C2)
    expect(page.locator(C2_POINTS)).to_have_count(len(served_years()))
    expect(page.locator(C2_TRIANGLES)).to_have_count(len(PV_YEARS))
    expect(page.locator(C2_CROSSBARS)).to_have_count(len(PV_YEARS))
    expect(page.locator(C2_STRIP)).to_have_count(len(DIFFERENT))
    assert DIFFERENT and PV_YEARS[0] == COVERAGE["pv_year_min"]  # the premises
    expect(page.locator(f"{C2} .textpoint")).to_have_count(0)
    texts_ = [b for b in boxes(page, C2_CHART_TEXTS) if b["w"] > 0]
    found = [b["text"] for b in texts_]
    assert found.count(labels.C2_VALUE_AXIS.replace("<br>", "")) == 1
    assert found.count(labels.LABELS["year"]) == 1
    for name in (
        labels.C2_MAJORITY_KEY.replace("<br>", ""),
        labels.LABELS["ec_share_full"],
        labels.LABELS["pv_share"],
        labels.C2_HYBRID_KEY,
        labels.C2_PV_DIFFERENT_KEY,
    ):
        assert found.count(name) == 1, (name, found)
    for i, a in enumerate(texts_):
        assert a["x"] >= 0 and a["x"] + a["w"] <= width, a
        for b in texts_[i + 1 :]:
            assert not overlaps(a, b), (a, b)
    last = served_years()[-1]
    assert_band_label_inside(page, C2)
    (plot,) = boxes(page, f"{C2} .draglayer .nsewdrag")
    for entry in boxes(page, f"{C2} .legendtext"):
        assert entry["y"] + entry["h"] <= plot["y"] + 1, (entry, plot)
    assert_hover_names_year(page, C2, f"{C2_POINTS} >> nth=-1", last)
    page.mouse.move(0, 0)
    assert_hover_names_year(page, C2, f"{C2_TRIANGLES} >> nth=0", str(PV_YEARS[0]))
    page.mouse.move(0, 0)
    assert_hover_names_year(page, C2, f"{C2_CROSSBARS} >> nth=-1", str(PV_YEARS[-1]))
    page.mouse.move(0, 0)
    assert_hover_names_year(page, C2, f"{C2_STRIP} >> nth=0", str(DIFFERENT[0]))


@pytest.mark.plotlyjs_fetches(1)
def test_the_year_filters_narrow_c2_and_its_table(page: Page) -> None:
    """#596 (D110): the list's filters narrow C2 and its table; the controls show the
    filters applied."""
    open_c2(page, "?year_from=1900&pv=1")
    shown = [y for y in PV_YEARS if y >= 1900]
    expect(page.locator(C2_POINTS)).to_have_count(len(shown))
    expect(page.locator(LEADER_ROWS)).to_have_count(len(shown))
    expect(page.locator(f"#{elections_view.PV_ID} input")).to_be_checked()
    expect(page.locator(f"{C2} .layer-below .shapelayer path")).to_have_count(
        len([0.25, 0.75, 1])  # the gridlines alone: no band
    )


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize(
    "query",
    [
        "?pv=1",  # the popular-vote years alone: no band
        "?year_from=2024",  # one year
        "?year_from=1968",  # a before band two elections wide: its label above
        "?year_to=1900",  # no popular-vote year: the electoral share alone
    ],
)
def test_filtered_c2_is_readable_at_360(page: Page, query: str) -> None:
    """#596 (D110): under a filter every text C2 draws stays inside 360 px with none
    over another, the key (the majority line's entry included) stays above the plot,
    and a band's label sits inside its band or above the plot."""
    width = 360
    page.set_viewport_size({"width": width, "height": 844})
    open_c2(page, query, width=width)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    texts_ = [b for b in boxes(page, C2_CHART_TEXTS) if b["w"] > 0]
    for i, a in enumerate(texts_):
        assert a["x"] >= 0 and a["x"] + a["w"] <= width, a
        for b in texts_[i + 1 :]:
            assert not overlaps(a, b), (a, b)
    (plot,) = boxes(page, f"{C2} .draglayer .nsewdrag")
    entries = boxes(page, f"{C2} .legendtext")
    assert labels.C2_MAJORITY_KEY.replace("<br>", "") in [e["text"] for e in entries]
    for entry in entries:
        assert entry["y"] + entry["h"] <= plot["y"] + 1, (entry, plot)
    for note in boxes(page, f"{C2} .annotation-text"):
        for mark in boxes(page, C2_MARKS):
            assert not overlaps(note, mark), (note, mark)
    # Each band's label inside its band, or above the plot (#596, D110): the bands are
    # the shapes the plot's full height.
    bands = [
        b
        for b in boxes(page, f"{C2} .layer-below .shapelayer path")
        if abs(b["h"] - plot["h"]) < 2
    ]
    notes = boxes(page, f"{C2} .annotation-text")
    if query == "?year_from=1968":
        # Not vacuous (#596's round 2): the narrow band and its one label are drawn.
        assert len(bands) == 1 and len(notes) == 1, (bands, notes)
    for note in notes:
        above = note["y"] + note["h"] <= plot["y"] + 1
        inside = any(
            band["x"] - 1 <= note["x"]
            and note["x"] + note["w"] <= band["x"] + band["w"] + 1
            and note["y"] >= plot["y"] - 1
            for band in bands
        )
        assert above or inside, (query, note, bands)
        if query == "?year_from=1968":
            assert above, note  # a band two elections wide: its label above the plot


@pytest.mark.plotlyjs_fetches(1)
def test_c2_redraws_on_a_theme_switch_with_no_reload_or_request(page: Page) -> None:
    open_c2(page)
    point = page.locator(C2_POINTS).first
    light = point.evaluate("el => getComputedStyle(el).fill")
    assert light == rgb(token(page, "--chart-ec"))
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    expect(point).not_to_have_css("fill", light)
    assert point.evaluate("el => getComputedStyle(el).fill") == rgb(
        token(page, "--chart-ec")
    )
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_c2_s_title_caption_and_table_render(
    page: Page,
) -> None:
    page.goto("/elections/majority")
    assert_rendered(page, MAJORITY_SUCCESS)
    memo = f"window.{charts.PLOTLYJS_MEMO}"
    page.wait_for_function(f"{memo} !== undefined")
    assert page.evaluate(f"async () => await {memo}") is False
    expect(page.locator(f"{C2} .chart-title")).to_have_text(labels.C2_TITLE)
    expect(page.locator(f"{C2} figcaption")).to_contain_text(labels.C2_LEADER_POINT)
    expect(page.locator(f"{C2} figcaption a")).to_have_attribute(
        "href", "#elections-leader-table"
    )
    expect(page.locator("#elections-leader-table")).to_be_visible()
    expect(page.locator(LEADER_ROWS)).to_have_count(len(served_years()))
    expect(page.locator(f"{C2} .js-plotly-plot")).to_have_count(0)


@pytest.mark.plotlyjs_fetches(2)
def test_each_mark_is_its_measure_s_color_and_no_axis_gridline_is_drawn(
    page: Page,
) -> None:
    """#593 (D109): circle red, triangle blue, crossbar purple, read from what the
    browser paints; and plotly draws no value-axis gridline on C2 (its gridlines are
    shapes, which ``TestC2Methods.test_no_gridline_at_the_majority_line`` in
    ``tests/unit/test_dashboard_elections_majority.py`` pins away from 50%). The
    control: C4, which keeps the
    axis's own gridlines, does draw ``.ygrid`` paths, so the count is not vacuous."""
    open_c2(page)
    for selector, measure, prop in (
        (C2_POINTS, "--chart-ec", "fill"),
        (C2_TRIANGLES, "--chart-pv", "fill"),
        (C2_CROSSBARS, "--chart-hybrid", "stroke"),
    ):
        painted = page.locator(selector).first.evaluate(
            f"el => getComputedStyle(el).{prop}"
        )
        assert painted == rgb(token(page, measure)), (selector, painted)
    expect(page.locator(f"{C2} .ygrid")).to_have_count(0)
    page.goto("/elections/over-time")
    page.locator("#c4 .main-svg").first.wait_for()
    expect(page.locator("#c4 .ygrid").first).to_be_attached()


@pytest.mark.plotlyjs_fetches(1)
def test_the_caption_is_closed_until_its_summary_is_opened(page: Page) -> None:
    """#593 (D109): hidden on load, shown once the summary is clicked; the table
    pointer shown throughout."""
    open_c2(page)
    text = page.locator(f"{C2} .chart-caption-text")
    expect(text).to_be_hidden()
    expect(page.locator(f"{C2} .chart-pointer a")).to_be_visible()
    page.locator(f"{C2} summary").click()
    expect(text).to_be_visible()
    expect(text).to_contain_text(labels.C2_HYBRID_MARK)


# --- the wide layout (#553, D102, D103) ----------------------------------------------


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", WIDE_WIDTHS)
def test_wide_c2_stays_full_width_above_its_table(page: Page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    open_c2(page, width=width)
    content = rect(page, MAJORITY_SUCCESS)
    c2 = rect(page, f"{C2} .chart-graph")
    assert abs(c2["width"] - content["width"]) <= 1, (c2, content)
    table = rect(page, ".table-scroll:has(#elections-leader-table)")
    assert c2["bottom"] <= table["top"], (c2, table)


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", [*WIDE_WIDTHS, NARROW_DESKTOP, *PHONE_WIDTHS])
def test_every_width_keeps_order_measure_and_tables(page: Page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    open_c2(page, width=width)
    assert_layout_holds(page, MAJORITY_SUCCESS, ("#elections-leader-table",), width)


# --- the headline counts (#569, D112) -------------------------------------------------

#: The block and the two values, by the page's stable ids.
COUNTS = "#majority-metrics"


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_the_counts_read_inside_phone_width(page: Page, width: int) -> None:
    """AC 360 px (#569): the two counts, their labels and the window note each sit
    inside the width with no sideways scroll, and read the recording's hand counts.
    Layout only: the counts add no color token. Their text and the note take the shared
    tokens ``TestThemeContrast`` (``tests/unit/test_dashboard_theme.py``) holds to AA in
    both palettes, the device's dark block being identical to the chosen one
    (``test_the_two_dark_blocks_are_identical``); #602's review, ge.6 and r2.recheck.1.
    So a theme changes nothing this test reads."""
    page.set_viewport_size({"width": width, "height": 844})
    open_c2(page, width=width)
    expect(page.locator("#majority-ec-no-majority-count")).to_have_text(
        "1 of 51 elections (1824–2024)"
    )
    expect(page.locator("#majority-pv-flip-count")).to_have_text(
        "2 of 13 elections (1976–2024)"
    )
    parts = page.locator(f"{COUNTS} dt, {COUNTS} dd, {COUNTS} p")
    assert parts.count() == 5
    for i in range(parts.count()):
        box = parts.nth(i).bounding_box()
        assert box is not None
        assert box["x"] >= 0 and box["x"] + box["width"] <= width + 0.5, (i, box)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # The block sits between the filters and the chart.
    counts, chart = rect(page, COUNTS), rect(page, C2)
    assert counts["bottom"] <= chart["top"], (counts, chart)
