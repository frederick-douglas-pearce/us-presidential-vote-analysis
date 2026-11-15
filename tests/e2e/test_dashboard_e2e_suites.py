"""The component-suite files a page loads, in a browser (#524).

Dash adds dash_table's bundle to every index, and no page renders a DataTable, so
``app.defer_dash_table_bundle`` marks it dynamic: no page requests any dash_table file.
dcc's ``async-datepicker`` chunk is not the date picker alone: it is a split chunk dcc's
own Graph, Dropdown and Slider loaders require, so a page with any of them still loads
it. The index's scripts do not depend on the page, so the home page and the not-found
page stand for every shell, and load none of dcc's lazily loaded chunks; ``/elections``,
with dropdowns, a slider and charts, is the control that the used chunk still loads.
Each test prints the suite files it saw (run with ``-s``), the browser network log
#524's acceptance asks for.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request

from tests.e2e.conftest import is_chunk
from tests.e2e.dashboard_pages import (
    ELECTIONS_SUCCESS,
    HOME_SUCCESS,
    NOT_FOUND_ERROR,
    PAGE_NOT_FOUND,
    assert_rendered,
)

pytestmark = pytest.mark.e2e

SUITES = "/_dash-component-suites/"

#: How long a page must request nothing new before a check that a request is absent
#: (the charts, election and nav modules wait as long).
SETTLE_MS = 500


def watch(page: Page) -> list[str]:
    """Record the path of every component-suite request ``page`` makes from now on."""
    seen: list[str] = []

    def on_request(request: Request) -> None:
        path = urlsplit(request.url).path
        if path.startswith(SUITES):
            seen.append(path[len(SUITES) :])

    page.on("request", on_request)
    return seen


def assert_shell_without_dash_table(path: str, seen: list[str]) -> None:
    print(f"\n{path}: {sorted(seen)}")
    assert not [s for s in seen if "/dash_table/" in s], seen
    # The control: the observer saw the shell's own bundles, the same kind of request
    # the line above finds absent.
    assert any(s.startswith("dash/dcc/dash_core_components.") for s in seen), seen
    assert any(s.startswith("dash/html/dash_html_components.") for s in seen), seen


def assert_no_lazy_dcc_chunk(page: Page, seen: list[str]) -> None:
    """A page with no Dropdown, Slider or Graph loads none of dcc's lazily loaded
    chunks (``dcc/async-*``), the date-picker chunk among them; dcc's two shell
    bundles load on every page by script tag. It waits long enough for a late chunk
    request to have gone out."""
    page.wait_for_timeout(SETTLE_MS)
    assert not [s for s in seen if s.startswith("dash/dcc/async-")], seen


def test_the_home_page_loads_no_dash_table_file(page: Page) -> None:
    seen = watch(page)
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert_shell_without_dash_table("/", seen)
    assert_no_lazy_dcc_chunk(page, seen)


@pytest.mark.expected_console_error(NOT_FOUND_ERROR)
def test_the_not_found_page_loads_no_dash_table_file(page: Page) -> None:
    seen = watch(page)
    page.goto("/no-such-page")
    page.locator(PAGE_NOT_FOUND).wait_for()
    assert_shell_without_dash_table("/no-such-page", seen)
    assert_no_lazy_dcc_chunk(page, seen)


def test_a_page_with_dropdowns_still_loads_the_shared_chunk(page: Page) -> None:
    """The used-chunk control: ``async-datepicker`` is lazy, so the success marker
    does not imply it loaded; the test waits for the request itself."""
    seen = watch(page)
    with page.expect_request(lambda r: is_chunk(r.url, "async-datepicker")):
        page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_shell_without_dash_table("/elections", seen)
