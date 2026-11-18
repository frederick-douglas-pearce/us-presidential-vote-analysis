"""The state history, T4, and the state picker (#279), and the state's people per
electoral vote page, T7 (#280; its own page since #559), with the section links
between a state's two pages (#559, D105).

Offline, against the recorded ``/v1/states/GA`` and the roster ``/v1/elections/2024``,
and ``/v1/states/GA/per-capita`` and ``/v1/states/TX/per-capita``
(the same snapshot as every other fixture, ``test_every_recorded_response_is_one_
snapshot``), through the helpers and the autouse offline process client of
``test_dashboard_app.py``. The registry-wide checks there pick the pages up
(``TestRegistryCoverage``, ``TestValidateBeforeFill`` with ``ZZ`` as the unserved code,
``TestRegistryContracts``), and the D070(b) guard renders ``/state/GA``,
``/state/GA/per-capita``, ``/states``, ``/state/ZZ`` and ``/state/ZZ/per-capita``.
These tests cover what is particular to the three pages.
"""

from __future__ import annotations

import ast
import copy
import inspect
import random
from typing import Any

import dash
import pytest
from dash import no_update

from explore import api, election_view, export, labels, query, state_view
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
from tests.unit.test_dashboard_elections import classed, find, of_type, parse
from tests.unit.test_dashboard_export import download

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
TABLE = MOD["TABLE_ID"]
PC_PAGE_ID = PC_MOD["PAGE_ID"]
PER_CAPITA = PC_MOD["PER_CAPITA_TABLE_ID"]


def ga_body() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[GA_PATH])


def ga_per_capita() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[GA_PER_CAPITA_PATH])


def render(query: str = "", body: Any = None, index: Any = None) -> Any:
    """The history page's body for ``query``, as the layout builds it."""
    content, _ = MOD["render"](
        ga_body() if body is None else body,
        copy.deepcopy(INDEX) if index is None else index,
        "GA",
        MOD["parse_filters"](parse(query)),
    )
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


def table_rows(tree: Any) -> list[list[Any]]:
    table = find(tree, TABLE)
    if table is None:
        return []
    return [list(tr.children) for tr in of_type(of_type(table, "Tbody"), "Tr")]


def row_texts(tree: Any) -> list[list[str]]:
    return [[" ".join(texts(td)) for td in row] for row in table_rows(tree)]


def years_shown(tree: Any) -> list[int]:
    return [int(row[0]) for row in row_texts(tree)]


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
    assert PAGE["query"] is MOD["parse_filters"]
    assert PAGE.get("order") is None


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
    # Its own ids: Dash keys callbacks by output, app-wide.
    assert PC_MOD["URL_ID"] != MOD["URL_ID"]
    assert PC_MOD["YEARS_ID"] != MOD["YEARS_ID"]


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
    assert PICKER["on_miss"] == (api.ROSTER_PATH,)
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
    def test_1864_shows_the_not_participating_label(self) -> None:
        rows = [r for r in row_texts(render()) if r[0] == "1864"]
        assert len(rows) == 2
        for row in rows:
            assert row[7] == labels.PV_STATUS["not_participating"]
            assert row[8] == labels.TOOK_NO_PART

    def test_1868_shows_disputed_with_the_archives_reason_verbatim(self) -> None:
        reason = next(
            r["electoral_count_status_reason"]
            for r in ga_body()["data"]
            if r["year"] == 1868 and r["candidate"] == "Horatio Seymour"
        )
        assert reason  # the Archives' sentence, read from the response
        (row,) = [
            r
            for r in table_rows(render())
            if texts(r[0]) == ["1868"] and texts(r[1]) == ["Horatio Seymour"]
        ]
        count = row[6]
        assert of_type(count, "Strong")[0].children == "Disputed"
        assert of_type(count, "Span")[0].children == reason

    def test_every_served_row_is_shown_unfiltered(self) -> None:
        tree = render()
        assert len(table_rows(tree)) == len(ga_body()["data"])
        assert f"Showing {len(ga_body()['data'])} of" in " ".join(texts(tree))

    def test_the_party_cell_and_the_party_notes_list(self) -> None:
        """T4 (#389): a pre-1976 party from the nominating-party field (MIT's
        ``party`` is null then, so a page reading it would fail here), a null with its
        one-cause note, a row note as help text, and the Party notes list."""
        index = MOD["FIELDS"].index("nominating_party")
        cells = {
            (texts(r[0])[0], texts(r[1])[0]): r[index] for r in table_rows(render())
        }
        assert texts(cells[("1824", "Andrew Jackson")]) == ["Democratic-Republican"]
        clay = cells[("1824", "Henry Clay")]
        assert texts(clay) == [labels.NOT_IN_DATASET]
        assert clay.title == labels.PARTY_NULL_NOTE
        note = next(
            r["nominating_party_note"]
            for r in ga_body()["data"]
            if r["year"] == 1872 and r["candidate"] == "Horace Greeley"
        )
        assert note
        assert cells[("1872", "Horace Greeley")].title == note
        (block,) = [
            d
            for d in of_type(render(), "Div")
            if getattr(d, "className", None) == "party-notes"
        ]
        assert [li.children for li in of_type(block, "Li")] == [
            labels.PARTY_NOTE_ITEM.format(
                candidate="Horace Greeley", year=1872, note=note
            )
        ]

    def test_t4_s_column_name_list_names_the_count_reason_and_the_party_note(
        self,
    ) -> None:
        named = [
            [texts(dd.children)[0] for dd in of_type(g, "Dd")]
            for g in of_type(render(), "Details")
        ]
        assert [
            *MOD["FIELDS"],
            "electoral_count_status_reason",
            "nominating_party_note",
        ] in named

    def test_the_heading_names_the_state_from_the_rows(self) -> None:
        _, name = MOD["render"](ga_body(), copy.deepcopy(INDEX), "GA", [])
        assert name == "Georgia"

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


def test_rows_are_sorted_by_the_page_not_trusted_in_api_order() -> None:
    body = ga_body()
    random.Random(279).shuffle(body["data"])
    shown = [(int(row[0]), row[1]) for row in row_texts(render(body=body))]
    # By year, then by candidate within a year.
    assert shown == sorted(shown)
    assert shown[0][0] == 1824 and shown[-1][0] == 2024
    assert len({year for year, _ in shown}) < len(shown)  # some year has several


# --- filters --------------------------------------------------------------------------


class TestFilters:
    def test_the_parser_keeps_only_its_own_keys_and_never_the_path_variable(
        self,
    ) -> None:
        pairs = MOD["parse_filters"](
            parse(
                "year_from=1860&year_to=1880&candidate=horatio-seymour"
                "&pv_status=popular_vote&usps=TX&state=GA&junk=1"
            )
        )
        assert pairs == [
            ("candidate", "horatio-seymour"),
            ("pv_status", "popular_vote"),
            ("year_from", "1860"),
            ("year_to", "1880"),
        ]

    @pytest.mark.parametrize(
        "query",
        [
            "candidate=Horatio",
            "candidate=" + "a" * 65,
            "pv_status=held",
            "year_from=186",
            "year_from=1880&year_to=1860",  # inverted: both bounds dropped
            "candidate=a&candidate=b",
        ],
    )
    def test_a_bad_parameter_is_dropped(self, query: str) -> None:
        assert MOD["parse_filters"](parse(query)) == []

    def test_the_year_range_narrows_the_rows(self) -> None:
        shown = years_shown(render("year_from=1860&year_to=1872"))
        assert sorted(set(shown)) == [1860, 1864, 1868, 1872]

    def test_a_bound_outside_the_datasets_span_falls_back_per_parameter(self) -> None:
        shown = years_shown(render("year_from=1700&year_to=1832"))
        assert sorted(set(shown)) == [1824, 1828, 1832]

    @staticmethod
    def admitted_1912() -> dict[str, Any]:
        """Georgia's body cut to 1912 on: a state admitted that year, as Arizona was."""
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] >= 1912]
        return body

    def test_a_range_before_the_states_first_election_is_an_honest_empty_result(
        self,
    ) -> None:
        # The dataset's span judges the bound (Fred, option (i)): 1900 is a year the
        # dataset holds, so it is kept, and the state has no election in range.
        for search in ("year_to=1900", "year_from=1824&year_to=1900"):
            tree = render(search, body=self.admitted_1912())
            assert table_rows(tree) == [], search
            assert "No rows match these filters." in texts(tree)
            (slider,) = of_type(tree, "RangeSlider")
            assert slider.value == [1824, 1900]

    def test_the_slider_spans_the_dataset_and_shows_the_selection(self) -> None:
        tree = render("year_from=1900", body=self.admitted_1912())
        (slider,) = of_type(tree, "RangeSlider")
        assert (slider.min, slider.max) == (1824, 2024)
        assert slider.value == [1900, 2024]
        assert min(years_shown(tree)) == 1912
        # So the callback writes back exactly what the URL said.
        assert (
            MOD["on_filter_change"](
                slider.value, None, None, slider.min, slider.max, "?year_from=1900"
            )
            is no_update
        )

    def test_the_span_is_read_from_the_bodys_coverage(self) -> None:
        # Not a constant: a snapshot whose coverage starts in 1860 moves the slider's
        # floor and the fallback of a bound before it.
        body = ga_body()
        body["meta"]["provenance"]["coverage"]["year_min"] = 1860
        tree = render("year_from=1840", body=body)
        (slider,) = of_type(tree, "RangeSlider")
        assert (slider.min, slider.max) == (1860, 2024)
        assert slider.value == [1860, 2024]
        assert min(years_shown(tree)) == 1860

    def test_the_spans_ceiling_is_read_from_the_bodys_coverage_too(self) -> None:
        # The ceiling, not only the floor: a hardcoded 2024 would go stale when a
        # later election lands, and this coverage ending in 2020 would show it.
        body = ga_body()
        body["meta"]["provenance"]["coverage"]["year_max"] = 2020
        tree = render("year_to=2030", body=body)
        (slider,) = of_type(tree, "RangeSlider")
        assert (slider.min, slider.max) == (1824, 2020)
        assert slider.value == [1824, 2020]
        assert max(years_shown(tree)) == 2020

    def test_a_candidate_narrows_and_one_absent_falls_back_to_all(self) -> None:
        shown = row_texts(render("candidate=horatio-seymour"))
        assert {row[1] for row in shown} == {"Horatio Seymour"}
        everyone = render("candidate=barack-obamaa")
        assert len(table_rows(everyone)) == len(ga_body()["data"])

    def test_a_status_is_kept_when_nothing_matches(self) -> None:
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["pv_status"] == "popular_vote"]
        tree = render("pv_status=legislature_chosen", body=body)
        assert table_rows(tree) == []
        assert "No rows match these filters." in texts(tree)

    def test_a_status_narrows(self) -> None:
        shown = years_shown(render("pv_status=not_participating"))
        assert set(shown) == {1864}


class TestCallback:
    def test_a_filter_change_writes_the_normal_form(self) -> None:
        search = MOD["on_filter_change"](
            [1860.0, 2024], "horatio-seymour", None, 1824, 2024, ""
        )
        assert search == "?candidate=horatio-seymour&year_from=1860"

    def test_the_full_span_and_cleared_controls_are_no_query(self) -> None:
        assert MOD["on_filter_change"]([1824, 2024], None, "", 1824, 2024, "?x") == ""

    def test_hostile_control_values_are_written_in_the_normal_form(self) -> None:
        # A callback payload is client-controlled: an inverted range, a non-slug
        # candidate and an unknown status all pass through the page's one parser.
        assert (
            MOD["on_filter_change"]([1880, 1860], "Horatio", "held", 1824, 2024, "?x")
            == ""
        )
        assert (
            MOD["on_filter_change"]([1824, 1860], "a b", "popular_vote", 1824, 2024, "")
            == "?pv_status=popular_vote&year_to=1860"
        )

    def test_an_unchanged_search_is_left_alone(self) -> None:
        current = "?pv_status=popular_vote"
        assert (
            MOD["on_filter_change"](
                [1824, 2024], None, "popular_vote", 1824, 2024, current
            )
            is no_update
        )


# --- links ----------------------------------------------------------------------------


def test_each_year_links_to_its_election() -> None:
    for row in table_rows(render()):
        (link,) = of_type(row[0], "Link")
        assert link.href == f"/election/{link.children}"


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
        assert PAGE_ID not in ids and TABLE not in ids
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

    @pytest.mark.parametrize("path", ["/state/GA/x", "/state/GA/per-capita/x"])
    def test_an_unknown_section_reaches_the_history_page_and_is_not_found(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        # The history page's greedy <usps> takes "GA/x", which is no USPS code.
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route(path))
        assert MOD["NOT_FOUND_ID"] in ids
        assert PAGE_ID not in ids and PC_PAGE_ID not in ids
        assert calls == []

    def test_filter_changes_make_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        route("/state/GA")
        calls.clear()
        for search in ("?year_from=1860", "?candidate=horatio-seymour", ""):
            assert PAGE_ID in routed_ids(route("/state/GA", search))
        MOD["on_filter_change"]([1860, 2024], None, None, 1824, 2024, "")
        assert calls == []

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
        assert calls == [ROSTER_PATH, GA_PATH]

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
    """The lede shows on success and on the degraded state, and the sentence naming
    the filters only on success, where the filters show (#392); the not-found state
    shows neither (#325)."""

    def test_the_two_sentences_are_todays_lede(self) -> None:
        # The split falls at the sentence boundary, so the degraded state offers no part
        # of the filter sentence; people per electoral vote left the lede with T7 (#559).
        assert MOD["FILTER_SENTENCE"] == (
            "Narrow the rows by year, candidate or popular-vote status."
        )
        assert f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}" == (
            "This state's electoral votes for each candidate in every election this "
            "dataset holds for it, with the popular vote where the dataset has it. "
            "Narrow the rows by year, candidate or popular-vote status."
        )

    def test_success_shows_the_lede_then_the_filter_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = route("/state/GA")
        assert PAGE_ID in routed_ids(response)
        body = response.get_data(as_text=True)
        assert f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}" in body
        # Once, and only in the lede.
        assert body.count(MOD["FILTER_SENTENCE"]) == 1

    def test_the_degraded_state_shows_the_lede_and_offers_no_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A malformed state body: render raises after validation, so the page degrades.
        TestMalformedBodies.client_with(monkeypatch, GA_PATH)
        response = route("/state/GA")
        ids = routed_ids(response)
        assert "unavailable" in ids and PAGE_ID not in ids
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] in body
        assert MOD["FILTER_SENTENCE"] not in body

    def test_the_unreachable_api_shows_the_lede_and_offers_no_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = offline_client(failing_fetch, prefetch_paths=lambda: [])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        response = route("/state/GA")
        assert "unavailable" in routed_ids(response)
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] in body
        assert MOD["FILTER_SENTENCE"] not in body

    def test_the_not_found_state_shows_neither(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = route("/state/ZZ")
        assert MOD["NOT_FOUND_ID"] in routed_ids(response)
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] not in body
        assert MOD["FILTER_SENTENCE"] not in body


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
        assert head.og_url == url("/state/GA?year_from=1860")

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

    def test_an_old_filtered_link_still_lands_on_the_history_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No query key reached T7 alone, so an old link is not redirected (D105): it
        answers 200 on the history page, with its year range applied to T4."""
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        search = "?year_from=1860&year_to=1872&candidate=horatio-seymour"
        status, head, _ = get(f"/state/GA{search}")
        assert status == 200
        assert head.canonical == url("/state/GA")
        response = route("/state/GA", search)
        assert PAGE_ID in routed_ids(response)
        # Through the layout, as the router calls it, so the query reaches the render.
        tree = MOD["layout"](usps="GA", **parse(search[1:]))
        assert years_shown(tree) == [1868]
        shown = years_shown(MOD["layout"](usps="GA", year_from="1860", year_to="1872"))
        assert set(shown) == {1860, 1864, 1868, 1872}

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
        assert calls == [ROSTER_PATH]
        calls.clear()
        # The state pages read the same roster: no second fill of it.
        assert PAGE_ID in routed_ids(route("/state/GA"))
        assert PC_PAGE_ID in routed_ids(route("/state/GA/per-capita"))
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
    def test_the_history_page_s_filters_do_not_reach_t7(self, search: str) -> None:
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


# --- the section links (#559, D105) ----------------------------------------------------


def section_entries(tree: Any) -> list[Any]:
    (nav,) = [n for n in of_type(tree, "Nav") if n.id == state_view.SECTIONS_ID]
    return list(nav.children)


class TestSectionLinks:
    """A state's two pages link each other on success only, in page order: the page
    being read is text with ``aria-current="page"``, the other a link carrying the year
    range the render applied and nothing else (#559, D105; the election pages' links
    carry no filter, D092)."""

    def test_the_link_texts_are_the_spec_s_and_name_each_page_apart(self) -> None:
        # ba's spec, approved at #559's plan gate: the two entries must differ, or a
        # reader could not tell which page a link opens.
        assert [state_view.SECTION_TEXT[s] for s in state_view.SECTIONS] == [
            "State history",
            "People per electoral vote",
        ]

    def test_the_landmark_is_named_and_drawn_as_the_election_pages_are(self) -> None:
        (nav,) = [n for n in of_type(render(), "Nav") if n.id == state_view.SECTIONS_ID]
        assert getattr(nav, "aria-label") == labels.STATE_SECTIONS_LABEL
        assert nav.className == election_view.SECTIONS_CLASS == "section-links"

    def test_on_the_history_page_the_history_is_marked(self) -> None:
        current, other = section_entries(render())
        assert type(current).__name__ == "Span"
        assert current.children == labels.SECTION_STATE_HISTORY
        assert getattr(current, "aria-current") == "page"
        assert type(other).__name__ == "Link"
        assert other.children == labels.SECTION_PER_CAPITA
        assert other.href == "/state/GA/per-capita"

    def test_on_the_per_capita_page_t7_is_marked(self) -> None:
        other, current = section_entries(pc_render())
        assert type(current).__name__ == "Span"
        assert current.children == labels.SECTION_PER_CAPITA
        assert getattr(current, "aria-current") == "page"
        assert type(other).__name__ == "Link"
        assert other.children == labels.SECTION_STATE_HISTORY
        assert other.href == "/state/GA"

    @pytest.mark.parametrize(
        ("query", "carried"),
        [
            ("year_from=1860&year_to=1900", "?year_from=1860&year_to=1900"),
            ("year_to=1900&candidate=horatio-seymour&pv_status=popular_vote",
             "?year_to=1900"),
            ("candidate=horatio-seymour", ""),
            # A bound outside the span falls back, so it is not carried.
            ("year_from=1700&year_to=1900", "?year_to=1900"),
            ("year_from=1824&year_to=2024", ""),
        ],
    )
    def test_the_history_link_carries_the_range_applied_only(
        self, query: str, carried: str
    ) -> None:
        _, link = section_entries(render(query))
        assert link.href == f"/state/GA/per-capita{carried}"

    @pytest.mark.parametrize(
        ("query", "carried"),
        [
            ("year_from=1860&year_to=1900", "?year_from=1860&year_to=1900"),
            ("year_from=1700", ""),
            ("", ""),
        ],
    )
    def test_the_per_capita_link_carries_the_range_applied(
        self, query: str, carried: str
    ) -> None:
        link, _ = section_entries(pc_render(query))
        assert link.href == f"/state/GA{carried}"

    def test_the_links_come_first_in_each_page_s_body(self) -> None:
        for tree in (render(), pc_render()):
            assert tree.children[0].id == state_view.SECTIONS_ID

    @pytest.mark.parametrize("path", ["/state/ZZ", "/state/ZZ/per-capita"])
    def test_the_not_found_state_has_no_section_links(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        assert state_view.SECTIONS_ID not in routed_ids(route(path))

    @pytest.mark.parametrize(
        ("path", "broken"),
        [("/state/GA", GA_PATH), ("/state/GA/per-capita", GA_PER_CAPITA_PATH)],
    )
    def test_the_degraded_state_has_no_section_links(
        self, monkeypatch: pytest.MonkeyPatch, path: str, broken: str
    ) -> None:
        TestMalformedBodies.client_with(monkeypatch, broken)
        ids = routed_ids(route(path))
        assert "unavailable" in ids
        assert state_view.SECTIONS_ID not in ids


# --- the dropdown filters (#475) ------------------------------------------------------


def _by_label(pairs: set[tuple[str, str]]) -> list[dict[str, str]]:
    """``{"label", "value"}`` options sorted by label, written out here rather than
    taken from the page."""
    return [
        {"label": label, "value": value}
        for value, label in sorted(pairs, key=lambda pair: pair[1])
    ]


def test_the_candidate_and_popular_vote_filters_show_their_options_and_value() -> None:
    """The two dropdown filters #475 moved onto ``components.dropdown_filter``, which
    no test named before: present by id, unset by default, set by their query keys,
    and their options GA's own candidates by name and every popular-vote status."""
    candidates = {(r["candidate_slug"], str(r["candidate"])) for r in ga_body()["data"]}
    tree = render()
    candidate = find(tree, "state-candidate")
    pv_status = find(tree, "state-pv-status")
    assert candidate is not None and pv_status is not None
    assert (candidate.value, pv_status.value) == (None, None)
    assert candidate.options == _by_label(candidates)
    # Labels and values, in the table's order (#540, AC3).
    assert pv_status.options == [
        {"label": labels.PV_STATUS[k], "value": k} for k in labels.PV_STATUS
    ]
    filtered = render("candidate=abraham-lincoln&pv_status=popular_vote")
    assert find(filtered, "state-candidate").value == "abraham-lincoln"
    assert find(filtered, "state-pv-status").value == "popular_vote"
    # Each label names its field, and the placeholder is another string: the page
    # passes them to the helper in that order (#475's acceptance gate).
    shown = {
        label.htmlFor: label.children
        for label in of_type(tree, "Label")
        if label.htmlFor in ("state-candidate", "state-pv-status")
    }
    assert shown == {
        "state-candidate": labels.LABELS["candidate"],
        "state-pv-status": labels.LABELS["pv_status"],
    }
    assert candidate.placeholder != shown["state-candidate"]
    assert pv_status.placeholder != shown["state-pv-status"]


# --- the wide layout (#545, D102) -------------------------------------------------------


class TestWideLayout:
    """The state history's filters at desktop width (#545): one ``.filters`` box that
    is a filter row, the slider's box first on a row of its own, then the two dropdown
    filters in source order. The rules are pinned in ``TestLayoutRules``
    (``test_dashboard_theme.py``) and what a browser draws in
    ``tests/e2e/test_dashboard_e2e_history.py``."""

    @pytest.mark.parametrize("query", ["", "candidate=abraham-lincoln&year_from=1860"])
    def test_the_slider_has_its_own_row_and_the_dropdowns_share_one(
        self, query: str
    ) -> None:
        tree = render(query)
        (box,) = classed(tree, "filters")
        assert box.className.split() == ["filters", "filter-row"]
        kids = list(box.children)
        assert [k.className.split() for k in kids] == [
            ["filter", "filter-own-row"],
            ["filter"],
            ["filter"],
        ]
        assert find(kids[0], MOD["YEARS_ID"]) is not None
        assert [d.id for d in of_type(kids[1:], "Dropdown")] == [
            MOD["CANDIDATE_ID"],
            MOD["PV_STATUS_ID"],
        ]
        # Only the slider's box keeps its own row.
        assert classed(tree, "filter-own-row") == [kids[0]]

    def test_no_slot_is_built_after_the_lede(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The future chart slot after the lede is a placement only (#543 §6). The lede
        # is added by layout(), so the whole page is checked there: the heading, the
        # lede and the page body, nothing between; in the body, the filters straight
        # after the page's Location; and no chart anywhere.
        cached_client(monkeypatch)
        page = MOD["layout"](usps="GA")
        heading, lede, content = page.children
        assert type(heading).__name__ == "H1"
        assert type(lede).__name__ == "P" and lede.className == "lede"
        assert getattr(content, "id", None) == PAGE_ID
        kids = list(content.children)
        # The section links first (#559), then the page's Location and the filters.
        assert kids[0].id == state_view.SECTIONS_ID
        assert type(kids[1]).__name__ == "Location"
        assert kids[2].className.split()[:1] == ["filters"]
        assert of_type(page, "Figure") == []

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
        (box,) = classed(content, "filters")
        assert kids[2] is box
        assert box.className.split() == ["filters", "filter-row"]
        (own,) = box.children
        assert own.className.split() == ["filter", "filter-own-row"]
        assert find(own, PC_MOD["YEARS_ID"]) is not None
        assert of_type(page, "Figure") == []
