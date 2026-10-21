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
    "candidate-history": "/candidate/<slug>",
}

#: Each page's reads before #309, recorded on ``main`` at 72312da with
#: :class:`RecordingClient` at the registry's concrete values: the download adds none.
#: The candidate history (#331) was built with its download, so its entry pins its
#: reads rather than recording them from before one; that a download makes no request
#: is guarded by ``test_the_shared_modules_read_no_api`` and ``TestRequestBudget``.
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
    "/candidate/<slug>": [
        "/v1/candidates",
        "/v1/elections",
        "/v1/candidates/andrew-jackson",
    ],
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
    "candidate-url.search",
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
        built = components.table(
            [], lambda r: html.Tr(), ("year",), "t", dl, notes=("N1", "N2")
        )
        assert links(built) == {} and of_type(built, "Table") == []
        # The empty sentence, then the notes: a note can explain the empty result.
        assert [p.children for p in built] == [components.NO_ROWS, "N1", "N2"]


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
            # The candidate history (#331): a range and a state the candidate's rows do
            # not name both fall back, so the view is unfiltered; one of their years and
            # one of their states are named.
            (
                "/candidate/<slug>",
                "year_from=1824&year_to=1828&state=AZ",
                "candidate-history",
                "/candidate/andrew-jackson",
            ),
            (
                "/candidate/<slug>",
                "year_from=1828&year_to=1828&state=GA",
                "candidate-history",
                "/candidate/andrew-jackson?state=GA&year_from=1828&year_to=1828",
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
            # Each status filter under its own key (closed values: kept even when no
            # row has them).
            (
                "/election/<year>",
                "electoral_count_status=disputed&pv_status=popular_vote",
                # T3 is never filtered, so its file names the view however few rows
                # T2 keeps.
                "election-nation",
                "/election/1824?electoral_count_status=disputed&pv_status=popular_vote",
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
                    "nominating_party",
                    "state_electoral_votes",
                    "electoral_votes",
                    "electoral_votes_counted",
                    "electoral_count_status",
                    "pv_status",
                    "popular_votes",
                    "electoral_count_status_reason",
                    "nominating_party_note",
                    "nominating_party_source",
                    "state_usps",
                    "candidate_slug",
                    "year",
                ),
            ),
            (
                "/election/<year>",
                "election-nation",
                (
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
                    "ec_share_hybrid",
                    "hybrid_score",
                    "nominating_party_note",
                    "nominating_party_source",
                    "candidate_slug",
                    "year",
                ),
            ),
            (
                "/election/<year>",
                "election-per-capita",
                ("state", *labels.PER_CAPITA_FIELDS, "state_usps", "year"),
            ),
            (
                "/state/<usps>",
                "state-history",
                (
                    "year",
                    "candidate",
                    "nominating_party",
                    "state_electoral_votes",
                    "electoral_votes",
                    "electoral_votes_counted",
                    "electoral_count_status",
                    "pv_status",
                    "popular_votes",
                    "electoral_count_status_reason",
                    "nominating_party_note",
                    "nominating_party_source",
                    "candidate_slug",
                    "state_usps",
                ),
            ),
            (
                "/state/<usps>",
                "state-per-capita",
                ("year", *labels.PER_CAPITA_FIELDS, "state_usps"),
            ),
            (
                "/candidate/<slug>",
                "candidate-history",
                (
                    "year",
                    "state",
                    "nominating_party",
                    "state_electoral_votes",
                    "electoral_votes",
                    "electoral_votes_counted",
                    "electoral_count_status",
                    "pv_status",
                    "popular_votes",
                    "electoral_count_status_reason",
                    "nominating_party_note",
                    "nominating_party_source",
                    "state_usps",
                    "candidate_slug",
                ),
            ),
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
            "candidate-history-csv": "candidate-andrew-jackson-history.csv",
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
        # Breckinridge and Bell carry no party row (#389): an empty cell, as served.
        nulls = {
            r["candidate"] for r in states.rows if r["nominating_party"] == ""
        }
        assert {"John C. Breckinridge", "John Bell"} <= nulls
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
        assert labels.PARTY_NULL_NOTE in states.lines

    def test_the_state_history_keeps_the_served_party_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#389: the page shows a party's display form; the file keeps the code, and
        the party's per-row source and note travel with it."""
        from usvote.party import NOMINATING_PARTIES, PARTY_SOURCES

        tree, _ = render("/state/<usps>", monkeypatch)
        history = download(tree, "state-history")
        codes = {r["nominating_party"] for r in history.rows} - {""}
        assert codes and codes <= set(NOMINATING_PARTIES)
        assert {r["nominating_party_source"] for r in history.rows} - {""} <= set(
            PARTY_SOURCES
        )
        assert set(labels.NOMINATING_PARTY.values()).isdisjoint(codes)

    def test_the_state_history_explains_its_null_party(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/state/<usps>", monkeypatch)
        history = download(tree, "state-history")
        # the premise: a null party
        assert "" in {r["nominating_party"] for r in history.rows}
        for note in (labels.PARTY_NOTE, labels.PARTY_NULL_NOTE):
            assert note in history.lines
            assert note in [p.children for p in of_type(tree, "P")]

    def test_the_candidate_history_carries_the_party_notes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/candidate/<slug>", monkeypatch)
        history = download(tree, "candidate-history")
        for note in (labels.PARTY_NOTE, labels.PARTY_NULL_NOTE):
            assert note in history.lines
            assert note in [p.children for p in of_type(tree, "P")]

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

    def test_the_national_file_carries_t3_s_notes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T3's notes (#352 adds the second share's) show under it and travel in its
        file, as every table note does."""
        tree, _ = render("/election/<year>", monkeypatch, year="1872")
        lines = download(tree, "election-nation").lines
        shown = [p.children for p in of_type(tree, "P")]
        for note in (
            labels.PARTY_NOTE,
            labels.PARTY_NULL_NOTE,
            labels.HYBRID_NOTE,
            labels.EC_SHARE_HYBRID_NOTE,
        ):
            assert note in lines
            assert note in shown

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
            "Data version: v-123",
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
            "Data version: v-123",
            "Electoral votes cover 1111–2222",
            "View: URL",
            "N1",
            "N2",
            export.NULL_LINE,
        ]

    def test_the_sources_keep_the_footer_s_order(self) -> None:
        """No table yet carries both census and party fields; the order is pinned for
        the one that will."""
        every = {
            *export.POPULAR_VOTE_FIELDS,
            *export.CENSUS_FIELDS,
            *export.NOMINATING_PARTY_FIELDS,
        }
        assert export.sources(every) == [
            export.EC_SOURCE,
            export.PV_SOURCE,
            export.CENSUS_SOURCE,
            export.USGOV_SOURCE,
        ]

    @pytest.mark.parametrize(
        ("table", "pv", "census", "usgov"),
        [
            ("elections-table", True, False, False),
            ("election-states", True, False, True),
            ("election-nation", True, False, True),
            ("election-per-capita", False, True, False),
            ("state-history", True, False, True),
            ("state-per-capita", False, True, False),
            ("candidate-history", True, False, True),
        ],
    )
    def test_each_table_names_the_sources_it_carries(
        self,
        monkeypatch: pytest.MonkeyPatch,
        table: str,
        pv: bool,
        census: bool,
        usgov: bool,
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
        # The party's curated source, labeled by what it supplies (#389).
        assert (
            any(
                x.startswith(
                    "Parties the National Archives does not print: "
                    f"{meta['usgov_source_name']} ("
                )
                for x in lines
            )
            is usgov
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
        assert "Data version: OWN-RESPONSE" in download(tree, table).lines
        assert "Data version: OWN-RESPONSE" not in download(tree, other).lines

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
        sets = (
            export.EC_FIELDS,
            export.POPULAR_VOTE_FIELDS,
            export.CENSUS_FIELDS,
            export.NOMINATING_PARTY_FIELDS,
        )
        for i, a in enumerate(sets):
            for b in sets[i + 1 :]:
                assert not a & b
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
        assert export.row(
            ["a,b", 'say "x"', "line\nbreak", "plain", "a #1", "lone\rcr"]
        ) == ('"a,b","say ""x""","line\nbreak",plain,"a #1","lone\rcr"\r\n')

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


# --- no raw values on a page (#355) ---------------------------------------------------

#: The recorded years of the one-election view, each rendered whole: read from the
#: recordings, so a newly recorded year is scanned too.
ELECTION_YEARS = tuple(
    sorted(
        m.group(1)
        for path in RECORDED
        if (m := re.fullmatch(r"/v1/elections/([0-9]{4})", path))
    )
)
# Non-vacuous: an empty tuple would make pytest skip the scan rather than fail it.
assert {"1824", "1896", "2024"} <= set(ELECTION_YEARS), ELECTION_YEARS

#: A value no cell has wording for: an underscore, so a raw rendering of it fails
#: :func:`raw_values` wherever it lands.
SENTINEL = "zz_sentinel"


def reader_texts(node: Any) -> list[str]:
    """Every string a reader sees in a rendered tree: children, a dropdown's option
    labels and its placeholder. ``Code`` is exempt, since a field name is shown as one
    where the page presents it as a field name (a glossary's names, the data version),
    and so are ``title`` tooltips: a header's is its field name by design, and the
    help-text constants are scanned by ``TestWordingRules`` instead."""
    if node is None:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, (int, float)):
        return [str(node)]
    if isinstance(node, (list, tuple)):
        return [t for child in node for t in reader_texts(child)]
    if isinstance(node, Component):
        if type(node).__name__ == "Code":
            return []
        own: list[str] = []
        for option in getattr(node, "options", None) or []:
            label = option.get("label") if isinstance(option, dict) else option
            own += reader_texts(label)
        placeholder = getattr(node, "placeholder", None)
        if isinstance(placeholder, str):
            own.append(placeholder)
        return own + reader_texts(getattr(node, "children", None))
    raise TypeError(f"unexpected node {node!r}")


def raw_values(tree: Any) -> list[str]:
    """Reader texts that are a raw value (#355): any text carrying an underscore, and
    any that is exactly a served code (a party, a party's source, or a closed-vocabulary
    value, which may be one word: ``counted``, ``covered``, ``whig``)."""
    from usvote.count_status import COUNT_STATUS_VALUES
    from usvote.mit.transform import EC_GETTER_PARTIES
    from usvote.party import NOMINATING_PARTIES, PARTY_SOURCES
    from usvote.pv.status import PV_STATUS_VALUES
    from usvote.snapshot_schema import (
        PER_CAPITA_BOUNDARY_BASIS_VALUES,
        PER_CAPITA_COVERAGE_VALUES,
    )

    codes = {
        *EC_GETTER_PARTIES,
        *NOMINATING_PARTIES,
        *PARTY_SOURCES,
        *PV_STATUS_VALUES,
        *COUNT_STATUS_VALUES,
        *PER_CAPITA_BOUNDARY_BASIS_VALUES,
        *PER_CAPITA_COVERAGE_VALUES,
    }
    return [text for text in reader_texts(tree) if "_" in text or text.strip() in codes]


def cells_reading(tree: Any, text: str) -> list[Any]:
    """Every ``Td`` and ``Dd`` whose text is ``text``."""
    return [
        cell
        for kind in ("Td", "Dd")
        for cell in of_type(tree, kind)
        if "".join(reader_texts(cell.children)) == text
    ]


def tables_in(tree: Any) -> dict[str, Any]:
    """Every table in a tree, by id."""
    return {t.id: t for t in of_type(tree, "Table") if getattr(t, "id", None)}


def doctor(monkeypatch: pytest.MonkeyPatch, path: str, change: Any) -> None:
    """Serve ``path`` changed by ``change`` for the rest of the test."""
    body = copy.deepcopy(RECORDED[path])
    change(body)
    monkeypatch.setitem(RECORDED, path, body)


#: Every field a ``labels`` function words, per row kind, by public field name: each is
#: doctored with :data:`SENTINEL`, except a name, which is open vocabulary (a text
#: sentinel would rightly be shown) and gets a non-text value instead. The party is a
#: closed vocabulary since #389, so it takes the sentinel too, and its row gets a text
#: note, so the unrecognized cell's help text is checked to win over a row note.
STATE_ROW_FIELDS = (
    "nominating_party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
)
SUMMARY_ROW_FIELDS = (
    "nominating_party",
    "national_electoral_votes",
    "national_electoral_votes_counted",
    "national_electoral_denominator",
    "electoral_rank",
    "took_office",
    "national_pv_votes",
    "ec_share_full",
    "pv_share",
    "ec_share_hybrid",
    "hybrid_score",
)
PER_CAPITA_ROW_FIELDS = (
    "governing_census_year",
    "state_electoral_votes",
    "population",
    "boundary_basis",
    "coverage",
    "persons_per_electoral_vote",
)
PANEL_WORDED_FIELDS = (
    "pv_flip",
    "hybrid_flip",
    "ec_margin",
    "pv_margin",
    "hybrid_margin",
    "ec_determinative",
    "pv_coverage",
)
PANEL_NAME_FIELDS = ("ec_winner", "pv_winner", "hybrid_winner")


#: A row note on each doctored row: text with no underscore, so it is no raw value.
DOCTORED_NOTE = "A doctored note."


def _row(*fields: str, **others: Any) -> Any:
    """Doctor the first row: each of ``fields`` to :data:`SENTINEL`, plus ``others``."""

    def change(body: dict[str, Any]) -> None:
        body["data"][0].update(dict.fromkeys(fields, SENTINEL), **others)

    return change


def _election(body: dict[str, Any]) -> None:
    _row(*STATE_ROW_FIELDS, nominating_party_note=DOCTORED_NOTE)(body)
    body["summary"][0].update(
        dict.fromkeys(SUMMARY_ROW_FIELDS, SENTINEL), nominating_party_note=DOCTORED_NOTE
    )
    body["election"].update(
        dict.fromkeys(PANEL_WORDED_FIELDS, SENTINEL),
        **dict.fromkeys(PANEL_NAME_FIELDS, 7),
    )


#: Per page: the responses to doctor, each with every field a ``labels`` function
#: words in one row of each table (and the panel) set to a value no cell has wording
#: for, so every such cell is exercised.
DOCTORED: dict[str, tuple[dict[str, str], dict[str, Any]]] = {
    "/elections": (
        {},
        {"/v1/elections": _row("has_popular_vote", "candidate_count")},
    ),
    "/election/<year>": (
        {"year": "2016"},
        {
            "/v1/elections/2016": _election,
            "/v1/elections/2016/per-capita": _row(*PER_CAPITA_ROW_FIELDS),
        },
    ),
    "/state/<usps>": (
        {"usps": "GA"},
        {
            "/v1/states/GA": _row(*STATE_ROW_FIELDS, nominating_party_note=DOCTORED_NOTE),
            "/v1/states/GA/per-capita": _row(*PER_CAPITA_ROW_FIELDS),
        },
    ),
    "/candidate/<slug>": (
        {"slug": "andrew-jackson"},
        {
            "/v1/candidates/andrew-jackson": _row(
                *STATE_ROW_FIELDS, nominating_party_note=DOCTORED_NOTE
            )
        },
    ),
}


#: How many cells read "Unrecognized value" on each doctored page, per table (and the
#: panel): one per doctored field (a state row's popular-vote cell reads it too, its
#: cause being the doctored status). Derived from the field lists above, which a new
#: worded column must join for its cell to be checked.
UNRECOGNIZED_CELLS = {
    "/elections": {"elections-table": 2},
    "/election/<year>": {
        "election-states": len(STATE_ROW_FIELDS) + 1,  # popular votes
        "election-nation": len(SUMMARY_ROW_FIELDS),
        "election-per-capita": len(PER_CAPITA_ROW_FIELDS),
        "election-panel": len(PANEL_WORDED_FIELDS) + len(PANEL_NAME_FIELDS),
    },
    "/state/<usps>": {
        "state-history": len(STATE_ROW_FIELDS) + 1,
        "state-per-capita": len(PER_CAPITA_ROW_FIELDS),
    },
    "/candidate/<slug>": {"candidate-history": len(STATE_ROW_FIELDS) + 1},
}


class TestOnePartyPerRow:
    """AC5 of #389, structurally: no header, label, field set or download names the
    popular-vote source's ``party``. Which field a party cell reads is pinned by the
    pre-1976 rows (MIT's ``party`` is null then): T2/T3 in
    ``test_dashboard_election.py``, T4 in ``test_dashboard_state.py``, T5 in
    ``test_dashboard_candidate.py``."""

    def test_no_page_shows_and_no_file_exports_the_popular_vote_party(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert "party" not in labels.LABELS
        for name in ("EC_FIELDS", "POPULAR_VOTE_FIELDS", "CENSUS_FIELDS"):
            assert "party" not in getattr(export, name), name
        trees = all_pages(monkeypatch)
        party_tables = 0
        for key, tree in trees.items():
            titles = {getattr(th, "title", None) for th in of_type(tree, "Th")}
            assert "party" not in titles, key
            for link in links(tree).values():
                header = Csv(link.href).header
                assert "party" not in header, key
                party_tables += "nominating_party" in header
        assert party_tables >= 4  # T2, T3, T4 and T5 each carry the party

    def test_a_no_nomination_row_keeps_its_code_and_names_its_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC3 in the download (#389), and #388's AC3: the code as served, the curated
        source per row, and the preamble's line for it, for the real catalog's 2016
        Colin Powell row (its note's colon and commas exercise the CSV's quoting); and a
        null beside it, Ron Paul's three fields set to null, reading as empty cells.
        Both are doctored here, never in a recorded file, so a re-recorded fixture
        cannot quietly change either premise. Test-only import of
        ``usvote.party_catalog`` (stdlib-only; D070(b) binds runtime modules)."""
        from usvote.party_catalog import CURATED_BY_KEY

        powell_row = CURATED_BY_KEY[(2016, "Colin Powell")]

        def change(body: dict[str, Any]) -> None:
            for row in [*body["data"], *body["summary"]]:
                if row["candidate"] == "Colin Powell":
                    row.update(
                        nominating_party=powell_row.party,
                        nominating_party_source="USGOV",
                        nominating_party_note=powell_row.note,
                    )
                if row["candidate"] == "Ron Paul":
                    row.update(
                        nominating_party=None,
                        nominating_party_source=None,
                        nominating_party_note=None,
                    )

        doctor(monkeypatch, "/v1/elections/2016", change)
        tree, _ = render("/election/<year>", monkeypatch, year="2016")
        for table in ("election-states", "election-nation"):
            file = download(tree, table)
            powell = [r for r in file.rows if r["candidate"] == "Colin Powell"]
            assert powell, table
            assert {r["nominating_party"] for r in powell} == {"no_nomination"}
            assert {r["nominating_party_source"] for r in powell} == {"USGOV"}
            assert {r["nominating_party_note"] for r in powell} == {powell_row.note}
            paul = [r for r in file.rows if r["candidate"] == "Ron Paul"]
            assert paul, table
            for field in (
                "nominating_party", "nominating_party_source", "nominating_party_note"
            ):
                assert {r[field] for r in paul} == {""}, (table, field)
            assert any(
                line.startswith("Parties the National Archives does not print: ")
                for line in file.lines
            ), table


class TestNoRawValues:
    """The glossary's no-raw-values rule over whole rendered pages (#355), as far as
    rendered text shows it (children, dropdown labels and placeholders; not tooltips).
    Recorded data reaches no fallback, so each table page is also rendered from bodies
    doctored as ``DOCTORED`` says: every doctored cell then reads "Unrecognized value"
    with its help text, never the raw value, and ``UNRECOGNIZED_CELLS`` pins how many
    per table, so a doctored cell that reads otherwise fails. Candidate and state names
    are shown as served (#367)."""

    def test_every_registered_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pages = all_pages(monkeypatch)
        assert set(TABLES) <= {i for tree in pages.values() for i in tables_in(tree)}
        assert {key: raw_values(tree) for key, tree in pages.items()} == dict.fromkeys(
            pages, []
        )

    @pytest.mark.parametrize("year", ELECTION_YEARS)
    def test_every_recorded_election(
        self, year: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/election/<year>", monkeypatch, year=year)
        on_page = {t for t, key in TABLES.items() if key == "/election/<year>"}
        assert on_page <= set(tables_in(tree))  # the premise: no degraded page
        assert raw_values(tree) == []

    @pytest.mark.parametrize("key", list(DOCTORED))
    def test_a_doctored_page_shows_no_raw_value_and_notes_every_unrecognized_cell(
        self, key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        values, changes = DOCTORED[key]
        for path, change in changes.items():
            doctor(monkeypatch, path, change)
        tree, _ = render(key, monkeypatch, **values)
        tables = tables_in(tree)
        on_page = {t for t, page in TABLES.items() if page == key}
        assert on_page <= set(tables)  # the premise: no degraded page
        assert raw_values(tree) == []
        unknown = cells_reading(tree, labels.UNRECOGNIZED)
        assert unknown
        assert [getattr(c, "title", None) for c in unknown] == [
            labels.UNRECOGNIZED_NOTE
        ] * len(unknown)
        regions = {
            **tables,
            **{
                d.id: d
                for d in of_type(tree, "Div")
                if getattr(d, "id", None) == "election-panel"
            },
        }
        assert set(UNRECOGNIZED_CELLS[key]) >= on_page
        assert {
            region: len(cells_reading(regions[region], labels.UNRECOGNIZED))
            for region in UNRECOGNIZED_CELLS[key]
        } == UNRECOGNIZED_CELLS[key]
        assert len(unknown) == sum(UNRECOGNIZED_CELLS[key].values())

    def test_the_scan_fails_what_it_should(self) -> None:
        # Non-vacuity: a raw code in a cell or a dropdown fails, one-word codes too; a
        # field name in a Code does not.
        assert raw_values(html.Td("mystery_code")) == ["mystery_code"]
        assert raw_values(html.Td(["Party: ", "REPUBLICAN"])) == ["REPUBLICAN"]
        assert raw_values(html.Td("counted")) == ["counted"]
        assert raw_values(html.Td(html.Code("ec_winner"))) == []
        dropdown = dash.dcc.Dropdown(
            options=[{"label": "popular_vote", "value": "popular_vote"}],
            placeholder="covered",
        )
        assert raw_values(dropdown) == ["popular_vote", "covered"]
