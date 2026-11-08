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
import json
import re
from pathlib import Path
from typing import Any

import dash
import pytest

from explore import app as appmod
from explore import charts, components, labels
from tests.unit.test_dashboard_elections import of_type
from tests.unit.test_dashboard_export import TEST_FIGURE
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
#: registers it; none is yet (C1–C5 are assigned to #433–#436 by their issues).
ISSUED: dict[str, tuple[str, str, bool]] = {}

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
    def test_it_refuses_a_figure_with_problems(
        self, change: Any, message: str
    ) -> None:
        """Each rule ``figure_problems`` gathers reaches the builder."""
        figure = copy.deepcopy(TEST_FIGURE)
        build(figure)  # the control: the figure passes before the change
        change(figure)
        with pytest.raises(ValueError, match=message):
            build(figure)


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
    """Every way ``source`` reaches ``dcc.Graph`` to build one (#452): any load of
    ``Graph`` (an attribute ``X.Graph``, or a name bound to it by ``from dash.dcc import
    Graph [as G]``), except as the base of a ``._type`` or ``._namespace`` read; a
    ``getattr(..., "Graph")``; and dcc's namespace written as a string (outside
    docstrings), which is how a server callback would return a graph as component JSON.
    One rule over loads, not calls, so an alias (``G = dcc.Graph``), a
    ``functools.partial``, an indexed reference and a subclass are all caught. A runtime
    module that built a graph, in a layout or a server callback's return, would mount it
    before plotly.js has loaded and bring Dash's blocked-CDN loop back. It reads source;
    a dynamic import or ``exec`` is the D070(b) lint's (``test_dashboard_guards.py``)."""
    tree = ast.parse(source)
    aliases = {
        a.asname or a.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module in ("dash", "dash.dcc")
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
        # The mount callback runs once per mount because its one input, the source
        # store, is never written (#452): a chart story that updated a figure by
        # writing the store would remount its graph on every update.
        assert appmod.server.test_client().get("/").status_code == 200
        writers = [k for k in appmod.app.callback_map if charts.SOURCE_TYPE in k]
        assert writers == []
        assert charts.SOURCE_TYPE == "explore-chart-source"

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
        ``test_the_registered_mount_function_does_nothing_after_a_failed_load``
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
        assert "if (typeof address !== 'string') {" in script
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
