"""What the browser tests locate and expect (#321).

Element ids and the field list a page module defines are written out here: Dash
executes a page module itself, so a test cannot import one. Shared ids, labels and
helpers are imported from ``explore`` so a test follows the shipped value, and expected
data values come from the recorded responses, never literals. It reads two recorded
responses at import, as ``test_dashboard_app.py`` does.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any

from playwright.sync_api import Locator, Page, expect

from explore import components, query
from tests.dashboard_fixtures import FIXTURE_DIR, RECORDED_FILES

#: The phone viewport #306's manual check ran at.
VIEWPORT = {"width": 390, "height": 844}

# Ids of the home page (pages/home.py).
HOME_SUCCESS = "#coverage"

# Ids of the elections index (pages/elections.py).
ELECTIONS_SUCCESS = "#elections"
ELECTIONS_ROWS = "#elections-table tbody tr"
YEARS = "#elections-years"
PV = "#elections-pv"
PV_BOX = "#elections-pv input[type=checkbox]"
LOWER_THUMB = f"{YEARS} [role=slider].dash-slider-thumb-1"
UPPER_THUMB = f"{YEARS} [role=slider].dash-slider-thumb-2"
MARKS = f"{YEARS} .dash-slider-mark"
#: T1's column-name list, by its id: the page has three since #436.
GLOSSARY = "#elections-glossary"
#: T1's columns, as pages/elections.py's ``FIELDS`` lists them (#563: N1's four after
#: the index's three).
FIELDS = (
    "year",
    "candidate_count",
    "has_popular_vote",
    "electoral_votes_outside_top_two",
    "electors_without_a_counted_vote",
    "ec_margin",
    "pv_margin",
)
#: T1's page-only column (#563, D116), as pages/elections.py's ``PAGE_ONLY`` lists it:
#: its header and the served fields it is built from.
RECIPIENTS = (
    "Who received electoral votes (cast, counted)",
    "candidate, national_electoral_votes, national_electoral_votes_counted",
)
#: Chart C9 (#563), above T1 on the list of elections.
C9 = "#c9"

#: The section links between the three elections pages (#562).
ELECTIONS_SECTIONS = "#elections-sections"

# Ids of the Electoral College majority page (pages/elections_majority.py, #562):
# chart C2 (#434) and its companion table.
MAJORITY_SUCCESS = "#elections-majority"
C2 = "#c2"
LEADER_ROWS = "#elections-leader-table tbody tr"

# Ids of the electors appointed and total popular vote page
# (pages/elections_over_time.py, #562): charts C4 and C5 and their shared companion
# table (#436), all states only.
OVER_TIME_SUCCESS = "#elections-over-time"
C4 = "#c4"
C5 = "#c5"
OVER_TIME_ROWS = "#elections-over-time-table tbody tr"

# Ids of the state history (pages/state.py) and its people per electoral vote
# (pages/state_per_capita.py, #559).
STATE_SUCCESS = "#state"
STATE_PER_CAPITA_SUCCESS = "#state-per-capita-page"

# Ids of the candidate history (pages/candidate.py).
CANDIDATE_SUCCESS = "#candidate"

# Ids of the one-election view (pages/election.py).
ELECTION_SUCCESS = "#election"
ELECTION_EARLIER = "#election-earlier"
ELECTION_LATER = "#election-later"
#: The election overview's two subpages (#465), their success markers and not-found
#: states, and the section links on all three.
STATES_SUCCESS = "#election-states-page"
PER_CAPITA_SUCCESS = "#election-per-capita-page"
STATES_NOT_FOUND = "#election-states-not-found"
SECTIONS = "#election-sections"

# Shared pieces (components.py).
PROVENANCE = f"#{components.PROVENANCE_ID}"
UNAVAILABLE = "#unavailable"

#: The outputs of the two callbacks one filter change should fire, by the ``output``
#: Dash posts: the page's filter callback and the Pages router.
FILTER_OUTPUT = "elections-url.search"
ROUTER_OUTPUT = ".._pages_content.children..._pages_store.data.."
UPDATE_PATH = "/_dash-update-component"


def recorded(path: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(
        (FIXTURE_DIR / RECORDED_FILES[path]).read_text(encoding="utf-8")
    )
    return body


META = recorded("/v1/meta")
ELECTIONS = recorded("/v1/elections")
COVERAGE = ELECTIONS["meta"]["provenance"]["coverage"]
FIRST: int = COVERAGE["year_min"]
LAST: int = COVERAGE["year_max"]
PV_FIRST: int = COVERAGE["pv_year_min"]


def _recorded_year(year: int) -> bool:
    """Whether both paths ``year``'s election pages fill are recorded (#465: the
    overview's, which the states page shares, and the per-capita page's)."""
    return all(
        path in RECORDED_FILES
        for path in (f"/v1/elections/{year}", f"/v1/elections/{year}/per-capita")
    )


def step_years() -> tuple[int, int]:
    """Two consecutive served years whose election pages are both recorded, from
    the recorded index, oldest first: where the browser test steps from one election
    to the next (#324). Called by that test, so a corpus with no such pair fails it,
    by name, rather than every module importing this one."""
    served = sorted(e["year"] for e in ELECTIONS["data"])
    for earlier, later in zip(served, served[1:], strict=False):
        if _recorded_year(earlier) and _recorded_year(later):
            return earlier, later
    raise AssertionError(
        "no two consecutive served years both have recorded /v1/elections/{year} "
        "and /per-capita responses"
    )


def years_shown(*, year_from: int = FIRST, pv_only: bool = False) -> list[int]:
    """The years the elections index should list, from the recorded index."""
    return [
        e["year"]
        for e in ELECTIONS["data"]
        if e["year"] >= year_from and (e["has_popular_vote"] is True or not pv_only)
    ]


def search(*, year_from: int = FIRST, pv_only: bool = False) -> str:
    """The normalized query string a filter change should write."""
    pairs = []
    if year_from != FIRST:
        pairs.append((query.YEAR_FROM, str(year_from)))
    if pv_only:
        pairs.append(("pv", "1"))
    return query.encode_search(pairs)


def row_years(page: Page) -> list[int]:
    years = page.locator(f"{ELECTIONS_ROWS} td:first-child a").all_inner_texts()
    return [int(text) for text in years]


def lower_thumb(page: Page) -> Locator:
    """The lower handle, located afresh: a filter change re-renders the layout."""
    return page.locator(LOWER_THUMB)


def assert_rendered(page: Page, success: str, *, width: int = 390) -> None:
    """The page rendered from data at the phone's width: its success marker is there,
    the degraded state is not. ``width`` is the viewport width the calling test set
    itself (:data:`PHONE_WIDTHS`, #558); only the
    default, 390, is the suite's pinned phone."""
    page.locator(success).wait_for()
    assert page.locator(UNAVAILABLE).count() == 0
    # The default is written out, not read from VIEWPORT, so editing that constant
    # cannot move the width this suite claims to check: #306's phone, 390 px.
    assert page.evaluate("innerWidth") == width


#: How a failed lazy chunk's console error starts (webpack's ``ChunkLoadError``, #456).
CHUNK_ERROR_PREFIX = "ChunkLoadError: Loading chunk"

#: Chromium's console error for a request that failed, logged once per failed request
#: (an aborted plotly.js load, #452, or an aborted chunk, #456).
RESOURCE_ERROR = "Failed to load resource: net::ERR_FAILED"

#: Chromium's console error for a document that answers 404, logged once per such load
#: (a not-found render, #325).
NOT_FOUND_ERROR = (
    "Failed to load resource: the server responded with a status of 404 (NOT FOUND)"
)

#: The custom-404 page's id (pages/not_found_404.py), for a path no page matches.
PAGE_NOT_FOUND = "#page-not-found"

#: How long a failed chunk must log nothing new to count as stopped (#456). Dash
#: 4.4.1's loop logged about 25 a second (D088), so it cannot hide in this window; a
#: loop slower than one line per window is out of this test's reach (D089).
CHUNK_QUIET_MS = 2000

#: How long to wait for a failed chunk's first error, and, after it, for the quiet
#: window to arrive.
CHUNK_FIRST_ERROR_MS = 10_000
CHUNK_DEADLINE_MS = 20_000

#: The marker line the barrier logs; every line logged before it has been delivered
#: once the test has seen it.
CHUNK_BARRIER = "e2e-chunk-barrier"


def watch_chunk_errors(page: Page) -> list[str]:
    """Record the page's ``ChunkLoadError`` console lines from now on (#456)."""
    seen: list[str] = []

    def on_console(message: Any) -> None:
        if message.type == "error" and message.text.startswith(CHUNK_ERROR_PREFIX):
            seen.append(message.text)

    page.on("console", on_console)
    return seen


def assert_chunk_failure_stops(page: Page, seen: list[str]) -> None:
    """A failed chunk logged at least one ``ChunkLoadError`` and then stopped (#456,
    D089): after the first line, the test waits until none has arrived for
    :data:`CHUNK_QUIET_MS`, restarting the window on each new line, and fails if that
    takes past :data:`CHUNK_DEADLINE_MS`; then a marker line is logged and awaited as a
    barrier, so every line logged before it has arrived, and the count must not have
    moved. The guard (``tests/e2e/conftest.py``, ``chunk_problems``) holds the totals
    to its bound. A loop slower than one line per window is out of reach; the harm
    this pins is D088's tight loop."""
    waited = 0
    while not seen and waited < CHUNK_FIRST_ERROR_MS:
        page.wait_for_timeout(100)
        waited += 100
    assert seen, "the aborted chunk logged no ChunkLoadError"
    waited = 0
    quiet = 0
    count = len(seen)
    while quiet < CHUNK_QUIET_MS:
        assert waited < CHUNK_DEADLINE_MS, (
            f"ChunkLoadError kept coming for {waited} ms: {len(seen)} lines (D088's loop)"
        )
        page.wait_for_timeout(100)
        waited += 100
        if len(seen) != count:
            count, quiet = len(seen), 0
        else:
            quiet += 100
    with page.expect_console_message(lambda message: message.text == CHUNK_BARRIER):
        page.evaluate(f"console.info({CHUNK_BARRIER!r})")
    assert len(seen) == count, (
        f"ChunkLoadError kept coming: {count}, then {len(seen)} (D088's loop)"
    )


def color_channels(color: str) -> tuple[float, float, float, float]:
    """A computed ``rgb()``/``rgba()`` color's channels and alpha; any other form fails."""
    match = re.fullmatch(
        r"rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)", color.strip()
    )
    assert match, color
    r, g, b = (float(match.group(i)) for i in (1, 2, 3))
    return (r, g, b, float(match.group(4) or 1))


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2's ratio of two opaque computed colors: a translucent one fails, since
    its ratio depends on what it is drawn over."""

    def luminance(color: str) -> float:
        def channel(c: float) -> float:
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        r, g, b, alpha = color_channels(color)
        assert alpha == 1, color
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def composited(color: str, backdrop: str) -> str:
    """``color`` drawn over the opaque ``backdrop``, as an opaque ``rgb()``: a fully
    transparent color comes back as the backdrop itself, so its ratio is 1."""
    r, g, b, alpha = color_channels(color)
    under = color_channels(backdrop)
    assert under[3] == 1, backdrop
    mixed = (round(alpha * c + (1 - alpha) * u) for c, u in zip((r, g, b), under[:3], strict=True))
    return "rgb({}, {}, {})".format(*mixed)


# --- the wide layout (#544, #545, D102) ------------------------------------------------

#: The wide breakpoint, 76rem at the default 16 px root size (D102(a)): from this
#: width a filter row and a pair take effect.
WIDE_BREAKPOINT_PX = 76 * 16
#: A width below the 76rem breakpoint and wider than the 64rem step, where every page
#: is still its one column.
NARROW_DESKTOP = 1100
WIDE_WIDTHS = [1280, 1850]
#: The measure, 42rem at the default 16 px root size.
MEASURE_PX = 42 * 16
#: A filter row's filter is 14rem to 20rem wide.
FILTER_MIN_PX, FILTER_MAX_PX = 14 * 16, 20 * 16


def boxes(page: Page, selector: str) -> list[dict[str, Any]]:
    """Each match's bounding box and text, in document order."""
    found: list[dict[str, Any]] = page.eval_on_selector_all(
        selector,
        """els => els.map(el => {
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height,
                    text: el.textContent};
        })""",
    )
    return found


def rects(page: Page, selector: str) -> list[dict[str, float]]:
    """Each match's box as edges, from :func:`boxes`."""
    return [
        {
            "left": b["x"],
            "right": b["x"] + b["w"],
            "top": b["y"],
            "bottom": b["y"] + b["h"],
            "width": b["w"],
        }
        for b in boxes(page, selector)
    ]


def rect(page: Page, selector: str) -> dict[str, float]:
    """The one match's box; a selector matching none or several fails."""
    (found,) = rects(page, selector)
    return found


def assert_layout_holds(
    page: Page,
    success: str,
    tables: tuple[str, ...],
    width: int,
    *,
    tables_expected: bool = True,
) -> None:
    """The checks every layout story inherits (#364, #543), at ``width``: no box under
    the page ``success`` marks is reordered (``order``, a reversed flex direction or a
    placed grid item) and none has a positive tab index; every paragraph, chart caption
    and party-notes item in ``main`` is within the 42rem measure; the page never
    scrolls sideways; each of ``tables`` (table ids) is there, and from about 1280 px
    none scrolls. A page that shows no table (home, the States list; #567) passes
    ``tables_expected=False`` with no ids: the other checks still run, and naming no
    table is otherwise refused, so a caller cannot drop its tables by accident."""
    found = page.evaluate(
        f"""() => {{
            const root = document.querySelector("{success}");
            const all = [...root.querySelectorAll("*")];
            const reordered = all.filter(el => {{
                const s = getComputedStyle(el);
                return s.order !== "0" || /reverse/.test(s.flexDirection)
                    || s.gridRowStart !== "auto" || s.gridColumnStart !== "auto";
            }}).map(el => el.id || el.className || el.tagName);
            const tabbed = all.filter(el => el.tabIndex > 0)
                .map(el => el.id || el.tagName);
            const text = [...document.querySelectorAll(
                "main p, main figcaption, main .party-notes li")];
            const wide = text
                .filter(el => el.getBoundingClientRect().width > {MEASURE_PX} + 0.5)
                .map(el => el.tagName + ": " + el.textContent.slice(0, 40));
            const tables = {list(tables)!r}.map(id => {{
                const box = root.querySelector(`.table-scroll:has(${{id}})`);
                return box && box.scrollWidth <= box.clientWidth + 1;
            }});
            return {{reordered, tabbed, wide, texts: text.length, tables,
                     page: document.documentElement.scrollWidth <= innerWidth}};
        }}"""
    )
    assert found["reordered"] == [], found
    assert found["tabbed"] == [], found
    assert found["texts"] > 0 and found["wide"] == [], found
    assert found["page"], found
    assert bool(tables) == tables_expected, (tables, tables_expected)
    assert None not in found["tables"], found  # every table is there
    if width >= 1280:
        assert all(found["tables"]), found


# --- the time series (#558, D104) ------------------------------------------------

#: The phone widths every time-series chart is checked at (#558; shared since #560, when
#: C7 joined C2, C4 and C5): the suite's 390 px
#: viewport and a narrower 360 px one.
PHONE_WIDTHS = (390, 360)
#: The least gap between two neighboring year ticks, so a wider font still fits.
TICK_GAP_PX = 6


def served_years() -> list[str]:
    return [str(row["year"]) for row in recorded("/v1/elections")["data"]]


def year_ticks() -> list[str]:
    """The year axis's tick text for the served years (#558, D104)."""
    axis = components.year_axis([int(year) for year in served_years()])
    return list(axis["ticktext"])


def assert_year_ticks_apart(page: Page, chart: str) -> None:
    """The year ticks along ``chart``'s bottom, as the axis names them, each at least
    :data:`TICK_GAP_PX` clear of the next."""
    ticks = boxes(page, f"{chart} .xtick text")
    assert [b["text"] for b in ticks] == year_ticks(), chart
    ordered = sorted(ticks, key=lambda b: b["x"])
    for a, b in itertools.pairwise(ordered):
        assert b["x"] - (a["x"] + a["w"]) >= TICK_GAP_PX, (chart, a, b)


def assert_hover_names_year(page: Page, chart: str, selector: str, year: str) -> None:
    """Hovering the drawn point ``selector`` shows a hover naming ``year``."""
    page.locator(selector).scroll_into_view_if_needed()
    box = page.locator(selector).bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    expect(page.locator(f"{chart} .hoverlayer .hovertext")).to_contain_text(year)


def assert_figures_inside(
    page: Page, block: str, width: int, parts_expected: int
) -> None:
    """A headline figures block (#600) under each theme choice (Light, Dark, Auto,
    which follows the device: the AC's "System"): every label, value and note inside
    ``width`` with no sideways scroll. The figures add no color token, so the theme is
    walked for the AC rather than for a color check."""
    parts = page.locator(f"{block} dt, {block} dd, {block} p")
    for choice in ("light", "dark", "auto"):
        page.locator(f"#theme-{choice}").click()
        assert parts.count() == parts_expected, choice
        for i in range(parts.count()):
            box = parts.nth(i).bounding_box()
            assert box is not None
            assert box["x"] >= 0 and box["x"] + box["width"] <= width + 0.5, (
                choice,
                i,
                box,
            )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            choice
        )
