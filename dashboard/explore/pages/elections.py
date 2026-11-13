"""The elections index (T1): every served election, filterable by year and popular vote.

The first table, and the one that sets the conventions later tables reuse (#306):

- **Labels** come from :mod:`explore.labels`, keyed by public field name.
- **Filters live only in the query string.** :func:`parse_filters` is the page's one
  parser: Dash's index uses it (``query=``) to normalize ``og:url``, and the layout uses
  it to read its filters, so a shared link reopens exactly the view it names. A filter
  change writes the normalized query to a page-local ``dcc.Location`` with
  ``refresh="callback-nav"``; Dash's Pages router then re-runs :func:`layout` with it,
  and that render reads the cached ``/v1/elections``, so changing a filter makes no API
  request.
- **The provenance footer** comes from :mod:`explore.components`, built from the
  response's own ``meta.provenance``.
- **The table** is :func:`explore.components.table`, which offers its rows as a CSV
  (#309) built from the same list as its body.
- **Chart C2** (#434, D096) sits above the filters, with its own companion table: each
  election's Electoral College leader's electoral share against the majority line,
  from N1 (:data:`explore.api.SUMMARY_PATH`), filled on a miss. No filter narrows
  either, and a failed or malformed N1 shows only that section's own sentence, so T1
  still renders.
- **The headline metrics** (#437, D097) sit between the filters and T1: the count of
  elections shown, then the average electoral and popular-vote margins over them, each
  with its own N and years, computed by :mod:`explore.metrics` from T1's own shown rows
  and N1's ``elections`` items (:func:`n1_items`, the one check C2 shares). A failed or
  malformed N1 replaces the averages with :data:`METRICS_UNAVAILABLE`; the count stays.
- **Charts C4 and C5** (#436, D100) follow T1, beside one companion table they share:
  electors appointed and the total popular vote in each election, for all states from
  N1, or for the one state the page's ``state`` filter chooses from N2
  (:data:`explore.api.ELECTION_STATES_PATH`, filled on a miss). The state filter
  switches their series and nothing else; the year and popular-vote filters never
  reach them. A failed or malformed N1 shows only the section's own sentence; a failed
  or malformed N2 keeps the all-states charts and hides the state choice.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable
from typing import Any, NamedTuple
from urllib.parse import parse_qs

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import (
    api,
    charts,
    components,
    election_view,
    export,
    labels,
    metrics,
    query,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in the table.
PAGE_ID = "elections"
TABLE_ID = "elections-table"
YEARS_ID = "elections-years"
PV_ID = "elections-pv"
URL_ID = "elections-url"

#: T1's columns, in display order, by public field name.
FIELDS = ("year", "candidate_count", "has_popular_vote")

#: Chart C2 (#434, D096) and its companion table, never narrowed by a filter.
C2_ID = "C2"
LEADER_TABLE_ID = "elections-leader-table"
LEADER_UNAVAILABLE_ID = "elections-leader-unavailable"
#: The companion table's columns, in display order, by public field name: the year's
#: Electoral College leader's national row, with the year's ``ec_determinative`` from
#: N1's ``elections`` item, and ``took_office`` last (owner, #434's plan gate).
LEADER_FIELDS = (
    "year",
    "candidate",
    "national_electoral_votes_counted",
    "national_electoral_denominator",
    "ec_share_full",
    "ec_determinative",
    "took_office",
)
#: The leader table's cells :func:`_leader_cells` words, in :data:`LEADER_FIELDS`
#: order (the year is a link and the candidate a linked name).
LEADER_WORDED = LEADER_FIELDS[2:]
#: Exported though not shown: the key of the candidate's history link.
LEADER_EXTRA = ("candidate_slug",)

#: Page-level wording (ba spec, approved by the owner at #434's plan gate, 2026-11-11).
LEDE = "Every US presidential election in this dataset."
#: Shown only on success, after :data:`LEDE` (the degraded page has no filters).
FILTER_SENTENCE = (
    "Narrow the list of elections by year, or to the years with a popular vote in "
    "this dataset."
)
C2_HEADING = "Did the Electoral College leader win a majority?"
C2_TABLE_HEADING = "Each election's Electoral College leader"
LIST_HEADING = "List of elections"
#: C2's section when N1 cannot be read or is malformed. Never ``UNAVAILABLE_MESSAGE``'s
#: wording: the D070(b) guard's success run asserts that absent from every page.
C2_UNAVAILABLE = (
    "The chart and table of each election's Electoral College leader can't be shown "
    "right now. Please try again in a minute."
)

#: The headline metrics (#437, D097): the block, its count line and each average's
#: value, by metric key; DOM ids are stable and never renamed.
METRICS_ID = "elections-metrics"
METRICS_UNAVAILABLE_ID = "elections-metrics-unavailable"
METRIC_IDS = {
    "elections_shown": "elections-shown",
    "ec_margin_mean": "elections-ec-margin-mean",
    "pv_margin_mean": "elections-pv-margin-mean",
}
#: The averages, in the order they show.
MEANS = ("ec_margin_mean", "pv_margin_mean")
#: The averages when N1 cannot be read or is malformed; the count still shows (ba spec,
#: #437). Never ``UNAVAILABLE_MESSAGE``'s wording, as :data:`C2_UNAVAILABLE`.
METRICS_UNAVAILABLE = (
    "The average margins can't be shown right now. Please try again in a minute."
)

#: C2's pixels per row (one tick line, so every year's label shows at 390 px) and the
#: margins around its plot: the top holds the majority line's label, the bottom the
#: share axis and the label again, and the right the widest point label, "100.0%".
_C2_ROW_PX = 24
_C2_TOP_PX = 56
_C2_BOTTOM_PX = 112
_C2_RIGHT_PX = 64

#: Charts C4 and C5 (#436, D100), the companion table they share, and the state
#: control that switches their series.
C4_ID = "C4"
C5_ID = "C5"
OVER_TIME_TABLE_ID = "elections-over-time-table"
OVER_TIME_UNAVAILABLE_ID = "elections-over-time-unavailable"
OVER_TIME_NO_STATES_ID = "elections-over-time-no-states"
STATE_ID = "elections-state"
#: The companion table's columns, in display order, by public field name: all states
#: (N1), and one state (N2's rows for it), whose download adds the state's code.
OVER_TIME_FIELDS = ("year", "electoral_denominator", "national_pv_denominator")
OVER_TIME_STATE_FIELDS = (
    "year",
    "state",
    "state_electoral_votes",
    "state_popular_total",
    "pv_status",
)
OVER_TIME_STATE_EXTRA = ("state_usps",)

#: The section's page-level wording (ba spec, approved at #436's plan gate).
OVER_TIME_HEADING = "Electors appointed and the total popular vote over time"
OVER_TIME_FILTER_SENTENCE = (
    "Choose a state to show its own figures in these two charts and their table; All "
    "states shows the national figures."
)
#: Shown only with the state control.
OVER_TIME_REACH = (
    "The state changes nothing else on the page: the chart of each election's "
    "Electoral College leader, the list of elections and its averages stay the same."
)
#: Shown whenever the charts render.
OVER_TIME_LIST_FILTERS = (
    "The list's year and popular-vote filters do not change these two charts or their "
    "table."
)
#: The section when N1 cannot be read or is malformed. Never ``UNAVAILABLE_MESSAGE``'s
#: wording, as :data:`C2_UNAVAILABLE`.
OVER_TIME_UNAVAILABLE = (
    "The charts and table of electors appointed and the total popular vote can't be "
    "shown right now. Please try again in a minute."
)
#: Shown in place of the filter sentence and the state control when N2 cannot be read
#: or is malformed; the charts and their table then show all states.
OVER_TIME_NO_STATES = (
    "Choosing a state can't be offered right now, so these charts and their table "
    "show all states. Please try again in a minute."
)
OVER_TIME_TABLE_HEADING = "Each election's electors appointed and total popular vote"
#: The state control's placeholder, which is "every state".
ALL_STATES = "All states"

#: C4 and C5's pixels per row (one tick line, so every year's label shows at 390 px),
#: and the margins around their plots: the top holds C5's band label, the bottom the
#: value axis's title, and the right the widest bar label.
_OVER_TIME_ROW_PX = 24
_OVER_TIME_TOP_PX = 56
_OVER_TIME_BOTTOM_PX = 48
_OVER_TIME_RIGHT_PX = 88
#: Each C5 marker label's symbol, so no two marker series differ by color alone.
_C5_SYMBOLS = {
    labels.C5_LEGISLATURE: "diamond",
    labels.C5_TOOK_NO_PART: "x",
    labels.C5_NO_TOTAL: "circle-open",
    labels.UNRECOGNIZED: "square-open",
}

#: The query keys this page reads. ``year_from`` and ``year_to`` are the API's own names
#: for a year range, so later tables with a year range share them. ``state`` is the
#: per-capita page's key, read by the same parser (#436).
YEAR_FROM = query.YEAR_FROM
YEAR_TO = query.YEAR_TO
PV = "pv"
STATE = election_view.STATE


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``,
    before any data is read. Keeps ``year_from`` / ``year_to`` only as four ASCII
    digits, ``pv`` only as ``"1"`` and ``state`` only as a USPS code
    (:func:`explore.election_view.parse_state`, #436); a key repeated with differing
    values is dropped, and so is a key it does not know. A range whose start is after
    its end drops both bounds. Whether a year lies inside the served span, or a state
    is served, is the layout's question (:func:`filters`, :func:`chosen_state`).
    """
    if not isinstance(params, dict):
        return []
    kept = query.parse_year_range(params)
    if query.single(params.get(PV)) == "1":
        kept[PV] = "1"
    kept.update(election_view.parse_state(params))
    return sorted(kept.items())


dash.register_page(
    __name__,
    path="/elections",
    title=f"Elections — {SITE_TITLE}",
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description="Every US presidential election in the dataset, filterable by year.",
    prefetch=(api.ELECTIONS_PATH,),
    # N1, filled on first use for C2 (#434), and N2 for C4 and C5's one-state series
    # (#436): literals (D074(ii)), never prefetched.
    on_miss=(api.SUMMARY_PATH, api.ELECTION_STATES_PATH),
    success=PAGE_ID,
    query=parse_filters,
    # The site navigation link this page marks (#448):
    # the elections index marks its own link.
    nav="elections",
)


class Filters(NamedTuple):
    """The filters a render applies, inside the served span.

    A ``NamedTuple``, not a dataclass: Dash executes a page module before it is in
    ``sys.modules``, which ``dataclass`` needs.
    """

    year_from: int
    year_to: int
    pv_only: bool


def span(coverage: dict[str, Any]) -> tuple[int, int]:
    """The served span, ``(year_min, year_max)``, or ``TypeError`` for a malformed one
    (:func:`explore.query.year_span`), which the layout turns into the degraded
    state."""
    return query.year_span(coverage["year_min"], coverage["year_max"])


def filters(pairs: list[tuple[str, str]], coverage: dict[str, Any]) -> Filters:
    """The filters to apply; a bound outside the served span falls back to its default.

    Fallback is per parameter, as ``og:url``'s is: ``og:url`` keeps each syntactically
    valid parameter except both bounds of an inverted pair (an out-of-span year
    included, which this replaces with its default) and drops the rest. The result is
    never inverted: :func:`parse_filters` already dropped an inverted pair, and a bound
    replaced by its default cannot pass the other bound.
    """
    first, last = span(coverage)
    year_from, year_to = query.year_range(pairs, first, last)
    return Filters(
        year_from=year_from,
        year_to=year_to,
        pv_only=dict(pairs).get(PV) == "1",
    )


def search_for(years: Any, pv: Any, first: Any, last: Any) -> str:
    """The query string for the controls' values, in the normal form ``og:url`` uses.

    Defaults are omitted, the pairs pass through :func:`parse_filters`, and the result
    is ``""`` or starts with ``?`` (a ``dcc.Location`` joins pathname and search
    verbatim).
    """
    params = query.year_range_search(years, first, last)
    if isinstance(pv, list) and "1" in pv:
        params[PV] = "1"
    return query.encode_search(parse_filters(params))


def applied_search(chosen: Filters, first: int, last: int) -> str:
    """The filters a render applied, in the normal form :func:`search_for` writes:
    already checked, so they are encoded without the parser."""
    params = query.year_range_search([chosen.year_from, chosen.year_to], first, last)
    if chosen.pv_only:
        params[PV] = "1"
    return query.encode_search(params.items())


#: Each filter control's query keys (#436): a change replaces only the keys of the
#: control that changed, so a key no control shows (a ``state`` the page could not
#: apply while N2 was unavailable) stays in the link.
CONTROL_KEYS: dict[str, tuple[str, ...]] = {
    YEARS_ID: (YEAR_FROM, YEAR_TO),
    PV_ID: (PV,),
    STATE_ID: (STATE,),
}


def merged_search(
    triggered: Any,
    years: Any,
    pv: Any,
    state: Any,
    first: Any,
    last: Any,
    current: Any,
) -> str:
    """The query string after the control ``triggered`` changed (#436, D100), in the
    normal form ``og:url`` uses: the current search through :func:`parse_filters`,
    only the triggered control's keys (:data:`CONTROL_KEYS`) replaced by its value,
    and the result through :func:`parse_filters` again. Pure; reads no API. A trigger
    that is no filter control replaces nothing."""
    params: dict[str, Any] = {}
    if isinstance(current, str):
        params.update(
            parse_filters(parse_qs(current.removeprefix("?"), keep_blank_values=True))
        )
    owned = CONTROL_KEYS.get(triggered, ()) if isinstance(triggered, str) else ()
    for key in owned:
        params.pop(key, None)
    if triggered == YEARS_ID:
        params.update(query.year_range_search(years, first, last))
    elif triggered == PV_ID:
        if isinstance(pv, list) and "1" in pv:
            params[PV] = "1"
    elif triggered == STATE_ID and isinstance(state, str) and state:
        params[STATE] = state
    return query.encode_search(parse_filters(params))


def next_search(
    triggered: Any,
    years: Any,
    pv: Any,
    state: Any,
    first: Any,
    last: Any,
    current: Any,
) -> Any:
    """What the filter callback writes: :func:`merged_search`, or ``no_update`` when
    that is the search the URL already has, which would navigate for nothing. Pure;
    reads no API."""
    search = merged_search(triggered, years, pv, state, first, last, current)
    return no_update if search == (current or "") else search


@callback(
    Output(URL_ID, "search"),
    Input(YEARS_ID, "value"),
    Input(PV_ID, "value"),
    Input(STATE_ID, "value"),
    State(YEARS_ID, "min"),
    State(YEARS_ID, "max"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(
    years: Any, pv: Any, state: Any, first: Any, last: Any, current: Any
) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. Only the changed control's keys change (:func:`next_search`).
    """
    return next_search(dash.ctx.triggered_id, years, pv, state, first, last, current)


def _row(election: dict[str, Any]) -> html.Tr:
    year = election["year"]
    return html.Tr(
        [
            # A year links to its one-election view (#307).
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            labels.cell(labels.number(election["candidate_count"])),
            labels.cell(labels.has_popular_vote(election["has_popular_vote"])),
        ]
    )


def n1_items(index: dict[str, Any], summary: Any) -> dict[int, dict[str, Any]]:
    """N1's ``elections`` items by year, one for each year the index serves (D096(c)):
    the one check of those items, which C2 (:func:`leaders`) and the averages (#437,
    D097) both call, so the rule for a valid item is in one place. Each refuses more on
    its own reads: C2 a missing ``ec_determinative`` and its rank-1 rule on ``data``
    rows, the averages a missing margin among the years shown.

    Pure; raises ``KeyError`` for a missing key and ``TypeError`` for a year (in the
    index's rows or in N1's items) that :func:`explore.election_view.row_year` refuses
    or that lies outside the served span, an N1 year the index does not serve, or a
    served year with no ``elections`` item or two. A year the index lists twice is one
    served year: refusing the duplicate is the index's own rule (#334). It reads no
    ``data`` row: those are C2's alone.
    """
    first, last = span(index["meta"]["provenance"]["coverage"])
    served: set[int] = set()
    for row in index["data"]:
        year = election_view.row_year(row)
        if year is None or not first <= year <= last:
            raise TypeError("/v1/elections names a year outside its served span")
        served.add(year)
    if not isinstance(summary, dict):
        raise TypeError(f"{api.SUMMARY_PATH} is not an object")
    items = summary["elections"]
    if not isinstance(items, list):
        raise TypeError(f"{api.SUMMARY_PATH} carries no list of elections")
    by_year: dict[int, dict[str, Any]] = {}
    for item in items:
        year = election_view.row_year(item)
        if year is None or year not in served or year in by_year:
            raise TypeError(f"{api.SUMMARY_PATH}: a bad elections item")
        by_year[year] = item
    if set(by_year) != served:
        raise TypeError(f"{api.SUMMARY_PATH} misses a served year")
    return by_year


def leaders(index: dict[str, Any], summary: Any) -> list[dict[str, Any]]:
    """Each served year's Electoral College leader, oldest first: N1's one ``data`` row
    with ``electoral_rank`` 1, with the year's ``ec_determinative`` from its one
    ``elections`` item (#434, D096). Derives nothing.

    Pure; raises what :func:`n1_items` raises, and ``TypeError`` for anything else C2
    cannot show: a ``data`` row whose year :func:`explore.election_view.row_year`
    refuses or the index does not serve, or a served year with no rank-1 row or two (a
    tie at rank 1 is valid API data, D094(iv), but C2 needs one leader per year).
    ``electoral_rank`` counts only as an ``int``, never a ``bool``.
    """
    by_year = n1_items(index, summary)
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
    return [
        {**leader[year], "ec_determinative": by_year[year]["ec_determinative"]}
        for year in sorted(served)
    ]


def _leader_cells(row: dict[str, Any]) -> dict[str, str]:
    """The leader table's worded cells, computed once per row per render and read by
    both the table and C2, so the chart writes every number as the table does."""
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


def _c2_figure(
    rows: list[dict[str, Any]], cells: list[dict[str, str]]
) -> dict[str, Any]:
    """C2's figure (#434, D096): one row per served year, oldest on top, each with one
    point, the leader's served ``ec_share_full``, labeled with the table's cell for it,
    against a dashed line at half of each election's electors appointed.

    A share the table does not show as one is drawn as a labeled marker at zero
    (:data:`explore.labels.C1_NO_SHARE` for a null or blank, else the table's cell),
    never a dropped year. Every hover and text item is a string the page wrote.
    """
    n = len(rows)
    positions = list(range(n))
    years = [str(row["year"]) for row in rows]
    xs: list[float | None] = []
    texts: list[str] = []
    hovers: list[str] = []
    marks: list[tuple[int, str, str, str]] = []  # (y, label, hover, id)
    for i, (row, cell) in enumerate(zip(rows, cells, strict=True)):
        shown = cell["ec_share_full"]
        number = labels.finite(row["ec_share_full"])
        # A finite value whose cell is no share (one whose percentage overflows reads
        # UNRECOGNIZED) is a marker too: the point stands only where the table shows it.
        x = number if number is not None and shown != labels.UNRECOGNIZED else None
        share = (
            f"{shown}<br>{labels.UNRECOGNIZED_NOTE}"
            if shown == labels.UNRECOGNIZED
            else shown
        )
        hover = labels.C2_HOVER.format(
            year=years[i],
            candidate=charts.escaped(str(row["candidate"])),
            share=share,
            counted=cell["national_electoral_votes_counted"],
            appointed=cell["national_electoral_denominator"],
            majority=_majority(cell["ec_determinative"]),
        )
        xs.append(x)
        texts.append(shown if x is not None else "")
        hovers.append(hover)
        if x is None:
            label = labels.C1_NO_SHARE if shown == labels.NOT_IN_DATASET else shown
            marks.append((i, label, hover, years[i]))
    data: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "markers+text",
            "name": labels.LABELS["ec_share_full"],
            "showlegend": False,
            "ids": years,
            "x": xs,
            "y": positions,
            "text": texts,
            "textposition": "middle right",
            "textfont": {"color": "var(--text)"},
            "cliponaxis": False,
            "marker": {"symbol": "circle", "size": 10, "color": "var(--chart-1)"},
            "hovertext": hovers,
            "hovertemplate": "%{hovertext}<extra></extra>",
        }
    ]
    if marks:
        data.append(
            {
                "type": "scatter",
                "mode": "markers+text",
                "name": labels.C2_NO_SHARE_SERIES,
                "showlegend": False,
                "ids": [mark[3] for mark in marks],
                "x": [0] * len(marks),
                "y": [mark[0] for mark in marks],
                "text": [mark[1] for mark in marks],
                "textposition": "middle right",
                "textfont": {"color": "var(--text)"},
                "cliponaxis": False,
                "marker": {"symbol": "x", "size": 10, "color": "var(--text)"},
                "hovertext": [mark[2] for mark in marks],
                "hovertemplate": "%{hovertext}<extra></extra>",
            }
        )
    line_label = {
        "text": labels.C2_MAJORITY_LINE,
        "xref": "x",
        "x": 0.5,
        "yref": "paper",
        "showarrow": False,
        "font": {"color": "var(--text)", "size": 12},
    }
    return {
        "data": data,
        "layout": {
            "title": {"text": labels.C2_TITLE},
            "height": _C2_ROW_PX * max(n, 1) + _C2_TOP_PX + _C2_BOTTOM_PX,
            "margin": {"t": _C2_TOP_PX, "b": _C2_BOTTOM_PX, "r": _C2_RIGHT_PX},
            "xaxis": {
                "range": [0, 1],
                "tickformat": ".0%",
                "dtick": 0.25,
                "title": {"text": labels.C2_X_AXIS},
            },
            "yaxis": {
                "tickvals": positions,
                "ticktext": years,
                "autorange": "reversed",
                "showgrid": False,
                "zeroline": False,
            },
            "shapes": [
                {
                    "type": "line",
                    "xref": "x",
                    "x0": 0.5,
                    "x1": 0.5,
                    "yref": "paper",
                    "y0": 0,
                    "y1": 1,
                    "layer": "below",
                    "line": {
                        "dash": "dash",
                        "width": 2,
                        "color": "var(--chart-reference)",
                    },
                }
            ],
            # The line's label above the plot and again below the share axis: the
            # chart is tall, so the top one has scrolled away by the last rows.
            "annotations": [
                {**line_label, "y": 1, "yanchor": "bottom"},
                {**line_label, "y": 0, "yanchor": "top", "yshift": -70},
            ],
        },
    }


def _c2_caption() -> str:
    """C2's caption: which candidate each point is, what the share counts, what the
    line marks and that the leader did not always take office. Constant, so it names
    no served text (D095(a)); ``components.chart`` adds the table pointer."""
    return " ".join(
        (
            labels.C2_LEADER_POINT,
            labels.C1_EC_BASIS,
            labels.C2_MAJORITY_NOTE,
            labels.C2_TOOK_OFFICE,
        )
    )


def _leader_section(index: dict[str, Any], summary: Any) -> list[Any]:
    """C2's section (#434, D096): its heading, the chart and its companion table, or,
    when N1 could not be read (``summary`` is ``None``) or is malformed, the heading and
    :data:`C2_UNAVAILABLE` only. The ``try`` covers everything built from N1 (the
    validation, the figure, the cells, and the companion table and its download), so no
    ``KeyError`` or ``TypeError`` from N1 reaches the page; never ``components.chart``,
    which no page catches around (D095(f))."""
    heading = html.H2(C2_HEADING)
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        rows = leaders(index, summary)
        cells = [_leader_cells(row) for row in rows]
        figure = _c2_figure(rows, cells)
        download = export.Download(
            filename="elections-electoral-college-leaders.csv",
            name="the Electoral College leaders",
            provenance=summary["meta"]["provenance"],
            # No filter reaches this table, so its view names none.
            view_url=export.view_url(CANONICAL_HOST, "/elections", ""),
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
            notes=(labels.C2_LEADER_ROW, labels.C2_TOOK_OFFICE),
        )
    except (KeyError, TypeError):
        return [
            heading,
            html.P(C2_UNAVAILABLE, id=LEADER_UNAVAILABLE_ID, className="note"),
        ]
    return [
        heading,
        components.chart(C2_ID, figure, LEADER_TABLE_ID, _c2_caption()),
        html.H2(C2_TABLE_HEADING),
        *table,
        labels.glossary(LEADER_FIELDS),
    ]


def _shown_year(row: Any) -> int:
    """A shown T1 row's year, checked (:func:`n1_items` already refused a bad one)."""
    year = election_view.row_year(row)
    if year is None:
        raise TypeError("/v1/elections names a year that is not one")
    return year


def _averages(
    index: dict[str, Any], summary: Any, shown: list[Any], pv_only: bool
) -> list[Any]:
    """The two average margins over the elections T1 shows (#437, D097), as a ``dl``
    and its notes, or :data:`METRICS_UNAVAILABLE` alone when N1 could not be read
    (``summary`` is ``None``), its ``elections`` items fail :func:`n1_items`, an item
    lacks a margin field, or the index's popular-vote window is malformed.

    Each year shown counts once, however often the index lists it (#334). Each mean
    reads the field ``metrics.METRICS`` names, so that table drives what is averaged.
    """
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        items = n1_items(index, summary)
        coverage = index["meta"]["provenance"]["coverage"]
        pv_window = query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
        years = sorted({_shown_year(e) for e in shown})
        means = {
            key: metrics.mean(
                (year, items[year][metrics.METRICS[key].source.field]) for year in years
            )
            for key in MEANS
        }
    except (KeyError, TypeError):
        return [
            html.P(METRICS_UNAVAILABLE, id=METRICS_UNAVAILABLE_ID, className="note")
        ]
    windows = {"ec_margin_mean": None, "pv_margin_mean": pv_window}
    entries: list[Any] = []
    for key in MEANS:
        value, over = labels.metric_mean(means[key], years, windows[key])
        children: Any = (
            value
            if over is None
            else [html.Span(value, className="metric-value"), html.Span(over)]
        )
        entries += [
            html.Dt(labels.METRIC_LABELS[key]),
            labels.cell(children, functools.partial(html.Dd, id=METRIC_IDS[key])),
        ]
    notes = [html.P(labels.MARGIN_NOTE, className="note")]
    ec, pv = (means[key] for key in MEANS)
    # The note names the popular-vote window as the reason the two differ, so it shows
    # only where the window is one: a year in the electoral average lies outside it. A
    # difference from a missing margin inside the window shows each average's own N
    # and years, and no note (owner, #437's code review).
    if (
        ec.value is not None
        and pv.value is not None
        and (ec.n, ec.first, ec.last) != (pv.n, pv.first, pv.last)
        and ec.first is not None
        and ec.last is not None
        and (ec.first < pv_window[0] or ec.last > pv_window[1])
    ):
        sentence = labels.METRIC_DIFFERENT_ELECTIONS.format(
            first=pv_window[0], last=pv_window[1]
        )
        if not pv_only:
            sentence = f"{sentence} {labels.METRIC_SAME_ELECTIONS}"
        notes.append(html.P(sentence, className="note"))
    return [html.Dl(entries, className="metrics"), *notes]


# --- Charts C4 and C5 (#436, D100) ---------------------------------------------------


def _same(a: Any, b: Any) -> bool:
    """Whether two served values are one value: of one type and equal, so a null beside
    a figure is two values, as D077 and D098 count NULL. A NaN repeated is one value
    (it is unequal to itself), which its cell then reads as unrecognized."""
    if type(a) is not type(b):
        return False
    return bool(a == b) or (isinstance(a, float) and a != a and b != b)


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
        if year in totals and not _same(totals[year], value):
            raise TypeError(f"{api.SUMMARY_PATH}: two national totals in {year}")
        totals[year] = value
    if set(totals) != years:
        raise TypeError(f"{api.SUMMARY_PATH} misses a served year")
    return totals


def n2_rows(body: Any, served: Iterable[int]) -> dict[str, list[dict[str, Any]]]:
    """N2's rows by USPS code, each state's in year order from its first served
    election (#436, D100): C4 and C5's one-state series and their table's rows.

    Pure; raises ``KeyError`` for a missing key and ``TypeError`` for a body whose rows
    are not a non-empty list, a row that is not an object, a year
    :func:`explore.election_view.row_year` refuses or that is not served, a USPS code
    :data:`explore.query.USPS_RE` refuses, two rows for one year and state, two names
    for one code, or a gap: a served year after a state's first with no row for it.
    """
    years = sorted(set(served))
    if not isinstance(body, dict):
        raise TypeError(f"{api.ELECTION_STATES_PATH} is not an object")
    rows = body["data"]
    if not isinstance(rows, list) or not rows:
        raise TypeError(f"{api.ELECTION_STATES_PATH} carries no list of rows")
    by_state: dict[str, dict[int, dict[str, Any]]] = {}
    names: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError(f"{api.ELECTION_STATES_PATH}: a row that is not an object")
        year = election_view.row_year(row)
        if year is None or year not in years:
            raise TypeError(f"{api.ELECTION_STATES_PATH}: a row for a year not served")
        usps = row["state_usps"]
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError(f"{api.ELECTION_STATES_PATH} carries a bad state code")
        name = row["state"]
        if not _same(names.setdefault(usps, name), name):
            raise TypeError(f"{api.ELECTION_STATES_PATH} names {usps} two ways")
        state_years = by_state.setdefault(usps, {})
        if year in state_years:
            raise TypeError(f"{api.ELECTION_STATES_PATH} repeats {usps} in {year}")
        state_years[year] = row
    series: dict[str, list[dict[str, Any]]] = {}
    for usps, state_years in by_state.items():
        expected = [year for year in years if year >= min(state_years)]
        if sorted(state_years) != expected:
            raise TypeError(f"{api.ELECTION_STATES_PATH} skips a year for {usps}")
        series[usps] = [state_years[year] for year in expected]
    return series


def chosen_state(
    pairs: list[tuple[str, str]], series: dict[str, list[dict[str, Any]]] | None
) -> str | None:
    """The state C4 and C5 show: the query's, if N2 serves it, else ``None`` ("all
    states"), as the per-capita page keeps its state. With N2 unavailable
    (``series`` is ``None``) every state falls back."""
    state = dict(pairs).get(STATE)
    return state if series is not None and state in series else None


def _plain(name: Any) -> str | None:
    """A served state name a title or caption may name (#436): text with something in
    it and nothing ``components.chart`` refuses in a title or plotly could read as
    markup or a token; else ``None``, and the "selected state" form is used."""
    if not isinstance(name, str) or not labels.has_text(name):
        return None
    if "<" in name or "var(" in name:
        return None
    return name


class Point(NamedTuple):
    """One row of C4 and C5 (#436): its year, the served appointed allotment and total
    popular vote, and the companion table's cells for them (and, for one state, for
    its ``pv_status``)."""

    year: int
    appointed: Any
    appointed_cell: str
    total: Any
    total_cell: str
    status: Any
    status_cell: str | None


def _all_states_points(
    items: dict[int, dict[str, Any]],
    totals: dict[int, Any],
    coverage: dict[str, Any],
) -> list[Point]:
    """All states: each served year's N1 allotment and national total, worded once."""
    points = []
    for year in sorted(items):
        appointed = items[year]["electoral_denominator"]
        points.append(
            Point(
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


def _state_points(rows: list[dict[str, Any]], coverage: dict[str, Any]) -> list[Point]:
    """One state: its N2 rows, from its first election, worded once."""
    points = []
    for row in rows:
        year = election_view.row_year(row)
        if year is None:
            raise TypeError(f"{api.ELECTION_STATES_PATH} names a year that is not one")
        status = row["pv_status"]
        points.append(
            Point(
                year=year,
                appointed=row["state_electoral_votes"],
                appointed_cell=labels.number(row["state_electoral_votes"]),
                total=row["state_popular_total"],
                total_cell=labels.popular_votes(
                    row["state_popular_total"],
                    status,
                    year,
                    coverage,
                    labels.NO_STATE_TOTAL,
                ),
                status=status,
                status_cell=labels.pv_status(status),
            )
        )
    return points


def _figure_value(value: Any, *, zero: bool) -> int | None:
    """A served count a bar can draw: an ``int`` (never a ``bool``) no larger than
    :data:`explore.charts.MAX_INTEGER`, above zero, or at zero too where ``zero``.
    Anything else is a marker."""
    if type(value) is not int or value > charts.MAX_INTEGER:
        return None
    return value if value > 0 or (zero and value == 0) else None


def _noted(cell: str) -> str:
    """A cell as a hover writes it: an unrecognized one adds its note."""
    if cell == labels.UNRECOGNIZED:
        return f"{cell}<br>{labels.UNRECOGNIZED_NOTE}"
    return cell


def _hover(point: Point, state: str | None, *, total: bool) -> str:
    """A row's hover in C4 (``total`` false) or C5: the table's cells. ``state`` is
    the escaped state name, or ``None`` for all states."""
    year = str(point.year)
    if state is None:
        if total:
            return labels.C5_HOVER.format(year=year, total=_noted(point.total_cell))
        return labels.C4_HOVER.format(year=year, appointed=_noted(point.appointed_cell))
    status = _noted(point.status_cell or labels.UNRECOGNIZED)
    if total:
        return labels.C5_STATE_HOVER.format(
            year=year, state=state, total=_noted(point.total_cell), pv_status=status
        )
    return labels.C4_STATE_HOVER.format(
        year=year,
        state=state,
        appointed=_noted(point.appointed_cell),
        pv_status=status,
    )


def _bar_trace(
    name: str, drawn: list[tuple[Point, int, str, str]], position: dict[int, int]
) -> dict[str, Any]:
    """A series of bars, one per drawn row, each labeled with its table cell."""
    return {
        "type": "bar",
        "orientation": "h",
        "name": name,
        "showlegend": False,
        "ids": [str(point.year) for point, _, _, _ in drawn],
        "x": [value for _, value, _, _ in drawn],
        "y": [position[point.year] for point, _, _, _ in drawn],
        "text": [cell for _, _, cell, _ in drawn],
        "textposition": "outside",
        "textfont": {"color": "var(--text)"},
        "cliponaxis": False,
        "marker": {"color": "var(--chart-1)"},
        "hovertext": [hover for _, _, _, hover in drawn],
        "hovertemplate": "%{hovertext}<extra></extra>",
    }


def _marker_trace(
    name: str,
    symbol: str,
    marks: list[tuple[Point, str, str]],
    position: dict[int, int],
) -> dict[str, Any]:
    """A series of labeled markers at zero, one per row with nothing to draw."""
    return {
        "type": "scatter",
        "mode": "markers+text",
        "name": name,
        "showlegend": False,
        "ids": [str(point.year) for point, _, _ in marks],
        "x": [0] * len(marks),
        "y": [position[point.year] for point, _, _ in marks],
        "text": [label for _, label, _ in marks],
        "textposition": "middle right",
        "textfont": {"color": "var(--text)"},
        "cliponaxis": False,
        "marker": {"symbol": symbol, "size": 10, "color": "var(--text)"},
        "hovertext": [hover for _, _, hover in marks],
        "hovertemplate": "%{hovertext}<extra></extra>",
    }


def _over_time_layout(
    title: str, axis: str, years: list[int], longest: int
) -> dict[str, Any]:
    """C4 and C5's shared layout: one row per served year, oldest on top, in every mode
    (an explicit range, so a state's empty rows before its first election keep their
    place), and value-axis ticks hidden, as C3's."""
    n = len(years)
    return {
        "title": {"text": title},
        "height": _OVER_TIME_ROW_PX * max(n, 1)
        + _OVER_TIME_TOP_PX
        + _OVER_TIME_BOTTOM_PX,
        "margin": {
            "t": _OVER_TIME_TOP_PX,
            "b": _OVER_TIME_BOTTOM_PX,
            "r": _OVER_TIME_RIGHT_PX,
        },
        "showlegend": False,
        "xaxis": {
            "range": [0, max(longest, 1)],
            "showticklabels": False,
            "title": {"text": axis},
        },
        "yaxis": {
            "tickvals": list(range(n)),
            "ticktext": [str(year) for year in years],
            "range": [n - 0.5, -0.5],
            "autorange": False,
            "showgrid": False,
            "zeroline": False,
        },
    }


class OverTime(NamedTuple):
    """A chart's figure and what its caption needs to say."""

    figure: dict[str, Any]
    zeros: bool
    missing: bool
    before: bool
    after: bool


def _c4_figure(
    points: list[Point], years: list[int], title: str, state: str | None
) -> OverTime:
    """C4's figure (#436, D100): the appointed allotment of each row with one, as a
    bar labeled with its table cell; a zero allotment is a labeled marker by its cause
    (the D091 exception), and a null or unknown one a marker in a series of its own.
    ``state`` is the escaped state name, or ``None`` for all states."""
    position = {year: i for i, year in enumerate(years)}
    drawn: list[tuple[Point, int, str, str]] = []
    zeros: list[tuple[Point, str, str]] = []
    missing: list[tuple[Point, str, str]] = []
    for point in points:
        hover = _hover(point, state, total=False)
        value = _figure_value(point.appointed, zero=False)
        if value is not None and point.appointed_cell != labels.UNRECOGNIZED:
            drawn.append((point, value, point.appointed_cell, hover))
        elif type(point.appointed) is int and point.appointed == 0:
            label = (
                labels.C4_NO_ELECTORS_TOOK_NO_PART
                if point.status == "not_participating"
                else labels.C4_NO_ELECTORS
            )
            zeros.append((point, label, hover))
        else:
            label = (
                labels.NOT_IN_DATASET
                if point.appointed_cell == labels.NOT_IN_DATASET
                else labels.UNRECOGNIZED
            )
            missing.append((point, label, hover))
    name = labels.LABELS[
        "electoral_denominator" if state is None else "state_electoral_votes"
    ]
    data: list[dict[str, Any]] = []
    if drawn:
        data.append(_bar_trace(name, drawn, position))
    if zeros:
        data.append(_marker_trace(labels.C4_NO_ELECTORS, "x", zeros, position))
    if missing:
        data.append(
            _marker_trace(labels.C4_NO_FIGURE_SERIES, "circle-open", missing, position)
        )
    longest = max((value for _, value, _, _ in drawn), default=1)
    figure = {
        "data": data,
        "layout": _over_time_layout(title, labels.C4_X_AXIS, years, longest),
    }
    return OverTime(figure, bool(zeros), bool(missing), False, False)


def _band(
    rows: list[int], label: str, *, top: bool
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A shaded band over ``rows`` (positions, consecutive) and its labels: at the
    band's lower edge, inside it, and, for the band before the window (``top``), above
    the plot too, since the chart is tall."""
    first, last = rows[0], rows[-1]
    shape = {
        "type": "rect",
        "xref": "paper",
        "x0": 0,
        "x1": 1,
        "yref": "y",
        "y0": first - 0.5,
        "y1": last + 0.5,
        "layer": "below",
        "fillcolor": "var(--chart-grid)",
        "line": {"width": 1, "color": "var(--chart-reference)"},
    }
    common = {
        "text": label,
        "showarrow": False,
        "font": {"color": "var(--text)", "size": 12},
    }
    notes = [
        {
            **common,
            "xref": "paper",
            "x": 1,
            "xanchor": "right",
            "yref": "y",
            "y": last + 0.5,
            "yanchor": "bottom",
        }
    ]
    if top:
        notes.append(
            {**common, "xref": "paper", "x": 0.5, "yref": "paper", "y": 1}
            | {"yanchor": "bottom"}
        )
    return shape, notes


def _c5_figure(
    points: list[Point],
    years: list[int],
    title: str,
    state: str | None,
    window: tuple[int, int],
) -> OverTime:
    """C5's figure (#436, D100): the total popular vote of each row with one, as a bar
    labeled with its table cell. The years before and after the popular-vote window
    (``window``, read from ``coverage``) are a labeled band, which alone marks a held
    popular vote outside it; every other row with nothing to draw is a labeled marker,
    one series per label (:data:`explore.labels.C5_MARKER_LABELS`), wherever it falls,
    inside the band included. ``state`` is the escaped state name, or ``None``."""
    position = {year: i for i, year in enumerate(years)}
    pv_min, pv_max = window
    banded = {
        labels.NOT_APPLICABLE,
        labels.AFTER_WINDOW,
        labels.BEFORE_WINDOW.format(pv_year_min=pv_min),
    }
    drawn: list[tuple[Point, int, str, str]] = []
    marks: dict[str, list[tuple[Point, str, str]]] = {}
    for point in points:
        hover = _hover(point, state, total=True)
        value = _figure_value(point.total, zero=True)
        if value is not None and point.total_cell == labels.number(value):
            drawn.append((point, value, point.total_cell, hover))
            continue
        outside = not pv_min <= point.year <= pv_max
        if outside and point.total_cell in banded:
            continue
        label = labels.C5_MARKER_LABELS.get(point.total_cell, labels.UNRECOGNIZED)
        marks.setdefault(label, []).append((point, label, hover))
    name = labels.LABELS[
        "national_pv_denominator" if state is None else "state_popular_total"
    ]
    data: list[dict[str, Any]] = []
    if drawn:
        data.append(_bar_trace(name, drawn, position))
    for label, symbol in _C5_SYMBOLS.items():
        if label in marks:
            data.append(_marker_trace(label, symbol, marks[label], position))
    longest = max((value for _, value, _, _ in drawn), default=1)
    layout = _over_time_layout(title, labels.C5_X_AXIS, years, longest)
    shapes: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    before = [position[year] for year in years if year < pv_min]
    after = [position[year] for year in years if year > pv_max]
    if before:
        shape, notes = _band(
            before, labels.C5_BEFORE_BAND.format(pv_year_min=pv_min), top=True
        )
        shapes.append(shape)
        annotations += notes
    if after:
        shape, notes = _band(
            after, labels.C5_AFTER_BAND.format(pv_year_max=pv_max), top=False
        )
        shapes.append(shape)
        annotations += notes
    if shapes:
        layout["shapes"] = shapes
        layout["annotations"] = annotations
    return OverTime(
        {"data": data, "layout": layout}, False, bool(marks), bool(before), bool(after)
    )


def _c4_caption(c4: OverTime, state: str | None, first: int | None) -> str:
    """C4's caption: what electors appointed is, what an all-states bar adds up, what
    each marker means where one is drawn, and a state's first election where it comes
    after the dataset's first. Names a served state only in plain text (``state`` is
    the plain name or ``None``); ``components.chart`` adds the table pointer."""
    parts = [labels.C4_BASIS]
    if first is None:
        parts.append(labels.C4_ALL_STATES)
    if c4.zeros:
        parts.append(labels.C4_ZERO_NOTE)
    if c4.missing:
        parts.append(labels.C4_NO_FIGURE_NOTE)
    return " ".join(parts + _first_note(state, first))


def _c5_caption(
    c5: OverTime, state: str | None, first: int | None, window: tuple[int, int]
) -> str:
    """C5's caption: what the total counts, what an all-states bar adds up, what the
    band and the markers mean where drawn, and a state's first election."""
    parts = [labels.C5_BASIS]
    if first is None:
        parts.append(labels.C5_ALL_STATES)
    if c5.before:
        parts.append(labels.C5_BEFORE_NOTE.format(pv_year_min=window[0]))
    if c5.after:
        parts.append(labels.C5_AFTER_NOTE.format(pv_year_max=window[1]))
    if c5.missing:
        parts.append(labels.C5_MARKER_NOTE)
    return " ".join(parts + _first_note(state, first))


def _first_note(state: str | None, first: int | None) -> list[str]:
    """The first-election sentence, for a state whose first election comes after the
    dataset's first (``first`` is that year, else ``None``)."""
    if first is None:
        return []
    if state is None:
        return [labels.FIRST_ELECTION_NOTE_SELECTED.format(year=first)]
    return [labels.FIRST_ELECTION_NOTE.format(state=state, year=first)]


def _state_control(
    series: dict[str, list[dict[str, Any]]] | None, chosen: str | None
) -> html.Div:
    """The state control, its options N2's states by name. Rendered on every successful
    render, so the filter callback's inputs always exist: with N2 unavailable
    (``series`` is ``None``) it is hidden, with no options and no value. Its value is
    always ``None`` or one of its options."""
    options = [
        {"label": str(rows[0]["state"]), "value": usps}
        for usps, rows in sorted(
            (series or {}).items(), key=lambda kv: str(kv[1][0]["state"])
        )
    ]
    value = chosen if any(option["value"] == chosen for option in options) else None
    hidden: dict[str, Any] = (
        {} if series is not None else {"style": {"display": "none"}}
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Label(
                        labels.LABELS[STATE], htmlFor=STATE_ID, className="label"
                    ),
                    dcc.Dropdown(
                        id=STATE_ID,
                        options=options,
                        value=value,
                        placeholder=ALL_STATES,
                        clearable=True,
                    ),
                ],
                className="filter",
            )
        ],
        className="filters",
        **hidden,
    )


def _over_time_row(point: Point, row: dict[str, Any]) -> html.Tr:
    """A row of the companion table: the year, linked to its election, then (for one
    state) the state's name linked to its history, and the cells C4 and C5 write."""
    year = html.Td(dcc.Link(str(point.year), href=f"/election/{point.year}"))
    if point.status_cell is None:
        return html.Tr(
            [year, labels.cell(point.appointed_cell), labels.cell(point.total_cell)]
        )
    return html.Tr(
        [
            year,
            components.state_cell(row),
            labels.cell(point.appointed_cell),
            labels.cell(point.total_cell),
            labels.cell(point.status_cell),
        ]
    )


def _over_time_section(
    index: dict[str, Any],
    summary: Any,
    states: Any,
    pairs: list[tuple[str, str]],
) -> list[Any]:
    """C4 and C5's section (#436, D100): its heading, the state choice, both charts and
    their one companion table.

    A failed (``summary`` is ``None``) or malformed N1 shows the heading and
    :data:`OVER_TIME_UNAVAILABLE` only, beside the hidden state control. A failed
    (``states`` is ``None``) or malformed N2 keeps the all-states charts and table and
    shows :data:`OVER_TIME_NO_STATES` in place of the control, hidden; a ``state`` in
    the link stays in it but is not applied. The ``try`` covers everything built from
    N1 and N2; never ``components.chart``, which no page catches around (D095(f))."""
    heading = html.H2(OVER_TIME_HEADING)
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        coverage = index["meta"]["provenance"]["coverage"]
        window = query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
        items = n1_items(index, summary)
        years = sorted(items)
        totals = national_pv(summary, years)
        series: dict[str, list[dict[str, Any]]] | None = None
        state_provenance: Any = None
        if states is not None:
            try:
                series = n2_rows(states, years)
                state_provenance = states["meta"]["provenance"]
            except (KeyError, TypeError):
                series = None
        chosen = chosen_state(pairs, series)
        if chosen is None or series is None:
            rows: list[dict[str, Any]] = [
                {
                    "year": year,
                    "electoral_denominator": items[year]["electoral_denominator"],
                    "national_pv_denominator": totals[year],
                }
                for year in years
            ]
            points = _all_states_points(items, totals, coverage)
            fields: tuple[str, ...] = OVER_TIME_FIELDS
            extra: tuple[str, ...] = ()
            name: Any = None
            first: int | None = None
            download = export.Download(
                filename="elections-electors-and-popular-vote-all-states.csv",
                name="electors appointed and the total popular vote, all states",
                provenance=summary["meta"]["provenance"],
                view_url=export.view_url(CANONICAL_HOST, "/elections", ""),
            )
        else:
            rows = series[chosen]
            points = _state_points(rows, coverage)
            fields, extra = OVER_TIME_STATE_FIELDS, OVER_TIME_STATE_EXTRA
            name = rows[0]["state"]
            first = points[0].year if points[0].year > years[0] else None
            download = export.Download(
                filename=f"elections-electors-and-popular-vote-{chosen}.csv",
                name="electors appointed and the total popular vote for this state",
                provenance=state_provenance,
                view_url=export.view_url(
                    CANONICAL_HOST,
                    "/elections",
                    query.encode_search([(STATE, chosen)]),
                ),
            )
        if not rows:
            raise TypeError("the over-time table has no rows")
        plain = _plain(name)
        state = None if chosen is None else charts.escaped(str(name))
        if chosen is None:
            c4_title, c5_title = labels.C4_TITLE, labels.C5_TITLE
        elif plain is None:
            c4_title, c5_title = labels.C4_TITLE_SELECTED, labels.C5_TITLE_SELECTED
        else:
            c4_title = labels.C4_TITLE_STATE.format(state=plain)
            c5_title = labels.C5_TITLE_STATE.format(state=plain)
        c4 = _c4_figure(points, years, c4_title, state)
        c5 = _c5_figure(points, years, c5_title, state, window)
        c4_caption = _c4_caption(c4, plain, first)
        c5_caption = _c5_caption(c5, plain, first, window)
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
            lambda r: _over_time_row(by_row[id(r)], r),
            fields,
            OVER_TIME_TABLE_ID,
            download,
            extra=extra,
            notes=notes,
        )
    except (KeyError, TypeError):
        return [
            heading,
            _state_control(None, None),
            html.P(
                OVER_TIME_UNAVAILABLE, id=OVER_TIME_UNAVAILABLE_ID, className="note"
            ),
        ]
    if series is None:
        choice = [
            html.P(OVER_TIME_NO_STATES, id=OVER_TIME_NO_STATES_ID, className="note"),
            _state_control(None, None),
        ]
    else:
        choice = [
            html.P(OVER_TIME_FILTER_SENTENCE, className="note"),
            _state_control(series, chosen),
            html.P(OVER_TIME_REACH, className="note"),
        ]
    return [
        heading,
        *choice,
        html.P(OVER_TIME_LIST_FILTERS, className="note"),
        components.chart(C4_ID, c4.figure, OVER_TIME_TABLE_ID, c4_caption),
        components.chart(C5_ID, c5.figure, OVER_TIME_TABLE_ID, c5_caption),
        html.H2(OVER_TIME_TABLE_HEADING),
        *table,
        labels.glossary(fields),
    ]


def render(
    body: dict[str, Any],
    pairs: list[tuple[str, str]],
    summary: Any = None,
    states: Any = None,
) -> html.Div:
    """The whole page for one ``/v1/elections`` response, this page's filter pairs,
    N1's body and N2's (each ``None`` when it could not be read): the heading and lede,
    C2's section, the list of elections with its headline metrics, then C4 and C5's
    section. The year and popular-vote filters narrow T1 and the metrics computed from
    it only; the state filter switches C4, C5 and their table only."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    chosen = filters(pairs, coverage)
    elections = body["data"]
    # A served snapshot always has elections: anything else is a malformed body, and
    # rendering it would show the success marker over "no elections match".
    if not isinstance(elections, list) or not elections:
        raise TypeError("/v1/elections carries no list of elections")
    shown = [
        e
        for e in elections
        if chosen.year_from <= e["year"] <= chosen.year_to
        and (e["has_popular_vote"] is True or not chosen.pv_only)
    ]
    first, last = span(coverage)
    controls = html.Div(
        [
            html.Label("Years", htmlFor=YEARS_ID, className="label"),
            components.year_slider(
                YEARS_ID, first, last, (chosen.year_from, chosen.year_to)
            ),
            dcc.Checklist(
                id=PV_ID,
                options=[
                    {
                        "label": " Only years with a popular vote in this dataset",
                        "value": "1",
                    }
                ],
                value=["1"] if chosen.pv_only else [],
            ),
        ],
        className="filters",
    )
    download = export.Download(
        filename="elections.csv",
        name="the elections",
        provenance=provenance,
        view_url=export.view_url(
            CANONICAL_HOST, "/elections", applied_search(chosen, first, last)
        ),
    )
    return html.Div(
        [
            html.H1("Elections"),
            html.P(f"{LEDE} {FILTER_SENTENCE}", className="lede"),
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            *_leader_section(body, summary),
            html.H2(LIST_HEADING),
            controls,
            html.Div(
                [
                    html.P(
                        labels.METRIC_LABELS["elections_shown"].format(
                            shown=metrics.count(shown),
                            total=metrics.count(elections),
                        ),
                        id=METRIC_IDS["elections_shown"],
                        className="count",
                    ),
                    *_averages(body, summary, shown, chosen.pv_only),
                ],
                id=METRICS_ID,
            ),
            *components.table(
                shown,
                _row,
                FIELDS,
                TABLE_ID,
                download,
                notes=(labels.HAS_POPULAR_VOTE_NOTE,),
                empty="No elections match these filters.",
            ),
            labels.glossary(FIELDS),
            *_over_time_section(body, summary, states, pairs),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(**query: Any) -> html.Div:
    """The elections index. On success, :func:`render`'s body is the whole page; the
    degraded state gets the heading and :data:`LEDE` here. N1 and then N2 are read in
    the same view, after the index, each in its own ``try``: a failed N1 degrades only
    C2's section, the averages and C4 and C5's section, and a failed N2 only the state
    choice."""
    try:
        with api.CLIENT.view() as view:
            body = view.get(api.ELECTIONS_PATH)
            try:
                summary = view.get(api.SUMMARY_PATH)
            except api.ApiUnavailable:
                summary = None
            try:
                states = view.get(api.ELECTION_STATES_PATH)
            except api.ApiUnavailable:
                states = None
        return render(body, parse_filters(query), summary, states)
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div([html.H1("Elections"), html.P(LEDE, className="lede"), content])
