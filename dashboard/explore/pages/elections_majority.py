"""Chart C2 and its companion table, on their own page (#434, D096; split by #562,
D107; extended by #564, D108): ``/elections/majority``, each served year's Electoral
College leader's electoral share, popular-vote share and hybrid score against the
majority line, from N1 (``api.SUMMARY_PATH``, filled on first use) read in the same
view as the index. The year filters of ``/elections`` narrow the chart, its table and
its download (#596, D110, reversing D096's "no filter"): the page's ``query=`` parser
is :func:`explore.elections_view.parse_filters`, and the controls sit in the chart's
section. A failed or malformed N1 degrades the chart's section only (D096(d)): the
heading, lede and success marker stay.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import dcc, html

from explore import (
    api,
    charts,
    components,
    election_view,
    elections_view,
    export,
    labels,
    over_time,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whether or not N1 could be read.
PAGE_ID = "elections-majority"
#: This page's own path, the view URL its download names.
PATH = elections_view.MAJORITY

#: Page-level wording (ba spec, approved by the owner at #562's plan gate, 2026-11-19).
#: The heading was C2's section heading on ``/elections`` (#434's plan gate).
HEADING = "Did the Electoral College leader win a majority?"
LEDE = (
    "For every election in this dataset: the candidate with the most electoral votes "
    "counted, and whether they won more than half of the electors appointed. For the "
    "years this dataset has popular-vote figures, the page also shows their "
    "popular-vote share and the hybrid score the project proposes."
)

#: Page-level wording (ba spec for #596, approved at #596's plan gate, 2026-11-20):
#: shown after :data:`LEDE` only when the filter controls render.
FILTER_SENTENCE = (
    "Narrow the chart and table by year, or to the years with a popular vote in this "
    "dataset."
)

#: Chart C2 (#434, D096) and its companion table, narrowed by the year filters since
#: #596 (D110).
C2_ID = "C2"
LEADER_TABLE_ID = "elections-leader-table"
LEADER_UNAVAILABLE_ID = "elections-leader-unavailable"
#: The companion table's columns, in display order, by public field name: the year's
#: Electoral College leader's national row, with the year's ``ec_determinative`` from
#: N1's ``elections`` item, and ``took_office`` (owner, #434's plan gate); then,
#: appended at the end by #564 (D108, amending D096(b)), the leader's ``pv_share`` and
#: ``hybrid_score`` and the year's ``pv_winner`` and ``hybrid_winner``.
LEADER_FIELDS = (
    "year",
    "candidate",
    "national_electoral_votes_counted",
    "national_electoral_denominator",
    "ec_share_full",
    "ec_determinative",
    "took_office",
    "pv_share",
    "hybrid_score",
    "pv_winner",
    "hybrid_winner",
)
#: The leader table's cells :func:`_leader_cells` words, in :data:`LEADER_FIELDS`
#: order (the year is a link and the candidate a linked name).
LEADER_WORDED = LEADER_FIELDS[2:]
#: Exported though not shown: the key of the candidate's history link.
LEADER_EXTRA = ("candidate_slug",)

C2_TABLE_HEADING = "Each election's Electoral College leader"
#: C2's section when N1 cannot be read or is malformed. Never ``UNAVAILABLE_MESSAGE``'s
#: wording: the D070(b) guard's success run asserts that absent from every page.
C2_UNAVAILABLE = (
    "The chart and table of each election's Electoral College leader can't be shown "
    "right now. Please try again in a minute."
)

#: C2's height (#564: taller than #558's 360 px, for the three marks a year and the
#: key; #593, D109: taller again, so the marks after 1976, which sit between 45% and
#: 60%, stand apart). Its title is page text (``components.chart`` takes it out of the
#: figure).
_C2_HEIGHT_PX = 560
#: The value axis runs past 100% to hold the strip of disagreement marks (#564, D108),
#: which sit at :data:`_C2_STRIP_Y`, above every share; its ticks stop at 100%.
_C2_Y_TOP = 1.12
_C2_STRIP_Y = 1.06
#: The value axis's ticks, and where the majority line sits among them (#593, D109):
#: every tick but 0, which is the axis line, and 50%, which is the majority line,
#: draws a gridline shape.
_C2_TICKS = (0, 0.25, 0.5, 0.75, 1)
_C2_MAJORITY = 0.5
#: C2's symbols (#558, D104; #564, D108): one per meaning across C2, C4, C5 and C7.
#: The open circle is no figure in this dataset and the open square an unrecognized
#: value, as in C4 and C5; the solid upward triangle is C2's alone (C4's open one means
#: no electors appointed: the fill carries the meaning).
_C2_EC_SYMBOL = "circle"
_C2_PV_SYMBOL = "triangle-up"
#: The hybrid score is a short horizontal crossbar on the connector (#593, D109): the
#: average of the other two shares, it always sits at the connector's midpoint, so a
#: crossbar reads as a tick on a range bar and stays visible when the circle and the
#: triangle nearly meet. ``line-ew`` and ``asterisk`` are line-only symbols, drawn
#: by their outline (:data:`_C2_LINE_PX`).
_C2_HYBRID_SYMBOL = "line-ew"
#: The crossbar's width (#596, D110: 16 px touched its neighbors at 360 px, where the
#: years after 1976 sit about 9 px apart): a little wider than the circle and the
#: triangle, :data:`_C2_EC_PX` and :data:`_C2_PV_PX`.
_C2_HYBRID_PX = 10
_C2_EC_PX = 7
_C2_PV_PX = 8
_C2_PV_DIFFERENT_SYMBOL = "asterisk"
_C2_HYBRID_DIFFERENT_SYMBOL = "pentagon"
#: The crossbar's and the asterisk's stroke width.
_C2_LINE_PX = 3
_C2_SYMBOLS = {
    labels.C2_NO_FIGURE: "circle-open",
    labels.UNRECOGNIZED: "square-open",
}
#: Each C2 series' stable identity, by series name (#596): the connector, which shares
#: the triangle's name, gets its own.
_C2_UIDS = {
    labels.C2_MAJORITY_KEY: "c2line",
    labels.LABELS["pv_share"]: "c2pv",
    labels.LABELS["ec_share_full"]: "c2ec",
    labels.C2_HYBRID_KEY: "c2hybrid",
    labels.C2_PV_DIFFERENT_KEY: "c2pvstrip",
    labels.C2_HYBRID_DIFFERENT_KEY: "c2hybridstrip",
    labels.C2_NO_FIGURE: "c2nofigure",
    labels.UNRECOGNIZED: "c2unrecognized",
}
#: The key's order, by series name (#596, D110): the drawing order puts the crossbar
#: last, so each keyed trace's ``legendrank`` is its place here, plus one.
_C2_KEY_ORDER = (
    labels.LABELS["pv_share"],
    labels.C2_HYBRID_KEY,
    labels.LABELS["ec_share_full"],
    labels.C2_PV_DIFFERENT_KEY,
    labels.C2_HYBRID_DIFFERENT_KEY,
    *_C2_SYMBOLS,
    labels.C2_MAJORITY_KEY,
)


dash.register_page(
    __name__,
    path=PATH,
    title=f"Electoral College majority — {SITE_TITLE}",
    description=(
        "Whether the Electoral College leader in each US presidential election won a "
        "majority of the electors appointed and, where this dataset has them, their "
        "popular-vote share and the project's proposed hybrid score."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    # N1, filled on first use (D096(c)): a literal (D074(ii)), never prefetched.
    on_miss=(api.SUMMARY_PATH,),
    success=PAGE_ID,
    # The year filters (#596, D110): og:url names the filtered view.
    query=elections_view.parse_filters,
    # The site navigation link this page marks (#448): the elections index's.
    nav="elections",
)


#: The year-level fields C2 merges into each leader's row from N1's ``elections`` item
#: (#434; #564, D108). The flags are read, never a list of years.
YEAR_FIELDS = (
    "ec_determinative",
    "pv_winner",
    "hybrid_winner",
    "pv_flip",
    "hybrid_flip",
)
#: Each flip with the winner slug it names, for :func:`leaders`' check.
FLIP_WINNERS = (("pv_flip", "pv_winner_slug"), ("hybrid_flip", "hybrid_winner_slug"))


def _agrees(flip: Any, winner_slug: Any, leader_slug: Any) -> bool:
    """Whether a served flip agrees with the winner it names, on the producer's own
    rule (``usvote.hybrid``): null exactly when that method has no winner, else true
    exactly when its winner is not the Electoral College's (#564's review, cr.2)."""
    if flip is None:
        return winner_slug is None
    if flip is True:
        return labels.has_text(winner_slug) and winner_slug != leader_slug
    if flip is False:
        return bool(winner_slug == leader_slug)
    return False


def leaders(
    index: dict[str, Any], summary: Any, has_pv: dict[int, bool]
) -> list[dict[str, Any]]:
    """Each served year's Electoral College leader, oldest first: N1's one ``data`` row
    with ``electoral_rank`` 1, with the year's :data:`YEAR_FIELDS` from its one
    ``elections`` item (#434, D096; #564, D108), and the year's ``has_popular_vote``
    from ``has_pv`` (the index's, checked by :func:`index_rule`). Derives nothing.

    Pure; raises what :func:`explore.elections_view.n1_items` raises, and ``TypeError``
    for anything else C2 cannot show: a ``data`` row whose year
    :func:`explore.election_view.row_year` refuses or the index does not serve, a
    served year with no rank-1 row or two (a tie at rank 1 is valid API data,
    D094(iv), but C2 needs one leader per year), a leader whose ``candidate_slug`` is
    not the item's ``ec_winner_slug`` (the flags' baseline), or a flip that disagrees
    with the winner it names (:func:`_agrees`: a flip that is no flag, a ``True`` flip
    with no winner or the leader as winner, a ``False`` one with another winner, a
    null one with a winner; #564's review, cr.2). ``electoral_rank`` counts only as an
    ``int``, never a ``bool``.
    """
    by_year = elections_view.n1_items(index, summary)
    served = set(by_year)
    rows = summary["data"]
    if not isinstance(rows, list):
        raise TypeError(f"{api.SUMMARY_PATH} carries no list of rows")
    leader: dict[int, dict[str, Any]] = {}
    for row in rows:
        year = election_view.row_year(row)
        if year is None or year not in served:
            raise TypeError(f"{api.SUMMARY_PATH}: a row for a year not served")
        rank = row.get("electoral_rank")
        if type(rank) is int and rank == 1:
            if year in leader:
                raise TypeError(f"{api.SUMMARY_PATH}: two leaders in {year}")
            leader[year] = row
    if set(leader) != served:
        raise TypeError(f"{api.SUMMARY_PATH} misses a served year")
    result = []
    for year in sorted(served):
        item = by_year[year]
        slug = leader[year]["candidate_slug"]
        if slug != item["ec_winner_slug"]:
            raise TypeError(f"{api.SUMMARY_PATH}: a leader is not ec_winner")
        for flip, winner in FLIP_WINNERS:
            if not _agrees(item[flip], item[winner], slug):
                raise TypeError(f"{api.SUMMARY_PATH}: a flip disagrees with its winner")
        result.append(
            {
                **leader[year],
                **{field: item[field] for field in YEAR_FIELDS},
                "has_popular_vote": has_pv[year],
            }
        )
    return result


#: The index's popular-vote window and flags, checked as the page's: shared with the
#: over-time page since #596, so both filter on one rule.
index_rule = elections_view.index_rule


def _leader_cells(row: dict[str, Any], coverage: dict[str, Any]) -> dict[str, str]:
    """The leader table's worded cells, computed once per row per render and read by
    both the table and C2, so the chart writes every number as the table does. The
    leader's popular-vote share and hybrid score follow T3's year rule (#564,
    :func:`explore.labels.national_pv`), the winners the panel's (``coverage``)."""
    has_pv = row["has_popular_vote"]
    applicable = labels.in_pv_window(row["year"], coverage)
    return {
        "national_electoral_votes_counted": labels.number(
            row["national_electoral_votes_counted"]
        ),
        "national_electoral_denominator": labels.number(
            row["national_electoral_denominator"]
        ),
        "ec_share_full": labels.share_cell(row["ec_share_full"]),
        "ec_determinative": labels.ec_majority(row["ec_determinative"]),
        "took_office": labels.yes_no(row["took_office"]),
        "pv_share": labels.national_pv(row["pv_share"], has_pv, True),
        "hybrid_score": labels.national_pv(row["hybrid_score"], has_pv, True),
        "pv_winner": labels.winner(row["pv_winner"], applicable),
        "hybrid_winner": labels.winner(row["hybrid_winner"], applicable),
    }


def _leader_row(row: dict[str, Any], cells: dict[str, str]) -> html.Tr:
    year = row["year"]
    return html.Tr(
        [
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            components.candidate_cell(row),
            *(labels.cell(cells[field]) for field in LEADER_WORDED),
        ]
    )


def _majority(cell: str) -> str:
    """The hover's last line, every year: the majority cell itself when it says
    whether anyone won one, else named by its field, as the table's header names it."""
    if cell in (labels.EC_MAJORITY, labels.NO_EC_MAJORITY):
        return cell
    return f"{labels.LABELS['ec_determinative']}: {cell}"


def _drawn(value: Any, cell: str) -> float | None:
    """A share or score a mark can stand at: finite, and its cell a share (one whose
    percentage overflows reads ``UNRECOGNIZED``); else ``None``, and a marker."""
    number = labels.finite(value)
    if number is None or cell == labels.UNRECOGNIZED:
        return None
    return number


class C2(NamedTuple):
    """C2's figure and what its caption needs to say (#564)."""

    figure: dict[str, Any]
    #: Whether any year shown has popular-vote figures (#596): if none does, only the
    #: electoral share is drawn and the title, axis and caption say so.
    pv_shown: bool
    marked: bool
    before: bool
    after: bool
    pv_different: bool
    hybrid_different: bool


def _c2_figure(
    rows: list[dict[str, Any]],
    cells: list[dict[str, str]],
    window: tuple[int, int],
) -> C2:
    """C2's figure (#434, D096, as amended by D104 for #558 and D108 for #564): election
    year along the bottom (:func:`explore.components.year_axis`), and for each served
    year the leader's served ``ec_share_full`` (a circle), ``pv_share`` (a solid
    triangle) joined to it by a thin line, and ``hybrid_score`` (a crossbar on that
    line, #593), each drawn wherever its table cell is a share, against a dashed line
    at half of each election's electors appointed; a strip of marks above 100% where
    the served ``pv_flip`` or ``hybrid_flip`` is true; and bands over the years
    outside the popular-vote ``window`` (from ``coverage``).

    No mark carries text: its hover writes the table's cells. A share or score the
    table does not show as one is a marker at zero, never a dropped year, in a series
    of its own per label (:data:`explore.labels.C2_NO_FIGURE` for no figure in this
    dataset, else :data:`explore.labels.UNRECOGNIZED`), each with its own symbol and
    named in the chart's key; a popular-vote cell that reads
    :data:`explore.labels.NOT_APPLICABLE` draws nothing, and the band says why. The
    majority line is a trace under every mark, named in the key (#596, D110: a label
    in the plot sat among the marks once a filter narrowed the years). Drawn in the
    order line, connector, triangles, circles, strip marks, markers, crossbars, so the
    crossbar is on top (#596, D110); each keyed trace's ``legendrank``
    (:data:`_C2_KEY_ORDER`) keeps the key's order: triangle, crossbar, circle, strip
    marks, markers, line. ``rows`` are the years shown; with none inside the
    popular-vote window, the title and value axis name the electoral share alone.
    """
    years = [row["year"] for row in rows]
    ec: list[tuple[int, float, str]] = []
    pv: list[tuple[int, float, str]] = []
    hybrid: list[tuple[int, float, str]] = []
    pv_strip: list[tuple[int, float, str]] = []
    hybrid_strip: list[tuple[int, float, str]] = []
    connector_x: list[int | None] = []
    connector_y: list[float | None] = []
    # label -> year -> hovers: one marker per label and year, its hovers joined, so a
    # year missing two marks for one cause is one point with one reachable hover
    # (#564's review, cr.5).
    marks: dict[str, dict[int, list[str]]] = {}

    def missing(year: int, cell: str, hover: str) -> None:
        label = (
            labels.C2_NO_FIGURE
            if cell in (labels.NOT_IN_DATASET, labels.NO_NATIONAL_FIGURE)
            else labels.UNRECOGNIZED
        )
        marks.setdefault(label, {}).setdefault(year, []).append(hover)

    for row, cell in zip(rows, cells, strict=True):
        year = row["year"]
        candidate = charts.escaped(str(row["candidate"]))
        shown = cell["ec_share_full"]
        hover = labels.C2_HOVER.format(
            year=str(year),
            candidate=candidate,
            share=over_time.noted(shown),
            counted=cell["national_electoral_votes_counted"],
            appointed=cell["national_electoral_denominator"],
            majority=_majority(cell["ec_determinative"]),
        )
        ec_y = _drawn(row["ec_share_full"], shown)
        if ec_y is None:
            missing(year, shown, hover)
        else:
            ec.append((year, ec_y, hover))
        pv_cell = cell["pv_share"]
        pv_y = None
        if pv_cell != labels.NOT_APPLICABLE:
            pv_hover = labels.C2_PV_HOVER.format(
                year=str(year), candidate=candidate, share=over_time.noted(pv_cell)
            )
            pv_y = _drawn(row["pv_share"], pv_cell)
            if pv_y is None:
                missing(year, pv_cell, pv_hover)
            else:
                pv.append((year, pv_y, pv_hover))
        if ec_y is not None and pv_y is not None:
            connector_x += [year, year, None]
            connector_y += [ec_y, pv_y, None]
        score_cell = cell["hybrid_score"]
        if score_cell != labels.NOT_APPLICABLE:
            score_hover = labels.C2_HYBRID_HOVER.format(
                year=str(year), candidate=candidate, score=over_time.noted(score_cell)
            )
            score_y = _drawn(row["hybrid_score"], score_cell)
            if score_y is None:
                missing(year, score_cell, score_hover)
            else:
                hybrid.append((year, score_y, score_hover))
        if row["pv_flip"] is True:
            pv_strip.append(
                (
                    year,
                    _C2_STRIP_Y,
                    labels.C2_PV_DIFFERENT_HOVER.format(
                        year=str(year),
                        winner=over_time.noted(charts.escaped(cell["pv_winner"])),
                    ),
                )
            )
        if row["hybrid_flip"] is True:
            hybrid_strip.append(
                (
                    year,
                    _C2_STRIP_Y,
                    labels.C2_HYBRID_DIFFERENT_HOVER.format(
                        year=str(year),
                        winner=over_time.noted(charts.escaped(cell["hybrid_winner"])),
                    ),
                )
            )

    data: list[dict[str, Any]] = []
    if connector_x:
        data.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": labels.LABELS["pv_share"],
                "showlegend": False,
                "x": connector_x,
                "y": connector_y,
                "cliponaxis": False,
                "line": {"width": 1, "color": "var(--chart-axis)"},
                "hoverinfo": "skip",
            }
        )
    # name, symbol, color, size, stroke (a line-only symbol's outline), drawn
    series: tuple[
        tuple[str, str, str, int, float | None, list[tuple[int, float, str]]], ...
    ] = (
        (
            labels.LABELS["pv_share"],
            _C2_PV_SYMBOL,
            charts.PV_COLOR,
            _C2_PV_PX,
            None,
            pv,
        ),
        (
            labels.LABELS["ec_share_full"],
            _C2_EC_SYMBOL,
            charts.EC_COLOR,
            _C2_EC_PX,
            None,
            ec,
        ),
        (
            labels.C2_PV_DIFFERENT_KEY,
            _C2_PV_DIFFERENT_SYMBOL,
            "var(--text)",
            11,
            _C2_LINE_PX,
            pv_strip,
        ),
        (
            labels.C2_HYBRID_DIFFERENT_KEY,
            _C2_HYBRID_DIFFERENT_SYMBOL,
            "var(--text)",
            9,
            None,
            hybrid_strip,
        ),
    )
    for name, symbol, color, size, stroke, drawn in series:
        if drawn:
            data.append(
                over_time.marker_trace(
                    name,
                    symbol,
                    [year for year, _, _ in drawn],
                    [hover for _, _, hover in drawn],
                    y=[y for _, y, _ in drawn],
                    size=size,
                    color=color,
                    line_width=stroke,
                )
            )
    for label, symbol in _C2_SYMBOLS.items():
        if label in marks:
            by_year = marks[label]
            data.append(
                over_time.marker_trace(
                    label,
                    symbol,
                    sorted(by_year),
                    ["<br>".join(by_year[year]) for year in sorted(by_year)],
                )
            )
    # The crossbar last, so neither the circle nor the triangle can hide it (#596).
    if hybrid:
        data.append(
            over_time.marker_trace(
                labels.C2_HYBRID_KEY,
                _C2_HYBRID_SYMBOL,
                [year for year, _, _ in hybrid],
                [hover for _, _, hover in hybrid],
                y=[y for _, y, _ in hybrid],
                size=_C2_HYBRID_PX,
                color=charts.HYBRID_COLOR,
                line_width=_C2_LINE_PX,
            )
        )
    axis = components.year_axis(years)
    # The majority line, under every mark and named in the key (#596, D110): drawn
    # across the axis's range, with no hover of its own.
    data.insert(
        0,
        {
            "type": "scatter",
            "mode": "lines",
            "name": labels.C2_MAJORITY_KEY,
            "showlegend": True,
            "x": list(axis["range"]),
            "y": [_C2_MAJORITY, _C2_MAJORITY],
            "cliponaxis": False,
            "line": {"dash": "dash", "width": 2, "color": "var(--chart-reference)"},
            "hoverinfo": "skip",
        },
    )
    for trace in data:
        if trace.get("showlegend"):
            trace["legendrank"] = _C2_KEY_ORDER.index(trace["name"]) + 1
    # A stable identity per trace (#596's architect review), which plotly.js writes
    # into each trace's class (``trace<uid>``), so a test finds a series by what it
    # is, never by its place in the drawing order, which a filter changes.
    connector = data[1] if connector_x else None
    for trace in data:
        uid = _C2_UIDS.get(trace["name"])
        if trace is connector:
            uid = "c2connector"
        if uid is not None:
            trace["uid"] = uid
    pv_min, pv_max = window
    bands = over_time.pv_bands(
        years,
        window,
        labels.C5_BEFORE_BAND.format(pv_year_min=pv_min),
        labels.C5_AFTER_BAND.format(pv_year_max=pv_max),
        # One key row per line of each entry the key shows, the most rows it can wrap
        # to, counted from the traces built above (#593's review; the majority line's
        # entry is two lines, #596).
        key_px=over_time.KEY_ROW_PX
        * sum(1 + t["name"].count("<br>") for t in data if t.get("showlegend")),
    )
    # The value axis draws no gridlines of its own (#593, D109): its 50% gridline
    # showed through the majority line's dashes, so it read as a doubled line. The
    # others are drawn as shapes from the ticks, under the line, over the bands.
    gridlines = [
        {
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": tick,
            "y1": tick,
            "layer": "below",
            "line": {"width": 1, "color": "var(--chart-grid)"},
        }
        for tick in _C2_TICKS
        if tick not in (0, _C2_MAJORITY)
    ]
    pv_shown = any(row["has_popular_vote"] is True for row in rows)
    layout: dict[str, Any] = {
        "title": {"text": labels.C2_TITLE if pv_shown else labels.C2_TITLE_NO_PV},
        "height": _C2_HEIGHT_PX,
        "showlegend": True,
        "legend": components.TIME_SERIES_LEGEND,
        "xaxis": axis,
        "yaxis": {
            "range": [0, _C2_Y_TOP],
            "tickformat": ".0%",
            "tickvals": list(_C2_TICKS),
            "showgrid": False,
            "title": {
                "text": labels.C2_VALUE_AXIS if pv_shown else labels.C2_VALUE_AXIS_NO_PV
            },
        },
        "shapes": [*bands.shapes, *gridlines],
        "annotations": bands.annotations,
    }
    if bands.top_px:
        layout["margin"] = {"t": bands.top_px}
    return C2(
        {"data": data, "layout": layout},
        pv_shown,
        bool(marks),
        bands.before,
        bands.after,
        bool(pv_strip),
        bool(hybrid_strip),
    )


def _c2_caption(c2: C2, window: tuple[int, int]) -> str:
    """C2's caption: which candidate each year's marks are, what each mark is, what
    the line marks, that a plurality under half is ordinary, that the leader did not
    always take office, and, only where each is drawn, the bands, the strip marks and
    the markers. It names no served text (D095(a)); ``components.chart`` adds the
    table pointer. With no year shown inside the popular-vote window it drops the
    popular-vote and hybrid sentences, as C1's caption does (#596, D110)."""
    pv_min, pv_max = window
    if c2.pv_shown:
        parts = [
            labels.C2_LEADER_POINT,
            labels.C2_EC_MARK,
            labels.C1_EC_BASIS,
            labels.C2_PV_MARK,
            labels.C2_HYBRID_MARK,
            labels.C2_MAJORITY_NOTE,
            labels.C1_LINE_EC_ONLY,
            labels.C2_PLURALITY_NOTE,
            labels.C2_TOOK_OFFICE,
        ]
    else:
        parts = [
            labels.C2_LEADER_POINT,
            labels.C2_EC_MARK,
            labels.C1_EC_BASIS,
            labels.C2_MAJORITY_NOTE,
            labels.C2_TOOK_OFFICE,
        ]
    if c2.before:
        parts.append(labels.C2_BEFORE_NOTE.format(pv_year_min=pv_min))
    if c2.after:
        parts.append(labels.C5_AFTER_NOTE.format(pv_year_max=pv_max))
    if c2.pv_different:
        parts.append(labels.C2_PV_DIFFERENT_NOTE)
    if c2.hybrid_different:
        parts.append(labels.C2_HYBRID_DIFFERENT_NOTE)
    if c2.marked:
        parts.append(labels.C2_NO_SHARE_NOTE)
    return " ".join(parts)


def _leader_section(
    index: dict[str, Any],
    summary: Any,
    window: tuple[int, int],
    has_pv: dict[int, bool],
    chosen: elections_view.Filters,
    search: str,
    served_span: tuple[int, int],
) -> tuple[list[Any], bool]:
    """C2's section (#434, D096) and whether its filters rendered: the year filters,
    then the chart and its companion table over the years they show (#596, D110), or
    :func:`explore.elections_view.no_match` when they show none; or, when N1 could not
    be read (``summary`` is ``None``) or is malformed, :data:`C2_UNAVAILABLE` only, with
    no filters (they would narrow nothing). Every served year's leader is read and its
    cells and table row built before the filters apply (#596's review, cr.1), so a
    filtered view never shows what the default view would refuse.
    The page's heading is the section's (#562). The index's popular-vote window and
    flags (``window``, ``has_pv``) are checked by :func:`render` as the page's. The
    ``try`` covers everything built from N1 (the validation, the figure, the cells, and
    the companion table and its download), so no ``KeyError`` or ``TypeError`` from it
    reaches the page; never ``components.chart``, which no page catches around
    (D095(f))."""
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        coverage = index["meta"]["provenance"]["coverage"]
        every = leaders(index, summary, has_pv)
        every_cells = [_leader_cells(row, coverage) for row in every]
        for row, cell in zip(every, every_cells, strict=True):
            _leader_row(row, cell)
        kept = [
            (row, cell)
            for row, cell in zip(every, every_cells, strict=True)
            if elections_view.shows(row["year"], row["has_popular_vote"], chosen)
        ]
        controls = elections_view.filter_controls(*served_span, chosen)
        if not kept:
            return [controls, elections_view.no_match()], True
        rows = [row for row, _ in kept]
        cells = [cell for _, cell in kept]
        c2 = _c2_figure(rows, cells, window)
        download = export.Download(
            filename="elections-electoral-college-leaders.csv",
            name="the Electoral College leaders",
            provenance=summary["meta"]["provenance"],
            # The view the filters left (#596).
            view_url=export.view_url(CANONICAL_HOST, PATH, search),
        )
        by_row = {id(row): cell for row, cell in zip(rows, cells, strict=True)}
        # Inside the try: the table and its CSV read N1 too (each row's slug, the
        # provenance the preamble names), and a defect there is N1's, not the page's.
        table = components.table(
            rows,
            lambda r: _leader_row(r, by_row[id(r)]),
            LEADER_FIELDS,
            LEADER_TABLE_ID,
            download,
            extra=LEADER_EXTRA,
            notes=(
                labels.C2_LEADER_ROW,
                labels.C2_TOOK_OFFICE,
                labels.C2_TABLE_METHODS_NOTE,
                labels.HYBRID_NOTE,
                labels.C2_HYBRID_TABLE_NOTE,
            ),
        )
    except (KeyError, TypeError):
        return [
            html.P(C2_UNAVAILABLE, id=LEADER_UNAVAILABLE_ID, className="note"),
        ], False
    return [
        controls,
        components.chart(C2_ID, c2.figure, LEADER_TABLE_ID, _c2_caption(c2, window)),
        html.H2(C2_TABLE_HEADING),
        *table,
        labels.glossary(LEADER_FIELDS),
    ], True


def render(
    index: dict[str, Any], summary: Any, pairs: list[tuple[str, str]] | None = None
) -> html.Div:
    """The whole page for one ``/v1/elections`` response, N1's body (``None`` when it
    could not be read) and the page's filter pairs
    (:func:`explore.elections_view.parse_filters`; none, every year): the heading and
    lede (with :data:`FILTER_SENTENCE` when the filters render), the section links
    carrying the filters applied, then C2's section, then the footer."""
    provenance = index["meta"]["provenance"]
    coverage = provenance["coverage"]
    # The index's rows are the page's, not a section's (cr.1): a defect there raises to
    # the layout, which degrades the whole page.
    elections_view.served_years(index)
    window, has_pv = index_rule(index)
    chosen = elections_view.filters(pairs or [], coverage)
    first, last = elections_view.span(coverage)
    search = elections_view.applied_search(chosen, first, last)
    section, filtered = _leader_section(
        index, summary, window, has_pv, chosen, search, (first, last)
    )
    return html.Div(
        [
            html.H1(HEADING),
            html.P(f"{LEDE} {FILTER_SENTENCE}" if filtered else LEDE, className="lede"),
            dcc.Location(id=elections_view.URL_ID, refresh="callback-nav"),
            elections_view.section_nav(elections_view.MAJORITY, search),
            # C2's section in one card (#567, D111), on every branch: the chart and its
            # table, the empty note, or the section's unavailable note.
            components.card(section),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(**query: Any) -> html.Div:
    """The Electoral College majority page. The index and then N1 are read in one view;
    a failed N1 degrades only C2's section, a failed index the whole page."""
    try:
        with api.CLIENT.view() as view:
            body = view.get(api.ELECTIONS_PATH)
            try:
                summary = view.get(api.SUMMARY_PATH)
            except api.ApiUnavailable:
                summary = None
        return render(body, summary, elections_view.parse_filters(query))
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div([html.H1(HEADING), html.P(LEDE, className="lede"), content])
