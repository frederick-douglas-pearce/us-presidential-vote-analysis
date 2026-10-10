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

from explore import api, components, labels
from explore import app as appmod
from tests.unit.test_dashboard_app import (
    META,
    RECORDED,
    VERSION,
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

    def test_an_unexpected_has_popular_vote_renders_as_text_not_a_claim(self) -> None:
        assert labels.has_popular_vote(None) == "None"
        assert labels.has_popular_vote(0) == "0"
        # Truthy non-bools too: only True itself may claim the dataset holds it.
        assert labels.has_popular_vote(1) == "1"
        assert labels.has_popular_vote("false") == "false"


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
        assert routed_years(route("/elections", written)) == [
            y for y in PV_YEARS if y >= 1900
        ]
        assert calls == [] and bucket.waits == []

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
        for years, pv in (([1900, LAST], ["1"]), ([FIRST, 1950], [])):
            MOD["on_filter_change"](years, pv, FIRST, LAST, "")
        assert calls == []
        assert bucket.waits == []

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
        assert calls == []  # the new body came with the swap, not a fill on a miss


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
        assert labels.LABELS["candidate_count"] == "Candidates"
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

SHARED_MODULES = ("components.py", "export.py", "labels.py", "query.py")

#: The shared modules by import name: the only ``explore`` modules a shared module may
#: import (#309: the shared table component builds on ``labels`` and ``export``).
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
        assert graph["components"] == {"export", "labels"}  # non-vacuity
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

    @pytest.mark.parametrize("module", sorted(dash.page_registry))
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


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path"] == "/elections"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    assert PAGE["on_miss"] == ()
    assert PAGE["success"] == PAGE_ID
    assert VERSION  # the recorded snapshot every cached render answers from
