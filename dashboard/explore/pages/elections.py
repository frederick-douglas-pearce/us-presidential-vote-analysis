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
    over_time,
    query,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in the table.
PAGE_ID = "elections"
TABLE_ID = "elections-table"
YEARS_ID = "elections-years"
PV_ID = "elections-pv"
URL_ID = "elections-url"
#: T1's column-name list: the page has three since #436.
GLOSSARY_ID = "elections-glossary"
#: The list's pair (#553, D102): its filters left, the count and averages right.
LIST_PAIR_ID = "elections-list-pair"

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

#: C2's height, the same for every number of served years now that years run along
#: the bottom (#558, D104). Its title is page text (``components.chart`` takes it out of
#: the figure), so the template's top margin holds nothing above the plot.
_C2_HEIGHT_PX = 360
#: How far below the majority line its label starts: more than C2's point radius.
_C2_LINE_LABEL_SHIFT_PX = 6
#: Each C2 marker series' symbol (#558, D104), so no two differ by color alone; one
#: symbol per meaning across C2, C4 and C5 (an open circle for no figure in this
#: dataset, an open square for an unrecognized value).
_C2_SYMBOLS = {
    labels.C1_NO_SHARE: "circle-open",
    labels.UNRECOGNIZED: "square-open",
}

#: Charts C4 and C5 (#436, D100), the companion table they share, and the state
#: control that switches their series.
C4_ID = "C4"
C5_ID = "C5"
OVER_TIME_TABLE_ID = "elections-over-time-table"
OVER_TIME_UNAVAILABLE_ID = "elections-over-time-unavailable"
OVER_TIME_NO_STATES_ID = "elections-over-time-no-states"
STATE_ID = "elections-state"
#: The state control's wrapper, hidden while N1 or N2 cannot be read.
STATE_CONTROL_ID = "elections-state-control"
#: C4 and C5's pair (#553, D102): C4 left, C5 right, their table full width below.
OVER_TIME_PAIR_ID = "elections-over-time-pair"
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

#: C4 and C5's top margin and the D077/D098 one-value rule, now in
#: :mod:`explore.over_time` (#560), under the names this page has always read them by.
_OVER_TIME_TOP_PX = over_time.TOP_PX
_same = over_time.same
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


def applied_search(chosen: Filters, first: int, last: int) -> str:
    """The filters a render applied, in the normal form :func:`merged_search` writes:
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
) -> tuple[dict[str, Any], bool]:
    """C2's figure (#434, D096, as amended by D104 for #558): election year along the
    bottom (:func:`explore.components.year_axis`), one point per served year at the
    leader's served ``ec_share_full``, against a dashed line at half of each election's
    electors appointed; and whether a marker is drawn.

    No point carries text: its hover writes the table's cells, the share among them. A
    share the table does not show as one is a marker at zero, never a dropped year, in
    a series of its own per label (:data:`explore.labels.C1_NO_SHARE` for a null or
    blank, else :data:`explore.labels.UNRECOGNIZED`), each with its own symbol and named
    in the chart's key. Every hover item is a string the page wrote.
    """
    years = [row["year"] for row in rows]
    xs: list[int] = []
    ys: list[float] = []
    hovers: list[str] = []
    marks: dict[str, list[tuple[int, str]]] = {}  # label -> [(year, hover)]
    for row, cell in zip(rows, cells, strict=True):
        shown = cell["ec_share_full"]
        number = labels.finite(row["ec_share_full"])
        hover = labels.C2_HOVER.format(
            year=str(row["year"]),
            candidate=charts.escaped(str(row["candidate"])),
            share=over_time.noted(shown),
            counted=cell["national_electoral_votes_counted"],
            appointed=cell["national_electoral_denominator"],
            majority=_majority(cell["ec_determinative"]),
        )
        # A finite value whose cell is no share (one whose percentage overflows reads
        # UNRECOGNIZED) is a marker too: the point stands only where the table shows it.
        if number is not None and shown != labels.UNRECOGNIZED:
            xs.append(row["year"])
            ys.append(number)
            hovers.append(hover)
        else:
            label = (
                labels.C1_NO_SHARE
                if shown == labels.NOT_IN_DATASET
                else labels.UNRECOGNIZED
            )
            marks.setdefault(label, []).append((row["year"], hover))
    data: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "markers",
            "name": labels.LABELS["ec_share_full"],
            "showlegend": False,
            "ids": [str(year) for year in xs],
            "x": xs,
            "y": ys,
            # A share near 100% sits at the plot's top edge: drawn whole, not clipped.
            "cliponaxis": False,
            "marker": {"symbol": "circle", "size": 7, "color": "var(--chart-1)"},
            "hovertext": hovers,
            "hovertemplate": "%{hovertext}<extra></extra>",
        }
    ]
    for label, symbol in _C2_SYMBOLS.items():
        if label in marks:
            years_, hovers_ = zip(*marks[label], strict=True)
            data.append(
                over_time.marker_trace(label, symbol, list(years_), list(hovers_))
            )
    layout: dict[str, Any] = {
        "title": {"text": labels.C2_TITLE},
        "height": _C2_HEIGHT_PX,
        "showlegend": bool(marks),
        "xaxis": components.year_axis(years),
        "yaxis": {
            "range": [0, 1],
            "tickformat": ".0%",
            "dtick": 0.25,
            "title": {"text": labels.C2_VALUE_AXIS},
        },
        "shapes": [
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": 0.5,
                "y1": 0.5,
                "layer": "below",
                "line": {
                    "dash": "dash",
                    "width": 2,
                    "color": "var(--chart-reference)",
                },
            }
        ],
        # The line's label just below it at the right (owner, #558's plan gate): the
        # leaders' shares sit above the line there, and the low ones are at the left.
        # Shifted down by more than a marker's radius, so a point just above the line
        # (2000's 50.4%) stays clear of it.
        "annotations": [
            {
                "text": labels.C2_MAJORITY_LINE,
                "xref": "paper",
                "x": 1,
                "xanchor": "right",
                "yref": "y",
                "y": 0.5,
                "yanchor": "top",
                "yshift": -_C2_LINE_LABEL_SHIFT_PX,
                "align": "right",
                "showarrow": False,
                "font": {"color": "var(--text)", "size": 12},
            }
        ],
    }
    if marks:
        layout["legend"] = components.TIME_SERIES_LEGEND
    return {"data": data, "layout": layout}, bool(marks)


def _c2_caption(marked: bool) -> str:
    """C2's caption: which candidate each point is, what the share counts, what the
    line marks, that the leader did not always take office and, where a marker is
    drawn (``marked``), what it means. It names no served text (D095(a));
    ``components.chart`` adds the table pointer."""
    parts = [
        labels.C2_LEADER_POINT,
        labels.C1_EC_BASIS,
        labels.C2_MAJORITY_NOTE,
        labels.C2_TOOK_OFFICE,
    ]
    if marked:
        parts.append(labels.C2_NO_SHARE_NOTE)
    return " ".join(parts)


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
        figure, marked = _c2_figure(rows, cells)
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
        components.chart(C2_ID, figure, LEADER_TABLE_ID, _c2_caption(marked)),
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
    :data:`explore.query.USPS_RE` refuses, a name that is not text with something in
    it (:func:`explore.labels.has_text`), two rows for one year and state, two names
    for one code, or a gap: a served year after a state's first with no row for it.
    Every row must carry ``state_electoral_votes``, ``state_popular_total`` and
    ``pv_status`` (``KeyError``), so the result does not depend on the state chosen.
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
        # Present on every row, whichever state is chosen, so a malformed N2 refuses
        # here (the all-states view stays) and never in the one-state build (#436's
        # review). Their values are worded by ``labels``, which reads an unknown one as
        # unrecognized.
        for field in ("state_electoral_votes", "state_popular_total", "pv_status"):
            row[field]
        name = row["state"]
        # A name failing ``labels.has_text`` refuses N2 (the all-states view stays)
        # rather than reaching the state control as "None", a blank option or a number
        # (#498, owner; D101). The API's ``ElectionStateRow.state`` is ``str``, so a
        # null or non-text name is an upstream fault; a blank one, which that type
        # admits, has nothing to show.
        if not labels.has_text(name):
            raise TypeError(f"{api.ELECTION_STATES_PATH} names {usps} with no text")
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


def _state_points(
    rows: list[dict[str, Any]], coverage: dict[str, Any]
) -> list[over_time.Point]:
    """One state: its N2 rows, from its first election, worded once."""
    points = []
    for row in rows:
        year = election_view.row_year(row)
        if year is None:
            raise TypeError(f"{api.ELECTION_STATES_PATH} names a year that is not one")
        status = row["pv_status"]
        points.append(
            over_time.Point(
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
    state: str | None,
    window: tuple[int, int],
) -> over_time.OverTime:
    """C5's figure (#436, D100): the total popular vote of each row with one, as a bar
    at its year. The years before and after the popular-vote window (``window``, read
    from ``coverage``) are a shaded band, labeled above the plot, which alone marks a
    held popular vote outside it; every other row with nothing to draw is a marker, one
    series per label (:data:`explore.labels.C5_MARKER_LABELS`), named in the chart's
    key (#558, D104), wherever it falls, inside the band included. ``state`` is the
    escaped state name, or ``None``."""
    pv_min, pv_max = window
    banded = {
        labels.NOT_APPLICABLE,
        labels.AFTER_WINDOW,
        labels.BEFORE_WINDOW.format(pv_year_min=pv_min),
    }
    drawn: list[tuple[over_time.Point, int, str, str]] = []
    marks: dict[str, list[tuple[over_time.Point, str]]] = {}
    for point in points:
        hover = over_time.point_hover(point, state, total=True)
        value = over_time.figure_value(point.total, zero=True)
        if value is not None and point.total_cell == labels.number(value):
            drawn.append((point, value, point.total_cell, hover))
            continue
        outside = not pv_min <= point.year <= pv_max
        if outside and point.total_cell in banded:
            continue
        label = labels.C5_MARKER_LABELS.get(point.total_cell, labels.UNRECOGNIZED)
        marks.setdefault(label, []).append((point, hover))
    name = labels.LABELS[
        "national_pv_denominator" if state is None else "state_popular_total"
    ]
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
        layout["margin"] = {"t": _OVER_TIME_TOP_PX + _BAND_LABEL_PX * len(annotations)}
    return over_time.OverTime(
        {"data": data, "layout": layout}, False, bool(marks), bool(before), bool(after)
    )


def _c4_caption(
    c4: over_time.OverTime, all_states: bool, state: str | None, first: int | None
) -> str:
    """C4's caption: what electors appointed is, what a bar adds up with all states
    (``all_states``), what each marker means where one is drawn, and a state's first
    election where it comes after the dataset's first. Names a served state only in
    plain text (``state`` is the plain name or ``None``); ``components.chart`` adds the
    table pointer."""
    parts = [labels.C4_BASIS]
    if all_states:
        parts.append(labels.C4_ALL_STATES)
    if c4.zeros:
        parts.append(labels.C4_ZERO_NOTE)
    if c4.missing:
        parts.append(labels.C4_NO_FIGURE_NOTE)
    return " ".join(parts + _first_note(state, first))


def _c5_caption(
    c5: over_time.OverTime,
    all_states: bool,
    state: str | None,
    first: int | None,
    window: tuple[int, int],
) -> str:
    """C5's caption: what the total counts, what a bar adds up with all states, what
    the band and the markers mean where drawn, and a state's first election."""
    parts = [labels.C5_BASIS]
    if all_states:
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
    options = components.label_sorted_options(
        {usps: str(rows[0]["state"]) for usps, rows in (series or {}).items()}
    )
    value = chosen if any(option["value"] == chosen for option in options) else None
    hidden: dict[str, Any] = (
        {} if series is not None else {"style": {"display": "none"}}
    )
    return html.Div(
        [
            components.dropdown_filter(
                STATE_ID, labels.LABELS[STATE], options, value, ALL_STATES
            )
        ],
        className="filters filter-row",
        id=STATE_CONTROL_ID,
        **hidden,
    )


def _over_time_row(point: over_time.Point, row: dict[str, Any]) -> html.Tr:
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
                # The one-state download reads N2's provenance; check it here, by the
                # function that reads it, so a malformed one falls back to all states.
                export.preamble(
                    (*OVER_TIME_STATE_FIELDS, *OVER_TIME_STATE_EXTRA),
                    state_provenance,
                    "",
                )
            except (KeyError, TypeError):
                series = None
        chosen = chosen_state(pairs, series)
        all_states = chosen is None or series is None
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
        plain = over_time.plain(name)
        state = None if chosen is None else charts.escaped(str(name))
        if chosen is None:
            c4_title, c5_title = labels.C4_TITLE, labels.C5_TITLE
        elif plain is None:
            c4_title, c5_title = labels.C4_TITLE_SELECTED, labels.C5_TITLE_SELECTED
        else:
            c4_title = labels.C4_TITLE_STATE.format(state=plain)
            c5_title = labels.C5_TITLE_STATE.format(state=plain)
        c4 = over_time.c4_figure(points, years, c4_title, state)
        c5 = _c5_figure(points, years, c5_title, state, window)
        # The pair's plots line up (#553's pair, #558): C4 leaves room for C5's band
        # labels.
        c4.figure["layout"]["margin"] = dict(c5.figure["layout"]["margin"])
        c4_caption = _c4_caption(c4, all_states, plain, first)
        c5_caption = _c5_caption(c5, all_states, plain, first, window)
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
        components.pair(
            [components.chart(C4_ID, c4.figure, OVER_TIME_TABLE_ID, c4_caption)],
            [components.chart(C5_ID, c5.figure, OVER_TIME_TABLE_ID, c5_caption)],
            OVER_TIME_PAIR_ID,
        ),
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
            # Source order is reading order at every width: the filters are the pair's
            # left column and the count and averages they narrow its right, which is
            # METRICS_ID itself, so the pair's margin reset reaches the count (#553).
            components.pair(
                [controls],
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
                LIST_PAIR_ID,
                right_id=METRICS_ID,
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
            labels.glossary(FIELDS, ident=GLOSSARY_ID),
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
