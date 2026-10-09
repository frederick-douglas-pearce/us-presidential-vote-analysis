"""Every table's CSV download (#309, D075).

Offline, against the recorded responses of ``test_dashboard_app.py``. Each table goes
through ``components.table``, which builds its body and its CSV from one row list and
puts the file in the link's ``data:`` URL; these tests decode that URL and read the file
as a spreadsheet or a script would.
"""

from __future__ import annotations

import copy
import csv
import io
import math
import re
from typing import Any
from urllib.parse import unquote_to_bytes

import dash
import pandas as pd
import pytest
from dash import html
from dash.development.base_component import Component

from explore import api, components, export, labels
from explore import app as appmod
from tests.unit.test_dashboard_app import (
    RECORDED,
    RecordingClient,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    concrete_values,
)
from tests.unit.test_dashboard_elections import label_key_problems, of_type, parse

#: Every table and its download link's id, by the page that renders it.
TABLES = {
    "elections-table": "/elections",
    "election-states": "/election/<year>",
    "election-nation": "/election/<year>",
    "election-per-capita": "/election/<year>",
    "state-history": "/state/<usps>",
    "state-per-capita": "/state/<usps>",
}

#: Each page's reads before #309, recorded on ``main`` at 72312da with
#: :class:`RecordingClient` at the registry's concrete values: the download adds none.
READS_BEFORE = {
    "/": ["/v1/meta"],
    "/elections": ["/v1/elections"],
    "/election/<year>": [
        "/v1/elections",
        "/v1/elections/1824",
        "/v1/elections/1824/per-capita",
        "/v1/elections",
    ],
    "/state/<usps>": [
        "/v1/elections",
        "/v1/elections/2024",
        "/v1/elections",
        "/v1/states/GA",
        "/v1/states/GA/per-capita",
    ],
    "/states": ["/v1/elections", "/v1/elections/2024"],
}

#: The server's routes before #309: a download adds none.
ROUTES = {
    "/",
    "/<path:path>",
    "/_ah/warmup",
    "/_dash-component-suites/<string:package_name>/<path:fingerprinted_path>",
    "/_dash-dependencies",
    "/_dash-layout",
    "/_dash-update-component",
    "/_favicon.ico",
    "/_reload-hash",
    "/assets/<path:filename>",
    "/static/<path:filename>",
}

FILENAME_RE = re.compile(r"[A-Za-z0-9-]+\.csv")


def page_of(key: str) -> dict[str, Any]:
    (page,) = [
        p
        for p in dash.page_registry.values()
        if (p.get("path_template") or p["path"]) == key
    ]
    found: dict[str, Any] = page
    return found


def render(
    key: str, monkeypatch: pytest.MonkeyPatch, query: str = "", **values: str
) -> tuple[Any, list[str]]:
    """A page's tree, rendered from recorded responses, and the paths it read."""
    page = page_of(key)
    client = RecordingClient()
    monkeypatch.setattr(api, "CLIENT", client)
    tree = page["layout"](**{**concrete_values(page), **values, **parse(query)})
    return tree, client.reads


def all_pages(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return {key: render(key, monkeypatch)[0] for key in READS_BEFORE}


class Csv:
    """A decoded download: its bytes, preamble sentences, header and rows."""

    def __init__(self, href: str) -> None:
        assert href.startswith(export.DATA_URL_PREFIX), href[:40]
        self.raw = unquote_to_bytes(href.removeprefix(export.DATA_URL_PREFIX))
        text = self.raw.decode("utf-8")
        assert text.startswith(export.BOM)
        records = list(csv.reader(io.StringIO(text.removeprefix(export.BOM))))
        blank = records.index([])
        self.preamble = records[:blank]
        self.header = records[blank + 1]
        self.rows = [
            dict(zip(self.header, r, strict=True)) for r in records[blank + 2 :]
        ]

    @property
    def lines(self) -> list[str]:
        return [text for _hash, text in self.preamble]


def links(tree: Any) -> dict[str, Any]:
    """Every download link in a tree, by id."""
    return {
        a.id: a
        for a in of_type(tree, "A")
        if isinstance(getattr(a, "id", None), str) and a.id.endswith("-csv")
    }


def download(tree: Any, table_id: str) -> Csv:
    return Csv(links(tree)[export.link_id(table_id)].href)


def body_rows(tree: Any, table_id: str) -> list[Any]:
    (table,) = [t for t in of_type(tree, "Table") if getattr(t, "id", None) == table_id]
    (tbody,) = of_type(table, "Tbody")
    return of_type(tbody, "Tr")


def table_problems(tree: Any) -> list[str]:
    """Each table without its download: every ``html.Table`` must sit in a
    ``table-scroll`` box followed by its link, whose file has one row per body row and
    the table's columns first, in order."""
    problems: list[str] = []

    def kids(node: Any) -> list[Any]:
        found = getattr(node, "children", None)
        if isinstance(found, (list, tuple)):
            return list(found)
        return [] if found is None else [found]

    def visit(nodes: list[Any], boxed: bool) -> None:
        for i, child in enumerate(nodes):
            if not isinstance(child, Component):
                continue
            if isinstance(child, html.Table):
                if not boxed:
                    problems.append(f"{getattr(child, 'id', None)}: not in a table box")
                continue
            box = getattr(child, "className", None) == "table-scroll"
            if box:
                after = nodes[i + 1] if i + 1 < len(nodes) else None
                for table in of_type(child, "Table"):
                    problems.extend(link_problems(table, after))
            visit(kids(child), box)

    visit(list(tree) if isinstance(tree, (list, tuple)) else [tree], False)
    return problems


def link_problems(table: Any, after: Any) -> list[str]:
    found = links(after) if after is not None else {}
    link = found.get(export.link_id(table.id))
    if link is None:
        return [f"{table.id}: no download link"]
    if not str(link.href).startswith(export.DATA_URL_PREFIX):
        return [f"{table.id}: the link is not a data: URL"]
    file = Csv(link.href)
    headers = [th.title for th in of_type(table, "Th")]
    problems = []
    if file.header[: len(headers)] != headers:
        problems.append(f"{table.id}: columns {file.header} do not start {headers}")
    if len(file.rows) != len(of_type(of_type(table, "Tbody"), "Tr")):
        problems.append(f"{table.id}: {len(file.rows)} rows in the file")
    if not FILENAME_RE.fullmatch(str(link.download)):
        problems.append(f"{table.id}: filename {link.download!r}")
    return problems


# --- coverage is structural -----------------------------------------------------------


class TestEveryTable:
    def test_every_rendered_table_offers_its_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        found: set[Any] = set()
        for key, tree in all_pages(monkeypatch).items():
            assert table_problems(tree) == [], key
            found |= {getattr(t, "id", None) for t in of_type(tree, "Table")}
        assert set(TABLES) <= found

    def test_a_bare_table_fails(self) -> None:
        bare = html.Div([html.Table([html.Tbody([html.Tr()])], id="bare")])
        assert table_problems(bare) == ["bare: not in a table box"]
        alone = html.Div(html.Table([], id="alone"))  # a single child, not a list
        assert table_problems(alone) == ["alone: not in a table box"]

    def test_a_boxed_table_without_its_link_fails(self) -> None:
        box = html.Div(html.Table([], id="t"), className="table-scroll")
        assert table_problems(html.Div([box])) == ["t: no download link"]

    def test_a_link_that_is_not_a_data_url_fails(self) -> None:
        box = html.Div(html.Table([], id="t"), className="table-scroll")
        for href in ("https://example.org/t.csv", "/t.csv"):
            link = html.P(html.A("x", href=href, id="t-csv", download="t.csv"))
            assert table_problems(html.Div([box, link])) == [
                "t: the link is not a data: URL"
            ]

    def test_a_file_with_another_row_count_fails(self) -> None:
        dl = export.Download("t.csv", "t", RECORDED["/v1/meta"]["provenance"], "u")
        rows = [{"year": 1824}, {"year": 1828}]
        built = components.table(rows, lambda r: html.Tr(), ("year",), "t", dl)
        box, link = built[0], built[1]
        box.children.children[1].children = [html.Tr()]  # one body row, two in the file
        assert table_problems(html.Div([box, link])) == ["t: 2 rows in the file"]

    def test_no_rows_no_table_and_no_download(self) -> None:
        dl = export.Download("t.csv", "t", {}, "u")
        built = components.table([], lambda r: html.Tr(), ("year",), "t", dl)
        assert links(built) == {} and of_type(built, "Table") == []
        assert built[0].children == components.NO_ROWS


# --- exactly the view -----------------------------------------------------------------


class TestExactlyTheView:
    def test_1860_filtered_to_south_carolina(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/election/<year>", monkeypatch, "state=SC", year="1860")
        for table in ("election-states", "election-per-capita"):
            file = download(tree, table)
            assert file.rows, table
            assert {r["state_usps"] for r in file.rows} == {"SC"}, table
            assert len(file.rows) == len(body_rows(tree, table)), table
        recorded = RECORDED["/v1/elections/1860"]
        states = download(tree, "election-states")
        expected = [r for r in recorded["data"] if r["state_usps"] == "SC"]
        assert [r["candidate_slug"] for r in states.rows] == [
            r["candidate_slug"] for r in expected
        ]
        nation = download(tree, "election-nation")
        assert [r["candidate_slug"] for r in nation.rows] == [
            r["candidate_slug"] for r in recorded["summary"]
        ]
        assert states.lines[
            [i for i, x in enumerate(states.lines) if "View" in x][0]
        ] == (
            "View: https://explore.us-presidential-election-center.org"
            "/election/1860?state=SC"
        )

    def test_the_file_follows_the_rows_the_table_shows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/state/<usps>", monkeypatch, "year_from=1976&year_to=1980")
        history = download(tree, "state-history")
        assert {r["year"] for r in history.rows} == {"1976", "1980"}
        per_capita = download(tree, "state-per-capita")
        assert {r["year"] for r in per_capita.rows} == {"1976", "1980"}

    def test_the_view_url_names_the_filters_the_render_applied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A state 1860 does not name falls back to "all", so the view is unfiltered.
        tree, _ = render("/election/<year>", monkeypatch, "state=ZZ", year="1860")
        lines = download(tree, "election-states").lines
        assert (
            "View: https://explore.us-presidential-election-center.org/election/1860"
            in lines
        )

    @pytest.mark.parametrize(
        ("key", "table", "columns"),
        [
            (
                "/elections",
                "elections-table",
                ("year", "candidate_count", "has_popular_vote"),
            ),
            (
                "/election/<year>",
                "election-states",
                (
                    "state",
                    "candidate",
                    "party",
                    "state_electoral_votes",
                    "electoral_votes",
                    "electoral_votes_counted",
                    "electoral_count_status",
                    "pv_status",
                    "popular_votes",
                    "electoral_count_status_reason",
                    "state_usps",
                    "candidate_slug",
                    "year",
                ),
            ),
            ("/election/<year>", "election-per-capita", None),
            ("/state/<usps>", "state-history", None),
        ],
    )
    def test_the_columns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        key: str,
        table: str,
        columns: tuple[str, ...] | None,
    ) -> None:
        file = download(render(key, monkeypatch)[0], table)
        if columns is not None:
            assert tuple(file.header) == columns
        assert label_key_problems(file.header) == []

    def test_every_column_is_a_public_api_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        headers = {
            field
            for tree in all_pages(monkeypatch).values()
            for link in links(tree).values()
            for field in Csv(link.href).header
        }
        assert label_key_problems(sorted(headers)) == []

    def test_each_filename_names_its_view_and_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = {
            link_id: link.download
            for tree in all_pages(monkeypatch).values()
            for link_id, link in links(tree).items()
        }
        assert names == {
            "elections-table-csv": "elections.csv",
            "election-states-csv": "election-1824-by-state.csv",
            "election-nation-csv": "election-1824-national.csv",
            "election-per-capita-csv": "election-1824-per-capita.csv",
            "state-history-csv": "state-GA-history.csv",
            "state-per-capita-csv": "state-GA-per-capita.csv",
        }

    def test_each_link_on_a_page_has_its_own_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, tree in all_pages(monkeypatch).items():
            names = [str(link.children) for link in links(tree).values()]
            assert len(names) == len(set(names)), key


# --- nulls ----------------------------------------------------------------------------


class TestNulls:
    def test_a_null_is_an_empty_cell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tree, _ = render("/election/<year>", monkeypatch, year="1860")
        states = download(tree, "election-states")
        recorded = RECORDED["/v1/elections/1860"]["data"]
        assert all(r["popular_votes"] is None for r in recorded)  # the premise
        assert {r["popular_votes"] for r in states.rows} == {""}
        assert {r["party"] for r in states.rows} == {""}
        nation = download(tree, "election-nation")
        assert {r["hybrid_score"] for r in nation.rows} == {""}

    def test_the_columns_that_explain_a_null_travel_with_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/election/<year>", monkeypatch, year="1872")
        states = download(tree, "election-states")
        reasons = {r["electoral_count_status_reason"] for r in states.rows}
        assert reasons - {""}, "1872 carries Archives reasons"
        assert {r["pv_status"] for r in states.rows} <= set(labels.PV_STATUS)
        assert {r["electoral_count_status"] for r in states.rows} <= set(
            labels.COUNT_STATUS
        )
        assert "Popular votes cover 1976–2024" in states.lines
        assert export.NULL_LINE in states.lines
        assert labels.PARTY_NOTE in states.lines

    def test_the_per_capita_notes_explain_its_nulls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/state/<usps>", monkeypatch)
        lines = download(tree, "state-per-capita").lines
        assert labels.GOVERNING_CENSUS_NOTE in lines
        assert labels.BOUNDARY_NOTE in lines

    @pytest.mark.parametrize(
        ("value", "written"),
        [
            (None, ""),
            (True, "true"),
            (False, "false"),
            (0, "0"),
            (-3, "-3"),
            (12345678901234567890, "12345678901234567890"),
            (0.5940594059405941, "0.5940594059405941"),
            (-0.25, "-0.25"),
            (math.nan, ""),
            (math.inf, ""),
            (-math.inf, ""),
            ("Abraham Lincoln", "Abraham Lincoln"),
            ("=HYPERLINK(1)", "'=HYPERLINK(1)"),
            ("+1", "'+1"),
            ("-1", "'-1"),
            ("@SUM(A1)", "'@SUM(A1)"),
            ("\tx", "'\tx"),
            ("\rx", "'\rx"),
            (["=x"], "['=x']"),
            ({"a": 1}, "{'a': 1}"),
        ],
        ids=repr,
    )
    def test_a_cell(self, value: Any, written: str) -> None:
        assert export.cell(value) == written

    def test_a_non_string_value_is_guarded_by_its_text(self) -> None:
        class Formula:
            def __str__(self) -> str:
                return "=1+1"

        assert export.cell(Formula()) == "'=1+1"


# --- attribution ----------------------------------------------------------------------


def provenance() -> dict[str, Any]:
    return copy.deepcopy(RECORDED["/v1/elections/1860"]["meta"]["provenance"])


class TestAttribution:
    def test_every_source_line_is_read_from_provenance(self) -> None:
        given = provenance()
        given.update(
            ec_source_name="EC-NAME",
            ec_license="EC-LIC",
            ec_license_url="https://ec.example",
            source_name="PV-NAME",
            license="PV-LIC",
            license_url="https://pv.example",
            snapshot_version="v-123",
        )
        given["coverage"] = {
            "year_min": 1111,
            "year_max": 2222,
            "pv_year_min": 1333,
            "pv_year_max": 1444,
        }
        lines = export.preamble(("year", "popular_votes"), given, "URL")
        assert lines == [
            "Electoral votes: EC-NAME (EC-LIC; https://ec.example)",
            "Popular votes: PV-NAME (PV-LIC; https://pv.example)",
            "Data snapshot: v-123",
            "Electoral votes cover 1111–2222",
            "Popular votes cover 1333–1444",
            "View: URL",
            export.NULL_LINE,
        ]

    @pytest.mark.parametrize(
        ("table", "pv", "census"),
        [
            ("elections-table", True, False),
            ("election-states", True, False),
            ("election-nation", True, False),
            ("election-per-capita", False, True),
            ("state-history", True, False),
            ("state-per-capita", False, True),
        ],
    )
    def test_each_table_names_the_sources_it_carries(
        self, monkeypatch: pytest.MonkeyPatch, table: str, pv: bool, census: bool
    ) -> None:
        tree, _ = render(TABLES[table], monkeypatch)
        lines = download(tree, table).lines
        meta = provenance()
        assert lines[0].startswith(f"Electoral votes: {meta['ec_source_name']} (")
        assert (
            any(x.startswith(f"Popular votes: {meta['source_name']}") for x in lines)
            is pv
        )
        assert (
            any(
                x.startswith(f"Population: {meta['census_source_name']}") for x in lines
            )
            is census
        )

    def test_a_per_capita_table_reads_its_own_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        per_capita = copy.deepcopy(RECORDED["/v1/states/GA/per-capita"])
        per_capita["meta"]["provenance"]["census_source_name"] = "OWN-RESPONSE"
        monkeypatch.setitem(RECORDED, "/v1/states/GA/per-capita", per_capita)
        tree, _ = render("/state/<usps>", monkeypatch)
        assert any(
            "OWN-RESPONSE" in x for x in download(tree, "state-per-capita").lines
        )

    def test_it_states_provenance_never_a_license_condition(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for tree in all_pages(monkeypatch).values():
            for link in links(tree).values():
                text = " ".join(Csv(link.href).lines).lower()
                for word in ("required", "must", "copyright", "©", "all rights"):
                    assert word not in text

    def test_the_field_sets_are_disjoint_and_cover_every_column(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sets = (export.EC_FIELDS, export.POPULAR_VOTE_FIELDS, export.CENSUS_FIELDS)
        assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        headers = {
            field
            for tree in all_pages(monkeypatch).values()
            for link in links(tree).values()
            for field in Csv(link.href).header
        }
        assert headers - set().union(*sets) == set()

    def test_a_sentence_is_one_guarded_line(self) -> None:
        lines = export.preamble(("year",), provenance(), "u", ["a\nb, c", "=1"])
        assert "a b, c" in lines and "'=1" in lines


# --- the file as a spreadsheet or a script reads it -----------------------------------


class TestFile:
    def test_the_href_carries_the_exact_bytes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/election/<year>", monkeypatch, year="1872")
        for link in links(tree).values():
            encoded = link.href.removeprefix(export.DATA_URL_PREFIX)
            assert not set(encoded) & {"#", " ", "\n", "\r", ","}
            file = Csv(link.href)
            assert file.raw.startswith("﻿".encode())
            assert file.raw.count("﻿".encode()) == 1

    def test_a_script_skipping_comments_reads_the_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/election/<year>", monkeypatch, year="1872")
        file = download(tree, "election-states")
        frame = pd.read_csv(
            io.BytesIO(file.raw), comment="#", encoding="utf-8-sig", dtype=str
        )
        assert list(frame.columns) == file.header
        assert len(frame) == len(file.rows) == len(body_rows(tree, "election-states"))

    def test_a_comma_or_quote_in_a_cell_is_quoted(self) -> None:
        assert export.row(["a,b", 'say "x"', "line\nbreak", "plain"]) == (
            '"a,b","say ""x""","line\nbreak",plain\r\n'
        )


# --- request budget and D070(b) -------------------------------------------------------


class TestRequestBudget:
    def test_a_render_reads_what_it_read_before(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, before in READS_BEFORE.items():
            _, reads = render(key, monkeypatch)
            assert reads == before, key

    def test_the_file_is_whole_without_the_api(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/election/<year>", monkeypatch, "state=SC", year="1860")

        class NoClient:
            def view(self) -> Any:
                raise AssertionError("a download read the API")

        monkeypatch.setattr(api, "CLIENT", NoClient())
        file = download(tree, "election-states")
        expected = [
            r for r in RECORDED["/v1/elections/1860"]["data"] if r["state_usps"] == "SC"
        ]
        assert [r["candidate"] for r in file.rows] == [r["candidate"] for r in expected]
        assert [r["electoral_votes"] for r in file.rows] == [
            str(r["electoral_votes"]) for r in expected
        ]

    def test_no_callback_or_route_serves_a_download(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outputs = [
            str(c.get("output")) for c in dash._callback.GLOBAL_CALLBACK_LIST
        ] + [str(key) for key in appmod.app.callback_map]
        assert outputs, "no callbacks found; the check would be vacuous"
        assert not [o for o in outputs if "-csv" in o or "download" in o.lower()]
        assert {r.rule for r in appmod.server.url_map.iter_rules()} == ROUTES
        for tree in all_pages(monkeypatch).values():
            assert of_type(tree, "Download") == []
