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
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in the table.
PAGE_ID = "elections"
TABLE_ID = "elections-table"
YEARS_ID = "elections-years"
PV_ID = "elections-pv"
URL_ID = "elections-url"

#: T1's columns, in display order, by public field name.
FIELDS = ("year", "candidate_count", "has_popular_vote")

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
    on_miss=(),
    success=PAGE_ID,
    query=parse_filters,
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
            html.Td(str(election["candidate_count"])),
            html.Td(labels.has_popular_vote(election["has_popular_vote"])),
        ]
    )


def render(body: dict[str, Any], pairs: list[tuple[str, str]]) -> html.Div:
    """The page body for one ``/v1/elections`` response and this page's filter pairs."""
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
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            controls,
            html.P(
                f"Showing {len(shown)} of {len(elections)} elections",
                className="count",
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
    try:
        with api.CLIENT.view() as view:
            body = view.get(api.ELECTIONS_PATH)
        content = render(body, parse_filters(query))
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1("Elections"),
            html.P(
                "Every US presidential election in this dataset. Narrow the list by "
                "year, or to the years with a popular vote in this dataset.",
                className="lede",
            ),
            content,
        ]
    )
