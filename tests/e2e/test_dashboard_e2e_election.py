"""The one-election view's earlier and later links in a browser (#324).

From a filtered view, the later link opens the next served year's own view
unfiltered, as a client-side navigation (a marker set on ``window`` before the click
survives it, which a full page load would clear), and back returns to the view it
left. No console error and no off-host request are asserted for every test by
``conftest._browser_guard``.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

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
