"""One state's history (#279): chart C7, its electors appointed in each election (#560),
chart C10, its total popular vote in each election (#582), and the one table the two
share (#618), with the state's headline figures (#601).

Its results by election (T4, #279) is a page of its own since #619,
``pages/state_results.py``, and its people per electoral vote (T7, #280) since #559,
``pages/state_per_capita.py``; what the three share is in :mod:`explore.state_view`,
and the section links join them (D105, D118). C7 and C10 come from one response,
``/v1/states/{usps}``, filled on a miss, which the results page reads too; they
collapse its rows, one per candidate, to one per election (D106, D113), and their table
joins the two collapses on the year (#618, D117). C7's collapse is
:func:`explore.state_view.electors`, run through :func:`explore.state_view.collapsed`,
the functions the ``/states`` table and map (#641, #623) are to share (#640, D120);
C10's, :func:`popular_totals`, is this page's alone. The state is the path
(``/state/<usps>``, an item singular as ``/states`` is plural), in upper case as the
API writes a USPS code. It is validated against the state roster before it is
formatted into an API path: the latest election's rows (``/v1/elections/{year_max}``,
:data:`explore.api.ROSTER_PATH`), since every state and DC takes part in it
(:func:`explore.state_view.on_roster`). That source is declared in ``on_miss`` and
built from the index's coverage, never from the path, so a code the dataset does not
serve never fills a path built from it: the most it costs is a fill of the shared
roster, once per render until one succeeds, and it 404s at the index once the roster
is cached (#279, D074).

The page's one filter is the year range (``year_from`` / ``year_to``, #620, D119), read
by its one ``query=`` parser and judged against the state's own span, from its first
election (:func:`explore.state_view.first_election`) to the latest served year: the
default view starts at that election, and a bound outside the span falls back to that
end of it. The range narrows C7, C10 and their table together, after each collapse
(both collapses read the state's whole history, which the headline figures summarize
unfiltered). T4's
``candidate`` and ``pv_status`` keys are moved to the results page (``moved=``, D092,
D118), so an old filtered link answers 302 there; the parser drops both. A filter change
is written to a page-local ``dcc.Location`` and re-rendered from the cache. The
provenance footer comes from the response's own ``meta.provenance``.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import (
    api,
    charts,
    components,
    export,
    labels,
    metrics,
    over_time,
    query,
    state_view,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries.
PAGE_ID = "state"
#: The wrapper of the not-found state: a code the dataset does not serve, or a section
#: the site does not have (``/state/GA/x``).
NOT_FOUND_ID = "state-not-found"
#: T4's ids here (``state-history``, its download's ``state-history-csv``, and the
#: filters' ``state-url``, ``state-years``, ``state-candidate`` and
#: ``state-pv-status``) are retired with T4's move, never reused (D097(g), D118).

#: Chart C7 (#560, D106): the state's electors appointed in each election. Its
#: companion table, narrowed with it by the Years filter (#620, D119), is the one C10
#: shares since #618 (D117): it kept C7's id and C10's, ``state-popular-total``, is
#: retired, never reused (D097(g)).
C7_ID = "C7"
ELECTORS_TABLE_ID = "state-electors"
ELECTORS_GLOSSARY_ID = "state-electors-glossary"
#: The sentence in C7's place (D096(d)'s rule) when the state's rows cannot be read as
#: one allotment per election.
C7_UNAVAILABLE_ID = "state-electors-unavailable"
#: The sentence in the shared table's place when neither chart can be built (D117).
ELECTORS_TABLE_UNAVAILABLE_ID = "state-electors-table-unavailable"
#: The Years filter (#620, D119): its slider, the page-local Location a change is
#: written to, and the note in place of C7, C10 and their table when the range holds
#: no election. New ids: D118(b)'s ``state-years`` and ``state-url`` stay retired.
YEARS_ID = "state-history-years"
URL_ID = "state-history-url"
NO_MATCH_ID = "state-history-no-match"
#: The note under the figures while a narrower range than the state's span applies.
METRICS_ALL_YEARS_ID = "state-history-metrics-all-years"

#: The headline figures (#601, D112(e), (g), D115): the block and each figure's value,
#: by metric key, in display order, the page's one per-key table (D114(d)); DOM ids are
#: stable and never renamed (D097(g)). First in C7's card, above the Years filter,
#: which does not reach them (#634, D122).
METRICS_ID = "state-history-metrics"
METRIC_IDS = {
    "state_elections_count": "state-elections-count",
    # #621 (D120), in the display order the owner approved, ids appended to the set.
    "state_first_election": "state-first-election",
    "state_pv_elections_count": "state-pv-elections-count",
    "state_electors_change": "state-electors-change",
    "state_took_office_count": "state-took-office-count",
}
#: The note under the figures naming the years with no electors appointed.
METRICS_NOTE_ID = "state-history-metrics-note"
#: The shared table's columns, by public field name, append-only from C7's own table
#: (#618), and what its CSV adds.
ELECTORS_FIELDS = ("year", "state_electoral_votes", "pv_status", "state_popular_total")
ELECTORS_EXTRA = ("state_usps",)

#: Chart C10 (#582, D113): the state's total popular vote in each election, directly
#: below C7; its companion table is C7's (#618, D117).
C10_ID = "C10"
#: The sentence in C10's place (D096(d)'s rule) when the state's rows cannot be read as
#: one total per election. Its id keeps the retired table's prefix and is live (D117).
C10_UNAVAILABLE_ID = "state-popular-total-unavailable"
#: What C10's figure is drawn with: C5's figure, one state's (#582, D113), on C7's
#: year-tick size, since the two stack on one page.
C10_CHART = over_time.TotalChart(
    name=labels.LABELS["state_popular_total"],
    marker_labels=labels.C10_MARKER_LABELS,
    symbols=over_time.C10_SYMBOLS,
    tick_px=components.YEAR_TICK_FONT_PX,
)

#: The not-found state (#325), shared by the three state pages (#559, #619).
NOT_FOUND = api.NotFound(
    labels.STATE_NOT_FOUND_HEADING, labels.STATE_NOT_FOUND_SENTENCE
)

#: The lede, on a successful render and on the degraded state, the not-found state none
#: (#325). People per electoral vote left it with T7 (#559), and each candidate's
#: electoral votes with T4 (#619; ba spec, approved at its plan gate, 2026-11-23). The
#: filter sentence follows it only where the Years slider renders (#620, D119; ba spec,
#: approved at #620's plan gate, 2026-11-23).
LEDE = (
    "This state's electors appointed in every election this dataset holds for it, and "
    "its total popular vote where the dataset has it."
)
FILTER_SENTENCE = "Narrow the charts and table to a range of years."
#: The page's headings (#560, #582, #618; ba specs, approved at their plan gates,
#: 2026-11-18, 2026-11-21 and 2026-11-23): C7, C10, then their one table.
C7_HEADING = "Electors appointed over time"
C7_UNAVAILABLE = (
    "The chart of this state's electors appointed in each election can't be shown "
    "right now. Please try again in a minute."
)
C10_HEADING = "Total popular vote over time"
C10_UNAVAILABLE = (
    "The chart of this state's total popular vote in each election can't be shown "
    "right now. Please try again in a minute."
)
#: The table C7 and C10 share (#618, D117; ba spec, approved at its plan gate,
#: 2026-11-23), its note when neither chart can be built, and the note first among its
#: notes when one chart's column reads :data:`explore.labels.UNAVAILABLE_CELL`.
ELECTORS_TOTALS_TABLE_HEADING = (
    "This state's electors appointed and total popular vote in each election"
)
ELECTORS_TOTALS_TABLE_UNAVAILABLE = (
    "The table of this state's electors appointed and total popular vote in each "
    "election can't be shown right now. Please try again in a minute."
)
ELECTORS_UNAVAILABLE_NOTE = (
    "One column can't be shown right now: electors appointed. In the download, its "
    "cells are empty because they could not be read right now, not because the "
    "dataset holds no value there. Please try again in a minute."
)
TOTALS_UNAVAILABLE_NOTE = (
    "One column can't be shown right now: the total popular vote. In the download, "
    "its cells are empty because they could not be read right now, not because the "
    "dataset holds no value there. Please try again in a minute."
)


VALIDATE: api.Validate = (api.ROSTER_PATH, state_view.on_roster)


def title(usps: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a code the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the code only when it is a USPS code."""
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return f"{usps} — state history — {SITE_TITLE}"
    return f"State history — {SITE_TITLE}"


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's one filter from a parsed query string, as sorted ``(key, value)``
    pairs: the year range, as :func:`explore.query.parse_year_range` keeps it (#620,
    D119). Syntactic and total, and it reads no API: Dash's index runs it to build
    ``og:url``. Every other key is dropped, the two moved to the results page included
    (D118), and so is ``usps``, the path variable. Whether a year is in the state's span
    is :func:`render`'s question."""
    if not isinstance(params, dict):
        return []
    return sorted(query.parse_year_range(params).items())


dash.register_page(
    __name__,
    path_template=state_view.template(state_view.HISTORY),
    title=title,
    # No names: the index HTML never waits on the API, so this cannot read the state.
    description=(
        "One US state's electors appointed in every presidential election in this "
        "dataset, and its total popular vote where the dataset has it."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, "/v1/states/{usps}"),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=parse_filters,
    # T4's two keys moved with it to the results page, so an old link naming either
    # answers 302 there (D092, D118); the parser drops both (app.page_move checks it).
    moved=(state_view.MOVED_KEYS, state_view.template(state_view.RESULTS)),
    # The site navigation link this page marks (#448):
    # a state's history marks its index, States.
    nav="states",
)


def popular_totals(
    rows: list[dict[str, Any]], served: set[int], usps: str, source: str
) -> list[dict[str, Any]]:
    """C10's rows (#582, D113): the state's total popular vote and popular-vote status,
    one per election from its first, collapsed from ``rows`` as
    :func:`explore.state_view.electors` collapses C7's, and as checked.

    ``state_popular_total`` is a joined field, null on any candidate row with no
    popular-vote record in the state (``EcPvRow``'s own description, "None if no PV"),
    so a row whose ``popular_votes`` and ``state_popular_total`` are both null is
    skipped (D113(b), narrowing D077 and D098 for this field alone). Every other row
    must carry a total, and those must be one value: a candidate figure beside a null
    total contradicts the field's meaning and refuses, alone in its year or not (D113,
    amendment). A year where every row is skipped reads a null total, which its cell
    then names the cause of. ``pv_status`` keeps C7's rule
    (:func:`explore.state_view.per_year`).

    Pure; raises ``KeyError`` for a row without a field and ``TypeError`` for a row
    with a figure and no total, a year's two totals or two statuses, or a gap after the
    state's first election (:func:`explore.over_time.state_series`), so C10 draws one
    value per election or nothing.
    """
    field = "state_popular_total"
    by_year = state_view.per_year(rows, usps, source, field)
    seen: set[int] = set()
    for row in rows:
        year, value, votes = row["year"], row[field], row["popular_votes"]
        if value is None and votes is None:
            continue
        if value is None:
            raise TypeError(f"{source} has a popular-vote figure with no {field}")
        if year in seen and not over_time.same(by_year[year][field], value):
            raise TypeError(f"{source} has two values of {field} in {year}")
        by_year[year][field] = value
        seen.add(year)
    return over_time.state_series(by_year, served, source, usps)


class Range(NamedTuple):
    """The year range a render applies (#620, D119), within the state's span: ``span``
    runs from the state's first election (or, where C7's collapse cannot be read, its
    first served row) to the latest served year, and ``start_known`` says whether its
    start is the first election :func:`explore.state_view.first_election` found."""

    year_from: int
    year_to: int
    span: tuple[int, int]
    start_known: bool

    @property
    def narrowed(self) -> bool:
        """Whether the range is narrower than the state's span."""
        return (self.year_from, self.year_to) != self.span


def state_range(
    pairs: list[tuple[str, str]],
    electors_records: list[dict[str, Any]] | None,
    rows: list[dict[str, Any]],
    year_max: int,
) -> Range:
    """The range to apply (#620, D119): ``pairs`` judged against the state's own span,
    per bound, as the shared year range is, so a bound outside it falls back to that
    end (a range wholly before the state's first election opens its whole history).
    The span's start reads data only, never whether a chart could be drawn: C7's
    collapse's first election, else the state's first served row, where both
    collapses start."""
    first = (
        None
        if electors_records is None
        else state_view.first_election(electors_records)
    )
    start = first if first is not None else min(r["year"] for r in rows)
    span = (start, year_max)
    year_from, year_to = query.year_range(pairs, *span)
    return Range(year_from, year_to, span, first is not None)


def narrow(records: list[dict[str, Any]], chosen: Range) -> list[dict[str, Any]]:
    """The records in the range: one predicate for both charts' collapses, so the two
    halves keep the same years and :func:`merge`'s join holds. Pure."""
    return [r for r in records if chosen.year_from <= r["year"] <= chosen.year_to]


def _took_office_flags(
    rows: list[dict[str, Any]], years: list[int]
) -> list[tuple[int, object]] | None:
    """One ``(year, flag)`` pair per year in ``years`` (the years the state appointed
    electors), for :func:`explore.metrics.flag_count` (#601, D112(e), D115): the year's
    one row with ``took_office`` true picks the candidate who took office, and that
    row's cast ``electoral_votes`` decides, above 0 true and 0 false (a split
    delegation counts). A null or a blank vote is passed as is, so it is left out of N.

    ``None`` (the figure reads unrecognized) for a year with no such row or two, a
    row of the year with ``took_office`` null, missing or not a bool, or a took-office
    row whose votes are no ``int`` at or above 0. Total: it reads ``rows`` with
    ``.get`` and raises nothing, so no fault here reaches C7's section or the page."""
    by_year: dict[int, list[dict[str, Any]]] = {year: [] for year in years}
    for row in rows:
        year = row.get("year")
        if year in by_year:
            by_year[year].append(row)
    pairs: list[tuple[int, object]] = []
    for year in years:
        picked = []
        for row in by_year[year]:
            took = row.get("took_office")
            if type(took) is not bool:
                return None
            if took:
                picked.append(row)
        if len(picked) != 1:
            return None
        votes = picked[0].get("electoral_votes")
        if labels.is_blank(votes):
            pairs.append((year, votes))
            continue
        if type(votes) is not int or votes < 0:
            return None
        pairs.append((year, votes > 0))
    return pairs


def _figures(
    records: list[dict[str, Any]], rows: list[dict[str, Any]], narrowed: bool
) -> html.Div:
    """The state's headline figures (#601, #621; D112(e), (g), D115, D120), as a
    ``dl``: the elections in which it appointed electors (an allotment above 0, from
    C7's collapse, ``records``), its first election, in how many of them it held a
    popular vote to choose its electors, the change in its electors from its first
    election to its latest (all four computed by
    :func:`explore.state_view.history_figures`, the computation the ``/states`` map
    is to share), and in how many its
    electors cast a vote for the candidate who took office (this page's alone: it needs
    the candidate rows). Unfiltered: ``records`` is C7's whole collapse, so the Years
    filter never reaches them (D112(g), D115(g), D119), and they sit above it (#634,
    D122); while it applies a narrower range (``narrowed``) a note says so.

    An allotment no figure can read makes every figure unrecognized (D120); a
    ``pv_status`` fault, the popular-vote count alone; a took-office fault, the
    took-office count alone (:func:`_took_office_flags`). Either way C7 and the page
    stay. A note names the years with no electors appointed while the count shows a
    number."""
    figures = state_view.history_figures(records)
    years = list(figures.years)
    entries: list[Any] = []
    # By key, not by kind (D120, amended at #635's review): two figures here are flag
    # counts (popular vote, took office). ``TestFurtherStateFigures.
    # test_the_figures_show_in_the_approved_order`` renders every ``METRIC_IDS`` id, so
    # the ``TypeError`` below is reachable only by a code change a test catches.
    for key, ident in METRIC_IDS.items():
        # A plain count words its own case (D115(i)); every other figure's, keyed.
        no_figure = (
            labels.METRIC_NO_FIGURE[key]
            if years and key != "state_elections_count"
            else labels.METRIC_NO_FIGURE_NO_ELECTORS
        )
        value: str
        rest: str | None
        if figures.unrecognized:
            value, rest = labels.UNRECOGNIZED, None
        elif key == "state_elections_count":
            value, rest = labels.metric_elections(figures.elections, years, no_figure)
        elif key == "state_first_election":
            value, rest = labels.metric_first_election(figures.first, no_figure)
        elif key == "state_pv_elections_count":
            value, rest = labels.metric_count(figures.popular_vote, years, no_figure)
        elif key == "state_electors_change":
            value, rest = labels.metric_change(figures.change, no_figure)
        elif key == "state_took_office_count":
            counted = metrics.METRICS[key].counted
            if counted is None:  # a code fault in METRICS, never a data fault
                raise TypeError(f"{key} has no counted value")
            flags = _took_office_flags(rows, years)
            result = (
                metrics.UNRECOGNIZED_COUNT
                if flags is None
                else metrics.flag_count(flags, counted)
            )
            value, rest = labels.metric_count(result, years, no_figure)
        else:
            raise TypeError(f"{key} is no figure this page computes")
        entries += components.metric_entry(key, ident, value, rest)
    block: list[Any] = [html.Dl(entries, className="metrics")]
    if not figures.unrecognized and years and figures.zeros:
        block.append(
            html.P(
                labels.METRIC_ZERO_ALLOTMENT_NOTE.format(
                    years=labels.metric_years(figures.zeros)
                ),
                id=METRICS_NOTE_ID,
                className="note",
            )
        )
    if narrowed:
        block.append(
            html.P(
                labels.METRIC_ALL_YEARS_NOTE, id=METRICS_ALL_YEARS_ID, className="note"
            )
        )
    # The class the card's top-space rule names, where the figures open the card
    # (#634, D122(e)); layout rules name classes, never ids (D111).
    return html.Div(block, id=METRICS_ID, className="figures")


class Part(NamedTuple):
    """One chart's half of the shared section (#618, D117): the collapsed records, the
    points its hover and its table column are written from, its figure and caption,
    and, for C10, the popular-vote window it read (``None`` for C7)."""

    records: list[dict[str, Any]]
    points: list[over_time.Point]
    figure: dict[str, Any]
    caption: str
    window: tuple[int, int] | None


class Merged(NamedTuple):
    """A row of the table C7 and C10 share (#618, D117): the record its CSV writes and
    the three cells its row shows. A chart that could not be built leaves its field
    ``None`` and its cell :data:`explore.labels.UNAVAILABLE_CELL`."""

    record: dict[str, Any]
    electors_cell: str
    status_cell: str
    total_cell: str


def _electors_part(
    records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    usps: str,
    source: str,
    start: int | None,
) -> Part | None:
    """C7's half (#560, D106) over ``records``, its collapse already narrowed to the
    range (#620, D119): ``None`` when its points cannot be built or a served name has
    nothing in it (the rule D101 set for N2's rows, which D106 keeps for C7's). The
    axis is the years shown (D104). ``start`` is the first election its caption names,
    or ``None``. ``components.chart`` is never called here (D095(f))."""
    try:
        points = over_time.appointed_points(records)
        years = [p.year for p in points]
        name = rows[0]["state"]
        # A name a hover would write as "None", a number or nothing names no state.
        if not labels.has_text(name):
            raise TypeError(f"{source} names {usps} with no text")
        plain = over_time.plain(name)
        title = (
            labels.C7_TITLE_THIS_STATE
            if plain is None
            else labels.C4_TITLE_STATE.format(state=plain)
        )
        c7 = over_time.c4_figure(points, years, title, charts.escaped(str(name)))
        # Stacked above C10, the two plots line up on one year axis (#582, D113).
        over_time.align(c7.figure, over_time.STATE_MARGIN)
        caption = _electors_caption(c7, plain, start)
    except (KeyError, TypeError):
        return None
    return Part(records, points, c7.figure, caption, None)


def _totals_part(
    records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    usps: str,
    body: dict[str, Any],
    source: str,
    start: int | None,
) -> Part | None:
    """C10's half (#582, D113) over ``records``, its collapse already narrowed to the
    range (#620, D119): ``None`` when its points cannot be built, the popular-vote
    window is present and malformed, or a served name has nothing in it.
    ``components.chart`` is never called here (D095(f))."""
    try:
        coverage = body["meta"]["provenance"]["coverage"]
        # Checked as C2 and C5 check theirs: a malformed window fails C10's half alone.
        window = query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
        points = over_time.total_points(records, coverage)
        years = [p.year for p in points]
        name = rows[0]["state"]
        # A name a hover would write as "None", a number or nothing names no state.
        if not labels.has_text(name):
            raise TypeError(f"{source} names {usps} with no text")
        plain = over_time.plain(name)
        title = (
            labels.C10_TITLE_THIS_STATE
            if plain is None
            else labels.C10_TITLE_STATE.format(state=plain)
        )
        c10 = over_time.total_figure(
            points, years, title, window, charts.escaped(str(name)), C10_CHART
        )
        over_time.align(c10.figure, over_time.STATE_MARGIN)
        caption = _totals_caption(c10, window, plain, start)
    except (KeyError, TypeError):
        return None
    return Part(records, points, c10.figure, caption, window)


def merge(c7: Part | None, c10: Part | None) -> list[Merged]:
    """The shared table's rows (#618, D117): one per election, joined on the year from
    whichever half was built, each column's cell the one its chart's hover writes
    (D091). Pure; over two halves built from one response it reads only what they
    checked. Both halves list the same years (both end in
    :func:`explore.over_time.state_series` over the same rows), so a year mismatch
    between them is a code fault and raises ``ValueError``; with neither half there are
    no rows."""
    if c7 is not None and c10 is not None:
        for a, b in zip(c7.points, c10.points, strict=True):
            if a.year != b.year:
                raise ValueError(f"C7 and C10 disagree on a year: {a.year}, {b.year}")
    base = c7 if c7 is not None else c10
    if base is None:
        return []
    merged: list[Merged] = []
    for i, (record, point) in enumerate(zip(base.records, base.points, strict=True)):
        appointed = None if c7 is None else c7.records[i]
        total = None if c10 is None else c10.records[i]
        merged.append(
            Merged(
                record={
                    "year": record["year"],
                    "state_usps": record["state_usps"],
                    "state_electoral_votes": (
                        None
                        if appointed is None
                        else appointed["state_electoral_votes"]
                    ),
                    "pv_status": record["pv_status"],
                    "state_popular_total": (
                        None if total is None else total["state_popular_total"]
                    ),
                },
                electors_cell=(
                    labels.UNAVAILABLE_CELL
                    if c7 is None
                    else c7.points[i].appointed_cell
                ),
                status_cell=point.status_cell or labels.UNRECOGNIZED,
                total_cell=(
                    labels.UNAVAILABLE_CELL
                    if c10 is None
                    else c10.points[i].total_cell
                ),
            )
        )
    return merged


def _merged_row(row: Merged) -> html.Tr:
    """A row of the shared table: the year, linked to its election, and the cells C7's
    and C10's hovers write."""
    year = row.record["year"]
    return html.Tr(
        [
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            labels.cell(row.electors_cell),
            labels.cell(row.status_cell),
            labels.cell(row.total_cell),
        ]
    )


def _notes(c7: Part | None, c10: Part | None) -> tuple[str, ...]:
    """The shared table's notes (#618, D117): the note naming a column that could not
    be built first, then both columns' bases, which define headers that stay, then the
    popular-vote window only when C10's half read it."""
    first = (
        () if c7 is not None else (ELECTORS_UNAVAILABLE_NOTE,)
    ) + (() if c10 is not None else (TOTALS_UNAVAILABLE_NOTE,))
    # ``c10.window is None`` only narrows the type: C10's half always sets its window.
    window = (
        ()
        if c10 is None or c10.window is None
        else (
            labels.OVER_TIME_WINDOW_NOTE.format(
                pv_year_min=c10.window[0], pv_year_max=c10.window[1]
            ),
        )
    )
    return (*first, labels.C4_BASIS, labels.C5_BASIS, *window)


def _electors_caption(
    c7: over_time.OverTime, plain: str | None, first: int | None
) -> str:
    """C7's caption: what electors appointed is, what each marker means where one is
    drawn, and where the chart starts at the state's first election, that election
    (``first``, set only after the dataset's first year; #620, D119);
    ``components.chart`` adds the table pointer. Names the state only in plain text
    (``plain``, else "this state")."""
    parts = [labels.C4_BASIS]
    if c7.zeros:
        parts.append(labels.C4_ZERO_NOTE)
    if c7.missing:
        parts.append(labels.C4_NO_FIGURE_NOTE)
    parts += _start_note(plain, first)
    return " ".join(parts)


def _start_note(plain: str | None, first: int | None) -> list[str]:
    """The sentence naming the chart's start at the state's first election, which C7's
    and C10's captions share (#620, D119), or none."""
    if first is None:
        return []
    if plain is None:
        return [labels.FIRST_ELECTION_START_NOTE_THIS_STATE.format(year=first)]
    return [labels.FIRST_ELECTION_START_NOTE.format(state=plain, year=first)]


def _totals_caption(
    c10: over_time.OverTime,
    window: tuple[int, int],
    plain: str | None,
    first: int | None,
) -> str:
    """C10's caption (#582; ba spec): what the total counts, its short value ticks
    where a bar is drawn, what the bands and markers mean where drawn, and the state's
    first election where the chart starts there (:func:`_start_note`);
    ``components.chart`` adds the table pointer.
    Names the state only in plain text (``plain``, else "this state")."""
    parts = [labels.C5_BASIS]
    if c10.bars:
        parts.append(labels.C10_SHORT_TICKS_NOTE)
    if c10.before:
        parts.append(labels.C5_BEFORE_NOTE.format(pv_year_min=window[0]))
    if c10.after:
        parts.append(labels.C5_AFTER_NOTE.format(pv_year_max=window[1]))
    if c10.missing:
        parts.append(labels.C5_MARKER_NOTE)
    parts += _start_note(plain, first)
    return " ".join(parts)


def _controls(chosen: Range) -> html.Div:
    """The Years slider (#620, D119), over the state's span, so its value is the
    selection and the callback never writes back a bound the reader did not move. It
    keeps a row of its own, at the measure, from 76rem (#545)."""
    first, last = chosen.span
    return html.Div(
        [
            html.Div(
                [
                    html.Label(
                        labels.YEARS_FILTER, htmlFor=YEARS_ID, className="label"
                    ),
                    components.year_slider(
                        YEARS_ID, first, last, (chosen.year_from, chosen.year_to)
                    ),
                ],
                className="filter filter-own-row",
            ),
        ],
        # The filters box, whose margin gives the card its space under its top rule
        # where it opens the card (#567, D111), as on the state's per-capita page; the
        # figures open it wherever C7's collapse was read (#634, D122).
        className="filters filter-row",
    )


def _charts_section(
    rows: list[dict[str, Any]],
    usps: str,
    body: dict[str, Any],
    source: str,
    full: tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None],
    chosen: Range,
    year_min: int,
) -> tuple[list[Any], bool]:
    """C7 and C10's one section (#560, #582, #618, #620, #634; D106, D113, D117, D119,
    D122): the headline figures (#601, D115), the Years slider, C7's heading, C7,
    C10's heading, C10, then the table the two share and its column-name list, for the
    state's rows from the API path ``source``. The slider sits directly above what it
    narrows and below the figures, which it does not (D122).

    ``full`` is each chart's whole collapse (:func:`explore.state_view.collapsed`),
    ``None`` where it
    cannot be read. With neither, there is nothing to narrow: no slider, and the
    table's heading shows :data:`ELECTORS_TOTALS_TABLE_UNAVAILABLE` in its place. Each
    chart draws its collapse narrowed to ``chosen`` (:func:`narrow`), in a ``try`` of
    its own; one that cannot be built shows its sentence in its place (D096(d)'s rule)
    and its column of the table reads :data:`explore.labels.UNAVAILABLE_CELL`, with a
    note first among the table's, while the other chart, its column and the page stay.
    What shows outside each chart's place follows the collapses, never whether a chart
    was drawn (a drawing reads the narrowed records, so it could depend on the range;
    D119(c), (d)): the slider, and the figures, which read C7's whole collapse and open
    the card wherever it was read, whether or not C7 was drawn. Where the range holds
    no election, :data:`explore.labels.STATE_NO_ELECTIONS_IN_RANGE` stands in place of
    both charts and the table, directly under the slider with no section heading
    (D122). ``components.chart`` and the table are built
    after both ``try`` blocks (D095(f)). Returns the content and whether the slider
    rendered, the one source :func:`render` passes on for the filter sentence."""
    electors_full, totals_full = full
    if electors_full is None and totals_full is None:
        return [
            html.H2(C7_HEADING),
            html.P(C7_UNAVAILABLE, id=C7_UNAVAILABLE_ID, className="note"),
            html.H2(C10_HEADING),
            html.P(C10_UNAVAILABLE, id=C10_UNAVAILABLE_ID, className="note"),
            html.H2(ELECTORS_TOTALS_TABLE_HEADING),
            html.P(
                ELECTORS_TOTALS_TABLE_UNAVAILABLE,
                id=ELECTORS_TABLE_UNAVAILABLE_ID,
                className="note",
            ),
        ], False
    # The caption names the first election only where the chart starts there and it
    # is after the dataset's first year (ba spec for #620).
    start = (
        chosen.year_from
        if chosen.start_known
        and chosen.year_from == chosen.span[0]
        and chosen.year_from > year_min
        else None
    )
    shown = [
        None if records is None else narrow(records, chosen)
        for records in (electors_full, totals_full)
    ]
    # The figures first, then the filter above only what it narrows (#634, D122).
    content: list[Any] = (
        []
        if electors_full is None
        else [_figures(electors_full, rows, chosen.narrowed)]
    )
    content.append(_controls(chosen))
    if not any(shown):
        # In place of C7, C10 and the table, so no section heading before it (D122).
        content.append(
            html.P(
                labels.STATE_NO_ELECTIONS_IN_RANGE, id=NO_MATCH_ID, className="empty"
            )
        )
        return content, True
    content.append(html.H2(C7_HEADING))
    electors_shown, totals_shown = shown
    c7 = (
        None
        if electors_shown is None
        else _electors_part(electors_shown, rows, usps, source, start)
    )
    c10 = (
        None
        if totals_shown is None
        else _totals_part(totals_shown, rows, usps, body, source, start)
    )
    if c7 is None:
        content.append(html.P(C7_UNAVAILABLE, id=C7_UNAVAILABLE_ID, className="note"))
    else:
        content.append(
            components.chart(C7_ID, c7.figure, ELECTORS_TABLE_ID, c7.caption)
        )
    content.append(html.H2(C10_HEADING))
    if c10 is None:
        content.append(html.P(C10_UNAVAILABLE, id=C10_UNAVAILABLE_ID, className="note"))
    else:
        content.append(
            components.chart(C10_ID, c10.figure, ELECTORS_TABLE_ID, c10.caption)
        )
    content.append(html.H2(ELECTORS_TOTALS_TABLE_HEADING))
    if c7 is None and c10 is None:
        content.append(
            html.P(
                ELECTORS_TOTALS_TABLE_UNAVAILABLE,
                id=ELECTORS_TABLE_UNAVAILABLE_ID,
                className="note",
            )
        )
        return content, True
    merged = merge(c7, c10)
    by_row = {id(m.record): m for m in merged}
    content += [
        *components.table(
            [m.record for m in merged],
            lambda r: _merged_row(by_row[id(r)]),
            ELECTORS_FIELDS,
            ELECTORS_TABLE_ID,
            export.Download(
                filename=f"state-{usps}-electors-and-total-popular-vote.csv",
                name=(
                    "this state's electors appointed and total popular vote in each "
                    "election"
                ),
                provenance=body["meta"]["provenance"],
                # The range the render applied (#620, D119).
                view_url=export.view_url(
                    CANONICAL_HOST,
                    state_view.path(usps, state_view.HISTORY),
                    applied_search(chosen),
                ),
            ),
            extra=ELECTORS_EXTRA,
            notes=_notes(c7, c10),
        ),
        labels.glossary(ELECTORS_FIELDS, ident=ELECTORS_GLOSSARY_ID),
    ]
    return content, True


def applied_search(chosen: Range) -> str:
    """The range a render applied, as the query its section links and its download's
    view URL carry, in the normal form ``og:url`` and the callback write (``""`` or
    ``?…``): a bound at its end of the state's span is the default and is omitted."""
    return state_view.year_search(chosen.year_from, chosen.year_to, chosen.span)


def render(
    body: dict[str, Any],
    index: dict[str, Any],
    usps: str,
    pairs: list[tuple[str, str]] | None = None,
) -> tuple[html.Div, Any, bool]:
    """The page body, the state's name as served (the layout checks it has text) and
    whether the Years slider rendered (the layout adds the filter sentence only then),
    for one ``/v1/states/{usps}`` response, the ``/v1/elections`` index (read through
    the same view) and this page's filter pairs: the section links, carrying the year
    range applied (D105, D119), the page-local Location, then C7 and C10's section with
    the table they share (#582, #618, #620; D113, D117, D119), and the footer."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    year_min, year_max = query.year_span(coverage["year_min"], coverage["year_max"])
    # Read before either chart's half (D117 as amended, D118), so a missing popular-vote
    # bound is the page's in every view: the shared table's download preamble reads
    # both bounds outside both halves. A bound that is present and malformed is C10's
    # half's to refuse (as pages/elections.py reads its own, D116).
    coverage["pv_year_min"], coverage["pv_year_max"]
    source = f"/v1/states/{usps}"
    served = state_view.served_years(index)
    rows = state_view.rows(body, usps, served, source)
    # Each collapse once, over the whole history (#620, D119): the span, the figures
    # and each chart's half read the same result.
    # A served name with nothing in it names no state, and both charts would refuse it
    # whatever the range, so it counts as neither collapse read: no slider, as before
    # #620 (D119(d)).
    full: tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None] = (
        (
            state_view.collapsed(state_view.electors, rows, served, usps, source),
            state_view.collapsed(popular_totals, rows, served, usps, source),
        )
        if labels.has_text(rows[0]["state"])
        else (None, None)
    )
    chosen = state_range(pairs or [], full[0], rows, year_max)
    section, filtered = _charts_section(
        rows, usps, body, source, full, chosen, year_min
    )
    content = html.Div(
        [
            state_view.section_nav(usps, state_view.HISTORY, applied_search(chosen)),
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            # The page's one section (#567, D111; #618, D117): the figures, then the
            # Years slider (#620, D119; #634, D122) over C7 and C10 with their table.
            components.card(section),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )
    return content, rows[0]["state"], filtered


def search_for(years: Any, first: Any, last: Any) -> str:
    """The query string for the slider's value, in the normal form ``og:url`` uses
    (``""`` or ``?…``): a bound at its end of the slider's track, the state's span, is
    omitted."""
    params = query.year_range_search(years, first, last)
    return query.encode_search(parse_filters(params))


@callback(
    Output(URL_ID, "search"),
    Input(YEARS_ID, "value"),
    State(YEARS_ID, "min"),
    State(YEARS_ID, "max"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(years: Any, first: Any, last: Any, current: Any) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.
    Reads no API. An unchanged search is left alone (#620, D119)."""
    search = search_for(years, first, last)
    return no_update if search == (current or "") else search


def layout(usps: Any = None, **params: Any) -> html.Div:
    heading = "State history"
    # The filter sentence only above the slider: not on the not-found or degraded
    # state, nor where neither chart could be read (#620). The not-found state shows
    # no lede at all (#325).
    lede: str | None = LEDE
    try:
        with api.CLIENT.view() as view:
            # Validated from the roster before it is formatted (#279, D074).
            if not api.accepted(view.get, VALIDATE, {"usps": usps}):
                heading, lede = labels.STATE_NOT_FOUND_HEADING, None
                content = state_view.not_found(NOT_FOUND_ID)
            else:
                index = view.get(api.ELECTIONS_PATH)
                body = view.get(f"/v1/states/{usps}")
                content, state, filtered = render(
                    body, index, usps, parse_filters(params)
                )
                # A served name with nothing in it names no state (#532's rule), as on
                # the per-capita page: the heading stays "State history".
                if labels.has_text(state):
                    heading = state
                if filtered:
                    lede = f"{LEDE} {FILTER_SENTENCE}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
