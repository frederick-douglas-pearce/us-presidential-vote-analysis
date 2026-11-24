"""The state pages' shared pieces (#559, #619).

Each state has three pages: its history at ``/state/<usps>`` (``pages/state.py``, C7
and C10), its results by election at ``/state/<usps>/elections``
(``pages/state_results.py``, T4) and its people per electoral vote at
``/state/<usps>/per-capita`` (``pages/state_per_capita.py``, T7), split as the
election pages were (D092, #465; D105, D118). A
page module cannot import another (Dash executes it before it is in ``sys.modules``),
so what they share lives here, as :mod:`explore.election_view` holds the election
pages' pieces: the section suffixes, the roster reading and the judge built on it,
the checks of a state's rows, the section links and the not-found state. The state
picker (``pages/states.py``) reads the roster through the same :func:`roster`, so a
body one refuses both refuse.

It also holds the state history's headline figures over one state's per-year records,
:func:`history_figures` (#621, D120), so the ``/states`` map (#623) computes exactly
what each state's page shows: the rule of an election with electors appointed and the
popular-vote flag live here, the arithmetic in :mod:`explore.metrics`.

A shared module, like ``components`` and ``labels``: pure functions of what a page
already read, importing nothing from ``explore`` but ``labels``, ``metrics`` and
``query``, never ``api`` or ``config`` (``TestSharedPieces``). Each page builds its own
``VALIDATE`` from :func:`on_roster` and ``api.ROSTER_PATH``. Its reader-facing words
are in :mod:`explore.labels`; this module words nothing.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from dash import dcc, html

from explore import labels, metrics, query

#: The state pages' path suffixes, in page order (#559, #619): the history, the
#: results by election and the people per electoral vote. The single source for each
#: page's path template, the section links and each download's view URL.
HISTORY = ""
RESULTS = "/elections"
PER_CAPITA = "/per-capita"
SECTIONS = (HISTORY, RESULTS, PER_CAPITA)

#: Each section's link text, by suffix.
SECTION_TEXT = {
    HISTORY: labels.SECTION_STATE_HISTORY,
    RESULTS: labels.SECTION_RESULTS_BY_ELECTION,
    PER_CAPITA: labels.SECTION_PER_CAPITA,
}

#: The history page's query keys that T4 took with it to the results page (#619,
#: D118): an old ``/state/<usps>?candidate=…`` or ``?pv_status=…`` link answers 302 to
#: :data:`RESULTS` (D092's ``moved=``). The year range is not moved: the section links
#: write it on every state page's URL, and the history page reads it (#620, D119).
MOVED_KEYS = ("candidate", "pv_status")


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
    rows = rows_of(body)
    if not rows:
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
    """The links between the state's three pages (#559, #619), in page order: the page
    being read is text carrying ``aria-current="page"`` (a ``dcc.Link`` renders no
    ``aria-*``, and a link to itself would be no link), the others client-side links
    carrying ``search``, the year range the render applied and nothing else (the
    election pages' section links carry no filter; D105). The history page carries the
    range it applied, judged against the state's own span (#620, D119)."""
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
    the same on every state page; ``content_id`` is the page's own not-found id."""
    return html.Div(
        [
            html.P(labels.STATE_NOT_FOUND_SENTENCE),
            dcc.Link(labels.STATE_NOT_FOUND_LINK, href="/states"),
        ],
        id=content_id,
    )


def allotment(value: object) -> int | None:
    """An allotment the figures can read: an ``int`` (never a ``bool``) at or above 0
    that :func:`explore.labels.finite` accepts (so not too large for a float, which a
    select and a change refuse), else ``None`` (#601, D115; moved here and the finite
    check added by #621, D120). C7 draws a null or a malformed allotment as a marker;
    the figures cannot count such a year either way, so all of them read
    unrecognized. The one rule of an election with electors appointed: an allotment
    this reads as above 0 (:func:`first_election`, :func:`history_figures`)."""
    if type(value) is int and value >= 0 and labels.finite(value) is not None:
        return value
    return None


def first_election(records: list[dict[str, Any]]) -> int | None:
    """The state's first election (#620, D119; moved here by #621, D120): the first
    year of its per-year ``records`` (C7's collapse) whose :func:`allotment` is above
    0, the one rule the election count and :func:`history_figures` use (D115(c));
    ``None`` if no year has one, which served data never has. Pure. The history page's
    year span starts here; :func:`history_figures`' first-election figure is a select
    over the same rule, so the two agree on readable data, and where an allotment no
    figure can read is present this skips it while the figures read unrecognized."""
    years = [r["year"] for r in records if allotment(r["state_electoral_votes"])]
    return min(years) if years else None


#: The ``pv_status`` code a year's flag counts (#621, D120): the state held a popular
#: vote to choose its electors.
POPULAR_VOTE = "popular_vote"
#: The code that contradicts a year with electors appointed (#621, architect M-1).
NOT_PARTICIPATING = "not_participating"


def popular_vote_flags(
    records: list[dict[str, Any]], years: list[int]
) -> list[tuple[int, object]] | None:
    """One ``(year, flag)`` pair per year in ``years`` (the years the state appointed
    electors), for :func:`explore.metrics.flag_count` (#621, D120): true where the
    year's ``pv_status`` is :data:`POPULAR_VOTE`, false for any other code of
    :data:`explore.labels.PV_STATUS` but :data:`NOT_PARTICIPATING`. A null or a blank
    is passed as is, so it is left out of N (D112(a)).

    ``None`` (the figure reads unrecognized) for a code outside the closed set, or
    :data:`NOT_PARTICIPATING` in a year with electors appointed, which contradicts
    itself. A status in a year outside ``years`` (an allotment of 0) is never read, so
    an unknown code there leaves the count as it is; that year's table cell words it
    (owner, #635's review, ge.5; D120). Raises nothing on the records
    :func:`history_figures` has accepted (mappings with an ``int`` year, one per
    year); a missing ``pv_status`` reads as null there, where C7's collapse refuses
    it, which the shared collapse #623 is to move here settles (D120)."""
    by_year = {r.get("year"): r.get("pv_status") for r in records}
    pairs: list[tuple[int, object]] = []
    for year in years:
        status = by_year.get(year)
        if labels.is_blank(status):
            pairs.append((year, status))
            continue
        if not isinstance(status, str) or status not in labels.PV_STATUS:
            return None
        if status == NOT_PARTICIPATING:
            return None
        pairs.append((year, status == POPULAR_VOTE))
    return pairs


class HistoryFigures(NamedTuple):
    """A state's history figures over its per-year records (#621, D120), each as
    :mod:`explore.metrics` computed it: the years it appointed electors in and their
    count, the years with an allotment of 0, its first election (a select over the
    allotment), its elections with a popular vote held (a flag count) and the change
    in its electors. ``unrecognized`` where an allotment no figure can read makes
    every figure unrecognized (D115(c), widened by D120)."""

    unrecognized: bool
    elections: int
    years: tuple[int, ...]
    zeros: tuple[int, ...]
    first: metrics.Selection
    popular_vote: metrics.FlagCount
    change: metrics.Change


#: Every figure unrecognized: an allotment no figure can read.
UNRECOGNIZED_HISTORY = HistoryFigures(
    True,
    0,
    (),
    (),
    metrics.UNRECOGNIZED_SELECTION,
    metrics.UNRECOGNIZED_COUNT,
    metrics.UNRECOGNIZED_CHANGE,
)


def history_figures(records: list[dict[str, Any]]) -> HistoryFigures:
    """The state history's figures over one state's per-year ``records`` (``year``,
    ``state_electoral_votes``, ``pv_status``), the one computation the history page
    (#621) and the ``/states`` map (#623) share, so the two cannot disagree (D120).

    **One record per year.** The page passes C7's collapse (``pages/state.py``
    ``electors``), which guarantees it and refuses a year whose rows disagree. This
    function refuses a year named twice itself: every figure then reads unrecognized
    (:data:`UNRECOGNIZED_HISTORY`), since :mod:`explore.metrics`' select and change do
    not detect a repeated year. That is the backstop; the ``/states`` map (#623) is to
    share the page's collapse, moved here, so the two refuse the same rows (D120).

    An allotment :func:`allotment` cannot read, a year that is not an ``int``, or a
    year named twice makes every figure unrecognized (:data:`UNRECOGNIZED_HISTORY`).
    Total on a list of mappings. The figures
    are over the years with an allotment above 0 (D115(c)); a ``pv_status`` fault makes
    the popular-vote count alone unrecognized (:func:`popular_vote_flags`). Each value's
    cell is :func:`explore.labels.number`'s, the function C7's table cell uses."""
    allotments: list[tuple[int, int]] = []
    for r in records:
        year, value = r.get("year"), allotment(r.get("state_electoral_votes"))
        if type(year) is not int or value is None:
            return UNRECOGNIZED_HISTORY
        allotments.append((year, value))
    if len({year for year, _ in allotments}) != len(allotments):
        return UNRECOGNIZED_HISTORY
    years = sorted(year for year, value in allotments if value)
    zeros = sorted(year for year, value in allotments if value == 0)
    triples: list[tuple[int, object, str]] = [
        (year, value, labels.number(value))
        for year, value in sorted(allotments)
        if value
    ]
    flags = popular_vote_flags(records, years)
    return HistoryFigures(
        False,
        metrics.count(set(years)),
        tuple(years),
        tuple(zeros),
        metrics.select(triples),
        metrics.UNRECOGNIZED_COUNT
        if flags is None
        else metrics.flag_count(flags, True),
        metrics.change(triples),
    )
