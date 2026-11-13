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
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import charts, components, labels
from tests.e2e.dashboard_pages import (
    C2,
    C4,
    C5,
    ELECTIONS_ROWS,
    ELECTIONS_SUCCESS,
    FIELDS,
    FILTER_OUTPUT,
    FIRST,
    GLOSSARY,
    LAST,
    LEADER_ROWS,
    MARKS,
    OVER_TIME_ROWS,
    PROVENANCE,
    PV,
    PV_BOX,
    PV_FIRST,
    RESOURCE_ERROR,
    ROUTER_OUTPUT,
    STATE_CONTROL,
    UPDATE_PATH,
    assert_chunk_failure_stops,
    assert_rendered,
    lower_thumb,
    recorded,
    row_years,
    search,
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


# --- chart C2 (#434, D096) ------------------------------------------------------------

#: C2's drawn texts: each point's share and, outside the plot, its year ticks, the share
#: axis's title and the majority line's two labels.
C2_POINT_TEXTS = f"{C2} .scatterlayer .textpoint text"
C2_CHART_TEXTS = ", ".join(
    f"{C2} {part}"
    for part in (".ytick text", ".xtick text", ".g-xtitle text", ".annotation-text")
)
C2_POINTS = f"{C2} .scatterlayer .trace:first-child .points path"


def open_c2(page: Page, query: str = "") -> None:
    page.goto(f"/elections{query}")
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.locator(f"{C2} .main-svg").first.wait_for()
    page.locator(f"{C2} .ytick text").first.wait_for()


def served_years() -> list[str]:
    return [str(row["year"]) for row in recorded("/v1/elections")["data"]]


@pytest.mark.plotlyjs_fetches(1)
def test_c2_is_readable_at_390_px(page: Page) -> None:
    """AC Phone width: every year's tick and every point's text inside 390 px, none over
    another, and no sideways scroll; one point per served year."""
    open_c2(page)
    expect(page.locator(f"{C2} .chart-title")).to_have_text(labels.C2_TITLE)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ticks = boxes(page, f"{C2} .ytick text")
    assert [b["text"] for b in ticks] == served_years()
    shares = boxes(page, C2_POINT_TEXTS)
    assert len(shares) == len(ticks)
    assert {"37.9%", "50.1%", "50.4%", "98.5%"} <= {b["text"] for b in shares}
    expect(page.locator(C2_POINTS)).to_have_count(len(ticks))
    others = boxes(page, C2_CHART_TEXTS)
    assert sum(b["text"] == labels.C2_X_AXIS for b in others) == 1
    labeled = [b for b in shares + others if b["w"] > 0]
    for i, a in enumerate(labeled):
        assert a["x"] >= 0 and a["x"] + a["w"] <= 390, a
        for b in labeled[i + 1 :]:
            assert not overlaps(a, b), (a, b)


@pytest.mark.plotlyjs_fetches(1)
def test_c2_and_its_table_ignore_the_filters(page: Page) -> None:
    """D096: a filter narrows T1, never C2 or its companion table."""
    open_c2(page, "?year_from=1900")
    ticks = [b["text"] for b in boxes(page, f"{C2} .ytick text")]
    assert ticks == served_years()
    expect(page.locator(LEADER_ROWS)).to_have_count(len(served_years()))
    assert row_years(page) == years_shown(year_from=1900)


@pytest.mark.plotlyjs_fetches(1)
def test_c2_redraws_on_a_theme_switch_with_no_reload_or_request(page: Page) -> None:
    open_c2(page)
    point = page.locator(C2_POINTS).first
    light = point.evaluate("el => getComputedStyle(el).fill")
    assert light == rgb(token(page, "--chart-1"))
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    expect(point).not_to_have_css("fill", light)
    assert point.evaluate("el => getComputedStyle(el).fill") == rgb(
        token(page, "--chart-1")
    )
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_c2_s_title_caption_and_both_tables_render(
    page: Page,
) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    memo = f"window.{charts.PLOTLYJS_MEMO}"
    page.wait_for_function(f"{memo} !== undefined")
    assert page.evaluate(f"async () => await {memo}") is False
    expect(page.locator(f"{C2} .chart-title")).to_have_text(labels.C2_TITLE)
    expect(page.locator(f"{C2} figcaption")).to_contain_text(labels.C2_LEADER_POINT)
    expect(page.locator(f"{C2} figcaption a")).to_have_attribute(
        "href", "#elections-leader-table"
    )
    expect(page.locator("#elections-leader-table")).to_be_visible()
    expect(page.locator(ELECTIONS_ROWS)).to_have_count(len(served_years()))
    expect(page.locator(f"{C2} .js-plotly-plot")).to_have_count(0)


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


# --- charts C4 and C5 (#436, D100) ---------------------------------------------------

#: Every text C4 or C5 draws that a reader reads: year ticks, bar labels, marker
#: labels, the band's labels and the value axis's title.
OVER_TIME_TEXTS = (
    ".ytick text",
    ".bartext",
    ".scatterlayer .textpoint text",
    ".annotation-text",
    ".g-xtitle text",
)


def open_over_time(page: Page, query: str = "") -> None:
    page.goto(f"/elections{query}")
    assert_rendered(page, ELECTIONS_SUCCESS)
    for chart in (C4, C5):
        page.locator(f"{chart} .main-svg").first.wait_for()
        page.locator(f"{chart} .ytick text").first.wait_for()


def state_name(usps: str) -> str:
    rows = recorded("/v1/elections/states")["data"]
    return str(next(r["state"] for r in rows if r["state_usps"] == usps))


def filter_posts(page: Page) -> list[str]:
    """The filter callback's posts, recorded from now on."""
    posts: list[str] = []

    def on_request(request: Request) -> None:
        if urlsplit(request.url).path == UPDATE_PATH and FILTER_OUTPUT in (
            request.post_data or ""
        ):
            posts.append(request.post_data or "")

    page.on("request", on_request)
    return posts


def choose_state(page: Page, name: str) -> None:
    page.locator(STATE_CONTROL).click()
    page.get_by_role("option", name=name, exact=True).click()


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("query", ["", "?state=GA", "?state=SC", "?state=AK"])
def test_c4_and_c5_are_readable_at_390_px(page: Page, query: str) -> None:
    """AC Phone width: every year's tick, bar label, marker label, band label and axis
    title inside 390 px, none over another, and no sideways scroll."""
    open_over_time(page, query)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for chart in (C4, C5):
        ticks = boxes(page, f"{chart} .ytick text")
        assert [b["text"] for b in ticks] == served_years(), chart
        drawn = [
            b
            for part in OVER_TIME_TEXTS
            for b in boxes(page, f"{chart} {part}")
            if b["w"] > 0 and b["text"]
        ]
        assert len(drawn) > len(ticks), chart  # bars and labels beside the ticks
        for i, a in enumerate(drawn):
            assert a["x"] >= 0 and a["x"] + a["w"] <= 390, (chart, a)
            for b in drawn[i + 1 :]:
                assert not overlaps(a, b), (chart, a, b)


@pytest.mark.plotlyjs_fetches(1)
def test_c5_bands_the_years_before_the_window(page: Page) -> None:
    open_over_time(page)
    notes = [b["text"] for b in boxes(page, f"{C5} .annotation-text")]
    band = labels.C5_BEFORE_BAND.format(pv_year_min=PV_FIRST).replace("<br>", "")
    assert notes == [band, band]
    expect(page.locator(f"{C5} .layer-below .shapelayer path")).to_have_count(1)


@pytest.mark.plotlyjs_fetches(1)
def test_a_state_change_writes_the_url_in_one_callback_and_back_and_forward_work(
    page: Page,
) -> None:
    open_over_time(page)
    posts = filter_posts(page)
    control = page.locator(STATE_CONTROL)
    top = control.bounding_box()
    assert top is not None
    choose_state(page, state_name("GA"))
    expect(page).to_have_url(url_pattern("?state=GA"))
    title = labels.C4_TITLE_STATE.format(state=state_name("GA"))
    expect(page.locator(f"{C4} .chart-title")).to_have_text(title)
    expect(page.locator(OVER_TIME_ROWS)).to_have_count(
        sum(1 for r in recorded("/v1/elections/states")["data"] if r["state_usps"] == "GA")
    )
    page.wait_for_timeout(SETTLE_MS)
    assert len(posts) == 1, posts
    # The re-render does not jump the page: the control stays in view.
    after = page.locator(STATE_CONTROL).bounding_box()
    assert after is not None and 0 <= after["y"] <= 844
    page.go_back()
    expect(page).to_have_url(url_pattern(""))
    expect(page.locator(f"{C4} .chart-title")).to_have_text(labels.C4_TITLE)
    page.go_forward()
    expect(page.locator(f"{C4} .chart-title")).to_have_text(title)


@pytest.mark.plotlyjs_fetches(1)
def test_a_pasted_state_and_year_url_narrows_t1_by_the_years_only(page: Page) -> None:
    open_over_time(page, "?state=GA&year_from=1900&pv=1")
    assert row_years(page) == years_shown(year_from=1900, pv_only=True)
    expect(page.locator(f"{C4} .chart-title")).to_have_text(
        labels.C4_TITLE_STATE.format(state=state_name("GA"))
    )
    assert [b["text"] for b in boxes(page, f"{C4} .ytick text")] == served_years()
    expect(page.locator(LEADER_ROWS)).to_have_count(len(served_years()))


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
def test_a_state_link_in_the_table_navigates_client_side(page: Page) -> None:
    open_over_time(page, "?state=GA")
    page.evaluate("window.__e2e_mark = 1")
    page.locator("#elections-over-time-table a[href='/state/GA']").first.click()
    expect(page).to_have_url(re.compile(r"/state/GA$"))
    assert page.evaluate("window.__e2e_mark") == 1


@pytest.mark.xfail(
    strict=True,
    reason="#496: the browser handles the fragment before Dash renders the chart",
)
@pytest.mark.plotlyjs_fetches(1)
def test_the_c4_fragment_scrolls_to_the_chart_after_dash_renders(page: Page) -> None:
    """Checked whether or not the C3 link ships (#436, owner): it does not, since the
    fragment does not land; #496 holds both."""
    page.goto("/elections#c4")
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.locator(f"{C4} .main-svg").first.wait_for()
    page.wait_for_timeout(SETTLE_MS)
    box = page.locator(f"{C4} .chart-title").bounding_box()
    assert box is not None and 0 <= box["y"] <= 844, box


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_c4_and_c5_keep_their_text_and_table(page: Page) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
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


@pytest.mark.aborted_chunk("async-dropdown")
def test_a_failed_dropdown_chunk_stops_logging(page: Page) -> None:
    """#456, D089, for the state control (#436): with dcc's dropdown chunk refused,
    the page logs a bounded number of errors and stops, and its tables render."""
    seen = watch_chunk_errors(page)
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_chunk_failure_stops(page, seen)
    expect(page.locator(OVER_TIME_ROWS)).to_have_count(len(served_years()))
