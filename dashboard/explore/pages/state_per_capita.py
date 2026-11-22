"""One state's people per electoral vote (#280, #559): T7, its persons per electoral
vote in every election this dataset holds for it, at ``/state/<usps>/per-capita``.

Split out of the state history by #559 (the history is ``pages/state.py``; the shared
pieces are in :mod:`explore.state_view`), as an election's per-capita page was split
from its overview (D092, D105). It reads one response, ``/v1/states/{usps}/per-capita``,
filled on a miss, after the code is validated against the state roster
(:func:`explore.state_view.on_roster`) as the history page validates it. Its one
filter is the shared year range (``year_from`` / ``year_to``), judged against the
dataset's span as on the history page; any other key is dropped, so the candidate and
popular-vote keys of a history link never reach ``og:url`` here (D081). The section
links carry the year range applied, in both directions. The chart that will sit beside
T7, C8, is #561; until then the page holds no chart slot (#545's rule).
"""

from __future__ import annotations

from typing import Any

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, export, labels, metrics, query, state_view
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filter leaves in T7.
PAGE_ID = "state-per-capita-page"
#: The wrapper of the not-found state: a code the dataset does not serve.
NOT_FOUND_ID = "state-per-capita-not-found"
PER_CAPITA_TABLE_ID = "state-per-capita"
#: The page's own URL and year control: distinct from the history page's, since Dash
#: registers callbacks app-wide, keyed by output.
URL_ID = "state-per-capita-url"
YEARS_ID = "state-per-capita-years"

#: T7's columns, in display order, by public field name (#280).
PER_CAPITA_FIELDS = ("year", *labels.PER_CAPITA_FIELDS)
#: What T7's CSV adds after its columns (#309): the state's key.
PER_CAPITA_EXTRA = ("state_usps",)

#: The not-found state (#325), shared by the two state pages (#559).
NOT_FOUND = api.NotFound(
    labels.STATE_NOT_FOUND_HEADING, labels.STATE_NOT_FOUND_SENTENCE
)

#: The page's heading on success, and on the degraded state, or before a code is
#: checked, its heading without a state (ba spec, approved at #559's plan gate,
#: 2026-11-18).
PER_CAPITA_HEADING = "{state}: people per electoral vote"
PER_CAPITA_GENERIC_HEADING = "State: people per electoral vote"
#: The lede, then, on a successful render only, the sentence naming its filter. It
#: makes no claim about which census applies: :data:`labels.GOVERNING_CENSUS_NOTE`,
#: under T7, says that (#423). The filter sentence names the table, so it stays true
#: if a chart beside it (C8, #561) is not narrowed by the range.
LEDE = (
    "How many people this state's electoral votes stood for in every election this "
    "dataset holds for it: the state's population divided by its electors appointed."
)
FILTER_SENTENCE = "Narrow the table to a range of years."

#: The headline figures (#600, D112(d)): the block and each figure's value, by metric
#: key, in display order, the page's one per-key table (#600's cr.9); DOM ids are
#: stable and never renamed (D097(g)).
METRICS_ID = "state-per-capita-metrics"
METRIC_IDS = {
    "state_per_capita_lowest": "state-per-capita-lowest",
    "state_per_capita_highest": "state-per-capita-highest",
}
#: The served field the figures select over, and T7's column for it.
FIGURE_FIELD = "persons_per_electoral_vote"

VALIDATE: api.Validate = (api.ROSTER_PATH, state_view.on_roster)


def title(usps: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a code the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the code only when it is a USPS code. It never names the
    state's name, which only the API can tell."""
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return f"{usps} — people per electoral vote — {SITE_TITLE}"
    return f"{PER_CAPITA_GENERIC_HEADING} — {SITE_TITLE}"


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's one filter, the year range, from a parsed query string, as sorted
    ``(key, value)`` pairs (:func:`explore.query.parse_year_range`); every other key
    is dropped. Syntactic and total, and it reads no API: Dash's index runs it to build
    ``og:url``. Never emits ``usps``, the path variable."""
    if not isinstance(params, dict):
        return []
    return sorted(query.parse_year_range(params).items())


dash.register_page(
    __name__,
    path_template=state_view.template(state_view.PER_CAPITA),
    # Before the history page, whose greedy ``<usps>`` would capture ``GA/per-capita``
    # (#559, as #465 ordered the election subpages; D092).
    order=0,
    title=title,
    # No names: the index HTML never waits on the API, so this cannot read the state.
    description=(
        "How many people one US state's electoral votes stood for in every "
        "presidential election in this dataset."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, "/v1/states/{usps}/per-capita"),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=parse_filters,
    # The site navigation link this page marks (#448): a state's page marks States.
    nav="states",
)


def search_for(years: Any, first: Any, last: Any) -> str:
    """The query string for the year control's value, in the normal form ``og:url``
    uses (``""`` or ``?…``). A bound at its end of the span is omitted. Unlike
    :func:`explore.state_view.year_search`, which encodes bounds a render already
    checked, this reads the control's raw values, so it passes them through the page's
    parser (an inverted pair is dropped there)."""
    return query.encode_search(
        parse_filters(query.year_range_search(years, first, last))
    )


@callback(
    Output(URL_ID, "search"),
    Input(YEARS_ID, "value"),
    State(YEARS_ID, "min"),
    State(YEARS_ID, "max"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(years: Any, first: Any, last: Any, current: Any) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. An unchanged search is left alone.
    """
    search = search_for(years, first, last)
    return no_update if search == (current or "") else search


def _controls(chosen: tuple[int, int], span: tuple[int, int]) -> html.Div:
    # The dataset's span, as on the history page: the slider's value is then the
    # selection, so the callback never writes back a bound the reader did not move.
    first, last = span
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Years", htmlFor=YEARS_ID, className="label"),
                    components.year_slider(YEARS_ID, first, last, chosen),
                ],
                # The slider keeps a row of its own, at the measure, from 76rem, as on
                # the history page (#545, D102).
                className="filter filter-own-row",
            ),
        ],
        className="filters filter-row",
    )


def _row(row: dict[str, Any], strings: dict[str, str]) -> html.Tr:
    year = row["year"]
    # A year links to its one-election view (#307), as in T4.
    return html.Tr(
        [
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            *labels.per_capita_cells(row, strings),
        ]
    )


def _figures(shown: list[dict[str, Any]], strings: list[dict[str, str]]) -> html.Div:
    """The state's lowest and highest people per electoral vote over the rows T7
    shows (#600, D112(d), (g)), as a ``dl``. One selection over the rows' served values,
    each shown as T7's own cell (``strings``, :func:`labels.per_capita_strings` per
    row), so the figures and the table cannot disagree. A value no figure can show
    makes both figures read unrecognized, T7 kept; the page's one read is their only
    input, so a failed read degrades the page (D114)."""
    years = [row["year"] for row in shown]
    selection = metrics.select(
        (row["year"], row[FIGURE_FIELD], cells[FIGURE_FIELD])
        for row, cells in zip(shown, strings, strict=True)
    )
    entries: list[Any] = []
    for key, ident in METRIC_IDS.items():
        metric = metrics.METRICS[key]
        if metric.kind != "select" or metric.pick is None:
            raise TypeError(f"{key} is no select")
        value, rest = labels.metric_select(
            selection, metric.pick, years, labels.METRIC_NO_FIGURE[key]
        )
        entries += components.metric_entry(key, ident, value, rest)
    return html.Div(html.Dl(entries, className="metrics"), id=METRICS_ID)


def _download(
    usps: str, body: dict[str, Any], search: str
) -> export.Download:
    """T7's download: the file named for the view and the table, the provenance of the
    response its rows come from, and this page's URL with the year range applied."""
    return export.Download(
        filename=f"state-{usps}-per-capita.csv",
        name="people per electoral vote",
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST, state_view.path(usps, state_view.PER_CAPITA), search
        ),
    )


def render(
    per_capita: dict[str, Any],
    index: dict[str, Any],
    usps: str,
    pairs: list[tuple[str, str]],
) -> tuple[html.Div, Any]:
    """The page body and the state's name as served (the layout checks it has text),
    for one ``/v1/states/{usps}/per-capita`` response and the ``/v1/elections`` index
    (read through the same view), and this page's filter pairs: the section links,
    carrying the year range applied, the year control, T7 and the footer, from the
    per-capita response's own provenance."""
    provenance = per_capita["meta"]["provenance"]
    coverage = provenance["coverage"]
    span = query.year_span(coverage["year_min"], coverage["year_max"])
    source = f"/v1/states/{usps}/per-capita"
    rows = state_view.rows(per_capita, usps, state_view.served_years(index), source)
    # One row per year, or the body is malformed and the page degrades (#609's review,
    # D114(g)): T7 and its figures read each year once, so a repeated year would
    # misstate N, or name a year twice in a tie. ``state_view.rows`` cannot refuse it,
    # since T4 holds many rows per year.
    if len({row["year"] for row in rows}) != len(rows):
        raise TypeError(f"{source} names a year twice")
    chosen = query.year_range(pairs, *span)
    search = state_view.year_search(*chosen, span)
    shown = [r for r in rows if chosen[0] <= r["year"] <= chosen[1]]
    # Each shown row's cells, worded once and read by T7 and the figures (#600).
    strings = {id(row): labels.per_capita_strings(row) for row in shown}
    content = html.Div(
        [
            state_view.section_nav(usps, state_view.PER_CAPITA, search),
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            # The page's one section, named by its H1, in one card (#567, D111).
            components.card(
                [
                    _controls(chosen, span),
                    # The headline figures over the rows shown (#600): after the year
                    # control and before the count line.
                    _figures(shown, [strings[id(row)] for row in shown]),
                    html.P(
                        f"Showing {len(shown)} of {len(rows)} rows", className="count"
                    ),
                    *components.table(
                        shown,
                        lambda r: _row(r, strings[id(r)]),
                        PER_CAPITA_FIELDS,
                        PER_CAPITA_TABLE_ID,
                        _download(usps, per_capita, search),
                        extra=PER_CAPITA_EXTRA,
                        notes=(labels.GOVERNING_CENSUS_NOTE, labels.BOUNDARY_NOTE),
                    ),
                    labels.glossary(PER_CAPITA_FIELDS),
                ]
            ),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )
    return content, rows[0]["state"]


def layout(usps: Any = None, **params: Any) -> html.Div:
    heading = PER_CAPITA_GENERIC_HEADING
    # The filter sentence only above the filter: not on the not-found or degraded
    # state, which show none. The not-found state shows no lede at all (#325).
    lede: str | None = LEDE
    try:
        with api.CLIENT.view() as view:
            # Validated from the roster before it is formatted (#279, D074).
            if not api.accepted(view.get, VALIDATE, {"usps": usps}):
                heading, lede = labels.STATE_NOT_FOUND_HEADING, None
                content = state_view.not_found(NOT_FOUND_ID)
            else:
                index = view.get(api.ELECTIONS_PATH)
                per_capita = view.get(f"/v1/states/{usps}/per-capita")
                content, state = render(
                    per_capita, index, usps, parse_filters(params)
                )
                # A served name with nothing in it names no state (#532's rule).
                if labels.has_text(state):
                    heading = PER_CAPITA_HEADING.format(state=state)
                lede = f"{LEDE} {FILTER_SENTENCE}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
