"""The landing page: where the data comes from and what it covers (#277).

The walking skeleton carries no tables. It proves the path a real view will take: one
canonical API URL, read through the in-process cache, rendered server-side, with a
plain-language message when the API cannot be read.
"""

from __future__ import annotations

from typing import Any

import dash
from dash import html

from explore import api
from explore.config import SITE_TITLE

#: The element only a successful render carries, holding the snapshot version.
SNAPSHOT_ID = "snapshot-version"

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
    # Rendered only from a successful read: the guard's per-page success contract.
    success=SNAPSHOT_ID,
)

#: The three sources, in display order: what each supplies, and the provenance keys
#: naming it and its license.
SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("Electoral votes", "ec_source_name", "ec_license", "ec_license_url"),
    ("Popular votes", "source_name", "license", "license_url"),
    ("Population", "census_source_name", "census_license", "census_license_url"),
)

UNAVAILABLE_MESSAGE = (
    "The election data service isn't responding right now, so there is nothing to "
    "show yet. Please try again in a minute."
)


def _years(first: Any, last: Any) -> str:
    return f"{first}–{last}"


def render(meta: dict[str, Any]) -> html.Div:
    """The page body for one ``/v1/meta`` response."""
    provenance = meta["provenance"]
    coverage = provenance["coverage"]
    return html.Div(
        [
            html.H2("Where the data comes from"),
            html.Ul(
                [
                    html.Li(
                        [
                            html.Span(f"{label}: ", className="label"),
                            f"{provenance[name]} (",
                            # str(): a value of an unexpected type renders as text,
                            # rather than failing in Dash's serializer, outside
                            # layout()'s try.
                            html.A(
                                str(provenance[lic]), href=str(provenance[url])
                            ),
                            ")",
                        ]
                    )
                    for label, name, lic, url in SOURCES
                ],
                id="provenance",
            ),
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
                id="coverage",
            ),
            html.P(
                ["Data snapshot ", html.Code(str(provenance["snapshot_version"]))],
                className="snapshot",
                id=SNAPSHOT_ID,
            ),
        ]
    )


def unavailable() -> html.Div:
    """The degraded state: a plain sentence, never an exception or a blank page."""
    return html.Div(
        html.P(UNAVAILABLE_MESSAGE), className="unavailable", id="unavailable"
    )


def layout(**_query: Any) -> html.Div:
    try:
        with api.CLIENT.view() as view:
            body = render(view.get(api.META_PATH))
    except (api.ApiUnavailable, KeyError, TypeError):
        body = unavailable()
    return html.Div(
        [
            html.H1("US Presidential Election Center"),
            html.P(
                "Tables and charts over the public election data are on their way. "
                "For now, this page shows what the data is and where it comes from.",
                className="lede",
            ),
            body,
        ]
    )
