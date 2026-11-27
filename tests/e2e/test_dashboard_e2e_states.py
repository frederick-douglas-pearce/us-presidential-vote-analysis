"""Chart C11, the map on ``/states`` (#623, D121 as amended by D124), in a browser.

At 390 and 360 px: no sideways scroll, the geo frame and its 51 state paths inside the
figure, the colorbar drawn at its thickness with one numbered tick per ``tickvals``
entry, all inside the width and none over another, the page key inside the width, and
the long option wrapping; a drag that does not pan and a touch swipe that scrolls the
page; a hover and a click on Texas. A change of figure (URL, title, Texas's fill, the
table unchanged, only Dash's update requests), back and forward, and a document load
of ``?metric=``; a theme switch redrawing Texas in the resolved tokens' interpolation,
and the lowest- and highest-valued states in the ramp's end stops, with no request; a
blocked CDN and a blocked outline file each leaving the title, caption, pointer, page
key, control and table; and one outline request across a load,
a change, back and forward. No console error and no off-host request are asserted for
every test by ``conftest._browser_guard``.
"""

from __future__ import annotations

import itertools
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, Route, expect

from explore import charts, components, labels, state_view
from tests.e2e.dashboard_pages import (
    C11,
    C11_BAR,
    C11_COLORBAR,
    C11_FRAME,
    C11_KEY,
    C11_PATHS,
    C11_TICKS,
    PHONE_WIDTHS,
    RESOURCE_ERROR,
    STATES_HISTORY_ROWS,
    STATES_LIST_SUCCESS,
    STATES_METRIC,
    TOPOJSON_ERROR,
    TOPOJSON_PATH,
    UPDATE_PATH,
    assert_rendered,
    boxes,
)
from tests.e2e.test_dashboard_e2e_election import overlaps, token

pytestmark = pytest.mark.e2e

#: How long a change is given to fire anything further after it settled.
SETTLE_MS = 1000
#: The figure each metric is, the default first.
METRICS = list(state_view.HISTORY_KEYS)
DEFAULT = METRICS[0]
CHANGE = "state_electors_change"
#: The plotted graph's div, where plotly.js keeps the figure it drew.
GRAPH = f"{C11} .js-plotly-plot"


def open_map(page: Page, metric: str = DEFAULT, *, width: int = 390) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    search = "" if metric == DEFAULT else f"?metric={metric}"
    page.goto(f"/states{search}")
    assert_rendered(page, STATES_LIST_SUCCESS, width=width)
    page.locator(C11_PATHS).first.wait_for()
    page.locator(C11_TICKS).first.wait_for()


def drawn(page: Page) -> dict[str, Any]:
    """The trace plotly.js drew: its locations, values, bounds and colorbar."""
    found: dict[str, Any] = page.locator(GRAPH).evaluate(
        """gd => { const t = gd.data[0];
           return {locations: t.locations, z: t.z, zmin: t.zmin, zmax: t.zmax,
                   colorbar: t.colorbar}; }"""
    )
    return found


def state_path(page: Page, usps: str) -> Any:
    """``usps``' drawn path."""
    index: int = page.eval_on_selector_all(
        C11_PATHS, "(els, usps) => els.findIndex(el => el.__data__.loc === usps)", usps
    )
    assert index >= 0, usps
    return page.locator(C11_PATHS).nth(index)


def texas(page: Page) -> Any:
    """Texas's drawn path."""
    return state_path(page, "TX")


def fill(locator: Any) -> tuple[int, int, int]:
    value: str = locator.evaluate("el => getComputedStyle(el).fill")
    assert value.startswith("rgb(")
    r, g, b = (int(part) for part in value[4:-1].split(","))
    return r, g, b


def hex_rgb(value: str) -> tuple[float, float, float]:
    digits = value.strip().lstrip("#")
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return float(r), float(g), float(b)


def ramp_stops(page: Page, metric: str) -> list[tuple[float, float, float]]:
    """``metric``'s ramp, its three tokens resolved in the theme in effect."""
    ramp = charts.MAP_RAMPS[1 if metric == "state_pv_elections_count" else 0]
    return [hex_rgb(token(page, t.removeprefix("var(").rstrip(")"))) for t in ramp]


def expected_fill(page: Page, usps: str, metric: str) -> tuple[float, float, float]:
    """The color plotly.js should draw ``usps`` in: its value's position on the scale,
    the ramp's three resolved tokens interpolated linearly in RGB at it (D124)."""
    trace = drawn(page)
    value = trace["z"][trace["locations"].index(usps)]
    position = (value - trace["zmin"]) / (trace["zmax"] - trace["zmin"])
    stops = ramp_stops(page, metric)
    segment = min(int(position * (len(stops) - 1)), len(stops) - 2)
    t = position * (len(stops) - 1) - segment
    low, high = stops[segment], stops[segment + 1]
    r, g, b = (low[i] + (high[i] - low[i]) * t for i in range(3))
    return r, g, b


def assert_fill_is(page: Page, usps: str, metric: str) -> None:
    want = expected_fill(page, usps, metric)
    got = fill(state_path(page, usps))
    assert all(abs(a - b) <= 1 for a, b in zip(got, want, strict=True)), (got, want)


def assert_ends_are_the_end_stops(page: Page, metric: str) -> None:
    """The lowest-valued drawn state's fill is the ramp's first stop and the
    highest-valued one's its third, the resolved ``--chart-bin-*-1`` and ``-3``,
    within 1 per channel."""
    trace = drawn(page)
    stops = ramp_stops(page, metric)
    for bound, stop in ((trace["zmin"], stops[0]), (trace["zmax"], stops[-1])):
        usps = trace["locations"][trace["z"].index(bound)]
        got = fill(state_path(page, usps))
        assert all(abs(a - b) <= 1 for a, b in zip(got, stop, strict=True)), (
            usps,
            got,
            stop,
        )


def center(locator: Any) -> tuple[float, float]:
    box = locator.bounding_box()
    assert box is not None
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def table_text(page: Page) -> list[str]:
    texts: list[str] = page.locator(STATES_HISTORY_ROWS).all_inner_texts()
    return texts


def choose(page: Page, metric: str) -> None:
    page.locator(STATES_METRIC).click()
    page.get_by_role("option", name=labels.STATES_HISTORY_HEADERS[metric]).click()


def requests_of(page: Page) -> list[str]:
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    return seen


# --- phone width -----------------------------------------------------------------------


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("metric", METRICS)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_c11_is_readable_at_phone_width(page: Page, width: int, metric: str) -> None:
    """AC5 at 390 and 360 px, for every figure: no sideways scroll; the geo frame
    inside the figure and every state path inside the frame, each far smaller than
    it (an inverted ring would fill it, D121's #637 amendment); the colorbar's bar
    drawn at the figure's thickness (D124's bounds); one tick label per tick, each
    drawn, inside the width and none over another, the ends at the bar's ends; and the
    page key inside the width."""
    open_map(page, metric, width=width)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    trace = drawn(page)
    expect(page.locator(C11_PATHS)).to_have_count(len(trace["locations"]))
    graph = boxes(page, f"{C11} .chart-graph")[0]
    (frame,) = boxes(page, C11_FRAME)
    assert frame["w"] > 0 and frame["h"] > 0
    assert graph["x"] - 0.5 <= frame["x"]
    assert frame["x"] + frame["w"] <= graph["x"] + graph["w"] + 0.5
    assert graph["y"] - 0.5 <= frame["y"]
    assert frame["y"] + frame["h"] <= graph["y"] + graph["h"] + 0.5
    for path in boxes(page, C11_PATHS):
        assert path["w"] > 0 and path["h"] > 0
        assert frame["x"] - 1 <= path["x"] <= frame["x"] + frame["w"], path
        assert path["x"] + path["w"] <= frame["x"] + frame["w"] + 1, path
        assert frame["y"] - 1 <= path["y"] and path["y"] + path["h"] <= (
            frame["y"] + frame["h"] + 1
        ), path
        assert path["w"] * path["h"] < frame["w"] * frame["h"] / 4, path
    (bar,) = boxes(page, C11_BAR)
    assert bar["h"] == pytest.approx(trace["colorbar"]["thickness"], abs=0.5)
    assert bar["x"] >= 0 and bar["x"] + bar["w"] <= width
    ticks = boxes(page, C11_TICKS)
    assert [b["text"] for b in ticks] == trace["colorbar"]["ticktext"]
    assert len(ticks) == len(trace["colorbar"]["tickvals"])
    for tick in ticks:
        assert tick["w"] > 0, tick  # drawn, not hidden past the figure's edge
        assert tick["x"] >= 0 and tick["x"] + tick["w"] <= width, tick
    for a, b in itertools.combinations(ticks, 2):
        assert not overlaps(a, b), (a, b)
    first, last = ticks[0], ticks[-1]
    assert first["x"] <= bar["x"] <= first["x"] + first["w"]
    assert last["x"] <= bar["x"] + bar["w"] <= last["x"] + last["w"]
    for box in boxes(page, f"{C11_KEY} p"):
        assert box["x"] >= 0 and box["x"] + box["w"] <= width, box
    (colorbar,) = boxes(page, C11_COLORBAR)
    assert colorbar["y"] + colorbar["h"] <= frame["y"] + 0.5  # the bar above the map


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_the_longest_figure_s_name_wraps_in_the_control(page: Page, width: int) -> None:
    """The change's 70-character name, chosen and listed, wraps inside the width at
    390 and 360 px rather than being cut (owner, #623's plan gate)."""
    open_map(page, CHANGE, width=width)
    value = page.locator(f"{STATES_METRIC} .dash-dropdown-value")
    expect(value).to_have_text(labels.STATES_HISTORY_HEADERS[CHANGE])
    shown = value.evaluate("el => [el.scrollWidth, el.clientWidth]")
    assert shown[0] <= shown[1], shown
    page.locator(STATES_METRIC).click()
    option = page.get_by_role("option", name=labels.STATES_HISTORY_HEADERS[CHANGE])
    box = option.bounding_box()
    assert box is not None
    assert box["x"] >= 0 and box["x"] + box["width"] <= width, box
    widths = option.evaluate("el => [el.scrollWidth, el.clientWidth]")
    assert widths[0] <= widths[1], widths
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.plotlyjs_fetches(1)
def test_a_drag_does_not_pan_the_map(page: Page) -> None:
    open_map(page)
    path = texas(page)
    before = path.bounding_box()
    x, y = center(path)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 120, y + 40, steps=8)
    page.mouse.up()
    page.wait_for_timeout(SETTLE_MS)
    assert path.bounding_box() == before


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.browser_context_args(has_touch=True)
def test_a_touch_swipe_on_the_map_scrolls_the_page(page: Page) -> None:
    """A swipe that starts on a state scrolls the page (D121's phone probe), with the
    control that the swipe can see a trap, as C1's test has it."""
    open_map(page)
    path = texas(page)
    path.scroll_into_view_if_needed()
    x, y = center(path)
    at = f"document.elementFromPoint({x}, {y})"
    assert page.evaluate(f"() => {at}.closest('{C11} .geo') !== null")
    session = page.context.new_cdp_session(page)

    def swipe() -> None:
        session.send(
            "Input.dispatchTouchEvent",
            {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]},
        )
        for step in range(1, 16):
            session.send(
                "Input.dispatchTouchEvent",
                {"type": "touchMove", "touchPoints": [{"x": x, "y": y - step * 20}]},
            )
            page.wait_for_timeout(16)
        session.send(
            "Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}
        )

    page.evaluate(
        f"""() => {{
            window.__e2eTrap = event => event.preventDefault();
            {at}.addEventListener("touchmove", window.__e2eTrap, {{passive: false}});
        }}"""
    )
    before = page.evaluate("scrollY")
    swipe()
    page.wait_for_timeout(SETTLE_MS)
    assert page.evaluate("scrollY") == before
    page.evaluate(
        f"() => {at}.removeEventListener('touchmove', window.__e2eTrap,"
        " {passive: false})"
    )
    swipe()
    page.wait_for_function(f"scrollY > {before} + 50")


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_a_hover_and_a_click_on_texas_name_it(page: Page, width: int) -> None:
    """D121's #637 amendment: a hover on Texas shows its hover text, the table's cell,
    and a click returns its location, at 390 and 360 px."""
    open_map(page, width=width)
    path = texas(page)
    # The map can sit below an 844 px viewport (it did on CI at 360 px, where text
    # wraps taller); a pointer outside the viewport hovers nothing.
    path.scroll_into_view_if_needed()
    x, y = center(path)
    assert page.evaluate(
        f"() => document.elementFromPoint({x}, {y})?.closest('{C11} .geo') != null"
    )
    page.mouse.move(x, y)
    hover = page.locator(f"{C11} .hoverlayer .hovertext")
    expect(hover).to_contain_text("Texas")
    expect(hover).to_contain_text(labels.STATES_HISTORY_HEADERS[DEFAULT])
    # The table's cell for Texas under the default figure, read from the page's table.
    texas_row = page.locator(STATES_HISTORY_ROWS).filter(
        has=page.locator("td:first-child", has_text="Texas")
    )
    expect(texas_row).to_have_count(1)
    cell = texas_row.locator("td").nth(1 + METRICS.index(DEFAULT)).inner_text()
    assert cell.strip()
    expect(hover).to_contain_text(cell.strip())
    page.locator(GRAPH).evaluate(
        """gd => { window.__e2eClicks = [];
           gd.on('plotly_click', e => window.__e2eClicks.push(e.points[0].location)); }"""
    )
    page.mouse.click(x, y)
    page.wait_for_function("window.__e2eClicks.length > 0")
    assert page.evaluate("window.__e2eClicks") == ["TX"]


# --- a change of figure ---------------------------------------------------------------


@pytest.mark.plotlyjs_fetches(1)
def test_a_change_of_figure_redraws_the_map_alone_and_back_and_forward(
    page: Page,
) -> None:
    """AC2 and AC5: choosing a figure writes the query and redraws the map, Texas in
    its new color, with only Dash's update requests and the table's text unchanged;
    back and forward restore each view; and plotly.js fetches the outlines once."""
    outlines: list[str] = []
    page.on(
        "request",
        lambda r: outlines.append(r.url) if r.url.endswith(TOPOJSON_PATH) else None,
    )
    open_map(page)
    table = table_text(page)
    assert len(table) == 51
    title = page.locator(f"{C11} .chart-title")
    expect(title).to_have_text(labels.C11_TITLES[DEFAULT])
    before = fill(texas(page))
    seen = requests_of(page)
    choose(page, "state_first_election")
    expect(page).to_have_url(f"{page.url.split('?')[0]}?metric=state_first_election")
    expect(title).to_have_text(labels.C11_TITLES["state_first_election"])
    page.locator(C11_TICKS).first.wait_for()
    expect(page.locator(C11_TICKS).first).to_have_text("1824")
    assert fill(texas(page)) != before
    assert_fill_is(page, "TX", "state_first_election")
    assert table_text(page) == table
    page.wait_for_timeout(SETTLE_MS)
    assert seen and set(seen) == {f"POST {UPDATE_PATH}"}, seen
    page.go_back()
    expect(page).to_have_url(page.url.split("?")[0])
    expect(title).to_have_text(labels.C11_TITLES[DEFAULT])
    expect(page.locator(f"{STATES_METRIC} .dash-dropdown-value")).to_have_text(
        labels.STATES_HISTORY_HEADERS[DEFAULT]
    )
    page.locator(C11_TICKS).first.wait_for()
    assert table_text(page) == table
    page.go_forward()
    expect(title).to_have_text(labels.C11_TITLES["state_first_election"])
    expect(page.locator(f"{STATES_METRIC} .dash-dropdown-value")).to_have_text(
        labels.STATES_HISTORY_HEADERS["state_first_election"]
    )
    page.locator(C11_TICKS).first.wait_for()
    assert table_text(page) == table
    page.wait_for_timeout(SETTLE_MS)
    assert len(outlines) == 1, outlines
    assert urlsplit(outlines[0]).hostname == "127.0.0.1"


@pytest.mark.plotlyjs_fetches(1)
def test_a_document_load_of_a_figure_draws_it(page: Page) -> None:
    open_map(page, CHANGE)
    expect(page.locator(f"{C11} .chart-title")).to_have_text(labels.C11_TITLES[CHANGE])
    trace = drawn(page)
    assert [b["text"] for b in boxes(page, C11_TICKS)] == trace["colorbar"]["ticktext"]
    assert "0" in trace["colorbar"]["ticktext"]
    expect(page.locator(f"{STATES_METRIC} .dash-dropdown-value")).to_have_text(
        labels.STATES_HISTORY_HEADERS[CHANGE]
    )
    assert_fill_is(page, "TX", CHANGE)


# --- the theme --------------------------------------------------------------------------


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize("metric", [DEFAULT, "state_pv_elections_count"])
def test_c11_redraws_on_a_theme_switch_with_no_reload_or_request(
    page: Page, metric: str
) -> None:
    """[R-6]: Texas's fill is the RGB interpolation of the ramp's resolved tokens at
    its value's position, and the lowest- and highest-valued drawn states' fills the
    ramp's first and third stops, within 1 per channel, in Light and then in Dark,
    which the switch draws with no request. This ties the unit tests' linear-RGB model
    of the ramp to the fills plotly.js draws (interior sampling is #654)."""
    open_map(page, metric)
    assert_fill_is(page, "TX", metric)
    assert_ends_are_the_end_stops(page, metric)
    light = fill(texas(page))
    seen = requests_of(page)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    page.wait_for_function(
        f"""() => {{ const els = document.querySelectorAll('{C11_PATHS}');
            const tx = Array.from(els).find(el => el.__data__.loc === 'TX');
            return getComputedStyle(tx).fill !== 'rgb({", ".join(map(str, light))})'; }}"""
    )
    assert_fill_is(page, "TX", metric)
    assert_ends_are_the_end_stops(page, metric)
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


# --- what survives a failed load ------------------------------------------------------


def assert_page_text_stays(page: Page) -> None:
    """The chart's page text and the section around it: the title, caption, pointer,
    page key, control and table (AC5's "legend" is the page key, D124)."""
    expect(page.locator(f"{C11} .chart-title")).to_have_text(labels.C11_TITLES[DEFAULT])
    expect(page.locator(f"{C11} figcaption")).to_contain_text(labels.C11_CAPTION)
    expect(page.locator(f"{C11} figcaption a")).to_have_attribute(
        "href", "#states-history"
    )
    expect(page.locator(f"{C11_KEY} p")).to_have_text(
        [labels.C11_COLOR_NOTE, labels.C11_PHONE_NOTE]
    )
    expect(page.locator(STATES_METRIC)).to_be_visible()
    expect(page.locator(STATES_HISTORY_ROWS)).to_have_count(51)


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_c11_s_page_text_and_table_render(page: Page) -> None:
    page.goto("/states")
    assert_rendered(page, STATES_LIST_SUCCESS)
    memo = f"window.{charts.PLOTLYJS_MEMO}"
    page.wait_for_function(f"{memo} !== undefined")
    assert page.evaluate(f"async () => await {memo}") is False
    assert_page_text_stays(page)
    expect(page.locator(f"{C11} .js-plotly-plot")).to_have_count(0)


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
@pytest.mark.expected_console_error(TOPOJSON_ERROR)
@pytest.mark.expected_console_error(TOPOJSON_ERROR)
def test_with_the_outlines_blocked_c11_s_page_text_and_table_render(
    page: Page,
) -> None:
    """D121(i): a failed outline fetch follows D088's path, with no loop: one request,
    then Chrome's resource error and plotly.js's own line twice (D124 records the
    count), and the page text and table stay; no state is drawn."""
    outlines: list[str] = []

    def refuse(route: Route) -> None:
        outlines.append(route.request.url)
        route.abort()

    page.route(f"**{TOPOJSON_PATH}", refuse)
    page.goto("/states")
    assert_rendered(page, STATES_LIST_SUCCESS)
    page.locator(f"{C11} .main-svg").first.wait_for()
    assert_page_text_stays(page)
    page.wait_for_timeout(SETTLE_MS)
    assert len(outlines) == 1, outlines
    expect(page.locator(C11_PATHS)).to_have_count(0)
