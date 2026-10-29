"""The home page in a browser, at a phone's width (#321, after #306's manual check)."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from explore import components
from tests.e2e.dashboard_pages import (
    ELECTIONS_SUCCESS,
    HOME_SUCCESS,
    META,
    PROVENANCE,
    assert_rendered,
)

pytestmark = pytest.mark.e2e


def test_home_renders_its_coverage_and_the_provenance_footer(page: Page) -> None:
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    coverage = META["provenance"]["coverage"]
    expect(page.locator(HOME_SUCCESS)).to_contain_text(
        f"{coverage['year_min']}–{coverage['year_max']}"
    )
    expect(page.locator(HOME_SUCCESS)).to_contain_text(
        f"{coverage['pv_year_min']}–{coverage['pv_year_max']}"
    )
    expect(page.locator(f"{PROVENANCE} li")).to_have_count(len(components.SOURCES))


def test_homes_link_opens_the_elections_index(page: Page) -> None:
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    page.locator('a[href="/elections"]').click()
    expect(page).to_have_url(re.compile(r"/elections$"))
    assert_rendered(page, ELECTIONS_SUCCESS)
