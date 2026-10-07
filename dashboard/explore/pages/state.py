"""One state's history (#279): T4, its rows across every election it took part in.

The rows come from one response, ``/v1/states/{usps}``, filled on a miss. The state is
the path (``/state/<usps>``, an item singular as ``/states`` is plural), in upper case
as the API writes a USPS code. It is validated against the state roster before it is
formatted into an API path: the latest election's rows (``/v1/elections/{year_max}``,
:data:`explore.api.ROSTER_PATH`), since every state and DC takes part in it. That
source is declared in ``on_miss`` and built from the index's coverage, never from the
path, so a code the dataset does not serve costs at most one fill per snapshot, of the
roster itself, and 404s at the index once the roster is cached (#279, D073).

It follows the one-election view's conventions (``pages/election.py``): labels and
null cells from :mod:`explore.labels`, filters only in the query string through the
page's one parser, a filter change written to a page-local ``dcc.Location`` and
re-rendered from the cache, and the provenance footer from the response's own
``meta.provenance``. The filters are the shared year range (``year_from`` /
``year_to``), ``candidate`` (a slug) and ``pv_status``.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, labels, query
from explore.config import SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T4.
PAGE_ID = "state"
#: The wrapper of the not-found state: a code the dataset does not serve.
NOT_FOUND_ID = "state-not-found"
TABLE_ID = "state-history"
URL_ID = "state-url"
YEARS_ID = "state-years"
CANDIDATE_ID = "state-candidate"
PV_STATUS_ID = "state-pv-status"

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
    """Whether ``path_vars["usps"]`` is a state the roster's rows name.

    Pure and total: a USPS code (two ASCII capitals) equal to a row's ``state_usps`` in
    the latest election, never a literal. A malformed body names no state.
    """
    usps = path_vars.get("usps")
    if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
        return False
    return any(
        isinstance(row, dict) and row.get("state_usps") == usps
        for row in _rows_of(body)
    )


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
    description="One US state's electoral votes in every presidential election.",
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, "/v1/states/{usps}"),
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


def filters(pairs: list[tuple[str, str]], rows: list[dict[str, Any]]) -> Filters:
    """The filters to apply to this state's rows, sorted by year.

    Per parameter, as ``og:url`` is: a bound outside the state's own span falls back to
    that end of it, and a candidate absent from its rows to "all". A status is a closed
    value, so it is kept even when no row has it: an empty result is the honest answer.
    """
    year_from, year_to = query.year_range(pairs, rows[0]["year"], rows[-1]["year"])
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


def _rows(body: Any, usps: str, served: set[int]) -> list[dict[str, Any]]:
    """The state's rows sorted by year then candidate, or ``TypeError``.

    A served state always has rows, so an empty list is a malformed body: rendering it
    would show the success marker over an empty table. Each row must name this state
    and a year the index serves (checked by :func:`explore.query.checked_year`), so no
    row of another state, or of a year the dataset does not hold, is shown.
    """
    rows = _rows_of(body)
    if not rows:
        raise TypeError(f"/v1/states/{usps} carries no list of rows")
    for row in rows:
        if not isinstance(row, dict) or row.get("state_usps") != usps:
            raise TypeError(f"/v1/states/{usps} carries a row of another state")
        if query.checked_year(row.get("year")) not in served:
            raise TypeError(f"/v1/states/{usps} carries a row of no served year")
    return sorted(rows, key=lambda r: (r["year"], str(r["candidate"])))


def _options(pairs: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"label": label, "value": value}
        for value, label in sorted(pairs.items(), key=lambda kv: kv[1])
    ]


def _controls(rows: list[dict[str, Any]], chosen: Filters) -> html.Div:
    first, last = rows[0]["year"], rows[-1]["year"]
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


def render(
    body: dict[str, Any],
    index: dict[str, Any],
    usps: str,
    pairs: list[tuple[str, str]],
) -> tuple[html.Div, str]:
    """The page body and the state's name, for one ``/v1/states/{usps}`` response, the
    ``/v1/elections`` index read through the same view, and this page's filter pairs."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    rows = _rows(body, usps, _served_years(index))
    chosen = filters(pairs, rows)
    shown = select(rows, chosen)
    content = html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            _controls(rows, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([labels.header(field) for field in FIELDS])),
                        html.Tbody([_row(r, coverage) for r in shown]),
                    ],
                    id=TABLE_ID,
                ),
                # Wider than a phone: the table scrolls sideways in its box, never
                # the page.
                className="table-scroll",
            )
            if shown
            else html.P("No rows match these filters.", className="empty"),
            html.P(labels.PARTY_NOTE, className="note"),
            labels.glossary(GLOSSARY),
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
            # Validated from the roster before it is formatted (#279, D073).
            if not api.accepted(view.get, VALIDATE, {"usps": usps}):
                content = not_found()
            else:
                index = view.get(api.ELECTIONS_PATH)
                body = view.get(f"/v1/states/{usps}")
                content, heading = render(body, index, usps, parse_filters(params))
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1(heading),
            html.P(
                "This state's electoral votes for each candidate in every election it "
                "took part in, with the popular vote where this dataset has it. Narrow "
                "the rows by year, candidate or popular-vote status.",
                className="lede",
            ),
            content,
        ]
    )
