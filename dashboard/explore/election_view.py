"""The election pages' shared pieces (#465).

Each election has three pages: the overview at ``/election/<year>`` (``pages/
election.py``), its results by state at ``/election/<year>/states`` (``pages/
election_states.py``) and its people per electoral vote at ``/election/<year>/
per-capita`` (``pages/election_per_capita.py``). A page module cannot import another
(Dash executes it before it is in ``sys.modules``), so what they share lives here: the
section suffixes, the checks of the year's bodies, the filter parsers, the earlier and
later links, the section links and the not-found state.

A shared module, like ``components`` and ``labels``: pure functions of what a page
already read, importing nothing from ``explore`` but the other shared modules, never
``api`` or ``config`` (``TestSharedPieces``). Each page builds its own ``VALIDATE``
from :func:`served_year` and ``api.ELECTIONS_PATH``. Its reader-facing words are in
:mod:`explore.labels`; this module is structure only.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from dash import dcc, html

from explore import labels, query

#: The election pages' path suffixes, in page order (#465): the overview, results by
#: state and people per electoral vote. The single source for each page's path
#: template, the earlier and later links, the section links, each download's view URL
#: and the overview's redirect target.
OVERVIEW = ""
STATES = "/states"
PER_CAPITA = "/per-capita"
SECTIONS = (OVERVIEW, STATES, PER_CAPITA)

#: Each section's link text, by suffix.
SECTION_TEXT = {
    OVERVIEW: labels.SECTION_OVERVIEW,
    STATES: labels.SECTION_STATES,
    PER_CAPITA: labels.SECTION_PER_CAPITA,
}


def template(section: str) -> str:
    """A section's Dash path template."""
    return f"/election/<year>{section}"


def path(year: int | str, section: str) -> str:
    """A section's path for a served year; no query (filters never carry across)."""
    return f"/election/{year}{section}"


# --- the year's bodies ---------------------------------------------------------------


def year_rows(body: Any) -> list[Any]:
    """A ``/v1/elections`` body's rows; ``[]`` for a malformed body."""
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else []


def row_year(row: Any) -> int | None:
    """A row's year, checked by :func:`explore.query.checked_year`; else ``None``."""
    return query.checked_year(row.get("year")) if isinstance(row, dict) else None


def served_year(path_vars: dict[str, Any], body: Any) -> bool:
    """Whether ``path_vars["year"]`` is a year ``/v1/elections`` serves.

    Pure and total: four ASCII digits, equal to a row year of the index (each checked
    by :func:`explore.query.checked_year`), never a literal. A malformed body serves
    nothing.
    """
    year = path_vars.get("year")
    if not isinstance(year, str) or not query.YEAR_RE.fullmatch(year):
        return False
    return any(row_year(row) == int(year) for row in year_rows(body))


def index_row(index: dict[str, Any], year: str) -> dict[str, Any]:
    """The year's row of ``/v1/elections``; ``KeyError`` if it has none."""
    for row in year_rows(index):
        if row_year(row) == int(year):
            return dict(row)
    raise KeyError(year)


class Neighbours(NamedTuple):
    """The nearest year before and after one that the index serves; ``None`` where
    there is none."""

    earlier: int | None
    later: int | None


def neighbours(body: Any, year: int) -> Neighbours:
    """The served years either side of ``year`` in a ``/v1/elections`` body (#324).

    Pure and total: read from the index's rows (each checked by
    :func:`explore.query.checked_year`, a malformed row skipped as :func:`served_year`
    skips it), never computed from ``year``, so the ends and any gap in the served
    years are right.
    """
    years = {y for y in map(row_year, year_rows(body)) if y is not None}
    return Neighbours(
        earlier=max((y for y in years if y < year), default=None),
        later=min((y for y in years if y > year), default=None),
    )


def rows(value: Any, year: int, name: str, source: str) -> list[Any]:
    """A non-empty list of the year's rows from the API path ``source``, each naming
    that year, or ``TypeError``.

    A served year always has state rows, and the API treats a year with no national
    summary as a build regression, so an empty list is a malformed body: rendering it
    would show the success marker over an empty table. Each row's year is checked
    against the validated one, so no row of another year (or of no year) is shown,
    and the cells read the validated year rather than the row's.
    """
    if not isinstance(value, list) or not value:
        raise TypeError(f"{source} carries no list of {name}")
    if any(row_year(row) != year for row in value):
        raise TypeError(f"{source} carries {name} of another year")
    return value


# --- the filters ---------------------------------------------------------------------

#: The query keys T2's filters read on the states page: the API's own filter names
#: for a state and a candidate, and the field names of the two closed vocabularies.
#: The per-capita page reads :data:`STATE` only.
STATE = "state"
CANDIDATE = "candidate"
PV_STATUS = "pv_status"
COUNT_STATUS = "electoral_count_status"
#: The keys the states page reads, which the overview's redirect moves (#465).
STATES_KEYS = (STATE, CANDIDATE, PV_STATUS, COUNT_STATUS)


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """T2's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``.
    Keeps ``state`` only as a USPS code, ``candidate`` only as a slug, and the two
    statuses only as one of their closed values; a key repeated with differing values
    is dropped, and so is a key it does not know. Never emits ``year``, the path
    variable. Whether a state or candidate is in this year's results is the layout's
    question.
    """
    if not isinstance(params, dict):
        return []
    kept: dict[str, str] = {}
    state = query.single(params.get(STATE))
    if state is not None and query.USPS_RE.fullmatch(state):
        kept[STATE] = state
    candidate = query.single(params.get(CANDIDATE))
    if candidate is not None and query.is_slug(candidate):
        kept[CANDIDATE] = candidate
    pv_status = query.single(params.get(PV_STATUS))
    if pv_status in labels.PV_STATUS:
        kept[PV_STATUS] = pv_status
    count_status = query.single(params.get(COUNT_STATUS))
    if count_status in labels.COUNT_STATUS:
        kept[COUNT_STATUS] = count_status
    return sorted(kept.items())


def parse_state(params: Any) -> list[tuple[str, str]]:
    """The per-capita page's one filter (#465), ``state`` as a USPS code, as
    :func:`parse_filters` keeps it; every other key is dropped. Syntactic and total."""
    return [pair for pair in parse_filters(params) if pair[0] == STATE]


# --- the earlier and later links, the section links, the not-found state -------------

#: The earlier and later links' landmark and links (#324, #464). Their bar is drawn by
#: ``style.css`` from the classes, never the ids, so every election page takes it.
NAV_ID = "election-nav"
EARLIER_ID = "election-earlier"
LATER_ID = "election-later"
NEIGHBOR_NAV_CLASS = "neighbor-nav"
NEIGHBOR_EARLIER_CLASS = "neighbor-earlier"
NEIGHBOR_LATER_CLASS = "neighbor-later"


def neighbor_nav(around: Neighbours, section: str) -> list[Any]:
    """The links to the earlier and later served years, on the same section (#465),
    unfiltered (owner, #324's plan gate); a side with no year has no link, and with
    neither there is no landmark. The bar's classes put the earlier link at the left
    and the later at the right, alone or together (#464)."""
    links = [
        dcc.Link(
            text.format(year=year),
            href=path(year, section),
            id=link_id,
            className=side,
        )
        for year, text, link_id, side in (
            (around.earlier, labels.EARLIER_LINK, EARLIER_ID, NEIGHBOR_EARLIER_CLASS),
            (around.later, labels.LATER_LINK, LATER_ID, NEIGHBOR_LATER_CLASS),
        )
        if year is not None
    ]
    if not links:
        return []
    name = (
        labels.ELECTION_NAV_LABEL
        if section == OVERVIEW
        else labels.ELECTION_NAV_SECTION_LABEL.format(section=SECTION_TEXT[section])
    )
    # Dash takes ``aria-*`` as keyword arguments its stubs do not name.
    aria: dict[str, Any] = {"aria-label": name}
    return [html.Nav(links, id=NAV_ID, className=NEIGHBOR_NAV_CLASS, **aria)]


#: The section links' landmark (#465) and the class ``style.css`` draws it by.
SECTIONS_ID = "election-sections"
SECTIONS_CLASS = "election-sections"


def section_nav(year: int, current: str) -> html.Nav:
    """The links between the year's three pages (#465), in page order: the page being
    read is text carrying ``aria-current="page"`` (a ``dcc.Link`` renders no
    ``aria-*``, and a link to itself would be no link), the other two client-side
    links, unfiltered."""
    aria_current: dict[str, Any] = {"aria-current": "page"}
    entries = [
        html.Span(SECTION_TEXT[section], **aria_current)
        if section == current
        else dcc.Link(SECTION_TEXT[section], href=path(year, section))
        for section in SECTIONS
    ]
    aria: dict[str, Any] = {"aria-label": labels.ELECTION_SECTIONS_LABEL}
    return html.Nav(entries, id=SECTIONS_ID, className=SECTIONS_CLASS, **aria)


def not_found(content_id: str) -> html.Div:
    """A year the dataset does not serve: said plainly, with the way back, under
    :data:`explore.labels.ELECTION_NOT_FOUND_HEADING` and no lede (#325), the same on
    every election page; ``content_id`` is the page's own not-found id."""
    return html.Div(
        [
            html.P(labels.ELECTION_NOT_FOUND_SENTENCE),
            dcc.Link(labels.ELECTION_NOT_FOUND_LINK, href="/elections"),
        ],
        id=content_id,
    )
