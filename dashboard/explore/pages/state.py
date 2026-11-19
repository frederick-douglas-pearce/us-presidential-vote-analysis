"""One state's history (#279): chart C7, its electors appointed in each election (#560),
and T4, its rows in every election this dataset holds for it.

Its people per electoral vote (T7, #280) is a page of its own since #559,
``pages/state_per_capita.py``; what the two share is in :mod:`explore.state_view`,
and the section links join them (D105). T4 and C7 come from one response,
``/v1/states/{usps}``, filled on a miss; C7 collapses its rows, one per candidate, to
one per election (D106). The state is the path (``/state/<usps>``, an
item singular as ``/states`` is plural), in upper case as the API writes a USPS code.
It is validated against the state roster before it is formatted into an API path: the
latest election's rows (``/v1/elections/{year_max}``, :data:`explore.api.ROSTER_PATH`),
since every state and DC takes part in it (:func:`explore.state_view.on_roster`). That
source is declared in ``on_miss`` and built from the index's coverage, never from the
path, so a code the dataset does not serve never fills a path built from it: the most it
costs is a fill of the shared roster, once per render until one succeeds, and it 404s
at the index once the roster is cached (#279, D074).

It follows the one-election view's conventions (``pages/election.py``): labels and
null cells from :mod:`explore.labels`, filters only in the query string through the
page's one parser, a filter change written to a page-local ``dcc.Location`` and
re-rendered from the cache, the provenance footer from the response's own
``meta.provenance``, and T4 through :func:`explore.components.table`, which offers its
rows as a CSV (#309) built from the same list as its body. The filters are the shared
year range (``year_from`` / ``year_to``, judged against the dataset's span as on
``/elections``, so a range before the state's first election is an honest empty
result), ``candidate`` (a slug) and ``pv_status``; the section link to the per-capita
page carries the year range only. No query key reaches T7 alone, so an old link to
this page needs no redirect (D105). Each candidate links to their history
(``pages/candidate.py``, #331).
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import (
    api,
    charts,
    components,
    export,
    labels,
    over_time,
    query,
    state_view,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T4.
PAGE_ID = "state"
#: The wrapper of the not-found state: a code the dataset does not serve, or a section
#: the site does not have (``/state/GA/x``).
NOT_FOUND_ID = "state-not-found"
TABLE_ID = "state-history"
URL_ID = "state-url"
YEARS_ID = "state-years"
CANDIDATE_ID = "state-candidate"
PV_STATUS_ID = "state-pv-status"

#: Chart C7 (#560, D106): the state's electors appointed in each election, before the
#: filters, with its own companion table, which no filter reaches (D093(a)).
C7_ID = "C7"
ELECTORS_TABLE_ID = "state-electors"
ELECTORS_GLOSSARY_ID = "state-electors-glossary"
#: The degraded section's sentence (D096(d)'s rule): C7's section alone, when the
#: rows T4 shows cannot be read as one allotment per election.
C7_UNAVAILABLE_ID = "state-electors-unavailable"
#: The companion table's columns, by public field name, and what its CSV adds.
ELECTORS_FIELDS = ("year", "state_electoral_votes", "pv_status")
ELECTORS_EXTRA = ("state_usps",)

#: T4's columns, in display order, by public field name.
FIELDS = (
    "year",
    "candidate",
    "nominating_party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
    "popular_votes",
)
#: The fields T4's glossary names: its columns, the reason its count cell shows, and the
#: party note its Party notes list shows (#389).
GLOSSARY = (*FIELDS, "electoral_count_status_reason", "nominating_party_note")
#: What T4's CSV adds after its columns (#309): the reason its count cell shows, the
#: party note and the party's per-row source (#389), and the keys its candidate filter
#: and its state are named by.
EXTRA = (
    "electoral_count_status_reason",
    "nominating_party_note",
    "nominating_party_source",
    "candidate_slug",
    "state_usps",
)

#: The query keys this page reads besides the shared year range: the API's filter name
#: for a candidate, and the field name of the closed popular-vote vocabulary.
CANDIDATE = "candidate"
PV_STATUS = "pv_status"

#: The not-found state (#325), shared by the two state pages (#559).
NOT_FOUND = api.NotFound(
    labels.STATE_NOT_FOUND_HEADING, labels.STATE_NOT_FOUND_SENTENCE
)

#: The lede, then, on a successful render only, the sentence naming the filters it
#: offers (#392): the degraded state shows the lede alone, the not-found state none
#: (#325). People per electoral vote left it with T7 (#559; ba spec, approved at its
#: plan gate, 2026-11-18).
LEDE = (
    "This state's electors appointed and its electoral votes for each candidate in "
    "every election this dataset holds for it, with the popular vote where the dataset "
    "has it."
)
FILTER_SENTENCE = (
    "Narrow the table of each candidate's electoral votes by year, candidate or "
    "popular-vote status."
)
#: The page's two sections' headings (#560; ba spec, approved at its plan gate,
#: 2026-11-18): C7 and its table, then T4, which its filters belong to.
C7_HEADING = "Electors appointed over time"
C7_TABLE_HEADING = "This state's electors appointed in each election"
HISTORY_TABLE_HEADING = "Each candidate's electoral votes in each election"
C7_UNAVAILABLE = (
    "The chart and table of this state's electors appointed in each election can't "
    "be shown right now. Please try again in a minute."
)


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``.
    Keeps the year range as :func:`explore.query.parse_year_range` does, ``candidate``
    only as a slug and ``pv_status`` only as one of its closed values; a key repeated
    with differing values is dropped, and so is a key it does not know. Never emits
    ``usps``, the path variable. Whether a year or candidate is in this state's rows is
    the layout's question (:func:`filters`).
    """
    if not isinstance(params, dict):
        return []
    kept = query.parse_year_range(params)
    candidate = query.single(params.get(CANDIDATE))
    if candidate is not None and query.is_slug(candidate):
        kept[CANDIDATE] = candidate
    pv_status = query.single(params.get(PV_STATUS))
    if pv_status in labels.PV_STATUS:
        kept[PV_STATUS] = pv_status
    return sorted(kept.items())


VALIDATE: api.Validate = (api.ROSTER_PATH, state_view.on_roster)


def title(usps: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a code the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the code only when it is a USPS code."""
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return f"{usps} — state history — {SITE_TITLE}"
    return f"State history — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template=state_view.template(state_view.HISTORY),
    title=title,
    # No names: the index HTML never waits on the API, so this cannot read the state.
    description=(
        "One US state's electoral votes in every presidential election in this dataset."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, "/v1/states/{usps}"),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=parse_filters,
    # The site navigation link this page marks (#448):
    # a state's history marks its index, States.
    nav="states",
)


class Filters(NamedTuple):
    """The filters a render applies; ``None`` is "all".

    A ``NamedTuple``, not a dataclass: Dash executes a page module before it is in
    ``sys.modules``, which ``dataclass`` needs.
    """

    year_from: int
    year_to: int
    candidate: str | None
    pv_status: str | None


def filters(
    pairs: list[tuple[str, str]], rows: list[dict[str, Any]], span: tuple[int, int]
) -> Filters:
    """The filters to apply to this state's rows.

    Per parameter, as ``og:url`` is. A year bound is judged against the dataset's span,
    as on ``/elections``: one outside it falls back to that end of it, while one inside
    it is kept even where the state has no election, so a range before its first is an
    honest empty result rather than its whole history. A candidate absent from its rows
    falls back to "all". A status is a closed value, so it is kept even when no row has
    it.
    """
    year_from, year_to = query.year_range(pairs, *span)
    given = dict(pairs)
    candidate = given.get(CANDIDATE)
    return Filters(
        year_from=year_from,
        year_to=year_to,
        candidate=(
            candidate if any(r["candidate_slug"] == candidate for r in rows) else None
        ),
        pv_status=given.get(PV_STATUS),
    )


def select(rows: list[dict[str, Any]], chosen: Filters) -> list[dict[str, Any]]:
    """The rows T4 shows: pure, and separate from building the table."""
    return [
        r
        for r in rows
        if chosen.year_from <= r["year"] <= chosen.year_to
        and chosen.candidate in (None, r["candidate_slug"])
        and chosen.pv_status in (None, r["pv_status"])
    ]


def search_for(
    years: Any, candidate: Any, pv_status: Any, first: Any, last: Any
) -> str:
    """The query string for the controls' values, in the normal form ``og:url`` uses
    (``""`` or ``?…``). Defaults and a cleared control are omitted."""
    params = query.year_range_search(years, first, last)
    for key, value in ((CANDIDATE, candidate), (PV_STATUS, pv_status)):
        if isinstance(value, str) and value:
            params[key] = value
    return query.encode_search(parse_filters(params))


def applied_search(chosen: Filters, span: tuple[int, int]) -> str:
    """The filters a render applied, in the normal form :func:`search_for` writes:
    already checked, so they are encoded without the parser."""
    params = query.year_range_search([chosen.year_from, chosen.year_to], *span)
    for key, value in ((CANDIDATE, chosen.candidate), (PV_STATUS, chosen.pv_status)):
        if value:
            params[key] = value
    return query.encode_search(params.items())


@callback(
    Output(URL_ID, "search"),
    Input(YEARS_ID, "value"),
    Input(CANDIDATE_ID, "value"),
    Input(PV_STATUS_ID, "value"),
    State(YEARS_ID, "min"),
    State(YEARS_ID, "max"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(
    years: Any, candidate: Any, pv_status: Any, first: Any, last: Any, current: Any
) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. An unchanged search is left alone.
    """
    search = search_for(years, candidate, pv_status, first, last)
    return no_update if search == (current or "") else search


def _controls(
    rows: list[dict[str, Any]], chosen: Filters, span: tuple[int, int]
) -> html.Div:
    # The dataset's span, as on /elections: the slider's value is then the selection,
    # so the callback never writes back a bound the reader did not move.
    first, last = span
    candidates = {r["candidate_slug"]: str(r["candidate"]) for r in rows}
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Years", htmlFor=YEARS_ID, className="label"),
                    components.year_slider(
                        YEARS_ID, first, last, (chosen.year_from, chosen.year_to)
                    ),
                ],
                # The slider keeps a row of its own, at the measure, from 76rem (#545).
                className="filter filter-own-row",
            ),
            components.dropdown_filter(
                CANDIDATE_ID,
                labels.LABELS[CANDIDATE],
                components.label_sorted_options(candidates),
                chosen.candidate,
                "All candidates",
            ),
            components.dropdown_filter(
                PV_STATUS_ID,
                labels.LABELS["pv_status"],
                [{"label": v, "value": k} for k, v in labels.PV_STATUS.items()],
                chosen.pv_status,
                "Any",
            ),
        ],
        # A filter row from 76rem (#545, D102): the two dropdowns side by side under it.
        className="filters filter-row",
    )


def _row(row: dict[str, Any], coverage: dict[str, Any]) -> html.Tr:
    year = row["year"]
    return html.Tr(
        [
            # A year links to its one-election view (#307).
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            # A candidate links to their history (#331).
            components.candidate_cell(row),
            labels.nominating_party_cell(row),
            labels.cell(labels.number(row["state_electoral_votes"])),
            labels.cell(labels.number(row["electoral_votes"])),
            labels.cell(labels.number(row["electoral_votes_counted"])),
            labels.cell(
                labels.count_status(
                    row["electoral_count_status"], row["electoral_count_status_reason"]
                )
            ),
            labels.cell(labels.pv_status(row["pv_status"])),
            labels.cell(
                labels.popular_votes(
                    row["popular_votes"], row["pv_status"], year, coverage
                )
            ),
        ]
    )


def electors(
    rows: list[dict[str, Any]], served: set[int], usps: str, source: str
) -> list[dict[str, Any]]:
    """C7's rows (#560, D106): the state's appointed allotment and popular-vote status,
    one per election from its first, collapsed from ``rows`` (T4's, one per candidate,
    already checked by :func:`explore.state_view.rows`, so each row's year is a served
    year).

    Pure; raises ``KeyError`` for a row without a field and ``TypeError`` for a year's
    rows that disagree on either value (a null beside a figure is two values, D077,
    D098) or a gap after the state's first election
    (:func:`explore.over_time.state_series`, the rule C4's one-state series reads), so
    C7 draws one value per election or nothing.
    """
    by_year: dict[int, dict[str, Any]] = {}
    for row in rows:
        year = row["year"]
        record = {
            "year": year,
            "state_usps": usps,
            "state_electoral_votes": row["state_electoral_votes"],
            "pv_status": row["pv_status"],
        }
        kept = by_year.setdefault(year, record)
        for field in ("state_electoral_votes", "pv_status"):
            if not over_time.same(kept[field], record[field]):
                raise TypeError(f"{source} has two values of {field} in {year}")
    return over_time.state_series(by_year, served, source, usps)


def _electors_row(point: over_time.Point) -> html.Tr:
    """A row of C7's companion table: the year, linked to its election, and the cells
    C7's hover writes."""
    return html.Tr(
        [
            html.Td(dcc.Link(str(point.year), href=f"/election/{point.year}")),
            labels.cell(point.appointed_cell),
            labels.cell(point.status_cell or labels.UNRECOGNIZED),
        ]
    )


def _electors_caption(
    c7: over_time.OverTime, plain: str | None, first: int | None
) -> str:
    """C7's caption: what electors appointed is, what each marker means where one is
    drawn, the state's first election where it comes after the dataset's first, and
    that the page's filters do not reach it (D093(a)); ``components.chart`` adds the
    table pointer. Names the state only in plain text (``plain``, else "this
    state")."""
    parts = [labels.C4_BASIS]
    if c7.zeros:
        parts.append(labels.C4_ZERO_NOTE)
    if c7.missing:
        parts.append(labels.C4_NO_FIGURE_NOTE)
    if first is not None:
        parts.append(
            labels.FIRST_ELECTION_NOTE_THIS_STATE.format(year=first)
            if plain is None
            else labels.FIRST_ELECTION_NOTE.format(state=plain, year=first)
        )
    parts.append(labels.C7_FILTERS_NOTE)
    return " ".join(parts)


def _electors_section(
    rows: list[dict[str, Any]],
    served: set[int],
    usps: str,
    body: dict[str, Any],
    source: str,
) -> list[Any]:
    """C7's section (#560, D106): its heading, the chart, its heading-led companion
    table and that table's column-name list, for the rows T4 shows from the API path
    ``source``. Rows that cannot be read as one allotment per election, or a served
    name with nothing in it (D101's rule, which C4's ``n2_rows`` applies), show the
    heading and :data:`C7_UNAVAILABLE` only, with no chart (D096(d)'s rule), while T4
    and the page stay. The ``try`` covers everything built from the rows, never
    ``components.chart`` (D095(f))."""
    heading = html.H2(C7_HEADING)
    try:
        records = electors(rows, served, usps, source)
        points = over_time.appointed_points(records)
        years = sorted(served)
        name = rows[0]["state"]
        # A name a hover would write as "None", a number or nothing names no state.
        if not labels.has_text(name):
            raise TypeError(f"{source} names {usps} with no text")
        plain = over_time.plain(name)
        title = (
            labels.C7_TITLE_THIS_STATE
            if plain is None
            else labels.C4_TITLE_STATE.format(state=plain)
        )
        c7 = over_time.c4_figure(points, years, title, charts.escaped(str(name)))
        first = points[0].year if points[0].year > years[0] else None
        caption = _electors_caption(c7, plain, first)
        by_row = {id(r): p for r, p in zip(records, points, strict=True)}
        table = components.table(
            records,
            lambda r: _electors_row(by_row[id(r)]),
            ELECTORS_FIELDS,
            ELECTORS_TABLE_ID,
            export.Download(
                filename=f"state-{usps}-electors.csv",
                name="this state's electors appointed in each election",
                provenance=body["meta"]["provenance"],
                view_url=export.view_url(
                    CANONICAL_HOST, state_view.path(usps, state_view.HISTORY), ""
                ),
            ),
            extra=ELECTORS_EXTRA,
            notes=(labels.C4_BASIS,),
        )
    except (KeyError, TypeError):
        return [
            heading,
            html.P(C7_UNAVAILABLE, id=C7_UNAVAILABLE_ID, className="note"),
        ]
    return [
        heading,
        components.chart(C7_ID, c7.figure, ELECTORS_TABLE_ID, caption),
        html.H2(C7_TABLE_HEADING),
        *table,
        labels.glossary(ELECTORS_FIELDS, ident=ELECTORS_GLOSSARY_ID),
    ]


def _download(
    usps: str, body: dict[str, Any], chosen: Filters, span: tuple[int, int]
) -> export.Download:
    """T4's download: the file named for the view and the table, the provenance of the
    response its rows come from, and the view's URL with the filters applied."""
    return export.Download(
        filename=f"state-{usps}-history.csv",
        name="this state's history",
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST,
            state_view.path(usps, state_view.HISTORY),
            applied_search(chosen, span),
        ),
    )


def render(
    body: dict[str, Any],
    index: dict[str, Any],
    usps: str,
    pairs: list[tuple[str, str]],
) -> tuple[html.Div, Any]:
    """The page body and the state's name as served (the layout checks it has text),
    for one ``/v1/states/{usps}`` response and
    the ``/v1/elections`` index (read through the same view), and this page's filter
    pairs. The section links come first, carrying the year range applied (#559), then
    C7's section, then T4's, under its own heading, with the filters that narrow it
    (#560, D106)."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    span = query.year_span(coverage["year_min"], coverage["year_max"])
    source = f"/v1/states/{usps}"
    served = state_view.served_years(index)
    rows = state_view.rows(body, usps, served, source)
    chosen = filters(pairs, rows, span)
    shown = select(rows, chosen)
    content = html.Div(
        [
            state_view.section_nav(
                usps,
                state_view.HISTORY,
                state_view.year_search(chosen.year_from, chosen.year_to, span),
            ),
            *_electors_section(rows, served, usps, body, source),
            html.H2(HISTORY_TABLE_HEADING),
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            _controls(rows, chosen, span),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            *components.table(
                shown,
                lambda r: _row(r, coverage),
                FIELDS,
                TABLE_ID,
                _download(usps, body, chosen, span),
                extra=EXTRA,
                notes=(labels.PARTY_NOTE, labels.PARTY_NULL_NOTE),
            ),
            *labels.party_notes(shown),
            labels.glossary(GLOSSARY),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )
    return content, rows[0]["state"]


def layout(usps: Any = None, **params: Any) -> html.Div:
    heading = "State history"
    # The filter sentence only above the filters: not on the not-found or degraded
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
                body = view.get(f"/v1/states/{usps}")
                content, state = render(body, index, usps, parse_filters(params))
                # A served name with nothing in it names no state (#532's rule), as on
                # the per-capita page: the heading stays "State history".
                if labels.has_text(state):
                    heading = state
                lede = f"{LEDE} {FILTER_SENTENCE}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
