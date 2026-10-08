"""The state history, T4, and the state picker (#279).

Offline, against the recorded ``/v1/states/GA`` and the roster ``/v1/elections/2024``
(the same snapshot as every other fixture, ``test_every_recorded_response_is_one_
snapshot``), through the helpers and the autouse offline process client of
``test_dashboard_app.py``. The registry-wide checks there pick both pages up
(``TestRegistryCoverage``, ``TestValidateBeforeFill`` with ``ZZ`` as the unserved code,
``TestRegistryContracts``), and the D070(b) guard renders ``/state/GA``, ``/states`` and
``/state/ZZ``. These tests cover what is particular to the two pages.
"""

from __future__ import annotations

import copy
import random
from typing import Any

import dash
import pytest
from dash import no_update

from explore import api, labels
from tests.unit.test_dashboard_app import (
    RECORDED,
    VERSION,
    FakeClock,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    component_ids,
    fake_fetch,
    get,
    offline_client,
    route,
    routed_ids,
    texts,
    url,
)
from tests.unit.test_dashboard_elections import find, of_type, parse

PAGE: dict[str, Any] = dash.page_registry["pages.state"]
#: The page module's namespace, reached through its layout (Dash loads it by path).
MOD: dict[str, Any] = PAGE["layout"].__globals__
PICKER: dict[str, Any] = dash.page_registry["pages.states"]
PICKER_MOD: dict[str, Any] = PICKER["layout"].__globals__

INDEX: dict[str, Any] = RECORDED[api.ELECTIONS_PATH]
ROSTER_PATH = "/v1/elections/2024"
ROSTER: dict[str, Any] = RECORDED[ROSTER_PATH]
GA_PATH = "/v1/states/GA"
PAGE_ID = MOD["PAGE_ID"]
TABLE = MOD["TABLE_ID"]


def ga_body() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[GA_PATH])


def render(query: str = "", body: Any = None, index: Any = None) -> Any:
    """The page body for ``query``, as the layout builds it."""
    content, _ = MOD["render"](
        ga_body() if body is None else body,
        copy.deepcopy(INDEX) if index is None else index,
        "GA",
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


# --- registration and validation ------------------------------------------------------


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path_template"] == "/state/<usps>"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    assert PAGE["on_miss"] == (api.ROSTER_PATH, "/v1/states/{usps}")
    assert PAGE["success"] == PAGE_ID
    # The registered judge is the one the layout calls, so the index's 404 and the
    # page's not-found state decide alike.
    assert PAGE["validate"] is MOD["VALIDATE"]
    assert PAGE["validate"] == (api.ROSTER_PATH, MOD["on_roster"])
    assert PAGE["query"] is MOD["parse_filters"]


def test_the_picker_is_registered_as_planned() -> None:
    assert PICKER["path"] == "/states"
    assert PICKER["prefetch"] == (api.ELECTIONS_PATH,)
    assert PICKER["on_miss"] == (api.ROSTER_PATH,)
    assert PICKER["success"] == PICKER_MOD["PAGE_ID"]


def test_the_roster_is_the_latest_served_election() -> None:
    # Resolved from the index (never a literal), and every state and DC takes part.
    assert api.ROSTER_PATH.format(**api.coverage_vars(INDEX)) == ROSTER_PATH
    assert len({row["state_usps"] for row in ROSTER["data"]}) == 51


class TestOnRoster:
    def test_every_state_and_dc_in_the_roster_is_accepted(self) -> None:
        judge = MOD["on_roster"]
        codes = {row["state_usps"] for row in ROSTER["data"]}
        assert "DC" in codes
        for usps in codes:
            assert judge({"usps": usps}, ROSTER) is True, usps

    @pytest.mark.parametrize(
        "usps",
        ["ZZ", "ga", "Ga", "GAA", "G", "", None, ["GA"], 1, "G1", "ＧＡ", " GA"],
    )
    def test_anything_else_is_refused(self, usps: Any) -> None:
        assert MOD["on_roster"]({"usps": usps}, ROSTER) is False

    @pytest.mark.parametrize(
        "body", [{}, [], None, "GA", {"data": "GA"}, {"data": [1]}, {"data": []}]
    )
    def test_a_malformed_roster_names_no_state(self, body: Any) -> None:
        assert MOD["on_roster"]({"usps": "GA"}, body) is False

    @pytest.mark.parametrize("position", [0, 50, -1])
    @pytest.mark.parametrize(
        "change",
        [{"year": 1824}, {"year": "2024"}, {"state_usps": "ga"}, {"state": None}],
        ids=repr,
    )
    def test_a_roster_the_picker_would_refuse_names_no_state(
        self, position: int, change: dict[str, Any]
    ) -> None:
        # One reading of the roster for both pages (api.roster): a row of another
        # year, a malformed code or a missing name refuses every code, GA included.
        body = copy.deepcopy(ROSTER)
        body["data"][position].update(change)
        assert MOD["on_roster"]({"usps": "GA"}, body) is False
        with pytest.raises(TypeError):
            PICKER_MOD["roster"](body, 2024)

    @pytest.mark.parametrize("year", [2020, 1824])
    def test_a_roster_whose_rows_all_name_another_year_names_no_state(
        self, year: int
    ) -> None:
        # Consistent rows, so api.roster reads it; but not the latest election, which
        # the judge checks against the roster's own coverage and the picker against
        # the year it read the roster for.
        body = copy.deepcopy(ROSTER)
        for row in body["data"]:
            row["year"] = year
        assert MOD["on_roster"]({"usps": "GA"}, body) is False
        with pytest.raises(TypeError):
            PICKER_MOD["roster"](body, 2024)

    @pytest.mark.parametrize("coverage", [{}, {"year_max": "2024"}, {"year_max": None}])
    def test_a_roster_with_no_checked_latest_year_names_no_state(
        self, coverage: dict[str, Any]
    ) -> None:
        body = copy.deepcopy(ROSTER)
        body["meta"]["provenance"]["coverage"] = coverage
        assert MOD["on_roster"]({"usps": "GA"}, body) is False


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

    def test_the_heading_names_the_state_from_the_rows(self) -> None:
        _, name = MOD["render"](ga_body(), copy.deepcopy(INDEX), "GA", [])
        assert name == "Georgia"


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
        for query in ("year_to=1900", "year_from=1824&year_to=1900"):
            tree = render(query, body=self.admitted_1912())
            assert table_rows(tree) == [], query
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
    election = dash.page_registry["pages.election"]["layout"].__globals__
    body = copy.deepcopy(RECORDED["/v1/elections/1868"])
    index_row = election["index_row"](INDEX, "1868")
    tree = election["render"](body, index_row, [])
    hrefs = {
        link.href for link in of_type(find(tree, election["STATES_TABLE_ID"]), "Link")
    }
    assert "/state/GA" in hrefs
    assert hrefs == {f"/state/{r['state_usps']}" for r in body["data"]}


@pytest.mark.parametrize("usps", ["ga", "G A", None, "../x", "<b>"])
def test_a_state_code_that_is_not_one_is_text_not_a_link(usps: Any) -> None:
    election = dash.page_registry["pages.election"]["layout"].__globals__
    body = copy.deepcopy(RECORDED["/v1/elections/1868"])
    body["data"] = [r for r in body["data"] if r["state_usps"] == "GA"]
    for row in body["data"]:
        row["state_usps"] = usps
    tree = election["render"](body, election["index_row"](INDEX, "1868"), [])
    assert of_type(find(tree, election["STATES_TABLE_ID"]), "Link") == []


# --- validation at the index and at render, and the request budget -------------------


class TestRoster:
    def test_a_served_state_renders_with_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch, source=api.ROSTER_PATH)
        assert PAGE_ID in routed_ids(route("/state/GA"))
        assert calls == [GA_PATH]
        assert len(bucket.waits) == 1
        calls.clear()
        assert PAGE_ID in routed_ids(route("/state/GA"))  # cached: none
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
    title = PAGE["title"](usps=usps)
    assert isinstance(title, str)
    assert (f"{usps} — state history" in title) is named
    assert "<" not in title


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
        [{"year": 2020}, {"year": "2024"}, {"state_usps": "ga"}, {"state_usps": None}],
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
        # The state page reads the same roster: no second fill of it.
        assert PAGE_ID in routed_ids(route("/state/GA"))
        assert calls == [GA_PATH]
