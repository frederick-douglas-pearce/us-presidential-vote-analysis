"""A state's results by election, T4 (#279), on its own page at
``/state/<usps>/elections`` since #619 (D118), moved off the state history.

Offline, against the recorded ``/v1/states/GA`` and the roster ``/v1/elections/2024``
(the same snapshot as every other fixture), through the helpers and the autouse
offline process client of ``test_dashboard_app.py``. The history page's own tests,
and the section links between a state's three pages on the history and per-capita
pages, are in ``test_dashboard_state.py``, whose shared helpers this module imports;
the registry-wide checks in ``test_dashboard_app.py`` pick the page up, and the old
filtered history links that now 302 here are pinned there (``TestMovedStateFilters``).
"""

from __future__ import annotations

import copy
import random
from typing import Any

import dash
import pytest
from dash import no_update

import tests.unit.test_dashboard_state as state_tests
from explore import api, labels, state_view
from tests.dashboard_cards import card_children, cards
from tests.unit.test_dashboard_app import (
    RECORDED,
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

PAGE: dict[str, Any] = dash.page_registry["pages.state_results"]
#: The page module's namespace, reached through its layout (Dash loads it by path).
MOD: dict[str, Any] = PAGE["layout"].__globals__
HISTORY: dict[str, Any] = dash.page_registry["pages.state"]
HISTORY_MOD: dict[str, Any] = HISTORY["layout"].__globals__
PC_MOD: dict[str, Any] = dash.page_registry["pages.state_per_capita"][
    "layout"
].__globals__

INDEX: dict[str, Any] = state_tests.INDEX
ROSTER_PATH = state_tests.ROSTER_PATH
GA_PATH = state_tests.GA_PATH
PAGE_ID = MOD["PAGE_ID"]
TABLE = MOD["TABLE_ID"]
PATH = "/state/GA/elections"
ga_body = state_tests.ga_body

#: T4's ids on the history page before #619, retired and never reused (D097(g), D118).
RETIRED_IDS = (
    "state-history",
    "state-history-csv",
    "state-url",
    "state-years",
    "state-candidate",
    "state-pv-status",
)

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


def render(
    query: str = "", body: Any = None, index: Any = None, usps: str = "GA"
) -> Any:
    """The results page's body for ``query``, as the layout builds it: ``usps``'s
    recorded history unless ``body`` is given."""
    content, _ = MOD["render"](
        copy.deepcopy(RECORDED[f"/v1/states/{usps}"]) if body is None else body,
        copy.deepcopy(INDEX) if index is None else index,
        usps,
        MOD["parse_filters"](parse(query)),
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


def admitted_1912() -> dict[str, Any]:
    """Georgia's body cut to 1912 on: a state admitted that year, as Arizona was."""
    body = ga_body()
    body["data"] = [r for r in body["data"] if r["year"] >= 1912]
    return body


def serving(monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]) -> list[str]:
    """A process client serving the recordings with ``body`` as Georgia's history,
    the index and the roster cached; returns its call list, cleared."""
    fetch, calls = fake_fetch({**RECORDED, GA_PATH: body})
    client = offline_client(
        fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, ROSTER_PATH]
    )
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    calls.clear()
    monkeypatch.setattr(api, "CLIENT", client)
    return calls


# --- registration -----------------------------------------------------------------------


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path_template"] == "/state/<usps>/elections"
    # Ahead of the history page's greedy <usps> (#619, as #559 ordered the per-capita
    # page); test_dashboard_app.TestStatePages checks the routing.
    assert PAGE["order"] == 1
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    # The history page's one response: a visit after it makes no request.
    assert PAGE["on_miss"] == (api.ROSTER_PATH, "/v1/states/{usps}")
    assert PAGE["on_miss"] == HISTORY["on_miss"]
    assert PAGE["success"] == PAGE_ID
    # The registered judge is the one the layout calls, and the history page's, so a
    # code is decided alike on every state page and a moved link never 404s.
    assert PAGE["validate"] is MOD["VALIDATE"]
    assert PAGE["validate"] == HISTORY["validate"]
    assert PAGE["query"] is MOD["parse_filters"]
    assert PAGE.get("moved") is None
    assert PAGE["nav"] == HISTORY["nav"] == "states"
    assert MOD["NOT_FOUND"] == HISTORY_MOD["NOT_FOUND"]
    # Its two keys besides the year range are the ones the history page moves here.
    assert (MOD["CANDIDATE"], MOD["PV_STATUS"]) == state_view.MOVED_KEYS
    assert state_view.MOVED_KEYS == ("candidate", "pv_status")


def test_its_ids_are_its_own_and_t4_s_old_ids_are_retired() -> None:
    """Dash keys callbacks by output, app-wide, so the page's ids differ from the
    per-capita page's; and T4's history ids are never reused (D097(g), D118)."""
    ids = {
        MOD[k]
        for k in (
            "PAGE_ID",
            "NOT_FOUND_ID",
            "TABLE_ID",
            "URL_ID",
            "YEARS_ID",
            "CANDIDATE_ID",
            "PV_STATUS_ID",
        )
    }
    assert ids == {
        "state-results-page",
        "state-results-not-found",
        "state-results",
        "state-results-url",
        "state-results-years",
        "state-results-candidate",
        "state-results-pv-status",
    }
    assert PC_MOD["URL_ID"] != MOD["URL_ID"]
    assert PC_MOD["YEARS_ID"] != MOD["YEARS_ID"]
    for tree in (render(), state_tests.render()):
        assert not set(RETIRED_IDS) & component_ids(tree)


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

    def test_the_heading_names_the_state_from_the_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, name = MOD["render"](ga_body(), copy.deepcopy(INDEX), "GA", [])
        assert name == "Georgia"
        cached_client(monkeypatch)
        heading, _, content = MOD["layout"](usps="GA").children
        assert heading.children == "Georgia: results by election"
        assert content.id == PAGE_ID

    @pytest.mark.parametrize("name", ["", "  ", "​"], ids=repr)
    def test_a_name_with_nothing_in_it_keeps_the_generic_heading(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        body = ga_body()
        for row in body["data"]:
            row["state"] = name
        serving(monkeypatch, body)
        heading, _, content = MOD["layout"](usps="GA").children
        assert heading.children == MOD["RESULTS_GENERIC_HEADING"]
        assert MOD["RESULTS_GENERIC_HEADING"] == "State: results by election"
        assert content.id == PAGE_ID

    def test_the_page_shows_no_chart_and_no_other_page_s_table(self) -> None:
        tree = render()
        assert of_type(tree, "Figure") == []
        assert find(tree, HISTORY_MOD["ELECTORS_TABLE_ID"]) is None
        assert find(tree, PC_MOD["PER_CAPITA_TABLE_ID"]) is None


# --- malformed bodies degrade --------------------------------------------------------


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
        render(body=state_tests.mutated(position, **change))


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


class TestPopularVoteWindow:
    """D118: ``render`` checks the popular-vote window with ``query.year_span`` before
    any cell reads it, since T4's cells read it only on some rows; so a missing or
    malformed window degrades the page in every view, the empty one included."""

    #: The default view, and two views that leave T4 empty: a range before the
    #: state's first election (on the 1912 body) and a status no 1824 row has.
    VIEWS = [
        ("", None),
        ("year_to=1900", admitted_1912),
        ("year_from=1824&year_to=1824&pv_status=popular_vote", None),
    ]

    @staticmethod
    def body_for(make: Any) -> dict[str, Any]:
        return ga_body() if make is None else make()

    @pytest.mark.parametrize(("query", "make"), VIEWS, ids=lambda v: repr(v))
    def test_the_views_premise(self, query: str, make: Any) -> None:
        tree = render(query, body=self.body_for(make))
        assert getattr(tree, "id", None) == PAGE_ID
        # The empty views show no table, so no cell would read the window there.
        assert (table_rows(tree) == []) is bool(query)

    @pytest.mark.parametrize("bound", ["pv_year_min", "pv_year_max"])
    @pytest.mark.parametrize(("query", "make"), VIEWS, ids=lambda v: repr(v))
    def test_a_missing_bound_degrades_the_page_in_every_view(
        self, bound: str, query: str, make: Any
    ) -> None:
        body = self.body_for(make)
        del body["meta"]["provenance"]["coverage"][bound]
        with pytest.raises(KeyError):
            render(query, body=body)

    @pytest.mark.parametrize(
        "window",
        [(2000, 1990), (True, 2024), (1976, 1976.5), (1976, "2024"), (None, 2024)],
        ids=repr,
    )
    @pytest.mark.parametrize(("query", "make"), VIEWS, ids=lambda v: repr(v))
    def test_a_malformed_window_degrades_the_page_in_every_view(
        self, window: tuple[Any, Any], query: str, make: Any
    ) -> None:
        body = self.body_for(make)
        coverage = body["meta"]["provenance"]["coverage"]
        coverage["pv_year_min"], coverage["pv_year_max"] = window
        with pytest.raises(TypeError, match="span"):
            render(query, body=body)

    @pytest.mark.parametrize("search", ["", "?year_to=1900", "?pv_status=popular_vote"])
    @pytest.mark.parametrize("fault", ["missing", "malformed"])
    def test_the_routed_page_shows_the_degraded_state(
        self, monkeypatch: pytest.MonkeyPatch, search: str, fault: str
    ) -> None:
        body = ga_body()
        coverage = body["meta"]["provenance"]["coverage"]
        if fault == "missing":
            del coverage["pv_year_max"]
        else:
            coverage["pv_year_min"], coverage["pv_year_max"] = (2000, 1990)
        serving(monkeypatch, body)
        ids = routed_ids(route(PATH, search))
        assert "unavailable" in ids
        assert PAGE_ID not in ids and TABLE not in ids


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

    def test_a_range_before_the_states_first_election_is_an_honest_empty_result(
        self,
    ) -> None:
        # The dataset's span judges the bound (Fred, option (i)): 1900 is a year the
        # dataset holds, so it is kept, and the state has no election in range.
        for search in ("year_to=1900", "year_from=1824&year_to=1900"):
            tree = render(search, body=admitted_1912())
            assert table_rows(tree) == [], search
            assert "No rows match these filters." in texts(tree)
            (slider,) = of_type(tree, "RangeSlider")
            assert slider.value == [1824, 1900]

    def test_the_slider_spans_the_dataset_and_shows_the_selection(self) -> None:
        tree = render("year_from=1900", body=admitted_1912())
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

    def test_the_download_names_the_page_the_table_and_the_filters_applied(
        self,
    ) -> None:
        tree = render("year_from=1860&year_to=1872&candidate=horatio-seymour&junk=1")
        file = download(tree, TABLE)
        (view,) = [line for line in file.lines if line.startswith("View: ")]
        assert view == (
            "View: https://explore.us-presidential-election-center.org/state/GA/"
            "elections?candidate=horatio-seymour&year_from=1860&year_to=1872"
        )
        assert {r["year"] for r in file.rows} == {"1868"}


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
    rows = table_rows(render())
    assert rows
    for row in rows:
        (link,) = of_type(row[0], "Link")
        assert link.href == f"/election/{link.children}"


class TestSectionLinks:
    """On the results page (#619): the history link, then the page itself as text
    carrying ``aria-current="page"``, then the per-capita link, both links carrying
    the year range the render applied and nothing else (D105, D118). The history and
    per-capita pages' links are in ``test_dashboard_state.TestSectionLinks``."""

    def test_the_results_page_is_marked_between_the_other_two(self) -> None:
        history, current, per_capita = state_tests.section_entries(render())
        assert type(current).__name__ == "Span"
        assert current.children == labels.SECTION_RESULTS_BY_ELECTION
        assert getattr(current, "aria-current") == "page"
        assert [type(e).__name__ for e in (history, per_capita)] == ["Link", "Link"]
        assert history.children == labels.SECTION_STATE_HISTORY
        assert per_capita.children == labels.SECTION_PER_CAPITA
        assert (history.href, per_capita.href) == ("/state/GA", "/state/GA/per-capita")

    @pytest.mark.parametrize(
        ("query", "carried"),
        [
            ("year_from=1860&year_to=1900", "?year_from=1860&year_to=1900"),
            (
                "year_to=1900&candidate=horatio-seymour&pv_status=popular_vote",
                "?year_to=1900",
            ),
            ("candidate=horatio-seymour", ""),
            # A bound outside the span falls back, so it is not carried.
            ("year_from=1700&year_to=1900", "?year_to=1900"),
            ("year_from=1824&year_to=2024", ""),
        ],
    )
    def test_each_link_carries_the_range_applied_only(
        self, query: str, carried: str
    ) -> None:
        history, _, per_capita = state_tests.section_entries(render(query))
        assert history.href == f"/state/GA{carried}"
        assert per_capita.href == f"/state/GA/per-capita{carried}"

    def test_the_links_come_first_in_the_body(self) -> None:
        assert render().children[0].id == state_view.SECTIONS_ID


# --- validation at the index and at render, and the request budget -------------------


class TestRoster:
    def test_a_served_state_renders_with_one_request_shared_with_the_history(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route(PATH))
        assert PAGE_ID in ids and TABLE in ids
        assert calls == [GA_PATH]
        assert len(bucket.waits) == 1
        calls.clear()
        # The history page reads the same response: no second request either way.
        assert HISTORY_MOD["PAGE_ID"] in routed_ids(route("/state/GA"))
        assert PAGE_ID in routed_ids(route(PATH))
        assert calls == []

    def test_filter_changes_make_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        route(PATH)
        calls.clear()
        for search in ("?year_from=1860", "?candidate=horatio-seymour", ""):
            assert PAGE_ID in routed_ids(route(PATH, search))
        MOD["on_filter_change"]([1860, 2024], None, None, 1824, 2024, "")
        assert calls == []

    @pytest.mark.parametrize("path", ["/state/ZZ/elections", "/state/QQ/elections"])
    def test_an_unserved_code_is_not_found_and_fills_nothing(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        ids = routed_ids(route(path))
        assert MOD["NOT_FOUND_ID"] in ids
        assert PAGE_ID not in ids and "unavailable" not in ids
        # No request at all, so none built from ZZ.
        assert calls == [] and bucket.waits == []

    def test_cold_an_unserved_code_costs_one_fill_of_the_roster_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        assert MOD["NOT_FOUND_ID"] in routed_ids(route("/state/ZZ/elections"))
        assert calls == [ROSTER_PATH]
        assert not any("ZZ" in c for c in calls)

    def test_cold_a_served_state_fills_the_roster_then_its_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        assert PAGE_ID in routed_ids(route(PATH))
        assert calls == [ROSTER_PATH, GA_PATH]


class TestNotFound:
    def test_the_not_found_state_shows_the_state_heading_and_no_lede(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        page = MOD["layout"](usps="ZZ", candidate="andrew-jackson")
        heading, content = page.children
        assert heading.children == labels.STATE_NOT_FOUND_HEADING
        assert content.id == MOD["NOT_FOUND_ID"]
        assert labels.STATE_NOT_FOUND_SENTENCE in texts(content)
        (link,) = of_type(content, "Link")
        assert (link.children, link.href) == (labels.STATE_NOT_FOUND_LINK, "/states")
        assert "ZZ" not in texts(content)
        assert calls == []

    @pytest.mark.parametrize(
        "path", ["/state/ZZ/elections", "/state/ga/elections", "/state/G1/elections"]
    )
    def test_with_the_roster_cached_an_unserved_code_is_a_404(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.ROSTER_PATH)
        status, head, body = get(f"{path}?candidate=andrew-jackson")
        assert status == 404
        assert head.noindex and head.canonical is None
        assert f"<title>{labels.STATE_NOT_FOUND_HEADING} — " in body
        assert calls == []


class TestLede:
    """The lede shows on success and on the degraded state, and the sentence naming
    the filters only on success, where the filters show (#392); the not-found state
    shows neither (#325)."""

    def test_the_wording_is_the_spec_s(self) -> None:
        # ba spec, approved at #619's plan gate, 2026-11-23.
        assert MOD["RESULTS_HEADING"] == "{state}: results by election"
        assert f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}" == (
            "This state's electoral votes for each candidate in every election this "
            "dataset holds for it, with the popular vote where the dataset has it, "
            "and whether Congress counted them. Narrow the rows by year, candidate or "
            "popular-vote status."
        )

    def test_success_shows_the_lede_then_the_filter_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = route(PATH)
        assert PAGE_ID in routed_ids(response)
        body = response.get_data(as_text=True)
        assert f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}" in body
        # Once, and only in the lede.
        assert body.count(MOD["FILTER_SENTENCE"]) == 1

    def test_the_degraded_state_shows_the_lede_and_offers_no_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A malformed state body: render raises after validation, so the page degrades.
        state_tests.TestMalformedBodies.client_with(monkeypatch, GA_PATH)
        response = route(PATH)
        ids = routed_ids(response)
        assert "unavailable" in ids and PAGE_ID not in ids
        body = response.get_data(as_text=True)
        assert MOD["RESULTS_GENERIC_HEADING"] in body
        assert MOD["LEDE"] in body
        assert MOD["FILTER_SENTENCE"] not in body

    def test_the_unreachable_api_shows_the_lede_and_offers_no_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = offline_client(failing_fetch, prefetch_paths=lambda: [])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        response = route(PATH)
        assert "unavailable" in routed_ids(response)
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] in body
        assert MOD["FILTER_SENTENCE"] not in body

    def test_the_not_found_state_shows_neither(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = route("/state/ZZ/elections")
        assert MOD["NOT_FOUND_ID"] in routed_ids(response)
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] not in body
        assert MOD["FILTER_SENTENCE"] not in body


class TestIndex:
    def test_a_served_state_is_found_with_its_canonical_url_and_filtered_og_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch, source=api.ROSTER_PATH)
        status, head, _ = get(
            f"{PATH}?year_from=1860&candidate=horatio-seymour&usps=TX&junk=1"
        )
        assert status == 200
        assert head.canonical == url(PATH)
        assert head.og_url == url(f"{PATH}?candidate=horatio-seymour&year_from=1860")

    def test_with_the_roster_cold_the_index_counts_it_matched_and_reads_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        status, head, _ = get("/state/ZZ/elections")
        assert status == 200  # D073: the index never waits on the API
        assert head.canonical == url("/state/ZZ/elections")
        assert calls == []


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
        ("GA/x", False),
    ],
)
def test_the_title_is_total_names_only_a_code_and_differs(
    usps: Any, named: bool
) -> None:
    # The page's own title; the registry's is app.py's wrapper (#325, D083).
    title = MOD["title"](usps=usps)
    assert isinstance(title, str)
    assert (f"{usps} — results by election" in title) is named
    assert title.startswith(MOD["RESULTS_GENERIC_HEADING"]) is not named
    assert "<" not in title
    assert title != HISTORY_MOD["title"](usps=usps)
    assert title != PC_MOD["title"](usps=usps)


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
    candidate_id, pv_id = MOD["CANDIDATE_ID"], MOD["PV_STATUS_ID"]
    candidates = {(r["candidate_slug"], str(r["candidate"])) for r in ga_body()["data"]}
    tree = render()
    candidate = find(tree, candidate_id)
    pv_status = find(tree, pv_id)
    assert candidate is not None and pv_status is not None
    assert (candidate.value, pv_status.value) == (None, None)
    assert candidate.options == _by_label(candidates)
    # Labels and values, in the table's order (#540, AC3).
    assert pv_status.options == [
        {"label": labels.PV_STATUS[k], "value": k} for k in labels.PV_STATUS
    ]
    filtered = render("candidate=abraham-lincoln&pv_status=popular_vote")
    assert find(filtered, candidate_id).value == "abraham-lincoln"
    assert find(filtered, pv_id).value == "popular_vote"
    # Each label names its field, and the placeholder is another string: the page
    # passes them to the helper in that order (#475's acceptance gate).
    shown = {
        label.htmlFor: label.children
        for label in of_type(tree, "Label")
        if label.htmlFor in (candidate_id, pv_id)
    }
    assert shown == {
        candidate_id: labels.LABELS["candidate"],
        pv_id: labels.LABELS["pv_status"],
    }
    assert candidate.placeholder != shown[candidate_id]
    assert pv_status.placeholder != shown[pv_id]


# --- the wide layout (#545, D102) -------------------------------------------------------


class TestWideLayout:
    """T4's filters at desktop width (#545), moved with it (#619): one ``.filters`` box
    that is a filter row, the slider's box first on a row of its own, then the two
    dropdown filters in source order. The rules are pinned in ``TestLayoutRules``
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

    def test_the_page_is_the_section_links_then_one_card_opened_by_the_filters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The heading, the lede and the page body, nothing between; in the body, the
        # section links, the page's Location, then T4's one card (#567, D111): its
        # filters, the count line, then the table; then the footer. No chart.
        cached_client(monkeypatch)
        page = MOD["layout"](usps="GA")
        heading, lede, content = page.children
        assert type(heading).__name__ == "H1"
        assert type(lede).__name__ == "P" and lede.className == "lede"
        assert getattr(content, "id", None) == PAGE_ID
        kids = list(content.children)
        assert kids[0].id == state_view.SECTIONS_ID
        assert type(kids[1]).__name__ == "Location" and kids[1].id == MOD["URL_ID"]
        assert cards(content) == [kids[2]]
        held = card_children(content, 2)
        (box,) = classed(content, "filters")
        assert held[0] is box
        assert held[1].className == "count"
        assert find(held, TABLE) is not None
        assert of_type(page, "Figure") == []
