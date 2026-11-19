"""The elections pages' shared pieces (#562).

The elections have three pages: the list of elections at ``/elections`` (``pages/
elections.py``), the Electoral College majority at ``/elections/majority`` (``pages/
elections_majority.py``, chart C2) and the electors appointed and total popular vote at
``/elections/over-time`` (``pages/elections_over_time.py``, charts C4 and C5). A page
module cannot import another (Dash executes it before it is in ``sys.modules``), so
what they share lives here: the section paths, the section links, and the check of
N1's ``elections`` items, which all three read.

A shared module, like ``election_view``: pure functions of what a page already read,
importing nothing from ``explore`` but the other shared modules, never ``api`` or
``config`` (``TestSharedPieces``). Its reader-facing words are in
:mod:`explore.labels`; this module is structure only.
"""

from __future__ import annotations

from typing import Any

from dash import dcc, html

from explore import election_view, labels, query

#: The three pages' paths, in page order (#562): the one source for each page's
#: registration, its download's view URL and the section links.
LIST = "/elections"
MAJORITY = "/elections/majority"
OVER_TIME = "/elections/over-time"
SECTIONS = (LIST, MAJORITY, OVER_TIME)
SECTION_TEXT = {
    LIST: labels.SECTION_ELECTIONS_LIST,
    MAJORITY: labels.SECTION_MAJORITY,
    OVER_TIME: labels.SECTION_OVER_TIME,
}

#: The section links' landmark, drawn by the class the election and state pages'
#: section links share (``style.css``).
SECTIONS_ID = "elections-sections"


def section_nav(current: str) -> html.Nav:
    """The links between the three elections pages (#562), in page order, on D092's
    pattern: the page being read is text carrying ``aria-current="page"`` (a
    ``dcc.Link`` renders no ``aria-*``), the other two client-side links, unfiltered.
    Rendered on success only."""
    aria_current: dict[str, Any] = {"aria-current": "page"}
    entries = [
        html.Span(SECTION_TEXT[section], **aria_current)
        if section == current
        else dcc.Link(SECTION_TEXT[section], href=section)
        for section in SECTIONS
    ]
    aria: dict[str, Any] = {"aria-label": labels.ELECTIONS_SECTIONS_LABEL}
    return html.Nav(
        entries, id=SECTIONS_ID, className=election_view.SECTIONS_CLASS, **aria
    )


#: How N1 is named in the errors below: a shared module names no API path (it reads no
#: ``api``), and the pages' ``try`` blocks turn every one into a section's own sentence.
N1 = "N1 (/elections/summary)"


def n1_items(index: dict[str, Any], summary: Any) -> dict[int, dict[str, Any]]:
    """N1's ``elections`` items by year, one for each year the index serves (D096(c)):
    the one check of those items, which C2, the averages (#437, D097) and C4 (#436)
    all call, so the rule for a valid item is in one place. Each refuses more on its
    own reads: C2 a missing ``ec_determinative`` and its rank-1 rule on ``data`` rows,
    the averages a missing margin among the years shown.

    Pure; raises ``KeyError`` for a missing key and ``TypeError`` for a year (in the
    index's rows or in N1's items) that :func:`explore.election_view.row_year` refuses
    or that lies outside the served span, an N1 year the index does not serve, or a
    served year with no ``elections`` item or two. A year the index lists twice is one
    served year: refusing the duplicate is the index's own rule (#334). It reads no
    ``data`` row: those are C2's alone.
    """
    coverage = index["meta"]["provenance"]["coverage"]
    first, last = query.year_span(coverage["year_min"], coverage["year_max"])
    served: set[int] = set()
    for row in index["data"]:
        year = election_view.row_year(row)
        if year is None or not first <= year <= last:
            raise TypeError("/v1/elections names a year outside its served span")
        served.add(year)
    if not isinstance(summary, dict):
        raise TypeError(f"{N1} is not an object")
    items = summary["elections"]
    if not isinstance(items, list):
        raise TypeError(f"{N1} carries no list of elections")
    by_year: dict[int, dict[str, Any]] = {}
    for item in items:
        year = election_view.row_year(item)
        if year is None or year not in served or year in by_year:
            raise TypeError(f"{N1}: a bad elections item")
        by_year[year] = item
    if set(by_year) != served:
        raise TypeError(f"{N1} misses a served year")
    return by_year
