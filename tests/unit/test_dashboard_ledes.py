"""The filter sentence shows only where the filters show, on every filtered page (#419).

A filtered page's lede names its filters ("Narrow the …") in a sentence of its own,
added to the lede only when the filter controls render: on a successful render. The
not-found state shows no lede at all (#325), and the degraded states show the lede
alone. Each page's own tests cover some of these states; this module checks the
states below on every page that registers a ``query=`` parser. A new filtered page
fails ``test_every_filtered_page_is_listed`` until it gets an entry in
:data:`BREAKS`; its success and not-found paths are then derived from the registry,
in the style of ``test_dashboard_app.TestRegistryCoverage``.

The states, each confirmed before the sentence's absence is asserted:

- **degraded, unreachable API**: the client has no snapshot, so the page fails at
  ``api.CLIENT.view()``, before ``api.accepted`` or any read;
- **degraded after a broken read**: one read the page makes is broken, and the reads
  the test records show the page got past validation. A malformed body (the pattern
  of ``test_dashboard_state.TestMalformedBodies.client_with``) makes the page's
  ``render`` raise. On the elections subpages, whose read is N1, a failed N1 degrades
  the section instead and the page keeps its success marker: one of the two states
  where the page's ``filtered`` flag, not the success path, withholds the sentence.
  The other is the state history's (#620): a served body whose two charts'
  collapses both fail leaves nothing to narrow, so the page keeps its success
  marker and shows neither the slider nor the sentence;
- **not-found**, on the pages that validate a path value.

Not covered: a validate source failing inside ``api.accepted`` while a snapshot
serves, and a sentence rendered from text other than the page's ``FILTER_SENTENCE*``
constants. The candidate page's one-year sentence is never the one a default render
shows; ``test_dashboard_candidate.TestRequestBudget.
test_a_one_election_candidate_reads_the_one_state_sentence`` shows it renders. Only
the filter sentence is enforced, not the glossary's general rule that a page-level
sentence shows only where it is true (owner decision on #419, 2026-11-22). No helper
builds the lede: each page decides when its sentence shows in its own way (after
``render``, from ``filtered``, or inside ``render``), so a helper would hold none of
the rule (architect ruling on #419).
"""

from __future__ import annotations

import copy
import re
import sys
from collections.abc import Callable
from typing import Any, NamedTuple

import dash
import pytest

import tests.unit.test_dashboard_state as state_tests
from explore import api
from tests.unit.test_dashboard_app import (
    RECORDED,
    UNSERVED_VALUES,
    VERSION,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    concrete_page_path,
    failing_fetch,
    fake_fetch,
    offline_client,
    route,
    routed_ids,
)


class Break(NamedTuple):
    """The read to break on one filtered page."""

    #: A path the page reads after validation: served malformed, so the whole page
    #: degrades, or, with ``section_unavailable``, failed, so one section does.
    path: str
    #: The id the section shows when it degrades; ``None`` when the page degrades.
    section_unavailable: str | None = None
    #: With ``section_unavailable``: a change that serves ``path`` doctored rather
    #: than failing its read, for a page that withholds its filters when a served
    #: value leaves nothing to narrow (the state history, #620).
    doctor: Callable[[dict[str, Any]], None] | None = None


def _no_collapse(body: dict[str, Any]) -> None:
    """Two statuses in one of Georgia's elections: neither C7's nor C10's collapse
    can be read, so the state history has nothing to narrow and shows no slider
    (#620, D119), while the page keeps its success marker."""
    (first, *_) = [r for r in body["data"] if r["year"] == 1900]
    first["pv_status"] = "legislature_chosen"


#: Every filtered page (a registered ``query=`` parser) and the read to break on it.
BREAKS: dict[str, Break] = {
    # The index is the read /elections validates nothing against; N1 would leave the
    # filters rendered.
    "pages.elections": Break(api.ELECTIONS_PATH),
    "pages.elections_majority": Break(api.SUMMARY_PATH, "elections-leader-unavailable"),
    "pages.elections_over_time": Break(
        api.SUMMARY_PATH, "elections-over-time-unavailable"
    ),
    "pages.election_states": Break("/v1/elections/1824"),
    "pages.election_per_capita": Break("/v1/elections/1824/per-capita"),
    # T4 and its filters left the state history for this page (#619, D118).
    "pages.state_results": Break("/v1/states/GA"),
    # The state history's one filter, the year range (#620, D119): with both charts'
    # collapses unreadable, the shared table's sentence stands in its place and the
    # page keeps its success marker, but neither the slider nor the filter sentence
    # shows. Its whole-page degraded state is test_dashboard_state.TestLede's.
    "pages.state": Break(
        "/v1/states/GA", "state-electors-table-unavailable", _no_collapse
    ),
    "pages.state_per_capita": Break("/v1/states/GA/per-capita"),
    "pages.candidate": Break("/v1/candidates/andrew-jackson"),
    # C11's figure (#623, D124): a failed N2 degrades the history section alone, which
    # takes the map, its control and the filter sentence with it; the list of states
    # and the success marker stay.
    "pages.states": Break(api.ELECTION_STATES_PATH, "states-history-unavailable"),
}

NAMES = sorted(BREAKS)


def page(name: str) -> dict[str, Any]:
    found: dict[str, Any] = dash.page_registry[name]
    return found


def module(name: str) -> dict[str, Any]:
    """The page module's namespace (Dash loads it by path, under its registry name)."""
    return vars(sys.modules[page(name)["module"]])


def validates(name: str) -> bool:
    return page(name).get("validate") is not None


NOT_FOUND_NAMES = [n for n in NAMES if validates(n)]


def unserved_path(name: str) -> str:
    """The page's path at a well-formed value it does not serve."""
    template = page(name)["path_template"]
    return re.sub(r"<(.*?)>", lambda m: UNSERVED_VALUES[m.group(1)], template)


def sentences(name: str) -> list[str]:
    """Every filter sentence the page defines (the candidate page has two)."""
    found = [
        value
        for key, value in module(name).items()
        if key.startswith("FILTER_SENTENCE") and isinstance(value, str)
    ]
    assert found, name
    return found


def strings(node: Any) -> list[str]:
    """Every string in a decoded JSON value, in document order."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in strings(value)]
    if isinstance(node, list):
        return [s for value in node for s in strings(value)]
    return []


def text_of(response: Any) -> str:
    """The routing response's strings as they render, one per line. The raw body is
    JSON, which escapes quotes and backslashes (and Dash, non-ASCII characters too),
    so a sentence holding one would never match it there; each string is matched
    whole, never across two."""
    assert response.status_code == 200, response.status_code
    return "\n".join(strings(response.get_json()))


def unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process client that can read nothing, as ``test_dashboard_state.TestLede``
    builds it, and that does not wait for a snapshot that will never come."""
    client = offline_client(
        failing_fetch, prefetch_paths=lambda: [], max_request_wait=0
    )
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(api, "CLIENT", client)


def broken(monkeypatch: pytest.MonkeyPatch, spec: Break) -> list[str]:
    """A process client serving the recorded responses with ``spec.path`` broken, and
    the paths it then fetches. A page's body loses its ``meta``
    (``test_dashboard_state.TestMalformedBodies.client_with``); a section's read fails
    (never a changed value, which could reach a figure)."""
    if spec.section_unavailable is None:
        return state_tests.TestMalformedBodies.client_with(monkeypatch, spec.path)
    if spec.doctor is not None:
        bodies = copy.deepcopy(RECORDED)
        spec.doctor(bodies[spec.path])
        fetch_doctored, served = fake_fetch(bodies, VERSION)
        client = offline_client(
            fetch_doctored, prefetch_paths=lambda: [api.ELECTIONS_PATH]
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        served.clear()
        monkeypatch.setattr(api, "CLIENT", client)
        return served
    good, calls = fake_fetch(RECORDED, VERSION)

    def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        if path == spec.path:
            calls.append(path)
            raise api.ApiUnavailable("down")
        return good(path, timeout)  # type: ignore[no-any-return]

    client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    calls.clear()
    monkeypatch.setattr(api, "CLIENT", client)
    return calls


def assert_lede_alone(name: str, text: str) -> None:
    assert module(name)["LEDE"] in text
    for sentence in sentences(name):
        assert sentence not in text, (name, sentence)


class TestFilterSentence:
    def test_every_filtered_page_is_listed(self) -> None:
        # Three sets agree: the pages that read filters from the query string, the
        # pages that name a filter sentence, and this table. A new filtered page fails
        # here until it is listed, whatever it names its sentence.
        with_query = {n for n, p in dash.page_registry.items() if p.get("query")}
        with_sentence = {
            n
            for n in dash.page_registry
            if any(k.startswith("FILTER_SENTENCE") for k in module(n))
        }
        assert with_query == with_sentence == set(BREAKS)
        # /election/<year> has had no filters since #465; its subpages carry them.
        assert "pages.election" not in with_query

    @pytest.mark.parametrize("name", NAMES)
    def test_success_shows_the_lede_then_its_filter_sentence(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        # The positive control: without it, the negatives below would pass for a
        # constant that never renders.
        cached_client(monkeypatch)
        response = route(concrete_page_path(page(name)))
        assert page(name)["success"] in routed_ids(response)
        text = text_of(response)
        lede = module(name)["LEDE"]
        shown = [s for s in sentences(name) if f"{lede} {s}" in text]
        assert len(shown) == 1, (name, shown)
        assert text.count(shown[0]) == 1

    @pytest.mark.parametrize("name", NAMES)
    def test_the_unreachable_api_shows_the_lede_alone(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        unreachable(monkeypatch)
        response = route(concrete_page_path(page(name)))
        ids = routed_ids(response)
        assert "unavailable" in ids and page(name)["success"] not in ids
        assert_lede_alone(name, text_of(response))

    @pytest.mark.parametrize("name", NAMES)
    def test_a_broken_read_shows_the_lede_alone(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        spec = BREAKS[name]
        calls = broken(monkeypatch, spec)
        response = route(concrete_page_path(page(name)))
        ids = routed_ids(response)
        if spec.section_unavailable is None:
            assert "unavailable" in ids and page(name)["success"] not in ids
            if validates(name):
                # Fetched only once validation accepted the path, so ``render`` ran.
                assert spec.path in calls, calls
                assert module(name)["NOT_FOUND_ID"] not in ids
            else:
                # The index is served from the snapshot; N1 is read after it, in
                # ``render``'s view.
                assert api.SUMMARY_PATH in calls, calls
        else:
            assert spec.path in calls, calls
            assert spec.section_unavailable in ids
            assert page(name)["success"] in ids
        assert_lede_alone(name, text_of(response))

    @pytest.mark.parametrize("name", NOT_FOUND_NAMES)
    def test_not_found_shows_neither(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        cached_client(monkeypatch)
        response = route(unserved_path(name))
        assert module(name)["NOT_FOUND_ID"] in routed_ids(response)
        text = text_of(response)
        assert module(name)["LEDE"] not in text
        for sentence in sentences(name):
            assert sentence not in text, (name, sentence)
