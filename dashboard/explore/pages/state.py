"""One state's history (#279): chart C7, its electors appointed in each election (#560),
chart C10, its total popular vote in each election (#582), and T4, its rows in every
election this dataset holds for it.

Its people per electoral vote (T7, #280) is a page of its own since #559,
``pages/state_per_capita.py``; what the two share is in :mod:`explore.state_view`, and
the section links join them (D105). T4, C7 and C10 come from one response,
``/v1/states/{usps}``, filled on a miss; C7 and C10 collapse its rows, one per
candidate, to one per election (D106, D113). The state is the path (``/state/<usps>``,
an item singular as ``/states`` is plural), in upper case as the API writes a USPS code.
It is validated against the state roster before it is formatted into an API path: the
latest election's rows (``/v1/elections/{year_max}``, :data:`explore.api.ROSTER_PATH`),
since every state and DC takes part in it (:func:`explore.state_view.on_roster`). That
source is declared in ``on_miss`` and built from the index's coverage, never from the
path, so a code the dataset does not serve never fills a path built from it: the most it
costs is a fill of the shared roster, once per render until one succeeds, and it 404s at
the index once the roster is cached (#279, D074).

It follows the one-election view's conventions (``pages/election.py``): labels and
null cells from :mod:`explore.labels`, filters only in the query string through the
page's one parser, a filter change written to a page-local ``dcc.Location`` and
re-rendered from the cache, the provenance footer from the response's own
``meta.provenance``, and T4 through :func:`explore.components.table`, which offers its
rows as a CSV (#309) built from the same list as its body. The filters are the shared
year range (``year_from`` / ``year_to``, judged against the dataset's span as on
``/elections``, so a range before the state's first election is an honest empty
result), ``candidate`` (a slug) and ``pv_status``; the section link to the per-capita
page carries the year range only. No query key reaches T7 alone, so an old link to
this page needs no redirect (D105). Each candidate links to their history
(``pages/candidate.py``, #331).
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

#: The wrapper every successful render carries, whatever the filters leave in T4.
PAGE_ID = "state"
#: The wrapper of the not-found state: a code the dataset does not serve, or a section
#: the site does not have (``/state/GA/x``).
NOT_FOUND_ID = "state-not-found"
TABLE_ID = "state-history"
URL_ID = "state-url"
YEARS_ID = "state-years"
CANDIDATE_ID = "state-candidate"
PV_STATUS_ID = "state-pv-status"

#: Chart C7 (#560, D106): the state's electors appointed in each election, before the
#: filters, with its own companion table, which no filter reaches (D093(a)).
C7_ID = "C7"
ELECTORS_TABLE_ID = "state-electors"
ELECTORS_GLOSSARY_ID = "state-electors-glossary"
#: The degraded section's sentence (D096(d)'s rule): C7's section alone, when the
#: rows T4 shows cannot be read as one allotment per election.
C7_UNAVAILABLE_ID = "state-electors-unavailable"
#: The headline figures (#601, D112(e), (g), D115): the block and each figure's value,
#: by metric key, in display order, the page's one per-key table (D114(d)); DOM ids are
#: stable and never renamed (D097(g)). In C7's card, after its heading.
METRICS_ID = "state-history-metrics"
METRIC_IDS = {
    "state_elections_count": "state-elections-count",
    "state_took_office_count": "state-took-office-count",
}
#: The note under the figures naming the years with no electors appointed.
METRICS_NOTE_ID = "state-history-metrics-note"
#: The companion table's columns, by public field name, and what its CSV adds.
ELECTORS_FIELDS = ("year", "state_electoral_votes", "pv_status")
ELECTORS_EXTRA = ("state_usps",)

#: Chart C10 (#582, D113): the state's total popular vote in each election, below C7,
#: before the filters, with its own companion table, which no filter reaches (D093(a)).
C10_ID = "C10"
TOTALS_TABLE_ID = "state-popular-total"
TOTALS_GLOSSARY_ID = "state-popular-total-glossary"
#: The degraded section's sentence (D096(d)'s rule): C10's section alone, when the
#: rows T4 shows cannot be read as one total per election.
C10_UNAVAILABLE_ID = "state-popular-total-unavailable"
TOTALS_FIELDS = ("year", "state_popular_total", "pv_status")
TOTALS_EXTRA = ("state_usps",)
#: What C10's figure is drawn with: C5's figure, one state's (#582, D113), on C7's
#: year-tick size, since the two stack on one page.
C10_CHART = over_time.TotalChart(
    name=labels.LABELS["state_popular_total"],
    marker_labels=labels.C10_MARKER_LABELS,
    symbols=over_time.C10_SYMBOLS,
    tick_px=components.YEAR_TICK_FONT_PX,
)

#: T4's columns, in display order, by public field name.
FIELDS = (
    "year",
    "candidate",
    "nominating_party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
    "popular_votes",
)
#: The fields T4's glossary names: its columns, the reason its count cell shows, and the
#: party note its Party notes list shows (#389).
GLOSSARY = (*FIELDS, "electoral_count_status_reason", "nominating_party_note")
#: What T4's CSV adds after its columns (#309): the reason its count cell shows, the
#: party note and the party's per-row source (#389), and the keys its candidate filter
#: and its state are named by.
EXTRA = (
    "electoral_count_status_reason",
    "nominating_party_note",
    "nominating_party_source",
    "candidate_slug",
    "state_usps",
)

#: The query keys this page reads besides the shared year range: the API's filter name
#: for a candidate, and the field name of the closed popular-vote vocabulary.
CANDIDATE = "candidate"
PV_STATUS = "pv_status"

#: The not-found state (#325), shared by the two state pages (#559).
NOT_FOUND = api.NotFound(
    labels.STATE_NOT_FOUND_HEADING, labels.STATE_NOT_FOUND_SENTENCE
)

#: The lede, then, on a successful render only, the sentence naming the filters it
#: offers (#392): the degraded state shows the lede alone, the not-found state none
#: (#325). People per electoral vote left it with T7 (#559; ba spec, approved at its
#: plan gate, 2026-11-18).
LEDE = (
    "This state's electors appointed, its total popular vote and its electoral votes "
    "for each candidate in every election this dataset holds for it, with popular-vote "
    "figures where the dataset has them."
)
FILTER_SENTENCE = (
    "Narrow the table of each candidate's electoral votes by year, candidate or "
    "popular-vote status."
)
#: The page's two sections' headings (#560; ba spec, approved at its plan gate,
#: 2026-11-18): C7 and its table, then T4, which its filters belong to.
C7_HEADING = "Electors appointed over time"
C7_TABLE_HEADING = "This state's electors appointed in each election"
HISTORY_TABLE_HEADING = "Each candidate's electoral votes in each election"
C7_UNAVAILABLE = (
    "The chart and table of this state's electors appointed in each election can't "
    "be shown right now. Please try again in a minute."
)
#: C10's section (#582; ba spec, approved at its plan gate, 2026-11-21), after C7's.
C10_HEADING = "Total popular vote over time"
C10_TABLE_HEADING = "This state's total popular vote in each election"
C10_UNAVAILABLE = (
    "The chart and table of this state's total popular vote in each election can't "
    "be shown right now. Please try again in a minute."
)


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``.
    Keeps the year range as :func:`explore.query.parse_year_range` does, ``candidate``
    only as a slug and ``pv_status`` only as one of its closed values; a key repeated
    with differing values is dropped, and so is a key it does not know. Never emits
    ``usps``, the path variable. Whether a year or candidate is in this state's rows is
    the layout's question (:func:`filters`).
    """
    if not isinstance(params, dict):
        return []
    kept = query.parse_year_range(params)
    candidate = query.single(params.get(CANDIDATE))
    if candidate is not None and query.is_slug(candidate):
        kept[CANDIDATE] = candidate
    pv_status = query.single(params.get(PV_STATUS))
    if pv_status in labels.PV_STATUS:
        kept[PV_STATUS] = pv_status
    return sorted(kept.items())


VALIDATE: api.Validate = (api.ROSTER_PATH, state_view.on_roster)


def title(usps: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a code the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the code only when it is a USPS code."""
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return f"{usps} — state history — {SITE_TITLE}"
    return f"State history — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template=state_view.template(state_view.HISTORY),
    title=title,
    # No names: the index HTML never waits on the API, so this cannot read the state.
    description=(
        "One US state's electoral votes in every presidential election in this dataset."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=(api.ROSTER_PATH, "/v1/states/{usps}"),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=parse_filters,
    # The site navigation link this page marks (#448):
    # a state's history marks its index, States.
    nav="states",
)


class Filters(NamedTuple):
    """The filters a render applies; ``None`` is "all".

    A ``NamedTuple``, not a dataclass: Dash executes a page module before it is in
    ``sys.modules``, which ``dataclass`` needs.
    """

    year_from: int
    year_to: int
    candidate: str | None
    pv_status: str | None


def filters(
    pairs: list[tuple[str, str]], rows: list[dict[str, Any]], span: tuple[int, int]
) -> Filters:
    """The filters to apply to this state's rows.

    Per parameter, as ``og:url`` is. A year bound is judged against the dataset's span,
    as on ``/elections``: one outside it falls back to that end of it, while one inside
    it is kept even where the state has no election, so a range before its first is an
    honest empty result rather than its whole history. A candidate absent from its rows
    falls back to "all". A status is a closed value, so it is kept even when no row has
    it.
    """
    year_from, year_to = query.year_range(pairs, *span)
    given = dict(pairs)
    candidate = given.get(CANDIDATE)
    return Filters(
        year_from=year_from,
        year_to=year_to,
        candidate=(
            candidate if any(r["candidate_slug"] == candidate for r in rows) else None
        ),
        pv_status=given.get(PV_STATUS),
    )


def select(rows: list[dict[str, Any]], chosen: Filters) -> list[dict[str, Any]]:
    """The rows T4 shows: pure, and separate from building the table."""
    return [
        r
        for r in rows
        if chosen.year_from <= r["year"] <= chosen.year_to
        and chosen.candidate in (None, r["candidate_slug"])
        and chosen.pv_status in (None, r["pv_status"])
    ]


def search_for(
    years: Any, candidate: Any, pv_status: Any, first: Any, last: Any
) -> str:
    """The query string for the controls' values, in the normal form ``og:url`` uses
    (``""`` or ``?…``). Defaults and a cleared control are omitted."""
    params = query.year_range_search(years, first, last)
    for key, value in ((CANDIDATE, candidate), (PV_STATUS, pv_status)):
        if isinstance(value, str) and value:
            params[key] = value
    return query.encode_search(parse_filters(params))


def applied_search(chosen: Filters, span: tuple[int, int]) -> str:
    """The filters a render applied, in the normal form :func:`search_for` writes:
    already checked, so they are encoded without the parser."""
    params = query.year_range_search([chosen.year_from, chosen.year_to], *span)
    for key, value in ((CANDIDATE, chosen.candidate), (PV_STATUS, chosen.pv_status)):
        if value:
            params[key] = value
    return query.encode_search(params.items())


@callback(
    Output(URL_ID, "search"),
    Input(YEARS_ID, "value"),
    Input(CANDIDATE_ID, "value"),
    Input(PV_STATUS_ID, "value"),
    State(YEARS_ID, "min"),
    State(YEARS_ID, "max"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(
    years: Any, candidate: Any, pv_status: Any, first: Any, last: Any, current: Any
) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. An unchanged search is left alone.
    """
    search = search_for(years, candidate, pv_status, first, last)
    return no_update if search == (current or "") else search


def _controls(
    rows: list[dict[str, Any]], chosen: Filters, span: tuple[int, int]
) -> html.Div:
    # The dataset's span, as on /elections: the slider's value is then the selection,
    # so the callback never writes back a bound the reader did not move.
    first, last = span
    candidates = {r["candidate_slug"]: str(r["candidate"]) for r in rows}
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Years", htmlFor=YEARS_ID, className="label"),
                    components.year_slider(
                        YEARS_ID, first, last, (chosen.year_from, chosen.year_to)
                    ),
                ],
                # The slider keeps a row of its own, at the measure, from 76rem (#545).
                className="filter filter-own-row",
            ),
            components.dropdown_filter(
                CANDIDATE_ID,
                labels.LABELS[CANDIDATE],
                components.label_sorted_options(candidates),
                chosen.candidate,
                "All candidates",
            ),
            components.dropdown_filter(
                PV_STATUS_ID,
                labels.LABELS["pv_status"],
                [{"label": v, "value": k} for k, v in labels.PV_STATUS.items()],
                chosen.pv_status,
                "Any",
            ),
        ],
        # A filter row from 76rem (#545, D102): the two dropdowns side by side under it.
        className="filters filter-row",
    )


def _row(row: dict[str, Any], coverage: dict[str, Any]) -> html.Tr:
    year = row["year"]
    return html.Tr(
        [
            # A year links to its one-election view (#307).
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            # A candidate links to their history (#331).
            components.candidate_cell(row),
            labels.nominating_party_cell(row),
            labels.cell(labels.number(row["state_electoral_votes"])),
            labels.cell(labels.number(row["electoral_votes"])),
            labels.cell(labels.number(row["electoral_votes_counted"])),
            labels.cell(
                labels.count_status(
                    row["electoral_count_status"], row["electoral_count_status_reason"]
                )
            ),
            labels.cell(labels.pv_status(row["pv_status"])),
            labels.cell(
                labels.popular_votes(
                    row["popular_votes"], row["pv_status"], year, coverage
                )
            ),
        ]
    )


def _per_year(
    rows: list[dict[str, Any]], usps: str, source: str, field: str
) -> dict[int, dict[str, Any]]:
    """One record per year of ``rows`` (``year``, ``state_usps``, ``pv_status`` and
    ``field``), the rule C7 and C10 share (D106, D113): every row of a year must carry
    one ``pv_status`` (a null beside a value is two values, D077, D098), so a
    disagreement there degrades both charts. Only ``field`` is left for the caller to
    fold in, as ``None`` here. Raises ``KeyError`` for a row without ``year`` or
    ``pv_status`` and ``TypeError`` for a year's two statuses."""
    by_year: dict[int, dict[str, Any]] = {}
    for row in rows:
        year = row["year"]
        record = {
            "year": year,
            "state_usps": usps,
            field: None,
            "pv_status": row["pv_status"],
        }
        kept = by_year.setdefault(year, record)
        if not over_time.same(kept["pv_status"], record["pv_status"]):
            raise TypeError(f"{source} has two values of pv_status in {year}")
    return by_year


def electors(
    rows: list[dict[str, Any]], served: set[int], usps: str, source: str
) -> list[dict[str, Any]]:
    """C7's rows (#560, D106): the state's appointed allotment and popular-vote status,
    one per election from its first, collapsed from ``rows`` (T4's, one per candidate,
    already checked by :func:`explore.state_view.rows`, so each row's year is a served
    year).

    Pure; raises ``KeyError`` for a row without a field and ``TypeError`` for a year's
    rows that disagree on either value (a null beside a figure is two values, D077,
    D098) or a gap after the state's first election
    (:func:`explore.over_time.state_series`, C7's rule, which C4's one-state series
    shared until #562, D107), so C7 draws one value per election or nothing.
    """
    field = "state_electoral_votes"
    by_year = _per_year(rows, usps, source, field)
    seen: set[int] = set()
    for row in rows:
        year, value = row["year"], row[field]
        if year in seen and not over_time.same(by_year[year][field], value):
            raise TypeError(f"{source} has two values of {field} in {year}")
        by_year[year][field] = value
        seen.add(year)
    return over_time.state_series(by_year, served, source, usps)


def popular_totals(
    rows: list[dict[str, Any]], served: set[int], usps: str, source: str
) -> list[dict[str, Any]]:
    """C10's rows (#582, D113): the state's total popular vote and popular-vote status,
    one per election from its first, collapsed from ``rows`` as :func:`electors`
    collapses C7's, and as checked.

    ``state_popular_total`` is a joined field, null on any candidate row with no
    popular-vote record in the state (``EcPvRow``'s own description, "None if no PV"),
    so a row whose ``popular_votes`` and ``state_popular_total`` are both null is
    skipped (D113(b), narrowing D077 and D098 for this field alone). Every other row
    must carry a total, and those must be one value: a candidate figure beside a null
    total contradicts the field's meaning and refuses, alone in its year or not (D113,
    amendment). A year where every row is skipped reads a null total, which its cell
    then names the cause of. ``pv_status`` keeps C7's rule (:func:`_per_year`).

    Pure; raises ``KeyError`` for a row without a field and ``TypeError`` for a row
    with a figure and no total, a year's two totals or two statuses, or a gap after the
    state's first election (:func:`explore.over_time.state_series`), so C10 draws one
    value per election or nothing.
    """
    field = "state_popular_total"
    by_year = _per_year(rows, usps, source, field)
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


def _allotment(value: object) -> int | None:
    """An allotment the figures can read: an ``int`` (never a ``bool``) at or above 0,
    else ``None`` (#601, D115). C7 draws a null or a malformed allotment as a marker;
    the figures cannot count such a year either way, so both read unrecognized."""
    return value if type(value) is int and value >= 0 else None


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


def _figures(records: list[dict[str, Any]], rows: list[dict[str, Any]]) -> html.Div:
    """The state's two headline figures (#601, D112(e), (g), D115), as a ``dl``: the
    elections in which it appointed electors (an allotment above 0, from C7's
    collapse, ``records``) and in how many of them its electors cast a vote for the
    candidate who took office. Unfiltered, so they reconcile to C7's table.

    An allotment no figure can read makes both unrecognized; a took-office fault, the
    second alone (:func:`_took_office_flags`). Either way C7, T4 and the page stay. A
    note names the years with no electors appointed while the count shows a number."""
    allotments = [(r["year"], _allotment(r["state_electoral_votes"])) for r in records]
    bad = any(value is None for _, value in allotments)
    years = sorted(year for year, value in allotments if value)
    zeros = sorted(year for year, value in allotments if value == 0)
    entries: list[Any] = []
    for key, ident in METRIC_IDS.items():
        metric = metrics.METRICS[key]
        rest: str | None
        if bad:
            value, rest = labels.UNRECOGNIZED, None
        elif metric.kind == "count":
            value, rest = labels.metric_elections(
                metrics.count(set(years)), years, labels.METRIC_NO_FIGURE_NO_ELECTORS
            )
        elif metric.kind == "flag_count" and metric.counted is not None:
            flags = _took_office_flags(rows, years)
            result = (
                metrics.UNRECOGNIZED_COUNT
                if flags is None
                else metrics.flag_count(flags, metric.counted)
            )
            no_figure = (
                labels.METRIC_NO_FIGURE[key]
                if years
                else labels.METRIC_NO_FIGURE_NO_ELECTORS
            )
            value, rest = labels.metric_count(result, years, no_figure)
        else:
            raise TypeError(f"{key} is no count or flag count")
        entries += components.metric_entry(key, ident, value, rest)
    block: list[Any] = [html.Dl(entries, className="metrics")]
    if not bad and years and zeros:
        block.append(
            html.P(
                labels.METRIC_ZERO_ALLOTMENT_NOTE.format(
                    years=labels.metric_years(zeros)
                ),
                id=METRICS_NOTE_ID,
                className="note",
            )
        )
    return html.Div(block, id=METRICS_ID)


def _electors_row(point: over_time.Point) -> html.Tr:
    """A row of C7's companion table: the year, linked to its election, and the cells
    C7's hover writes."""
    return html.Tr(
        [
            html.Td(dcc.Link(str(point.year), href=f"/election/{point.year}")),
            labels.cell(point.appointed_cell),
            labels.cell(point.status_cell or labels.UNRECOGNIZED),
        ]
    )


def _electors_caption(
    c7: over_time.OverTime, plain: str | None, first: int | None
) -> str:
    """C7's caption: what electors appointed is, what each marker means where one is
    drawn, the state's first election where it comes after the dataset's first, and
    that the page's filters do not reach it (D093(a)); ``components.chart`` adds the
    table pointer. Names the state only in plain text (``plain``, else "this
    state")."""
    parts = [labels.C4_BASIS]
    if c7.zeros:
        parts.append(labels.C4_ZERO_NOTE)
    if c7.missing:
        parts.append(labels.C4_NO_FIGURE_NOTE)
    if first is not None:
        parts.append(
            labels.FIRST_ELECTION_NOTE_THIS_STATE.format(year=first)
            if plain is None
            else labels.FIRST_ELECTION_NOTE.format(state=plain, year=first)
        )
    parts.append(labels.C7_FILTERS_NOTE)
    return " ".join(parts)


def _electors_section(
    rows: list[dict[str, Any]],
    served: set[int],
    usps: str,
    body: dict[str, Any],
    source: str,
) -> list[Any]:
    """C7's section (#560, D106): its heading, the chart, its heading-led companion
    table and that table's column-name list, for the rows T4 shows from the API path
    ``source``. Rows that cannot be read as one allotment per election, or a served
    name with nothing in it (the rule D101 set for N2's rows, which D106 keeps for
    C7's and D107 retired for N2), show the
    heading and :data:`C7_UNAVAILABLE` only, with no chart (D096(d)'s rule), while T4
    and the page stay. The ``try`` covers everything built from the rows, never
    ``components.chart`` (D095(f)), nor the headline figures (#601, D115), which sit
    after the heading and before the chart and are built from C7's collapse outside it,
    so a fault only they can see never removes C7."""
    heading = html.H2(C7_HEADING)
    try:
        records = electors(rows, served, usps, source)
        points = over_time.appointed_points(records)
        years = sorted(served)
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
        first = points[0].year if points[0].year > years[0] else None
        caption = _electors_caption(c7, plain, first)
        by_row = {id(r): p for r, p in zip(records, points, strict=True)}
        table = components.table(
            records,
            lambda r: _electors_row(by_row[id(r)]),
            ELECTORS_FIELDS,
            ELECTORS_TABLE_ID,
            export.Download(
                filename=f"state-{usps}-electors.csv",
                name="this state's electors appointed in each election",
                provenance=body["meta"]["provenance"],
                view_url=export.view_url(
                    CANONICAL_HOST, state_view.path(usps, state_view.HISTORY), ""
                ),
            ),
            extra=ELECTORS_EXTRA,
            notes=(labels.C4_BASIS,),
        )
    except (KeyError, TypeError):
        return [
            heading,
            html.P(C7_UNAVAILABLE, id=C7_UNAVAILABLE_ID, className="note"),
        ]
    return [
        heading,
        _figures(records, rows),
        components.chart(C7_ID, c7.figure, ELECTORS_TABLE_ID, caption),
        html.H2(C7_TABLE_HEADING),
        *table,
        labels.glossary(ELECTORS_FIELDS, ident=ELECTORS_GLOSSARY_ID),
    ]


def _totals_row(point: over_time.Point) -> html.Tr:
    """A row of C10's companion table: the year, linked to its election, and the cells
    C10's hover writes."""
    return html.Tr(
        [
            html.Td(dcc.Link(str(point.year), href=f"/election/{point.year}")),
            labels.cell(point.total_cell),
            labels.cell(point.status_cell or labels.UNRECOGNIZED),
        ]
    )


def _totals_caption(
    c10: over_time.OverTime,
    window: tuple[int, int],
    plain: str | None,
    first: int | None,
) -> str:
    """C10's caption (#582; ba spec): what the total counts, its short value ticks
    where a bar is drawn, what the bands and markers mean where drawn, the state's
    first election where it comes after the dataset's first, and that the page's
    filters do not reach it (D093(a)); ``components.chart`` adds the table pointer.
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
    if first is not None:
        parts.append(
            labels.C10_FIRST_ELECTION_NOTE_THIS_STATE.format(year=first)
            if plain is None
            else labels.C10_FIRST_ELECTION_NOTE.format(state=plain, year=first)
        )
    parts.append(labels.C7_FILTERS_NOTE)
    return " ".join(parts)


def _totals_section(
    rows: list[dict[str, Any]],
    served: set[int],
    usps: str,
    body: dict[str, Any],
    source: str,
) -> list[Any]:
    """C10's section (#582, D113): its heading, the chart, its heading-led companion
    table and that table's column-name list, for the rows T4 shows from the API path
    ``source``. Rows that cannot be read as one total per election, or a served name
    with nothing in it, show the heading and :data:`C10_UNAVAILABLE` only, with no
    chart (D096(d)'s rule), while T4 and the page stay. A fault in a total, or in the
    popular-vote window where T4 can still compare it, degrades C10 alone; one in what
    C7 reads too (the years, the state's name, ``pv_status``) degrades both; one T4
    cannot read (a window it cannot compare) degrades the page (D113(c), as amended).
    The ``try`` covers everything built from the rows, never ``components.chart``
    (D095(f))."""
    heading = html.H2(C10_HEADING)
    try:
        coverage = body["meta"]["provenance"]["coverage"]
        # Checked as C2 and C5 check theirs: a malformed window degrades C10 alone.
        window = query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
        records = popular_totals(rows, served, usps, source)
        points = over_time.total_points(records, coverage)
        years = sorted(served)
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
        first = points[0].year if points[0].year > years[0] else None
        caption = _totals_caption(c10, window, plain, first)
        by_row = {id(r): p for r, p in zip(records, points, strict=True)}
        table = components.table(
            records,
            lambda r: _totals_row(by_row[id(r)]),
            TOTALS_FIELDS,
            TOTALS_TABLE_ID,
            export.Download(
                filename=f"state-{usps}-total-popular-vote.csv",
                name="this state's total popular vote in each election",
                provenance=body["meta"]["provenance"],
                view_url=export.view_url(
                    CANONICAL_HOST, state_view.path(usps, state_view.HISTORY), ""
                ),
            ),
            extra=TOTALS_EXTRA,
            notes=(
                labels.C5_BASIS,
                labels.OVER_TIME_WINDOW_NOTE.format(
                    pv_year_min=window[0], pv_year_max=window[1]
                ),
            ),
        )
    except (KeyError, TypeError):
        return [
            heading,
            html.P(C10_UNAVAILABLE, id=C10_UNAVAILABLE_ID, className="note"),
        ]
    return [
        heading,
        components.chart(C10_ID, c10.figure, TOTALS_TABLE_ID, caption),
        html.H2(C10_TABLE_HEADING),
        *table,
        labels.glossary(TOTALS_FIELDS, ident=TOTALS_GLOSSARY_ID),
    ]


def _download(
    usps: str, body: dict[str, Any], chosen: Filters, span: tuple[int, int]
) -> export.Download:
    """T4's download: the file named for the view and the table, the provenance of the
    response its rows come from, and the view's URL with the filters applied."""
    return export.Download(
        filename=f"state-{usps}-history.csv",
        name="this state's history",
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST,
            state_view.path(usps, state_view.HISTORY),
            applied_search(chosen, span),
        ),
    )


def render(
    body: dict[str, Any],
    index: dict[str, Any],
    usps: str,
    pairs: list[tuple[str, str]],
) -> tuple[html.Div, Any]:
    """The page body and the state's name as served (the layout checks it has text),
    for one ``/v1/states/{usps}`` response and
    the ``/v1/elections`` index (read through the same view), and this page's filter
    pairs. The section links come first, carrying the year range applied (#559), then
    C7's section, C10's (#582, D113), then T4's, under its own heading, with the
    filters that narrow it (#560, D106)."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    span = query.year_span(coverage["year_min"], coverage["year_max"])
    source = f"/v1/states/{usps}"
    served = state_view.served_years(index)
    rows = state_view.rows(body, usps, served, source)
    chosen = filters(pairs, rows, span)
    shown = select(rows, chosen)
    content = html.Div(
        [
            state_view.section_nav(
                usps,
                state_view.HISTORY,
                state_view.year_search(chosen.year_from, chosen.year_to, span),
            ),
            # Three sections, three cards (#567, D111; #582): C7 with its table, C10
            # with its table, and T4 with the filters that narrow only it.
            components.card(_electors_section(rows, served, usps, body, source)),
            components.card(_totals_section(rows, served, usps, body, source)),
            components.card(
                [
                    html.H2(HISTORY_TABLE_HEADING),
                    dcc.Location(id=URL_ID, refresh="callback-nav"),
                    _controls(rows, chosen, span),
                    html.P(
                        f"Showing {len(shown)} of {len(rows)} rows", className="count"
                    ),
                    *components.table(
                        shown,
                        lambda r: _row(r, coverage),
                        FIELDS,
                        TABLE_ID,
                        _download(usps, body, chosen, span),
                        extra=EXTRA,
                        notes=(labels.PARTY_NOTE, labels.PARTY_NULL_NOTE),
                    ),
                    *labels.party_notes(shown),
                    labels.glossary(GLOSSARY),
                ]
            ),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )
    return content, rows[0]["state"]


def layout(usps: Any = None, **params: Any) -> html.Div:
    heading = "State history"
    # The filter sentence only above the filters: not on the not-found or degraded
    # state, which show none. The not-found state shows no lede at all (#325).
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
                content, state = render(body, index, usps, parse_filters(params))
                # A served name with nothing in it names no state (#532's rule), as on
                # the per-capita page: the heading stays "State history".
                if labels.has_text(state):
                    heading = state
                lede = f"{LEDE} {FILTER_SENTENCE}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
