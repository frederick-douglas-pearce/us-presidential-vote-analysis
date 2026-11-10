"""One election's people per electoral vote (#280, #465): T6, every state's persons
per electoral vote, at ``/election/<year>/per-capita``.

Split out of the one-election view by #465 (the overview is ``pages/election.py``;
the shared pieces are in :mod:`explore.election_view`). It reads one response,
``/v1/elections/{year}/per-capita``, filled on a miss; the year's heading and its
neighbours come from the prefetched ``/v1/elections``. Its one filter is ``state`` (a
USPS code, :func:`explore.election_view.parse_state`), checked against the rows this
page reads: a state T6's rows do not name falls back to every state (#465, amending
#280's rule that T6 followed T2's resolved state).
"""

from __future__ import annotations

from typing import Any

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, components, election_view, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filter leaves in T6.
PAGE_ID = "election-per-capita-page"
#: The wrapper of the not-found state: a year the dataset does not serve.
NOT_FOUND_ID = "election-per-capita-not-found"
PER_CAPITA_TABLE_ID = "election-per-capita"
#: The page's own URL and state control: distinct from the states page's, since Dash
#: registers callbacks app-wide, keyed by output.
URL_ID = "election-per-capita-url"
STATE_ID = "election-per-capita-state"

#: T6's columns, in display order, by public field name (#280).
PER_CAPITA_FIELDS = ("state", *labels.PER_CAPITA_FIELDS)
#: What T6's CSV adds after its columns (#309): the state's key and the year.
PER_CAPITA_EXTRA = ("state_usps", "year")

#: The not-found state (#325), shared by the three election pages (#465).
NOT_FOUND = api.NotFound(
    labels.ELECTION_NOT_FOUND_HEADING, labels.ELECTION_NOT_FOUND_SENTENCE
)

#: The page's heading, its title before the site title, and before a year is checked,
#: or on the degraded state, its heading without a year (ba spec, approved at #465's
#: plan gate, 2026-11-10).
PER_CAPITA_HEADING = "The {year} election: people per electoral vote"
PER_CAPITA_GENERIC_HEADING = "Election: people per electoral vote"
#: The lede, then, on a successful render only, the sentence naming its filter. It
#: makes no claim about which census applies (#423 is pending).
LEDE = (
    "How many people each state's electoral votes stood for: the state's population "
    "divided by its electors appointed."
)
FILTER_SENTENCE = "Narrow the rows to one state."

VALIDATE: api.Validate = (api.ELECTIONS_PATH, election_view.served_year)


def title(year: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a year the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the year only when the year is four ASCII digits."""
    if isinstance(year, str) and query.YEAR_RE.fullmatch(year):
        return f"{PER_CAPITA_HEADING.format(year=year)} — {SITE_TITLE}"
    return f"{PER_CAPITA_GENERIC_HEADING} — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template=election_view.template(election_view.PER_CAPITA),
    # Before the overview, whose greedy ``<year>`` would capture ``1824/per-capita``
    # (#465; see ``pages/election_states.py``).
    order=1,
    title=title,
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description=(
        "How many people each state's electoral votes stood for in one US "
        "presidential election."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=("/v1/elections/{year}/per-capita",),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=election_view.parse_state,
    nav="elections",
)


def chosen_state(
    pairs: list[tuple[str, str]], rows: list[dict[str, Any]]
) -> str | None:
    """The state to narrow T6 to: the query's, if T6's own rows name it, else ``None``
    ("all"). Per parameter, as ``og:url`` is: it keeps a well-formed state the year's
    rows do not name, which falls back here."""
    state = dict(pairs).get(election_view.STATE)
    return state if any(r["state_usps"] == state for r in rows) else None


def search_for(state: Any) -> str:
    """The query string for the control's value, in the normal form ``og:url`` uses
    (``""`` or ``?…``). A cleared control is "all" and is omitted."""
    params = {election_view.STATE: state} if isinstance(state, str) and state else {}
    return query.encode_search(election_view.parse_state(params))


@callback(
    Output(URL_ID, "search"),
    Input(STATE_ID, "value"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(state: Any, current: Any) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. An unchanged search is left alone.
    """
    search = search_for(state)
    return no_update if search == (current or "") else search


def _per_capita_rows(value: Any, year: int) -> list[dict[str, Any]]:
    """T6's rows sorted by state name, or ``TypeError``.

    As :func:`explore.election_view.rows` reads the year's rows: a non-empty list,
    each naming the validated year, so an empty list or a row of another year is a
    malformed body. Each must name a USPS code too, which the state filter and the
    state link read. A null cell is not malformed:
    :func:`explore.labels.per_capita_cells` says why it is null.
    """
    path = f"/v1/elections/{year}/per-capita"
    rows = election_view.rows(value, year, "rows", path)
    for row in rows:
        usps = row.get("state_usps")
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError(f"{path} carries a bad state code")
    return sorted(rows, key=lambda r: str(r["state"]))


def _control(rows: list[dict[str, Any]], chosen: str | None) -> html.Div:
    """The state control, its options T6's own rows."""
    states = {r["state_usps"]: r["state"] for r in rows}
    options = [
        {"label": name, "value": usps}
        for usps, name in sorted(states.items(), key=lambda kv: kv[1])
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Label(
                        labels.LABELS[election_view.STATE],
                        htmlFor=STATE_ID,
                        className="label",
                    ),
                    dcc.Dropdown(
                        id=STATE_ID,
                        options=options,
                        value=chosen,
                        placeholder="All states",
                        clearable=True,
                    ),
                ],
                className="filter",
            )
        ],
        className="filters",
    )


def _download(year: int, body: dict[str, Any], chosen: str | None) -> export.Download:
    """T6's download: the file named for the view and the table, the provenance of the
    response its rows come from, and this page's URL with the state applied."""
    return export.Download(
        filename=f"election-{year}-per-capita.csv",
        name="people per electoral vote",
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST,
            election_view.path(year, election_view.PER_CAPITA),
            query.encode_search(
                [(election_view.STATE, chosen)] if chosen is not None else []
            ),
        ),
    )


def render(
    per_capita: dict[str, Any],
    index_row: dict[str, Any],
    pairs: list[tuple[str, str]],
    around: election_view.Neighbours,
) -> html.Div:
    """The page body for one ``/v1/elections/{year}/per-capita`` response, the year's
    row of ``/v1/elections`` (read through the same view), this page's filter pairs and
    the year's served neighbours: the earlier and later links, the heading, the lede
    with its filter sentence, the section links, the state control, T6 and the
    footer, from the per-capita response's own provenance."""
    year = election_view.row_year(index_row)
    if year is None:
        raise TypeError("the index row names no year")
    rows = _per_capita_rows(per_capita["data"], year)
    chosen = chosen_state(pairs, rows)
    shown = [r for r in rows if chosen in (None, r["state_usps"])]
    return html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            *election_view.neighbor_nav(around, election_view.PER_CAPITA),
            html.H1(PER_CAPITA_HEADING.format(year=year)),
            html.P(f"{LEDE} {FILTER_SENTENCE}", className="lede"),
            election_view.section_nav(year, election_view.PER_CAPITA),
            _control(rows, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            *components.table(
                shown,
                lambda r: html.Tr(
                    [components.state_cell(r), *labels.per_capita_cells(r)]
                ),
                PER_CAPITA_FIELDS,
                PER_CAPITA_TABLE_ID,
                _download(year, per_capita, chosen),
                extra=PER_CAPITA_EXTRA,
                notes=(labels.GOVERNING_CENSUS_NOTE, labels.BOUNDARY_NOTE),
            ),
            labels.glossary(PER_CAPITA_FIELDS),
            components.provenance_footer(per_capita["meta"]["provenance"]),
        ],
        id=PAGE_ID,
    )


def layout(year: Any = None, **params: Any) -> html.Div:
    """The people per electoral vote. On success, :func:`render`'s body is the whole
    page. The not-found and degraded states get their heading here, heading first, and
    the degraded state its lede, without the filter sentence."""
    heading = PER_CAPITA_GENERIC_HEADING
    lede: str | None = LEDE
    try:
        with api.CLIENT.view() as view:
            # Validated from the prefetched index before it is formatted (#312).
            if not api.accepted(view.get, VALIDATE, {"year": year}):
                heading, lede = labels.ELECTION_NOT_FOUND_HEADING, None
                content = election_view.not_found(NOT_FOUND_ID)
            else:
                per_capita = view.get(f"/v1/elections/{year}/per-capita")
                index = view.get(api.ELECTIONS_PATH)
                return render(
                    per_capita,
                    election_view.index_row(index, year),
                    election_view.parse_state(params),
                    election_view.neighbours(index, int(year)),
                )
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
