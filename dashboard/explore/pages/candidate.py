"""One candidate's history (#331): T5, their rows, state by state, in every election in
which they received at least one electoral vote.

T5 comes from one response, ``/v1/candidates/{slug}``, filled on a miss. The candidate
is the path (``/candidate/<slug>``, an item singular), as the API writes a slug. It is
validated against the candidate index, :data:`explore.api.CANDIDATES_PATH` (#330),
before it is formatted into an API path: a literal source declared in ``on_miss``
(D074(ii)), so a slug the index does not list never fills a path built from it, costs
at most a fill of the shared index, and 404s at the index once the index is cached.
The match is exact: a slug in another letter case is not found, as ``/state/ga`` is
(#279), so only a slug the index itself lists is ever a fill or a cache key (D073).

It follows the state history's conventions (``pages/state.py``): labels and null cells
from :mod:`explore.labels`, filters only in the query string through the page's one
parser, a filter change written to a page-local ``dcc.Location`` and re-rendered from
the cache, the provenance footer from the response's own ``meta.provenance``, and the
table through :func:`explore.components.table`, which offers its rows as a CSV (#309).
The filters are one election year and ``state``. The year is a single choice among the
candidate's own election years (:func:`explore.components.year_buttons`, the owner's
choice at #331's plan gate, over the state page's slider), carried in the shared keys as
``year_from`` = ``year_to``, and not shown for a candidate with one election year.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T5.
PAGE_ID = "candidate"
#: The wrapper of the not-found state: a slug the candidate index does not list.
NOT_FOUND_ID = "candidate-not-found"
TABLE_ID = "candidate-history"
URL_ID = "candidate-url"
YEAR_ID = "candidate-year"
STATE_ID = "candidate-state"

#: T5's columns, in display order, by public field name.
FIELDS = (
    "year",
    "state",
    "nominating_party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
    "popular_votes",
)
#: The fields T5's column-name list names: its columns, the reason its count cell
#: shows, and the party note its Party notes list shows (#389).
GLOSSARY = (*FIELDS, "electoral_count_status_reason", "nominating_party_note")
#: What T5's CSV adds after its columns (#309): the reason its count cell shows, the
#: party note and the party's per-row source (#389), and the keys its state filter and
#: its candidate are named by.
EXTRA = (
    "electoral_count_status_reason",
    "nominating_party_note",
    "nominating_party_source",
    "state_usps",
    "candidate_slug",
)

#: The query key this page reads besides the shared year keys: the API's state filter.
STATE = "state"

#: The generic heading, before a candidate's name is known (not found, degraded).
HEADING = "Candidate history"
#: The not-found state's sentence. True for a listed slug in another letter case too, so
#: it never says the dataset lacks the candidate; the raw path value is never echoed.
NOT_FOUND_SENTENCE = "This link does not match any candidate in this dataset."
NOT_FOUND_LINK = "Browse every election to find a candidate"
#: The lede, then, on a successful render only, the sentence naming the filters it
#: shows.
LEDE = (
    "This candidate's electoral votes, state by state, in every election in which they "
    "received at least one, with the popular vote where this dataset has it. A state "
    "whose electors cast none for them shows 0; an election in which they received "
    "none is not listed."
)
FILTER_SENTENCE = "Narrow the rows to one election year, one state, or both."
FILTER_SENTENCE_ONE_YEAR = "Narrow the rows to one state."
#: The year control's first option, every one of the candidate's election years.
ALL_YEARS = "All years"
STATE_PLACEHOLDER = "All states"


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``.
    Keeps the year keys only as one year, ``year_from`` = ``year_to``, each as
    :func:`explore.query.parse_year_range` keeps it: a range or a lone bound names no
    view this page shows, so both keys are dropped. ``state`` is kept only as a USPS
    code; a key repeated with differing values is dropped, and so is a key it does not
    know. Never emits ``slug``, the path variable. Whether the year or the state is in
    this candidate's rows is the layout's question (:func:`filters`).
    """
    if not isinstance(params, dict):
        return []
    kept = query.parse_year_range(params)
    if kept.get("year_from") != kept.get("year_to"):
        kept.pop("year_from", None)
        kept.pop("year_to", None)
    state = query.single(params.get(STATE))
    if state is not None and query.USPS_RE.fullmatch(state):
        kept[STATE] = state
    return sorted(kept.items())


def _rows_of(body: Any) -> list[Any]:
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else []


def listed(body: Any) -> set[str]:
    """The slugs the candidate index lists, read all or nothing.

    One item that is not an object whose ``candidate_slug`` is a slug
    (:func:`explore.query.is_slug`) makes the index name no slug, as
    :func:`explore.api.roster` refuses a roster with one bad row: a listed value is
    formatted into an API path, so it is checked as a path variable is.
    """
    items = _rows_of(body)
    if not items or not all(
        isinstance(item, dict)
        and isinstance(slug := item.get("candidate_slug"), str)
        and query.is_slug(slug)
        for item in items
    ):
        return set()
    return {item["candidate_slug"] for item in items}


def on_index(path_vars: dict[str, Any], body: Any) -> bool:
    """Whether ``path_vars["slug"]`` is a slug the candidate index lists.

    Pure and total: a slug (:func:`explore.query.is_slug`) that is exactly one of the
    index's own, never a literal. No letter case is folded.
    """
    slug = path_vars.get("slug")
    if not isinstance(slug, str) or not query.is_slug(slug):
        return False
    return slug in listed(body)


VALIDATE: api.Validate = (api.CANDIDATES_PATH, on_index)


def title(**_vars: Any) -> str:
    """The page title. Called by Dash at index time with the **unvalidated** path
    variable, so it is total and reads no API; no name can be told from a slug, so it
    names no candidate."""
    return f"{HEADING} — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template="/candidate/<slug>",
    title=title,
    # No names: the index HTML never waits on the API, so this cannot read the slug.
    description=(
        "One US presidential candidate's electoral votes, state by state, in every "
        "election in this dataset where they received any."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.CANDIDATES_PATH, "/v1/candidates/{slug}"),
    success=PAGE_ID,
    validate=VALIDATE,
    query=parse_filters,
)


class Filters(NamedTuple):
    """The filters a render applies; ``None`` is "all".

    A ``NamedTuple``, not a dataclass: Dash executes a page module before it is in
    ``sys.modules``, which ``dataclass`` needs.
    """

    year: int | None
    state: str | None


def _years(rows: list[dict[str, Any]]) -> list[int]:
    return sorted({r["year"] for r in rows})


def filters(
    pairs: list[tuple[str, str]], rows: list[dict[str, Any]], years: list[int]
) -> Filters:
    """The filters to apply to this candidate's rows, whose election years are
    ``years``.

    Per parameter, as ``og:url`` is. A year is applied only as one of the candidate's
    own election years, written ``year_from`` = ``year_to``; any other pair (a range,
    one bound, a year they received no electoral vote in) falls back to every year. A
    state absent from their rows falls back to "all".
    """
    given = dict(pairs)
    year_from, year_to = given.get("year_from"), given.get("year_to")
    year = None
    if year_from is not None and year_from == year_to:
        candidate_year = int(year_from)
        if candidate_year in years:
            year = candidate_year
    state = given.get(STATE)
    return Filters(
        year=year,
        state=state if any(r["state_usps"] == state for r in rows) else None,
    )


def select(rows: list[dict[str, Any]], chosen: Filters) -> list[dict[str, Any]]:
    """The rows T5 shows: pure, and separate from building the table."""
    return [
        r
        for r in rows
        if chosen.year in (None, r["year"]) and chosen.state in (None, r["state_usps"])
    ]


def search_for(year: Any, state: Any) -> str:
    """The query string for the controls' values, in the normal form ``og:url`` uses
    (``""`` or ``?…``). Every year and a cleared control are omitted."""
    params: dict[str, Any] = {}
    if isinstance(year, str) and year:
        params["year_from"] = params["year_to"] = year
    if isinstance(state, str) and state:
        params[STATE] = state
    return query.encode_search(parse_filters(params))


def applied_search(chosen: Filters) -> str:
    """The filters a render applied, in the normal form :func:`search_for` writes:
    already checked, so they are encoded without the parser."""
    params: dict[str, str] = {}
    if chosen.year is not None:
        params["year_from"] = params["year_to"] = str(chosen.year)
    if chosen.state:
        params[STATE] = chosen.state
    return query.encode_search(sorted(params.items()))


@callback(
    Output(URL_ID, "search"),
    Input(YEAR_ID, "value"),
    Input(STATE_ID, "value"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(year: Any, state: Any, current: Any) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. An unchanged search is left alone.
    """
    search = search_for(year, state)
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


def _rows(body: Any, slug: str, served: set[int]) -> list[dict[str, Any]]:
    """The candidate's rows, sorted by year then state, or ``TypeError``.

    A listed candidate always has rows, so an empty list is a malformed body: rendering
    it would show the success marker over an empty table. Each row must name this
    candidate, a year ``/v1/elections`` serves (checked by
    :func:`explore.query.checked_year`) and a USPS code, which the state filter offers.
    """
    path = f"/v1/candidates/{slug}"
    rows = _rows_of(body)
    if not rows:
        raise TypeError(f"{path} carries no list of rows")
    for row in rows:
        if not isinstance(row, dict) or row.get("candidate_slug") != slug:
            raise TypeError(f"{path} carries a row of another candidate")
        if query.checked_year(row.get("year")) not in served:
            raise TypeError(f"{path} carries a row of no served year")
        usps = row.get("state_usps")
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError(f"{path} carries a row with no state code")
    return sorted(rows, key=lambda r: (r["year"], str(r.get("state", ""))))


def _controls(
    rows: list[dict[str, Any]], years: list[int], several: bool, chosen: Filters
) -> html.Div:
    states = {r["state_usps"]: str(r["state"]) for r in rows}
    return html.Div(
        [
            components.year_buttons(
                YEAR_ID,
                labels.LABELS["year"],
                ALL_YEARS,
                years,
                chosen.year,
                hidden=not several,
            ),
            html.Div(
                [
                    html.Label(
                        labels.LABELS[STATE], htmlFor=STATE_ID, className="label"
                    ),
                    dcc.Dropdown(
                        id=STATE_ID,
                        options=[
                            {"label": label, "value": value}
                            for value, label in sorted(
                                states.items(), key=lambda kv: kv[1]
                            )
                        ],
                        value=chosen.state,
                        placeholder=STATE_PLACEHOLDER,
                        clearable=True,
                    ),
                ],
                className="filter",
            ),
        ],
        className="filters",
    )


def _row(row: dict[str, Any], coverage: dict[str, Any]) -> html.Tr:
    year = row["year"]
    return html.Tr(
        [
            # A year links to its one-election view (#307), a state to its history.
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            components.state_cell(row),
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


def render(
    body: dict[str, Any], index: dict[str, Any], slug: str, pairs: list[tuple[str, str]]
) -> tuple[html.Div, str, bool]:
    """The page body, the heading and whether the year control is shown, for one
    ``/v1/candidates/{slug}`` response and the ``/v1/elections`` index (both read
    through the same view), and this page's filter pairs."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    rows = _rows(body, slug, _served_years(index))
    years = _years(rows)
    # One decision, read by the year control and by the lede alike.
    several = len(years) > 1
    chosen = filters(pairs, rows, years)
    shown = select(rows, chosen)
    download = export.Download(
        filename=f"candidate-{slug}-history.csv",
        name="this candidate's history",
        provenance=provenance,
        view_url=export.view_url(
            CANONICAL_HOST, f"/candidate/{slug}", applied_search(chosen)
        ),
    )
    content = html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            _controls(rows, years, several, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            *components.table(
                shown,
                lambda r: _row(r, coverage),
                FIELDS,
                TABLE_ID,
                download,
                extra=EXTRA,
                notes=(labels.PARTY_NOTE, labels.PARTY_NULL_NOTE),
            ),
            *labels.party_notes(shown),
            labels.glossary(GLOSSARY),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )
    name = rows[0]["candidate"]
    heading = name if isinstance(name, str) and name.strip() else HEADING
    return content, heading, several


def not_found() -> html.Div:
    """A slug the index does not list: said plainly, with the way back."""
    return html.Div(
        [
            html.P(NOT_FOUND_SENTENCE),
            dcc.Link(NOT_FOUND_LINK, href="/elections"),
        ],
        id=NOT_FOUND_ID,
    )


def layout(slug: Any = None, **params: Any) -> html.Div:
    heading = HEADING
    # The filter sentence only above the filters: not on the not-found or degraded
    # state, which show none.
    lede = LEDE
    try:
        with api.CLIENT.view() as view:
            # Validated against the candidate index before it is formatted (#331, D073).
            if not api.accepted(view.get, VALIDATE, {"slug": slug}):
                content = not_found()
            else:
                index = view.get(api.ELECTIONS_PATH)
                body = view.get(f"/v1/candidates/{slug}")
                content, heading, several = render(
                    body, index, slug, parse_filters(params)
                )
                sentence = FILTER_SENTENCE if several else FILTER_SENTENCE_ONE_YEAR
                lede = f"{LEDE} {sentence}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div([html.H1(heading), html.P(lede, className="lede"), content])
