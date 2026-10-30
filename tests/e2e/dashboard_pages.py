"""What the browser tests locate and expect (#321).

Element ids and the field list a page module defines are written out here: Dash
executes a page module itself, so a test cannot import one. Shared ids, labels and
helpers are imported from ``explore`` so a test follows the shipped value, and expected
data values come from the recorded responses, never literals. It reads two recorded
responses at import, as ``test_dashboard_app.py`` does.
"""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Locator, Page

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
GLOSSARY = f"{ELECTIONS_SUCCESS} details.glossary"
#: T1's columns, as pages/elections.py's ``FIELDS`` lists them.
FIELDS = ("year", "candidate_count", "has_popular_vote")

# Ids of the one-election view (pages/election.py).
ELECTION_SUCCESS = "#election"
ELECTION_EARLIER = "#election-earlier"
ELECTION_LATER = "#election-later"

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
    """Whether both paths the one-election view fills for ``year`` are recorded."""
    return all(
        path in RECORDED_FILES
        for path in (f"/v1/elections/{year}", f"/v1/elections/{year}/per-capita")
    )


_SERVED = [e["year"] for e in ELECTIONS["data"]]
#: Two consecutive served years whose one-election views are both recorded, from the
#: recorded index: where the browser test steps from one election to the next (#324).
STEP_FROM, STEP_TO = next(
    (a, b)
    for a, b in zip(_SERVED, _SERVED[1:], strict=False)
    if _recorded_year(a) and _recorded_year(b)
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


def assert_rendered(page: Page, success: str) -> None:
    """The page rendered from data at the phone's width: its success marker is there,
    the degraded state is not."""
    page.locator(success).wait_for()
    assert page.locator(UNAVAILABLE).count() == 0
    # Written out, not read from VIEWPORT, so editing that constant cannot move the
    # width this suite claims to check: #306's phone, 390 px.
    assert page.evaluate("innerWidth") == 390
