"""The one-election view, T2 and T3 (#307).

Offline, against recorded ``/v1/elections/{year}`` responses for 1824, 1860, 1868, 1872
and 2016 (one snapshot, ``v1_meta.json``'s), through the helpers and the autouse offline
process client of ``test_dashboard_app.py``. Its registry-wide checks pick this page up
from the registry (``TestRegistryCoverage``, ``TestValidateBeforeFill``,
``TestRegistryContracts`` and ``test_every_registered_page_is_found_at_the_index_and_
reads_nothing``), and the D070(b) guard renders it at 1824 as its fill on a miss. These
tests cover what is particular to this page.
"""

from __future__ import annotations

import copy
import urllib.parse
from typing import Any

import dash
import pytest
from dash import no_update

from explore import api, labels
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


def render(year: int, query: str = "", body: Any = None) -> Any:
    """The page body for ``year`` and ``query``, as the layout builds it."""
    body = year_body(year) if body is None else body
    return MOD["render"](body, index_row(year), MOD["parse_filters"](parse(query)))


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
    assert PAGE["on_miss"] == ("/v1/elections/{year}",)
    assert PAGE["success"] == PAGE_ID
    # The registered judge is the one the layout calls, so the index's 404 and the
    # page's not-found state decide alike.
    assert PAGE["validate"] is MOD["VALIDATE"]
    assert PAGE["validate"] == (api.ELECTIONS_PATH, MOD["served_year"])
    assert PAGE["query"] is MOD["parse_filters"]


@pytest.mark.parametrize("path", sorted(RECORDED))
def test_every_recorded_response_is_one_snapshot(path: str) -> None:
    """Every recorded response (``/v1/meta``, ``/v1/elections`` and each year) was
    recorded from one snapshot, the one ``v1_meta.json`` names."""
    body = RECORDED[path]
    provenance = (
        body["provenance"] if path == api.META_PATH else body["meta"]["provenance"]
    )
    assert provenance["snapshot_version"] == VERSION
    if path.startswith("/v1/elections/"):
        assert body["election"]["year"] == int(path.rsplit("/", 1)[1])


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
        for row in (*body["data"], *body["summary"]):
            row["year"] = 1825
        fetch, calls = fake_fetch(
            {**RECORDED, api.ELECTIONS_PATH: added, "/v1/elections/1825": body}
        )
        client = offline_client(fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH])
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        status, head, _ = get("/election/1825")
        assert (status, head.canonical) == (200, url("/election/1825"))
        assert PAGE_ID in routed_ids(route("/election/1825"))
        assert "/v1/elections/1825" in calls

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

        assert new_york(1800) == {
            "No popular-vote figure for this candidate in this state"
        }
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
        stay correct; the page shows none of the block, so it renders."""
        body = year_body(1872)
        body["election"] = None
        fetch, _ = fake_fetch({**RECORDED, "/v1/elections/1872": body})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        tree = PAGE["layout"](year="1872")
        assert PAGE_ID in component_ids(tree)
        assert len(table_rows(tree, STATES)) == 222

    def test_an_unformattable_share_renders_as_text_not_a_server_error(
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
        assert shares[0] == str(10**400)
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
            "party": "Party",
            "state_electoral_votes": "Electors appointed (state)",
            "electoral_votes": "Electoral votes cast",
            "electoral_votes_counted": "Electoral votes counted",
            "electoral_count_status": "Count status",
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
        }
        assert {k: labels.LABELS[k] for k in expected} == expected

    @pytest.mark.parametrize(
        ("table_id", "fields"),
        [(STATES, "STATE_FIELDS"), (NATION, "NATION_FIELDS")],
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

    def test_the_glossaries_name_every_column_and_the_count_reason(self) -> None:
        glossaries = of_type(render(1872), "Details")
        assert len(glossaries) == 2
        named = [[texts(dd.children)[0] for dd in of_type(g, "Dd")] for g in glossaries]
        assert named[0] == list(MOD["STATE_FIELDS"]) + ["electoral_count_status_reason"]
        assert named[1] == list(MOD["NATION_FIELDS"])

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
            (None, "mystery", 2016, "mystery"),  # text, never a claim
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
            "No popular-vote figure for this candidate in this state"
        )
        assert labels.NOT_IN_DATASET == "Not in this dataset"
        assert labels.PARTY_NOTE == (
            "Party comes from the popular-vote source, so it is recorded only where a "
            "popular-vote figure is."
        )
        assert labels.COUNT_STATUS == {
            "counted": ("Counted", None),
            "not_counted": ("Not counted", "Congress refused the votes"),
            "disputed": ("Disputed", "Congress never resolved the question"),
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
        for row in nation_rows(tree).values():
            assert row["national_pv_votes"] == labels.NOT_IN_DATASET
            assert row["pv_share"] == labels.NOT_IN_DATASET

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
        assert trump["party"] == "REPUBLICAN"

    def test_t3_reads_the_index_s_flag_and_the_coverage_years(self) -> None:
        """Doctored inputs, so a literal window in the page fails: the year-level
        decision comes from the index row, the sentence's years from coverage."""
        held = MOD["render"](
            year_body(1872), {**index_row(1872), "has_popular_vote": True}, []
        )
        assert find(held, MOD["NO_PV_ID"]) is None
        grant = nation_rows(held)["Ulysses S. Grant"]
        assert grant["national_pv_votes"] == "No popular-vote figure for this candidate"
        missing = MOD["render"](
            year_body(2016), {**index_row(2016), "has_popular_vote": False}, []
        )
        assert find(missing, MOD["NO_PV_ID"]) is not None
        trump = nation_rows(missing)["Donald J. Trump"]
        assert trump["national_pv_votes"] == trump["pv_share"] == "Not in this dataset"
        body = year_body(1860)
        body["meta"]["provenance"]["coverage"].update(
            pv_year_min=1900, pv_year_max=2000
        )
        note = find(render(1860, body=body), MOD["NO_PV_ID"])
        assert note.children == (
            "This dataset has no popular vote for 1860; its popular-vote figures cover "
            "1900–2000."
        )

    @pytest.mark.parametrize("flag", ["false", 1, None])
    def test_only_a_true_flag_claims_a_popular_vote(self, flag: Any) -> None:
        """A malformed index flag never makes T3 claim the year has a popular vote."""
        tree = MOD["render"](
            year_body(1872), {**index_row(1872), "has_popular_vote": flag}, []
        )
        assert find(tree, MOD["NO_PV_ID"]) is not None

    def test_the_index_s_flag_and_the_window_agree(self) -> None:
        """A check of the recorded data, not of the page: the index's flag and the
        coverage window name the same years, so T2 (window from coverage) and T3 (flag
        from the index) cannot disagree on this snapshot."""
        for row in INDEX["data"]:
            inside = PV_MIN <= row["year"] <= PV_MAX
            assert row["has_popular_vote"] is inside, row["year"]

    def test_a_null_party_says_so_with_its_reason(self) -> None:
        tree = render(1860)
        cells = [
            row[MOD["STATE_FIELDS"].index("party")] for row in table_rows(tree, STATES)
        ]
        cells += [
            row[MOD["NATION_FIELDS"].index("party")] for row in table_rows(tree, NATION)
        ]
        assert cells
        for cell in cells:
            assert cell.children == labels.NOT_IN_DATASET
            assert cell.title == labels.PARTY_NOTE
        notes = [p for p in of_type(tree, "P") if p.children == labels.PARTY_NOTE]
        assert len(notes) == 2  # under T2 and under T3
        # The page's party cells are what the shared cell builds (S4 reuses it).
        shared = labels.party_cell(None)
        assert (shared.children, getattr(shared, "title", None)) == (
            cells[0].children,
            cells[0].title,
        )
        assert labels.party_cell("WHIG").children == "WHIG"
        assert getattr(labels.party_cell("WHIG"), "title", None) is None

    @pytest.mark.parametrize(
        ("fn", "value", "shown"),
        [
            (labels.yes_no, True, "Yes"),
            (labels.yes_no, False, "No"),
            (labels.yes_no, None, "None"),
            (labels.yes_no, 1, "1"),
            (labels.share, 0.5, "50.0%"),
            (labels.share, True, "True"),
            (labels.share, "x", "x"),
            (labels.number, 1234567, "1,234,567"),
            (labels.number, False, "False"),
            (labels.party, None, labels.NOT_IN_DATASET),
            (labels.share, 10**400, str(10**400)),  # no float holds it
            (labels.share, float("inf"), "inf"),
            (labels.pv_status, "legislature_chosen", "State legislature chose"),
            (labels.pv_status, "mystery", "mystery"),
            (labels.pv_status, None, "None"),
        ],
    )
    def test_an_unexpected_value_renders_as_text(
        self, fn: Any, value: Any, shown: str
    ) -> None:
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
        assert labels.count_status("mystery", None) == ["mystery"]

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
    def test_opening_a_year_makes_at_most_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        assert PAGE_ID in routed_ids(route("/election/1872"))
        assert calls == ["/v1/elections/1872"]
        assert len(bucket.waits) == 1
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
        assert calls == [api.ELECTIONS_PATH, "/v1/elections/1872"]


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
