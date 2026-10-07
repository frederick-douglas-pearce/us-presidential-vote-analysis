"""The state picker (#279): every state and DC in the dataset, linked to its history.

The roster comes from the latest election's rows, ``/v1/elections/{year_max}``
(:data:`explore.api.ROSTER_PATH`), since every state and DC takes part in it; there is
no second copy of it (D006). ``year_max`` is read from the prefetched ``/v1/elections``
and checked to be a year it serves (:func:`explore.api.coverage_vars`), never from the
request. The roster is filled on a miss and shared with every ``/state/<usps>`` page,
which validates its code against it.
"""

from __future__ import annotations

from typing import Any

import dash
from dash import dcc, html

from explore import api, components, query
from explore.config import SITE_TITLE

#: The wrapper every successful render carries: the list of states.
PAGE_ID = "states"
LIST_ID = "states-list"

dash.register_page(
    __name__,
    path="/states",
    title=f"States — {SITE_TITLE}",
    description=(
        "Every US state and DC in the dataset, each linked to its electoral votes "
        "in every presidential election."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH,),
    success=PAGE_ID,
)


def roster(body: Any, year: int) -> list[tuple[str, str]]:
    """``(usps, name)`` for each state the roster's rows name, sorted by name, or
    ``TypeError``.

    Every row must name the year it was read for and carry a USPS code (two ASCII
    capitals), or the body is malformed: a link is built from the code.
    """
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list) or not rows:
        raise TypeError(f"/v1/elections/{year} carries no list of state rows")
    states: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or query.checked_year(row.get("year")) != year:
            raise TypeError(f"/v1/elections/{year} carries a row of another year")
        usps = row.get("state_usps")
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError(f"/v1/elections/{year} carries a malformed state code")
        states[usps] = str(row["state"])
    return sorted(states.items(), key=lambda kv: kv[1])


def render(body: dict[str, Any], year: int) -> html.Div:
    """The page body for the roster response of ``year``."""
    states = roster(body, year)
    return html.Div(
        [
            html.Ul(
                [
                    html.Li(dcc.Link(name, href=f"/state/{usps}"))
                    for usps, name in states
                ],
                id=LIST_ID,
                className="states",
            ),
            components.provenance_footer(body["meta"]["provenance"]),
        ],
        id=PAGE_ID,
    )


def layout(**_query: Any) -> html.Div:
    try:
        with api.CLIENT.view() as view:
            # From the cached index, never from the query (``?year_max=`` included).
            year_max = api.coverage_vars(view.get(api.ELECTIONS_PATH))
            body = view.get(api.ROSTER_PATH.format(**year_max))
        content = render(body, int(year_max["year_max"]))
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div(
        [
            html.H1("States"),
            html.P(
                "Every state and DC in this dataset. Open one to see its electoral "
                "votes in every election it took part in.",
                className="lede",
            ),
            content,
        ]
    )
