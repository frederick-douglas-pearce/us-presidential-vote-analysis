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

from explore import api, charts, components, elections_view, labels, over_time
from tests.dashboard_cards import cards, in_one_card
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
    caption_text,
    classed,
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
    # The elections pages' one parser (#596, D110, amending D107's all-years scope).
    assert PAGE["query"] is elections_view.parse_filters
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


def agreeing(index: dict[str, Any]) -> dict[str, Any]:
    """``index`` with each row's ``has_popular_vote`` true exactly inside its coverage
    window, as a snapshot serves it: the page checks the two agree (``index_rule``,
    #596), so a test that moves the window moves the flags with it."""
    coverage = index["meta"]["provenance"]["coverage"]
    for row in index["data"]:
        row["has_popular_vote"] = (
            coverage["pv_year_min"] <= row["year"] <= coverage["pv_year_max"]
        )
    return index


def after_2016() -> tuple[dict[str, Any], dict[str, Any]]:
    """The index with its popular-vote window ending in 2016, and N1 as such a snapshot
    serves it: no national total after the window."""
    moved = copy.deepcopy(BODY)
    moved["meta"]["provenance"]["coverage"]["pv_year_max"] = 2016
    agreeing(moved)
    summary = copy.deepcopy(SUMMARY)
    for row in summary["data"]:
        if row["year"] > 2016:
            row["national_pv_denominator"] = None
    return moved, summary


N1_TOTALS = {row["year"]: row["national_pv_denominator"] for row in SUMMARY["data"]}


def caption(tree: Any, dom: str) -> str:
    """A chart's caption text, without its table pointer."""
    (figcaption,) = of_type(find(tree, dom), "Figcaption")
    return caption_text(figcaption)


class TestC4:
    def test_each_bar_series_is_its_measure_s_color(self) -> None:
        """#593 (D109): electors appointed is electoral (red), the total popular
        vote popular-vote (blue); read by measure, not by position."""
        tree = render_over_time()
        for dom, field, color in (
            (C4, "electoral_denominator", "var(--chart-ec)"),
            (C5, "national_pv_denominator", "var(--chart-pv)"),
        ):
            (bars,) = [
                tr for tr in chart_figure(tree, dom)["data"] if tr["type"] == "bar"
            ]
            assert bars["name"] == labels.LABELS[field]
            assert bars["marker"]["color"] == color

    def test_the_captions_are_collapsed(self) -> None:
        """#593 (D109): each caption closed under its summary, the pointer shown."""
        tree = render_over_time()
        for dom in (C4, C5):
            (figcaption,) = of_type(find(tree, dom), "Figcaption")
            details, pointer = figcaption.children
            assert type(details).__name__ == "Details"
            assert details.children[0].children == labels.CHART_CAPTION_SUMMARY
            assert pointer.children[0].children == labels.CHART_TABLE_POINTER

    def test_registered_on_their_page_beside_the_shared_table(self) -> None:
        assert charts.CHARTS["C4"] == charts.Chart("/elections/over-time", OVER_TIME)
        # C5's value axis writes its numbers short, one of the chart rule's two
        # exceptions with C10's (#596, D110; #582, D113).
        assert charts.CHARTS["C5"] == charts.Chart(
            "/elections/over-time", OVER_TIME, short_value_ticks=True
        )
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
        assert charts.figure_problems(figure, short_value_ticks=True) == []

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
        agreeing(moved)
        assert band(moved) == (FIRST - pad, (1976 + 1980) / 2)
        figure = chart_figure(render_over_time(index=moved), C5)
        # One label, inside the band at its top left (#593, D109).
        (note,) = figure["layout"]["annotations"]
        assert note["text"] == labels.C5_BEFORE_BAND.format(pv_year_min=1980)
        assert (note["xref"], note["x"], note["xanchor"]) == ("x", FIRST - pad, "left")
        assert (note["yref"], note["y"], note["yanchor"]) == ("paper", 1, "top")
        inset = over_time.BAND_LABEL_INSET_PX
        assert (note["yshift"], note["xshift"]) == (-inset, inset)

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

    @pytest.mark.parametrize(
        ("marker_labels", "symbols"),
        [
            (labels.C5_MARKER_LABELS, MOD["_C5_SYMBOLS"]),
            # C10 shares C5's figure since #582 (D113(d)).
            (labels.C10_MARKER_LABELS, over_time.C10_SYMBOLS),
        ],
    )
    def test_every_marker_label_has_a_symbol(
        self, marker_labels: dict[str, str], symbols: dict[str, str]
    ) -> None:
        """A C5 or C10 marker label with no symbol would be dropped silently (#436's
        review; #582's, cr.13): inside the band that would read as a held popular
        vote."""
        assert set(marker_labels.values()) | {labels.UNRECOGNIZED} <= set(symbols)

    def test_c10_draws_c5_s_symbols(self) -> None:
        """One symbol per meaning (D113, amendment): every label C10 shares with C5
        keeps C5's symbol, and C10 has no other."""
        assert MOD["_C5_SYMBOLS"] == over_time.C10_SYMBOLS

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
        assert c4["layout"]["xaxis"] == components.year_axis(
            YEARS, tick_px=components.YEAR_TICK_NARROW_PX
        )
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
        # The section's note is in the section's one card (#567).
        in_one_card(tree, MOD["OVER_TIME_UNAVAILABLE_ID"])
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
            axis["tickfont"] == {"size": components.YEAR_TICK_FONT_PX} == {"size": 14}
        )
        assert "tickformat" not in axis and "dtick" not in axis

    @pytest.mark.parametrize(
        ("years", "ticks"),
        [
            # A shorter span takes a finer step, never a tick within a quarter step
            # of either end (#596, D110).
            ([1964, 1968, 2000, 2024], [1980, 2000]),
            ([1976, 2024], [1980, 1990, 2000, 2010, 2020]),
            ([1824, 1900], [1840, 1860, 1880]),
            ([1960, 2000], [1968, 1976, 1984, 1992]),
            # The first step that goes into the span at most five times, checked
            # before the end trim: 8 here, though 4 would draw five (#596's review).
            ([1900, 1924], [1904, 1912, 1920]),
            # Fewer than two inside: both ends.
            ([2000, 2004], [2000, 2004]),
            ([2024], [2024]),
        ],
    )
    def test_a_short_span_still_names_its_ends(
        self, years: list[int], ticks: list[int]
    ) -> None:
        axis = components.year_axis(years)
        assert axis["tickvals"] == ticks
        assert axis["ticktext"] == [str(t) for t in ticks]

    def test_no_span_writes_more_than_five_ticks(self) -> None:
        """#596 (D110(c)): over every first and last year a filter can leave, the axis
        writes at least one and at most ``YEAR_TICK_MAX`` ticks, each inside the span."""
        for i, first in enumerate(YEARS):
            for last in YEARS[i:]:
                ticks = components.year_axis([first, last])["tickvals"]
                assert 1 <= len(ticks) <= components.YEAR_TICK_MAX, (first, last)
                assert all(first <= t <= last for t in ticks), (first, last, ticks)

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
        circles = next(
            t for t in figure["data"] if t.get("name") == labels.LABELS["ec_share_full"]
        )
        assert circles["x"] == years
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

    def test_marker_trace_carries_its_keywords_and_keeps_its_defaults(self) -> None:
        """#564: C2 passes ``y``, ``size`` and ``color``; C4, C5 and C7 keep zeros, 9 and
        the text color."""
        plain = over_time.marker_trace("n", "x", [1824, 1828], ["a", "b"])
        assert plain["y"] == [0, 0]
        assert plain["marker"] == {"symbol": "x", "size": 9, "color": "var(--text)"}
        drawn = over_time.marker_trace(
            "n", "star", [1824], ["a"], y=[0.4], size=5, color="var(--chart-hybrid)"
        )
        assert drawn["y"] == [0.4]
        assert drawn["marker"] == {
            "symbol": "star",
            "size": 5,
            "color": "var(--chart-hybrid)",
        }

    def test_c5_s_bands_are_the_shared_pv_bands(self) -> None:
        """g.7 (#564's review): C5 draws exactly what ``over_time.pv_bands`` gives for its
        years and window, the function C2 shares, so the two cannot drift apart."""
        c5 = chart_figure(render_over_time(), C5)
        coverage = BODY["meta"]["provenance"]["coverage"]
        window = (coverage["pv_year_min"], coverage["pv_year_max"])
        years = sorted(row["year"] for row in BODY["data"])
        expected = over_time.pv_bands(
            years,
            window,
            labels.C5_BEFORE_BAND.format(pv_year_min=window[0]),
            labels.C5_AFTER_BAND.format(pv_year_max=window[1]),
        )
        assert c5["layout"]["shapes"] == expected.shapes
        assert c5["layout"]["annotations"] == expected.annotations
        # No after band: the before band's label takes no margin (#593, D109).
        assert expected.top_px == 0
        assert c5["layout"]["margin"]["t"] == over_time.TOP_PX

    def test_the_stacked_plots_share_one_left_and_right_margin(self) -> None:
        """#593 (D109): C4 above C5 on one year axis, so their plots start and end at
        the same x: one fixed left and right margin, and no value axis pushing its
        own. Each keeps its own top margin."""
        tree = render_over_time()
        c4, c5 = chart_figure(tree, C4), chart_figure(tree, C5)
        margin = MOD["OVER_TIME_MARGIN"]
        assert margin == {"l": 72, "r": 16}
        for figure in (c4, c5):
            assert {k: figure["layout"]["margin"][k] for k in "lr"} == margin
            assert figure["layout"]["yaxis"]["automargin"] is False
        assert c4["layout"]["margin"]["t"] == over_time.TOP_PX
        # Narrowed by that margin, their year ticks keep 12 px (#593: 14 px crowded at
        # 360 px); C2 and C7 take the shared 14 px.
        for figure in (c4, c5):
            assert figure["layout"]["xaxis"]["tickfont"] == {"size": 12}
        assert components.YEAR_TICK_NARROW_PX == 12

    def test_c7_keeps_its_own_margins(self) -> None:
        """The fixed margins are the over-time page's, never the shared layout's
        (#593's architect review, I2): C7's short ticks keep their width."""
        layout = over_time.time_layout("t", "a", list(YEARS), 10, marked=False)
        assert layout["margin"] == {"t": over_time.TOP_PX}
        assert "automargin" not in layout["yaxis"]

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

    def test_the_before_label_sits_in_its_band_and_the_after_label_above(
        self,
    ) -> None:
        """#593 (D109): the before band spans every year before the window, so its
        label sits inside it at its top left; an after band can be one election wide
        (#558, architect I-2), so its label sits above the plot at its right edge,
        raised over the chart's key when the key is drawn."""
        moved, summary = after_2016()
        moved["meta"]["provenance"]["coverage"]["pv_year_max"] = 2020
        agreeing(moved)
        for row in summary["data"]:
            if row["year"] == 2020:
                (n1,) = [r for r in SUMMARY["data"] if r["year"] == 2020][:1]
                row["national_pv_denominator"] = n1["national_pv_denominator"]
        figure = chart_figure(render_over_time(index=moved, summary=summary), C5)
        before, after = figure["layout"]["shapes"]
        assert (after["x0"], after["x1"]) == (2022, LAST + components.YEAR_PAD)
        first_note, last_note = figure["layout"]["annotations"]
        assert (first_note["yref"], first_note["y"], first_note["yanchor"]) == (
            "paper",
            1,
            "top",
        )
        assert (last_note["yref"], last_note["y"], last_note["yanchor"]) == (
            "paper",
            1,
            "bottom",
        )
        assert (first_note["x"], first_note["xanchor"]) == (before["x0"], "left")
        assert (last_note["x"], last_note["xanchor"]) == (after["x1"], "right")
        # No marker in this body, so no key and no raise (#593's review: literal, never
        # derived from the figure); the marked cases are
        # ``test_the_after_label_rises_one_key_row_per_key_entry``.
        assert figure["layout"]["showlegend"] is False
        key = 0
        assert first_note["yshift"] == -over_time.BAND_LABEL_INSET_PX
        assert last_note["yshift"] == key
        # The after label's room: two lines of 12 px text at plotly's 1.3 line height,
        # plus a gap (#558, guard-efficacy F2), over the key's.
        assert first_note["font"]["size"] == last_note["font"]["size"] == 12
        assert 2 * math.ceil(12 * 1.3) + 4 <= over_time.BAND_LABEL_PX
        assert figure["layout"]["margin"]["t"] == (
            over_time.TOP_PX + key + over_time.BAND_LABEL_PX
        )
        # The before label is two short lines (#593's ba spec), naming no year.
        assert first_note["text"] == labels.C5_BEFORE_BAND
        assert first_note["text"].count("<br>") == 1
        assert charts.figure_problems(figure, short_value_ticks=True) == []


    @pytest.mark.parametrize(("doctored", "rows"), [(("x",), 1), (("x", None), 2)])
    def test_the_after_label_rises_one_key_row_per_key_entry(
        self, doctored: tuple[Any, ...], rows: int
    ) -> None:
        """#593's review: with an after band drawn, the label is raised by one key row
        per entry the key shows (an unrecognized total, then also a missing one inside
        the window), and the top margin holds it."""
        moved, summary = after_2016()
        for value, year in zip(doctored, (1996, 2000), strict=False):
            for row in summary["data"]:
                if row["year"] == year:
                    row["national_pv_denominator"] = value
        figure = chart_figure(render_over_time(index=moved, summary=summary), C5)
        assert len([tr for tr in figure["data"] if tr["showlegend"]]) == rows
        (after,) = [
            n
            for n in figure["layout"]["annotations"]
            if n["text"] == labels.C5_AFTER_BAND.format(pv_year_max=2016)
        ]
        assert after["yshift"] == rows * 24
        assert figure["layout"]["margin"]["t"] == 16 + rows * 24 + 40

    def test_the_key_sits_above_the_plot(self) -> None:
        """#593 (D109), pinned by value, not by the constant compared with itself."""
        assert components.TIME_SERIES_LEGEND == {
            "orientation": "h",
            "yref": "paper",
            "y": 1,
            "yanchor": "bottom",
            "x": 0,
            "xanchor": "left",
        }


class TestWideLayout:
    """C4 and C5 stacked (#593, D109, amending D102 and D103(c)), on their own page
    since #562."""

    def test_c4_sits_above_c5_in_one_column_with_no_pair(self) -> None:
        tree = render_over_time()
        assert classed(tree, "pair") == []
        order = ids_of(tree)
        # C4, then C5, then the companion table (D102(d)).
        assert order.index(C4) < order.index(C5) < order.index(OVER_TIME)
        # Both charts sit directly in the page's one card (#567), with no wrapper.
        c4, c5 = find(tree, C4), find(tree, C5)
        (card,) = cards(tree)
        assert c4 in card.children and c5 in card.children

    def test_the_heading_and_lede_open_the_page_with_the_year_filters(self) -> None:
        """The year filters of ``/elections`` (#596, D110): one slider, one checklist
        and the page-local location, and no state dropdown (#562)."""
        tree = render_over_time()
        kids = list(tree.children)
        assert type(kids[0]).__name__ == "H1" and kids[1].className == "lede"
        assert of_type(tree, "Dropdown") == []
        for kind in ("RangeSlider", "Checklist", "Location"):
            assert len(of_type(tree, kind)) == 1, kind

    def test_an_unavailable_n1_builds_no_chart(self) -> None:
        tree = MOD["render"](copy.deepcopy(BODY), None)
        assert find(tree, C4) is None and find(tree, C5) is None


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

    def test_the_one_state_total_hover_writes_c10s_cells(self) -> None:
        """C5 asks for no state; one state's total hover is C10's (#582), and writes
        its table's cells: the total, then the popular-vote status (until #582 a state
        here raised, since #562 retired C5's one-state mode)."""
        point = over_time.Point(
            year=2016,
            appointed=None,
            appointed_cell="",
            total=4114732,
            total_cell="4,114,732",
            status="popular_vote",
            status_cell="Popular vote held",
        )
        assert over_time.point_hover(point, "Georgia", total=True) == (
            "2016: Georgia<br>Total popular vote: 4,114,732<br>"
            "Popular vote in this state: Popular vote held"
        )
        assert over_time.point_hover(point, None, total=True) == (
            "2016, all states<br>Total popular vote: 4,114,732"
        )


# --- the year filters, C5's short ticks and the narrow band (#596, D110) -----------------


def filtered_over_time(query: dict[str, str], summary: Any = None) -> Any:
    """The page under ``query``, read through the page's own parser."""
    return MOD["render"](
        copy.deepcopy(BODY),
        copy.deepcopy(SUMMARY) if summary is None else summary,
        elections_view.parse_filters(query),
    )


class TestOverTimeFilters:
    def test_the_filters_narrow_both_charts_and_the_table(self) -> None:
        tree = filtered_over_time({"year_from": "1900", "year_to": "1990"})
        shown = [y for y in YEARS if 1900 <= y <= 1990]
        assert [int(r[0]) for r in over_time_rows(tree)] == shown
        for dom in (C4, C5):
            axis = chart_figure(tree, dom)["layout"]["xaxis"]
            assert axis == components.year_axis(
                shown, tick_px=components.YEAR_TICK_NARROW_PX
            )

    def test_popular_vote_only_draws_no_band(self) -> None:
        figure = chart_figure(filtered_over_time({"pv": "1"}), C5)
        assert not figure["layout"].get("shapes")
        assert not figure["layout"].get("annotations")

    def test_a_filter_leaving_no_year_shows_the_empty_note(self) -> None:
        tree = filtered_over_time({"year_to": "1972", "pv": "1"})
        assert tree.id == PAGE_ID
        assert find(tree, elections_view.NO_MATCH_ID).children == (
            labels.NO_ELECTIONS_MATCH
        )
        assert find(tree, C4) is None and find(tree, C5) is None
        assert find(tree, MOD["OVER_TIME_TABLE_ID"]) is None
        assert len(of_type(tree, "RangeSlider")) == 1
        # The note and the filters share the section's one card (#567).
        assert in_one_card(tree, elections_view.NO_MATCH_ID) is in_one_card(
            tree, elections_view.YEARS_ID
        )

    def test_a_failed_n1_shows_no_filters(self) -> None:
        tree = MOD["render"](copy.deepcopy(BODY), None, [("pv", "1")])
        assert of_type(tree, "RangeSlider") == []
        (lede,) = [p for p in of_type(tree, "P") if p.className == "lede"]
        assert lede.children == MOD["LEDE"]

    def test_an_old_state_key_still_changes_nothing(self) -> None:
        assert elections_view.parse_filters({"state": "GA"}) == []
        assert PAGE["query"]({"state": "GA"}) == []


class TestC5ShortTicks:
    def test_c5_writes_short_ticks_and_c4_full_ones(self) -> None:
        tree = render_over_time()
        c4, c5 = chart_figure(tree, C4), chart_figure(tree, C5)
        assert c5["layout"]["yaxis"]["tickformat"] == "~s"
        assert "tickformat" not in c4["layout"]["yaxis"]
        assert charts.figure_problems(c5, short_value_ticks=True) == []
        # The hover and the table keep full numbers.
        (bar,) = [t for t in c5["data"] if t.get("type") == "bar"]
        assert any(re.search(r"\d{1,3}(,\d{3}){2,}", h) for h in bar["hovertext"])
        assert any(
            re.fullmatch(r"\d{1,3}(,\d{3}){2,}", r[2]) for r in over_time_rows(tree)
        )

    def test_the_caption_explains_them_while_a_bar_is_drawn(self) -> None:
        tree = render_over_time()
        (caption,) = of_type(find(tree, C5), "Figcaption")
        assert labels.C5_SHORT_TICKS_NOTE in caption_text(caption)

    def test_with_no_bar_drawn_c5_writes_no_value_ticks(self) -> None:
        """ba spec (d)2 / architect Q2: before the window C5 draws no bar, its axis
        runs 0-1, and the SI form would write "200m"; it writes no value ticks."""
        tree = filtered_over_time({"year_to": "1972"})
        c5 = chart_figure(tree, C5)
        assert not [t for t in c5["data"] if t.get("type") == "bar"]
        assert c5["layout"]["yaxis"]["showticklabels"] is False
        assert "tickformat" not in c5["layout"]["yaxis"]
        (caption,) = of_type(find(tree, C5), "Figcaption")
        assert labels.C5_SHORT_TICKS_NOTE not in caption_text(caption)


class TestNarrowBand:
    def test_a_wide_before_band_keeps_its_label_inside(self) -> None:
        bands = over_time.pv_bands(YEARS, (1976, 2024), "before", "after")
        (note,) = bands.annotations
        assert (note["yanchor"], note["yshift"]) == (
            "top",
            -over_time.BAND_LABEL_INSET_PX,
        )
        assert bands.top_px == 0

    def test_a_narrow_before_band_puts_its_label_above_the_plot(self) -> None:
        """#596 (D110): a filter can leave the before band an election or two wide;
        under half of the axis, its label sits above the plot at its left edge."""
        years = [y for y in YEARS if y >= 1968]
        bands = over_time.pv_bands(years, (1976, 2024), "before", "after", key_px=24)
        (note,) = bands.annotations
        assert (note["xanchor"], note["yanchor"], note["yshift"]) == (
            "left",
            "bottom",
            24,
        )
        assert "xshift" not in note
        assert bands.top_px == over_time.TOP_PX + 24 + over_time.BAND_LABEL_PX

    def test_two_labels_above_stack(self) -> None:
        years = [y for y in YEARS if y >= 1968]
        bands = over_time.pv_bands(years, (1976, 2016), "before", "after", key_px=24)
        before, after = bands.annotations
        assert after["yshift"] == 24
        assert before["yshift"] == 24 + over_time.BAND_LABEL_PX
        assert bands.top_px == over_time.TOP_PX + 24 + 2 * over_time.BAND_LABEL_PX

    @staticmethod
    def share(years: list[int], pv_min: int) -> float:
        before = [y for y in years if y < pv_min]
        low, high = components.year_edges(years, before[0], before[-1])
        pad = components.YEAR_PAD
        return (high - low) / (max(years) + pad - (min(years) - pad))

    @pytest.mark.parametrize(
        ("years", "pv_min", "inside"),
        [
            # A band just over half of the padded axis (0.545) keeps its label inside.
            ([1900, 1904, 1908, 1912, 1916, 1920, 1924, 1928, 1932, 1936, 1940], 1924, True),
            # Exactly half: inside (the rule is "at least").
            ([1900, 1904, 1908, 1912, 1916, 1920], 1912, True),
            # Just under half (0.455): above the plot.
            ([1900, 1904, 1908, 1912, 1916, 1920, 1924, 1928, 1932, 1936, 1940], 1920, False),
        ],
    )
    def test_the_rule_is_at_least_half_the_padded_axis(
        self, years: list[int], pv_min: int, inside: bool
    ) -> None:
        """guard-efficacy .3: the threshold at its boundary, measured on the padded
        axis by the band's edges, never by its year count."""
        share = self.share(years, pv_min)
        assert (share >= over_time.BAND_INSIDE_SHARE) is inside, share
        bands = over_time.pv_bands(years, (pv_min, 2024), "before", "after", key_px=24)
        (note,) = bands.annotations
        assert note["yanchor"] == ("top" if inside else "bottom"), share
        assert bands.top_px == (
            0 if inside else over_time.TOP_PX + 24 + over_time.BAND_LABEL_PX
        )

    def test_the_cases_sit_at_the_boundary(self) -> None:
        """The cases above straddle 0.5 closely: a threshold above one half, a strict
        comparison, or an unpadded axis would flip one of them; the last assert pins
        the value itself, which a threshold just under one half would not flip."""
        years = [1900, 1904, 1908, 1912, 1916, 1920, 1924, 1928, 1932, 1936, 1940]
        shares = [
            self.share(years, 1924),
            self.share([1900, 1904, 1908, 1912, 1916, 1920], 1912),
            self.share(years, 1920),
        ]
        assert shares[0] > 0.5 and shares[1] == 0.5 and shares[2] < 0.5
        assert all(abs(x - 0.5) < 0.1 for x in shares), shares
        assert over_time.BAND_INSIDE_SHARE == 0.5


class TestOverTimeReviewGuards:
    """Guards #596's round-2 review found missing."""

    def test_a_hidden_year_s_defect_degrades_the_filtered_view_too(self) -> None:
        """r2.1: every served year's point and table row are built before the filters
        apply, so a filtered view never shows what the default view refuses (D110(a),
        its addendum). 1828 is hidden by ``year_from=1900``."""
        summary = copy.deepcopy(SUMMARY)
        (item,) = [i for i in summary["elections"] if i["year"] == 1828]
        del item["electoral_denominator"]
        for pairs in ([], [("year_from", "1900")]):
            tree = MOD["render"](copy.deepcopy(BODY), copy.deepcopy(summary), pairs)
            assert find(tree, MOD["OVER_TIME_UNAVAILABLE_ID"]) is not None, pairs
            assert find(tree, C4) is None and find(tree, C5) is None, pairs


# --- the headline figures (#600, D112(d), D114) ----------------------------------------

FIGURES = MOD["METRICS_ID"]
FIGURE_IDS: dict[str, str] = MOD["METRIC_IDS"]


def figure_text(tree: Any, key: str) -> str:
    """A figure's ``dd`` text, its value and the rest run together."""
    dd = find(tree, FIGURE_IDS[key])
    assert dd is not None, key
    return "".join(texts(dd))


def figure_notes(tree: Any) -> list[str]:
    block = find(tree, FIGURES)
    return ["".join(texts(p)) for p in of_type(block, "P")]


class TestOverTimeFigures:
    def test_the_hand_counts(self) -> None:
        # #569's plan recordings, as the companion table writes each value.
        tree = render_over_time()
        span = "among 51 elections with a figure (1824–2024)"
        pv = "among 13 elections with a figure (1976–2024)"
        assert {key: figure_text(tree, key) for key in FIGURE_IDS} == {
            "ec_appointed_first": f"261 in 1824, {span}",
            "ec_appointed_latest": f"538 in 2024, {span}",
            "pv_total_first": f"81,601,344 in 1976, {pv}",
            "pv_total_latest": f"155,410,204 in 2024, {pv}",
        }
        assert figure_notes(tree) == [
            labels.METRIC_PV_TOTAL_WINDOW_NOTE.format(first=PV_MIN, last=PV_MAX)
        ]

    @pytest.mark.parametrize(
        "query",
        [
            {},
            {"year_from": "1900", "year_to": "1990"},
            {"pv": "1"},
            {"year_from": "2000"},
        ],
    )
    def test_each_figure_is_its_year_s_table_cell(self, query: dict[str, str]) -> None:
        # D097(a)'s reconcile clause: the figure's value is the cell the table shows.
        tree = filtered_over_time(query)
        rows = {int(row[0]): row for row in over_time_rows(tree)}
        for key, column in (
            ("ec_appointed_first", 1),
            ("ec_appointed_latest", 1),
            ("pv_total_first", 2),
            ("pv_total_latest", 2),
        ):
            text = figure_text(tree, key)
            if text.startswith("No figure"):
                continue
            value, year = re.fullmatch(r"(\S+) in (\d{4}),.*", text).groups()  # type: ignore[union-attr]
            assert rows[int(year)][column] == value, (query, key)

    def test_the_filters_set_the_years_and_the_window_wording(self) -> None:
        tree = filtered_over_time({"year_from": "1900", "year_to": "1960"})
        assert figure_text(tree, "ec_appointed_first").startswith(
            "447 in 1900, among 16"
        )
        window = labels.METRIC_NO_FIGURE_PV_YEARS.format(first=PV_MIN, last=PV_MAX)
        assert figure_text(tree, "pv_total_first") == window
        assert figure_text(tree, "pv_total_latest") == window
        # No total shows a number, so no window note.
        assert figure_notes(tree) == []

    def test_the_popular_vote_filter_moves_the_earliest_electors(self) -> None:
        tree = filtered_over_time({"pv": "1"})
        assert figure_text(tree, "ec_appointed_first").startswith(
            "538 in 1976, among 13"
        )

    def test_one_year_keeps_every_figure_and_shows_one_value(self) -> None:
        tree = filtered_over_time({"year_from": "2000", "year_to": "2000"})
        assert all(find(tree, ident) is not None for ident in FIGURE_IDS.values())
        assert figure_text(tree, "ec_appointed_first") == (
            "538 in 2000, the only election shown with a figure"
        )
        assert figure_text(tree, "ec_appointed_latest") == (
            labels.METRIC_SELECT_SAME.format(other="earliest", year=2000)
        )

    def test_they_sit_in_the_charts_card_after_the_filters_and_before_c4(self) -> None:
        tree = render_over_time()
        in_one_card(tree, FIGURES)
        ids = ids_of(tree)
        assert ids.index(elections_view.YEARS_ID) < ids.index(FIGURES) < ids.index(C4)

    def test_no_year_shown_shows_no_figure(self) -> None:
        tree = filtered_over_time({"pv": "1", "year_from": "1824", "year_to": "1960"})
        assert find(tree, FIGURES) is None

    @pytest.mark.parametrize("summary", [None, "malformed"])
    def test_a_failed_or_malformed_n1_removes_them_with_the_section(
        self, summary: Any
    ) -> None:
        if summary == "malformed":
            summary = copy.deepcopy(SUMMARY)
            summary["data"][0]["national_pv_denominator"] = 5  # two values in 1824
            tree = render_over_time(summary=summary)
        else:
            tree = MOD["render"](copy.deepcopy(BODY), None)
        assert find(tree, FIGURES) is None
        assert find(tree, MOD["OVER_TIME_UNAVAILABLE_ID"]) is not None

    def test_a_value_its_cell_cannot_show_makes_that_field_unrecognized(self) -> None:
        # Architect I1 (D114): a float allotment, which the table reads Unrecognized
        # value, makes both electors figures unrecognized; the totals and charts stay.
        summary = copy.deepcopy(SUMMARY)
        item = next(i for i in summary["elections"] if i["year"] == 1900)
        item["electoral_denominator"] = 447.0
        tree = render_over_time(summary=summary)
        for key in ("ec_appointed_first", "ec_appointed_latest"):
            dd = find(tree, FIGURE_IDS[key])
            assert figure_text(tree, key) == labels.UNRECOGNIZED
            assert dd.title == labels.UNRECOGNIZED_NOTE
        assert figure_text(tree, "pv_total_first").startswith("81,601,344 in 1976")
        assert find(tree, C4) is not None and find(tree, OVER_TIME) is not None

    def test_og_url_reopens_the_same_figures(self) -> None:
        from explore import app as appmod

        query = "year_from=1980&year_to=2010&pv=1"
        resolution = appmod.resolve("/elections/over-time", query, None)
        assert resolution.og_url is not None
        normal = urllib.parse.urlsplit(resolution.og_url).query
        raw, reopened = (
            filtered_over_time(dict(urllib.parse.parse_qsl(q))) for q in (query, normal)
        )
        for key in FIGURE_IDS:
            assert figure_text(raw, key) == figure_text(reopened, key), key
