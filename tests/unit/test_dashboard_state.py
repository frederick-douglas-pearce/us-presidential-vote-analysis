"""The state history, T4, and the state picker (#279), and the state's people per
electoral vote page, T7 (#280; its own page since #559), with the section links
between a state's two pages (#559, D105).

Offline, against the recorded ``/v1/states/GA`` and ``/v1/states/TX`` (C7 and C10
run over both, #575) and the roster ``/v1/elections/2024``,
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
import re
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
TABLE = MOD["TABLE_ID"]
PC_PAGE_ID = PC_MOD["PAGE_ID"]
PER_CAPITA = PC_MOD["PER_CAPITA_TABLE_ID"]


#: Georgia's noted candidate-years (#575's re-record), in T4's order.
GA_NOTED = (
    (1824, "Henry Clay"),
    (1832, "John Floyd"),
    (1832, "William Wirt"),
    (1836, "Daniel Webster"),
    (1836, "Hugh L. White"),
    (1856, "Millard Fillmore"),
    (1860, "John Bell"),
    (1872, "Benjamin Gratz Brown"),
    (1872, "Charles J. Jenkins"),
    (1872, "Horace Greeley"),
    (1872, "Thomas A. Hendricks"),
    (1892, "James B. Weaver"),
    (1912, "William H. Taft"),
    (1924, "Robert M. La Follette"),
    (1948, "J. Strom Thurmond"),
    (1956, "Walter B. Jones"),
    (1960, "Harry F. Byrd"),
    (1968, "George C. Wallace"),
    (1972, "John Hospers"),
    (1976, "Ronald Reagan"),
    (1988, "Lloyd Bentsen"),
    (2004, "John Edwards"),
    (2016, "Bernie Sanders"),
    (2016, "Colin Powell"),
    (2016, "Faith Spotted Eagle"),
    (2016, "John Kasich"),
    (2016, "Ron Paul"),
)


def ga_body() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[GA_PATH])


def ga_per_capita() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[GA_PER_CAPITA_PATH])


def render(
    query: str = "", body: Any = None, index: Any = None, usps: str = "GA"
) -> Any:
    """The history page's body for ``query``, as the layout builds it: ``usps``'s
    recorded history unless ``body`` is given."""
    content, _ = MOD["render"](
        copy.deepcopy(RECORDED[f"/v1/states/{usps}"]) if body is None else body,
        copy.deepcopy(INDEX) if index is None else index,
        usps,
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
        # Clay's party comes from the USGOV catalog since #575's re-record (#388).
        assert texts(cells[("1824", "Henry Clay")]) == ["Democratic-Republican"]
        notes = {
            (r["year"], r["candidate"]): r["nominating_party_note"]
            for r in ga_body()["data"]
            if r["nominating_party_note"]
        }
        # A null with its one-cause note, on a doctored row: the USGOV catalog (#388)
        # keeps filling the recorded nulls (#575).
        body = ga_body()
        target = [r for r in body["data"] if r["year"] == 1900]
        assert target and all(r["nominating_party"] for r in target)  # the premise
        for row in target:
            row.update(
                nominating_party=None,
                nominating_party_source=None,
                nominating_party_note=None,
            )
        doctored = {
            (texts(r[0])[0], texts(r[1])[0]): r[index]
            for r in table_rows(render(body=body))
        }
        for row in target:
            null = doctored[("1900", row["candidate"])]
            assert texts(null) == [labels.NOT_IN_DATASET]
            assert null.title == labels.PARTY_NULL_NOTE
        note = notes[(1872, "Horace Greeley")]
        assert cells[("1872", "Horace Greeley")].title == note
        (block,) = [
            d
            for d in of_type(render(), "Div")
            if getattr(d, "className", None) == "party-notes"
        ]
        # Every noted candidate-year once, in the table's year order.
        assert [li.children for li in of_type(block, "Li")] == [
            labels.PARTY_NOTE_ITEM.format(
                candidate=name, year=year, note=notes[(year, name)]
            )
            for year, name in GA_NOTED
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
        # of the filter sentence; people per electoral vote left the lede with T7
        # (#559), and the electors appointed came in with C7, which the filters do not
        # reach, so the filter sentence names the table they narrow (#560); C10's total
        # popular vote came in after it (#582; ba spec, approved at its plan gate).
        assert MOD["FILTER_SENTENCE"] == (
            "Narrow the table of each candidate's electoral votes by year, candidate "
            "or popular-vote status."
        )
        assert f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}" == (
            "This state's electors appointed, its total popular vote and its "
            "electoral votes for each candidate in every election this dataset holds "
            "for it, with popular-vote figures where the dataset has them. Narrow the "
            "table of each candidate's electoral votes by year, candidate or "
            "popular-vote status."
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

    def test_c7_and_c10_s_section_comes_after_the_section_links_and_before_t4_s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # #560, D106; #618, D117: the lede is added by layout(), so the whole page is
        # checked there: the heading, the lede and the page body, nothing between. In
        # the body, the section links first (#559, D105); then one card holding C7's
        # heading, its headline figures (#601, D115), C7, C10's heading, C10, the
        # heading of the table the two share, the table in its scroll box, its
        # download, its notes and its column-name list; then T4's, under its own
        # heading, with the page's Location and the filters that narrow it. Two
        # charts, C7 and C10.
        cached_client(monkeypatch)
        page = MOD["layout"](usps="GA")
        heading, lede, content = page.children
        assert type(heading).__name__ == "H1"
        assert type(lede).__name__ == "P" and lede.className == "lede"
        assert getattr(content, "id", None) == PAGE_ID
        kids = list(content.children)
        assert kids[0].id == state_view.SECTIONS_ID
        # Two cards (#567, D111; #618, D117): C7 and C10 with their table, then T4's.
        assert cards(content) == kids[1:3]
        charts_card = card_children(content, 1)
        assert [type(k).__name__ for k in charts_card[:6]] == [
            "H2",
            "Div",
            "Figure",
            "H2",
            "Figure",
            "H2",
        ]
        assert charts_card[0].children == MOD["C7_HEADING"]
        assert charts_card[1].id == MOD["METRICS_ID"]
        assert charts_card[2].id == charts.dom_id(MOD["C7_ID"])
        assert charts_card[3].children == MOD["C10_HEADING"]
        assert charts_card[4].id == charts.dom_id(MOD["C10_ID"])
        assert charts_card[5].children == MOD["ELECTORS_TOTALS_TABLE_HEADING"]
        # The one table and its column-name list follow both charts, in their card.
        assert find(charts_card, MOD["ELECTORS_TABLE_ID"]) is not None
        assert find(charts_card, MOD["ELECTORS_GLOSSARY_ID"]) is not None
        assert find(charts_card, MOD["TABLE_ID"]) is None
        # The retired table and its list are gone (D097(g): never reused).
        assert find(content, "state-popular-total") is None
        assert find(content, "state-popular-total-glossary") is None
        t4 = card_children(content, 2)
        assert type(t4[0]).__name__ == "H2"
        assert t4[0].children == MOD["HISTORY_TABLE_HEADING"]
        assert type(t4[1]).__name__ == "Location"
        assert t4[2].className.split()[:1] == ["filters"]
        assert find(t4, MOD["TABLE_ID"]) is not None
        assert find(t4, MOD["ELECTORS_TABLE_ID"]) is None
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
        records = MOD["electors"](
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
        expected = over_time.c4_figure(
            over_time.appointed_points(n2),
            SERVED,
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
            records = MOD["electors"](n2, set(SERVED), usps, "N2")
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

    @pytest.mark.parametrize("query", ["", "year_from=1900&candidate=jimmy-carter"])
    def test_the_table_s_links_view_and_note(self, query: str) -> None:
        # The table C7 shares with C10 (#618), never T4: each year links to that
        # election's page, its file names the history page with no filter whatever the
        # render applied (D093(a)), and the allotment's basis is among its notes, under
        # the table and in the file's preamble (#560's acceptance gate, Class B).
        tree = render(query)
        rows = body_rows(tree, ELECTORS)
        assert rows
        for tr in rows:
            (link,) = of_type(tr.children[0], "Link")
            assert link.href == f"/election/{link.children}"
        lines = download(tree, ELECTORS).lines
        assert "View: https://explore.us-presidential-election-center.org/state/GA" in (
            lines
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

    def test_texas_s_first_election_is_named_on_its_own_history(self) -> None:
        """Texas's first election, 1848, is after the dataset's, so its caption names
        it and its axis keeps the dataset's span (on real data; the doctored Georgia
        case is :meth:`test_a_later_first_election_is_named_and_the_axis_keeps_the_dataset_s`)."""
        tree = render(usps="TX")
        assert labels.FIRST_ELECTION_NOTE.format(state="Texas", year=1848) in (
            c7_caption(tree)
        )
        assert c7_figure(tree)["layout"]["xaxis"] == components.year_axis(SERVED)

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

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "year_from=1900",
            "year_to=1900",
            "candidate=andrew-jackson",
            "pv_status=not_participating",
            "year_from=1700&year_to=1800",
        ],
    )
    def test_no_filter_changes_the_chart_or_its_table(self, query: str) -> None:
        plain = render()
        tree = render(query)
        assert c7_figure(tree) == c7_figure(plain)
        assert download(tree, ELECTORS).raw == download(plain, ELECTORS).raw
        assert c7_caption(tree) == c7_caption(plain)

    def test_the_caption_describes_the_series(self) -> None:
        caption = c7_caption(render())
        assert caption.startswith(labels.C4_BASIS)
        assert labels.C7_FILTERS_NOTE in caption
        # Georgia's first election is the dataset's, so no first-election sentence.
        assert "The first election in this dataset" not in caption
        assert labels.C4_NO_FIGURE_NOTE not in caption

    def test_a_later_first_election_is_named_and_the_axis_keeps_the_dataset_s(
        self,
    ) -> None:
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] >= 1832]
        tree = render(body=body)
        assert labels.FIRST_ELECTION_NOTE.format(state="Georgia", year=1832) in (
            c7_caption(tree)
        )
        figure = c7_figure(tree)
        assert figure["layout"]["xaxis"] == components.year_axis(SERVED)

    def test_the_first_election_sentence_follows_the_served_years_not_coverage(
        self,
    ) -> None:
        # The sentence compares the state's first election with the first served
        # year (the index's, as C4 does), never the body's ``coverage.year_min``: with
        # coverage starting before 1824, Georgia's 1824 is still the dataset's first.
        body = ga_body()
        body["meta"]["provenance"]["coverage"]["year_min"] = 1700
        tree = render(body=body)
        assert "The first election in this dataset" not in c7_caption(tree)

    def test_a_name_that_is_not_plain_text_takes_this_state_s_forms(self) -> None:
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] >= 1832]
        for row in body["data"]:
            row["state"] = "<b>Georgia"
        tree = render(body=body)
        figure = c7_figure(tree)
        assert c7_title(tree) == labels.C7_TITLE_THIS_STATE
        assert labels.FIRST_ELECTION_NOTE_THIS_STATE.format(year=1832) in (
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
    when the table gives way to :data:`ELECTORS_TOTALS_TABLE_UNAVAILABLE`. T4, its
    filters and the page's success marker stay either way."""

    def assert_degraded(self, body: dict[str, Any], *, both: bool) -> None:
        tree = render(body=body)
        assert getattr(tree, "id", None) == PAGE_ID
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert (find(tree, MOD["C10_UNAVAILABLE_ID"]) is not None) is both
        assert [f.id for f in of_type(tree, "Figure")] == ([] if both else [C10_DOM])
        assert c7_figure(tree) is None
        # The figures are built from C7's collapse, so they go with it (D115(g)).
        assert find(tree, MOD["METRICS_ID"]) is None
        assert find(tree, TABLE) is not None
        assert find(tree, MOD["YEARS_ID"]) is not None
        headings = [h.children for h in of_type(tree, "H2")]
        assert headings[:4] == [
            MOD["C7_HEADING"],
            MOD["C10_HEADING"],
            MOD["ELECTORS_TOTALS_TABLE_HEADING"],
            MOD["HISTORY_TABLE_HEADING"],
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
        # C7's note is in the page's first card, with C10 and the table (#618), and T4
        # in the second (#567).
        c7 = in_one_card(tree, MOD["C7_UNAVAILABLE_ID"], total=2)
        assert in_one_card(tree, TABLE, total=2) is not c7
        assert every_card(tree)[0] is c7

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

    def test_two_allotments_leave_c10_exactly_as_it_was(self) -> None:
        """#582 (D113(c)), AC5's converse, kept inside one table by #618 (D117): an
        allotment C7 cannot read leaves C10, its column and the status column the
        undoctored render's (T4 shows the allotment, so its file changes, and T4
        stays)."""
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
        assert find(tree, TABLE) is not None

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
        # T4 reads the field too, so this degrades the page rather than C7 alone: a
        # fault in what T4 shows is never swallowed by C7's section.
        with pytest.raises(KeyError):
            render(body=body)

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
        assert lede.children == f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}"
        assert find(content, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert find(content, C7_DOM) is None
        assert find(content, TABLE) is not None


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
        content, _ = MOD["render"](body, copy.deepcopy(INDEX), usps, [])
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

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "year_from=1900",
            "year_to=1900",
            "candidate=jimmy-carter",
            "pv_status=not_participating",
            "year_from=1700&year_to=1800",
        ],
    )
    def test_no_filter_changes_the_chart_or_its_table(self, query: str) -> None:
        plain = render()
        tree = render(query)
        assert c10_figure(tree) == c10_figure(plain)
        assert download(tree, TOTALS).raw == download(plain, TOTALS).raw
        assert c10_caption(tree) == c10_caption(plain)

    def test_the_caption_describes_the_series(self) -> None:
        caption = c10_caption(render())
        assert caption.startswith(labels.C5_BASIS)
        assert labels.C10_SHORT_TICKS_NOTE in caption
        assert labels.C5_BEFORE_NOTE.format(pv_year_min=WINDOW[0]) in caption
        assert labels.C5_MARKER_NOTE in caption
        assert caption.index(labels.C7_FILTERS_NOTE) > caption.index(
            labels.C5_MARKER_NOTE
        )
        assert "The first election in this dataset" not in caption

    def test_a_later_first_election_and_a_name_that_is_not_plain_text(self) -> None:
        body = ga_body()
        body["data"] = [r for r in body["data"] if r["year"] >= 1832]
        tree = render(body=body)
        assert labels.C10_TITLE_STATE.format(state="Georgia") == c10_title(tree)
        assert labels.C10_FIRST_ELECTION_NOTE.format(state="Georgia", year=1832) in (
            c10_caption(tree)
        )
        assert c10_figure(tree)["layout"]["xaxis"] == components.year_axis(SERVED)
        for row in body["data"]:
            row["state"] = "<b>Georgia"
        tree = render(body=body)
        assert c10_title(tree) == labels.C10_TITLE_THIS_STATE
        assert labels.C10_FIRST_ELECTION_NOTE_THIS_STATE.format(year=1832) in (
            c10_caption(tree)
        )
        hovers = hovers_by_year(c10_figure(tree)).values()
        assert all(charts.escaped("<b>Georgia") in h for h in hovers)

    def test_the_table_s_links_view_and_notes(self) -> None:
        tree = render("year_from=1900&candidate=jimmy-carter")
        for tr in body_rows(tree, TOTALS):
            (link,) = of_type(tr.children[0], "Link")
            assert link.href == f"/election/{link.children}"
        lines = download(tree, TOTALS).lines
        assert "View: https://explore.us-presidential-election-center.org/state/GA" in (
            lines
        )
        assert labels.C5_BASIS in lines
        # C7, C10 and their one table share the page's first card (#567, #618).
        card = in_one_card(tree, TOTALS, total=2)
        assert in_one_card(tree, C10_DOM, total=2) is card
        assert in_one_card(tree, C7_DOM, total=2) is card
        assert every_card(tree)[0] is card


class TestSharedTable:
    """The one table C7 and C10 share (#618, D117): joined on the year from the two
    collapses, each column the cells its chart's hover writes, its notes by a fixed
    rule, and a build that never takes the page down."""

    @pytest.mark.parametrize("usps", RECORDED_STATES)
    def test_c7_s_and_c10_s_status_cells_agree_every_year(self, usps: str) -> None:
        # The status column is taken from C7's points; C10's must say the same (m-5).
        body = copy.deepcopy(RECORDED[f"/v1/states/{usps}"])
        rows = state_view.rows(body, usps, set(SERVED), f"/v1/states/{usps}")
        c7 = MOD["_electors_part"](rows, set(SERVED), usps, "src")
        c10 = MOD["_totals_part"](rows, set(SERVED), usps, body, "src")
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
        body = ga_body()
        rows = state_view.rows(body, "GA", set(SERVED), GA_PATH)
        c7 = MOD["_electors_part"](rows, set(SERVED), "GA", GA_PATH)
        c10 = MOD["_totals_part"](rows, set(SERVED), "GA", body, GA_PATH)
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
        assert find(tree, TABLE) is not None
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
    """AC5 as #618 keeps it (owner's ruling, D117): a body T4 accepts whose total
    popular vote C10 cannot read as one per election puts :data:`C10_UNAVAILABLE` in
    C10's place, with no chart and no ``c10`` id, and the shared table's total column
    reads unavailable with :data:`TOTALS_UNAVAILABLE_NOTE` first among its notes and no
    window note, while C7 (exactly as it was), the headline figures, the electors and
    status columns, T4, its filters and the page's success marker stay (D113(c))."""

    def assert_degraded(self, body: dict[str, Any], *, t4_file: bool = True) -> None:
        """``t4_file``: T4's CSV equals the undoctored render's; false only where the
        doctoring is in the provenance its preamble writes (the window)."""
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
        if t4_file:
            assert download(tree, TABLE).raw == download(plain, TABLE).raw
        else:
            assert download(tree, TABLE).rows == download(plain, TABLE).rows
        assert find(tree, MOD["YEARS_ID"]) is not None
        assert find(tree, MOD["ELECTORS_TABLE_UNAVAILABLE_ID"]) is None
        headings = [h.children for h in of_type(tree, "H2")]
        assert MOD["C10_HEADING"] in headings
        card = in_one_card(tree, MOD["C10_UNAVAILABLE_ID"], total=2)
        assert every_card(tree)[0] is card

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
        inverted or mistyped one that T4 can still compare degrades C10 alone, never
        a self-contradicting caption."""
        body = ga_body()
        coverage = body["meta"]["provenance"]["coverage"]
        coverage["pv_year_min"], coverage["pv_year_max"] = window
        self.assert_degraded(body, t4_file=False)
        # Accepted leftover (#618's architect review, m-1; D117): the file still
        # carries a popular-vote field, so its preamble writes the window as served.
        lines = download(render(body=body), ELECTORS).lines
        assert f"Popular votes cover {window[0]}–{window[1]}" in lines

    @pytest.mark.parametrize("window", [(1976, "2024"), (None, 2024)])
    def test_a_window_t4_cannot_compare_degrades_the_page(
        self, window: tuple[Any, Any]
    ) -> None:
        # T4's popular-vote cells compare each year with the window first, so a fault
        # in what T4 shows is never swallowed by C10's section (as C7's
        # ``test_a_row_without_the_allotment``).
        body = ga_body()
        coverage = body["meta"]["provenance"]["coverage"]
        coverage["pv_year_min"], coverage["pv_year_max"] = window
        with pytest.raises(TypeError):
            render(body=body)

    @pytest.mark.parametrize("bound", ["pv_year_min", "pv_year_max"])
    @pytest.mark.parametrize(
        "query", ["", "year_from=1824&year_to=1824&pv_status=popular_vote"]
    )
    def test_a_missing_window_bound_degrades_the_page_in_every_view(
        self, bound: str, query: str
    ) -> None:
        """#629's review, cr.1 (D117 as amended): ``render`` reads both bounds before
        either half, so a missing one is the page's in every view, T4's empty result
        included, where the shared table's download preamble would read it anyway."""
        body = ga_body()
        del body["meta"]["provenance"]["coverage"][bound]
        if query:
            # The view leaves T4 empty (no table, no download), so only the shared
            # table's preamble would read the window: the case main kept the page in.
            assert find(render(query), TABLE) is None
        with pytest.raises(KeyError):
            render(query, body=body)

    @pytest.mark.parametrize("bound", ["pv_year_min", "pv_year_max"])
    def test_a_missing_bound_degrades_the_page_where_nothing_else_reads_it(
        self, bound: str
    ) -> None:
        """The mechanism, not only the outcome: with both halves failed (two statuses in
        1900) there is no shared table, and T4's view is empty, so no download
        preamble reads the window; only ``render``'s own read makes a missing bound the
        page's (D117 as amended)."""
        query = "year_from=1824&year_to=1824&pv_status=popular_vote"
        body = ga_body()
        (first, *_) = [r for r in body["data"] if r["year"] == 1900]
        first["pv_status"] = "legislature_chosen"
        kept = render(query, body=copy.deepcopy(body))
        assert getattr(kept, "id", None) == PAGE_ID
        assert find(kept, ELECTORS) is None and find(kept, TABLE) is None
        del body["meta"]["provenance"]["coverage"][bound]
        with pytest.raises(KeyError):
            render(query, body=body)

    def test_a_malformed_window_with_t4_empty_degrades_c10_alone(self) -> None:
        """#629's review, cr.1: a bound that is present and malformed stays C10's half's
        to refuse, so the page, C7 and the shared table stay in a view T4 shows
        nothing in."""
        body = ga_body()
        coverage = body["meta"]["provenance"]["coverage"]
        coverage["pv_year_min"], coverage["pv_year_max"] = (2000, 1990)
        tree = render("year_from=1824&year_to=1824&pv_status=popular_vote", body=body)
        assert getattr(tree, "id", None) == PAGE_ID
        assert find(tree, MOD["C10_UNAVAILABLE_ID"]) is not None
        assert c7_figure(tree) is not None
        assert find(tree, ELECTORS) is not None
        assert set(column(tree, "state_popular_total")) == {""}

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
        assert find(tree, TABLE) is not None

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

    def test_georgia_equals_the_state_history(self) -> None:
        history = {r["year"]: r for r in RECORDED["/v1/states/GA"]["data"]}
        for row in [r for r in N2["data"] if r["state_usps"] == "GA"]:
            assert (
                row["state_electoral_votes"]
                == history[row["year"]]["state_electoral_votes"]
            )
            assert row["pv_status"] == history[row["year"]]["pv_status"]

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
    def test_t4_s_filters_never_reach_them(self, query: str) -> None:
        plain, filtered = render(), render(query)
        assert texts(find(filtered, TABLE)) != texts(find(plain, TABLE))
        for key in ST_FIGURE_IDS:
            assert st_figure(filtered, key) == st_figure(plain, key), (query, key)

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
        # Architect I3 (D115): the flag figure alone reads it; the count, C7, T4 and
        # the page stay, so nothing it reads reaches C7's section's except.
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
        assert c7_figure(tree) is not None
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is None
        assert find(tree, TABLE) is not None and tree.id == PAGE_ID

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
    def test_an_allotment_no_count_can_read_makes_both_unrecognized_and_keeps_c7(
        self, value: Any
    ) -> None:
        # Architect I4 (D115): set on every row of 1828, so C7's collapse holds one
        # value; C7 draws it as a marker and stays, as T4 and the page do.
        body = ga_body()
        for row in body["data"]:
            if row["year"] == 1828:
                row["state_electoral_votes"] = value
        tree = render(body=body)
        for key in ST_FIGURE_IDS:
            assert st_figure(tree, key) == labels.UNRECOGNIZED, key
        assert find(tree, MOD["METRICS_NOTE_ID"]) is None
        assert c7_figure(tree) is not None
        assert find(tree, TABLE) is not None and tree.id == PAGE_ID

    def test_a_collapse_fault_removes_them_with_c7(self) -> None:
        # D112(c)'s precedent: C7's collapse is their input, so two allotments in one
        # year degrade C7's section and the figures go with it; T4 stays.
        body = ga_body()
        rows_1828 = [r for r in body["data"] if r["year"] == 1828]
        rows_1828[0]["state_electoral_votes"] += 1
        tree = render(body=body)
        assert find(tree, MOD["C7_UNAVAILABLE_ID"]) is not None
        assert find(tree, ST_FIGURES) is None
        assert find(tree, TABLE) is not None

    def test_no_year_with_electors_says_so_for_both(self) -> None:
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

    def test_they_sit_in_c7_s_card_after_its_heading_and_before_the_chart(
        self,
    ) -> None:
        tree = render()
        card = in_one_card(tree, ST_FIGURES, total=2)
        assert find(card, charts.dom_id(MOD["C7_ID"])) is not None
        order = [getattr(n, "id", None) for n in components._within(card.children)]
        assert order.index(ST_FIGURES) < order.index(charts.dom_id(MOD["C7_ID"]))

    def test_the_page_still_makes_the_same_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route("/state/GA"))
        assert ST_FIGURES in ids and all(i in ids for i in ST_FIGURE_IDS.values())
        assert calls == [GA_PATH]
