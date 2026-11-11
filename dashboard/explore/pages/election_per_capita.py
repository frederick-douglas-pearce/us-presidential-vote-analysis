"""One election's people per electoral vote (#280, #465): T6, every state's persons
per electoral vote, at ``/election/<year>/per-capita``.

Split out of the one-election view by #465 (the overview is ``pages/election.py``;
the shared pieces are in :mod:`explore.election_view`), with chart C3 (#435, D093)
above T6. It reads one response,
``/v1/elections/{year}/per-capita``, filled on a miss; the year's heading and its
neighbours come from the prefetched ``/v1/elections``. Its one filter is ``state`` (a
USPS code, :func:`explore.election_view.parse_state`), checked against the rows this
page reads: a state T6's rows do not name falls back to every state (#465, amending
#280's rule that T6 followed T2's resolved state).
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, charts, components, election_view, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filter leaves in T6.
PAGE_ID = "election-per-capita-page"
#: The wrapper of the not-found state: a year the dataset does not serve.
NOT_FOUND_ID = "election-per-capita-not-found"
PER_CAPITA_TABLE_ID = "election-per-capita"
#: Chart C3 (#435): every state's people per electoral vote, beside T6.
C3_ID = "C3"
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
#: It names the table: the filter never narrows C3 (#435's ba spec).
FILTER_SENTENCE = "Narrow the table to one state."

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
    state link read, and no state may be named twice (C3 marks the selected state
    with one point). A null cell is not malformed:
    :func:`explore.labels.per_capita_strings` says why it is null.
    """
    path = f"/v1/elections/{year}/per-capita"
    rows = election_view.rows(value, year, "rows", path)
    seen: set[str] = set()
    for row in rows:
        usps = row.get("state_usps")
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError(f"{path} carries a bad state code")
        # One row per state (the API's key is the year and the state): C3 marks the
        # selected state with one point (#435).
        if usps in seen:
            raise TypeError(f"{path} names a state twice")
        seen.add(usps)
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


#: Pixels per state row and the margins around C3's plot (#435): one bar and its label
#: per row at 390 px; the top margin holds the legend, one line per entry.
_ROW_PX = 22
_LEGEND_PX = 26
_TOP_PX = 16
_BOTTOM_PX = 48
#: The marker and selected-mark sizes, and the gap between the row names and the axis
#: (#435): the selected mark sits at zero, so it needs the gap on its left and, beside a
#: marker, the marker's label set clear on its right. The e2e test
#: ``test_c3_marks_the_selected_state_over_no_text`` observes it at 390 px.
_MARK_PX = 14
_SELECTED_PX = 12
_STANDOFF_PX = 12

#: The border cell that draws a bar striped: present-day borders, in every year.
_STRIPED = labels.BOUNDARY_BASIS["present_day"]
_AT_ELECTION = labels.BOUNDARY_BASIS["at_election"]


def _drawn(row: dict[str, Any], cell: str) -> float | None:
    """The ratio C3 draws as a bar, or ``None`` for a marker: a number
    :func:`explore.labels.finite` accepts whose T6 cell is that figure, never a cause
    (#435). The chart computes nothing; it draws the served value labeled with T6's
    cell."""
    number = labels.finite(row["persons_per_electoral_vote"])
    return None if number is None or cell in labels.C3_MARKER_LABELS else number


def _c3_order(
    rows: list[dict[str, Any]], strings: dict[str, dict[str, str]]
) -> tuple[list[tuple[dict[str, Any], float]], list[dict[str, Any]]]:
    """C3's rows: the drawn ones by ratio, most first, ties by state name; then every
    other row in T6's order (by state name)."""
    drawn = []
    others = []
    for row in rows:
        value = _drawn(row, strings[row["state_usps"]]["persons_per_electoral_vote"])
        if value is None:
            others.append(row)
        else:
            drawn.append((row, value))
    drawn.sort(key=lambda pair: (-pair[1], str(pair[0]["state"])))
    return drawn, others


class C3(NamedTuple):
    """C3's figure and what its caption needs to say."""

    figure: dict[str, Any]
    striped: bool
    plain: str | None
    markers: bool
    census: bool


def _c3_figure(
    rows: list[dict[str, Any]],
    strings: dict[str, dict[str, str]],
    chosen: str | None,
    year: int,
) -> C3:
    """C3's figure (#435, D093), from every T6 row (never narrowed by the filter) and
    T6's cell strings (``strings``, by USPS code).

    One row per state, on a numeric axis (reversed, names as tick text, escaped by
    :func:`explore.charts.escaped`). A drawn ratio is a bar labeled with T6's cell;
    the bars are two series split on T6's border cell, striped exactly for
    present-day borders, sharing one ``offsetgroup`` so each row draws one centered
    bar. Any other row gets a marker at zero labeled from T6's cell
    (:data:`explore.labels.C3_MARKER_LABELS`), with the cell in full in its hover,
    never a zero-length bar or an infinity. The selected state is one diamond filled
    with the page color at the start of its row, in a series of its own (never a
    per-point symbol list), drawn before the markers.
    """
    drawn, others = _c3_order(rows, strings)
    ordered = [row for row, _ in drawn] + others
    position = {row["state_usps"]: i for i, row in enumerate(ordered)}
    names = [charts.escaped(str(row["state"])) for row in ordered]
    data: list[dict[str, Any]] = []
    plain_rows: list[tuple[dict[str, Any], float]] = []
    striped_rows: list[tuple[dict[str, Any], float]] = []
    for row, value in drawn:
        striped = strings[row["state_usps"]]["boundary_basis"] == _STRIPED
        (striped_rows if striped else plain_rows).append((row, value))
    plain_name: str | None = None
    if plain_rows:
        plain_name = (
            _AT_ELECTION
            if all(
                strings[row["state_usps"]]["boundary_basis"] == _AT_ELECTION
                for row, _ in plain_rows
            )
            else labels.C3_PLAIN_SERIES
        )
    for series, name, pattern in (
        (plain_rows, plain_name, None),
        (striped_rows, _STRIPED, "/"),
    ):
        if not series:
            continue
        marker: dict[str, Any] = {"color": "var(--chart-1)"}
        if pattern is not None:
            marker["pattern"] = {
                "shape": pattern,
                "fillmode": "overlay",
                "fgcolor": "var(--page)",
            }
        hovers = []
        for row, _ in series:
            cell = strings[row["state_usps"]]
            hovers.append(
                labels.C3_BAR_HOVER.format(
                    state=charts.escaped(str(row["state"])),
                    ratio=cell["persons_per_electoral_vote"],
                    population=cell["population"],
                    electoral_votes=cell["state_electoral_votes"],
                    census_year=cell["governing_census_year"],
                    boundary=cell["boundary_basis"],
                )
            )
        data.append(
            {
                "type": "bar",
                "orientation": "h",
                "name": name,
                "offsetgroup": "c3",
                "ids": [str(row["state_usps"]) for row, _ in series],
                "x": [value for _, value in series],
                "y": [position[row["state_usps"]] for row, _ in series],
                "text": [
                    strings[row["state_usps"]]["persons_per_electoral_vote"]
                    for row, _ in series
                ],
                "textposition": "outside",
                "textfont": {"color": "var(--text)"},
                "cliponaxis": False,
                "marker": marker,
                "hovertext": hovers,
                "hovertemplate": "%{hovertext}<extra></extra>",
                "showlegend": True,
            }
        )
    # Before the marker trace, so a marker drawn in the same row is on top.
    if chosen is not None:
        data.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": labels.C3_SELECTED,
                "showlegend": True,
                "ids": [chosen],
                "x": [0],
                "y": [position[chosen]],
                "cliponaxis": False,
                # Filled with the page color, so the half over a bar's start is
                # parted from it at 3:1 in both palettes, and ringed in the text
                # color (#435's review).
                "marker": {
                    "symbol": "diamond",
                    "size": _SELECTED_PX,
                    "color": "var(--page)",
                    "line": {"width": 2, "color": "var(--text)"},
                },
                "hoverinfo": "skip",
            }
        )
    if others:
        marks = []
        for row in others:
            ratio = strings[row["state_usps"]]["persons_per_electoral_vote"]
            hover = (
                f"{ratio}<br>{labels.UNRECOGNIZED_NOTE}"
                if ratio == labels.UNRECOGNIZED
                else ratio
            )
            marks.append(
                (
                    row,
                    labels.C3_MARKER_LABELS.get(ratio, labels.UNRECOGNIZED),
                    labels.C3_NO_FIGURE_HOVER.format(
                        state=charts.escaped(str(row["state"])), cell=hover
                    ),
                )
            )
        data.append(
            {
                "type": "scatter",
                "mode": "markers+text",
                "name": labels.C3_NO_FIGURE_SERIES,
                "showlegend": False,
                "ids": [str(row["state_usps"]) for row, _, _ in marks],
                "x": [0] * len(marks),
                "y": [position[row["state_usps"]] for row, _, _ in marks],
                "text": [label for _, label, _ in marks],
                "textposition": "middle right",
                "textfont": {"color": "var(--text)"},
                "cliponaxis": False,
                # Sized above the selected mark, so plotly sets this label clear of it.
                "marker": {"symbol": "x", "size": _MARK_PX, "color": "var(--text)"},
                "hovertext": [hover for _, _, hover in marks],
                "hovertemplate": "%{hovertext}<extra></extra>",
            }
        )
    census = {strings[row["state_usps"]]["governing_census_year"] for row in rows}
    # A year only when every row names the same one: never a cause or an unknown.
    one_census = len(census) == 1 and census.isdisjoint(
        {labels.UNRECOGNIZED, labels.NOT_IN_DATASET}
    )
    title = (
        labels.C3_TITLE.format(year=year, census_year=next(iter(census)))
        if one_census
        else labels.C3_TITLE_NO_CENSUS.format(year=year)
    )
    entries = sum(1 for trace in data if trace.get("showlegend"))
    top = _TOP_PX + _LEGEND_PX * entries
    longest = max((value for _, value in drawn), default=1.0)
    layout: dict[str, Any] = {
        "title": {"text": title},
        "height": _ROW_PX * max(len(ordered), 1) + top + _BOTTOM_PX,
        "margin": {"t": top, "b": _BOTTOM_PX, "r": 64},
        "showlegend": entries > 0,
        "xaxis": {
            "range": [0, longest],
            "showticklabels": False,
            "title": {"text": labels.C3_X_AXIS},
        },
        "yaxis": {
            "tickvals": list(range(len(ordered))),
            "ticktext": names,
            "autorange": "reversed",
            "showgrid": False,
            "zeroline": False,
            # Room at the axis for the selected mark, which sits at zero.
            "ticklabelstandoff": _STANDOFF_PX,
        },
    }
    if entries:
        layout["legend"] = {
            "orientation": "h",
            "yref": "container",
            "y": 1,
            "yanchor": "top",
            "x": 0,
            "xanchor": "left",
        }
    return C3(
        {"data": data, "layout": layout},
        striped=bool(striped_rows),
        plain=plain_name,
        markers=bool(others),
        census=one_census,
    )


def _c3_caption(c3: C3, selected: str | None) -> str:
    """C3's caption (#435): what the ratio is, which census, what the stripes mean (or
    which borders every bar uses), what a marker means where one is drawn, and the
    selected state's mark where the filter selects one. ``components.chart`` adds the
    table pointer."""
    parts = [
        labels.C3_RATIO,
        labels.C3_CENSUS if c3.census else labels.C3_CENSUS_MIXED,
    ]
    if c3.striped:
        parts += [labels.C3_STRIPES, labels.BOUNDARY_NOTE]
    elif c3.plain == _AT_ELECTION:
        parts.append(labels.C3_ALL_AT_ELECTION)
    if c3.plain == labels.C3_PLAIN_SERIES:
        parts.append(labels.C3_PLAIN_MIXED)
    if c3.markers:
        parts.append(labels.C3_NO_FIGURE_NOTE)
    if selected is not None:
        parts.append(labels.C3_SELECTED_NOTE.format(state=selected))
    return " ".join(parts)


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
    with its filter sentence, the section links, chart C3 (every state, whatever the
    filter), the state control, T6 and the footer, from the per-capita response's own
    provenance."""
    year = election_view.row_year(index_row)
    if year is None:
        raise TypeError("the index row names no year")
    rows = _per_capita_rows(per_capita["data"], year)
    chosen = chosen_state(pairs, rows)
    shown = [r for r in rows if chosen in (None, r["state_usps"])]
    # T6's worded cells, once per row for every row: T6 and C3 both read them (#435).
    strings = {r["state_usps"]: labels.per_capita_strings(r) for r in rows}
    c3 = _c3_figure(rows, strings, chosen, year)
    selected = next((str(r["state"]) for r in rows if r["state_usps"] == chosen), None)
    return html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            *election_view.neighbor_nav(around, election_view.PER_CAPITA),
            html.H1(PER_CAPITA_HEADING.format(year=year)),
            html.P(f"{LEDE} {FILTER_SENTENCE}", className="lede"),
            election_view.section_nav(year, election_view.PER_CAPITA),
            components.chart(
                C3_ID, c3.figure, PER_CAPITA_TABLE_ID, _c3_caption(c3, selected)
            ),
            _control(rows, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            *components.table(
                shown,
                lambda r: html.Tr(
                    [
                        components.state_cell(r),
                        *labels.per_capita_cells(r, strings[r["state_usps"]]),
                    ]
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
