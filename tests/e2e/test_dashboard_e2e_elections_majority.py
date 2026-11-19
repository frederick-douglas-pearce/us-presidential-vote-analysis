"""The Electoral College majority page, ``/elections/majority``, in a browser (#562):
chart C2 (#434, D096) and its companion table, on their own page since #562 (D107).
No console error and no off-host request are asserted for every test by
``conftest._browser_guard``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

from explore import charts, components, labels
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
    year_ticks,
)
from tests.e2e.test_dashboard_e2e_election import boxes, overlaps, rgb, token

pytestmark = pytest.mark.e2e

#: How long a filter change is given to fire anything further after it settled. The

#: How long a redraw is given to fire anything further after it settled.
SETTLE_MS = 1000

# --- chart C2 (#434, D096) ------------------------------------------------------------

#: C2's drawn texts (#558, D104): its year ticks along the bottom, its share ticks, both
#: axes' titles, the majority line's label and the key's entries; no point draws text.
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
#: C2's traces in drawing order (#564, D108): the connector, the triangles, the stars,
#: the circles, then the strip; on the recorded N1 every one is drawn.
C2_TRACE = f"{C2} .scatterlayer .trace:nth-child({{}}) .points path"
C2_TRIANGLES = C2_TRACE.format(2)
C2_STARS = C2_TRACE.format(3)
C2_POINTS = C2_TRACE.format(4)
C2_STRIP = C2_TRACE.format(5)
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
    width and none over another, the majority line's label over no mark (circle,
    triangle, star or strip), no sideways scroll; one circle per served year, a
    triangle and a star per popular-vote year, a strip mark per disagreement, no mark
    text, and hovers on a circle, a triangle, a star and a strip mark naming their
    year."""
    page.set_viewport_size({"width": width, "height": 844})
    open_c2(page, width=width)
    expect(page.locator(f"{C2} .chart-title")).to_have_text(labels.C2_TITLE)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert_year_ticks_apart(page, C2)
    expect(page.locator(C2_POINTS)).to_have_count(len(served_years()))
    expect(page.locator(C2_TRIANGLES)).to_have_count(len(PV_YEARS))
    expect(page.locator(C2_STARS)).to_have_count(len(PV_YEARS))
    expect(page.locator(C2_STRIP)).to_have_count(len(DIFFERENT))
    assert DIFFERENT and PV_YEARS[0] == COVERAGE["pv_year_min"]  # the premises
    expect(page.locator(f"{C2} .textpoint")).to_have_count(0)
    texts_ = [b for b in boxes(page, C2_CHART_TEXTS) if b["w"] > 0]
    found = [b["text"] for b in texts_]
    assert found.count(labels.C2_VALUE_AXIS.replace("<br>", "")) == 1
    assert found.count(labels.LABELS["year"]) == 1
    line = labels.C2_MAJORITY_LINE.replace("<br>", "")
    assert found.count(line) == 1
    for name in (
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
    (label,) = [b for b in texts_ if b["text"] == line]
    for point in boxes(page, C2_MARKS):
        assert not overlaps(label, point), (label, point)
    last = served_years()[-1]
    assert_hover_names_year(page, C2, f"{C2_POINTS} >> nth=-1", last)
    page.mouse.move(0, 0)
    assert_hover_names_year(page, C2, f"{C2_TRIANGLES} >> nth=0", str(PV_YEARS[0]))
    page.mouse.move(0, 0)
    assert_hover_names_year(page, C2, f"{C2_STARS} >> nth=-1", str(PV_YEARS[-1]))
    page.mouse.move(0, 0)
    assert_hover_names_year(page, C2, f"{C2_STRIP} >> nth=0", str(DIFFERENT[0]))


@pytest.mark.plotlyjs_fetches(1)
def test_no_filter_reaches_c2_or_its_table(page: Page) -> None:
    """D096(b): the page has no filter, so the list's old keys change nothing."""
    open_c2(page, "?year_from=1900&pv=1")
    ticks = [b["text"] for b in boxes(page, f"{C2} .xtick text")]
    assert ticks == year_ticks()
    expect(page.locator(C2_POINTS)).to_have_count(len(served_years()))
    expect(page.locator(LEADER_ROWS)).to_have_count(len(served_years()))


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
@pytest.mark.parametrize("width", [*WIDE_WIDTHS, NARROW_DESKTOP, 390])
def test_every_width_keeps_order_measure_and_tables(page: Page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    open_c2(page, width=width)
    assert_layout_holds(page, MAJORITY_SUCCESS, ("#elections-leader-table",), width)
