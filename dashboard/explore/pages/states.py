"""The state picker (#279): every state and DC in the dataset, linked to its history,
and the four history figures of each, side by side (#641, D123).

The roster comes from the latest election's rows, ``/v1/elections/{year_max}``
(:data:`explore.api.ROSTER_PATH`), since every state and DC takes part in it; there is
no second copy of it (D006). ``year_max`` is read from the prefetched ``/v1/elections``
and checked to be the latest year it serves (:func:`explore.api.coverage_vars`), never
from the request. The roster is filled on a miss and shared with every
``/state/<usps>`` page and its ``/elections`` and ``/per-capita`` pages, which validate
the code against it.

The history table reads N2, ``/v1/elections/states``
(:data:`explore.api.ELECTION_STATES_PATH`), once, filled on a miss (D123, amending
D107; D072's prefetch extent unchanged), and computes every state's figures through
:func:`explore.state_view.states_history`, the path each state's own page takes, so a
cell equals that page's figure. A failed or malformed N2 degrades that section alone
(D096(d)'s rule): the list of states, the heading, the lede and the success marker
stay.

Chart C11 (#623, D121 as amended by D124) sits in that section, between its intro and
the table: a US map shading every state by one of the four figures, read by the same
path as the table's cells (:func:`explore.state_view.history_values`), and chosen by
the one query key ``metric`` (:func:`parse_metric`, a closed vocabulary). A change of
figure writes the query and the router re-renders the page from the cache, with no
request to the API; the table and its download do not change.
"""

from __future__ import annotations

from typing import Any

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, charts, components, export, labels, query, state_view
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries: the list of states.
PAGE_ID = "states"
LIST_ID = "states-list"

#: The history table (#641, D123), its column-name list and the sentence in its place
#: when N2 cannot be read (D096(d)'s rule; its own id, never the page's degraded
#: state's).
HISTORY_TABLE_ID = "states-history"
HISTORY_GLOSSARY_ID = "states-history-glossary"
HISTORY_UNAVAILABLE_ID = "states-history-unavailable"

#: Chart C11 (#623): its registry ID, the sentence in its place when no state has a
#: number for the figure chosen, the page's own URL and the figure's control (distinct
#: from every other page's, since Dash registers callbacks app-wide, keyed by output).
C11_ID = "C11"
C11_NO_FIGURES_ID = "states-map-no-figures"
URL_ID = "states-url"
METRIC_ID = "states-metric"
#: The query key choosing C11's figure, and its values: the four metric keys
#: (:data:`explore.state_view.HISTORY_KEYS`), the first the default, which the query
#: never names (D073).
METRIC = "metric"
DEFAULT_METRIC = state_view.HISTORY_KEYS[0]

#: The page's wording (#641; ba spec, approved at its plan gate, 2026-11-25; #623's,
#: re-run 2026-11-27, approved at its plan gate). The lede is true on every state the
#: page renders, the section's degraded one included; the filter sentence follows it
#: only where the figure's control renders (#419).
LEDE = (
    "Every state and DC in this dataset, and how their histories in it compare. "
    "Each state also has pages of its own."
)
DESCRIPTION = (
    "Every US state and DC in this dataset, compared on elections with electors "
    "appointed, first election, elections with a popular vote to choose electors, and "
    "change in electors appointed, with a link to each state's pages."
)
FILTER_SENTENCE = "Choose the figure the map shows; the table always shows all four."
#: C11's control: its label, and its placeholder, which never shows (the control
#: cannot be cleared) but is read as page text.
METRIC_LABEL = "Show on the map"
METRIC_PLACEHOLDER = "Choose a figure"
STATES_HISTORY_HEADING = "State histories compared"
STATES_HISTORY_INTRO = (
    "The figures each state's own history page shows, side by side for every state "
    "and DC. They cover only the elections in this dataset."
)
#: The section's sentence when N2 cannot be read or is malformed, in place of the
#: map and the table (#623): never ``UNAVAILABLE_MESSAGE``'s wording, which means the
#: whole page.
STATES_HISTORY_UNAVAILABLE = (
    "The map and table of each state's history figures can't be shown right now. "
    "Please try again in a minute."
)
#: Under the table while a state's row reads :data:`explore.labels.UNAVAILABLE_CELL`.
STATES_HISTORY_UNAVAILABLE_NOTE = (
    f'Where a state\'s figures read "{labels.UNAVAILABLE_CELL}", this page could not '
    "check what this dataset holds for that state just now, so it shows none of its "
    "figures. Please try again in a minute."
)
#: Under the table and in its download's preamble (ba, after the plan gate; wording
#: not yet approved at the merge gate).
STATES_HISTORY_DOWNLOAD_NOTE = (
    "In the download, each figure column holds the number the page shows, written as "
    "a plain number: the elections with electors appointed, the year of the first "
    "election, the elections with a popular vote to choose electors, and the change "
    "in electors appointed, with a minus sign for a fall. The popular-vote count and "
    "the number of elections it is out of are in two columns. A cell there is blank "
    f'where the page shows no figure, "{labels.UNRECOGNIZED}" or '
    f'"{labels.UNAVAILABLE_CELL}".'
)
#: The download's last preamble line, in place of :data:`explore.export.NULL_LINE`:
#: an empty figure cell here is no null (D123; ba, after the plan gate).
STATES_HISTORY_EMPTY_CELL_LINE = (
    "An empty cell means the page shows no number for that figure, and the table on "
    "the page says why; the state's name and two-letter code are never empty."
)

#: The table's one served column, then its CSV-only columns: the code and the figures'
#: raw values (D123, amending D116(a)).
HISTORY_FIELDS = ("state",)
HISTORY_EXTRA = ("state_usps", *state_view.HISTORY_VALUE_KEYS)
#: The four figure columns, shown and not downloaded as shown (D116(a)): each header,
#: then the download columns and the served fields it is built from (its tooltip and
#: its column-name list entry; ba, after the plan gate).
PAGE_ONLY = (
    (
        labels.STATES_HISTORY_HEADERS["state_elections_count"],
        "state_elections_count (from year, state_electoral_votes)",
    ),
    (
        labels.STATES_HISTORY_HEADERS["state_first_election"],
        "state_first_election (from year, state_electoral_votes)",
    ),
    (
        labels.STATES_HISTORY_HEADERS["state_pv_elections_count"],
        "state_pv_elections_count, state_pv_elections_n (from year, "
        "state_electoral_votes, pv_status)",
    ),
    (
        labels.STATES_HISTORY_HEADERS["state_electors_change"],
        "state_electors_change (from year, state_electoral_votes)",
    ),
)


def parse_metric(params: Any) -> list[tuple[str, str]]:
    """The page's one query key (#623), ``metric``, kept only as a metric key C11 can
    show other than the default (:data:`DEFAULT_METRIC`, which the query never names,
    D073): a closed vocabulary, so any other value, or one given twice with two
    values, is dropped. Every other key is dropped. Total and API-free."""
    if not isinstance(params, dict):
        return []
    value = query.single(params.get(METRIC))
    if value in state_view.HISTORY_KEYS and value != DEFAULT_METRIC:
        return [(METRIC, value)]
    return []


def chosen_metric(pairs: list[tuple[str, str]]) -> str:
    """The metric key C11 shows for ``pairs`` (:func:`parse_metric`'s)."""
    return dict(pairs).get(METRIC, DEFAULT_METRIC)


def search_for(metric: Any) -> str:
    """The query string for the control's value, in the normal form ``og:url`` uses
    (``""`` or ``?…``): the default figure is omitted."""
    return query.encode_search(
        parse_metric({METRIC: metric} if isinstance(metric, str) else {})
    )


@callback(
    Output(URL_ID, "search"),
    Input(METRIC_ID, "value"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_metric_change(metric: Any, current: Any) -> Any:
    """A change of figure becomes a URL change; the router re-renders from the cache,
    so it reads no API. An unchanged search is left alone."""
    search = search_for(metric)
    return no_update if search == (current or "") else search


dash.register_page(
    __name__,
    path="/states",
    title=f"States — {SITE_TITLE}",
    description=DESCRIPTION,
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, api.ELECTION_STATES_PATH),
    success=PAGE_ID,
    query=parse_metric,
    # The site navigation link this page marks (#448):
    # the state picker marks its own link.
    nav="states",
)


def roster(body: Any, year: int) -> list[tuple[str, str]]:
    """``(usps, name)`` for each state the roster names, sorted by what its link shows
    (the name, or the code where the name is blank), or ``TypeError``.

    Read by :func:`explore.state_view.roster`, the reading the state pages judge from
    too, and the rows must name the year the roster was read for. Each name is as
    served, sorted by what its link shows (:func:`link_text`), so a state shown by
    its code sorts by that code (#647's review, r1.code-review.10).
    """
    named, states = state_view.roster(body)
    if named != year:
        raise TypeError(f"/v1/elections/{year} carries rows of {named}")
    return sorted(states.items(), key=lambda kv: link_text(*kv))


def link_text(usps: str, name: str) -> str:
    """A state's link text on this page: its name, or its code where the name has
    nothing in it, so no link is invisible (#641, D123; owner at its plan gate)."""
    return name if labels.has_text(name) else usps


def cell_text(figures: state_view.HistoryFigures | None, key: str) -> str:
    """One figure's cell text (#641), which the table's cell and C11's hover both show
    (#623, D091, D123(e)): :data:`explore.labels.UNAVAILABLE_CELL` for a refused
    state, else the value half of the state page's figure
    (:func:`explore.state_view.history_cell`), the popular-vote count with its N
    (:data:`explore.labels.STATES_COUNT_OF`) where it has a figure: where
    :func:`explore.state_view.history_cell` gives it a rest, which
    :func:`explore.labels.metric_count` does only for a recognized count with an N."""
    if figures is None:
        return labels.UNAVAILABLE_CELL
    value, rest = state_view.history_cell(figures, key)
    if key == "state_pv_elections_count" and rest is not None:
        pv = figures.popular_vote
        value = labels.STATES_COUNT_OF.format(count=pv.count, n=pv.n)
    return value


def figure_cell(figures: state_view.HistoryFigures | None, key: str) -> Any:
    """One figure's table cell (#641): :func:`cell_text` in a cell."""
    return labels.cell(cell_text(figures, key))


# --- chart C11 (#623, D121 as amended by D124) ----------------------------------------

#: Each figure's ramp (D109): the three figures derived from the electoral allotment
#: red, the count of elections with a popular vote held blue.
C11_RAMPS = {
    "state_elections_count": charts.MAP_RAMPS[0],
    "state_first_election": charts.MAP_RAMPS[0],
    "state_pv_elections_count": charts.MAP_RAMPS[1],
    "state_electors_change": charts.MAP_RAMPS[0],
}
#: C11's height in px (D124, amending D121(h)'s height from the width, which the
#: server does not know), and its colorbar's thickness, inside
#: ``charts.MAP_COLORBAR_THICKNESS``.
C11_HEIGHT_PX = 330
C11_COLORBAR_PX = 12
#: The figure's side margins, so the scale's end labels are drawn (D124's
#: measurement: at 0 px plotly.js hid "1824" and "+50" at 390 and 360 px).
C11_SIDE_PX = 16


def tick_text(metric: str, value: int) -> str:
    """A number on C11's scale, in the table's value format (ba, #623): a bare count,
    a year with no separator, the change signed (:func:`explore.labels.signed`: "+",
    U+2212, an unsigned "0"). Never the table's "{count} of {n}": a tick is a point on
    the scale, not a state."""
    return labels.signed(value) if metric == "state_electors_change" else str(value)


def c11_figure(
    metric: str,
    states: list[tuple[str, str]],
    figures: dict[str, state_view.HistoryFigures | None],
) -> dict[str, Any] | None:
    """C11's figure for ``metric`` (#623, D124), or ``None`` where no state has a
    number for it. One choropleth trace over every roster state whose value
    (:func:`explore.state_view.history_values`, the table's path) is a number; a state
    with none (refused, unrecognized or no figure) is left out, drawn in outline only
    (D121(f), D123(f)). ``z`` is the value itself, on a linear scale from the lowest
    drawn value to the highest (one above the lowest where all are equal), in the
    figure's ramp, its low end nearest the page. The colorbar runs along the top with
    numbered ticks at both ends, and at 0 for the change where the scale spans it. The
    hover writes the state, the figure's header and the table's cell, escaped (D091).
    No ``layout.geo``: the template's."""
    drawn = [
        (usps, name, value)
        for usps, name in states
        if (value := state_view.history_values(figures[usps])[metric]) is not None
    ]
    if not drawn:
        return None
    values = [value for _, _, value in drawn]
    low, high = min(values), max(values)
    if high == low:
        high = low + 1
    ticks = [low, high]
    if metric == "state_electors_change" and low < 0 < high:
        ticks = [low, 0, high]
    header = labels.STATES_HISTORY_HEADERS[metric]
    hovers = [
        labels.C11_HOVER.format(
            state=charts.escaped(link_text(usps, name)),
            figure=charts.escaped(header),
            value=charts.escaped(cell_text(figures[usps], metric)),
        )
        for usps, name, _ in drawn
    ]
    trace = {
        "type": "choropleth",
        "name": header,
        "locationmode": "USA-states",
        "locations": [usps for usps, _, _ in drawn],
        "z": values,
        "zmin": low,
        "zmax": high,
        "colorscale": charts.map_colorscale(C11_RAMPS[metric]),
        "showscale": True,
        "colorbar": {
            "orientation": "h",
            "thickness": C11_COLORBAR_PX,
            "tickmode": "array",
            "tickvals": ticks,
            "ticktext": [tick_text(metric, tick) for tick in ticks],
            "outlinewidth": 0,
        },
        "marker": {"line": {"color": charts.MAP_BORDER}},
        "hovertext": hovers,
        "hovertemplate": "%{hovertext}<extra></extra>",
    }
    # The side margins hold half of an end tick's label: plotly.js hides a colorbar
    # label that would cross the figure's edge, and the bar starts 10 px in.
    layout = {
        "title": {"text": labels.C11_TITLES[metric]},
        "height": C11_HEIGHT_PX,
        "margin": {"l": C11_SIDE_PX, "r": C11_SIDE_PX, "t": 8, "b": 0},
    }
    return {"data": [trace], "layout": layout}


def c11(
    metric: str,
    states: list[tuple[str, str]],
    figures: dict[str, state_view.HistoryFigures | None],
) -> list[Any]:
    """C11 for ``metric``, or :data:`explore.labels.C11_NO_FIGURES` in its place where
    no state has a number for it. Its caption: :data:`explore.labels.C11_CAPTION`, the
    figure's :data:`explore.labels.C11_BASIS`, then
    :data:`explore.labels.C11_OUTLINES_CREDIT` (``components.chart`` adds the table
    pointer). Its key, page text inside its figure: the color note, the outline-only
    entry where a state is left out, then the phone note."""
    figure = c11_figure(metric, states, figures)
    if figure is None:
        return [html.P(labels.C11_NO_FIGURES, id=C11_NO_FIGURES_ID, className="note")]
    left_out = len(figure["data"][0]["locations"]) < len(states)
    key = [
        html.P(labels.C11_COLOR_NOTE),
        *([html.P(labels.C11_NO_FIGURE_KEY)] if left_out else []),
        html.P(labels.C11_PHONE_NOTE),
    ]
    caption = " ".join(
        (labels.C11_CAPTION, labels.C11_BASIS[metric], labels.C11_OUTLINES_CREDIT)
    )
    return [
        components.chart(C11_ID, figure, HISTORY_TABLE_ID, caption, legend_key=key)
    ]


def metric_control(metric: str) -> html.Div:
    """C11's control: one figure at a time, never cleared, its options the table's
    headers in :data:`explore.state_view.HISTORY_KEYS`' order (a closed vocabulary,
    not sorted)."""
    options = [
        {"label": labels.STATES_HISTORY_HEADERS[key], "value": key}
        for key in state_view.HISTORY_KEYS
    ]
    return html.Div(
        [
            components.dropdown_filter(
                METRIC_ID,
                METRIC_LABEL,
                options,
                metric,
                METRIC_PLACEHOLDER,
                clearable=False,
            )
        ],
        className="filters wrapped-choice",
    )


def history_section(
    n2: Any, states: list[tuple[str, str]], index: Any, metric: str = DEFAULT_METRIC
) -> tuple[list[Any], bool]:
    """The history section's children (#641, D123), and whether C11's control shows:
    its heading, intro, the control, C11 for ``metric`` (#623), then the table, its
    notes and column-name list; or :data:`STATES_HISTORY_UNAVAILABLE` alone, with no
    control, where N2 (``n2``, ``None`` when it could not be read) or its rows cannot
    be read. Everything read from N2 is inside the ``try``; the chart and its control
    are built after it, from the checked figures (D095(f))."""
    heading = html.H2(STATES_HISTORY_HEADING)
    try:
        if n2 is None:
            raise TypeError(f"{api.ELECTION_STATES_PATH} could not be read")
        served = state_view.served_years(index)
        figures = state_view.states_history(
            n2, [usps for usps, _ in states], served, api.ELECTION_STATES_PATH
        )
        provenance = n2["meta"]["provenance"]
        rows = [
            {
                "state": link_text(usps, name),
                "state_usps": usps,
                **state_view.history_values(figures[usps]),
            }
            for usps, name in states
        ]
        notes = (
            (
                STATES_HISTORY_UNAVAILABLE_NOTE,
                STATES_HISTORY_DOWNLOAD_NOTE,
            )
            if any(f is None for f in figures.values())
            else (STATES_HISTORY_DOWNLOAD_NOTE,)
        )
        table = components.table(
            rows,
            lambda r: html.Tr(
                [
                    components.state_cell(r),
                    *(
                        figure_cell(figures[r["state_usps"]], key)
                        for key in state_view.HISTORY_KEYS
                    ),
                ]
            ),
            HISTORY_FIELDS,
            HISTORY_TABLE_ID,
            export.Download(
                filename="states-history-figures.csv",
                name="each state's history figures",
                provenance=provenance,
                view_url=export.view_url(CANONICAL_HOST, "/states", ""),
            ),
            extra=HISTORY_EXTRA,
            notes=notes,
            page_only=PAGE_ONLY,
            null_line=STATES_HISTORY_EMPTY_CELL_LINE,
        )
    except (KeyError, TypeError):
        return [
            heading,
            html.P(
                STATES_HISTORY_UNAVAILABLE, id=HISTORY_UNAVAILABLE_ID, className="note"
            ),
        ], False
    return [
        heading,
        html.P(STATES_HISTORY_INTRO),
        metric_control(metric),
        *c11(metric, states, figures),
        *table,
        labels.glossary(HISTORY_FIELDS, ident=HISTORY_GLOSSARY_ID, page_only=PAGE_ONLY),
    ], True


def render(
    body: dict[str, Any],
    year: int,
    n2: Any = None,
    index: Any = None,
    metric: str = DEFAULT_METRIC,
) -> tuple[html.Div, bool]:
    """The page body for the roster response of ``year``, and whether C11's control
    shows: the history section (#641) first, from N2's response ``n2`` and the index,
    with C11 drawing ``metric`` (#623), then the list of states, each in its own card
    (#567, D111), so the map and the table are not under 51 links on a phone (owner,
    #641's plan gate). The page's URL control renders only with C11's control."""
    states = roster(body, year)
    section, chooser = history_section(n2, states, index, metric)
    location = [dcc.Location(id=URL_ID, refresh="callback-nav")] if chooser else []
    return html.Div(
        [
            *location,
            components.card(section),
            components.card(
                [
                    html.Ul(
                        [
                            html.Li(
                                dcc.Link(link_text(usps, name), href=f"/state/{usps}")
                            )
                            for usps, name in states
                        ],
                        id=LIST_ID,
                        className="states",
                    )
                ]
            ),
            components.provenance_footer(body["meta"]["provenance"]),
        ],
        id=PAGE_ID,
    ), chooser


def layout(**params: Any) -> html.Div:
    """The page. On success its lede is followed by :data:`FILTER_SENTENCE` only where
    C11's control renders: never on the whole page's or the section's degraded
    state."""
    lede = LEDE
    try:
        with api.CLIENT.view() as view:
            # From the cached index, never from the query (``?year_max=`` included).
            index = view.get(api.ELECTIONS_PATH)
            year_max = api.coverage_vars(index)
            body = view.get(api.ROSTER_PATH.format(**year_max))
            # N2 in its own try (D096(d)'s rule): unread, only its section degrades.
            try:
                n2 = view.get(api.ELECTION_STATES_PATH)
            except api.ApiUnavailable:
                n2 = None
        content, chooser = render(
            body,
            int(year_max["year_max"]),
            n2,
            index,
            chosen_metric(parse_metric(params)),
        )
        if chooser:
            lede = f"{LEDE} {FILTER_SENTENCE}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1("States"),
            html.P(lede, className="lede"),
            content,
        ]
    )
