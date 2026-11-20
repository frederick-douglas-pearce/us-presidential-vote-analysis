"""Charts C4 and C5 and their companion table, on their own page (#436, D100; split
by #562, D107): ``/elections/over-time``, electors appointed and the total popular vote
in each election, for all states together. They read N1 (``api.SUMMARY_PATH``, filled
on first use) in the same view as the index: each ``elections`` item's
``electoral_denominator`` (checked by :func:`explore.elections_view.n1_items`) and each
year's one ``national_pv_denominator`` across N1's rows (:func:`national_pv`).

The year filters of ``/elections`` narrow both charts, the table and its download
(#596, D110, amending D107's all-years scope): the page's ``query=`` parser is
:func:`explore.elections_view.parse_filters`, which drops an old ``state`` key, so it
still changes nothing. The index's popular-vote window and flags are checked as the
page's (:func:`explore.elections_view.index_rule`, which the filter reads), so a
disagreement degrades the whole page, as on the majority page. The one-state mode
(D100(a), (c), (e), (f)) retired with #562: a state's electors appointed are chart
C7, on its own page. A failed or malformed N1 degrades the section only; the heading,
lede and success marker stay.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

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
PAGE_ID = "elections-over-time"
#: This page's own path, the view URL its download names.
PATH = elections_view.OVER_TIME

#: Page-level wording (ba spec, approved by the owner at #562's plan gate, 2026-11-19).
#: The heading was the section heading on ``/elections`` (#436's plan gate).
HEADING = "Electors appointed and the total popular vote over time"
LEDE = (
    "For every election in this dataset: the electors appointed across all states, "
    "and the total popular vote across the country. A state's own electors appointed "
    "are on that state's page."
)

#: Page-level wording (ba spec for #596, approved at #596's plan gate, 2026-11-20):
#: shown after :data:`LEDE` only when the filter controls render.
FILTER_SENTENCE = (
    "Narrow the charts and table by year, or to the years with a popular vote in this "
    "dataset."
)

#: Charts C4 and C5 (#436, D100) and the companion table they share.
C4_ID = "C4"
C5_ID = "C5"
OVER_TIME_TABLE_ID = "elections-over-time-table"
OVER_TIME_UNAVAILABLE_ID = "elections-over-time-unavailable"
#: C4 and C5 stacked, C4 above C5, their table below (#593, D109, amending D102 and
#: D103(c), which set them side by side): they share the election-year axis, so one
#: column lets a reader read a year down both. Their one left and right margin, so the
#: two plots start and end at the same x, sized for the widest value tick either can
#: write (C5's short ticks since #596, D110, at most "150M"; C4's "500") and the axis
#: title, which plotly.js places by this margin: 72 px leaves each title 9 px from the
#: chart's edge at 360 px (112 before #596, sized for "160,000,000").
#: ``test_the_shared_margin_holds_every_value_tick_and_title`` (e2e) holds 8 px.
OVER_TIME_MARGIN = {"l": 72, "r": 16}
#: The companion table's columns, in display order, by public field name.
OVER_TIME_FIELDS = ("year", "electoral_denominator", "national_pv_denominator")
OVER_TIME_TABLE_HEADING = "Each election's electors appointed and total popular vote"
#: The section when N1 cannot be read or is malformed. Never ``UNAVAILABLE_MESSAGE``'s
#: wording: the D070(b) guard's success run asserts that absent from every page.
OVER_TIME_UNAVAILABLE = (
    "The charts and table of electors appointed and the total popular vote can't be "
    "shown right now. Please try again in a minute."
)

#: C5's value-axis format (#596, D110): d3's SI form, trailing zeros trimmed ("50M").
C5_TICKFORMAT = charts.SHORT_TICKFORMAT

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
    # The year filters (#596, D110): og:url names the filtered view.
    query=elections_view.parse_filters,
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


def _c5_figure(
    points: list[over_time.Point],
    years: list[int],
    title: str,
    window: tuple[int, int],
) -> over_time.OverTime:
    """C5's figure (#436, D100): the total popular vote of each row with one, as a bar
    at its year. The years before and after the popular-vote window (``window``, read
    from ``coverage``) are a shaded band, labeled inside it at its top (the band after
    the window, and a before band under half the axis, above the plot: #593, D109;
    #596, D110), which alone marks a held popular vote
    outside it; every other row with nothing to draw is a marker, one
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
        data.append(over_time.bar_trace(name, drawn, charts.PV_COLOR))
    data += over_time.series(marks, _C5_SYMBOLS)
    longest = max((value for _, value, _, _ in drawn), default=1)
    layout = over_time.time_layout(
        title,
        labels.C5_VALUE_AXIS,
        years,
        longest,
        marked=bool(marks),
        tick_px=components.YEAR_TICK_NARROW_PX,
    )
    bands = over_time.pv_bands(
        years,
        window,
        labels.C5_BEFORE_BAND.format(pv_year_min=pv_min),
        labels.C5_AFTER_BAND.format(pv_year_max=pv_max),
        # One key row per entry, the most rows the key can wrap to (#593's review).
        key_px=over_time.KEY_ROW_PX * len(marks),
    )
    # Short value ticks, C5's exception to the chart rule (#596, D110; its CHARTS row's
    # short_value_ticks); with no bar drawn the axis runs 0-1 and the SI form would
    # write "200m", so it writes no value ticks at all.
    if drawn:
        layout["yaxis"]["tickformat"] = C5_TICKFORMAT
    else:
        layout["yaxis"]["showticklabels"] = False
    if bands.shapes:
        layout["shapes"] = bands.shapes
        layout["annotations"] = bands.annotations
    if bands.top_px:
        layout["margin"] = {"t": bands.top_px}
    return over_time.OverTime(
        {"data": data, "layout": layout},
        False,
        bool(marks),
        bands.before,
        bands.after,
        bool(drawn),
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
    if c5.bars:
        parts.append(labels.C5_SHORT_TICKS_NOTE)
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


def _over_time_section(
    index: dict[str, Any],
    summary: Any,
    has_pv: dict[int, bool],
    chosen: elections_view.Filters,
    search: str,
    window: tuple[int, int],
    served_span: tuple[int, int],
) -> tuple[list[Any], bool]:
    """C4 and C5's section (#436, D100) and whether its filters rendered: the year
    filters, then both charts and their one companion table over the years they show
    (#596, D110), or :func:`explore.elections_view.no_match` when they show none; or,
    when N1 could not be read (``summary`` is ``None``) or is malformed,
    :data:`OVER_TIME_UNAVAILABLE` only, with no filters. Every served year's
    allotment, total and cells are read (``_all_states_points``) before the filters
    apply (#596's review, cr.1), so a filtered view never shows what the default view
    would refuse; a table row only wraps those cells, so none is built for a hidden
    year. The
    ``try`` covers everything built from
    N1; never ``components.chart``, which no page catches around (D095(f))."""
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        coverage = index["meta"]["provenance"]["coverage"]
        items = elections_view.n1_items(index, summary)
        totals = national_pv(summary, sorted(items))
        every = _all_states_points(items, totals, coverage)
        controls = elections_view.filter_controls(*served_span, chosen)
        points = [
            point
            for point in every
            if elections_view.shows(point.year, has_pv[point.year], chosen)
        ]
        if not points:
            return [controls, elections_view.no_match()], True
        years = [point.year for point in points]
        rows: list[dict[str, Any]] = [
            {
                "year": point.year,
                "electoral_denominator": point.appointed,
                "national_pv_denominator": point.total,
            }
            for point in points
        ]
        download = export.Download(
            filename="elections-electors-and-popular-vote-all-states.csv",
            name="electors appointed and the total popular vote, all states",
            provenance=summary["meta"]["provenance"],
            view_url=export.view_url(CANONICAL_HOST, PATH, search),
        )
        c4 = over_time.c4_figure(
            points,
            years,
            labels.C4_TITLE,
            None,
            tick_px=components.YEAR_TICK_NARROW_PX,
        )
        c5 = _c5_figure(points, years, labels.C5_TITLE, window)
        # Stacked, the two plots line up on one year axis (#593, D109): one fixed
        # left and right margin for both, sized for C5's widest value ticks, with no
        # value axis pushing its own; each keeps its own top margin.
        for figure in (c4.figure, c5.figure):
            layout = figure["layout"]
            layout["margin"] = {**layout.get("margin", {}), **OVER_TIME_MARGIN}
            layout["yaxis"]["automargin"] = False
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
        ], False
    return [
        controls,
        components.chart(C4_ID, c4.figure, OVER_TIME_TABLE_ID, _c4_caption(c4)),
        components.chart(
            C5_ID, c5.figure, OVER_TIME_TABLE_ID, _c5_caption(c5, window)
        ),
        html.H2(OVER_TIME_TABLE_HEADING),
        *table,
        labels.glossary(OVER_TIME_FIELDS),
    ], True


def render(
    index: dict[str, Any], summary: Any, pairs: list[tuple[str, str]] | None = None
) -> html.Div:
    """The whole page for one ``/v1/elections`` response, N1's body (``None`` when it
    could not be read) and the page's filter pairs
    (:func:`explore.elections_view.parse_filters`; none, every year): the heading and
    lede (with :data:`FILTER_SENTENCE` when the filters render), the section links
    carrying the filters applied, then C4 and C5's section, then the footer."""
    provenance = index["meta"]["provenance"]
    coverage = provenance["coverage"]
    # The index's rows are the page's, not a section's (cr.1): a defect there raises to
    # the layout, which degrades the whole page; so do its popular-vote flags, which
    # the filter reads (#596).
    elections_view.served_years(index)
    window, has_pv = elections_view.index_rule(index)
    chosen = elections_view.filters(pairs or [], coverage)
    first, last = elections_view.span(coverage)
    search = elections_view.applied_search(chosen, first, last)
    section, filtered = _over_time_section(
        index, summary, has_pv, chosen, search, window, (first, last)
    )
    return html.Div(
        [
            html.H1(HEADING),
            html.P(f"{LEDE} {FILTER_SENTENCE}" if filtered else LEDE, className="lede"),
            dcc.Location(id=elections_view.URL_ID, refresh="callback-nav"),
            elections_view.section_nav(elections_view.OVER_TIME, search),
            *section,
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
        return render(body, summary, elections_view.parse_filters(query))
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div([html.H1(HEADING), html.P(LEDE, className="lede"), content])
