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
import urllib.parse
from typing import Any

import dash
import pytest

from explore import api, charts, components, labels, over_time
from tests.unit.test_dashboard_app import (
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    route,
    routed_ids,
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
    n1_client,
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

C4 = charts.dom_id("C4")
C5 = charts.dom_id("C5")
OVER_TIME = MOD["OVER_TIME_TABLE_ID"]
N1_ITEMS = {item["year"]: item for item in SUMMARY["elections"]}
PV_MIN, PV_MAX = COVERAGE["pv_year_min"], COVERAGE["pv_year_max"]


def render_over_time(summary: Any = None, index: Any = None) -> Any:
    """The page for the index and N1 (the recordings unless given)."""
    return MOD["render"](
        copy.deepcopy(BODY if index is None else index),
        copy.deepcopy(SUMMARY if summary is None else summary),
    )


def marked_summary() -> dict[str, Any]:
    """N1 doctored so both charts draw markers (ge.2, #562's review): C4 a zero, a
    null and an unrecognized allotment, C5 an unrecognized total inside the window.
    The recording draws every year as a bar, so a marker check on it checks nothing."""
    summary = copy.deepcopy(SUMMARY)
    items = {item["year"]: item for item in summary["elections"]}
    items[1824]["electoral_denominator"] = 0
    items[1828]["electoral_denominator"] = None
    items[1832]["electoral_denominator"] = "x"
    for row in summary["data"]:
        if row["year"] == 2016:
            row["national_pv_denominator"] = "x"
    return summary


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


N1_TOTALS = {row["year"]: row["national_pv_denominator"] for row in SUMMARY["data"]}


def caption(tree: Any, dom: str) -> str:
    """A chart's caption text, without its table pointer."""
    (figcaption,) = of_type(find(tree, dom), "Figcaption")
    return str(figcaption.children[0])


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

    @pytest.mark.parametrize("year", [1976, 1988, 2004, 2016])
    def test_a_year_with_a_candidate_lacking_popular_votes_is_one_total(
        self, year: int
    ) -> None:
        """The recorded years where a candidate has no popular-vote figure still
        carry one national total on every row (D100(c))."""
        rows = [row for row in SUMMARY["data"] if row["year"] == year]
        assert any(row["national_pv_votes"] is None for row in rows)  # the premise
        totals = MOD["national_pv"](SUMMARY, YEARS)
        assert totals[year] == rows[0]["national_pv_denominator"] is not None

    def test_the_band_comes_from_coverage_never_a_literal(self) -> None:
        def band(index: Any) -> tuple[float, float]:
            figure = chart_figure(render_over_time(index=index), C5)
            (shape,) = figure["layout"]["shapes"]
            # Vertical, the whole height of the plot (#558, D104).
            assert (shape["xref"], shape["yref"]) == ("x", "paper")
            assert (shape["y0"], shape["y1"]) == (0, 1)
            return shape["x0"], shape["x1"]

        pad = components.YEAR_PAD
        before = YEARS[YEARS.index(PV_MIN) - 1]
        assert band(BODY) == (FIRST - pad, (before + PV_MIN) / 2)
        moved = copy.deepcopy(BODY)
        moved["meta"]["provenance"]["coverage"]["pv_year_min"] = 1980
        assert band(moved) == (FIRST - pad, (1976 + 1980) / 2)
        figure = chart_figure(render_over_time(index=moved), C5)
        # One label, above the plot at the band's left edge, never inside the band.
        (note,) = figure["layout"]["annotations"]
        assert note["text"] == labels.C5_BEFORE_BAND.format(pv_year_min=1980)
        assert (note["xref"], note["x"], note["xanchor"]) == ("x", FIRST - pad, "left")
        assert (note["yref"], note["y"], note["yanchor"]) == ("paper", 1, "bottom")

    def test_a_year_after_the_window_is_banded_too(self) -> None:
        moved, summary = after_2016()
        figure = chart_figure(render_over_time(index=moved, summary=summary), C5)
        assert len(figure["layout"]["shapes"]) == 2
        texts_ = [a["text"] for a in figure["layout"]["annotations"]]
        assert labels.C5_AFTER_BAND.format(pv_year_max=2016) in texts_
        # 2020 and 2024 have no total now, so their rows are banded, never marked.
        marked = {y for t in figure["data"] for y in year_points(figure, t["name"])}
        assert not marked & {2020, 2024}
        tree = render_over_time(index=moved, summary=summary)
        note = labels.C5_AFTER_NOTE.format(pv_year_max=2016)
        assert any(note in text for text in texts(tree))

    def test_every_marker_label_has_a_symbol(self) -> None:
        """A C5 marker label with no symbol would be dropped silently (#436's
        review): inside the band that would read as a held popular vote."""
        symbols = MOD["_C5_SYMBOLS"]
        assert set(labels.C5_MARKER_LABELS.values()) | {labels.UNRECOGNIZED} <= set(
            symbols
        )

    def test_a_repeated_nan_total_is_one_unrecognized_value(self) -> None:
        """D100(c) (#498): every 2016 row's total NaN is one value, though NaN is
        unequal to itself, and C5 marks it unrecognized rather than degrading."""
        summary = copy.deepcopy(SUMMARY)
        for row in summary["data"]:
            if row["year"] == 2016:
                row["national_pv_denominator"] = float("nan")
        assert math.isnan(MOD["national_pv"](summary, YEARS)[2016])
        tree = render_over_time(summary=summary)
        assert find(tree, MOD["OVER_TIME_UNAVAILABLE_ID"]) is None
        figure = chart_figure(tree, C5)
        assert year_points(figure, labels.UNRECOGNIZED) == {
            2016: (0, labels.UNRECOGNIZED)
        }
        # The cell, not only the marker's label, reads unrecognized, and its hover
        # carries the note (the marker's label is the series', whatever the cell).
        by_year = {int(r[0]): r for r in over_time_rows(tree)}
        assert by_year[2016][2] == labels.UNRECOGNIZED
        marker = trace(figure, labels.UNRECOGNIZED)
        assert marker is not None
        (hover,) = marker["hovertext"]
        assert labels.UNRECOGNIZED_NOTE in hover

    def test_an_in_window_national_null_is_no_total(self) -> None:
        """All states (#498): a null national total inside the window is a marker
        naming it, as a state's is."""
        summary = copy.deepcopy(SUMMARY)
        for row in summary["data"]:
            if row["year"] == 2016:
                row["national_pv_denominator"] = None
        figure = chart_figure(render_over_time(summary=summary), C5)
        assert year_points(figure, labels.C5_NO_TOTAL) == {
            2016: (0, labels.C5_NO_TOTAL)
        }

    def test_no_bar_is_a_null_and_a_zero_total_is_a_bar(self) -> None:
        figure = chart_figure(render_over_time(), C5)
        for t in figure["data"]:
            if t["type"] == "bar":
                assert all(isinstance(x, int) and x >= 0 for x in t["x"])
        # A zero total is a drawn, labeled bar (D091); D100(d)'s exception is for
        # allotments only.
        summary = copy.deepcopy(SUMMARY)
        for row in summary["data"]:
            if row["year"] == 2016:
                row["national_pv_denominator"] = 0
        figure = chart_figure(render_over_time(summary=summary), C5)
        drawn = year_points(figure, labels.LABELS["national_pv_denominator"])
        assert drawn[2016] == (0, "0")

    def test_both_charts_share_one_year_axis(self) -> None:
        tree = render_over_time()
        c4, c5 = chart_figure(tree, C4), chart_figure(tree, C5)
        # One year axis, the served years' (D100(a), #558, D104).
        assert c4["layout"]["xaxis"] == c5["layout"]["xaxis"]
        assert c4["layout"]["xaxis"] == components.year_axis(YEARS)
        assert c4["layout"]["xaxis"]["range"][0] < FIRST


def ids_of(tree: Any) -> list[Any]:
    """Every component id in a rendered tree, in document order."""
    return [n.id for n in in_order(tree) if getattr(n, "id", None) is not None]


class TestOverTimeTable:
    def test_all_states_columns_rows_and_download(self) -> None:
        tree = render_over_time()
        table = find(tree, OVER_TIME)
        header = [th.title for th in table.children[0].children.children]
        assert header == list(MOD["OVER_TIME_FIELDS"])
        assert [int(r[0]) for r in over_time_rows(tree)] == YEARS
        link = find(tree, f"{OVER_TIME}-csv")
        assert link.download == "elections-electors-and-popular-vote-all-states.csv"

    def test_cells_before_inside_and_after_the_window(self) -> None:
        moved, summary = after_2016()
        by_year = {
            int(r[0]): r
            for r in over_time_rows(render_over_time(index=moved, summary=summary))
        }
        assert by_year[1824][2] == labels.NOT_APPLICABLE
        assert by_year[2024][2] == labels.NOT_APPLICABLE
        assert by_year[2016][2] == f"{N1_TOTALS[2016]:,}"

    def test_the_rows_are_the_charts_points(self) -> None:
        tree = render_over_time()
        table = {int(r[0]): r for r in over_time_rows(tree)}
        for dom, column in ((C4, 1), (C5, 2)):
            figure = chart_figure(tree, dom)
            for t in figure["data"]:
                if t["type"] != "bar":
                    continue
                for year, (value, text) in year_points(figure, t["name"]).items():
                    assert table[year][column] == text, (dom, year)
                    # The bar's height is the number its row writes (#558, I-5): with
                    # no text beside it, nothing else ties where it is drawn to the
                    # table.
                    assert labels.number(value) == text, (dom, year)


class TestOverTimeValidation:
    def test_national_pv_is_strict(self) -> None:
        def refuses(change: Any) -> None:
            summary = copy.deepcopy(SUMMARY)
            change(summary)
            with pytest.raises((KeyError, TypeError)):
                MOD["national_pv"](summary, YEARS)

        def first_of(year: int) -> Any:
            return lambda s: next(r for r in s["data"] if r["year"] == year)

        # A null beside a figure is two values (D077, D098).
        refuses(lambda s: first_of(2016)(s).update(national_pv_denominator=None))
        refuses(lambda s: first_of(2016)(s).update(national_pv_denominator=1))
        refuses(lambda s: first_of(2016)(s).pop("national_pv_denominator"))
        refuses(lambda s: s.update(data=[r for r in s["data"] if r["year"] != 1824]))
        refuses(lambda s: first_of(2016)(s).update(year=1825))
        refuses(lambda s: s.update(data={}))
        totals = MOD["national_pv"](SUMMARY, YEARS)
        assert totals[1824] is None and totals[2016] == N1_TOTALS[2016]

    def test_national_pv_counts_an_equal_float_as_a_second_total(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        rows = [r for r in summary["data"] if r["year"] == 2016]
        assert len(rows) > 1 and isinstance(rows[0]["national_pv_denominator"], int)
        rows[-1]["national_pv_denominator"] = float(rows[0]["national_pv_denominator"])
        with pytest.raises(TypeError, match="two national totals"):
            MOD["national_pv"](summary, YEARS)

    def test_same_is_one_type_and_equal_or_a_repeated_nan(self) -> None:
        """D100(c), the type check (#498): a value of another type is another value,
        however Python compares them; NaN with NaN is one."""
        same = over_time.same  # cr.10 (#560): the page keeps no alias
        assert not same(1, 1.0) and not same(1.0, 1)
        assert not same(True, 1) and not same(1, True)
        assert not same(None, 0)
        assert same(1, 1) and same(None, None) and same("GA", "GA")
        assert same(float("nan"), float("nan"))
        assert not same(float("nan"), 1.0)


class TestOverTimeDegraded:
    def test_an_unavailable_n1_shows_only_the_section_s_sentence(self) -> None:
        tree = MOD["render"](copy.deepcopy(BODY), None)
        assert find(tree, MOD["OVER_TIME_UNAVAILABLE_ID"]) is not None
        assert find(tree, C4) is None and find(tree, C5) is None
        assert find(tree, OVER_TIME) is None
        # The page's success marker, heading and lede stay (D096(d)'s rule).
        assert tree.id == PAGE_ID
        assert of_type(tree, "H1")[0].children == MOD["HEADING"]
        assert MOD["LEDE"] in texts(tree)

    def test_a_malformed_n1_shows_only_the_section_s_sentence(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        summary["data"][0]["national_pv_denominator"] = 5  # two values in 1824
        tree = render_over_time(summary=summary)
        assert find(tree, MOD["OVER_TIME_UNAVAILABLE_ID"]) is not None
        assert find(tree, C4) is None and find(tree, OVER_TIME) is None
        assert tree.id == PAGE_ID

    def test_one_fill_per_render_and_never_n2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """N1 is the page's one fill (#562, D107): an old ``state`` key reads no N2."""

        def down(path: str) -> api.Response:
            raise api.ApiUnavailable("down")

        calls, _ = n1_client(monkeypatch, down)
        ids = routed_ids(route("/elections/over-time", "?state=GA"))
        assert calls == [api.SUMMARY_PATH]
        assert PAGE_ID in ids and MOD["OVER_TIME_UNAVAILABLE_ID"] in ids

    def test_the_index_down_degrades_the_whole_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        tree = PAGE["layout"]()
        assert components.UNAVAILABLE_MESSAGE in texts(tree)
        assert find(tree, C4) is None and find(tree, PAGE_ID) is None
        assert of_type(tree, "H1")[0].children == MOD["HEADING"]


class TestOverTimeMechanisms:
    """Guards the acceptance gate's mutation pass found missing (#436)."""

    def test_a_boolean_count_is_an_unrecognized_marker_never_a_bar(self) -> None:
        """``True`` is an ``int`` to ``isinstance``; a bar needs a count of type ``int``
        itself, so a served boolean is a marker in both charts."""
        summary = copy.deepcopy(SUMMARY)
        for item in summary["elections"]:
            if item["year"] == 2016:
                item["electoral_denominator"] = True
        for row in summary["data"]:
            if row["year"] == 2016:
                row["national_pv_denominator"] = True
        tree = render_over_time(summary=summary)
        c4, c5 = chart_figure(tree, C4), chart_figure(tree, C5)
        assert 2016 not in year_points(c4, labels.LABELS["electoral_denominator"])
        assert 2016 not in year_points(c5, labels.LABELS["national_pv_denominator"])
        assert year_points(c4, labels.UNRECOGNIZED)[2016] == (
            0,
            labels.UNRECOGNIZED,
        )
        assert year_points(c5, labels.UNRECOGNIZED)[2016] == (0, labels.UNRECOGNIZED)

    def test_every_served_year_keeps_its_row_by_an_explicit_range(self) -> None:
        """Plotly's autorange would fit the drawn points: each chart fixes the year
        axis's range to every served year, oldest at the left (D100(a), #558, D104)."""
        tree = render_over_time()
        pad = components.YEAR_PAD
        for dom in (C4, C5):
            xaxis = chart_figure(tree, dom)["layout"]["xaxis"]
            assert xaxis["range"] == [FIRST - pad, LAST + pad], dom
            assert xaxis.get("autorange") in (None, False), dom


class TestOverTimeCaptions:
    """Each mode's caption sentences (#436's review): the all-states sentences
    only with all states, whatever the chosen state's first election."""

    def test_all_states(self) -> None:
        tree = render_over_time()
        c4, c5 = caption(tree, C4), caption(tree, C5)
        assert labels.C4_ALL_STATES in c4 and labels.C5_ALL_STATES in c5
        assert labels.C5_BEFORE_NOTE.format(pv_year_min=PV_MIN) in c5
        assert labels.C4_ZERO_NOTE not in c4 and labels.C5_MARKER_NOTE not in c5


class TestTimeSeriesAxis:
    """The year axis every time-series chart shares (#558, D104): numeric, at the
    years themselves, with sparse, plain ticks, one axis in every mode; and each chart's
    points named by their year and carrying no text."""

    def test_the_ticks_are_every_40_years_written_plainly(self) -> None:
        axis = components.year_axis(YEARS)
        assert axis["type"] == "linear"
        assert axis["tickvals"] == [1840, 1880, 1920, 1960, 2000]
        assert axis["ticktext"] == ["1840", "1880", "1920", "1960", "2000"]
        assert axis["range"] == [
            FIRST - components.YEAR_PAD,
            LAST + components.YEAR_PAD,
        ]
        assert axis["title"] == {"text": labels.LABELS["year"]}
        assert components.YEAR_TICK_STEP == 40
        assert (
            axis["tickfont"] == {"size": components.YEAR_TICK_FONT_PX} == {"size": 12}
        )
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

    @pytest.mark.parametrize("marked", [False, True])
    def test_every_hover_names_its_year_on_x(self, marked: bool) -> None:
        """AC: the hover on every point names its year, the year it is drawn at."""
        tree = render_over_time(marked_summary() if marked else None)
        figures = [chart_figure(tree, C4), chart_figure(tree, C5)]
        if marked:  # the premise: both charts draw a marker (r2.recheck.3)
            assert all(any(t["type"] == "scatter" for t in f["data"]) for f in figures)
        figures.append(c2_figure(render_majority()))
        for figure in figures:
            for t in figure["data"]:
                if t.get("hoverinfo") == "skip":  # C2's connector (#564): no hover
                    continue
                assert len(t["x"]) == len(t["hovertext"]) > 0
                for x, hover in zip(t["x"], t["hovertext"], strict=True):
                    assert hover.startswith(str(x)), (t["name"], x)

    @pytest.mark.parametrize("marked", [False, True])
    def test_no_point_bar_or_marker_carries_text(self, marked: bool) -> None:
        """C2's points and C4 and C5's bars and markers draw no text (#558, D104):
        the hover and the chart's key carry it."""
        tree = render_over_time(marked_summary() if marked else None)
        if marked:  # the premise: both charts draw a marker (r2.recheck.3)
            for dom in (C4, C5):
                assert any(
                    t["type"] == "scatter" for t in chart_figure(tree, dom)["data"]
                )
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
        names = (labels.C2_NO_FIGURE, labels.UNRECOGNIZED)
        marks = [t for t in figure["data"] if t["name"] in names]
        symbols = {t["name"]: t["marker"]["symbol"] for t in marks}
        assert symbols == {
            labels.C2_NO_FIGURE: "circle-open",
            labels.UNRECOGNIZED: "square-open",
        }
        assert charts.figure_problems(figure) == []
        # Every hover, the markers' too, names the year it is drawn at (F5).
        for t in figure["data"]:
            if t.get("hoverinfo") == "skip":  # C2's connector (#564): no hover
                continue
            for x, hover in zip(t["x"], t["hovertext"], strict=True):
                assert hover.startswith(f"{x}: "), (t["name"], x)
        assert [t["x"] for t in marks] == [
            [leaders_[1]["year"]],
            [leaders_[2]["year"]],
        ]

    def test_points_and_markers_at_the_plot_s_edge_are_drawn_whole(self) -> None:
        """A marker at zero and a share near 100% sit on the plot's edge, where
        plotly's default would clip half of each (#558, review cr.1)."""
        summary = copy.deepcopy(SUMMARY)
        summary["data"][0]["ec_share_full"] = None
        figures = [c2_figure(render_majority(summary))]
        tree = render_over_time(marked_summary())
        figures += [chart_figure(tree, C4), chart_figure(tree, C5)]
        for figure in figures:
            # The premise: each figure draws a marker, so the loop below checks one.
            assert any(t["type"] == "scatter" for t in figure["data"])
            for t in figure["data"]:
                if t["type"] == "scatter":
                    assert t["cliponaxis"] is False, t["name"]

    def test_the_pair_s_plots_start_at_one_height(self) -> None:
        """C4 takes C5's top margin, the room C5's band labels need (#558, cr.6)."""
        tree = render_over_time()
        c4, c5 = chart_figure(tree, C4), chart_figure(tree, C5)
        assert c4["layout"]["margin"] == c5["layout"]["margin"]
        assert c5["layout"]["margin"]["t"] == (over_time.TOP_PX + over_time.BAND_LABEL_PX)

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
        assert (
            first_note["yshift"] == over_time.BAND_LABEL_PX and last_note["yshift"] == 0
        )
        assert first_note["font"]["size"] == last_note["font"]["size"] == 12
        assert 2 * math.ceil(12 * 1.3) + 4 <= over_time.BAND_LABEL_PX
        assert figure["layout"]["margin"]["t"] == (
            over_time.TOP_PX + 2 * over_time.BAND_LABEL_PX
        )
        assert charts.figure_problems(figure) == []


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


class TestGuardsTheGateAdded:
    """Guards #562's acceptance gate found missing (Class B)."""

    def test_national_pv_refuses_a_row_for_a_year_not_served(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        summary["data"].append({**summary["data"][0], "year": 1826})
        with pytest.raises(TypeError, match="not served"):
            MOD["national_pv"](summary, YEARS)

    def test_the_download_names_this_page_as_its_view(self) -> None:
        link = find(render_over_time(), f"{OVER_TIME}-csv")
        text = urllib.parse.unquote(link.href)
        assert "explore.us-presidential-election-center.org/elections/over-time" in text

    def test_the_all_states_sentences_are_the_approved_wording(self) -> None:
        """ba spec rows 26 and 27, approved at #562's plan gate."""
        assert labels.C4_ALL_STATES == (
            "Each bar is the whole Electoral College that year: every state's "
            "electors appointed, added up."
        )
        assert labels.C5_ALL_STATES == (
            "Each bar is the national total: every state's total, added up."
        )

    def test_c5_has_no_one_state_hover(self) -> None:
        point = over_time.Point(
            year=2016,
            appointed=1,
            appointed_cell="1",
            total=1,
            total_cell="1",
            status=None,
            status_cell=None,
        )
        with pytest.raises(ValueError, match="all states only"):
            over_time.point_hover(point, "Georgia", total=True)
        assert over_time.point_hover(point, None, total=True).startswith("2016")
