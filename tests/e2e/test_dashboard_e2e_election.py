"""The one-election view in a browser: its earlier and later links (#324), an
unserved year's not-found state (#325), and chart C1 (#433) at the phone's width.

From a filtered view, the later link opens the next served year's own view
unfiltered, as a client-side navigation (a marker set on ``window`` before the click
survives it, which a full page load would clear), and back returns to the view it
left. ``conftest._browser_guard`` fails every test on an off-host request, or on any
console error other than those it names with ``expected_console_error``, each as many
times as named.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import dash
import pytest
from playwright.sync_api import Page, Request, expect

import explore.app  # noqa: F401  (registers the pages, whose not-found states it reads)
from explore import charts, components, labels
from tests.e2e.dashboard_pages import (
    ELECTION_EARLIER,
    ELECTION_LATER,
    ELECTION_SUCCESS,
    RESOURCE_ERROR,
    assert_rendered,
    recorded,
    step_years,
)

pytestmark = pytest.mark.e2e

#: The earlier and later links' landmark name (#324), apart from the site
#: navigation's (#448), read from the page module through its layout.
ELECTION_NAV_LABEL = dash.page_registry["pages.election"]["layout"].__globals__[
    "ELECTION_NAV_LABEL"
]

#: A filter the starting view applies, so the step shows that none carries over.
FILTERED = "?state=GA"


def assert_year(page: Page, year: int, search: str = "") -> None:
    """The view of ``year`` with exactly ``search``: the URL ends there."""
    expect(page).to_have_url(re.compile(re.escape(f"/election/{year}{search}") + "$"))
    assert_rendered(page, ELECTION_SUCCESS)
    expect(page.get_by_role("heading", level=1)).to_contain_text(str(year))


def test_the_later_link_opens_the_next_election_and_back_returns(page: Page) -> None:
    earlier, later = step_years()
    page.goto(f"/election/{earlier}{FILTERED}")
    assert_year(page, earlier, FILTERED)
    expect(page.get_by_role("navigation", name=ELECTION_NAV_LABEL)).to_have_count(1)
    link = page.locator(ELECTION_LATER)
    expect(link).to_have_attribute("href", f"/election/{later}")
    page.evaluate("window.__e2e_mark = 1")
    link.click()
    assert_year(page, later)
    assert page.evaluate("window.__e2e_mark") == 1
    expect(page.locator(ELECTION_EARLIER)).to_have_attribute(
        "href", f"/election/{earlier}"
    )
    page.go_back()
    assert_year(page, earlier, FILTERED)


@pytest.mark.plotlyjs_fetches(0)  # a not-found render mounts no chart (#433)
@pytest.mark.expected_console_error(
    "Failed to load resource: the server responded with a status of 404 (NOT FOUND)"
)
def test_an_unserved_year_loads_as_a_404_with_its_not_found_heading(page: Page) -> None:
    """#325: a shared link to an unserved year, opened directly. The document's own 404
    is the one console error, and the guard requires it exactly once. The title here
    is the server's ``<title>``, which the router's title then matches; the next test
    is what shows the tab following the router."""
    not_found = dash.page_registry["pages.election"]["not_found"]
    response = page.goto("/election/1825")
    assert response is not None and response.status == 404
    expect(page.get_by_role("heading", level=1)).to_have_text(not_found.heading)
    expect(page).to_have_title(not_found.title)
    expect(page.locator("#election-not-found")).to_contain_text(not_found.sentence)


def test_the_tab_follows_the_router_to_an_unserved_year(page: Page) -> None:
    """#325: the tab follows the year's validation, not the server's ``<title>``. From
    a served year, whose tab names it, a client-side navigation (as a ``dcc.Link``
    makes one: ``pushState``, then Dash's ``_dashprivate_pushstate`` event) loads no
    document, so only Dash's router, through ``follow_validation``'s title, can change
    the tab to the unserved year's not-found title."""
    not_found = dash.page_registry["pages.election"]["not_found"]
    earlier, _ = step_years()
    page.goto(f"/election/{earlier}")
    assert_year(page, earlier)
    expect(page).to_have_title(re.compile(re.escape(f"The {earlier} election")))
    page.evaluate("window.__e2e_mark = 1")
    page.evaluate(
        """() => {
            window.history.pushState({}, "", "/election/1825");
            window.dispatchEvent(new CustomEvent("_dashprivate_pushstate"));
        }"""
    )
    expect(page.get_by_role("heading", level=1)).to_have_text(not_found.heading)
    expect(page).to_have_title(not_found.title)
    assert page.evaluate("window.__e2e_mark") == 1  # no document load in between


# --- chart C1 (#433) -------------------------------------------------------------------

C1 = "#c1"
#: Each bar plotly drew, by trace: the electoral share first, then the popular vote.
EC_BARS = f"{C1} .barlayer .trace:nth-child(1) .point path"
PV_BARS = f"{C1} .barlayer .trace:nth-child(2) .point path"
#: Every text C1 draws on the plot: the bars' labels and the markers' labels.
PLOT_TEXTS = f"{C1} .barlayer .bartext, {C1} .scatterlayer .textpoint text"
#: Every other text C1 draws: tick labels, the axis title, the legend's entries and
#: the majority line's label.
CHART_TEXTS = ", ".join(
    f"{C1} {part}"
    for part in (
        ".ytick text",
        ".xtick text",
        ".g-xtitle text",
        ".legend .legendtext",
        ".annotation-text",
    )
)
#: The marker points (the markers' symbols, not their labels).
MARK_POINTS = f"{C1} .scatterlayer .trace .points path"
#: Long enough for a request the browser would make after a change to have gone out.
SETTLE_MS = 500


def names(year: int) -> list[str]:
    return [row["candidate"] for row in recorded(f"/v1/elections/{year}")["summary"]]


def open_c1(page: Page, year: int) -> None:
    page.goto(f"/election/{year}")
    assert_rendered(page, ELECTION_SUCCESS)
    page.locator(EC_BARS).first.wait_for()


def boxes(page: Page, selector: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = page.eval_on_selector_all(
        selector,
        """els => els.map(el => {
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height,
                    text: el.textContent};
        })""",
    )
    return found


def overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool(
        a["x"] < b["x"] + b["w"]
        and b["x"] < a["x"] + a["w"]
        and a["y"] < b["y"] + b["h"]
        and b["y"] < a["y"] + a["h"]
    )


def rgb(hex_color: str) -> str:
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


def first_ec_fill(page: Page) -> str:
    fill: str = page.locator(EC_BARS).first.evaluate("el => getComputedStyle(el).fill")
    return fill


@pytest.mark.plotlyjs_fetches(1)
def test_c1_on_2016_is_readable_at_390_px(page: Page) -> None:
    """AC Phone-width floor: 2016's seven candidates and both values, labeled, with no
    sideways scroll and no label over another; the electoral bar is each row's upper
    one, as the caption says."""
    open_c1(page, 2016)
    expect(page.locator(f"{C1} .chart-title")).to_have_text(
        labels.C1_TITLE.format(year=2016)
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ticks = [b["text"] for b in boxes(page, f"{C1} .ytick text")]
    assert ticks == names(2016)
    texts = boxes(page, PLOT_TEXTS)
    shown = [b["text"] for b in texts]
    # Seven electoral labels, two popular-vote labels, five markers.
    assert sorted(shown) == sorted(
        ["56.5%", "42.2%", "0.6%", "0.2%", "0.2%", "0.2%", "0.2%", "46.0%", "48.1%"]
        + [labels.C1_NO_FIGURE] * 5
    )
    others = boxes(page, CHART_TEXTS)
    # The premise: every kind of text was found: the row names, the x tick labels, the
    # axis title, the two legend entries and the two-line majority label.
    assert len([b for b in others if b["text"] in names(2016)]) == 7
    assert {"0%", "50%", "100%"} <= {b["text"] for b in others}
    assert any(b["text"] == labels.C1_X_AXIS for b in others)
    assert any(b["text"].startswith("Majority line") for b in others)
    assert len([b for b in others if "share" in b["text"]]) >= 2
    labeled = [b for b in texts + others if b["w"] > 0]
    for i, a in enumerate(labeled):
        assert a["x"] >= 0 and a["x"] + a["w"] <= 390, a
        for b in labeled[i + 1 :]:
            assert not overlaps(a, b), (a, b)
    expect(page.locator(f"{C1} .legend .traces")).to_have_count(2)
    ec = boxes(page, EC_BARS)[0]
    pv = boxes(page, PV_BARS)[0]
    assert ec["y"] + ec["h"] <= pv["y"] + 0.5  # Trump: electoral above popular
    # Each marker sits in its row's popular-vote slot: its offset from its row's tick
    # equals a drawn popular-vote bar's offset from its own (D091's (1 − bargap) / 4).
    ticks = boxes(page, f"{C1} .ytick text")

    def center(box: dict[str, Any]) -> float:
        return float(box["y"] + box["h"] / 2)

    slot = center(pv) - center(ticks[0])
    assert slot > 2  # the premise: the popular-vote bar is below its row's center
    marks = boxes(page, MARK_POINTS)
    assert len(marks) == 5
    for row, mark in zip(range(2, 7), marks, strict=True):
        assert abs(center(mark) - center(ticks[row]) - slot) <= 1.5, (row, mark)
    # The drawing fills its box, now and after a resize (#433's responsive check).
    for width in (390, 340):
        page.set_viewport_size({"width": width, "height": 844})
        page.wait_for_function(
            f"""() => {{
                const svg = document.querySelector("{C1} .main-svg");
                const box = document.querySelector("{C1} .chart-graph");
                return svg && Math.abs(svg.getBoundingClientRect().width
                    - box.getBoundingClientRect().width) < 1;
            }}"""
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.plotlyjs_fetches(1)
def test_c1_on_1860_draws_the_electoral_share_alone(page: Page) -> None:
    open_c1(page, 1860)
    expect(page.locator(f"{C1} .barlayer .trace")).to_have_count(1)
    expect(page.locator(f"{C1} .legend")).to_have_count(0)
    first, last = _window()
    expect(page.locator(f"{C1} figcaption")).to_contain_text(
        labels.C1_NO_PV_CAPTION.format(first=first, last=last, year=1860)
    )
    assert [b["text"] for b in boxes(page, f"{C1} .ytick text")] == names(1860)


def _window() -> tuple[int, int]:
    coverage = recorded("/v1/elections")["meta"]["provenance"]["coverage"]
    return coverage["pv_year_min"], coverage["pv_year_max"]


@pytest.mark.plotlyjs_fetches(1)
def test_c1_redraws_on_a_theme_switch_with_no_reload_or_request(page: Page) -> None:
    """AC Themes: drawn in the theme in effect, and redrawn in the other on a switch,
    with no reload (a marker on ``window`` survives) and no request."""
    open_c1(page, 2016)
    light = first_ec_fill(page)
    assert light == rgb(token(page, "--chart-1"))
    line = f"{C1} .shapelayer path"
    stroke = page.locator(line).first.evaluate("el => getComputedStyle(el).stroke")
    assert stroke == rgb(token(page, "--chart-reference"))
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    expect(page.locator(EC_BARS).first).not_to_have_css("fill", light)
    assert first_ec_fill(page) == rgb(token(page, "--chart-1"))
    stroke = page.locator(line).first.evaluate("el => getComputedStyle(el).stroke")
    assert stroke == rgb(token(page, "--chart-reference"))
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.browser_context_args(color_scheme="dark")
def test_c1_follows_a_dark_device_under_auto(page: Page) -> None:
    """AC Themes, the System (Auto) choice: with no saved choice, a device in dark mode
    draws C1 in the dark palette."""
    open_c1(page, 2016)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") is None
    assert page.evaluate("matchMedia('(prefers-color-scheme: dark)').matches")
    expect(page.locator(EC_BARS).first).to_have_css(
        "fill", rgb(token(page, "--chart-1"))
    )
    assert first_ec_fill(page) != rgb("#2a78d6")  # not the light palette's --chart-1


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.browser_context_args(has_touch=True)
def test_a_touch_swipe_on_c1_scrolls_the_page(page: Page) -> None:
    """AC Phone-width floor: touch never traps page scrolling. A swipe that starts on
    plotly's drag layer (where its pointer and touch listeners sit) scrolls the page.
    Raw touch events, which Chromium turns into a scroll as a finger's would be
    (``Input.synthesizeScrollGesture`` scrolls nothing in headless Chromium, on the chart
    or off it). The control first shows the swipe can see a trap: with a listener on the
    drag layer canceling ``touchmove``, as plotly's own drag handling would where it
    traps touch, the same swipe does not scroll. (``touch-action: none`` on the drag
    layer is no control: Chromium ignores it on an SVG ``rect``, and the swipe still
    scrolls.)"""
    open_c1(page, 2016)
    graph = page.locator(f"{C1} .chart-graph")
    graph.scroll_into_view_if_needed()
    box = graph.bounding_box()
    assert box is not None
    x, y = box["x"] + box["width"] * 0.7, box["y"] + min(box["height"] / 2, 300)
    # The premise: the swipe starts on plotly's drag layer, not beside the drawing.
    at = f"document.elementFromPoint({x}, {y})"
    assert page.evaluate(f"() => {at}.closest('{C1} .nsewdrag') !== null")
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

    # The control: a trapped swipe does not scroll.
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
    # The chart as shipped: the same swipe scrolls the page.
    page.evaluate(
        f"() => {at}.removeEventListener('touchmove', window.__e2eTrap,"
        " {passive: false})"
    )
    swipe()
    page.wait_for_function(f"scrollY > {before} + 50")


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_t3_the_title_and_caption_render(page: Page) -> None:
    """AC States: if plotly.js fails to load, T3 and the caption still render."""
    page.goto("/election/2016")
    assert_rendered(page, ELECTION_SUCCESS)
    memo = f"window.{charts.PLOTLYJS_MEMO}"
    page.wait_for_function(f"{memo} !== undefined")
    assert page.evaluate(f"async () => await {memo}") is False
    expect(page.locator(f"{C1} .chart-title")).to_have_text(
        labels.C1_TITLE.format(year=2016)
    )
    expect(page.locator(f"{C1} figcaption")).to_contain_text(labels.C1_BASES)
    expect(page.locator("#election-nation")).to_be_visible()
    expect(page.locator(f"{C1} .js-plotly-plot")).to_have_count(0)


def test_passing_through_a_chart_page_needs_no_marker(page: Page) -> None:
    """D091: the guard derives this test's plotly.js bound (one fetch per document,
    from a chart page), so stepping through two years' charts declares nothing."""
    earlier, later = step_years()
    page.goto(f"/election/{earlier}")
    assert_year(page, earlier)
    page.locator(EC_BARS).first.wait_for()
    page.locator(ELECTION_LATER).click()
    assert_year(page, later)
    page.locator(EC_BARS).first.wait_for()
    assert page.evaluate("typeof window.Plotly") == "object"
