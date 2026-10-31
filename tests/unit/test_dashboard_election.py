"""The one-election view, T2 and T3 (#307), T6, every state's persons per electoral
vote (#280), and the election panel with T3's hybrid columns (#308).

Offline, against recorded ``/v1/elections/{year}`` responses for 1824, 1860, 1868, 1872,
2016 and 2024, and ``/v1/elections/{year}/per-capita`` for those years and 1848 and 1864
(one snapshot, ``v1_meta.json``'s), through the helpers and the autouse offline
process client of ``test_dashboard_app.py``. Its registry-wide checks pick this page up
from the registry (``TestRegistryCoverage``, ``TestValidateBeforeFill``,
``TestRegistryContracts`` and ``test_every_registered_page_is_found_at_the_index_and_
reads_nothing``), and the D070(b) guard renders it at 1824 as its first fills on a
miss. These tests cover what is particular to this page.
"""

from __future__ import annotations

import copy
import re
import urllib.parse
from typing import Any

import dash
import pytest
from dash import no_update

from explore import api, components, export, labels
from explore import app as appmod
from tests.unit.test_dashboard_app import (
    META,
    RECORDED,
    VERSION,
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
from tests.unit.test_dashboard_elections import find, json_node, of_type, parse
from usvote.count_status import COUNT_STATUS_VALUES
from usvote.pv.status import PV_STATUS_VALUES
from usvote.snapshot_schema import (
    PER_CAPITA_BOUNDARY_BASIS_VALUES,
    PER_CAPITA_COVERAGE_VALUES,
)

PAGE: dict[str, Any] = dash.page_registry["pages.election"]
#: The page module's namespace, reached through its layout (Dash loads it by path).
MOD: dict[str, Any] = PAGE["layout"].__globals__

INDEX: dict[str, Any] = RECORDED[api.ELECTIONS_PATH]
YEARS = [row["year"] for row in INDEX["data"]]
COVERAGE = INDEX["meta"]["provenance"]["coverage"]
PV_MIN, PV_MAX = COVERAGE["pv_year_min"], COVERAGE["pv_year_max"]
RECORDED_YEARS = (1824, 1860, 1868, 1872, 2016)

PAGE_ID = MOD["PAGE_ID"]
STATES = MOD["STATES_TABLE_ID"]
NATION = MOD["NATION_TABLE_ID"]


def year_body(year: int) -> dict[str, Any]:
    return copy.deepcopy(RECORDED[f"/v1/elections/{year}"])


def index_row(year: int, index: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = MOD["index_row"](index or INDEX, str(year))
    return result


def per_capita_body(year: int) -> dict[str, Any]:
    return copy.deepcopy(RECORDED[f"/v1/elections/{year}/per-capita"])


def render(year: int, query: str = "", body: Any = None, per_capita: Any = None) -> Any:
    """The page body for ``year`` and ``query``, as the layout builds it."""
    body = year_body(year) if body is None else body
    per_capita = per_capita_body(year) if per_capita is None else per_capita
    return MOD["render"](
        body,
        index_row(year),
        MOD["parse_filters"](parse(query)),
        per_capita,
        MOD["neighbours"](INDEX, year),
    )


def table_rows(tree: Any, table_id: str) -> list[list[Any]]:
    """Each body row's cells (``Td`` components) of the table ``table_id``."""
    table = find(tree, table_id)
    if table is None:
        return []
    return [list(tr.children) for tr in of_type(of_type(table, "Tbody"), "Tr")]


def cell_text(cell: Any) -> str:
    return "".join(texts(cell.children))


def column(tree: Any, table_id: str, fields: tuple[str, ...], field: str) -> list[str]:
    i = fields.index(field)
    return [cell_text(row[i]) for row in table_rows(tree, table_id)]


def state_rows(tree: Any) -> list[dict[str, str]]:
    """T2's rows as ``{field: cell text}``."""
    fields = MOD["STATE_FIELDS"]
    return [
        dict(zip(fields, (cell_text(c) for c in row), strict=True))
        for row in table_rows(tree, STATES)
    ]


def nation_rows(tree: Any) -> dict[str, dict[str, str]]:
    """T3's rows as ``{candidate: {field: cell text}}``."""
    fields = MOD["NATION_FIELDS"]
    rows = [
        dict(zip(fields, (cell_text(c) for c in row), strict=True))
        for row in table_rows(tree, NATION)
    ]
    return {row["candidate"]: row for row in rows}


def routed_states(response: Any) -> list[list[str]]:
    """T2's rows in a routed render, as state and candidate; ``[]`` with no table."""
    table = json_node(response.get_json(), STATES)
    if table is None:
        return []
    _, body = table["props"]["children"]
    return [
        [_cell_text(td["props"]["children"]) for td in tr["props"]["children"][:2]]
        for tr in body["props"]["children"]
    ]


def _cell_text(child: Any) -> Any:
    # A linked cell (#279's state links) serializes as a Link node.
    if isinstance(child, dict) and child.get("type") == "Link":
        return child["props"]["children"]
    return child


# --- registration and the recorded responses -----------------------------------------


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path_template"] == "/election/<year>"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    assert PAGE["on_miss"] == (
        "/v1/elections/{year}",
        "/v1/elections/{year}/per-capita",
    )
    assert PAGE["success"] == PAGE_ID
    # The registered judge is the one the layout calls, so the index's 404 and the
    # page's not-found state decide alike.
    assert PAGE["validate"] is MOD["VALIDATE"]
    assert PAGE["validate"] == (api.ELECTIONS_PATH, MOD["served_year"])
    assert PAGE["query"] is MOD["parse_filters"]


@pytest.mark.parametrize("path", sorted(RECORDED))
def test_every_recorded_response_is_one_snapshot(path: str) -> None:
    """Every recorded response (``/v1/meta``, ``/v1/elections``, each year, each state,
    each per-capita table, the candidate index and each candidate) was recorded from
    one snapshot, the one ``v1_meta.json`` names, and each answers the path it is
    recorded under."""
    body = RECORDED[path]
    provenance = (
        body["provenance"] if path == api.META_PATH else body["meta"]["provenance"]
    )
    assert provenance["snapshot_version"] == VERSION
    if year_path := re.fullmatch(r"/v1/elections/([0-9]{4})", path):
        assert body["election"]["year"] == int(year_path[1])
    # The per-capita tables (#280): every row names the path's year, or its state.
    if per_year := re.fullmatch(r"/v1/elections/([0-9]{4})/per-capita", path):
        assert body["data"]
        assert {row["year"] for row in body["data"]} == {int(per_year[1])}
    if per_state := re.fullmatch(r"/v1/states/([A-Z]{2})/per-capita", path):
        assert body["data"]
        assert {row["state_usps"] for row in body["data"]} == {per_state[1]}
    # The candidate history (#331): every row names the path's slug, and the recorded
    # index lists it.
    if slug := re.fullmatch(r"/v1/candidates/([a-z0-9-]+)", path):
        assert body["data"]
        assert {row["candidate_slug"] for row in body["data"]} == {slug[1]}
        listed = {i["candidate_slug"] for i in RECORDED[api.CANDIDATES_PATH]["data"]}
        assert slug[1] in listed


# --- validation: served years come from /v1/elections, never literals ---------------


class TestServedYear:
    def test_every_year_the_index_serves_is_accepted(self) -> None:
        judge = MOD["served_year"]
        # The served years span exactly the snapshot's coverage, read from the
        # response rather than a literal count (AC: the span from coverage).
        assert (min(YEARS), max(YEARS)) == (COVERAGE["year_min"], COVERAGE["year_max"])
        for year in YEARS:
            assert judge({"year": str(year)}, INDEX) is True, year

    @pytest.mark.parametrize(
        "year",
        ["1825", "1823", "2028", "01824", "1824 ", "", "abcd", "١٨٢٤", None, 1824],
    )
    def test_anything_else_is_refused(self, year: Any) -> None:
        assert MOD["served_year"]({"year": year}, INDEX) is False

    def test_the_index_decides_not_a_literal(self) -> None:
        judge = MOD["served_year"]
        without = copy.deepcopy(INDEX)
        without["data"] = [r for r in without["data"] if r["year"] != 1860]
        assert judge({"year": "1860"}, without) is False
        added = copy.deepcopy(INDEX)
        added["data"].append({**added["data"][0], "year": 1825})
        assert judge({"year": "1825"}, added) is True

    @pytest.mark.parametrize(
        ("path_year", "row_year"), [("0001", True), ("0000", False)]
    )
    def test_a_boolean_row_year_serves_nothing(
        self, path_year: str, row_year: bool
    ) -> None:
        """A bool is an int to Python (True == 1): the index's year must be a real
        integer, or a malformed row would serve /election/0001."""
        body = {"data": [{"year": row_year}]}
        assert MOD["served_year"]({"year": path_year}, body) is False

    @pytest.mark.parametrize(
        "body",
        [
            None,
            {},
            {"data": "1824"},
            {"data": [None, "x", {"year": True}, {"year": "1824"}, {"year": 1824.0}]},
        ],
    )
    def test_it_is_total_over_a_malformed_index(self, body: Any) -> None:
        assert MOD["served_year"]({"year": "1824"}, body) is False


class TestNotFound:
    def test_an_unserved_year_is_404_noindex_with_no_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        status, head, _ = get("/election/1825")
        assert status == 404
        assert head.noindex
        assert (head.canonical, head.og_url) == (None, None)

    def test_a_served_year_is_found_with_its_canonical_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        status, head, _ = get("/election/1860?state=SC&junk=1")
        assert status == 200
        assert head.canonical == url("/election/1860")
        assert head.og_url == url("/election/1860?state=SC")

    def test_the_page_says_the_dataset_has_no_election_that_year(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        response = route("/election/1825")
        ids = routed_ids(response)
        assert MOD["NOT_FOUND_ID"] in ids
        assert PAGE_ID not in ids
        body = response.get_data(as_text=True)
        assert MOD["NOT_FOUND_SENTENCE"] in body
        assert (
            "1825" not in json_node(response.get_json(), MOD["NOT_FOUND_ID"]).__str__()
        )
        assert calls == []
        # The way back leads to the elections index.
        links = of_type(MOD["not_found"](), "Link")
        assert [link.href for link in links] == ["/elections"]

    def test_the_index_s_404_follows_the_index_served(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        without = copy.deepcopy(INDEX)
        without["data"] = [r for r in without["data"] if r["year"] != 1860]
        cached_client(monkeypatch)
        api.CLIENT.snapshot.responses[api.ELECTIONS_PATH] = without  # type: ignore[union-attr]
        status, head, _ = get("/election/1860")
        assert (status, head.canonical) == (404, None)

    def test_a_year_the_index_adds_is_served(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No literal sits beside the index: a year it adds renders, at the index and
        in the page."""
        added = copy.deepcopy(INDEX)
        added["data"].append({**added["data"][0], "year": 1825})
        body = year_body(1824)
        for row in (*body["data"], *body["summary"], body["election"]):
            row["year"] = 1825
        per_capita = per_capita_body(1824)
        for row in per_capita["data"]:
            row["year"] = 1825
        fetch, calls = fake_fetch(
            {
                **RECORDED,
                api.ELECTIONS_PATH: added,
                "/v1/elections/1825": body,
                "/v1/elections/1825/per-capita": per_capita,
            }
        )
        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        status, head, _ = get("/election/1825")
        assert (status, head.canonical) == (200, url("/election/1825"))
        assert PAGE_ID in routed_ids(route("/election/1825"))
        assert "/v1/elections/1825" in calls
        assert "/v1/elections/1825/per-capita" in calls

    def test_the_not_found_state_follows_the_index_served(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        without = copy.deepcopy(INDEX)
        without["data"] = [r for r in without["data"] if r["year"] != 1860]
        fetch, calls = fake_fetch({**RECORDED, api.ELECTIONS_PATH: without})
        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        calls.clear()
        monkeypatch.setattr(api, "CLIENT", client)
        assert MOD["NOT_FOUND_ID"] in routed_ids(route("/election/1860"))
        assert calls == []


# --- T2 and T3 render for every served year ------------------------------------------


class TestRender:
    @pytest.mark.parametrize("year", RECORDED_YEARS)
    def test_every_recorded_year_renders_both_tables(
        self, monkeypatch: pytest.MonkeyPatch, year: int
    ) -> None:
        cached_client(monkeypatch)
        response = route(f"/election/{year}")
        ids = routed_ids(response)
        assert {PAGE_ID, STATES, NATION} <= ids
        assert "isn't responding" not in response.get_data(as_text=True)
        tree = render(year)
        body = year_body(year)
        assert len(table_rows(tree, STATES)) == len(body["data"])
        assert len(table_rows(tree, NATION)) == len(body["summary"])

    def test_the_heading_names_the_year_only_once_validated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        found = of_type(PAGE["layout"](year="1872"), "H1")
        missing = of_type(PAGE["layout"](year="1825"), "H1")
        assert [h.children for h in found] == ["The 1872 election"]
        assert [h.children for h in missing] == ["Election"]

    def test_the_window_is_read_from_coverage_not_literals(self) -> None:
        def new_york(pv_year_min: int) -> set[str]:
            body = year_body(1860)
            body["meta"]["provenance"]["coverage"].update(pv_year_min=pv_year_min)
            rows = state_rows(render(1860, body=body))
            return {r["popular_votes"] for r in rows if r["state"] == "New York"}

        assert new_york(1800) == {labels.NO_FIGURE}
        assert new_york(1900) == {"Popular vote held; not in this dataset before 1900"}

    def test_the_window_s_end_is_read_from_coverage_not_literals(self) -> None:
        ended = {**COVERAGE, "pv_year_max": 2012}
        assert labels.popular_votes(None, "popular_vote", 2016, ended) == (
            "Popular vote held; not in this dataset yet"
        )
        assert labels.popular_votes(None, "popular_vote", 2012, ended) == (
            labels.NO_FIGURE
        )

    def test_a_null_election_block_still_renders(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The API serves ``election: null`` on a build gap while the rows beside it
        stay correct; the panel says it is unavailable and the tables render (#308)."""
        body = year_body(1872)
        body["election"] = None
        fetch, _ = fake_fetch({**RECORDED, "/v1/elections/1872": body})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        tree = PAGE["layout"](year="1872")
        assert PAGE_ID in component_ids(tree)
        assert len(table_rows(tree, STATES)) == 222
        assert len(table_rows(tree, NATION)) == len(body["summary"])
        assert MOD["PANEL_ID"] not in component_ids(tree)
        unavailable = find(tree, MOD["PANEL_UNAVAILABLE_ID"])
        assert unavailable.children == (
            "The comparison across methods is not available for this year."
        )

    def test_an_unformattable_share_reads_unrecognized_not_a_server_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = year_body(1872)
        body["summary"][0]["ec_share_full"] = 10**400
        body["summary"][1]["ec_share_full"] = None
        fetch, _ = fake_fetch({**RECORDED, "/v1/elections/1872": body})
        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        response = route("/election/1872")
        assert response.status_code == 200
        assert PAGE_ID in routed_ids(response)
        tree = PAGE["layout"](year="1872")
        shares = column(tree, NATION, MOD["NATION_FIELDS"], "ec_share_full")
        assert shares[0] == labels.UNRECOGNIZED  # never the raw value (#355)
        assert shares[1] == "Not in this dataset"  # nullable in the schema: labelled

    @pytest.mark.parametrize(
        "change",
        [
            lambda b: b.update(data=[]),
            lambda b: b.update(summary=[]),
            lambda b: b.update(data={}),
            lambda b: b["data"][0].update(year=1864),  # a row of another year
            lambda b: b["data"][0].update(year="1872"),  # a year that is no integer
            lambda b: b["data"][0].update(year=True),
            lambda b: b["summary"][0].update(year=1868),
            # Every row is checked, not only the first.
            lambda b: b["data"][-1].update(year=1864),
            lambda b: b["summary"][-1].update(year=1868),
            lambda b: b.pop("meta"),
            # The election block (#308): required, a dict, naming the validated year.
            lambda b: b.pop("election"),
            lambda b: b.update(election=[]),
            lambda b: b.update(election="1872"),
            lambda b: b["election"].update(year=1868),
            lambda b: b["election"].update(year="1872"),
            lambda b: b["election"].update(year=True),
            lambda b: b["election"].pop("year"),
        ],
    )
    def test_a_malformed_body_shows_the_plain_message(
        self, monkeypatch: pytest.MonkeyPatch, change: Any
    ) -> None:
        body = year_body(1872)
        change(body)
        fetch, _ = fake_fetch({**RECORDED, "/v1/elections/1872": body})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        tree = PAGE["layout"](year="1872")
        assert "isn't responding" in " ".join(texts(tree))
        assert PAGE_ID not in component_ids(tree)


# --- headers --------------------------------------------------------------------------


class TestHeaders:
    def test_the_approved_labels(self) -> None:
        expected = {
            "state": "State",
            "candidate": "Candidate",
            "nominating_party": "Party",
            "nominating_party_note": "Party note",
            "state_electoral_votes": "Electors appointed (state)",
            "electoral_votes": "Electoral votes cast",
            "electoral_votes_counted": "Electoral votes counted",
            "electoral_count_status": "Count status",
            "electoral_count_status_reason": (
                "Count status: the National Archives' reason"
            ),
            "pv_status": "Popular vote in this state",
            "popular_votes": "Popular votes",
            "national_electoral_votes": "Electoral votes cast (nation)",
            "national_electoral_votes_counted": "Electoral votes counted (nation)",
            "national_electoral_denominator": "Electors appointed (nation)",
            "electoral_rank": "Electoral rank (counted votes)",
            "took_office": "Took office",
            "national_pv_votes": "Popular votes (nation)",
            "ec_share_full": "Electoral share (counted ÷ appointed)",
            "pv_share": "Popular-vote share",
            # The per-capita table (#280), reworded to the glossary (#352).
            "governing_census_year": "Census used",
            "population": "Population (from that census)",
            "boundary_basis": "Borders used",
            "persons_per_electoral_vote": "People per electoral vote",
            # The election panel and T3's hybrid columns (#308), approved 2026-10-08;
            # the winner and flip rows reworded to the glossary (#352). ``ec_winner``'s
            # is the label with no ``ec_determinative`` in hand; the panel's follows it
            # (#355, ``TestEcWinnerLabel``).
            "ec_winner": "Electoral College leader",
            "pv_winner": "Popular-vote winner",
            "hybrid_winner": "Hybrid winner",
            "pv_flip": "Popular-vote winner differs from the Electoral College result",
            "hybrid_flip": "Hybrid winner differs from the Electoral College result",
            "ec_margin": "Electoral margin (percentage points)",
            "pv_margin": "Popular-vote margin (percentage points)",
            "hybrid_margin": "Hybrid margin (percentage points)",
            "ec_determinative": "Electoral College majority",
            "pv_coverage": (
                "Share of electors appointed by states that held a popular vote"
            ),
            "ec_share_hybrid": "Electoral share in the hybrid",
            "hybrid_score": "Hybrid score",
        }
        assert {k: labels.LABELS[k] for k in expected} == expected

    @pytest.mark.parametrize(
        ("table_id", "fields"),
        [
            (STATES, "STATE_FIELDS"),
            (NATION, "NATION_FIELDS"),
            (MOD["PER_CAPITA_TABLE_ID"], "PER_CAPITA_FIELDS"),
        ],
    )
    def test_each_header_is_its_label_with_the_raw_field_name(
        self, table_id: str, fields: str
    ) -> None:
        headers = of_type(find(render(1872), table_id), "Th")
        assert [(h.children, h.title, h.scope) for h in headers] == [
            (labels.LABELS[f], f, "col") for f in MOD[fields]
        ]

    def test_each_field_is_in_its_response(self) -> None:
        body = year_body(2016)
        assert set(MOD["STATE_GLOSSARY"]) <= set(body["data"][0])
        assert set(MOD["NATION_FIELDS"]) <= set(body["summary"][0])
        assert set(MOD["PANEL_FIELDS"]) <= set(body["election"])

    def test_the_glossaries_name_every_column_and_the_count_reason(self) -> None:
        glossaries = of_type(render(1872), "Details")
        assert len(glossaries) == 4
        named = [[texts(dd.children)[0] for dd in of_type(g, "Dd")] for g in glossaries]
        assert named[0] == list(MOD["PANEL_FIELDS"])
        assert named[1] == list(MOD["STATE_FIELDS"]) + [
            "electoral_count_status_reason",
            "nominating_party_note",
        ]
        assert named[2] == list(MOD["NATION_FIELDS"]) + ["nominating_party_note"]
        assert named[3] == list(MOD["PER_CAPITA_FIELDS"])
        summaries = [g.children[0].children for g in glossaries]
        assert summaries == ["Field names"] + ["Column names"] * 3

    def test_every_closed_value_has_a_label(self) -> None:
        assert set(labels.PV_STATUS) == set(PV_STATUS_VALUES)
        assert set(labels.COUNT_STATUS) == set(COUNT_STATUS_VALUES)
        assert labels.COUNT_STATUS["not_counted"][0] == "Not counted"
        assert labels.COUNT_STATUS["disputed"][0] == "Disputed"


# --- a null is never bare -------------------------------------------------------------


class TestNullCells:
    @pytest.mark.parametrize(
        ("value", "status", "year", "cell"),
        [
            (None, "legislature_chosen", 1860, labels.LEGISLATURE_CHOSE),
            (None, "legislature_chosen", 2000, labels.LEGISLATURE_CHOSE),
            (None, "not_participating", 1868, labels.TOOK_NO_PART),
            (None, "popular_vote", 1860, f"not in this dataset before {PV_MIN}"),
            (None, "popular_vote", PV_MIN, labels.NO_FIGURE),
            (None, "popular_vote", PV_MAX, labels.NO_FIGURE),
            (None, "popular_vote", PV_MAX + 4, labels.AFTER_WINDOW),
            (62985062, "popular_vote", 2016, "62,985,062"),
            (0, "popular_vote", 2016, "0"),
            # A blank is no figure: its status explains it (#355's review).
            ("", "legislature_chosen", 1860, labels.LEGISLATURE_CHOSE),
            (" ", "popular_vote", PV_MIN, labels.NO_FIGURE),
            # Never the raw value (#355): an unknown status, and no status at all.
            (None, "mystery_code", 2016, labels.UNRECOGNIZED),
            (None, None, 2016, labels.NOT_IN_DATASET),
            ("many", "popular_vote", 2016, labels.UNRECOGNIZED),
        ],
    )
    def test_the_null_table(
        self, value: Any, status: str, year: int, cell: str
    ) -> None:
        shown = labels.popular_votes(value, status, year, COVERAGE)
        assert cell in shown
        assert shown not in ("", "None")

    def test_the_approved_cell_wording(self) -> None:
        """The issue's null table and help text, as written there."""
        cells = {
            "legislature_chosen": "No popular vote: the state legislature chose the electors",
            "not_participating": "Took no part in this election",
        }
        for status, text in cells.items():
            assert labels.popular_votes(None, status, 1860, COVERAGE) == text
        assert labels.popular_votes(None, "popular_vote", 1860, COVERAGE) == (
            "Popular vote held; not in this dataset before 1976"
        )
        assert labels.popular_votes(None, "popular_vote", 2016, COVERAGE) == (
            "No popular-vote figure in this dataset for this candidate in this state"
        )
        assert labels.NO_NATIONAL_FIGURE == (
            "No popular-vote figure in this dataset for this candidate"
        )
        # Reworded at #355's review so it runs one way only: a null cell reads "Not in
        # this dataset" too, and is no false (owner decision, 2026-10-13).
        assert labels.HAS_POPULAR_VOTE_NOTE == (
            'A false in the popular-vote column, shown as "Not in this dataset", means '
            "this dataset holds no popular-vote figure for that year. It does not say "
            "whether a popular vote was held."
        )
        # The note quotes the cell it explains, so the two cannot drift apart.
        assert f'"{labels.NOT_IN_DATASET}"' in labels.HAS_POPULAR_VOTE_NOTE
        assert labels.NOT_IN_DATASET == "Not in this dataset"
        # The party's wording (#389, owner approval at the plan gate).
        assert labels.PARTY_NOTE == (
            "The party column shows the party that nominated the candidate for "
            "President in that election. In 1824 and 1828, for a candidate no national "
            "convention or caucus nominated, and in 1836, for a Whig candidate, it "
            "shows the party this dataset's source names for them."
        )
        assert labels.PARTY_NULL_NOTE == (
            'A party shown as "Not in this dataset" (an empty cell in the download) '
            "means this dataset records no party for that candidate in that election. "
            "It does not say whether a party nominated them."
        )
        assert f'"{labels.NOT_IN_DATASET}"' in labels.PARTY_NULL_NOTE
        assert labels.NO_NOMINATION == (
            "Without a party's nomination for President when the electors voted"
        )
        assert labels.NO_NOMINATION_NOTE == (
            "Either no party nominated this candidate for President, or the "
            "nomination was withdrawn before the electors voted. It does not mean the "
            "candidate had no party."
        )
        assert labels.PARTY_NOTES_HEADING == "Party notes"
        assert labels.PARTY_NOTE_ITEM == "{candidate}, {year}: {note}"
        assert labels.COUNT_STATUS == {
            "counted": ("Counted", None),
            "not_counted": ("Not counted", "Congress decided not to count them"),
            "disputed": ("Disputed", "Congress never reached a decision"),
        }
        assert labels.PV_STATUS == {
            "popular_vote": "Popular vote held",
            "legislature_chosen": "State legislature chose the electors",
            "not_participating": "Took no part",
        }

    def test_1860_reads_the_legislature_and_the_window_differently(self) -> None:
        rows = state_rows(render(1860))
        sc = {r["popular_votes"] for r in rows if r["state"] == "South Carolina"}
        ny = {r["popular_votes"] for r in rows if r["state"] == "New York"}
        assert sc == {"No popular vote: the state legislature chose the electors"}
        assert ny == {"Popular vote held; not in this dataset before 1976"}
        assert sc != ny

    def test_2016_electoral_votes_without_a_figure_read_inside_the_window(self) -> None:
        body = year_body(2016)
        expected = {
            (r["state"], r["candidate"])
            for r in body["data"]
            if r["electoral_votes"] and r["popular_votes"] is None
        }
        assert (
            len(expected) == 5
        )  # Sanders HI, Kasich and Paul TX, Powell and Spotted Eagle WA
        rows = state_rows(render(2016))
        shown = {
            (r["state"], r["candidate"]): r["popular_votes"]
            for r in rows
            if (r["state"], r["candidate"]) in expected
        }
        assert shown == dict.fromkeys(expected, labels.NO_FIGURE)

    def test_no_popular_vote_cell_is_ever_blank(self) -> None:
        for year in RECORDED_YEARS:
            for row in state_rows(render(year)):
                assert row["popular_votes"] not in ("", "None"), (year, row)

    @pytest.mark.parametrize("year", [1824, 1860, 1872])
    def test_a_pre_window_t3_explains_the_year(self, year: int) -> None:
        tree = render(year)
        note = find(tree, MOD["NO_PV_ID"])
        assert note is not None
        assert note.children == MOD["NO_PV_SENTENCE"].format(
            year=year, first=PV_MIN, last=PV_MAX
        )
        # One wording for the outside-the-window cause (#352): T3's popular-vote
        # columns and hybrid score read the panel's, never the bare "Not in this
        # dataset".
        rows = nation_rows(tree)
        for row in rows.values():
            for field in ("national_pv_votes", "pv_share", "hybrid_score"):
                assert row[field] == labels.NOT_APPLICABLE, (year, field)
            # The second share is a value at every year, not a popular-vote cell.
            assert row["ec_share_hybrid"].endswith("%"), (year, row)
        assert {panel(tree)[f] for f in PV_FIELDS} == {labels.NOT_APPLICABLE}
        # A null party has nothing to do with the window (#389): it reads "Not in
        # this dataset", never the window's wording.
        null_party = [
            r["candidate"]
            for r in year_body(year)["summary"]
            if r["nominating_party"] is None
        ]
        assert null_party  # the premise
        for name in null_party:
            assert rows[name]["nominating_party"] == labels.NOT_IN_DATASET, (year, name)

    def test_inside_the_window_t3_has_no_year_note_and_names_a_missing_figure(
        self,
    ) -> None:
        tree = render(2016)
        assert find(tree, MOD["NO_PV_ID"]) is None
        rows = nation_rows(tree)
        powell = rows["Colin Powell"]
        assert powell["national_pv_votes"] == labels.NO_NATIONAL_FIGURE
        assert powell["pv_share"] == labels.NO_NATIONAL_FIGURE
        trump = rows["Donald J. Trump"]
        assert trump["national_pv_votes"] == "62,985,062"
        assert trump["pv_share"] == "46.0%"
        assert trump["nominating_party"] == "Republican"  # its display form (#389)

    def test_t3_reads_the_index_s_flag_and_the_coverage_years(self) -> None:
        """Doctored inputs, so a literal window in the page fails: the year-level
        decision comes from the index row, the sentence's years from coverage."""
        held = MOD["render"](
            year_body(1872),
            {**index_row(1872), "has_popular_vote": True},
            [],
            per_capita_body(1872),
            MOD["neighbours"](INDEX, 1872),
        )
        assert find(held, MOD["NO_PV_ID"]) is None
        grant = nation_rows(held)["Ulysses S. Grant"]
        assert grant["national_pv_votes"] == labels.NO_NATIONAL_FIGURE
        missing = MOD["render"](
            year_body(2016),
            {**index_row(2016), "has_popular_vote": False},
            [],
            per_capita_body(2016),
            MOD["neighbours"](INDEX, 2016),
        )
        assert find(missing, MOD["NO_PV_ID"]) is not None
        trump = nation_rows(missing)["Donald J. Trump"]
        assert trump["national_pv_votes"] == trump["pv_share"] == labels.NOT_APPLICABLE
        body = year_body(1860)
        body["meta"]["provenance"]["coverage"].update(
            pv_year_min=1900, pv_year_max=2000
        )
        note = find(render(1860, body=body), MOD["NO_PV_ID"])
        assert note.children == (
            "This dataset has no popular-vote figures for 1860; its popular-vote "
            "figures cover 1900–2000."
        )

    @pytest.mark.parametrize("flag", ["false", 1, None])
    def test_only_a_true_flag_claims_a_popular_vote(self, flag: Any) -> None:
        """A malformed index flag never makes T3 claim the year has a popular vote."""
        tree = MOD["render"](
            year_body(1872),
            {**index_row(1872), "has_popular_vote": flag},
            [],
            per_capita_body(1872),
            MOD["neighbours"](INDEX, 1872),
        )
        assert find(tree, MOD["NO_PV_ID"]) is not None

    def test_the_index_s_flag_and_the_window_agree(self) -> None:
        """A check of the recorded data, not of the page: the index's flag and the
        coverage window name the same years, so T2 (window from coverage) and T3 (flag
        from the index) cannot disagree on this snapshot."""
        for row in INDEX["data"]:
            inside = PV_MIN <= row["year"] <= PV_MAX
            assert row["has_popular_vote"] is inside, row["year"]

    def test_a_party_and_a_null_on_real_rows(self) -> None:
        """AC1, AC2, AC4 (#389): 1860 gives a party for the President and the Main
        Opponent and "Not in this dataset" (with its one-cause note) for the others;
        1896's Bryan reads one joint value. AC7's third state, ``no_nomination``, is
        ``test_a_no_nomination_row_reads_its_own_label``."""
        tree = render(1860)
        nation = nation_rows(tree)
        assert nation["Abraham Lincoln"]["nominating_party"] == "Republican"
        assert nation["Stephen A. Douglas"]["nominating_party"] == "Democratic"
        for name in ("John C. Breckinridge", "John Bell"):
            assert nation[name]["nominating_party"] == labels.NOT_IN_DATASET, name
        by_name = {r["candidate"]: r for r in state_rows(tree)}
        assert by_name["Abraham Lincoln"]["nominating_party"] == "Republican"
        index = MOD["STATE_FIELDS"].index("nominating_party")
        null_cells = [
            row[index]
            for row in table_rows(tree, STATES)
            if cell_text(row[index]) == labels.NOT_IN_DATASET
        ]
        null_cells += [
            row[MOD["NATION_FIELDS"].index("nominating_party")]
            for row in table_rows(tree, NATION)
            if cell_text(row[MOD["NATION_FIELDS"].index("nominating_party")])
            == labels.NOT_IN_DATASET
        ]
        assert null_cells
        assert {c.title for c in null_cells} == {labels.PARTY_NULL_NOTE}
        for note in (labels.PARTY_NOTE, labels.PARTY_NULL_NOTE):
            shown = [p for p in of_type(tree, "P") if p.children == note]
            assert len(shown) == 2, note  # under T2 and under T3
        bryan = nation_rows(render(1896))["William J. Bryan"]
        assert bryan["nominating_party"] == "Democratic and Populist"

    def test_a_row_note_is_help_text_and_listed_once(self) -> None:
        """1872 Greeley (#389): the note is the cell's help text and one Party notes
        item under each table, however many state rows repeat it."""
        body = year_body(1872)
        note = next(
            r["nominating_party_note"]
            for r in body["summary"]
            if r["candidate"] == "Horace Greeley"
        )
        assert note
        tree = render(1872)
        index = MOD["NATION_FIELDS"].index("nominating_party")
        greeley = next(
            row[index]
            for row in table_rows(tree, NATION)
            if cell_text(row[0]) == "Horace Greeley"
        )
        assert cell_text(greeley) == "Liberal Republican and Democratic"
        assert greeley.title == note
        lists = [
            d
            for d in of_type(tree, "Div")
            if getattr(d, "className", None) == "party-notes"
        ]
        assert len(lists) == 2  # under T2 and under T3
        item = labels.PARTY_NOTE_ITEM.format(
            candidate="Horace Greeley", year=1872, note=note
        )
        for block in lists:
            assert [li.children for li in of_type(block, "Li")] == [item]

    def test_t2_lists_only_the_notes_of_the_rows_it_shows(self) -> None:
        """1872 filtered to Grant (#389): T2 shows none of Greeley's rows, so its Party
        notes list is absent; T3, which the filter does not narrow, keeps his."""
        tree = render(1872, "candidate=ulysses-s-grant")
        assert {r["candidate"] for r in state_rows(tree)} == {"Ulysses S. Grant"}
        lists = [
            d
            for d in of_type(tree, "Div")
            if getattr(d, "className", None) == "party-notes"
        ]
        assert len(lists) == 1
        assert [li.children for li in of_type(lists[0], "Li")] == [
            labels.PARTY_NOTE_ITEM.format(
                candidate="Horace Greeley",
                year=1872,
                note=next(
                    r["nominating_party_note"]
                    for r in year_body(1872)["summary"]
                    if r["candidate"] == "Horace Greeley"
                ),
            )
        ]

    def test_a_no_nomination_row_reads_its_own_label(self) -> None:
        """AC3 (#389): no row is served with ``no_nomination`` yet, so the body is
        doctored here, never in a recorded file."""
        body = year_body(2016)
        for row in [*body["data"], *body["summary"]]:
            if row["candidate"] == "Colin Powell":
                row.update(
                    nominating_party="no_nomination",
                    nominating_party_source="USGOV",
                    nominating_party_note="A doctored note.",
                )
        tree = render(2016, body=body)
        index = MOD["NATION_FIELDS"].index("nominating_party")
        powell = next(
            row[index]
            for row in table_rows(tree, NATION)
            if cell_text(row[0]) == "Colin Powell"
        )
        assert cell_text(powell) == labels.NO_NOMINATION
        assert labels.NO_NOMINATION not in {labels.NOT_IN_DATASET, labels.UNRECOGNIZED}
        assert powell.title == f"{labels.NO_NOMINATION_NOTE} A doctored note."
        items = [li.children for li in of_type(tree, "Li")]
        assert "Colin Powell, 2016: A doctored note." in items

    @pytest.mark.parametrize(
        ("row", "shown", "title"),
        [
            ({"nominating_party": "whig"}, "Whig", None),
            (
                {"nominating_party": "whig", "nominating_party_note": "A note."},
                "Whig",
                "A note.",
            ),
            (
                {"nominating_party": "no_nomination"},
                labels.NO_NOMINATION,
                labels.NO_NOMINATION_NOTE,
            ),
            ({"nominating_party": None}, labels.NOT_IN_DATASET, labels.PARTY_NULL_NOTE),
            ({"nominating_party": "  "}, labels.NOT_IN_DATASET, labels.PARTY_NULL_NOTE),
            ({}, labels.NOT_IN_DATASET, labels.PARTY_NULL_NOTE),
            ({"nominating_party": 7}, labels.UNRECOGNIZED, labels.UNRECOGNIZED_NOTE),
            # The unrecognized note wins over a row note (labels.cell forces it).
            (
                {"nominating_party": 7, "nominating_party_note": "A note."},
                labels.UNRECOGNIZED,
                labels.UNRECOGNIZED_NOTE,
            ),
            # Defensive (no such row is served): a null with a note keeps the null's
            # note first, as a no_nomination row keeps its own (owner, #389 review).
            (
                {"nominating_party": None, "nominating_party_note": "A note."},
                labels.NOT_IN_DATASET,
                f"{labels.PARTY_NULL_NOTE} A note.",
            ),
            (
                {"nominating_party": "no_nomination", "nominating_party_note": "A note."},
                labels.NO_NOMINATION,
                f"{labels.NO_NOMINATION_NOTE} A note.",
            ),
            # A closed vocabulary: exact match, never stripped or re-cased (#389).
            (
                {"nominating_party": " whig "},
                labels.UNRECOGNIZED,
                labels.UNRECOGNIZED_NOTE,
            ),
            ({"nominating_party": "WHIG"}, labels.UNRECOGNIZED, labels.UNRECOGNIZED_NOTE),
            # A note that is not text with something in it is no note.
            ({"nominating_party": "whig", "nominating_party_note": 7}, "Whig", None),
            ({"nominating_party": "whig", "nominating_party_note": " "}, "Whig", None),
        ],
    )
    def test_the_party_cell(
        self, row: dict[str, Any], shown: str, title: str | None
    ) -> None:
        built = labels.nominating_party_cell(row)
        assert (built.children, getattr(built, "title", None)) == (shown, title)

    def test_the_party_notes_list(self) -> None:
        def row(year: int, name: Any, slug: Any, note: Any = None) -> dict[str, Any]:
            return {
                "year": year,
                "candidate": name,
                "candidate_slug": slug,
                "nominating_party_note": note,
            }

        rows = [
            row(1872, "Z", "z", "First."),  # first seen is listed first
            row(1872, "A", "a", "N."),
            row(1872, "A", "a", "N."),  # the same candidate-year again: once
            row(1876, "A", "a", "N."),  # the same slug and note, another year: listed
            row(1872, "E", "e", "N."),  # another candidate, the same note: listed
            row(1872, "B", "b"),  # no note
            row(1872, "D", "d", 7),  # a note that is not text: none
            row(1872, "F", "f", "  "),  # a blank note: none
            row(1872, 7, "c", "M."),  # a name that is not text
            row(1872, None, "n", "O."),  # no name
            row(1880, "G", None, "P."),  # two candidates with no slug never merge
            row(1880, "H", None, "Q."),
            row(1884, "J", "j-1", "R."),  # one name, two slugs: two candidates
            row(1884, "J", "j-2", "R."),
        ]
        (block,) = labels.party_notes(rows)
        assert of_type(block, "Strong")[0].children == labels.PARTY_NOTES_HEADING
        assert [li.children for li in of_type(block, "Li")] == [
            "Z, 1872: First.",
            "A, 1872: N.",
            "A, 1876: N.",
            "E, 1872: N.",
            f"{labels.UNRECOGNIZED}, 1872: M.",
            f"{labels.NOT_IN_DATASET}, 1872: O.",
            "G, 1880: P.",
            "H, 1880: Q.",
            "J, 1884: R.",
            "J, 1884: R.",
        ]
        assert labels.party_notes([row(1872, "B", "b")]) == []

    @pytest.mark.parametrize(
        ("fn", "value", "shown"),
        [
            (labels.yes_no, True, "Yes"),
            (labels.yes_no, False, "No"),
            (labels.yes_no, None, labels.NOT_IN_DATASET),
            (labels.yes_no, 1, labels.UNRECOGNIZED),
            (labels.yes_no, "yes_no", labels.UNRECOGNIZED),
            (labels.share, 0.5, "50.0%"),
            (labels.share, True, labels.UNRECOGNIZED),
            (labels.share, "x_y", labels.UNRECOGNIZED),
            (labels.share, None, labels.NOT_IN_DATASET),
            (labels.share, 10**400, labels.UNRECOGNIZED),  # no float holds it
            # #355's review: one rule, so a non-finite number is a value no cell
            # can word, as is a finite one whose percentage overflows.
            (labels.share, float("inf"), labels.UNRECOGNIZED),
            (labels.share, float("nan"), labels.UNRECOGNIZED),
            (labels.share, 1e307, labels.UNRECOGNIZED),
            (labels.share, 10**307, labels.UNRECOGNIZED),
            (labels.share, "", labels.NOT_IN_DATASET),
            # A count shows any integer, however large; a non-finite one is no count.
            (labels.number, 10**400, f"{10**400:,}"),
            (labels.number, float("nan"), labels.UNRECOGNIZED),
            (labels.census_year, float("nan"), labels.UNRECOGNIZED),
            (labels.number, 1234567, "1,234,567"),
            (labels.number, False, labels.UNRECOGNIZED),
            (labels.number, 1.5, labels.UNRECOGNIZED),  # a count is an integer
            (labels.number, "1_000", labels.UNRECOGNIZED),
            (labels.number, None, labels.NOT_IN_DATASET),
            (labels.nominating_party, None, labels.NOT_IN_DATASET),
            (labels.nominating_party, "", labels.NOT_IN_DATASET),
            (labels.nominating_party, 7, labels.UNRECOGNIZED),
            (labels.nominating_party, "_", labels.UNRECOGNIZED),
            (labels.nominating_party, "DEMOCRAT", labels.UNRECOGNIZED),  # MIT's code
            (labels.nominating_party, " democratic ", labels.UNRECOGNIZED),
            (labels.nominating_party, "democratic", "Democratic"),
            (labels.nominating_party, "no_nomination", labels.NO_NOMINATION),
            # A blank is no value in every function the rule covers (#355's review).
            (labels.has_popular_vote, "", labels.NOT_IN_DATASET),
            (labels.has_popular_vote, " ", labels.NOT_IN_DATASET),
            (labels.yes_no, "", labels.NOT_IN_DATASET),
            (labels.yes_no, " ", labels.NOT_IN_DATASET),
            (labels.number, "", labels.NOT_IN_DATASET),
            (labels.number, " ", labels.NOT_IN_DATASET),
            (labels.census_year, "", labels.NOT_IN_DATASET),
            (labels.census_year, " ", labels.NOT_IN_DATASET),
            (
                labels.pv_status,
                "legislature_chosen",
                "State legislature chose the electors",
            ),
            (labels.pv_status, "mystery_code", labels.UNRECOGNIZED),
            (labels.pv_status, 7, labels.UNRECOGNIZED),
            (labels.pv_status, None, labels.NOT_IN_DATASET),
            (labels.pv_status, " ", labels.NOT_IN_DATASET),
            (labels.census_year, 1910, "1910"),  # a year: no thousands separator
            (labels.census_year, "1910", labels.UNRECOGNIZED),
            (labels.census_year, None, labels.NOT_IN_DATASET),
        ],
    )
    def test_an_unexpected_value_is_never_shown_raw(
        self, fn: Any, value: Any, shown: str
    ) -> None:
        """#355: a null or blank names no cause; any other value with no wording
        reads "Unrecognized value", never the raw value."""
        assert fn(value) == shown


# --- electoral count status -----------------------------------------------------------


class TestCountStatus:
    @pytest.mark.parametrize(
        ("year", "status", "label"),
        [(1872, "not_counted", "Not counted"), (1868, "disputed", "Disputed")],
    )
    def test_every_uncounted_row_shows_its_status_and_the_reason_verbatim(
        self, year: int, status: str, label: str
    ) -> None:
        body = year_body(year)
        reasons = {
            (r["state"], r["candidate"]): r["electoral_count_status_reason"]
            for r in body["data"]
            if r["electoral_count_status"] != "counted"
        }
        assert reasons and all(reasons.values())
        rows = state_rows(render(year))
        meaning = labels.COUNT_STATUS[status][1]
        for row in rows:
            key = (row["state"], row["candidate"])
            if key in reasons:
                assert row["electoral_count_status"] == (
                    f"{label} ({meaning}){reasons[key]}"
                ), key
            else:
                assert row["electoral_count_status"] == "Counted", key

    def test_the_reason_is_its_own_element(self) -> None:
        cell = labels.count_status("not_counted", "A <b>reason</b>.")
        assert [type(c).__name__ for c in cell] == ["Strong", "str", "Br", "Span"]
        assert cell[3].children == "A <b>reason</b>."
        assert labels.count_status("counted", "ignored") == ["Counted"]
        assert labels.count_status("mystery_code", None) == [labels.UNRECOGNIZED]
        assert labels.count_status(None, None) == [labels.NOT_IN_DATASET]
        assert labels.count_status("", None) == [labels.NOT_IN_DATASET]
        assert labels.count_status(" ", None) == [labels.NOT_IN_DATASET]
        # #355's review: only a reason that is text with something in it is shown.
        for reason in (None, "", "  ", 5):
            assert [type(c).__name__ for c in labels.count_status("disputed", reason)] == [
                "Strong",
                "str",
            ], reason

    def test_1872_grant_reads_cast_counted_and_appointed(self) -> None:
        grant = nation_rows(render(1872))["Ulysses S. Grant"]
        assert grant["national_electoral_votes"] == "300"
        assert grant["national_electoral_votes_counted"] == "286"
        assert grant["national_electoral_denominator"] == "366"
        assert grant["took_office"] == "Yes"
        assert grant["ec_share_full"] == "78.1%"  # counted ÷ appointed

    def test_t3_is_never_filtered(self) -> None:
        tree = render(1872, "state=GA&candidate=horace-greeley")
        assert len(table_rows(tree, NATION)) == len(year_body(1872)["summary"])
        assert len(table_rows(tree, STATES)) == 1


# --- filters --------------------------------------------------------------------------


class TestParser:
    @pytest.mark.parametrize(
        ("params", "pairs"),
        [
            ({}, []),
            ({"state": "SC"}, [("state", "SC")]),
            ({"state": "sc"}, []),
            ({"state": "SCX"}, []),
            ({"state": ["SC", "SC"]}, [("state", "SC")]),
            ({"state": ["SC", "NY"]}, []),
            ({"candidate": "abraham-lincoln"}, [("candidate", "abraham-lincoln")]),
            ({"candidate": "Abraham Lincoln"}, []),
            ({"candidate": "a-" * 40}, []),
            ({"candidate": "a" * 64}, [("candidate", "a" * 64)]),
            ({"candidate": "a" * 65}, []),  # a valid slug, over the length cap
            ({"candidate": "-a"}, []),
            (
                {"pv_status": "legislature_chosen"},
                [("pv_status", "legislature_chosen")],
            ),
            ({"pv_status": "unknown"}, []),
            (
                {"electoral_count_status": "disputed"},
                [("electoral_count_status", "disputed")],
            ),
            ({"electoral_count_status": "Disputed"}, []),
            ({"year": "1872", "junk": "1"}, []),
            (
                {
                    "state": "GA",
                    "candidate": "horace-greeley",
                    "pv_status": "popular_vote",
                },
                [
                    ("candidate", "horace-greeley"),
                    ("pv_status", "popular_vote"),
                    ("state", "GA"),
                ],
            ),
        ],
    )
    def test_parse_filters(self, params: dict[str, Any], pairs: list[Any]) -> None:
        assert MOD["parse_filters"](params) == pairs

    @pytest.mark.parametrize("params", [None, [], "state=SC", 3, {"state": None}])
    def test_parse_filters_is_total(self, params: Any) -> None:
        assert MOD["parse_filters"](params) == []


class TestFilters:
    def test_the_filters_select_the_rows(self) -> None:
        rows = state_rows(render(1860, "state=SC"))
        assert {r["state"] for r in rows} == {"South Carolina"} and len(rows) == 4
        rows = state_rows(
            render(1860, "candidate=abraham-lincoln&pv_status=popular_vote")
        )
        assert {r["candidate"] for r in rows} == {"Abraham Lincoln"}
        assert "South Carolina" not in {r["state"] for r in rows}
        rows = state_rows(render(1872, "electoral_count_status=not_counted"))
        assert len(rows) == 3

    def test_a_state_or_candidate_absent_that_year_falls_back_to_all(self) -> None:
        for query in ("state=ZZ", "state=AZ", "candidate=no-such-person"):
            tree = render(1860, query)
            assert len(table_rows(tree, STATES)) == 132, query

    def test_a_status_no_row_has_is_an_honest_empty_result(self) -> None:
        tree = render(2016, "electoral_count_status=disputed")
        assert find(tree, STATES) is None
        assert "No rows match these filters." in texts(tree)
        assert "Showing 0 of 357 rows" in texts(tree)
        assert PAGE_ID in component_ids(tree)  # still a successful render

    def test_the_controls_show_the_filters_in_force(self) -> None:
        tree = render(1872, "state=GA&candidate=horace-greeley&state=")
        values = {
            control: find(tree, MOD[control]).value
            for control in (
                "STATE_ID",
                "CANDIDATE_ID",
                "PV_STATUS_ID",
                "COUNT_STATUS_ID",
            )
        }
        assert values == {
            "STATE_ID": None,  # a differing repeat is dropped
            "CANDIDATE_ID": "horace-greeley",
            "PV_STATUS_ID": None,
            "COUNT_STATUS_ID": None,
        }
        state = find(render(1872, "state=GA"), MOD["STATE_ID"])
        assert state.value == "GA"
        assert {"label": "Georgia", "value": "GA"} in state.options
        for control in ("STATE_ID", "CANDIDATE_ID", "PV_STATUS_ID", "COUNT_STATUS_ID"):
            assert getattr(find(tree, MOD[control]), "persistence", None) is None


SHARED = (
    "state=GA&junk=x&candidate=horace-greeley&state=GA",
    "electoral_count_status=not_counted",
    "state=ZZ",  # syntactically kept; absent that year in the layout
    "pv_status=nope&junk=1",  # (a ``year`` key would override the path: #326)
    "",
)


class TestShareableUrl:
    @pytest.mark.parametrize("query", SHARED)
    def test_a_filtered_og_url_reopens_the_filtered_view(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        cached_client(monkeypatch)
        status, head, _ = get(f"/election/1872?{query}")
        assert status == 200
        assert head.og_url is not None
        reopened = urllib.parse.urlsplit(head.og_url)
        assert reopened.path == "/election/1872"
        original = route("/election/1872", f"?{query}" if query else "")
        again = route(reopened.path, f"?{reopened.query}" if reopened.query else "")
        assert PAGE_ID in routed_ids(original)
        assert original.get_json() == again.get_json()

    def test_the_round_trip_check_sees_a_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        filtered = routed_states(route("/election/1872", f"?{SHARED[0]}"))
        assert filtered == [["Georgia", "Horace Greeley"]]

    @pytest.mark.parametrize(
        "query",
        [
            SHARED[0],
            SHARED[1],
            "pv_status=legislature_chosen",
            "electoral_count_status=disputed&pv_status=popular_vote",
            "state=ZZ",
            "",
        ],
    )
    def test_the_callback_writes_the_og_url_s_query_byte_for_byte(
        self, query: str
    ) -> None:
        """A fixed point, where the layout kept every parameter og:url names."""
        tree = render(1872, query)
        values = [
            find(tree, MOD[c]).value
            for c in ("STATE_ID", "CANDIDATE_ID", "PV_STATUS_ID", "COUNT_STATUS_ID")
        ]
        written = MOD["search_for"](*values)
        og_url = appmod.resolve("/election/1872", query, None).og_url
        assert og_url is not None
        expected = urllib.parse.urlsplit(og_url).query
        if query == "state=ZZ":
            # og:url keeps a state absent that year; the controls cannot. Both URLs
            # open the unfiltered view.
            assert (written, expected) == ("", "state=ZZ")
        else:
            assert written == (f"?{expected}" if expected else "")

    def test_the_callback_is_wired_to_the_page_s_location(self) -> None:
        graph = appmod.server.test_client().get("/_dash-dependencies").get_json()
        entries = [c for c in graph if c["output"] == f"{MOD['URL_ID']}.search"]
        assert len(entries) == 1
        assert entries[0]["inputs"] == [
            {"id": MOD[c], "property": "value"}
            for c in ("STATE_ID", "CANDIDATE_ID", "PV_STATUS_ID", "COUNT_STATUS_ID")
        ]
        assert entries[0]["state"] == [{"id": MOD["URL_ID"], "property": "search"}]
        assert entries[0]["prevent_initial_call"] is True
        location = find(render(1872), MOD["URL_ID"])
        assert location.refresh == "callback-nav"

    def test_the_callback_leaves_an_unchanged_url_alone(self) -> None:
        callback = MOD["on_filter_change"]
        assert callback("GA", None, None, None, "") == "?state=GA"
        assert callback("GA", None, None, None, "?state=GA") is no_update
        assert callback(None, None, None, None, None) is no_update
        assert callback(None, None, None, None, "?state=GA") == ""
        # Each control writes its own key, in the normal form.
        assert callback(None, None, "legislature_chosen", "disputed", "") == (
            "?electoral_count_status=disputed&pv_status=legislature_chosen"
        )
        # Syntactically bad values are dropped.
        assert callback("ga", ["x"], "nope", "", "?state=GA") == ""


# --- request budget -------------------------------------------------------------------


class TestRequestBudget:
    def test_opening_a_year_makes_at_most_two_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The year's rows, then its per-capita table (#280)."""
        _, calls, bucket = cached_client(monkeypatch)
        assert PAGE_ID in routed_ids(route("/election/1872"))
        assert calls == ["/v1/elections/1872", "/v1/elections/1872/per-capita"]
        assert len(bucket.waits) == 2
        calls.clear()
        assert PAGE_ID in routed_ids(route("/election/1872"))  # cached: none
        assert calls == []

    def test_filter_changes_make_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        route("/election/1872")
        calls.clear()
        for search in ("?state=GA", "?electoral_count_status=not_counted", ""):
            assert PAGE_ID in routed_ids(route("/election/1872", search))
        MOD["on_filter_change"]("GA", None, None, None, "")
        assert calls == []

    def test_the_callback_reads_no_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class NoView:
            def view(self) -> Any:
                raise AssertionError("the filter callback read the API")

        monkeypatch.setattr(api, "CLIENT", NoView())
        assert MOD["on_filter_change"]("GA", None, None, None, "") == "?state=GA"

    def test_with_the_index_cold_the_first_open_also_fills_the_index(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The approved reading (#307 plan gate): the budget holds in the steady state,
        with the prefetched index cached; cold, the index is filled first."""
        _, calls, _ = cached_client(monkeypatch, elections=False)
        assert PAGE_ID in routed_ids(route("/election/1872"))
        assert calls == [
            api.ELECTIONS_PATH,
            "/v1/elections/1872",
            "/v1/elections/1872/per-capita",
        ]


# --- the earlier and later links (#324) ----------------------------------------------


def nav_links(tree: Any) -> list[tuple[str, str, Any]]:
    """The nav's links as ``(id, href, text)``; ``[]`` with no nav."""
    nav = find(tree, MOD["NAV_ID"])
    if nav is None:
        return []
    return [(link.id, link.href, link.children) for link in of_type(nav, "Link")]


def routed_hrefs(response: Any) -> dict[str, str]:
    """The nav's link hrefs in a routed render, by link id."""
    nav = json_node(response.get_json(), MOD["NAV_ID"])
    if nav is None:
        return {}
    return {
        link["props"]["id"]: link["props"]["href"] for link in nav["props"]["children"]
    }


def lede(tree: Any) -> str:
    (paragraph,) = [
        p for p in of_type(tree, "P") if getattr(p, "className", None) == "lede"
    ]
    return str(paragraph.children)


class TestNeighbourLinks:
    def test_the_neighbours_are_the_index_s_nearest_years(self) -> None:
        neighbours = MOD["neighbours"]
        assert neighbours(INDEX, YEARS[0]) == (None, YEARS[1])
        assert neighbours(INDEX, YEARS[-1]) == (YEARS[-2], None)
        assert neighbours(INDEX, 1868) == (1864, 1872)

    def test_a_gap_in_the_served_years_is_followed_not_computed(self) -> None:
        """With 1864 and 1872 unserved, 1868's neighbours are the nearest years the
        index serves."""
        gapped = copy.deepcopy(INDEX)
        gapped["data"] = [r for r in gapped["data"] if r["year"] not in (1864, 1872)]
        assert MOD["neighbours"](gapped, 1868) == (1860, 1876)

    def test_a_served_year_off_the_four_year_grid_is_a_neighbour(self) -> None:
        """Never computed from the year: no step of four, however repeated, reaches
        1866 or 1870 from 1868, so only reading the rows finds them."""
        off_grid = copy.deepcopy(INDEX)
        off_grid["data"] += [{**INDEX["data"][0], "year": y} for y in (1866, 1870)]
        assert MOD["neighbours"](off_grid, 1868) == (1866, 1870)

    def test_a_malformed_row_is_skipped(self) -> None:
        """Each malformed year sits where it would be a neighbour if it were read."""
        doctored = copy.deepcopy(INDEX)
        doctored["data"] += [
            *({**INDEX["data"][0], "year": y} for y in ("1866", 1867.5, 1869.0)),
            {"year": None},
            "1870",
        ]
        assert MOD["neighbours"](doctored, 1868) == (1864, 1872)
        # A bool is not a year, though it is an int (query.YEAR_MIN already excludes
        # True, which is 1, so this pins the bound as much as the type).
        assert MOD["neighbours"]({"data": [{"year": True}]}, 2) == (None, None)
        # Out of range: 999 would be the first year's earlier neighbour, and 10000 the
        # last year's later one.
        outside = copy.deepcopy(INDEX)
        outside["data"] += [{**INDEX["data"][0], "year": y} for y in (999, 10000)]
        assert MOD["neighbours"](outside, YEARS[0]).earlier is None
        assert MOD["neighbours"](outside, YEARS[-1]).later is None

    @pytest.mark.parametrize("body", [None, {}, {"data": "x"}, {"data": [1866]}])
    def test_a_malformed_index_has_no_neighbours(self, body: Any) -> None:
        assert MOD["neighbours"](body, 1868) == (None, None)

    def test_a_middle_year_links_both_ways_unfiltered(self) -> None:
        tree = render(1868, "state=GA&candidate=ulysses-s-grant")
        assert nav_links(tree) == [
            (MOD["EARLIER_ID"], "/election/1864", "Earlier: the 1864 election"),
            (MOD["LATER_ID"], "/election/1872", "Later: the 1872 election"),
        ]
        nav = find(tree, MOD["NAV_ID"])
        assert getattr(nav, "aria-label") == MOD["ELECTION_NAV_LABEL"]
        # A client-side navigation, never a full page load.
        assert not any(getattr(link, "refresh", False) for link in of_type(nav, "Link"))

    def test_the_nav_comes_before_the_panel(self) -> None:
        ids = [getattr(child, "id", None) for child in render(1868).children]
        assert ids.index(MOD["NAV_ID"]) < ids.index(MOD["PANEL_ID"])

    def test_the_first_and_last_years_link_one_way(self) -> None:
        assert [i for i, _, _ in nav_links(render(YEARS[0]))] == [MOD["LATER_ID"]]
        assert [i for i, _, _ in nav_links(render(YEARS[-1]))] == [MOD["EARLIER_ID"]]

    def test_with_no_neighbour_there_is_no_landmark(self) -> None:
        tree = MOD["render"](
            year_body(1872),
            index_row(1872),
            [],
            per_capita_body(1872),
            MOD["Neighbours"](None, None),
        )
        assert find(tree, MOD["NAV_ID"]) is None
        assert tree.id == PAGE_ID

    def test_the_layout_reads_the_neighbours_from_the_served_index(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gapped = copy.deepcopy(INDEX)
        gapped["data"] = [r for r in gapped["data"] if r["year"] not in (1864, 1872)]
        gapped["data"].append({**INDEX["data"][0], "year": 1866})
        cached_client(monkeypatch)
        api.CLIENT.snapshot.responses[api.ELECTIONS_PATH] = gapped  # type: ignore[union-attr]
        assert routed_hrefs(route("/election/1868")) == {
            MOD["EARLIER_ID"]: "/election/1866",
            MOD["LATER_ID"]: "/election/1876",
        }

    def test_following_a_link_makes_only_the_target_year_s_fills(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC3 as amended at the plan gate: the target year's own fills on a miss (two
        since #280), and none of the link's own."""
        _, calls, _ = cached_client(monkeypatch)
        response = route("/election/1868")
        assert calls == ["/v1/elections/1868", "/v1/elections/1868/per-capita"]
        calls.clear()
        later = routed_hrefs(response)[MOD["LATER_ID"]]
        assert PAGE_ID in routed_ids(route(later))
        assert calls == ["/v1/elections/1872", "/v1/elections/1872/per-capita"]

    def test_no_nav_and_no_filter_sentence_where_the_page_has_no_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        found = MOD["layout"](year="1872")
        assert find(found, MOD["NAV_ID"]) is not None
        assert lede(found) == f"{MOD['LEDE']} {MOD['FILTER_SENTENCE']}"
        not_found = MOD["layout"](year="1825")
        assert find(not_found, MOD["NOT_FOUND_ID"]) is not None
        assert find(not_found, MOD["NAV_ID"]) is None
        assert lede(not_found) == MOD["LEDE"]

        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        degraded = MOD["layout"](year="1872")
        assert components.UNAVAILABLE_MESSAGE in texts(degraded)
        assert find(degraded, MOD["NAV_ID"]) is None
        assert lede(degraded) == MOD["LEDE"]

    @pytest.mark.parametrize("failure", ["unavailable", "malformed"])
    def test_with_the_index_read_a_failed_render_shows_neither(
        self, monkeypatch: pytest.MonkeyPatch, failure: str
    ) -> None:
        """The degraded state after the index was read and validated the year: a fill
        fails, or the body makes the render refuse it. The links and the filter
        sentence come only after the render, never between the index and the fills."""
        target = "/v1/elections/1872/per-capita"
        recorded, _ = fake_fetch(RECORDED)

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == target:
                if failure == "unavailable":
                    raise api.ApiUnavailable(f"GET {path}: HTTP 503")
                body = {**per_capita_body(1872), "data": []}
                return api.Response(body=body, version=VERSION)
            response: api.Response = recorded(path, timeout)
            return response

        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        degraded = MOD["layout"](year="1872")
        assert components.UNAVAILABLE_MESSAGE in texts(degraded)
        assert find(degraded, MOD["NAV_ID"]) is None
        assert lede(degraded) == MOD["LEDE"]


# --- the title ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "named"),
    [
        ("1872", True),
        ("1825", True),  # #325: a not-found title is a follow-up
        (None, False),
        ("", False),
        (["1872"], False),
        ("<script>", False),
        ("18720", False),
    ],
)
def test_the_title_is_total_and_names_only_a_four_digit_year(
    year: Any, named: bool
) -> None:
    title = PAGE["title"](year=year)
    assert isinstance(title, str)
    assert (f"The {year} election" in title) is named
    assert "<" not in title


def test_the_footer_carries_the_response_s_provenance() -> None:
    body = year_body(1872)
    body["meta"]["provenance"]["snapshot_version"] = "SENTINEL-version"
    assert "SENTINEL-version" in texts(render(1872, body=body))
    assert f"{META['provenance']['source_name']} (" in texts(render(1872))


# --- the per-capita table, T6 (#280) --------------------------------------------------

PER_CAPITA = MOD["PER_CAPITA_TABLE_ID"]
NO_FIGURE = "No census figure for this state at this election"
NO_VOTES = "No electoral votes this election"


def per_capita_rows(tree: Any) -> dict[str, dict[str, str]]:
    """T6's rows as ``{state: {field: cell text}}``."""
    fields = MOD["PER_CAPITA_FIELDS"]
    rows = [
        dict(zip(fields, (cell_text(c) for c in row), strict=True))
        for row in table_rows(tree, PER_CAPITA)
    ]
    return {row["state"]: row for row in rows}


def section(year: int, body: Any = None, **chosen: Any) -> Any:
    """T6 alone, built from the per-capita response only (so it also serves 1848 and
    1864, whose ``/v1/elections/{year}`` is not recorded), with the filters
    ``chosen``."""
    body = per_capita_body(year) if body is None else body
    filters = MOD["Filters"](
        **{"state": None, "candidate": None, "pv_status": None, "count_status": None}
        | chosen
    )
    download = MOD["_download"](year, "per-capita", "x", body, filters)
    rows = MOD["_per_capita_rows"](body["data"], year)
    return MOD["_per_capita_section"](rows, filters, download)


def all_cells(tree: Any) -> list[str]:
    return [cell_text(c) for row in table_rows(tree, PER_CAPITA) for c in row]


def test_t6_reads_every_field_from_its_response() -> None:
    row = per_capita_body(1872)["data"][0]
    assert set(MOD["PER_CAPITA_FIELDS"]) <= set(row)
    assert MOD["PER_CAPITA_FIELDS"] == (
        "state",
        "governing_census_year",
        "state_electoral_votes",
        "population",
        "boundary_basis",
        "coverage",
        "persons_per_electoral_vote",
    )


def test_1848_texas_says_no_census_figure_governs_the_election() -> None:
    texas = per_capita_rows(section(1848))["Texas"]
    assert texas["population"] == NO_FIGURE
    assert texas["coverage"] == NO_FIGURE
    assert texas["persons_per_electoral_vote"] == NO_FIGURE
    # The only such cell that year; every other state has its figure.
    rows = per_capita_rows(section(1848))
    assert [s for s, r in rows.items() if r["persons_per_electoral_vote"] == NO_FIGURE] == [
        "Texas"
    ]


def test_1864_every_zero_allotment_says_it_had_no_electoral_votes() -> None:
    body = per_capita_body(1864)
    zero = {r["state"] for r in body["data"] if r["state_electoral_votes"] == 0}
    assert len(zero) == 11  # read from the response, checked against F10
    rows = per_capita_rows(section(1864))
    assert {s for s, r in rows.items() if r["persons_per_electoral_vote"] == NO_VOTES} == zero
    for row in (r for r in body["data"] if r["state_electoral_votes"] == 0):
        shown = rows[row["state"]]
        assert shown["state_electoral_votes"] == "0"
        # Its population is still shown: only the ratio has no denominator.
        assert shown["population"] == f"{row['population']:,}"


@pytest.mark.parametrize("year", [1848, 1864, 1868, 1872, 2024])
def test_no_recorded_t6_cell_is_bare_or_infinite(year: int) -> None:
    for text in all_cells(section(year)):
        assert text.strip()
        assert text not in ("None", "null")
        assert "inf" not in text.lower() and "nan" not in text.lower()


def test_a_ratio_is_shown_to_a_whole_person() -> None:
    body = per_capita_body(2024)
    california = next(r for r in body["data"] if r["state_usps"] == "CA")
    shown = per_capita_rows(section(2024))["California"]
    assert shown["persons_per_electoral_vote"] == (
        f"{round(california['persons_per_electoral_vote']):,}"
    )
    assert shown["population"] == f"{california['population']:,}"
    assert shown["governing_census_year"] == str(california["governing_census_year"])


def test_the_governing_census_is_shown_with_its_reason() -> None:
    tree = section(1872)
    assert {r["governing_census_year"] for r in per_capita_rows(tree).values()} == {
        "1870"
    }
    assert labels.GOVERNING_CENSUS_NOTE in texts(tree)
    assert labels.GOVERNING_CENSUS_NOTE == (
        "Each election uses the census that set the state's electoral votes, not the "
        "nearest one: 2020 uses the 2010 census, and 1924 and 1928 use 1910, because "
        "Congress did not redistribute House seats after the 1920 census."
    )


def test_each_boundary_basis_cell_carries_its_help_text() -> None:
    tree = section(1848)
    basis = MOD["PER_CAPITA_FIELDS"].index("boundary_basis")
    cells = [row[basis] for row in table_rows(tree, PER_CAPITA)]
    assert {c.title for c in cells} == {labels.BOUNDARY_NOTE}
    assert {cell_text(c) for c in cells} == {
        "Borders at the election",
        "Present-day borders",
    }
    assert labels.BOUNDARY_NOTE in texts(tree)
    assert labels.BOUNDARY_NOTE == (
        "At the election: the people inside the state's borders when the election was "
        "held. Present-day borders: the Census Bureau's figure for the state as its "
        "table reports it, which this dataset does not claim matches the state's "
        "borders at that election."
    )


def test_every_recorded_year_renders_t6_beside_t2_and_t3() -> None:
    for year in RECORDED_YEARS:
        tree = render(year)
        states = {r["state"] for r in per_capita_body(year)["data"]}
        assert set(per_capita_rows(tree)) == states
        assert find(tree, STATES) is not None and find(tree, NATION) is not None


def test_t6_is_sorted_by_the_page_not_trusted_in_api_order() -> None:
    body = per_capita_body(1872)
    body["data"].reverse()
    names = list(per_capita_rows(render(1872, per_capita=body)))
    assert names == sorted(names)


class TestT6Filters:
    def test_the_state_filter_narrows_t6(self) -> None:
        assert list(per_capita_rows(render(1872, "state=GA"))) == ["Georgia"]

    def test_t6_follows_the_state_t2_resolved(self) -> None:
        """T2 falls back to "all" for a state absent from its rows, and T6 applies T2's
        resolved filter rather than re-resolving: one URL never shows T2 unfiltered
        and T6 filtered."""
        body = year_body(1872)
        body["data"] = [r for r in body["data"] if r["state_usps"] != "GA"]
        tree = render(1872, "state=GA", body=body)
        assert len(per_capita_rows(tree)) == len(per_capita_body(1872)["data"])
        # And a state T2 resolves that T6 lacks is an honest empty result.
        per_capita = per_capita_body(1872)
        per_capita["data"] = [r for r in per_capita["data"] if r["state_usps"] != "GA"]
        tree = render(1872, "state=GA", per_capita=per_capita)
        assert per_capita_rows(tree) == {}
        assert "No rows match these filters." in texts(tree)

    @pytest.mark.parametrize(
        "search",
        ["candidate=horace-greeley", "pv_status=legislature_chosen",
         "electoral_count_status=not_counted"],
    )
    def test_the_other_filters_do_not_narrow_t6(self, search: str) -> None:
        tree = render(1872, search)
        assert len(per_capita_rows(tree)) == len(per_capita_body(1872)["data"])

    def test_t6_says_which_filter_applies_and_counts_its_rows(self) -> None:
        tree = render(1872, "state=GA")
        total = len(per_capita_body(1872)["data"])
        assert MOD["PER_CAPITA_FILTER_NOTE"] in texts(tree)
        assert f"Showing 1 of {total} rows" in texts(tree)


class TestT6Bodies:
    @pytest.mark.parametrize("data", [[], None, "rows"])
    def test_a_body_with_no_rows_is_malformed(self, data: Any) -> None:
        body = per_capita_body(1872)
        body["data"] = data
        with pytest.raises(TypeError, match="/v1/elections/1872/per-capita"):
            render(1872, per_capita=body)

    @pytest.mark.parametrize(
        "change",
        [{"year": 1868}, {"year": "1872"}, {"year": None}, {"state_usps": "ga"},
         {"state_usps": None}],
    )
    def test_a_row_of_another_year_or_no_state_code_is_malformed(
        self, change: dict[str, Any]
    ) -> None:
        body = per_capita_body(1872)
        body["data"][3].update(change)
        with pytest.raises(TypeError, match="/v1/elections/1872/per-capita"):
            render(1872, per_capita=body)

    def test_a_malformed_body_degrades_the_whole_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The page's success marker covers T6: no marker without it."""
        body = per_capita_body(1872)
        body["data"] = []
        fetch, _ = fake_fetch({**RECORDED, "/v1/elections/1872/per-capita": body})
        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        ids = routed_ids(route("/election/1872"))
        assert "unavailable" in ids
        assert PAGE_ID not in ids

    @pytest.mark.parametrize(
        "answer",
        [
            api.ApiUnavailable("GET /v1/elections/1872/per-capita: HTTP 503"),
            # The real recorded body: only its version is wrong, so this degrades only
            # through View.get's version check.
            api.Response(
                body=copy.deepcopy(RECORDED["/v1/elections/1872/per-capita"]),
                version="another-snapshot",
            ),
        ],
        ids=["unavailable", "another-version"],
    )
    def test_a_failed_per_capita_read_degrades_the_whole_page(
        self, monkeypatch: pytest.MonkeyPatch, answer: api.Response | Exception
    ) -> None:
        """The read itself failing, not only a malformed body: the page's success
        marker covers T6, so T2 and T3 do not render without it, and a response of
        another snapshot is never mixed into the render."""
        target = "/v1/elections/1872/per-capita"
        recorded, _ = fake_fetch(RECORDED)
        calls: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls.append(path)
            if path == target:
                if isinstance(answer, Exception):
                    raise answer
                return answer
            response: api.Response = recorded(path, timeout)
            return response

        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        ids = routed_ids(route("/election/1872"))
        assert "unavailable" in ids
        assert PAGE_ID not in ids and STATES not in ids
        assert target in calls

    def test_a_non_finite_ratio_reads_unrecognized(self) -> None:
        body = per_capita_body(1872)
        row = next(r for r in body["data"] if r["state_usps"] == "GA")
        row["persons_per_electoral_vote"] = float("inf")
        shown = per_capita_rows(render(1872, per_capita=body))["Georgia"]
        assert shown["persons_per_electoral_vote"] == labels.UNRECOGNIZED

    def test_an_unexplained_null_names_no_cause_and_does_not_degrade(self) -> None:
        body = per_capita_body(1872)
        row = next(r for r in body["data"] if r["state_usps"] == "GA")
        row["persons_per_electoral_vote"] = None
        row["population"] = None
        shown = per_capita_rows(render(1872, per_capita=body))["Georgia"]
        assert shown["persons_per_electoral_vote"] == labels.NOT_IN_DATASET
        assert shown["population"] == labels.NOT_IN_DATASET

    def test_an_unknown_coverage_value_reads_unrecognized(self) -> None:
        body = per_capita_body(1872)
        row = next(r for r in body["data"] if r["state_usps"] == "GA")
        row.update(coverage="estimated", persons_per_electoral_vote=None)
        shown = per_capita_rows(render(1872, per_capita=body))["Georgia"]
        assert shown["coverage"] == labels.UNRECOGNIZED
        assert shown["persons_per_electoral_vote"] == labels.UNRECOGNIZED


def test_the_routed_page_shows_t6_and_reads_its_own_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, calls, _ = cached_client(monkeypatch)
    ids = routed_ids(route("/election/1868"))
    assert {PAGE_ID, PER_CAPITA} <= ids
    assert "/v1/elections/1868/per-capita" in calls


def test_the_footer_names_the_census_bureau_and_its_license() -> None:
    provenance = per_capita_body(1872)["meta"]["provenance"]
    footer = of_type(render(1872), "Footer")
    (footer_node,) = footer
    assert provenance["census_source_name"] == "U.S. Census Bureau"
    assert f"{provenance['census_source_name']} (" in texts(footer_node)
    links = {a.href: a.children for a in of_type(footer_node, "A")}
    assert links[provenance["census_license_url"]] == provenance["census_license"]


def test_every_per_capita_closed_value_has_a_label() -> None:
    assert set(labels.BOUNDARY_BASIS) == set(PER_CAPITA_BOUNDARY_BASIS_VALUES)
    assert set(labels.PER_CAPITA_COVERAGE) == set(PER_CAPITA_COVERAGE_VALUES)
    assert labels.NO_GOVERNING_FIGURE in PER_CAPITA_COVERAGE_VALUES


class TestPerCapitaCells:
    """The null rule's single source, :func:`explore.labels.persons_per_electoral_vote`
    and :func:`explore.labels.population` (#280)."""

    def test_a_missing_census_figure_wins_over_a_zero_allotment(self) -> None:
        cell = labels.persons_per_electoral_vote(None, "no_governing_figure", 0)
        assert cell == NO_FIGURE

    @pytest.mark.parametrize(
        ("value", "coverage", "allotment", "shown"),
        [
            (None, "covered", 0, NO_VOTES),
            (None, "covered", 0.0, NO_VOTES),
            (None, "covered", False, labels.NOT_IN_DATASET),  # a bool is no allotment
            (None, "covered", 3, labels.NOT_IN_DATASET),
            (None, "estimated", 3, labels.UNRECOGNIZED),
            (None, None, 3, labels.NOT_IN_DATASET),
            (None, "", 3, labels.NOT_IN_DATASET),
            (None, "  ", 3, labels.NOT_IN_DATASET),
            (None, 7, 3, labels.UNRECOGNIZED),
            (677344.6545454545, "covered", 55, "677,345"),
            (12, "covered", 1, "12"),
            (float("inf"), "covered", 1, labels.UNRECOGNIZED),
            (float("-inf"), "covered", 0, labels.UNRECOGNIZED),
            (float("nan"), "covered", 1, labels.UNRECOGNIZED),
            # A blank is no figure, so its row's cause explains it (#355).
            ("", "no_governing_figure", 5, NO_FIGURE),
            (" ", "covered", 0, NO_VOTES),
            ("", "covered", 3, labels.NOT_IN_DATASET),
            # A zero allotment wins over an unrecognized coverage.
            (None, "estimated", 0, NO_VOTES),
            (10**400, "covered", 1, labels.UNRECOGNIZED),
            (True, "covered", 1, labels.UNRECOGNIZED),
            ("many", "covered", 1, labels.UNRECOGNIZED),
        ],
    )
    def test_the_ratio_cell_is_total(
        self, value: Any, coverage: Any, allotment: Any, shown: str
    ) -> None:
        assert labels.persons_per_electoral_vote(value, coverage, allotment) == shown

    @pytest.mark.parametrize(
        ("value", "coverage", "shown"),
        [
            (None, "no_governing_figure", NO_FIGURE),
            (None, "covered", labels.NOT_IN_DATASET),
            (None, "estimated", labels.UNRECOGNIZED),
            ("", "no_governing_figure", NO_FIGURE),  # a blank is no figure (#355)
            (None, None, labels.NOT_IN_DATASET),
            (None, "", labels.NOT_IN_DATASET),
            (37253956, "covered", "37,253,956"),
            ("many", "covered", labels.UNRECOGNIZED),
        ],
    )
    def test_the_population_cell_is_total(
        self, value: Any, coverage: Any, shown: str
    ) -> None:
        assert labels.population(value, coverage) == shown

    @pytest.mark.parametrize("value", ["county", "at_sea", 7, ["at_election"]])
    def test_a_closed_value_s_unknown_value_reads_unrecognized(
        self, value: Any
    ) -> None:
        assert labels.boundary_basis(value) == labels.UNRECOGNIZED
        assert labels.per_capita_coverage(value) == labels.UNRECOGNIZED

    @pytest.mark.parametrize("value", [None, "", "  "])
    def test_a_closed_value_that_is_no_value_is_never_bare(self, value: Any) -> None:
        assert labels.boundary_basis(value) == labels.NOT_IN_DATASET
        assert labels.per_capita_coverage(value) == labels.NOT_IN_DATASET


# --- the election panel and T3's hybrid columns (#308) --------------------------------

PANEL = MOD["PANEL_ID"]
PANEL_FIELDS: tuple[str, ...] = MOD["PANEL_FIELDS"]
#: The panel's fields with no value outside the popular-vote window.
PV_FIELDS = (
    "pv_winner",
    "hybrid_winner",
    "pv_flip",
    "hybrid_flip",
    "pv_margin",
    "hybrid_margin",
)
#: The panel's fields the API fills for every year.
EC_FIELDS = ("ec_winner", "ec_margin", "ec_determinative", "pv_coverage")
NOT_APPLICABLE = "Not in this dataset: no popular-vote figures for this year"
PANEL_YEARS = (*RECORDED_YEARS, 2024)


def panel(tree: Any) -> dict[str, str]:
    """The panel's cells as ``{field: text}``: each ``Dd`` with the ``Dt`` before it,
    keyed by that ``Dt``'s raw field name."""
    node = find(tree, PANEL)
    assert node is not None
    items = list(of_type(node, "Dl")[0].children)
    assert [type(i).__name__ for i in items] == ["Dt", "Dd"] * (len(items) // 2)
    return {
        dt.title: "".join(texts(dd.children))
        for dt, dd in zip(items[::2], items[1::2], strict=True)
    }


def panel_of(year: int, change: Any = None) -> dict[str, str]:
    body = year_body(year)
    if change is not None:
        change(body)
    return panel(render(year, body=body))


def ids_in_order(node: Any) -> list[str]:
    """Every ``id`` in a rendered tree, in document order."""
    if isinstance(node, (list, tuple)):
        return [i for child in node for i in ids_in_order(child)]
    own = getattr(node, "id", None)
    children = getattr(node, "children", None)
    if own is None and children is None:
        return []
    return ([own] if isinstance(own, str) else []) + ids_in_order(children)


class TestPanel:
    def test_1824_reads_not_applicable_and_no_majority(self) -> None:
        cells = panel_of(1824)
        assert {f: cells[f] for f in PV_FIELDS} == dict.fromkeys(
            PV_FIELDS, NOT_APPLICABLE
        )
        assert cells["ec_determinative"] == (
            "No candidate reached a majority of electors appointed"
        )
        # Below 1 while the popular-vote fields are not applicable (AC).
        assert year_body(1824)["election"]["pv_coverage"] < 1
        assert cells["pv_coverage"] == "72.8%"
        assert cells["ec_winner"] == "Andrew Jackson"
        assert cells["ec_margin"] == "5.7 percentage points"

    def test_2016_the_popular_vote_flips_and_the_hybrid_does_not(self) -> None:
        assert panel_of(2016) == {
            "ec_winner": "Donald J. Trump",
            "pv_winner": "Hillary Clinton",
            "hybrid_winner": "Donald J. Trump",
            "pv_flip": (
                "Yes: the popular-vote winner is not the Electoral College winner"
            ),
            "hybrid_flip": "No",
            "ec_margin": "14.3 percentage points",
            "pv_margin": "2.1 percentage points",
            "hybrid_margin": "6.1 percentage points",
            "ec_determinative": "A candidate won a majority of electors appointed",
            "pv_coverage": "100.0%",
        }

    def test_2024_inside_the_window_with_no_flip(self) -> None:
        cells = panel_of(2024)
        assert (cells["pv_flip"], cells["hybrid_flip"]) == ("No", "No")
        # Exact, so a margin scaled as a share (×100) fails.
        assert [cells[f] for f in ("ec_margin", "pv_margin", "hybrid_margin")] == [
            "16.0 percentage points",
            "1.5 percentage points",
            "8.7 percentage points",
        ]

    def test_1860_a_majority_reads_as_one(self) -> None:
        assert panel_of(1860)["ec_determinative"] == (
            "A candidate won a majority of electors appointed"
        )

    def test_a_hybrid_flip_reads_its_own_sentence(self) -> None:
        cells = panel_of(2016, lambda b: b["election"].update(hybrid_flip=True))
        assert cells["hybrid_flip"] == (
            "Yes: the hybrid winner is not the Electoral College winner"
        )

    @pytest.mark.parametrize(
        ("determinative", "role"), [(False, "leader"), (None, "leader")]
    )
    def test_a_flip_without_a_majority_names_the_leader(
        self, determinative: Any, role: str
    ) -> None:
        """#355: with no Electoral College majority (1824), a flip names its leader,
        never its winner."""
        cells = panel_of(
            2016,
            lambda b: b["election"].update(
                pv_flip=True, hybrid_flip=True, ec_determinative=determinative
            ),
        )
        assert cells["pv_flip"] == (
            f"Yes: the popular-vote winner is not the Electoral College {role}"
        )
        assert cells["hybrid_flip"] == (
            f"Yes: the hybrid winner is not the Electoral College {role}"
        )

    @pytest.mark.parametrize("year", PANEL_YEARS)
    def test_a_null_is_never_no(self, year: int) -> None:
        block = year_body(year)["election"]
        cells = panel_of(year)
        assert set(cells) == set(PANEL_FIELDS)
        for field, value in block.items():
            if field in cells and value is None:
                assert cells[field] in (NOT_APPLICABLE, labels.NOT_IN_DATASET), field
        assert not {"", "None", "No", "False", "0"} & {
            cells[f] for f in PANEL_FIELDS if block[f] is None
        }

    @pytest.mark.parametrize(
        ("flips", "shown"),
        [
            (
                (True, False, False),
                (
                    "Yes: the popular-vote winner is not the Electoral College leader",
                    "No",
                    labels.NO_EC_MAJORITY,
                ),
            ),
            ((False, False, True), ("No", "No", labels.EC_MAJORITY)),
        ],
    )
    def test_each_cell_reads_its_own_field(
        self, flips: tuple[bool, bool, bool], shown: tuple[str, str, str]
    ) -> None:
        """A distinct value in every panel field, so a cell reading another field
        shows the wrong one. The three booleans (``pv_flip``, ``hybrid_flip``,
        ``ec_determinative``) cannot all differ in one render, so two renders between
        them give every pair different values in at least one (#355: a non-bool is
        unrecognized, so string sentinels would all read alike)."""
        pv_flip, hybrid_flip, determinative = flips
        sentinels = {
            "ec_winner": "Sentinel EC",
            "pv_winner": "Sentinel PV",
            "hybrid_winner": "Sentinel Hybrid",
            "pv_flip": pv_flip,
            "hybrid_flip": hybrid_flip,
            "ec_margin": 11.11,
            "pv_margin": 22.22,
            "hybrid_margin": 33.33,
            "ec_determinative": determinative,
            "pv_coverage": 0.123,
        }
        assert set(sentinels) == set(PANEL_FIELDS)
        cells = panel_of(2016, lambda b: b["election"].update(sentinels))
        assert cells == {
            "ec_winner": "Sentinel EC",
            "pv_winner": "Sentinel PV",
            "hybrid_winner": "Sentinel Hybrid",
            "pv_flip": shown[0],
            "hybrid_flip": shown[1],
            "ec_margin": "11.1 percentage points",
            "pv_margin": "22.2 percentage points",
            "hybrid_margin": "33.3 percentage points",
            "ec_determinative": shown[2],
            "pv_coverage": "12.3%",
        }

    def test_the_window_is_read_from_coverage_not_literals(self) -> None:
        def window(pv_year_min: int, pv_year_max: int) -> Any:
            return lambda b: b["meta"]["provenance"]["coverage"].update(
                pv_year_min=pv_year_min, pv_year_max=pv_year_max
            )

        # 1824's fields are null: inside a window that starts earlier, they name no
        # cause; they are not "not applicable".
        inside = panel_of(1824, window(1800, 2024))
        assert {f: inside[f] for f in PV_FIELDS} == dict.fromkeys(
            PV_FIELDS, labels.NOT_IN_DATASET
        )

        # After the window's end: not applicable too.
        def ended(b: dict[str, Any]) -> None:
            window(1976, 2012)(b)
            b["election"].update(dict.fromkeys(PV_FIELDS))

        after = panel_of(2016, ended)
        assert {f: after[f] for f in PV_FIELDS} == dict.fromkeys(
            PV_FIELDS, NOT_APPLICABLE
        )
        # A value outside the window is still shown, as T2's popular votes are.
        assert panel_of(2016, window(1976, 2012))["pv_winner"] == "Hillary Clinton"

    @pytest.mark.parametrize("year", [1824, 2016])
    @pytest.mark.parametrize("field", EC_FIELDS)
    def test_an_electoral_college_null_names_no_cause(
        self, year: int, field: str
    ) -> None:
        cells = panel_of(year, lambda b: b["election"].update({field: None}))
        assert cells[field] == labels.NOT_IN_DATASET

    def test_the_panel_follows_the_links_inside_the_success_marker(self) -> None:
        order = ids_in_order(render(2016))
        # The success marker, the page's own URL store, the earlier and later links
        # (#324), then the panel, ahead of every table.
        assert order[:5] == [
            PAGE_ID,
            MOD["URL_ID"],
            MOD["NAV_ID"],
            MOD["EARLIER_ID"],
            MOD["LATER_ID"],
        ]
        assert order[5] == PANEL
        assert (
            order.index(PANEL)
            < order.index(STATES)
            < order.index(NATION)
            < order.index(MOD["PER_CAPITA_TABLE_ID"])
        )

    @pytest.mark.parametrize("year", [1824, 2024])
    @pytest.mark.parametrize(
        "window",
        [
            {"pv_year_min": True},
            {"pv_year_min": 1976.0},
            {"pv_year_min": "1976"},
            {"pv_year_max": float("nan")},
            {"pv_year_min": float("-inf"), "pv_year_max": float("inf")},
            {"pv_year_min": 2024, "pv_year_max": 1976},  # reversed
            {"pv_year_min": None},
            {"pv_year_max": None},
            {"pv_year_min": KeyError},  # removed
            {"pv_year_max": KeyError},  # removed
        ],
    )
    @pytest.mark.parametrize("block", ["recorded", "null"])
    def test_a_malformed_window_degrades_the_page(
        self,
        monkeypatch: pytest.MonkeyPatch,
        year: int,
        window: dict[str, Any],
        block: str,
    ) -> None:
        """At 2024 the panel is the window's only other reader (every row has a
        figure, and the year has a popular vote), and with a null block nothing else
        reads it: the page checks the window itself, before any cell does."""
        body = year_body(year)
        coverage = body["meta"]["provenance"]["coverage"]
        for key, value in window.items():
            if value is KeyError:
                coverage.pop(key)
            else:
                coverage[key] = value
        if block == "null":
            body["election"] = None
        fetch, _ = fake_fetch({**RECORDED, f"/v1/elections/{year}": body})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        tree = PAGE["layout"](year=str(year))
        assert "isn't responding" in " ".join(texts(tree))
        assert PAGE_ID not in component_ids(tree)

    @pytest.mark.parametrize("field", PANEL_FIELDS)
    def test_a_missing_panel_field_degrades_the_page(
        self, monkeypatch: pytest.MonkeyPatch, field: str
    ) -> None:
        body = year_body(2016)
        body["election"].pop(field)
        fetch, _ = fake_fetch({**RECORDED, "/v1/elections/2016": body})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        tree = PAGE["layout"](year="2016")
        assert "isn't responding" in " ".join(texts(tree))
        assert not {PAGE_ID, PANEL} & component_ids(tree)

    def test_the_panel_renders_only_with_the_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        assert PANEL in component_ids(PAGE["layout"](year="2016"))
        assert PANEL not in component_ids(PAGE["layout"](year="1825"))
        body = year_body(2016)
        body["election"]["year"] = 2012
        fetch, _ = fake_fetch({**RECORDED, "/v1/elections/2016": body})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        degraded = PAGE["layout"](year="2016")
        assert "isn't responding" in " ".join(texts(degraded))
        assert not {PAGE_ID, PANEL} & component_ids(degraded)

    @pytest.mark.parametrize(
        ("year", "ec_winner"),
        [
            (1872, labels.EC_WINNER),
            (2016, labels.EC_WINNER),
            (1824, labels.EC_LEADER_NO_MAJORITY),
        ],
    )
    def test_each_label_carries_its_field_name_and_a_glossary_names_them(
        self, year: int, ec_winner: str
    ) -> None:
        """The list and its glossary show one label per field: ``ec_winner``'s as
        ``ec_determinative`` chooses it (#355), every other one ``LABELS``'."""
        node = find(render(year), PANEL)
        expected = [
            (ec_winner if f == "ec_winner" else labels.LABELS[f], f)
            for f in PANEL_FIELDS
        ]
        dts = of_type(of_type(node, "Dl")[0], "Dt")
        assert [(dt.children, dt.title) for dt in dts] == expected
        glossary = of_type(node, "Details")
        assert [
            (dt.children, texts(dd.children)[0])
            for dt, dd in zip(
                of_type(glossary, "Dt"), of_type(glossary, "Dd"), strict=True
            )
        ] == expected

    def test_margins_are_labeled_in_percentage_points(self) -> None:
        for field in ("ec_margin", "pv_margin", "hybrid_margin"):
            assert labels.LABELS[field].endswith("(percentage points)"), field

    def test_the_hybrid_is_described_in_the_panel_and_under_t3(self) -> None:
        assert labels.HYBRID_NOTE == (
            "The hybrid score is the average of a candidate's electoral share and "
            "popular-vote share; the candidate with the highest score wins it."
        )
        tree = render(2016)
        assert labels.HYBRID_NOTE in texts(find(tree, PANEL))
        assert texts(tree).count(labels.HYBRID_NOTE) == 2
        # The second is T3's: after its table, before the next section's heading.
        order = texts(tree)
        under_t3 = len(order) - 1 - order[::-1].index(labels.HYBRID_NOTE)
        last_t3_cell = texts(find(tree, NATION))[-1]
        assert under_t3 > order.index(last_t3_cell)
        assert under_t3 < order.index("People per electoral vote")

    @pytest.mark.parametrize("year", PANEL_YEARS)
    def test_no_panel_text_calls_the_hybrid_better(self, year: int) -> None:
        """No word from a fixed list of evaluative words, matched as a word, in the
        panel's text or the hybrid's labels and note. A list cannot prove the hybrid is
        described rather than advocated: that rests on every fixed string the panel
        renders being pinned exactly (its heading here; the labels, cell sentences,
        notes and unavailable sentence in their own tests). This scan catches a familiar
        word in a future edit."""
        evaluative = re.compile(
            r"\b(better|best|fair|fairer|fairest|worse|worst|superior|should)\b",
            re.IGNORECASE,
        )
        tree = render(year)
        heading = [h.children for h in of_type(tree, "H2")]
        assert heading[0] == "Under each method"
        prose = [
            *texts(find(tree, PANEL)),
            *heading,
            labels.HYBRID_NOTE,
            MOD["PANEL_UNAVAILABLE"],
            labels.EC_WINNER,
            labels.EC_LEADER_NO_MAJORITY,
            labels.UNRECOGNIZED,
            labels.UNRECOGNIZED_NOTE,
            *(labels.LABELS[f] for f in PANEL_FIELDS),
            labels.LABELS["ec_share_hybrid"],
            labels.LABELS["hybrid_score"],
        ]
        assert [t for t in prose if evaluative.search(t)] == []
        assert evaluative.search("a fairer method")  # non-vacuity

    def test_the_approved_cell_wording(self) -> None:
        """The issue's sentences, as written there."""
        assert labels.NOT_APPLICABLE == NOT_APPLICABLE
        assert labels.EC_MAJORITY == "A candidate won a majority of electors appointed"
        assert labels.NO_EC_MAJORITY == (
            "No candidate reached a majority of electors appointed"
        )
        assert labels.FLIP_YES.format(method="popular-vote", role="winner") == (
            "Yes: the popular-vote winner is not the Electoral College winner"
        )
        assert labels.FLIP_YES.format(method="hybrid", role="leader") == (
            "Yes: the hybrid winner is not the Electoral College leader"
        )
        assert labels.EC_WINNER == "Electoral College winner"
        assert labels.EC_LEADER_NO_MAJORITY == "Electoral College leader (no majority)"
        assert labels.UNRECOGNIZED == "Unrecognized value"


class TestWordingRules:
    """The glossary's wording rules (#352, ``docs/glossary.md``): no constant #352
    rewords or adds carries an underscore. A snake_case field name always has one; a
    one-word field name (``party``, ``population``) is ordinary English and cannot be
    told from prose, so the underscore is what a test can check. #355 adds its labels
    and notes here; its closed-value and fallback paths are guarded per function
    (``test_an_unexpected_value_is_never_shown_raw``) and on each table page rendered
    from doctored bodies (``TestNoRawValues`` in ``test_dashboard_export.py``)."""

    @staticmethod
    def reworded() -> dict[str, str]:
        """Every wording #352 and #355 change or add, by where it lives."""
        texts_ = {
            f"LABELS[{key}]": labels.LABELS[key]
            for key in (
                "candidate_count",
                "boundary_basis",
                "governing_census_year",
                "population",
                "electoral_count_status_reason",
                "pv_flip",
                "hybrid_flip",
                "pv_winner",
                "hybrid_winner",
                "ec_winner",
            )
        }
        texts_ |= {f"PV_STATUS[{k}]": v for k, v in labels.PV_STATUS.items()}
        texts_ |= {
            f"COUNT_STATUS[{k}]": meaning
            for k, (_, meaning) in labels.COUNT_STATUS.items()
            if meaning is not None
        }
        texts_["BOUNDARY_BASIS[present_day]"] = labels.BOUNDARY_BASIS["present_day"]
        texts_["PER_CAPITA_COVERAGE[no_governing_figure]"] = (
            labels.PER_CAPITA_COVERAGE[labels.NO_GOVERNING_FIGURE]
        )
        for name in (
            "BOUNDARY_NOTE",
            "GOVERNING_CENSUS_NOTE",
            "NOT_APPLICABLE",
            "NO_FIGURE",
            "NO_NATIONAL_FIGURE",
            "HAS_POPULAR_VOTE_NOTE",
            "PARTY_NOTE",
            "PARTY_NULL_NOTE",
            "NO_NOMINATION",
            "NO_NOMINATION_NOTE",
            "PARTY_NOTES_HEADING",
            "MARGIN_NOTE",
            "EC_SHARE_HYBRID_NOTE",
            "UNRECOGNIZED",
            "UNRECOGNIZED_NOTE",
            "EC_WINNER",
            "EC_LEADER_NO_MAJORITY",
        ):
            texts_[name] = getattr(labels, name)
        for role in ("winner", "leader"):
            texts_[f"FLIP_YES[{role}]"] = labels.FLIP_YES.format(
                method="popular-vote", role=role
            )
        texts_ |= {
            f"NOMINATING_PARTY[{k}]": v for k, v in labels.NOMINATING_PARTY.items()
        }
        texts_["NO_PV_SENTENCE"] = MOD["NO_PV_SENTENCE"].format(
            year=1860, first=1976, last=2024
        )
        return texts_

    @staticmethod
    def breaks_the_rule(text: str) -> bool:
        return "_" in text

    @classmethod
    def violations(cls) -> dict[str, str]:
        """The scan: every reworded text that breaks the rule, by name."""
        return {
            name: text
            for name, text in cls.reworded().items()
            if cls.breaks_the_rule(text)
        }

    def test_no_reworded_constant_carries_an_underscore(self) -> None:
        assert self.violations() == {}

    def test_the_scan_reports_exactly_a_constant_that_breaks_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuity of the scan itself, not only of the predicate (#352's review,
        deferred to #355): one listed constant underscored is the one name reported."""
        monkeypatch.setattr(labels, "UNRECOGNIZED_NOTE", "pv_status is unknown")
        assert self.violations() == {"UNRECOGNIZED_NOTE": "pv_status is unknown"}

    def test_the_rule_fails_what_it_should(self) -> None:
        # Non-vacuity: the note #352 replaced named the raw field.
        assert self.breaks_the_rule(
            "has_popular_vote is false where this dataset holds no popular-vote "
            "figure for the year; it does not say whether a popular vote was held."
        )

    def test_the_drafted_notes_are_pinned(self) -> None:
        """Drafted for the owner's review in place (#352): pinned as shipped, so a
        reword is a deliberate change here, and the panel's every fixed string stays
        pinned (``test_no_panel_text_calls_the_hybrid_better``)."""
        assert labels.MARGIN_NOTE == (
            "A margin is the gap, in percentage points, between the first- and "
            "second-place candidates under that method. Each method ranks the "
            "candidates on its own."
        )
        assert labels.EC_SHARE_HYBRID_NOTE == (
            "The hybrid uses each candidate's electoral share as it is, so the hybrid's "
            "electoral share repeats it. Both are shown so you can check that."
        )
        # Drafted with the glossary (#355) for the owner's review in place.
        assert labels.UNRECOGNIZED_NOTE == (
            "This dataset holds a value that this page has no label for."
        )

    def test_the_drafted_notes_show_where_they_explain(self) -> None:
        tree = render(1872)
        panel_notes = [p.children for p in of_type(find(tree, PANEL), "P")]
        assert labels.MARGIN_NOTE in panel_notes
        assert labels.HYBRID_NOTE in panel_notes
        shown = [p.children for p in of_type(tree, "P")]
        assert labels.EC_SHARE_HYBRID_NOTE in shown
        assert labels.EC_SHARE_HYBRID_NOTE not in panel_notes

    def test_the_footer_names_the_data_version(self) -> None:
        footer = find(render(1872), components.SNAPSHOT_ID)
        assert footer is not None
        assert footer.children[0] == "Data version "


class TestEcWinnerLabel:
    """``ec_winner``'s label follows ``ec_determinative`` in all three states (#355)."""

    @pytest.mark.parametrize(
        ("determinative", "label"),
        [
            (True, "Electoral College winner"),
            (False, "Electoral College leader (no majority)"),
            (None, "Electoral College leader"),
            # Unknown values claim neither a majority nor its absence.
            (1, "Electoral College leader"),
            ("true", "Electoral College leader"),
        ],
    )
    def test_the_label(self, determinative: Any, label: str) -> None:
        assert labels.ec_winner_label(determinative) == label

    @pytest.mark.parametrize(
        ("year", "change", "label"),
        [
            (1824, None, "Electoral College leader (no majority)"),
            (2016, None, "Electoral College winner"),
            (2016, False, "Electoral College leader (no majority)"),
            (1824, True, "Electoral College winner"),
            (2016, "null", "Electoral College leader"),
        ],
    )
    def test_the_panel_row_and_its_field_name_read_the_chosen_label(
        self, year: int, change: Any, label: str
    ) -> None:
        body = year_body(year)
        if change is not None:
            body["election"]["ec_determinative"] = None if change == "null" else change
        node = find(render(year, body=body), PANEL)
        dts = {dt.title: dt.children for dt in of_type(of_type(node, "Dl")[0], "Dt")}
        assert dts["ec_winner"] == label
        names = {
            texts(dd.children)[0]: dt.children
            for dt, dd in zip(
                of_type(of_type(node, "Details"), "Dt"),
                of_type(of_type(node, "Details"), "Dd"),
                strict=True,
            )
        }
        assert names["ec_winner"] == label


class TestPartyDisplay:
    """The nominating party's display forms (#389): the API and the download keep the
    code. Test-only import of ``usvote.party``, the vocabulary of record (stdlib-only;
    the runtime imports no ``usvote``, D070(b))."""

    #: The owner-approved display forms (#389's plan gate, 2026-10-19), written out.
    EXPECTED = {
        "democratic_republican": "Democratic-Republican",
        "national_republican": "National Republican",
        "democratic": "Democratic",
        "anti_masonic": "Anti-Masonic",
        "whig": "Whig",
        "american": "American (Know-Nothing)",
        "republican": "Republican",
        "southern_democratic": "Southern Democratic",
        "constitutional_union": "Constitutional Union",
        "liberal_republican": "Liberal Republican",
        "populist": "Populist",
        "progressive_1912": "Progressive (1912)",
        "progressive_1924": "Progressive (1924)",
        "states_rights_democratic": "States' Rights Democratic",
        "american_independent": "American Independent",
        "libertarian": "Libertarian",
        "liberal_republican_democratic": "Liberal Republican and Democratic",
        "democratic_populist": "Democratic and Populist",
        "american_whig": "American (Know-Nothing) and Whig",
        "no_nomination": (
            "Without a party's nomination for President when the electors voted"
        ),
    }

    def test_every_code_has_a_display_form(self) -> None:
        # A new code (a superseding D-entry) fails here until it has a form.
        from usvote.party import NOMINATING_PARTIES

        assert set(labels.NOMINATING_PARTY) == set(NOMINATING_PARTIES)
        assert labels.NOMINATING_PARTY == self.EXPECTED

    def test_a_joint_form_names_its_components_joined_by_and(self) -> None:
        from usvote.party import PARTY_COMPONENTS

        joint = {c: parts for c, parts in PARTY_COMPONENTS.items() if len(parts) > 1}
        assert joint  # non-vacuous
        for code, parts in joint.items():
            expected = " and ".join(labels.NOMINATING_PARTY[p] for p in parts)
            assert labels.NOMINATING_PARTY[code] == expected, code

    def test_the_forms_are_distinct_and_never_a_fallback(self) -> None:
        forms = list(labels.NOMINATING_PARTY.values())
        assert len(set(forms)) == len(forms)  # two codes never read as one party
        assert not set(forms) & {labels.NOT_IN_DATASET, labels.UNRECOGNIZED}
        assert labels.NOMINATING_PARTY["no_nomination"] == labels.NO_NOMINATION
        assert "no party" not in labels.NO_NOMINATION.lower()

    def test_the_recorded_responses_carry_only_vocabulary_codes(self) -> None:
        """Ties the table to what the API actually served."""
        from usvote.party import NOMINATING_PARTIES

        found: set[Any] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "nominating_party":
                        found.add(value)
                    else:
                        walk(value)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(RECORDED)
        assert found - {None} <= set(NOMINATING_PARTIES)
        # Non-vacuous: the recordings carry both joint codes now served.
        assert {"liberal_republican_democratic", "democratic_populist"} <= found

    def test_the_page_shows_the_form_and_its_downloads_keep_the_code(self) -> None:
        """T2 and T3 show the display form; both files carry the code (or an empty
        cell), never a display form. T4's file: ``test_dashboard_export.py``."""
        from tests.unit.test_dashboard_export import Csv, links
        from usvote.party import NOMINATING_PARTIES

        tree = render(2016)
        assert nation_rows(tree)["Hillary Clinton"]["nominating_party"] == "Democratic"
        shown = {r["nominating_party"] for r in state_rows(tree)} - {
            labels.NOT_IN_DATASET
        }
        assert shown == {"Democratic", "Republican"}
        for table_id in (STATES, NATION):
            rows = Csv(links(tree)[export.link_id(table_id)].href).rows
            codes = {r["nominating_party"] for r in rows} - {""}
            assert codes == {"democratic", "republican"}, table_id
            assert codes <= set(NOMINATING_PARTIES)


class TestUnrecognizedCell:
    """An "Unrecognized value" cell carries its help text (#355, owner decision at the
    plan gate): the cell builder, and a T2 cell and a panel cell here; every table's
    cells on a doctored page in ``TestNoRawValues`` (``test_dashboard_export.py``)."""

    def test_the_cell_builder(self) -> None:
        unknown = labels.cell(labels.UNRECOGNIZED)
        assert (unknown.children, unknown.title) == (
            labels.UNRECOGNIZED,
            labels.UNRECOGNIZED_NOTE,
        )
        assert labels.cell([labels.UNRECOGNIZED]).title == labels.UNRECOGNIZED_NOTE
        assert getattr(labels.cell("12"), "title", None) is None
        # An unrecognized value's note wins over a cell's own help text.
        assert labels.cell(labels.UNRECOGNIZED, title="x").title == (
            labels.UNRECOGNIZED_NOTE
        )
        assert labels.cell("ok", title="x").title == "x"
        assert type(labels.cell("ok", dash.html.Dd)).__name__ == "Dd"

    def test_a_table_cell_and_a_panel_cell_carry_the_note(self) -> None:
        body = year_body(2016)
        body["data"][0]["pv_status"] = "mystery_code"
        body["data"][0]["electoral_count_status"] = "mystery_code"
        body["election"]["ec_margin"] = "wide"
        tree = render(2016, body=body)
        flagged = [
            c
            for row in table_rows(tree, STATES)
            for c in row
            if getattr(c, "title", None) == labels.UNRECOGNIZED_NOTE
        ]
        # Its popular-vote cell too: its cause is the unknown status.
        assert [cell_text(c) for c in flagged] == [labels.UNRECOGNIZED] * 3
        dds = of_type(of_type(find(tree, PANEL), "Dl")[0], "Dd")
        margin = dds[PANEL_FIELDS.index("ec_margin")]
        assert (margin.children, margin.title) == (
            labels.UNRECOGNIZED,
            labels.UNRECOGNIZED_NOTE,
        )
        assert [d.title for d in dds if getattr(d, "title", None)] == [
            labels.UNRECOGNIZED_NOTE
        ]


class TestT3Hybrid:
    def test_1824_hybrid_scores_are_not_applicable(self) -> None:
        rows = nation_rows(render(1824))
        assert {r["hybrid_score"] for r in rows.values()} == {NOT_APPLICABLE}
        assert rows["Andrew Jackson"]["ec_share_hybrid"] == "37.9%"

    def test_2016_scores_and_a_candidate_with_no_figure(self) -> None:
        rows = nation_rows(render(2016))
        assert rows["Donald J. Trump"]["hybrid_score"] == "51.3%"
        assert rows["Hillary Clinton"]["hybrid_score"] == "45.2%"
        assert rows["Hillary Clinton"]["ec_share_hybrid"] == "42.2%"
        assert rows["Colin Powell"]["hybrid_score"] == labels.NO_NATIONAL_FIGURE

    @pytest.mark.parametrize("year", PANEL_YEARS)
    def test_every_hybrid_cell_is_labeled(self, year: int) -> None:
        for row in nation_rows(render(year)).values():
            assert row["ec_share_hybrid"].endswith("%"), (year, row)
            assert row["hybrid_score"] not in ("", "None", "No", "0"), (year, row)

    def test_t3_reads_the_index_s_flag_for_the_hybrid_score(self) -> None:
        """Doctored index rows, so the score's year rule is T3's, not a literal."""
        missing = MOD["render"](
            year_body(2016),
            {**index_row(2016), "has_popular_vote": False},
            [],
            per_capita_body(2016),
            MOD["neighbours"](INDEX, 2016),
        )
        assert nation_rows(missing)["Donald J. Trump"]["hybrid_score"] == NOT_APPLICABLE
        held = MOD["render"](
            year_body(1872),
            {**index_row(1872), "has_popular_vote": True},
            [],
            per_capita_body(1872),
            MOD["neighbours"](INDEX, 1872),
        )
        grant = nation_rows(held)["Ulysses S. Grant"]
        assert grant["hybrid_score"] == labels.NO_NATIONAL_FIGURE

    def test_a_null_hybrid_share_names_no_cause(self) -> None:
        body = year_body(2016)
        body["summary"][0]["ec_share_hybrid"] = None
        rows = nation_rows(render(2016, body=body))
        assert rows[body["summary"][0]["candidate"]]["ec_share_hybrid"] == (
            labels.NOT_IN_DATASET
        )


class TestPanelCells:
    @pytest.mark.parametrize(
        ("value", "applicable", "cell"),
        [
            (None, False, NOT_APPLICABLE),
            (None, True, labels.NOT_IN_DATASET),
            (2.097, False, "2.1 percentage points"),  # a value wins
            (0, True, "0.0 percentage points"),
            (True, True, labels.UNRECOGNIZED),
            ("wide", True, labels.UNRECOGNIZED),
            (10**400, True, labels.UNRECOGNIZED),
            ("", True, labels.NOT_IN_DATASET),
            ("", False, NOT_APPLICABLE),
            (float("nan"), True, labels.UNRECOGNIZED),
            (float("inf"), True, labels.UNRECOGNIZED),
        ],
    )
    def test_margin(self, value: Any, applicable: bool, cell: str) -> None:
        assert labels.margin(value, applicable) == cell

    @pytest.mark.parametrize(
        ("value", "applicable", "determinative", "cell"),
        [
            (
                True,
                True,
                True,
                "Yes: the hybrid winner is not the Electoral College winner",
            ),
            # With no majority, or none known, the Electoral College has a leader (#355).
            (
                True,
                True,
                False,
                "Yes: the hybrid winner is not the Electoral College leader",
            ),
            (
                True,
                True,
                None,
                "Yes: the hybrid winner is not the Electoral College leader",
            ),
            (
                True,
                True,
                1,
                "Yes: the hybrid winner is not the Electoral College leader",
            ),
            (False, True, True, "No"),
            # A value is shown whatever the year (approved): only a null outside the
            # window is not applicable.
            (False, False, True, "No"),
            (
                True,
                False,
                True,
                "Yes: the hybrid winner is not the Electoral College winner",
            ),
            (None, False, True, NOT_APPLICABLE),
            (None, True, True, labels.NOT_IN_DATASET),
            ("", True, True, labels.NOT_IN_DATASET),
            (0, True, True, labels.UNRECOGNIZED),  # only a boolean is Yes or No
            (1, True, True, labels.UNRECOGNIZED),
            ("false", True, True, labels.UNRECOGNIZED),
        ],
    )
    def test_flip(
        self, value: Any, applicable: bool, determinative: Any, cell: str
    ) -> None:
        assert (
            labels.flip(value, "hybrid", applicable, determinative=determinative)
            == cell
        )

    @pytest.mark.parametrize(
        ("value", "cell"),
        [
            (True, "A candidate won a majority of electors appointed"),
            (False, "No candidate reached a majority of electors appointed"),
            (None, labels.NOT_IN_DATASET),
            ("", labels.NOT_IN_DATASET),
            (0, labels.UNRECOGNIZED),
            ("no", labels.UNRECOGNIZED),
        ],
    )
    def test_ec_majority(self, value: Any, cell: str) -> None:
        assert labels.ec_majority(value) == cell

    def test_winner_and_share_cell(self) -> None:
        assert labels.winner(None, False) == NOT_APPLICABLE
        assert labels.winner(None, True) == labels.NOT_IN_DATASET
        assert labels.winner("Abraham Lincoln", False) == "Abraham Lincoln"
        # A blank is no name; a name that is not text is unrecognized (#355).
        assert labels.winner(" ", False) == NOT_APPLICABLE
        assert labels.winner("", True) == labels.NOT_IN_DATASET
        assert labels.winner(7, True) == labels.UNRECOGNIZED
        assert labels.share_cell(None) == labels.NOT_IN_DATASET
        assert labels.share_cell(0.7279693486590039) == "72.8%"

    def test_the_window(self) -> None:
        assert labels.in_pv_window(PV_MIN, COVERAGE) is True
        assert labels.in_pv_window(PV_MAX, COVERAGE) is True
        assert labels.in_pv_window(PV_MIN - 4, COVERAGE) is False
        assert labels.in_pv_window(PV_MAX + 4, COVERAGE) is False

    @pytest.mark.parametrize(
        "coverage",
        [{}, {"pv_year_min": 1976}, {"pv_year_min": "1976", "pv_year_max": 2024}],
    )
    def test_a_malformed_window_raises_rather_than_guesses(self, coverage: Any) -> None:
        with pytest.raises((KeyError, TypeError)):
            labels.in_pv_window(2016, coverage)


def test_a_blank_t3_figure_is_a_missing_one() -> None:
    """#355's review: a blank is no value, so inside the window it reads as a
    candidate with no popular-vote figure, as a null does."""
    national_pv = MOD["_national_pv"]
    assert national_pv("", True, False) == labels.NO_NATIONAL_FIGURE
    assert national_pv(" ", True, True) == labels.NO_NATIONAL_FIGURE
    assert national_pv("", False, True) == labels.NOT_APPLICABLE
