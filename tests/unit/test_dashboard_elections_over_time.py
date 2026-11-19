"""The electors appointed and total popular vote page, ``/elections/over-time``:
charts C4 and C5 and their companion table (#436, D100), on their own page and for all
states only since #562 (D107).

Offline, against the recorded ``/v1/elections`` and N1 fixtures, through the helpers
and the autouse offline process client of ``test_dashboard_app.py``.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

import dash
import pytest

from explore import api, charts, components, labels, over_time
from tests.unit.test_dashboard_app import (
    RECORDED,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    texts,
)
from tests.unit.test_dashboard_elections import (
    BODY,
    COVERAGE,
    FIRST,
    LAST,
    SUMMARY,
    YEARS,
    c2_figure,
    find,
    in_order,
    of_type,
    render_majority,
)

PAGE: dict[str, Any] = dash.page_registry["pages.elections_over_time"]
#: The page module's namespace, reached through its layout (``pages.elections``' rule).
MOD: dict[str, Any] = PAGE["layout"].__globals__
PAGE_ID = MOD["PAGE_ID"]


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path"] == "/elections/over-time"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    # N1, C4 and C5's source: a literal filled on a miss (#436, D074(ii)); never N2.
    assert PAGE["on_miss"] == (api.SUMMARY_PATH,)
    assert PAGE["success"] == PAGE_ID
    assert PAGE.get("query") is None  # no filter reaches C4 or C5 (#562, D107)
    assert PAGE["nav"] == "elections"


# --- charts C4 and C5 (#436, D100) ---------------------------------------------------

#: N2, by its literal path: read by no page since #562; its recording stays test input.
N2: dict[str, Any] = RECORDED["/v1/elections/states"]
C4 = charts.dom_id("C4")
C5 = charts.dom_id("C5")
OVER_TIME = MOD["OVER_TIME_TABLE_ID"]
N1_ITEMS = {item["year"]: item for item in SUMMARY["elections"]}
PV_MIN, PV_MAX = COVERAGE["pv_year_min"], COVERAGE["pv_year_max"]


def render_over_time(
    query: dict[str, Any] | None = None,
    summary: Any = None,
    states: Any = None,
    index: Any = None,
    *,
    n2: bool = True,
) -> Any:
    """The page for the index and N1 (the recordings unless given). ``query``,
    ``states`` and ``n2`` are what the one-state mode read before #562 (D107); the page
    reads neither, so they change nothing."""
    return MOD["render"](
        copy.deepcopy(BODY if index is None else index),
        copy.deepcopy(SUMMARY if summary is None else summary),
    )


def chart_figure(tree: Any, dom: str) -> dict[str, Any]:
    (store,) = [
        node
        for node in of_type(tree, "Store")
        if isinstance(getattr(node, "id", None), dict) and node.id.get("chart") == dom
    ]
    figure: dict[str, Any] = store.data
    return figure


def trace(figure: dict[str, Any], name: str) -> dict[str, Any] | None:
    found = [t for t in figure["data"] if t.get("name") == name]
    assert len(found) <= 1
    return found[0] if found else None


#: The hover line carrying a C4 or C5 bar's table cell, which the bar's text label
#: carried before #558 (D104).
OVER_TIME_CELL_LINE = re.compile(
    r"<br>(?:Electors appointed|Total popular vote): (.*?)(?:<br>|$)"
)


def year_points(figure: dict[str, Any], name: str) -> dict[int, Any]:
    """A trace's points by year (its x, on the numeric year axis, #558, D104):
    ``{year: (value, label)}``, the value up the side and, for a bar, the table cell
    its hover writes, or for a marker the series' name, which the chart's key shows
    (no point carries text)."""
    t = trace(figure, name)
    if t is None:
        return {}
    assert "text" not in t
    assert t["ids"] == [str(x) for x in t["x"]]
    assert all(type(x) is int for x in t["x"])
    if t["type"] == "bar":
        found = [OVER_TIME_CELL_LINE.search(hover) for hover in t["hovertext"]]
        assert all(found), t["hovertext"]
        cells = [match.group(1) for match in found if match]
    else:
        assert t["showlegend"] is True and set(t["y"]) == {0}
        cells = [t["name"]] * len(t["x"])
    return dict(zip(t["x"], zip(t["y"], cells, strict=True), strict=True))


def state_rows(usps: str) -> list[dict[str, Any]]:
    return [row for row in N2["data"] if row["state_usps"] == usps]


def over_time_rows(tree: Any) -> list[list[str]]:
    table = find(tree, OVER_TIME)
    assert table is not None
    body = table.children[1]
    return [
        [
            "".join(texts(cell))
            if not isinstance(cell.children, str)
            else cell.children
            for cell in tr.children
        ]
        for tr in body.children
    ]


def after_2016() -> tuple[dict[str, Any], dict[str, Any]]:
    """The index with its popular-vote window ending in 2016, and N1 as such a snapshot
    serves it: no national total after the window."""
    moved = copy.deepcopy(BODY)
    moved["meta"]["provenance"]["coverage"]["pv_year_max"] = 2016
    summary = copy.deepcopy(SUMMARY)
    for row in summary["data"]:
        if row["year"] > 2016:
            row["national_pv_denominator"] = None
    return moved, summary


class TestC4:
    def test_registered_on_their_page_beside_the_shared_table(self) -> None:
        assert charts.CHARTS["C4"] == charts.Chart("/elections/over-time", OVER_TIME)
        assert charts.CHARTS["C5"] == charts.Chart("/elections/over-time", OVER_TIME)
        tree = render_over_time()
        assert type(find(tree, C4)).__name__ == "Figure"  # the #c4 fragment's target
        assert type(find(tree, C5)).__name__ == "Figure"

    def test_all_states_equals_each_n1_item_s_electoral_denominator(self) -> None:
        figure = chart_figure(render_over_time(), C4)
        drawn = year_points(figure, labels.LABELS["electoral_denominator"])
        assert {year: x for year, (x, _) in drawn.items()} == {
            year: item["electoral_denominator"] for year, item in N1_ITEMS.items()
        }
        assert all(text == f"{x:,}" for x, text in drawn.values())
        assert charts.figure_problems(figure) == []

    def test_a_null_or_unknown_allotment_is_a_marker_never_a_bar(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        summary["elections"][0]["electoral_denominator"] = None
        summary["elections"][1]["electoral_denominator"] = "x"
        figure = chart_figure(render_over_time(summary=summary), C4)
        assert year_points(figure, labels.NOT_IN_DATASET) == {
            YEARS[0]: (0, labels.NOT_IN_DATASET)
        }
        assert year_points(figure, labels.UNRECOGNIZED) == {
            YEARS[1]: (0, labels.UNRECOGNIZED)
        }
        assert charts.figure_problems(figure) == []

    def test_its_marker_symbols_are_pinned_and_distinct(self) -> None:
        """Each C4 marker series an all-states figure can reach has its own symbol
        (#498), one series per label (#558, D104), so no two differ by color alone;
        every such series is drawn here, from a doctored N1 (#562: no N2)."""
        summary = copy.deepcopy(SUMMARY)
        items = {item["year"]: item for item in summary["elections"]}
        items[1824]["electoral_denominator"] = 0  # no electors appointed
        items[1828]["electoral_denominator"] = None  # not in this dataset
        items[1832]["electoral_denominator"] = "x"  # unrecognized
        figure = chart_figure(render_over_time(summary=summary), C4)
        symbols = {
            t["name"]: t["marker"]["symbol"]
            for t in figure["data"]
            if t["type"] == "scatter"
        }
        # One symbol per meaning across C2, C4 and C5 (#558): no figure in this
        # dataset is C5's open circle.
        assert symbols == {
            labels.C4_NO_ELECTORS: "triangle-up-open",
            labels.NOT_IN_DATASET: "circle-open",
            labels.UNRECOGNIZED: "square-open",
        }


class TestC5:
    def test_all_states_equals_n1_s_national_total(self) -> None:
        figure = chart_figure(render_over_time(), C5)
        drawn = year_points(figure, labels.LABELS["national_pv_denominator"])
        expected = {
            row["year"]: row["national_pv_denominator"]
            for row in SUMMARY["data"]
            if row["national_pv_denominator"] is not None
        }
        assert {year: x for year, (x, _) in drawn.items()} == expected
        assert set(expected) == {y for y in YEARS if PV_MIN <= y <= PV_MAX}
        assert charts.figure_problems(figure) == []

def state_name(usps: str) -> str:
    return str(state_rows(usps)[0]["state"])


class TestTimeSeriesAxis:
    """The year axis every time-series chart shares (#558, D104): numeric, at the
    years themselves, with sparse, plain ticks, one axis in every mode; and each chart's
    points named by their year and carrying no text."""

    def test_the_ticks_are_every_40_years_written_plainly(self) -> None:
        axis = components.year_axis(YEARS)
        assert axis["type"] == "linear"
        assert axis["tickvals"] == [1840, 1880, 1920, 1960, 2000]
        assert axis["ticktext"] == ["1840", "1880", "1920", "1960", "2000"]
        assert axis["range"] == [FIRST - components.YEAR_PAD, LAST + components.YEAR_PAD]
        assert axis["title"] == {"text": labels.LABELS["year"]}
        assert components.YEAR_TICK_STEP == 40
        assert axis["tickfont"] == {"size": components.YEAR_TICK_FONT_PX} == {"size": 12}
        assert "tickformat" not in axis and "dtick" not in axis

    @pytest.mark.parametrize(
        ("years", "ticks"),
        [
            ([1964, 1968, 2000, 2024], [1964, 2024]),  # one multiple: both ends
            ([2000, 2004], [2000, 2004]),
            ([1960, 2000], [1960, 2000]),
            ([2024], [2024]),
        ],
    )
    def test_a_short_span_still_names_its_ends(
        self, years: list[int], ticks: list[int]
    ) -> None:
        axis = components.year_axis(years)
        assert axis["tickvals"] == ticks
        assert axis["ticktext"] == [str(t) for t in ticks]

    def test_a_gap_between_elections_is_drawn_at_its_true_width(self) -> None:
        """No even spacing: a figure built on served years 1824, 1828 and 1900 puts
        each point at its year, so the 72-year gap is 18 times the 4-year one."""
        years = [1824, 1828, 1900]
        axis = components.year_axis(years)
        assert axis["range"] == [1822, 1902]
        assert components.year_edges(years, 1828, 1828) == (1826, 1864)
        assert components.year_edges(years, 1824, 1828) == (1822, 1864)
        assert components.year_edges(years, 1900, 1900) == (1864, 1902)
        index = copy.deepcopy(BODY)
        index["data"] = [r for r in index["data"] if r["year"] in years]
        cov = index["meta"]["provenance"]["coverage"]
        cov["year_min"], cov["year_max"] = 1824, 1900
        summary = copy.deepcopy(SUMMARY)
        for key in ("data", "elections"):
            summary[key] = [r for r in summary[key] if r["year"] in years]
        figure = c2_figure(render_majority(summary, index))
        assert figure["data"][0]["x"] == years
        assert figure["layout"]["xaxis"] == components.year_axis(years)

    @pytest.mark.parametrize("query", [{}, {"state": "GA"}, {"state": "SC"}])
    def test_every_hover_names_its_year_on_x(self, query: dict[str, Any]) -> None:
        """AC: the hover on every point names its year, the year it is drawn at."""
        tree = render_over_time(query)
        figures = [chart_figure(tree, C4), chart_figure(tree, C5)]
        figures.append(c2_figure(render_majority()))
        for figure in figures:
            for t in figure["data"]:
                assert len(t["x"]) == len(t["hovertext"]) > 0
                for x, hover in zip(t["x"], t["hovertext"], strict=True):
                    assert hover.startswith(str(x)), (t["name"], x)

    @pytest.mark.parametrize("query", [{}, {"state": "GA"}, {"state": "SC"}])
    def test_no_point_bar_or_marker_carries_text(self, query: dict[str, Any]) -> None:
        """C2's points and C4 and C5's bars and markers draw no text (#558, D104):
        the hover and the chart's key carry it."""
        tree = render_over_time(query)
        for figure in (
            c2_figure(render_majority()),
            chart_figure(tree, C4),
            chart_figure(tree, C5),
        ):
            for t in figure["data"]:
                assert not {"text", "texttemplate", "textposition"} & set(t)
                assert "text" not in t.get("mode", "")

    def test_c2_s_marker_symbols_are_pinned_and_distinct(self) -> None:
        """Both C2 marker series drawn at once (#558, guard-efficacy F1): each its own
        symbol, written out, so neither differs from the other by color alone."""
        summary = copy.deepcopy(SUMMARY)
        leaders_ = [r for r in summary["data"] if r["electoral_rank"] == 1]
        leaders_[1]["ec_share_full"] = None
        leaders_[2]["ec_share_full"] = "zz"
        figure = c2_figure(render_majority(summary))
        symbols = {t["name"]: t["marker"]["symbol"] for t in figure["data"][1:]}
        assert symbols == {
            labels.C1_NO_SHARE: "circle-open",
            labels.UNRECOGNIZED: "square-open",
        }
        assert charts.figure_problems(figure) == []
        # Every hover, the markers' too, names the year it is drawn at (F5).
        for t in figure["data"]:
            for x, hover in zip(t["x"], t["hovertext"], strict=True):
                assert hover.startswith(f"{x}: "), (t["name"], x)
        assert [t["x"] for t in figure["data"][1:]] == [
            [leaders_[1]["year"]],
            [leaders_[2]["year"]],
        ]

    def test_points_and_markers_at_the_plot_s_edge_are_drawn_whole(self) -> None:
        """A marker at zero and a share near 100% sit on the plot's edge, where
        plotly's default would clip half of each (#558, review cr.1)."""
        summary = copy.deepcopy(SUMMARY)
        summary["data"][0]["ec_share_full"] = None
        figures = [c2_figure(render_majority(summary))]
        tree = render_over_time({"state": "SC"})
        figures += [chart_figure(tree, C4), chart_figure(tree, C5)]
        for figure in figures:
            for t in figure["data"]:
                if t["type"] == "scatter":
                    assert t["cliponaxis"] is False, t["name"]

    def test_the_pair_s_plots_start_at_one_height(self) -> None:
        """C4 takes C5's top margin, the room C5's band labels need (#558, cr.6)."""
        for query in ({}, {"state": "AK"}):
            tree = render_over_time(query)
            c4, c5 = chart_figure(tree, C4), chart_figure(tree, C5)
            assert c4["layout"]["margin"] == c5["layout"]["margin"]
            assert c5["layout"]["margin"]["t"] == (
                over_time.TOP_PX + MOD["_BAND_LABEL_PX"]
            )

    def test_no_years_is_a_type_error(self) -> None:
        """Caught by a page's degraded state, never a 500 (#558, cr.10)."""
        with pytest.raises(TypeError):
            components.year_axis([])

    def test_only_marker_series_join_the_key(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        for row in summary["data"]:
            if row["year"] == 2016:
                row["national_pv_denominator"] = "x"  # unrecognized, inside the window
        figure = chart_figure(render_over_time(summary=summary), C5)
        shown = {t["name"] for t in figure["data"] if t["showlegend"]}
        assert shown == {labels.UNRECOGNIZED}
        assert figure["layout"]["showlegend"] is True
        assert figure["layout"]["legend"] == components.TIME_SERIES_LEGEND
        assert chart_figure(render_over_time(), C4)["layout"]["showlegend"] is False

    def test_both_band_labels_sit_above_the_plot_never_in_a_band(self) -> None:
        """An after-band can be one election wide, so no band label is inside one
        (#558, architect I-2): each is above the plot, the before label at its band's
        left edge and raised over the after label, at its band's right edge."""
        moved, summary = after_2016()
        moved["meta"]["provenance"]["coverage"]["pv_year_max"] = 2020
        for row in summary["data"]:
            if row["year"] == 2020:
                (n1,) = [r for r in SUMMARY["data"] if r["year"] == 2020][:1]
                row["national_pv_denominator"] = n1["national_pv_denominator"]
        figure = chart_figure(render_over_time(index=moved, summary=summary), C5)
        before, after = figure["layout"]["shapes"]
        assert (after["x0"], after["x1"]) == (2022, LAST + components.YEAR_PAD)
        first_note, last_note = figure["layout"]["annotations"]
        for note in (first_note, last_note):
            assert (note["yref"], note["y"], note["yanchor"]) == ("paper", 1, "bottom")
        assert (first_note["x"], first_note["xanchor"]) == (before["x0"], "left")
        assert (last_note["x"], last_note["xanchor"]) == (after["x1"], "right")
        # The before label is raised by one label's room over the after label: two lines
        # of 12 px text at plotly's 1.3 line height, plus a gap, so the two never touch
        # (#558, guard-efficacy F2).
        assert first_note["yshift"] == MOD["_BAND_LABEL_PX"] and last_note["yshift"] == 0
        assert first_note["font"]["size"] == last_note["font"]["size"] == 12
        assert MOD["_BAND_LABEL_PX"] >= 2 * math.ceil(12 * 1.3) + 4
        assert figure["layout"]["margin"]["t"] == (
            over_time.TOP_PX + 2 * MOD["_BAND_LABEL_PX"]
        )
        assert charts.figure_problems(figure) == []


def ids_of(tree: Any) -> list[Any]:
    """Every component id in a rendered tree, in document order."""
    return [n.id for n in in_order(tree) if getattr(n, "id", None) is not None]


class TestWideLayout:
    """C4 and C5's pair (#553, D102), on their own page since #562."""

    def test_the_over_time_pair_holds_c4_left_and_c5_right(self) -> None:
        tree = render_over_time()
        pair = find(tree, MOD["OVER_TIME_PAIR_ID"])
        assert pair is not None and pair.className == "pair"
        left, right = pair.children
        assert [f.id for f in of_type(left, "Figure")] == [C4]
        assert [f.id for f in of_type(right, "Figure")] == [C5]
        assert of_type(pair, "Table") == [] and find(pair, OVER_TIME) is None
        # The companion table after the pair, full width (D102(d), D103).
        order = ids_of(tree)
        assert order.index(C5) < order.index(OVER_TIME)

    def test_the_heading_and_lede_open_the_page_with_no_control(self) -> None:
        """No filter reaches the page (#562): no dropdown, slider or checklist."""
        tree = render_over_time()
        kids = list(tree.children)
        assert type(kids[0]).__name__ == "H1" and kids[1].className == "lede"
        for kind in ("Dropdown", "RangeSlider", "Checklist", "Location"):
            assert of_type(tree, kind) == [], kind

    def test_an_unavailable_n1_builds_no_over_time_pair(self) -> None:
        tree = MOD["render"](copy.deepcopy(BODY), None)
        assert find(tree, MOD["OVER_TIME_PAIR_ID"]) is None
