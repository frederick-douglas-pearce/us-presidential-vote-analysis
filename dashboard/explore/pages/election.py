"""One election in full (#307): the election panel (#308), the winner under each
method, T2, results by state, T3, national results, and T6, every state's persons per
electoral vote (#280).

The panel, T2 and T3 come from one response, ``/v1/elections/{year}`` (its
``election`` block, ``data`` and ``summary``), and T6 from a second,
``/v1/elections/{year}/per-capita``; both are filled on a miss, in the same render, so
the page's success marker renders only when the panel (or, where the API serves
``election: null``, the panel's unavailable sentence) and all three tables did. The year
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
filtered: it is the year's national result, as the API's ``summary`` is. T6 is narrowed
by the same ``state`` filter, as T2 resolves it, and by nothing else. The panel is
never filtered either.
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
PER_CAPITA_TABLE_ID = "election-per-capita"
PANEL_ID = "election-panel"
#: The panel's place when the API serves ``election: null`` (a build gap).
PANEL_UNAVAILABLE_ID = "election-panel-unavailable"
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
    "ec_share_hybrid",
    "hybrid_score",
)

#: The election panel's fields, in display order, by public field name (#308): who led
#: under each method, whether either other method changes the winner, the three
#: margins, whether anyone won a majority of electors, and the share of electors
#: appointed by states that held a popular vote.
PANEL_FIELDS = (
    "ec_winner",
    "pv_winner",
    "hybrid_winner",
    "pv_flip",
    "hybrid_flip",
    "ec_margin",
    "pv_margin",
    "hybrid_margin",
    "ec_determinative",
    "pv_coverage",
)

#: The panel's sentence when the API serves no ``election`` block for the year.
PANEL_UNAVAILABLE = "The comparison across methods is not available for this year."

#: T6's columns, in display order, by public field name (#280).
PER_CAPITA_FIELDS = ("state", *labels.PER_CAPITA_FIELDS)

#: Which of the page's filters T6 follows: the state, and not the others.
PER_CAPITA_FILTER_NOTE = (
    "The state filter above applies to this table; the candidate and status filters "
    "do not."
)

#: The query keys this page reads: the API's own filter names for a state and a
#: candidate, and the field names of the two closed vocabularies.
STATE = "state"
CANDIDATE = "candidate"
PV_STATUS = "pv_status"
COUNT_STATUS = "electoral_count_status"

#: The year's popular-vote sentence above T3, when the dataset holds none for it.
NO_PV_SENTENCE = (
    "This dataset has no popular vote for {year}; its popular-vote figures cover "
    "{first}–{last}."
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
    return query.checked_year(row.get("year")) if isinstance(row, dict) else None


def served_year(path_vars: dict[str, Any], body: Any) -> bool:
    """Whether ``path_vars["year"]`` is a year ``/v1/elections`` serves.

    Pure and total: four ASCII digits, equal to a row year of the index (each checked
    by :func:`explore.query.checked_year`), never a literal. A malformed body serves
    nothing.
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
    on_miss=("/v1/elections/{year}", "/v1/elections/{year}/per-capita"),
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
        (STATE_ID, labels.LABELS[STATE], _options(states), chosen.state, "All states"),
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


def _state_cell(row: dict[str, Any]) -> html.Td:
    """The state's name, linked to its history (#279) when its code is a USPS code."""
    usps = row["state_usps"]
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return html.Td(dcc.Link(str(row["state"]), href=f"/state/{usps}"))
    return html.Td(str(row["state"]))


def _state_row(row: dict[str, Any], year: int, coverage: dict[str, Any]) -> html.Tr:
    return html.Tr(
        [
            _state_cell(row),
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


def _national_pv(
    value: Any,
    has_popular_vote: bool,
    as_share: bool,
    missing: str = labels.NOT_IN_DATASET,
) -> str:
    """A T3 cell that needs the popular vote: ``missing`` in a year with no popular
    vote (T3's year rule, from the index row), and inside it a null is a candidate
    with no popular-vote figure."""
    if not has_popular_vote:
        return missing
    if value is None:
        return labels.NO_NATIONAL_FIGURE
    return labels.share(value) if as_share else labels.number(value)


def _nation_row(row: dict[str, Any], has_popular_vote: bool) -> html.Tr:
    return html.Tr(
        [
            html.Td(str(row["candidate"])),
            labels.party_cell(row["party"]),
            html.Td(labels.number(row["national_electoral_votes"])),
            html.Td(labels.number(row["national_electoral_votes_counted"])),
            html.Td(labels.number(row["national_electoral_denominator"])),
            html.Td(labels.number(row["electoral_rank"])),
            html.Td(labels.yes_no(row["took_office"])),
            html.Td(_national_pv(row["national_pv_votes"], has_popular_vote, False)),
            # Nullable in the API's schema, though real for every served year.
            html.Td(labels.share_cell(row["ec_share_full"])),
            html.Td(_national_pv(row["pv_share"], has_popular_vote, True)),
            html.Td(labels.share_cell(row["ec_share_hybrid"])),
            # The hybrid's own wording (#308), on T3's year rule so the row agrees.
            html.Td(
                _national_pv(
                    row["hybrid_score"], has_popular_vote, True, labels.NOT_APPLICABLE
                )
            ),
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


def _rows(value: Any, year: int, name: str, path: str | None = None) -> list[Any]:
    """A non-empty list of the year's rows from ``path`` (``/v1/elections/{year}`` by
    default), each naming that year, or ``TypeError``.

    A served year always has state rows, and the API treats a year with no national
    summary as a build regression, so an empty list is a malformed body: rendering it
    would show the success marker over an empty table. Each row's year is checked
    against the validated one, so no row of another year (or of no year) is shown,
    and the cells read the validated year rather than the row's.
    """
    path = path or f"/v1/elections/{year}"
    if not isinstance(value, list) or not value:
        raise TypeError(f"{path} carries no list of {name}")
    if any(_row_year(row) != year for row in value):
        raise TypeError(f"{path} carries {name} of another year")
    return value


def _election(value: Any, year: int) -> dict[str, Any] | None:
    """The year's ``election`` block, ``None`` where the API serves none, or
    ``TypeError``.

    The API serves ``election: null`` on a build gap while the rows beside it stay
    correct, so a null is the panel's own unavailable state, never the page's. Any
    other shape, or a block naming another year (checked as :func:`_rows` checks a
    row's), is a malformed body.
    """
    if value is None:
        return None
    if not isinstance(value, dict) or _row_year(value) != year:
        raise TypeError(f"/v1/elections/{year} carries no election block of that year")
    return value


def _panel_cells(block: dict[str, Any], year: int, coverage: Any) -> dict[str, str]:
    """Each panel field's cell. The Electoral College fields and ``pv_coverage`` exist
    for every year, so a null there names no cause; a popular-vote or hybrid field
    outside the window (from ``coverage``) is not applicable."""
    applicable = labels.in_pv_window(year, coverage)
    return {
        "ec_winner": labels.winner(block["ec_winner"], True),
        "pv_winner": labels.winner(block["pv_winner"], applicable),
        "hybrid_winner": labels.winner(block["hybrid_winner"], applicable),
        "pv_flip": labels.flip(block["pv_flip"], "popular-vote", applicable),
        "hybrid_flip": labels.flip(block["hybrid_flip"], "hybrid", applicable),
        "ec_margin": labels.margin(block["ec_margin"], True),
        "pv_margin": labels.margin(block["pv_margin"], applicable),
        "hybrid_margin": labels.margin(block["hybrid_margin"], applicable),
        "ec_determinative": labels.ec_majority(block["ec_determinative"]),
        "pv_coverage": labels.share_cell(block["pv_coverage"]),
    }


def _panel(block: dict[str, Any] | None, year: int, coverage: Any) -> list[Any]:
    """The election panel (#308): each field's label (its raw name as the tooltip, as
    a column header's is) beside its cell, the hybrid's help text, and a glossary."""
    heading = html.H2("Under each method")
    if block is None:
        return [
            heading,
            html.P(PANEL_UNAVAILABLE, id=PANEL_UNAVAILABLE_ID, className="note"),
        ]
    cells = _panel_cells(block, year, coverage)
    return [
        heading,
        html.Div(
            [
                html.Dl(
                    [
                        item
                        for field in PANEL_FIELDS
                        for item in (
                            html.Dt(labels.LABELS[field], title=field),
                            html.Dd(cells[field]),
                        )
                    ]
                ),
                html.P(labels.HYBRID_NOTE, className="note"),
                labels.glossary(PANEL_FIELDS, "Field names"),
            ],
            id=PANEL_ID,
            className="panel",
        ),
    ]


def _per_capita_rows(value: Any, year: int) -> list[dict[str, Any]]:
    """T6's rows sorted by state name, or ``TypeError``.

    As :func:`_rows` reads the year's rows: a non-empty list, each naming the validated
    year, so an empty list or a row of another year is a malformed body. Each must name
    a USPS code too, which the state filter and the state link read. A null cell is not
    malformed: :func:`explore.labels.per_capita_cells` says why it is null.
    """
    path = f"/v1/elections/{year}/per-capita"
    rows = _rows(value, year, "rows", path)
    for row in rows:
        usps = row.get("state_usps")
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError(f"{path} carries a bad state code")
    return sorted(rows, key=lambda r: str(r["state"]))


def _per_capita_section(rows: list[dict[str, Any]], chosen: Filters) -> list[Any]:
    """T6: every state's persons per electoral vote, narrowed by T2's resolved state."""
    shown = [r for r in rows if chosen.state in (None, r["state_usps"])]
    return [
        html.H2("People per electoral vote"),
        html.P(PER_CAPITA_FILTER_NOTE, className="note"),
        html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
        _table(
            PER_CAPITA_FIELDS,
            [html.Tr([_state_cell(r), *labels.per_capita_cells(r)]) for r in shown],
            PER_CAPITA_TABLE_ID,
        )
        if shown
        else html.P("No rows match these filters.", className="empty"),
        html.P(labels.GOVERNING_CENSUS_NOTE, className="note"),
        html.P(labels.BOUNDARY_NOTE, className="note"),
        labels.glossary(PER_CAPITA_FIELDS),
    ]


def render(
    body: dict[str, Any],
    index_row: dict[str, Any],
    pairs: list[tuple[str, str]],
    per_capita: dict[str, Any],
) -> html.Div:
    """The page body for one ``/v1/elections/{year}`` response, the year's row of
    ``/v1/elections`` and its ``/per-capita`` response (all read through the same
    view), and this page's filter pairs. The response's ``election`` key is required,
    though its value may be null (:func:`_election`)."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    # The popular-vote window, checked once before any cell reads it, whatever the
    # ``election`` block holds: two years, the first no later than the last (#308).
    query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
    year = _row_year(index_row)
    if year is None:
        raise TypeError("the index row names no year")
    rows = _rows(body["data"], year, "state rows")
    summary = _rows(body["summary"], year, "candidates")
    per_capita_rows = _per_capita_rows(per_capita["data"], year)
    block = _election(body["election"], year)
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
        html.P(labels.HYBRID_NOTE, className="note"),
        labels.glossary(NATION_FIELDS),
    ]
    return html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            *_panel(block, year, coverage),
            html.H2("Results by state"),
            _controls(rows, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            _table(
                STATE_FIELDS,
                [_state_row(r, year, coverage) for r in shown],
                STATES_TABLE_ID,
            )
            if shown
            else html.P("No rows match these filters.", className="empty"),
            html.P(labels.PARTY_NOTE, className="note"),
            labels.glossary(STATE_GLOSSARY),
            *nation,
            *_per_capita_section(per_capita_rows, chosen),
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
                per_capita = view.get(f"/v1/elections/{year}/per-capita")
                index = view.get(api.ELECTIONS_PATH)
                content = render(
                    body, index_row(index, year), parse_filters(params), per_capita
                )
                heading = f"The {year} election"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1(heading),
            html.P(
                "Who led under the Electoral College, the popular vote and the "
                "hybrid; every state's electoral votes for each candidate, with the "
                "popular vote where this dataset has it; the national result; and how "
                "many people each state's electoral votes stood for. Narrow the state "
                "results by state, candidate or status.",
                className="lede",
            ),
            content,
        ]
    )
