"""The landing page: what the data covers and where it comes from (#277, #306).

It reads ``/v1/meta`` through the in-process cache, renders server-side, and shows a
plain-language message when the API cannot be read. The sources and the snapshot version
are the shared provenance footer (:mod:`explore.components`).
"""

from __future__ import annotations

from typing import Any

import dash
from dash import dcc, html

from explore import api, components
from explore.config import SITE_TITLE

#: The element only a successful render carries: the coverage list, home's own content.
COVERAGE_ID = "coverage"

dash.register_page(
    __name__,
    path="/",
    title=SITE_TITLE,
    # No years here: the index HTML never waits on the API, so this text cannot read
    # the coverage windows, and a second copy of them would be a second source of truth.
    description=(
        "Where the US presidential election data comes from and which years it covers."
    ),
    # Every canonical API path this page reads, as prefetched (warmed on each new
    # snapshot version, so no visitor waits on a cold API) or filled on a miss.
    prefetch=(api.META_PATH,),
    on_miss=(),
    # Rendered only from a successful read: this page's success contract, asserted by
    # the D070(b) guard in test_dashboard_guards.py.
    success=COVERAGE_ID,
)


def _years(first: Any, last: Any) -> str:
    return f"{first}–{last}"


def render(meta: dict[str, Any]) -> html.Div:
    """The page body for one ``/v1/meta`` response."""
    provenance = meta["provenance"]
    coverage = provenance["coverage"]
    return html.Div(
        [
            html.H2("What it covers"),
            html.Ul(
                [
                    html.Li(
                        [
                            html.Span("Electoral College: ", className="label"),
                            _years(coverage["year_min"], coverage["year_max"]),
                        ]
                    ),
                    html.Li(
                        [
                            html.Span("Popular vote: ", className="label"),
                            _years(coverage["pv_year_min"], coverage["pv_year_max"]),
                        ]
                    ),
                ],
                id=COVERAGE_ID,
            ),
            html.P(
                dcc.Link("Browse every election in the dataset", href="/elections"),
                className="next",
            ),
            html.P(
                dcc.Link("Browse by state", href="/states"),
                className="next",
            ),
            components.provenance_footer(provenance),
        ]
    )


def layout(**_query: Any) -> html.Div:
    try:
        with api.CLIENT.view() as view:
            body = render(view.get(api.META_PATH))
    except (api.ApiUnavailable, KeyError, TypeError):
        body = components.unavailable()
    return html.Div(
        [
            html.H1("US Presidential Election Center"),
            html.P(
                "Tables and charts over the public election data. Start with the list "
                "of elections, or a state's history; more views are on their way.",
                className="lede",
            ),
            body,
        ]
    )
