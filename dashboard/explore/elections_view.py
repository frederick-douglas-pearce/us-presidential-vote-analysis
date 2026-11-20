"""The elections pages' shared pieces (#562).

The elections have three pages: the list of elections at ``/elections`` (``pages/
elections.py``), the Electoral College majority at ``/elections/majority`` (``pages/
elections_majority.py``, chart C2) and the electors appointed and total popular vote at
``/elections/over-time`` (``pages/elections_over_time.py``, charts C4 and C5). A page
module cannot import another (Dash executes it before it is in ``sys.modules``), so
what they share lives here: the section paths, the section links, the check of N1's
``elections`` items, which all three read, and the year filters (#596, D110): the one
query parser, the controls, the empty note and the one filter callback.

A shared module, like ``election_view``: pure functions of what a page already read,
importing nothing from ``explore`` but the other shared modules, never ``api`` or
``config`` (``TestSharedPieces``). One exception to "pure functions": it registers the
one filter callback, :func:`on_filter_change`, which serves all three pages, since they
render the same three control ids (#596's architect review: a page module would make
the other pages work only because it was imported). Its reader-facing words are in
:mod:`explore.labels`; this module is structure only.
"""

from __future__ import annotations

from typing import Any, NamedTuple
from urllib.parse import parse_qs

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import components, election_view, labels, query

#: The three pages' paths, in page order (#562): the one source for each page's
#: registration, its download's view URL and the section links.
LIST = "/elections"
MAJORITY = "/elections/majority"
OVER_TIME = "/elections/over-time"
SECTIONS = (LIST, MAJORITY, OVER_TIME)
SECTION_TEXT = {
    LIST: labels.SECTION_ELECTIONS_LIST,
    MAJORITY: labels.SECTION_MAJORITY,
    OVER_TIME: labels.SECTION_OVER_TIME,
}

#: The section links' landmark, drawn by the class the election and state pages'
#: section links share (``style.css``).
SECTIONS_ID = "elections-sections"


def section_nav(current: str, search: str) -> html.Nav:
    """The links between the three elections pages (#562), in page order, on D092's
    pattern: the page being read is text carrying ``aria-current="page"`` (a
    ``dcc.Link`` renders no ``aria-*``), the other two client-side links carrying
    ``search``, the filters the render applied (#596, D110, as a state's two pages
    carry the year range, D105), from :func:`applied_search`, never the request.
    Rendered on success only."""
    aria_current: dict[str, Any] = {"aria-current": "page"}
    entries = [
        html.Span(SECTION_TEXT[section], **aria_current)
        if section == current
        else dcc.Link(SECTION_TEXT[section], href=f"{section}{search}")
        for section in SECTIONS
    ]
    aria: dict[str, Any] = {"aria-label": labels.ELECTIONS_SECTIONS_LABEL}
    return html.Nav(
        entries, id=SECTIONS_ID, className=election_view.SECTIONS_CLASS, **aria
    )


#: How N1 is named in the errors below: a shared module names no API path (it reads no
#: ``api``), and the pages' ``try`` blocks turn every one into a section's own sentence.
N1 = "N1 (/elections/summary)"


def served_years(index: dict[str, Any]) -> set[int]:
    """The years a ``/v1/elections`` body serves (#562's review, cr.1): the one check of
    the index's rows on the two elections subpages, which call it before building any
    section, so an index defect degrades the whole page and only an N1 defect a section.

    Pure; raises ``KeyError`` for a missing key and ``TypeError`` for ``data`` that is
    not a non-empty list, a row whose year :func:`explore.election_view.row_year`
    refuses, or a year outside the served span. A year listed twice is one served year
    (#334). ``/elections`` keeps its own checks until #334 converges them.
    """
    coverage = index["meta"]["provenance"]["coverage"]
    first, last = query.year_span(coverage["year_min"], coverage["year_max"])
    rows = index["data"]
    if not isinstance(rows, list) or not rows:
        raise TypeError("/v1/elections carries no list of elections")
    served: set[int] = set()
    for row in rows:
        year = election_view.row_year(row)
        if year is None or not first <= year <= last:
            raise TypeError("/v1/elections names a year outside its served span")
        served.add(year)
    return served


def n1_items(index: dict[str, Any], summary: Any) -> dict[int, dict[str, Any]]:
    """N1's ``elections`` items by year, one for each year the index serves (D096(c)):
    the one check of those items, which C2, the averages (#437, D097) and C4 (#436)
    all call, so the rule for a valid item is in one place. Each refuses more on its
    own reads: C2 a missing ``ec_determinative`` and its rank-1 rule on ``data`` rows,
    the averages a missing margin among the years shown.

    Pure; raises ``KeyError`` for a missing key and ``TypeError`` for a year (in the
    index's rows or in N1's items) that :func:`explore.election_view.row_year` refuses
    or that lies outside the served span, an N1 year the index does not serve, or a
    served year with no ``elections`` item or two. A year the index lists twice is one
    served year: refusing the duplicate is the index's own rule (#334). It reads no
    ``data`` row: those are C2's alone.
    """
    served = served_years(index)
    if not isinstance(summary, dict):
        raise TypeError(f"{N1} is not an object")
    items = summary["elections"]
    if not isinstance(items, list):
        raise TypeError(f"{N1} carries no list of elections")
    by_year: dict[int, dict[str, Any]] = {}
    for item in items:
        year = election_view.row_year(item)
        if year is None or year not in served or year in by_year:
            raise TypeError(f"{N1}: a bad elections item")
        by_year[year] = item
    if set(by_year) != served:
        raise TypeError(f"{N1} misses a served year")
    return by_year


def index_rule(index: dict[str, Any]) -> tuple[tuple[int, int], dict[int, bool]]:
    """The index's popular-vote window and each served year's ``has_popular_vote``,
    checked as the page's, never a section's (#562's cr.1; #564's review, cr.3 and
    cr.8; moved here by #596, so both subpages filter on one rule): the window through
    ``query.year_span``, each flag a ``bool``, one flag per year, and each flag true
    exactly inside the window, so C2's marks (T3's rule), its bands and caption (the
    window) and the popular-vote filter follow one agreed rule. Pure; raises
    ``KeyError`` or ``TypeError``, which a page's layout shows as the degraded page."""
    coverage = index["meta"]["provenance"]["coverage"]
    window = query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
    has_pv: dict[int, bool] = {}
    for row in index["data"]:
        year = election_view.row_year(row)
        flag = row["has_popular_vote"]
        if year is None or type(flag) is not bool:
            raise TypeError("/v1/elections: has_popular_vote is not a bool")
        if has_pv.get(year, flag) is not flag:
            raise TypeError("/v1/elections: one year, two has_popular_vote")
        if flag is not (window[0] <= year <= window[1]):
            raise TypeError("/v1/elections: has_popular_vote disagrees with coverage")
        has_pv[year] = flag
    return window, has_pv


# --- The year filters (#306 on /elections; on all three pages since #596, D110) ---

#: The filter controls and the page-local location the callback writes, the same ids
#: on all three pages, so :func:`on_filter_change` serves each (#596).
YEARS_ID = "elections-years"
PV_ID = "elections-pv"
URL_ID = "elections-url"
#: The note a chart page shows in place of its charts and table when the filters leave
#: no election (#596).
NO_MATCH_ID = "elections-no-match"

#: The query keys the filters read. ``year_from`` and ``year_to`` are the API's own
#: names for a year range, so later tables with a year range share them.
YEAR_FROM = query.YEAR_FROM
YEAR_TO = query.YEAR_TO
PV = "pv"


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """The elections pages' filters from a parsed query string, as sorted ``(key,
    value)`` pairs: each page's one parser (``query=``), so ``og:url`` names the
    filtered view (the canonical link names none, D073).

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``,
    before any data is read. Keeps ``year_from`` / ``year_to`` only as four ASCII
    digits and ``pv`` only as ``"1"``; a key repeated with differing values is
    dropped, and so is a key it does not know, ``state`` among them since #562: on
    ``/elections`` an old link carrying one is redirected (``moved_to_path``) once the
    roster in memory accepts its code, and served the list with the key ignored
    otherwise; on ``/elections/over-time`` it changes nothing. A range whose start is
    after its end drops both bounds. Whether a year lies inside the served span is the
    layout's question (:func:`filters`).
    """
    if not isinstance(params, dict):
        return []
    kept = query.parse_year_range(params)
    if query.single(params.get(PV)) == "1":
        kept[PV] = "1"
    return sorted(kept.items())


class Filters(NamedTuple):
    """The filters a render applies, inside the served span."""

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


def shows(year: int, has_pv: bool, chosen: Filters) -> bool:
    """Whether the filters ``chosen`` show ``year``, whose ``has_popular_vote`` is
    ``has_pv``: the one rule all three pages apply (#596). Only ``True`` counts as a
    popular vote."""
    return chosen.year_from <= year <= chosen.year_to and (
        has_pv is True or not chosen.pv_only
    )


def applied_search(chosen: Filters, first: int, last: int) -> str:
    """The filters a render applied, in the normal form :func:`merged_search` writes
    (``""`` or ``?…``): already checked, so they are encoded without the parser. The
    section links and each download's view URL carry it."""
    params = query.year_range_search([chosen.year_from, chosen.year_to], first, last)
    if chosen.pv_only:
        params[PV] = "1"
    return query.encode_search(params.items())


def filter_controls(first: int, last: int, chosen: Filters) -> html.Div:
    """The year-range slider over the served span and the popular-vote checkbox, set
    to ``chosen``: the same controls, ids and wording on all three pages (#596)."""
    return html.Div(
        [
            html.Label(labels.YEARS_FILTER, htmlFor=YEARS_ID, className="label"),
            components.year_slider(
                YEARS_ID, first, last, (chosen.year_from, chosen.year_to)
            ),
            dcc.Checklist(
                id=PV_ID,
                options=[{"label": f" {labels.PV_ONLY_FILTER}", "value": "1"}],
                value=["1"] if chosen.pv_only else [],
            ),
        ],
        className="filters",
    )


def no_match() -> html.P:
    """What a chart page shows in place of its charts, table and download when the
    filters leave no election (#596): the one note, worded as T1's empty text."""
    return html.P(labels.NO_ELECTIONS_MATCH, id=NO_MATCH_ID, className="empty")


#: Each filter control's query keys (#436): a change replaces only the keys of the
#: control that changed.
CONTROL_KEYS: dict[str, tuple[str, ...]] = {
    YEARS_ID: (YEAR_FROM, YEAR_TO),
    PV_ID: (PV,),
}


def merged_search(
    triggered: Any,
    years: Any,
    pv: Any,
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
    elif triggered == PV_ID and isinstance(pv, list) and "1" in pv:
        params[PV] = "1"
    return query.encode_search(parse_filters(params))


def next_search(
    triggered: Any,
    years: Any,
    pv: Any,
    first: Any,
    last: Any,
    current: Any,
) -> Any:
    """What the filter callback writes: :func:`merged_search`, or ``no_update`` when
    that is the search the URL already has, which would navigate for nothing. Pure;
    reads no API."""
    search = merged_search(triggered, years, pv, first, last, current)
    return no_update if search == (current or "") else search


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
    """A filter change on any of the three elections pages becomes a URL change; the
    router re-renders from the cache, on the page being read.

    Reads no API. Only the changed control's keys change (:func:`next_search`).
    """
    return next_search(dash.ctx.triggered_id, years, pv, first, last, current)
