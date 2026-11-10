"""One election's results by state (#307, #465): T2, every state's electoral votes for
each candidate, with the popular vote where the dataset has it, at
``/election/<year>/states``.

Split out of the one-election view by #465 (the overview is ``pages/election.py``;
the shared pieces are in :mod:`explore.election_view`). It reads
``/v1/elections/{year}``, the same response as the overview, filled on a miss: reached
from the overview it makes no request, and cold, one. T2's filters are the API's own
query names, ``state`` (a USPS code) and ``candidate`` (a slug), and the field names
``pv_status`` and ``electoral_count_status``, read by the page's one parser
(:func:`explore.election_view.parse_filters`); a filter change is written to a
page-local ``dcc.Location`` and re-rendered from the cache. A state or candidate absent
that year falls back to no filter, while a status is kept even when nothing matches.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, election_view, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T2.
PAGE_ID = "election-states-page"
#: The wrapper of the not-found state: a year the dataset does not serve.
NOT_FOUND_ID = "election-states-not-found"
STATES_TABLE_ID = "election-states"
URL_ID = "election-url"
STATE_ID = "election-state"
CANDIDATE_ID = "election-candidate"
PV_STATUS_ID = "election-pv-status"
COUNT_STATUS_ID = "election-count-status"

#: T2's columns, in display order, by public field name.
STATE_FIELDS = (
    "state",
    "candidate",
    "nominating_party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
    "popular_votes",
)
#: The fields T2's glossary names: its columns, the reason its count cell shows, and the
#: party note its Party notes list shows (#389).
STATE_GLOSSARY = (
    *STATE_FIELDS,
    "electoral_count_status_reason",
    "nominating_party_note",
)
#: What T2's CSV adds after its columns (#309): the reason its count cell shows, the
#: party note and the party's per-row source (#389), and the keys its filters and its
#: year are named by.
STATE_EXTRA = (
    "electoral_count_status_reason",
    "nominating_party_note",
    "nominating_party_source",
    "state_usps",
    "candidate_slug",
    "year",
)

#: The not-found state (#325), shared by the three election pages (#465).
NOT_FOUND = api.NotFound(
    labels.ELECTION_NOT_FOUND_HEADING, labels.ELECTION_NOT_FOUND_SENTENCE
)

#: The page's heading, its title before the site title, and before a year is checked,
#: or on the degraded state, its heading without a year (ba spec, approved at #465's
#: plan gate, 2026-11-10). Year first, so browser tabs still tell years apart.
STATES_HEADING = "The {year} election: results by state"
STATES_GENERIC_HEADING = "Election: results by state"
#: The lede, then, on a successful render only, the sentence naming the filters it
#: offers (#324, #419's rule): the not-found and degraded states have no filters.
LEDE = (
    "Every state's electoral votes for each candidate, with the popular vote where "
    "this dataset has it, and whether Congress counted them."
)
FILTER_SENTENCE = (
    "Narrow the rows by state, candidate, popular-vote status or count status."
)

VALIDATE: api.Validate = (api.ELECTIONS_PATH, election_view.served_year)


def title(year: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a year the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the year only when the year is four ASCII digits."""
    if isinstance(year, str) and query.YEAR_RE.fullmatch(year):
        return f"{STATES_HEADING.format(year=year)} — {SITE_TITLE}"
    return f"{STATES_GENERIC_HEADING} — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template=election_view.template(election_view.STATES),
    # Before the overview, whose greedy ``<year>`` would capture ``1824/states``:
    # Dash's router takes the first page in registry order that matches, and an
    # ordered page sorts before every unordered one (#465).
    order=0,
    title=title,
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description=(
        "One US presidential election, state by state: each state's electoral votes "
        "for each candidate, with the popular vote where the dataset has it."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=("/v1/elections/{year}",),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=election_view.parse_filters,
    nav="elections",
)


class Filters(NamedTuple):
    """The filters a render applies; ``None`` is "all".

    A ``NamedTuple``, not a dataclass: Dash executes a page module before it is in
    ``sys.modules``, which ``dataclass`` needs.
    """

    state: str | None
    candidate: str | None
    pv_status: str | None
    count_status: str | None


def filters(pairs: list[tuple[str, str]], rows: list[dict[str, Any]]) -> Filters:
    """The filters to apply to this year's rows.

    Per parameter, as ``og:url`` is: a state or candidate this year's results do not
    name falls back to "all" (``og:url`` keeps it, as the index keeps an out-of-span
    year). A status is a closed value, so it is kept even when no row has it: an empty
    result is the honest answer.
    """
    given = dict(pairs)
    state = given.get(election_view.STATE)
    candidate = given.get(election_view.CANDIDATE)
    return Filters(
        state=state if any(r["state_usps"] == state for r in rows) else None,
        candidate=(
            candidate if any(r["candidate_slug"] == candidate for r in rows) else None
        ),
        pv_status=given.get(election_view.PV_STATUS),
        count_status=given.get(election_view.COUNT_STATUS),
    )


def select(rows: list[dict[str, Any]], chosen: Filters) -> list[dict[str, Any]]:
    """The rows T2 shows: pure, and separate from building the table."""
    return [
        r
        for r in rows
        if chosen.state in (None, r["state_usps"])
        and chosen.candidate in (None, r["candidate_slug"])
        and chosen.pv_status in (None, r["pv_status"])
        and chosen.count_status in (None, r["electoral_count_status"])
    ]


def search_for(state: Any, candidate: Any, pv_status: Any, count_status: Any) -> str:
    """The query string for the controls' values, in the normal form ``og:url`` uses
    (``""`` or ``?…``). A cleared control is "all" and is omitted."""
    params = {
        key: value
        for key, value in (
            (election_view.STATE, state),
            (election_view.CANDIDATE, candidate),
            (election_view.PV_STATUS, pv_status),
            (election_view.COUNT_STATUS, count_status),
        )
        if isinstance(value, str) and value
    }
    return query.encode_search(election_view.parse_filters(params))


def applied_search(chosen: Filters) -> str:
    """The filters a render applied, in the normal form :func:`search_for` writes:
    already checked, so they are encoded without the parser."""
    keys = election_view.STATES_KEYS
    return query.encode_search(
        (key, value) for key, value in zip(keys, chosen, strict=True) if value
    )


@callback(
    Output(URL_ID, "search"),
    Input(STATE_ID, "value"),
    Input(CANDIDATE_ID, "value"),
    Input(PV_STATUS_ID, "value"),
    Input(COUNT_STATUS_ID, "value"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(
    state: Any, candidate: Any, pv_status: Any, count_status: Any, current: Any
) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. An unchanged search is left alone.
    """
    search = search_for(state, candidate, pv_status, count_status)
    return no_update if search == (current or "") else search


def _options(pairs: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"label": label, "value": value}
        for value, label in sorted(pairs.items(), key=lambda kv: kv[1])
    ]


def _controls(rows: list[dict[str, Any]], chosen: Filters) -> html.Div:
    states = {r["state_usps"]: r["state"] for r in rows}
    candidates = {r["candidate_slug"]: r["candidate"] for r in rows}
    dropdowns = (
        (
            STATE_ID,
            labels.LABELS[election_view.STATE],
            _options(states),
            chosen.state,
            "All states",
        ),
        (
            CANDIDATE_ID,
            labels.LABELS[election_view.CANDIDATE],
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
        (
            COUNT_STATUS_ID,
            labels.LABELS["electoral_count_status"],
            [{"label": v[0], "value": k} for k, v in labels.COUNT_STATUS.items()],
            chosen.count_status,
            "Any",
        ),
    )
    return html.Div(
        [
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
        ],
        className="filters",
    )


def _state_row(row: dict[str, Any], year: int, coverage: dict[str, Any]) -> html.Tr:
    return html.Tr(
        [
            components.state_cell(row),
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


def _download(year: int, body: dict[str, Any], chosen: Filters) -> export.Download:
    """T2's download: the file named for the view and the table, the provenance of the
    response its rows come from, and this page's URL with the filters applied."""
    return export.Download(
        filename=f"election-{year}-by-state.csv",
        name="the results by state",
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST,
            election_view.path(year, election_view.STATES),
            applied_search(chosen),
        ),
    )


def render(
    body: dict[str, Any],
    index_row: dict[str, Any],
    pairs: list[tuple[str, str]],
    around: election_view.Neighbours,
) -> html.Div:
    """The page body for one ``/v1/elections/{year}`` response, the year's row of
    ``/v1/elections`` (read through the same view), this page's filter pairs and the
    year's served neighbours: the earlier and later links, the heading, the lede with
    its filter sentence, the section links, T2 and its filters, and the footer."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    # The popular-vote window, checked once before any cell reads it (#308).
    query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
    year = election_view.row_year(index_row)
    if year is None:
        raise TypeError("the index row names no year")
    rows = election_view.rows(body["data"], year, "state rows", f"/v1/elections/{year}")
    chosen = filters(pairs, rows)
    shown = select(rows, chosen)
    return html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            *election_view.neighbor_nav(around, election_view.STATES),
            html.H1(STATES_HEADING.format(year=year)),
            html.P(f"{LEDE} {FILTER_SENTENCE}", className="lede"),
            election_view.section_nav(year, election_view.STATES),
            _controls(rows, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            *components.table(
                shown,
                lambda r: _state_row(r, year, coverage),
                STATE_FIELDS,
                STATES_TABLE_ID,
                _download(year, body, chosen),
                extra=STATE_EXTRA,
                notes=(labels.PARTY_NOTE, labels.PARTY_NULL_NOTE),
            ),
            *labels.party_notes(shown),
            labels.glossary(STATE_GLOSSARY),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(year: Any = None, **params: Any) -> html.Div:
    """The results by state. On success, :func:`render`'s body is the whole page. The
    not-found and degraded states get their heading here, heading first, and the
    degraded state its lede, without the filter sentence."""
    heading = STATES_GENERIC_HEADING
    lede: str | None = LEDE
    try:
        with api.CLIENT.view() as view:
            # Validated from the prefetched index before it is formatted (#312).
            if not api.accepted(view.get, VALIDATE, {"year": year}):
                heading, lede = labels.ELECTION_NOT_FOUND_HEADING, None
                content = election_view.not_found(NOT_FOUND_ID)
            else:
                body = view.get(f"/v1/elections/{year}")
                index = view.get(api.ELECTIONS_PATH)
                return render(
                    body,
                    election_view.index_row(index, year),
                    election_view.parse_filters(params),
                    election_view.neighbours(index, int(year)),
                )
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
