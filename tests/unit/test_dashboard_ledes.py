"""The filter sentence shows only where the filters show, on every filtered page (#419).

A filtered page's lede names its filters ("Narrow the …") in a sentence of its own,
added to the lede only when the filter controls render: on a successful render. The
not-found state shows no lede at all (#325), and the degraded states show the lede
alone. Each page's own tests cover some of these states; this module checks all of
them on every page that registers a ``query=`` parser, in the style of
``TestRegistryCoverage``, so a new filtered page is covered as soon as it registers.

The states, each reached and confirmed before the sentence's absence is asserted:

- **degraded, unreachable API**: nothing can be read, so the page shows its
  unavailable state before any read (on the validated pages, inside ``api.accepted``);
- **degraded after validation**: the page's own data path is served malformed, so the
  page's ``render`` runs and raises (on the two elections subpages, whose read is N1,
  the section degrades instead and the page keeps its success marker; that is the
  one state where the page's ``filtered`` flag, not the success path, withholds the
  sentence);
- **not-found**, on the five pages that validate a path value.

What this does not catch: a filter sentence rendered from text other than the page's
``FILTER_SENTENCE*`` constants. Only the filter sentence is enforced, not the
glossary's general rule that a page-level sentence shows only where it is true (owner
decision on #419, 2026-11-22). No helper builds the lede: each page decides when its
sentence shows in its own way (after ``render``, from ``filtered``, or inside
``render``), so a helper would hold none of the rule (architect ruling on #419).
"""

from __future__ import annotations

import copy
from typing import Any, NamedTuple

import dash
import pytest

from explore import api
from tests.unit.test_dashboard_app import (
    RECORDED,
    VERSION,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    failing_fetch,
    offline_client,
    route,
    routed_ids,
)


class Filtered(NamedTuple):
    """How to reach each state of one filtered page."""

    #: A served path whose default render succeeds.
    success: str
    #: A path the page validates and refuses, or ``None`` where it validates none.
    not_found: str | None
    #: The read to serve malformed (``page``) or failed (``section``).
    breaks: str
    #: ``page``: the whole page degrades; ``section``: one section does, and the page
    #: keeps its success marker.
    degrades: str
    #: The id the section shows when it degrades (``section`` only).
    section_unavailable: str | None = None


#: Every filtered page: the registered pages with a ``query=`` parser.
FILTERED_PAGES: dict[str, Filtered] = {
    "pages.elections": Filtered("/elections", None, api.ELECTIONS_PATH, "page"),
    "pages.elections_majority": Filtered(
        "/elections/majority",
        None,
        api.SUMMARY_PATH,
        "section",
        "elections-leader-unavailable",
    ),
    "pages.elections_over_time": Filtered(
        "/elections/over-time",
        None,
        api.SUMMARY_PATH,
        "section",
        "elections-over-time-unavailable",
    ),
    "pages.election_states": Filtered(
        "/election/1824/states",
        "/election/1825/states",
        "/v1/elections/1824",
        "page",
    ),
    "pages.election_per_capita": Filtered(
        "/election/1824/per-capita",
        "/election/1825/per-capita",
        "/v1/elections/1824/per-capita",
        "page",
    ),
    "pages.state": Filtered("/state/GA", "/state/ZZ", "/v1/states/GA", "page"),
    "pages.state_per_capita": Filtered(
        "/state/GA/per-capita",
        "/state/ZZ/per-capita",
        "/v1/states/GA/per-capita",
        "page",
    ),
    "pages.candidate": Filtered(
        "/candidate/andrew-jackson",
        "/candidate/nobody-ever",
        "/v1/candidates/andrew-jackson",
        "page",
    ),
}

NAMES = sorted(FILTERED_PAGES)
NOT_FOUND_NAMES = sorted(n for n, p in FILTERED_PAGES.items() if p.not_found)


def page(name: str) -> dict[str, Any]:
    found: dict[str, Any] = dash.page_registry[name]
    return found


def module(name: str) -> dict[str, Any]:
    """The page module's namespace, reached through its layout (Dash loads it by
    path)."""
    namespace: dict[str, Any] = page(name)["layout"].__globals__
    return namespace


def sentences(name: str) -> list[str]:
    """Every filter sentence the page defines (the candidate page has two)."""
    found = [
        value
        for key, value in module(name).items()
        if key.startswith("FILTER_SENTENCE") and isinstance(value, str)
    ]
    assert found, name
    return found


def body_of(response: Any) -> str:
    assert response.status_code == 200, response.status_code
    return str(response.get_data(as_text=True))


def unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process client that can read nothing, built as ``TestLede`` builds it."""
    client = offline_client(failing_fetch, prefetch_paths=lambda: [])
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(api, "CLIENT", client)


def broken(monkeypatch: pytest.MonkeyPatch, spec: Filtered) -> None:
    """A process client serving the recorded responses with ``spec.breaks`` broken:
    a failed read for a section (never a changed value, which could reach a figure),
    a body without ``meta`` for a page (``TestMalformedBodies.client_with``)."""
    bodies = copy.deepcopy(RECORDED)
    if spec.degrades == "page":
        del bodies[spec.breaks]["meta"]

    def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        if spec.degrades == "section" and path == spec.breaks:
            raise api.ApiUnavailable("down")
        return api.Response(body=bodies[path], version=VERSION)

    client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    monkeypatch.setattr(api, "CLIENT", client)


class TestFilterSentence:
    def test_every_filtered_page_is_listed(self) -> None:
        # Three sets agree: the pages that read filters from the query string, the
        # pages that name a filter sentence, and this table. A new filtered page fails
        # here until it is listed, whatever it names its sentence.
        with_query = {n for n, p in dash.page_registry.items() if p.get("query")}
        with_sentence = {
            n
            for n, p in dash.page_registry.items()
            if any(k.startswith("FILTER_SENTENCE") for k in p["layout"].__globals__)
        }
        assert with_query == with_sentence == set(FILTERED_PAGES)
        # /election/<year> has had no filters since #465; its subpages carry them.
        assert "pages.election" not in with_query

    @pytest.mark.parametrize("name", NAMES)
    def test_success_shows_the_lede_then_its_filter_sentence(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        # The positive control: without it, the negatives below would pass for a
        # constant that never renders.
        cached_client(monkeypatch)
        response = route(FILTERED_PAGES[name].success)
        assert page(name)["success"] in routed_ids(response)
        body = body_of(response)
        lede = module(name)["LEDE"]
        shown = [s for s in sentences(name) if f"{lede} {s}" in body]
        assert len(shown) == 1, (name, shown)
        assert body.count(shown[0]) == 1

    @pytest.mark.parametrize("name", NAMES)
    def test_the_unreachable_api_shows_the_lede_alone(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        unreachable(monkeypatch)
        response = route(FILTERED_PAGES[name].success)
        ids = routed_ids(response)
        assert "unavailable" in ids and page(name)["success"] not in ids
        body = body_of(response)
        assert module(name)["LEDE"] in body
        for sentence in sentences(name):
            assert sentence not in body, (name, sentence)

    @pytest.mark.parametrize("name", NAMES)
    def test_a_broken_read_shows_the_lede_alone(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        spec = FILTERED_PAGES[name]
        broken(monkeypatch, spec)
        response = route(spec.success)
        ids = routed_ids(response)
        if spec.degrades == "page":
            assert "unavailable" in ids and page(name)["success"] not in ids
        else:
            assert spec.section_unavailable in ids
            assert page(name)["success"] in ids
        body = body_of(response)
        assert module(name)["LEDE"] in body
        for sentence in sentences(name):
            assert sentence not in body, (name, sentence)

    @pytest.mark.parametrize("name", NOT_FOUND_NAMES)
    def test_not_found_shows_neither(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        cached_client(monkeypatch)
        not_found = FILTERED_PAGES[name].not_found
        assert not_found is not None
        response = route(not_found)
        assert module(name)["NOT_FOUND_ID"] in routed_ids(response)
        body = body_of(response)
        assert module(name)["LEDE"] not in body
        for sentence in sentences(name):
            assert sentence not in body, (name, sentence)
