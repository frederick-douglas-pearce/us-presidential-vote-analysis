"""The election pages (#307, split by #465): the overview (the election panel with
T3's hybrid column, #308, chart C1, #433, and T3), the states page (T2 and its
filters) and the per-capita page (T6, every state's persons per electoral vote, #280,
and its state filter), their shared pieces in ``explore.election_view``.

Offline, against recorded ``/v1/elections/{year}`` responses for 1824, 1860, 1868, 1872,
2016 and 2024, and ``/v1/elections/{year}/per-capita`` for those years and 1848 and 1864
(one snapshot, ``v1_meta.json``'s), through the helpers and the autouse offline
process client of ``test_dashboard_app.py``. Their registry-wide checks pick these pages
up from the registry (``TestRegistryCoverage``, ``TestValidateBeforeFill``,
``TestRegistryContracts`` and ``test_every_registered_page_is_found_at_the_index_and_
reads_nothing``), and the D070(b) guard renders them at 1824, after the candidate
history's fills (``ELECTION_PAGE_MISSES``). These tests cover what is particular to
these pages.
"""

from __future__ import annotations

import copy
import re
import urllib.parse
from typing import Any

import dash
import pytest
from dash import no_update

from explore import api, components, election_view, export, labels
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
STATES_PAGE: dict[str, Any] = dash.page_registry["pages.election_states"]
PER_CAPITA_PAGE: dict[str, Any] = dash.page_registry["pages.election_per_capita"]
#: Each page module's namespace, reached through its layout (Dash loads it by path):
#: the overview, results by state and people per electoral vote (#465).
OV: dict[str, Any] = PAGE["layout"].__globals__
ST: dict[str, Any] = STATES_PAGE["layout"].__globals__
PC: dict[str, Any] = PER_CAPITA_PAGE["layout"].__globals__
#: The shared module and the three namespaces as one, for the names only one defines (a table's fields
#: and ids, a figure helper). A name two pages define (``PAGE_ID``, ``LEDE``,
#: ``render``) is read from the page it is about, never from here.
MOD: dict[str, Any] = {**vars(election_view), **PC, **ST, **OV}

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
    result: dict[str, Any] = election_view.index_row(index or INDEX, str(year))
    return result


def per_capita_body(year: int) -> dict[str, Any]:
    return copy.deepcopy(RECORDED[f"/v1/elections/{year}/per-capita"])


def render(year: int, query: str = "", body: Any = None, per_capita: Any = None) -> Any:
    """The three election pages' bodies for ``year`` and ``query`` (#465), as their
    layouts build them, side by side: the overview (the panel, C1, T3), the states page
    (T2 and its filters) and the per-capita page (T6 and its filter), each given the
    query as its own parser reads it. A table or the panel is on one page only, so
    ``find`` on the result finds it on its page; what a single page shows, or does not,
    is tested on :func:`render_page`."""
    return dash.html.Div(
        [render_page(page, year, query, body, per_capita) for page in (OV, ST, PC)]
    )


def render_page(
    page: dict[str, Any],
    year: int,
    query: str = "",
    body: Any = None,
    per_capita: Any = None,
) -> Any:
    """One election page's body (``OV``, ``ST`` or ``PC``), as its layout builds it."""
    body = year_body(year) if body is None else body
    per_capita = per_capita_body(year) if per_capita is None else per_capita
    around = election_view.neighbours(INDEX, year)
    if page is OV:
        return OV["render"](body, index_row(year), around)
    if page is ST:
        pairs = election_view.parse_filters(parse(query))
        return ST["render"](body, index_row(year), pairs, around)
    pairs = election_view.parse_state(parse(query))
    return PC["render"](per_capita, index_row(year), pairs, around)


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


#: The three election pages (#465): path template, fills on a miss, ``query=`` parser.
PAGES = {
    "pages.election": ("/election/<year>", ("/v1/elections/{year}",), None),
    "pages.election_states": (
        "/election/<year>/states",
        ("/v1/elections/{year}",),
        election_view.parse_filters,
    ),
    "pages.election_per_capita": (
        "/election/<year>/per-capita",
        ("/v1/elections/{year}/per-capita",),
        election_view.parse_state,
    ),
}


@pytest.mark.parametrize("module", list(PAGES))
def test_each_page_is_registered_as_planned(module: str) -> None:
    template, on_miss, parser = PAGES[module]
    page = dash.page_registry[module]
    mod = page["layout"].__globals__
    assert page["path_template"] == template
    assert page["prefetch"] == (api.ELECTIONS_PATH,)
    assert page["on_miss"] == on_miss  # one fill each (#465)
    assert page["success"] == mod["PAGE_ID"]
    # The registered judge is the one the layout calls, so the index's 404 and the
    # page's not-found state decide alike; all three judge by the overview's rule.
    assert page["validate"] is mod["VALIDATE"]
    assert page["validate"] == (api.ELECTIONS_PATH, election_view.served_year)
    assert page.get("query") is parser
    assert page["nav"] == "elections"
    assert page["not_found"] == OV["NOT_FOUND"]


def test_the_pages_success_markers_are_their_own_and_no_table_s() -> None:
    markers = [dash.page_registry[m]["success"] for m in PAGES]
    tables = {OV["NATION_TABLE_ID"], ST["STATES_TABLE_ID"], PC["PER_CAPITA_TABLE_ID"]}
    assert len(set(markers)) == 3
    assert not set(markers) & tables


def test_the_overview_moves_t2_s_keys_to_the_states_page() -> None:
    assert PAGE["moved"] == (election_view.STATES_KEYS, "/election/<year>/states")
    assert set(election_view.STATES_KEYS) == {
        "state",
        "candidate",
        "pv_status",
        "electoral_count_status",
    }


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
        # The overview reads no filter, so its og:url names no query (#465).
        status, head, _ = get("/election/1860?junk=1")
        assert status == 200
        assert head.canonical == url("/election/1860")
        assert head.og_url == url("/election/1860")
        for section, query, kept in (
            ("states", "state=SC&junk=1&year=1900", "?state=SC"),
            ("per-capita", "state=SC&candidate=abraham-lincoln&junk=1", "?state=SC"),
        ):
            status, head, _ = get(f"/election/1860/{section}?{query}")
            assert status == 200, section
            assert head.canonical == url(f"/election/1860/{section}"), section
            assert head.og_url == url(f"/election/1860/{section}{kept}"), section

    def test_the_page_says_the_dataset_has_no_election_that_year(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        response = route("/election/1825")
        ids = routed_ids(response)
        assert MOD["NOT_FOUND_ID"] in ids
        assert PAGE_ID not in ids
        body = response.get_data(as_text=True)
        assert labels.ELECTION_NOT_FOUND_SENTENCE in body
        assert (
            "1825" not in json_node(response.get_json(), MOD["NOT_FOUND_ID"]).__str__()
        )
        assert calls == []
        # The way back leads to the elections index.
        links = of_type(election_view.not_found(MOD["NOT_FOUND_ID"]), "Link")
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
        assert PC["PAGE_ID"] in routed_ids(route("/election/1825/per-capita"))
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
        for path, expected in (
            (f"/election/{year}", {PAGE_ID, NATION}),
            (f"/election/{year}/states", {ST["PAGE_ID"], STATES}),
        ):
            response = route(path)
            assert expected <= routed_ids(response), path
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
        assert [h.children for h in missing] == [
            labels.ELECTION_NOT_FOUND_HEADING
        ]  # #325

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
        assert len(table_rows(tree, NATION)) == len(body["summary"])
        assert len(table_rows(STATES_PAGE["layout"](year="1872"), STATES)) == 222
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
            # The election panel and T3's hybrid column (#308), approved 2026-10-08;
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
        # National results come before Results by state (owner, #433's plan gate).
        assert named[1] == list(MOD["NATION_FIELDS"]) + ["nominating_party_note"]
        assert named[2] == list(MOD["STATE_FIELDS"]) + [
            "electoral_count_status_reason",
            "nominating_party_note",
        ]
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
            # The electoral share is a value at every year, not a popular-vote cell.
            assert row["ec_share_full"].endswith("%"), (year, row)
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
        held = OV["render"](
            year_body(1872),
            {**index_row(1872), "has_popular_vote": True},
            election_view.neighbours(INDEX, 1872),
        )
        assert find(held, MOD["NO_PV_ID"]) is None
        grant = nation_rows(held)["Ulysses S. Grant"]
        assert grant["national_pv_votes"] == labels.NO_NATIONAL_FIGURE
        missing = OV["render"](
            year_body(2016),
            {**index_row(2016), "has_popular_vote": False},
            election_view.neighbours(INDEX, 2016),
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
        tree = OV["render"](
            year_body(1872),
            {**index_row(1872), "has_popular_vote": flag},
            election_view.neighbours(INDEX, 1872),
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
            row(1872, "  ", "s", "S."),  # a blank name
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
            f"{labels.NOT_IN_DATASET}, 1872: S.",
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
        status, head, _ = get(f"/election/1872/states?{query}")
        assert status == 200
        assert head.og_url is not None
        reopened = urllib.parse.urlsplit(head.og_url)
        assert reopened.path == "/election/1872/states"
        original = route("/election/1872/states", f"?{query}" if query else "")
        again = route(reopened.path, f"?{reopened.query}" if reopened.query else "")
        assert ST["PAGE_ID"] in routed_ids(original)
        assert original.get_json() == again.get_json()

    def test_the_round_trip_check_sees_a_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        filtered = routed_states(route("/election/1872/states", f"?{SHARED[0]}"))
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
        og_url = appmod.resolve("/election/1872/states", query, None).og_url
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
    def test_each_election_page_makes_one_fill(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One fill per page (#465): the overview the year's rows, the states page none
        after it (one cold), the per-capita page its own table."""
        _, calls, bucket = cached_client(monkeypatch)
        assert PAGE_ID in routed_ids(route("/election/1872"))
        assert calls == ["/v1/elections/1872"]
        assert len(bucket.waits) == 1
        calls.clear()
        assert PAGE_ID in routed_ids(route("/election/1872"))  # cached: none
        assert ST["PAGE_ID"] in routed_ids(route("/election/1872/states"))
        assert calls == []
        assert PC["PAGE_ID"] in routed_ids(route("/election/1872/per-capita"))
        assert calls == ["/v1/elections/1872/per-capita"]

    @pytest.mark.parametrize(
        ("section", "fill"),
        [
            ("", "/v1/elections/1868"),
            ("/states", "/v1/elections/1868"),
            ("/per-capita", "/v1/elections/1868/per-capita"),
        ],
    )
    def test_each_page_opened_cold_makes_one_fill(
        self, monkeypatch: pytest.MonkeyPatch, section: str, fill: str
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        route(f"/election/1868{section}")
        assert calls == [fill]
        assert len(bucket.waits) == 1

    def test_filter_changes_make_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        route("/election/1872/states")
        calls.clear()
        for search in ("?state=GA", "?electoral_count_status=not_counted", ""):
            assert ST["PAGE_ID"] in routed_ids(route("/election/1872/states", search))
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

    @pytest.mark.parametrize("section", election_view.SECTIONS)
    def test_a_middle_year_links_both_ways_unfiltered(self, section: str) -> None:
        """On every election page, to the same page of the neighboring years (#465)."""
        page = {"": OV, "/states": ST, "/per-capita": PC}[section]
        tree = render_page(page, 1868, "state=GA&candidate=ulysses-s-grant")
        assert nav_links(tree) == [
            (
                MOD["EARLIER_ID"],
                f"/election/1864{section}",
                "Earlier: the 1864 election",
            ),
            (MOD["LATER_ID"], f"/election/1872{section}", "Later: the 1872 election"),
        ]
        nav = find(tree, MOD["NAV_ID"])
        assert getattr(nav, "aria-label") == (
            labels.ELECTION_NAV_LABEL
            if not section
            else labels.ELECTION_NAV_SECTION_LABEL.format(
                section=election_view.SECTION_TEXT[section]
            )
        )
        # A client-side navigation, never a full page load.
        assert not any(getattr(link, "refresh", False) for link in of_type(nav, "Link"))

    def test_the_nav_comes_before_the_panel(self) -> None:
        ids = [getattr(child, "id", None) for child in render_page(OV, 1868).children]
        assert ids.index(MOD["NAV_ID"]) < ids.index(MOD["PANEL_ID"])

    def test_the_first_and_last_years_link_one_way(self) -> None:
        assert [i for i, _, _ in nav_links(render(YEARS[0]))] == [MOD["LATER_ID"]]
        assert [i for i, _, _ in nav_links(render(YEARS[-1]))] == [MOD["EARLIER_ID"]]

    def test_with_no_neighbour_there_is_no_landmark(self) -> None:
        none = election_view.Neighbours(None, None)
        for tree, marker in (
            (OV["render"](year_body(1872), index_row(1872), none), PAGE_ID),
            (ST["render"](year_body(1872), index_row(1872), [], none), ST["PAGE_ID"]),
            (
                PC["render"](per_capita_body(1872), index_row(1872), [], none),
                PC["PAGE_ID"],
            ),
        ):
            assert find(tree, MOD["NAV_ID"]) is None
            assert tree.id == marker

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
        """AC3 as amended at the plan gate: the target year's own fills on a miss (one
        per page since #465), and none of the link's own."""
        _, calls, _ = cached_client(monkeypatch)
        response = route("/election/1868")
        assert calls == ["/v1/elections/1868"]
        calls.clear()
        later = routed_hrefs(response)[MOD["LATER_ID"]]
        assert PAGE_ID in routed_ids(route(later))
        assert calls == ["/v1/elections/1872"]
        calls.clear()
        response = route("/election/1868/per-capita")
        later = routed_hrefs(response)[MOD["LATER_ID"]]
        assert later == "/election/1872/per-capita"
        calls.clear()
        assert PC["PAGE_ID"] in routed_ids(route(later))
        assert calls == ["/v1/elections/1872/per-capita"]

    def test_no_nav_and_no_filter_sentence_where_the_page_has_no_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        # The overview has no filters, so its lede has no filter sentence (#465).
        assert lede(OV["layout"](year="1872")) == OV["LEDE"]
        found = ST["layout"](year="1872")
        assert find(found, MOD["NAV_ID"]) is not None
        assert lede(found) == f"{ST['LEDE']} {ST['FILTER_SENTENCE']}"
        not_found = ST["layout"](year="1825")
        assert find(not_found, ST["NOT_FOUND_ID"]) is not None
        assert find(not_found, MOD["NAV_ID"]) is None
        # No lede at all: it describes a page that is not there (#325).
        assert not [
            p for p in of_type(not_found, "P") if getattr(p, "className", None) == "lede"
        ]

        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        degraded = ST["layout"](year="1872")
        assert components.UNAVAILABLE_MESSAGE in texts(degraded)
        assert find(degraded, MOD["NAV_ID"]) is None
        assert lede(degraded) == ST["LEDE"]

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
        degraded = PC["layout"](year="1872")
        assert components.UNAVAILABLE_MESSAGE in texts(degraded)
        assert find(degraded, MOD["NAV_ID"]) is None
        assert lede(degraded) == PC["LEDE"]


class TestNeighborBar:
    """#464: the earlier and later links sit in a bar above the heading, each on its
    own side, drawn by classes ``style.css`` styles (its rules are
    ``test_dashboard_theme.py``'s; the browser measures are the e2e suite's)."""

    def test_on_success_the_links_come_first_then_the_heading_then_the_lede(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        body = OV["layout"](year="1868")
        assert body.id == PAGE_ID
        kinds = [type(child).__name__ for child in body.children]
        # The links, the heading, the lede, then the section links (#465).
        assert kinds[:4] == ["Nav", "H1", "P", "Nav"]
        nav, heading, lede_, sections = body.children[:4]
        assert nav.id == MOD["NAV_ID"]
        assert heading.children == "The 1868 election"
        assert lede_.className == "lede"
        assert lede_.children == OV["LEDE"]
        assert sections.id == election_view.SECTIONS_ID
        ids = [getattr(child, "id", None) for child in body.children]
        assert ids.index(MOD["NAV_ID"]) < ids.index(MOD["PANEL_ID"])
        assert [h.children for h in of_type(body, "H1")] == ["The 1868 election"]
        for page, heading_text in (
            (ST, "The 1868 election: results by state"),
            (PC, "The 1868 election: people per electoral vote"),
        ):
            body = page["layout"](year="1868")
            kinds = [type(child).__name__ for child in body.children]
            # The page-local Location renders nothing; the bar is the first shown.
            assert kinds[:5] == ["Location", "Nav", "H1", "P", "Nav"], heading_text
            assert body.children[2].children == heading_text
            assert body.children[3].children == (
                f"{page['LEDE']} {page['FILTER_SENTENCE']}"
            )
            assert [h.children for h in of_type(body, "H1")] == [heading_text]

    def test_the_states_with_no_links_keep_the_heading_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        not_found = MOD["layout"](year="1825")
        assert type(not_found.children[0]).__name__ == "H1"
        assert not_found.children[0].children == labels.ELECTION_NOT_FOUND_HEADING

        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        degraded = MOD["layout"](year="1868")
        assert type(degraded.children[0]).__name__ == "H1"
        assert len(of_type(degraded, "H1")) == 1
        assert find(degraded, MOD["NAV_ID"]) is None

    @pytest.mark.parametrize(
        ("page", "heading"),
        [(OV, "HEADING"), (ST, "STATES_HEADING"), (PC, "PER_CAPITA_HEADING")],
    )
    def test_the_heading_and_the_tab_share_one_wording(
        self, page: dict[str, Any], heading: str
    ) -> None:
        text = page[heading].format(year=1868)
        assert text.startswith("The 1868 election")
        assert page["title"]("1868").startswith(text + " — ")
        (h1,) = of_type(render_page(page, 1868), "H1")
        assert h1.children == text

    @pytest.mark.parametrize("which", ["both", "first", "last"])
    def test_each_link_carries_its_side_and_its_text_alone(self, which: str) -> None:
        # 1868 is a recorded year with a served year on each side.
        year = {"both": 1868, "first": YEARS[0], "last": YEARS[-1]}[which]
        tree = render_page(OV, year)
        nav = find(tree, MOD["NAV_ID"])
        assert nav.className == MOD["NEIGHBOR_NAV_CLASS"]
        sides = {
            MOD["EARLIER_ID"]: MOD["NEIGHBOR_EARLIER_CLASS"],
            MOD["LATER_ID"]: MOD["NEIGHBOR_LATER_CLASS"],
        }
        expected = {
            "both": [MOD["EARLIER_ID"], MOD["LATER_ID"]],
            "first": [MOD["LATER_ID"]],
            "last": [MOD["EARLIER_ID"]],
        }[which]
        links = of_type(nav, "Link")
        assert [link.id for link in links] == expected
        earlier, later = MOD["neighbours"](INDEX, year)
        texts_by_id = {
            MOD["EARLIER_ID"]: labels.EARLIER_LINK.format(year=earlier),
            MOD["LATER_ID"]: labels.LATER_LINK.format(year=later),
        }
        for link in links:
            assert link.className == sides[link.id]
            # The chevrons are drawn by the stylesheet: no arrow in the link's text.
            assert link.children == texts_by_id[link.id]


class TestSectionLinks:
    """#465: each election page links the year's other two, in page order, the page
    being read marked as current by text, not a link, and only on success."""

    @pytest.mark.parametrize("section", election_view.SECTIONS)
    def test_the_three_pages_in_order_the_current_one_marked(
        self, section: str
    ) -> None:
        page = {"": OV, "/states": ST, "/per-capita": PC}[section]
        tree = render_page(page, 1868, "state=GA&candidate=ulysses-s-grant")
        nav = find(tree, election_view.SECTIONS_ID)
        assert type(nav).__name__ == "Nav"
        assert getattr(nav, "aria-label") == labels.ELECTION_SECTIONS_LABEL
        assert [texts(entry) for entry in nav.children] == [
            [labels.SECTION_OVERVIEW],
            [labels.SECTION_STATES],
            [labels.SECTION_PER_CAPITA],
        ]
        for entry, target in zip(nav.children, election_view.SECTIONS, strict=True):
            if target == section:
                # Announced as current, and no link to itself.
                assert type(entry).__name__ == "Span"
                assert getattr(entry, "aria-current") == "page"
            else:
                # A client-side link to the other page, unfiltered.
                assert type(entry).__name__ == "Link"
                assert entry.href == f"/election/1868{target}"
                assert not getattr(entry, "refresh", False)
                assert "aria-current" not in entry.to_plotly_json()["props"]

    def test_the_landmark_s_name_is_its_own(self) -> None:
        names = {
            labels.SITE_NAV_LABEL,
            labels.ELECTION_NAV_LABEL,
            *(
                labels.ELECTION_NAV_SECTION_LABEL.format(section=text)
                for text in (labels.SECTION_STATES, labels.SECTION_PER_CAPITA)
            ),
        }
        assert labels.ELECTION_SECTIONS_LABEL not in names
        assert len(names) == 4

    @pytest.mark.parametrize("page", [OV, ST, PC], ids=["overview", "states", "pc"])
    def test_success_only(
        self, monkeypatch: pytest.MonkeyPatch, page: dict[str, Any]
    ) -> None:
        cached_client(monkeypatch)
        assert find(page["layout"](year="1868"), election_view.SECTIONS_ID) is not None
        assert find(page["layout"](year="1825"), election_view.SECTIONS_ID) is None

        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        assert find(page["layout"](year="1868"), election_view.SECTIONS_ID) is None

    def test_after_the_lede_before_the_page_s_content(self) -> None:
        for page, first_after in ((OV, OV["PANEL_ID"]), (PC, PC["STATE_ID"])):
            order = ids_in_order(render_page(page, 1868))
            assert order.index(election_view.SECTIONS_ID) < order.index(first_after)


# --- the title ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "named"),
    [
        ("1872", True),
        ("1825", True),  # the page's own title: app.py calls it only once accepted
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
    # The page's own title; the registry's is app.py's wrapper (#325, D083).
    for page in (OV, ST, PC):
        title = page["title"](year=year)
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


def section(year: int, body: Any = None, state: str | None = None) -> Any:
    """T6's page (#465), built from the per-capita response and the index only (so it
    also serves 1848 and 1864, whose ``/v1/elections/{year}`` is not recorded), with
    the state filter ``state``."""
    body = per_capita_body(year) if body is None else body
    pairs = election_view.parse_state({"state": state} if state else {})
    around = election_view.neighbours(INDEX, year)
    return PC["render"](body, index_row(year), pairs, around)


def lede_text(tree: Any) -> str:
    (found,) = [
        p for p in of_type(tree, "P") if getattr(p, "className", None) == "lede"
    ]
    text: str = found.children
    return text


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

    def test_t6_s_state_is_checked_against_t6_s_own_rows(self) -> None:
        """#465, amending #280: a state T6's own rows lack falls back to every state T6
        has, never an empty table. The other direction, that the page reads no T2 rows
        to resolve it, is a read, pinned by ``READS_BEFORE`` (``test_dashboard_export.py``)
        and ``test_the_routed_page_shows_t6_and_reads_its_own_path``."""
        per_capita = per_capita_body(1872)
        per_capita["data"] = [r for r in per_capita["data"] if r["state_usps"] != "GA"]
        tree = render_page(PC, 1872, "state=GA", per_capita=per_capita)
        assert len(per_capita_rows(tree)) == len(per_capita["data"])
        assert "No rows match these filters." not in texts(tree)
        control = find(tree, PC["STATE_ID"])
        assert control.value is None
        assert "GA" not in {o["value"] for o in control.options}
        # A state T6 names narrows it to that state.
        assert list(per_capita_rows(render_page(PC, 1872, "state=GA"))) == ["Georgia"]

    @pytest.mark.parametrize(
        "search",
        ["candidate=horace-greeley", "pv_status=legislature_chosen",
         "electoral_count_status=not_counted"],
    )
    def test_the_other_filters_do_not_narrow_t6(self, search: str) -> None:
        tree = render(1872, search)
        assert len(per_capita_rows(tree)) == len(per_capita_body(1872)["data"])

    def test_t6_says_which_filter_applies_and_counts_its_rows(self) -> None:
        tree = render_page(PC, 1872, "state=GA")
        total = len(per_capita_body(1872)["data"])
        # One filter, its own (#465): no note says which filters apply.
        assert "PER_CAPITA_FILTER_NOTE" not in PC
        assert f"Showing 1 of {total} rows" in texts(tree)
        assert lede_text(tree) == f"{PC['LEDE']} {PC['FILTER_SENTENCE']}"


class TestPerCapitaCallback:
    """#465: the per-capita page's own filter callback, on its own ids (Dash keys
    callbacks by output app-wide), as the states page's is tested in
    ``TestShareableUrl``."""

    def test_the_callback_is_wired_to_the_page_s_own_location(self) -> None:
        graph = appmod.server.test_client().get("/_dash-dependencies").get_json()
        entries = [c for c in graph if c["output"] == f"{PC['URL_ID']}.search"]
        assert len(entries) == 1
        assert entries[0]["inputs"] == [{"id": PC["STATE_ID"], "property": "value"}]
        assert entries[0]["state"] == [{"id": PC["URL_ID"], "property": "search"}]
        assert entries[0]["prevent_initial_call"] is True
        assert {PC["URL_ID"], PC["STATE_ID"]}.isdisjoint({ST["URL_ID"], ST["STATE_ID"]})
        location = find(render_page(PC, 1872), PC["URL_ID"])
        assert location.refresh == "callback-nav"

    def test_the_callback_leaves_an_unchanged_url_alone(self) -> None:
        callback = PC["on_filter_change"]
        assert callback("GA", "") == "?state=GA"
        assert callback("GA", "?state=GA") is no_update
        assert callback(None, None) is no_update
        assert callback(None, "?state=GA") == ""
        # Syntactically bad values are dropped.
        assert callback("ga", "?state=GA") == ""
        assert callback(["GA"], "?state=GA") == ""

    @pytest.mark.parametrize(
        "query", ["state=GA", "state=GA&candidate=horace-greeley", "state=ZZ", ""]
    )
    def test_the_callback_writes_the_og_url_s_query_byte_for_byte(
        self, query: str
    ) -> None:
        value = find(render_page(PC, 1872, query), PC["STATE_ID"]).value
        written = PC["search_for"](value)
        og_url = appmod.resolve("/election/1872/per-capita", query, None).og_url
        assert og_url is not None
        expected = urllib.parse.urlsplit(og_url).query
        if query == "state=ZZ":
            # og:url keeps a state T6 lacks; the control cannot. Both open every state.
            assert (written, expected) == ("", "state=ZZ")
        else:
            assert written == (f"?{expected}" if expected else "")

    def test_the_callback_reads_no_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class NoView:
            def view(self) -> Any:
                raise AssertionError("the filter callback read the API")

        monkeypatch.setattr(api, "CLIENT", NoView())
        assert PC["on_filter_change"]("GA", "") == "?state=GA"


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
        ids = routed_ids(route("/election/1872/per-capita"))
        assert "unavailable" in ids
        assert PC["PAGE_ID"] not in ids
        # The overview reads no per-capita table, so it still renders (#465).
        assert PAGE_ID in routed_ids(route("/election/1872"))

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
        ids = routed_ids(route("/election/1872/per-capita"))
        assert "unavailable" in ids
        assert PC["PAGE_ID"] not in ids and PER_CAPITA not in ids
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
    ids = routed_ids(route("/election/1868/per-capita"))
    assert {PC["PAGE_ID"], PER_CAPITA} <= ids
    assert calls == ["/v1/elections/1868/per-capita"]  # never the year's own rows


def test_the_footer_names_the_census_bureau_and_its_license() -> None:
    provenance = per_capita_body(1872)["meta"]["provenance"]
    footer = of_type(render_page(PC, 1872), "Footer")
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


# --- the election panel and T3's hybrid column (#308) ---------------------------------

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
        order = ids_in_order(render_page(OV, 2016))
        # The success marker, the earlier and later links (#324), the section links
        # (#465), then the panel, ahead of every table.
        assert order[:5] == [
            PAGE_ID,
            MOD["NAV_ID"],
            MOD["EARLIER_ID"],
            MOD["LATER_ID"],
            election_view.SECTIONS_ID,
        ]
        assert order[5] == PANEL
        # National results: C1, then T3 (owner, #433). T2 and T6 are pages of their
        # own since #465.
        assert order.index(PANEL) < order.index("c1") < order.index(NATION)
        assert STATES not in order
        assert MOD["PER_CAPITA_TABLE_ID"] not in order

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
        tree = render_page(OV, 2016)
        assert labels.HYBRID_NOTE in texts(find(tree, PANEL))
        assert texts(tree).count(labels.HYBRID_NOTE) == 2
        # The second is T3's: after its table, before the footer.
        order = texts(tree)
        under_t3 = len(order) - 1 - order[::-1].index(labels.HYBRID_NOTE)
        last_t3_cell = texts(find(tree, NATION))[-1]
        assert under_t3 > order.index(last_t3_cell)
        footer = texts(of_type(tree, "Footer")[0])
        assert under_t3 < order.index(footer[0])

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

    def test_the_approved_notes_are_pinned(self) -> None:
        """Approved by the owner: ``MARGIN_NOTE`` in place on the #352 branch deploy
        (2026-10-12), ``UNRECOGNIZED_NOTE`` at #354's plan gate (2026-10-15). Pinned as
        shipped, so a reword is a deliberate change here, and the panel's every fixed
        string stays pinned (``test_no_panel_text_calls_the_hybrid_better``)."""
        assert labels.MARGIN_NOTE == (
            "A margin is the gap, in percentage points, between the first- and "
            "second-place candidates under that method. Each method ranks the "
            "candidates on its own."
        )
        # Drafted with the glossary (#355); approved at #354's plan gate, 2026-10-15.
        assert labels.UNRECOGNIZED_NOTE == (
            "This dataset holds a value that this page has no label for."
        )

    def test_the_margin_note_shows_in_the_panel(self) -> None:
        panel_notes = [p.children for p in of_type(find(render(1872), PANEL), "P")]
        assert labels.MARGIN_NOTE in panel_notes

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
        assert rows["Andrew Jackson"]["ec_share_full"] == "37.9%"

    def test_2016_scores_and_a_candidate_with_no_figure(self) -> None:
        rows = nation_rows(render(2016))
        assert rows["Donald J. Trump"]["hybrid_score"] == "51.3%"
        assert rows["Hillary Clinton"]["hybrid_score"] == "45.2%"
        assert rows["Hillary Clinton"]["ec_share_full"] == "42.2%"
        assert rows["Colin Powell"]["hybrid_score"] == labels.NO_NATIONAL_FIGURE

    @pytest.mark.parametrize("year", PANEL_YEARS)
    def test_every_hybrid_cell_is_labeled(self, year: int) -> None:
        for row in nation_rows(render(year)).values():
            assert row["hybrid_score"] not in ("", "None", "No", "0"), (year, row)

    def test_t3_reads_the_index_s_flag_for_the_hybrid_score(self) -> None:
        """Doctored index rows, so the score's year rule is T3's, not a literal."""
        missing = OV["render"](
            year_body(2016),
            {**index_row(2016), "has_popular_vote": False},
            election_view.neighbours(INDEX, 2016),
        )
        assert nation_rows(missing)["Donald J. Trump"]["hybrid_score"] == NOT_APPLICABLE
        held = OV["render"](
            year_body(1872),
            {**index_row(1872), "has_popular_vote": True},
            election_view.neighbours(INDEX, 1872),
        )
        grant = nation_rows(held)["Ulysses S. Grant"]
        assert grant["hybrid_score"] == labels.NO_NATIONAL_FIGURE

    def test_t3_shows_the_electoral_share_once(self) -> None:
        """#358: under the shipped coverage policy, (b) (D038), the hybrid's input share
        equals ``ec_share_full``, so T3 shows one electoral share and no note about a
        repeat. Pinned as a literal, since
        ``test_each_header_is_its_label_with_the_raw_field_name`` and
        ``test_the_glossaries_name_every_column_and_the_count_reason`` derive T3's headers
        and column-name list from ``NATION_FIELDS``."""
        assert MOD["NATION_FIELDS"] == (
            "candidate",
            "nominating_party",
            "national_electoral_votes",
            "national_electoral_votes_counted",
            "national_electoral_denominator",
            "electoral_rank",
            "took_office",
            "national_pv_votes",
            "ec_share_full",
            "pv_share",
            "hybrid_score",
        )
        tree = render(2016)
        titles = [h.title for h in of_type(find(tree, NATION), "Th")]
        assert "ec_share_hybrid" not in titles
        assert {"ec_share_full", "hybrid_score"} <= set(titles)
        shown = " ".join(texts(tree))
        assert "Electoral share in the hybrid" not in shown
        assert "electoral share repeats it" not in shown
        # Non-vacuity: the scan reads the page's headers and notes.
        assert labels.LABELS["ec_share_full"] in shown
        assert labels.HYBRID_NOTE in shown

    def test_t3_never_reads_the_served_hybrid_share(self) -> None:
        """A served ``ec_share_hybrid`` that differed would still not reach T3. T3 shows
        ``ec_share_full`` beside ``hybrid_score`` under ``labels.HYBRID_NOTE``, which is
        true only while the two shares are equal: the shipped policy, (b), checked on the
        build side by ``test_the_two_ec_shares_are_equal_under_the_shipped_policy``
        (``test_snapshot.py``). Shipping policy (c) must revisit T3 (D084)."""
        body = year_body(2016)
        first = body["summary"][0]
        first["ec_share_hybrid"] = 0.999
        row = nation_rows(render(2016, body=body))[first["candidate"]]
        assert "99.9%" not in row.values()
        assert row["ec_share_full"] == labels.share(first["ec_share_full"])


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


# --- chart C1 (#433) -------------------------------------------------------------------

C1 = "c1"
RECONCILED_YEARS = (1824, 1860, 1872, 2016, 2024)
#: The hover templates as shipped, copied at import, so a test that patches the page's
#: template sees the reconciliation compare against the approved one.
EC_HOVER, PV_HOVER = labels.C1_EC_HOVER, labels.C1_PV_HOVER


def c1(tree: Any) -> Any:
    """The rendered C1: its ``figure`` element, or ``None``."""
    return find(tree, C1)


def c1_figure(tree: Any) -> dict[str, Any]:
    """The figure C1's source store holds (the title is the page text above it)."""
    (store,) = of_type(c1(tree), "Store")
    figure: dict[str, Any] = store.data
    return figure


def c1_caption(tree: Any) -> str:
    (caption,) = of_type(c1(tree), "Figcaption")
    return "".join(texts(caption.children))


def traces(figure: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """C1's traces by role: ``ec`` and ``pv`` bars, and ``marks``."""
    found: dict[str, dict[str, Any]] = {}
    for trace in figure["data"]:
        if trace["type"] == "scatter":
            found["marks"] = trace
        else:
            found[{"ec_share_full": "ec", "pv_share": "pv"}[trace["offsetgroup"]]] = (
                trace
            )
    return found


def t3_cells(year: int, body: Any = None) -> list[dict[str, str]]:
    """T3's cell text per row, in T3's order, with each row's slug."""
    tree = render(year, body=body)
    fields = MOD["NATION_FIELDS"]
    rows = []
    summary = (year_body(year) if body is None else body)["summary"]
    for row, cells in zip(summary, table_rows(tree, NATION), strict=True):
        texts_ = dict(zip(fields, (cell_text(c) for c in cells), strict=True))
        rows.append({**texts_, "slug": row["candidate_slug"]})
    return rows


class TestC1:
    def test_registered_with_t3_as_its_companion(self) -> None:
        from explore import charts

        assert charts.CHARTS["C1"] == charts.Chart("/election/<year>", NATION)
        assert MOD["C1_ID"] == "C1"

    @pytest.mark.parametrize("year", RECONCILED_YEARS)
    def test_inside_the_success_marker_in_national_results_before_t3(
        self, year: int
    ) -> None:
        tree = render_page(OV, year)
        assert tree.id == PAGE_ID
        order = ids_in_order(tree)
        assert order.index(PANEL) < order.index(C1) < order.index(NATION)
        # The overview's last section: T2 and T6 are pages of their own (#465).
        headings = [h.children for h in of_type(tree, "H2")]
        assert headings[-2:] == ["National results", "Where the data comes from"]
        # The chart comes after its section's heading and before T3's own pieces.
        section = tree.children
        h2 = next(
            i
            for i, child in enumerate(section)
            if getattr(child, "children", None) == "National results"
        )
        chart = next(i for i, child in enumerate(section) if child is c1(tree))
        assert h2 < chart
        assert type(c1(tree)).__name__ == "Figure"
        # Never the success marker (#432): the chart holds no page id.
        assert PAGE_ID not in ids_in_order(c1(tree))

    def test_never_on_the_not_found_or_degraded_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = route("/election/1825")
        assert MOD["NOT_FOUND_ID"] in routed_ids(response)
        assert json_node(response.get_json(), C1) is None
        assert C1 in routed_ids(route("/election/2016"))  # the control

        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        degraded = MOD["layout"](year="2016")
        assert components.UNAVAILABLE_MESSAGE in texts(degraded)
        assert c1(degraded) is None

    @pytest.mark.parametrize("year", RECONCILED_YEARS)
    def test_every_plotted_value_is_t3_s_cell_for_the_same_slug(self, year: int) -> None:
        """AC Reconciliation, keyed by slug through each trace's ``ids``: every series
        slot of every T3 row is exactly one bar or exactly one marker. A bar is the
        served value (the chart computes no share) and is drawn exactly where T3's cell
        is a share; its text is that cell and its hover the template filled with T3's
        cells. A marker stands exactly where the cell is not a share, labeled and
        hovered from that cell."""
        tree = render(year)
        found = traces(c1_figure(tree))
        t3 = {row["slug"]: row for row in t3_cells(year)}
        summary = {r["candidate_slug"]: r for r in year_body(year)["summary"]}
        figure = c1_figure(tree)
        assert figure["layout"]["yaxis"]["ticktext"] == [
            r["candidate"] for r in t3.values()
        ]
        marks = found.get("marks", {"ids": [], "text": [], "hovertext": []})
        assert len(set(marks["ids"])) == len(marks["ids"])
        series = [("ec", "ec_share_full")]
        if "pv" in found:
            series.append(("pv", "pv_share"))
        slots = 0
        for role, field in series:
            trace = found[role]
            assert trace["ids"] == list(t3)  # T3's rows, in T3's order
            assert trace["y"] == list(range(len(t3)))
            for i, slug in enumerate(trace["ids"]):
                served, cell, row = summary[slug][field], t3[slug][field], t3[slug]
                is_share = cell != labels.UNRECOGNIZED and cell == labels.share(served)
                x, mark = trace["x"][i], f"{slug}/{field}"
                assert (x is not None) is is_share, (slug, field, cell)
                assert (mark in marks["ids"]) is not is_share, (slug, field)
                slots += 1
                if is_share:
                    assert x == served and type(x) is type(served)
                    assert trace["text"][i] == cell
                    expected = (
                        EC_HOVER.format(
                            candidate=row["candidate"],
                            share=cell,
                            counted=row["national_electoral_votes_counted"],
                            appointed=row["national_electoral_denominator"],
                        )
                        if field == "ec_share_full"
                        else PV_HOVER.format(
                            candidate=row["candidate"],
                            share=cell,
                            votes=row["national_pv_votes"],
                        )
                    )
                    assert trace["hovertext"][i] == expected
                    continue
                assert trace["text"][i] == ""
                k = marks["ids"].index(mark)
                if cell == labels.NO_NATIONAL_FIGURE:
                    label, shown = labels.C1_NO_FIGURE, cell
                elif cell == labels.NOT_IN_DATASET:
                    label, shown = labels.C1_NO_SHARE, f"{labels.LABELS[field]}: {cell}"
                else:
                    label, shown = cell, f"{cell}<br>{labels.UNRECOGNIZED_NOTE}"
                assert marks["text"][k] == label
                assert marks["hovertext"][k] == labels.C1_NO_FIGURE_HOVER.format(
                    candidate=row["candidate"], cell=shown
                )
        drawn = sum(x is not None for role, _ in series for x in found[role]["x"])
        assert drawn + len(marks["ids"]) == slots == len(t3) * len(series)

    def test_the_reconciliation_fails_a_chart_that_draws_no_bar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuity (round 1): with ``_plotted`` drawing nothing, every share
        becomes a marker, and the reconciliation fails."""
        monkeypatch.setitem(OV, "_plotted", lambda value, cell: None)
        with pytest.raises(AssertionError):
            self.test_every_plotted_value_is_t3_s_cell_for_the_same_slug(2024)

    def test_the_reconciliation_fails_a_hover_with_the_wrong_votes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GE8's mutant: the "Popular votes" line filled with another cell."""
        monkeypatch.setattr(
            labels, "C1_PV_HOVER", PV_HOVER.replace("{votes}", "{counted}")
        )
        hover = traces(c1_figure(render(2024)))["pv"]["hovertext"][0]
        assert "Popular votes: 312" in hover  # the premise: the mutant took
        with pytest.raises(AssertionError):
            self.test_every_plotted_value_is_t3_s_cell_for_the_same_slug(2024)

    def test_the_popular_vote_window_comes_from_t3_s_year_rule(self) -> None:
        """AC Window: the popular-vote series only where T3 treats the year as having
        popular votes (the index row's flag), with the window from coverage."""
        for year, expected in (
            (1860, False),
            (1824, False),
            (2016, True),
            (2024, True),
        ):
            figure = c1_figure(render(year))
            assert ("pv" in traces(figure)) is expected, year
            assert index_row(year)["has_popular_vote"] is expected
        body = year_body(2016)
        tree = OV["render"](
            body,
            {**index_row(2016), "has_popular_vote": False},
            election_view.neighbours(INDEX, 2016),
        )
        assert "pv" not in traces(c1_figure(tree))

    def test_1860_says_why_no_popular_vote_share_is_drawn(self) -> None:
        tree = render(1860)
        caption = c1_caption(tree)
        assert (
            labels.C1_NO_PV_CAPTION.format(first=PV_MIN, last=PV_MAX, year=1860)
            in caption
        )
        assert labels.C1_EC_BASIS in caption
        assert labels.C1_MAJORITY_NOTE in caption
        assert labels.C1_ROW_ORDER not in caption
        assert caption.endswith(f"{labels.CHART_TABLE_POINTER}.")
        title = of_type(c1(tree), "P")[0].children
        assert title == labels.C1_TITLE_NO_PV.format(year=1860)
        figure = c1_figure(tree)
        assert "legend" not in figure["layout"]
        assert traces(figure)["ec"]["showlegend"] is False
        # The year sentence above T3 stays (owner, option (a)).
        assert find(tree, MOD["NO_PV_ID"]) is not None

    def test_the_window_in_the_caption_is_never_a_literal(self) -> None:
        body = year_body(1860)
        body["meta"]["provenance"]["coverage"].update(
            pv_year_min=1980, pv_year_max=2020
        )
        caption = c1_caption(render(1860, body=body))
        assert "1980–2020" in caption and f"{PV_MIN}–{PV_MAX}" not in caption

    def test_2016_draws_a_labeled_marker_for_each_missing_popular_vote_figure(
        self,
    ) -> None:
        """AC Missing figure: the five candidates with electoral votes and no
        popular-vote figure get a marker in the popular-vote slot, never a zero-length
        bar; Trump and Clinton get bars."""
        tree = render(2016)
        found = traces(c1_figure(tree))
        pv, marks = found["pv"], found["marks"]
        missing = [
            r["candidate_slug"]
            for r in year_body(2016)["summary"]
            if r["pv_share"] is None
        ]
        assert len(missing) == 5
        assert [i.split("/")[0] for i in marks["ids"]] == missing
        assert {i.split("/")[1] for i in marks["ids"]} == {"pv_share"}
        assert marks["text"] == [labels.C1_NO_FIGURE] * 5
        assert all(labels.NO_NATIONAL_FIGURE in h for h in marks["hovertext"])
        for slug in missing:
            assert pv["x"][pv["ids"].index(slug)] is None  # no bar at all, not a zero
        assert [x is not None for x in pv["x"]] == [True, True] + [False] * 5
        # Each marker sits in its row's popular-vote slot.
        slot = (1 - MOD["charts"].TEMPLATE["layout"]["bargap"]) / 4
        rows = [pv["ids"].index(s) for s in missing]
        assert marks["y"] == [row + slot for row in rows]
        assert marks["x"] == [0] * 5
        assert marks["showlegend"] is False
        assert marks["name"] == labels.C1_NO_FIGURE_SERIES
        assert labels.C1_NO_FIGURE_NOTE.format(label=labels.C1_NO_FIGURE) in (
            c1_caption(tree)
        )

    def test_2024_draws_no_marker_and_no_marker_note(self) -> None:
        tree = render(2024)
        assert "marks" not in traces(c1_figure(tree))
        caption = c1_caption(tree)
        assert labels.C1_NO_FIGURE not in caption
        for sentence in (
            labels.C1_BASES,
            labels.C1_MAJORITY_NOTE,
            labels.C1_LINE_EC_ONLY,
            labels.C1_ROW_ORDER,
        ):
            assert sentence in caption

    def test_1872_greeley_s_zero_is_a_drawn_labeled_bar(self) -> None:
        tree = render(1872)
        found = traces(c1_figure(tree))
        ec = found["ec"]
        i = ec["ids"].index("horace-greeley")
        assert ec["x"][i] == 0.0
        assert (
            ec["text"][i]
            == "0.0%"
            == nation_rows(tree)["Horace Greeley"]["ec_share_full"]
        )
        assert "marks" not in found  # a zero is a value, never a missing figure

    def test_1872_hover_says_the_share_is_counted_over_appointed(self) -> None:
        ec = traces(c1_figure(render(1872)))["ec"]
        grant = ec["hovertext"][ec["ids"].index("ulysses-s-grant")]
        assert "Electoral votes counted: 286" in grant
        assert "Electors appointed: 366" in grant
        assert "300" not in grant  # never the votes cast
        greeley = ec["hovertext"][ec["ids"].index("horace-greeley")]
        assert "Electoral votes counted: 0<br>" in greeley

    def test_the_dashed_majority_line_at_half_of_electors_appointed(self) -> None:
        tree = render(2016)
        layout = c1_figure(tree)["layout"]
        (line,) = layout["shapes"]
        assert (line["type"], line["xref"], line["x0"], line["x1"]) == (
            "line",
            "x",
            0.5,
            0.5,
        )
        assert line["line"]["dash"] == "dash"
        assert line["line"]["color"] == "var(--chart-reference)"
        assert layout["xaxis"]["range"] == [0, 1]
        (note,) = layout["annotations"]
        assert (note["text"], note["x"], note["xref"]) == (
            labels.C1_MAJORITY_LINE,
            0.5,
            "x",
        )
        assert labels.C1_MAJORITY_NOTE in c1_caption(tree)

    @pytest.mark.parametrize("year", [2016, 2024])
    def test_the_legend_names_both_series_in_a_popular_vote_year(
        self, year: int
    ) -> None:
        """Acceptance gate, Class B survivor: with every series hidden from the legend
        the figure still had a legend layout and passed. The legend must list exactly
        the two series, and never the marker series."""
        figure = c1_figure(render(year))
        shown = [t["name"] for t in figure["data"] if t.get("showlegend") is True]
        assert shown == [labels.LABELS["ec_share_full"], labels.LABELS["pv_share"]]
        assert "legend" in figure["layout"]

    def test_t2_s_filters_never_reach_the_chart(self) -> None:
        """AC Same rows as T3: like T3, C1 ignores T2's filters."""
        plain = c1_figure(render(2016))
        filtered = render(
            2016,
            "state=GA&candidate=donald-j-trump&pv_status=popular_vote"
            "&electoral_count_status=counted",
        )
        # The premise: the filters applied to T2.
        assert {r["state"] for r in state_rows(filtered)} == {"Georgia"}
        assert {r["candidate"] for r in state_rows(filtered)} == {"Donald J. Trump"}
        assert c1_figure(filtered) == plain
        assert c1_caption(filtered) == c1_caption(render(2016))

    def test_the_two_series_differ_without_color(self) -> None:
        from explore import charts

        figure = c1_figure(render(2016))
        found = traces(figure)
        assert found["ec"]["marker"].get("pattern") is None
        assert found["pv"]["marker"]["pattern"]["shape"] == "/"
        assert charts.color_only_pairs(figure) == []
        # Upper bar electoral: the first trace takes the row's upper slot on a
        # reversed axis, which the caption's row-order sentence states.
        assert figure["data"][0] is not None and figure["data"][0]["offsetgroup"] == (
            "ec_share_full"
        )
        assert figure["layout"]["yaxis"]["autorange"] == "reversed"
        assert figure["layout"]["legend"]["orientation"] == "h"

    def test_no_trace_sets_its_own_bar_width_or_offset(self) -> None:
        for year in RECONCILED_YEARS:
            for trace in c1_figure(render(year))["data"]:
                assert "width" not in trace and "offset" not in trace

    def test_an_unrecognized_share_gets_a_marker_never_a_bar(self) -> None:
        body = year_body(2016)
        body["summary"][0].update(pv_share="zz", ec_share_full=float("nan"))
        tree = render(2016, body=body)
        found = traces(c1_figure(tree))
        assert found["ec"]["x"][0] is None and found["pv"]["x"][0] is None
        marks = found["marks"]
        ours = [i for i, ident in enumerate(marks["ids"]) if ident.startswith("donald")]
        assert sorted(marks["ids"][i] for i in ours) == [
            "donald-j-trump/ec_share_full",
            "donald-j-trump/pv_share",
        ]
        slot = (1 - MOD["charts"].TEMPLATE["layout"]["bargap"]) / 4
        for i in ours:
            assert marks["text"][i] == labels.UNRECOGNIZED
            assert labels.UNRECOGNIZED_NOTE in marks["hovertext"][i]
            expected = -slot if marks["ids"][i].endswith("ec_share_full") else slot
            assert marks["y"][i] == expected
        assert nation_rows(tree)["Donald J. Trump"]["pv_share"] == labels.UNRECOGNIZED

    @pytest.mark.parametrize("blank", [None, " "])
    def test_a_null_electoral_share_is_a_marker_naming_its_series(
        self, blank: Any
    ) -> None:
        body = year_body(1860)
        body["summary"][0]["ec_share_full"] = blank
        tree = render(1860, body=body)
        marks = traces(c1_figure(tree))["marks"]
        assert marks["ids"] == ["abraham-lincoln/ec_share_full"]
        assert marks["text"] == [labels.C1_NO_SHARE]
        assert marks["hovertext"] == [
            "Abraham Lincoln<br>Electoral share (counted ÷ appointed): "
            + labels.NOT_IN_DATASET
        ]
        assert marks["y"] == [0.0]  # one series: the bar's slot is the row's center
        assert nation_rows(tree)["Abraham Lincoln"]["ec_share_full"] == (
            labels.NOT_IN_DATASET
        )
        # (1860 draws no popular vote, so no caption note can show here; the next test
        # checks a year that could show one.)

    def test_a_null_electoral_share_adds_no_caption_note_in_a_popular_vote_year(
        self,
    ) -> None:
        """Round 2: the addendum's "no caption sentence" for the C1_NO_SHARE marker,
        in a year whose caption could carry C1_NO_FIGURE_NOTE (2024 draws no popular-vote
        marker, so the note's presence could only come from this marker)."""
        body = year_body(2024)
        body["summary"][0]["ec_share_full"] = None
        tree = render(2024, body=body)
        marks = traces(c1_figure(tree))["marks"]
        assert marks["ids"] == ["donald-j-trump/ec_share_full"]
        assert marks["text"] == [labels.C1_NO_SHARE]
        assert marks["y"] == [-MOD["_SLOT"]]  # the electoral bar's slot, the upper one
        caption = c1_caption(tree)
        assert labels.C1_NO_FIGURE not in caption
        assert labels.C1_NO_FIGURE_NOTE.format(label=labels.C1_NO_FIGURE) not in caption
        assert caption.startswith(labels.C1_BASES)  # the premise: a popular-vote year

    def test_a_share_too_large_to_show_is_no_bar(self) -> None:
        body = year_body(2024)
        body["summary"][0]["ec_share_full"] = 1e308
        ec = traces(c1_figure(render(2024, body=body)))["ec"]
        assert ec["x"][0] is None

    def test_a_hostile_name_is_drawn_as_written(self) -> None:
        body = year_body(2016)
        body["summary"][0]["candidate"] = "<b>A & B</b>"
        for row in body["data"]:
            if row["candidate_slug"] == "donald-j-trump":
                row["candidate"] = "<b>A & B</b>"
        tree = render(2016, body=body)
        figure = c1_figure(tree)
        assert (
            figure["layout"]["yaxis"]["ticktext"][0] == "&lt;b&gt;A &amp; B&lt;/b&gt;"
        )
        ec = traces(figure)["ec"]
        assert ec["hovertext"][0].startswith("&lt;b&gt;A &amp; B&lt;/b&gt;<br>")

    @pytest.mark.parametrize(
        "name", ["var(--chart-1)", "var(--unset)", "x var(--page) y", "(a)"]
    )
    def test_a_name_spelling_a_token_reference_is_drawn_as_written(
        self, name: str
    ) -> None:
        """Round 1: a served name holding ``var(`` once made ``components.chart``
        refuse the figure and took the whole page down; since #467 (D095) it would only
        leave the chart not drawn, and the escape keeps it drawn. ``(`` is written as
        an entity, which plotly draws as ``(``."""
        body = year_body(2016)
        body["summary"][0]["candidate"] = name
        tree = render(2016, body=body)
        assert c1(tree) is not None and find(tree, NATION) is not None
        figure = c1_figure(tree)
        shown = figure["layout"]["yaxis"]["ticktext"][0]
        assert "(" not in shown and shown == name.replace("(", "&#40;")
        hover = traces(figure)["ec"]["hovertext"][0]
        assert hover.startswith(f"{shown}<br>") and "var(" not in hover

    def test_a_slug_spelling_a_token_reference_still_renders(self) -> None:
        body = year_body(2016)
        body["summary"][0]["candidate_slug"] = "var(--chart-1)"
        assert c1(render(2016, body=body)) is not None

    @pytest.mark.parametrize("name", [7, None, " "])
    def test_a_name_that_is_not_text_still_renders(self, name: Any) -> None:
        body = year_body(2024)
        body["summary"][0]["candidate"] = name
        tree = render(2024, body=body)
        assert c1(tree) is not None
        assert c1_figure(tree)["layout"]["yaxis"]["ticktext"][0] == str(name)

    def test_the_title_is_the_page_text(self) -> None:
        tree = render(2016)
        title = of_type(c1(tree), "P")[0]
        assert title.children == labels.C1_TITLE.format(year=2016)
        assert "title" not in c1_figure(tree)["layout"]  # the builder took it

    def test_the_height_follows_the_rows(self) -> None:
        heights = {
            year: c1_figure(render(year))["layout"]["height"] for year in (2016, 2024)
        }
        assert heights[2016] - heights[2024] == 5 * MOD["_ROW_PX"]

    def test_the_hover_templates_name_only_the_page_s_strings(self) -> None:
        from explore import charts

        for year in RECONCILED_YEARS:
            figure = c1_figure(render(year))
            assert charts.template_problems(figure) == []
            for trace in figure["data"]:
                assert trace["hovertemplate"] == "%{hovertext}<extra></extra>"

    def test_t3_and_c1_read_one_computation_of_the_cells(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Round 1: ``_nation_cells`` runs once per T3 row per render, and both T3 and
        C1 read its result."""
        calls: list[str] = []
        real = MOD["_nation_cells"]

        def counted(row: dict[str, Any], has_popular_vote: bool) -> dict[str, str]:
            calls.append(row["candidate_slug"])
            return {
                **real(row, has_popular_vote),
                "electoral_rank": "SENTINEL-RANK",
                "national_electoral_denominator": "SENTINEL-APPOINTED",
            }

        monkeypatch.setitem(OV, "_nation_cells", counted)
        tree = render(2024)
        summary = year_body(2024)["summary"]
        assert calls == [r["candidate_slug"] for r in summary]
        assert column(tree, NATION, MOD["NATION_FIELDS"], "electoral_rank") == [
            "SENTINEL-RANK"
        ] * len(summary)
        # C1 reads the same result: its hover carries the sentinel T3's cell shows.
        assert column(
            tree, NATION, MOD["NATION_FIELDS"], "national_electoral_denominator"
        ) == ["SENTINEL-APPOINTED"] * len(summary)
        for hover in traces(c1_figure(tree))["ec"]["hovertext"]:
            assert hover.endswith("Electors appointed: SENTINEL-APPOINTED")

    def test_t3_s_cells_are_unchanged_by_the_shared_helper(self) -> None:
        """T3 reads :func:`_nation_cells` too: its rows match the pre-C1 rules."""
        row = year_body(2016)["summary"][2]  # Colin Powell: no popular-vote figure
        cells = MOD["_nation_cells"](row, True)
        assert cells["pv_share"] == labels.NO_NATIONAL_FIGURE
        assert cells["ec_share_full"] == labels.share_cell(row["ec_share_full"])
        assert MOD["_nation_cells"](row, False)["pv_share"] == labels.NOT_APPLICABLE
        assert tuple(MOD["_nation_cells"](row, True)) == MOD["NATION_WORDED"]


# --- chart C3 (#435) ------------------------------------------------------------------

C3 = "c3"
C3_YEARS = (1848, 1864, 1868, 2016, 2024)


def c3(tree: Any) -> Any:
    """The rendered C3: its ``figure`` element, or ``None``."""
    return find(tree, C3)


def c3_figure(tree: Any) -> dict[str, Any]:
    (store,) = of_type(c3(tree), "Store")
    figure: dict[str, Any] = store.data
    return figure


def c3_caption(tree: Any) -> str:
    (caption,) = of_type(c3(tree), "Figcaption")
    return "".join(texts(caption.children))


def c3_title(tree: Any) -> str:
    (title,) = [p for p in of_type(c3(tree), "P") if p.className == "chart-title"]
    text: str = title.children
    return text


def c3_traces(figure: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """C3's traces by role: ``plain`` and ``striped`` bars, ``marks``, ``selected``."""
    found: dict[str, dict[str, Any]] = {}
    for trace in figure["data"]:
        if trace["type"] == "bar":
            striped = "pattern" in trace["marker"]
            found["striped" if striped else "plain"] = trace
        elif trace["name"] == labels.C3_SELECTED:
            found["selected"] = trace
        else:
            found["marks"] = trace
    return found


def t6_strings(year: int, body: Any = None) -> dict[str, dict[str, str]]:
    """T6's cell text per state, keyed by USPS code, from the unfiltered render."""
    tree = section(year, body)
    rows = (per_capita_body(year) if body is None else body)["data"]
    by_name = per_capita_rows(tree)
    return {r["state_usps"]: by_name[r["state"]] for r in rows}


def census_body(year: int) -> dict[str, Any]:
    """A per-capita body for ``year`` built from the recorded ``/v1/states/{GA,TX}/
    per-capita`` rows (doctored: no election body for 1924 or 1928 is recorded at the
    fixtures' snapshot, #435's plan gate)."""
    rows = []
    for usps in ("GA", "TX"):
        state = RECORDED[f"/v1/states/{usps}/per-capita"]
        rows += [copy.deepcopy(r) for r in state["data"] if r["year"] == year]
    assert len(rows) == 2, year
    return {**copy.deepcopy(per_capita_body(2016)), "data": rows}


class TestC3:
    def test_registered_with_t6_as_its_companion_at_fragment_c3(self) -> None:
        from explore import charts

        assert charts.CHARTS["C3"] == charts.Chart(
            "/election/<year>/per-capita", PER_CAPITA
        )
        assert PC["C3_ID"] == "C3"
        assert charts.dom_id("C3") == C3
        assert c3(section(2024)).id == C3

    @pytest.mark.parametrize("year", C3_YEARS)
    def test_after_the_section_links_and_before_the_state_control(
        self, year: int
    ) -> None:
        tree = section(year)
        order = ids_in_order(tree)
        assert (
            order.index("election-sections")
            < order.index(C3)
            < order.index(PC["STATE_ID"])
            < order.index(PER_CAPITA)
        )
        assert PC["PAGE_ID"] not in ids_in_order(c3(tree))

    def test_never_on_the_not_found_or_degraded_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        assert C3 in routed_ids(route("/election/2016/per-capita"))  # the control
        response = route("/election/1825/per-capita")
        assert PC["NOT_FOUND_ID"] in routed_ids(response)
        assert json_node(response.get_json(), C3) is None

        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        degraded = PC["layout"](year="2016")
        assert components.UNAVAILABLE_MESSAGE in texts(degraded)
        assert c3(degraded) is None

    @pytest.mark.parametrize("year", C3_YEARS)
    def test_every_state_once_drawn_by_ratio_then_the_rest_by_name(
        self, year: int
    ) -> None:
        """AC Every state: one row per served state and DC; drawn rows by the served
        ratio, most first (ties by name), then every row with no bar in T6's order."""
        rows = per_capita_body(year)["data"]
        figure = c3_figure(section(year))
        ticks = figure["layout"]["yaxis"]["ticktext"]
        assert sorted(ticks) == sorted(r["state"] for r in rows)
        assert len(ticks) == len(set(ticks)) == len(rows)
        drawn = sorted(
            (r for r in rows if isinstance(r["persons_per_electoral_vote"], float)),
            key=lambda r: (-r["persons_per_electoral_vote"], r["state"]),
        )
        rest = sorted(
            (r for r in rows if r not in drawn), key=lambda r: str(r["state"])
        )
        assert ticks == [r["state"] for r in drawn + rest]
        assert figure["layout"]["yaxis"]["tickvals"] == list(range(len(rows)))

    @pytest.mark.parametrize("year", C3_YEARS)
    def test_every_value_is_t6_s_cell_for_the_same_state(self, year: int) -> None:
        """AC Reconciliation: each state is exactly one bar or one marker. A bar is the
        served ratio (the chart computes nothing), its text T6's cell and its hover
        filled with T6's cells; a marker sits at zero in its row, its label looked up
        from T6's cell and T6's cell in full in its hover."""
        rows = {r["state_usps"]: r for r in per_capita_body(year)["data"]}
        t6 = t6_strings(year)
        figure = c3_figure(section(year))
        position = {
            name: i for i, name in enumerate(figure["layout"]["yaxis"]["ticktext"])
        }
        seen: list[str] = []
        for role, trace in c3_traces(figure).items():
            if role == "selected":
                continue
            for i, usps in enumerate(trace["ids"]):
                seen.append(usps)
                cell = t6[usps]
                assert trace["y"][i] == position[rows[usps]["state"]]
                if role == "marks":
                    assert trace["x"][i] == 0
                    ratio = cell["persons_per_electoral_vote"]
                    assert trace["text"][i] == labels.C3_MARKER_LABELS[ratio]
                    assert trace["hovertext"][i] == labels.C3_NO_FIGURE_HOVER.format(
                        state=rows[usps]["state"], cell=ratio
                    )
                else:
                    assert trace["x"][i] == rows[usps]["persons_per_electoral_vote"]
                    assert trace["text"][i] == cell["persons_per_electoral_vote"]
                    assert trace["hovertext"][i] == labels.C3_BAR_HOVER.format(
                        state=rows[usps]["state"],
                        ratio=cell["persons_per_electoral_vote"],
                        population=cell["population"],
                        electoral_votes=cell["state_electoral_votes"],
                        census_year=cell["governing_census_year"],
                        boundary=cell["boundary_basis"],
                    )
        assert sorted(seen) == sorted(rows)

    def test_1848_texas_shows_the_no_census_figure_marker(self) -> None:
        marks = c3_traces(c3_figure(section(1848)))["marks"]
        assert marks["ids"] == ["TX"]
        assert marks["text"] == [labels.C3_NO_CENSUS_FIGURE]
        assert NO_FIGURE in marks["hovertext"][0]

    def test_1864_each_zero_allotment_has_its_own_marker_never_a_bar(self) -> None:
        rows = per_capita_body(1864)["data"]
        zero = sorted(r["state_usps"] for r in rows if r["state_electoral_votes"] == 0)
        assert len(zero) == 11
        found = c3_traces(c3_figure(section(1864)))
        assert sorted(found["marks"]["ids"]) == zero
        assert set(found["marks"]["text"]) == {labels.C3_NO_ELECTORAL_VOTES}
        assert all(NO_VOTES in hover for hover in found["marks"]["hovertext"])
        for role in ("plain", "striped"):
            trace = found.get(role, {"ids": [], "x": []})
            assert not set(trace["ids"]) & set(zero)
            assert all(isinstance(x, float) and x > 0 for x in trace["x"])
        assert c3_caption(section(1864)).count(labels.C3_NO_FIGURE_NOTE) == 1

    def test_no_marker_and_no_marker_note_in_a_year_with_every_figure(self) -> None:
        tree = section(2024)
        assert "marks" not in c3_traces(c3_figure(tree))
        assert labels.C3_NO_FIGURE_NOTE not in c3_caption(tree)

    @pytest.mark.parametrize(
        ("year", "census"), [(2024, "2020"), (2016, "2010"), (1864, "1860")]
    )
    def test_the_title_names_the_census_used(self, year: int, census: str) -> None:
        assert c3_title(section(year)) == labels.C3_TITLE.format(
            year=year, census_year=census
        )

    @pytest.mark.parametrize("year", [1924, 1928])
    def test_1924_and_1928_read_the_1910_census(self, year: int) -> None:
        tree = section(year, census_body(year))
        assert c3_title(tree) == labels.C3_TITLE.format(year=year, census_year="1910")
        assert labels.C3_CENSUS in c3_caption(tree)

    def test_the_census_year_is_read_never_derived(self) -> None:
        body = copy.deepcopy(per_capita_body(2024))
        for row in body["data"]:
            row["governing_census_year"] = 1999
        assert c3_title(section(2024, body)) == labels.C3_TITLE.format(
            year=2024, census_year="1999"
        )

    @pytest.mark.parametrize("bad", [[1990, 2000], ["x", "x"]])
    def test_mixed_or_unrecognized_census_years_drop_the_year(
        self, bad: list[Any]
    ) -> None:
        body = copy.deepcopy(per_capita_body(2024))
        body["data"][0]["governing_census_year"] = bad[0]
        body["data"][1]["governing_census_year"] = bad[1]
        if bad[0] == "x":
            for row in body["data"]:
                row["governing_census_year"] = "x"
        tree = section(2024, body)
        assert c3_title(tree) == labels.C3_TITLE_NO_CENSUS.format(year=2024)
        caption = c3_caption(tree)
        assert labels.C3_CENSUS_MIXED in caption
        assert labels.C3_CENSUS not in caption

    @pytest.mark.parametrize("year", C3_YEARS)
    def test_present_day_bars_are_striped_and_split_on_t6_s_cell(
        self, year: int
    ) -> None:
        """AC Census and borders: a present-day row is striped (a pattern, a non-color
        channel), with T6's help text in the caption; one shared row slot."""
        t6 = t6_strings(year)
        found = c3_traces(c3_figure(section(year)))
        striped = set(found.get("striped", {"ids": []})["ids"])
        plain = set(found.get("plain", {"ids": []})["ids"])
        drawn = striped | plain
        assert striped == {
            u for u in drawn if t6[u]["boundary_basis"] == "Present-day borders"
        }
        for role in ("striped", "plain"):
            if role in found:
                assert found[role]["offsetgroup"] == "c3"
                assert found[role]["showlegend"] is True
        if striped:
            assert found["striped"]["marker"]["pattern"]["shape"] == "/"
            assert found["striped"]["name"] == labels.BOUNDARY_BASIS["present_day"]
            assert labels.C3_STRIPES + " " + labels.BOUNDARY_NOTE in c3_caption(
                section(year)
            )
        if plain:
            assert found["plain"]["name"] == labels.BOUNDARY_BASIS["at_election"]

    def test_a_year_on_present_day_borders_only_shows_one_legend_entry(self) -> None:
        found = c3_traces(c3_figure(section(2024)))
        assert set(found) == {"striped"}
        assert c3_figure(section(2024))["layout"]["showlegend"] is True

    def test_an_unrecognized_border_basis_is_drawn_plain_and_named_so(self) -> None:
        body = copy.deepcopy(per_capita_body(2024))
        body["data"][0]["boundary_basis"] = "sideways"
        tree = section(2024, body)
        found = c3_traces(c3_figure(tree))
        usps = body["data"][0]["state_usps"]
        assert found["plain"]["ids"] == [usps]
        assert found["plain"]["name"] == labels.C3_PLAIN_SERIES
        assert labels.UNRECOGNIZED in found["plain"]["hovertext"][0]
        assert labels.C3_PLAIN_MIXED in c3_caption(tree)

    def test_an_all_at_election_year_says_so(self) -> None:
        body = copy.deepcopy(per_capita_body(1848))
        for row in body["data"]:
            row["boundary_basis"] = "at_election"
        tree = section(1848, body)
        assert "striped" not in c3_traces(c3_figure(tree))
        caption = c3_caption(tree)
        assert labels.C3_ALL_AT_ELECTION in caption
        assert labels.C3_STRIPES not in caption

    @pytest.mark.parametrize(("year", "usps"), [(2024, "TX"), (2024, "WY"), (1848, "TX")])
    def test_the_selected_state_is_one_point_at_the_start_of_its_row(
        self, year: int, usps: str
    ) -> None:
        """AC: never narrowed by the filter; the selected state is a second trace (one
        point, its own symbol), never a per-point symbol list."""
        tree = section(year, state=usps)
        figure = c3_figure(tree)
        default = c3_figure(section(year))
        assert figure["layout"]["yaxis"] == default["layout"]["yaxis"]
        found = c3_traces(figure)
        selected = found.pop("selected")
        assert selected["ids"] == [usps] and selected["x"] == [0]
        name = next(
            r["state"] for r in per_capita_body(year)["data"] if r["state_usps"] == usps
        )
        assert selected["y"] == [figure["layout"]["yaxis"]["ticktext"].index(name)]
        assert selected["hoverinfo"] == "skip"
        assert isinstance(selected["marker"]["symbol"], str)
        assert found == {
            k: v for k, v in c3_traces(default).items() if k != "selected"
        }
        assert labels.C3_SELECTED_NOTE.format(state=name) in c3_caption(tree)
        # T6, not the chart, is narrowed.
        assert list(per_capita_rows(tree)) == [name]

    def test_no_selected_mark_without_a_selected_state(self) -> None:
        for state in (None, "CA"):  # no filter; a state 1848 does not hold
            tree = section(1848, state=state)
            assert "selected" not in c3_traces(c3_figure(tree))
            assert "selected state" not in c3_caption(tree)

    def test_no_average_line_or_any_shape(self) -> None:
        for year in C3_YEARS:
            layout = c3_figure(section(year))["layout"]
            assert "shapes" not in layout
            assert "annotations" not in layout

    def test_tick_labels_are_hidden_and_the_axis_is_titled(self) -> None:
        xaxis = c3_figure(section(2024))["layout"]["xaxis"]
        assert xaxis["showticklabels"] is False
        assert xaxis["title"]["text"] == labels.LABELS["persons_per_electoral_vote"]

    def test_a_body_naming_a_state_twice_degrades_the_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = copy.deepcopy(per_capita_body(2024))
        body["data"].append(copy.deepcopy(body["data"][0]))
        with pytest.raises(TypeError, match="twice"):
            section(2024, body)

    @pytest.mark.parametrize(
        ("value", "label"),
        [
            (float("nan"), labels.UNRECOGNIZED),
            (True, labels.UNRECOGNIZED),
            ("12", labels.UNRECOGNIZED),
            (0.0, labels.UNRECOGNIZED),
            (-5.0, labels.UNRECOGNIZED),
            (0.4, labels.UNRECOGNIZED),
            (0.5, labels.UNRECOGNIZED),
            (None, labels.NOT_IN_DATASET),
            ("", labels.NOT_IN_DATASET),
        ],
        ids=repr,
    )
    def test_a_value_no_figure_can_show_is_a_marker_never_a_bar(
        self, value: Any, label: str
    ) -> None:
        """Each value T6 cannot show as a figure is a marker labeled with T6's own
        cell (#435's review: the exact label, not any allowed one), and an
        unrecognized one carries its note in the hover, as T6's cell does."""
        body = copy.deepcopy(per_capita_body(2024))
        body["data"][0]["persons_per_electoral_vote"] = value
        row = body["data"][0]
        tree = section(2024, body)
        found = c3_traces(c3_figure(tree))
        assert found["marks"]["ids"] == [row["state_usps"]]
        assert row["state_usps"] not in found["striped"]["ids"]
        assert found["marks"]["text"] == [label]
        assert per_capita_rows(tree)[row["state"]]["persons_per_electoral_vote"] == label
        cell = label
        if label == labels.UNRECOGNIZED:
            cell = f"{label}<br>{labels.UNRECOGNIZED_NOTE}"
        assert found["marks"]["hovertext"] == [
            labels.C3_NO_FIGURE_HOVER.format(state=row["state"], cell=cell)
        ]

    @pytest.mark.parametrize("value", [0, 0.0, -5.0, -0.4, 0.4, 0.5])
    def test_a_ratio_of_zero_or_less_reads_unrecognized_in_every_table(
        self, value: Any
    ) -> None:
        """#435's review (F2): no population divided by electors appointed is zero or
        less, so the shared cell (T6, T7 and C3) reads it as unrecognized, and C3's
        value axis never needs to reach below zero."""
        assert (
            labels.persons_per_electoral_vote(value, "covered", 3)
            == labels.UNRECOGNIZED
        )
        # A figure is written to a whole person, so one that rounds to zero is too:
        # 0.5 rounds half to even (round-2 review).
        assert labels.persons_per_electoral_vote(0.6, "covered", 3) == "1"

    def test_the_drawn_range_starts_at_zero_and_reaches_the_longest_bar(self) -> None:
        figure = c3_figure(section(2024))
        rows = per_capita_body(2024)["data"]
        longest = max(r["persons_per_electoral_vote"] for r in rows)
        assert figure["layout"]["xaxis"]["range"] == [0, longest]

    def test_stripes_are_the_page_color_over_the_bar_and_plain_bars_have_none(
        self,
    ) -> None:
        found = c3_traces(c3_figure(section(1848)))
        assert found["striped"]["marker"] == {
            "color": "var(--chart-1)",
            "pattern": {"shape": "/", "fillmode": "overlay", "fgcolor": "var(--page)"},
        }
        assert found["plain"]["marker"] == {"color": "var(--chart-1)"}

    def test_the_selected_mark_is_page_filled_ringed_and_under_the_markers(
        self,
    ) -> None:
        """#435's review (F3): the mark sits half over its bar's start, so it is filled
        with the page color, which ``test_each_mark_meets_3_to_1_on_the_page``
        (``test_dashboard_theme.py``) holds at 3:1 against ``--chart-1`` in both
        palettes, ringed in the text color; drawn before the marker trace, so a
        marker in its row is on top."""
        from tests.unit.test_dashboard_theme import (
            EXPLICIT_DARK,
            LIGHT,
            NON_TEXT,
            block,
            contrast,
            parse_color,
        )

        figure = c3_figure(section(1864, state="GA"))
        roles = [
            "selected" if t["name"] == labels.C3_SELECTED else t["type"]
            for t in figure["data"]
        ]
        assert roles.index("selected") < roles.index("scatter")
        selected = c3_traces(figure)["selected"]
        assert selected["marker"] == {
            "symbol": "diamond",
            "size": PC["_SELECTED_PX"],
            "color": "var(--page)",
            "line": {"width": 2, "color": "var(--text)"},
        }
        for palette in (LIGHT, EXPLICIT_DARK):
            colors = block(palette)
            pair = (parse_color(colors["--page"]), parse_color(colors["--chart-1"]))
            assert contrast(*pair) >= NON_TEXT

    @pytest.mark.parametrize(
        ("year", "body", "state", "parts"),
        [
            (2024, None, None, ["C3_RATIO", "C3_CENSUS", "C3_STRIPES", "BOUNDARY_NOTE"]),
            (
                1848,
                None,
                None,
                [
                    "C3_RATIO",
                    "C3_CENSUS",
                    "C3_STRIPES",
                    "BOUNDARY_NOTE",
                    "C3_NO_FIGURE_NOTE",
                ],
            ),
            (
                1864,
                None,
                "GA",
                [
                    "C3_RATIO",
                    "C3_CENSUS",
                    "C3_STRIPES",
                    "BOUNDARY_NOTE",
                    "C3_NO_FIGURE_NOTE",
                    "C3_SELECTED_NOTE",
                ],
            ),
            (
                1848,
                "all_at_election",
                None,
                ["C3_RATIO", "C3_CENSUS", "C3_ALL_AT_ELECTION", "C3_NO_FIGURE_NOTE"],
            ),
            (
                2024,
                "unrecognized_border",
                None,
                [
                    "C3_RATIO",
                    "C3_CENSUS",
                    "C3_STRIPES",
                    "BOUNDARY_NOTE",
                    "C3_PLAIN_MIXED",
                ],
            ),
            (
                2024,
                "mixed_census",
                None,
                ["C3_RATIO", "C3_CENSUS_MIXED", "C3_STRIPES", "BOUNDARY_NOTE"],
            ),
        ],
    )
    def test_the_caption_is_exactly_its_configuration_s_sentences(
        self, year: int, body: str | None, state: str | None, parts: list[str]
    ) -> None:
        """#435's review (ge.2): the whole caption, in order, so a sentence shown in
        the wrong configuration fails, not only a missing one."""
        doctored = copy.deepcopy(per_capita_body(year))
        if body == "all_at_election":
            for row in doctored["data"]:
                row["boundary_basis"] = "at_election"
        elif body == "unrecognized_border":
            doctored["data"][0]["boundary_basis"] = "sideways"
        elif body == "mixed_census":
            doctored["data"][0]["governing_census_year"] = 1990
        tree = section(year, doctored, state=state)
        name = next(
            (r["state"] for r in doctored["data"] if r["state_usps"] == state), ""
        )
        sentences = [
            labels.C3_SELECTED_NOTE.format(state=name)
            if part == "C3_SELECTED_NOTE"
            else getattr(labels, part)
            for part in parts
        ]
        expected = " ".join(sentences) + " " + labels.CHART_TABLE_POINTER + "."
        assert c3_caption(tree) == expected

    @pytest.mark.parametrize("census", [None, " "])
    def test_an_absent_census_year_names_no_census(self, census: Any) -> None:
        """#435's review (F4): a year whose every census-year cell is a cause names no
        census in the title or caption."""
        body = copy.deepcopy(per_capita_body(2024))
        for row in body["data"]:
            row["governing_census_year"] = census
        tree = section(2024, body)
        assert c3_title(tree) == labels.C3_TITLE_NO_CENSUS.format(year=2024)
        caption = c3_caption(tree)
        assert labels.C3_CENSUS_MIXED in caption and labels.C3_CENSUS not in caption

    def test_equal_ratios_are_ordered_by_state_name(self) -> None:
        """#435's review (ge.8a): called directly, with the tie in reverse name order,
        since a render sorts rows by name first and the sort is stable."""
        rows = [
            r
            for r in copy.deepcopy(per_capita_body(2024))["data"]
            if r["state_usps"] in ("AK", "WY")
        ]
        for row in rows:
            row["persons_per_electoral_vote"] = 100.0
        rows.sort(key=lambda r: str(r["state"]), reverse=True)
        strings = {r["state_usps"]: labels.per_capita_strings(r) for r in rows}
        drawn, rest = PC["_c3_order"](rows, strings)
        assert [r["state"] for r, _ in drawn] == ["Alaska", "Wyoming"] and rest == []

    def test_a_hostile_state_name_is_drawn_as_written(self) -> None:
        body = copy.deepcopy(per_capita_body(1848))
        hostile = "<b>A & B</b>"
        for row in body["data"]:
            if row["state_usps"] in ("TX", "NY"):
                row["state"] = hostile + row["state_usps"]
        tree = section(1848, body)
        figure = c3_figure(tree)
        escaped = "&lt;b&gt;A &amp; B&lt;/b&gt;"
        ticks = figure["layout"]["yaxis"]["ticktext"]
        assert f"{escaped}TX" in ticks and f"{escaped}NY" in ticks
        found = c3_traces(figure)
        bars = found["plain"]["hovertext"] + found["striped"]["hovertext"]
        assert any(h.startswith(f"{escaped}NY<br>") for h in bars)
        assert found["marks"]["hovertext"][0].startswith(f"{escaped}TX<br>")

    @pytest.mark.parametrize(
        "name", ["var(--chart-1)", "var(--unset)", "x var(--page) y", "(a)"]
    )
    def test_a_state_name_spelling_a_token_reference_is_drawn_as_written(
        self, name: str
    ) -> None:
        """As C1's round 1: a served name holding ``var(`` would make
        ``components.chart`` refuse the figure, so the chart would not be drawn (#467,
        D095); the escape keeps it drawn."""
        from explore import charts

        body = copy.deepcopy(per_capita_body(1848))
        for row in body["data"]:
            if row["state_usps"] in ("TX", "NY"):
                row["state"] = name + row["state_usps"]
        tree = section(1848, body)
        assert c3(tree) is not None and find(tree, PER_CAPITA) is not None
        figure = c3_figure(tree)
        assert charts.figure_problems(figure) == []
        shown = name.replace("(", "&#40;")
        ticks = figure["layout"]["yaxis"]["ticktext"]
        assert f"{shown}TX" in ticks and f"{shown}NY" in ticks
        found = c3_traces(figure)
        hovers = (
            found["plain"]["hovertext"]
            + found["striped"]["hovertext"]
            + found["marks"]["hovertext"]
        )
        assert all("var(" not in h for h in hovers)
        assert found["marks"]["hovertext"][0].startswith(f"{shown}TX<br>")

    def test_the_legend_lists_the_bar_series_and_the_selection_never_the_markers(
        self,
    ) -> None:
        """The acceptance gate's Class B survivors: which traces the legend lists is
        each trace's own ``showlegend``, asserted rather than inferred."""
        # 1848: both bar series, a marker (Texas), and Texas selected.
        found = c3_traces(c3_figure(section(1848, state="TX")))
        assert found["marks"]["showlegend"] is False
        assert found["selected"]["showlegend"] is True
        assert found["plain"]["showlegend"] is True
        assert found["striped"]["showlegend"] is True

    @pytest.mark.parametrize(("year", "state"), [(2024, None), (1864, "GA")])
    def test_the_first_row_is_drawn_at_the_top_and_the_legend_has_room(
        self, year: int, state: str | None
    ) -> None:
        """The acceptance gate's Class B survivors: the row axis is reversed (row 0,
        the most people per electoral vote, drawn at the top, as the caption says), and
        the height adds the legend's margin to the rows' and the bottom's."""
        figure = c3_figure(section(year, state=state))
        layout = figure["layout"]
        assert layout["yaxis"]["autorange"] == "reversed"
        entries = sum(1 for t in figure["data"] if t.get("showlegend"))
        top = PC["_TOP_PX"] + PC["_LEGEND_PX"] * entries
        rows = len(layout["yaxis"]["ticktext"])
        assert layout["margin"]["t"] == top
        assert layout["height"] == PC["_ROW_PX"] * rows + top + PC["_BOTTOM_PX"]

    def test_the_chart_reads_t6_s_strings_never_its_own(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The acceptance gate's Class B survivors (the mechanism, not the outcome): C3
        takes every drawn string and the stripe split from ``labels.per_capita_strings``,
        so a sentinel there reaches the chart. A chart that formatted its own text, split
        stripes on the raw value, or labeled an unknown cause with the cause itself would
        reach today's outcome and miss these sentinels."""
        real = labels.per_capita_strings
        body = copy.deepcopy(per_capita_body(1848))
        plain_row = next(r for r in body["data"] if r["boundary_basis"] == "at_election")
        texas = next(r for r in body["data"] if r["state_usps"] == "TX")

        def doctored(row: dict[str, Any]) -> dict[str, str]:
            strings = real(row)
            if row["state_usps"] == plain_row["state_usps"]:
                strings["persons_per_electoral_vote"] = "SENTINEL 1,234"
                strings["boundary_basis"] = labels.BOUNDARY_BASIS["present_day"]
            if row["state_usps"] == "TX":
                strings["persons_per_electoral_vote"] = "A cause no table names"
            return strings

        monkeypatch.setattr(labels, "per_capita_strings", doctored)
        found = c3_traces(c3_figure(section(1848, body)))
        usps = plain_row["state_usps"]
        assert usps in found["striped"]["ids"]
        assert usps not in found.get("plain", {"ids": []})["ids"]
        i = found["striped"]["ids"].index(usps)
        assert found["striped"]["text"][i] == "SENTINEL 1,234"
        assert "SENTINEL 1,234" in found["striped"]["hovertext"][i]
        assert texas["state_usps"] in found["marks"]["ids"]
        j = found["marks"]["ids"].index("TX")
        assert found["marks"]["text"][j] == labels.UNRECOGNIZED

    def test_the_lede_names_the_table_as_what_the_filter_narrows(self) -> None:
        assert PC["FILTER_SENTENCE"] == "Narrow the table to one state."
        assert lede_text(section(2024)).endswith(PC["FILTER_SENTENCE"])

    def test_the_footer_still_credits_the_census_bureau(self) -> None:
        assert any("Census Bureau" in t for t in texts(section(2024)))
