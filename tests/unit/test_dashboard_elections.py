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
import urllib.parse
from pathlib import Path
from typing import Any

import dash
import pytest
from dash import no_update
from dash.development.base_component import Component

from explore import api, charts, components, labels, metrics
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
        written = MOD["search_for"](years.value, pv.value, years.min, years.max)
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
        written = MOD["search_for"](years.value, pv.value, years.min, years.max)
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
                {"id": MOD["URL_ID"], "property": "search", "value": ""},
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
        # The render fills N1 once, on a miss, for chart C2 (#434); never the index.
        assert calls == [api.SUMMARY_PATH] and len(bucket.waits) == 1

    def test_the_callback_leaves_an_unchanged_url_alone(self) -> None:
        callback = MOD["on_filter_change"]
        assert callback([1900, LAST], ["1"], FIRST, LAST, "") == "?pv=1&year_from=1900"
        assert callback([1900, LAST], ["1"], FIRST, LAST, "?pv=1&year_from=1900") is (
            no_update
        )
        assert callback([FIRST, LAST], [], FIRST, LAST, None) is no_update
        assert callback([FIRST, LAST], [], FIRST, LAST, "?pv=1") == ""

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
    def test_search_for_is_total_and_normal(
        self, years: Any, pv: Any, search: str
    ) -> None:
        assert MOD["search_for"](years, pv, FIRST, LAST) == search


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
            # Only the first render fills N1, on a miss, for chart C2 (#434, D096);
            # every filter change after it is answered from the cache.
            assert calls == [api.SUMMARY_PATH], search
            assert len(bucket.waits) == 1, search
        for years, pv in (([1900, LAST], ["1"]), ([FIRST, 1950], [])):
            MOD["on_filter_change"](years, pv, FIRST, LAST, "")
        assert calls == [api.SUMMARY_PATH]
        assert len(bucket.waits) == 1

    def test_the_callback_reads_no_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class NoView:
            def view(self) -> Any:
                raise AssertionError("the filter callback read the API")

        monkeypatch.setattr(api, "CLIENT", NoView())
        assert MOD["on_filter_change"]([1900, LAST], [], FIRST, LAST, "") == (
            "?year_from=1900"
        )

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
        # C2's N1 is filled on a miss in each snapshot (#434); D072's prefetch is not.
        assert calls == [api.SUMMARY_PATH]
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
        assert calls == [api.SUMMARY_PATH]


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
    "export.py",
    "labels.py",
    "metrics.py",  # the dashboard's own summaries (#437, D097)
    "query.py",
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
        assert in_cycles(graph) == []

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


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path"] == "/elections"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    # N1, chart C2's source, a literal filled on a miss (#434, D074(ii)).
    assert PAGE["on_miss"] == (api.SUMMARY_PATH,)
    assert PAGE["success"] == PAGE_ID
    assert VERSION  # the recorded snapshot every cached render answers from


# --- chart C2 (#434, D096) ------------------------------------------------------------

SUMMARY: dict[str, Any] = RECORDED[api.SUMMARY_PATH]
C2 = charts.dom_id("C2")
LEADERS = MOD["LEADER_TABLE_ID"]
#: The years with a recorded ``/v1/elections/{year}``: T3's rows to reconcile against.
RECONCILED = (1824, 1860, 1868, 1872, 1896, 2016, 2024)
#: T3's worded cells, from the overview's own function (one source for T3 and C1).
NATION_CELLS = dash.page_registry["pages.election"]["layout"].__globals__[
    "_nation_cells"
]


def render_c2(
    summary: Any = None, index: Any = None, query: dict[str, Any] | None = None
) -> Any:
    """The page for the index and an N1 body (the recording unless given)."""
    return MOD["render"](
        copy.deepcopy(BODY if index is None else index),
        MOD["parse_filters"](query or {}),
        copy.deepcopy(SUMMARY if summary is None else summary),
    )


def c2_figure(tree: Any) -> dict[str, Any]:
    (store,) = [
        node
        for node in of_type(tree, "Store")
        if isinstance(getattr(node, "id", None), dict) and node.id.get("chart") == C2
    ]
    figure: dict[str, Any] = store.data
    return figure


def points(tree: Any) -> dict[str, tuple[Any, str, str]]:
    """Each year's main point: its x, text and hover, by the year (the trace's ids)."""
    trace = c2_figure(tree)["data"][0]
    assert trace["name"] == labels.LABELS["ec_share_full"]
    return {
        year: (x, text, hover)
        for year, x, text, hover in zip(
            trace["ids"], trace["x"], trace["text"], trace["hovertext"], strict=True
        )
    }


def leader_rows(tree: Any) -> list[list[str]]:
    table = find(tree, LEADERS)
    return [texts(tr.children) for tr in of_type(of_type(table, "Tbody"), "Tr")]


def rank1(year: int) -> dict[str, Any]:
    summary: list[dict[str, Any]] = RECORDED[f"/v1/elections/{year}"]["summary"]
    (row,) = [r for r in summary if r["electoral_rank"] == 1]
    return row


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


class TestC2:
    def test_registered_on_the_index_with_its_own_companion_table(self) -> None:
        assert charts.CHARTS["C2"] == charts.Chart("/elections", LEADERS)
        assert MOD["C2_ID"] == "C2" and C2 == "c2"
        tree = render_c2()
        assert type(find(tree, C2)).__name__ == "Figure"  # the #c2 fragment's target
        assert PAGE_ID not in [n.id for n in of_type(find(tree, C2), "Div") if n.id]

    def test_the_page_order_puts_the_chart_above_the_list(self) -> None:
        tree = render_c2()
        headings = [h.children for h in of_type(tree, "H2")]
        assert headings[:3] == [
            MOD["C2_HEADING"],
            MOD["C2_TABLE_HEADING"],
            MOD["LIST_HEADING"],
        ]
        assert of_type(tree, "H1")[0].children == "Elections"
        assert of_type(tree, "P")[0].children == (
            f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}"
        )
        # The chart itself, in document order, above the list's heading and T1.
        order = in_order(tree)
        chart = order.index(find(tree, C2))
        (list_heading,) = [
            n
            for n in order
            if type(n).__name__ == "H2" and n.children == MOD["LIST_HEADING"]
        ]
        assert chart < order.index(list_heading) < order.index(find(tree, TABLE_ID))

    def test_one_point_for_every_served_year_oldest_first(self) -> None:
        tree = render_c2()
        figure = c2_figure(tree)
        assert [str(y) for y in YEARS] == figure["data"][0]["ids"]
        assert figure["layout"]["yaxis"]["ticktext"] == [str(y) for y in YEARS]
        # Oldest on top: rows 0…n−1 on a reversed axis.
        assert figure["data"][0]["y"] == list(range(len(YEARS)))
        assert figure["layout"]["yaxis"]["tickvals"] == list(range(len(YEARS)))
        assert figure["layout"]["yaxis"]["autorange"] == "reversed"
        assert (YEARS[0], YEARS[-1]) == (FIRST, LAST)  # the span is coverage's
        assert len(figure["data"]) == 1  # no marker: every leader has a share
        assert charts.figure_problems(figure) == []

    def test_one_point_per_year_however_the_index_is_cut(self) -> None:
        """No literal span: an index serving fewer years gets that many points."""
        index = copy.deepcopy(BODY)
        index["data"] = [r for r in index["data"] if r["year"] <= 1900]
        index["meta"]["provenance"]["coverage"]["year_max"] = 1900
        summary = copy.deepcopy(SUMMARY)
        for key in ("data", "elections"):
            summary[key] = [r for r in summary[key] if r["year"] <= 1900]
        ids = points(render_c2(summary, index))
        assert list(ids) == [str(r["year"]) for r in index["data"]]

    @pytest.mark.parametrize("year", RECONCILED)
    def test_each_recorded_year_reconciles_with_t3_s_leader(self, year: int) -> None:
        x, text, hover = points(render_c2())[str(year)]
        row = rank1(year)
        has_pv = (
            year
            >= RECORDED[api.ELECTIONS_PATH]["meta"]["provenance"]["coverage"][
                "pv_year_min"
            ]
        )
        cell = NATION_CELLS(row, has_pv)
        assert x == row["ec_share_full"]
        assert text == cell["ec_share_full"]
        assert cell["national_electoral_votes_counted"] in hover
        assert cell["national_electoral_denominator"] in hover
        assert hover.startswith(f"{year}: {row['candidate']}<br>")

    def test_1824_sits_below_the_line_and_reads_as_no_majority(self) -> None:
        x, text, hover = points(render_c2())["1824"]
        assert x < 0.5 and text == "37.9%"
        assert hover.endswith(f"<br>{labels.NO_EC_MAJORITY}")
        assert "Andrew Jackson" in hover

    @pytest.mark.parametrize(("year", "text"), [("1876", "50.1%"), ("2000", "50.4%")])
    def test_1876_and_2000_sit_just_above_the_line(self, year: str, text: str) -> None:
        x, shown, hover = points(render_c2())[year]
        assert 0.5 < x < 0.51 and shown == text
        assert hover.endswith(f"<br>{labels.EC_MAJORITY}")

    @pytest.mark.parametrize(
        ("year", "counted", "appointed"),
        [("2016", "304", "538"), ("1868", "214", "294"), ("1872", "286", "366")],
    )
    def test_the_counted_basis(self, year: str, counted: str, appointed: str) -> None:
        _, _, hover = points(render_c2())[year]
        assert f"Electoral votes counted: {counted}<br>" in hover
        assert f"Electors appointed: {appointed}<br>" in hover

    def test_every_hover_carries_a_majority_line(self) -> None:
        for year, (_, _, hover) in points(render_c2()).items():
            assert hover.rsplit("<br>", 1)[1] in (
                labels.EC_MAJORITY,
                labels.NO_EC_MAJORITY,
            ), year

    def test_a_null_majority_is_named_by_its_field(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        summary["elections"][1]["ec_determinative"] = None
        _, _, hover = points(render_c2(summary))[str(summary["elections"][1]["year"])]
        assert hover.endswith(
            f"<br>{labels.LABELS['ec_determinative']}: {labels.NOT_IN_DATASET}"
        )

    def test_the_point_is_the_served_ec_share_full(self) -> None:
        """Not a sibling or a derived value: 1860's leader's ``ec_share_full`` alone is
        doctored (deliberately inconsistent with its counts and ``ec_share_hybrid``), and
        the point, its text and the table's cell all follow it."""
        summary = copy.deepcopy(SUMMARY)
        (row,) = [
            r for r in summary["data"] if r["year"] == 1860 and r["electoral_rank"] == 1
        ]
        assert row["ec_share_hybrid"] != 0.25  # the premise
        row["ec_share_full"] = 0.25
        tree = render_c2(summary)
        x, text, hover = points(tree)["1860"]
        assert (x, text) == (0.25, "25.0%")
        assert "(counted ÷ appointed): 25.0%<br>" in hover
        (shown,) = [r for r in leader_rows(tree) if r[0] == "1860"]
        assert shown[4] == "25.0%"

    def test_the_candidate_is_escaped_in_the_hover(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        name = "A <b>&</b> B"
        summary["data"][0]["candidate"] = name  # 1824's leader
        figure = c2_figure(render_c2(summary))
        _, _, hover = points(render_c2(summary))["1824"]
        assert hover.startswith(f"1824: {charts.escaped(name)}<br>")
        assert charts.escaped(name) != name  # the premise
        assert charts.figure_problems(figure) == []

    def test_an_index_listing_a_year_twice_draws_it_once(self) -> None:
        index = copy.deepcopy(BODY)
        index["data"].append(copy.deepcopy(index["data"][0]))
        assert list(points(render_c2(index=index))) == [str(y) for y in YEARS]

    @pytest.mark.parametrize(
        ("value", "label"),
        [
            (None, labels.C1_NO_SHARE),
            ("zz", labels.UNRECOGNIZED),
            # Finite, but its percentage overflows, so its cell reads UNRECOGNIZED.
            (1e308, labels.UNRECOGNIZED),
        ],
    )
    def test_a_share_with_no_figure_is_a_labeled_marker(
        self, value: Any, label: str
    ) -> None:
        summary = copy.deepcopy(SUMMARY)
        (row,) = [
            r for r in summary["data"] if r["year"] == 1860 and r["electoral_rank"] == 1
        ]
        row["ec_share_full"] = value
        tree = render_c2(summary)
        figure = c2_figure(tree)
        x, text, _ = points(tree)["1860"]
        assert x is None and text == ""
        (marks,) = figure["data"][1:]
        assert marks["name"] == labels.C2_NO_SHARE_SERIES
        assert marks["ids"] == ["1860"] and marks["x"] == [0]
        assert marks["text"] == [label] and marks["marker"]["symbol"] == "x"
        if label == labels.UNRECOGNIZED:
            note = f"{labels.UNRECOGNIZED}<br>{labels.UNRECOGNIZED_NOTE}"
            assert note in marks["hovertext"][0]
        assert charts.figure_problems(figure) == []

    def test_the_majority_line_is_a_dashed_shape_at_half(self) -> None:
        layout = c2_figure(render_c2())["layout"]
        (line,) = layout["shapes"]
        assert (line["x0"], line["x1"], line["line"]["dash"]) == (0.5, 0.5, "dash")
        assert [a["text"] for a in layout["annotations"]] == [
            labels.C2_MAJORITY_LINE
        ] * 2
        assert layout["xaxis"]["range"] == [0, 1]

    def test_the_title_is_page_text(self) -> None:
        assert find(render_c2(), f"{C2}-title").children == labels.C2_TITLE

    def test_the_companion_table_holds_the_points_values(self) -> None:
        tree = render_c2()
        rows = leader_rows(tree)
        shown = points(tree)
        assert [r[0] for r in rows] == [str(y) for y in YEARS]
        for row in rows:
            year, candidate, counted, appointed, share, majority, took = row
            _, text, hover = shown[year]
            assert share == text
            assert hover == labels.C2_HOVER.format(
                year=year,
                candidate=candidate,
                share=share,
                counted=counted,
                appointed=appointed,
                majority=majority,
            )
            assert took in ("Yes", "No")
        assert rows[0][1] == "Andrew Jackson" and rows[0][6] == "No"
        table = find(tree, LEADERS)
        links = {a.href for a in of_type(table, "Link")}
        assert {f"/election/{y}" for y in YEARS} <= links

    @pytest.mark.parametrize(
        "query", [{"year_from": "1900"}, {"pv": "1"}, {"year_to": "1880"}]
    )
    def test_no_filter_narrows_the_chart_or_its_table(
        self, query: dict[str, str]
    ) -> None:
        filtered, plain = render_c2(query=query), render_c2()
        assert c2_figure(filtered) == c2_figure(plain)
        assert leader_rows(filtered) == leader_rows(plain)
        assert shown_years(filtered) != shown_years(plain)  # T1 is narrowed

    def test_the_download_names_the_leaders(self) -> None:
        (link,) = [
            a
            for a in of_type(render_c2(), "A")
            if getattr(a, "id", None) == f"{LEADERS}-csv"
        ]
        assert link.download == "elections-electoral-college-leaders.csv"
        assert link.children == "Download the Electoral College leaders (CSV)"


def _without(year: int) -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    summary["elections"] = [e for e in summary["elections"] if e["year"] != year]
    return summary


def _second_leader() -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    extra = copy.deepcopy(next(r for r in summary["data"] if r["year"] == 1860))
    extra["candidate_slug"] = "someone-else"
    summary["data"].append(extra)
    return summary


def _unserved() -> dict[str, Any]:
    # A rank-2 row (1824's Adams), so only the unserved-year check refuses it.
    summary = copy.deepcopy(SUMMARY)
    assert summary["data"][1]["electoral_rank"] == 2  # the premise
    summary["data"].append({**summary["data"][1], "year": 1826})
    return summary


def _second_item() -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    item = copy.deepcopy(summary["elections"][0])
    item["ec_determinative"] = not item["ec_determinative"]
    summary["elections"].append(item)
    return summary


def _bool_rank() -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    for row in summary["data"]:
        if row["year"] == 1824 and row["electoral_rank"] == 1:
            row["electoral_rank"] = True
    return summary


MALFORMED = {
    "a served year with no elections item": _without(1876),
    "two rank-1 rows in a year": _second_leader(),
    "a row for a year not served": _unserved(),
    "a served year with two elections items": _second_item(),
    "a rank that is a bool": _bool_rank(),
    "data that is not a list": {**SUMMARY, "data": {}},
    "no elections key": {k: v for k, v in SUMMARY.items() if k != "elections"},
    "a year that is a string": {
        **SUMMARY,
        "elections": [{**SUMMARY["elections"][0], "year": "1824"}]
        + SUMMARY["elections"][1:],
    },
    "not an object": [],
}


def _shape_defects() -> dict[str, Any]:
    """#487's scope ruling: every key of N1's body itself, its ``meta``, its first row,
    first ``elections`` item, ``meta.provenance`` and its ``coverage``, deleted and set
    to a wrong type, so no N1 defect the section can raise on is left untested,
    whichever piece reads the key (the top level and ``meta``: round 2's finding)."""
    cases: dict[str, Any] = {}
    places = {
        "N1": lambda b: b,
        "meta": lambda b: b["meta"],
        "data[0]": lambda b: b["data"][0],
        "elections[0]": lambda b: b["elections"][0],
        "meta.provenance": lambda b: b["meta"]["provenance"],
        "meta.provenance.coverage": lambda b: b["meta"]["provenance"]["coverage"],
    }
    for where, at in places.items():
        for key in at(SUMMARY):
            for change, value in (("deleted", None), ("None", None), ("[]", [])):
                body = copy.deepcopy(SUMMARY)
                if change == "deleted":
                    del at(body)[key]
                else:
                    at(body)[key] = value
                cases[f"{where}.{key} {change}"] = body
    return cases


SHAPE_DEFECTS = _shape_defects()


class TestC2Validation:
    def test_a_row_for_a_year_not_served_is_refused_by_its_own_check(self) -> None:
        with pytest.raises(TypeError, match="not served"):
            MOD["leaders"](copy.deepcopy(BODY), _unserved())

    @pytest.mark.parametrize("name", SHAPE_DEFECTS)
    def test_no_n1_defect_reaches_the_page(self, name: str) -> None:
        """The page's success marker and T1 always render; C2's section is whole (a
        key the section never reads) or shows only its own sentence."""
        tree = render_c2(SHAPE_DEFECTS[name])
        assert tree.id == PAGE_ID
        assert shown_years(tree) == YEARS
        whole = find(tree, C2) is not None and find(tree, LEADERS) is not None
        degraded = find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None
        assert whole != degraded, name
        if degraded:
            assert find(tree, C2) is None and find(tree, LEADERS) is None

    def test_the_shape_defects_reach_the_table_s_own_reads(self) -> None:
        """Non-vacuity: the cases include the two the table alone reads (#487, cr.1)."""
        for name in (
            "data[0].candidate_slug deleted",
            "meta.provenance.coverage deleted",
        ):
            tree = render_c2(SHAPE_DEFECTS[name])
            assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None, name

    @pytest.mark.parametrize("name", MALFORMED)
    def test_a_malformed_body_is_refused(self, name: str) -> None:
        with pytest.raises((TypeError, KeyError)):
            MOD["leaders"](copy.deepcopy(BODY), copy.deepcopy(MALFORMED[name]))

    def test_the_recording_is_accepted(self) -> None:
        leaders = MOD["leaders"](copy.deepcopy(BODY), copy.deepcopy(SUMMARY))
        assert [r["year"] for r in leaders] == YEARS
        assert all(r["electoral_rank"] == 1 for r in leaders)
        assert leaders[0]["ec_determinative"] is False

    def test_an_index_year_outside_its_span_is_refused(self) -> None:
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"]["year_max"] = 2020
        with pytest.raises(TypeError):
            MOD["leaders"](index, copy.deepcopy(SUMMARY))

    @pytest.mark.parametrize("name", MALFORMED)
    def test_a_malformed_body_degrades_only_the_section(self, name: str) -> None:
        tree = render_c2(MALFORMED[name])
        assert tree.id == PAGE_ID  # the page's success marker: T1 rendered
        assert shown_years(tree) == YEARS
        assert find(tree, C2) is None and find(tree, LEADERS) is None
        unavailable = find(tree, MOD["LEADER_UNAVAILABLE_ID"])
        assert unavailable.children == MOD["C2_UNAVAILABLE"]
        assert components.UNAVAILABLE_MESSAGE not in texts(tree)
        assert "isn't responding" not in MOD["C2_UNAVAILABLE"]


class TestC2Degraded:
    def test_an_unavailable_n1_leaves_t1_and_retries_once_per_render(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def down(path: str) -> api.Response:
            raise api.ApiUnavailable("down")

        calls, bucket = n1_client(monkeypatch, down)
        for search in ("", "?year_from=1900"):
            calls.clear()
            response = route("/elections", search)
            ids = routed_ids(response)
            assert PAGE_ID in ids and TABLE_ID in ids
            assert MOD["LEADER_UNAVAILABLE_ID"] in ids
            assert C2 not in ids and LEADERS not in ids
            # At most one fill per render, of N1 only (D096).
            assert calls == [api.SUMMARY_PATH], search

    def test_a_malformed_n1_from_the_api_leaves_t1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        n1_client(
            monkeypatch,
            lambda path: api.Response(body=_second_leader(), version=VERSION),
        )
        tree = PAGE["layout"]()
        assert tree.id == PAGE_ID
        assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None
        assert find(tree, C2) is None

    def test_the_index_down_degrades_the_whole_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        tree = PAGE["layout"]()
        assert components.UNAVAILABLE_MESSAGE in texts(tree)
        assert find(tree, C2) is None and find(tree, PAGE_ID) is None
        assert MOD["FILTER_SENTENCE"] not in texts(tree)
        assert MOD["LEDE"] in texts(tree)


class TestN1Fixture:
    """The N1 recording agrees with the per-year recordings of the same snapshot."""

    def test_same_snapshot_as_the_index(self) -> None:
        assert SUMMARY["meta"]["provenance"] == BODY["meta"]["provenance"]

    @pytest.mark.parametrize("year", RECONCILED)
    def test_each_recorded_year_matches(self, year: int) -> None:
        body = RECORDED[f"/v1/elections/{year}"]
        (item,) = [e for e in SUMMARY["elections"] if e["year"] == year]
        assert item == body["election"]
        rows = [r for r in SUMMARY["data"] if r["year"] == year]

        def key(r: dict[str, Any]) -> tuple[int, str]:
            return r["electoral_rank"], r["candidate_slug"]

        # Order-insensitive: the year recordings predate 0.8.0's order within ties, and
        # this checks content; C2 reads only each year's rank-1 row.
        assert sorted(rows, key=key) == sorted(body["summary"], key=key)


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


def _shown_pairs(tree: Any, field: str) -> list[tuple[int, Any]]:
    return [(year, ITEMS[year][field]) for year in sorted(set(shown_years(tree)))]


class TestMetrics:
    @pytest.mark.parametrize("name", list(CASES))
    def test_each_mean_equals_its_literal(self, name: str) -> None:
        query, *expected = CASES[name]
        tree = render_c2(query=query)
        for key, want in zip(MOD["MEANS"], expected, strict=True):
            field = metrics.METRICS[key].source.field
            mean = metrics.mean(_shown_pairs(tree, field))
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
        tree = render_c2(query=CASES[name][0])
        shown = len(rows(tree))
        assert metric_text(tree, "elections_shown") == (
            f"Showing {shown} of {len(YEARS)} elections"
        )

    def test_an_empty_selection_shows_no_zero_and_no_nan(self) -> None:
        tree = render_c2(query=CASES["an empty selection"][0])
        assert rows(tree) == []
        for key in MOD["MEANS"]:
            text = metric_text(tree, key)
            assert not any(ch.isdigit() for ch in text) and "nan" not in text.lower()

    def test_both_averages_name_their_own_elections_and_years_side_by_side(
        self,
    ) -> None:
        """The default view is the mismatched case: the two Ns and windows both show,
        in one list, and a note says the two do not cover the same elections."""
        tree = render_c2()
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
        assert notes_of(render_c2(query=CASES[name][0])) == [labels.MARGIN_NOTE]

    def test_the_hint_shows_only_while_the_popular_vote_filter_is_off(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] == 2024:
                item["pv_margin"] = None
        tree = render_c2(summary, query={"pv": "1"})
        assert metric_text(tree, "pv_margin_mean").endswith(
            "over 12 elections (1976–2020)"
        )
        assert notes_of(tree) == [
            labels.MARGIN_NOTE,
            "The two averages do not cover the same elections: this dataset's "
            "popular-vote figures cover 1976–2024.",
        ]

    def test_a_single_year_reconciles_to_its_served_margin(self) -> None:
        """Wherever a served figure exists, the metric reconciles to it: an average
        over one election shows that year's panel margin cell exactly (a precision pin:
        a mean of one value is that value)."""
        tree = render_c2(query=CASES["a single year"][0])
        for key in MOD["MEANS"]:
            dd = find(tree, METRIC_IDS[key])
            value, rest = (span.children for span in of_type(dd, "Span"))
            field = metrics.METRICS[key].source.field
            assert value == labels.margin(ITEMS[2000][field], True)
            assert rest == ", over 1 election (2000)"

    def test_the_metric_table_drives_what_is_averaged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuity of the source check: the page reads each mean's field from
        ``metrics.METRICS``, so pointing a row at another field changes the figure."""
        monkeypatch.setitem(
            metrics.METRICS,
            "ec_margin_mean",
            metrics.Metric("mean", metrics.Source("ElectionSummary", "hybrid_margin")),
        )
        tree = render_c2(query={"pv": "1"})
        assert metric_text(tree, "ec_margin_mean") == (
            "19.4 percentage points, over 13 elections (1976–2024)"
        )

    def test_a_year_listed_twice_counts_once_in_an_average(self) -> None:
        index = copy.deepcopy(BODY)
        index["data"].append(next(r for r in index["data"] if r["year"] == 2000))
        tree = render_c2(index=index, query=CASES["a single year"][0])
        assert metric_text(tree, "elections_shown") == "Showing 2 of 52 elections"
        assert metric_text(tree, "ec_margin_mean").endswith(", over 1 election (2000)")

    def test_an_unrecognized_margin_reads_so_and_names_no_n(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] == 2000:
                item["ec_margin"] = "x"
        tree = render_c2(summary)
        dd = find(tree, METRIC_IDS["ec_margin_mean"])
        assert dd.children == labels.UNRECOGNIZED
        assert dd.title == labels.UNRECOGNIZED_NOTE
        assert metric_text(tree, "pv_margin_mean").startswith("5.7 percentage points")
        assert notes_of(tree) == [labels.MARGIN_NOTE]

    def test_metrics_render_only_inside_the_list_of_elections(self) -> None:
        tree = render_c2()
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
    def test_an_item_level_defect_degrades_the_averages_and_c2(
        self, name: str, summary: Any
    ) -> None:
        if name == "an elections item for a year not served":
            summary = copy.deepcopy(SUMMARY)
            summary["elections"].append({**summary["elections"][0], "year": 1826})
        if name == "an item with no ec_margin":
            summary = copy.deepcopy(SUMMARY)
            del summary["elections"][3]["ec_margin"]
        tree = render_c2(summary)
        assert find(tree, MOD["METRICS_UNAVAILABLE_ID"]) is not None, name
        assert find(tree, METRIC_IDS["elections_shown"]) is not None
        assert shown_years(tree) == YEARS
        if name != "an item with no ec_margin":  # C2 reads no margin
            assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None, name

    def test_a_rank_level_defect_leaves_the_averages(self) -> None:
        """A tie at rank 1 is valid API data (D094(iv)) that C2 refuses by design; the
        averages read no ``data`` row, so they still show."""
        tree = render_c2(_second_leader())
        assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None
        assert find(tree, MOD["METRICS_UNAVAILABLE_ID"]) is None
        assert metric_text(tree, "ec_margin_mean").startswith("41.2 percentage points")

    def test_a_malformed_popular_vote_window_degrades_only_the_averages(self) -> None:
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"]["pv_year_min"] = True
        tree = render_c2(index=index)
        assert find(tree, MOD["METRICS_UNAVAILABLE_ID"]) is not None
        assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is None
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
        assert len(bucket.waits) == 1  # N1's one fill, before the filter changes

    @pytest.mark.parametrize("query", SHARED)
    def test_og_url_reopens_the_same_figures(self, query: str) -> None:
        resolution = appmod.resolve("/elections", query, None)
        assert resolution.og_url is not None
        normal = urllib.parse.urlsplit(resolution.og_url).query
        raw, reopened = (render_c2(query=parse(q)) for q in (query, normal))
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
        items = MOD["n1_items"](copy.deepcopy(BODY), copy.deepcopy(SUMMARY))
        assert sorted(items) == YEARS
        assert items[2000]["ec_margin"] == ITEMS[2000]["ec_margin"]

    @pytest.mark.parametrize(
        "name", ["a served year with no elections item", "two items for one year"]
    )
    def test_an_item_defect_is_refused(self, name: str) -> None:
        summary = _without(1876) if name.startswith("a served") else _second_item()
        with pytest.raises(TypeError):
            MOD["n1_items"](copy.deepcopy(BODY), summary)

    def test_it_reads_no_data_row(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        summary["data"] = "not a list"
        assert sorted(MOD["n1_items"](copy.deepcopy(BODY), summary)) == YEARS
