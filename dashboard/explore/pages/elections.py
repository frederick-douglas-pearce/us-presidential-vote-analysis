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
- **Charts C2, C4 and C5** have their own pages since #562 (D107):
  ``pages/elections_majority.py`` and ``pages/elections_over_time.py``. An old
  ``?state=`` link, which C4 and C5 read before, answers 302 to the state's page
  (``moved_to_path``), where chart C7 draws its electors appointed.
- **The headline metrics** (#437, D097) sit between the filters and T1: the count of
  elections shown, then the average electoral and popular-vote margins over them, each
  with its own N and years, computed by :mod:`explore.metrics` from T1's own shown rows
  and N1's ``elections`` items (:func:`explore.elections_view.n1_items`, the one check
  C2 shares), N1 (:data:`explore.api.SUMMARY_PATH`) filled on a miss. A failed or
  malformed N1 replaces the averages with :data:`METRICS_UNAVAILABLE`; the count stays.
- **T1's N1 columns and chart C9** (#563, D116): T1 appends the two #570 fields, the
  electoral and popular-vote margins (the election panel's one cell function,
  :func:`explore.election_view.margin_cells`) and, last and on the page only, who
  received electoral votes (:data:`RECIPIENTS_HEADER`), from N1's ``elections`` items
  and ``data`` rows. Chart C9 draws each shown year's served ``candidate_count`` above
  T1, its hover the year's Recipients cell, and narrows with T1 (D110). Two tiers
  (D116(e)): N1 unread, its items failing their check, the popular-vote window's
  bounds failing ``query.year_span``, or a served year's item lacking a field T1's
  cells read empties every N1 cell (:data:`T1_N1_UNAVAILABLE_CELL`) and C9; a
  recipient row check or the
  reconciliation with ``candidate_count`` failing in any served year empties the
  Recipients cells and C9 only. Both are checked over every served year before the
  filters apply (:func:`_n1_rows`).
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
    metrics,
    over_time,
    query,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in the table.
PAGE_ID = "elections"
TABLE_ID = "elections-table"
#: The filter controls' ids, shared with the two chart pages (#596, D110).
YEARS_ID = elections_view.YEARS_ID
PV_ID = elections_view.PV_ID
URL_ID = elections_view.URL_ID
#: T1's column-name list, by an id of its own (the page had three from #436 to #562;
#: the id stays, since the e2e tests name it).
GLOSSARY_ID = "elections-glossary"
#: The list's pair (#553, D102): its filters left, the count and averages right.
LIST_PAIR_ID = "elections-list-pair"

#: T1's columns, in display order, by public field name: the index's three, then N1's
#: four (#563), each from the year's ``elections`` item.
INDEX_FIELDS = ("year", "candidate_count", "has_popular_vote")
N1_FIELDS = (
    "electoral_votes_outside_top_two",
    "electors_without_a_counted_vote",
    "ec_margin",
    "pv_margin",
)
FIELDS = (*INDEX_FIELDS, *N1_FIELDS)
#: T1's page-only column (#563, D116): its header and the served fields its cells are
#: built from (the header's tooltip and the column-name list's entry). Not a ``LABELS``
#: key, and never in T1's download.
RECIPIENTS_HEADER = "Who received electoral votes (cast, counted)"
RECIPIENTS_FIELDS = (
    "candidate, national_electoral_votes, national_electoral_votes_counted"
)
PAGE_ONLY = ((RECIPIENTS_HEADER, RECIPIENTS_FIELDS),)

#: Page-level wording (ba spec, approved by the owner at #434's plan gate, 2026-11-11).
LEDE = "Every US presidential election in this dataset."
#: Shown only on success, after :data:`LEDE` (the degraded page has no filters).
FILTER_SENTENCE = (
    "Narrow the chart and the list of elections by year, or to the years with a "
    "popular vote in this dataset."
)
LIST_HEADING = "List of elections"

#: The headline metrics (#437, D097): the block, its count line and each average's
#: value, by metric key; DOM ids are stable and never renamed.
METRICS_ID = "elections-metrics"
METRICS_UNAVAILABLE_ID = "elections-metrics-unavailable"
METRIC_IDS = {
    "elections_shown": "elections-shown",
    "ec_margin_mean": "elections-ec-margin-mean",
    "pv_margin_mean": "elections-pv-margin-mean",
}
#: The averages, in the order they show: the page's means, read off ``METRIC_IDS``
#: by kind (#600's cr.9: ``METRIC_IDS`` is each page's one per-key table).
MEANS = tuple(key for key in METRIC_IDS if metrics.METRICS[key].kind == "mean")
#: The averages when N1 cannot be read or is malformed; the count still shows (ba spec,
#: #437). Never ``UNAVAILABLE_MESSAGE``'s wording: the D070(b) guard's success run
#: asserts that absent from every page.
METRICS_UNAVAILABLE = (
    "The average margins can't be shown right now. Please try again in a minute."
)

#: T1's notes (ba spec, approved at #563's plan gate, 2026-11-22), shown under T1 and
#: written into its download.
RECIPIENTS_DOWNLOAD_NOTE = (
    'The download leaves out the "Who received electoral votes" column. Each '
    "election's own page lists them, with their electoral votes cast and counted, in "
    "its national results table and that table's download."
)
OUTSIDE_TOP_TWO_NOTE = (
    "Electoral votes cast outside the top two are the votes cast for candidates ranked "
    "below second by electoral votes counted. Candidates with equal counted totals "
    "share a rank. A candidate whose votes were cast but not counted ranks below "
    "second and still adds to it: in 1872, Horace Greeley's 3."
)
NO_COUNTED_VOTE_NOTE = (
    "Electors without a counted vote are electors appointed whose vote is not in "
    "Congress's count: either the elector did not vote, or the vote was cast and not "
    "counted. In 2000, one elector from the District of Columbia did not vote."
)
#: Each N1 cell, and the note first among T1's, when N1 cannot be read (tier 1); in a
#: recipient-row fault (tier 2) only the Recipients cells read the cell, with no note.
T1_N1_UNAVAILABLE_CELL = "Not available right now"
T1_N1_UNAVAILABLE_NOTE = (
    "Some columns can't be shown right now: electoral votes cast outside the top two, "
    "electors without a counted vote, the electoral and popular-vote margins, and who "
    "received electoral votes. In the download, the first four of these have empty "
    "cells because they could not be read right now, not because the dataset holds no "
    "value there. Please try again in a minute."
)
#: Chart C9 (#563): its registry id, and its unavailable note's DOM id.
C9_ID = "C9"
C9_UNAVAILABLE_ID = "elections-c9-unavailable"

#: The query keys and the one parser, shared with the two chart pages (#596, D110):
#: :func:`explore.elections_view.parse_filters`.
YEAR_FROM = elections_view.YEAR_FROM
YEAR_TO = elections_view.YEAR_TO
PV = elections_view.PV
#: The key C4 and C5 read before #562, whose value now names a state's page, where
#: chart C7 draws its electors appointed: an old link answers 302 there (D107).
STATE = election_view.STATE
parse_filters = elections_view.parse_filters


dash.register_page(
    __name__,
    path=elections_view.LIST,
    title=f"Elections — {SITE_TITLE}",
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description="Every US presidential election in the dataset, filterable by year.",
    prefetch=(api.ELECTIONS_PATH,),
    # N1, filled on first use for the averages (#437): a literal (D074(ii)), never
    # prefetched.
    on_miss=(api.SUMMARY_PATH,),
    success=PAGE_ID,
    query=parse_filters,
    # An old link's state, which C4 and C5 read before #562, names the state's page
    # (D107): a 302 there only for a state its own validate accepts.
    moved_to_path=(STATE, "/state/<usps>"),
    # The site navigation link this page marks (#448):
    # the elections index marks its own link.
    nav="elections",
)


#: The filter helpers and the one filter callback live in :mod:`explore.elections_view`
#: since #596 (D110), which all three elections pages share.
Filters = elections_view.Filters
span = elections_view.span
filters = elections_view.filters
applied_search = elections_view.applied_search
CONTROL_KEYS = elections_view.CONTROL_KEYS
merged_search = elections_view.merged_search
next_search = elections_view.next_search


class N1Cells(NamedTuple):
    """T1's N1 cells for one row (#563), built once per row per render and read by its
    ``Tr`` and, for the Recipients lines, C9's hover: each N1 field's cell by field,
    and the Recipients lines (one per recipient, served order), or ``None`` where they
    are unavailable."""

    fields: dict[str, str]
    recipients: tuple[str, ...] | None


#: Every N1 cell when N1 cannot be read (tier 1).
UNAVAILABLE_CELLS = N1Cells(dict.fromkeys(N1_FIELDS, T1_N1_UNAVAILABLE_CELL), None)


def recipient_lines(recipients: list[elections_view.Recipient]) -> tuple[str, ...]:
    """A year's Recipients cell, one line per recipient in served order
    (:data:`explore.labels.RECIPIENT_LINE`), as the page writes it: C9's hover escapes
    each line."""
    return tuple(
        labels.RECIPIENT_LINE.format(
            candidate=r.candidate,
            cast=labels.number(r.cast),
            counted=labels.number(r.counted),
        )
        for r in recipients
    )


def _row(election: dict[str, Any], cells: N1Cells) -> html.Tr:
    year = election["year"]
    lines = cells.recipients
    return html.Tr(
        [
            # A year links to its one-election view (#307).
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            labels.cell(labels.number(election["candidate_count"])),
            labels.cell(labels.has_popular_vote(election["has_popular_vote"])),
            *(labels.cell(cells.fields[field]) for field in N1_FIELDS),
            # The page-only column, last (D116): one line per recipient.
            html.Td(
                T1_N1_UNAVAILABLE_CELL
                if lines is None
                else [
                    part
                    for i, line in enumerate(lines)
                    for part in ((html.Br(),) if i else ()) + (line,)
                ]
            ),
        ]
    )


def _n1_rows(
    index: dict[str, Any], summary: Any, shown: list[Any]
) -> tuple[
    list[dict[str, Any]], list[N1Cells], dict[int, tuple[str, ...]] | None, bool
]:
    """T1's shown rows with N1's four fields joined on (``None`` each where N1 cannot be
    read, so the download's cells are empty and it never raises), each row's
    :class:`N1Cells`, each served year's Recipients lines (``None`` where C9 cannot be
    drawn), and whether N1 could not be read at all (tier 1), from the check itself,
    never from a cell (#563, D116(e)).

    Tier 1 is N1 unread, :func:`explore.elections_view.n1_items` failing, the index's
    popular-vote window's bounds failing :func:`explore.query.year_span` (a missing
    bound is the page's: T1's download preamble reads it), or any served year's
    item lacking a field T1's cells or :func:`explore.election_view.margin_cells` read.
    Every one of those reads is done here, for every served year before the filters
    apply, inside the ``try``; tier 2 is :func:`explore.elections_view.n1_recipients`
    failing. An index defect is the page's, raised before this is called."""
    coverage = index["meta"]["provenance"]["coverage"]
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
        items = elections_view.n1_items(index, summary)
        by_year = {
            year: (
                {field: item[field] for field in N1_FIELDS},
                {
                    "electoral_votes_outside_top_two": labels.number(
                        item["electoral_votes_outside_top_two"]
                    ),
                    "electors_without_a_counted_vote": labels.number(
                        item["electors_without_a_counted_vote"]
                    ),
                    **{
                        field: cell
                        for field, cell in election_view.margin_cells(
                            item, year, coverage
                        ).items()
                        if field in N1_FIELDS
                    },
                },
            )
            for year, item in items.items()
        }
    except (KeyError, TypeError):
        rows = [{**e, **dict.fromkeys(N1_FIELDS)} for e in shown]
        return rows, [UNAVAILABLE_CELLS] * len(rows), None, True
    try:
        lines: dict[int, tuple[str, ...]] | None = {
            year: recipient_lines(found)
            for year, found in elections_view.n1_recipients(index, summary).items()
        }
    except (KeyError, TypeError):
        lines = None
    rows, cells = [], []
    for election in shown:
        year = _shown_year(election)
        values, worded = by_year[year]
        rows.append({**election, **values})
        cells.append(N1Cells(worded, None if lines is None else lines[year]))
    return rows, cells, lines, False


def _c9_caption(counts: dict[int, int]) -> str:
    """C9's caption (ba spec): what a bar is, the cast-not-counted note, the finding
    over the years shown and the hover note; ``components.chart`` adds the pointer."""
    parts = [labels.C9_BASIS, labels.C9_CAST_NOTE]
    if len(counts) == 1:
        ((year, count),) = counts.items()
        parts.append(
            labels.C9_FINDING_ONE.format(year=year, count=labels.number(count))
        )
    else:
        more = sum(1 for count in counts.values() if count > 2)
        n = labels.number(len(counts))
        if more:
            most = max(counts.values())
            parts.append(
                labels.C9_FINDING.format(
                    more=labels.number(more),
                    n=n,
                    most=labels.number(most),
                    years=labels.metric_years(
                        sorted(year for year, count in counts.items() if count == most)
                    ),
                )
            )
        else:
            parts.append(labels.C9_FINDING_NONE.format(n=n))
    parts.append(labels.C9_HOVER_NOTE)
    return " ".join(parts)


def _c9_figure(
    counts: dict[int, int], lines: dict[int, tuple[str, ...]]
) -> dict[str, Any]:
    """C9's figure (#563, D116): one bar per distinct year shown, at its year on the
    year axis (D104), its height the served ``candidate_count`` (already reconciled
    with N1's rows, so a figure), no bar text (D104(c)), and a hover writing the year,
    T1's count cell and the year's Recipients lines, escaped (D091)."""
    years = sorted(counts)
    hovers = [
        labels.C9_HOVER.format(
            year=year,
            count=labels.number(counts[year]),
            recipients="<br>".join(charts.escaped(line) for line in lines[year]),
        )
        for year in years
    ]
    bars = {
        "type": "bar",
        "name": labels.LABELS["candidate_count"],
        "showlegend": False,
        "ids": [str(year) for year in years],
        "x": years,
        "y": [counts[year] for year in years],
        "marker": {"color": charts.EC_COLOR},
        "hovertext": hovers,
        "hovertemplate": "%{hovertext}<extra></extra>",
    }
    layout = over_time.time_layout(
        labels.C9_TITLE,
        labels.C9_VALUE_AXIS,
        years,
        max(counts.values()),
        marked=False,
    )
    return {"data": [bars], "layout": layout}


def _c9(
    shown: list[Any], lines: dict[int, tuple[str, ...]] | None
) -> list[Any]:
    """C9 over the years T1 shows (D110), or :data:`explore.labels.C9_UNAVAILABLE`
    where N1's rows could not be read or reconciled; nothing when no year is shown,
    where T1's empty note stands. ``components.chart`` sits outside the ``try``
    (D095(f))."""
    if not shown:
        return []
    try:
        if lines is None:
            raise TypeError("C9's rows are unavailable")
        counts = {_shown_year(e): e["candidate_count"] for e in shown}
        figure = _c9_figure(counts, lines)
        caption = _c9_caption(counts)
    except (KeyError, TypeError):
        return [html.P(labels.C9_UNAVAILABLE, id=C9_UNAVAILABLE_ID, className="note")]
    return [components.chart(C9_ID, figure, TABLE_ID, caption)]


def _shown_year(row: Any) -> int:
    """A shown T1 row's year, checked (:func:`explore.elections_view.n1_items` already
    refused a bad one)."""
    year = election_view.row_year(row)
    if year is None:
        raise TypeError("/v1/elections names a year that is not one")
    return year


def _averages(
    index: dict[str, Any], summary: Any, shown: list[Any], pv_only: bool
) -> list[Any]:
    """The two average margins over the elections T1 shows (#437, D097), as a ``dl``
    and its notes, or :data:`METRICS_UNAVAILABLE` alone when N1 could not be read
    (``summary`` is ``None``), its ``elections`` items fail
    :func:`explore.elections_view.n1_items`, an item
    lacks a margin field, or the index's popular-vote window is malformed.

    Each year shown counts once, however often the index lists it (#334). Each mean
    reads the field ``metrics.METRICS`` names, so that table drives what is averaged.
    """
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        items = elections_view.n1_items(index, summary)
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
    entries: list[Any] = []
    for key in MEANS:
        window = pv_window if metrics.METRICS[key].reads_pv_window else None
        value, over = labels.metric_mean(means[key], years, window)
        entries += components.metric_entry(key, METRIC_IDS[key], value, over)
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
    body: dict[str, Any],
    pairs: list[tuple[str, str]],
    summary: Any = None,
) -> html.Div:
    """The whole page for one ``/v1/elections`` response, this page's filter pairs and
    N1's body (``None`` when it could not be read): the heading and lede, then the list
    of elections with its headline metrics. The year and popular-vote filters narrow
    T1 and the metrics computed from it."""
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
        if elections_view.shows(e["year"], e["has_popular_vote"], chosen)
    ]
    rows, cells, lines, unread = _n1_rows(body, summary, shown)
    notes: tuple[str, ...] = (
        labels.HAS_POPULAR_VOTE_NOTE,
        RECIPIENTS_DOWNLOAD_NOTE,
        OUTSIDE_TOP_TWO_NOTE,
        NO_COUNTED_VOTE_NOTE,
        labels.MARGIN_NOTE,
    )
    if unread:
        notes = (T1_N1_UNAVAILABLE_NOTE, *notes)
    # Keyed by identity: ``rows`` holds every dict for the whole render, and
    # ``components.table`` passes each one to ``_row`` as given.
    by_row = {id(r): c for r, c in zip(rows, cells, strict=True)}
    first, last = span(coverage)
    search = applied_search(chosen, first, last)
    controls = elections_view.filter_controls(first, last, chosen)
    download = export.Download(
        filename="elections.csv",
        name="the elections",
        provenance=provenance,
        view_url=export.view_url(
            CANONICAL_HOST, elections_view.LIST, search
        ),
    )
    return html.Div(
        [
            html.H1("Elections"),
            html.P(f"{LEDE} {FILTER_SENTENCE}", className="lede"),
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            elections_view.section_nav(elections_view.LIST, search),
            # The list's one section in one card (#567, D111): its filters, count and
            # averages (the pair) and T1 below them.
            components.card(
                [
                    html.H2(LIST_HEADING),
                    # Source order is reading order at every width: the filters are
                    # the pair's left column and the count and averages they narrow
                    # its right, which is METRICS_ID itself, so the pair's margin
                    # reset reaches the count (#553).
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
                    # C9 below the pair, full width, above its companion T1 (#563).
                    *_c9(shown, lines),
                    *components.table(
                        rows,
                        lambda r: _row(r, by_row[id(r)]),
                        FIELDS,
                        TABLE_ID,
                        download,
                        notes=notes,
                        empty=labels.NO_ELECTIONS_MATCH,
                        page_only=PAGE_ONLY,
                    ),
                    labels.glossary(FIELDS, ident=GLOSSARY_ID, page_only=PAGE_ONLY),
                ]
            ),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(**query: Any) -> html.Div:
    """The elections index. On success, :func:`render`'s body is the whole page; the
    degraded state gets the heading and :data:`LEDE` here. N1 is read in the same view,
    after the index, in its own ``try``: a failed N1 degrades only the averages."""
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
