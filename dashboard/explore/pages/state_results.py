"""One state's results by election (#279, #619): T4, the state's electoral votes for
each candidate in every election this dataset holds for it, at
``/state/<usps>/elections``.

Moved off the state history by #619 (the history is ``pages/state.py``; the shared
pieces are in :mod:`explore.state_view`), as #559 moved T7 and #465 split the election
pages (D092, D105, D118). It reads ``/v1/states/{usps}``, the one response the history
page reads, filled on a miss, so a visit after the history page makes no request. The
code is validated against the state roster (:func:`explore.state_view.on_roster`)
before it is formatted into an API path, as on the other state pages.

It follows the one-election view's conventions (``pages/election.py``): labels and
null cells from :mod:`explore.labels`, filters only in the query string through the
page's one parser, a filter change written to a page-local ``dcc.Location`` and
re-rendered from the cache, the provenance footer from the response's own
``meta.provenance``, and T4 through :func:`explore.components.table`, which offers its
rows as a CSV (#309) built from the same list as its body. The filters are the shared
year range (``year_from`` / ``year_to``, judged against the dataset's span as on
``/elections``, so a range before the state's first election is an honest empty
result), ``candidate`` (a slug) and ``pv_status``. The last two are the history page's
moved keys (D118): an old ``/state/<usps>?candidate=…`` link answers 302 to this page.
The section links carry the year range applied and nothing else. Each candidate links
to their history (``pages/candidate.py``, #331).
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, export, labels, query, state_view
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T4.
PAGE_ID = "state-results-page"
#: The wrapper of the not-found state: a code the dataset does not serve.
NOT_FOUND_ID = "state-results-not-found"
#: T4's table (#619): T4's id on the history page, ``state-history``, is retired,
#: never reused (D097(g), D118).
TABLE_ID = "state-results"
#: The page's own URL and controls: distinct from the other state pages', since Dash
#: registers callbacks app-wide, keyed by output.
URL_ID = "state-results-url"
YEARS_ID = "state-results-years"
CANDIDATE_ID = "state-results-candidate"
PV_STATUS_ID = "state-results-pv-status"

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
#: for a candidate, and the field name of the closed popular-vote vocabulary. Named
#: here, not read from :data:`explore.state_view.MOVED_KEYS` (the history page's
#: redirect list, D118), so a change to that list never swaps this page's parser;
#: ``test_the_page_is_registered_as_planned`` pins that the two agree.
CANDIDATE = "candidate"
PV_STATUS = "pv_status"

#: The not-found state (#325), shared by the three state pages (#559, #619).
NOT_FOUND = api.NotFound(
    labels.STATE_NOT_FOUND_HEADING, labels.STATE_NOT_FOUND_SENTENCE
)

#: The page's heading on success, and on the degraded state, or before a code is
#: checked, its heading without a state; the lede, then, on a successful render only,
#: the sentence naming its filters (#392) (ba spec, approved at #619's plan gate,
#: 2026-11-23).
RESULTS_HEADING = "{state}: results by election"
RESULTS_GENERIC_HEADING = "State: results by election"
LEDE = (
    "This state's electoral votes for each candidate in every election this dataset "
    "holds for it, with the popular vote where the dataset has it, and whether "
    "Congress counted them."
)
FILTER_SENTENCE = "Narrow the rows by year, candidate or popular-vote status."

VALIDATE: api.Validate = (api.ROSTER_PATH, state_view.on_roster)


def title(usps: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a code the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the code only when it is a USPS code. It never names the
    state's name, which only the API can tell."""
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return f"{usps} — results by election — {SITE_TITLE}"
    return f"{RESULTS_GENERIC_HEADING} — {SITE_TITLE}"


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``,
    and app.py runs it to build the Location of a moved history link (D118). Keeps the
    year range as :func:`explore.query.parse_year_range` does, ``candidate`` only as a
    slug and ``pv_status`` only as one of its closed values; a key repeated with
    differing values is dropped, and so is a key it does not know. Never emits
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


dash.register_page(
    __name__,
    path_template=state_view.template(state_view.RESULTS),
    # Before the history page, whose greedy ``<usps>`` would capture ``GA/elections``
    # (#619, as #559 ordered the per-capita page; D092, D105).
    order=1,
    title=title,
    # No names: the index HTML never waits on the API, so this cannot read the state.
    description=(
        "One US state's electoral votes for each candidate in every presidential "
        "election in this dataset, with the popular vote where the dataset has it."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, "/v1/states/{usps}"),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=parse_filters,
    # The site navigation link this page marks (#448): a state's page marks States.
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


def _download(
    usps: str, body: dict[str, Any], chosen: Filters, span: tuple[int, int]
) -> export.Download:
    """T4's download: the file named for the view and the table (D075), the provenance
    of the response its rows come from, and the view's URL with the filters applied."""
    return export.Download(
        filename=f"state-{usps}-by-election.csv",
        name="the results by election",
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST,
            state_view.path(usps, state_view.RESULTS),
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
    for one ``/v1/states/{usps}`` response and the ``/v1/elections`` index (read
    through the same view), and this page's filter pairs: the section links, carrying
    the year range applied, then T4 with its filters in one card, and the footer."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    span = query.year_span(coverage["year_min"], coverage["year_max"])
    # The popular-vote window, checked once before any cell reads it (D118, the rule
    # ``labels.in_pv_window`` states): T4's cells read it only on some rows, so a
    # missing or malformed window degrades the page in every view, the empty one too.
    query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
    source = f"/v1/states/{usps}"
    rows = state_view.rows(body, usps, state_view.served_years(index), source)
    chosen = filters(pairs, rows, span)
    shown = select(rows, chosen)
    content = html.Div(
        [
            state_view.section_nav(
                usps,
                state_view.RESULTS,
                state_view.year_search(chosen.year_from, chosen.year_to, span),
            ),
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            # The page's one section, named by its H1, in one card (#567, D111).
            components.card(
                [
                    _controls(rows, chosen, span),
                    html.P(
                        f"Showing {len(shown)} of {len(rows)} rows", className="count"
                    ),
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
                ]
            ),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )
    return content, rows[0]["state"]


def layout(usps: Any = None, **params: Any) -> html.Div:
    heading = RESULTS_GENERIC_HEADING
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
                # A served name with nothing in it names no state (#532's rule).
                if labels.has_text(state):
                    heading = RESULTS_HEADING.format(state=state)
                lede = f"{LEDE} {FILTER_SENTENCE}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
