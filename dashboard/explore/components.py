"""View pieces every page shares: the provenance footer, the degraded state (#306), the
year-range slider every year-filtered table uses (#279), and the table itself with its
CSV download (#309).

Pure functions of what a page already read, so they read no API: a page reads through
its own render-scoped view and hands them what it read.
``TestSharedPieces.test_the_shared_modules_read_no_api`` (in
``test_dashboard_elections.py``) checks that this module imports nothing from
``explore`` but the other shared modules, and names no ``api`` or ``CLIENT``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from dash import dcc, html

from explore import export, labels

#: The id of the paragraph carrying the snapshot version.
SNAPSHOT_ID = "snapshot-version"

#: The id of the footer's list of sources.
PROVENANCE_ID = "provenance"

#: The three sources, in display order: what each supplies, and the provenance keys
#: naming it and its license. The CSV preamble names the same triples (#309).
SOURCES: tuple[tuple[str, str, str, str], ...] = (
    export.EC_SOURCE,
    export.PV_SOURCE,
    export.CENSUS_SOURCE,
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


#: Years between slider labels; an interior label nearer an end than half of this is
#: dropped, so the end labels never run into it on a phone.
MARK_STEP = 40


def year_marks(first: int, last: int) -> dict[int, str]:
    """A range slider's labels: both ends, and every :data:`MARK_STEP` years between."""
    interior = range((first // MARK_STEP + 1) * MARK_STEP, last, MARK_STEP)
    keep = [y for y in interior if min(y - first, last - y) >= MARK_STEP // 2]
    return {year: str(year) for year in sorted({first, last, *keep})}


def year_slider(
    slider_id: str, first: int, last: int, chosen: tuple[int, int]
) -> dcc.RangeSlider:
    """The year-range control over a served span ``first``–``last``.

    No ``persistence``: it would override the URL, which is where the range lives.
    """
    return dcc.RangeSlider(
        id=slider_id,
        min=first,
        max=last,
        step=1,
        value=list(chosen),
        allowCross=False,
        allow_direct_input=False,
        marks=year_marks(first, last),
        tooltip={"placement": "bottom"},
    )


#: A table's sentence when its filters leave no rows.
NO_ROWS = "No rows match these filters."


def table(
    rows: Sequence[dict[str, Any]],
    render_row: Callable[[dict[str, Any]], html.Tr],
    fields: tuple[str, ...],
    table_id: str,
    download: export.Download,
    *,
    extra: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    empty: str = NO_ROWS,
) -> list[Any]:
    """A table, its CSV download and its notes (#309).

    Every table goes through here: ``TestEveryTable`` in ``test_dashboard_export.py``
    records each call while rendering every registered page and fails a rendered table
    it did not build. The body and the CSV are built from the one list ``rows``, so the
    file holds exactly the rows the table shows, in the same order. The CSV's columns
    are the table's ``fields`` in display order, then ``extra`` (the count reason a cell
    shows, and the keys a filter or another year needs, which the table shows only
    inside a cell or not at all). ``notes`` are shown under the table and written into
    the file's preamble, so what they explain is explained in both. With no rows, there
    is no table and nothing to download: ``empty`` says so. The link is the scroll
    box's next sibling, outside it, so it never scrolls away with the table.
    """
    shown = [html.P(note, className="note") for note in notes]
    if not rows:
        return [html.P(empty, className="empty"), *shown]
    text = export.csv_text((*fields, *extra), rows, download, notes)
    return [
        # Wider than a phone: the table scrolls sideways inside its box, the page never.
        html.Div(
            html.Table(
                [
                    html.Thead(html.Tr([labels.header(field) for field in fields])),
                    html.Tbody([render_row(row) for row in rows]),
                ],
                id=table_id,
            ),
            className="table-scroll",
        ),
        export.link(table_id, download, text),
        *shown,
    ]
