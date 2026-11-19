"""Charts C4 and C5 and their companion table, on their own page (#436, D100; split
by #562, D107): ``/elections/over-time``, electors appointed and the total popular vote
in each election, for all states together. They read N1 (``api.SUMMARY_PATH``, filled
on first use) in the same view as the index: each ``elections`` item's
``electoral_denominator`` (checked by :func:`explore.elections_view.n1_items`) and each
year's one ``national_pv_denominator`` across N1's rows (:func:`national_pv`).

No filter reaches the page: it has no ``query=`` parser. The one-state mode (D100(a),
(c), (e), (f)) retired with #562: a state's electors appointed are chart C7, on its
own page. A failed or malformed N1 degrades the section only; the heading, lede and
success marker stay.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import dash
from dash import dcc, html

from explore import (
    api,
    components,
    election_view,
    elections_view,
    export,
    labels,
    over_time,
    query,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whether or not N1 could be read.
PAGE_ID = "elections-over-time"
#: This page's own path, the view URL its download names.
PATH = "/elections/over-time"

#: Page-level wording (ba spec, approved by the owner at #562's plan gate, 2026-11-19).
#: The heading was the section heading on ``/elections`` (#436's plan gate).
HEADING = "Electors appointed and the total popular vote over time"
LEDE = (
    "For every election in this dataset: the electors appointed across all states, "
    "and the total popular vote across the country. A state's own electors appointed "
    "are on that state's page."
)

#: Charts C4 and C5 (#436, D100) and the companion table they share.
C4_ID = "C4"
C5_ID = "C5"
OVER_TIME_TABLE_ID = "elections-over-time-table"
OVER_TIME_UNAVAILABLE_ID = "elections-over-time-unavailable"
#: C4 and C5's pair (#553, D102): C4 left, C5 right, their table full width below.
OVER_TIME_PAIR_ID = "elections-over-time-pair"
#: The companion table's columns, in display order, by public field name.
OVER_TIME_FIELDS = ("year", "electoral_denominator", "national_pv_denominator")
OVER_TIME_TABLE_HEADING = "Each election's electors appointed and total popular vote"
#: The section when N1 cannot be read or is malformed. Never ``UNAVAILABLE_MESSAGE``'s
#: wording: the D070(b) guard's success run asserts that absent from every page.
OVER_TIME_UNAVAILABLE = (
    "The charts and table of electors appointed and the total popular vote can't be "
    "shown right now. Please try again in a minute."
)

#: Room for each of C5's band labels above the plot: two lines of 12 px text at
#: plotly's 1.3 line height (2 × 16 px) and 8 px between labels (#558, D104).
_BAND_LABEL_PX = 40
#: Each C5 marker label's symbol, so no two marker series differ by color alone.
_C5_SYMBOLS = {
    labels.C5_LEGISLATURE: "diamond",
    labels.C5_TOOK_NO_PART: "x",
    labels.C5_NO_TOTAL: "circle-open",
    labels.UNRECOGNIZED: "square-open",
}


dash.register_page(
    __name__,
    path=PATH,
    title=f"Electors appointed and total popular vote — {SITE_TITLE}",
    description=(
        "Electors appointed and the total popular vote in each US presidential "
        "election, all states together."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    # N1, filled on first use (D096(c)): a literal (D074(ii)), never prefetched.
    on_miss=(api.SUMMARY_PATH,),
    success=PAGE_ID,
    # The site navigation link this page marks (#448): the elections index's.
    nav="elections",
)


def national_pv(summary: Any, served: Iterable[int]) -> dict[int, Any]:
    """Each served year's one ``national_pv_denominator`` across N1's ``data`` rows
    (#436): C5's all-states value. A year's value may be null.

    Pure and strict; raises ``KeyError`` for a row without the field and ``TypeError``
    for a body with no list of rows, a row whose year
    :func:`explore.election_view.row_year` refuses or that is not served, a served
    year with no row, or two values in one year (a null beside a figure counts as
    two). It reads nothing but the year and that field.
    """
    years = set(served)
    if not isinstance(summary, dict):
        raise TypeError(f"{api.SUMMARY_PATH} is not an object")
    rows = summary["data"]
    if not isinstance(rows, list):
        raise TypeError(f"{api.SUMMARY_PATH} carries no list of rows")
    totals: dict[int, Any] = {}
    for row in rows:
        year = election_view.row_year(row)
        if year is None or year not in years:
            raise TypeError(f"{api.SUMMARY_PATH}: a row for a year not served")
        value = row["national_pv_denominator"]
        if year in totals and not over_time.same(totals[year], value):
            raise TypeError(f"{api.SUMMARY_PATH}: two national totals in {year}")
        totals[year] = value
    if set(totals) != years:
        raise TypeError(f"{api.SUMMARY_PATH} misses a served year")
    return totals


def _all_states_points(
    items: dict[int, dict[str, Any]],
    totals: dict[int, Any],
    coverage: dict[str, Any],
) -> list[over_time.Point]:
    """All states: each served year's N1 allotment and national total, worded once."""
    points = []
    for year in sorted(items):
        appointed = items[year]["electoral_denominator"]
        points.append(
            over_time.Point(
                year=year,
                appointed=appointed,
                appointed_cell=labels.number(appointed),
                total=totals[year],
                total_cell=labels.national_total(totals[year], year, coverage),
                status=None,
                status_cell=None,
            )
        )
    return points


def _band(
    years: list[int], first: int, last: int, label: str, *, after: bool, raised: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A shaded band over the served years ``first`` to ``last`` of ``years``
    (:func:`explore.components.year_edges`), the whole height of the plot, and its
    label above the plot (#558, D104), never inside the band, which can be one
    election wide: the band before the window's at its left edge, after it (``after``)
    at its right, ``raised`` pixels higher where another label sits below it."""
    low, high = components.year_edges(years, first, last)
    shape = {
        "type": "rect",
        "xref": "x",
        "x0": low,
        "x1": high,
        "yref": "paper",
        "y0": 0,
        "y1": 1,
        "layer": "below",
        "fillcolor": "var(--chart-grid)",
        "line": {"width": 1, "color": "var(--chart-reference)"},
    }
    note = {
        "text": label,
        "showarrow": False,
        "font": {"color": "var(--text)", "size": 12},
        "xref": "x",
        "x": high if after else low,
        "xanchor": "right" if after else "left",
        "align": "right" if after else "left",
        "yref": "paper",
        "y": 1,
        "yanchor": "bottom",
        "yshift": raised,
    }
    return shape, note


def _c5_figure(
    points: list[over_time.Point],
    years: list[int],
    title: str,
    window: tuple[int, int],
) -> over_time.OverTime:
    """C5's figure (#436, D100): the total popular vote of each row with one, as a bar
    at its year. The years before and after the popular-vote window (``window``, read
    from ``coverage``) are a shaded band, labeled above the plot, which alone marks a
    held popular vote outside it; every other row with nothing to draw is a marker, one
    series per label (:data:`explore.labels.C5_MARKER_LABELS`), named in the chart's
    key (#558, D104), wherever it falls, inside the band included. All states only
    since #562 (D107)."""
    pv_min, pv_max = window
    banded = {
        labels.NOT_APPLICABLE,
        labels.AFTER_WINDOW,
        labels.BEFORE_WINDOW.format(pv_year_min=pv_min),
    }
    drawn: list[tuple[over_time.Point, int, str, str]] = []
    marks: dict[str, list[tuple[over_time.Point, str]]] = {}
    for point in points:
        hover = over_time.point_hover(point, None, total=True)
        value = over_time.figure_value(point.total, zero=True)
        if value is not None and point.total_cell == labels.number(value):
            drawn.append((point, value, point.total_cell, hover))
            continue
        outside = not pv_min <= point.year <= pv_max
        if outside and point.total_cell in banded:
            continue
        label = labels.C5_MARKER_LABELS.get(point.total_cell, labels.UNRECOGNIZED)
        marks.setdefault(label, []).append((point, hover))
    name = labels.LABELS["national_pv_denominator"]
    data: list[dict[str, Any]] = []
    if drawn:
        data.append(over_time.bar_trace(name, drawn))
    data += over_time.series(marks, _C5_SYMBOLS)
    longest = max((value for _, value, _, _ in drawn), default=1)
    layout = over_time.time_layout(
        title, labels.C5_VALUE_AXIS, years, longest, marked=bool(marks)
    )
    shapes: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    before = [year for year in years if year < pv_min]
    after = [year for year in years if year > pv_max]
    # Both labels sit above the plot; with both drawn, the before label goes on top.
    raised = _BAND_LABEL_PX if before and after else 0
    if before:
        shape, note = _band(
            years,
            before[0],
            before[-1],
            labels.C5_BEFORE_BAND.format(pv_year_min=pv_min),
            after=False,
            raised=raised,
        )
        shapes.append(shape)
        annotations.append(note)
    if after:
        shape, note = _band(
            years,
            after[0],
            after[-1],
            labels.C5_AFTER_BAND.format(pv_year_max=pv_max),
            after=True,
            raised=0,
        )
        shapes.append(shape)
        annotations.append(note)
    if shapes:
        layout["shapes"] = shapes
        layout["annotations"] = annotations
        layout["margin"] = {"t": over_time.TOP_PX + _BAND_LABEL_PX * len(annotations)}
    return over_time.OverTime(
        {"data": data, "layout": layout}, False, bool(marks), bool(before), bool(after)
    )


def _c4_caption(c4: over_time.OverTime) -> str:
    """C4's caption: what electors appointed is, what a bar adds up, and what each
    marker means where one is drawn; ``components.chart`` adds the table pointer."""
    parts = [labels.C4_BASIS, labels.C4_ALL_STATES]
    if c4.zeros:
        parts.append(labels.C4_ZERO_NOTE)
    if c4.missing:
        parts.append(labels.C4_NO_FIGURE_NOTE)
    return " ".join(parts)


def _c5_caption(c5: over_time.OverTime, window: tuple[int, int]) -> str:
    """C5's caption: what the total counts, what a bar adds up, and what the band and
    the markers mean where drawn."""
    parts = [labels.C5_BASIS, labels.C5_ALL_STATES]
    if c5.before:
        parts.append(labels.C5_BEFORE_NOTE.format(pv_year_min=window[0]))
    if c5.after:
        parts.append(labels.C5_AFTER_NOTE.format(pv_year_max=window[1]))
    if c5.missing:
        parts.append(labels.C5_MARKER_NOTE)
    return " ".join(parts)


def _over_time_row(point: over_time.Point) -> html.Tr:
    """A row of the companion table: the year, linked to its election, and the cells
    C4 and C5 write."""
    return html.Tr(
        [
            html.Td(dcc.Link(str(point.year), href=f"/election/{point.year}")),
            labels.cell(point.appointed_cell),
            labels.cell(point.total_cell),
        ]
    )


def _over_time_section(index: dict[str, Any], summary: Any) -> list[Any]:
    """C4 and C5's section (#436, D100): both charts and their one companion table,
    or, when N1 could not be read (``summary`` is ``None``) or is malformed,
    :data:`OVER_TIME_UNAVAILABLE` only. The ``try`` covers everything built from N1;
    never ``components.chart``, which no page catches around (D095(f))."""
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        coverage = index["meta"]["provenance"]["coverage"]
        window = query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
        items = elections_view.n1_items(index, summary)
        years = sorted(items)
        totals = national_pv(summary, years)
        rows: list[dict[str, Any]] = [
            {
                "year": year,
                "electoral_denominator": items[year]["electoral_denominator"],
                "national_pv_denominator": totals[year],
            }
            for year in years
        ]
        if not rows:
            raise TypeError("the over-time table has no rows")
        points = _all_states_points(items, totals, coverage)
        download = export.Download(
            filename="elections-electors-and-popular-vote-all-states.csv",
            name="electors appointed and the total popular vote, all states",
            provenance=summary["meta"]["provenance"],
            view_url=export.view_url(CANONICAL_HOST, PATH, ""),
        )
        c4 = over_time.c4_figure(points, years, labels.C4_TITLE, None)
        c5 = _c5_figure(points, years, labels.C5_TITLE, window)
        # The pair's plots line up (#553's pair, #558): C4 leaves room for C5's band
        # labels.
        c4.figure["layout"]["margin"] = dict(c5.figure["layout"]["margin"])
        by_row = {id(row): point for row, point in zip(rows, points, strict=True)}
        notes = (
            labels.C4_BASIS,
            labels.C5_BASIS,
            labels.OVER_TIME_WINDOW_NOTE.format(
                pv_year_min=window[0], pv_year_max=window[1]
            ),
        )
        table = components.table(
            rows,
            lambda r: _over_time_row(by_row[id(r)]),
            OVER_TIME_FIELDS,
            OVER_TIME_TABLE_ID,
            download,
            notes=notes,
        )
    except (KeyError, TypeError):
        return [
            html.P(
                OVER_TIME_UNAVAILABLE, id=OVER_TIME_UNAVAILABLE_ID, className="note"
            )
        ]
    return [
        components.pair(
            [components.chart(C4_ID, c4.figure, OVER_TIME_TABLE_ID, _c4_caption(c4))],
            [
                components.chart(
                    C5_ID, c5.figure, OVER_TIME_TABLE_ID, _c5_caption(c5, window)
                )
            ],
            OVER_TIME_PAIR_ID,
        ),
        html.H2(OVER_TIME_TABLE_HEADING),
        *table,
        labels.glossary(OVER_TIME_FIELDS),
    ]


def render(index: dict[str, Any], summary: Any) -> html.Div:
    """The whole page for one ``/v1/elections`` response and N1's body (``None`` when
    it could not be read): the heading and lede, then C4 and C5's section, then the
    footer."""
    provenance = index["meta"]["provenance"]
    return html.Div(
        [
            html.H1(HEADING),
            html.P(LEDE, className="lede"),
            *_over_time_section(index, summary),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(**query: Any) -> html.Div:
    """The electors appointed and total popular vote page. The index and then N1 are
    read in one view; a failed N1 degrades only the section, a failed index the whole
    page."""
    try:
        with api.CLIENT.view() as view:
            body = view.get(api.ELECTIONS_PATH)
            try:
                summary = view.get(api.SUMMARY_PATH)
            except api.ApiUnavailable:
                summary = None
        return render(body, summary)
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div([html.H1(HEADING), html.P(LEDE, className="lede"), content])
