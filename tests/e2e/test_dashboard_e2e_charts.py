"""The chart foundation in a browser (#432), on ``serve.py``'s test chart page: before
C1 (#433), no production page renders a chart.

plotly.js is fetched from its CDN address only where a chart mounts, fulfilled from the
installed file by the browser guard, which counts every fetch (``plotlyjs_fetches``;
zero for every other test). A chart is drawn in the theme in effect, redrawn on a theme
switch with no reload and no server round trip, and its table pointer moves within the
page. If the CDN is blocked, the page, the chart's title and caption and its table still
render, though Dash then logs an error without end (D087's residual).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import charts, components, labels
from tests.e2e.conftest import plotlyjs_file, plotlyjs_url
from tests.e2e.dashboard_pages import ELECTIONS_SUCCESS, HOME_SUCCESS, assert_rendered
from tests.e2e.serve import CHART_ID, CHART_PAGE, CHART_SUCCESS, CHART_TABLE

pytestmark = pytest.mark.e2e

CHART = f"#{charts.dom_id(CHART_ID)}"
GRAPH = f"{CHART} .chart-graph .js-plotly-plot"
#: The first series' first bar: the trace with no pattern, so its fill is a color.
FIRST_BAR = f"{CHART} .barlayer .trace:first-child .point path"
UPDATE_PATH = "/_dash-update-component"
#: Long enough for a callback the browser would post after a change to have gone out.
SETTLE_MS = 500


def rgb(hex_color: str) -> str:
    """``#rrggbb`` as the computed style writes it."""
    digits = hex_color.strip().lstrip("#")
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
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    expect(page.locator(FIRST_BAR).first).not_to_have_css("fill", light)
    assert first_fill(page) == rgb(token(page, "--chart-1"))
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


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


#: Chrome's error for the refused script, once.
BLOCKED_RESOURCE = "Failed to load resource: net::ERR_FAILED"
#: dcc's lazy graph rethrows its rejected load on every render and Dash's error
#: boundary remounts it, so Dash logs the script's error event without end, about 130
#: times a second, the same with a bare ``dcc.Graph`` and no callback: Dash 4.4.1's own
#: behavior, an accepted residual of #432 (D087) with a follow-up before C1.
BLOCKED_EVENT = "Event"


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(BLOCKED_RESOURCE)
@pytest.mark.expected_console_error(BLOCKED_EVENT, repeats=True)
def test_a_blocked_cdn_leaves_the_page_and_its_table(page: Page) -> None:
    page.goto(CHART_PAGE)
    assert_rendered(page, f"#{CHART_SUCCESS}")
    page.wait_for_timeout(SETTLE_MS)
    expect(page.locator(f"{CHART} .chart-title")).to_have_text("A test chart")
    expect(page.locator(f"{CHART} figcaption")).to_contain_text("A caption.")
    expect(page.locator(f"#{CHART_TABLE}")).to_be_visible()
    expect(page.locator(FIRST_BAR)).to_have_count(0)
    assert page.evaluate("typeof window.Plotly") == "undefined"
