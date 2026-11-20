"""Page section cards in a browser (#567, D111).

Each page section is one ``.card``: a top and a bottom rule in ``--card-edge`` and the
space around them, with no side edge and no side padding. The edge is decorative
(below 3:1, ``DECORATIVE`` in ``tests/unit/test_dashboard_theme.py``), so the space is
what separates the sections, and these tests measure it, on every page that shows a
card at each layout width: the space between a card and what is before and after it,
the space between a card's edge and what it holds, and that the space into a card is
larger than any space between the things inside it. Under forced colors the edge stays
a visible solid rule. No console error and no off-host request are asserted for every
test by ``conftest._browser_guard``.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page

from tests.e2e.dashboard_pages import (
    CANDIDATE_SUCCESS,
    ELECTION_SUCCESS,
    ELECTIONS_SUCCESS,
    HOME_SUCCESS,
    MAJORITY_SUCCESS,
    MEASURE_PX,
    NARROW_DESKTOP,
    OVER_TIME_SUCCESS,
    PER_CAPITA_SUCCESS,
    PHONE_WIDTHS,
    STATE_PER_CAPITA_SUCCESS,
    STATE_SUCCESS,
    STATES_SUCCESS,
    WIDE_WIDTHS,
    contrast_ratio,
)

pytestmark = pytest.mark.e2e

#: Every page that shows a card, at a recorded value, with its success marker and how
#: many cards it shows (the unit suite's ``CARD_COUNTS``).
CARD_PAGES: dict[str, tuple[str, int]] = {
    "/": (HOME_SUCCESS, 1),
    "/states": ("#states", 1),
    "/elections": (ELECTIONS_SUCCESS, 1),
    "/elections/majority": (MAJORITY_SUCCESS, 1),
    "/elections/over-time": (OVER_TIME_SUCCESS, 1),
    "/election/2016": (ELECTION_SUCCESS, 1),
    "/election/2016/states": (STATES_SUCCESS, 1),
    "/election/2016/per-capita": (PER_CAPITA_SUCCESS, 1),
    "/state/GA": (STATE_SUCCESS, 2),
    "/state/GA/per-capita": (STATE_PER_CAPITA_SUCCESS, 1),
    "/candidate/andrew-jackson": (CANDIDATE_SUCCESS, 1),
}
WIDTHS = [*WIDE_WIDTHS, NARROW_DESKTOP, *PHONE_WIDTHS]

#: The least space between a card's rule and the nearest thing outside it (1.5rem).
GAP_OUTSIDE_PX = 24
#: The least space between a card's rule and what it holds (0.75rem).
INSET_PX = 12


def open_page(page: Page, path: str, width: int) -> str:
    """``path`` at ``width``, its charts drawn; returns its success marker."""
    success, _ = CARD_PAGES[path]
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(path)
    page.locator(success).wait_for()
    # A chart's height settles only once plotly.js has drawn it.
    page.wait_for_function(
        """() => [...document.querySelectorAll("figure.chart")]
            .every(f => f.querySelector(".main-svg"))"""
    )
    return success


GEOMETRY = """() => {
    // Drawn: a box with height, not inside a closed <details> (a closed column-name
    // list or chart caption keeps layout boxes Chromium never paints).
    const shown = el => el.getBoundingClientRect().height > 0
        && el.checkVisibility({visibilityProperty: true, contentVisibilityAuto: true});
    const sibling = (el, step) => {
        let at = el[step];
        while (at && !shown(at)) at = at[step];
        return at;
    };
    return [...document.querySelectorAll(".card")].map(card => {
        const r = card.getBoundingClientRect();
        const s = getComputedStyle(card);
        const top = r.top + parseFloat(s.borderTopWidth);
        const bottom = r.bottom - parseFloat(s.borderBottomWidth);
        const inside = [...card.querySelectorAll("*")].filter(shown)
            .map(el => el.getBoundingClientRect());
        const first = Math.min(...inside.map(b => b.top));
        const last = Math.max(...inside.map(b => b.bottom));
        const kids = [...card.children].filter(shown)
            .map(el => el.getBoundingClientRect());
        const between = kids.slice(1).map((b, i) => b.top - kids[i].bottom);
        const before = sibling(card, "previousElementSibling");
        const after = sibling(card, "nextElementSibling");
        const above = before ? before.getBoundingClientRect().bottom : null;
        return {
            gapBefore: above === null ? null : r.top - above,
            gapAfter: after ? after.getBoundingClientRect().top - r.bottom : null,
            insetTop: first - top,
            insetBottom: bottom - last,
            into: above === null ? null : first - above,
            widestWithin: Math.max(0, ...between),
            left: r.left, width: r.width,
            side: [s.borderLeftWidth, s.borderRightWidth,
                   s.paddingLeft, s.paddingRight],
            wide: [...card.querySelectorAll("p, figcaption")]
                .filter(el => el.getBoundingClientRect().width > MEASURE_PX + 0.5).length,
        };
    });
}""".replace("MEASURE_PX", str(MEASURE_PX))


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("path", list(CARD_PAGES))
def test_space_separates_every_card(page: Page, path: str, width: int) -> None:
    success = open_page(page, path, width)
    _, count = CARD_PAGES[path]
    found: list[dict[str, Any]] = page.evaluate(GEOMETRY)
    assert len(found) == count, found
    content = page.evaluate(
        f"""() => {{
            const r = document.querySelector("{success}").getBoundingClientRect();
            return {{left: r.left, width: r.width,
                     page: document.documentElement.scrollWidth <= innerWidth}};
        }}"""
    )
    # The page never scrolls sideways (home and the States list have no layout test
    # of their own, so this is theirs too).
    assert content["page"], content
    for card in found:
        # No side edge or side padding: a card is exactly as wide as the page's
        # content, so it takes no width from a table or a chart (the owner's choice
        # at #567's plan gate).
        assert card["side"] == ["0px", "0px", "0px", "0px"], card
        assert abs(card["width"] - content["width"]) <= 1, (card, content)
        # Running text keeps the measure inside a card (D102(f)).
        assert card["wide"] == 0, card
        # The space around a card, and inside its rules.
        if card["gapBefore"] is not None:
            assert card["gapBefore"] >= GAP_OUTSIDE_PX, card
        if card["gapAfter"] is not None:
            assert card["gapAfter"] >= GAP_OUTSIDE_PX, card
        assert card["insetTop"] >= INSET_PX, card
        assert card["insetBottom"] >= INSET_PX, card
        # Spacing alone separates the sections: the way into a card is wider than any
        # gap between the things inside it.
        if card["into"] is not None:
            assert card["into"] > card["widestWithin"], card


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_forced_colors_keep_each_card_s_rules(page: Page, scheme: str) -> None:
    """In both forced palettes (Chromium's emulation), each of the state history's two
    cards keeps a solid top and bottom rule at least 1 px wide, at 3:1 against the
    page's backdrop: the edge stays visible rather than being lost."""
    page.emulate_media(color_scheme=scheme, forced_colors="active")  # type: ignore[arg-type]
    open_page(page, "/state/GA", 390)
    painted = page.evaluate(
        """() => ({
            cards: [...document.querySelectorAll(".card")].map(card => {
                const s = getComputedStyle(card);
                return {
                    top: [parseFloat(s.borderTopWidth), s.borderTopStyle,
                          s.borderTopColor],
                    bottom: [parseFloat(s.borderBottomWidth), s.borderBottomStyle,
                             s.borderBottomColor],
                };
            }),
            backdrop: getComputedStyle(document.body).backgroundColor,
        })"""
    )
    assert len(painted["cards"]) == 2, painted
    for card in painted["cards"]:
        for width, style, color in (card["top"], card["bottom"]):
            assert width >= 1 and style == "solid", painted
            assert contrast_ratio(color, painted["backdrop"]) >= 3.0, (color, painted)
