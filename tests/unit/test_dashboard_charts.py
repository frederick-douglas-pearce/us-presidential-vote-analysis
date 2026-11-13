"""The chart foundation (#432, E14-S3): the chart registry, ``components.chart``, the
color allowlist, the rule that color is never the only carrier, the template, the shared
config and the chart callback.

What a page's charts must satisfy when rendered (built by the builder, registered, on
their page, beside their table, never the success marker) is ``TestEveryChart`` in
``test_dashboard_export.py``; their text is ``TestNoRawValues``'s there. What the
browser does with the callback (drawing in the theme in effect, the CDN load and its
failure) is ``tests/e2e/test_dashboard_e2e_charts.py``'s.
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import dash
import pytest

from explore import app as appmod
from explore import charts, components, labels
from tests.chart_log import LOGGER, Records, chart_log_checked, chart_log_problems
from tests.unit.test_dashboard_elections import of_type
from tests.unit.test_dashboard_export import TEST_FIGURE, render
from tests.unit.test_dashboard_guards import RUNTIME_MODULES
from tests.unit.test_dashboard_theme import (
    EXPLICIT_DARK,
    LIGHT,
    MEDIA_DARK,
    NOT_COLORS,
    TOKENS,
    block,
)

#: Every chart ID ever issued, live and retired, with its whole row (page, companion
#: table, retired): written by hand, never derived from the registry, so a renumbered,
#: reused, un-retired or deleted ID fails. An ID is issued when its chart story
#: registers it: C1 by #433 and C3 by #435; C2, C4 and C5 are assigned to #434 and
#: #436 by their issues.
ISSUED: dict[str, tuple[str, str, bool]] = {
    "C1": ("/election/<year>", "election-nation", False),
    "C3": ("/election/<year>/per-capita", "election-per-capita", False),
    "C2": ("/elections", "elections-leader-table", False),
}

#: A registry with one live and one retired row, for the builder's tests.
REGISTRY = {
    "C1": charts.Chart("/elections", "elections-table"),
    "C2": charts.Chart("/elections", "elections-table", retired=True),
}


def issued_problems(
    literal: dict[str, tuple[str, str, bool]], registry: Any
) -> list[str]:
    """How ``registry`` differs from the hand-written ``literal`` of issued IDs: an ID
    missing from either, or a row whose page, table or retired flag changed."""
    problems = [f"{c}: issued but not registered" for c in literal if c not in registry]
    problems += [f"{c}: registered but not issued" for c in registry if c not in literal]
    problems += [
        f"{c}: row {tuple(registry[c])} is not {row}"
        for c, row in literal.items()
        if c in registry and tuple(registry[c]) != row
    ]
    return problems


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(charts, "CHARTS", REGISTRY)


def build(figure: Any = None, **overrides: Any) -> Any:
    args: dict[str, Any] = {
        "chart_id": "C1",
        "figure": TEST_FIGURE if figure is None else figure,
        "table_id": "elections-table",
        "caption": "A caption.",
    }
    args.update(overrides)
    return components.chart(**args)


def bars(**second: Any) -> dict[str, Any]:
    """Two bar traces, the second changed by ``second``."""
    figure = copy.deepcopy(TEST_FIGURE)
    figure["data"][1]["marker"] = {"color": "var(--chart-2)"}
    figure["data"][1].update(second)
    return figure


# --- the registry ----------------------------------------------------------------------


class TestChartRegistry:
    def test_the_registry_equals_every_issued_id(self) -> None:
        assert issued_problems(ISSUED, charts.CHARTS) == []

    def test_the_comparison_fails_every_drift(self) -> None:
        literal = {
            "C1": ("/elections", "elections-table", False),
            "C2": ("/elections", "elections-table", True),
        }
        assert issued_problems(literal, REGISTRY) == []
        assert issued_problems(literal, {"C1": REGISTRY["C1"]}) == [
            "C2: issued but not registered"  # a retired row deleted
        ]
        assert issued_problems({"C1": literal["C1"]}, REGISTRY) == [
            "C2: registered but not issued"
        ]
        moved = {**REGISTRY, "C1": charts.Chart("/states", "elections-table")}
        assert issued_problems(literal, moved) == [
            "C1: row ('/states', 'elections-table', False) is not "
            "('/elections', 'elections-table', False)"
        ]
        # A retired ID brought back, or an ID reused for another table.
        revived = {**REGISTRY, "C2": charts.Chart("/elections", "elections-table")}
        assert issued_problems(literal, revived) == [
            "C2: row ('/elections', 'elections-table', False) is not "
            "('/elections', 'elections-table', True)"
        ]
        reused = {**REGISTRY, "C1": charts.Chart("/elections", "another-table")}
        assert len(issued_problems(literal, reused)) == 1

    def test_the_literal_is_written_by_hand(self) -> None:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        (node,) = [
            n
            for n in tree.body
            if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and n.target.id == "ISSUED"
        ]
        assert isinstance(node.value, ast.Dict)
        assert all(isinstance(key, ast.Constant) for key in node.value.keys)
        for value in node.value.values:
            assert isinstance(value, ast.Tuple)
            assert all(isinstance(part, ast.Constant) for part in value.elts)

    def test_every_row_is_well_formed_and_on_a_registered_page(self) -> None:
        assert charts.registry_problems(charts.CHARTS) == []
        templates = {
            page.get("path_template") or page["path"]
            for page in dash.page_registry.values()
        }
        assert {row.page for row in charts.CHARTS.values()} <= templates

    def test_the_row_check_refuses_a_malformed_id_or_row(self) -> None:
        assert charts.registry_problems(REGISTRY) == []
        assert charts.registry_problems(
            {
                "C0": charts.Chart("/a", "t"),
                "c1": charts.Chart("/a", "t"),
                "C01": charts.Chart("/a", "t"),
                "C3": charts.Chart("a", "t"),
                "C4": ("/a", "t"),  # type: ignore[dict-item]
            }
        ) == [
            "'C0': not a chart ID",
            "'c1': not a chart ID",
            "'C01': not a chart ID",
            "'C3': not a chart row",
            "'C4': not a chart row",
        ]

    def test_the_dom_id_is_the_id_in_lower_case(self) -> None:
        assert charts.dom_id("C1") == "c1"
        assert charts.dom_id("C12") == "c12"


# --- the builder -----------------------------------------------------------------------


@pytest.mark.usefixtures("registry")
class TestChartBuilder:
    def test_it_renders_the_title_graph_store_and_caption_in_order(self) -> None:
        built = build()
        assert type(built).__name__ == "Figure"
        assert built.id == "c1"
        title, wrapper, store, caption = built.children
        assert type(title).__name__ == "P"
        assert (title.id, title.className) == ("c1-title", "chart-title")
        assert title.children == "Each candidate's two shares"
        assert type(wrapper).__name__ == "Div"
        assert wrapper.role == "img"
        assert getattr(wrapper, "aria-labelledby") == "c1-title"
        assert type(store).__name__ == "Store"
        assert store.id == charts.source_id("c1")
        assert type(caption).__name__ == "Figcaption"

    def test_the_mount_point_is_empty_and_no_graph_is_built(self) -> None:
        # #452: the graph is put in by the mount callback once plotly.js has loaded.
        built = build()
        mount = built.children[1]
        assert mount.id == charts.mount_id("c1")
        assert mount.className == "chart-graph"
        assert getattr(mount, "children", None) is None
        assert of_type(built, "Graph") == []

    def test_the_mount_id(self) -> None:
        assert charts.mount_id("c1") == {"type": "explore-chart-mount", "chart": "c1"}
        assert len({charts.MOUNT_TYPE, charts.GRAPH_TYPE, charts.SOURCE_TYPE}) == 3

    def test_the_store_holds_the_figure_without_its_title(self) -> None:
        store = build().children[2]
        expected = copy.deepcopy(TEST_FIGURE)
        del expected["layout"]["title"]
        assert store.data == expected
        assert "title" in TEST_FIGURE["layout"]  # the caller's figure is not changed

    def test_the_caption_ends_with_the_table_pointer(self) -> None:
        caption = build(caption="What it shows.").children[3]
        text, space, link, period = caption.children
        assert (text, space, period) == ("What it shows.", " ", ".")
        assert type(link).__name__ == "A"
        assert link.children == labels.CHART_TABLE_POINTER
        assert link.href == "#elections-table"

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"chart_id": "C9"}, "not a live registered chart"),
            ({"chart_id": "C2"}, "not a live registered chart"),
            ({"table_id": "other"}, "companion table is 'elections-table'"),
            ({"caption": "  "}, "has no caption"),
        ],
    )
    def test_it_refuses_an_unregistered_or_retired_id_another_table_or_no_caption(
        self, overrides: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            build(**overrides)

    @pytest.mark.parametrize(
        "title", [None, {"text": ""}, {"text": "A<br>title"}, {"text": 3}, "Plain"]
    )
    def test_it_refuses_a_missing_empty_marked_up_or_misplaced_title(
        self, title: Any
    ) -> None:
        figure = copy.deepcopy(TEST_FIGURE)
        if title is None:
            del figure["layout"]["title"]
        else:
            figure["layout"]["title"] = title
        with pytest.raises(ValueError, match="no plain-text chart title"):
            build(figure)

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda f: f["data"][0]["marker"].update(color="#fff"), "not a color token"),
            (lambda f: f["data"][0].pop("hovertemplate"), "no hovertemplate"),
            (lambda f: f["layout"].update(template={}), "the template is the found"),
            (lambda f: f["layout"].update(hovermode="x unified"), "fixed by the templ"),
            (lambda f: f["data"][0].update(name="<b>A</b>"), "markup in"),
            (lambda f: f["data"][0]["marker"].update(symbol=0), "a number, not a name"),
            (lambda f: f["data"][1]["marker"].pop("pattern"), "differ by color alone"),
        ],
        ids=["color", "hover", "template", "override", "markup", "number", "color-only"],
    )
    @pytest.mark.expected_chart_failure("C1")
    def test_a_figure_with_problems_is_not_drawn_and_is_logged(
        self, change: Any, message: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Each rule ``figure_problems`` gathers reaches the builder (#432), and a
        figure that breaks one is not drawn (#467, D095): the chart keeps its DOM id,
        its title and its caption with the table pointer, and has no mount point and
        no source store, so no callback runs for it; one error record names the chart,
        its page and the rule. The conftest check holds the count to exactly one."""
        figure = copy.deepcopy(TEST_FIGURE)
        drawn = build(figure)  # the control: the figure passes before the change
        assert self.mounted(drawn)
        caplog.clear()
        change(figure)
        built = build(figure)
        assert built.id == "c1" and not self.mounted(built)
        assert [getattr(c, "id", None) for c in built.children] == ["c1-title", None]
        assert built.children[0].children == TEST_FIGURE["layout"]["title"]["text"]
        caption = built.children[1]
        assert caption.children[0] == "A caption."
        assert caption.children[2].href == "#elections-table"
        [record] = [r for r in caplog.records if r.name == "explore.components"]
        assert record.levelno == logging.ERROR and record.chart_id == "C1"  # type: ignore[attr-defined]
        assert "C1 on /elections not drawn" in record.getMessage()
        assert message in record.getMessage()

    @staticmethod
    def mounted(chart: Any) -> bool:
        """Whether a built chart holds its mount point and its source store."""
        ids = [getattr(c, "id", None) for c in chart.children]
        return charts.mount_id("c1") in ids and charts.source_id("c1") in ids

    @pytest.mark.expected_chart_failure("C1")
    def test_the_log_lists_at_most_three_problems(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A problem can repr a served value, one per row: the line counts them all
        and lists the first :data:`components.LOGGED_PROBLEMS`."""
        figure = copy.deepcopy(TEST_FIGURE)
        figure["data"][0]["hovertext"] = [f"<b>{n}</b>" for n in range(5)]
        figure["data"][0]["x"] = [str(n) for n in range(5)]
        figure["data"][0]["y"] = [0.1] * 5
        problems = charts.figure_problems(figure)
        assert len(problems) > components.LOGGED_PROBLEMS == 3
        build(figure)
        [record] = [r for r in caplog.records if r.name == "explore.components"]
        assert f"{len(problems)} figure problem(s)" in record.getMessage()
        assert record.args[-1] == problems[:3]  # type: ignore[index]


# --- the figure rules ------------------------------------------------------------------


class TestColorAllowlist:
    def test_the_test_figure_passes(self) -> None:
        assert charts.figure_problems(TEST_FIGURE) == []

    @pytest.mark.parametrize(
        ("figure", "problem"),
        [
            ({"data": [{"marker": {"color": "#fff"}}]}, "data[0].marker.color"),
            ({"data": [{"marker": {"color": "red"}}]}, "data[0].marker.color"),
            ({"data": [{"marker": {"color": [1, 2]}}]}, "data[0].marker.color"),
            # A list of tokens colors points one by one: only colorway takes a list.
            (
                {"data": [{"marker": {"color": ["var(--chart-1)", "var(--chart-2)"]}}]},
                "data[0].marker.color",
            ),
            ({"data": [{"marker": {"color": 3}}]}, "data[0].marker.color"),
            (
                {"data": [{"line": {"color": "var(--chart-1) "}}]},
                "data[0].line.color",
            ),
            ({"data": [{"marker": {"colorscale": "Viridis"}}]}, "no colorscale"),
            ({"data": [], "layout": {"colorway": ["#000"]}}, "layout.colorway"),
            ({"data": [], "layout": {"colorway": []}}, "layout.colorway"),
            (
                {"data": [], "layout": {"font": {"family": "x var(--font-body)"}}},
                "layout.font.family",
            ),
            (
                {"data": [{"name": "var(--chart-1)"}]},
                "a token reference outside a color",
            ),
            # The font token is no color, and no color token is the font.
            (
                {"data": [{"marker": {"color": "var(--font-body)"}}]},
                "data[0].marker.color",
            ),
            (
                {"data": [], "layout": {"font": {"family": "var(--text)"}}},
                "layout.font.family",
            ),
        ],
    )
    def test_a_color_that_is_no_token_reference_fails(
        self, figure: dict[str, Any], problem: str
    ) -> None:
        assert any(problem in p for p in charts.color_problems(figure)), (
            charts.color_problems(figure)
        )

    def test_token_references_pass(self) -> None:
        figure = {
            "data": [{"marker": {"color": "var(--chart-1)"}}],
            "layout": {
                "colorway": ["var(--chart-1)", "var(--chart-2)"],
                "font": {"family": "var(--font-body)", "color": "var(--text)"},
            },
        }
        assert charts.color_problems(figure) == []

    @pytest.mark.parametrize(
        "figure",
        [
            {"data": []},
            {"data": [], "layout": {"template": {}}},
            {"data": [], "config": {}},
            {"data": [], "layout": []},
            {"data": "x"},
            {"data": ["x"]},
            [],
        ],
    )
    def test_a_figure_that_is_not_a_plain_chart_figure_fails(self, figure: Any) -> None:
        problems = charts.figure_problems(figure)
        assert (problems == []) is (figure == {"data": []}), problems


def trace(kind: str = "scatter", **fields: Any) -> dict[str, Any]:
    return {"type": kind, "hovertemplate": "x", **fields}


class TestColorIsNeverTheOnlyCarrier:
    @pytest.mark.parametrize(
        ("first", "second", "apart"),
        [
            (trace(mode="markers"), trace(mode="markers"), False),
            (
                trace(mode="markers"),
                trace(mode="markers", marker={"symbol": "square"}),
                True,
            ),
            # A symbol only counts where the trace draws markers.
            (trace(mode="lines"), trace(mode="lines", marker={"symbol": "x"}), False),
            # Shown text names a scatter series only where the trace draws text.
            (
                trace(mode="markers", name="A", text="A"),
                trace(mode="markers", name="B", text="B"),
                False,
            ),
            (
                trace(mode="markers+text", name="A", text="A"),
                trace(mode="markers+text", name="B", text="B"),
                True,
            ),
            # Different types differ in shape, though neither draws a counted channel.
            (trace(mode="text"), trace("pie"), True),
            # A dash only counts where the trace draws a line.
            (trace(mode="markers"), trace(mode="markers", line={"dash": "dot"}), False),
            (trace(mode="lines"), trace(mode="lines", line={"dash": "dot"}), True),
            (
                trace(mode="lines+markers"),
                trace(mode="lines+markers", marker={"symbol": "x"}),
                True,
            ),
            # A symbol only counts where the trace draws markers: a bar draws none.
            (trace("bar"), trace("bar", marker={"symbol": "x"}), False),
            (trace("bar"), trace("bar", marker={"pattern": {"shape": "/"}}), True),
            # A direct label is shown text that, placeholders removed, is the name.
            (
                trace("bar", name="A", texttemplate="%{y} A"),
                trace("bar", name="B", texttemplate="%{y} B"),
                True,
            ),
            (
                trace("bar", name="A", texttemplate="%{fullData.name}: %{y}"),
                trace("bar", name="B", texttemplate="%{fullData.name}: %{y}"),
                True,
            ),
            # Not by substring: both bars show the same text.
            (
                trace("bar", name="Electoral", texttemplate="%{y} Electoral share"),
                trace(
                    "bar", name="Electoral share", texttemplate="%{y} Electoral share"
                ),
                False,
            ),
            # A label on one trace only does not excuse the pair.
            (
                trace("bar", name="A", texttemplate="A"),
                trace("bar", name="B"),
                False,
            ),
            # Different shapes: dots against a line, or bars against a line.
            (trace(mode="markers"), trace(mode="lines"), True),
            (trace("bar"), trace(mode="lines"), True),
            (
                trace("bar", name="A", texttemplate="%{y}"),
                trace("bar", name="B", texttemplate="%{y}"),
                False,
            ),
            (
                trace("bar", name="A", text="A", textposition="none"),
                trace("bar", name="B", text="B", textposition="none"),
                False,
            ),
            (
                trace(mode="markers", name="A"),
                trace(mode="markers", name="B"),
                False,
            ),
            # Two traces of a type this does not know draw no counted channel.
            (trace("pie"), trace("pie", marker={"pattern": {"shape": "/"}}), False),
        ],
    )
    def test_a_pair_differs_only_by_a_channel_both_draw(
        self, first: dict[str, Any], second: dict[str, Any], apart: bool
    ) -> None:
        figure = {"data": [first, second]}
        assert (charts.color_only_pairs(figure) == []) is apart

    def test_an_annotation_naming_each_series_labels_it(self) -> None:
        figure: dict[str, Any] = {
            "data": [trace(mode="markers", name="A"), trace(mode="markers", name="B")],
            "layout": {"annotations": [{"text": "A"}, {"text": "B"}]},
        }
        assert charts.color_only_pairs(figure) == []
        figure["layout"]["annotations"] = [{"text": "A"}]
        assert charts.color_only_pairs(figure) == [(0, 1)]

    def test_every_pair_is_checked(self) -> None:
        figure = {
            "data": [
                trace(mode="markers"),
                trace(mode="markers", marker={"symbol": "x"}),
                trace(mode="markers"),
            ]
        }
        assert charts.color_only_pairs(figure) == [(0, 2)]


class TestMarkupNumbersAndOverrides:
    @pytest.mark.parametrize(
        ("text", "refused"),
        [
            ("Plain", False),
            ("Two<br>lines", False),
            ("%{y}<extra></extra>", False),
            ("%{y}<extra>%{fullData.name}</extra>", False),
            ('<span style="color:#f00">A</span>', True),
            ("<b>A</b>", True),
            ('<a href="/x">A</a>', True),
            ("a < b", True),
        ],
    )
    def test_only_a_line_break_and_the_extra_box_are_allowed(
        self, text: str, refused: bool
    ) -> None:
        for figure in (
            {"data": [{"name": text}]},
            {"data": [], "layout": {"annotations": [{"text": text}]}},
            {"data": [{"hovertemplate": text}]},
        ):
            assert bool(charts.markup_problems(figure)) is refused, (text, figure)

    @pytest.mark.parametrize(
        ("part", "key", "value", "refused"),
        [
            ("marker", "symbol", 0, True),
            ("marker", "symbol", [0, "x"], True),
            ("line", "dash", 2, True),
            # A string of digits is a number to plotly ("0" is "circle").
            ("marker", "symbol", "0", True),
            ("marker", "symbol", ["x", "100"], True),
            ("marker", "symbol", "circle", False),
            ("marker", "symbol", ["circle", "x"], False),
            ("line", "dash", "dot", False),
        ],
    )
    def test_a_numeric_symbol_or_dash_is_refused(
        self, part: str, key: str, value: Any, refused: bool
    ) -> None:
        figure = {"data": [{"type": "bar", part: {key: value}}]}
        assert bool(charts.number_problems(figure)) is refused

    @pytest.mark.parametrize(
        ("trace", "refused"),
        [
            ({"type": "scatter"}, True),
            ({}, True),  # plotly's default type is scatter
            ({"type": "scatter", "mode": None}, True),
            ({"type": "scatter", "mode": "lines"}, False),
            ({"type": "bar"}, False),
        ],
    )
    def test_a_scatter_trace_names_its_mode(
        self, trace: dict[str, Any], refused: bool
    ) -> None:
        """Plotly picks a mode-less scatter's mode by its point count, so the color-only
        rule could not tell what it draws (#432's round 2)."""
        assert bool(charts.number_problems({"data": [trace]})) is refused

    def test_a_trace_cannot_name_another_legend(self) -> None:
        assert charts.override_problems({"data": [{"legend": "legend2"}]}) == [
            "data[0].legend: 'legend2', not the template's legend"
        ]
        assert charts.override_problems({"data": [{"legend": "legend"}, {}]}) == []

    @pytest.mark.parametrize(
        "layout",
        [
            {"hovermode": "x unified"},
            {"dragmode": "zoom"},
            {"bargroupgap": 0},
            {"legend": {"itemclick": "toggle"}},
            {"legend": {"itemdoubleclick": "toggleothers"}},
            {"xaxis": {"fixedrange": False}},
            {"yaxis": {"exponentformat": "SI"}},
            {"xaxis2": {"separatethousands": False}},
            {"yaxis": {"tickformat": ".2s"}},
            {"yaxis": {"tickformat": "~e"}},
            {"yaxis": {"tickformat": ".3g"}},
            # No type is d3's ~g; n is ,g; an unknown type falls back to g.
            {"yaxis": {"tickformat": ",.2"}},
            {"yaxis": {"tickformat": ",.3~"}},
            {"yaxis": {"tickformat": "n"}},
            {"yaxis": {"tickformat": "E"}},
            {"yaxis": {"tickformat": "s.2"}},  # not a d3 format at all
            # Bars that touch: no gap between locations, or stacked or overlaid.
            {"bargap": 0},
            {"barmode": "stack"},
            {"barmode": "overlay"},
            # A second legend, which the template's legend does not reach.
            {"legend2": {"itemclick": "toggle"}},
            {"legend3": {}},
        ],
    )
    def test_a_figure_cannot_override_the_template_s_fixed_defaults(
        self, layout: dict[str, Any]
    ) -> None:
        assert charts.override_problems({"data": [], "layout": layout})

    @pytest.mark.parametrize(
        "layout",
        [
            {"margin": {"l": 10}},
            {"xaxis": {"automargin": False, "title": {"text": "Year"}}},
            {"font": {"size": 12}},
            {"yaxis": {"tickformat": ".0%"}},
            {"yaxis": {"tickformat": ",d"}},
            {"yaxis": {"tickformat": ",.1f"}},
            {"yaxis": {"tickformat": "+.1%"}},
            {"xaxis": {"tickformat": "%Y"}},  # a date format, not a number one
            {"legend": {"orientation": "h"}},
        ],
    )
    def test_what_a_chart_may_still_set(self, layout: dict[str, Any]) -> None:
        assert charts.override_problems({"data": [], "layout": layout}) == []


class TestC1Rules:
    """The three rules C1 made (#433, D091), each beside a control that passes."""

    @pytest.mark.parametrize(
        ("template", "refused"),
        [
            ("%{hovertext}<extra></extra>", False),
            ("%{text}", False),
            ("%{customdata[0]}<br>%{customdata[1]}", False),
            ("%{customdata.pv_share} of votes<extra>%{fullData.name}</extra>", False),
            ("No placeholder at all", False),
            ("%{x}", True),
            ("%{y:.1%}", True),
            ("%{customdata[0]:,}", True),  # a format on a string the page wrote
            ("%{hovertext} %{x}", True),
            ("%{meta}", True),
        ],
    )
    def test_a_template_names_only_strings_the_page_wrote(
        self, template: str, refused: bool
    ) -> None:
        for key in ("hovertemplate", "texttemplate"):
            figure = {"data": [{"type": "bar", key: template}]}
            assert bool(charts.template_problems(figure)) is refused, (key, template)
        # Per point, too.
        per_point: dict[str, Any] = {
            "data": [{"type": "bar", "hovertemplate": ["%{text}", template]}]
        }
        assert bool(charts.template_problems(per_point)) is refused

    @pytest.mark.parametrize(
        "figure",
        [
            {"data": [], "layout": {"xaxis": {"hoverformat": ".1%"}}},
            {"data": [], "layout": {"yaxis2": {"hoverformat": ",d"}}},
            {"data": [{"type": "bar", "xhoverformat": ".1%"}]},
            {"data": [{"type": "scatter", "yhoverformat": ".2f"}]},
        ],
    )
    def test_no_hover_format(self, figure: dict[str, Any]) -> None:
        assert any("no hover format" in p for p in charts.template_problems(figure))

    @pytest.mark.parametrize(
        ("figure", "refused"),
        [
            ({"data": [{"type": "bar"}]}, False),
            ({"data": [{"type": "bar", "width": 0.5}]}, True),
            ({"data": [{"type": "bar", "offset": -0.2}]}, True),
            ({"data": [{"type": "bar", "width": [0.5, 0.4]}]}, True),
            # A scatter's marker width is no bar width.
            ({"data": [{"type": "scatter", "marker": {"line": {"width": 2}}}]}, False),
            ({"data": [], "layout": {"scattergap": 0.1}}, True),
        ],
    )
    def test_no_bar_sets_its_own_width_or_offset(
        self, figure: dict[str, Any], refused: bool
    ) -> None:
        assert bool(charts.bar_problems(figure)) is refused

    @pytest.mark.parametrize(
        ("trace", "refused"),
        [
            ({"type": "bar", "text": ["50.0%", ""]}, False),
            ({"type": "bar", "text": "A label"}, False),
            ({"type": "bar", "hovertext": ["A<br>B"]}, False),
            ({"type": "bar", "customdata": [{"pv_share": "48.0%"}, ["a", "b"]]}, False),
            # plotly would format each of these itself.
            ({"type": "bar", "text": [0.5]}, True),
            ({"type": "bar", "text": 0.5}, True),
            ({"type": "bar", "hovertext": ["A", 3]}, True),
            ({"type": "bar", "customdata": [{"pv_share": 0.48}]}, True),
            ({"type": "bar", "customdata": [[0.1, "a"]]}, True),
            ({"type": "bar", "text": [None]}, True),
            ({"type": "bar", "text": [True]}, True),
        ],
    )
    def test_text_hovertext_and_customdata_hold_only_strings(
        self, trace: dict[str, Any], refused: bool
    ) -> None:
        """The owner's ruling on round 1: a hover or text label shows only strings the
        page wrote, so a number in ``text``, ``hovertext`` or ``customdata``, which a
        ``%{text}`` would let plotly format, is refused."""
        problems = charts.template_problems({"data": [trace]})
        assert bool(problems) is refused, problems
        assert all("not a string the page wrote" in p for p in problems)

    def test_figure_problems_gathers_the_c1_rules(self) -> None:
        assert charts.figure_problems(TEST_FIGURE) == []
        for change, message in (
            (lambda f: f["data"][0].update(hovertemplate="%{y}"), "not a string"),
            (lambda f: f["data"][0].update(width=0.3), "width and place"),
            (lambda f: f["layout"]["xaxis"].update(hoverformat=".1%"), "hover format"),
            (lambda f: f["data"][0].update(text=[0.5, 0.4]), "not a string the page"),
        ):
            figure = copy.deepcopy(TEST_FIGURE)
            change(figure)
            assert any(message in p for p in charts.figure_problems(figure)), message

    @pytest.mark.parametrize(
        ("first", "second", "apart"),
        [
            # plotly draws the texttemplate when set: a ``text`` it replaces names
            # nothing (#432's note 1).
            (
                trace("bar", name="A", text="A", texttemplate="%{y}"),
                trace("bar", name="B", text="B", texttemplate="%{y}"),
                False,
            ),
            # A conservative refusal, on purpose: placeholders are not resolved, so a
            # label written only through %{text} is not credited, though plotly would
            # draw "A" (#468 defers resolving it).
            (
                trace("bar", name="A", text="A", texttemplate="%{text}"),
                trace("bar", name="B", text="B", texttemplate="%{text}"),
                False,
            ),
            (
                trace("bar", name="A", text="A", texttemplate=""),
                trace("bar", name="B", text="B", texttemplate=""),
                True,
            ),
            (
                trace("bar", name="A", text="A"),
                trace("bar", name="B", text="B"),
                True,
            ),
        ],
    )
    def test_a_direct_label_is_the_drawn_string(
        self, first: dict[str, Any], second: dict[str, Any], apart: bool
    ) -> None:
        assert (charts.color_only_pairs({"data": [first, second]}) == []) is apart


class TestHoverText:
    def test_a_trace_writes_its_hover_text_or_turns_hover_off(self) -> None:
        figure = {
            "data": [
                {"hovertemplate": "%{y}"},
                {"hoverinfo": "skip"},
                {"hoverinfo": "none"},
                {},
                {"hovertemplate": " "},
                {"hoverinfo": "x+y"},
            ]
        }
        assert charts.hover_problems(figure) == [
            "data[3]: no hovertemplate",
            "data[4]: no hovertemplate",
            "data[5]: no hovertemplate",
        ]


# --- the template and the config -------------------------------------------------------


class TestTemplate:
    def test_the_template_names_no_color_and_every_token_exists(self) -> None:
        assert charts.color_problems(charts.TEMPLATE) == []
        named = charts.tokens_named(charts.TEMPLATE)
        assert {"--page", "--text", "--chart-1", "--chart-axis"} <= named
        # A color token is declared in every palette block; the font stack, not a
        # color, only on the light block's bare :root, which the dark blocks inherit.
        assert "--font-body" in block(LIGHT) and "--font-body" in NOT_COLORS
        for key in (LIGHT, MEDIA_DARK, EXPLICIT_DARK):
            declared = set(block(key))
            assert named - NOT_COLORS <= declared, (key, named - declared)

    def test_every_token_the_test_figure_names_is_a_color_token(self) -> None:
        assert charts.tokens_named(TEST_FIGURE) <= set(TOKENS)

    def test_the_colorway_is_the_series_tokens_in_order(self) -> None:
        series = [t for t in TOKENS if re.fullmatch(r"--chart-\d+", t)]
        assert charts.TEMPLATE["layout"]["colorway"] == [f"var({t})" for t in series]

    def test_the_shared_defaults(self) -> None:
        layout = charts.TEMPLATE["layout"]
        assert layout["hovermode"] == "closest"
        assert layout["dragmode"] is False
        assert layout["barmode"] == "group"
        assert layout["bargap"] > 0
        assert layout["bargroupgap"] > 0
        assert layout["legend"]["itemclick"] is False
        assert layout["legend"]["itemdoubleclick"] is False
        for axis in ("xaxis", "yaxis"):
            assert layout[axis]["fixedrange"] is True
            assert layout[axis]["separatethousands"] is True
            assert layout[axis]["exponentformat"] == "none"

    def test_every_fixed_key_is_set_by_the_template(self) -> None:
        layout = charts.TEMPLATE["layout"]
        for key in charts.FIXED_LAYOUT_KEYS:
            assert key in layout, key
        for key in charts.FIXED_LEGEND_KEYS:
            assert key in layout["legend"], key
        for axis in ("xaxis", "yaxis"):
            for key in charts.FIXED_AXIS_KEYS:
                assert key in layout[axis], (axis, key)
        assert charts.override_problems({"data": [], "layout": {}}) == []

    def test_the_config(self) -> None:
        assert charts.CHART_CONFIG == {
            "displaylogo": False,
            "scrollZoom": False,
            "displayModeBar": False,
            "responsive": True,
        }


# --- the callback ----------------------------------------------------------------------


class TestChartCallback:
    KEY = (
        '..{"chart":["MATCH"],"type":"explore-chart-graph"}.figure'
        '...{"chart":["MATCH"],"type":"explore-chart-graph"}.style..'
    )

    def test_one_clientside_match_callback_on_the_source_and_the_theme(self) -> None:
        assert appmod.server.test_client().get("/").status_code == 200
        spec = appmod.app.callback_map[self.KEY]
        assert spec["inputs"] == [
            {"id": '{"chart":["MATCH"],"type":"explore-chart-source"}', "property": "data"},
            {"id": components.THEME_STORE_ID, "property": "data"},
        ]
        assert spec["state"] == []
        assert "callback" not in spec  # clientside: no Python function runs
        drawn = [k for k in appmod.app.callback_map if charts.GRAPH_TYPE in k]
        assert drawn == [self.KEY]

    def test_it_waits_for_the_theme_and_builds_nothing(self) -> None:
        script = charts.CHART_CALLBACK
        assert script.startswith("function (source, theme) {")
        assert (
            "if (theme === null || theme === undefined || source === null"
            " || source === undefined) {"
            " return [clientside.no_update, clientside.no_update]; }"
        ) in script
        for banned in (
            "eval",
            "innerHTML",
            "Function(",
            "setAttribute",
            "fetch",
            # The theme never enters the URL, and nothing leaves the browser.
            "location",
            "history",
            "XMLHttpRequest",
            "sendBeacon",
        ):
            assert banned not in script, banned

    def test_it_resolves_whole_string_tokens_and_fails_loudly_on_an_unset_one(
        self,
    ) -> None:
        script = charts.CHART_CALLBACK
        pattern = json.loads(
            re.search(r"var token = new RegExp\((\"[^\"]*\")\);", script).group(1)  # type: ignore[union-attr]
        )
        assert pattern == "^" + charts.TOKEN_RE.pattern + "$"
        assert re.fullmatch(pattern.strip("^$"), "var(--chart-1)")
        assert "getPropertyValue(match[1]).trim()" in script
        assert "throw new Error('chart token ' + match[1] + ' is unset')" in script
        assert 'return [figure, {visibility: "visible"}];' in script

    def test_it_carries_the_template(self) -> None:
        script = charts.CHART_CALLBACK
        start = script.index("var template = ") + len("var template = ")
        template, _ = json.JSONDecoder().raw_decode(script[start:])
        assert template == charts.TEMPLATE
        assert "figure.layout.template = resolve(template);" in script


# --- the mount callback (#452) ---------------------------------------------------------


def graph_uses(source: str) -> list[str]:
    """The listed ways ``source`` reaches ``dcc.Graph`` to build one (#452): any load of
    ``Graph`` (an attribute ``X.Graph``, the bare name ``Graph``, or a name an import of
    ``Graph`` from any module binds, ``from dash.dcc import Graph as G``), except as the
    base of a ``._type`` or ``._namespace`` read; a
    ``getattr(..., "Graph")``; and dcc's namespace written as a string (outside
    docstrings), which is how a server callback would return a graph as component JSON.
    One rule over loads, not calls, so an alias (``G = dcc.Graph``), a
    ``functools.partial``, an indexed reference and a subclass are all caught. A runtime
    module that built a graph, in a layout or a server callback's return, would mount it
    before plotly.js has loaded and bring Dash's blocked-CDN loop back. It reads source:
    a dynamic import is the D070(b) lint's (``test_dashboard_guards.py``), while
    ``exec`` or ``eval`` of built text is outside both lints, as that lint's own
    docstring says of evasion."""
    tree = ast.parse(source)
    aliases = {"Graph"} | {
        a.asname or a.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for a in node.names
        if a.name == "Graph"
    }
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    found = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        is_graph = (isinstance(node, ast.Attribute) and node.attr == "Graph") or (
            isinstance(node, ast.Name) and node.id in aliases
        )
        if is_graph:
            parent = parents.get(node)
            read = (
                isinstance(parent, ast.Attribute)
                and parent.value is node
                and parent.attr in ("_type", "_namespace")
            )
            if not read:
                found.append(f"line {line}: {ast.unparse(node)}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and any(
                isinstance(a, ast.Constant) and a.value == "Graph" for a in node.args
            )
        ):
            found.append(f"line {line}: {ast.unparse(node)}")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "dash_core_components" in node.value
            and id(node) not in docstrings
        ):
            found.append(f"line {line}: dcc's namespace written as a string")
    return found


def set_props_refs(source: str) -> list[str]:
    """Where ``source`` refers to Dash's ``set_props`` in code (#452): a load of the name
    or attribute ``set_props``, or an import of it (reported by line), and a string
    outside a docstring that names it (a clientside callback's JS), each reported as the
    top-level definition or assignment it sits in. Comments are not code, so they do
    not count."""
    tree = ast.parse(source)
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    found = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            where = stmt.name
        elif isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
            where = stmt.targets[0].id
        else:
            where = f"line {stmt.lineno}"
        for node in ast.walk(stmt):
            hit = (
                (isinstance(node, ast.Name) and node.id == "set_props")
                or (isinstance(node, ast.Attribute) and node.attr == "set_props")
                or (
                    isinstance(node, ast.ImportFrom)
                    and any(a.name == "set_props" for a in node.names)
                )
                or (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "set_props" in node.value
                    and id(node) not in docstrings
                )
            )
            if hit and where not in found:
                found.append(where)
    return found


class TestMountCallback:
    KEY = '{"chart":["MATCH"],"type":"explore-chart-mount"}.children'

    def test_no_runtime_module_builds_a_graph(self) -> None:
        assert RUNTIME_MODULES, "no runtime modules found"
        found = {
            str(path): calls
            for path in RUNTIME_MODULES
            if (calls := graph_uses(path.read_text(encoding="utf-8")))
        }
        assert found == {}

    @pytest.mark.parametrize(
        ("source", "caught"),
        [
            ("from dash import dcc\ndcc.Graph(id='x')\n", True),
            ("import dash\ndash.dcc.Graph()\n", True),
            ("from dash.dcc import Graph\nGraph()\n", True),
            ("from dash.dcc import Graph as G\nG(figure={})\n", True),
            ("from dash import dcc as d\nd.Graph()\n", True),
            # #452's review: an alias, a partial, an indexed reference, a subclass,
            # getattr, and a graph returned as component JSON.
            ("from dash import dcc\nmake = dcc.Graph\nmake(id=1)\n", True),
            ("import functools\nfrom dash import dcc\nfunctools.partial(dcc.Graph)()\n", True),
            ("from dash import dcc\n[dcc.Graph][0]()\n", True),
            ("from dash import dcc\nclass G(dcc.Graph):\n    pass\n", True),
            ("from dash import dcc\ngetattr(dcc, 'Graph')()\n", True),
            ("x = {'type': 'Graph', 'namespace': 'dash_core_components'}\n", True),
            # #452's round 2: Graph's own module, and a star import.
            ("from dash.dcc.Graph import Graph\nGraph()\n", True),
            ("from dash.dcc import *\nGraph()\n", True),
            ("from dash import dcc\nt = dcc.Graph._type\n", False),
            ("from dash import dcc\nn = dcc.Graph._namespace\n", False),
            ("from dash import dcc\ndcc.Store(id='s')\n", False),
            ('"""A docstring naming dash_core_components."""\n', False),
        ],
    )
    def test_the_lint_catches_the_listed_ways_to_reach_graph(
        self, source: str, caught: bool
    ) -> None:
        assert bool(graph_uses(source)) is caught

    def test_one_clientside_match_callback_on_the_source_with_the_mount_id(
        self,
    ) -> None:
        assert appmod.server.test_client().get("/").status_code == 200
        spec = appmod.app.callback_map[self.KEY]
        assert spec["inputs"] == [
            {"id": '{"chart":["MATCH"],"type":"explore-chart-source"}', "property": "data"}
        ]
        assert spec["state"] == [
            {"id": '{"chart":["MATCH"],"type":"explore-chart-mount"}', "property": "id"}
        ]
        assert "callback" not in spec  # clientside: no Python function runs
        mounted = [k for k in appmod.app.callback_map if charts.MOUNT_TYPE in k]
        assert mounted == [self.KEY]

    def test_the_chart_callbacks_graph_outputs_need_callback_exceptions_off(
        self,
    ) -> None:
        # The chart callback outputs to a graph no layout holds (#452; the mount
        # callback's output is the mount point, which the layout holds), which Dash
        # allows only with suppress_callback_exceptions.
        assert appmod.app.config.suppress_callback_exceptions is True

    def test_no_callback_writes_a_chart_source_store(self) -> None:
        """The mount callback runs once per mount because its one input, the source
        store, is never written (#452): a chart story that updated a figure by writing
        the store would remount its graph on every update. The two write paths guarded:
        no callback declares a source store as an output, and nothing but the theme
        listener (in ``app.THEME_CALLBACK``) calls ``set_props``. Not guarded: a
        callback's ``running=`` argument, which sets props too."""
        assert appmod.server.test_client().get("/").status_code == 200
        writers = [k for k in appmod.app.callback_map if charts.SOURCE_TYPE in k]
        assert writers == []
        assert charts.SOURCE_TYPE == "explore-chart-source"
        found = {
            path.name: refs
            for path in RUNTIME_MODULES
            if (refs := set_props_refs(path.read_text(encoding="utf-8")))
        }
        assert found == {"app.py": ["THEME_CALLBACK"]}

    @pytest.mark.parametrize(
        ("source", "found"),
        [
            ("import dash\ndef cb():\n    dash.set_props('s', {})\n", ["cb"]),
            ("from dash import set_props as s\ndef cb():\n    s('s', {})\n", ["line 1"]),
            ("JS = 'window.dash_clientside.set_props(id, {});'\n", ["JS"]),
            ("from dash import set_props\n", ["line 1"]),
            ("# set_props in a comment\nx = 1\n", []),
            ('"""A docstring naming set_props."""\n', []),
            ("def cb():\n    return 1\n", []),
        ],
    )
    def test_the_set_props_rule_finds_what_it_should(
        self, source: str, found: list[str]
    ) -> None:
        """Non-vacuity of the set_props guard, rule by rule (#452's round 2)."""
        assert set_props_refs(source) == found

    def test_its_text_returns_dccs_own_graph_with_the_shared_config_hidden(
        self,
    ) -> None:
        script = charts.CHART_MOUNT_CALLBACK
        start = script.index("var graph = ") + len("var graph = ")
        graph, _ = json.JSONDecoder().raw_decode(script[start:])
        assert graph == {
            "type": dash.dcc.Graph._type,
            "namespace": dash.dcc.Graph._namespace,
            "props": {"config": charts.CHART_CONFIG, "style": {"visibility": "hidden"}},
        }
        assert (graph["type"], graph["namespace"]) == ("Graph", "dash_core_components")
        assert (
            ' props.id = {type: "explore-chart-graph", chart: mount.chart};' in script
        )
        assert (
            " return {type: graph.type, namespace: graph.namespace, props: props}; });"
        ) in script

    def test_its_text_loads_plotlyjs_once_per_document_from_dashs_address(self) -> None:
        """Pins the callback's text only: what it does in a browser is pinned by
        ``test_two_charts_on_a_page_share_one_load``,
        ``test_two_blocked_charts_cost_one_fetch_and_one_error``,
        ``test_after_a_blocked_load_a_return_to_the_chart_makes_no_second_fetch`` and
        ``test_the_registered_mount_function_waits_for_plotlyjs_after_a_failed_load``
        (``tests/e2e/test_dashboard_e2e_charts.py``)."""
        script = charts.CHART_MOUNT_CALLBACK
        assert script.startswith("function (source, mount) {")
        assert f'var memo = "{charts.PLOTLYJS_MEMO}";' in script
        # window.Plotly first, on every call; then one memo, set before any wait and
        # never cleared.
        assert script.index("if (window.Plotly) { return Promise.resolve(true); }") < (
            script.index("if (!window[memo]) {")
        )
        assert "window[memo] = new Promise(function (resolve) {" in script
        assert script.count("window[memo] =") == 1
        assert "delete " not in script
        assert " var address = window._dashPlotlyJSURL;" in script
        assert (
            "if (typeof address !== 'string') {"
            " console.error('chart: no plotly.js address'); resolve(false); return; }"
        ) in script
        # The timeout gives up (resolves false), never mounts.
        assert (
            " var timer = setTimeout(function () { resolve(false); },"
            f" {charts.PLOTLYJS_TIMEOUT_MS});"
        ) in script
        assert script.count("resolve(true)") == 1  # only the window.Plotly shortcut
        assert charts.PLOTLYJS_TIMEOUT_MS == 30_000
        assert "resolve(Boolean(window.Plotly))" in script
        assert "if (!loaded) { return clientside.no_update; }" in script
        assert script.count("document.body.appendChild(script)") == 1

    def test_its_text_never_rejects_throws_or_builds_html(self) -> None:
        """Pins the callback's text only (its spelling); the browser tests named in
        :meth:`test_its_text_loads_plotlyjs_once_per_document_from_dashs_address` pin
        that a failed load logs nothing of its own."""
        script = charts.CHART_MOUNT_CALLBACK
        for banned in (
            "reject",
            "throw",
            "eval",
            "innerHTML",
            "Function(",
            "setAttribute",
            "fetch(",
            "integrity",
            "location",
            "history",
            "XMLHttpRequest",
            "sendBeacon",
        ):
            assert banned not in script, banned


# --- the not-drawn log check (#467, D095) --------------------------------------------


class TestNotDrawnLogCheck:
    """The check ``tests/unit/conftest.py`` runs after every dashboard test, on the
    error records ``components.chart`` leaves when it does not draw a figure."""

    @staticmethod
    def record(chart_id: Any = "C1") -> logging.LogRecord:
        record = logging.LogRecord(
            "explore.components", logging.ERROR, __file__, 1, "x not drawn", None, None
        )
        if chart_id is not None:
            record.chart_id = chart_id
        return record

    def test_no_record_and_none_expected_is_clean(self) -> None:
        assert chart_log_problems([], {}) == []

    def test_an_unexpected_record_fails(self) -> None:
        assert chart_log_problems([self.record()], {}) == [
            "C1: 1 not-drawn record(s), expected 0"
        ]

    def test_an_expected_record_is_clean(self) -> None:
        assert chart_log_problems([self.record()], {"C1": 1}) == []

    def test_a_wrong_count_or_a_missing_record_fails(self) -> None:
        two = [self.record(), self.record()]
        assert chart_log_problems(two, {"C1": 1}) == [
            "C1: 2 not-drawn record(s), expected 1"
        ]
        assert chart_log_problems([], {"C1": 1}) == [
            "C1: 0 not-drawn record(s), expected 1"
        ]

    def test_another_chart_is_not_excused_by_the_expected_one(self) -> None:
        records = [self.record("C1"), self.record("C3")]
        assert chart_log_problems(records, {"C1": 1}) == [
            "C3: 1 not-drawn record(s), expected 0"
        ]

    def test_a_record_naming_no_chart_fails(self) -> None:
        assert chart_log_problems([self.record(None)], {}) == [
            "an error record naming no chart: x not drawn"
        ]

    def test_the_conftest_check_is_listening_during_a_dashboard_test(self) -> None:
        """The autouse fixture runs for this file: exactly one of its handlers is on
        the builder's logger while a ``test_dashboard_*`` test body runs (so it is
        loaded, autouse, admits these files, attaches before the body and leaked no
        handler from an earlier test)."""
        handlers = logging.getLogger(LOGGER).handlers
        assert [type(h) for h in handlers].count(Records) == 1, handlers

    @pytest.mark.parametrize(
        ("path", "checked"),
        [
            ("tests/unit/test_dashboard_charts.py", True),
            ("tests/e2e/test_dashboard_e2e_charts.py", False),
            ("tests/unit/test_api_app.py", False),
            ("tests/integration/test_dashboard_x.py", False),
        ],
    )
    def test_only_unit_dashboard_files_are_checked(
        self, path: str, checked: bool
    ) -> None:
        """The one placement rule the fixture and the collection hook share."""
        assert chart_log_checked(Path("/repo") / path) is checked

    # The check itself, driven directly (#467 acceptance, Class B): each block below
    # also writes its records past this test's own conftest check, which the marker
    # holds to the exact total.
    UNIT = Path("/repo/tests/unit/test_dashboard_x.py")

    @staticmethod
    def log(*charts_: str) -> None:
        for chart_id in charts_:
            logging.getLogger(LOGGER).error("x", extra={"chart_id": chart_id})

    @pytest.mark.expected_chart_failure("C1")
    def test_the_check_fails_a_record_it_was_not_told_about(self) -> None:
        from tests.unit.conftest import chart_log_check

        with (
            pytest.raises(pytest.fail.Exception, match="C1: 1 not-drawn record"),
            chart_log_check(self.UNIT, []),
        ):
            self.log("C1")

    @pytest.mark.expected_chart_failure("C1", 2)
    def test_the_check_passes_what_its_markers_declare(self) -> None:
        from tests.unit.conftest import chart_log_check

        with chart_log_check(self.UNIT, [pytest.mark.expected_chart_failure("C1").mark]):
            self.log("C1")
        with (
            pytest.raises(pytest.fail.Exception, match="C1: 0 not-drawn record"),
            chart_log_check(self.UNIT, [pytest.mark.expected_chart_failure("C1").mark]),
        ):
            pass
        with chart_log_check(self.UNIT, []):
            pass
        self.log("C1")  # outside any block: only this test's own check sees it

    @pytest.mark.expected_chart_failure("C1", 3)
    def test_repeated_markers_for_one_chart_add_up(self) -> None:
        from tests.unit.conftest import chart_log_check

        twice = [
            pytest.mark.expected_chart_failure("C1").mark,
            pytest.mark.expected_chart_failure("C1", 2).mark,
        ]
        with chart_log_check(self.UNIT, twice):
            self.log("C1", "C1", "C1")

    @pytest.mark.expected_chart_failure("C1")
    def test_an_unchecked_file_is_not_checked(self) -> None:
        from tests.unit.conftest import chart_log_check

        with chart_log_check(Path("/repo/tests/e2e/test_dashboard_e2e_x.py"), []):
            self.log("C1")

    def test_the_collection_hook_refuses_a_misplaced_marker_only(self) -> None:
        """``tests/conftest.py``'s hook, called directly: an item carrying the marker
        outside the unit dashboard files is a usage error naming it; one inside, or an
        unmarked one anywhere, is not."""
        from types import SimpleNamespace

        from tests.conftest import pytest_collection_modifyitems

        mark = pytest.mark.expected_chart_failure("C1").mark

        def item(path: str, marked: bool) -> Any:
            return SimpleNamespace(
                nodeid=f"{path}::t",
                path=Path("/repo") / path,
                get_closest_marker=lambda name: mark if marked else None,
            )

        fine = [
            item("tests/unit/test_dashboard_x.py", True),
            item("tests/e2e/test_dashboard_e2e_x.py", False),
        ]
        pytest_collection_modifyitems(None, fine)  # type: ignore[arg-type]
        wrong = [*fine, item("tests/e2e/test_dashboard_e2e_x.py", True)]
        with pytest.raises(pytest.UsageError, match="tests/e2e/test_dashboard_e2e_x"):
            pytest_collection_modifyitems(None, wrong)  # type: ignore[arg-type]

    def test_the_marker_binds_its_count_by_position_or_name(self) -> None:
        from tests.unit.conftest import _expected_chart_failure

        assert _expected_chart_failure("C1") == ("C1", 1)
        assert _expected_chart_failure("C1", 2) == ("C1", 2)
        assert _expected_chart_failure("C1", count=3) == ("C1", 3)
        with pytest.raises(TypeError):
            _expected_chart_failure()  # type: ignore[call-arg]

    @pytest.mark.expected_chart_failure("C1", 2)
    def test_a_positional_count_is_held_exactly(self) -> None:
        logger = logging.getLogger(LOGGER)
        logger.error("one", extra={"chart_id": "C1"})
        logger.error("two", extra={"chart_id": "C1"})

    # The record this test writes reaches the conftest check too, which holds it to one.
    @pytest.mark.expected_chart_failure("C1")
    def test_the_handler_keeps_only_error_records_of_the_builder_logger(self) -> None:
        handler = Records()
        logger = logging.getLogger(LOGGER)
        logger.addHandler(handler)
        try:
            logger.warning("not an error")
            logger.error("an error", extra={"chart_id": "C1"})
            logging.getLogger("explore.api").error("another logger")
        finally:
            logger.removeHandler(handler)
        assert [r.getMessage() for r in handler.records] == ["an error"]
        assert components.log.name == LOGGER


# --- totality (#484, D099) -------------------------------------------------------------


#: A figure holding every slot :data:`charts.SLOT_KINDS` names, at every level the
#: checks read (layout, trace, marker, line, pattern, axis, legend, annotation), that
#: passes every rule: the base each case below changes one slot of.
BASE: dict[str, Any] = {
    "data": [
        {
            "type": "bar",
            "name": "A",
            "marker": {"color": "var(--chart-1)", "pattern": {"shape": "/"}},
            "text": ["a"],
            "textposition": "auto",
            "texttemplate": "%{text}",
            "hovertemplate": "%{customdata}<extra></extra>",
            "customdata": ["x"],
            "hovertext": ["h"],
        },
        {
            "type": "scatter",
            "mode": "markers+lines+text",
            "name": "B",
            "marker": {"symbol": "diamond", "color": "var(--chart-2)"},
            "line": {"dash": "dot", "color": "var(--chart-2)"},
            "text": ["b"],
            "hoverinfo": "text",
            "hovertemplate": "%{text}",
            "legend": "legend",
        },
    ],
    "layout": {
        "font": {"family": "var(--font-body)", "size": 12},
        "legend": {"font": {"color": "var(--text)"}},
        "xaxis": {"tickformat": ",d", "title": {"text": "t"}},
        "yaxis": {"automargin": True},
        "annotations": [{"text": "A", "font": {"size": 12}}],
    },
}

#: Each JSON value kind a slot is replaced by (AC1 of #484): strings empty, holding
#: ``var(``, ``<`` and ``%{``, and very long; a number of each kind, a boolean, null; a
#: list and an object, nested.
KINDS: dict[str, Any] = {
    "empty": "",
    "token": "var(--x)",
    "markup": "<b>",
    "placeholder": "%{y}",
    "long": "%{" * 100_000,
    "integer": 7,
    "huge integer": 10**5000,
    "float": 1.5,
    "boolean": True,
    "null": None,
    "list": ["a", ["b"]],
    "object": {"a": {"b": 1}},
}


def nested(levels: int) -> Any:
    """A string inside ``levels`` lists."""
    value: Any = "x"
    for _ in range(levels):
        value = [value]
    return value


SlotPath = tuple[str | int, ...]


def slots(value: Any, path: SlotPath = ()) -> list[SlotPath]:
    """Every slot under ``value``: each key of an object and each item of a list, as a
    path from the root. The test's own walk, never the module's."""
    found: list[SlotPath] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            found += [(*path, key), *slots(inner, (*path, key))]
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found += [(*path, index), *slots(inner, (*path, index))]
    return found


def first_items(paths: list[SlotPath]) -> list[SlotPath]:
    """``paths`` without a list item but the first, so a long list costs one slot."""
    return [p for p in paths if all(part == 0 for part in p if isinstance(part, int))]


def at(figure: Any, path: SlotPath) -> tuple[Any, str | int]:
    holder = figure
    for part in path[:-1]:
        holder = holder[part]
    return holder, path[-1]


def replaced(figure: Any, path: SlotPath, value: Any) -> Any:
    figure = copy.deepcopy(figure)
    holder, last = at(figure, path)
    holder[last] = value
    return figure


def dotted(path: SlotPath) -> str:
    """``path`` written as the module writes one (``data[0].marker``)."""
    text = ""
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else part)
    return text


def is_total(figure: Any) -> bool:
    problems = charts.figure_problems(figure)
    return isinstance(problems, list) and all(isinstance(p, str) for p in problems)


@pytest.fixture
def live_figures(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Each live registered chart's figure, as its page's default render builds it."""
    figures: dict[str, Any] = {}
    real = components.chart

    def recording(chart_id: str, figure: Any, *args: Any, **kwargs: Any) -> Any:
        figures[chart_id] = copy.deepcopy(figure)
        return real(chart_id, figure, *args, **kwargs)

    monkeypatch.setattr(components, "chart", recording)
    live = {c: row for c, row in charts.CHARTS.items() if not row.retired}
    for row in live.values():
        render(row.page, monkeypatch)
    monkeypatch.setattr(components, "chart", real)
    assert set(figures) == set(live)  # the premise: every live chart was built
    return figures


class TestTotality:
    """#484 (D099): ``figure_problems`` returns a list of strings and never raises,
    whatever any one slot holds. It calls ``figure_problems`` and no sub-check by
    name (``test_it_names_no_sub_check``), so a check added later is swept here, with
    no change to this class, over every slot BASE holds; a slot it newly reads by name
    must be declared in ``SLOT_KINDS`` and held by BASE
    (``test_every_slot_read_by_name_is_declared``, ``test_the_base_passes``)."""

    def test_the_base_passes(self) -> None:
        """And holds every declared slot, so the sweeps below change each one."""
        assert charts.figure_problems(BASE) == []
        held = {normalized(dotted(p)) for p in slots(BASE)}
        assert {
            f"{ANCHOR_PATHS[anchor]}.{key}"
            for anchor, table in EXPECTED_KINDS.items()
            if anchor != "any"
            for key in table
        } <= held
        keys = {p[-1] for p in slots(BASE)}
        assert set(EXPECTED_KINDS["any"]) <= keys

    @pytest.mark.parametrize("kind", list(KINDS))
    def test_every_slot_of_the_base_holding_each_kind(self, kind: str) -> None:
        raised = []
        for path in slots(BASE):
            try:
                total = is_total(replaced(BASE, path, KINDS[kind]))
            except Exception as error:  # noqa: BLE001 - the finding to report
                raised.append(f"{dotted(path)}: {type(error).__name__}")
            else:
                if not total:
                    raised.append(f"{dotted(path)}: not a list of strings")
        assert raised == []

    @pytest.mark.parametrize("kind", list(KINDS))
    def test_every_slot_of_every_live_chart_holding_each_kind(
        self, kind: str, live_figures: dict[str, Any]
    ) -> None:
        """Each live chart's own figure (C4 and C5 join by their registry rows), one
        item of each list."""
        raised = []
        for chart_id, figure in live_figures.items():
            for path in first_items(slots(figure)):
                holder, last = at(figure, path)
                kept = holder[last]
                holder[last] = KINDS[kind]
                try:
                    if not is_total(figure):
                        raised.append(f"{chart_id} {dotted(path)}: not a list of str")
                except Exception as error:  # noqa: BLE001 - the finding to report
                    raised.append(f"{chart_id} {dotted(path)}: {type(error).__name__}")
                finally:
                    holder[last] = kept
        assert raised == []

    @pytest.mark.parametrize(
        "path", [("layout", "meta"), ("data", 0, "customdata")], ids=dotted
    )
    def test_the_depth_bound_is_counted_from_the_root(self, path: SlotPath) -> None:
        """Containers from the root, the figure counted: at ``layout.meta`` (under two)
        and ``data[0].customdata`` (under three) the deepest value accepted is
        ``MAX_DEPTH`` less that many lists deep, and one more is refused, at its own
        path."""
        allowed = charts.MAX_DEPTH - len(path)
        assert charts.figure_problems(replaced(BASE, path, nested(allowed))) == []
        problems = charts.figure_problems(replaced(BASE, path, nested(allowed + 1)))
        deepest = dotted(path) + "[0]" * allowed
        assert problems == [f"{deepest}: nested deeper than {charts.MAX_DEPTH}"]

    @pytest.mark.parametrize("path", slots(BASE), ids=dotted)
    def test_a_value_deeper_than_the_recursion_limit_is_refused(
        self, path: SlotPath
    ) -> None:
        deep = nested(5_000)
        with pytest.raises(RecursionError):  # the premise: a recursive walk fails
            copy.deepcopy(deep)
        problems = charts.figure_problems(replaced(BASE, path, deep))
        assert problems and all("nested deeper than" in p for p in problems)

    @pytest.mark.parametrize(
        ("value", "problem"),
        [
            ({1}, "data[0].name: set, not a JSON value"),
            (("a",), "data[0].name: tuple, not a JSON value"),
            (object(), "data[0].name: object, not a JSON value"),
            ({1: "a"}, "data[0].name: int key, not a string"),
            (float("nan"), "data[0].name: not a finite number"),
            (float("inf"), "data[0].name: not a finite number"),
            (10**5000, "data[0].name: an integer beyond 2**53 - 1"),
            (-(2**53), "data[0].name: an integer beyond 2**53 - 1"),
        ],
        ids=["set", "tuple", "object", "int-key", "nan", "inf", "huge", "past-safe"],
    )
    def test_what_is_no_json_value_is_refused_alone(
        self, value: Any, problem: str
    ) -> None:
        """Refused by the structural check, whose problems come back alone, since
        every other check assumes a JSON value."""
        figure = copy.deepcopy(BASE)
        figure["data"][0]["name"] = value
        figure["layout"]["hovermode"] = "x unified"  # another rule, not reported
        assert charts.figure_problems(figure) == [problem]

    @pytest.mark.parametrize("value", [2**53 - 1, -(2**53 - 1)], ids=["max", "min"])
    def test_the_largest_exact_integer_is_accepted(self, value: int) -> None:
        """The integer bound's edge (#484's mutation pass): JavaScript's largest exact
        integer, either sign, is a value the figure may hold."""
        assert charts.figure_problems(replaced(BASE, ("layout", "meta"), value)) == []

    def test_a_cyclic_figure_ends(self) -> None:
        figure = copy.deepcopy(BASE)
        figure["layout"]["meta"] = figure["layout"]
        problems = charts.figure_problems(figure)
        assert problems and all("nested deeper than" in p for p in problems)

    def test_a_long_placeholder_string_is_checked_in_linear_time(self) -> None:
        figure = copy.deepcopy(BASE)
        long = "%{" * 100_000
        figure["data"][0].update(text=long, texttemplate=long, hovertemplate=long)
        started = time.perf_counter()
        assert is_total(figure)
        assert time.perf_counter() - started < 2

    def test_it_names_no_sub_check(self) -> None:
        """AC3: this class reaches the module only through ``figure_problems`` (and
        the depth bound it tests)."""
        tree = ast.parse(Path(__file__).read_text())
        [cls] = [
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "TestTotality"
        ]
        used = {
            n.attr
            for n in ast.walk(cls)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "charts"
        }
        assert used == {"figure_problems", "MAX_DEPTH"}


#: The kinds each slot a check reads may hold (#484, D099), written by hand, never read
#: from ``charts.SLOT_KINDS``, which must equal it: a kind widened or a slot dropped
#: there fails here.
EXPECTED_KINDS: dict[str, dict[str, set[str]]] = {
    "trace": {
        "type": {"a string"},
        "mode": {"a string"},
        "name": {"a string"},
        "hoverinfo": {"a string"},
        "textposition": {"a string"},
        "text": {"a string", "a list of strings"},
        "hovertext": {"a string", "a list of strings"},
        "customdata": {"a list", "a list of strings"},
        "marker": {"an object"},
        "line": {"an object"},
    },
    "marker": {"symbol": {"a string"}, "pattern": {"an object"}},
    "pattern": {"shape": {"a string"}},
    "line": {"dash": {"a string"}},
    "layout": {"legend": {"an object"}, "annotations": {"a list", "a list of strings"}},
    "axis": {"tickformat": {"a string"}},
    "annotation": {"text": {"a string"}},
    "any": {
        "family": {"a string"},
        "hovertemplate": {"a string", "a list of strings"},
        "texttemplate": {"a string", "a list of strings"},
    },
}
EXPECTED_ANCHOR_KINDS = {"axis": {"an object"}, "annotation": {"an object"}}

#: Where each anchor sits in :data:`BASE`, one path or more.
ANCHORS: dict[str, list[SlotPath]] = {
    "trace": [("data", 0), ("data", 1)],
    "marker": [("data", 0, "marker"), ("data", 1, "marker")],
    "pattern": [("data", 0, "marker", "pattern")],
    "line": [("data", 1, "line")],
    "layout": [("layout",)],
    "axis": [("layout", "xaxis"), ("layout", "yaxis")],
    "annotation": [("layout", "annotations", 0)],
    "any": [("data", 0), ("layout", "font"), ("layout", "annotations", 0, "font")],
}

#: A value of each kind, as ``charts`` names kinds.
SAMPLES: dict[str, list[Any]] = {
    "a string": ["s"],
    "a list of strings": [["s"], []],
    "a list": [[1], [["a"]], [{"a": "b"}]],
    "a number": [7, 1.5],
    "a boolean": [True],
    "null": [None],
    "an object": [{"a": "b"}],
}

#: Slots a check reads by name that ``SLOT_KINDS`` does not list by anchor: ``data`` and
#: ``layout``, the figure's own (``figure_problems`` checks both); slots whose own rule
#: pins the value whatever its kind (a trace's ``legend``, refused unless exactly
#: ``"legend"``; a bar's ``width`` and ``offset``, ``config`` and the layout's fixed
#: keys, each refused on any value); and the template keys, declared under ``any``.
OTHER_READS = {
    "data",
    "layout",
    "config",
    "data[i].legend",
    "data[i].width",
    "data[i].offset",
    "data[i].hovertemplate",
    "data[i].texttemplate",
    "layout.template",
    "layout.scattergap",
    *(f"layout.{key}" for key in charts.FIXED_LAYOUT_KEYS),
    *(f"layout.legend.{key}" for key in charts.FIXED_LEGEND_KEYS),
    *(f"layout.<axis>.{key}" for key in charts.FIXED_AXIS_KEYS),
}

#: Where each anchor of ``SLOT_KINDS`` sits, as a normalized read path.
ANCHOR_PATHS = {
    "trace": "data[i]",
    "marker": "data[i].marker",
    "pattern": "data[i].marker.pattern",
    "line": "data[i].line",
    "layout": "layout",
    "axis": "layout.<axis>",
    "annotation": "layout.annotations[i]",
}


class Reads(dict[str, Any]):
    """An object that records each key read from it by name (``get``, ``[]``,
    ``in``), found or not, into ``log``."""

    def __init__(self, data: dict[str, Any], path: str, log: set[str]) -> None:
        super().__init__(data)
        self.path, self.log = path, log

    def _read(self, key: Any) -> None:
        self.log.add(f"{self.path}.{key}" if self.path else str(key))

    def get(self, key: Any, default: Any = None) -> Any:
        self._read(key)
        return super().get(key, default)

    def __getitem__(self, key: Any) -> Any:
        self._read(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        self._read(key)
        return super().__contains__(key)


def recording(value: Any, path: str, log: set[str]) -> Any:
    if isinstance(value, dict):
        return Reads(
            {k: recording(v, f"{path}.{k}" if path else k, log) for k, v in value.items()},
            path,
            log,
        )
    if isinstance(value, list):
        return [recording(v, f"{path}[{i}]", log) for i, v in enumerate(value)]
    return value


def normalized(path: str) -> str:
    path = re.sub(r"\[\d+\]", "[i]", path)
    return re.sub(r"^layout\.[xy]axis\d*", "layout.<axis>", path)


def kind_refusals(problems: list[str], path: SlotPath) -> list[str]:
    """The problems refusing the kind ``path`` holds: another rule may refuse an
    expected kind's sample (a ``tickformat`` that shortens numbers), this one may not."""
    form = re.compile(rf"{re.escape(dotted(path))}: ({'|'.join(SAMPLES)}), not ")
    return [p for p in problems if form.match(p)]


class TestSlotKinds:
    """#484 (D099): a slot a check reads, holding a kind that check does not expect, is
    refused by a problem at that slot's own path; a kind it expects is not."""

    def test_the_table_is_the_hand_written_one(self) -> None:
        assert {
            anchor: {key: set(kinds) for key, kinds in table.items()}
            for anchor, table in charts.SLOT_KINDS.items()
        } == EXPECTED_KINDS
        assert {
            anchor: set(kinds) for anchor, kinds in charts.ANCHOR_KINDS.items()
        } == EXPECTED_ANCHOR_KINDS

    def test_every_kind_is_sampled(self) -> None:
        named = {k for t in EXPECTED_KINDS.values() for kinds in t.values() for k in kinds}
        assert named <= set(SAMPLES)

    @pytest.mark.parametrize(
        ("anchor", "key"),
        [(a, k) for a, table in EXPECTED_KINDS.items() for k in table],
        ids=lambda v: str(v),
    )
    def test_a_slot_refuses_each_kind_it_does_not_expect(
        self, anchor: str, key: str
    ) -> None:
        expected = EXPECTED_KINDS[anchor][key]
        for base_path in ANCHORS[anchor]:
            path = (*base_path, key)
            for kind, values in SAMPLES.items():
                for value in values:
                    problems = charts.figure_problems(replaced(BASE, path, value))
                    if kind in expected:
                        assert kind_refusals(problems, path) == [], (path, value)
                    else:
                        here = [p for p in problems if p.startswith(f"{dotted(path)}:")]
                        assert here, (path, value)

    @pytest.mark.parametrize("anchor", list(EXPECTED_ANCHOR_KINDS))
    def test_an_anchor_refuses_each_kind_it_does_not_expect(self, anchor: str) -> None:
        for path in ANCHORS[anchor]:
            for kind, values in SAMPLES.items():
                for value in values:
                    problems = charts.figure_problems(replaced(BASE, path, value))
                    if kind in EXPECTED_ANCHOR_KINDS[anchor]:
                        assert kind_refusals(problems, path) == [], (path, value)
                    else:
                        here = [p for p in problems if p.startswith(f"{dotted(path)}:")]
                        assert here, (path, value)

    def test_every_slot_read_by_name_is_declared(
        self, live_figures: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What the checks read by name, over the base, every case of the base with one
        slot changed, and each live chart's figure, is each a declared slot; and each
        declared slot is read by a check other than ``slot_problems``, which reads
        every declared slot by construction and is swapped out here so that half can
        fail. Reads by pattern (the walk's ``items()``, the layout's axis and
        second-legend scans) are invisible to this recorder, so ``any`` and the axis
        anchor are declared by hand."""
        monkeypatch.setattr(charts, "slot_problems", lambda figure: [])
        log: set[str] = set()
        figures = [BASE, *live_figures.values()]
        figures += [
            replaced(BASE, path, value)
            for path in slots(BASE)
            for value in ("s", 7, None, ["s"], {"a": "b"})
        ]
        for figure in figures:
            charts.figure_problems(recording(figure, "", log))
        read = {normalized(p) for p in log}
        declared = {
            f"{ANCHOR_PATHS[anchor]}.{key}"
            for anchor, table in EXPECTED_KINDS.items()
            if anchor != "any"
            for key in table
        }
        assert read - declared - OTHER_READS == set()
        assert declared - read == set()


class TestPlaceholderScan:
    """#484 (D099): the linear scan finds exactly the regex's placeholders."""

    PATTERN = re.compile(r"%\{[^}]*\}")

    def test_it_matches_the_pattern_on_every_short_string(self) -> None:
        for length in range(8):
            for chars in itertools.product("%{}a\n", repeat=length):
                text = "".join(chars)
                spans = [m.span() for m in self.PATTERN.finditer(text)]
                assert list(charts._placeholder_spans(text)) == spans, text
                assert charts._placeholders(text) == self.PATTERN.findall(text)
                assert charts._without_placeholders(text) == self.PATTERN.sub(
                    "", text
                )


class TestTotalityGuards:
    """#484 (D099): what the totality tests above cannot see. The bound's value, pinned
    by hand (a bound past the recursion limit would let ``components.chart``'s copy
    raise on a figure the check accepts); a figure exactly that deep drawn; no ``try``
    or ``suppress`` in the check or the chart builder (D095(f): totality is never a
    catch); and the caller's figure left whole on the not-drawn path."""

    def test_the_depth_bound_is_sixteen(self) -> None:
        assert charts.MAX_DEPTH == 16
        assert charts.MAX_INTEGER == 9_007_199_254_740_991

    @pytest.mark.usefixtures("registry")
    def test_a_figure_exactly_as_deep_as_the_bound_is_drawn(self) -> None:
        figure = copy.deepcopy(TEST_FIGURE)
        figure["layout"]["meta"] = nested(charts.MAX_DEPTH - 2)
        assert charts.figure_problems(figure) == []
        assert of_type(build(figure), "Store")  # drawn: it has its source store

    def test_no_catch_in_the_check_or_the_chart_builder(self) -> None:
        sources = {
            "charts": ast.parse(Path(charts.__file__).read_text(encoding="utf-8")),
            "components.chart": next(
                node
                for node in ast.walk(
                    ast.parse(Path(components.__file__).read_text(encoding="utf-8"))
                )
                if isinstance(node, ast.FunctionDef) and node.name == "chart"
            ),
        }
        found = {
            name: [
                type(node).__name__
                for node in ast.walk(tree)
                if isinstance(node, (ast.Try, ast.TryStar))
                or (isinstance(node, ast.Name) and node.id == "suppress")
                or (isinstance(node, ast.Attribute) and node.attr == "suppress")
            ]
            for name, tree in sources.items()
        }
        assert found == {"charts": [], "components.chart": []}

    @pytest.mark.usefixtures("registry")
    @pytest.mark.expected_chart_failure("C1", 2)
    def test_the_not_drawn_path_leaves_the_caller_s_figure_whole(self) -> None:
        deep = copy.deepcopy(TEST_FIGURE)
        deep["layout"]["meta"] = nested(5_000)
        odd = copy.deepcopy(TEST_FIGURE)
        odd["data"][0]["name"] = {"a set"}
        for figure in (deep, odd):
            assert of_type(build(figure), "Store") == []  # not drawn
            assert figure["layout"]["title"] == TEST_FIGURE["layout"]["title"]
