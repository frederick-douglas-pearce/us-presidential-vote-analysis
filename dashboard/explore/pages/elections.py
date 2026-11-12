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
"""

from __future__ import annotations

import functools
from typing import Any, NamedTuple

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

#: The query keys this page reads. ``year_from`` and ``year_to`` are the API's own names
#: for a year range, so later tables with a year range share them.
YEAR_FROM = query.YEAR_FROM
YEAR_TO = query.YEAR_TO
PV = "pv"


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``,
    before any data is read. Keeps ``year_from`` / ``year_to`` only as four ASCII digits
    and ``pv`` only as ``"1"``; a key repeated with differing values is dropped, and so
    is a key it does not know. A range whose start is after its end drops both bounds.
    Whether a year lies inside the served span is the layout's question
    (:func:`filters`).
    """
    if not isinstance(params, dict):
        return []
    kept = query.parse_year_range(params)
    if query.single(params.get(PV)) == "1":
        kept[PV] = "1"
    return sorted(kept.items())


dash.register_page(
    __name__,
    path="/elections",
    title=f"Elections — {SITE_TITLE}",
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description="Every US presidential election in the dataset, filterable by year.",
    prefetch=(api.ELECTIONS_PATH,),
    # N1, filled on first use for C2 (#434): a literal (D074(ii)), never prefetched.
    on_miss=(api.SUMMARY_PATH,),
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


@callback(
    Output(URL_ID, "search"),
    Input(YEARS_ID, "value"),
    Input(PV_ID, "value"),
    State(YEARS_ID, "min"),
    State(YEARS_ID, "max"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(years: Any, pv: Any, first: Any, last: Any, current: Any) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. Writing the search the URL already has would navigate for nothing,
    so an unchanged one is left alone.
    """
    search = search_for(years, pv, first, last)
    return no_update if search == (current or "") else search


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
    the one check of those items, shared by C2 (:func:`leaders`) and the averages
    (#437, D097), so an item both read is accepted or refused by both alike (C2 adds its
    own rank-1 rule, :func:`leaders`).

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


def render(
    body: dict[str, Any], pairs: list[tuple[str, str]], summary: Any = None
) -> html.Div:
    """The whole page for one ``/v1/elections`` response, this page's filter pairs and
    N1's body (``None`` when it could not be read): the heading and lede, C2's section,
    then the list of elections with its headline metrics. The filters narrow T1 and the
    metrics computed from it only."""
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
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(**query: Any) -> html.Div:
    """The elections index. On success, :func:`render`'s body is the whole page; the
    degraded state gets the heading and :data:`LEDE` here. N1 is read in the same view,
    after the index, in its own ``try``: a failed read degrades only C2's section."""
    try:
        with api.CLIENT.view() as view:
            body = view.get(api.ELECTIONS_PATH)
            try:
                summary = view.get(api.SUMMARY_PATH)
            except api.ApiUnavailable:
                summary = None
        return render(body, parse_filters(query), summary)
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div([html.H1("Elections"), html.P(LEDE, className="lede"), content])
