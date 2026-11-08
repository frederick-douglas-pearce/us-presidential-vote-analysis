"""The chart foundation in a browser (#432), on ``serve.py``'s test chart page: before
C1 (#433), no production page renders a chart.

plotly.js is fetched from its CDN address only where a chart mounts, fulfilled from the
installed file by the browser guard, which counts every fetch (``plotlyjs_fetches``;
zero for every other test). A chart is drawn in the theme in effect, redrawn on a theme
switch with no reload and no server round trip, and its table pointer moves within the
page. If the CDN is blocked, the page, the chart's title, caption and pointer and its
table still render, with one console error and no loop: no graph mounts until plotly.js
has loaded, and the load is never retried within a document (#452, D088).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import charts, components, labels
from tests.e2e.conftest import plotlyjs_file, plotlyjs_url
from tests.e2e.dashboard_pages import ELECTIONS_SUCCESS, HOME_SUCCESS, assert_rendered
from tests.e2e.serve import (
    CHART_ID,
    CHART_PAGE,
    CHART_SUCCESS,
    CHART_TABLE,
    THEME_PROBE_CALLS,
    TWO_CHART_IDS,
    TWO_CHARTS_PAGE,
    TWO_CHARTS_SUCCESS,
)

pytestmark = pytest.mark.e2e

CHART = f"#{charts.dom_id(CHART_ID)}"
GRAPH = f"{CHART} .chart-graph .js-plotly-plot"
#: The first series' first bar: the trace with no pattern, so its fill is a color.
FIRST_BAR = f"{CHART} .barlayer .trace:first-child .point path"
UPDATE_PATH = "/_dash-update-component"
#: Long enough for a callback the browser would post after a change to have gone out.
SETTLE_MS = 500


def rgb(hex_color: str) -> str:
    """``#rrggbb`` or ``#rgb`` as the computed style writes it."""
    digits = hex_color.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


def token(page: Page, name: str) -> str:
    value: str = page.evaluate(
        "name => getComputedStyle(document.documentElement)"
        ".getPropertyValue(name).trim()",
        name,
    )
    return value


def first_fill(page: Page) -> str:
    fill: str = page.locator(FIRST_BAR).first.evaluate("el => getComputedStyle(el).fill")
    return fill


def painted(page: Page) -> dict[str, str]:
    """What the template paints, as the browser computed it: the paper (the main SVG's
    background; plotly draws no separate plot-area rectangle when the plot's color is
    the paper's) and an x-axis tick label's text."""
    found: dict[str, str] = page.evaluate(
        """(chart) => {
            const root = document.querySelector(chart);
            const style = el => getComputedStyle(el);
            return {
                paper: style(root.querySelector(".main-svg")).backgroundColor,
                tick: style(root.querySelector(".xtick text")).fill,
            };
        }""",
        CHART,
    )
    return found


def open_chart(page: Page) -> None:
    page.goto(CHART_PAGE)
    assert_rendered(page, f"#{CHART_SUCCESS}")
    page.locator(FIRST_BAR).first.wait_for()


def test_the_installed_plotlyjs_is_the_version_the_address_names() -> None:
    with plotlyjs_file().open(encoding="utf-8") as handle:
        banner = handle.read(200)
    match = re.search(r"\* plotly\.js v([0-9.]+)\n", banner)
    assert match, banner
    assert urlsplit(plotlyjs_url()).path == f"/plotly-{match.group(1)}.min.js"
    assert urlsplit(plotlyjs_url()).netloc == "cdn.plot.ly"


@pytest.mark.parametrize(
    ("path", "success"), [("/", HOME_SUCCESS), ("/elections", ELECTIONS_SUCCESS)]
)
def test_a_page_with_no_chart_fetches_no_plotlyjs(
    page: Page, path: str, success: str
) -> None:
    # The browser guard expects no fetch without the marker; this waits long enough
    # for one to have gone out.
    page.goto(path)
    assert_rendered(page, success)
    page.wait_for_timeout(SETTLE_MS)
    assert page.evaluate("typeof window.Plotly") == "undefined"


@pytest.mark.plotlyjs_fetches(1)
def test_a_chart_draws_in_the_theme_in_effect(page: Page) -> None:
    open_chart(page)
    expect(page.locator(f"{CHART} .chart-graph > div")).to_have_css(
        "visibility", "visible"
    )
    assert first_fill(page) == rgb(token(page, "--chart-1"))
    assert first_fill(page) == rgb("#2a78d6")  # the light palette: Chromium's default
    expect(page.locator(f"{CHART} .chart-title")).to_have_text("A test chart")
    expect(page.locator(GRAPH)).to_have_count(1)


@pytest.mark.plotlyjs_fetches(1)
def test_a_theme_switch_redraws_the_chart_with_no_reload_or_request(
    page: Page,
) -> None:
    open_chart(page)
    light = first_fill(page)
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    href = page.evaluate("location.href")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    expect(page.locator(FIRST_BAR).first).not_to_have_css("fill", light)
    assert first_fill(page) == rgb(token(page, "--chart-1"))
    # The template, not only the trace: in dark its paper and tick text differ from
    # plotly's own defaults (a white paper, #444 tick text), so a template plotly
    # ignored fails.
    assert painted(page) == {
        "paper": rgb(token(page, "--page")),
        "tick": rgb(token(page, "--text-secondary")),
    }
    assert token(page, "--page") == "#121212"
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1
    assert page.evaluate("location.href") == href  # the theme never enters the URL


@pytest.mark.plotlyjs_fetches(1)
def test_the_table_pointer_moves_within_the_page(page: Page) -> None:
    open_chart(page)
    pointer = page.locator(f"{CHART} figcaption a")
    expect(pointer).to_have_text(labels.CHART_TABLE_POINTER)
    expect(page.locator(f"{CHART} figcaption")).to_have_text(
        f"A caption. {labels.CHART_TABLE_POINTER}."
    )
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    pointer.click()
    page.wait_for_timeout(SETTLE_MS)
    assert page.evaluate("location.hash") == f"#{CHART_TABLE}"
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


@pytest.mark.plotlyjs_fetches(1)
def test_the_drawing_is_named_by_the_chart_title(page: Page) -> None:
    open_chart(page)
    expect(page.get_by_role("img", name="A test chart")).to_have_count(1)


#: Chrome's error for the refused script: the one console error a blocked CDN causes,
#: once per document (#452). Before #452, a mounted ``dcc.Graph`` rethrew its rejected
#: load on every render and Dash logged the script's error event without end.
BLOCKED_RESOURCE = "Failed to load resource: net::ERR_FAILED"
#: Long enough for the old loop to have logged hundreds of errors (12 by 300 ms, 256
#: by 2 s, #432's measure), so "bounded" is observed rather than assumed.
LOOP_WINDOW_MS = 2000
MOUNT = f"{CHART} .chart-graph"


def assert_blocked_chart(page: Page) -> None:
    """The chart page as a blocked CDN leaves it: the title, caption, pointer and table,
    an empty mount point, and no plotly.js."""
    expect(page.locator(f"{CHART} .chart-title")).to_have_text("A test chart")
    expect(page.locator(f"{CHART} figcaption")).to_contain_text("A caption.")
    expect(page.locator(f"{CHART} figcaption a")).to_have_text(
        labels.CHART_TABLE_POINTER
    )
    expect(page.locator(f"#{CHART_TABLE}")).to_be_visible()
    assert page.locator(MOUNT).evaluate("el => el.childElementCount") == 0
    expect(page.locator(f"{CHART} .js-plotly-plot")).to_have_count(0)
    assert page.evaluate("typeof window.Plotly") == "undefined"


#: Resolves to the document's settled plotly.js load (``true`` or ``false``), or
#: ``null`` before the mount callback has made one.
SETTLED_LOAD = f"async () => (window.{charts.PLOTLYJS_MEMO} === undefined ? null"
SETTLED_LOAD += f" : await window.{charts.PLOTLYJS_MEMO})"


def await_failed_load(page: Page) -> None:
    """Wait for the mount callback's load to be made and to have settled as failed, so
    a later step cannot join a still-pending load (#452's review)."""
    page.wait_for_function(f"window.{charts.PLOTLYJS_MEMO} !== undefined")
    assert page.evaluate(SETTLED_LOAD) is False


def wait_out_the_loop(page: Page) -> None:
    """A theme switch, then the old loop's window. The barrier is the theme probe's
    callback count: the switch is a re-render that a mounted graph's chart callback
    would answer, but on a blocked page there is no graph for it to answer. What
    observes a loop is the window together with the browser guard's exact count of
    console errors and fetches, which a repeat inside it would break."""
    calls = page.evaluate(f"window.{THEME_PROBE_CALLS} || 0")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    page.wait_for_function(f"(window.{THEME_PROBE_CALLS} || 0) > {calls}")
    page.wait_for_timeout(LOOP_WINDOW_MS)


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(BLOCKED_RESOURCE)
def test_a_blocked_cdn_leaves_the_page_and_its_table(page: Page) -> None:
    # The guard's exact count is the bound: one resource error, nothing repeated.
    page.goto(CHART_PAGE)
    assert_rendered(page, f"#{CHART_SUCCESS}")
    await_failed_load(page)
    wait_out_the_loop(page)
    assert_blocked_chart(page)


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(BLOCKED_RESOURCE)
def test_after_a_blocked_load_a_return_to_the_chart_makes_no_second_fetch(
    page: Page,
) -> None:
    # No retry within a document (D088): a reload is how a reader retries.
    page.goto(CHART_PAGE)
    assert_rendered(page, f"#{CHART_SUCCESS}")
    await_failed_load(page)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.NAV_LINK_IDS['elections']}").click()
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.go_back()
    assert_rendered(page, f"#{CHART_SUCCESS}")
    wait_out_the_loop(page)
    assert page.evaluate("window.__e2e_mark") == 1  # no document load
    assert_blocked_chart(page)


TWO = [f"#{charts.dom_id(c)}" for c in TWO_CHART_IDS]


@pytest.mark.plotlyjs_fetches(1)
def test_two_charts_on_a_page_share_one_load(page: Page) -> None:
    page.goto(TWO_CHARTS_PAGE)
    assert_rendered(page, f"#{TWO_CHARTS_SUCCESS}")
    for chart in TWO:
        page.locator(f"{chart} .barlayer .point path").first.wait_for()
        expect(page.locator(f"{chart} .js-plotly-plot")).to_have_count(1)
    page.wait_for_timeout(SETTLE_MS)
    cdn = plotlyjs_url()
    assert page.evaluate(
        "cdn => document.querySelectorAll(`script[src='${cdn}']`).length", cdn
    ) == 1


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(BLOCKED_RESOURCE)
def test_two_blocked_charts_cost_one_fetch_and_one_error(page: Page) -> None:
    page.goto(TWO_CHARTS_PAGE)
    assert_rendered(page, f"#{TWO_CHARTS_SUCCESS}")
    await_failed_load(page)
    wait_out_the_loop(page)
    for chart in TWO:
        mount = page.locator(f"{chart} .chart-graph")
        assert mount.evaluate("el => el.childElementCount") == 0
    assert page.evaluate("typeof window.Plotly") == "undefined"


@pytest.mark.plotlyjs_fetches(1)
def test_one_plotlyjs_script_one_fetch_and_the_apps_load(page: Page) -> None:
    """What it observes: exactly one script element with the CDN address, exactly one
    fetch (the browser guard), and the app's load kept as a Promise. It cannot tell
    which loader appended the script; that the graph mounts only after plotly.js has
    loaded is observed indirectly, by these exact counts (a graph mounted early makes
    dcc append a second script) and, on the blocked path, by the guard's exact count
    of console errors (#452)."""
    open_chart(page)
    page.wait_for_timeout(SETTLE_MS)
    cdn = plotlyjs_url()
    assert page.evaluate(
        "cdn => document.querySelectorAll(`script[src='${cdn}']`).length", cdn
    ) == 1
    assert page.evaluate(f"window.{charts.PLOTLYJS_MEMO} instanceof Promise") is True


@pytest.mark.plotlyjs_fetches(1)
def test_a_return_to_the_chart_draws_it_in_the_theme_chosen_away(page: Page) -> None:
    open_chart(page)
    light = first_fill(page)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.NAV_LINK_IDS['elections']}").click()
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    page.wait_for_function("getComputedStyle(document.documentElement)"
                           ".colorScheme === 'dark'")
    page.go_back()
    assert_rendered(page, f"#{CHART_SUCCESS}")
    page.locator(FIRST_BAR).first.wait_for()
    expect(page.locator(FIRST_BAR).first).not_to_have_css("fill", light)
    assert first_fill(page) == rgb(token(page, "--chart-1"))
    assert painted(page)["paper"] == rgb(token(page, "--page"))
    assert token(page, "--page") == "#121212"
    assert page.evaluate("window.__e2e_mark") == 1  # no document load


#: The mount callback's key in ``/_dash-dependencies``: its one output.
MOUNT_OUTPUT = '{"chart":["MATCH"],"type":"explore-chart-mount"}.children'

#: Finds the registered mount function and calls it for chart ``x1`` (#452).
CALL_MOUNT = """async ([output]) => {
    const deps = await (await fetch("/_dash-dependencies")).json();
    const spec = deps.find(d => d.output === output).clientside_function;
    const fn = window.dash_clientside[spec.namespace][spec.function_name];
    const result = await fn({}, {type: "explore-chart-mount", chart: "x1"});
    return result === window.dash_clientside.no_update ? "no_update" : result;
}"""


@pytest.mark.plotlyjs_fetches(1)
def test_the_registered_mount_function_returns_the_graph_once_loaded(
    page: Page,
) -> None:
    open_chart(page)
    result: Any = page.evaluate(CALL_MOUNT, [MOUNT_OUTPUT])
    assert result == {
        "type": "Graph",
        "namespace": "dash_core_components",
        "props": {
            "config": charts.CHART_CONFIG,
            "style": {"visibility": "hidden"},
            "id": charts.graph_id("x1"),
        },
    }


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(BLOCKED_RESOURCE)
def test_the_registered_mount_function_does_nothing_after_a_failed_load(
    page: Page,
) -> None:
    page.goto(CHART_PAGE)
    assert_rendered(page, f"#{CHART_SUCCESS}")
    await_failed_load(page)
    assert page.evaluate(CALL_MOUNT, [MOUNT_OUTPUT]) == "no_update"
    page.wait_for_timeout(SETTLE_MS)  # the guard then sees no second fetch
    # A script that lands after the load gave up serves the next mount (#452's review):
    # window.Plotly is checked before the memo, on every call.
    page.evaluate("window.Plotly = {}")
    result: Any = page.evaluate(CALL_MOUNT, [MOUNT_OUTPUT])
    assert result["type"] == "Graph"
    assert result["props"]["id"] == charts.graph_id("x1")


#: The chart callback's key in ``/_dash-dependencies``: its two outputs.
CALLBACK_OUTPUT = (
    '..{"chart":["MATCH"],"type":"explore-chart-graph"}.figure'
    '...{"chart":["MATCH"],"type":"explore-chart-graph"}.style..'
)


@pytest.mark.plotlyjs_fetches(1)
def test_the_registered_callback_resolves_without_touching_its_source(
    page: Page,
) -> None:
    """The JS itself (#432's review), as Dash registered it: found through
    ``_dash-dependencies`` (a Dash-private shape, acceptable in this advisory suite, as
    the site navigation's test does) and called with a test source."""
    open_chart(page)
    result: dict[str, Any] = page.evaluate(
        """async ([output]) => {
            const deps = await (await fetch("/_dash-dependencies")).json();
            const spec = deps.find(d => d.output === output).clientside_function;
            const fn = window.dash_clientside[spec.namespace][spec.function_name];
            const noUpdate = window.dash_clientside.no_update;
            const source = {data: [{marker: {color: "var(--chart-1)"}, name: "A"}],
                            layout: {}};
            const before = JSON.stringify(source);
            const waiting = fn(source, null);
            const drawn = fn(source, "light");
            let unset = null;
            try { fn({data: [{marker: {color: "var(--nope)"}}]}, "light"); }
            catch (error) { unset = String(error.message); }
            return {
                waiting: waiting.every(v => v === noUpdate) && waiting.length === 2,
                unchanged: JSON.stringify(source) === before,
                color: drawn[0].data[0].marker.color,
                name: drawn[0].data[0].name,
                style: drawn[1],
                unset,
            };
        }""",
        [CALLBACK_OUTPUT],
    )
    assert result["waiting"] is True
    assert result["unchanged"] is True
    assert result["color"] == token(page, "--chart-1")
    assert result["name"] == "A"
    assert result["style"] == {"visibility": "visible"}
    assert result["unset"] == "chart token --nope is unset"
