"""Every table's CSV download (#309, D075).

Offline, against the recorded responses of ``test_dashboard_app.py``. Each table goes
through ``components.table``, which builds its body and its CSV from one row list and
puts the file in the link's ``data:`` URL; these tests decode that URL and read the file
as a spreadsheet or a script would.
"""

from __future__ import annotations

import copy
import csv
import functools
import io
import math
import re
from collections.abc import Callable
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
from tests.unit.test_dashboard_guards import DOWNLOAD_IDS

#: Every table's id (its link's is ``export.link_id(id)``), by the page that renders it.
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

#: Every callback output once Dash has registered them all, before and after #309: the
#: Pages router's two and each filtered page's URL. A download adds none.
CALLBACK_OUTPUTS = {
    ".._pages_content.children..._pages_store.data..",
    "_pages_dummy.children",
    "elections-url.search",
    "election-url.search",
    "state-url.search",
}

HOST = "https://explore.us-presidential-election-center.org"


def page_key(page: dict[str, Any]) -> str:
    key: str = page.get("path_template") or page["path"]
    return key


def page_of(key: str) -> dict[str, Any]:
    (page,) = [p for p in dash.page_registry.values() if page_key(p) == key]
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
    """Every registered page's tree, at the registry's concrete values."""
    keys = [page_key(page) for page in dash.page_registry.values()]
    return {key: render(key, monkeypatch)[0] for key in keys}


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
    if not headers or not all(isinstance(h, str) and h for h in headers):
        return [f"{table.id}: no column headers"]
    problems = []
    if file.header[: len(headers)] != headers:
        problems.append(f"{table.id}: columns {file.header} do not start {headers}")
    if len(file.rows) != len(of_type(of_type(table, "Tbody"), "Tr")):
        problems.append(f"{table.id}: {len(file.rows)} rows in the file")
    if not FILENAME_RE.fullmatch(str(link.download)):
        problems.append(f"{table.id}: filename {link.download!r}")
    return problems


def unbuilt_tables(
    build: Callable[[], Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, set[Any]]:
    """``build()``'s tree, and the ids of its tables ``components.table`` did not
    build during that call (recorded through a wrapper; pages call it by attribute)."""
    built: list[str] = []
    real = components.table

    def recording(*args: Any, **kwargs: Any) -> list[Any]:
        built.append(args[3])  # the table id
        return real(*args, **kwargs)

    monkeypatch.setattr(components, "table", recording)
    tree = build()
    monkeypatch.setattr(components, "table", real)
    ids = {getattr(t, "id", None) for t in of_type(tree, "Table")}
    return tree, ids - set(built)


# --- coverage is structural -----------------------------------------------------------


class TestEveryTable:
    def test_every_rendered_table_offers_its_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every registered page, rendered: each table is built by
        ``components.table`` (recorded through a wrapper) and carries its link."""
        found: set[Any] = set()
        for page in dash.page_registry.values():
            key = page_key(page)
            tree, unbuilt = unbuilt_tables(
                functools.partial(lambda k: render(k, monkeypatch)[0], key), monkeypatch
            )
            assert table_problems(tree) == [], key
            assert unbuilt == set(), key
            found |= {getattr(t, "id", None) for t in of_type(tree, "Table")}
        assert set(TABLES) <= found

    def test_a_table_built_outside_the_component_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuity for the wrapper: a boxed, linked table a page builds by hand is
        caught, though ``table_problems`` passes it."""
        dl = export.Download("t.csv", "t", provenance(), "u")
        rows = [{"year": 1824}]
        built_by_hand = components.table(
            rows, lambda r: html.Tr(html.Td("1824")), ("year",), "by-hand", dl
        )

        def layout() -> Any:
            via = components.table(
                rows, lambda r: html.Tr(html.Td("1824")), ("year",), "via", dl
            )
            return html.Div([*via, *built_by_hand])

        tree, unbuilt = unbuilt_tables(layout, monkeypatch)
        assert table_problems(tree) == []
        assert unbuilt == {"by-hand"}

    def test_the_registry_and_the_table_literals_agree(self) -> None:
        assert set(READS_BEFORE) == {page_key(p) for p in dash.page_registry.values()}
        assert {export.link_id(table) for table in TABLES} == set(DOWNLOAD_IDS)

    def test_the_file_keeps_the_body_s_order(self) -> None:
        dl = export.Download("t.csv", "t", provenance(), "u")
        rows = [{"year": y} for y in (1830, 1824, 1828)]
        seen: list[int] = []

        def render_row(row: dict[str, Any]) -> html.Tr:
            seen.append(row["year"])
            return html.Tr()

        built = components.table(rows, render_row, ("year",), "t", dl)
        assert [int(r["year"]) for r in Csv(built[1].children.href).rows] == seen
        assert seen == [1830, 1824, 1828]

    def test_a_file_with_other_columns_or_a_bad_filename_fails(self) -> None:
        box = html.Div(
            html.Table([html.Thead(html.Tr(labels.header("year"))), html.Tbody([])]),
            className="table-scroll",
        )
        box.children.id = "t"
        dl = export.Download("t.csv", "t", provenance(), "u")
        wrong = export.link("t", dl, export.csv_text(("candidate",), [], dl))
        assert table_problems(html.Div([box, wrong])) == [
            "t: columns ['candidate'] do not start ['year']"
        ]
        named = export.link("t", dl._replace(filename="a b.csv"), "x")
        named.children.href = export.href(export.csv_text(("year",), [], dl))
        assert table_problems(html.Div([box, named])) == ["t: filename 'a b.csv'"]

    def test_a_table_with_no_headers_fails(self) -> None:
        box = html.Div(html.Table([html.Tbody([])], id="t"), className="table-scroll")
        dl = export.Download("t.csv", "t", provenance(), "u")
        link = export.link("t", dl, export.csv_text(("year",), [], dl))
        assert table_problems(html.Div([box, link])) == ["t: no column headers"]

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
        expected = sorted(
            (r for r in RECORDED["/v1/states/GA"]["data"] if 1976 <= r["year"] <= 1980),
            key=lambda r: (r["year"], str(r["candidate"])),
        )
        assert [(r["year"], r["candidate_slug"]) for r in history.rows] == [
            (str(r["year"]), r["candidate_slug"]) for r in expected
        ]
        assert len(history.rows) == len(body_rows(tree, "state-history"))
        per_capita = download(tree, "state-per-capita")
        assert [r["year"] for r in per_capita.rows] == [
            str(r["year"])
            for r in sorted(
                RECORDED["/v1/states/GA/per-capita"]["data"], key=lambda r: r["year"]
            )
            if 1976 <= r["year"] <= 1980
        ]
        assert len(per_capita.rows) == len(body_rows(tree, "state-per-capita"))

    def test_the_elections_file_follows_its_filters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/elections", monkeypatch, "year_from=1976&pv=1")
        file = download(tree, "elections-table")
        assert [r["year"] for r in file.rows] == [
            str(r["year"])
            for r in RECORDED["/v1/elections"]["data"]
            if r["year"] >= 1976 and r["has_popular_vote"] is True
        ]
        assert len(file.rows) == len(body_rows(tree, "elections-table"))
        assert {r["has_popular_vote"] for r in file.rows} == {"true"}

    @pytest.mark.parametrize(
        ("key", "query", "table", "view"),
        [
            # Out of span: the bound falls back, so only the applied filter is named.
            ("/elections", "year_from=1700&pv=1", "elections-table", "/elections?pv=1"),
            # The full span is the default: no filter at all.
            (
                "/elections",
                "year_from=1824&year_to=2024",
                "elections-table",
                "/elections",
            ),
            # A candidate the state never had falls back to "all".
            (
                "/state/<usps>",
                "year_from=1976&candidate=no-such-slug",
                "state-history",
                "/state/GA?year_from=1976",
            ),
            (
                "/state/<usps>",
                "year_to=2024&pv_status=popular_vote",
                "state-per-capita",
                "/state/GA?pv_status=popular_vote",
            ),
        ],
    )
    def test_the_view_url_names_only_the_applied_filters(
        self,
        monkeypatch: pytest.MonkeyPatch,
        key: str,
        query: str,
        table: str,
        view: str,
    ) -> None:
        tree, _ = render(key, monkeypatch, query)
        assert f"View: {HOST}{view}" in download(tree, table).lines

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
        state = page_of("/state/<usps>")["layout"].__globals__
        assert state["PER_CAPITA_FILTER_NOTE"] in lines
        tree, _ = render("/election/<year>", monkeypatch)
        election = page_of("/election/<year>")["layout"].__globals__
        assert election["PER_CAPITA_FILTER_NOTE"] in (
            download(tree, "election-per-capita").lines
        )

    def test_the_elections_file_says_what_false_means(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/elections", monkeypatch)
        file = download(tree, "elections-table")
        assert labels.HAS_POPULAR_VOTE_NOTE in file.lines
        assert {r["has_popular_vote"] for r in file.rows} == {"true", "false"}

    def test_every_data_cell_goes_through_cell(self) -> None:
        dl = export.Download("t.csv", "t", provenance(), "u")
        row = {"a": "=x", "b": None, "c": True, "d": math.nan, "e": -2}
        text = export.csv_text(tuple(row), [row], dl)
        assert text.endswith("\r\n'=x,,true,,-2\r\n")

    def test_a_lone_surrogate_is_replaced_not_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = copy.deepcopy(RECORDED["/v1/elections/1824"])
        body["data"][0]["candidate"] = "A\ud800B"
        monkeypatch.setitem(RECORDED, "/v1/elections/1824", body)
        tree, _ = render("/election/<year>", monkeypatch)
        assert of_type(tree, "Table"), "the page degraded"
        file = download(tree, "election-states")
        assert "A?B" in [r["candidate"] for r in file.rows]

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
            # A spreadsheet may trim leading whitespace before evaluating.
            (" =1", "' =1"),
            ("\xa0=1", "'\xa0=1"),
            ("\u3000+1", "'\u3000+1"),
            ("\n-1", "'\n-1"),
            ("a =1", "a =1"),
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

    def test_the_census_line_and_the_notes_have_their_places(self) -> None:
        given = provenance()
        given.update(
            ec_source_name="EC-NAME",
            ec_license="EC-LIC",
            ec_license_url="https://ec.example",
            census_source_name="CB-NAME",
            census_license="CB-LIC",
            census_license_url="https://cb.example",
            snapshot_version="v-123",
        )
        given["coverage"] = {
            "year_min": 1111,
            "year_max": 2222,
            "pv_year_min": 1333,
            "pv_year_max": 1444,
        }
        lines = export.preamble(("year", "population"), given, "URL", ("N1", "N2"))
        assert lines == [
            "Electoral votes: EC-NAME (EC-LIC; https://ec.example)",
            "Population: CB-NAME (CB-LIC; https://cb.example)",
            "Data snapshot: v-123",
            "Electoral votes cover 1111–2222",
            "View: URL",
            "N1",
            "N2",
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

    @pytest.mark.parametrize(
        ("key", "path", "table", "other"),
        [
            (
                "/state/<usps>",
                "/v1/states/GA/per-capita",
                "state-per-capita",
                "state-history",
            ),
            (
                "/election/<year>",
                "/v1/elections/1824/per-capita",
                "election-per-capita",
                "election-states",
            ),
        ],
    )
    def test_a_per_capita_table_reads_its_own_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
        key: str,
        path: str,
        table: str,
        other: str,
    ) -> None:
        # The recorded pair carry identical provenance, so only a changed copy tells
        # which response a file read.
        per_capita = copy.deepcopy(RECORDED[path])
        per_capita["meta"]["provenance"]["snapshot_version"] = "OWN-RESPONSE"
        monkeypatch.setitem(RECORDED, path, per_capita)
        tree, _ = render(key, monkeypatch)
        assert "Data snapshot: OWN-RESPONSE" in download(tree, table).lines
        assert "Data snapshot: OWN-RESPONSE" not in download(tree, other).lines

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
        text = export.BOM + "#,a b%–\r\n\r\nx\r\n"
        encoded = export.href(text).removeprefix(export.DATA_URL_PREFIX)
        assert unquote_to_bytes(encoded) == text.encode("utf-8")
        tree, _ = render("/election/<year>", monkeypatch, year="1872")
        for link in links(tree).values():
            encoded = link.href.removeprefix(export.DATA_URL_PREFIX)
            assert not set(encoded) & {"#", " ", "\n", "\r", ","}
            file = Csv(link.href)
            assert file.raw.startswith(export.BOM.encode())
            assert file.raw.count(export.BOM.encode()) == 1
            # Only a preamble row starts with a bare "#".
            body = file.raw.removeprefix(export.BOM.encode()).split(b"\r\n")
            marked = [line for line in body if line.startswith(b"#")]
            assert len(marked) == len(file.preamble)
            assert all(line.startswith(b"#,") for line in marked)

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
        assert export.row(["a,b", 'say "x"', "line\nbreak", "plain", "a #1"]) == (
            '"a,b","say ""x""","line\nbreak",plain,"a #1"\r\n'
        )

    def test_a_hash_in_a_cell_never_cuts_its_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = copy.deepcopy(RECORDED["/v1/elections/1824"])
        body["data"][0]["candidate"] = "Lincoln #1"
        monkeypatch.setitem(RECORDED, "/v1/elections/1824", body)
        tree, _ = render("/election/<year>", monkeypatch)
        file = download(tree, "election-states")
        frame = pd.read_csv(
            io.BytesIO(file.raw), comment="#", encoding="utf-8-sig", dtype=str
        )
        assert len(frame) == len(file.rows)
        hashed = frame[frame["candidate"] == "Lincoln #1"]
        assert len(hashed) == 1
        assert hashed.iloc[0]["state_usps"] == body["data"][0]["state_usps"]
        assert "Lincoln #1" in [r["candidate"] for r in file.rows]


# --- request budget and D070(b) -------------------------------------------------------


class TestRequestBudget:
    def test_a_render_reads_what_it_read_before(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, before in READS_BEFORE.items():
            _, reads = render(key, monkeypatch)
            assert reads == before, key

    def test_no_callback_or_route_serves_a_download(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A download is the link's own ``data:`` URL: no callback output, route or
        ``dcc.Download`` serves one (with ``link_problems``' check that every link is
        a ``data:`` URL)."""
        # A first request makes Dash register every callback in its map.
        assert appmod.server.test_client().get("/elections").status_code == 200
        outputs = {str(c.get("output")) for c in dash._callback.GLOBAL_CALLBACK_LIST}
        assert outputs | set(appmod.app.callback_map) == CALLBACK_OUTPUTS
        assert {r.rule for r in appmod.server.url_map.iter_rules()} == ROUTES
        assert of_type(appmod.app.layout, "Download") == []
        for tree in all_pages(monkeypatch).values():
            assert of_type(tree, "Download") == []
