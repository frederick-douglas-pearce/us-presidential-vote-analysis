"""The elections index (T1) and the shared table conventions it sets (#306).

Offline, against the recorded ``/v1/elections`` fixture, through the helpers and the
autouse offline process client of ``test_dashboard_app.py``. Its registry-wide checks
pick this page up from the registry: ``TestRegistryCoverage``,
``TestRegistryContracts.test_every_query_parser_keeps_its_contract`` and
``test_every_registered_page_is_found_at_the_index_and_reads_nothing``; so do the D070(b)
guard's two runs in ``test_dashboard_guards.py``. These tests cover what is particular
to this page.
"""

from __future__ import annotations

import ast
import copy
import functools
import json
import sys
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, TypeGuard

import dash
import pytest
from dash import html, no_update
from dash.development.base_component import Component

from explore import api, charts, components, elections_view, labels, metrics
from explore import app as appmod
from tests.unit.test_dashboard_app import (
    META,
    RECORDED,
    VERSION,
    RecordingBucket,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    component_ids,
    concrete_page_path,
    fake_fetch,
    get,
    home_module,
    offline_client,
    route,
    routed_ids,
    texts,
)
from tests.unit.test_dashboard_guards import RUNTIME_MODULES

PAGE: dict[str, Any] = dash.page_registry["pages.elections"]
#: The page module's namespace. Dash loads a page by path, as ``pages.elections``, so
#: it is reached through its layout rather than imported a second time.
MOD: dict[str, Any] = PAGE["layout"].__globals__

BODY: dict[str, Any] = RECORDED[api.ELECTIONS_PATH]
YEARS = [row["year"] for row in BODY["data"]]
PV_YEARS = [row["year"] for row in BODY["data"] if row["has_popular_vote"]]
COVERAGE = BODY["meta"]["provenance"]["coverage"]
FIRST, LAST = COVERAGE["year_min"], COVERAGE["year_max"]

PAGE_ID = MOD["PAGE_ID"]
TABLE_ID = MOD["TABLE_ID"]
YEARS_ID = MOD["YEARS_ID"]
PV_ID = MOD["PV_ID"]
#: The paths a first render fills on a miss: N1 for the averages (#437); C2, C4 and C5
#: read it from their own pages since #562, and no page reads N2 (D107).
FILLS_TUPLE = (api.SUMMARY_PATH,)
FILLS = list(FILLS_TUPLE)


def find(node: Any, wanted: str) -> Any:
    """The component with ``id`` ``wanted`` in a rendered tree, or ``None``."""
    if isinstance(node, (list, tuple)):
        for child in node:
            found = find(child, wanted)
            if found is not None:
                return found
        return None
    if isinstance(node, Component):
        if getattr(node, "id", None) == wanted:
            return node
        return find(getattr(node, "children", None), wanted)
    return None


def in_order(node: Any) -> list[Any]:
    """Every component in a rendered tree, in document order."""
    if isinstance(node, (list, tuple)):
        return [c for child in node for c in in_order(child)]
    if isinstance(node, Component):
        return [node, *in_order(getattr(node, "children", None))]
    return []


def of_type(node: Any, name: str) -> list[Any]:
    """Every component of type ``name`` in a rendered tree, depth-first."""
    if isinstance(node, (list, tuple)):
        return [c for child in node for c in of_type(child, name)]
    if isinstance(node, Component):
        own = [node] if type(node).__name__ == name else []
        return own + of_type(getattr(node, "children", None), name)
    return []


def classed(node: Any, wanted: str) -> list[Any]:
    """Every component in a rendered tree whose class list holds ``wanted``,
    depth-first, as :func:`of_type` walks it."""
    if isinstance(node, (list, tuple)):
        return [c for child in node for c in classed(child, wanted)]
    if isinstance(node, Component):
        names = (getattr(node, "className", None) or "").split()
        own = [node] if wanted in names else []
        return own + classed(getattr(node, "children", None), wanted)
    return []


def render(query: dict[str, Any] | None = None, body: Any = None) -> Any:
    """The page body for ``query``, as the layout builds it from a response."""
    body = copy.deepcopy(BODY if body is None else body)
    return MOD["render"](body, MOD["parse_filters"](query or {}))


def rows(tree: Any) -> list[list[str]]:
    table = find(tree, TABLE_ID)
    if table is None:
        return []
    return [texts(tr.children) for tr in of_type(of_type(table, "Tbody"), "Tr")]


def shown_years(tree: Any) -> list[int]:
    return [int(row[0]) for row in rows(tree)]


def json_node(node: Any, wanted: str) -> Any:
    """The component with ``id`` ``wanted`` in a routed response's JSON, or ``None``."""
    if isinstance(node, list):
        for child in node:
            found = json_node(child, wanted)
            if found is not None:
                return found
    elif isinstance(node, dict):
        props = node.get("props")
        if isinstance(props, dict) and props.get("id") == wanted:
            return node
        for value in node.values():
            found = json_node(value, wanted)
            if found is not None:
                return found
    return None


def routed_years(response: Any) -> list[int]:
    """The year column of the table a routed render carries; ``[]`` with no table."""
    table = json_node(response.get_json(), TABLE_ID)
    if table is None:
        return []
    head, body = table["props"]["children"]
    assert body["type"] == "Tbody"
    years = []
    for tr in body["props"]["children"]:
        link = tr["props"]["children"][0]["props"]["children"]  # the year's Link (#307)
        assert link["type"] == "Link"
        years.append(int(link["props"]["children"]))
    return years


def parse(query: str) -> dict[str, Any]:
    """A query string as Dash's router hands it to a layout."""
    return dash._pages._parse_query_string(f"?{query}") if query else {}


def from_controls(years: Any, pv: Any, first: Any, last: Any) -> str:
    """The search the year and popular-vote controls write from an empty URL: the
    years control's change, then the pv control's, each replacing only its own keys
    (``merged_search``, #436)."""
    after_years = MOD["merged_search"](YEARS_ID, years, pv, first, last, "")
    search: str = MOD["merged_search"](PV_ID, years, pv, first, last, after_years)
    return search


def controls(tree: Any) -> tuple[Any, Any]:
    return find(tree, YEARS_ID), find(tree, PV_ID)


# --- T1: rows and span from the response ---------------------------------------------


class TestTable:
    def test_lists_every_served_year(self) -> None:
        tree = render()
        assert shown_years(tree) == YEARS
        assert YEARS[0] == 1824 and YEARS[-1] == 2024  # the served span today
        assert f"Showing {len(YEARS)} of {len(YEARS)} elections" in texts(tree)

    def test_rows_and_span_are_read_from_the_response_not_literals(self) -> None:
        body = copy.deepcopy(BODY)
        body["meta"]["provenance"]["coverage"].update(year_min=1788, year_max=2032)
        body["data"] = [
            {"year": 1788, "candidate_count": 12, "has_popular_vote": False},
            {"year": 2032, "candidate_count": 3, "has_popular_vote": True},
        ]
        tree = render(body=body)
        assert rows(tree) == [
            ["1788", "12", labels.NOT_IN_DATASET],
            ["2032", "3", "Yes"],
        ]
        years, _ = controls(tree)
        assert (years.min, years.max, years.value) == (1788, 2032, [1788, 2032])
        assert not any("1824" in t or "2024" in t for t in texts(tree))
        # The slider's labels are props, not children, so texts() cannot see them.
        assert (min(years.marks), max(years.marks)) == (1788, 2032)
        assert 1824 not in years.marks and 2024 not in years.marks

    def test_each_year_links_to_its_one_election_view(self) -> None:
        """Clicking a year in T1 opens that year's /election/<year> (#307)."""
        table = find(render(), TABLE_ID)
        links = of_type(table, "Link")
        assert [(link.children, link.href) for link in links] == [
            (str(y), f"/election/{y}") for y in YEARS
        ]
        election = dash.page_registry["pages.election"]
        for link in links:
            page, path_vars = dash._pages._path_to_page(link.href.strip("/"))
            assert page["module"] == election["module"], link.href
            assert election["validate"][1](path_vars, BODY) is True, link.href

    def test_every_false_has_popular_vote_reads_not_in_this_dataset(self) -> None:
        assert labels.NOT_IN_DATASET == "Not in this dataset"  # the AC's wording
        cells = {row[0]: row[2] for row in rows(render())}
        for record in BODY["data"]:
            expected = "Yes" if record["has_popular_vote"] else labels.NOT_IN_DATASET
            assert cells[str(record["year"])] == expected
        assert labels.NOT_IN_DATASET in cells.values()
        assert "No" not in texts(render())

    def test_an_unexpected_has_popular_vote_is_never_a_claim_or_raw(self) -> None:
        # #355: a null names no cause; any other non-bool is unrecognized.
        assert labels.has_popular_vote(None) == labels.NOT_IN_DATASET
        assert labels.has_popular_vote(0) == labels.UNRECOGNIZED
        # Truthy non-bools too: only True itself may claim the dataset holds it.
        assert labels.has_popular_vote(1) == labels.UNRECOGNIZED
        assert labels.has_popular_vote("false") == labels.UNRECOGNIZED


# --- filters ---------------------------------------------------------------------


class TestFilters:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ({"year_from": "1900", "year_to": "1950"}, range(1900, 1951)),
            ({"year_from": "1990"}, range(1990, 2025)),
            ({"year_to": "1840"}, range(1824, 1841)),
            ({"pv": "1"}, PV_YEARS),
            ({"pv": "1", "year_to": "1990"}, range(1976, 1991)),
        ],
    )
    def test_the_filters_select_the_rows(
        self, query: dict[str, Any], expected: Any
    ) -> None:
        assert shown_years(render(query)) == [y for y in YEARS if y in set(expected)]

    def test_the_controls_cannot_invert_and_keep_no_state_of_their_own(self) -> None:
        years, pv = controls(render())
        assert (years.min, years.max, years.step) == (FIRST, LAST, 1)
        assert years.allowCross is False
        # A typed digit would commit mid-year and re-render the page under the reader.
        assert years.allow_direct_input is False
        # Browser storage would override the URL, the only filter state.
        assert getattr(years, "persistence", None) is None
        assert getattr(pv, "persistence", None) is None
        assert [o["value"] for o in pv.options] == ["1"]

    @pytest.mark.parametrize(
        ("first", "last"), [(FIRST, LAST), (1788, 2032), (1830, 1850)]
    )
    def test_slider_labels_never_crowd_each_other(self, first: int, last: int) -> None:
        """The 390 px smoke test found "1824" and "1840" printed as one word."""
        marks = sorted(components.year_marks(first, last))
        assert marks[0] == first and marks[-1] == last
        gaps = [b - a for a, b in zip(marks, marks[1:], strict=False)]
        # A literal, not the module's own constant: 16 years (1824 to 1840) crowded.
        assert all(gap >= 20 for gap in gaps), marks

    def test_the_served_span_s_slider_labels(self) -> None:
        assert sorted(components.year_marks(FIRST, LAST)) == [
            1824,
            1880,
            1920,
            1960,
            2000,
            2024,
        ]

    def test_the_controls_show_the_filters_in_force(self) -> None:
        years, pv = controls(render({"year_from": "1900", "pv": "1"}))
        assert years.value == [1900, LAST]
        assert pv.value == ["1"]

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ({"year_from": "2000", "year_to": "1900"}, (FIRST, LAST, False)),
            ({"year_from": "1700"}, (FIRST, LAST, False)),
            ({"year_to": "3000"}, (FIRST, LAST, False)),
            ({"year_from": "19x0", "pv": "yes"}, (FIRST, LAST, False)),
            ({"year_from": "١٩٧٦"}, (FIRST, LAST, False)),
            ({"junk": "1", "<script>": "x"}, (FIRST, LAST, False)),
            ({"year_from": ["1900", "1950"]}, (FIRST, LAST, False)),
            # Per parameter: the valid filters stay, as og:url keeps them.
            ({"year_from": "1976", "year_to": "3000"}, (1976, LAST, False)),
            ({"year_from": "1976", "pv": ["1", "0"], "junk": "x"}, (1976, LAST, False)),
            ({"year_to": "1900", "pv": ["1", "1"]}, (FIRST, 1900, True)),
        ],
    )
    def test_a_bad_parameter_falls_back_to_that_filter_s_default(
        self, query: dict[str, Any], expected: tuple[int, int, bool]
    ) -> None:
        years, pv = controls(render(query))
        assert (years.value[0], years.value[1], pv.value == ["1"]) == expected

    @pytest.mark.parametrize(
        "search",
        [
            "?year_from=2000&year_to=1900",
            "?year_from=%00&pv=%3Cscript%3E",
            "?year_from=1976&year_from=1980&year_to=",
            "?" + urllib.parse.quote("<>\"'&="),
            "?year_to=1900&pv=1",  # matches nothing: still a successful render
        ],
    )
    def test_a_hostile_query_never_errors_or_blanks_the_page(
        self, monkeypatch: pytest.MonkeyPatch, search: str
    ) -> None:
        cached_client(monkeypatch)
        response = route("/elections", search)
        assert response.status_code == 200
        assert PAGE_ID in routed_ids(response)

    def test_an_empty_result_is_still_a_successful_render(self) -> None:
        tree = render({"year_to": "1900", "pv": "1"})
        assert PAGE_ID in component_ids(tree)
        assert TABLE_ID not in component_ids(tree)
        assert "No elections match these filters." in texts(tree)
        assert f"Showing 0 of {len(YEARS)} elections" in texts(tree)


# --- the one parser ----------------------------------------------------------------


class TestParser:
    @pytest.mark.parametrize(
        ("params", "pairs"),
        [
            ({}, []),
            (
                {"year_to": "1950", "pv": "1", "year_from": "1900"},
                [("pv", "1"), ("year_from", "1900"), ("year_to", "1950")],
            ),
            ({"year_from": ["1900", "1900"]}, [("year_from", "1900")]),
            ({"year_from": ["1900", "1904"]}, []),
            ({"year_from": "2000", "year_to": "1900"}, []),
            (
                {"year_from": "1900", "year_to": "1900"},
                [("year_from", "1900"), ("year_to", "1900")],
            ),
            ({"year_from": "1976\n"}, []),
            ({"year_from": "١٩٧٦"}, []),
            ({"year_from": "176"}, []),
            ({"pv": "true"}, []),
            ({"pv": ""}, []),
            # The state key moved to a path (#562): the parser drops it.
            ({"from": "1900", "state": "OH"}, []),
            ({"year_from": 1900}, []),
        ],
    )
    def test_parse_filters(self, params: dict[str, Any], pairs: list[Any]) -> None:
        assert MOD["parse_filters"](params) == pairs

    def test_parse_filters_is_total_over_a_non_dict(self) -> None:
        assert MOD["parse_filters"](None) == []

    def test_the_registered_parser_is_the_layout_s_parser(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert PAGE["query"] is MOD["parse_filters"]
        cached_client(monkeypatch)
        seen: list[dict[str, Any]] = []
        original = MOD["parse_filters"]

        def spy(params: dict[str, Any]) -> list[tuple[str, str]]:
            seen.append(dict(params))
            return [("pv", "1")]  # not what the query says: the render must follow it

        monkeypatch.setitem(MOD, "parse_filters", spy)
        tree = PAGE["layout"](**{"year_from": "1900"})
        assert seen == [{"year_from": "1900"}]
        assert shown_years(tree) == PV_YEARS
        assert original({"year_from": "1900"}) == [("year_from", "1900")]


# --- shareable URL state: og:url, and the callback that writes the URL ---------------

SHARED = (
    "year_to=1990&junk=x&pv=1&year_from=1976&year_from=1976",
    "pv=1&year_from=1900&year_from=1904",  # a repeated, differing value is dropped
    "year_from=2000&year_to=1900&pv=1",  # an inverted range is dropped
    "year_from=1700&pv=1",  # syntactically kept; outside the span in the layout
    "junk=1",
)


class TestShareableUrl:
    @pytest.mark.parametrize("query", SHARED)
    def test_a_filtered_og_url_reopens_the_filtered_view(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        cached_client(monkeypatch)
        status, head, _ = get(f"/elections?{query}")
        assert status == 200
        assert head.og_url is not None
        # The attribute was HTML-escaped; Head's parser unescapes it, as a platform would.
        reopened = urllib.parse.urlsplit(head.og_url)
        assert reopened.path == "/elections"
        original = route("/elections", f"?{query}")
        again = route(reopened.path, f"?{reopened.query}" if reopened.query else "")
        assert PAGE_ID in routed_ids(original)
        assert original.get_json() == again.get_json()
        # The renders are the filtered view, not two copies of the default one.
        assert routed_years(original) == shown_years(render(parse(query)))

    def test_the_round_trip_check_sees_a_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuity: SHARED[0] filters, so a router that dropped the query fails."""
        cached_client(monkeypatch)
        filtered = routed_years(route("/elections", f"?{SHARED[0]}"))
        assert filtered == [1976, 1980, 1984, 1988]
        assert filtered != YEARS

    def test_the_og_url_query_is_the_normal_form(self) -> None:
        resolution = appmod.resolve("/elections", SHARED[0], None)
        assert resolution.og_url is not None
        assert resolution.og_url.endswith("/elections?pv=1&year_from=1976&year_to=1990")

    @pytest.mark.parametrize("query", [SHARED[0], SHARED[1], "", "year_to=1990"])
    def test_the_callback_writes_the_og_url_s_query_byte_for_byte(
        self, query: str
    ) -> None:
        """A fixed point: the URL written from a render's controls is its og:url's."""
        years, pv = controls(render(parse(query)))
        written = from_controls(years.value, pv.value, years.min, years.max)
        og_url = appmod.resolve("/elections", query, None).og_url
        assert og_url is not None
        expected = urllib.parse.urlsplit(og_url).query
        assert written == (f"?{expected}" if expected else "")

    @pytest.mark.parametrize(
        "query", ["year_from=1824&year_to=2024", "year_from=1700&pv=1", "pv=1&junk=x"]
    )
    def test_where_the_bytes_differ_both_urls_open_the_same_view(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        """og:url keeps a bound the layout replaced with its default (an explicit
        default, or a year outside the span); the callback, seeing only the controls,
        omits it. The two URLs still render the same view."""
        cached_client(monkeypatch)
        years, pv = controls(render(parse(query)))
        written = from_controls(years.value, pv.value, years.min, years.max)
        og_url = appmod.resolve("/elections", query, None).og_url
        assert og_url is not None
        shared = urllib.parse.urlsplit(og_url).query
        by_callback = route("/elections", written)
        by_og_url = route("/elections", f"?{shared}" if shared else "")
        assert by_callback.get_json() == by_og_url.get_json()
        assert routed_years(by_callback) == shown_years(render(parse(query)))

    def test_the_callback_is_wired_to_the_page_s_location(self) -> None:
        # What a browser is told, from the endpoint it reads the callback graph from.
        graph = appmod.server.test_client().get("/_dash-dependencies").get_json()
        entries = [c for c in graph if c["output"] == "elections-url.search"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["inputs"] == [
            {"id": YEARS_ID, "property": "value"},
            {"id": PV_ID, "property": "value"},
        ]
        assert entry["state"] == [
            {"id": YEARS_ID, "property": "min"},
            {"id": YEARS_ID, "property": "max"},
            {"id": MOD["URL_ID"], "property": "search"},
        ]
        assert entry["prevent_initial_call"] is True
        location = find(render(), MOD["URL_ID"])
        assert type(location).__name__ == "Location"
        # callback-nav: the router navigates to the new search without a reload.
        assert location.refresh == "callback-nav"

    def test_a_filter_change_posted_by_a_browser_writes_the_url_and_reads_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        body = {
            "output": "elections-url.search",
            "outputs": {"id": MOD["URL_ID"], "property": "search"},
            "inputs": [
                {"id": YEARS_ID, "property": "value", "value": [1900, LAST]},
                {"id": PV_ID, "property": "value", "value": ["1"]},
            ],
            "state": [
                {"id": YEARS_ID, "property": "min", "value": FIRST},
                {"id": YEARS_ID, "property": "max", "value": LAST},
                # The URL already names the year the slider shows; the change is the
                # pv control's, so only its key is replaced (#436).
                {"id": MOD["URL_ID"], "property": "search", "value": "?year_from=1900"},
            ],
            "changedPropIds": [f"{PV_ID}.value"],
        }
        client = appmod.server.test_client()
        response = client.post("/_dash-update-component", json=body)
        assert response.status_code == 200
        written = response.get_json()["response"][MOD["URL_ID"]]["search"]
        assert written == "?pv=1&year_from=1900"
        assert calls == [] and bucket.waits == []  # the callback reads nothing
        assert routed_years(route("/elections", written)) == [
            y for y in PV_YEARS if y >= 1900
        ]
        # The render fills N1 once, on a miss, for the averages (#437); never the
        # index, and never N2 (#562).
        assert calls == FILLS and len(bucket.waits) == 1

    def test_the_callback_leaves_an_unchanged_url_alone(self) -> None:
        def callback(years: Any, pv: Any, last: Any, current: Any) -> Any:
            # The pv control changed, so its key and nothing else is replaced; then
            # the years, so theirs.
            by_pv = MOD["next_search"](PV_ID, years, pv, FIRST, last, current)
            current = (current or "") if by_pv is no_update else by_pv
            by_years = MOD["next_search"](
                YEARS_ID, years, pv, FIRST, last, current
            )
            return by_years if by_years is not no_update else by_pv

        assert callback([1900, LAST], ["1"], LAST, "") == "?pv=1&year_from=1900"
        assert callback([1900, LAST], ["1"], LAST, "?pv=1&year_from=1900") is (
            no_update
        )
        assert callback([FIRST, LAST], [], LAST, None) is no_update
        assert callback([FIRST, LAST], [], LAST, "?pv=1") == ""

    @pytest.mark.parametrize(
        ("years", "pv", "search"),
        [
            ([1900.0, 1950.0], [], "?year_from=1900&year_to=1950"),
            ([1950, 1900], [], ""),  # an inverted pair never reaches the URL
            (None, None, ""),
            ([True, False], ["1"], "?pv=1"),
            (["1900", 1950], [], "?year_to=1950"),
        ],
    )
    def test_the_merge_from_the_controls_is_total_and_normal(
        self, years: Any, pv: Any, search: str
    ) -> None:
        assert from_controls(years, pv, FIRST, LAST) == search


# --- request budget and the snapshot cutover -----------------------------------------


class TestRequestBudget:
    def test_filter_changes_make_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        for search in ("", "?pv=1", "?year_from=1900", "?year_from=1900&year_to=1950"):
            response = route("/elections", search)
            # Each render is the filtered one, answered from the cache.
            assert routed_years(response) == shown_years(render(parse(search[1:])))
            # Only the first render fills N1, on a miss, for the averages (#437);
            # every filter change after it is answered from the cache.
            assert calls == FILLS, search
            assert len(bucket.waits) == 1, search
        # An old state key reads nothing more: no page reads N2 since #562 (D107).
        for search in ("?state=GA", "?state=GA&year_from=1900", "?state=AK&pv=1"):
            route("/elections", search)
        assert calls == FILLS
        assert len(bucket.waits) == 1

    @pytest.mark.parametrize(
        ("changed", "years", "pv", "current", "written"),
        [
            (YEARS_ID, [1900, LAST], [], "", "?year_from=1900"),
            # A key the parser drops (the moved state, #562) leaves with the change.
            (PV_ID, [FIRST, LAST], ["1"], "?state=GA", "?pv=1"),
        ],
    )
    def test_the_callback_reads_no_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
        changed: str,
        years: Any,
        pv: Any,
        current: str,
        written: str,
    ) -> None:
        """The callback as Dash dispatches it, under a client that fails any read: each
        control's change writes the URL and reads nothing (#436's review)."""

        class NoView:
            def ensure_refresher(self) -> None:  # app.py's hook on every request
                pass

            def view(self) -> Any:
                raise AssertionError("the filter callback read the API")

        monkeypatch.setattr(api, "CLIENT", NoView())
        body = {
            "output": "elections-url.search",
            "outputs": {"id": MOD["URL_ID"], "property": "search"},
            "inputs": [
                {"id": YEARS_ID, "property": "value", "value": years},
                {"id": PV_ID, "property": "value", "value": pv},
            ],
            "state": [
                {"id": YEARS_ID, "property": "min", "value": FIRST},
                {"id": YEARS_ID, "property": "max", "value": LAST},
                {"id": MOD["URL_ID"], "property": "search", "value": current},
            ],
            "changedPropIds": [f"{changed}.value"],
        }
        response = appmod.server.test_client().post("/_dash-update-component", json=body)
        assert response.status_code == 200
        assert response.get_json()["response"][MOD["URL_ID"]]["search"] == written

    def test_a_snapshot_cutover_reaches_the_view_through_the_refresher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = {"version": "version-A"}
        later = [row for row in BODY["data"] if row["year"] >= 2000]

        calls: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls.append(path)
            if path == api.META_PATH:
                body = copy.deepcopy(META)
                provenance = body["provenance"]
            elif path == api.SUMMARY_PATH:
                body = copy.deepcopy(RECORDED[api.SUMMARY_PATH])
                provenance = body["meta"]["provenance"]
                if state["version"] == "version-B":
                    for key in ("data", "elections"):
                        body[key] = [r for r in body[key] if r["year"] >= 2000]
            else:
                body = copy.deepcopy(BODY)
                provenance = body["meta"]["provenance"]
                if state["version"] == "version-B":
                    body["data"] = later
            provenance["snapshot_version"] = state["version"]
            return api.Response(body=body, version=state["version"])

        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        client.refresh()
        calls.clear()
        before = PAGE["layout"]()
        assert shown_years(before) == YEARS
        assert "version-A" in texts(before)
        # N1 is filled on a miss in each snapshot (#437); D072's prefetch is not.
        assert calls == FILLS
        calls.clear()
        state["version"] = "version-B"
        # Until the refresher runs, renders keep serving A from the cache.
        assert shown_years(PAGE["layout"]()) == YEARS
        assert calls == []
        client.refresh()  # the refresher's cycle: /v1/meta names B, so prefetch + swap
        assert calls == [api.META_PATH, api.ELECTIONS_PATH]
        calls.clear()
        after = PAGE["layout"]()
        assert shown_years(after) == [row["year"] for row in later]
        assert "version-B" in texts(after)
        assert "version-A" not in texts(after)
        # The index came with the swap, not a fill on a miss; N1 is B's own miss.
        assert calls == FILLS


# --- labels -----------------------------------------------------------------------


def public_api_fields() -> tuple[set[str], set[str]]:
    """Every field name the public API's response models declare, and every snapshot
    column they accept as an input alias. Test-only: the runtime imports no ``usvote``.
    """
    from pydantic import BaseModel

    from usvote.api import models

    names: set[str] = set()
    aliases: set[str] = set()
    for value in vars(models).values():
        if (
            isinstance(value, type)
            and issubclass(value, BaseModel)
            and value.__module__ == models.__name__
        ):
            for name, field in value.model_fields.items():
                names.add(name)
                if isinstance(field.validation_alias, str):
                    aliases.add(field.validation_alias)
    return names, aliases


def label_key_problems(keys: Any) -> list[str]:
    names, aliases = public_api_fields()
    problems = [f"{k}: not a public field" for k in keys if k not in names]
    problems += [f"{k}: a snapshot column alias" for k in keys if k in aliases]
    return problems


class TestLabels:
    def test_t1_shows_exactly_its_three_fields(self) -> None:
        assert MOD["FIELDS"] == ("year", "candidate_count", "has_popular_vote")
        for record in BODY["data"]:
            assert set(MOD["FIELDS"]) <= set(record)

    def test_each_header_is_its_label_with_the_raw_field_name_on_demand(self) -> None:
        tree = render()
        headers = of_type(find(tree, TABLE_ID), "Th")
        assert [h.children for h in headers] == [
            labels.LABELS[f] for f in MOD["FIELDS"]
        ]
        assert [h.title for h in headers] == list(MOD["FIELDS"])
        assert [h.scope for h in headers] == ["col"] * len(MOD["FIELDS"])
        glossary = of_type(tree, "Details")
        assert len(glossary) == 1
        pairs = list(zip(of_type(glossary, "Dt"), of_type(glossary, "Dd"), strict=True))
        assert [(dt.children, texts(dd.children)) for dt, dd in pairs] == [
            (labels.LABELS[f], [f]) for f in MOD["FIELDS"]
        ]

    def test_the_approved_labels(self) -> None:
        assert labels.LABELS["year"] == "Election year"
        assert labels.LABELS["candidate_count"] == "Candidates with electoral votes"
        assert labels.LABELS["has_popular_vote"] == "Popular vote in this dataset"

    def test_every_label_keys_a_public_api_field_never_a_snapshot_column(self) -> None:
        assert label_key_problems(labels.LABELS) == []

    def test_the_label_key_check_fails_what_it_should(self) -> None:
        # Non-vacuity: a snapshot column the models accept only as an input alias, and
        # a name no model declares.
        assert label_key_problems(["total_electoral_votes", "nonsense"]) == [
            "total_electoral_votes: not a public field",
            "nonsense: not a public field",
            "total_electoral_votes: a snapshot column alias",
        ]


# --- the shared pieces: footer, degraded state, purity -------------------------------

SHARED_MODULES = (
    "charts.py",
    "components.py",
    "election_view.py",  # the election pages' shared pieces (#465)
    "elections_view.py",  # the elections pages' shared pieces (#562)
    "export.py",
    "labels.py",
    "metrics.py",  # the dashboard's own summaries (#437, D097)
    "over_time.py",  # the election-year time series' pieces, C4's and C7's (#560)
    "query.py",
    "state_view.py",  # the state pages' shared pieces (#559)
)

#: The shared modules by import name: the only ``explore`` modules a shared module may
#: import (#309: the shared table component builds on ``labels`` and ``export``; #432:
#: the chart builder on ``charts``).
SHARED_NAMES = frozenset(name.removesuffix(".py") for name in SHARED_MODULES)


def with_span(first: Any, last: Any) -> dict[str, Any]:
    """The recorded body with its coverage span replaced."""
    body = copy.deepcopy(BODY)
    body["meta"]["provenance"]["coverage"].update(year_min=first, year_max=last)
    return body


PACKAGE = Path(api.__file__).parent


def shared_imports(source: str) -> set[str]:
    """The shared modules (:data:`SHARED_NAMES`) a module imports by name."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "explore":
                found |= {a.name for a in node.names} & SHARED_NAMES
            elif (node.module or "").startswith("explore."):
                found |= {(node.module or "").split(".", 1)[1]} & SHARED_NAMES
        if isinstance(node, ast.Import):
            found |= {
                a.name.split(".", 1)[1]
                for a in node.names
                if a.name.startswith("explore.")
            } & SHARED_NAMES
    return found


def in_cycles(graph: dict[str, set[str]]) -> list[str]:
    """The nodes of ``graph`` (module -> what it imports) that reach themselves."""

    def reaches(start: str, goal: str, seen: frozenset[str]) -> bool:
        return any(
            n == goal or (n not in seen and reaches(n, goal, seen | {n}))
            for n in graph.get(start, set())
        )

    return sorted(name for name in graph if reaches(name, name, frozenset()))


def imports_api(source: str) -> bool:
    """Whether a module could reach ``explore.api``.

    Flagged: any ``from explore …`` import but one naming only shared modules
    (:data:`SHARED_NAMES`, which import nothing else from it: ``explore.app`` and the
    pages import ``api``, so any of them is a way in); every ``import explore`` or
    ``import explore.<module>``, shared or not, since either binds the package name
    ``explore``, through which any module is reachable (``explore.pages…``); any
    relative import; any name or attribute ``api`` or ``CLIENT``; and ``__import__`` /
    ``importlib``.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0 or module == "importlib":
                return True
            if module == "explore" and any(
                alias.name not in SHARED_NAMES for alias in node.names
            ):
                return True
            if module.startswith("explore.") and (
                module.split(".", 1)[1] not in SHARED_NAMES
            ):
                return True
        if isinstance(node, ast.Import) and any(
            alias.name in ("explore", "importlib")
            or alias.name.startswith(("explore.", "importlib."))
            for alias in node.names
        ):
            return True
        if isinstance(node, ast.Name) and node.id in ("api", "CLIENT", "__import__"):
            return True
        if isinstance(node, ast.Attribute) and node.attr in ("api", "CLIENT"):
            return True
    return False


class TestSharedPieces:
    @pytest.mark.parametrize("name", SHARED_MODULES)
    def test_the_shared_modules_read_no_api(self, name: str) -> None:
        assert not imports_api((PACKAGE / name).read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        ("source", "imports"),
        [
            ("from explore import api\n", True),
            ("from explore.api import CLIENT\n", True),
            ("import explore.api\n", True),
            ("from . import api\n", True),
            ("import explore\nexplore.api.CLIENT.view()\n", True),
            ("from explore import app\napp.api.CLIENT.view()\n", True),
            ("from explore.pages import elections\n", True),
            ("from .config import X\n", True),
            ("x = __import__('explore.api')\n", True),
            ("import importlib\n", True),
            ("CLIENT.view()\n", True),
            ("from dash import html\n", False),
            ("from typing import Any\n", False),
            # #309: a shared module may import another shared module, and only that.
            ("from explore import export, labels\n", False),
            ("from explore.labels import header\n", False),
            ("import explore.query\n", True),
            ("import explore.query\nexplore.pages.election.layout()\n", True),
            ("from explore import labels, api\n", True),
            ("from explore import config\n", True),
            ("from explore.api import fetch\n", True),
            ("import explore.app\n", True),
            ("import explore\n", True),
            ("from . import labels\n", True),
            ("from explore.labels.x import y\n", True),
        ],
    )
    def test_the_purity_check_fails_what_it_should(
        self, source: str, imports: bool
    ) -> None:
        assert imports_api(source) is imports

    def test_the_shared_modules_import_each_other_without_a_cycle(self) -> None:
        """A cycle would make the import order decide what a module sees."""
        graph = {
            name.removesuffix(".py"): shared_imports(
                (PACKAGE / name).read_text(encoding="utf-8")
            )
            for name in SHARED_MODULES
        }
        assert graph["components"] == {"charts", "export", "labels", "query"}
        assert graph["charts"] == set()  # the chart rules import nothing from explore
        # The election pages' shared pieces build on labels and query only (#465).
        assert graph["election_view"] == {"labels", "query"}
        # And the elections pages' (#562), which check a year as the election pages do.
        assert graph["elections_view"] == {"election_view", "labels", "query"}
        # And the state pages' (#559), which therefore own the roster reading.
        assert graph["state_view"] == {"labels", "query"}
        # The summaries share the cells' rule of what is a figure (#437, D097(f)).
        assert graph["metrics"] == {"labels"}
        assert in_cycles(graph) == []

    def test_every_module_is_a_shared_one_or_named_as_not(self) -> None:
        """A new module under ``explore/`` must be listed in :data:`SHARED_MODULES` or
        here, so none escapes the two checks above by being left out (#562, I-3)."""
        not_shared = {"__init__.py", "api.py", "app.py", "config.py"}
        found = {p.name for p in PACKAGE.glob("*.py")}
        assert found == set(SHARED_MODULES) | not_shared

    def test_the_cycle_check_sees_a_cycle(self) -> None:
        assert shared_imports("from explore import components\n") == {"components"}
        assert shared_imports("import explore.labels\nfrom explore import api\n") == {
            "labels"
        }
        assert in_cycles({"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}}) == [
            "a",
            "b",
            "c",
        ]
        assert in_cycles({"a": {"b"}, "b": set()}) == []

    @pytest.mark.parametrize(
        "module",
        # The custom-404 page reads no data, so it has no provenance to show (#325).
        sorted(m for m, p in dash.page_registry.items() if not appmod.is_not_found_page(p)),
    )
    def test_every_page_renders_the_shared_footer(
        self, monkeypatch: pytest.MonkeyPatch, module: str
    ) -> None:
        """Through the component itself, with the provenance the page read."""
        cached_client(monkeypatch)
        given: list[Any] = []
        real = components.provenance_footer

        def spy(provenance: dict[str, Any]) -> Any:
            given.append(provenance)
            return dash.html.Footer(real(provenance), id="footer-spy")

        monkeypatch.setattr(components, "provenance_footer", spy)
        page = dash.page_registry[module]
        response = route(concrete_page_path(page))
        ids = routed_ids(response)
        assert {"footer-spy", page["success"]} <= ids
        assert len(given) == 1
        assert given[0]["snapshot_version"] == VERSION
        assert given[0]["coverage"] == COVERAGE

    def test_the_footer_is_built_from_the_response_s_provenance(self) -> None:
        body = copy.deepcopy(BODY)
        body["meta"]["provenance"]["snapshot_version"] = "SENTINEL-version"
        body["meta"]["provenance"]["census_license"] = "SENTINEL-license"
        text = texts(render(body=body))
        assert "SENTINEL-version" in text
        assert "SENTINEL-license" in text

    def test_no_page_s_success_marker_is_the_shared_footer_s(self) -> None:
        """A page's marker is its own content: the footer renders on every success,
        so its ids would prove only that the footer did."""
        footer_ids = component_ids(components.provenance_footer(META["provenance"]))
        assert {components.PROVENANCE_ID, components.SNAPSHOT_ID} <= footer_ids
        for module, page in dash.page_registry.items():
            if appmod.is_not_found_page(page):
                assert "success" not in page, module  # reads no data (#325)
                continue
            assert page["success"] not in footer_ids, module
        assert (
            dash.page_registry["pages.home"]["success"] == home_module()["COVERAGE_ID"]
        )

    def test_home_links_to_the_elections_and_states_pages(self) -> None:
        tree = home_module()["render"](copy.deepcopy(META))
        links = [link.href for link in of_type(tree, "Link")]
        assert links == [PAGE["path"], "/states"]
        assert set(links) <= {p["path"] for p in dash.page_registry.values()}

    def test_home_keeps_no_second_copy_of_the_footer(self) -> None:
        source = (PACKAGE / "pages" / "home.py").read_text(encoding="utf-8")
        assert "SOURCES" not in home_module()
        for key in ("ec_license_url", "census_source_name", "snapshot_version"):
            assert key not in source, key  # provenance keys are the component's alone

    def test_an_unreadable_api_shows_the_plain_message_and_no_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            raise api.ApiUnavailable("GET /v1/elections: HTTP 503 SECRET-DETAIL")

        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        tree = PAGE["layout"]()
        assert components.UNAVAILABLE_MESSAGE in texts(tree)
        assert "SECRET-DETAIL" not in " ".join(texts(tree))
        assert PAGE_ID not in component_ids(tree)

    @pytest.mark.parametrize(
        "broken",
        [
            {"data": []},  # no meta
            {"meta": {"provenance": {"coverage": {}}}, "data": []},
            {
                "meta": {
                    "provenance": {"coverage": {"year_min": "1824", "year_max": 2024}}
                },
                "data": [],
            },
            {**BODY, "data": {}},
            {**BODY, "data": ""},
            {**BODY, "data": []},  # a served snapshot always has elections
            with_span(2024, 1824),  # inverted
            with_span(0, 400_000_000),  # unbounded slider labels
            with_span(824, 2024),  # below 1000
        ],
    )
    def test_a_malformed_body_shows_the_plain_message(
        self, monkeypatch: pytest.MonkeyPatch, broken: dict[str, Any]
    ) -> None:
        fetch, _ = fake_fetch({api.META_PATH: META, api.ELECTIONS_PATH: broken})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        tree = PAGE["layout"]()
        assert components.UNAVAILABLE_MESSAGE in texts(tree)
        assert PAGE_ID not in component_ids(tree)


def as_json(component: Component) -> str:
    """A component tree as JSON, children and props included, keys sorted: two trees
    with the same text render the same markup."""
    def plain(node: Any) -> Any:
        if isinstance(node, Component):
            return plain(node.to_plotly_json())
        if isinstance(node, dict):
            return {key: plain(value) for key, value in node.items()}
        if isinstance(node, (list, tuple)):
            return [plain(item) for item in node]
        return node

    return json.dumps(plain(component), sort_keys=True)


def _where(stmt: ast.stmt) -> str:
    """How the source scans name the top-level statement a hit sits in: its
    definition's or assignment's name, else its line."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return stmt.name
    if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
        return stmt.targets[0].id
    return f"line {stmt.lineno}"


def dropdown_uses(source: str) -> list[str]:
    """Where ``source`` builds a dropdown itself (#475), each reported as the top-level
    definition or assignment it sits in (an import by line): any name, attribute or
    import of ``Dropdown`` (``dcc.Dropdown``, ``dash.dcc.Dropdown``, an imported or
    aliased ``Dropdown``), and any string containing ``Dropdown`` (``getattr(dcc,
    "Dropdown")``, a dropdown returned as component JSON, or one a clientside
    callback's JS builds). Bare string statements (docstrings) are not code and are
    skipped. It reads source, so a page changing the helper's result
    after the call, ``exec`` or ``eval``, and a type name built at runtime are not
    seen."""
    tree = ast.parse(source)
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    found: list[str] = []
    for stmt in tree.body:
        where = _where(stmt)
        for node in ast.walk(stmt):
            hit = (
                (
                    isinstance(node, (ast.Import, ast.ImportFrom))
                    and any(
                        "Dropdown" in name
                        for a in node.names
                        for name in (a.name, a.asname or "")
                    )
                )
                or (isinstance(node, ast.Name) and node.id == "Dropdown")
                or (isinstance(node, ast.Attribute) and node.attr == "Dropdown")
                or (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "Dropdown" in node.value
                    and id(node) not in docstrings
                )
            )
            if hit and where not in found:
                found.append(where)
    return found


class TestDropdownFilter:
    """``components.dropdown_filter`` (#475): every dashboard dropdown filter is built
    through it, so a fix to its markup is made once.
    ``test_only_the_helper_builds_a_dropdown`` checks that no other runtime module
    names ``Dropdown``."""

    OPTIONS = [{"label": "Alabama", "value": "AL"}, {"label": "Alaska", "value": "AK"}]

    @pytest.mark.parametrize("value", ["AK", None])
    def test_it_builds_the_markup_the_pages_built_by_hand(
        self, value: str | None
    ) -> None:
        """The tree each page built before #475, verbatim: same ids, classes, props
        and children."""
        by_hand = dash.html.Div(
            [
                dash.html.Label("State", htmlFor="some-id", className="label"),
                dash.dcc.Dropdown(
                    id="some-id",
                    options=self.OPTIONS,
                    value=value,
                    placeholder="All states",
                    clearable=True,
                ),
            ],
            className="filter",
        )
        built = components.dropdown_filter(
            "some-id", "State", self.OPTIONS, value, "All states"
        )
        assert as_json(built) == as_json(by_hand)

    def test_each_argument_lands_on_its_prop(self) -> None:
        built = components.dropdown_filter(
            "the-id", "The label", self.OPTIONS, "AL", "The placeholder"
        )
        assert built.to_plotly_json()["props"]["className"] == "filter"
        label, dropdown = built.children
        assert isinstance(label, dash.html.Label)
        assert isinstance(dropdown, dash.dcc.Dropdown)
        label_props = label.to_plotly_json()["props"]
        props = dropdown.to_plotly_json()["props"]
        assert label_props == {
            "children": "The label",
            "htmlFor": "the-id",
            "className": "label",
        }
        # Exactly these props: none added (``persistence`` would override the URL,
        # which holds the value), none dropped.
        assert props == {
            "id": "the-id",
            "options": self.OPTIONS,
            "value": "AL",
            "placeholder": "The placeholder",
            "clearable": True,
        }

    def test_only_the_helper_builds_a_dropdown(self) -> None:
        """No runtime module but ``components.dropdown_filter`` names ``Dropdown``, so
        every dropdown a page shows comes from the helper (residuals:
        :func:`dropdown_uses`)."""
        assert RUNTIME_MODULES, "no runtime modules found"
        found = {
            str(path.relative_to(PACKAGE)): refs
            for path in RUNTIME_MODULES
            if (refs := dropdown_uses(path.read_text(encoding="utf-8")))
        }
        assert found == {"components.py": ["dropdown_filter"]}

    @pytest.mark.parametrize(
        ("source", "found"),
        [
            ("from dash import dcc\ndef f():\n    dcc.Dropdown(id='d')\n", ["f"]),
            ("import dash\nD = dash.dcc.Dropdown(id='d')\n", ["D"]),
            ("from dash.dcc import Dropdown\n", ["line 1"]),
            ("from dash.dcc import Dropdown as D\n", ["line 1"]),
            # Only the name rule sees a star-imported Dropdown.
            ("from dash.dcc import *\ndef f():\n    Dropdown(id='d')\n", ["f"]),
            ("from dash import dcc as c\ndef f():\n    c.Dropdown()\n", ["f"]),
            ("from dash import dcc\ndef f():\n    getattr(dcc, 'Dropdown')()\n", ["f"]),
            ("X = {'type': 'Dropdown', 'namespace': 'dash_core_components'}\n", ["X"]),
            ("CB = \"return {type: 'Dropdown', namespace: NS};\"\n", ["CB"]),
            ("from explore import components\ncomponents.dropdown_filter()\n", []),
            # Docstrings naming Dropdown: caught but for the docstring skip.
            ('"""Dropdown"""\n', []),
            ('"""Builds no dcc.Dropdown."""\n', []),
            ('def f():\n    """Dropdown"""\n', []),
            ("from dash import dcc\ndcc.RadioItems(id='r')\n", []),
        ],
    )
    def test_the_dropdown_scan_catches_the_listed_ways(
        self, source: str, found: list[str]
    ) -> None:
        assert dropdown_uses(source) == found


def _is_option(node: ast.AST) -> bool:
    """A dict display whose keys are exactly ``"label"`` and ``"value"``."""
    return isinstance(node, ast.Dict) and {
        k.value for k in node.keys if isinstance(k, ast.Constant)
    } == {"label", "value"}


def _is_sorted(node: ast.AST) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sorted"
    )


_COMPREHENSIONS = (ast.ListComp, ast.GeneratorExp, ast.SetComp)


def option_sorts(source: str) -> list[str]:
    """Where ``source`` sorts dropdown options itself (#540), each reported as the
    top-level definition or assignment it sits in: a comprehension building
    ``{"label", "value"}`` dicts that iterates a ``sorted(...)`` call, or a
    ``sorted(...)`` call over such a comprehension: the shapes #540 removed. A
    comprehension over a closed vocabulary's table, which is not sorted, is not
    reported. It is a tripwire for those shapes, not a proof that no page sorts
    options: among the shapes it does not see are a ``.sort()`` call, a ``sorted(...)`` result bound to a
    name before the comprehension reads it, a loop that appends, options built with
    ``dict(label=..., value=...)``, a re-sort of the builder's result, or a sort reached
    through another name. ``TestNameOptionsComeFromTheBuilder``
    (``test_dashboard_export.py``) is what checks each page takes the builder's list."""
    found: list[str] = []
    for stmt in ast.parse(source).body:
        for node in ast.walk(stmt):
            hit = (
                isinstance(node, _COMPREHENSIONS)
                and _is_option(node.elt)
                and any(_is_sorted(g.iter) for g in node.generators)
            ) or (
                _is_sorted(node)
                and any(
                    isinstance(a, _COMPREHENSIONS) and _is_option(a.elt)
                    for a in node.args
                )
            )
            if hit:
                found.append(_where(stmt))
                break
    return found


def _is_dropdown_filter_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr == "dropdown_filter") or (
        isinstance(func, ast.Name) and func.id == "dropdown_filter"
    )


def looped_dropdown_filters(source: str) -> list[str]:
    """Where ``source`` calls ``dropdown_filter`` from a loop (#540): inside a
    comprehension, a generator expression or a ``for`` or ``while`` body, the two
    tuple-table shapes #540 removed. Each is reported as its top-level definition or
    assignment. It is a tripwire for those shapes, not a check that each filter has
    its own call: among the shapes it does not see are ``dropdown_filter`` passed to
    ``map`` or ``itertools.starmap``, called from a ``lambda`` outside a loop (one
    passed to ``map``, say), through an alias or a wrapper function, or with rows taken
    from a table by index (``dropdown_filter(*T[0])``)."""
    found: list[str] = []
    for stmt in ast.parse(source).body:
        loops = [
            n
            for n in ast.walk(stmt)
            if isinstance(n, (*_COMPREHENSIONS, ast.DictComp, ast.For, ast.While))
        ]
        if any(
            _is_dropdown_filter_call(inner) for loop in loops for inner in ast.walk(loop)
        ):
            found.append(_where(stmt))
    return found


class TestLabelSortedOptions:
    """``components.label_sorted_options`` (#540): every dropdown filter whose choices
    are names takes its options from it, so their shape and order are set once."""

    def test_it_sorts_by_label_not_by_value(self) -> None:
        # Value order (AK, AL, AZ) and label order (Alabama, Alaska, Arizona) differ.
        built = components.label_sorted_options(
            {"AZ": "Arizona", "AK": "Alaska", "AL": "Alabama"}
        )
        assert built == [
            {"label": "Alabama", "value": "AL"},
            {"label": "Alaska", "value": "AK"},
            {"label": "Arizona", "value": "AZ"},
        ]

    def test_equal_labels_keep_the_maps_order(self) -> None:
        """Two candidates of one name keep the order the page read them in: the sort
        is on the label alone, never the label then the value."""
        built = components.label_sorted_options(
            {"z-smith": "Smith", "a-jones": "Jones", "b-smith": "Smith"}
        )
        assert [o["value"] for o in built] == ["a-jones", "z-smith", "b-smith"]

    def test_each_option_is_exactly_a_label_and_a_value(self) -> None:
        built = components.label_sorted_options({"GA": "Georgia"})
        assert built == [{"label": "Georgia", "value": "GA"}]
        assert list(built[0]) == ["label", "value"]

    def test_no_entries_give_no_options(self) -> None:
        assert components.label_sorted_options({}) == []

    def test_labels_are_used_as_passed(self) -> None:
        """No conversion: a page that needs ``str()`` applies it to its map."""

        class Name(str):
            pass

        label = Name("Georgia")
        (option,) = components.label_sorted_options({"GA": label})
        assert option["label"] is label

    def test_only_the_builder_sorts_options(self) -> None:
        assert RUNTIME_MODULES, "no runtime modules found"
        found = {
            str(path.relative_to(PACKAGE)): refs
            for path in RUNTIME_MODULES
            if (refs := option_sorts(path.read_text(encoding="utf-8")))
        }
        assert found == {"components.py": ["label_sorted_options"]}

    @pytest.mark.parametrize(
        ("source", "found"),
        [
            # The five shapes #540 removed.
            (
                "def _options(pairs):\n    return [\n"
                "        {'label': label, 'value': value}\n"
                "        for value, label in sorted(pairs.items(), key=k)\n    ]\n",
                ["_options"],
            ),
            (
                "def f(states):\n    x = [{'label': n, 'value': u}\n"
                "        for u, n in sorted(states.items(), key=k)]\n",
                ["f"],
            ),
            (
                "def f(s):\n    return [{'label': str(r[0]), 'value': u}\n"
                "        for u, r in sorted((s or {}).items(), key=k)]\n",
                ["f"],
            ),
            ("X = ({'label': a, 'value': b} for a, b in sorted(p))\n", ["X"]),
            ("X = sorted([{'label': a, 'value': b} for a, b in p], key=k)\n", ["X"]),
            # A closed vocabulary in its table's order is not a sort.
            ("X = [{'label': v, 'value': k} for k, v in T.items()]\n", []),
            ("X = sorted(p)\n", []),
            ("X = [{'label': a} for a in sorted(p)]\n", []),
        ],
    )
    def test_the_sort_scan_catches_the_listed_ways(
        self, source: str, found: list[str]
    ) -> None:
        assert option_sorts(source) == found

    def test_no_page_calls_dropdown_filter_from_a_loop(self) -> None:
        """No runtime module calls ``components.dropdown_filter`` from a loop, the
        shape #540's tuple tables took; :func:`looped_dropdown_filters` names some
        shapes the scan does not see."""
        found = {
            str(path.relative_to(PACKAGE)): refs
            for path in RUNTIME_MODULES
            if (refs := looped_dropdown_filters(path.read_text(encoding="utf-8")))
        }
        assert found == {}

    @pytest.mark.parametrize(
        ("source", "found"),
        [
            # The two tuple-table shapes #540 removed.
            (
                "def f(t):\n    return [components.dropdown_filter(a, b, c, d, e)\n"
                "        for a, b, c, d, e in t]\n",
                ["f"],
            ),
            (
                "def f(t):\n    return [*(components.dropdown_filter(*r)"
                " for r in t)]\n",
                ["f"],
            ),
            ("def f(t):\n    for r in t:\n        dropdown_filter(*r)\n", ["f"]),
            ("def f(t):\n    while t:\n        dropdown_filter(t.pop())\n", ["f"]),
            ("def f():\n    return [components.dropdown_filter(1, 2, 3, 4, 5)]\n", []),
            (
                "def f(t):\n    x = [o for o in t]\n"
                "    return components.dropdown_filter(1, 2, x, 4, 5)\n",
                [],
            ),
        ],
    )
    def test_the_loop_scan_catches_the_listed_ways(
        self, source: str, found: list[str]
    ) -> None:
        assert looped_dropdown_filters(source) == found


class TestHasText:
    """``labels.has_text``, the shared predicate for whether a name, a note or a reason
    has text to show (#367)."""

    @pytest.mark.parametrize("value", ["Andrew Jackson", " x ", "5"])
    def test_text_with_something_in_it(self, value: str) -> None:
        assert labels.has_text(value) is True

    # 5 and True are the trap: a bare ``not labels.is_blank(value)`` is true of both,
    # and would link a name that is not text (PR #390, cr.6).
    @pytest.mark.parametrize("value", [None, "", "  ", "\t\n", 5, True, 0.0, ["x"]])
    def test_anything_else(self, value: object) -> None:
        assert labels.has_text(value) is False

    # A format or control character carries nothing to read (#532): alone, mixed with
    # whitespace, or several together, it is no text.
    @pytest.mark.parametrize(
        "value",
        [
            "\u200b",  # zero-width space (Cf)
            "\ufeff",  # byte-order mark (Cf)
            "\u200b\ufeff",
            " \u200b\t",  # whitespace and Cf together
            "\u2060",  # word joiner (Cf)
            "\u00ad",  # soft hyphen (Cf)
            "\u180e",  # Mongolian vowel separator (Cf, whitespace before Unicode 6.3)
            "\u061c",  # Arabic letter mark (Cf)
            "\U000e0001",  # language tag, outside the BMP (Cf)
            "\x01",  # a control that is not whitespace (Cc)
            "\x7f\x1b",  # delete and escape (Cc)
            "\x00",  # NUL (Cc)
            # Whitespace between them, not only around them: a rule that strips the
            # ends and then checks what is left calls these text (#532's review, F8).
            "\u200b \u200b",
            "\x01\t\x01",
        ],
        ids=repr,
    )
    def test_format_or_control_characters_only(self, value: str) -> None:
        assert labels.has_text(value) is False

    # Those characters never erase real text beside them.
    @pytest.mark.parametrize(
        "value",
        ["\ufeffAndrew Jackson", "Andrew\u200bJackson", "Andrew Jackson\x01", "\u200bx"],
        ids=repr,
    )
    def test_real_text_carrying_them_is_text(self, value: str) -> None:
        assert labels.has_text(value) is True


@functools.cache
def _code_points_by_category() -> dict[str, list[str]]:
    """Every code point of the running interpreter's Unicode version, by general
    category: what the class sweep below reads its expectations from, so it holds on any
    supported Python (the ``requires-python`` floor, 3.11, is Unicode 14.0; CI and App
    Engine run 3.14, Unicode 16.0)."""
    found: dict[str, list[str]] = {}
    for point in range(sys.maxunicode + 1):
        char = chr(point)
        found.setdefault(unicodedata.category(char), []).append(char)
    return found


class TestHasTextClass:
    """The class ``labels.has_text`` treats as nothing to read, pinned over every code
    point rather than a hand-picked list (#532; architect, I2): whitespace (exactly what
    ``str.strip`` removes, so ordinary whitespace behaves as before), and the general
    categories Cf (format) and Cc (control, the owner's addition at the plan gate). A
    table holding only the sample characters, or a rule keyed on another category,
    fails here."""

    #: The categories, written out here rather than read from ``labels``, so a change to
    #: the module's set is a change to this literal too.
    NOTHING_TO_READ = frozenset({"Cc", "Cf"})

    def nothing_to_read(self) -> list[str]:
        by_category = _code_points_by_category()
        return [c for category in self.NOTHING_TO_READ for c in by_category[category]]

    def test_the_module_names_the_same_categories(self) -> None:
        assert labels.NOTHING_TO_READ_CATEGORIES == self.NOTHING_TO_READ

    def test_every_format_or_control_character_alone_is_no_text(self) -> None:
        chars = self.nothing_to_read()
        assert len(chars) > 200  # 170 Cf + 65 Cc on Unicode 16.0
        assert [c for c in chars if labels.has_text(c)] == []

    def test_every_one_of_them_leaves_real_text_text(self) -> None:
        chars = self.nothing_to_read()
        assert [c for c in chars if not labels.has_text(f"a{c}")] == []
        assert [c for c in chars if not labels.has_text(f"{c}a")] == []

    def test_every_whitespace_character_alone_is_no_text(self) -> None:
        by_category = _code_points_by_category()
        spaces = [c for chars in by_category.values() for c in chars if c.isspace()]
        assert "\u00a0" in spaces and "\u3000" in spaces  # not only ASCII whitespace
        assert [c for c in spaces if labels.has_text(c)] == []
        # What ``str.strip`` removes, so ordinary whitespace behaves as before (AC3).
        assert all(not c.strip() for c in spaces)

    def test_every_other_category_counts_as_text(self) -> None:
        """One character of every other category counts as text, unassigned, private
        use and surrogate code points included, so no other category is wholly nothing
        to read (one character per category, not every one: the documented residuals,
        such as U+3164, are not pinned here), and the class is never every ``C*``
        category. The first character of each that is not whitespace."""
        by_category = _code_points_by_category()
        others = {
            category: next(c for c in chars if not c.isspace())
            for category, chars in by_category.items()
            if category not in self.NOTHING_TO_READ
            and any(not c.isspace() for c in chars)
        }
        assert {"Cn", "Co", "Cs", "Lo", "Mn", "So"} <= set(others)
        assert {cat: c for cat, c in others.items() if not labels.has_text(c)} == {}

    # The residuals ``labels.has_text``'s docstring names: characters that render as
    # nothing but sit outside Cc and Cf, so they still count as text (#532's acceptance
    # gate, Class B: no test held them). Change this together with the docstring, if
    # the class ever widens to take them in.
    @pytest.mark.parametrize(
        "value",
        [
            "\u3164",  # Hangul filler (Lo)
            "\u115f",  # Hangul choseong filler (Lo)
            "\uffa0",  # halfwidth Hangul filler (Lo)
            "\u2800",  # blank braille pattern (So)
            "\u0301",  # a lone combining acute accent (Mn)
        ],
        ids=repr,
    )
    def test_the_documented_residuals_still_count_as_text(self, value: str) -> None:
        assert labels.has_text(value) is True


class TestIsBlankKeepsWhitespaceOnly:
    """The fork #532's plan gate settled (owner, fork A; architect): ``labels.is_blank``
    keeps ``str.strip``, so text made only of format or control characters that are not
    whitespace is neither blank nor text, while text of whitespace controls (U+001F,
    U+0085) stays blank. A cell falling back through ``labels._unknown`` reads the
    first as unrecognized, never as the null wording, which would claim the dataset
    holds nothing here when it holds a value (D101's reasoning: a fallback that hides an
    upstream fault is refused). Widening ``is_blank`` to match ``has_text`` is a
    decision, not a consistency fix."""

    @pytest.mark.parametrize("value", ["\u200b", "\ufeff", "\x01", " \u200b "], ids=repr)
    def test_format_or_control_text_is_not_blank(self, value: str) -> None:
        assert labels.is_blank(value) is False
        assert labels.has_text(value) is False

    @pytest.mark.parametrize("value", ["\u200b", "\x01"], ids=repr)
    def test_a_winner_made_of_them_reads_unrecognized(self, value: str) -> None:
        assert labels.winner(value, True) == labels.UNRECOGNIZED
        assert labels.winner(value, False) == labels.UNRECOGNIZED

    # The boundary (#532's review, D2, owner option A): a control character that is
    # also whitespace makes a value blank, as ``str.strip`` always has, so it names no
    # cause; ``has_text`` still refuses it.
    @pytest.mark.parametrize("value", ["\x1f", "\x85", "\x1c\x1d"], ids=repr)
    def test_whitespace_controls_stay_blank(self, value: str) -> None:
        assert labels.is_blank(value) is True
        assert labels.has_text(value) is False
        assert labels.winner(value, True) == labels.NOT_IN_DATASET

    @pytest.mark.parametrize("value", [None, "", "  "], ids=repr)
    def test_a_null_or_blank_winner_still_names_no_cause(self, value: object) -> None:
        assert labels.winner(value, True) == labels.NOT_IN_DATASET
        assert labels.winner(value, False) == labels.NOT_APPLICABLE


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path"] == "/elections"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    # N1, the averages' source: a literal filled on a miss (#437, D074(ii)); no N2
    # since #562 (D107).
    assert PAGE["on_miss"] == FILLS_TUPLE
    assert PAGE["success"] == PAGE_ID
    assert VERSION  # the recorded snapshot every cached render answers from



# --- N1, which the headline metrics read (#437) ---------------------------------------

SUMMARY: dict[str, Any] = RECORDED[api.SUMMARY_PATH]


def render_n1(
    summary: Any = None, index: Any = None, query: dict[str, Any] | None = None
) -> Any:
    """The page for the index and an N1 body (the recording unless given)."""
    return MOD["render"](
        copy.deepcopy(BODY if index is None else index),
        MOD["parse_filters"](query or {}),
        copy.deepcopy(SUMMARY if summary is None else summary),
    )


def n1_client(monkeypatch: pytest.MonkeyPatch, answer: Any) -> tuple[list[str], Any]:
    """A process client serving the recordings, with N1 answered by ``answer(path)``."""
    calls: list[str] = []

    def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        calls.append(path)
        if path == api.SUMMARY_PATH:
            result: api.Response = answer(path)
            return result
        return api.Response(body=RECORDED[path], version=VERSION)

    bucket = RecordingBucket()
    client = offline_client(
        fetch, bucket=bucket, prefetch_paths=lambda: [api.ELECTIONS_PATH]
    )
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    calls.clear()
    bucket.waits.clear()
    monkeypatch.setattr(api, "CLIENT", client)
    return calls, bucket

#: The Electoral College majority page (#562), for the year-axis checks C2 shares with
#: C4 and C5 below.
MAJORITY: dict[str, Any] = dash.page_registry["pages.elections_majority"][
    "layout"
].__globals__


def render_majority(summary: Any = None, index: Any = None) -> Any:
    """The majority page for the index and an N1 body (the recording unless given)."""
    return MAJORITY["render"](
        copy.deepcopy(BODY if index is None else index),
        copy.deepcopy(SUMMARY if summary is None else summary),
    )


def c2_figure(tree: Any) -> dict[str, Any]:
    """C2's figure, from the source store ``components.chart`` gave it."""
    c2 = charts.dom_id("C2")
    (store,) = [
        node
        for node in of_type(tree, "Store")
        if isinstance(getattr(node, "id", None), dict) and node.id.get("chart") == c2
    ]
    figure: dict[str, Any] = store.data
    return figure



def _without(year: int) -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    summary["elections"] = [e for e in summary["elections"] if e["year"] != year]
    return summary


def _second_item() -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    item = copy.deepcopy(summary["elections"][0])
    item["ec_determinative"] = not item["ec_determinative"]
    summary["elections"].append(item)
    return summary


def _second_leader() -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    extra = copy.deepcopy(next(r for r in summary["data"] if r["year"] == 1860))
    extra["candidate_slug"] = "someone-else"
    summary["data"].append(extra)
    return summary


# --- the headline metrics (#437, D097) ------------------------------------------------

METRICS_BLOCK = MOD["METRICS_ID"]
METRIC_IDS = MOD["METRIC_IDS"]
ITEMS: dict[int, dict[str, Any]] = {e["year"]: e for e in SUMMARY["elections"]}

#: Each case's query and, per average, ``(mean, n, first, last, text)`` or the no-average
#: text. The means were computed once at plan time from the recorded N1's JSON, outside
#: the code under test, with ``sum()/len()`` and again with ``statistics.fmean`` (which
#: sums with ``math.fsum``), the two agreeing to the last digit; the text is the mean to
#: one decimal, as the panel shows a margin.
CASES: dict[str, tuple[dict[str, str], Any, Any]] = {
    "the full span": (
        {},
        (41.15552204050586, 51, 1824, 2024, "41.2 percentage points"),
        (5.687741898936854, 13, 1976, 2024, "5.7 percentage points"),
    ),
    "a range inside the popular-vote window": (
        {"year_from": "1980", "year_to": "2000"},
        (52.47831474597274, 6, 1980, 2000, "52.5 percentage points"),
        (8.38330161022184, 6, 1980, 2000, "8.4 percentage points"),
    ),
    "a range wholly before it": (
        {"year_to": "1900"},
        (33.859688838064855, 20, 1824, 1900, "33.9 percentage points"),
        "No average: this dataset's popular-vote figures cover 1976–2024, not the "
        "years shown",
    ),
    "a single year": (
        {"year_from": "2000", "year_to": "2000"},
        (0.9293680297397799, 1, 2000, 2000, "0.9 percentage points"),
        (0.5112914484084907, 1, 2000, 2000, "0.5 percentage points"),
    ),
    "only years with a popular vote": (
        {"pv": "1"},
        (33.471547040320274, 13, 1976, 2024, "33.5 percentage points"),
        (5.687741898936854, 13, 1976, 2024, "5.7 percentage points"),
    ),
    "a range straddling the window": (
        {"year_from": "1960", "year_to": "1990"},
        (57.04359722539511, 8, 1960, 1988, "57.0 percentage points"),
        (9.435891644389528, 4, 1976, 1988, "9.4 percentage points"),
    ),
    "an empty selection": (
        {"pv": "1", "year_to": "1900"},
        "No average: no elections match these filters",
        "No average: no elections match these filters",
    ),
}


def metric_text(tree: Any, key: str) -> str:
    """A metric's whole shown text (the count line, or an average's value)."""
    node = find(tree, METRIC_IDS[key])
    assert node is not None, key
    return "".join(texts(node.children))


def notes_of(tree: Any) -> list[str]:
    block = find(tree, METRICS_BLOCK)
    return ["".join(texts(p.children)) for p in of_type(block, "P")][1:]


def over(n: int, first: int, last: int) -> str:
    """The wording after an average's value, written out (ba spec, #437)."""
    if n == 1:
        return f", over 1 election ({first})"
    return f", over {n} elections ({first}–{last})"


class TestMetrics:
    @pytest.mark.parametrize("name", list(CASES))
    def test_each_mean_equals_its_literal(
        self, name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The page's own means, as ``metrics.mean`` returned them during the render
        (so a mean computed anywhere else, or over rounded margins, fails), against the
        literals; and each one's shown text."""
        query, *expected = CASES[name]
        computed: list[metrics.Mean] = []
        real = metrics.mean

        def spy(pairs: Any) -> metrics.Mean:
            computed.append(real(pairs))
            return computed[-1]

        monkeypatch.setattr(metrics, "mean", spy)
        tree = render_n1(query=query)
        assert len(computed) == len(MOD["MEANS"]), name
        for key, want, mean in zip(MOD["MEANS"], expected, computed, strict=True):
            if isinstance(want, str):
                assert (mean.value, mean.n) == (None, 0), (name, key)
                assert metric_text(tree, key) == want, (name, key)
                continue
            value, n, first, last, text = want
            assert (mean.n, mean.first, mean.last) == (n, first, last), (name, key)
            assert mean.value == pytest.approx(value, rel=1e-12), (name, key)
            assert metric_text(tree, key) == text + over(n, first, last), (name, key)

    @pytest.mark.parametrize("name", list(CASES))
    def test_the_count_is_t1_s_row_count(self, name: str) -> None:
        tree = render_n1(query=CASES[name][0])
        shown = len(rows(tree))
        assert metric_text(tree, "elections_shown") == (
            f"Showing {shown} of {len(YEARS)} elections"
        )

    def test_an_empty_selection_shows_no_zero_and_no_nan(self) -> None:
        tree = render_n1(query=CASES["an empty selection"][0])
        assert rows(tree) == []
        for key in MOD["MEANS"]:
            text = metric_text(tree, key)
            assert not any(ch.isdigit() for ch in text) and "nan" not in text.lower()

    def test_both_averages_name_their_own_elections_and_years_side_by_side(
        self,
    ) -> None:
        """The default view is the mismatched case: the two Ns and windows both show,
        in one list, and a note says the two do not cover the same elections."""
        tree = render_n1()
        (dl,) = of_type(find(tree, METRICS_BLOCK), "Dl")
        assert [dt.children for dt in of_type(dl, "Dt")] == [
            "Average electoral margin",
            "Average popular-vote margin",
        ]
        shown = "".join(texts(dl.children))
        assert "over 51 elections (1824–2024)" in shown
        assert "over 13 elections (1976–2024)" in shown
        assert notes_of(tree) == [
            labels.MARGIN_NOTE,
            "The two averages do not cover the same elections: this dataset's "
            "popular-vote figures cover 1976–2024. To compare the two over the same "
            'elections, select "Only years with a popular vote in this dataset".',
        ]

    @pytest.mark.parametrize(
        "name",
        [
            "a range inside the popular-vote window",
            "a single year",
            "only years with a popular vote",
            "a range wholly before it",
            "an empty selection",
        ],
    )
    def test_no_note_when_the_two_cover_the_same_elections_or_one_has_none(
        self, name: str
    ) -> None:
        assert notes_of(render_n1(query=CASES[name][0])) == [labels.MARGIN_NOTE]

    @pytest.mark.parametrize(
        ("year", "window"), [(2024, "1976–2020"), (2000, "1976–2024")]
    )
    def test_a_missing_margin_inside_the_window_shows_no_note(
        self, year: int, window: str
    ) -> None:
        """The note names the window as the reason the two differ, so a difference from
        a missing popular-vote margin inside it shows no note, whether it moves the
        average's years (2024) or only its N (2000); each average names its own."""
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] == year:
                item["pv_margin"] = None
        tree = render_n1(summary, query={"pv": "1"})
        assert metric_text(tree, "pv_margin_mean").endswith(
            f"over 12 elections ({window})"
        )
        assert metric_text(tree, "ec_margin_mean").endswith(
            "over 13 elections (1976–2024)"
        )
        assert notes_of(tree) == [labels.MARGIN_NOTE]

    def test_the_hint_shows_only_while_the_popular_vote_filter_is_off(self) -> None:
        """A year outside the window kept by the popular-vote filter (1972, doctored to
        say it has one) enters the electoral average only: the note shows, the hint
        does not, since the filter is on."""
        index = copy.deepcopy(BODY)
        for row in index["data"]:
            if row["year"] == 1972:
                row["has_popular_vote"] = True
        tree = render_n1(index=index, query={"pv": "1"})
        assert metric_text(tree, "ec_margin_mean").endswith(
            "over 14 elections (1972–2024)"
        )
        assert notes_of(tree) == [
            labels.MARGIN_NOTE,
            "The two averages do not cover the same elections: this dataset's "
            "popular-vote figures cover 1976–2024.",
        ]

    def test_the_note_is_not_shown_when_no_electoral_year_lies_outside_the_window(
        self,
    ) -> None:
        """The exact test: years outside the window are shown, but none entered the
        electoral average, so the window is no cause (ba, #437's code review)."""
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] < 1976:
                item["ec_margin"] = None
            if item["year"] == 2000:
                item["pv_margin"] = None
        tree = render_n1(summary, query={"year_from": "1960"})
        assert metric_text(tree, "ec_margin_mean").endswith(
            "over 13 elections (1976–2024)"
        )
        assert metric_text(tree, "pv_margin_mean").endswith(
            "over 12 elections (1976–2024)"
        )
        assert notes_of(tree) == [labels.MARGIN_NOTE]

    @pytest.mark.parametrize(
        ("query", "note"), [({}, "1972–2020."), ({"year_to": "1900"}, None)]
    )
    def test_the_popular_vote_years_come_from_coverage(
        self, query: dict[str, str], note: str | None
    ) -> None:
        """Both sentences that name the popular-vote years take them from the index's
        ``coverage``, never a literal: a doctored window shows in each."""
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"].update(
            pv_year_min=1972, pv_year_max=2020
        )
        tree = render_n1(index=index, query=query)
        if note is None:
            assert metric_text(tree, "pv_margin_mean") == (
                "No average: this dataset's popular-vote figures cover 1972–2020, "
                "not the years shown"
            )
        else:
            (_, sentence) = notes_of(tree)
            assert sentence.startswith(
                "The two averages do not cover the same elections: this dataset's "
                f"popular-vote figures cover {note}"
            )

    def test_the_note_shows_for_an_electoral_year_after_the_window(self) -> None:
        """The trigger's other half: an election served after the popular-vote window
        (here 2024, with the window doctored to end in 2020 and its margin missing)
        enters the electoral average only, so the window is a cause and the note shows,
        with the hint while the popular-vote filter is off."""
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"].update(
            pv_year_min=1976, pv_year_max=2020
        )
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] == 2024:
                item["pv_margin"] = None
        tree = render_n1(summary, index=index, query={"year_from": "1976"})
        assert metric_text(tree, "ec_margin_mean").endswith(
            "over 13 elections (1976–2024)"
        )
        assert metric_text(tree, "pv_margin_mean").endswith(
            "over 12 elections (1976–2020)"
        )
        assert notes_of(tree) == [
            labels.MARGIN_NOTE,
            "The two averages do not cover the same elections: this dataset's "
            "popular-vote figures cover 1976–2020. To compare the two over the same "
            'elections, select "Only years with a popular vote in this dataset".',
        ]

    def test_a_range_after_the_window_names_the_window(self) -> None:
        """No year shown lies inside the popular-vote window when every one is after
        it (the window doctored to end in 2020, 2024 shown with no popular-vote
        margin): the popular-vote value names the window, not a missing margin."""
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"].update(
            pv_year_min=1976, pv_year_max=2020
        )
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] == 2024:
                item["pv_margin"] = None
        tree = render_n1(summary, index=index, query={"year_from": "2024"})
        assert metric_text(tree, "pv_margin_mean") == (
            "No average: this dataset's popular-vote figures cover 1976–2020, "
            "not the years shown"
        )

    def test_the_hint_names_the_checkbox_by_its_own_text(self) -> None:
        """``METRIC_SAME_ELECTIONS`` tells the reader to select the popular-vote
        checkbox by its label, so the two must not drift apart."""
        (checklist,) = of_type(render_n1(), "Checklist")
        (option,) = checklist.options
        assert f'"{option["label"].strip()}"' in labels.METRIC_SAME_ELECTIONS

    def test_a_single_year_reconciles_to_its_served_margin(self) -> None:
        """Wherever a served figure exists, the metric reconciles to it: an average
        over one election shows that year's panel margin cell exactly (a precision pin:
        a mean of one value is that value)."""
        tree = render_n1(query=CASES["a single year"][0])
        for key in MOD["MEANS"]:
            dd = find(tree, METRIC_IDS[key])
            value, rest = (span.children for span in of_type(dd, "Span"))
            field = metrics.METRICS[key].source.field
            assert value == labels.margin(ITEMS[2000][field], True)
            assert rest == ", over 1 election (2000)"

    @pytest.mark.parametrize("key", ["ec_margin_mean", "pv_margin_mean"])
    def test_the_metric_table_drives_what_is_averaged(
        self, key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuity of the source check: the page reads each mean's field from
        ``metrics.METRICS``, so pointing a row at another field changes the figure
        (the hybrid margin over the popular-vote years: 19.379… by ``sum()/len()``)."""
        monkeypatch.setitem(
            metrics.METRICS,
            key,
            metrics.Metric("mean", metrics.Source("ElectionSummary", "hybrid_margin")),
        )
        tree = render_n1(query={"pv": "1"})
        assert metric_text(tree, key) == (
            "19.4 percentage points, over 13 elections (1976–2024)"
        )

    def test_a_year_listed_twice_counts_once_in_an_average(self) -> None:
        index = copy.deepcopy(BODY)
        index["data"].append(next(r for r in index["data"] if r["year"] == 2000))
        tree = render_n1(index=index, query=CASES["a single year"][0])
        assert metric_text(tree, "elections_shown") == "Showing 2 of 52 elections"
        assert metric_text(tree, "ec_margin_mean").endswith(", over 1 election (2000)")

    def test_an_unrecognized_margin_reads_so_and_names_no_n(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] == 2000:
                item["ec_margin"] = "x"
        tree = render_n1(summary)
        dd = find(tree, METRIC_IDS["ec_margin_mean"])
        assert dd.children == labels.UNRECOGNIZED
        assert dd.title == labels.UNRECOGNIZED_NOTE
        assert metric_text(tree, "pv_margin_mean").startswith("5.7 percentage points")
        assert notes_of(tree) == [labels.MARGIN_NOTE]

    def test_metrics_render_only_inside_the_list_of_elections(self) -> None:
        tree = render_n1()
        order = [getattr(n, "id", None) for n in in_order(tree)]
        assert order.index(YEARS_ID) < order.index(METRICS_BLOCK)
        assert order.index(METRICS_BLOCK) < order.index(TABLE_ID)


class TestMetricsDegraded:
    def test_an_unreadable_n1_keeps_the_count(self) -> None:
        tree = render()  # no N1 body
        assert metric_text(tree, "elections_shown") == "Showing 51 of 51 elections"
        sentence = find(tree, MOD["METRICS_UNAVAILABLE_ID"])
        assert sentence.children == MOD["METRICS_UNAVAILABLE"]
        assert of_type(find(tree, METRICS_BLOCK), "Dl") == []
        assert components.UNAVAILABLE_MESSAGE not in MOD["METRICS_UNAVAILABLE"]
        assert "isn't responding" not in MOD["METRICS_UNAVAILABLE"]

    @pytest.mark.parametrize(
        ("name", "summary"),
        [
            ("a served year with no elections item", _without(1876)),
            ("an elections item for a year not served", None),
            ("two items for one year", _second_item()),
            ("an item with no ec_margin", None),
        ],
    )
    def test_an_item_level_defect_degrades_the_averages(
        self, name: str, summary: Any
    ) -> None:
        """Each defect replaces the averages with their sentence and keeps the count."""
        if name == "an elections item for a year not served":
            summary = copy.deepcopy(SUMMARY)
            summary["elections"].append({**summary["elections"][0], "year": 1826})
        if name == "an item with no ec_margin":
            summary = copy.deepcopy(SUMMARY)
            del summary["elections"][3]["ec_margin"]
        tree = render_n1(summary)
        assert find(tree, MOD["METRICS_UNAVAILABLE_ID"]) is not None, name
        assert find(tree, METRIC_IDS["elections_shown"]) is not None
        assert shown_years(tree) == YEARS

    def test_c2_and_the_averages_share_one_item_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both readers call ``elections_view.n1_items`` (D097(c)), C2 from its own page
        since #562: when it refuses the recording, both sections degrade and the count
        still shows; when it hands back doctored items, the averages show them."""

        def refuse(index: Any, summary: Any) -> Any:
            raise TypeError("refused")

        majority = dash.page_registry["pages.elections_majority"]["layout"].__globals__
        monkeypatch.setattr(elections_view, "n1_items", refuse)
        tree = render_n1()
        assert find(tree, MOD["METRICS_UNAVAILABLE_ID"]) is not None
        assert find(tree, METRIC_IDS["elections_shown"]) is not None
        c2 = majority["render"](copy.deepcopy(BODY), copy.deepcopy(SUMMARY))
        assert find(c2, majority["LEADER_UNAVAILABLE_ID"]) is not None

        def doctored(index: Any, summary: Any) -> dict[int, dict[str, Any]]:
            return {y: {**item, "ec_margin": 10.0} for y, item in ITEMS.items()}

        monkeypatch.setattr(elections_view, "n1_items", doctored)
        assert metric_text(render_n1(), "ec_margin_mean").startswith(
            "10.0 percentage points"
        )

    def test_a_rank_level_defect_leaves_the_averages(self) -> None:
        """A tie at rank 1 is valid API data (D094(iv)) that C2 refuses by design; the
        averages read no ``data`` row, so they still show."""
        tree = render_n1(_second_leader())
        assert find(tree, MOD["METRICS_UNAVAILABLE_ID"]) is None
        assert metric_text(tree, "ec_margin_mean").startswith("41.2 percentage points")

    def test_a_malformed_popular_vote_window_degrades_only_the_averages(self) -> None:
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"]["pv_year_min"] = True
        tree = render_n1(index=index)
        assert find(tree, MOD["METRICS_UNAVAILABLE_ID"]) is not None
        assert shown_years(tree) == YEARS

    def test_the_degraded_page_has_no_metrics(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        tree = PAGE["layout"]()
        assert find(tree, METRICS_BLOCK) is None
        assert find(tree, METRIC_IDS["elections_shown"]) is None


class TestMetricsFilters:
    def test_a_filter_change_makes_no_request_once_n1_is_cached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        route("/elections", "")  # fills N1 on its miss
        calls.clear()
        seen = set()
        for search in ("?pv=1", "?year_to=1900", "?year_from=1980&year_to=2000", ""):
            response = route("/elections", search)
            node = json_node(response.get_json(), METRIC_IDS["ec_margin_mean"])
            assert node is not None, search
            seen.add(str(node["props"]["children"]))
            assert calls == [], search
        assert len(seen) == 4  # each filter change showed its own figure
        assert len(bucket.waits) == 1  # N1's fill, before the filters

    @pytest.mark.parametrize("query", SHARED)
    def test_og_url_reopens_the_same_figures(self, query: str) -> None:
        resolution = appmod.resolve("/elections", query, None)
        assert resolution.og_url is not None
        normal = urllib.parse.urlsplit(resolution.og_url).query
        raw, reopened = (render_n1(query=parse(q)) for q in (query, normal))
        for key in METRIC_IDS:
            assert metric_text(raw, key) == metric_text(reopened, key), (query, key)


class TestMetricLabels:
    def test_every_metric_has_a_label_and_no_metric_key_is_a_field_label(self) -> None:
        assert list(labels.METRIC_LABELS) == list(metrics.METRICS)
        assert set(labels.METRIC_LABELS).isdisjoint(labels.LABELS)
        assert set(METRIC_IDS) == set(metrics.METRICS)
        assert set(MOD["MEANS"]) == {
            k for k, m in metrics.METRICS.items() if m.kind == "mean"
        }

    def test_every_source_is_a_public_api_field(self) -> None:
        assert metric_source_problems(metrics.METRICS.values()) == []

    def test_the_source_check_fails_what_it_should(self) -> None:
        bad = [
            metrics.Metric("mean", metrics.Source("ElectionSummary", "nonsense")),
            metrics.Metric("mean", metrics.Source("NoSuchModel", "year")),
            metrics.Metric("count", metrics.Source("ElectionSummary", "ec_denominator")),
        ]
        assert metric_source_problems(bad) == [
            "ElectionSummary.nonsense",
            "NoSuchModel.year",
            "ElectionSummary.ec_denominator",
        ]


def metric_source_problems(rows: Any) -> list[str]:
    """Each metric source that names no public field of its ``/v1`` model (a snapshot
    column the model accepts only as an input alias is not one). Test-only: the
    runtime imports no ``usvote``."""
    from usvote.api import models

    problems = []
    for metric in rows:
        model = getattr(models, metric.source.model, None)
        fields = getattr(model, "model_fields", {})
        if metric.source.field not in fields:
            problems.append(f"{metric.source.model}.{metric.source.field}")
    return problems


class TestMetricsModule:
    @pytest.mark.parametrize("value", [None, "", "  "])
    def test_a_null_or_blank_is_left_out(self, value: Any) -> None:
        mean = metrics.mean([(1976, 2.0), (1980, value), (1984, 4.0)])
        assert mean == metrics.Mean(3.0, 2, 1976, 1984)

    @pytest.mark.parametrize(
        "value", [True, False, "x", float("nan"), float("inf"), float("-inf"), 10**400]
    )
    def test_a_value_no_figure_can_show_makes_the_mean_unrecognized(
        self, value: Any
    ) -> None:
        assert metrics.mean([(1976, 2.0), (1980, value)]) == metrics.UNRECOGNIZED

    def test_a_sum_that_overflows_is_unrecognized(self) -> None:
        assert metrics.mean([(1976, 1e308), (1980, 1e308)]) == metrics.UNRECOGNIZED

    def test_no_value_is_no_average(self) -> None:
        assert metrics.mean([]) == metrics.NO_AVERAGE
        assert metrics.mean([(1824, None)]) == metrics.NO_AVERAGE
        assert metrics.NO_AVERAGE.value is None and not metrics.NO_AVERAGE.unrecognized

    def test_an_int_and_a_negative_zero_are_figures(self) -> None:
        assert metrics.mean([(1976, 1), (1980, -0.0)]) == metrics.Mean(
            0.5, 2, 1976, 1980
        )

    @pytest.mark.parametrize(
        "args",
        [
            (1.0, 0, None, None),
            (None, 1, 2000, 2000),
            (1.0, 1, 2004, 2000),
            (float("nan"), 1, 2000, 2000),
            (1.0, 1, None, 2000),
            (1, 1, 2000, 2000),
            (None, 0, 2000, None),
            (1.0, 1, 2000, 2000, True),
            (1.0, 0, 2000, 2000),  # a number needs at least one election
        ],
    )
    def test_a_mean_in_no_state_cannot_be_built(self, args: tuple[Any, ...]) -> None:
        with pytest.raises(ValueError):
            metrics.Mean(*args)

    def test_count_counts_rows(self) -> None:
        assert metrics.count([]) == 0
        assert metrics.count(BODY["data"]) == len(YEARS)


class TestN1Items:
    def test_the_recording_gives_one_item_per_served_year(self) -> None:
        items = elections_view.n1_items(copy.deepcopy(BODY), copy.deepcopy(SUMMARY))
        assert sorted(items) == YEARS
        assert items[2000]["ec_margin"] == ITEMS[2000]["ec_margin"]

    @pytest.mark.parametrize(
        "name", ["a served year with no elections item", "two items for one year"]
    )
    def test_an_item_defect_is_refused(self, name: str) -> None:
        summary = _without(1876) if name.startswith("a served") else _second_item()
        with pytest.raises(TypeError):
            elections_view.n1_items(copy.deepcopy(BODY), summary)

    def test_it_reads_no_data_row(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        summary["data"] = "not a list"
        assert sorted(elections_view.n1_items(copy.deepcopy(BODY), summary)) == YEARS


class TestMetricMeanWording:
    """``labels.metric_mean``'s no-average causes, in their order (#437)."""

    @pytest.mark.parametrize(
        ("years", "window", "text"),
        [
            ([], (1976, 2024), labels.METRIC_NO_AVERAGE_FILTERS),
            ([1980], (1976, 2024), labels.METRIC_NO_AVERAGE_NULL),
            ([1980], None, labels.METRIC_NO_AVERAGE_NULL),
            (
                [1900],
                (1976, 2024),
                "No average: this dataset's popular-vote figures cover 1976–2024, "
                "not the years shown",
            ),
            ([1900, 1980], (1976, 2024), labels.METRIC_NO_AVERAGE_NULL),
            (
                [2028],  # after the window: both of its bounds are checked
                (1976, 2024),
                "No average: this dataset's popular-vote figures cover 1976–2024, "
                "not the years shown",
            ),
        ],
    )
    def test_each_cause(
        self, years: list[int], window: tuple[int, int] | None, text: str
    ) -> None:
        assert labels.metric_mean(metrics.NO_AVERAGE, years, window) == (text, None)

    def test_an_unrecognized_mean_names_no_n(self) -> None:
        assert labels.metric_mean(metrics.UNRECOGNIZED, [1980], None) == (
            labels.UNRECOGNIZED,
            None,
        )

    @pytest.mark.parametrize("query", [{}, {"year_to": "1900"}])
    def test_every_null_margin_reads_the_null_text_on_the_page(
        self, query: dict[str, str]
    ) -> None:
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            item["ec_margin"] = None
            item["pv_margin"] = None
        tree = render_n1(summary, query=query)
        assert metric_text(tree, "ec_margin_mean") == labels.METRIC_NO_AVERAGE_NULL
        if not query:
            assert metric_text(tree, "pv_margin_mean") == (
                labels.METRIC_NO_AVERAGE_NULL
            )


# --- the wide layout (#553, D102, D103) ----------------------------------------------


class TestPair:
    """``components.pair``, the one way to build a ``.pair`` (D103): two column divs in
    source order, refusing a table. ``test_only_components_builds_a_pair``
    (``test_dashboard_guards.py``) fails a module that sets the class itself."""

    def test_it_builds_two_columns_in_source_order(self) -> None:
        left, right = html.P("left", id="l"), html.P("right", id="r")
        built: Any = components.pair([left], [right], "p")
        assert built.id == "p" and built.className == "pair"
        first, second = built.children
        assert type(first).__name__ == type(second).__name__ == "Div"
        assert first.children == [left] and second.children == [right]
        # A column has no id unless the page names one.
        assert "id" not in first.to_plotly_json()["props"]
        assert "id" not in second.to_plotly_json()["props"]

    def test_a_column_id_names_the_column_itself(self) -> None:
        held = html.P("x", id="x")
        built: Any = components.pair([held], [held], "p", left_id="a", right_id="b")
        first, second = built.children
        assert (first.id, second.id) == ("a", "b")
        assert first.children == [held] and second.children == [held]

    def test_it_accepts_a_chart(self) -> None:
        # Imported here: test_dashboard_export imports from this module.
        from tests.unit.test_dashboard_export import TEST_FIGURE

        figure: Any = components.chart(
            "C4", TEST_FIGURE, "elections-over-time-table", "Caption"
        )
        assert find(components.pair([figure], [], "p"), figure.id) is figure

    @pytest.mark.parametrize(
        "column",
        [
            lambda: [html.Table([], id="t")],
            lambda: [html.Div([html.P("x"), html.Div(html.Table([]))])],
            lambda: [html.Div(html.P("x"), className="note table-scroll")],
        ],
        ids=["table", "nested-table", "scroll-box"],
    )
    @pytest.mark.parametrize("side", ["left", "right"])
    def test_it_refuses_a_table_in_either_column(self, column: Any, side: str) -> None:
        held = column()
        left, right = (held, []) if side == "left" else ([], held)
        with pytest.raises(ValueError, match="holds a table"):
            components.pair(left, right, "p")


class TestWideLayout:
    """The elections index's wide layout (#553, D102): the list's pair (C4 and C5's
    pair is on their own page since #562). The stylesheet's rules are pinned in
    ``TestLayoutRules`` (``test_dashboard_theme.py``); what a browser draws, at which
    width, is the e2e suite's (``test_dashboard_e2e_elections.py``)."""

    @staticmethod
    def pair(tree: Any, key: str) -> Any:
        node = find(tree, MOD[key])
        assert node is not None and node.className == "pair"
        return node

    def test_the_list_pair_holds_the_filters_left_and_the_metrics_right(self) -> None:
        tree = render_n1()
        pair = self.pair(tree, "LIST_PAIR_ID")
        kids = list(tree.children)
        # A direct child of the success marker, right after the list's heading.
        heading = kids[kids.index(pair) - 1]
        assert type(heading).__name__ == "H2"
        assert heading.children == MOD["LIST_HEADING"]
        left, right = pair.children
        assert find(left, YEARS_ID) is not None and find(left, PV_ID) is not None
        assert find(left, MOD["METRICS_ID"]) is None and find(right, YEARS_ID) is None
        # The right column is the metrics block itself, with no wrapper of its own,
        # so the pair's margin reset reaches the count line (#553's review, r1.cr.1).
        assert right.id == MOD["METRICS_ID"]
        assert right.children[0].className == "count"
        assert left.children[0].className == "filters"

    def test_t1_follows_the_list_pair_and_is_not_in_it(self) -> None:
        tree = render_n1()
        pair = self.pair(tree, "LIST_PAIR_ID")
        assert of_type(pair, "Table") == [] and find(pair, TABLE_ID) is None
        kids = list(tree.children)
        assert any(find(kid, TABLE_ID) is not None for kid in kids[kids.index(pair) :])

    def test_the_list_opens_the_page_in_no_pair(self) -> None:
        """Since #562 C2 has its own page: the heading, the lede and the URL control
        open the page, then the list's heading, outside every pair."""
        tree = render_n1()
        kids = list(tree.children)
        assert type(kids[0]).__name__ == "H1" and kids[1].className == "lede"
        assert type(kids[2]).__name__ == "Location"
        assert kids[3].id == elections_view.SECTIONS_ID  # the section links (#562)
        assert type(kids[4]).__name__ == "H2" and kids[4].children == MOD["LIST_HEADING"]
        assert find(tree, charts.dom_id("C2")) is None

    def test_an_unavailable_n1_keeps_the_list_pair(self) -> None:
        tree = MOD["render"](copy.deepcopy(BODY), [], None)
        # The list pair stands, its right column holding the averages' sentence.
        _, right = self.pair(tree, "LIST_PAIR_ID").children
        assert find(right, MOD["METRICS_UNAVAILABLE_ID"]) is not None

    def test_an_empty_list_keeps_the_pair_and_its_sentence_follows(self) -> None:
        tree = render_n1(query={"year_to": "1900", "pv": "1"})
        assert shown_years(tree) == []
        pair = self.pair(tree, "LIST_PAIR_ID")
        assert classed(pair, "empty") == []
        assert classed(tree, "empty") != []


def ids_of(tree: Any) -> list[Any]:
    """Every component id in a rendered tree, in document order."""
    return [n.id for n in in_order(tree) if getattr(n, "id", None) is not None]


# --- the section links between the three elections pages (#562, D092's pattern) ------

ELECTIONS_PAGES = {
    elections_view.LIST: "pages.elections",
    elections_view.MAJORITY: "pages.elections_majority",
    elections_view.OVER_TIME: "pages.elections_over_time",
}


class TestSectionLinks:
    @staticmethod
    def rendered(path: str, summary: Any = None) -> Any:
        page = dash.page_registry[ELECTIONS_PAGES[path]]
        own = page["layout"].__globals__
        index = copy.deepcopy(BODY)
        n1 = copy.deepcopy(SUMMARY) if summary is None else summary
        if path == elections_view.LIST:
            return own["render"](index, [], n1)
        return own["render"](index, n1)

    @pytest.mark.parametrize("path", list(ELECTIONS_PAGES))
    def test_each_page_marks_itself_and_links_the_other_two(self, path: str) -> None:
        nav = find(self.rendered(path), elections_view.SECTIONS_ID)
        assert type(nav).__name__ == "Nav"
        assert getattr(nav, "aria-label") == labels.ELECTIONS_SECTIONS_LABEL
        assert nav.className == "section-links"
        texts_in_order = [entry.children for entry in nav.children]
        assert texts_in_order == [
            labels.SECTION_ELECTIONS_LIST,
            labels.SECTION_MAJORITY,
            labels.SECTION_OVER_TIME,
        ]
        for entry, section in zip(nav.children, elections_view.SECTIONS, strict=True):
            if section == path:
                assert type(entry).__name__ == "Span"
                assert getattr(entry, "aria-current") == "page"
            else:
                # Client-side and unfiltered: the bare path, no query.
                assert type(entry).__name__ == "Link" and entry.href == section

    def test_the_index_s_links_carry_no_filter(self) -> None:
        own = PAGE["layout"].__globals__
        tree = own["render"](
            copy.deepcopy(BODY),
            own["parse_filters"]({"year_from": "1900", "pv": "1"}),
            copy.deepcopy(SUMMARY),
        )
        nav = find(tree, elections_view.SECTIONS_ID)
        hrefs = [e.href for e in nav.children if type(e).__name__ == "Link"]
        assert hrefs == [elections_view.MAJORITY, elections_view.OVER_TIME]

    @pytest.mark.parametrize("path", list(ELECTIONS_PAGES))
    def test_a_failed_n1_keeps_the_links(self, path: str) -> None:
        page = dash.page_registry[ELECTIONS_PAGES[path]]
        own = page["layout"].__globals__
        if path == elections_view.LIST:
            tree = own["render"](copy.deepcopy(BODY), [], None)
        else:
            tree = own["render"](copy.deepcopy(BODY), None)
        assert find(tree, elections_view.SECTIONS_ID) is not None
        assert tree.id == page["success"]

    @pytest.mark.parametrize("path", list(ELECTIONS_PAGES))
    def test_the_degraded_page_has_no_links(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        """On success only (D092): the index unreadable, no section links."""

        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        tree = dash.page_registry[ELECTIONS_PAGES[path]]["layout"]()
        assert find(tree, elections_view.SECTIONS_ID) is None
        assert components.UNAVAILABLE_MESSAGE in texts(tree)

    def test_the_links_route_client_side_to_each_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        for path, module in ELECTIONS_PAGES.items():
            success = dash.page_registry[module]["success"]
            ids = routed_ids(route(path))
            assert success in ids and elections_view.SECTIONS_ID in ids, path
