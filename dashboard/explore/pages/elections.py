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
"""

from __future__ import annotations

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
    metrics,
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

#: T1's columns, in display order, by public field name.
FIELDS = ("year", "candidate_count", "has_popular_vote")

#: Page-level wording (ba spec, approved by the owner at #434's plan gate, 2026-11-11).
LEDE = "Every US presidential election in this dataset."
#: Shown only on success, after :data:`LEDE` (the degraded page has no filters).
FILTER_SENTENCE = (
    "Narrow the list of elections by year, or to the years with a popular vote in "
    "this dataset."
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
                    *components.table(
                        shown,
                        _row,
                        FIELDS,
                        TABLE_ID,
                        download,
                        notes=(labels.HAS_POPULAR_VOTE_NOTE,),
                        empty=labels.NO_ELECTIONS_MATCH,
                    ),
                    labels.glossary(FIELDS, ident=GLOSSARY_ID),
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
