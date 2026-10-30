"""The one-election view's earlier and later links in a browser (#324).

A link is a client-side navigation to the next served year's own view, and back
returns to the year it left. No console error and no off-host request are asserted
for every test by ``conftest._browser_guard``.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.dashboard_pages import (
    ELECTION_EARLIER,
    ELECTION_LATER,
    ELECTION_SUCCESS,
    STEP_FROM,
    STEP_TO,
    assert_rendered,
)

pytestmark = pytest.mark.e2e


def assert_year(page: Page, year: int) -> None:
    expect(page).to_have_url(re.compile(re.escape(f"/election/{year}") + "$"))
    assert_rendered(page, ELECTION_SUCCESS)
    expect(page.get_by_role("heading", level=1)).to_contain_text(str(year))


def test_the_later_link_opens_the_next_election_and_back_returns(page: Page) -> None:
    page.goto(f"/election/{STEP_FROM}")
    assert_year(page, STEP_FROM)
    expect(page.get_by_role("navigation")).to_have_count(1)
    later = page.locator(ELECTION_LATER)
    expect(later).to_have_attribute("href", f"/election/{STEP_TO}")
    later.click()
    assert_year(page, STEP_TO)
    expect(page.locator(ELECTION_EARLIER)).to_have_attribute(
        "href", f"/election/{STEP_FROM}"
    )
    page.go_back()
    assert_year(page, STEP_FROM)
