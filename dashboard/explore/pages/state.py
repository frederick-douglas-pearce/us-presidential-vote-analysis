"""One state's history (#279): T4, its rows in every election this dataset holds for it,
and T7, its persons per electoral vote in each of them (#280).

T4 comes from one response, ``/v1/states/{usps}``, and T7 from a second,
``/v1/states/{usps}/per-capita``; both are filled on a miss, in the same render, so the
page's success marker renders only when both tables did. The state is
the path (``/state/<usps>``, an item singular as ``/states`` is plural), in upper case
as the API writes a USPS code. It is validated against the state roster before it is
formatted into an API path: the latest election's rows (``/v1/elections/{year_max}``,
:data:`explore.api.ROSTER_PATH`), since every state and DC takes part in it. That
source is declared in ``on_miss`` and built from the index's coverage, never from the
path, so a code the dataset does not serve never fills a path built from it: the most it
costs is a fill of the shared roster, once per render until one succeeds, and it 404s
at the index once the roster is cached (#279, D074).

It follows the one-election view's conventions (``pages/election.py``): labels and
null cells from :mod:`explore.labels`, filters only in the query string through the
page's one parser, a filter change written to a page-local ``dcc.Location`` and
re-rendered from the cache, the provenance footer from the response's own
``meta.provenance``, and both tables through :func:`explore.components.table`, which
offers its rows as a CSV (#309) built from the same list as its body. The filters are
the shared year range (``year_from`` / ``year_to``, judged against the dataset's span
as on ``/elections``, so a range before the state's first election is an honest empty
result), ``candidate`` (a slug) and ``pv_status``. T7 is narrowed by the year range
only.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T4.
PAGE_ID = "state"
#: The wrapper of the not-found state: a code the dataset does not serve.
NOT_FOUND_ID = "state-not-found"
TABLE_ID = "state-history"
URL_ID = "state-url"
YEARS_ID = "state-years"
CANDIDATE_ID = "state-candidate"
PV_STATUS_ID = "state-pv-status"
PER_CAPITA_TABLE_ID = "state-per-capita"

#: T4's columns, in display order, by public field name.
FIELDS = (
    "year",
    "candidate",
    "party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
    "popular_votes",
)
#: The fields T4's glossary names: its columns, and the reason its count cell shows.
GLOSSARY = (*FIELDS, "electoral_count_status_reason")
#: What T4's CSV adds after its columns (#309): the reason its count cell shows, and the
#: keys its candidate filter and its state are named by.
EXTRA = ("electoral_count_status_reason", "candidate_slug", "state_usps")

#: T7's columns, in display order, by public field name (#280).
PER_CAPITA_FIELDS = ("year", *labels.PER_CAPITA_FIELDS)
#: What T7's CSV adds after its columns (#309): the state's key.
PER_CAPITA_EXTRA = ("state_usps",)

#: Which of the page's filters T7 follows: the year range, and not the others.
PER_CAPITA_FILTER_NOTE = (
    "Only the year range applies to this table; the candidate and popular-vote "
    "filters do not."
)

#: The query keys this page reads besides the shared year range: the API's filter name
#: for a candidate, and the field name of the closed popular-vote vocabulary.
CANDIDATE = "candidate"
PV_STATUS = "pv_status"

#: The not-found state's sentence. The raw path value is never echoed.
NOT_FOUND_SENTENCE = "This dataset has no state with that code."


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


def _rows_of(body: Any) -> list[Any]:
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else []


def on_roster(path_vars: dict[str, Any], body: Any) -> bool:
    """Whether ``path_vars["usps"]`` is a state the roster names.

    Pure and total: a USPS code (two ASCII capitals) among the states
    :func:`explore.api.roster` reads, never a literal. A malformed roster names no
    state, and neither does one whose rows name another year than its own
    ``coverage.year_max``: the judge has only the roster's body, so that is the latest
    election it can check against (the picker checks the index's, the same snapshot).
    """
    usps = path_vars.get("usps")
    if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
        return False
    try:
        named, states = api.roster(body)
        latest = query.checked_year(body["meta"]["provenance"]["coverage"]["year_max"])
    except (KeyError, TypeError):
        return False
    return named == latest and usps in states


VALIDATE: api.Validate = (api.ROSTER_PATH, on_roster)


def title(usps: Any = None, **_vars: Any) -> str:
    """The page title. Called by Dash at index time with the **unvalidated** path
    variable, so it is total and reads no API; it names the code only when it is a
    USPS code."""
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return f"{usps} — state history — {SITE_TITLE}"
    return f"State history — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template="/state/<usps>",
    title=title,
    # No names: the index HTML never waits on the API, so this cannot read the state.
    description=(
        "One US state's electoral votes in every presidential election in this dataset."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, "/v1/states/{usps}", "/v1/states/{usps}/per-capita"),
    success=PAGE_ID,
    validate=VALIDATE,
    query=parse_filters,
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


def _served_years(index: Any) -> set[int]:
    years = {
        year
        for row in _rows_of(index)
        if isinstance(row, dict) and (year := query.checked_year(row.get("year")))
    }
    if not years:
        raise TypeError("/v1/elections serves no year")
    return years


def _rows(
    body: Any, usps: str, served: set[int], path: str | None = None
) -> list[dict[str, Any]]:
    """The state's rows from ``path`` (``/v1/states/{usps}`` by default), sorted by
    year then candidate, or ``TypeError``.

    A served state always has rows, so an empty list is a malformed body: rendering it
    would show the success marker over an empty table. Each row must name this state
    and a year the index serves (checked by :func:`explore.query.checked_year`), so no
    row of another state, or of a year the dataset does not hold, is shown. The same
    rule reads T7's ``/per-capita`` rows (#280), which name no candidate.
    """
    path = path or f"/v1/states/{usps}"
    rows = _rows_of(body)
    if not rows:
        raise TypeError(f"{path} carries no list of rows")
    for row in rows:
        if not isinstance(row, dict) or row.get("state_usps") != usps:
            raise TypeError(f"{path} carries a row of another state")
        if query.checked_year(row.get("year")) not in served:
            raise TypeError(f"{path} carries a row of no served year")
    return sorted(rows, key=lambda r: (r["year"], str(r.get("candidate", ""))))


def _options(pairs: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"label": label, "value": value}
        for value, label in sorted(pairs.items(), key=lambda kv: kv[1])
    ]


def _controls(
    rows: list[dict[str, Any]], chosen: Filters, span: tuple[int, int]
) -> html.Div:
    # The dataset's span, as on /elections: the slider's value is then the selection,
    # so the callback never writes back a bound the reader did not move.
    first, last = span
    candidates = {r["candidate_slug"]: str(r["candidate"]) for r in rows}
    dropdowns = (
        (
            CANDIDATE_ID,
            labels.LABELS[CANDIDATE],
            _options(candidates),
            chosen.candidate,
            "All candidates",
        ),
        (
            PV_STATUS_ID,
            labels.LABELS["pv_status"],
            [{"label": v, "value": k} for k, v in labels.PV_STATUS.items()],
            chosen.pv_status,
            "Any",
        ),
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Years", htmlFor=YEARS_ID, className="label"),
                    components.year_slider(
                        YEARS_ID, first, last, (chosen.year_from, chosen.year_to)
                    ),
                ],
                className="filter",
            ),
            *(
                html.Div(
                    [
                        html.Label(label, htmlFor=control_id, className="label"),
                        dcc.Dropdown(
                            id=control_id,
                            options=options,
                            value=value,
                            placeholder=placeholder,
                            clearable=True,
                        ),
                    ],
                    className="filter",
                )
                for control_id, label, options, value, placeholder in dropdowns
            ),
        ],
        className="filters",
    )


def _row(row: dict[str, Any], coverage: dict[str, Any]) -> html.Tr:
    year = row["year"]
    return html.Tr(
        [
            # A year links to its one-election view (#307).
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            html.Td(str(row["candidate"])),
            labels.party_cell(row["party"]),
            html.Td(labels.number(row["state_electoral_votes"])),
            html.Td(labels.number(row["electoral_votes"])),
            html.Td(labels.number(row["electoral_votes_counted"])),
            html.Td(
                labels.count_status(
                    row["electoral_count_status"], row["electoral_count_status_reason"]
                )
            ),
            html.Td(labels.pv_status(row["pv_status"])),
            html.Td(
                labels.popular_votes(
                    row["popular_votes"], row["pv_status"], year, coverage
                )
            ),
        ]
    )


def _per_capita_row(row: dict[str, Any]) -> html.Tr:
    year = row["year"]
    # A year links to its one-election view (#307), as in T4.
    return html.Tr(
        [
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            *labels.per_capita_cells(row),
        ]
    )


def _download(
    usps: str,
    table: str,
    name: str,
    body: dict[str, Any],
    chosen: Filters,
    span: tuple[int, int],
) -> export.Download:
    """A table's download: the file named for the view and the table, the provenance of
    the response its rows come from, and the view's URL with the filters applied."""
    search = applied_search(chosen, span)
    return export.Download(
        filename=f"state-{usps}-{table}.csv",
        name=name,
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(CANONICAL_HOST, f"/state/{usps}", search),
    )


def _per_capita_section(
    rows: list[dict[str, Any]], chosen: Filters, download: export.Download
) -> list[Any]:
    """T7: the state's persons per electoral vote, narrowed by the year range only."""
    shown = [r for r in rows if chosen.year_from <= r["year"] <= chosen.year_to]
    return [
        html.H2("People per electoral vote"),
        html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
        *components.table(
            shown,
            _per_capita_row,
            PER_CAPITA_FIELDS,
            PER_CAPITA_TABLE_ID,
            download,
            extra=PER_CAPITA_EXTRA,
            notes=(
                PER_CAPITA_FILTER_NOTE,
                labels.GOVERNING_CENSUS_NOTE,
                labels.BOUNDARY_NOTE,
            ),
        ),
        labels.glossary(PER_CAPITA_FIELDS),
    ]


def render(
    body: dict[str, Any],
    index: dict[str, Any],
    usps: str,
    pairs: list[tuple[str, str]],
    per_capita: dict[str, Any],
) -> tuple[html.Div, str]:
    """The page body and the state's name, for one ``/v1/states/{usps}`` response, the
    ``/v1/elections`` index and the state's ``/per-capita`` response (all read through
    the same view), and this page's filter pairs."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    span = query.year_span(coverage["year_min"], coverage["year_max"])
    served = _served_years(index)
    rows = _rows(body, usps, served)
    per_capita_rows = _rows(per_capita, usps, served, f"/v1/states/{usps}/per-capita")
    chosen = filters(pairs, rows, span)
    shown = select(rows, chosen)
    content = html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            _controls(rows, chosen, span),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            *components.table(
                shown,
                lambda r: _row(r, coverage),
                FIELDS,
                TABLE_ID,
                _download(usps, "history", "this state's history", body, chosen, span),
                extra=EXTRA,
                notes=(labels.PARTY_NOTE,),
            ),
            labels.glossary(GLOSSARY),
            *_per_capita_section(
                per_capita_rows,
                chosen,
                _download(
                    usps,
                    "per-capita",
                    "people per electoral vote",
                    per_capita,
                    chosen,
                    span,
                ),
            ),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )
    return content, str(rows[0]["state"])


def not_found() -> html.Div:
    """A code the dataset does not serve: said plainly, with the way back."""
    return html.Div(
        [
            html.P(NOT_FOUND_SENTENCE),
            dcc.Link("Browse every state in the dataset", href="/states"),
        ],
        id=NOT_FOUND_ID,
    )


def layout(usps: Any = None, **params: Any) -> html.Div:
    heading = "State history"
    try:
        with api.CLIENT.view() as view:
            # Validated from the roster before it is formatted (#279, D074).
            if not api.accepted(view.get, VALIDATE, {"usps": usps}):
                content = not_found()
            else:
                index = view.get(api.ELECTIONS_PATH)
                body = view.get(f"/v1/states/{usps}")
                per_capita = view.get(f"/v1/states/{usps}/per-capita")
                content, heading = render(
                    body, index, usps, parse_filters(params), per_capita
                )
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1(heading),
            html.P(
                "This state's electoral votes for each candidate in every election "
                "this dataset holds for it, with the popular vote where the dataset "
                "has it, and how many people its electoral votes stood for. Narrow "
                "the rows by year, candidate or popular-vote status.",
                className="lede",
            ),
            content,
        ]
    )
