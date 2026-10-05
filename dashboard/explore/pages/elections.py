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
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple
from urllib.parse import quote, urlencode

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, labels
from explore.config import SITE_TITLE

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
YEAR_FROM = "year_from"
YEAR_TO = "year_to"
PV = "pv"

_YEAR_RE = re.compile(r"[0-9]{4}")  # ASCII only: \d and int() accept other digits


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
    kept: dict[str, str] = {}
    for key in (YEAR_FROM, YEAR_TO):
        value = _single(params.get(key))
        if value is not None and _YEAR_RE.fullmatch(value):
            kept[key] = value
    if _single(params.get(PV)) == "1":
        kept[PV] = "1"
    if YEAR_FROM in kept and YEAR_TO in kept and kept[YEAR_FROM] > kept[YEAR_TO]:
        del kept[YEAR_FROM], kept[YEAR_TO]
    return sorted(kept.items())


def _single(value: Any) -> str | None:
    """A query value, if it is one string or the same string repeated."""
    values = value if isinstance(value, list) else [value]
    if not values or any(v != values[0] for v in values):
        return None
    return values[0] if isinstance(values[0], str) else None


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


def _coverage_year(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"coverage year is not an integer: {value!r}")
    return value


def filters(pairs: list[tuple[str, str]], coverage: dict[str, Any]) -> Filters:
    """The filters to apply; a bound outside the served span falls back to its default.

    Fallback is per parameter, as ``og:url`` keeps the valid parameters and drops the
    rest. The result is never inverted: :func:`parse_filters` already dropped an
    inverted pair, and a bound replaced by its default cannot pass the other bound.
    """
    first = _coverage_year(coverage["year_min"])
    last = _coverage_year(coverage["year_max"])
    given = dict(pairs)
    year_from = int(given.get(YEAR_FROM, first))
    year_to = int(given.get(YEAR_TO, last))
    return Filters(
        year_from=year_from if first <= year_from <= last else first,
        year_to=year_to if first <= year_to <= last else last,
        pv_only=given.get(PV) == "1",
    )


def _as_year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value if isinstance(value, int) else None


def search_for(years: Any, pv: Any, first: Any, last: Any) -> str:
    """The query string for the controls' values, in the normal form ``og:url`` uses.

    Defaults are omitted, the pairs pass through :func:`parse_filters`, and the result
    is ``""`` or starts with ``?`` (a ``dcc.Location`` joins pathname and search
    verbatim).
    """
    params: dict[str, str] = {}
    if isinstance(years, list) and len(years) == 2:
        low, high = (_as_year(v) for v in years)
        if low is not None and low != first:
            params[YEAR_FROM] = str(low)
        if high is not None and high != last:
            params[YEAR_TO] = str(high)
    if isinstance(pv, list) and "1" in pv:
        params[PV] = "1"
    pairs = parse_filters(params)
    return "?" + urlencode(pairs, quote_via=quote) if pairs else ""


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


#: Years between slider labels; an interior label nearer an end than half of this is
#: dropped, so the end labels never run into it on a phone.
MARK_STEP = 40


def _marks(first: int, last: int) -> dict[int, str]:
    interior = range((first // MARK_STEP + 1) * MARK_STEP, last, MARK_STEP)
    keep = [y for y in interior if min(y - first, last - y) >= MARK_STEP // 2]
    return {year: str(year) for year in sorted({first, last, *keep})}


def _row(election: dict[str, Any]) -> html.Tr:
    return html.Tr(
        [
            html.Td(str(election["year"])),
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
    shown = [
        e
        for e in elections
        if chosen.year_from <= e["year"] <= chosen.year_to
        and (e["has_popular_vote"] is True or not chosen.pv_only)
    ]
    first, last = coverage["year_min"], coverage["year_max"]
    controls = html.Div(
        [
            html.Label("Years", htmlFor=YEARS_ID, className="label"),
            dcc.RangeSlider(
                id=YEARS_ID,
                min=first,
                max=last,
                step=1,
                value=[chosen.year_from, chosen.year_to],
                allowCross=False,
                allow_direct_input=False,
                marks=_marks(first, last),
                tooltip={"placement": "bottom"},
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
    table = html.Table(
        [
            html.Thead(html.Tr([labels.header(field) for field in FIELDS])),
            html.Tbody([_row(e) for e in shown]),
        ],
        id=TABLE_ID,
    )
    return html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            controls,
            html.P(
                f"Showing {len(shown)} of {len(elections)} elections",
                className="count",
            ),
            table
            if shown
            else html.P("No elections match these filters.", className="empty"),
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
