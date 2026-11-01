"""The one-election view's earlier and later links in a browser (#324).

From a filtered view, the later link opens the next served year's own view
unfiltered, as a client-side navigation (a marker set on ``window`` before the click
survives it, which a full page load would clear), and back returns to the view it
left. No console error and no off-host request are asserted for every test by
``conftest._browser_guard``.
"""

from __future__ import annotations

import re

import dash
import pytest
from playwright.sync_api import Page, expect

import explore.app  # noqa: F401  (registers the pages, whose not-found states it reads)
from tests.e2e.dashboard_pages import (
    ELECTION_EARLIER,
    ELECTION_LATER,
    ELECTION_SUCCESS,
    assert_rendered,
    step_years,
)

pytestmark = pytest.mark.e2e

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
    expect(page.get_by_role("navigation")).to_have_count(1)
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


@pytest.mark.expected_console_error(
    "Failed to load resource: the server responded with a status of 404 (NOT FOUND)"
)
def test_an_unserved_year_reads_as_not_found_in_the_tab_and_the_page(
    page: Page,
) -> None:
    """#325: Dash's client router sets the tab from the page's title after the layout
    ran, so only a browser shows that the tab follows the year's validation. The
    document's own 404 is the one console error, and the guard requires it."""
    not_found = dash.page_registry["pages.election"]["not_found"]
    response = page.goto("/election/1825")
    assert response is not None and response.status == 404
    expect(page.get_by_role("heading", level=1)).to_have_text(not_found.heading)
    expect(page).to_have_title(not_found.title)
    expect(page.locator("#election-not-found")).to_contain_text(not_found.sentence)
