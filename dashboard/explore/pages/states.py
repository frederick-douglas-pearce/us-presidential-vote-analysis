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
stay. Chart C11's map (#623) is to join the section.
"""

from __future__ import annotations

from typing import Any

import dash
from dash import dcc, html

from explore import api, components, export, labels, state_view
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

#: The page's wording (#641; ba spec, approved at its plan gate, 2026-11-25). The lede
#: is true on every state the page renders, the section's degraded one included.
LEDE = (
    "Every state and DC in this dataset, and how their histories in it compare. "
    "Each state also has pages of its own."
)
DESCRIPTION = (
    "Every US state and DC in this dataset, compared on elections with electors "
    "appointed, first election, elections with a popular vote to choose electors, and "
    "change in electors appointed, with a link to each state's pages."
)
STATES_HISTORY_HEADING = "State histories compared"
STATES_HISTORY_INTRO = (
    "The figures each state's own history page shows, side by side for every state "
    "and DC. They cover only the elections in this dataset."
)
#: The section's sentence when N2 cannot be read or is malformed: never
#: ``UNAVAILABLE_MESSAGE``'s wording, which means the whole page.
STATES_HISTORY_UNAVAILABLE = (
    "The table of each state's history figures can't be shown right now. Please try "
    "again in a minute."
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

dash.register_page(
    __name__,
    path="/states",
    title=f"States — {SITE_TITLE}",
    description=DESCRIPTION,
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, api.ELECTION_STATES_PATH),
    success=PAGE_ID,
    # The site navigation link this page marks (#448):
    # the state picker marks its own link.
    nav="states",
)


def roster(body: Any, year: int) -> list[tuple[str, str]]:
    """``(usps, name)`` for each state the roster names, sorted by name, or
    ``TypeError``.

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


def figure_cell(figures: state_view.HistoryFigures | None, key: str) -> Any:
    """One figure's cell (#641): :data:`explore.labels.UNAVAILABLE_CELL` for a refused
    state, else the value half of the state page's figure
    (:func:`explore.state_view.history_cell`), the popular-vote count with its N
    (:data:`explore.labels.STATES_COUNT_OF`) where it has a figure: where
    :func:`explore.state_view.history_cell` gives it a rest, which
    :func:`explore.labels.metric_count` does only for a recognized count with an N."""
    if figures is None:
        return labels.cell(labels.UNAVAILABLE_CELL)
    value, rest = state_view.history_cell(figures, key)
    if key == "state_pv_elections_count" and rest is not None:
        pv = figures.popular_vote
        value = labels.STATES_COUNT_OF.format(count=pv.count, n=pv.n)
    return labels.cell(value)


def history_section(n2: Any, states: list[tuple[str, str]], index: Any) -> list[Any]:
    """The history section's children (#641, D123): its heading, then the table, its
    notes and column-name list, or :data:`STATES_HISTORY_UNAVAILABLE` alone where N2
    (``n2``, ``None`` when it could not be read) or its rows cannot be read.
    Everything built from N2 is inside the ``try``; a chart (#623) is to sit outside
    it (D095(f))."""
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
        ]
    return [
        heading,
        html.P(STATES_HISTORY_INTRO),
        *table,
        labels.glossary(HISTORY_FIELDS, ident=HISTORY_GLOSSARY_ID, page_only=PAGE_ONLY),
    ]


def render(
    body: dict[str, Any], year: int, n2: Any = None, index: Any = None
) -> html.Div:
    """The page body for the roster response of ``year``: the history section (#641)
    first, from N2's response ``n2`` and the index, then the list of states, each in
    its own card (#567, D111), so the table, and later the map, is not under 51 links on
    a phone (owner, #641's plan gate)."""
    states = roster(body, year)
    return html.Div(
        [
            components.card(history_section(n2, states, index)),
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
    )


def layout(**_query: Any) -> html.Div:
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
        content = render(body, int(year_max["year_max"]), n2, index)
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1("States"),
            html.P(LEDE, className="lede"),
            content,
        ]
    )
