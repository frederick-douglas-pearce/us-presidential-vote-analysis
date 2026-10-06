"""View pieces every page shares: the provenance footer and the degraded state (#306).

Pure functions of what a page already read, so they read no API: a page reads through
its own render-scoped view and hands them what it read.
``TestSharedPieces.test_the_shared_modules_read_no_api`` (in
``test_dashboard_elections.py``) checks that this module imports nothing from
``explore`` and names no ``api`` or ``CLIENT``.
"""

from __future__ import annotations

from typing import Any

from dash import html

#: The id of the paragraph carrying the snapshot version.
SNAPSHOT_ID = "snapshot-version"

#: The id of the footer's list of sources.
PROVENANCE_ID = "provenance"

#: The three sources, in display order: what each supplies, and the provenance keys
#: naming it and its license.
SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("Electoral votes", "ec_source_name", "ec_license", "ec_license_url"),
    ("Popular votes", "source_name", "license", "license_url"),
    ("Population", "census_source_name", "census_license", "census_license_url"),
)

#: The degraded state's sentence. ``scripts/probe_dashboard.sh`` greps the routed root
#: page for "isn't responding", so the wording is load-bearing.
UNAVAILABLE_MESSAGE = (
    "The election data service isn't responding right now, so there is nothing to "
    "show yet. Please try again in a minute."
)


def provenance_footer(provenance: dict[str, Any]) -> html.Footer:
    """Each source named with its license linked, and the snapshot version.

    Built from a response's ``provenance`` (``/v1/meta``'s, or the ``meta.provenance``
    every other ``/v1`` response carries), so it cannot drift from the snapshot served.
    """
    return html.Footer(
        [
            html.H2("Where the data comes from"),
            html.Ul(
                [
                    html.Li(
                        [
                            html.Span(f"{label}: ", className="label"),
                            f"{provenance[name]} (",
                            # str(): a value of an unexpected type renders as text,
                            # rather than failing in Dash's serializer, outside the
                            # page layout's try.
                            html.A(str(provenance[lic]), href=str(provenance[url])),
                            ")",
                        ]
                    )
                    for label, name, lic, url in SOURCES
                ],
                id=PROVENANCE_ID,
            ),
            html.P(
                ["Data snapshot ", html.Code(str(provenance["snapshot_version"]))],
                className="snapshot",
                id=SNAPSHOT_ID,
            ),
        ],
        className="provenance-footer",
    )


def unavailable() -> html.Div:
    """The degraded state: a plain sentence, never an exception or a blank page."""
    return html.Div(
        html.P(UNAVAILABLE_MESSAGE), className="unavailable", id="unavailable"
    )
