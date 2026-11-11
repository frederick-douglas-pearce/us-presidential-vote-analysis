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
from urllib.parse import unquote_to_bytes, urlsplit

import dash
import pandas as pd
import pytest
from dash import html
from dash.development.base_component import Component

from explore import api, charts, components, export, labels
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
    "election-states": "/election/<year>/states",
    "election-nation": "/election/<year>",
    "election-per-capita": "/election/<year>/per-capita",
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
    "/not-found-404": [],  # the custom-404 page reads no data (#325)
    "/elections": ["/v1/elections"],
    # #465 split the one-election view's reads across its three pages: each fills one
    # path (the per-capita page reads no /v1/elections/{year}), and none adds a read.
    "/election/<year>": ["/v1/elections", "/v1/elections/1824", "/v1/elections"],
    "/election/<year>/states": ["/v1/elections", "/v1/elections/1824", "/v1/elections"],
    "/election/<year>/per-capita": [
        "/v1/elections",
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
#: Pages router's two, each filtered page's URL (the election per-capita page's since
#: #465), the theme callback's store and its
#: three buttons' pressed states (#359, #447), the site navigation's marker (#448), and
#: every chart's figure and visibility (#432, one MATCH callback). A download adds none.
CALLBACK_OUTPUTS = {
    '{"chart":["MATCH"],"type":"explore-chart-mount"}.children',
    '..{"chart":["MATCH"],"type":"explore-chart-graph"}.figure'
    '...{"chart":["MATCH"],"type":"explore-chart-graph"}.style..',
    ".._pages_content.children..._pages_store.data..",
    "..theme-in-effect.data...theme-dark.aria-pressed...theme-auto.aria-pressed"
    "...theme-light.aria-pressed..",
    "site-nav.data-current",
    "_pages_dummy.children",
    "elections-url.search",
    "election-url.search",
    "election-per-capita-url.search",
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


def chart_render(
    build: Callable[[], Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, list[tuple[str, Any]]]:
    """``build()``'s tree, and each chart ``components.chart`` built during that call
    with the component it returned (recorded through a wrapper; pages call it by
    attribute)."""
    built: list[tuple[str, Any]] = []
    real = components.chart

    def recording(*args: Any, **kwargs: Any) -> Any:
        figure = real(*args, **kwargs)
        built.append((args[0] if args else kwargs["chart_id"], figure))
        return figure

    monkeypatch.setattr(components, "chart", recording)
    tree = build()
    monkeypatch.setattr(components, "chart", real)
    return tree, built


def _contains(node: Any, wanted: str) -> bool:
    """Whether a component with id ``wanted`` sits in ``node``'s subtree."""
    if isinstance(node, (list, tuple)):
        return any(_contains(child, wanted) for child in node)
    if isinstance(node, Component):
        return getattr(node, "id", None) == wanted or _contains(
            getattr(node, "children", None), wanted
        )
    return False


def components_in(node: Any) -> list[Any]:
    """Every component in a rendered tree, depth-first, through ``children`` only (as
    ``of_type`` walks)."""
    if isinstance(node, (list, tuple)):
        return [c for child in node for c in components_in(child)]
    if isinstance(node, Component):
        return [node, *components_in(getattr(node, "children", None))]
    return []


def mount_points(tree: Any) -> list[Any]:
    """Every chart mount point in ``tree`` (#452): a component of any type whose pattern
    id is of ``charts.MOUNT_TYPE``."""
    return [
        c
        for c in components_in(tree)
        if isinstance(getattr(c, "id", None), dict)
        and c.id.get("type") == charts.MOUNT_TYPE
    ]


def graphs(tree: Any) -> list[Any]:
    """Every ``dcc.Graph`` in ``tree`` (#452), matched as the renderer matches one, by
    dcc's namespace and type, so a subclass is one too."""
    graph = (dash.dcc.Graph._namespace, dash.dcc.Graph._type)
    return [
        c
        for c in components_in(tree)
        if (getattr(c, "_namespace", None), getattr(c, "_type", None)) == graph
    ]


def chart_problems(
    tree: Any, key: str, built: list[tuple[str, Any]], success: str
) -> list[str]:
    """What is wrong with the charts in one page's ``tree`` (#432, #452): any
    ``dcc.Graph`` at all (a graph is only ever put in a mount point by the mount
    callback, once plotly.js has loaded, so one in a layout would bring Dash's
    blocked-CDN loop back); a chart mount point that is not the one inside a figure
    ``components.chart`` returned (compared by identity, so a hand-built mount point
    reusing a built chart's id is caught), one with an unregistered ID, one on a page
    other than its registry row's, one rendered without its companion table; a chart
    naming a token that is not a declared color token; and a success marker that is a
    chart or sits inside one. It walks ``children`` only, so a graph or mount point in
    another component-valued prop is not seen here; a runtime module that builds a graph
    anywhere is the lint's (``TestMountCallback.test_no_runtime_module_builds_a_graph``).

    It reads the one tree it is given: ``TestEveryChart`` hands it each page's default
    render, and each chart page's renders under :data:`CHART_QUERIES` (#435, D093(c)),
    so a companion table that a filter empties fails it."""
    from tests.unit.test_dashboard_theme import TOKENS

    problems = []
    live = {
        charts.dom_id(chart_id): chart_id
        for chart_id, row in charts.CHARTS.items()
        if not row.retired
    }
    problems += [
        f"{key}: a dcc.Graph in a rendered layout: {getattr(g, 'id', None)}"
        for g in graphs(tree)
    ]
    from_builder = {id(m) for _, figure in built for m in mount_points(figure)}
    tables = {getattr(t, "id", None) for t in of_type(tree, "Table")}
    for mount in mount_points(tree):
        mount_id = mount.id
        dom = mount_id.get("chart")
        if id(mount) not in from_builder:
            problems.append(
                f"{key}: a chart mount point not built by components.chart: {mount_id}"
            )
        if dom not in live:
            problems.append(f"{key}: a chart with an unregistered ID: {mount_id}")
            continue
        row = charts.CHARTS[live[dom]]
        if row.page != key:
            problems.append(f"{key}: {live[dom]} belongs on {row.page}")
        if row.table not in tables:
            problems.append(f"{key}: {live[dom]} has no companion table {row.table}")
    for store in of_type(tree, "Store"):
        store_id = getattr(store, "id", None)
        if isinstance(store_id, dict) and store_id.get("type") == charts.SOURCE_TYPE:
            named = charts.tokens_named(getattr(store, "data", None) or {})
            unknown = sorted(named - set(TOKENS) - {charts.FONT_TOKEN})
            if unknown:
                problems.append(f"{key}: {store_id['chart']} names no token {unknown}")
    for figure in of_type(tree, "Figure"):
        figure_id = getattr(figure, "id", None)
        if figure_id in live and (figure_id == success or _contains(figure, success)):
            problems.append(f"{key}: the success marker is inside chart {figure_id}")
    return problems


#: A test figure (#432): two bar series told apart by a pattern, with every kind of
#: figure text the raw-value scan reads, all plain.
TEST_FIGURE: dict[str, Any] = {
    "data": [
        {
            "type": "bar",
            "name": "Electoral share",
            "x": ["A", "B"],
            "y": [0.5, 0.4],
            "marker": {"color": "var(--chart-1)"},
            "hovertext": ["A: 50.0% of electors", "B: 40.0% of electors"],
            "hovertemplate": "%{hovertext}<extra></extra>",
        },
        {
            "type": "bar",
            "name": "Popular-vote share",
            "x": ["A", "B"],
            "y": [0.48, 0.45],
            "marker": {"color": "var(--chart-2)", "pattern": {"shape": "/"}},
            "hovertemplate": "%{customdata.pv_share} of votes<extra>%{fullData.name}</extra>",
            "customdata": [{"pv_share": "48.0%"}, {"pv_share": "45.0%"}],
        },
    ],
    "layout": {
        "title": {"text": "Each candidate's two shares"},
        "xaxis": {"title": {"text": "Candidate"}, "ticktext": ["A", "B"]},
        "yaxis": {"title": {"text": "Share"}},
        "legend": {"title": {"text": "Measure"}},
        "annotations": [{"text": "Majority", "x": 0, "y": 0.5}],
    },
}


#: Each chart page's filtered renders (#435, D093(c)): its path values, a query, and
#: whether the query names a value the page's rows hold (``filtered``) or one they do
#: not (``absent``). Hand-written, so a page's own filters are listed by the story that
#: adds its chart: ``test_every_chart_page_with_a_filter_lists_its_queries`` fails a
#: live chart page with a ``query=`` parser that lists no query of each kind. The
#: overview reads no filter, so its entry checks a client-side route carrying one.
CHART_QUERIES: dict[str, list[tuple[dict[str, str], str, str]]] = {
    "/election/<year>": [({}, "state=GA", "filtered")],
    "/election/<year>/per-capita": [
        ({}, "state=GA", "filtered"),
        # No California in 1824: the filter falls back to every state.
        ({}, "state=CA", "absent"),
        # 1864: zero allotments, so markers beside the selected state's row.
        ({"year": "1864"}, "state=GA", "filtered"),
        ({"year": "1864"}, "state=ZZ", "absent"),
    ],
}


#: Each chart's selected-item trace, by the chart's DOM id and the trace's name (#435,
#: D093(b)): the one trace a filter may add. Hand-written; a chart story that marks a
#: selection adds its row.
SELECTION_TRACES: dict[str, str] = {charts.dom_id("C3"): labels.C3_SELECTED}


def chart_figures(tree: Any) -> dict[str, dict[str, Any]]:
    """Each chart's unresolved figure in ``tree``, by the chart's DOM id (its source
    store's)."""
    return {
        store.id["chart"]: store.data
        for store in of_type(tree, "Store")
        if isinstance(getattr(store, "id", None), dict)
        and store.id.get("type") == charts.SOURCE_TYPE
    }


def table_row_count(tree: Any, table_id: str) -> int:
    """How many body rows the table ``table_id`` renders in ``tree`` (0 when absent)."""
    tables = [t for t in of_type(tree, "Table") if getattr(t, "id", None) == table_id]
    return sum(len(of_type(t, "Tr")) - 1 for t in tables)


# --- coverage is structural -----------------------------------------------------------


class TestEveryChart:
    """Every chart is built by ``components.chart`` (#432), with a registered ID, on its
    registry row's page, beside its companion table, and is never a page's success
    marker; and no layout holds a ``dcc.Graph`` (#452). No page renders a chart before
    C1 (#433); the checks run on every page now and on test registries below."""

    def test_every_rendered_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for page in dash.page_registry.values():
            key = page_key(page)
            tree, built = chart_render(
                functools.partial(lambda k: render(k, monkeypatch)[0], key), monkeypatch
            )
            # The custom-404 page reads no data and declares no success marker.
            success = page.get("success", "")
            assert chart_problems(tree, key, built, success) == [], key

    @pytest.mark.parametrize(
        ("key", "values", "query", "kind"),
        [
            (key, values, query, kind)
            for key, entries in CHART_QUERIES.items()
            for values, query, kind in entries
        ],
    )
    def test_every_chart_page_under_its_listed_queries(
        self,
        monkeypatch: pytest.MonkeyPatch,
        key: str,
        values: dict[str, str],
        query: str,
        kind: str,
    ) -> None:
        """#435, D093(c): each chart page rendered under a filter (``filtered``) and
        under one naming a value the rows do not hold (``absent``) passes the same
        checks as its default render, so a filter that emptied a companion table (and
        left a caption pointing at a table that is not rendered) fails here. And the
        filter never narrows a chart (D093(a)): every trace but the chart's selected
        item (:data:`SELECTION_TRACES`) equals the unfiltered render's, as do its row
        labels; a ``filtered`` query on a page with a filter adds exactly one selected
        point and narrows the companion table, and an ``absent`` one does neither."""
        page = page_of(key)
        success = page.get("success", "")
        parser = page.get("query")
        if parser is not None:
            # Not vacuous: the page's own parser keeps the query's filter.
            assert parser(parse(query)), (key, query)
        tree, built = chart_render(
            lambda: render(key, monkeypatch, query, **values)[0], monkeypatch
        )
        assert built, f"{key}{query}: no chart rendered"
        assert chart_problems(tree, key, built, success) == [], (key, query)
        plain = render(key, monkeypatch, **values)[0]
        selects = kind == "filtered" and parser is not None
        filtered, unfiltered = chart_figures(tree), chart_figures(plain)
        assert set(filtered) == set(unfiltered), (key, query)
        for dom, figure in filtered.items():
            name = SELECTION_TRACES.get(dom)
            default = unfiltered[dom]
            kept = [t for t in figure["data"] if name is None or t.get("name") != name]
            marks = [t for t in figure["data"] if name is not None and t.get("name") == name]
            assert kept == default["data"], (key, query, dom)
            assert not [t for t in default["data"] if t.get("name") == name]
            assert figure["layout"]["yaxis"].get("ticktext") == default["layout"][
                "yaxis"
            ].get("ticktext"), (key, query, dom)
            if selects and name is not None:
                assert len(marks) == 1 and len(marks[0]["x"]) == 1, (key, query, dom)
            else:
                assert marks == [], (key, query, dom)
        for row in charts.CHARTS.values():
            if row.retired or row.page != key:
                continue
            shown = table_row_count(tree, row.table)
            everything = table_row_count(plain, row.table)
            assert shown > 0, (key, query, row.table)
            if selects:
                assert shown < everything, (key, query, row.table)
            else:
                assert shown == everything, (key, query, row.table)

    def test_every_chart_page_with_a_filter_lists_its_queries(self) -> None:
        """#435, D093(c): every live chart page whose page reads filters (a ``query=``
        parser) lists at least one filtered query and one naming an absent value in
        :data:`CHART_QUERIES`, so a chart story adding a filtered page lists its own."""
        for chart_id, row in charts.CHARTS.items():
            if row.retired:
                continue
            kinds = {kind for _, _, kind in CHART_QUERIES.get(row.page, [])}
            if page_of(row.page).get("query") is not None:
                assert {"filtered", "absent"} <= kinds, (chart_id, row.page)
            else:
                assert kinds, (chart_id, row.page)

    def test_the_shared_layout_holds_no_graph_and_no_chart(self) -> None:
        # #452: the header, main and stores every page sits in.
        assert graphs(appmod.app.layout) == []
        assert mount_points(appmod.app.layout) == []

    def test_a_mount_point_built_by_hand_or_unregistered_or_any_graph_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            charts, "CHARTS", {"C1": charts.Chart("/elections", "elections-table")}
        )
        by_hand = html.Div(id=charts.mount_id("c2"), role="img")
        # A mount point that is no Div, and a subclass of dcc.Graph (#452's review).
        section = html.Section(id=charts.mount_id("c9"), role="img")

        class MyGraph(dash.dcc.Graph):
            pass

        subclass = MyGraph(id="sub")
        # A mount point reusing the built chart's own id, outside the figure it returned.
        twin = html.Div(id=charts.mount_id("c1"), role="img")
        # A graph anywhere, even with a chart's own graph id (#452).
        graph = dash.dcc.Graph(id=charts.graph_id("c1"))

        def layout() -> Any:
            built = components.chart("C1", TEST_FIGURE, "elections-table", "Caption")
            table = html.Table(id="elections-table")
            plain = dash.dcc.Graph(id="plain")
            return html.Div([built, table, by_hand, plain, twin, graph, section, subclass])

        tree, built = chart_render(layout, monkeypatch)
        assert [chart_id for chart_id, _ in built] == ["C1"]
        assert chart_problems(tree, "/elections", built, "elections") == [
            "/elections: a dcc.Graph in a rendered layout: plain",
            "/elections: a dcc.Graph in a rendered layout: "
            "{'type': 'explore-chart-graph', 'chart': 'c1'}",
            "/elections: a dcc.Graph in a rendered layout: sub",
            "/elections: a chart mount point not built by components.chart: "
            "{'type': 'explore-chart-mount', 'chart': 'c2'}",
            "/elections: a chart with an unregistered ID: "
            "{'type': 'explore-chart-mount', 'chart': 'c2'}",
            "/elections: a chart mount point not built by components.chart: "
            "{'type': 'explore-chart-mount', 'chart': 'c1'}",
            "/elections: a chart mount point not built by components.chart: "
            "{'type': 'explore-chart-mount', 'chart': 'c9'}",
            "/elections: a chart with an unregistered ID: "
            "{'type': 'explore-chart-mount', 'chart': 'c9'}",
        ]

    def test_a_built_chart_passes_and_holds_no_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            charts, "CHARTS", {"C1": charts.Chart("/elections", "elections-table")}
        )

        def layout() -> Any:
            built = components.chart("C1", TEST_FIGURE, "elections-table", "Caption")
            return html.Div([built, html.Table(id="elections-table")])

        tree, built = chart_render(layout, monkeypatch)
        assert len(mount_points(tree)) == 1
        assert graphs(tree) == []
        assert chart_problems(tree, "/elections", built, "elections") == []

    def test_a_chart_naming_an_undeclared_token_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            charts, "CHARTS", {"C1": charts.Chart("/elections", "elections-table")}
        )
        figure = copy.deepcopy(TEST_FIGURE)
        figure["data"][0]["marker"]["color"] = "var(--chart-9)"

        def layout() -> Any:
            built = components.chart("C1", figure, "elections-table", "Caption")
            return html.Div([built, html.Table(id="elections-table")])

        tree, built = chart_render(layout, monkeypatch)
        assert chart_problems(tree, "/elections", built, "elections") == [
            "/elections: c1 names no token ['--chart-9']"
        ]

    def test_a_figure_with_no_id_is_no_chart(self) -> None:
        assert chart_problems(html.Div([html.Figure([])]), "/elections", [], "x") == []

    def test_a_chart_on_the_wrong_page_or_without_its_table_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            charts, "CHARTS", {"C1": charts.Chart("/elections", "elections-table")}
        )

        def layout() -> Any:
            return html.Div(
                [components.chart("C1", TEST_FIGURE, "elections-table", "Caption")]
            )

        tree, built = chart_render(layout, monkeypatch)
        assert chart_problems(tree, "/states", built, "states") == [
            "/states: C1 belongs on /elections",
            "/states: C1 has no companion table elections-table",
        ]

    def test_a_success_marker_inside_a_chart_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            charts, "CHARTS", {"C1": charts.Chart("/elections", "elections-table")}
        )

        def layout() -> Any:
            built = components.chart("C1", TEST_FIGURE, "elections-table", "Caption")
            return html.Div([built, html.Table(id="elections-table")])

        tree, built = chart_render(layout, monkeypatch)
        assert chart_problems(tree, "/elections", built, "elections") == []
        assert chart_problems(tree, "/elections", built, "c1") == [
            "/elections: the success marker is inside chart c1"
        ]
        assert chart_problems(tree, "/elections", built, "c1-title") == [
            "/elections: the success marker is inside chart c1"
        ]


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
        # T2 on the states page and T6 on the per-capita page (#465), each narrowed by
        # its own page's state filter; T3, on the overview, is never filtered.
        trees = {
            table: render(TABLES[table], monkeypatch, "state=SC", year="1860")[0]
            for table in ("election-states", "election-per-capita")
        }
        for table, tree in trees.items():
            file = download(tree, table)
            assert file.rows, table
            assert {r["state_usps"] for r in file.rows} == {"SC"}, table
            assert len(file.rows) == len(body_rows(tree, table)), table
        recorded = RECORDED["/v1/elections/1860"]
        states = download(trees["election-states"], "election-states")
        expected = [r for r in recorded["data"] if r["state_usps"] == "SC"]
        assert [r["candidate_slug"] for r in states.rows] == [
            r["candidate_slug"] for r in expected
        ]
        tree, _ = render("/election/<year>", monkeypatch, year="1860")
        nation = download(tree, "election-nation")
        assert [r["candidate_slug"] for r in nation.rows] == [
            r["candidate_slug"] for r in recorded["summary"]
        ]
        for table, section in (
            ("election-states", "states"),
            ("election-per-capita", "per-capita"),
        ):
            lines = download(trees[table], table).lines
            assert lines[[i for i, x in enumerate(lines) if "View" in x][0]] == (
                "View: https://explore.us-presidential-election-center.org"
                f"/election/1860/{section}?state=SC"
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
                "/election/<year>/states",
                "electoral_count_status=counted&pv_status=popular_vote",
                "election-states",
                "/election/1824/states"
                "?electoral_count_status=counted&pv_status=popular_vote",
            ),
            # The per-capita page reads the state only (#465).
            (
                "/election/<year>/per-capita",
                "state=SC&candidate=andrew-jackson",
                "election-per-capita",
                "/election/1824/per-capita?state=SC",
            ),
            # The overview reads no filter, so T3's file names the bare overview.
            (
                "/election/<year>",
                "zz=1",
                "election-nation",
                "/election/1824",
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
        tree, _ = render(
            "/election/<year>/states", monkeypatch, "state=ZZ", year="1860"
        )
        lines = download(tree, "election-states").lines
        assert (
            "View: https://explore.us-presidential-election-center.org"
            "/election/1860/states" in lines
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
                "/election/<year>/states",
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
                    "hybrid_score",
                    "nominating_party_note",
                    "nominating_party_source",
                    "candidate_slug",
                    "year",
                ),
            ),
            (
                "/election/<year>/per-capita",
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
        tree, _ = render("/election/<year>/states", monkeypatch, year="1860")
        states = download(tree, "election-states")
        recorded = RECORDED["/v1/elections/1860"]["data"]
        assert all(r["popular_votes"] is None for r in recorded)  # the premise
        assert {r["popular_votes"] for r in states.rows} == {""}
        # Breckinridge and Bell carry no party row (#389): an empty cell, as served.
        nulls = {
            r["candidate"] for r in states.rows if r["nominating_party"] == ""
        }
        assert {"John C. Breckinridge", "John Bell"} <= nulls
        tree, _ = render("/election/<year>", monkeypatch, year="1860")
        nation = download(tree, "election-nation")
        assert {r["hybrid_score"] for r in nation.rows} == {""}

    def test_the_columns_that_explain_a_null_travel_with_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tree, _ = render("/election/<year>/states", monkeypatch, year="1872")
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
        # T6's page has one filter, its own (#465), so no note says which apply.
        tree, _ = render("/election/<year>/per-capita", monkeypatch)
        lines = download(tree, "election-per-capita").lines
        assert labels.GOVERNING_CENSUS_NOTE in lines
        assert labels.BOUNDARY_NOTE in lines
        assert (
            "PER_CAPITA_FILTER_NOTE"
            not in page_of("/election/<year>/per-capita")["layout"].__globals__
        )

    def test_the_national_file_carries_t3_s_notes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T3's notes show under it and travel in its file, as every table note does;
        since #358 none explains a repeated electoral share."""
        tree, _ = render("/election/<year>", monkeypatch, year="1872")
        lines = download(tree, "election-nation").lines
        shown = [p.children for p in of_type(tree, "P")]
        for note in (
            labels.PARTY_NOTE,
            labels.PARTY_NULL_NOTE,
            labels.HYBRID_NOTE,
        ):
            assert note in lines
            assert note in shown
        # #358: one electoral share, so no note explains a repeat.
        assert not [line for line in lines if "electoral share repeats it" in line]

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
        tree, _ = render("/election/<year>/states", monkeypatch)
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
        other_tree, _ = render(TABLES[other], monkeypatch)
        assert "Data version: OWN-RESPONSE" not in download(other_tree, other).lines

    def test_the_per_capita_page_s_file_reads_its_own_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T6 has a page of its own since #465, whose other read is the index (for the
        heading and the neighbours): its file and footer carry the per-capita
        response's provenance, never the index's."""
        for path, version in (
            ("/v1/elections/1824/per-capita", "OWN-RESPONSE"),
            ("/v1/elections", "INDEX-RESPONSE"),
        ):
            body = copy.deepcopy(RECORDED[path])
            body["meta"]["provenance"]["snapshot_version"] = version
            monkeypatch.setitem(RECORDED, path, body)
        tree, reads = render("/election/<year>/per-capita", monkeypatch)
        assert "/v1/elections" in reads  # the premise: the index was read
        lines = download(tree, "election-per-capita").lines
        assert "Data version: OWN-RESPONSE" in lines
        assert not [line for line in lines if "INDEX-RESPONSE" in line]
        (footer,) = of_type(tree, "Footer")
        assert "OWN-RESPONSE" in str(footer)
        assert "INDEX-RESPONSE" not in str(footer)

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
        links_1872 = {
            link_id: link
            for key in ("/election/<year>", "/election/<year>/states")
            for link_id, link in links(render(key, monkeypatch, year="1872")[0]).items()
        }
        for link in links_1872.values():
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
        tree, _ = render("/election/<year>/states", monkeypatch, year="1872")
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
        tree, _ = render("/election/<year>/states", monkeypatch)
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

#: The recorded years of the election pages, each page rendered whole: read from the
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
        node_id = getattr(node, "id", None)
        if isinstance(node_id, dict) and node_id.get("type") == charts.SOURCE_TYPE:
            return figure_texts(getattr(node, "data", None))
        own: list[str] = []
        for option in getattr(node, "options", None) or []:
            label = option.get("label") if isinstance(option, dict) else option
            own += reader_texts(label)
        placeholder = getattr(node, "placeholder", None)
        if isinstance(placeholder, str):
            own.append(placeholder)
        return own + reader_texts(getattr(node, "children", None))
    raise TypeError(f"unexpected node {node!r}")


#: What a hover or text template carries that a reader never sees as written: a
#: ``%{…}`` placeholder (filled with a value, or a field path such as
#: ``%{customdata.pv_share}``) and the ``<extra>`` box's markup.
_TEMPLATE_CODE = re.compile(r"%\{[^}]*\}|</?extra>|<br>")


def _leaves(value: Any) -> list[str]:
    """Every string in ``value``, a list or a dict of any depth (``customdata``)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for inner in value.values() for t in _leaves(inner)]
    if isinstance(value, list):
        return [t for inner in value for t in _leaves(inner)]
    return []


def figure_texts(figure: Any) -> list[str]:
    """Every string a chart's figure shows a reader (#432): axis, legend, legend-group
    and chart titles, tick text (``ticktext``, and the category values plotly draws as
    tick labels: every string in a trace's ``x`` and ``y``), trace names, hover and text
    templates (placeholders and markup removed), ``text`` and ``hovertext``, every string
    in ``customdata`` (which a ``%{customdata.…}`` placeholder shows), and annotations.
    The chart title reaches the page as HTML, so a built chart's title is scanned as
    ordinary children too. Shape labels are not read: no chart draws one before C4 and
    C5 (#436)."""
    if not isinstance(figure, dict):
        return []
    found: list[str] = []
    found_layout = figure.get("layout")
    layout: dict[str, Any] = found_layout if isinstance(found_layout, dict) else {}

    def title(part: Any) -> None:
        text = part.get("title") if isinstance(part, dict) else None
        text = text.get("text") if isinstance(text, dict) else text
        if isinstance(text, str):
            found.append(text)

    title(layout)
    for key, part in layout.items():
        if re.fullmatch(r"[xy]axis\d*", key) and isinstance(part, dict):
            title(part)
            found += [str(t) for t in part.get("ticktext") or []]
    title(layout.get("legend"))
    found += [
        str(note["text"])
        for note in layout.get("annotations") or []
        if isinstance(note, dict) and "text" in note
    ]
    for trace in figure.get("data") or []:
        if not isinstance(trace, dict):
            continue
        for field in ("name", "hovertemplate", "texttemplate", "text", "hovertext"):
            value = trace.get(field)
            for text in value if isinstance(value, list) else [value]:
                if isinstance(text, str):
                    found.append(_TEMPLATE_CODE.sub(" ", text))
        for field in ("x", "y", "customdata"):
            found += _leaves(trace.get(field))
        group = trace.get("legendgrouptitle")
        if isinstance(group, dict) and isinstance(group.get("text"), str):
            found.append(group["text"])
    return [text for text in found if text.strip()]


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
    "/election/<year>": ({"year": "2016"}, {"/v1/elections/2016": _election}),
    "/election/<year>/states": ({"year": "2016"}, {"/v1/elections/2016": _election}),
    "/election/<year>/per-capita": (
        {"year": "2016"},
        {"/v1/elections/2016/per-capita": _row(*PER_CAPITA_ROW_FIELDS)},
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
        "election-nation": len(SUMMARY_ROW_FIELDS),
        "election-panel": len(PANEL_WORDED_FIELDS) + len(PANEL_NAME_FIELDS),
    },
    "/election/<year>/states": {
        "election-states": len(STATE_ROW_FIELDS) + 1,  # popular votes
    },
    "/election/<year>/per-capita": {
        "election-per-capita": len(PER_CAPITA_ROW_FIELDS),
    },
    "/state/<usps>": {
        "state-history": len(STATE_ROW_FIELDS) + 1,
        "state-per-capita": len(PER_CAPITA_ROW_FIELDS),
    },
    "/candidate/<slug>": {"candidate-history": len(STATE_ROW_FIELDS) + 1},
}


def test_no_label_or_field_set_names_the_hybrid_share() -> None:
    """#358: ``ec_share_hybrid`` has no label and is in no field set, so no table can
    show it (``labels.header`` reads ``LABELS``) or export it
    (``test_the_field_sets_are_disjoint_and_cover_every_column``)."""
    assert "ec_share_hybrid" not in labels.LABELS
    for name in (
        "EC_FIELDS",
        "POPULAR_VOTE_FIELDS",
        "CENSUS_FIELDS",
        "NOMINATING_PARTY_FIELDS",
    ):
        assert "ec_share_hybrid" not in getattr(export, name), name


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
        for table in ("election-states", "election-nation"):
            tree, _ = render(TABLES[table], monkeypatch, year="2016")
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


def test_no_in_app_link_builds_a_filtered_overview_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#465: the overview reads no filter, and a filtered overview link is only ever
    an old one the index redirects, so no page links to the overview with a query.
    Decided by Dash's router, as ``is_chart_path`` decides a chart page, never a
    pattern of the template: ``/election/2016/?q`` reaches the overview too."""
    from dash._pages import _path_to_page

    from explore import app as appmod

    trees = list(all_pages(monkeypatch).values())
    trees += [
        render(key, monkeypatch, "state=GA&candidate=donald-j-trump", year="2016")[0]
        for key in ("/election/<year>/states", "/election/<year>/per-capita")
    ]
    hrefs = [
        href
        for tree in trees
        for node in of_type(tree, "Link") + of_type(tree, "A")
        if isinstance(href := getattr(node, "href", None), str)
    ]
    on_overview = []
    for href in hrefs:
        parts = urlsplit(href)
        if (
            parts.scheme not in ("", "https")
            or (parts.netloc and parts.netloc != HOST.removeprefix("https://"))
            or not parts.path.startswith("/")
        ):
            # A download's data: URL, another site's link (the API docs), or a fragment
            # on the same page (a chart's pointer to its table).
            continue
        page, _ = _path_to_page(appmod.router_key(parts.path))
        if page.get("module") == "pages.election":
            on_overview.append(href)
    assert on_overview  # the premise: the section links and the bar reach it
    assert [href for href in on_overview if urlsplit(href).query] == []


class TestNoRawValues:
    """The glossary's no-raw-values rule over whole rendered pages (#355), as far as
    rendered text shows it (children, dropdown labels and placeholders; not tooltips).
    Recorded data reaches no fallback, so each table page is also rendered from bodies
    doctored as ``DOCTORED`` says: every doctored cell then reads "Unrecognized value"
    with its help text, never the raw value, and ``UNRECOGNIZED_CELLS`` pins how many
    per table, so a doctored cell that reads otherwise fails. Candidate and state names
    are shown as served (#367): the API types a row's names as required text, never
    null or non-text."""

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
        for page in sorted({TABLES[t] for t in TABLES if t.startswith("election-")}):
            tree, _ = render(page, monkeypatch, year=year)
            on_page = {t for t, key in TABLES.items() if key == page}
            assert on_page <= set(tables_in(tree)), page  # the premise: not degraded
            assert raw_values(tree) == [], page

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

    def test_a_chart_s_figure_text_is_scanned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#432: a chart's figure text is reader text: a raw value in any of its kinds
        fails, while a hover placeholder naming a field (``%{customdata.pv_share}``)
        does not."""
        monkeypatch.setattr(
            charts, "CHARTS", {"C1": charts.Chart("/elections", "elections-table")}
        )
        built = components.chart("C1", TEST_FIGURE, "elections-table", "Caption")
        assert raw_values(built) == []
        texts = reader_texts(built)
        for shown in ("Each candidate's two shares", "Candidate", "Share", "Measure"):
            assert shown in texts, shown
        assert "Majority" in texts and "Electoral share" in texts
        for path in (
            ("layout", "xaxis", "title", "text"),
            ("layout", "legend", "title", "text"),
            ("layout", "annotations", 0, "text"),
            ("layout", "xaxis", "ticktext", 1),
            ("data", 0, "name"),
            ("data", 1, "hovertemplate"),
            # A category value, drawn as a tick label, and hover-only values.
            ("data", 0, "x", 0),
            ("data", 0, "y", 0),
            ("data", 1, "customdata", 0, "pv_share"),
            ("data", 0, "hovertext"),
            ("data", 0, "texttemplate"),
            ("data", 0, "legendgrouptitle"),
        ):
            doctored = copy.deepcopy(TEST_FIGURE)
            part: Any = doctored
            for step in path[:-1]:
                part = part[step]
            part[path[-1]] = (
                {"text": "ec_share_full"}
                if path[-1] == "legendgrouptitle"
                else "ec_share_full"
            )
            if path[:2] == ("data", 0):
                doctored["data"][0]["marker"]["pattern"] = {"shape": "x"}
            chart = components.chart("C1", doctored, "elections-table", "Caption")
            assert raw_values(chart) == ["ec_share_full"], path

