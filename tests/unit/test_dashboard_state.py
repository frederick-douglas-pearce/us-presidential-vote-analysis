"""The state history, charts C7 and C10 and the table they share, and the state
picker (#279), and the state's people per electoral vote page, T7 (#280; its own page
since #559), with the section links between a state's three pages (#559, #619; D105,
D118). T4, the state's results by election, is a page of its own since #619, tested in
``test_dashboard_state_results.py``, which imports this module's shared helpers.

Offline, against the recorded ``/v1/states/GA`` and ``/v1/states/TX`` (C7 and C10
run over both, #575) and the roster ``/v1/elections/2024``,
and ``/v1/states/GA/per-capita`` and ``/v1/states/TX/per-capita``
(the same snapshot as every other fixture, ``test_every_recorded_response_is_one_
snapshot``), through the helpers and the autouse offline process client of
``test_dashboard_app.py``. The registry-wide checks there pick the pages up
(``TestRegistryCoverage``, ``TestValidateBeforeFill`` with ``ZZ`` as the unserved code,
``TestRegistryContracts``), and the D070(b) guard renders ``/state/GA``,
``/state/GA/elections``, ``/state/GA/per-capita``, ``/states``, ``/state/ZZ``,
``/state/ZZ/elections`` and ``/state/ZZ/per-capita``. These tests cover what is
particular to the pages.
"""

from __future__ import annotations

import ast
import copy
import inspect
import random
import re
from collections.abc import Callable
from typing import Any, NamedTuple

import dash
import pytest
from dash import no_update

from explore import (
    api,
    charts,
    components,
    election_view,
    export,
    labels,
    over_time,
    query,
    state_view,
)
from explore import app as appmod
from tests.dashboard_cards import card_children, cards, every_card, in_one_card
from tests.unit.test_dashboard_app import (
    RECORDED,
    VERSION,
    FakeClock,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    component_ids,
    failing_fetch,
    fake_fetch,
    get,
    offline_client,
    route,
    routed_ids,
    texts,
    url,
)
from tests.unit.test_dashboard_elections import (
    caption_text,
    classed,
    find,
    of_type,
    parse,
)
from tests.unit.test_dashboard_export import SERVED_KINDS, body_rows, download

PAGE: dict[str, Any] = dash.page_registry["pages.state"]
#: The page module's namespace, reached through its layout (Dash loads it by path).
MOD: dict[str, Any] = PAGE["layout"].__globals__
PICKER: dict[str, Any] = dash.page_registry["pages.states"]
PICKER_MOD: dict[str, Any] = PICKER["layout"].__globals__
PC_PAGE: dict[str, Any] = dash.page_registry["pages.state_per_capita"]
PC_MOD: dict[str, Any] = PC_PAGE["layout"].__globals__

INDEX: dict[str, Any] = RECORDED[api.ELECTIONS_PATH]
ROSTER_PATH = "/v1/elections/2024"
ROSTER: dict[str, Any] = RECORDED[ROSTER_PATH]
GA_PATH = "/v1/states/GA"
GA_PER_CAPITA_PATH = "/v1/states/GA/per-capita"
PAGE_ID = MOD["PAGE_ID"]
#: The results page (#619), read through the registry: importing its test module here
#: would collect its tests twice, and it imports this one.
RS_PAGE: dict[str, Any] = dash.page_registry["pages.state_results"]
RS_MOD: dict[str, Any] = RS_PAGE["layout"].__globals__
RS_PAGE_ID = RS_MOD["PAGE_ID"]
#: T4, on the results page since #619.
RESULTS = RS_MOD["TABLE_ID"]
PC_PAGE_ID = PC_MOD["PAGE_ID"]
PER_CAPITA = PC_MOD["PER_CAPITA_TABLE_ID"]


def ga_body() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[GA_PATH])


def ga_per_capita() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[GA_PER_CAPITA_PATH])


def render_all(
    query: str = "", *, body: Any = None, index: Any = None, usps: str = "GA"
) -> tuple[Any, Any, bool]:
    """``render``'s three values for ``query`` (#620, D119): the history page's body,
    the state's name as served and whether the Years slider rendered, for ``usps``'s
    recorded history unless ``body`` is given, the query read by the page's own
    parser, as the layout reads it."""
    content, name, filtered = MOD["render"](
        copy.deepcopy(RECORDED[f"/v1/states/{usps}"]) if body is None else body,
        copy.deepcopy(INDEX) if index is None else index,
        usps,
        MOD["parse_filters"](parse(query)),
    )
    return content, name, filtered


def render(
    query: str = "", *, body: Any = None, index: Any = None, usps: str = "GA"
) -> Any:
    """The history page's body for ``query`` (its one filter, the year range, #620,
    D119), as the layout builds it: ``usps``'s recorded history unless ``body`` is
    given."""
    return render_all(query, body=body, index=index, usps=usps)[0]


def serve_history(monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]) -> None:
    """A process client serving the recordings with ``body`` as Georgia's history,
    the index and the roster cached."""
    fetch, _ = fake_fetch({**RECORDED, GA_PATH: body})
    client = offline_client(
        fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, ROSTER_PATH]
    )
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    monkeypatch.setattr(api, "CLIENT", client)


def history_layout(query: str = "", usps: str = "GA") -> Any:
    """The history page's body through its layout, as the router calls it with the
    query's keys as keyword arguments; the caller installs the process client."""
    _, _, content = MOD["layout"](usps=usps, **parse(query)).children
    return content


def pc_render(
    query: str = "", per_capita: Any = None, index: Any = None, usps: str = "GA"
) -> Any:
    """The per-capita page's body for ``query``, as the layout builds it."""
    content, _ = PC_MOD["render"](
        (
            copy.deepcopy(RECORDED[f"/v1/states/{usps}/per-capita"])
            if per_capita is None
            else per_capita
        ),
        copy.deepcopy(INDEX) if index is None else index,
        usps,
        PC_MOD["parse_filters"](parse(query)),
    )
    return content


# --- registration and validation ------------------------------------------------------


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path_template"] == "/state/<usps>"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    # The history page no longer fills T7's path (#559).
    assert PAGE["on_miss"] == (api.ROSTER_PATH, "/v1/states/{usps}")
    assert PAGE["success"] == PAGE_ID
    # The registered judge is the one the layout calls, so the index's 404 and the
    # page's not-found state decide alike.
    assert PAGE["validate"] is MOD["VALIDATE"]
    assert PAGE["validate"] == (api.ROSTER_PATH, state_view.on_roster)
    assert PAGE.get("order") is None
    # Its one filter is the year range (#620, D119), read by its own parser; T4's two
    # keys moved with it to the results page (D118), so an old link naming either
    # answers 302 there; the year range is not moved.
    assert PAGE["query"] is MOD["parse_filters"]
    assert PAGE["moved"] == (("candidate", "pv_status"), "/state/<usps>/elections")
    assert PAGE["moved"] == (
        state_view.MOVED_KEYS,
        state_view.template(state_view.RESULTS),
    )
    # New ids (D097(g)): T4's retired ones are never reused, here or on the results
    # page, whose ids are its own.
    assert (MOD["YEARS_ID"], MOD["URL_ID"], MOD["NO_MATCH_ID"]) == (
        "state-history-years",
        "state-history-url",
        "state-history-no-match",
    )
    assert MOD["METRICS_ALL_YEARS_ID"] == "state-history-metrics-all-years"
    retired = {"state-history", "state-url", "state-years", "state-candidate"}
    assert not retired & {MOD["YEARS_ID"], MOD["URL_ID"], MOD["NO_MATCH_ID"]}
    assert MOD["URL_ID"] not in (RS_MOD["URL_ID"], PC_MOD["URL_ID"])
    assert MOD["YEARS_ID"] not in (RS_MOD["YEARS_ID"], PC_MOD["YEARS_ID"])
    for name in ("TABLE_ID", "HISTORY_TABLE_HEADING"):
        assert name not in MOD, name
    assert not hasattr(labels, "C7_FILTERS_NOTE")
    # The four first-election notes are retired (#620): the axis no longer starts
    # before the state's first election.
    for retired_note in (
        "FIRST_ELECTION_NOTE",
        "FIRST_ELECTION_NOTE_THIS_STATE",
        "C10_FIRST_ELECTION_NOTE",
        "C10_FIRST_ELECTION_NOTE_THIS_STATE",
    ):
        assert not hasattr(labels, retired_note), retired_note


@pytest.mark.parametrize(
    ("params", "pairs"),
    [
        (
            {"year_from": "1900", "year_to": "1990"},
            [("year_from", "1900"), ("year_to", "1990")],
        ),
        # T4's moved keys, the path variable and anything else are dropped (D118).
        (
            {
                "candidate": "andrew-jackson",
                "pv_status": "popular_vote",
                "usps": "TX",
                "state": "TX",
                "junk": "1",
                "year_to": "1900",
            },
            [("year_to", "1900")],
        ),
        ({"candidate": "andrew-jackson"}, []),
        # An inverted pair drops both bounds, as on every year-filtered page.
        ({"year_from": "1990", "year_to": "1900"}, []),
        ([("year_from", "1900")], []),
        (None, []),
    ],
    ids=repr,
)
def test_the_history_parser_keeps_only_the_year_range(params: Any, pairs: Any) -> None:
    """#620 (D119): the history page's one filter, syntactic, as the per-capita
    page's parser reads it."""
    assert MOD["parse_filters"](params) == pairs
    if isinstance(params, dict):
        assert MOD["parse_filters"](params) == PC_MOD["parse_filters"](params)


class TestFirstElection:
    """The state's first election (#620, D119; in ``state_view`` since #621, D120): the
    first year of C7's collapse whose allotment is an ``int`` above 0, never a
    ``bool``; ``None`` where none is."""

    @staticmethod
    def records(*pairs: tuple[int, Any]) -> list[dict[str, Any]]:
        return [{"year": y, "state_electoral_votes": v} for y, v in pairs]

    def test_the_first_year_with_an_int_above_0(self) -> None:
        first = state_view.first_election
        assert first(self.records((1824, 0), (1828, 0), (1832, 5))) == 1832
        assert first(self.records((1832, 5), (1828, 3))) == 1828

    @pytest.mark.parametrize(
        "value", [True, False, 0, -1, None, 1.0, "5", float("nan")], ids=repr
    )
    def test_nothing_but_an_int_above_0_counts(self, value: Any) -> None:
        first = state_view.first_election
        assert first(self.records((1824, value), (1828, 7))) == 1828
        assert first(self.records((1824, value))) is None

    def test_none_where_there_is_none(self) -> None:
        assert state_view.first_election([]) is None
        assert state_view.first_election(self.records((1864, 0), (1868, 0))) is None

    @pytest.mark.parametrize("usps", ["GA", "TX"])
    def test_on_each_recorded_state(self, usps: str) -> None:
        path = f"/v1/states/{usps}"
        served = set(state_view.served_years(INDEX))
        records = state_view.electors(
            state_view.rows(copy.deepcopy(RECORDED[path]), usps, served, path),
            served,
            usps,
            path,
        )
        assert state_view.first_election(records) == {"GA": 1824, "TX": 1848}[usps]


def test_the_per_capita_page_is_registered_as_planned() -> None:
    assert PC_PAGE["path_template"] == "/state/<usps>/per-capita"
    # Ahead of the history page's greedy <usps> (#559, as D092 ordered the election
    # subpages); test_every_page_s_path_routes_to_that_page checks the routing.
    assert PC_PAGE["order"] == 0
    assert PC_PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    assert PC_PAGE["on_miss"] == (api.ROSTER_PATH, "/v1/states/{usps}/per-capita")
    assert PC_PAGE["success"] == PC_PAGE_ID
    # The same judge as the history page, so both decide a code alike.
    assert PC_PAGE["validate"] is PC_MOD["VALIDATE"]
    assert PC_PAGE["validate"] == PAGE["validate"]
    assert PC_PAGE["query"] is PC_MOD["parse_filters"]
    assert PC_PAGE["nav"] == PAGE["nav"] == "states"
    assert PC_MOD["NOT_FOUND"] == MOD["NOT_FOUND"]
    # Its own ids: Dash keys callbacks by output, app-wide (the results page's are
    # pinned in test_dashboard_state_results.py).
    assert PC_MOD["URL_ID"] != RS_MOD["URL_ID"]
    assert PC_MOD["YEARS_ID"] != RS_MOD["YEARS_ID"]


@pytest.mark.parametrize(
    "params",
    [
        {"candidate": "abraham-lincoln", "pv_status": "popular_vote"},
        {"usps": "TX", "state": "TX", "junk": "1"},
    ],
    ids=repr,
)
def test_the_per_capita_parser_keeps_only_the_year_range(
    params: dict[str, str],
) -> None:
    assert PC_MOD["parse_filters"]({**params, "year_from": "1860"}) == [
        ("year_from", "1860")
    ]


def test_the_picker_is_registered_as_planned() -> None:
    assert PICKER["path"] == "/states"
    assert PICKER["prefetch"] == (api.ELECTIONS_PATH,)
    # N2 since #641 (D123, amending D107), filled on a miss: D072's prefetch unchanged.
    assert PICKER["on_miss"] == (api.ROSTER_PATH, api.ELECTION_STATES_PATH)
    assert PICKER["success"] == PICKER_MOD["PAGE_ID"]


def test_the_picker_reads_the_roster_through_state_view() -> None:
    """One reading of the roster (#279, moved by #559): the picker calls
    ``state_view.roster`` and parses no row of its own."""
    assert PICKER_MOD["state_view"] is state_view
    assert "roster" not in vars(api)
    tree = ast.parse(inspect.getsource(PICKER_MOD["roster"]))
    calls = {
        ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert "state_view.roster" in calls
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.comprehension))]


def test_the_roster_is_the_latest_served_election() -> None:
    # Resolved from the index (never a literal), and every state and DC takes part.
    assert api.ROSTER_PATH.format(**api.coverage_vars(INDEX)) == ROSTER_PATH
    assert len({row["state_usps"] for row in ROSTER["data"]}) == 51


class TestOnRoster:
    def test_every_state_and_dc_in_the_roster_is_accepted(self) -> None:
        judge = state_view.on_roster
        codes = {row["state_usps"] for row in ROSTER["data"]}
        assert "DC" in codes
        for usps in codes:
            assert judge({"usps": usps}, ROSTER) is True, usps

    @pytest.mark.parametrize(
        "usps",
        ["ZZ", "ga", "Ga", "GAA", "G", "", None, ["GA"], 1, "G1", "ＧＡ", " GA"],
    )
    def test_anything_else_is_refused(self, usps: Any) -> None:
        assert state_view.on_roster({"usps": usps}, ROSTER) is False

    @pytest.mark.parametrize(
        "body", [{}, [], None, "GA", {"data": "GA"}, {"data": [1]}, {"data": []}]
    )
    def test_a_malformed_roster_names_no_state(self, body: Any) -> None:
        assert state_view.on_roster({"usps": "GA"}, body) is False

    @pytest.mark.parametrize("position", [0, 50, -1])
    @pytest.mark.parametrize(
        "change",
        [
            {"year": 1824},
            {"year": "2024"},
            {"state_usps": "ga"},
            # Too long: a prefix match would take it; the code must be the whole value.
            {"state_usps": "GAA"},
            {"state": None},
        ],
        ids=repr,
    )
    def test_a_roster_the_picker_would_refuse_names_no_state(
        self, position: int, change: dict[str, Any]
    ) -> None:
        # Both refuse alike (one reading, state_view.roster, which
        # test_the_picker_reads_the_roster_through_state_view pins): a row of another
        # year, a malformed code or a missing name refuses every code, GA included.
        body = copy.deepcopy(ROSTER)
        body["data"][position].update(change)
        assert state_view.on_roster({"usps": "GA"}, body) is False
        with pytest.raises(TypeError):
            PICKER_MOD["roster"](body, 2024)

    @pytest.mark.parametrize("year", [2020, 1824])
    def test_a_roster_whose_rows_all_name_another_year_names_no_state(
        self, year: int
    ) -> None:
        # Consistent rows, so state_view.roster reads it; but not the latest election, which
        # the judge checks against the roster's own coverage and the picker against
        # the year it read the roster for.
        body = copy.deepcopy(ROSTER)
        for row in body["data"]:
            row["year"] = year
        assert state_view.on_roster({"usps": "GA"}, body) is False
        with pytest.raises(TypeError):
            PICKER_MOD["roster"](body, 2024)

    @pytest.mark.parametrize("coverage", [{}, {"year_max": "2024"}, {"year_max": None}])
    def test_a_roster_with_no_checked_latest_year_names_no_state(
        self, coverage: dict[str, Any]
    ) -> None:
        body = copy.deepcopy(ROSTER)
        body["meta"]["provenance"]["coverage"] = coverage
        assert state_view.on_roster({"usps": "GA"}, body) is False


# --- the Georgia acceptance criterion ------------------------------------------------


class TestGeorgia:
    """The history page's heading and what it does not show (#279, #559, #619)."""

    def test_the_heading_names_the_state_from_the_rows(self) -> None:
        _, name, filtered = MOD["render"](ga_body(), copy.deepcopy(INDEX), "GA")
        assert name == "Georgia"
        assert filtered is True

    @pytest.mark.parametrize("name", ["", "  ", "\u200b"], ids=repr)
    def test_a_name_with_nothing_in_it_keeps_the_generic_heading(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        body = ga_body()
        for row in body["data"]:
            row["state"] = name
        fetch, _ = fake_fetch({**RECORDED, GA_PATH: body})
        client = offline_client(
            fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, ROSTER_PATH]
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        heading, _, content = MOD["layout"](usps="GA").children
        assert heading.children == "State history"
        assert content.id == PAGE_ID

    def test_the_history_page_shows_no_t7(self) -> None:
        tree = render()
        assert find(tree, PER_CAPITA) is None
        assert "People per electoral vote" not in [
            h.children for h in of_type(tree, "H2")
        ]

    def test_the_history_page_shows_no_t4_and_one_year_filter(self) -> None:
        """T4 and its filters left with #619 (D118): no T4, no dropdown and none of
        T4's retired ids. Since #620 (D119) its one filter is the Years slider, over
        the state's span, with its own page-local Location; no popular-vote checkbox
        (the owner's ruling at #620's plan gate)."""
        tree = render()
        assert find(tree, RESULTS) is None
        (slider,) = of_type(tree, "RangeSlider")
        assert slider.id == MOD["YEARS_ID"]
        assert (slider.min, slider.max) == (1824, 2024)
        (location,) = of_type(tree, "Location")
        assert location.id == MOD["URL_ID"]
        assert location.refresh == "callback-nav"
        assert of_type(tree, "Dropdown") == []
        assert of_type(tree, "Checklist") == []
        (own,) = classed(tree, "filter")
        assert find(own, MOD["YEARS_ID"]) is slider
        assert not {
            "state-history",
            "state-url",
            "state-years",
            "state-candidate",
            "state-pv-status",
        } & component_ids(tree)


# --- malformed bodies degrade --------------------------------------------------------


def mutated(index: int, **change: Any) -> dict[str, Any]:
    body = ga_body()
    body["data"][index].update(change)
    return body


@pytest.mark.parametrize("position", [0, 60, -1])  # first, middle and last rows
@pytest.mark.parametrize(
    "change",
    [
        {"state_usps": "AL"},
        {"state_usps": None},
        {"year": 1826},  # four digits, not a served year
        {"year": "1868"},
        {"year": True},
        {"year": 1868.0},
        {"year": None},
    ],
    ids=repr,
)
def test_a_row_of_another_state_or_no_served_year_is_malformed(
    position: int, change: dict[str, Any]
) -> None:
    # Matched, so the check under test raises, not a later comparison of the rows.
    with pytest.raises(TypeError, match="another state|no served year"):
        render(body=mutated(position, **change))


@pytest.mark.parametrize("data", [[], None, {}, "rows", [1]])
def test_a_body_with_no_rows_is_malformed(data: Any) -> None:
    body = ga_body()
    body["data"] = data
    with pytest.raises(TypeError):
        render(body=body)


def test_an_index_serving_no_year_is_malformed() -> None:
    index = copy.deepcopy(INDEX)
    index["data"] = [{"year": "1868"}]
    with pytest.raises(TypeError, match="serves no year"):
        render(index=index)


def test_the_one_election_view_links_each_state_to_its_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2 on the election's states page and T6 on its per-capita page (#465)."""
    states = dash.page_registry["pages.election_states"]["layout"].__globals__
    per_capita_page = dash.page_registry["pages.election_per_capita"]["layout"]
    per_capita_mod = per_capita_page.__globals__
    body = copy.deepcopy(RECORDED["/v1/elections/1868"])
    per_capita = copy.deepcopy(RECORDED["/v1/elections/1868/per-capita"])
    index_row = election_view.index_row(INDEX, "1868")
    around = election_view.neighbours(INDEX, 1868)
    for tree, table, rows in (
        (
            states["render"](body, index_row, [], around),
            states["STATES_TABLE_ID"],
            body["data"],
        ),
        (
            per_capita_mod["render"](per_capita, index_row, [], around),
            per_capita_mod["PER_CAPITA_TABLE_ID"],
            per_capita["data"],
        ),
    ):
        hrefs = {
            link.href
            for link in of_type(find(tree, table), "Link")
            if link.href.startswith("/state/")
        }
        assert "/state/GA" in hrefs
        assert hrefs == {f"/state/{r['state_usps']}" for r in rows}


@pytest.mark.parametrize("usps", ["ga", "G A", None, "../x", "<b>"])
def test_a_state_code_that_is_not_one_is_text_not_a_link(usps: Any) -> None:
    states = dash.page_registry["pages.election_states"]["layout"].__globals__
    body = copy.deepcopy(RECORDED["/v1/elections/1868"])
    body["data"] = [r for r in body["data"] if r["state_usps"] == "GA"]
    for row in body["data"]:
        row["state_usps"] = usps
    tree = states["render"](
        body,
        election_view.index_row(INDEX, "1868"),
        [],
        election_view.neighbours(INDEX, 1868),
    )
    links = of_type(find(tree, states["STATES_TABLE_ID"]), "Link")
    assert [link.href for link in links if link.href.startswith("/state/")] == []


# --- validation at the index and at render, and the request budget -------------------


class TestRoster:
    def test_a_served_state_renders_with_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The state's rows only: T7's path is the per-capita page's (#559)."""
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        assert PAGE_ID in routed_ids(route("/state/GA"))
        assert calls == [GA_PATH]
        assert len(bucket.waits) == 1
        calls.clear()
        assert PAGE_ID in routed_ids(route("/state/GA"))  # cached: none
        assert calls == []

    def test_the_per_capita_page_renders_with_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T7's rows only, never the history's (#559)."""
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route("/state/GA/per-capita"))
        assert PC_PAGE_ID in ids and PER_CAPITA in ids
        assert PAGE_ID not in ids and RESULTS not in ids
        assert calls == [GA_PER_CAPITA_PATH]
        assert len(bucket.waits) == 1
        calls.clear()
        assert PC_PAGE_ID in routed_ids(route("/state/GA/per-capita"))
        assert calls == []

    def test_the_per_capita_page_s_filter_changes_make_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        route("/state/GA/per-capita")
        calls.clear()
        for search in ("?year_from=1860", "?year_to=1900", ""):
            assert PC_PAGE_ID in routed_ids(route("/state/GA/per-capita", search))
        PC_MOD["on_filter_change"]([1860, 2024], 1824, 2024, "")
        assert calls == []

    @pytest.mark.parametrize("path", ["/state/ZZ/per-capita", "/state/QQ/per-capita"])
    def test_an_unserved_code_on_the_per_capita_page_is_not_found_and_fills_nothing(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route(path))
        assert PC_MOD["NOT_FOUND_ID"] in ids
        assert PC_PAGE_ID not in ids and "unavailable" not in ids
        assert calls == [] and bucket.waits == []

    @pytest.mark.parametrize(
        "path",
        ["/state/GA/x", "/state/GA/per-capita/x", "/state/GA/elections/x"],
    )
    def test_an_unknown_section_reaches_the_history_page_and_is_not_found(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        # The history page's greedy <usps> takes "GA/x", which is no USPS code.
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route(path))
        assert MOD["NOT_FOUND_ID"] in ids
        assert PAGE_ID not in ids and PC_PAGE_ID not in ids and RS_PAGE_ID not in ids
        assert calls == []

    @pytest.mark.parametrize(
        "search", ["?year_from=1860", "?candidate=horatio-seymour", "?pv_status=x", ""]
    )
    def test_a_client_side_route_with_a_query_renders_the_history_with_no_request(
        self, monkeypatch: pytest.MonkeyPatch, search: str
    ) -> None:
        """A routing request never reaches the index, so a moved key is not
        redirected there (D092): the history renders, applies only the year range
        (#620, D119), makes no request, and shows no T4."""
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        route("/state/GA")
        calls.clear()
        ids = routed_ids(route("/state/GA", search))
        assert PAGE_ID in ids
        assert RS_PAGE_ID not in ids and RESULTS not in ids
        assert calls == []
        (slider,) = of_type(history_layout(search.lstrip("?")), "RangeSlider")
        expected = [1860, 2024] if search == "?year_from=1860" else [1824, 2024]
        assert slider.value == expected

    def test_an_unserved_code_is_not_found_and_fills_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route("/state/ZZ"))
        assert MOD["NOT_FOUND_ID"] in ids
        assert PAGE_ID not in ids
        assert "unavailable" not in ids
        assert calls == [] and bucket.waits == []

    def test_cold_an_unserved_code_costs_one_fill_of_the_roster_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The index is cached; the roster is not.
        _, calls, _ = cached_client(monkeypatch)
        assert MOD["NOT_FOUND_ID"] in routed_ids(route("/state/ZZ"))
        assert calls == [ROSTER_PATH]
        calls.clear()
        assert MOD["NOT_FOUND_ID"] in routed_ids(route("/state/QQ"))
        assert calls == []  # the roster is shared, and now cached

    def test_cold_a_served_state_fills_the_roster_then_its_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        assert PAGE_ID in routed_ids(route("/state/GA"))
        assert calls == [ROSTER_PATH, GA_PATH]

    def test_cold_the_per_capita_page_fills_the_roster_then_its_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        assert PC_PAGE_ID in routed_ids(route("/state/GA/per-capita"))
        assert calls == [ROSTER_PATH, GA_PER_CAPITA_PATH]

    def test_a_cold_second_fill_is_refused_when_too_little_time_is_left(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = FakeClock()
        calls: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls.append(path)
            if path == ROSTER_PATH:
                # The roster takes most of the render's deadline: under
                # MIN_USEFUL_FETCH_S remains for the state's own rows.
                clock.now += api.MAX_REQUEST_WAIT_S - api.MIN_USEFUL_FETCH_S / 2
            return api.Response(body=copy.deepcopy(RECORDED[path]), version=VERSION)

        client = offline_client(
            fetch,
            clock=clock,
            max_request_wait=api.MAX_REQUEST_WAIT_S,
            prefetch_paths=lambda: [api.ELECTIONS_PATH],
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        calls.clear()
        monkeypatch.setattr(api, "CLIENT", client)
        assert "unavailable" in routed_ids(route("/state/GA"))
        assert calls == [ROSTER_PATH]  # never started

    @pytest.mark.parametrize(
        "search",
        # 1860 is served (and recorded): a page reading a served year from the query
        # would fill it, and the call list would show it.
        ["?year_max=1825", "?year_max=2028&year_max=x", "?year_max=1860"],
    )
    def test_the_roster_year_is_never_read_from_the_query(
        self, monkeypatch: pytest.MonkeyPatch, search: str
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        assert PAGE_ID in routed_ids(route("/state/GA", search))
        assert PICKER["success"] in routed_ids(route("/states", search))
        assert calls == [ROSTER_PATH, GA_PATH, api.ELECTION_STATES_PATH]

    @pytest.mark.parametrize(
        "coverage",
        [
            {"year_max": 2028},
            {"year_max": 1860},  # served, but not the latest
            {"year_max": True},
            {"year_max": "2024"},
            {"year_max": 2024.0},
        ],
        ids=repr,
    )
    def test_an_index_naming_no_served_latest_year_degrades_and_fills_nothing(
        self, monkeypatch: pytest.MonkeyPatch, coverage: dict[str, Any]
    ) -> None:
        bodies = copy.deepcopy(RECORDED)
        bodies[api.ELECTIONS_PATH]["meta"]["provenance"]["coverage"].update(coverage)
        fetch, calls = fake_fetch(bodies)
        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        calls.clear()
        monkeypatch.setattr(api, "CLIENT", client)
        assert "unavailable" in routed_ids(route("/state/GA"))
        assert "unavailable" in routed_ids(route("/states"))
        assert calls == []


class TestMalformedBodies:
    @staticmethod
    def client_with(monkeypatch: pytest.MonkeyPatch, path: str) -> list[str]:
        bodies = copy.deepcopy(RECORDED)
        del bodies[path]["meta"]
        fetch, calls = fake_fetch(bodies)
        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        calls.clear()
        monkeypatch.setattr(api, "CLIENT", client)
        return calls

    def test_a_state_body_without_meta_degrades(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.client_with(monkeypatch, GA_PATH)
        ids = routed_ids(route("/state/GA"))
        assert "unavailable" in ids and PAGE_ID not in ids

    def test_a_roster_body_without_meta_degrades_the_picker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.client_with(monkeypatch, ROSTER_PATH)
        ids = routed_ids(route("/states"))
        assert "unavailable" in ids and PICKER["success"] not in ids


class TestLede:
    """The history page's lede shows on success and on the degraded state, and the
    not-found state shows none (#325). Its filter sentence follows the lede only where
    the Years slider renders (#620, D119): on success, not on the degraded or
    not-found state, nor where neither chart's collapse can be read; and no state of
    it shows another state page's sentence."""

    #: Every state page's filter sentence, and the word each one opens with.
    SENTENCES = (
        RS_MOD["FILTER_SENTENCE"],
        PC_MOD["FILTER_SENTENCE"],
        MOD["FILTER_SENTENCE"],
        "Narrow ",
    )

    def test_the_lede_and_filter_sentence_are_the_spec_s(self) -> None:
        # People per electoral vote left the lede with T7 (#559), and each
        # candidate's electoral votes with T4 (#619; ba spec, approved at its plan
        # gate, 2026-11-23); the filter sentence is #620's ba spec.
        assert MOD["LEDE"] == (
            "This state's electors appointed in every election this dataset holds for "
            "it, and its total popular vote where the dataset has it."
        )
        assert MOD["FILTER_SENTENCE"] == (
            "Narrow the charts and table to a range of years."
        )
        assert [k for k in MOD if k.startswith("FILTER_SENTENCE")] == [
            "FILTER_SENTENCE"
        ]

    def test_success_shows_the_lede_then_its_filter_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = route("/state/GA")
        assert PAGE_ID in routed_ids(response)
        body = response.get_data(as_text=True)
        assert f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}" in body
        for sentence in (RS_MOD["FILTER_SENTENCE"], PC_MOD["FILTER_SENTENCE"]):
            assert sentence not in body
        heading, lede, content = MOD["layout"](usps="GA").children
        assert lede.children == f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}"
        assert content.id == PAGE_ID

    def test_both_collapses_failed_shows_the_lede_alone_and_no_slider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """I2 (#620's architect review): two statuses in one year fail both
        collapses, so there is nothing to narrow: no slider and no filter sentence,
        while the page keeps its success marker."""
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["pv_status"] = "legislature_chosen"
        _, name, filtered = render_all(body=copy.deepcopy(body))
        assert (name, filtered) == ("Georgia", False)
        serve_history(monkeypatch, body)
        heading, lede, content = MOD["layout"](usps="GA").children
        assert content.id == PAGE_ID
        assert lede.children == MOD["LEDE"]
        assert of_type(content, "RangeSlider") == []
        # Even under a query: nothing to narrow, so the range shows nowhere.
        _, lede, content = MOD["layout"](usps="GA", year_from="1900").children
        assert lede.children == MOD["LEDE"]
        assert of_type(content, "RangeSlider") == []

    def test_the_degraded_state_shows_the_lede(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A malformed state body: render raises after validation, so the page degrades.
        TestMalformedBodies.client_with(monkeypatch, GA_PATH)
        response = route("/state/GA")
        ids = routed_ids(response)
        assert "unavailable" in ids and PAGE_ID not in ids
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] in body
        for sentence in self.SENTENCES:
            assert sentence not in body

    def test_the_unreachable_api_shows_the_lede(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = offline_client(failing_fetch, prefetch_paths=lambda: [])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        response = route("/state/GA")
        assert "unavailable" in routed_ids(response)
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] in body
        for sentence in self.SENTENCES:
            assert sentence not in body

    def test_the_not_found_state_shows_no_lede(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = route("/state/ZZ")
        assert MOD["NOT_FOUND_ID"] in routed_ids(response)
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] not in body
        for sentence in self.SENTENCES:
            assert sentence not in body


class TestPerCapitaLede:
    """The per-capita page's heading, lede and filter sentence, on the history page's
    rules (#392, #325), worded by #559's ba spec."""

    def test_the_wording_is_the_spec_s(self) -> None:
        assert PC_MOD["PER_CAPITA_HEADING"] == "{state}: people per electoral vote"
        assert PC_MOD["PER_CAPITA_GENERIC_HEADING"] == (
            "State: people per electoral vote"
        )
        assert f"{PC_MOD['LEDE']} {PC_MOD['FILTER_SENTENCE']}" == (
            "How many people this state's electoral votes stood for in every election "
            "this dataset holds for it: the state's population divided by its electors "
            "appointed. Narrow the table to a range of years."
        )

    def test_success_names_the_state_then_the_lede_and_its_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        page = PC_MOD["layout"](usps="GA")
        heading, lede, content = page.children
        assert heading.children == "Georgia: people per electoral vote"
        assert lede.children == f"{PC_MOD['LEDE']} {PC_MOD['FILTER_SENTENCE']}"
        assert content.id == PC_PAGE_ID

    def test_the_degraded_state_shows_the_generic_heading_and_no_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        TestMalformedBodies.client_with(monkeypatch, GA_PER_CAPITA_PATH)
        response = route("/state/GA/per-capita")
        ids = routed_ids(response)
        assert "unavailable" in ids and PC_PAGE_ID not in ids
        body = response.get_data(as_text=True)
        assert PC_MOD["PER_CAPITA_GENERIC_HEADING"] in body
        assert PC_MOD["LEDE"] in body
        assert PC_MOD["FILTER_SENTENCE"] not in body

    def test_the_not_found_state_shows_the_state_heading_and_no_lede(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        page = PC_MOD["layout"](usps="ZZ")
        heading, content = page.children
        assert heading.children == labels.STATE_NOT_FOUND_HEADING
        assert content.id == PC_MOD["NOT_FOUND_ID"]
        assert labels.STATE_NOT_FOUND_SENTENCE in texts(content)
        (link,) = of_type(content, "Link")
        assert (link.children, link.href) == (labels.STATE_NOT_FOUND_LINK, "/states")


@pytest.mark.parametrize(
    ("value", "year"),
    [(1000, 1000), (9999, 9999), (999, None), (10000, None), (True, None)],
)
def test_checked_year_accepts_exactly_the_four_digit_years(
    value: Any, year: int | None
) -> None:
    assert query.checked_year(value) == year


class TestIndex:
    def test_a_served_state_is_found_with_its_canonical_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        status, head, _ = get("/state/GA?year_from=1860&usps=TX&junk=1")
        assert status == 200
        assert head.canonical == url("/state/GA")
        # Its parser keeps the year range alone (#620, D119), so og:url names it and
        # nothing else, the path variable dropped (D081).
        assert head.og_url == url("/state/GA?year_from=1860")

    @pytest.mark.parametrize(
        ("search", "og"),
        [
            ("?year_to=1990&year_from=1900", "?year_from=1900&year_to=1990"),
            ("?year_from=1900&year_from=1900", "?year_from=1900"),
            ("?year_from=1990&year_to=1900", ""),
            ("?year_from=abc", ""),
            # Syntactic, as og:url always is: an out-of-span year is kept here and
            # replaced by its default in the render.
            ("?year_from=1700", "?year_from=1700"),
            ("?year_to=1844", "?year_to=1844"),
        ],
    )
    def test_og_url_names_the_normalized_range(
        self, monkeypatch: pytest.MonkeyPatch, search: str, og: str
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        status, head, _ = get(f"/state/GA{search}")
        assert status == 200
        assert head.canonical == url("/state/GA")
        assert head.og_url == url(f"/state/GA{og}")

    @pytest.mark.parametrize("path", ["/state/ZZ", "/state/ga", "/state/G1"])
    def test_with_the_roster_cached_an_unserved_code_is_a_404(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        status, head, _ = get(path)
        assert status == 404
        assert head.noindex and head.canonical is None
        assert calls == []

    def test_the_per_capita_page_s_canonical_url_drops_the_query_and_og_url_keeps_the_range(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        status, head, _ = get(
            "/state/GA/per-capita?year_from=1860&candidate=abraham-lincoln"
            "&pv_status=popular_vote&usps=TX"
        )
        assert status == 200
        assert head.canonical == url("/state/GA/per-capita")
        assert head.og_url == url("/state/GA/per-capita?year_from=1860")

    @pytest.mark.parametrize(
        "path", ["/state/ZZ/per-capita", "/state/ga/per-capita", "/state/GA/x"]
    )
    def test_with_the_roster_cached_an_unserved_state_or_section_is_a_404(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        status, head, _ = get(path)
        assert status == 404
        assert head.noindex and head.canonical is None
        assert calls == []

    def test_an_old_filtered_link_answers_302_to_the_results_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T4 left the history page (#619), so an old link naming its candidate or
        status is moved there (D092's ``moved=``, D118), the year range riding along
        through the results page's parser; and the page it lands on applies it. A
        link with the year range alone is not moved. The full contract is
        ``test_dashboard_app.TestMovedStateFilters``."""
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        search = "?year_from=1860&year_to=1872&candidate=horatio-seymour"
        response = appmod.server.test_client().get(f"/state/GA{search}")
        assert response.status_code == 302
        target = response.headers["Location"]
        assert target == (
            "/state/GA/elections?candidate=horatio-seymour&year_from=1860&year_to=1872"
        )
        assert calls == []
        # The target, through the layout as the router calls it, applies the filters.
        path, query = target.split("?")
        assert path == state_view.path("GA", state_view.RESULTS)
        tree = RS_MOD["layout"](usps="GA", **parse(query))
        years = [
            int(texts(tr.children[0])[0])
            for tr in of_type(of_type(find(tree, RESULTS), "Tbody"), "Tr")
        ]
        assert years == [1868]
        status, head, _ = get("/state/GA?year_from=1860&year_to=1872")
        assert status == 200
        assert head.canonical == url("/state/GA")

    def test_with_the_roster_cold_the_index_counts_it_matched_and_reads_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        status, head, _ = get("/state/ZZ")
        assert status == 200  # D073: the index never waits on the API
        assert head.canonical == url("/state/ZZ")
        assert calls == []


# --- the title ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("usps", "named"),
    [
        ("GA", True),
        ("ZZ", True),
        ("ga", False),
        (None, False),
        (["GA"], False),
        ("<script>", False),
        ("", False),
    ],
)
def test_the_title_is_total_and_names_only_a_usps_code(usps: Any, named: bool) -> None:
    # The page's own title; the registry's is app.py's wrapper (#325, D083).
    title = MOD["title"](usps=usps)
    assert isinstance(title, str)
    assert (f"{usps} — state history" in title) is named
    assert "<" not in title
    assert title != RS_MOD["title"](usps=usps)


@pytest.mark.parametrize(
    ("usps", "named"),
    [("GA", True), ("ZZ", True), ("ga", False), (None, False), ("GA/x", False)],
)
def test_the_per_capita_title_is_total_names_only_a_code_and_differs(
    usps: Any, named: bool
) -> None:
    title = PC_MOD["title"](usps=usps)
    assert isinstance(title, str)
    assert (f"{usps} — people per electoral vote" in title) is named
    assert title.startswith(PC_MOD["PER_CAPITA_GENERIC_HEADING"]) is not named
    assert title != MOD["title"](usps=usps)


# --- the picker -----------------------------------------------------------------------


class TestPicker:
    def test_every_state_and_dc_is_listed_once_by_name_and_linked(self) -> None:
        tree = PICKER_MOD["render"](copy.deepcopy(ROSTER), 2024)
        links = of_type(find(tree, PICKER_MOD["LIST_ID"]), "Link")
        names = {r["state_usps"]: r["state"] for r in ROSTER["data"]}
        assert len(links) == 51
        assert [link.children for link in links] == sorted(names.values())
        assert {link.href for link in links} == {f"/state/{u}" for u in names}
        assert PICKER["success"] in component_ids(tree)

    @pytest.mark.parametrize(
        "change",
        [
            {"year": 2020},
            {"year": "2024"},
            {"state_usps": "ga"},
            {"state_usps": "GAA"},
            {"state_usps": None},
        ],
        ids=repr,
    )
    @pytest.mark.parametrize("position", [0, 50, -1])
    def test_a_malformed_roster_row_degrades(
        self, change: dict[str, Any], position: int
    ) -> None:
        body = copy.deepcopy(ROSTER)
        body["data"][position].update(change)
        with pytest.raises(TypeError):
            PICKER_MOD["render"](body, 2024)

    @pytest.mark.parametrize("data", [[], None, "rows"])
    def test_a_roster_with_no_rows_degrades(self, data: Any) -> None:
        body = copy.deepcopy(ROSTER)
        body["data"] = data
        with pytest.raises(TypeError):
            PICKER_MOD["render"](body, 2024)

    def test_the_picker_routes_from_the_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        assert PICKER["success"] in routed_ids(route("/states"))
        # The roster, then N2 for the history table (#641, D123).
        assert calls == [ROSTER_PATH, api.ELECTION_STATES_PATH]
        calls.clear()
        # The state pages read the same roster: no second fill of it.
        assert PAGE_ID in routed_ids(route("/state/GA"))
        assert PC_PAGE_ID in routed_ids(route("/state/GA/per-capita"))
        # The results page reads the history's response, already cached (#619).
        assert RS_PAGE_ID in routed_ids(route("/state/GA/elections"))
        assert calls == [GA_PATH, GA_PER_CAPITA_PATH]


# --- the per-capita page, T7 (#280, #559) --------------------------------------------

NO_FIGURE = "No census figure for this state at this election"
NO_VOTES = "No electoral votes this election"


def per_capita_rows(tree: Any) -> dict[int, dict[str, str]]:
    """T7's rows as ``{year: {field: cell text}}``."""
    table = find(tree, PER_CAPITA)
    rows = [] if table is None else of_type(of_type(table, "Tbody"), "Tr")
    fields = PC_MOD["PER_CAPITA_FIELDS"]
    shown = [
        dict(zip(fields, (" ".join(texts(td)) for td in tr.children), strict=True))
        for tr in rows
    ]
    return {int(row["year"]): row for row in shown}


class TestGeorgiaPerCapita:
    def test_every_served_year_is_shown_in_order(self) -> None:
        body = ga_per_capita()
        rows = per_capita_rows(pc_render())
        assert list(rows) == sorted(r["year"] for r in body["data"])

    def test_rows_are_sorted_by_the_page_not_trusted_in_api_order(self) -> None:
        body = ga_per_capita()
        random.Random(280).shuffle(body["data"])
        assert [r["year"] for r in body["data"]] != sorted(
            r["year"] for r in body["data"]
        )
        rows = per_capita_rows(pc_render(per_capita=body))
        assert list(rows) == sorted(r["year"] for r in body["data"])

    def test_the_governing_census_is_the_apportionment_s_not_the_nearest(self) -> None:
        rows = per_capita_rows(pc_render())
        assert rows[2020]["governing_census_year"] == "2010"
        assert rows[2024]["governing_census_year"] == "2020"
        assert rows[1924]["governing_census_year"] == "1910"
        assert rows[1928]["governing_census_year"] == "1910"
        assert labels.GOVERNING_CENSUS_NOTE in texts(pc_render())

    def test_1864_says_georgia_had_no_electoral_votes(self) -> None:
        rows = per_capita_rows(pc_render())
        assert rows[1864]["persons_per_electoral_vote"] == NO_VOTES
        assert rows[1864]["state_electoral_votes"] == "0"

    def test_each_year_links_to_its_election(self) -> None:
        table = find(pc_render(), PER_CAPITA)
        links = of_type(table, "Link")
        assert links and all(a.href == f"/election/{a.children}" for a in links)

    def test_each_header_is_its_label_with_the_raw_field_name(self) -> None:
        headers = of_type(find(pc_render(), PER_CAPITA), "Th")
        assert [(h.children, h.title) for h in headers] == [
            (labels.LABELS[f], f) for f in PC_MOD["PER_CAPITA_FIELDS"]
        ]
        assert set(PC_MOD["PER_CAPITA_FIELDS"]) <= set(ga_per_capita()["data"][0])

    def test_the_notes_are_t6_s_and_name_no_other_filter(self) -> None:
        tree = pc_render()
        shown = texts(tree)
        assert labels.GOVERNING_CENSUS_NOTE in shown
        assert labels.BOUNDARY_NOTE in shown
        # The year range is the page's only filter, so no note names another (#559).
        assert not any("candidate" in t for t in shown if isinstance(t, str))
        # T7's own heading is dropped: the H1 names the table (#559's ba spec).
        assert labels.SECTION_PER_CAPITA not in [h.children for h in of_type(tree, "H2")]

    def test_the_column_name_list_and_the_footer_follow_the_table(self) -> None:
        tree = pc_render()
        named = [
            [c.children for c in of_type(g, "Code")]
            for g in of_type(tree, "Details")
        ]
        assert list(PC_MOD["PER_CAPITA_FIELDS"]) in named
        provenance = ga_per_capita()["meta"]["provenance"]
        (footer,) = of_type(tree, "Footer")
        assert f"{provenance['census_source_name']} (" in texts(footer)

    def test_the_heading_names_the_state_from_t7_s_rows(self) -> None:
        _, name = PC_MOD["render"](ga_per_capita(), copy.deepcopy(INDEX), "GA", [])
        assert name == "Georgia"

    @pytest.mark.parametrize("name", ["", "  ", "\u200b"], ids=repr)
    def test_a_name_with_nothing_in_it_gets_the_generic_heading(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        body = ga_per_capita()
        for row in body["data"]:
            row["state"] = name
        fetch, _ = fake_fetch({**RECORDED, GA_PER_CAPITA_PATH: body})
        client = offline_client(
            fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, ROSTER_PATH]
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        heading, _, content = PC_MOD["layout"](usps="GA").children
        assert heading.children == PC_MOD["PER_CAPITA_GENERIC_HEADING"]
        assert content.id == PC_PAGE_ID


def test_texas_1848_has_no_census_figure_and_1864_1868_no_votes() -> None:
    rows = per_capita_rows(pc_render(usps="TX"))
    assert rows[1848]["population"] == NO_FIGURE
    assert rows[1848]["persons_per_electoral_vote"] == NO_FIGURE
    assert rows[1864]["persons_per_electoral_vote"] == NO_VOTES
    assert rows[1868]["persons_per_electoral_vote"] == NO_VOTES


class TestT7Filters:
    def test_the_year_range_narrows_t7(self) -> None:
        rows = per_capita_rows(pc_render("year_from=1860&year_to=1872"))
        assert list(rows) == [1860, 1864, 1868, 1872]

    @pytest.mark.parametrize(
        "search", ["candidate=horatio-seymour", "pv_status=not_participating"]
    )
    def test_the_results_page_s_filters_do_not_reach_t7(self, search: str) -> None:
        assert len(per_capita_rows(pc_render(search))) == len(ga_per_capita()["data"])

    def test_t7_counts_its_rows(self) -> None:
        tree = pc_render("year_from=1860&year_to=1872")
        total = len(ga_per_capita()["data"])
        assert f"Showing 4 of {total} rows" in texts(tree)

    def test_a_range_before_the_state_s_first_election_is_empty(self) -> None:
        tree = pc_render("year_from=1824&year_to=1840", usps="TX")
        assert per_capita_rows(tree) == {}
        assert "No rows match these filters." in texts(tree)

    def test_the_year_control_is_the_only_control(self) -> None:
        tree = pc_render("year_from=1860")
        (slider,) = of_type(tree, "RangeSlider")
        assert slider.id == PC_MOD["YEARS_ID"]
        assert slider.value == [1860, 2024]
        assert of_type(tree, "Dropdown") == []

    @pytest.mark.parametrize(
        ("years", "current", "expected"),
        [
            ([1860, 2024], "", "?year_from=1860"),
            ([1824, 1900], "", "?year_to=1900"),
            ([1824, 2024], "?year_from=1860", ""),
            ([1860, 2024], "?year_from=1860", no_update),
        ],
        ids=repr,
    )
    def test_a_year_change_writes_only_the_range(
        self, years: list[int], current: str, expected: Any
    ) -> None:
        assert PC_MOD["on_filter_change"](years, 1824, 2024, current) == expected

    def test_the_download_names_the_page_and_the_range_applied(self) -> None:
        # Read off the rendered link, so the search the render passes is what is
        # checked: the range applied, and never the history page's keys.
        tree = pc_render("year_from=1860&candidate=horatio-seymour")
        file = download(tree, PER_CAPITA)
        assert find(tree, export.link_id(PER_CAPITA)).download == (
            "state-GA-per-capita.csv"
        )
        (view,) = [line for line in file.lines if line.startswith("View: ")]
        assert view.endswith("/state/GA/per-capita?year_from=1860")
        assert [r["year"] for r in file.rows][0] == "1860"


class TestT7Bodies:
    @pytest.mark.parametrize(
        "change",
        [{"state_usps": "AL"}, {"state_usps": None}, {"year": 1826}, {"year": "1868"}],
    )
    def test_a_row_of_another_state_or_no_served_year_is_malformed(
        self, change: dict[str, Any]
    ) -> None:
        body = ga_per_capita()
        body["data"][5].update(change)
        with pytest.raises(TypeError, match="/v1/states/GA/per-capita"):
            pc_render(per_capita=body)

    @pytest.mark.parametrize("data", [[], None, "rows"])
    def test_a_body_with_no_rows_is_malformed(self, data: Any) -> None:
        body = ga_per_capita()
        body["data"] = data
        with pytest.raises(TypeError):
            pc_render(per_capita=body)

    def test_a_malformed_body_degrades_only_the_per_capita_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = ga_per_capita()
        body["data"] = []
        fetch, _ = fake_fetch({**RECORDED, GA_PER_CAPITA_PATH: body})
        client = offline_client(
            fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, ROSTER_PATH]
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        ids = routed_ids(route("/state/GA/per-capita"))
        assert "unavailable" in ids
        assert PC_PAGE_ID not in ids
        assert PAGE_ID in routed_ids(route("/state/GA"))


@pytest.mark.parametrize(
    "answer",
    [
        api.ApiUnavailable("GET /v1/states/GA/per-capita: HTTP 503"),
        # The real recorded body: only its version is wrong, so this degrades only
        # through View.get's version check.
        api.Response(
            body=copy.deepcopy(RECORDED[GA_PER_CAPITA_PATH]),
            version="another-snapshot",
        ),
    ],
    ids=["unavailable", "another-version"],
)
def test_a_failed_per_capita_read_degrades_only_its_own_page(
    monkeypatch: pytest.MonkeyPatch, answer: api.Response | Exception
) -> None:
    """The read itself failing, not only a malformed body: the per-capita page
    degrades, a response of another snapshot is never mixed into the render, and the
    history page, which never reads T7's path (#559), still renders."""
    recorded, _ = fake_fetch(RECORDED)
    calls: list[str] = []

    def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        calls.append(path)
        if path == GA_PER_CAPITA_PATH:
            if isinstance(answer, Exception):
                raise answer
            return answer
        response: api.Response = recorded(path, timeout)
        return response

    client = offline_client(
        fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, ROSTER_PATH]
    )
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    monkeypatch.setattr(api, "CLIENT", client)
    ids = routed_ids(route("/state/GA/per-capita"))
    assert "unavailable" in ids
    assert PC_PAGE_ID not in ids and PER_CAPITA not in ids
    assert GA_PER_CAPITA_PATH in calls
    calls.clear()
    assert PAGE_ID in routed_ids(route("/state/GA"))
    assert GA_PER_CAPITA_PATH not in calls


def test_the_routed_per_capita_page_shows_t7_and_the_history_page_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_client(monkeypatch, source=api.ROSTER_PATH)
    assert {PC_PAGE_ID, PER_CAPITA} <= routed_ids(route("/state/GA/per-capita"))
    history = routed_ids(route("/state/GA"))
    assert PAGE_ID in history and PER_CAPITA not in history


# --- the section links (#559, #619; D105, D118) ------------------------------------------


def section_entries(tree: Any) -> list[Any]:
    (nav,) = [n for n in of_type(tree, "Nav") if n.id == state_view.SECTIONS_ID]
    return list(nav.children)


class TestSectionLinks:
    """A state's three pages link each other on success only, in page order: the page
    being read is text with ``aria-current="page"``, the others links. The history
    page applies no year range (until #620), so its links carry no query; the results
    and per-capita pages' links carry the year range the render applied and nothing
    else (#559, #619; D105, D118; the election pages' links carry no filter, D092).
    The results page's own entries are in
    ``test_dashboard_state_results.TestSectionLinks``."""

    def test_the_link_texts_are_the_spec_s_and_name_each_page_apart(self) -> None:
        # ba's specs, approved at #559's and #619's plan gates: the entries must
        # differ, or a reader could not tell which page a link opens.
        assert state_view.SECTIONS == ("", "/elections", "/per-capita")
        assert [state_view.SECTION_TEXT[s] for s in state_view.SECTIONS] == [
            "State history",
            "Results by election",
            "People per electoral vote",
        ]

    def test_the_landmark_is_named_and_drawn_as_the_election_pages_are(self) -> None:
        (nav,) = [n for n in of_type(render(), "Nav") if n.id == state_view.SECTIONS_ID]
        assert getattr(nav, "aria-label") == labels.STATE_SECTIONS_LABEL
        assert nav.className == election_view.SECTIONS_CLASS == "section-links"

    def test_on_the_history_page_the_history_is_marked(self) -> None:
        current, results, per_capita = section_entries(render())
        assert type(current).__name__ == "Span"
        assert current.children == labels.SECTION_STATE_HISTORY
        assert getattr(current, "aria-current") == "page"
        assert [type(e).__name__ for e in (results, per_capita)] == ["Link", "Link"]
        assert results.children == labels.SECTION_RESULTS_BY_ELECTION
        assert per_capita.children == labels.SECTION_PER_CAPITA
        assert (results.href, per_capita.href) == (
            "/state/GA/elections",
            "/state/GA/per-capita",
        )
        for link in (results, per_capita):
            assert not hasattr(link, "aria-current")

    @pytest.mark.parametrize(
        ("query", "usps", "carried"),
        [
            ("year_from=1860&year_to=1900", "GA", "?year_from=1860&year_to=1900"),
            (
                "year_to=1900&candidate=horatio-seymour&pv_status=popular_vote",
                "GA",
                "?year_to=1900",
            ),
            ("candidate=horatio-seymour", "GA", ""),
            # A bound outside the state's span is its default, so it is not carried.
            ("year_from=1700", "GA", ""),
            # Texas's span starts at its first election, 1848 (#620, D119): a bound
            # at that end is the default; one before it falls back to it.
            ("year_from=1848&year_to=1900", "TX", "?year_to=1900"),
            ("year_from=1840&year_to=1870", "TX", "?year_to=1870"),
            ("year_from=1852", "TX", "?year_from=1852"),
        ],
    )
    def test_the_history_s_links_carry_the_range_applied_only(
        self, monkeypatch: pytest.MonkeyPatch, query: str, usps: str, carried: str
    ) -> None:
        """#620 (D119, restoring D105 for the history hop): through the layout, as the
        router calls it with the URL's keys, the links carry the year range the render
        applied against the state's span, in the normal form, and nothing else."""
        cached_client(monkeypatch)
        _, results, per_capita = section_entries(history_layout(query, usps=usps))
        assert (results.href, per_capita.href) == (
            f"/state/{usps}/elections{carried}",
            f"/state/{usps}/per-capita{carried}",
        )

    def test_on_the_per_capita_page_t7_is_marked(self) -> None:
        history, results, current = section_entries(pc_render())
        assert type(current).__name__ == "Span"
        assert current.children == labels.SECTION_PER_CAPITA
        assert getattr(current, "aria-current") == "page"
        assert [type(e).__name__ for e in (history, results)] == ["Link", "Link"]
        assert history.children == labels.SECTION_STATE_HISTORY
        assert results.children == labels.SECTION_RESULTS_BY_ELECTION
        assert (history.href, results.href) == ("/state/GA", "/state/GA/elections")

    @pytest.mark.parametrize(
        ("query", "carried"),
        [
            ("year_from=1860&year_to=1900", "?year_from=1860&year_to=1900"),
            ("year_to=1900&candidate=horatio-seymour", "?year_to=1900"),
            ("year_from=1700", ""),
            ("", ""),
        ],
    )
    def test_the_per_capita_links_carry_the_range_applied_only(
        self, query: str, carried: str
    ) -> None:
        history, results, _ = section_entries(pc_render(query))
        assert history.href == f"/state/GA{carried}"
        assert results.href == f"/state/GA/elections{carried}"

    def test_the_links_come_first_in_each_page_s_body(self) -> None:
        for tree in (render(), pc_render()):
            assert tree.children[0].id == state_view.SECTIONS_ID

    @pytest.mark.parametrize(
        "path", ["/state/ZZ", "/state/ZZ/elections", "/state/ZZ/per-capita"]
    )
    def test_the_not_found_state_has_no_section_links(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route(path))
        assert any(i.endswith("not-found") for i in ids)
        assert state_view.SECTIONS_ID not in ids

    @pytest.mark.parametrize(
        ("path", "broken"),
        [
            ("/state/GA", GA_PATH),
            ("/state/GA/elections", GA_PATH),
            ("/state/GA/per-capita", GA_PER_CAPITA_PATH),
        ],
    )
    def test_the_degraded_state_has_no_section_links(
        self, monkeypatch: pytest.MonkeyPatch, path: str, broken: str
    ) -> None:
        TestMalformedBodies.client_with(monkeypatch, broken)
        ids = routed_ids(route(path))
        assert "unavailable" in ids
        assert state_view.SECTIONS_ID not in ids

    def test_the_success_state_has_them_on_every_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        for path in ("/state/GA", "/state/GA/elections", "/state/GA/per-capita"):
            assert state_view.SECTIONS_ID in routed_ids(route(path)), path


# --- the wide layout (#545, D102) -------------------------------------------------------


class TestWideLayout:
    """The state pages' layout at desktop width (#545). T4's filter row moved with T4
    to the results page (#619), whose ``TestWideLayout`` pins it; the rules are pinned
    in ``TestLayoutRules`` (``test_dashboard_theme.py``) and what a browser draws in
    ``tests/e2e/test_dashboard_e2e_history.py``."""

    def test_the_history_is_the_section_links_then_c7_and_c10_s_one_card(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # #560, D106; #618, D117; #619, D118; #620, D119: the lede is added by
        # layout(), so the whole page is checked there: the heading, the lede and the
        # page body, nothing between. In the body, the section links first (#559,
        # D105), then the page-local Location (#620); then one card holding the
        # headline figures (#601, D115), the Years slider in a row of its own (#634,
        # D122), C7's heading, C7, C10's heading, C10, the heading of the table the two
        # share, the table in
        # its scroll box, its download, its notes and its column-name list; then the
        # footer. Two charts, C7 and C10; no T4 and no dropdown.
        cached_client(monkeypatch)
        page = MOD["layout"](usps="GA")
        heading, lede, content = page.children
        assert type(heading).__name__ == "H1"
        assert type(lede).__name__ == "P" and lede.className == "lede"
        assert getattr(content, "id", None) == PAGE_ID
        kids = list(content.children)
        assert kids[0].id == state_view.SECTIONS_ID
        assert type(kids[1]).__name__ == "Location" and kids[1].id == MOD["URL_ID"]
        # One card (#567, D111; #618, D117; #619): C7 and C10 with their table.
        assert cards(content) == [kids[2]]
        assert len(kids) == 4
        charts_card = card_children(content, 2)
        assert [type(k).__name__ for k in charts_card[:7]] == [
            "Div",
            "Div",
            "H2",
            "Figure",
            "H2",
            "Figure",
            "H2",
        ]
        # The card opens with the figures, then the slider's box, its row of its own
        # (#545's rule), above only what it narrows (#634, D122).
        assert charts_card[0].id == MOD["METRICS_ID"]
        (own,) = classed(charts_card[1], "filter-own-row")
        assert "filter" in own.className.split()
        label, slider = own.children
        assert type(label).__name__ == "Label"
        assert (label.children, label.htmlFor) == (labels.YEARS_FILTER, MOD["YEARS_ID"])
        assert slider.id == MOD["YEARS_ID"]
        # What follows the figures and the slider's box.
        charts_card = charts_card[2:]
        assert charts_card[0].children == MOD["C7_HEADING"]
        assert charts_card[1].id == charts.dom_id(MOD["C7_ID"])
        assert charts_card[2].children == MOD["C10_HEADING"]
        assert charts_card[3].id == charts.dom_id(MOD["C10_ID"])
        assert charts_card[4].children == MOD["ELECTORS_TOTALS_TABLE_HEADING"]
        # The one table and its column-name list follow both charts, in their card.
        assert find(charts_card, MOD["ELECTORS_TABLE_ID"]) is not None
        assert find(charts_card, MOD["ELECTORS_GLOSSARY_ID"]) is not None
        # The retired tables and lists are gone (D097(g): never reused).
        for retired in (
            "state-popular-total",
            "state-popular-total-glossary",
            "state-history",
            "state-history-glossary",
        ):
            assert find(content, retired) is None, retired
        assert find(content, RESULTS) is None
        assert [loc.id for loc in of_type(content, "Location")] == [MOD["URL_ID"]]
        assert of_type(content, "Dropdown") == []
        (only,) = classed(content, "filter")
        assert only is own
        assert [h.children for h in of_type(charts_card, "H2")] == [
            MOD["C7_HEADING"],
            MOD["C10_HEADING"],
            MOD["ELECTORS_TOTALS_TABLE_HEADING"],
        ]
        assert [f.id for f in of_type(page, "Figure")] == [
            charts.dom_id("C7"),
            charts.dom_id("C10"),
        ]

    def test_the_per_capita_page_s_slider_has_its_own_row_and_no_slot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The year range alone, in the history page's filter row (#545, D102), and no
        # chart slot until C8 (#561) lands (#545's rule).
        cached_client(monkeypatch)
        page = PC_MOD["layout"](usps="GA")
        heading, lede, content = page.children
        assert type(heading).__name__ == "H1"
        assert lede.className == "lede"
        kids = list(content.children)
        assert kids[0].id == state_view.SECTIONS_ID
        assert type(kids[1]).__name__ == "Location"
        # The page's one section is one card (#567, D111), opened by the filters.
        assert cards(content) == [kids[2]]
        (box,) = classed(content, "filters")
        assert card_children(content, 2)[0] is box
        assert box.className.split() == ["filters", "filter-row"]
        (own,) = box.children
        assert own.className.split() == ["filter", "filter-own-row"]
        assert find(own, PC_MOD["YEARS_ID"]) is not None
        assert of_type(page, "Figure") == []


# --- chart C7: the state's electors appointed in each election (#560, D106) ----------

C7_DOM = charts.dom_id("C7")
ELECTORS = MOD["ELECTORS_TABLE_ID"]
#: N2, by its literal path: no dashboard page reads it since #562 (D107), and its
#: recording stays test input for C7's reconciliation (D106(h)).
N2: dict[str, Any] = RECORDED["/v1/elections/states"]
SERVED = sorted(state_view.served_years(INDEX))
#: The states whose history is recorded (``/v1/states/{usps}``). C10's oracle runs
#: over each with no edit; C7's also reads the state's entry in :data:`HISTORIES`,
#: so a newly recorded state needs one there, which
#: ``TestC7.test_the_literals_cover_every_recorded_state`` enforces.
RECORDED_STATES = sorted(
    path.rsplit("/", 1)[1]
    for path in RECORDED
    if path.startswith("/v1/states/") and path.count("/") == 3
)


class History(NamedTuple):
    """A recorded state's name, first election and zero allotments."""

    name: str
    first: int
    zeros: list[int]


#: Each recorded state's facts, written as literals so the C7 tests built over
#: ``RECORDED_STATES`` check against something other than the recording they read:
#: Georgia took no part in 1864, Texas in 1864 and 1868, and Texas's first election
#: is 1848 (#575).
HISTORIES = {
    "GA": History("Georgia", 1824, [1864]),
    "TX": History("Texas", 1848, [1864, 1868]),
}


def shared_cells(tree: Any) -> list[tuple[str, str, str, str]]:
    """The table C7 and C10 share (#618): each row's year, allotment, status and total
    texts."""
    return [
        tuple(" ".join(texts(cell)) for cell in tr.children)  # type: ignore[misc]
        for tr in body_rows(tree, ELECTORS)
    ]


def body_cells(tree: Any) -> list[tuple[str, str, str]]:
    """C7's columns of its companion table: each row's year, allotment and status."""
    return [(year, appointed, status) for year, appointed, status, _ in shared_cells(tree)]


def c7_figure(tree: Any) -> Any:
    """C7's unresolved figure in a rendered tree, or ``None`` where it is not built."""
    source = repr(charts.source_id(C7_DOM))
    stores = [
        s for s in of_type(tree, "Store") if repr(getattr(s, "id", None)) == source
    ]
    return stores[0].data if stores else None


def c7_title(tree: Any) -> str:
    """C7's title, as page text (``components.chart`` lifts it out of the figure)."""
    (title,) = [p for p in of_type(tree, "P") if getattr(p, "id", None) == "c7-title"]
    return str(title.children)


def c7_caption(tree: Any) -> str:
    (figure,) = [f for f in of_type(tree, "Figure") if f.id == C7_DOM]
    (caption,) = of_type(figure, "Figcaption")
    return caption_text(caption)


def n2_state(usps: str) -> list[dict[str, Any]]:
    """The recorded N2 rows of one state, in year order: C7's reconciliation oracle
    (D106(h)), C4's one-state source until #562."""
    return sorted(
        (r for r in N2["data"] if r["state_usps"] == usps), key=lambda r: r["year"]
    )


def traces(figure: dict[str, Any]) -> dict[str, list[int]]:
    """Each trace's years, by its name: the bar's and each marker series'."""
    return {t["name"]: list(t["x"]) for t in figure["data"]}


def with_year(body: dict[str, Any], year: int, **fields: Any) -> dict[str, Any]:
    """``body`` with ``fields`` set on every candidate row of ``year``."""
    for row in body["data"]:
        if row["year"] == year:
            row.update(copy.deepcopy(fields))
    return body


#: URLs that change nothing on the history page: T4's moved keys (#619, D118), which
#: its parser drops, and year ranges whose every bound is outside the state's span or
#: at its end, each falling back to or being the default (#620, D119).
UNFILTERED_URLS = [
    "candidate=andrew-jackson",
    "pv_status=not_participating",
    "year_from=1700&year_to=1800",
    "year_from=1824&year_to=2024",
    "candidate=horatio-seymour&pv_status=popular_vote&junk=1",
]


def state_years(usps: str) -> list[int]:
    """The served years from ``usps``'s first election: the default view's axis and
    table (#620, D119)."""
    return [y for y in SERVED if y >= HISTORIES[usps].first]


def assert_no_filter_sentence(caption: str) -> None:
    """A chart caption on the history page names no filter (#619, D118): neither a
    state page's filter sentence nor the note C7 and C10 carried before."""
    for sentence in (RS_MOD["FILTER_SENTENCE"], PC_MOD["FILTER_SENTENCE"]):
        assert sentence not in caption
    assert "filter" not in caption.lower()
    assert "Narrow" not in caption


class TestC7:
    def test_its_bars_are_electoral_red_and_its_caption_collapsed(self) -> None:
        """#593 (D109): a state's electors appointed is electoral (red); the 14 px year
        ticks and the key above the plot reach C7 through the shared pieces."""
        tree = render()
        figure = c7_figure(tree)
        (bars,) = [tr for tr in figure["data"] if tr["type"] == "bar"]
        assert bars["marker"]["color"] == "var(--chart-ec)"
        assert figure["layout"]["xaxis"]["tickfont"] == {"size": 14}
        figcaption, _ = of_type(tree, "Figcaption")
        assert type(figcaption.children[0]).__name__ == "Details"

    def test_its_plot_shares_c10_s_left_and_right_margin(self) -> None:
        """#582 (D113(f)): stacked above C10, C7 takes the state page's one fixed left
        and right margin, keeps its own top, and its value axis pushes none."""
        figure = c7_figure(render())
        margin = figure["layout"]["margin"]
        assert {k: margin[k] for k in ("l", "r")} == over_time.STATE_MARGIN
        assert margin["t"] == over_time.TOP_PX
        assert figure["layout"]["yaxis"]["automargin"] is False

    def test_it_is_registered_on_the_history_page_with_the_shared_table(self) -> None:
        assert charts.CHARTS["C7"] == charts.Chart("/state/<usps>", ELECTORS)
        tree = render()
        figure, _ = of_type(tree, "Figure")
        assert figure.id == C7_DOM == "c7"
        assert find(tree, ELECTORS) is not None
        csv = download(tree, ELECTORS)
        # Shared with C10 since #618 (D117): append-only from C7's own columns.
        assert csv.header == [
            "year",
            "state_electoral_votes",
            "pv_status",
            "state_popular_total",
            "state_usps",
        ]
        assert {r["state_usps"] for r in csv.rows} == {"GA"}

    def test_the_literals_cover_every_recorded_state(self) -> None:
        assert sorted(HISTORIES) == RECORDED_STATES
        for usps, history in HISTORIES.items():
            names = {r["state"] for r in RECORDED[f"/v1/states/{usps}"]["data"]}
            assert names == {history.name}, usps

    @pytest.mark.parametrize("usps", RECORDED_STATES)
    def test_its_points_are_n2_s_one_state_series(self, usps: str) -> None:
        # AC2 (#560, and #575 for Texas) against the recorded N2 rows directly, never
        # C4's render (D106(h)), so it survives #562; and the history and N2 agree on
        # every year both hold.
        path = f"/v1/states/{usps}"
        records = state_view.electors(
            state_view.rows(copy.deepcopy(RECORDED[path]), usps, set(SERVED), path),
            set(SERVED),
            usps,
            path,
        )
        n2 = n2_state(usps)
        assert [
            (r["year"], r["state_electoral_votes"], r["pv_status"]) for r in records
        ] == [(r["year"], r["state_electoral_votes"], r["pv_status"]) for r in n2]
        assert n2[0]["year"] == HISTORIES[usps].first
        name = HISTORIES[usps].name
        tree = render(usps=usps)
        figure = c7_figure(tree)
        # The default view starts at the state's first election (#620, D119).
        expected = over_time.c4_figure(
            over_time.appointed_points(n2),
            state_years(usps),
            labels.C4_TITLE_STATE.format(state=name),
            name,
        ).figure
        # Aligned with C10 on the state page's one margin (#582, D113(f)).
        over_time.align(expected, over_time.STATE_MARGIN)
        # ``components.chart`` takes the title out of the figure into page text.
        title = expected["layout"].pop("title")["text"]
        assert figure == expected
        assert c7_title(tree) == title

    def test_every_n2_state_s_series_reads_the_same_through_c7(self) -> None:
        # AC2 on the recorded N2 fixture (beside the recorded histories), against N2's rows
        # directly and never C4's builders, so #562 can retire C4's one-state mode
        # (D106(h)): each state's rows, one per election, pass C7's collapse unchanged,
        # and its points word exactly N2's allotment and status.
        states = {r["state_usps"] for r in N2["data"]}
        assert len(states) == 51
        for usps in sorted(states):
            n2 = n2_state(usps)
            records = state_view.electors(n2, set(SERVED), usps, "N2")
            assert [
                (r["year"], r["state_electoral_votes"], r["pv_status"])
                for r in records
            ] == [
                (r["year"], r["state_electoral_votes"], r["pv_status"]) for r in n2
            ], usps
            points = over_time.appointed_points(records)
            assert [
                (p.year, p.appointed, p.appointed_cell, p.status, p.status_cell)
                for p in points
            ] == [
                (
                    r["year"],
                    r["state_electoral_votes"],
                    labels.number(r["state_electoral_votes"]),
                    r["pv_status"],
                    labels.pv_status(r["pv_status"]),
                )
                for r in n2
            ], usps

    @pytest.mark.parametrize("usps", RECORDED_STATES)
    def test_the_chart_equals_its_table_s_cells(self, usps: str) -> None:
        tree = render(usps=usps)
        figure = c7_figure(tree)
        rows = download(tree, ELECTORS).rows
        (bars,) = [t for t in figure["data"] if t["type"] == "bar"]
        drawn = dict(zip(bars["x"], bars["y"], strict=True))
        cells = {int(r["year"]): r for r in rows}
        assert set(cells) == set(range(HISTORIES[usps].first, 2025, 4))
        for year, value in drawn.items():
            assert cells[year]["state_electoral_votes"] == str(value), year
        markers = {y for t in figure["data"] if t["type"] != "bar" for y in t["x"]}
        assert markers == set(HISTORIES[usps].zeros)
        for year in HISTORIES[usps].zeros:
            assert cells[year]["state_electoral_votes"] == "0", year
        # Each hover writes the table's cells (D091).
        hovers = [h for t in figure["data"] for h in t["hovertext"]]
        assert len(hovers) == len(rows)
        body = body_cells(tree)
        name = HISTORIES[usps].name
        for hover, (year, appointed, status) in zip(
            sorted(hovers, key=lambda h: int(h[:4])), body, strict=True
        ):
            assert hover == labels.C4_STATE_HOVER.format(
                year=year, state=name, appointed=appointed, pv_status=status
            )

    @pytest.mark.parametrize(
        ("query", "view"),
        [
            ("", ""),
            ("year_from=1900&candidate=jimmy-carter", "?year_from=1900"),
            ("year_to=1990&year_from=1900", "?year_from=1900&year_to=1990"),
            ("year_from=1700&pv_status=popular_vote", ""),
        ],
    )
    def test_the_table_s_links_view_and_note(
        self, monkeypatch: pytest.MonkeyPatch, query: str, view: str
    ) -> None:
        # The table C7 shares with C10 (#618): each year links to that election's
        # page, its file names the history page with the year range the render
        # applied and nothing else (#620, D119; T4's moved keys are never read,
        # D118), and the allotment's basis is among its notes, under the table and in
        # the file's preamble (#560's acceptance gate, Class B).
        cached_client(monkeypatch)
        tree = history_layout(query)
        rows = body_rows(tree, ELECTORS)
        assert rows
        for tr in rows:
            (link,) = of_type(tr.children[0], "Link")
            assert link.href == f"/election/{link.children}"
        lines = download(tree, ELECTORS).lines
        assert (
            f"View: https://explore.us-presidential-election-center.org/state/GA{view}"
            in lines
        )
        assert labels.C4_BASIS in lines
        # The note follows the table's scroll box, in C7's card (#567).
        (card,) = [k for k in cards(tree) if find(k, ELECTORS) is not None]
        held = list(card.children)
        at = [i for i, k in enumerate(held) if find(k, ELECTORS) is not None]
        assert at
        assert labels.C4_BASIS in texts(held[at[0] + 1 : at[0] + 4])

    @pytest.mark.parametrize("usps", RECORDED_STATES)
    def test_a_zero_allotment_is_a_marker_by_its_cause(self, usps: str) -> None:
        # AC2 (#575): each recorded state's zeros, read from its rendered page. Both
        # states took no part in those years (D100(d)), so every zero is in that
        # marker series, none in the no-electors one, and none is drawn as a bar.
        zeros = [r["year"] for r in n2_state(usps) if r["state_electoral_votes"] == 0]
        assert zeros == HISTORIES[usps].zeros  # the premise
        assert {
            r["pv_status"] for r in n2_state(usps) if r["year"] in zeros
        } == {"not_participating"}
        tree = render(usps=usps)
        figure = c7_figure(tree)
        assert traces(figure)[labels.C4_NO_ELECTORS_TOOK_NO_PART] == HISTORIES[usps].zeros
        assert labels.C4_NO_ELECTORS not in traces(figure)
        bar = traces(figure)[labels.LABELS["state_electoral_votes"]]
        assert not set(HISTORIES[usps].zeros) & set(bar)
        assert labels.C4_ZERO_NOTE in c7_caption(tree)

    def test_texas_s_default_starts_at_its_first_election(self) -> None:
        """#620 (D119), AC1: Texas's first election, 1848, is after the dataset's, so
        its default view starts there: C7's and C10's axis and the table hold 1848 on,
        and both captions name the start (on real data; the doctored Georgia case is
        :meth:`test_a_later_first_election_starts_the_axis_and_is_named`)."""
        tree = render(usps="TX")
        years = state_years("TX")
        assert years[0] == 1848
        axis = components.year_axis(years)
        assert c7_figure(tree)["layout"]["xaxis"] == axis
        assert c10_figure(tree)["layout"]["xaxis"] == axis
        assert [int(y) for y, _, _ in body_cells(tree)] == years
        note = labels.FIRST_ELECTION_START_NOTE.format(state="Texas", year=1848)
        assert note in c7_caption(tree)
        assert note in c10_caption(tree)
        # The slider runs over the state's span, both ends chosen.
        (slider,) = of_type(tree, "RangeSlider")
        assert (slider.min, slider.max, slider.value) == (1848, 2024, [1848, 2024])

    def test_georgia_s_default_is_unchanged(self) -> None:
        """Georgia's first election is the dataset's, 1824, so its default view keeps
        every served year, and neither caption names a start."""
        tree = render()
        assert state_years("GA") == SERVED
        axis = components.year_axis(SERVED)
        assert c7_figure(tree)["layout"]["xaxis"] == axis
        assert c10_figure(tree)["layout"]["xaxis"] == axis
        assert [int(y) for y, _, _ in body_cells(tree)] == SERVED
        for caption in (c7_caption(tree), c10_caption(tree)):
            assert "This chart starts at" not in caption
        (slider,) = of_type(tree, "RangeSlider")
        assert (slider.min, slider.max, slider.value) == (1824, 2024, [1824, 2024])

    @pytest.mark.parametrize(
        ("value", "label"),
        [
            (None, labels.NOT_IN_DATASET),
            (-1, labels.UNRECOGNIZED),
            (True, labels.UNRECOGNIZED),
            (float("nan"), labels.UNRECOGNIZED),
            ("12", labels.UNRECOGNIZED),
        ],
    )
    def test_a_null_or_an_unrecognized_allotment_is_its_own_marker(
        self, value: Any, label: str
    ) -> None:
        # Set on every candidate row of the year, so C7 draws the marker rather than
        # refusing the year as two values (#560's architect review, C6).
        tree = render(body=with_year(ga_body(), 1900, state_electoral_votes=value))
        figure = c7_figure(tree)
        assert figure is not None
        assert traces(figure)[label] == [1900]
        assert 1900 not in traces(figure)[labels.LABELS["state_electoral_votes"]]
        assert labels.C4_NO_FIGURE_NOTE in c7_caption(tree)
        # The table's cell is the hover's (D091).
        (cell,) = [c for y, c, _ in body_cells(tree) if y == "1900"]
        assert cell == labels.number(value)
        hovers = [
            h for t in figure["data"] if t["name"] == label for h in t["hovertext"]
        ]
        assert hovers and cell in hovers[0]

    @pytest.mark.parametrize("query", UNFILTERED_URLS)
    def test_a_query_that_applies_no_range_changes_neither_chart_nor_table(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        # T4's moved keys are never read (D118), and a range wholly outside the
        # state's span falls back to its default (#620, D119): through the layout, as
        # the router calls it with the URL's keys, such a URL renders exactly the
        # unfiltered C7, C10 and their table, view URL included.
        cached_client(monkeypatch)
        plain, tree = history_layout(), history_layout(query)
        assert c7_figure(tree) == c7_figure(plain)
        assert c10_figure(tree) == c10_figure(plain)
        assert download(tree, ELECTORS).raw == download(plain, ELECTORS).raw
        assert c7_caption(tree) == c7_caption(plain)
        assert c10_caption(tree) == c10_caption(plain)

    def test_the_caption_describes_the_series(self) -> None:
        caption = c7_caption(render())
        assert caption.startswith(labels.C4_BASIS)
        # No filter sentence in a caption: the lede carries it (#619, #620).
        assert_no_filter_sentence(caption)
        # Georgia's first election is the dataset's, so no start sentence.
        assert "This chart starts at" not in caption
        assert labels.C4_NO_FIGURE_NOTE not in caption

    def test_a_later_first_election_starts_the_axis_and_is_named(self) -> None:
        # Georgia doctored to start in 1832 (#620, D119): the axis and the table start
        # there, and the caption names the start.
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] >= 1832]
        tree = render(body=body)
        assert labels.FIRST_ELECTION_START_NOTE.format(state="Georgia", year=1832) in (
            c7_caption(tree)
        )
        years = [y for y in SERVED if y >= 1832]
        assert c7_figure(tree)["layout"]["xaxis"] == components.year_axis(years)
        assert [int(y) for y, _, _ in body_cells(tree)] == years

    def test_the_start_sentence_compares_with_the_coverage_s_first_year(
        self,
    ) -> None:
        """The start sentence shows only when the state's first election is after the
        dataset's first year, read from the body's ``coverage.year_min`` (#620's ba
        spec; the retired sentence compared with the first served year instead).
        Served data never differs; doctored, Georgia's 1824 is after a coverage
        starting in 1700, so the sentence names it."""
        body = ga_body()
        body["meta"]["provenance"]["coverage"]["year_min"] = 1700
        tree = render(body=body)
        assert labels.FIRST_ELECTION_START_NOTE.format(state="Georgia", year=1824) in (
            c7_caption(tree)
        )
        assert "This chart starts at" not in c7_caption(render())

    def test_a_name_that_is_not_plain_text_takes_this_state_s_forms(self) -> None:
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] >= 1832]
        for row in body["data"]:
            row["state"] = "<b>Georgia"
        tree = render(body=body)
        figure = c7_figure(tree)
        assert c7_title(tree) == labels.C7_TITLE_THIS_STATE
        assert labels.FIRST_ELECTION_START_NOTE_THIS_STATE.format(year=1832) in (
            c7_caption(tree)
        )
        hovers = [h for t in figure["data"] for h in t["hovertext"]]
        assert all(charts.escaped("<b>Georgia") in h for h in hovers)


def column(tree: Any, field: str) -> list[str]:
    """One column of the shared table's file, by field name."""
    return [r[field] for r in download(tree, ELECTORS).rows]


#: Every note the shared table can carry (#618, D117(d)), so a degrade test can pin the
#: exact list it shows, not only an order among some of them.
def shared_notes(lines: list[str]) -> list[str]:
    window_note = labels.OVER_TIME_WINDOW_NOTE.format(
        pv_year_min=WINDOW[0], pv_year_max=WINDOW[1]
    )
    known = (
        MOD["ELECTORS_UNAVAILABLE_NOTE"],
        MOD["TOTALS_UNAVAILABLE_NOTE"],
        labels.C4_BASIS,
        labels.C5_BASIS,
        window_note,
    )
    return [line for line in lines if line in known]


def assert_column_unavailable(
    tree: Any, plain: Any, field: str, note: str
) -> None:
    """The shared table stays with ``field``'s column unavailable (#618, D117): the same
    header and years as the undoctored render's file, every cell of the column empty
    there and :data:`explore.labels.UNAVAILABLE_CELL` on the page, and ``note`` first
    among the table's notes, under it and in the preamble."""
    csv, before = download(tree, ELECTORS), download(plain, ELECTORS)
    assert csv.header == before.header
    assert column(tree, "year") == column(plain, "year")
    assert set(column(tree, field)) == {""}
    at = {"state_electoral_votes": 1, "state_popular_total": 3}[field]
    assert {row[at] for row in shared_cells(tree)} == {labels.UNAVAILABLE_CELL}
    # The exact notes (D117(d); #629's review, cr.2): the degraded column's note first,
    # never the other column's, both bases, and the window only when C10's half was
    # built, in the file and under the table alike.
    window = (
        []
        if field == "state_popular_total"
        else [
            labels.OVER_TIME_WINDOW_NOTE.format(
                pv_year_min=WINDOW[0], pv_year_max=WINDOW[1]
            )
        ]
    )
    expected = [note, labels.C4_BASIS, labels.C5_BASIS, *window]
    assert shared_notes(csv.lines) == expected
    (card,) = [k for k in cards(tree) if find(k, ELECTORS) is not None]
    held = list(card.children)
    (at_table,) = [i for i, k in enumerate(held) if find(k, ELECTORS) is not None]
    assert shared_notes(texts(held[at_table + 1 :])) == expected


class TestC7Degraded:
    """A body T4 accepts that C7 cannot read as one allotment per election (D096(d)'s
    rule, #560's AC5) puts :data:`C7_UNAVAILABLE` in C7's place, with no chart, no
    ``c7`` id and no headline figures. Which faults also reach C10 is exact per test
    (#582, D113(c) as amended; #618, D117): a fault in the allotment C7 alone, when the
    shared table stays with its electors column unavailable and C10 and its column as
    they were; one in what both read (the years, the state's name, ``pv_status``) both,
    when the table gives way to :data:`ELECTORS_TOTALS_TABLE_UNAVAILABLE`. The page's
    success marker and section links stay either way (T4 is on its own page since
    #619)."""

    def assert_degraded(self, body: dict[str, Any], *, both: bool) -> None:
        tree = render(body=body)
        assert getattr(tree, "id", None) == PAGE_ID
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert (find(tree, MOD["C10_UNAVAILABLE_ID"]) is not None) is both
        assert [f.id for f in of_type(tree, "Figure")] == ([] if both else [C10_DOM])
        assert c7_figure(tree) is None
        # The figures are built from C7's collapse, so they go with it (D115(g)).
        assert find(tree, MOD["METRICS_ID"]) is None
        assert find(tree, state_view.SECTIONS_ID) is not None
        # The page's one card holds these three headings and no other.
        headings = [h.children for h in of_type(every_card(tree), "H2")]
        assert headings == [
            MOD["C7_HEADING"],
            MOD["C10_HEADING"],
            MOD["ELECTORS_TOTALS_TABLE_HEADING"],
        ]
        if both:
            assert find(tree, ELECTORS) is None
            assert find(tree, MOD["ELECTORS_TABLE_UNAVAILABLE_ID"]) is not None
        else:
            plain = render()
            assert find(tree, MOD["ELECTORS_TABLE_UNAVAILABLE_ID"]) is None
            assert_column_unavailable(
                tree,
                plain,
                "state_electoral_votes",
                MOD["ELECTORS_UNAVAILABLE_NOTE"],
            )
            assert c10_figure(tree) == c10_figure(plain)
        # C7's note is in the page's one card, with C10 and the table (#618, #619).
        c7 = in_one_card(tree, MOD["C7_UNAVAILABLE_ID"], total=1)
        assert every_card(tree) == [c7]

    def test_two_allotments_in_one_election(self) -> None:
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["state_electoral_votes"] = 99
        self.assert_degraded(body, both=False)

    def test_a_figure_beside_a_null_or_true_beside_one(self) -> None:
        for value in (None, True):
            body = with_year(ga_body(), 1900, state_electoral_votes=1)
            (first, *_) = [r for r in body["data"] if r["year"] == 1900]
            first["state_electoral_votes"] = value
            self.assert_degraded(body, both=False)

    def test_two_statuses_in_one_election(self) -> None:
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["pv_status"] = "legislature_chosen"
        self.assert_degraded(body, both=True)

    def test_a_row_without_pv_status(self) -> None:
        # #640 (D120): what both collapses read, so both charts degrade, as the shared
        # collapse refuses the same fault in N2's rows (TestSharedCollapse).
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        del first["pv_status"]
        self.assert_degraded(body, both=True)

    def test_two_allotments_leave_c10_exactly_as_it_was(self) -> None:
        """#582 (D113(c)), AC5's converse, kept inside one table by #618 (D117): an
        allotment C7 cannot read leaves C10, its column and the status column the
        undoctored render's, and the page stays."""
        plain = render()
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["state_electoral_votes"] = 99
        tree = render(body=body)
        assert c7_figure(tree) is None
        assert c10_figure(tree) == c10_figure(plain)
        for field in ("year", "pv_status", "state_popular_total", "state_usps"):
            assert column(tree, field) == column(plain, field), field
        assert [t for _, t, _ in totals_cells(tree)] == [
            t for _, t, _ in totals_cells(plain)
        ]
        assert getattr(tree, "id", None) == PAGE_ID

    def test_a_gap_after_the_first_election(self) -> None:
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] != 1900]
        self.assert_degraded(body, both=True)

    @pytest.mark.parametrize("name", [None, 7, "", "   "])
    def test_a_served_name_with_nothing_in_it(self, name: Any) -> None:
        # D101's rule, as C4's n2_rows applied it until #562: a hover would write it as
        # "None", a number or nothing, so the section degrades.
        body = ga_body()
        for row in body["data"]:
            row["state"] = name
        self.assert_degraded(body, both=True)

    def test_a_row_without_the_allotment(self) -> None:
        body = ga_body()
        for row in body["data"]:
            if row["year"] == 1900:
                del row["state_electoral_votes"]
        # On the history page only C7 reads the field since T4 left it (#619, D118),
        # so the fault degrades C7 alone, with its column unavailable in the table.
        self.assert_degraded(copy.deepcopy(body), both=False)
        # T4 reads it too, so on the results page the same body degrades the page: a
        # fault in what T4 shows is never swallowed.
        with pytest.raises(KeyError):
            RS_MOD["render"](body, copy.deepcopy(INDEX), "GA", [])

    def test_the_page_s_degraded_layout_keeps_its_success_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["state_electoral_votes"] = 99
        fetch, _ = fake_fetch({**RECORDED, GA_PATH: body})
        client = offline_client(
            fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, ROSTER_PATH]
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        page = MOD["layout"](usps="GA")
        _, lede, content = page.children
        assert content.id == PAGE_ID
        # C10's collapse is read, so there is a range to narrow: the slider and the
        # filter sentence stay (#620, D119).
        assert lede.children == f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}"
        assert find(content, MOD["YEARS_ID"]) is not None
        assert find(content, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert find(content, C7_DOM) is None
        assert find(content, ELECTORS) is not None


# --- chart C10: the state's total popular vote in each election (#582, D113) ----------

C10_DOM = charts.dom_id("C10")
#: C10's companion table, the one it shares with C7 since #618 (D117).
TOTALS = ELECTORS
#: The years the narrowed one-value rule decides for Georgia (D113(b)): each has a
#: candidate row with no popular-vote record, whose total is null, beside the figure.
GA_SKIPPED_YEARS = (1976, 1988, 2004, 2016)
COVERAGE: dict[str, Any] = INDEX["meta"]["provenance"]["coverage"]
WINDOW = (COVERAGE["pv_year_min"], COVERAGE["pv_year_max"])


def c10_figure(tree: Any) -> Any:
    """C10's unresolved figure in a rendered tree, or ``None`` where it is not built."""
    source = repr(charts.source_id(C10_DOM))
    stores = [
        s for s in of_type(tree, "Store") if repr(getattr(s, "id", None)) == source
    ]
    return stores[0].data if stores else None


def c10_title(tree: Any) -> str:
    (title,) = [
        p for p in of_type(tree, "P") if getattr(p, "id", None) == "c10-title"
    ]
    return str(title.children)


def c10_caption(tree: Any) -> str:
    (figure,) = [f for f in of_type(tree, "Figure") if f.id == C10_DOM]
    (caption,) = of_type(figure, "Figcaption")
    return caption_text(caption)


def totals_cells(tree: Any) -> list[tuple[str, str, str]]:
    """C10's columns of its companion table: each row's year, total and status."""
    return [(year, total, status) for year, _, status, total in shared_cells(tree)]


def bars_of(figure: dict[str, Any]) -> dict[int, int]:
    (bars,) = [t for t in figure["data"] if t["type"] == "bar"]
    return dict(zip(bars["x"], bars["y"], strict=True))


def hovers_by_year(figure: dict[str, Any]) -> dict[int, str]:
    return {
        x: h for t in figure["data"] for x, h in zip(t["x"], t["hovertext"], strict=True)
    }


def popular_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = MOD["popular_totals"](
        rows, set(SERVED), "GA", GA_PATH
    )
    return records


class TestC10:
    def test_it_is_registered_on_the_history_page_with_the_shared_table(self) -> None:
        assert charts.CHARTS["C10"] == charts.Chart(
            "/state/<usps>", TOTALS, short_value_ticks=True
        )
        tree = render()
        figures = [f.id for f in of_type(tree, "Figure")]
        assert figures == [C7_DOM, C10_DOM] and C10_DOM == "c10"
        csv = download(tree, TOTALS)
        assert csv.header == [
            "year",
            "state_electoral_votes",
            "pv_status",
            "state_popular_total",
            "state_usps",
        ]
        assert {r["state_usps"] for r in csv.rows} == {"GA"}

    def test_its_bars_are_popular_vote_blue_on_c7_s_axis_and_margin(self) -> None:
        """#593's colors; #582 (D113(e), (f)): short value ticks, C7's year-tick size
        and the state page's one left and right margin, with no automargin."""
        tree = render()
        figure = c10_figure(tree)
        (bars,) = [t for t in figure["data"] if t["type"] == "bar"]
        assert bars["marker"]["color"] == "var(--chart-pv)"
        layout = figure["layout"]
        assert layout["xaxis"] == c7_figure(tree)["layout"]["xaxis"]
        assert layout["xaxis"]["tickfont"] == {"size": 14}
        assert layout["yaxis"]["tickformat"] == charts.SHORT_TICKFORMAT
        assert layout["yaxis"]["automargin"] is False
        margin = layout["margin"]
        assert {k: margin[k] for k in ("l", "r")} == over_time.STATE_MARGIN
        # Its own top margin stays (the template's, or the room for a label above).
        assert margin["t"] >= over_time.TOP_PX
        assert not any("text" in t for t in figure["data"])

    @pytest.mark.parametrize("usps", RECORDED_STATES)
    def test_each_year_s_bar_is_n2_s_total(self, usps: str) -> None:
        """AC2's oracle (B-1 of #582's architect review): each recorded state's N2
        totals, read straight from the recording and never through C10's collapse or
        figure builder, against the bars and hovers C10 draws from its history."""
        body = copy.deepcopy(RECORDED[f"/v1/states/{usps}"])
        content, _, _ = MOD["render"](body, copy.deepcopy(INDEX), usps)
        figure = c10_figure(content)
        bars = bars_of(figure)
        hovers = hovers_by_year(figure)
        n2 = {r["year"]: r["state_popular_total"] for r in n2_state(usps)}
        assert n2
        for year, total in n2.items():
            if total is None:
                assert year not in bars, year
            else:
                assert bars[year] == total, year
                assert labels.number(total) in hovers[year], year
        assert set(bars) == {y for y, t in n2.items() if t is not None}
        if usps == "GA":
            assert set(GA_SKIPPED_YEARS) <= set(bars)

    def test_every_n2_state_s_cells_word_its_totals(self) -> None:
        """Across the recorded N2 fixture, C10's points carry each state's N2 total
        and status and choose ``NO_STATE_TOTAL`` as the cell inside the window: the
        field mapping only, not AC2's oracle, which is
        :meth:`test_each_year_s_bar_is_n2_s_total` (each recorded state's rendered
        history). No N2 row goes through the collapse (B-1)."""
        states = {r["state_usps"] for r in N2["data"]}
        assert len(states) == 51
        for usps in sorted(states):
            n2 = n2_state(usps)
            points = over_time.total_points(n2, COVERAGE)
            assert [
                (p.year, p.total, p.total_cell, p.status, p.status_cell)
                for p in points
            ] == [
                (
                    r["year"],
                    r["state_popular_total"],
                    labels.popular_votes(
                        r["state_popular_total"],
                        r["pv_status"],
                        r["year"],
                        COVERAGE,
                        no_figure=labels.NO_STATE_TOTAL,
                    ),
                    r["pv_status"],
                    labels.pv_status(r["pv_status"]),
                )
                for r in n2
            ], usps

    @pytest.mark.parametrize("usps", RECORDED_STATES)
    def test_the_chart_equals_its_table_s_cells(self, usps: str) -> None:
        # On every recorded state (#618's AC2: GA and TX), against the table C10
        # shares with C7.
        tree = render(usps=usps)
        figure = c10_figure(tree)
        rows = download(tree, TOTALS).rows
        cells = {int(r["year"]): r for r in rows}
        assert set(cells) == set(range(HISTORIES[usps].first, 2025, 4))
        for year, value in bars_of(figure).items():
            assert cells[year]["state_popular_total"] == str(value), year
        # Each hover writes the table's cells (D091), one per drawn point.
        hovers = hovers_by_year(figure)
        assert hovers
        for shown, total, status in totals_cells(tree):
            if int(shown) in hovers:
                assert hovers[int(shown)] == labels.C10_HOVER.format(
                    year=shown,
                    state=HISTORIES[usps].name,
                    total=total,
                    pv_status=status,
                )

    def test_the_band_comes_from_coverage_never_a_literal(self) -> None:
        figure = c10_figure(render())
        (before,) = figure["layout"]["shapes"]
        low, high = components.year_edges(SERVED, 1824, WINDOW[0] - 4)
        assert (before["x0"], before["x1"]) == (low, high)
        body = ga_body()
        body["meta"]["provenance"]["coverage"]["pv_year_min"] = 1984
        (moved,) = c10_figure(render(body=body))["layout"]["shapes"]
        assert moved["x1"] == components.year_edges(SERVED, 1824, 1980)[1]
        # A year held before the window draws nothing: the band says why.
        assert 1900 not in hovers_by_year(figure)

    def test_recorded_causes_are_markers(self) -> None:
        """AC3 on recorded data: Georgia's legislature chose its electors in 1824 and
        it took no part in 1864; neither draws a bar."""
        tree = render()
        figure = c10_figure(tree)
        assert traces(figure)[labels.C5_LEGISLATURE] == [1824]
        assert traces(figure)[labels.C5_TOOK_NO_PART] == [1864]
        assert not {1824, 1864} & set(bars_of(figure))
        assert labels.C5_MARKER_NOTE in c10_caption(tree)

    @pytest.mark.parametrize(
        ("fields", "label", "cell"),
        [
            # AC3 by doctoring: no recorded year has these causes.
            (
                {"state_popular_total": None, "popular_votes": None},
                labels.C5_NO_TOTAL,
                labels.NO_STATE_TOTAL,
            ),
            ({"state_popular_total": "12"}, labels.UNRECOGNIZED, labels.UNRECOGNIZED),
            # A number no bar draws is written as served, as C5 writes it.
            ({"state_popular_total": -1}, labels.UNRECOGNIZED, labels.number(-1)),
            # One key entry for both null-total cells (D113, amendment); the cell and
            # the hover still say which it is.
            (
                {"state_popular_total": None, "popular_votes": None, "pv_status": None},
                labels.C5_NO_TOTAL,
                labels.NOT_IN_DATASET,
            ),
        ],
    )
    def test_a_missing_or_unrecognized_total_is_its_own_marker(
        self, fields: dict[str, Any], label: str, cell: str
    ) -> None:
        tree = render(body=with_year(ga_body(), 2000, **fields))
        figure = c10_figure(tree)
        assert figure is not None
        assert traces(figure)[label] == [2000]
        assert 2000 not in bars_of(figure)
        (got,) = [t for y, t, _ in totals_cells(tree) if y == "2000"]
        assert got == cell
        assert got in hovers_by_year(figure)[2000]
        symbols = {t["name"]: t["marker"]["symbol"] for t in figure["data"][1:]}
        assert symbols[label] == over_time.C10_SYMBOLS[label]

    @pytest.mark.parametrize("query", UNFILTERED_URLS)
    def test_a_query_that_applies_no_range_changes_neither_chart_nor_table(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        cached_client(monkeypatch)
        plain, tree = history_layout(), history_layout(query)
        assert c10_figure(tree) == c10_figure(plain)
        assert download(tree, TOTALS).raw == download(plain, TOTALS).raw
        assert c10_caption(tree) == c10_caption(plain)

    def test_the_caption_describes_the_series(self) -> None:
        caption = c10_caption(render())
        assert caption.startswith(labels.C5_BASIS)
        assert labels.C10_SHORT_TICKS_NOTE in caption
        assert labels.C5_BEFORE_NOTE.format(pv_year_min=WINDOW[0]) in caption
        assert labels.C5_MARKER_NOTE in caption
        # No filter sentence in a caption (#619, #620), after the marker note or
        # anywhere.
        assert_no_filter_sentence(caption)
        assert "This chart starts at" not in caption

    def test_a_later_first_election_and_a_name_that_is_not_plain_text(self) -> None:
        # #620 (D119): C10's axis starts at the state's first election with C7's, and
        # its caption shares C7's start sentence.
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] >= 1832]
        tree = render(body=body)
        assert labels.C10_TITLE_STATE.format(state="Georgia") == c10_title(tree)
        assert labels.FIRST_ELECTION_START_NOTE.format(state="Georgia", year=1832) in (
            c10_caption(tree)
        )
        years = [y for y in SERVED if y >= 1832]
        assert c10_figure(tree)["layout"]["xaxis"] == components.year_axis(years)
        for row in body["data"]:
            row["state"] = "<b>Georgia"
        tree = render(body=body)
        assert c10_title(tree) == labels.C10_TITLE_THIS_STATE
        assert labels.FIRST_ELECTION_START_NOTE_THIS_STATE.format(year=1832) in (
            c10_caption(tree)
        )
        hovers = hovers_by_year(c10_figure(tree)).values()
        assert all(charts.escaped("<b>Georgia") in h for h in hovers)

    def test_the_table_s_links_view_and_notes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        tree = history_layout("year_from=1900&candidate=jimmy-carter")
        for tr in body_rows(tree, TOTALS):
            (link,) = of_type(tr.children[0], "Link")
            assert link.href == f"/election/{link.children}"
        lines = download(tree, TOTALS).lines
        # The range applied, and never T4's moved key (#620, D119).
        assert (
            "View: https://explore.us-presidential-election-center.org/state/GA"
            "?year_from=1900"
        ) in lines
        assert labels.C5_BASIS in lines
        # C7, C10 and their one table share the page's one card (#567, #618, #619).
        card = in_one_card(tree, TOTALS, total=1)
        assert in_one_card(tree, C10_DOM, total=1) is card
        assert in_one_card(tree, C7_DOM, total=1) is card
        assert every_card(tree)[0] is card


def halves(body: dict[str, Any], usps: str) -> tuple[Any, Any]:
    """C7's and C10's halves over ``usps``'s whole history, built as ``render`` builds
    them under the default view (each collapse once, #620, D119), with no start
    sentence."""
    path = f"/v1/states/{usps}"
    rows = state_view.rows(body, usps, set(SERVED), path)
    electors_full = state_view.electors(rows, set(SERVED), usps, path)
    totals_full = MOD["popular_totals"](rows, set(SERVED), usps, path)
    return (
        MOD["_electors_part"](electors_full, rows, usps, path, None),
        MOD["_totals_part"](totals_full, rows, usps, body, path, None),
    )


class TestSharedTable:
    """The one table C7 and C10 share (#618, D117): joined on the year from the two
    collapses, each column the cells its chart's hover writes, its notes by a fixed
    rule, and a build that never takes the page down."""

    @pytest.mark.parametrize("usps", RECORDED_STATES)
    def test_c7_s_and_c10_s_status_cells_agree_every_year(self, usps: str) -> None:
        # The status column is taken from C7's points; C10's must say the same (m-5).
        body = copy.deepcopy(RECORDED[f"/v1/states/{usps}"])
        c7, c10 = halves(body, usps)
        assert c7 is not None and c10 is not None
        assert [p.year for p in c7.points] == [p.year for p in c10.points]
        assert [p.status_cell for p in c7.points] == [
            p.status_cell for p in c10.points
        ]
        merged = MOD["merge"](c7, c10)
        assert [m.status_cell for m in merged] == [
            p.status_cell or labels.UNRECOGNIZED for p in c10.points
        ]

    def test_halves_that_disagree_on_the_years_are_a_code_fault(self) -> None:
        c7, c10 = halves(ga_body(), "GA")
        assert c7 is not None and c10 is not None
        with pytest.raises(ValueError):
            MOD["merge"](c7, c10._replace(points=c10.points[1:]))
        shifted = [p._replace(year=p.year + 1) for p in c10.points]
        with pytest.raises(ValueError):
            MOD["merge"](c7, c10._replace(points=shifted))
        assert MOD["merge"](None, None) == []

    def test_its_notes_on_success(self) -> None:
        # m-4: both bases always (they define headers that stay), then the window,
        # which C10's half read; no unavailable note.
        tree = render()
        lines = download(tree, ELECTORS).lines
        window_note = labels.OVER_TIME_WINDOW_NOTE.format(
            pv_year_min=WINDOW[0], pv_year_max=WINDOW[1]
        )
        notes = [
            line
            for line in lines
            if line
            in (
                labels.C4_BASIS,
                labels.C5_BASIS,
                window_note,
                MOD["ELECTORS_UNAVAILABLE_NOTE"],
                MOD["TOTALS_UNAVAILABLE_NOTE"],
            )
        ]
        assert notes == [labels.C4_BASIS, labels.C5_BASIS, window_note]

    @pytest.mark.parametrize("field", ["state_electoral_votes", "state_popular_total"])
    @pytest.mark.parametrize("kind", sorted(SERVED_KINDS))
    def test_no_served_value_takes_the_page_down(self, field: str, kind: str) -> None:
        """I-1 (#618's architect review): the table is built after both halves'
        ``try`` blocks, so a served value either half lets through must never raise
        there. Every kind in each field of 2016's rows leaves the page, its success
        marker and the shared table, or that half's sentence with the other half's
        table."""
        body = with_year(ga_body(), 2016, **{field: SERVED_KINDS[kind]})
        tree = render(body=body)
        assert getattr(tree, "id", None) == PAGE_ID
        assert find(tree, ELECTORS) is not None
        assert len(download(tree, ELECTORS).rows) == len(body_rows(tree, ELECTORS))


class TestPopularTotals:
    """C10's collapse (#582, D113(b)): a row is skipped only when its candidate
    ``popular_votes`` and its ``state_popular_total`` are both null; every other row's
    total is read, and those must be one value."""

    def rows(self) -> list[dict[str, Any]]:
        return state_view.rows(ga_body(), "GA", set(SERVED), GA_PATH)

    def test_a_null_null_row_beside_figures_is_skipped(self) -> None:
        records = {r["year"]: r for r in popular_totals(self.rows())}
        for year in GA_SKIPPED_YEARS:
            (figure,) = {
                r["state_popular_total"]
                for r in self.rows()
                if r["year"] == year and r["popular_votes"] is not None
            }
            assert records[year]["state_popular_total"] == figure, year

    def test_a_year_where_every_row_is_skipped_reads_a_null_total(self) -> None:
        records = {r["year"]: r for r in popular_totals(self.rows())}
        assert records[1972]["state_popular_total"] is None
        assert records[1824]["pv_status"] == "legislature_chosen"
        assert sorted(records) == SERVED

    def test_a_different_total_on_a_row_with_no_figure_is_read(self) -> None:
        rows = self.rows()
        (skipped,) = [
            r for r in rows if r["year"] == 1988 and r["popular_votes"] is None
        ]
        skipped["state_popular_total"] = 1
        with pytest.raises(TypeError, match="two values of state_popular_total"):
            popular_totals(rows)

    def test_a_figure_row_with_a_null_total_is_refused(self) -> None:
        rows = self.rows()
        (first, *_) = [r for r in rows if r["year"] == 1988 and r["popular_votes"]]
        first["state_popular_total"] = None
        with pytest.raises(TypeError, match="figure with no state_popular_total"):
            popular_totals(rows)

    def test_a_lone_figure_row_with_a_null_total_is_refused(self) -> None:
        """D113, amendment (wording.5): the year's only row read, with a candidate
        figure and no total, refuses rather than reading a null total."""
        rows = [
            r
            for r in self.rows()
            if r["year"] != 1988 or r["popular_votes"] is not None
        ]
        (only, *rest) = [r for r in rows if r["year"] == 1988]
        rows = [r for r in rows if r not in rest]
        only["state_popular_total"] = None
        with pytest.raises(TypeError, match="figure with no state_popular_total"):
            popular_totals(rows)

    @pytest.mark.parametrize("total", ["", 0, float("nan")])
    def test_a_blank_zero_or_nan_total_is_read_never_skipped(self, total: Any) -> None:
        # ``is None`` on the total's side too (ge.1): a row with no candidate figure
        # whose total is a value, not a null, is read, and differs from the figure.
        rows = self.rows()
        (skipped,) = [
            r for r in rows if r["year"] == 1988 and r["popular_votes"] is None
        ]
        skipped["state_popular_total"] = total
        with pytest.raises(TypeError, match="two values of state_popular_total"):
            popular_totals(rows)

    @pytest.mark.parametrize("value", ["", float("nan")])
    def test_a_blank_or_nan_figure_is_read_never_skipped(self, value: Any) -> None:
        # ``is None``, never ``is_blank``: a blank or NaN ``popular_votes`` is a value,
        # so the row is read, and a figure with no total refuses.
        rows = self.rows()
        (skipped,) = [
            r for r in rows if r["year"] == 1988 and r["popular_votes"] is None
        ]
        skipped["popular_votes"] = value
        with pytest.raises(TypeError, match="figure with no state_popular_total"):
            popular_totals(rows)

    def test_a_row_without_popular_votes_is_refused(self) -> None:
        rows = self.rows()
        del rows[0]["popular_votes"]
        with pytest.raises(KeyError):
            popular_totals(rows)

    def test_the_states_recording_s_premise(self) -> None:
        """The rule's premise in the recording (I-6): a recorded state's row carries no
        total exactly when it carries no candidate figure. A re-recording that changes
        the field's meaning fails here, not silently in the oracle."""
        for usps in RECORDED_STATES:
            for row in RECORDED[f"/v1/states/{usps}"]["data"]:
                assert (row["popular_votes"] is None) == (
                    row["state_popular_total"] is None
                ), (usps, row["year"], row["candidate"])


class TestC10Degraded:
    """AC5 as #618 keeps it (owner's ruling, D117): a body whose total popular vote C10
    cannot read as one per election puts :data:`C10_UNAVAILABLE` in C10's place, with
    no chart and no ``c10`` id, and the shared table's total column reads unavailable
    with :data:`TOTALS_UNAVAILABLE_NOTE` first among its notes and no window note,
    while C7 (exactly as it was), the headline figures, the electors and status
    columns, the section links and the page's success marker stay (D113(c)). Since
    T4 left the page (#619, D118), a missing popular-vote bound still degrades the
    whole history page, and a present malformed one C10 alone."""

    def assert_degraded(self, body: dict[str, Any]) -> None:
        plain = render()
        tree = render(body=body)
        assert getattr(tree, "id", None) == PAGE_ID
        assert find(tree, MOD["C10_UNAVAILABLE_ID"]) is not None
        assert c10_figure(tree) is None
        assert find(tree, C10_DOM) is None
        assert [f.id for f in of_type(tree, "Figure")] == [C7_DOM]
        assert c7_figure(tree) == c7_figure(plain)
        metrics = find(tree, MOD["METRICS_ID"])
        assert metrics is not None
        assert texts(metrics) == texts(find(plain, MOD["METRICS_ID"]))
        assert_column_unavailable(
            tree, plain, "state_popular_total", MOD["TOTALS_UNAVAILABLE_NOTE"]
        )
        for field in ("year", "state_electoral_votes", "pv_status", "state_usps"):
            assert column(tree, field) == column(plain, field), field
        assert [c[:3] for c in shared_cells(tree)] == [
            c[:3] for c in shared_cells(plain)
        ]
        window_note = labels.OVER_TIME_WINDOW_NOTE.format(
            pv_year_min=WINDOW[0], pv_year_max=WINDOW[1]
        )
        assert window_note in download(plain, ELECTORS).lines
        assert window_note not in download(tree, ELECTORS).lines
        assert window_note not in texts(tree)
        assert find(tree, state_view.SECTIONS_ID) is not None
        assert find(tree, MOD["ELECTORS_TABLE_UNAVAILABLE_ID"]) is None
        headings = [h.children for h in of_type(tree, "H2")]
        assert MOD["C10_HEADING"] in headings
        card = in_one_card(tree, MOD["C10_UNAVAILABLE_ID"], total=1)
        assert every_card(tree) == [card]

    def test_two_totals_in_one_election(self) -> None:
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 2016]
        first["state_popular_total"] = 99
        self.assert_degraded(body)

    def test_a_figure_row_with_a_null_total_beside_the_figure(self) -> None:
        body = ga_body()
        (first, *_) = [
            r for r in body["data"] if r["year"] == 2016 and r["popular_votes"]
        ]
        first["state_popular_total"] = None
        self.assert_degraded(body)

    @pytest.mark.parametrize("window", [(2000, 1990), (True, 2024), (1976, 1976.5)])
    def test_a_malformed_popular_vote_window(self, window: tuple[Any, Any]) -> None:
        """cr.1: C10 checks the window as C2 and C5 do (``query.year_span``), so an
        inverted or mistyped one degrades C10 alone, never a self-contradicting
        caption."""
        body = ga_body()
        coverage = body["meta"]["provenance"]["coverage"]
        coverage["pv_year_min"], coverage["pv_year_max"] = window
        self.assert_degraded(body)
        # Accepted leftover (#618's architect review, m-1; D117): the file still
        # carries a popular-vote field, so its preamble writes the window as served.
        lines = download(render(body=body), ELECTORS).lines
        assert f"Popular votes cover {window[0]}–{window[1]}" in lines

    @pytest.mark.parametrize("window", [(1976, "2024"), (None, 2024)])
    def test_a_window_t4_cannot_compare_degrades_c10_here_and_t4_s_page(
        self, window: tuple[Any, Any]
    ) -> None:
        """Before #619 T4's popular-vote cells compared each year with the window on
        this page, so such a window degraded it. T4 has left (D118): here it is a
        present malformed bound, C10's alone; the results page, which checks the
        window before any cell, degrades whole."""
        body = ga_body()
        coverage = body["meta"]["provenance"]["coverage"]
        coverage["pv_year_min"], coverage["pv_year_max"] = window
        self.assert_degraded(copy.deepcopy(body))
        with pytest.raises(TypeError):
            RS_MOD["render"](body, copy.deepcopy(INDEX), "GA", [])

    @pytest.mark.parametrize("bound", ["pv_year_min", "pv_year_max"])
    def test_a_missing_window_bound_degrades_the_whole_page(
        self, monkeypatch: pytest.MonkeyPatch, bound: str
    ) -> None:
        """#629's review, cr.1 (D117 as amended, D118): ``render`` reads both bounds
        before either half, so a missing one is the page's, whatever URL reached it:
        the routed page shows the degraded state, with or without the keys it read
        before #619."""
        body = ga_body()
        del body["meta"]["provenance"]["coverage"][bound]
        with pytest.raises(KeyError):
            render(body=copy.deepcopy(body))
        serve_history(monkeypatch, body)
        for search in ("", "?year_from=1824&year_to=1824"):
            ids = routed_ids(route("/state/GA", search))
            assert "unavailable" in ids and PAGE_ID not in ids, search

    @pytest.mark.parametrize("bound", ["pv_year_min", "pv_year_max"])
    def test_a_missing_bound_degrades_the_page_where_nothing_else_reads_it(
        self, bound: str
    ) -> None:
        """The mechanism, not only the outcome: with both halves failed (two statuses in
        1900) there is no shared table, so no download preamble reads the window; only
        ``render``'s own read makes a missing bound the page's (D117 as amended)."""
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["pv_status"] = "legislature_chosen"
        kept = render(body=copy.deepcopy(body))
        assert getattr(kept, "id", None) == PAGE_ID
        assert find(kept, ELECTORS) is None
        del body["meta"]["provenance"]["coverage"][bound]
        with pytest.raises(KeyError):
            render(body=body)

    def test_a_present_malformed_bound_degrades_c10_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#629's review, cr.1: a bound that is present and malformed stays C10's half's
        to refuse, so the page, C7 and the shared table stay, whatever URL reached
        it."""
        body = ga_body()
        coverage = body["meta"]["provenance"]["coverage"]
        coverage["pv_year_min"], coverage["pv_year_max"] = (2000, 1990)
        tree = render(body=copy.deepcopy(body))
        assert getattr(tree, "id", None) == PAGE_ID
        assert find(tree, MOD["C10_UNAVAILABLE_ID"]) is not None
        assert c7_figure(tree) is not None
        assert find(tree, ELECTORS) is not None
        assert set(column(tree, "state_popular_total")) == {""}
        serve_history(monkeypatch, body)
        content = history_layout("year_from=1824&year_to=1824&pv_status=popular_vote")
        assert content.id == PAGE_ID
        assert find(content, MOD["C10_UNAVAILABLE_ID"]) is not None
        assert find(content, ELECTORS) is not None

    def test_a_row_without_the_total(self) -> None:
        body = ga_body()
        for row in body["data"]:
            if row["year"] == 2016:
                del row["state_popular_total"]
        self.assert_degraded(body)

    def test_two_statuses_degrade_both_charts(self) -> None:
        """D113(c): ``pv_status`` is read by both, so its disagreement degrades both."""
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["pv_status"] = "legislature_chosen"
        tree = render(body=body)
        assert getattr(tree, "id", None) == PAGE_ID
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert find(tree, MOD["C10_UNAVAILABLE_ID"]) is not None
        assert of_type(tree, "Figure") == []
        # Neither half was built, so the shared table gives way to its note (#618).
        assert find(tree, ELECTORS) is None
        assert find(tree, MOD["ELECTORS_TABLE_UNAVAILABLE_ID"]) is not None
        # The page stays, with its section links.
        assert find(tree, state_view.SECTIONS_ID) is not None

    def test_the_try_never_wraps_the_chart_call(self) -> None:
        """D095(f): ``components.chart`` is called after both halves' ``try`` blocks,
        never in one, so a figure the chart rules refuse is logged, never swallowed as
        a chart that could not be built (#618: C7's half as well as C10's)."""
        for name in ("_electors_part", "_totals_part"):
            tree = ast.parse(inspect.getsource(MOD[name]).lstrip())
            (handler,) = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
            assert [
                n
                for n in ast.walk(ast.Module(body=handler.body, type_ignores=[]))
                if isinstance(n, ast.Attribute) and n.attr == "chart"
            ] == [], name
        section = ast.parse(inspect.getsource(MOD["_charts_section"]).lstrip())
        assert [n for n in ast.walk(section) if isinstance(n, ast.Try)] == []
        calls = [
            n
            for n in ast.walk(section)
            if isinstance(n, ast.Attribute)
            and n.attr == "chart"
            and isinstance(n.value, ast.Name)
            and n.value.id == "components"
        ]
        assert len(calls) == 2


class TestStateSeries:
    """The one-state ordering and gap rule C7 uses (#560), which C4's ``n2_rows``
    shared until #562 (D107)."""

    def test_rows_in_year_order_from_the_first(self) -> None:
        got = over_time.state_series(
            {1832: "b", 1828: "a", 1836: "c"}, [1824, 1828, 1832, 1836], "src", "GA"
        )
        assert got == ["a", "b", "c"]

    def test_a_gap_or_no_row_is_refused(self) -> None:
        with pytest.raises(TypeError, match="skips a year for GA"):
            over_time.state_series(
                {1824: "a", 1832: "c"}, [1824, 1828, 1832], "s", "GA"
            )
        with pytest.raises(TypeError, match="in a year not served"):
            over_time.state_series({1824: "a", 1826: "b"}, [1824, 1828], "s", "GA")
        with pytest.raises(TypeError, match="has no row for GA"):
            over_time.state_series({}, [1824], "s", "GA")


# --- the N2 recording, C7's oracle (#562's review, cr.4) ------------------------------

_N1: dict[str, Any] = RECORDED["/v1/elections/summary"]
N2_FIXTURE_N1_ITEMS = {item["year"]: item for item in _N1["elections"]}
N2_FIXTURE_N1_TOTALS = {
    row["year"]: row["national_pv_denominator"] for row in _N1["data"]
}
N2_FIXTURE_PV = (
    INDEX["meta"]["provenance"]["coverage"]["pv_year_min"],
    INDEX["meta"]["provenance"]["coverage"]["pv_year_max"],
)


class TestN2Fixture:
    """The N2 recording's own integrity (#436; moved here by #562's review, cr.4): no
    page reads N2 since #562 (D107), but it is C7's reconciliation oracle above, so a
    re-recording with a repeated row or a year that disagrees with N1 fails here."""

    def test_one_snapshot_with_the_index(self) -> None:
        assert N2["meta"]["provenance"] == INDEX["meta"]["provenance"]

    def test_count_and_no_repeat(self) -> None:
        assert N2["meta"]["count"] == len(N2["data"])
        keys = [(r["year"], r["state_usps"]) for r in N2["data"]]
        assert len(keys) == len(set(keys))

    @pytest.mark.parametrize("usps", ["GA", "TX"])
    def test_each_state_equals_its_state_history(self, usps: str) -> None:
        # #641's AC2, per year: N2's allotment and status for each year equal the
        # state history's, and the two hold the same years, both ways (TX since #641).
        history: dict[int, list[dict[str, Any]]] = {}
        for r in RECORDED[f"/v1/states/{usps}"]["data"]:
            history.setdefault(r["year"], []).append(r)
        mine = [r for r in N2["data"] if r["state_usps"] == usps]
        assert {r["year"] for r in mine} == set(history)
        for row in mine:
            for candidate_row in history[row["year"]]:
                assert (
                    row["state_electoral_votes"]
                    == candidate_row["state_electoral_votes"]
                )
                assert row["pv_status"] == candidate_row["pv_status"]

    def test_each_per_capita_recording_on_the_shared_fields(self) -> None:
        shared = (
            "state",
            "governing_census_year",
            "state_electoral_votes",
            "population",
            "persons_per_electoral_vote",
        )
        by_key = {(r["year"], r["state_usps"]): r for r in N2["data"]}
        checked = 0
        for path, body in RECORDED.items():
            if not (path.startswith("/v1/elections/") and path.endswith("/per-capita")):
                continue
            for row in body["data"]:
                key = (row["year"], row["state_usps"])
                assert {f: by_key[key][f] for f in shared} == {
                    f: row[f] for f in shared
                }, key
                checked += 1
        assert checked > 0

    def test_each_year_sums_to_n1(self) -> None:
        """A test-side integrity check of the recordings; the dashboard sums nothing."""
        for year, item in N2_FIXTURE_N1_ITEMS.items():
            year_rows = [r for r in N2["data"] if r["year"] == year]
            assert (
                sum(r["state_electoral_votes"] for r in year_rows)
                == (item["electoral_denominator"])
            ), year
            totals = [r["state_popular_total"] for r in year_rows]
            if N2_FIXTURE_PV[0] <= year <= N2_FIXTURE_PV[1]:
                assert sum(totals) == N2_FIXTURE_N1_TOTALS[year], year
            else:
                assert set(totals) == {None}, year


# --- the per-capita page's headline figures (#600, D112(d), D114) -----------------------

PC_FIGURES = PC_MOD["METRICS_ID"]
PC_FIGURE_IDS: dict[str, str] = PC_MOD["METRIC_IDS"]
LOWEST, HIGHEST = "state_per_capita_lowest", "state_per_capita_highest"


def pc_figure(tree: Any, key: str) -> str:
    dd = find(tree, PC_FIGURE_IDS[key])
    assert dd is not None, key
    return "".join(texts(dd))


def pc_cells(tree: Any) -> dict[int, str]:
    """T7's people-per-electoral-vote cell by year."""
    table = find(tree, PER_CAPITA)
    assert table is not None
    column = 1 + list(labels.PER_CAPITA_FIELDS).index("persons_per_electoral_vote")
    return {
        int(" ".join(texts(row[0]))): " ".join(texts(row[column]))
        for row in [list(tr.children) for tr in of_type(of_type(table, "Tbody"), "Tr")]
    }


class TestPerCapitaFigures:
    @pytest.mark.parametrize(
        ("usps", "lowest", "highest"),
        [
            (
                "GA",
                "37,888 in 1824 and 1828, among 50 elections with a figure (1824–2024)",
                "669,494 in 2024, among 50 elections with a figure (1824–2024)",
            ),
            (
                "TX",
                "53,148 in 1852, 1856 and 1860, among 42 elections with a figure "
                "(1852–2024)",
                "728,638 in 2024, among 42 elections with a figure (1852–2024)",
            ),
        ],
    )
    def test_the_hand_counts(self, usps: str, lowest: str, highest: str) -> None:
        # #569's plan recordings (GA 37,887.67 tied in 1824 and 1828; TX 53,148.0 in
        # 1852, 1856 and 1860; TX null in 1848, 1864, 1868), as T7 writes each value.
        tree = pc_render(usps=usps)
        assert pc_figure(tree, LOWEST) == lowest
        assert pc_figure(tree, HIGHEST) == highest

    @pytest.mark.parametrize(
        ("usps", "query"),
        [
            ("GA", ""),
            ("TX", ""),
            ("GA", "year_from=1900&year_to=1960"),
            ("TX", "year_from=1856"),
        ],
    )
    def test_each_figure_is_its_years_t7_cells(self, usps: str, query: str) -> None:
        # D097(a)'s reconcile clause, and the tie by cell (owner at the plan gate):
        # every year named shows the figure's cell, and no other year shown does.
        tree = pc_render(query, usps=usps)
        cells = pc_cells(tree)
        for key in (LOWEST, HIGHEST):
            text = pc_figure(tree, key)
            value, years = text.split(" in ", 1)
            named = [int(y) for y in re.findall(r"\d{4}", years.split(", among")[0])]
            assert named and all(cells[y] == value for y in named), (key, text)
            assert sorted(y for y, c in cells.items() if c == value) == named

    def test_the_year_range_narrows_them(self) -> None:
        tree = pc_render("year_from=1900&year_to=1960")
        cells = pc_cells(tree)
        assert set(cells) == set(range(1900, 1961, 4))
        assert "among 16 elections with a figure (1900–1960)" in pc_figure(tree, LOWEST)

    def test_one_year_keeps_both_figures_and_shows_one_value(self) -> None:
        tree = pc_render("year_from=2000&year_to=2000")
        assert pc_figure(tree, LOWEST).endswith(
            " in 2000, the only election shown with a figure"
        )
        assert pc_figure(tree, HIGHEST) == labels.METRIC_SELECT_SAME.format(
            other="lowest", year=2000
        )

    def test_every_value_null_names_no_cause(self) -> None:
        # TX 1864–1868: no electoral votes, so no figure in any year shown (I4).
        tree = pc_render("year_from=1864&year_to=1868", usps="TX")
        for key in (LOWEST, HIGHEST):
            assert pc_figure(tree, key) == labels.METRIC_NO_FIGURE[key]

    def test_a_range_with_no_election_for_the_state_says_so(self) -> None:
        # TX's first election is 1848; the slider spans the dataset (I4).
        tree = pc_render("year_from=1824&year_to=1844", usps="TX")
        for key in (LOWEST, HIGHEST):
            assert pc_figure(tree, key) == labels.METRIC_NO_FIGURE_NO_ELECTIONS

    @pytest.mark.parametrize("value", ["x", True, -5.0, float("nan")])
    def test_a_value_no_figure_can_show_makes_both_unrecognized_and_keeps_t7(
        self, value: Any
    ) -> None:
        # Architect I1 and Q4 (D114): one selection, so both figures read it; T7 and
        # the page stay, the one read being the figures' only input.
        body = ga_per_capita()
        body["data"][3]["persons_per_electoral_vote"] = value
        tree = pc_render(per_capita=body)
        for key in (LOWEST, HIGHEST):
            assert pc_figure(tree, key) == labels.UNRECOGNIZED
            assert find(tree, PC_FIGURE_IDS[key]).title == labels.UNRECOGNIZED_NOTE
        assert find(tree, PER_CAPITA) is not None and tree.id == PC_PAGE_ID

    @pytest.mark.parametrize("index", [0, -1])
    def test_a_body_naming_a_year_twice_degrades_the_page(
        self, index: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Owner at #609's review (r1.cr.1, D114(g)): a repeated year is a malformed
        # body, which degrades the page, never an uncaught error; the doubled row here
        # is 1824 (a tied lowest) or 2024 (the highest).
        body = ga_per_capita()
        body["data"].append(copy.deepcopy(body["data"][index]))
        with pytest.raises(TypeError, match="names a year twice"):
            pc_render(per_capita=body)
        # Through the layout: the degraded page, not an exception.
        monkeypatch.setitem(RECORDED, GA_PER_CAPITA_PATH, body)
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route("/state/GA/per-capita"))
        assert PC_PAGE_ID not in ids and PC_FIGURES not in ids
        assert "unavailable" in ids

    def test_they_sit_in_the_card_after_the_year_control_and_before_the_count(
        self,
    ) -> None:
        tree = pc_render()
        card = in_one_card(tree, PC_FIGURES)
        order = [
            getattr(n, "id", None) or getattr(n, "className", None)
            for n in components._within(card.children)
        ]
        assert (
            order.index(PC_MOD["YEARS_ID"])
            < order.index(PC_FIGURES)
            < order.index("count")
        )

    def test_the_page_still_makes_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route("/state/GA/per-capita"))
        assert PC_FIGURES in ids and all(i in ids for i in PC_FIGURE_IDS.values())
        assert calls == [GA_PER_CAPITA_PATH]


METRICS_MODULE = MOD["metrics"]

# The state history's headline figures (#601, D112(e), (g), D115).
ST_FIGURES = MOD["METRICS_ID"]
ST_FIGURE_IDS: dict[str, str] = MOD["METRIC_IDS"]
ELECTIONS_COUNT = "state_elections_count"
TOOK_OFFICE = "state_took_office_count"


def st_figure(tree: Any, key: str) -> str:
    dd = find(tree, ST_FIGURE_IDS[key])
    assert dd is not None, key
    return "".join(texts(dd))


def took_office_row(body: dict[str, Any], year: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = [
        r for r in body["data"] if r["year"] == year and r["took_office"]
    ]
    (row,) = rows
    return row


class TestStateFigures:
    def test_the_hand_counts(self) -> None:
        # #569's plan recordings: GA has rows in 51 years, 50 with electors appointed
        # (1864's allotment is 0); the candidate who took office got at least one of
        # its cast votes in 27 of them. GA has no split delegation, so comparing
        # ``electoral_votes`` with ``state_electoral_votes`` also gives 27 over these 50
        # years (28 only with 1864 included, 0 == 0); that mistake is caught by
        # ``test_a_split_delegation_counts`` (#612's review, r1.ge.3).
        tree = render()
        assert st_figure(tree, ELECTIONS_COUNT) == "50 elections (1824–2024)"
        assert st_figure(tree, TOOK_OFFICE) == "27 of 50 elections (1824–2024)"
        note = find(tree, MOD["METRICS_NOTE_ID"])
        assert " ".join(texts(note)) == labels.METRIC_ZERO_ALLOTMENT_NOTE.format(
            years="1864"
        )

    def test_the_count_reconciles_to_c7_s_table(self) -> None:
        # D112(g): unfiltered, so the count is C7's companion table's rows whose
        # allotment is above 0, and the note's years those at 0.
        tree = render()
        cells = body_cells(tree)
        nonzero = [int(year) for year, appointed, _ in cells if appointed != "0"]
        zero = [int(year) for year, appointed, _ in cells if appointed == "0"]
        assert len(cells) == 51 and zero == [1864]
        assert st_figure(tree, ELECTIONS_COUNT) == (
            f"{len(nonzero)} elections ({nonzero[0]}–{nonzero[-1]})"
        )

    @pytest.mark.parametrize(
        "query",
        [
            "year_from=1900&year_to=1960",
            "candidate=andrew-jackson",
            "pv_status=popular_vote",
        ],
    )
    def test_a_filtered_url_renders_the_same_figures(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        """AC3 (#620, D119; the owner's ruling at the plan gate): the figures read the
        state's whole history whatever the URL holds, T4's moved keys (D118) or the
        history page's own year range, which narrows C7, C10 and their table but never
        the figures; while it does, :data:`labels.METRIC_ALL_YEARS_NOTE` follows them.
        Through the layout as the router calls it. The same query does narrow T4 on
        the results page, so it is a real filter, not one the parser drops."""
        cached_client(monkeypatch)
        plain, filtered = history_layout(), history_layout(query)
        for key in ST_FIGURE_IDS:
            assert st_figure(filtered, key) == st_figure(plain, key), (query, key)
        narrowed = query.startswith("year_")
        note = [labels.METRIC_ALL_YEARS_NOTE] if narrowed else []
        assert texts(find(filtered, ST_FIGURES)) == [
            *texts(find(plain, ST_FIGURES)),
            *note,
        ]
        assert (find(filtered, MOD["METRICS_ALL_YEARS_ID"]) is not None) is narrowed
        assert find(plain, MOD["METRICS_ALL_YEARS_ID"]) is None
        if narrowed:
            # The range does narrow the table, so the note is true.
            assert len(body_rows(filtered, ELECTORS)) < len(body_rows(plain, ELECTORS))
        results = RS_MOD["layout"](usps="GA", **parse(query))
        unfiltered = RS_MOD["layout"](usps="GA")
        assert texts(find(results, RESULTS)) != texts(find(unfiltered, RESULTS))

    @pytest.mark.parametrize(
        "change",
        [
            "no took-office row",
            "two took-office rows",
            "null",
            "missing",
            "a number",
            "zero",
            "blank",
        ],
    )
    def test_a_took_office_fault_makes_that_figure_alone_unrecognized(
        self, change: str
    ) -> None:
        # Architect I3 (D115): the flag figure alone reads it; the count, C7, the
        # shared table and the page stay, so nothing it reads reaches C7's section's except.
        body = ga_body()
        row = took_office_row(body, 1828)
        other = next(
            r for r in body["data"] if r["year"] == 1828 and not r["took_office"]
        )
        if change == "no took-office row":
            row["took_office"] = False
        elif change == "two took-office rows":
            other["took_office"] = True
        elif change == "null":
            other["took_office"] = None
        elif change == "missing":
            del other["took_office"]
        elif change == "zero":
            # Falsy and no bool (#612's review, r1.ge.1): never read as False.
            other["took_office"] = 0
        elif change == "blank":
            other["took_office"] = ""
        else:
            other["took_office"] = 1
        tree = render(body=body)
        assert st_figure(tree, TOOK_OFFICE) == labels.UNRECOGNIZED
        assert find(tree, ST_FIGURE_IDS[TOOK_OFFICE]).title == labels.UNRECOGNIZED_NOTE
        assert st_figure(tree, ELECTIONS_COUNT) == "50 elections (1824–2024)"
        # #621's three figures stay too (#635's review, cr.7).
        assert st_figure(tree, "state_first_election") == (
            "1824, with 9 electors appointed"
        )
        assert st_figure(tree, "state_pv_elections_count") == (
            "49 of 50 elections (1824–2024)"
        )
        assert st_figure(tree, "state_electors_change") == (
            "+7, from 9 in 1824 to 16 in 2024"
        )
        assert c7_figure(tree) is not None
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is None
        assert tree.id == PAGE_ID and find(tree, ELECTORS) is not None

    @pytest.mark.parametrize("votes", [3.0, True, -1, "x"])
    def test_a_took_office_vote_no_count_can_read_is_unrecognized(
        self, votes: Any
    ) -> None:
        body = ga_body()
        took_office_row(body, 1828)["electoral_votes"] = votes
        tree = render(body=body)
        assert st_figure(tree, TOOK_OFFICE) == labels.UNRECOGNIZED
        assert st_figure(tree, ELECTIONS_COUNT) == "50 elections (1824–2024)"

    @pytest.mark.parametrize("votes", [None, "", " "])
    def test_a_null_took_office_vote_is_left_out_of_n(self, votes: Any) -> None:
        # D112(a) as amended, architect I5: a null is never read as false; N drops.
        body = ga_body()
        row = took_office_row(body, 2024)
        assert row["electoral_votes"] > 0  # a year counted among the 27
        row["electoral_votes"] = votes
        tree = render(body=body)
        assert st_figure(tree, TOOK_OFFICE) == "26 of 49 elections (1824–2020)"
        assert st_figure(tree, ELECTIONS_COUNT) == "50 elections (1824–2024)"

    def test_every_took_office_vote_null_names_no_cause(self) -> None:
        body = ga_body()
        for row in body["data"]:
            if row["took_office"]:
                row["electoral_votes"] = None
        tree = render(body=body)
        assert st_figure(tree, TOOK_OFFICE) == labels.METRIC_NO_FIGURE[TOOK_OFFICE]

    def test_a_split_delegation_counts(self) -> None:
        # D112(e): any cast vote for the candidate who took office counts. GA 1828's
        # took-office row set to one vote of its allotment still counts.
        body = ga_body()
        row = took_office_row(body, 1828)
        before = st_figure(render(body=copy.deepcopy(body)), TOOK_OFFICE)
        row["electoral_votes"] = 1
        assert row["state_electoral_votes"] > 1
        assert st_figure(render(body=body), TOOK_OFFICE) == before

    @pytest.mark.parametrize("value", [9.0, None, -1, "x", True])
    def test_an_allotment_no_count_can_read_makes_every_figure_unrecognized_and_keeps_c7(
        self, value: Any
    ) -> None:
        # Architect I4 (D115): set on every row of 1828, so C7's collapse holds one
        # value; C7 draws it as a marker and stays, as the shared table and the page
        # do.
        body = ga_body()
        for row in body["data"]:
            if row["year"] == 1828:
                row["state_electoral_votes"] = value
        tree = render(body=body)
        for key in ST_FIGURE_IDS:
            assert st_figure(tree, key) == labels.UNRECOGNIZED, key
        assert find(tree, MOD["METRICS_NOTE_ID"]) is None
        assert c7_figure(tree) is not None
        assert tree.id == PAGE_ID and find(tree, ELECTORS) is not None

    def test_a_collapse_fault_removes_them_with_c7(self) -> None:
        # D112(c)'s precedent: C7's collapse is their input, so two allotments in one
        # year degrade C7's section and the figures go with it; the shared table
        # stays, its electors column unavailable.
        body = ga_body()
        rows_1828 = [r for r in body["data"] if r["year"] == 1828]
        rows_1828[0]["state_electoral_votes"] += 1
        tree = render(body=body)
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert find(tree, ST_FIGURES) is None
        assert find(tree, ELECTORS) is not None
        assert set(column(tree, "state_electoral_votes")) == {""}

    def test_no_year_with_electors_says_so_for_every_figure(self) -> None:
        body = ga_body()
        for row in body["data"]:
            row["state_electoral_votes"] = 0
        tree = render(body=body)
        for key in ST_FIGURE_IDS:
            assert st_figure(tree, key) == labels.METRIC_NO_FIGURE_NO_ELECTORS, key
        assert find(tree, MOD["METRICS_NOTE_ID"]) is None

    def test_one_year_with_electors_names_its_year(self) -> None:
        body = ga_body()
        for row in body["data"]:
            if row["year"] != 1828:
                row["state_electoral_votes"] = 0
        tree = render(body=body)
        assert st_figure(tree, ELECTIONS_COUNT) == "1 election (1828)"
        assert st_figure(tree, TOOK_OFFICE).endswith(" of 1 election (1828)")

    def test_the_count_is_metrics_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # #612's review (r2.recheck.1, D097, D115 amendment): the count is computed in
        # ``metrics``, over the distinct years, and ``labels`` only words it.
        seen: list[Any] = []

        def count(rows: Any) -> int:
            seen.append(rows)
            return 7

        monkeypatch.setattr(METRICS_MODULE, "count", count)
        tree = render()
        assert st_figure(tree, ELECTIONS_COUNT) == "7 elections (1824–2024)"
        assert [len(s) for s in seen] == [50] and all(isinstance(s, set) for s in seen)

    def test_they_open_c7_s_card_above_the_filter(self) -> None:
        """#634 (D122): the figures are the card's first child, before the Years
        filter's box and so before C7's heading and C7."""
        tree = render()
        card = in_one_card(tree, ST_FIGURES, total=1)
        held = list(card.children)
        assert held[0].id == ST_FIGURES
        assert "filters" in held[1].className.split()
        assert find(held[1], YEARS) is not None
        assert find(held[2:], charts.dom_id(MOD["C7_ID"])) is not None

    def test_the_page_still_makes_the_same_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route("/state/GA"))
        assert ST_FIGURES in ids and all(i in ids for i in ST_FIGURE_IDS.values())
        assert calls == [GA_PATH]


# --- the Years filter (#620, D119) ------------------------------------------------------

NO_MATCH = MOD["NO_MATCH_ID"]
ALL_YEARS = MOD["METRICS_ALL_YEARS_ID"]
YEARS = MOD["YEARS_ID"]


def slider_of(tree: Any) -> Any:
    (slider,) = of_type(tree, "RangeSlider")
    assert slider.id == YEARS
    return slider


def xs_of(figure: dict[str, Any]) -> set[int]:
    """Every year a figure's traces draw a point at."""
    return {x for t in figure["data"] for x in t.get("x", []) if x is not None}


def table_years(tree: Any) -> list[int]:
    return [int(y) for y, _, _ in body_cells(tree)]


def zeroed(body: dict[str, Any], *years: int) -> dict[str, Any]:
    """``body`` with no electors appointed in ``years``, on every row of each, so C7's
    collapse reads one zero there and the state's first election moves past them."""
    for year in years:
        with_year(body, year, state_electoral_votes=0)
    return body


FIRST = "state_first_election"
PV_COUNT = "state_pv_elections_count"
CHANGE = "state_electors_change"


def set_year(body: dict[str, Any], year: int, field: str, value: Any) -> None:
    """Set ``field`` to ``value`` on every row of ``year``, so a collapse holds one
    value for it."""
    rows = [r for r in body["data"] if r["year"] == year]
    assert rows, year
    for row in rows:
        row[field] = value


def collapse(usps: str, body: Any = None) -> list[dict[str, Any]]:
    """C7's collapse of ``usps``'s recorded history (or ``body``), as the page runs it."""
    path = f"/v1/states/{usps}"
    served = set(state_view.served_years(INDEX))
    source = copy.deepcopy(RECORDED[path] if body is None else body)
    records: list[dict[str, Any]] = state_view.electors(
        state_view.rows(source, usps, served, path), served, usps, path
    )
    return records


class TestFurtherStateFigures:
    """The state history's first election, its elections with a popular vote held and
    the change in its electors (#621, D120), computed by
    ``state_view.history_figures`` and worded by ``labels``."""

    @pytest.mark.parametrize(
        ("usps", "expected"),
        [
            # Plan-time hand reads of the recordings (#621's plan): GA rows 1824–2024,
            # 1864's allotment 0 (not participating), 1824's electors chosen by the
            # legislature; TX rows 1848–2024, 1864 and 1868 at 0.
            (
                "GA",
                {
                    FIRST: "1824, with 9 electors appointed",
                    PV_COUNT: "49 of 50 elections (1824–2024)",
                    CHANGE: "+7, from 9 in 1824 to 16 in 2024",
                },
            ),
            (
                "TX",
                {
                    FIRST: "1848, with 4 electors appointed",
                    PV_COUNT: "43 of 43 elections (1848–2024)",
                    CHANGE: "+36, from 4 in 1848 to 40 in 2024",
                },
            ),
        ],
    )
    def test_the_hand_values(self, usps: str, expected: dict[str, str]) -> None:
        tree = render(usps=usps)
        for key, text in expected.items():
            assert st_figure(tree, key) == text, key

    def test_the_figures_show_in_the_approved_order(self) -> None:
        # ba's order, approved at #621's plan gate: elections, first election, popular
        # vote, change, took office.
        assert list(ST_FIGURE_IDS) == [
            ELECTIONS_COUNT,
            FIRST,
            PV_COUNT,
            CHANGE,
            TOOK_OFFICE,
        ]
        tree = render()
        dds = [
            dd.id for dd in of_type(find(tree, ST_FIGURES), "Dd") if dd.id is not None
        ]
        assert dds == list(ST_FIGURE_IDS.values())

    def test_the_popular_vote_count_reconciles_to_the_table(self) -> None:
        # Architect M-4 (D097(a)): no served figure exists, so the table's cells are
        # the target: rows with electors appointed whose status cell reads "Popular
        # vote held", of the rows with electors appointed.
        tree = render()
        appointed = [
            (int(year), status)
            for year, electors, status in body_cells(tree)
            if electors != "0"
        ]
        held = [y for y, status in appointed if status == labels.PV_STATUS["popular_vote"]]
        assert st_figure(tree, PV_COUNT) == (
            f"{len(held)} of {len(appointed)} elections "
            f"({appointed[0][0]}–{appointed[-1][0]})"
        )

    @pytest.mark.parametrize("zero_first", [False, True])
    def test_the_first_election_is_the_span_s_start(self, zero_first: bool) -> None:
        # Architect I-5 (D119(a), D120 as amended): one rule, ``state_view.allotment``,
        # for the Years filter's start and the figure, computed twice (the figure is a
        # select) and checked here to agree; the figure refuses what
        # ``first_election`` skips.
        body = ga_body()
        if zero_first:
            set_year(body, 1824, "state_electoral_votes", 0)
        first = state_view.first_election(collapse("GA", body))
        assert first == (1828 if zero_first else 1824)
        assert st_figure(render(body=body), FIRST).startswith(f"{first}, with ")

    @pytest.mark.parametrize("status", ["sentinel_code", 7, "not_participating"])
    def test_a_status_fault_makes_the_popular_vote_count_alone_unrecognized(
        self, status: Any
    ) -> None:
        # D120 (architect M-1, M-2): only pv_status is doctored, so the allotment
        # figures cannot mask it; "not_participating" with electors appointed
        # contradicts itself. C7, the table and the page stay.
        body = ga_body()
        set_year(body, 1828, "pv_status", status)
        tree = render(body=body)
        assert st_figure(tree, PV_COUNT) == labels.UNRECOGNIZED
        assert find(tree, ST_FIGURE_IDS[PV_COUNT]).title == labels.UNRECOGNIZED_NOTE
        assert st_figure(tree, ELECTIONS_COUNT) == "50 elections (1824–2024)"
        assert st_figure(tree, FIRST) == "1824, with 9 electors appointed"
        assert st_figure(tree, CHANGE) == "+7, from 9 in 1824 to 16 in 2024"
        assert c7_figure(tree) is not None
        assert c10_figure(tree) is not None  # #635's review, cr.7
        assert tree.id == PAGE_ID and find(tree, ELECTORS) is not None
        assert "sentinel_code" not in " ".join(texts(find(tree, ST_FIGURES)))

    def test_an_unknown_status_in_a_year_with_no_electors_is_not_read(self) -> None:
        # Owner, #635's review (ge.5; D120 amended): the figures are over the years
        # with electors appointed, so GA 1864 (an allotment of 0) is outside them; its
        # table cell words the unknown code.
        body = ga_body()
        set_year(body, 1864, "pv_status", "sentinel_code")
        tree = render(body=body)
        assert st_figure(tree, PV_COUNT) == "49 of 50 elections (1824–2024)"

    @pytest.mark.parametrize("status", [None, "", " "])
    def test_a_null_status_is_left_out_of_n(self, status: Any) -> None:
        # D112(a) as amended: a null is never read as "no"; N drops. GA 1828 held a
        # popular vote, so both counts drop by one.
        body = ga_body()
        set_year(body, 1828, "pv_status", status)
        tree = render(body=body)
        assert st_figure(tree, PV_COUNT) == "48 of 49 elections (1824–2024)"

    def test_every_status_null_names_no_cause(self) -> None:
        body = ga_body()
        for row in body["data"]:
            row["pv_status"] = None
        tree = render(body=body)
        assert st_figure(tree, PV_COUNT) == labels.METRIC_NO_FIGURE[PV_COUNT]

    @pytest.mark.parametrize(
        ("latest", "text"),
        [
            (5, "−4, from 9 in 1824 to 5 in 2024"),
            (9, "0, from 9 in 1824 to 9 in 2024"),
        ],
    )
    def test_a_change_is_signed_and_zero_is_a_value(
        self, latest: int, text: str
    ) -> None:
        body = ga_body()
        set_year(body, 2024, "state_electoral_votes", latest)
        assert st_figure(render(body=body), CHANGE) == text

    def test_one_year_with_electors(self) -> None:
        body = ga_body()
        for row in body["data"]:
            if row["year"] != 1828:
                row["state_electoral_votes"] = 0
        tree = render(body=body)
        assert st_figure(tree, FIRST) == "1828, with 9 electors appointed"
        assert st_figure(tree, PV_COUNT) == "1 of 1 election (1828)"
        assert st_figure(tree, CHANGE) == labels.METRIC_NO_FIGURE[CHANGE]

    def test_one_elector_is_singular(self) -> None:
        body = ga_body()
        set_year(body, 1824, "state_electoral_votes", 1)
        assert st_figure(render(body=body), FIRST) == "1824, with 1 elector appointed"

    def test_the_page_and_the_shared_function_agree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Architect I-1: the page words what ``history_figures`` computed, once, over
        # C7's whole collapse.
        seen: list[Any] = []
        real = state_view.history_figures

        def spy(records: Any) -> Any:
            seen.append([r["year"] for r in records])
            return real(records)

        monkeypatch.setattr(state_view, "history_figures", spy)
        render("year_from=1900&year_to=1960")
        assert seen == [[r["year"] for r in collapse("GA")]]


def n2_records() -> dict[str, list[dict[str, Any]]]:
    """N2's rows, one state's at a time, along the path the ``/states`` table and map
    (#641, #623) are to take (#640, D120): the page's row check, ``state_view.rows``,
    then C7's per-year collapse, ``state_view.electors``, as the history page runs
    them. The collapse refuses a year whose rows disagree and a gap; it accepts a
    repeated identical row, so N2's one row per state-year is
    ``TestN2Fixture.test_count_and_no_repeat``'s check, not this helper's."""
    path = "/v1/elections/states"
    served = set(state_view.served_years(INDEX))
    by_state: dict[str, list[dict[str, Any]]] = {}
    for row in N2["data"]:
        by_state.setdefault(row["state_usps"], []).append(row)
    return {
        usps: state_view.electors(
            state_view.rows({"data": rows}, usps, served, path), served, usps, path
        )
        for usps, rows in by_state.items()
    }


class TestHistoryFiguresOnN2:
    """``state_view.history_figures`` is the one computation the ``/states`` table
    and map are to share (#621, D120; #641, #623): N2 serves one row per state-year
    with the fields it reads, and each state's rows pass the page's own row check and
    collapse (:func:`n2_records`, #640), so the map's values are to equal each state
    page's."""

    def test_it_is_total_over_every_state_and_spreads_as_planned(self) -> None:
        # The plan's falsifier, on the recording: 13 states lost electors from their
        # first election to their latest, 8 kept the same number, 30 gained.
        records = n2_records()
        assert len(records) == 51
        figures = {usps: state_view.history_figures(r) for usps, r in records.items()}
        assert not any(f.unrecognized for f in figures.values())
        signs = [f.change.value for f in figures.values()]
        assert all(type(v) is int for v in signs)
        counts = (
            sum(v < 0 for v in signs),  # type: ignore[operator]
            sum(v == 0 for v in signs),
            sum(v > 0 for v in signs),  # type: ignore[operator]
        )
        assert counts == (13, 8, 30)
        ga = figures["GA"].popular_vote
        assert (ga.count, ga.n, ga.first, ga.last) == (49, 50, 1824, 2024)

    @pytest.mark.parametrize("usps", ["GA", "TX"])
    def test_n2_gives_each_page_s_figures(self, usps: str) -> None:
        assert state_view.history_figures(
            n2_records()[usps]
        ) == state_view.history_figures(collapse(usps))


class TestHistoryFiguresRefusals:
    """``state_view.history_figures``' own refusals (#635's review; D120 amended):
    its totality backstop for a caller that passes records C7's collapse did not
    produce, or rows the page's row check (``state_view.rows``) did not check first."""

    @staticmethod
    def records(*rows: tuple[Any, Any]) -> list[dict[str, Any]]:
        return [
            {"year": y, "state_electoral_votes": v, "pv_status": "popular_vote"}
            for y, v in rows
        ]

    @pytest.mark.parametrize(
        "rows",
        [
            ((1824, 9), (1824, 10), (2024, 16)),  # cr.1: at the first year
            ((1824, 9), (2024, 16), (2024, 15)),  # at the latest
            ((1824, 9), (1900, 5), (1900, 5), (2024, 16)),  # inside, same value
        ],
    )
    def test_a_year_named_twice_makes_every_figure_unrecognized(
        self, rows: Any
    ) -> None:
        assert (
            state_view.history_figures(self.records(*rows))
            == state_view.UNRECOGNIZED_HISTORY
        )

    @pytest.mark.parametrize("year", ["1824", 1824.0, None, True], ids=repr)
    def test_a_year_that_is_no_int_makes_every_figure_unrecognized(
        self, year: Any
    ) -> None:
        # ge.4: a rule of the shared function. A float year passes C7's collapse
        # (``state_series`` reads 1824.0 as the served 1824); the page refuses it
        # earlier, in ``state_view.rows``, and #641 is to check N2's rows the same
        # way (#640, D120), so this is the backstop for a caller that does not.
        assert (
            state_view.history_figures(self.records((year, 9), (2024, 16)))
            == state_view.UNRECOGNIZED_HISTORY
        )

    def test_an_allotment_too_large_for_a_float_is_unrecognized_for_all(self) -> None:
        # cr.5: one rule for every figure, since a select and a change refuse it.
        assert (
            state_view.history_figures(self.records((1824, 10**400), (2024, 16)))
            == state_view.UNRECOGNIZED_HISTORY
        )

    def test_one_record_per_year_is_read(self) -> None:
        figures = state_view.history_figures(self.records((2024, 16), (1824, 9)))
        assert not figures.unrecognized
        assert figures.change.value == 7 and figures.first.first == (1824, "9")


class TestYearsFilter:
    """The state history's one filter (#620, D119): the year range, judged against the
    state's own span, from its first election to the latest served year, narrows C7,
    C10 and their table together; the headline figures read the whole history."""

    @pytest.mark.parametrize(
        ("usps", "query"),
        [
            ("GA", "year_from=1900&year_to=1990"),
            ("GA", "year_to=1872"),
            ("TX", "year_from=1840&year_to=1870"),
            ("TX", "year_from=2000"),
        ],
    )
    def test_both_charts_and_the_table_hold_the_same_years(
        self, usps: str, query: str
    ) -> None:
        tree = render(query, usps=usps)
        pairs = dict(MOD["parse_filters"](parse(query)))
        first = HISTORIES[usps].first
        low = max(int(pairs.get("year_from", first)), first)
        high = int(pairs.get("year_to", 2024))
        years = [y for y in SERVED if low <= y <= high]
        assert years and years != state_years(usps)
        axis = components.year_axis(years)
        c7, c10 = c7_figure(tree), c10_figure(tree)
        assert c7["layout"]["xaxis"] == axis
        assert c10["layout"]["xaxis"] == axis
        assert table_years(tree) == years
        assert [int(r["year"]) for r in download(tree, ELECTORS).rows] == years
        assert xs_of(c7) <= set(years) and xs_of(c10) <= set(years)
        # Each chart still equals its table's cells over the years shown (D091). C10
        # draws no bar before the popular-vote window, so its bars may be none.
        cells = {int(r["year"]): r for r in download(tree, ELECTORS).rows}
        drawn = [
            (field, dict(zip(t["x"], t["y"], strict=True)))
            for field, figure in (
                ("state_electoral_votes", c7),
                ("state_popular_total", c10),
            )
            for t in figure["data"]
            if t["type"] == "bar"
        ]
        assert drawn
        for field, bars in drawn:
            for year, value in bars.items():
                assert cells[year][field] == str(value), (field, year)
        # The slider shows the range applied, over the state's span.
        slider = slider_of(tree)
        assert (slider.min, slider.max) == (first, 2024)
        assert slider.value == [low, high]

    def test_georgia_s_narrowed_figures_are_the_default_s_with_a_note(self) -> None:
        """AC3 (#620; the owner's ruling at the plan gate): the figures read C7's whole
        collapse, so a narrowed range leaves them as the default render's, and
        :data:`labels.METRIC_ALL_YEARS_NOTE` follows them; under the default it does
        not."""
        plain, tree = render(), render("year_from=1900&year_to=1990")
        for key in ST_FIGURE_IDS:
            assert st_figure(tree, key) == st_figure(plain, key), key
        assert st_figure(tree, ELECTIONS_COUNT) == "50 elections (1824–2024)"
        note = find(tree, ALL_YEARS)
        assert note is not None and note.className == "note"
        assert note.children == labels.METRIC_ALL_YEARS_NOTE
        assert labels.METRIC_ALL_YEARS_NOTE == (
            "These figures cover this state's whole history in this dataset. The "
            "Years filter does not change them."
        )
        # In the figures' block, after the zero-allotment note.
        block = find(tree, ST_FIGURES)
        assert [getattr(k, "id", None) for k in block.children][-2:] == [
            MOD["METRICS_NOTE_ID"],
            ALL_YEARS,
        ]
        assert find(plain, ALL_YEARS) is None
        assert labels.METRIC_ALL_YEARS_NOTE not in texts(plain)

    @pytest.mark.parametrize(
        ("usps", "query", "zeros"),
        [
            ("GA", "", [1864]),
            ("GA", "year_from=1860&year_to=1868", [1864]),
            ("TX", "", [1864, 1868]),
            ("TX", "year_from=1860&year_to=1872", [1864, 1868]),
            ("TX", "year_from=1864&year_to=1864", [1864]),
        ],
    )
    def test_a_zero_allotment_keeps_its_marker_and_row(
        self, usps: str, query: str, zeros: list[int]
    ) -> None:
        """AC1: a mid-history zero allotment stays its labeled marker and its table
        row under the default view and under a range that covers it."""
        tree = render(query, usps=usps)
        c7 = c7_figure(tree)
        assert traces(c7)[labels.C4_NO_ELECTORS_TOOK_NO_PART] == zeros
        bars = [t for t in c7["data"] if t["type"] == "bar"]
        assert not set(zeros) & {x for t in bars for x in t["x"]}
        assert labels.C4_ZERO_NOTE in c7_caption(tree)
        assert traces(c10_figure(tree))[labels.C5_TOOK_NO_PART] == zeros
        rows = {y: appointed for y, appointed, _ in body_cells(tree)}
        for year in zeros:
            assert rows[str(year)] == "0", year

    @pytest.mark.parametrize(
        "query",
        [
            "year_to=1844",
            "year_from=1824&year_to=1844",
            "year_from=1700&year_to=1800",
            "year_from=1844",
        ],
    )
    def test_a_range_wholly_before_texas_s_first_election_is_the_default(
        self, query: str
    ) -> None:
        """#620 (D119): each bound outside the state's span falls back to its end, so
        a range before Texas's 1848 opens its whole history (replacing #279's honest
        empty result on this page)."""
        plain, tree = render(usps="TX"), render(query, usps="TX")
        assert c7_figure(tree) == c7_figure(plain)
        assert c10_figure(tree) == c10_figure(plain)
        assert download(tree, ELECTORS).raw == download(plain, ELECTORS).raw
        assert slider_of(tree).value == slider_of(plain).value == [1848, 2024]
        assert find(tree, NO_MATCH) is None and find(tree, ALL_YEARS) is None
        assert texts(find(tree, ST_FIGURES)) == texts(find(plain, ST_FIGURES))
        _, results, per_capita = section_entries(tree)
        assert (results.href, per_capita.href) == (
            "/state/TX/elections",
            "/state/TX/per-capita",
        )

    def test_a_range_holding_no_election_shows_the_note(self) -> None:
        """I1 (#620's architect review): the slider steps by one year, so a range can
        hold no election. The figures with the all-years note and the slider stay, then
        :data:`labels.STATE_NO_ELECTIONS_IN_RANGE` in place of both charts and the
        table, with no section heading before it (#634, D122); the success marker and
        section links stay."""
        query = "year_from=1850&year_to=1850"
        tree = render(query, usps="TX")
        assert tree.id == PAGE_ID
        note = find(tree, NO_MATCH)
        assert note is not None and note.className == "empty"
        assert note.children == labels.STATE_NO_ELECTIONS_IN_RANGE
        assert labels.STATE_NO_ELECTIONS_IN_RANGE == (
            "No election for this state falls in the years chosen."
        )
        slider = slider_of(tree)
        assert (slider.min, slider.max, slider.value) == (1848, 2024, [1850, 1850])
        assert of_type(tree, "Figure") == []
        assert c7_figure(tree) is None and c10_figure(tree) is None
        assert find(tree, ELECTORS) is None
        for unavailable in (
            MOD["C7_UNAVAILABLE_ID"],
            MOD["C10_UNAVAILABLE_ID"],
            MOD["ELECTORS_TABLE_UNAVAILABLE_ID"],
        ):
            assert find(tree, unavailable) is None, unavailable
        # The figures read the whole history (AC3), with the note that says so.
        plain = render(usps="TX")
        for key in ST_FIGURE_IDS:
            assert st_figure(tree, key) == st_figure(plain, key), key
        assert find(tree, ALL_YEARS) is not None
        # The one card: the figures, the slider, then the note (#634, D122).
        card = in_one_card(tree, NO_MATCH, total=1)
        held = list(card.children)
        assert [type(k).__name__ for k in held] == ["Div", "Div", "P"]
        assert held[0].id == ST_FIGURES
        assert find(held[1], YEARS) is slider
        assert held[2] is note
        _, results, per_capita = section_entries(tree)
        assert results.href == f"/state/TX/elections?{query}"
        assert per_capita.href == f"/state/TX/per-capita?{query}"

    def test_the_empty_range_through_the_layout_keeps_the_lede_and_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        heading, lede, content = MOD["layout"](
            usps="TX", year_from="1850", year_to="1850"
        ).children
        assert heading.children == "Texas"
        assert lede.children == f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}"
        assert content.id == PAGE_ID and find(content, NO_MATCH) is not None
        ids = routed_ids(route("/state/TX", "?year_from=1850&year_to=1850"))
        assert PAGE_ID in ids and NO_MATCH in ids and ELECTORS not in ids
        assert "c7" not in ids and "c10" not in ids

    def test_both_collapses_failed_shows_no_slider(self) -> None:
        """I2: with neither collapse read there is nothing to narrow, so no slider,
        the three sentences in place of both charts and the table, no figures, and
        ``render`` says so, so the layout adds no filter sentence."""
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["pv_status"] = "legislature_chosen"
        for search in ("", "year_from=1900&year_to=1990"):
            tree, _, filtered = render_all(search, body=copy.deepcopy(body))
            assert filtered is False
            assert tree.id == PAGE_ID
            assert of_type(tree, "RangeSlider") == []
            assert find(tree, ST_FIGURES) is None
            assert find(tree, NO_MATCH) is None
            for unavailable in (
                MOD["C7_UNAVAILABLE_ID"],
                MOD["C10_UNAVAILABLE_ID"],
                MOD["ELECTORS_TABLE_UNAVAILABLE_ID"],
            ):
                assert find(tree, unavailable) is not None, unavailable

    def test_a_c7_collapse_fault_starts_the_span_at_the_first_row(self) -> None:
        """B1 (#620's architect review): the span's start reads data only. Georgia
        doctored to appoint no electors in 1824 and 1828 starts at 1832; with C7's
        collapse also unreadable (two allotments in 1900), its first election cannot
        be told, so the span falls back to the first served row, where C10's collapse
        starts, and C10 renders over it with no start sentence."""
        body = zeroed(ga_body(), 1824, 1828)
        tree = render(body=copy.deepcopy(body))
        assert slider_of(tree).min == 1832
        years = [y for y in SERVED if y >= 1832]
        assert c10_figure(tree)["layout"]["xaxis"] == components.year_axis(years)
        start = labels.FIRST_ELECTION_START_NOTE.format(state="Georgia", year=1832)
        assert start in c7_caption(tree) and start in c10_caption(tree)
        (fault, *_) = [r for r in body["data"] if r["year"] == 1900]
        fault["state_electoral_votes"] = 99
        tree = render(body=copy.deepcopy(body))
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert find(tree, ST_FIGURES) is None
        slider = slider_of(tree)
        assert (slider.min, slider.value) == (1824, [1824, 2024])
        assert c10_figure(tree)["layout"]["xaxis"] == components.year_axis(SERVED)
        assert "This chart starts at" not in c10_caption(tree)
        assert table_years(tree) == SERVED
        # A range still narrows C10 and the table from the fallback span.
        tree = render("year_to=1900", body=copy.deepcopy(body))
        narrowed = [y for y in SERVED if y <= 1900]
        assert c10_figure(tree)["layout"]["xaxis"] == components.year_axis(narrowed)
        assert table_years(tree) == narrowed

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_a_blank_name_counts_as_neither_collapse_read(self, name: Any) -> None:
        """#620's scope ruling (D119(d)): a served name with no text fails both charts
        whatever the range, so it counts as neither collapse read: no slider, no
        filter sentence, no figures, and the three unavailable sentences, as before
        #620."""
        body = ga_body()
        for row in body["data"]:
            row["state"] = name
        tree, _, filtered = render_all("year_from=1900", body=body)
        assert filtered is False
        assert find(tree, MOD["YEARS_ID"]) is None
        assert find(tree, ST_FIGURES) is None
        for ident in (
            MOD["C7_UNAVAILABLE_ID"],
            MOD["C10_UNAVAILABLE_ID"],
            MOD["ELECTORS_TABLE_UNAVAILABLE_ID"],
        ):
            assert find(tree, ident) is not None

    @pytest.mark.parametrize(
        "query", ["", "year_to=1900", "year_from=1850&year_to=1850"]
    )
    def test_a_drawing_fault_moves_neither_the_span_nor_the_figures(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        """#620's scope ruling (cr.6, ge.3): what shows outside a chart's place follows
        the collapses, never the drawing. With C7's figure refusing to draw, the span
        still starts at the first election (1832, as doctored), and the slider, the
        filter sentence and the figures stay in every range, the empty one (1850, no
        election) included."""

        def refuse(*_args: Any, **_kwargs: Any) -> Any:
            raise TypeError("C7 cannot be drawn")

        monkeypatch.setattr(over_time, "c4_figure", refuse)
        body = zeroed(ga_body(), 1824, 1828)
        tree, _, filtered = render_all(query, body=body)
        assert filtered is True
        assert slider_of(tree).min == 1832
        assert find(tree, ST_FIGURES) is not None
        if query.endswith("1850"):
            assert find(tree, MOD["NO_MATCH_ID"]) is not None
        else:
            assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
            # C10 still draws: the fault is C7's drawing alone.
            assert c10_caption(tree)

    def test_texas_with_c7_s_collapse_unreadable_names_no_first_election(
        self,
    ) -> None:
        """#620's review (ge.1): with C7's collapse unreadable (two allotments in
        1900) the span falls back to Texas's first served row, 1848, after the
        dataset's first year, yet no caption names a first election, since none was
        read (``start_known``)."""
        body = copy.deepcopy(RECORDED["/v1/states/TX"])
        (fault, *_) = [r for r in body["data"] if r["year"] == 1900]
        fault["state_electoral_votes"] = 99
        tree = render(body=body, usps="TX")
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert slider_of(tree).min == 1848
        assert "This chart starts at" not in c10_caption(tree)

    @pytest.mark.parametrize(
        ("usps", "query", "shown"),
        [
            ("TX", "", True),
            ("TX", "year_to=1900", True),
            # Falls back to the first election, so the chart starts there.
            ("TX", "year_from=1840", True),
            ("TX", "year_from=1900", False),
            ("TX", "year_from=1852&year_to=1900", False),
            ("GA", "", False),
            ("GA", "year_to=1900", False),
        ],
    )
    def test_the_start_sentence_shows_only_where_the_chart_starts_there(
        self, usps: str, query: str, shown: bool
    ) -> None:
        """#620's ba spec: only when the years shown start at the state's first
        election and that is after the dataset's first year."""
        tree = render(query, usps=usps)
        sentence = labels.FIRST_ELECTION_START_NOTE.format(
            state=HISTORIES[usps].name, year=HISTORIES[usps].first
        )
        assert (sentence in c7_caption(tree)) is shown
        assert (sentence in c10_caption(tree)) is shown
        # Where none is due, no start sentence at all, for any year: a chart narrowed
        # to start at 1900 must not call 1900 the state's first election (#620's
        # mutation pass found this unpinned).
        if not shown:
            prefix = labels.FIRST_ELECTION_START_NOTE.split("{year}")[0]
            assert prefix not in c7_caption(tree)
            assert prefix not in c10_caption(tree)
        assert labels.FIRST_ELECTION_START_NOTE == (
            "This chart starts at {year}, the first election in this dataset in which "
            "{state} appointed electors."
        )
        assert labels.FIRST_ELECTION_START_NOTE_THIS_STATE == (
            "This chart starts at {year}, the first election in this dataset in which "
            "this state appointed electors."
        )


class TestCallback:
    """The history page's one filter callback (#620, D119): the slider's value as the
    normalized query, judged against the slider's own span, the state's."""

    @pytest.mark.parametrize(
        ("years", "first", "last", "current", "search"),
        [
            ([1900, 1990], 1824, 2024, "", "?year_from=1900&year_to=1990"),
            ([1900.0, 2024], 1824, 2024, None, "?year_from=1900"),
            ([1824, 1990], 1824, 2024, "", "?year_to=1990"),
            # Texas's span: its first election is the slider's start, so the default.
            ([1848, 1900], 1848, 2024, "", "?year_to=1900"),
            ([1848, 2024], 1848, 2024, "?year_from=1900", ""),
            # A hostile payload passes through the page's parser: inverted, dropped.
            ([1990, 1900], 1824, 2024, "?year_to=1990", ""),
            ("x", 1824, 2024, "?year_to=1990", ""),
        ],
    )
    def test_a_change_writes_the_normalized_search(
        self, years: Any, first: Any, last: Any, current: Any, search: str
    ) -> None:
        assert MOD["on_filter_change"](years, first, last, current) == search

    @pytest.mark.parametrize(
        ("years", "first", "last", "current"),
        [
            ([1824, 2024], 1824, 2024, ""),
            ([1824, 2024], 1824, 2024, None),
            ([1848, 2024], 1848, 2024, ""),
            ([1900, 1990], 1824, 2024, "?year_from=1900&year_to=1990"),
        ],
    )
    def test_an_unchanged_search_is_left_alone(
        self, years: Any, first: Any, last: Any, current: Any
    ) -> None:
        assert MOD["on_filter_change"](years, first, last, current) is no_update

    def test_it_is_registered_on_the_slider_and_the_page_s_location(self) -> None:
        assert appmod.server.test_client().get("/").status_code == 200
        spec = appmod.app.callback_map[f"{MOD['URL_ID']}.search"]
        assert spec["inputs"] == [{"id": YEARS, "property": "value"}]
        assert spec["state"] == [
            {"id": YEARS, "property": "min"},
            {"id": YEARS, "property": "max"},
            {"id": MOD["URL_ID"], "property": "search"},
        ]
        # Dash keeps no initial-call flag in its map: read it from the decorator.
        decorator = ast.parse(inspect.getsource(MOD["on_filter_change"])).body[0]
        assert isinstance(decorator, ast.FunctionDef)
        (call,) = decorator.decorator_list
        assert isinstance(call, ast.Call)
        keywords = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
        assert keywords == {"prevent_initial_call": True}

    def test_a_filter_change_makes_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        route("/state/GA")
        route("/state/TX")
        calls.clear()
        waits = len(bucket.waits)
        search = MOD["on_filter_change"]([1900, 1990], 1824, 2024, "")
        assert search == "?year_from=1900&year_to=1990"
        for path, shown in (
            ("/state/GA", search),
            ("/state/GA", "?year_to=1872"),
            ("/state/TX", "?year_from=1850&year_to=1850"),
            ("/state/GA", ""),
        ):
            assert PAGE_ID in routed_ids(route(path, shown)), (path, shown)
        assert calls == []
        assert len(bucket.waits) == waits


# --- the card's order: the figures above the Years filter (#634, D122) ------------------


def card_key(node: Any) -> tuple[str, str]:
    """A card child as (type, what tells it apart): its id, a heading's text, or, with
    neither, its classes (``filters`` alone for the filters box, which has no id)."""
    kind = type(node).__name__
    if kind == "H2":
        return kind, node.children
    ident = getattr(node, "id", None)
    if ident is not None:
        return kind, ident
    classes = (getattr(node, "className", None) or "").split()
    return kind, "filters" if "filters" in classes else " ".join(classes)


FIGURES_KEY = ("Div", ST_FIGURES)
FILTERS_KEY = ("Div", "filters")
C7_HEADING_KEY = ("H2", MOD["C7_HEADING"])
C10_HEADING_KEY = ("H2", MOD["C10_HEADING"])
TABLE_HEADING_KEY = ("H2", MOD["ELECTORS_TOTALS_TABLE_HEADING"])


class TestCardOrder:
    """#634 (D122, amending D115(g), D117(a), D119(c), (d)): a filter sits directly
    above what it narrows and below what it does not. The state history's one card
    opens with the headline figures (unfiltered, no heading of their own), then the
    Years filter, then C7, C10 and their table. Each case pins the card's direct
    children in order through the table's heading (the empty range's whole card), checks
    that no filter or heading follows the table's heading, and checks that its render
    took its branch."""

    def keys(self, tree: Any) -> list[tuple[str, str]]:
        (card,) = every_card(tree)
        return [card_key(k) for k in card.children]

    def test_the_default_view(self) -> None:
        tree = render()
        assert find(tree, ALL_YEARS) is None and find(tree, NO_MATCH) is None
        keys = self.keys(tree)
        assert keys[:7] == [
            FIGURES_KEY,
            FILTERS_KEY,
            C7_HEADING_KEY,
            ("Figure", charts.dom_id(MOD["C7_ID"])),
            C10_HEADING_KEY,
            ("Figure", C10_DOM),
            TABLE_HEADING_KEY,
        ]
        # Only the table and its column-name list follow its heading.
        assert FIGURES_KEY not in keys[7:] and FILTERS_KEY not in keys[7:]
        assert all(kind != "H2" for kind, _ in keys[7:])
        (card,) = every_card(tree)
        tail = list(card.children)[7:]
        assert find(tail, ELECTORS) is not None
        assert find(tail, MOD["ELECTORS_GLOSSARY_ID"]) is not None
        # The block the card's top-space rule names (D122(e)): the wrapper's class,
        # and the figures' dl first in it.
        figures = list(card.children)[0]
        assert figures.className == "figures"
        first = list(figures.children)[0]
        assert type(first).__name__ == "Dl" and first.className == "metrics"

    def test_a_narrowed_range(self) -> None:
        tree = render("year_from=1900&year_to=1990")
        # The branch: a narrower range applies, so the all-years note shows, inside
        # the figures block, above the filter.
        note = find(tree, ALL_YEARS)
        assert note is not None
        assert find(find(tree, ST_FIGURES), ALL_YEARS) is note
        assert self.keys(tree) == self.keys(render())

    def test_a_range_holding_no_election(self) -> None:
        tree = render("year_from=1850&year_to=1850", usps="TX")
        assert find(tree, NO_MATCH) is not None and find(tree, ALL_YEARS) is not None
        # No section heading before the note: it stands for C7, C10 and the table.
        assert self.keys(tree) == [FIGURES_KEY, FILTERS_KEY, ("P", NO_MATCH)]

    def test_c7_unreadable(self) -> None:
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["state_electoral_votes"] = 99
        tree = render(body=body)
        # The branch: C7's collapse is unreadable, so the figures go with it, and C10
        # stays.
        assert find(tree, ST_FIGURES) is None
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert c10_figure(tree) is not None
        keys = self.keys(tree)
        assert keys[:6] == [
            FILTERS_KEY,
            C7_HEADING_KEY,
            ("P", MOD["C7_UNAVAILABLE_ID"]),
            C10_HEADING_KEY,
            ("Figure", C10_DOM),
            TABLE_HEADING_KEY,
        ]
        assert FILTERS_KEY not in keys[6:]
        assert all(kind != "H2" for kind, _ in keys[6:])
        (card,) = every_card(tree)
        tail = list(card.children)[6:]
        assert find(tail, ELECTORS) is not None
        assert find(tail, MOD["ELECTORS_GLOSSARY_ID"]) is not None

    @pytest.mark.parametrize(
        ("usps", "query"),
        [
            ("GA", "year_from=1900&year_to=1990"),
            ("GA", "year_to=1872"),
            ("TX", "year_from=1850&year_to=1850"),
        ],
    )
    def test_nothing_the_card_shows_above_the_filter_changes_with_it(
        self, usps: str, query: str
    ) -> None:
        """AC1, tied to the placement: the text the card shows above the filter is the
        same under the default and a narrowed range, but for the all-years note, which
        names the filter and narrows nothing (D122(d)). The section links above the card
        carry the range in their hrefs (D119(e)), which this does not read."""

        def above(tree: Any) -> list[str]:
            (card,) = every_card(tree)
            held = list(card.children)
            at = [card_key(k) for k in held].index(FILTERS_KEY)
            return [t for k in held[:at] for t in texts(k)]

        narrowed = above(render(query, usps=usps))
        plain = above(render(usps=usps))
        assert narrowed[-1] == labels.METRIC_ALL_YEARS_NOTE
        assert narrowed[:-1] == plain


#: Each fault C7's collapse refuses, applied to one year (1900, after GA's first
#: election) of a list of rows: a second row is a copy of the year's first with one
#: field replaced (the page's rows already hold several per year; N2's hold one).
SHARED_FAULTS: dict[str, Callable[[list[dict[str, Any]]], None]] = {}


def _fault(name: str) -> Callable[..., Any]:
    def register(
        apply: Callable[[list[dict[str, Any]]], None],
    ) -> Callable[[list[dict[str, Any]]], None]:
        SHARED_FAULTS[name] = apply
        return apply

    return register


def _with_second(rows: list[dict[str, Any]], **fields: Any) -> None:
    (first, *_) = [r for r in rows if r["year"] == 1900]
    rows.append({**first, **fields})


@_fault("two statuses in a year")
def _two_statuses(rows: list[dict[str, Any]]) -> None:
    _with_second(rows, pv_status="legislature_chosen")


@_fault("a null status beside a value")
def _null_status(rows: list[dict[str, Any]]) -> None:
    _with_second(rows, pv_status=None)


@_fault("two allotments in a year")
def _two_allotments(rows: list[dict[str, Any]]) -> None:
    _with_second(rows, state_electoral_votes=99)


@_fault("a null allotment beside a value")
def _null_allotment(rows: list[dict[str, Any]]) -> None:
    _with_second(rows, state_electoral_votes=None)


@_fault("a gap after the first election")
def _gap(rows: list[dict[str, Any]]) -> None:
    rows[:] = [r for r in rows if r["year"] != 1900]


@_fault("a row without pv_status")
def _no_status(rows: list[dict[str, Any]]) -> None:
    (first, *_) = [r for r in rows if r["year"] == 1900]
    del first["pv_status"]


@_fault("a row without the allotment")
def _no_allotment(rows: list[dict[str, Any]]) -> None:
    (first, *_) = [r for r in rows if r["year"] == 1900]
    del first["state_electoral_votes"]


class TestSharedCollapse:
    """C7's per-year collapse lives in ``state_view`` (#640, D120): the history page
    reads a state's rows through ``state_view.collapsed(state_view.electors, …)``, and
    the ``/states`` table and map (#641, #623) are to read N2's through the same call.
    These tests feed both shapes of rows to it directly: each fault reads as ``None``
    (no figures) for both. That the ``/states`` render calls it is #641's to guard."""

    SOURCE = "/v1/elections/states"

    @staticmethod
    def page_rows() -> list[dict[str, Any]]:
        """GA's recorded history rows, checked as the page checks them."""
        return state_view.rows(ga_body(), "GA", set(SERVED), GA_PATH)

    @staticmethod
    def n2_rows() -> list[dict[str, Any]]:
        return copy.deepcopy(n2_state("GA"))

    def read(self, rows: list[dict[str, Any]], source: str) -> Any:
        return state_view.collapsed(
            state_view.electors, rows, set(SERVED), "GA", source
        )

    def test_both_inputs_read_clean_and_agree(self) -> None:
        page = self.read(self.page_rows(), GA_PATH)
        n2 = self.read(self.n2_rows(), self.SOURCE)
        assert page is not None and n2 is not None
        assert [
            (r["year"], r["state_electoral_votes"], r["pv_status"]) for r in page
        ] == [(r["year"], r["state_electoral_votes"], r["pv_status"]) for r in n2]

    @pytest.mark.parametrize("fault", sorted(SHARED_FAULTS))
    def test_each_fault_is_refused_for_the_page_and_for_n2(self, fault: str) -> None:
        # AC3 and its parity (architect Q3): the same fault in the page's rows and in
        # N2's rows reads as no collapse for both.
        page, n2 = self.page_rows(), self.n2_rows()
        SHARED_FAULTS[fault](page)
        SHARED_FAULTS[fault](n2)
        assert self.read(page, GA_PATH) is None
        assert self.read(n2, self.SOURCE) is None

    @pytest.mark.parametrize(
        "fault", ["a row without pv_status", "a null status beside a value"]
    )
    def test_the_collapse_changes_what_n2_s_figures_read(self, fault: str) -> None:
        # The collapse is stricter than ``over_time.state_series`` alone on these
        # faults (architect Q3): the same rows, keyed by year (the last of a year's
        # rows kept) and read by ``state_series`` and ``history_figures``, give figures
        # that read as recognized, where the shared collapse refuses them. It guards
        # no caller; the spy below guards the page's.
        rows = self.n2_rows()
        SHARED_FAULTS[fault](rows)
        by_year = {r["year"]: r for r in rows}
        old = over_time.state_series(by_year, set(SERVED), self.SOURCE, "GA")
        assert not state_view.history_figures(old).unrecognized
        assert self.read(rows, self.SOURCE) is None

    def test_the_page_reads_the_shared_collapse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The page cannot fork the collapse: its render calls ``state_view.collapsed``
        # on ``state_view.electors`` with its checked rows (architect Q4),
        # and ``history_figures`` reads the very records that call returned (AC1).
        calls: list[tuple[Any, Any]] = []
        electors_rows: list[Any] = []
        figures_input: list[Any] = []
        real_collapsed = state_view.collapsed
        real_electors = state_view.electors
        real_figures = state_view.history_figures

        def spy_electors(rows: Any, *args: Any) -> Any:
            electors_rows.append(copy.deepcopy(rows))
            return real_electors(rows, *args)

        def spy_collapsed(collapse: Any, *args: Any) -> Any:
            result = real_collapsed(collapse, *args)
            calls.append((collapse, result))
            return result

        def spy_figures(records: Any) -> Any:
            figures_input.append(records)
            return real_figures(records)

        monkeypatch.setattr(state_view, "electors", spy_electors)
        monkeypatch.setattr(state_view, "collapsed", spy_collapsed)
        monkeypatch.setattr(state_view, "history_figures", spy_figures)
        render()
        by_collapse = dict(calls)
        assert len(calls) == 2
        assert set(by_collapse) == {spy_electors, MOD["popular_totals"]}
        assert electors_rows == [self.page_rows()]
        assert len(figures_input) == 1
        assert figures_input[0] is by_collapse[spy_electors]

    @pytest.mark.parametrize("error", [ValueError, AttributeError, IndexError])
    def test_collapsed_reads_only_its_two_faults_as_none(
        self, error: type[Exception]
    ) -> None:
        # ``collapsed``'s contract (ge.2): a ``KeyError`` or ``TypeError`` is rows that
        # cannot be read, ``None``; any other exception is a defect and propagates.
        def raising(exc: type[Exception]) -> Any:
            def collapse(*_args: Any) -> Any:
                raise exc("x")

            return collapse

        args: tuple[Any, ...] = ([], set(SERVED), "GA", GA_PATH)
        assert state_view.collapsed(raising(KeyError), *args) is None
        assert state_view.collapsed(raising(TypeError), *args) is None
        with pytest.raises(error):
            state_view.collapsed(raising(error), *args)

    @pytest.mark.parametrize(
        "name", ["electors", "_per_year", "per_year", "collapsed", "Collapse"]
    )
    def test_the_page_defines_no_collapse_of_its_own(self, name: str) -> None:
        assert name not in MOD
