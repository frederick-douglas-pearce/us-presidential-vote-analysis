"""The state pages' shared pieces (#559).

Each state has two pages: its history at ``/state/<usps>`` (``pages/state.py``, T4)
and its people per electoral vote at ``/state/<usps>/per-capita``
(``pages/state_per_capita.py``, T7), split as the election pages were (D092, #465). A
page module cannot import another (Dash executes it before it is in ``sys.modules``),
so what they share lives here, as :mod:`explore.election_view` holds the election
pages' pieces: the section suffixes, the roster reading and the judge built on it,
the checks of a state's rows, the section links and the not-found state. The state
picker (``pages/states.py``) reads the roster through the same :func:`roster`, so a
body one refuses both refuse.

A shared module, like ``components`` and ``labels``: pure functions of what a page
already read, importing nothing from ``explore`` but ``labels`` and ``query``, never
``api`` or ``config`` (``TestSharedPieces``). Each page builds its own ``VALIDATE``
from :func:`on_roster` and ``api.ROSTER_PATH``. Its reader-facing words are in
:mod:`explore.labels`; this module is structure only.
"""

from __future__ import annotations

from typing import Any

from dash import dcc, html

from explore import labels, query

#: The state pages' path suffixes, in page order (#559): the history and the people
#: per electoral vote. The single source for each page's path template, the section
#: links and each download's view URL.
HISTORY = ""
PER_CAPITA = "/per-capita"
SECTIONS = (HISTORY, PER_CAPITA)

#: Each section's link text, by suffix.
SECTION_TEXT = {
    HISTORY: labels.SECTION_STATE_HISTORY,
    PER_CAPITA: labels.SECTION_PER_CAPITA,
}


def template(section: str) -> str:
    """A section's Dash path template."""
    return f"/state/<usps>{section}"


def path(usps: str, section: str) -> str:
    """A section's path for a served state, with no query."""
    return f"/state/{usps}{section}"


# --- the roster and the state's rows -------------------------------------------------


def rows_of(body: Any) -> list[Any]:
    """A body's ``data`` rows; ``[]`` for a malformed body."""
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else []


def roster(body: Any) -> tuple[int, dict[str, str]]:
    """The year a roster response names and each state in it, ``{usps: name}``, or
    ``TypeError``.

    The one reading of the roster's body (``api.ROSTER_PATH``), shared by the state
    pages' judge and the picker, so a body this refuses all refuse (#279): a non-empty
    list of rows, every one naming the same checked year and a USPS code (two ASCII
    capitals) with a state name. Each caller also requires that year to be the latest
    election. Moved here from ``api`` by #559, since a shared module reads no ``api``.
    """
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list) or not rows:
        raise TypeError("the roster carries no list of state rows")
    years: set[int | None] = set()
    states: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("the roster carries a row that is not an object")
        years.add(query.checked_year(row.get("year")))
        usps, name = row.get("state_usps"), row.get("state")
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError("the roster carries a malformed state code")
        if not isinstance(name, str):
            raise TypeError("the roster carries a malformed state name")
        states[usps] = name
    year = years.pop() if len(years) == 1 else None
    if year is None:
        raise TypeError("the roster's rows do not name one election year")
    return year, states


def on_roster(path_vars: dict[str, Any], body: Any) -> bool:
    """Whether ``path_vars["usps"]`` is a state the roster names.

    Pure and total: a USPS code (two ASCII capitals) among the states :func:`roster`
    reads, never a literal. A malformed roster names no state, and neither does one
    whose rows name another year than its own ``coverage.year_max``: the judge has only
    the roster's body, so that is the latest election it can check against (the picker
    checks the index's, the same snapshot). A greedy ``<usps>`` holding a section the
    site does not have (``GA/x``) is no USPS code, so it is refused.
    """
    usps = path_vars.get("usps")
    if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
        return False
    try:
        named, states = roster(body)
        latest = query.checked_year(body["meta"]["provenance"]["coverage"]["year_max"])
    except (KeyError, TypeError):
        return False
    return named == latest and usps in states


def served_years(index: Any) -> set[int]:
    """The years a ``/v1/elections`` body serves, each checked by
    :func:`explore.query.checked_year`, or ``TypeError`` if it serves none."""
    years = {
        year
        for row in rows_of(index)
        if isinstance(row, dict) and (year := query.checked_year(row.get("year")))
    }
    if not years:
        raise TypeError("/v1/elections serves no year")
    return years


def rows(body: Any, usps: str, served: set[int], source: str) -> list[dict[str, Any]]:
    """The state's rows from the API path ``source``, sorted by year then candidate,
    or ``TypeError``.

    A served state always has rows, so an empty list is a malformed body: rendering it
    would show the success marker over an empty table. Each row must name this state
    and a year the index serves (checked by :func:`explore.query.checked_year`), so no
    row of another state, or of a year the dataset does not hold, is shown. The same
    rule reads T4's rows and T7's ``/per-capita`` rows (#280), which name no candidate.
    """
    found = rows_of(body)
    if not found:
        raise TypeError(f"{source} carries no list of rows")
    for row in found:
        if not isinstance(row, dict) or row.get("state_usps") != usps:
            raise TypeError(f"{source} carries a row of another state")
        if query.checked_year(row.get("year")) not in served:
            raise TypeError(f"{source} carries a row of no served year")
    return sorted(found, key=lambda r: (r["year"], str(r.get("candidate", ""))))


# --- the section links and the not-found state ---------------------------------------

#: The section links' landmark (#559) and the class ``style.css`` draws it by, which
#: the election pages' section links share.
SECTIONS_ID = "state-sections"
SECTIONS_CLASS = "section-links"


def year_search(year_from: int, year_to: int, span: tuple[int, int]) -> str:
    """The year range a render applied, as the query a section link carries (#559), in
    the normal form ``og:url`` uses (``""`` or ``?…``): a bound at its end of the span
    is the default and is omitted. Built from bounds already checked against the span,
    never from the request."""
    params = query.year_range_search([year_from, year_to], *span)
    return query.encode_search(params.items())


def section_nav(usps: str, current: str, search: str) -> html.Nav:
    """The links between the state's two pages (#559), in page order: the page being
    read is text carrying ``aria-current="page"`` (a ``dcc.Link`` renders no
    ``aria-*``, and a link to itself would be no link), the other a client-side link
    carrying ``search``, the year range the render applied and nothing else (the
    election pages' section links carry no filter; both state pages read the year
    range, D105)."""
    aria_current: dict[str, Any] = {"aria-current": "page"}
    entries = [
        html.Span(SECTION_TEXT[section], **aria_current)
        if section == current
        else dcc.Link(SECTION_TEXT[section], href=f"{path(usps, section)}{search}")
        for section in SECTIONS
    ]
    aria: dict[str, Any] = {"aria-label": labels.STATE_SECTIONS_LABEL}
    return html.Nav(entries, id=SECTIONS_ID, className=SECTIONS_CLASS, **aria)


def not_found(content_id: str) -> html.Div:
    """A link that names no page of a state the dataset serves: said plainly, with the
    way back, under :data:`explore.labels.STATE_NOT_FOUND_HEADING` and no lede (#325),
    the same on both state pages; ``content_id`` is the page's own not-found id."""
    return html.Div(
        [
            html.P(labels.STATE_NOT_FOUND_SENTENCE),
            dcc.Link(labels.STATE_NOT_FOUND_LINK, href="/states"),
        ],
        id=content_id,
    )
