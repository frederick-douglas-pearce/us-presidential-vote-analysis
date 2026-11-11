"""The election pages in a browser: the overview and its two subpages (#465), their
earlier and later links (#324), an unserved year's not-found state (#325), and charts
C1 (#433) and C3 (#435) at the phone's width.

From a filtered view, the later link opens the next served year's own view
unfiltered, as a client-side navigation (a marker set on ``window`` before the click
survives it, which a full page load would clear), and back returns to the view it
left. ``conftest._browser_guard`` fails every test on an off-host request, or on any
console error other than those it names with ``expected_console_error``, each as many
times as named.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

import dash
import pytest
from playwright.sync_api import Page, Request, expect

import explore.app  # (registers the pages, whose not-found states it reads)
from explore import charts, components, election_view, labels
from tests.dashboard_fixtures import RECORDED_FILES
from tests.e2e.dashboard_pages import (
    ELECTION_EARLIER,
    ELECTION_LATER,
    ELECTION_SUCCESS,
    ELECTIONS,
    FIRST,
    LAST,
    PER_CAPITA_SUCCESS,
    RESOURCE_ERROR,
    SECTIONS,
    STATES_NOT_FOUND,
    STATES_SUCCESS,
    assert_rendered,
    composited,
    contrast_ratio,
    recorded,
    step_years,
)

pytestmark = pytest.mark.e2e

#: The states page's earlier and later links' landmark name (#324, #465), apart from
#: the site navigation's (#448).
STATES_NAV_LABEL = labels.ELECTION_NAV_SECTION_LABEL.format(
    section=labels.SECTION_STATES
)

#: A filter the starting view applies, so the step shows that none carries over.
FILTERED = "?state=GA"

#: Each election page's path suffix and success marker (#465).
PAGES = {
    election_view.OVERVIEW: ELECTION_SUCCESS,
    election_view.STATES: STATES_SUCCESS,
    election_view.PER_CAPITA: PER_CAPITA_SUCCESS,
}


def assert_year(
    page: Page, year: int, search: str = "", section: str = election_view.OVERVIEW
) -> None:
    """The page ``section`` of ``year`` with exactly ``search``: the URL ends there."""
    expect(page).to_have_url(
        re.compile(re.escape(f"/election/{year}{section}{search}") + "$")
    )
    assert_rendered(page, PAGES[section])
    expect(page.get_by_role("heading", level=1)).to_contain_text(str(year))


def assert_section(page: Page, section: str) -> None:
    """The section links mark ``section`` as the page being read, by text with
    ``aria-current="page"``, and link the other two; the site navigation marks
    Elections (#448)."""
    nav = page.get_by_role("navigation", name=labels.ELECTION_SECTIONS_LABEL)
    expect(nav).to_have_count(1)
    current = nav.locator('[aria-current="page"]')
    expect(current).to_have_text(election_view.SECTION_TEXT[section])
    expect(nav.get_by_role("link")).to_have_count(2)
    expect(page.locator(f"#{components.SITE_NAV_ID} [aria-current=true]")).to_have_text(
        labels.NAV_ELECTIONS
    )


def test_the_later_link_opens_the_next_election_and_back_returns(page: Page) -> None:
    """#324's test, on the states page since #465: from a filtered view, the later
    link opens the same page of the next year, unfiltered, and back returns."""
    earlier, later = step_years()
    states = election_view.STATES
    page.goto(f"/election/{earlier}{states}{FILTERED}")
    assert_year(page, earlier, FILTERED, states)
    expect(page.get_by_role("navigation", name=STATES_NAV_LABEL)).to_have_count(1)
    link = page.locator(ELECTION_LATER)
    expect(link).to_have_attribute("href", f"/election/{later}{states}")
    page.evaluate("window.__e2e_mark = 1")
    link.click()
    assert_year(page, later, section=states)
    assert page.evaluate("window.__e2e_mark") == 1
    expect(page.locator(ELECTION_EARLIER)).to_have_attribute(
        "href", f"/election/{earlier}{states}"
    )
    page.go_back()
    assert_year(page, earlier, FILTERED, states)


@pytest.mark.plotlyjs_fetches(1)  # the overview's C1, once for the one document
def test_the_overview_and_its_subpages_are_one_client_side_chain(page: Page) -> None:
    """#465: the overview shows the panel, C1 and T3 and neither T2 nor T6; the section
    links move to each subpage and back and forward with no document load, the URL,
    the tab, the section mark and the site mark following."""
    year, _ = step_years()
    page.goto(f"/election/{year}")
    assert_year(page, year)
    for shown in ("#election-panel", "#c1", "#election-nation"):
        expect(page.locator(shown)).to_have_count(1)
    for absent in ("#election-states", "#election-per-capita"):
        expect(page.locator(absent)).to_have_count(0)
    assert_section(page, election_view.OVERVIEW)
    page.evaluate("window.__e2e_mark = 1")
    nav = page.get_by_role("navigation", name=labels.ELECTION_SECTIONS_LABEL)
    titles = {
        election_view.OVERVIEW: f"The {year} election",
        election_view.STATES: f"The {year} election: results by state",
        election_view.PER_CAPITA: f"The {year} election: people per electoral vote",
    }

    def landed(section: str) -> None:
        """The page ``section``: its URL, success marker, tab, and both marks."""
        assert_year(page, year, section=section)
        expect(page).to_have_title(re.compile("^" + re.escape(titles[section]) + " — "))
        assert_section(page, section)

    landed(election_view.OVERVIEW)
    for section in (election_view.STATES, election_view.PER_CAPITA):
        nav.get_by_role("link", name=election_view.SECTION_TEXT[section]).click()
        landed(section)
        expect(page.locator("#c1")).to_have_count(0)
        # C3 is the per-capita page's alone (#435).
        expect(page.locator("#c3")).to_have_count(
            1 if section == election_view.PER_CAPITA else 0
        )
    page.go_back()
    landed(election_view.STATES)
    page.go_back()
    landed(election_view.OVERVIEW)
    page.go_forward()
    landed(election_view.STATES)
    assert page.evaluate("window.__e2e_mark") == 1  # no document load in between
    assert (
        page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        <= 0
    )


def test_a_state_filter_change_on_the_states_page_and_back(page: Page) -> None:
    """#465: T2's filters on its own page still write the URL, and back undoes it."""
    year, _ = step_years()
    page.goto(f"/election/{year}/states")
    assert_year(page, year, section=election_view.STATES)
    page.evaluate("window.__e2e_mark = 1")
    page.locator("#election-state").click()
    page.keyboard.type("Georgia")
    page.keyboard.press("Enter")
    assert_year(page, year, "?state=GA", election_view.STATES)
    expect(page.locator("#election-states tbody tr td:first-child")).to_contain_text(
        ["Georgia"]
    )
    page.go_back()
    assert_year(page, year, section=election_view.STATES)
    assert page.evaluate("window.__e2e_mark") == 1


def test_an_old_filtered_overview_link_lands_on_the_states_page(page: Page) -> None:
    """#465: a link shared before the split, loaded as a document, is redirected (302)
    to the states page with its filter applied."""
    response = page.goto("/election/2016?state=GA")
    assert response is not None and response.status == 200
    assert_year(page, 2016, "?state=GA", election_view.STATES)
    expect(page.locator("#election-states tbody tr td:first-child")).to_contain_text(
        ["Georgia"]
    )
    rows = page.locator("#election-states tbody tr")
    expect(rows).to_have_count(
        sum(r["state_usps"] == "GA" for r in recorded("/v1/elections/2016")["data"])
    )


@pytest.mark.plotlyjs_fetches(0)  # a not-found render mounts no chart (#433)
@pytest.mark.expected_console_error(
    "Failed to load resource: the server responded with a status of 404 (NOT FOUND)"
)
def test_an_unserved_year_reads_as_not_found_on_the_states_page(page: Page) -> None:
    not_found = dash.page_registry["pages.election_states"]["not_found"]
    response = page.goto("/election/1825/states")
    assert response is not None and response.status == 404
    expect(page.get_by_role("heading", level=1)).to_have_text(not_found.heading)
    expect(page).to_have_title(not_found.title)
    expect(page.locator(STATES_NOT_FOUND)).to_contain_text(not_found.sentence)
    expect(page.locator(SECTIONS)).to_have_count(0)


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


# --- the earlier-and-later bar (#464) ----------------------------------------------

#: The bar and its links, by ``election_view``'s ids and ``labels``' wording.
BAR = f"#{election_view.NAV_ID}"
EARLIER_LINK: str = labels.EARLIER_LINK
LATER_LINK: str = labels.LATER_LINK
THEME_KEY = explore.app.THEME_STORAGE_KEY

#: What the browser measures of the bar: each box in CSS px, the content box inside
#: the bar's border and padding, each link's text line count (the client rects of a
#: Range over its text, so a wrapped text counts two however its box is drawn), the
#: page's sideways overflow, the site header's bottom and the H1's top.
BAR_MEASURE = """() => {
    const bar = document.querySelector(__BAR__);
    const box = e => { const r = e.getBoundingClientRect();
        return {left: r.left, right: r.right, top: r.top, bottom: r.bottom}; };
    const s = getComputedStyle(bar);
    const outer = box(bar);
    const lines = e => {
        const walker = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
        let count = 0;
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const range = document.createRange();
            range.selectNodeContents(node);
            const tops = new Set([...range.getClientRects()].map(r => Math.round(r.top)));
            count += tops.size;
        }
        return count;
    };
    const links = [...bar.querySelectorAll("a")].map(a => ({
        id: a.id, box: box(a), lines: lines(a),
    }));
    const main = document.querySelector("main");
    return {
        bar: outer,
        content: {
            left: outer.left + parseFloat(s.borderLeftWidth) + parseFloat(s.paddingLeft),
            right: outer.right - parseFloat(s.borderRightWidth)
                - parseFloat(s.paddingRight),
        },
        links,
        overflow: document.documentElement.scrollWidth
            - document.documentElement.clientWidth,
        header: box(document.querySelector("header")).bottom,
        h1: box(document.querySelector("h1")).top,
        inHeader: bar.closest("header") !== null,
        firstHeading: main.querySelector("h1, h2, h3, h4, h5, h6").tagName,
        firstInMain: main.querySelector("#__PAGE__ > :not(script):not([id$='-url'])")
            === bar,
    };
}"""


def bar_measure(page: Page, section: str = election_view.OVERVIEW) -> dict[str, Any]:
    script = BAR_MEASURE.replace("__BAR__", json.dumps(BAR)).replace(
        "__PAGE__", PAGES[section].removeprefix("#")
    )
    found: dict[str, Any] = page.evaluate(script)
    return found


def middle_year() -> int:
    """A served year with a served year on each side whose view is recorded."""
    served = sorted(e["year"] for e in ELECTIONS["data"])
    for year in served[1:-1]:
        if all(
            f"/v1/elections/{year}{tail}" in RECORDED_FILES
            for tail in ("", "/per-capita")
        ):
            return int(year)
    raise AssertionError("no recorded served year with a neighbor on each side")


def open_year(
    page: Page,
    year: int,
    theme: str,
    width: int,
    section: str = election_view.OVERVIEW,
) -> None:
    """The page ``section`` of ``year`` under an explicit ``theme`` choice at
    ``width``."""
    page.add_init_script(
        f"localStorage.setItem({json.dumps(THEME_KEY)}, {json.dumps(theme)});"
    )
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"/election/{year}{section}")
    # assert_rendered checks 390 px, so a wide view waits on the marker itself.
    page.locator(PAGES[section]).wait_for()
    assert page.evaluate("document.documentElement.dataset.theme") == theme


def disjoint(a: dict[str, Any], b: dict[str, Any]) -> float:
    """The gap between two boxes, positive when they neither touch nor overlap."""
    return float(
        max(
            b["left"] - a["right"],
            a["left"] - b["right"],
            b["top"] - a["bottom"],
            a["top"] - b["bottom"],
        )
    )


def inside(inner: dict[str, Any], outer: dict[str, Any]) -> bool:
    return bool(
        inner["left"] >= outer["left"] - 0.5
        and inner["right"] <= outer["right"] + 0.5
        and inner["top"] >= outer["top"] - 0.5
        and inner["bottom"] <= outer["bottom"] + 0.5
    )


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("section", election_view.SECTIONS)  # every page (#465)
def test_the_bar_sets_its_two_links_apart_above_the_heading(
    page: Page, theme: str, width: int, section: str
) -> None:
    year = middle_year()
    open_year(page, year, theme, width, section)
    found = bar_measure(page, section)
    earlier, later = found["links"]
    assert [earlier["id"], later["id"]] == [ELECTION_EARLIER[1:], ELECTION_LATER[1:]]
    # Two links: a positive gap between them, both inside the box, one line each.
    assert disjoint(earlier["box"], later["box"]) > 0, found
    assert inside(earlier["box"], found["bar"]) and inside(later["box"], found["bar"])
    assert earlier["lines"] == 1 and later["lines"] == 1, found
    # Each on its side, on one row or two.
    assert abs(earlier["box"]["left"] - found["content"]["left"]) <= 0.5, found
    assert abs(later["box"]["right"] - found["content"]["right"]) <= 0.5, found
    # Above the heading, outside the site header and apart from it, and the page's
    # first heading is still the H1.
    assert found["bar"]["bottom"] <= found["h1"], found
    assert not found["inHeader"] and found["bar"]["top"] - found["header"] >= 16, found
    assert found["firstInMain"] and found["firstHeading"] == "H1", found
    assert found["overflow"] <= 0, found
    width_ = page.locator(BAR).evaluate("e => getComputedStyle(e).borderTopWidth")
    assert float(width_.removesuffix("px")) >= 1
    # The chevrons are no part of either link's name.
    neighbors = election_view.neighbours(ELECTIONS, year)
    for text in (
        EARLIER_LINK.format(year=neighbors.earlier),
        LATER_LINK.format(year=neighbors.later),
    ):
        expect(page.get_by_role("link", name=text, exact=True)).to_have_count(1)
    if width == 390:
        rows = "one row" if earlier["box"]["top"] == later["box"]["top"] else "two rows"
        print(f"#464 bar at 390 px ({theme}): {rows}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_bar_keeps_its_links_inside_at_320_px(page: Page, theme: str) -> None:
    open_year(page, middle_year(), theme, 320)
    found = bar_measure(page)
    assert found["overflow"] <= 0, found
    for link in found["links"]:
        assert inside(link["box"], found["bar"]) and link["lines"] == 1, found


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("year", "side"), [(FIRST, "later"), (LAST, "earlier")])
def test_a_year_at_either_end_keeps_its_one_link_on_its_side(
    page: Page, year: int, side: str, theme: str, width: int
) -> None:
    open_year(page, year, theme, width)
    found = bar_measure(page)
    (link,) = found["links"]
    if side == "later":
        assert link["id"] == ELECTION_LATER[1:]
        assert abs(link["box"]["right"] - found["content"]["right"]) <= 0.5, found
    else:
        assert link["id"] == ELECTION_EARLIER[1:]
        assert abs(link["box"]["left"] - found["content"]["left"]) <= 0.5, found


def focus_earlier(page: Page) -> None:
    """Focus the earlier link from the keyboard, so ``:focus-visible`` applies."""
    page.locator(f"#{components.THEME_BUTTON_IDS['light']}").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == ELECTION_EARLIER[1:]


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_forced_colors_keep_the_edge_the_links_and_the_focus_ring(
    page: Page, scheme: str
) -> None:
    """In both forced palettes (Chromium's emulation): the box's edge is a solid
    border at least 1 px wide, and it, both links and a focused link's ring each
    reach 3:1 against the page's backdrop, the nearest opaque background (body)."""
    page.emulate_media(color_scheme=scheme, forced_colors="active")  # type: ignore[arg-type]
    page.goto(f"/election/{middle_year()}")
    assert_rendered(page, ELECTION_SUCCESS)
    focus_earlier(page)
    painted = page.evaluate(
        """bar => {
            const nav = document.querySelector(bar);
            const s = getComputedStyle(nav);
            const links = [...nav.querySelectorAll("a")].map(a => getComputedStyle(a).color);
            const ring = getComputedStyle(document.activeElement);
            return {
                width: parseFloat(s.borderTopWidth), style: s.borderTopStyle,
                edge: s.borderTopColor, links,
                ring: ring.outlineColor, ringStyle: ring.outlineStyle,
                backdrop: getComputedStyle(document.body).backgroundColor,
            };
        }""",
        BAR,
    )
    assert painted["width"] >= 1 and painted["style"] == "solid", painted
    assert painted["ringStyle"] == "solid", painted
    # contrast_ratio refuses a translucent or non-rgb() color, so a transparent edge
    # or link fails rather than reading as black. Chromium draws the forced ring in a
    # translucent system color, so the ring is measured as it lands on the backdrop,
    # where a transparent one becomes the backdrop and fails at 1:1.
    ring = composited(painted["ring"], painted["backdrop"])
    for color in (painted["edge"], *painted["links"], ring):
        assert contrast_ratio(color, painted["backdrop"]) >= 3.0, (color, painted)


def test_tab_reaches_the_bar_first_in_the_page_content(page: Page) -> None:
    """From the top of the document: the site navigation, the theme toggle, then the
    earlier link and the later, each target at least 24 px tall."""
    page.goto(f"/election/{middle_year()}")
    assert_rendered(page, ELECTION_SUCCESS)
    expected = [
        *components.NAV_LINK_IDS.values(),
        components.NAV_API_DOCS_ID,
        *components.THEME_BUTTON_IDS.values(),
        ELECTION_EARLIER[1:],
        ELECTION_LATER[1:],
    ]
    order = []
    for _ in expected:
        page.keyboard.press("Tab")
        order.append(page.evaluate("document.activeElement.id"))
    assert order == expected
    for link in (ELECTION_EARLIER, ELECTION_LATER):
        height = page.locator(link).evaluate("e => e.getBoundingClientRect().height")
        assert height >= 24, (link, height)


# --- chart C3 (#435) ------------------------------------------------------------------

C3 = "#c3"
C3_BARS = f"{C3} .barlayer .trace .point path"
C3_PLOT_TEXTS = f"{C3} .barlayer .bartext, {C3} .scatterlayer .textpoint text"
C3_CHART_TEXTS = ", ".join(
    f"{C3} {part}" for part in (".ytick text", ".g-xtitle text", ".legend .legendtext")
)
#: The selected state's mark: the first scatter trace, drawn before the markers.
C3_SELECTED = f"{C3} .scatterlayer .trace:first-child .points path"
#: The two bar series: plain (first when drawn) and striped.
C3_STRIPED = f"{C3} .barlayer .trace:last-child .point path"
C3_PLAIN = f"{C3} .barlayer .trace:first-child .point path"


def c3_order(year: int) -> list[str]:
    """C3's rows for ``year``, by the page's rule (drawn by ratio, most first, ties by
    name; then the rest by name), from the recorded response."""
    rows = recorded(f"/v1/elections/{year}/per-capita")["data"]
    drawn = sorted(
        (r for r in rows if isinstance(r["persons_per_electoral_vote"], float)),
        key=lambda r: (-r["persons_per_electoral_vote"], r["state"]),
    )
    rest = sorted((r for r in rows if r not in drawn), key=lambda r: r["state"])
    return [r["state"] for r in drawn + rest]


def open_c3(page: Page, year: int, query: str = "") -> None:
    page.goto(f"/election/{year}/per-capita{query}")
    assert_rendered(page, PER_CAPITA_SUCCESS)
    page.locator(f"{C3} .main-svg").first.wait_for()
    page.locator(f"{C3} .ytick text").first.wait_for()


def assert_c3_readable(page: Page, year: int) -> list[dict[str, Any]]:
    """Every state's row name and every drawn label inside 390 px, none over another,
    no sideways scroll; returns the tick boxes."""
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ticks = boxes(page, f"{C3} .ytick text")
    assert [b["text"] for b in ticks] == c3_order(year)
    texts = boxes(page, C3_PLOT_TEXTS)
    others = boxes(page, C3_CHART_TEXTS)
    assert any(b["text"] == labels.C3_X_AXIS for b in others)
    labeled = [b for b in texts + others if b["w"] > 0]
    for i, a in enumerate(labeled):
        assert a["x"] >= 0 and a["x"] + a["w"] <= 390, a
        for b in labeled[i + 1 :]:
            assert not overlaps(a, b), (a, b)
    return ticks


def center(box: dict[str, Any]) -> float:
    return float(box["y"] + box["h"] / 2)


@pytest.mark.plotlyjs_fetches(1)
def test_c3_on_2024_is_readable_at_390_px(page: Page) -> None:
    """AC Shared: all 51 entries legible at 390 px; each row one bar centered on its
    row name; the one legend entry (every bar is on present-day borders)."""
    open_c3(page, 2024)
    expect(page.locator(f"{C3} .chart-title")).to_have_text(
        labels.C3_TITLE.format(year=2024, census_year="2020")
    )
    ticks = assert_c3_readable(page, 2024)
    assert len(ticks) == 51
    bars = boxes(page, C3_BARS)
    assert len(bars) == 51
    texts = [b["text"] for b in boxes(page, f"{C3} .barlayer .bartext")]
    assert len(texts) == 51 and "732,189" in texts and "192,284" in texts
    assert_centered(ticks, bars)
    expect(page.locator(f"{C3} .legend .traces")).to_have_count(1)
    expect(page.locator(f"{C3} .xtick text")).to_have_count(0)


@pytest.mark.plotlyjs_fetches(1)
def test_c3_on_1864_marks_each_state_with_no_electoral_votes(page: Page) -> None:
    """AC Nulls: each zero allotment is a labeled marker, never a zero bar, and every
    label stays inside 390 px with none over another."""
    open_c3(page, 1864)
    assert_c3_readable(page, 1864)
    marks = [b["text"] for b in boxes(page, f"{C3} .scatterlayer .textpoint text")]
    assert marks == [labels.C3_NO_ELECTORAL_VOTES] * 11
    expect(page.locator(C3_BARS)).to_have_count(36 - 11)


def assert_centered(ticks: list[dict[str, Any]], bars: list[dict[str, Any]]) -> None:
    """Each drawn bar centered on its row name (the shared ``offsetgroup``)."""
    by_row = sorted(bars, key=center)
    drawn = ticks[: len(by_row)]
    for tick, bar in zip(drawn, by_row, strict=True):
        assert abs(center(bar) - center(tick)) <= 1.5, (tick, bar)


def stripe_color(page: Page) -> str:
    """The color a striped bar's pattern draws its stripes in: the bar's fill is a
    ``url(#…)`` pattern, whose stripe path is stroked in the pattern's color."""
    color: str = page.locator(C3_STRIPED).first.evaluate(
        """el => {
            const fill = getComputedStyle(el).fill;
            const id = /url\\("?#([^")]+)"?\\)/.exec(fill)[1];
            const stripe = document.getElementById(id).querySelector("path");
            return getComputedStyle(stripe).stroke;
        }"""
    )
    return color


@pytest.mark.plotlyjs_fetches(1)
def test_c3_on_1848_labels_texas_and_stripes_present_day_bars(page: Page) -> None:
    """1848 draws both bar series: each bar centered on its row name (the shared
    ``offsetgroup`` matters only here), the plain bars filled ``--chart-1`` and the
    present-day bars striped in the page color, before and after a theme switch."""
    open_c3(page, 1848)
    ticks = assert_c3_readable(page, 1848)
    marks = [b["text"] for b in boxes(page, f"{C3} .scatterlayer .textpoint text")]
    assert marks == [labels.C3_NO_CENSUS_FIGURE]
    expect(page.locator(f"{C3} .legend .traces")).to_have_count(2)
    expect(page.locator(f"{C3} .barlayer .trace")).to_have_count(2)
    assert_centered(ticks, boxes(page, C3_BARS))
    for theme in ("light", "dark"):
        if theme == "dark":
            page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
            # The palette has switched before any token is read (round 2's review).
            page.wait_for_function(
                "getComputedStyle(document.documentElement).colorScheme === 'dark'"
            )
            expect(page.locator(C3_STRIPED).first).to_be_visible()
        chart_1 = rgb(token(page, "--chart-1"))
        # The plain bars (the first bar trace) are filled with the series color.
        expect(page.locator(C3_PLAIN).first).to_have_css("fill", chart_1)
        assert page.locator(C3_STRIPED).first.evaluate(
            "el => getComputedStyle(el).fill"
        ).startswith("url(")
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector("{C3_STRIPED}");
                const fill = getComputedStyle(el).fill;
                const m = /url\\("?#([^")]+)"?\\)/.exec(fill);
                if (!m) return false;
                const p = document.getElementById(m[1]);
                return p && getComputedStyle(p.querySelector("path")).stroke
                    === "{{page}}";
            }}""".replace("{page}", rgb(token(page, "--page")))
        )
        assert stripe_color(page) == rgb(token(page, "--page"))


@pytest.mark.plotlyjs_fetches(1)
@pytest.mark.parametrize(("year", "usps"), [(2024, "CA"), (2024, "WY"), (1848, "TX")])
def test_c3_marks_the_selected_state_over_no_text(
    page: Page, year: int, usps: str
) -> None:
    """AC: a filtered state is marked by a non-color channel, in its own row, over no
    drawn text, and the chart keeps every state while T6 shows one."""
    open_c3(page, year, f"?state={usps}")
    ticks = assert_c3_readable(page, year)
    name = next(
        r["state"]
        for r in recorded(f"/v1/elections/{year}/per-capita")["data"]
        if r["state_usps"] == usps
    )
    (mark,) = boxes(page, C3_SELECTED)
    row = c3_order(year).index(name)
    assert abs(center(mark) - center(ticks[row])) <= 1.5
    for text in boxes(page, C3_PLOT_TEXTS + ", " + C3_CHART_TEXTS):
        if text["w"] > 0:
            assert not overlaps(mark, text), (mark, text)
    expect(page.locator("#election-per-capita tbody tr")).to_have_count(1)


@pytest.mark.plotlyjs_fetches(1)
def test_c3_redraws_on_a_theme_switch_with_no_reload_or_request(page: Page) -> None:
    # 1848: its first bar trace is the plain one (a striped bar fills with a pattern).
    open_c3(page, 1848)
    bar = page.locator(f"{C3} .barlayer .trace:first-child .point path").first
    light = bar.evaluate("el => getComputedStyle(el).fill")
    assert light == rgb(token(page, "--chart-1"))
    seen: list[str] = []

    def on_request(request: Request) -> None:
        seen.append(f"{request.method} {urlsplit(request.url).path}")

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    page.locator(f"#{components.THEME_BUTTON_IDS['dark']}").click()
    expect(bar).not_to_have_css("fill", light)
    assert bar.evaluate("el => getComputedStyle(el).fill") == rgb(
        token(page, "--chart-1")
    )
    page.wait_for_timeout(SETTLE_MS)
    assert seen == [], seen
    assert page.evaluate("window.__e2e_mark") == 1


@pytest.mark.plotlyjs_fetches(1, abort=True)
@pytest.mark.expected_console_error(RESOURCE_ERROR)
def test_with_plotlyjs_blocked_t6_and_c3_s_title_and_caption_render(
    page: Page,
) -> None:
    page.goto("/election/2024/per-capita")
    assert_rendered(page, PER_CAPITA_SUCCESS)
    memo = f"window.{charts.PLOTLYJS_MEMO}"
    page.wait_for_function(f"{memo} !== undefined")
    assert page.evaluate(f"async () => await {memo}") is False
    expect(page.locator(f"{C3} .chart-title")).to_have_text(
        labels.C3_TITLE.format(year=2024, census_year="2020")
    )
    expect(page.locator(f"{C3} figcaption")).to_contain_text(labels.C3_RATIO)
    expect(page.locator(f"{C3} figcaption a")).to_have_attribute(
        "href", "#election-per-capita"
    )
    expect(page.locator("#election-per-capita")).to_be_visible()
    expect(page.locator(f"{C3} .js-plotly-plot")).to_have_count(0)


@pytest.mark.plotlyjs_fetches(0)  # a degraded render mounts no chart (#435)
def test_a_degraded_per_capita_page_shows_no_chart(page: Page) -> None:
    """A served year whose per-capita response is not recorded reads as unavailable
    (the e2e server answers an unrecorded path ``ApiUnavailable``), with no C3."""
    served = [r["year"] for r in recorded("/v1/elections")["data"]]
    year = next(
        y
        for y in served
        if f"/v1/elections/{y}/per-capita" not in RECORDED_FILES
    )
    page.goto(f"/election/{year}/per-capita")
    expect(page.get_by_text(components.UNAVAILABLE_MESSAGE)).to_be_visible()
    expect(page.locator(C3)).to_have_count(0)
