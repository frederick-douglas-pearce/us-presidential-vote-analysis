"""The site navigation in a browser (#448): one row at a phone's width on every page
template, a wrap rather than a sideways scroll at 320 px, the full site name from
45rem, the bar's ends lined up with the page's content at the wide layout, the
current-page marker after a direct load, a client-side navigation, a filter change and
back and forward, the registered callback on every path of the shared corpus, Tab
order, and in-app links that load no document and make no other request.

The marker is ``aria-current`` on the link, which ``NAV_CALLBACK`` writes in the
browser and reports as the nav's ``data-current``. The layout renders no
``data-current``, so ``data-current=""`` ("nothing marked") is present only once the
callback has run. ``conftest._browser_guard`` fails every test on an off-host request,
so no test follows the API docs link.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import components, config, labels
from tests.e2e.dashboard_pages import (
    ELECTION_LATER,
    ELECTION_SUCCESS,
    ELECTIONS_SUCCESS,
    HOME_SUCCESS,
    LOWER_THUMB,
    ROUTER_OUTPUT,
    UNAVAILABLE,
    UPDATE_PATH,
    assert_rendered,
    step_years,
)
from tests.nav_marks import MARKS

pytestmark = pytest.mark.e2e

NOT_FOUND_ERROR = (
    "Failed to load resource: the server responded with a status of 404 (NOT FOUND)"
)
NAV = f"#{components.SITE_NAV_ID}"
LINK_IDS = components.NAV_LINK_IDS

#: The slack the bar keeps at 390 px, so a wider font still fits on one row (the
#: architect's margin for SF Pro, #448). CI's DejaVu Sans is the widest checked: at
#: 8 px gaps and 28 px toggle buttons it left 4 px, so the gaps are 6 px and the
#: buttons 24 px (owner decision, PR #451).
MIN_SLACK_PX = 16

#: How long a test waits for a callback that should not change anything.
SETTLE_MS = 500

#: Each page template, what its body renders (a success marker, a not-found state or
#: the degraded state), and the link it marks with its aria-current (None: none).
#: /state/TX is served by the roster but its history is not recorded, so it degrades.
TEMPLATES: dict[str, tuple[str, tuple[str, str] | None]] = {
    "/": (HOME_SUCCESS, ("home", "page")),
    "/elections": (ELECTIONS_SUCCESS, ("elections", "page")),
    "/election/1824": (ELECTION_SUCCESS, ("elections", "true")),
    "/election/1825": ("#election-not-found", ("elections", "true")),
    # The overview's subpages (#465), and an unserved year on one.
    "/election/1824/states": ("#election-states-page", ("elections", "true")),
    "/election/1824/per-capita": ("#election-per-capita-page", ("elections", "true")),
    "/election/1825/states": ("#election-states-not-found", ("elections", "true")),
    # An unserved year on the per-capita page, chart C3's (#435).
    "/election/1825/per-capita": (
        "#election-per-capita-not-found",
        ("elections", "true"),
    ),
    "/states": ("#states", ("states", "page")),
    "/state/GA": ("#state", ("states", "true")),
    "/state/TX": (UNAVAILABLE, ("states", "true")),
    "/candidate/andrew-jackson": ("#candidate", None),
    "/no-such-page": ("#page-not-found", None),
}

#: The templates whose document answers 404, which logs one console error.
NOT_FOUND_PATHS = {
    "/election/1825",
    "/election/1825/states",
    "/election/1825/per-capita",
    "/no-such-page",
}


def template_params() -> list[Any]:
    return [
        pytest.param(
            path,
            # A not-found render never mounts a chart: exactly no plotly.js, never
            # the derived bound (#433's round 1).
            marks=[
                pytest.mark.expected_console_error(NOT_FOUND_ERROR),
                pytest.mark.plotlyjs_fetches(0),
            ]
            if path in NOT_FOUND_PATHS
            else [],
            id=path,
        )
        for path in TEMPLATES
    ]


def open_page(page: Page, path: str) -> None:
    page.goto(path)
    page.locator(TEMPLATES[path][0]).wait_for()


def expect_marked(page: Page, mark: tuple[str, str] | None) -> None:
    """The nav reports ``mark`` and exactly that link carries it."""
    key = "" if mark is None else mark[0]
    expect(page.locator(NAV)).to_have_attribute("data-current", key)
    for link, link_id in LINK_IDS.items():
        locator = page.locator(f"#{link_id}")
        if mark is not None and link == mark[0]:
            expect(locator).to_have_attribute("aria-current", mark[1])
        else:
            expect(locator).not_to_have_attribute("aria-current", "page")
            expect(locator).not_to_have_attribute("aria-current", "true")
            assert locator.get_attribute("aria-current") is None, link


def push(page: Page, path: str) -> None:
    """A client-side navigation, as a ``dcc.Link`` makes one."""
    page.evaluate(
        """path => {
            window.history.pushState({}, "", path);
            window.dispatchEvent(new CustomEvent("_dashprivate_pushstate"));
        }""",
        path,
    )


#: The bar's entries, their boxes, each label's overflow, and the slack the row keeps.
MEASURE = """() => {
    const header = document.querySelector('.site-header');
    const nav = document.getElementById(__NAV__);
    const entries = [...nav.children, document.getElementById(__TOGGLE__)];
    const boxes = entries.map(e => e.getBoundingClientRect());
    const style = getComputedStyle(header);
    const content = header.clientWidth - parseFloat(style.paddingLeft)
        - parseFloat(style.paddingRight);
    const gaps = 3 * parseFloat(getComputedStyle(nav).columnGap)
        + parseFloat(style.columnGap);
    return {
        tops: boxes.map(b => b.top), bottoms: boxes.map(b => b.bottom),
        widths: boxes.map(b => b.width), heights: boxes.map(b => b.height),
        rights: boxes.map(b => b.right),
        overflow: [...nav.children].map(a => a.scrollWidth > a.clientWidth),
        navOverflow: nav.scrollWidth > nav.clientWidth,
        slack: content - boxes.reduce((sum, b) => sum + b.width, 0) - gaps,
        page: document.documentElement.scrollWidth,
    };
}""".replace("__NAV__", json.dumps(components.SITE_NAV_ID)).replace(
    "__TOGGLE__", json.dumps(components.THEME_CONTROL_ID)
)


def measure(page: Page) -> dict[str, Any]:
    result: dict[str, Any] = page.evaluate(MEASURE)
    return result


@pytest.mark.parametrize("path", template_params())
def test_the_bar_keeps_one_row_at_a_phones_width(page: Page, path: str) -> None:
    open_page(page, path)
    assert page.evaluate("innerWidth") == 390
    found = measure(page)
    # One row: every entry overlaps every other vertically, which holds whether or not
    # the entries' heights match (they are centered on the row).
    assert max(found["tops"]) < min(found["bottoms"]), found
    # No label wraps or is cut: each link one 24 px line, nothing overflowing.
    assert not any(found["overflow"]) and not found["navOverflow"], found
    assert all(h <= 24.5 for h in found["heights"][:4]), found
    # WCAG 2.5.8: each link's target at least 24 x 24 CSS px.
    assert all(
        w >= 24 and h >= 24
        for w, h in zip(found["widths"][:4], found["heights"][:4], strict=True)
    ), found
    assert found["page"] == 390, found
    print(f"site navigation slack at 390 px on {path}: {found['slack']:.1f} px")
    assert found["slack"] >= MIN_SLACK_PX, found


def test_the_bar_wraps_rather_than_scrolls_at_320_px(page: Page) -> None:
    page.set_viewport_size({"width": 320, "height": 844})
    page.goto("/elections")
    page.locator(ELECTIONS_SUCCESS).wait_for()
    found = measure(page)
    assert found["page"] == 320, found
    assert not any(found["overflow"]), found
    assert max(found["rights"]) <= 320, found


def chromium_name(page: Page, selector: str) -> str:
    """The element's accessible name as Chromium's accessibility tree computes it, what
    a screen reader on Chromium hears; Playwright's role locators compute names their
    own way, from DOM text. In Chromium the name keeps its space with or without
    ``.site-name-rest``'s ``white-space: pre``, so this does not pin that declaration:
    ``test_the_rest_of_the_site_name_keeps_its_space`` (``test_dashboard_theme.py``)
    does."""
    client = page.context.new_cdp_session(page)
    root = client.send("DOM.getDocument")["root"]["nodeId"]
    node = client.send("DOM.querySelector", {"nodeId": root, "selector": selector})
    tree = client.send(
        "Accessibility.getPartialAXTree",
        {"nodeId": node["nodeId"], "fetchRelatives": False},
    )
    client.detach()
    return str(tree["nodes"][0]["name"]["value"])


def test_the_full_site_name_shows_from_45rem(page: Page) -> None:
    rest = page.locator(f"{NAV} .site-name-rest")
    home = f"#{LINK_IDS['home']}"
    page.goto("/elections")
    page.locator(ELECTIONS_SUCCESS).wait_for()
    # Narrow: the rest is clipped, and the link's name is still the full site title.
    assert rest.evaluate("e => e.getBoundingClientRect().width") <= 1
    assert chromium_name(page, home) == config.SITE_TITLE
    # Just under the 45rem breakpoint (720 px) the rest is still clipped.
    page.set_viewport_size({"width": 704, "height": 844})
    assert rest.evaluate("e => e.getBoundingClientRect().width") <= 1
    page.set_viewport_size({"width": 720, "height": 844})
    assert rest.evaluate("e => e.getBoundingClientRect().width") > 100
    assert chromium_name(page, home) == config.SITE_TITLE
    found = measure(page)
    assert max(found["tops"]) < min(found["bottoms"]), found
    assert not any(found["overflow"]) and found["page"] == 720, found


@pytest.mark.parametrize("path", template_params())
def test_a_direct_load_marks_the_pages_link(page: Page, path: str) -> None:
    open_page(page, path)
    expect_marked(page, TEMPLATES[path][1])


@pytest.mark.parametrize(
    "path",
    ["/election", "/elections/x", "/no-such-page", "/candidate/andrew-jackson"],
)
def test_a_navigation_to_a_page_with_no_mark_clears_it(page: Page, path: str) -> None:
    # Starting marked, so the cleared state proves the callback ran on the new path.
    # On a page with no chart (#434: /elections draws C2), so no plotly.js fetch can
    # land after the push and be counted against the page pushed to.
    page.goto("/states")
    page.locator("#states").wait_for()
    expect_marked(page, ("states", "page"))
    push(page, path)
    expect_marked(page, None)


@pytest.mark.parametrize(
    ("path", "mark"),
    [
        ("/election/1824/x", ("elections", "true")),
        ("/state/ZZ", ("states", "true")),
        ("/", ("home", "page")),
    ],
)
def test_a_navigation_marks_by_the_routers_rule(
    page: Page, path: str, mark: tuple[str, str]
) -> None:
    page.goto("/candidate/andrew-jackson")
    page.locator("#candidate").wait_for()
    push(page, path)
    expect_marked(page, mark)


def test_a_nav_click_loads_no_document_and_posts_only_the_router(page: Page) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    expect_marked(page, ("elections", "page"))
    # C2 (#434) drawn first: plotly.js and dcc's graph chunk load once per document,
    # so the return to /elections below requests neither.
    page.locator("#c2 .main-svg").first.wait_for()
    seen: list[tuple[str, str, str]] = []

    def on_request(request: Request) -> None:
        # Every request the page makes, of every kind: the router's one POST is named
        # by the output it asks for, anything else by its method, type and path.
        path = urlsplit(request.url).path
        if request.method == "POST" and path == UPDATE_PATH:
            body: Any = request.post_data_json
            seen.append(("callback", "POST", body["output"]))
        else:
            seen.append((request.resource_type, request.method, path))

    page.on("request", on_request)
    page.evaluate("window.__e2e_mark = 1")
    for key, success, mark in (
        ("states", "#states", ("states", "page")),
        ("home", HOME_SUCCESS, ("home", "page")),
        ("elections", ELECTIONS_SUCCESS, ("elections", "page")),
    ):
        seen.clear()
        page.locator(f"#{LINK_IDS[key]}").click()
        assert_rendered(page, success)
        expect_marked(page, mark)
        page.wait_for_timeout(SETTLE_MS)
        # The router's one request, and nothing else: no document, no re-bootstrap, no
        # asset, and no request for the marker, which runs in the browser.
        assert seen == [("callback", "POST", ROUTER_OUTPUT)], (key, seen)
    assert page.evaluate("window.__e2e_mark") == 1


def test_the_bar_lines_up_with_the_content_at_the_wide_layout(page: Page) -> None:
    # #360's desktop layout: the bar keeps one row, and its ends sit on the page's
    # content edges (the site name on the left, the toggle on the right).
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto("/elections")
    page.locator(ELECTIONS_SUCCESS).wait_for()
    found = measure(page)
    assert max(found["tops"]) < min(found["bottoms"]), found
    edges = page.evaluate(
        """() => {
            const box = e => e.getBoundingClientRect();
            const main = document.querySelector("main.explore");
            const style = getComputedStyle(main);
            return {
                left: box(main).left + parseFloat(style.paddingLeft),
                right: box(main).right - parseFloat(style.paddingRight),
                name: box(document.getElementById(__HOME__)).left,
                toggle: box(document.getElementById(__TOGGLE__)).right,
            };
        }""".replace("__HOME__", json.dumps(LINK_IDS["home"])).replace(
            "__TOGGLE__", json.dumps(components.THEME_CONTROL_ID)
        )
    )
    assert abs(edges["name"] - edges["left"]) <= 0.5, edges
    assert abs(edges["toggle"] - edges["right"]) <= 0.5, edges


def test_the_registered_callback_marks_every_path(page: Page) -> None:
    # The JS itself, on the shared corpus the unit suite's Python model also reads:
    # the function Dash registered for the nav's output, called with each path, its
    # return and the links' aria-current read after each call. Found through
    # _dash-dependencies, a Dash-private shape, acceptable in this advisory suite.
    # It checks the mark, not which table entry matched: on the election pages
    # (#465) every entry marks Elections alike, so #465's NAV_CALLBACK criterion holds
    # here by the mark alone, and the matched entry is TestCurrentPage's (unit suite).
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    expect_marked(page, ("elections", "page"))
    results: dict[str, Any] = page.evaluate(
        """async ([output, ids, paths]) => {
            const deps = await (await fetch("/_dash-dependencies")).json();
            const spec = deps.find(d => d.output === output).clientside_function;
            const fn = window.dash_clientside[spec.namespace][spec.function_name];
            const out = {};
            for (const path of paths) {
                const marked = fn(path);
                const current = {};
                for (const [key, id] of Object.entries(ids)) {
                    current[key] = document.getElementById(id).getAttribute(
                        "aria-current");
                }
                out[path] = {marked, current};
            }
            return out;
        }""",
        [f"{components.SITE_NAV_ID}.data-current", LINK_IDS, list(MARKS)],
    )
    for path, mark in MARKS.items():
        got = results[path]
        assert got["marked"] == ("" if mark is None else mark[0]), (path, got)
        expected: dict[str, str | None] = dict.fromkeys(LINK_IDS)
        if mark is not None:
            expected[mark[0]] = mark[1]
        assert got["current"] == expected, (path, got)


def test_the_marker_follows_the_earlier_later_link_and_a_filter(page: Page) -> None:
    earlier, later = step_years()
    page.goto(f"/election/{earlier}")
    assert_rendered(page, ELECTION_SUCCESS)
    expect_marked(page, ("elections", "true"))
    page.locator(ELECTION_LATER).click()
    page.wait_for_url(f"**/election/{later}")
    assert_rendered(page, ELECTION_SUCCESS)
    expect_marked(page, ("elections", "true"))
    page.locator(f"#{LINK_IDS['elections']}").click()
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.locator(LOWER_THUMB).press("ArrowRight")
    page.wait_for_url("**/elections?*")
    assert_rendered(page, ELECTIONS_SUCCESS)
    expect_marked(page, ("elections", "page"))


def test_back_and_forward_move_the_marker(page: Page) -> None:
    page.goto("/elections")
    expect_marked(page, ("elections", "page"))
    page.locator(f"#{LINK_IDS['states']}").click()
    expect_marked(page, ("states", "page"))
    page.go_back()
    assert_rendered(page, ELECTIONS_SUCCESS)
    expect_marked(page, ("elections", "page"))
    page.go_forward()
    page.locator("#states").wait_for()
    expect_marked(page, ("states", "page"))


def test_tab_reaches_the_bar_in_visual_order(page: Page) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    expected = [
        *LINK_IDS.values(),
        components.NAV_API_DOCS_ID,
        *components.THEME_BUTTON_IDS.values(),
    ]
    order = []
    for _ in expected:
        page.keyboard.press("Tab")
        order.append(page.evaluate("document.activeElement.id"))
    assert order == expected
    # Visual order agrees: each entry starts right of the one before it.
    lefts = [
        page.locator(f"#{element}").evaluate("e => e.getBoundingClientRect().left")
        for element in expected
    ]
    assert lefts == sorted(lefts), lefts
    # The API docs link goes off this site in the same tab; it is never followed here.
    docs = page.locator(f"#{components.NAV_API_DOCS_ID}")
    expect(docs).to_have_attribute("href", config.API_BASE + "/docs")
    assert docs.get_attribute("target") is None
    expect(page.get_by_role("navigation", name=labels.SITE_NAV_LABEL)).to_have_count(1)


def test_each_link_shows_a_focus_ring(page: Page) -> None:
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    for element in [*LINK_IDS.values(), components.NAV_API_DOCS_ID]:
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.id") == element
        ring = page.locator(f"#{element}").evaluate(
            "e => { const s = getComputedStyle(e);"
            " return [s.outlineStyle, s.outlineWidth]; }"
        )
        assert ring == ["solid", "2px"], (element, ring)


def test_the_marker_is_drawn_under_forced_colors(page: Page) -> None:
    page.emulate_media(forced_colors="active")
    page.goto("/states")
    page.locator("#states").wait_for()
    expect_marked(page, ("states", "page"))
    lines = {
        key: page.locator(f"#{link_id}").evaluate(
            "e => getComputedStyle(e).textDecorationLine"
        )
        for key, link_id in LINK_IDS.items()
    }
    assert lines == {"home": "none", "elections": "none", "states": "underline"}
