"""One election in full (#307): T2, results by state, and T3, national results.

Both tables come from one response, ``/v1/elections/{year}``, filled on a miss. The year
is the path (``/election/<year>``, an item singular as the index is plural); it is
validated from the ``/v1/elections`` the page prefetches before it is formatted into an
API path (#312), so a year the dataset does not serve is not found, at the index (404)
and in the page.

It follows the elections index's conventions (``pages/elections.py``): labels from
:mod:`explore.labels`, filters only in the query string through the page's one parser,
a filter change written to a page-local ``dcc.Location`` and re-rendered from the
cache, and the provenance footer from the response's own ``meta.provenance``. T2's
filters are the API's own query names, ``state`` (a USPS code) and ``candidate`` (a
slug), and the field names ``pv_status`` and ``electoral_count_status``. T3 is never
filtered: it is the year's national result, as the API's ``summary`` is.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, labels, query
from explore.config import SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T2.
PAGE_ID = "election"
#: The wrapper of the not-found state: a year the dataset does not serve.
NOT_FOUND_ID = "election-not-found"
STATES_TABLE_ID = "election-states"
NATION_TABLE_ID = "election-nation"
NO_PV_ID = "election-no-pv"
URL_ID = "election-url"
STATE_ID = "election-state"
CANDIDATE_ID = "election-candidate"
PV_STATUS_ID = "election-pv-status"
COUNT_STATUS_ID = "election-count-status"

#: T2's columns, in display order, by public field name.
STATE_FIELDS = (
    "state",
    "candidate",
    "party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
    "popular_votes",
)
#: The fields T2's glossary names: its columns, and the reason its count cell shows.
STATE_GLOSSARY = (*STATE_FIELDS, "electoral_count_status_reason")

#: T3's columns, in display order, by public field name.
NATION_FIELDS = (
    "candidate",
    "party",
    "national_electoral_votes",
    "national_electoral_votes_counted",
    "national_electoral_denominator",
    "electoral_rank",
    "took_office",
    "national_pv_votes",
    "ec_share_full",
    "pv_share",
)

#: The query keys this page reads: the API's own filter names for a state and a
#: candidate, and the field names of the two closed vocabularies.
STATE = "state"
CANDIDATE = "candidate"
PV_STATUS = "pv_status"
COUNT_STATUS = "electoral_count_status"

#: The year's popular-vote sentence above T3, when the dataset holds none for it.
NO_PV_SENTENCE = (
    "This dataset has no popular vote for {year}; it covers {first}–{last}."
)

#: The not-found state's sentence. The raw path value is never echoed.
NOT_FOUND_SENTENCE = "This dataset has no presidential election for that year."


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``.
    Keeps ``state`` only as a USPS code, ``candidate`` only as a slug, and the two
    statuses only as one of their closed values; a key repeated with differing values
    is dropped, and so is a key it does not know. Never emits ``year``, the path
    variable. Whether a state or candidate is in this year's results is the layout's
    question (:func:`filters`).
    """
    if not isinstance(params, dict):
        return []
    kept: dict[str, str] = {}
    state = query.single(params.get(STATE))
    if state is not None and query.USPS_RE.fullmatch(state):
        kept[STATE] = state
    candidate = query.single(params.get(CANDIDATE))
    if candidate is not None and query.is_slug(candidate):
        kept[CANDIDATE] = candidate
    pv_status = query.single(params.get(PV_STATUS))
    if pv_status in labels.PV_STATUS:
        kept[PV_STATUS] = pv_status
    count_status = query.single(params.get(COUNT_STATUS))
    if count_status in labels.COUNT_STATUS:
        kept[COUNT_STATUS] = count_status
    return sorted(kept.items())


def _year_rows(body: Any) -> list[Any]:
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else []


def _row_year(row: Any) -> int | None:
    year = row.get("year") if isinstance(row, dict) else None
    return year if isinstance(year, int) and not isinstance(year, bool) else None


def served_year(path_vars: dict[str, Any], body: Any) -> bool:
    """Whether ``path_vars["year"]`` is a year ``/v1/elections`` serves.

    Pure and total: four ASCII digits, equal to an integer row year in the index,
    never a literal. A malformed body serves nothing.
    """
    year = path_vars.get("year")
    if not isinstance(year, str) or not query.YEAR_RE.fullmatch(year):
        return False
    return any(_row_year(row) == int(year) for row in _year_rows(body))


VALIDATE: api.Validate = (api.ELECTIONS_PATH, served_year)


def title(year: Any = None, **_vars: Any) -> str:
    """The page title. Called by Dash at index time with the **unvalidated** path
    variable, so it is total and reads no API; it names the year only when the year
    is four ASCII digits."""
    if isinstance(year, str) and query.YEAR_RE.fullmatch(year):
        return f"The {year} election — {SITE_TITLE}"
    return f"Election — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template="/election/<year>",
    title=title,
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description="One US presidential election: results by state and nationally.",
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=("/v1/elections/{year}",),
    success=PAGE_ID,
    validate=VALIDATE,
    query=parse_filters,
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
    state = given.get(STATE)
    candidate = given.get(CANDIDATE)
    return Filters(
        state=state if any(r["state_usps"] == state for r in rows) else None,
        candidate=(
            candidate if any(r["candidate_slug"] == candidate for r in rows) else None
        ),
        pv_status=given.get(PV_STATUS),
        count_status=given.get(COUNT_STATUS),
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
            (STATE, state),
            (CANDIDATE, candidate),
            (PV_STATUS, pv_status),
            (COUNT_STATUS, count_status),
        )
        if isinstance(value, str) and value
    }
    return query.encode_search(parse_filters(params))


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
        (STATE_ID, "State", _options(states), chosen.state, "All states"),
        (
            CANDIDATE_ID,
            "Candidate",
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


def _party_cell(value: Any) -> html.Td:
    if value is None:
        return html.Td(labels.NOT_IN_DATASET, title=labels.PARTY_NOTE)
    return html.Td(str(value))


def _state_row(row: dict[str, Any], coverage: dict[str, Any]) -> html.Tr:
    return html.Tr(
        [
            html.Td(str(row["state"])),
            html.Td(str(row["candidate"])),
            _party_cell(row["party"]),
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
                    row["popular_votes"], row["pv_status"], row["year"], coverage
                )
            ),
        ]
    )


def _national_pv(value: Any, has_popular_vote: bool, as_share: bool) -> str:
    if not has_popular_vote:
        return labels.NOT_IN_DATASET
    if value is None:
        return labels.NO_NATIONAL_FIGURE
    return labels.share(value) if as_share else labels.number(value)


def _nation_row(row: dict[str, Any], has_popular_vote: bool) -> html.Tr:
    return html.Tr(
        [
            html.Td(str(row["candidate"])),
            _party_cell(row["party"]),
            html.Td(labels.number(row["national_electoral_votes"])),
            html.Td(labels.number(row["national_electoral_votes_counted"])),
            html.Td(labels.number(row["national_electoral_denominator"])),
            html.Td(labels.number(row["electoral_rank"])),
            html.Td(labels.yes_no(row["took_office"])),
            html.Td(_national_pv(row["national_pv_votes"], has_popular_vote, False)),
            html.Td(labels.share(row["ec_share_full"])),
            html.Td(_national_pv(row["pv_share"], has_popular_vote, True)),
        ]
    )


def _table(fields: tuple[str, ...], rows: list[html.Tr], table_id: str) -> html.Div:
    # Wider than a phone: the table scrolls sideways inside its box, the page never.
    return html.Div(
        html.Table(
            [
                html.Thead(html.Tr([labels.header(field) for field in fields])),
                html.Tbody(rows),
            ],
            id=table_id,
        ),
        className="table-scroll",
    )


def _list(value: Any, name: str) -> list[Any]:
    # A served year always has rows: anything else is a malformed body, and rendering
    # it would show the success marker over empty tables.
    if not isinstance(value, list) or not value:
        raise TypeError(f"/v1/elections/{{year}} carries no list of {name}")
    return value


def render(
    body: dict[str, Any], index_row: dict[str, Any], pairs: list[tuple[str, str]]
) -> html.Div:
    """The page body for one ``/v1/elections/{year}`` response, the year's row of
    ``/v1/elections`` (read through the same view), and this page's filter pairs."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    year = _row_year(index_row)
    if year is None or body["election"]["year"] != year:
        raise TypeError("the response is not the requested year's")
    rows = _list(body["data"], "state rows")
    summary = _list(body["summary"], "candidates")
    has_popular_vote = index_row["has_popular_vote"] is True
    chosen = filters(pairs, rows)
    shown = select(rows, chosen)
    nation: list[Any] = [html.H2("National results")]
    if not has_popular_vote:
        nation.append(
            html.P(
                NO_PV_SENTENCE.format(
                    year=year,
                    first=coverage["pv_year_min"],
                    last=coverage["pv_year_max"],
                ),
                id=NO_PV_ID,
                className="note",
            )
        )
    nation += [
        _table(
            NATION_FIELDS,
            [_nation_row(r, has_popular_vote) for r in summary],
            NATION_TABLE_ID,
        ),
        html.P(labels.PARTY_NOTE, className="note"),
        labels.glossary(NATION_FIELDS),
    ]
    return html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            html.H2("Results by state"),
            _controls(rows, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            _table(
                STATE_FIELDS,
                [_state_row(r, coverage) for r in shown],
                STATES_TABLE_ID,
            )
            if shown
            else html.P("No rows match these filters.", className="empty"),
            html.P(labels.PARTY_NOTE, className="note"),
            labels.glossary(STATE_GLOSSARY),
            *nation,
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def index_row(index: dict[str, Any], year: str) -> dict[str, Any]:
    """The year's row of ``/v1/elections``; ``KeyError`` if it has none."""
    for row in _year_rows(index):
        if _row_year(row) == int(year):
            return dict(row)
    raise KeyError(year)


def not_found() -> html.Div:
    """A year the dataset does not serve: said plainly, with the way back."""
    return html.Div(
        [
            html.P(NOT_FOUND_SENTENCE),
            dcc.Link("Browse every election in the dataset", href="/elections"),
        ],
        id=NOT_FOUND_ID,
    )


def layout(year: Any = None, **params: Any) -> html.Div:
    heading = "Election"
    try:
        with api.CLIENT.view() as view:
            # Validated from the prefetched index before it is formatted (#312).
            if not api.accepted(view.get, VALIDATE, {"year": year}):
                content = not_found()
            else:
                body = view.get(f"/v1/elections/{year}")
                index = view.get(api.ELECTIONS_PATH)
                content = render(body, index_row(index, year), parse_filters(params))
                heading = f"The {year} election"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1(heading),
            html.P(
                "Every state's electoral votes for each candidate, with the popular "
                "vote where this dataset has it, and the national result. Narrow the "
                "state results by state, candidate or status.",
                className="lede",
            ),
            content,
        ]
    )
