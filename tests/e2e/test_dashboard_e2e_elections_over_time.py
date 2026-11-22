"""The electors appointed and total popular vote page, ``/elections/over-time``, in a
browser (#562): charts C4 and C5 (#436, D100) and their companion table, all states only
since #562 (D107). No console error and no off-host request are asserted for every test
by ``conftest._browser_guard``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect

from explore import charts, components, elections_view, labels
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
    WIDE_WIDTHS,
    assert_figures_inside,
    assert_hover_names_year,
    assert_layout_holds,
    assert_rendered,
    assert_year_ticks_apart,
    rect,
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
    assert_band_label_inside(page, C5)
    for chart in (C4, C5):
        bar = f"{chart} .barlayer .point path >> nth=-1"
        assert_hover_names_year(page, chart, bar, served_years()[-1])


def assert_band_label_inside(page: Page, chart: str) -> None:
    """The before band's label lies inside its band's box (#593, D109; the architect's
    B2): the e2e overlap checks compare text with text only, so a label running out of
    its band over the marks would pass them. The label is found by its exact text
    (the after band's starts "Shaded:" too); the before band is the chart's first
    shape (``over_time.pv_bands`` draws it first), so this holds on a recording with
    an after band as well."""
    before = labels.C5_BEFORE_BAND.replace("<br>", "")
    (note,) = [
        b for b in boxes(page, f"{chart} .annotation-text") if b["text"] == before
    ]
    band = page.locator(f"{chart} .layer-below .shapelayer path").first
    box = band.bounding_box()
    assert box is not None
    assert note["x"] >= box["x"] - 0.5, (note, box)
    assert note["x"] + note["w"] <= box["x"] + box["width"] + 0.5, (note, box)
    assert note["y"] >= box["y"] - 0.5, (note, box)
    assert note["y"] + note["h"] <= box["y"] + box["height"] + 0.5, (note, box)


@pytest.mark.plotlyjs_fetches(1)
def test_c5_bands_the_years_before_the_window(page: Page) -> None:
    open_over_time(page)
    notes = [b["text"] for b in boxes(page, f"{C5} .annotation-text")]
    band = labels.C5_BEFORE_BAND.format(pv_year_min=PV_FIRST).replace("<br>", "")
    assert notes == [band]
    # Inside the band at its top (#593, D109), under the plot's top edge.
    (note,) = boxes(page, f"{C5} .annotation-text")
    (plot,) = boxes(page, f"{C5} .draglayer .nsewdrag")
    assert plot["y"] <= note["y"] <= plot["y"] + 12, (note, plot)
    expect(page.locator(f"{C5} .layer-below .shapelayer path")).to_have_count(1)
    assert_band_label_inside(page, C5)


@pytest.mark.plotlyjs_fetches(1)
def test_c4_and_c5_redraw_on_a_theme_switch_with_no_request(page: Page) -> None:
    open_over_time(page)
    bars = [page.locator(f"{chart} .barlayer .point path").first for chart in (C4, C5)]
    light = [bar.evaluate("el => getComputedStyle(el).fill") for bar in bars]
    seen: list[str] = []
    page.on("request", lambda r: seen.append(urlsplit(r.url).path))
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    # Each chart's measure (#593, D109): electors appointed red, the total popular
    # vote blue.
    for bar, before, measure in zip(
        bars, light, ("--chart-ec", "--chart-pv"), strict=True
    ):
        expect(bar).not_to_have_css("fill", before)
        assert bar.evaluate("el => getComputedStyle(el).fill") == rgb(
            token(page, measure)
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


@pytest.mark.plotlyjs_fetches(1)
def test_each_caption_is_closed_until_its_summary_is_opened(page: Page) -> None:
    """#593 (D109): the caption is hidden on load and shown once its summary is
    clicked; the table pointer is shown throughout."""
    open_over_time(page)
    for chart, basis in ((C4, labels.C4_BASIS), (C5, labels.C5_BASIS)):
        text = page.locator(f"{chart} .chart-caption-text")
        expect(text).to_be_hidden()
        expect(page.locator(f"{chart} .chart-pointer a")).to_be_visible()
        page.locator(f"{chart} summary").click()
        expect(text).to_be_visible()
        expect(text).to_contain_text(basis)


# --- C4 above C5 (#593, D109, amending D102 and D103(c)) ------------------------------


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


def assert_plots_align(page: Page) -> None:
    """C4's plot area directly above C5's: the same left edge and width, so a year
    reads straight down both (#593's architect review, I2)."""
    c4, c5 = (rect(page, f"{chart} .draglayer .nsewdrag") for chart in (C4, C5))
    assert abs(c4["left"] - c5["left"]) <= 1, (c4, c5)
    assert abs(c4["width"] - c5["width"]) <= 1, (c4, c5)
    assert c4["bottom"] <= c5["top"], (c4, c5)


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", [*WIDE_WIDTHS, NARROW_DESKTOP, *PHONE_WIDTHS])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_c4_sits_above_c5_with_their_plots_aligned(
    page: Page, width: int, theme: str
) -> None:
    open_at(page, width)
    if theme == "dark":
        page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    wait_charts_fill(page)
    expect(page.locator(".pair")).to_have_count(0)
    assert rect(page, C4)["bottom"] <= rect(page, C5)["top"] + 0.5
    assert abs(rect(page, C4)["left"] - rect(page, C5)["left"]) <= 0.5
    assert_plots_align(page)
    table = rect(page, ".table-scroll:has(#elections-over-time-table)")
    assert table["top"] > rect(page, C5)["bottom"], table


@pytest.mark.plotlyjs_fetches(1)
def test_the_plots_stay_aligned_across_resizes(page: Page) -> None:
    open_at(page, 1280)
    for width in (1280, NARROW_DESKTOP, 1280, 1850, 390, 1280):
        page.set_viewport_size({"width": width, "height": 900})
        wait_charts_fill(page)
        assert_plots_align(page)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", [*WIDE_WIDTHS, NARROW_DESKTOP, *PHONE_WIDTHS])
def test_every_width_keeps_order_measure_and_tables(page: Page, width: int) -> None:
    open_at(page, width)
    assert_layout_holds(page, OVER_TIME_SUCCESS, ("#elections-over-time-table",), width)


# --- the year filters, C5's short ticks and the shared margin (#596, D110) ---------------

#: The views whose value ticks and bands differ: the default, the popular-vote years, a
#: narrow before band, no bar on C5 (no value ticks), and a short span inside the window.
FILTERED_VIEWS = (
    "",
    "?pv=1",
    "?year_from=1968",
    "?year_to=1972",
    "?year_from=1976&year_to=1980",
)
#: The least room, in px, left of each value-axis text inside its chart's SVG: the
#: shared margin's slack (architect Q6, #596).
MARGIN_SLACK_PX = 8


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("query", FILTERED_VIEWS)
def test_the_shared_margin_holds_every_value_tick_and_title(
    page: Page, query: str
) -> None:
    """#596 (D110): with the value axes' own margins off, nothing pushes the shared
    left margin, so every value tick and axis title of C4 and C5 must start inside its
    chart's SVG, with slack, under every filter; and C5's ticks are short ("50M")."""
    width = 360
    page.set_viewport_size({"width": width, "height": 844})
    open_over_time(page, query, width=width)
    for chart in (C4, C5):
        page.locator(f"{chart} .main-svg").first.wait_for()
        (svg,) = boxes(page, f"{chart} .main-svg >> nth=0")
        texts_ = [
            b
            for b in boxes(page, f"{chart} .ytick text, {chart} .g-ytitle text")
            if b["w"] > 0
        ]
        assert texts_, (chart, query)
        for b in texts_:
            assert b["x"] - svg["x"] >= MARGIN_SLACK_PX, (chart, query, b)
            assert b["x"] + b["w"] <= width, (chart, query, b)
    c5_ticks = [b["text"] for b in boxes(page, f"{C5} .ytick text") if b["w"] > 0]
    if query == "?year_to=1972":
        assert c5_ticks == []  # no bar drawn: no value ticks
    else:
        assert c5_ticks[0] == "0" and all(
            t == "0" or t.endswith("M") for t in c5_ticks
        ), c5_ticks
    assert_plots_align(page)


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("query", FILTERED_VIEWS[1:])
def test_filtered_c4_and_c5_are_readable_at_360(page: Page, query: str) -> None:
    """#596 (D110): under a filter every text C4 and C5 draw stays inside 360 px with
    none over another, and a band's label is over no bar or marker."""
    width = 360
    page.set_viewport_size({"width": width, "height": 844})
    open_over_time(page, query, width=width)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for chart in (C4, C5):
        page.locator(f"{chart} .xtick text").first.wait_for()
        texts_ = [
            b
            for b in boxes(
                page,
                ", ".join(
                    f"{chart} {part}"
                    for part in (
                        ".xtick text",
                        ".ytick text",
                        ".g-xtitle text",
                        ".g-ytitle text",
                        ".annotation-text",
                        ".legendtext",
                    )
                ),
            )
            if b["w"] > 0
        ]
        for i, a in enumerate(texts_):
            assert a["x"] >= 0 and a["x"] + a["w"] <= width, (chart, query, a)
            for b in texts_[i + 1 :]:
                assert not overlaps(a, b), (chart, query, a, b)
        for note in boxes(page, f"{chart} .annotation-text"):
            for mark in boxes(page, f"{chart} .barlayer path, {chart} .points path"):
                assert not overlaps(note, mark), (chart, query, note, mark)


@pytest.mark.plotlyjs_fetches(0)
def test_a_filter_leaving_no_year_shows_the_note(page: Page) -> None:
    page.goto("/elections/over-time?year_to=1972&pv=1")
    assert_rendered(page, OVER_TIME_SUCCESS)
    expect(page.locator(f"#{elections_view.NO_MATCH_ID}")).to_have_text(
        labels.NO_ELECTIONS_MATCH
    )
    expect(page.locator(f"{C4}, {C5}, #elections-over-time-table")).to_have_count(0)


# --- the headline figures (#600, D112(d)) ----------------------------------------------

FIGURES = "#elections-over-time-metrics"


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_the_figures_read_inside_phone_width(page: Page, width: int) -> None:
    """AC 360 px (#600): the four figures, their labels and the window note sit inside
    the width with no sideways scroll in Light, Dark and System, read the recording's
    hand counts, and sit between the filters and C4."""
    page.set_viewport_size({"width": width, "height": 844})
    open_over_time(page, width=width)
    expect(page.locator("#elections-over-time-ec-appointed-first")).to_have_text(
        "261 in 1824, among 51 elections with a figure (1824–2024)"
    )
    expect(page.locator("#elections-over-time-pv-total-latest")).to_have_text(
        "155,410,204 in 2024, among 13 elections with a figure (1976–2024)"
    )
    assert_figures_inside(page, FIGURES, width, 9)
    figures, chart = rect(page, FIGURES), rect(page, C4)
    assert figures["bottom"] <= chart["top"], (figures, chart)
    years = rect(page, f"#{elections_view.YEARS_ID}")
    assert years["bottom"] <= figures["top"], (years, figures)

