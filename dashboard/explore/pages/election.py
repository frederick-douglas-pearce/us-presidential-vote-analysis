"""One election in full (#307): the election panel (#308), the winner under each
method, T3, national results, with chart C1 (#433), T2, results by state, and T6, every
state's persons per electoral vote (#280).

The panel, T2 and T3 come from one response, ``/v1/elections/{year}`` (its
``election`` block, ``data`` and ``summary``), and T6 from a second,
``/v1/elections/{year}/per-capita``; both are filled on a miss, in the same render, so
the page's success marker renders only when the panel (or, where the API serves
``election: null``, the panel's unavailable sentence) and all three tables did. The year
is the path (``/election/<year>``, an item singular as the index is plural); it is
validated from the ``/v1/elections`` the page prefetches before it is formatted into an
API path (#312), so a year the dataset does not serve is not found, at the index (404)
and in the page.

It follows the elections index's conventions (``pages/elections.py``): labels from
:mod:`explore.labels`, filters only in the query string through the page's one parser,
a filter change written to a page-local ``dcc.Location`` and re-rendered from the
cache, the provenance footer from the response's own ``meta.provenance``, and every
table through :func:`explore.components.table`, which offers its rows as a CSV (#309)
built from the same list as its body. T2's
filters are the API's own query names, ``state`` (a USPS code) and ``candidate`` (a
slug), and the field names ``pv_status`` and ``electoral_count_status``. T3 is never
filtered: it is the year's national result, as the API's ``summary`` is. T6 is narrowed
by the same ``state`` filter, as T2 resolves it, and by nothing else. The panel is
never filtered either.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import dash
from dash import Input, Output, State, callback, dcc, html, no_update

from explore import api, charts, components, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whatever the filters leave in T2.
PAGE_ID = "election"
#: The wrapper of the not-found state: a year the dataset does not serve.
NOT_FOUND_ID = "election-not-found"
STATES_TABLE_ID = "election-states"
NATION_TABLE_ID = "election-nation"
NO_PV_ID = "election-no-pv"
PER_CAPITA_TABLE_ID = "election-per-capita"
PANEL_ID = "election-panel"
#: The panel's place when the API serves ``election: null`` (a build gap).
PANEL_UNAVAILABLE_ID = "election-panel-unavailable"
URL_ID = "election-url"
STATE_ID = "election-state"
CANDIDATE_ID = "election-candidate"
PV_STATUS_ID = "election-pv-status"
COUNT_STATUS_ID = "election-count-status"

#: T2's columns, in display order, by public field name.
STATE_FIELDS = (
    "state",
    "candidate",
    "nominating_party",
    "state_electoral_votes",
    "electoral_votes",
    "electoral_votes_counted",
    "electoral_count_status",
    "pv_status",
    "popular_votes",
)
#: The fields T2's glossary names: its columns, the reason its count cell shows, and the
#: party note its Party notes list shows (#389).
STATE_GLOSSARY = (
    *STATE_FIELDS,
    "electoral_count_status_reason",
    "nominating_party_note",
)
#: What T2's CSV adds after its columns (#309): the reason its count cell shows, the
#: party note and the party's per-row source (#389), and the keys its filters and its
#: year are named by.
STATE_EXTRA = (
    "electoral_count_status_reason",
    "nominating_party_note",
    "nominating_party_source",
    "state_usps",
    "candidate_slug",
    "year",
)

#: T3's columns, in display order, by public field name.
NATION_FIELDS = (
    "candidate",
    "nominating_party",
    "national_electoral_votes",
    "national_electoral_votes_counted",
    "national_electoral_denominator",
    "electoral_rank",
    "took_office",
    "national_pv_votes",
    "ec_share_full",
    "pv_share",
    "hybrid_score",
)
#: The fields T3's column-name list names: its columns and the party note (#389).
NATION_GLOSSARY = (*NATION_FIELDS, "nominating_party_note")
#: What T3's CSV adds after its columns (#309): the party note and the party's per-row
#: source (#389), then the candidate's key and the year.
NATION_EXTRA = (
    "nominating_party_note",
    "nominating_party_source",
    "candidate_slug",
    "year",
)

#: The election panel's fields, in display order, by public field name (#308): who led
#: under each method, whether the popular-vote or the hybrid winner differs from the
#: Electoral College result, the three margins, whether anyone won a majority of
#: electors, and the share of electors appointed by states that held a popular vote.
PANEL_FIELDS = (
    "ec_winner",
    "pv_winner",
    "hybrid_winner",
    "pv_flip",
    "hybrid_flip",
    "ec_margin",
    "pv_margin",
    "hybrid_margin",
    "ec_determinative",
    "pv_coverage",
)

#: The panel's sentence when the API serves no ``election`` block for the year.
PANEL_UNAVAILABLE = "The comparison across methods is not available for this year."

#: T6's columns, in display order, by public field name (#280).
PER_CAPITA_FIELDS = ("state", *labels.PER_CAPITA_FIELDS)
#: What T6's CSV adds after its columns (#309): the state's key and the year.
PER_CAPITA_EXTRA = ("state_usps", "year")

#: Which of the page's filters T6 follows: the state, and not the others.
PER_CAPITA_FILTER_NOTE = (
    "Only the state filter applies to this table; the candidate and status filters do "
    "not."
)

#: The query keys this page reads: the API's own filter names for a state and a
#: candidate, and the field names of the two closed vocabularies.
STATE = "state"
CANDIDATE = "candidate"
PV_STATUS = "pv_status"
COUNT_STATUS = "electoral_count_status"

#: Chart C1 (#433): each candidate's electoral share beside their popular-vote share,
#: with the majority line, beside T3.
C1_ID = "C1"

#: The year's popular-vote sentence above C1 and T3, when the dataset holds none for it.
NO_PV_SENTENCE = (
    "This dataset has no popular-vote figures for {year}; its popular-vote figures "
    "cover {first}–{last}."
)

#: The not-found state's heading and sentence (#325). The heading also leads the
#: page's title on a not-found link (``api.NotFound.title``, D083). "Not found" is about
#: the link: a real election outside the dataset (1820) is not found too. The raw path
#: value is never echoed.
NOT_FOUND_HEADING = "Election not found"
NOT_FOUND_SENTENCE = "This dataset has no presidential election for that year."
NOT_FOUND = api.NotFound(NOT_FOUND_HEADING, NOT_FOUND_SENTENCE)

#: The lede, then, on a successful render only, the sentence naming the filters it
#: offers (#324, as the candidate history does since #331): the not-found and degraded
#: states have no filters.
LEDE = (
    "Who led under the Electoral College, the popular vote and the hybrid; the "
    "national result; every state's electoral votes for each candidate, with the "
    "popular vote where this dataset has it; and how many people each state's "
    "electoral votes stood for."
)
FILTER_SENTENCE = "Narrow the state results by state, candidate or status."

#: The links to the nearest earlier and later year the index serves (#324), and the
#: accessible name of the landmark holding them. "Earlier" and "later" are about the
#: years this dataset serves, never a claim that no election fell between.
NAV_ID = "election-nav"
EARLIER_ID = "election-earlier"
LATER_ID = "election-later"
EARLIER_LINK = "Earlier: the {year} election"
LATER_LINK = "Later: the {year} election"
ELECTION_NAV_LABEL = "Earlier and later elections in this dataset"


def parse_filters(params: Any) -> list[tuple[str, str]]:
    """This page's filters from a parsed query string, as sorted ``(key, value)`` pairs.

    Syntactic and total, and it reads no API: Dash's index runs it to build ``og:url``.
    Keeps ``state`` only as a USPS code, ``candidate`` only as a slug, and the two
    statuses only as one of their closed values; a key repeated with differing values
    is dropped, and so is a key it does not know. Never emits ``year``, the path
    variable. Whether a state or candidate is in this year's results is the layout's
    question (:func:`filters`).
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


def _year_rows(body: Any) -> list[Any]:
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else []


def _row_year(row: Any) -> int | None:
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
    return any(_row_year(row) == int(year) for row in _year_rows(body))


VALIDATE: api.Validate = (api.ELECTIONS_PATH, served_year)


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
    years = {y for y in map(_row_year, _year_rows(body)) if y is not None}
    return Neighbours(
        earlier=max((y for y in years if y < year), default=None),
        later=min((y for y in years if y > year), default=None),
    )


def title(year: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a year the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the year only when the year is four ASCII digits."""
    if isinstance(year, str) and query.YEAR_RE.fullmatch(year):
        return f"The {year} election — {SITE_TITLE}"
    return f"Election — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template="/election/<year>",
    title=title,
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description="One US presidential election: results by state and nationally.",
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=("/v1/elections/{year}", "/v1/elections/{year}/per-capita"),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    query=parse_filters,
    # The site navigation link this page marks (#448):
    # a one-election view marks its index, Elections.
    nav="elections",
)


class Filters(NamedTuple):
    """The filters a render applies; ``None`` is "all".

    A ``NamedTuple``, not a dataclass: Dash executes a page module before it is in
    ``sys.modules``, which ``dataclass`` needs.
    """

    state: str | None
    candidate: str | None
    pv_status: str | None
    count_status: str | None


def filters(pairs: list[tuple[str, str]], rows: list[dict[str, Any]]) -> Filters:
    """The filters to apply to this year's rows.

    Per parameter, as ``og:url`` is: a state or candidate this year's results do not
    name falls back to "all" (``og:url`` keeps it, as the index keeps an out-of-span
    year). A status is a closed value, so it is kept even when no row has it: an empty
    result is the honest answer.
    """
    given = dict(pairs)
    state = given.get(STATE)
    candidate = given.get(CANDIDATE)
    return Filters(
        state=state if any(r["state_usps"] == state for r in rows) else None,
        candidate=(
            candidate if any(r["candidate_slug"] == candidate for r in rows) else None
        ),
        pv_status=given.get(PV_STATUS),
        count_status=given.get(COUNT_STATUS),
    )


def select(rows: list[dict[str, Any]], chosen: Filters) -> list[dict[str, Any]]:
    """The rows T2 shows: pure, and separate from building the table."""
    return [
        r
        for r in rows
        if chosen.state in (None, r["state_usps"])
        and chosen.candidate in (None, r["candidate_slug"])
        and chosen.pv_status in (None, r["pv_status"])
        and chosen.count_status in (None, r["electoral_count_status"])
    ]


def search_for(state: Any, candidate: Any, pv_status: Any, count_status: Any) -> str:
    """The query string for the controls' values, in the normal form ``og:url`` uses
    (``""`` or ``?…``). A cleared control is "all" and is omitted."""
    params = {
        key: value
        for key, value in (
            (STATE, state),
            (CANDIDATE, candidate),
            (PV_STATUS, pv_status),
            (COUNT_STATUS, count_status),
        )
        if isinstance(value, str) and value
    }
    return query.encode_search(parse_filters(params))


def applied_search(chosen: Filters) -> str:
    """The filters a render applied, in the normal form :func:`search_for` writes:
    already checked, so they are encoded without the parser."""
    keys = (STATE, CANDIDATE, PV_STATUS, COUNT_STATUS)
    return query.encode_search(
        (key, value) for key, value in zip(keys, chosen, strict=True) if value
    )


@callback(
    Output(URL_ID, "search"),
    Input(STATE_ID, "value"),
    Input(CANDIDATE_ID, "value"),
    Input(PV_STATUS_ID, "value"),
    Input(COUNT_STATUS_ID, "value"),
    State(URL_ID, "search"),
    prevent_initial_call=True,
)
def on_filter_change(
    state: Any, candidate: Any, pv_status: Any, count_status: Any, current: Any
) -> Any:
    """A filter change becomes a URL change; the router re-renders from the cache.

    Reads no API. An unchanged search is left alone.
    """
    search = search_for(state, candidate, pv_status, count_status)
    return no_update if search == (current or "") else search


def _options(pairs: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"label": label, "value": value}
        for value, label in sorted(pairs.items(), key=lambda kv: kv[1])
    ]


def _controls(rows: list[dict[str, Any]], chosen: Filters) -> html.Div:
    states = {r["state_usps"]: r["state"] for r in rows}
    candidates = {r["candidate_slug"]: r["candidate"] for r in rows}
    dropdowns = (
        (STATE_ID, labels.LABELS[STATE], _options(states), chosen.state, "All states"),
        (
            CANDIDATE_ID,
            labels.LABELS[CANDIDATE],
            _options(candidates),
            chosen.candidate,
            "All candidates",
        ),
        (
            PV_STATUS_ID,
            labels.LABELS["pv_status"],
            [{"label": v, "value": k} for k, v in labels.PV_STATUS.items()],
            chosen.pv_status,
            "Any",
        ),
        (
            COUNT_STATUS_ID,
            labels.LABELS["electoral_count_status"],
            [{"label": v[0], "value": k} for k, v in labels.COUNT_STATUS.items()],
            chosen.count_status,
            "Any",
        ),
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Label(label, htmlFor=control_id, className="label"),
                    dcc.Dropdown(
                        id=control_id,
                        options=options,
                        value=value,
                        placeholder=placeholder,
                        clearable=True,
                    ),
                ],
                className="filter",
            )
            for control_id, label, options, value, placeholder in dropdowns
        ],
        className="filters",
    )


def _state_row(row: dict[str, Any], year: int, coverage: dict[str, Any]) -> html.Tr:
    return html.Tr(
        [
            components.state_cell(row),
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


def _national_pv(value: Any, has_popular_vote: bool, as_share: bool) -> str:
    """A T3 cell that needs the popular vote: :data:`labels.NOT_APPLICABLE` in a year
    with no popular vote (T3's year rule, from the index row), the panel's wording for
    the same cause (#352), and inside it a null (or a blank, #355) is a candidate with
    no popular-vote figure."""
    if not has_popular_vote:
        return labels.NOT_APPLICABLE
    if labels.is_blank(value):
        return labels.NO_NATIONAL_FIGURE
    return labels.share(value) if as_share else labels.number(value)


#: The T3 fields :func:`_nation_cells` words, in T3's order: every column but the
#: candidate and the party, which are cells of their own (a link, a note).
NATION_WORDED = NATION_FIELDS[2:]


def _nation_cells(row: dict[str, Any], has_popular_vote: bool) -> dict[str, str]:
    """T3's cell text for each of :data:`NATION_WORDED`: the one source of the strings
    T3 shows and C1 draws (#433), so the chart writes each number as the table does."""
    return {
        "national_electoral_votes": labels.number(row["national_electoral_votes"]),
        "national_electoral_votes_counted": labels.number(
            row["national_electoral_votes_counted"]
        ),
        "national_electoral_denominator": labels.number(
            row["national_electoral_denominator"]
        ),
        "electoral_rank": labels.number(row["electoral_rank"]),
        "took_office": labels.yes_no(row["took_office"]),
        "national_pv_votes": _national_pv(
            row["national_pv_votes"], has_popular_vote, False
        ),
        # Nullable in the API's schema, though real for every served year.
        "ec_share_full": labels.share_cell(row["ec_share_full"]),
        "pv_share": _national_pv(row["pv_share"], has_popular_vote, True),
        # On T3's year rule, so the row agrees with itself.
        "hybrid_score": _national_pv(row["hybrid_score"], has_popular_vote, True),
    }


def _nation_row(row: dict[str, Any], cells: dict[str, str]) -> html.Tr:
    """A T3 row from its :func:`_nation_cells`, computed once per render and shared
    with C1."""
    return html.Tr(
        [
            components.candidate_cell(row),
            labels.nominating_party_cell(row),
            *(labels.cell(cells[field]) for field in NATION_WORDED),
        ]
    )


def _escaped(text: str) -> str:
    """Served text as plotly's pseudo-HTML shows it as written (#433): a name holding
    ``<`` or ``&`` is drawn, never read as markup, and ``(`` is written as an entity, so
    no served string can spell a ``var(--token)`` reference, which the figure rules
    refuse outside a color (``charts.color_problems``) and the chart callback would
    resolve. plotly draws each entity as its character."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("(", "&#40;")
    )


def _plotted(value: Any, cell: str) -> float | None:
    """The value C1 draws for a share, or ``None`` for a marker: only a number
    :func:`explore.labels.finite` accepts whose T3 cell is a share (#433). The chart
    computes no share; it draws the served value and labels it with T3's cell."""
    number = labels.finite(value)
    is_share = cell != labels.UNRECOGNIZED and cell == labels.share(value)
    return number if number is not None and is_share else None


#: Where a marker sits in a row (#433): the center of the slot of the bar it stands
#: for, from the template's ``bargap`` (one source), as plotly places two grouped bars
#: at a quarter of the row's bar band either side of its center. With one series the
#: bar is centered. The e2e test ``test_c1_on_2016_is_readable_at_390_px`` observes it
#: against a drawn bar.
_SLOT = (1 - charts.TEMPLATE["layout"]["bargap"]) / 4

#: Pixels per row and the margins around the plot (#433): two bars and their labels
#: per row at 390 px; the top margin holds the legend and the majority line's label.
_ROW_PX = 56
_TOP_PX = {True: 96, False: 56}
_BOTTOM_PX = 48


def _marker(field: str, cell: str) -> tuple[str, str]:
    """A marker's label and its hover cell, for a value T3 does not show as a share
    (#433): a missing popular-vote figure, a null or blank electoral share (named by its
    series, as T3's header names that cell), or an unrecognized value with its note."""
    if cell == labels.NO_NATIONAL_FIGURE:
        return labels.C1_NO_FIGURE, cell
    if field == "ec_share_full" and cell == labels.NOT_IN_DATASET:
        return labels.C1_NO_SHARE, f"{labels.LABELS[field]}: {cell}"
    if cell == labels.UNRECOGNIZED:
        return cell, f"{cell}<br>{labels.UNRECOGNIZED_NOTE}"
    return cell, cell


def _c1_figure(
    summary: list[dict[str, Any]],
    cells: list[dict[str, str]],
    has_popular_vote: bool,
    year: int,
) -> tuple[dict[str, Any], bool]:
    """C1's figure (#433), from T3's rows in T3's order, and whether it draws a
    :data:`labels.C1_NO_FIGURE` marker.

    One row per T3 row, at its position (0…n−1, reversed so T3's first is on top),
    labeled with the candidate's name as T3 shows it. Each bar is the served share,
    labeled with T3's cell for it; a share T3 does not show as one gets a labeled marker
    in its bar's slot, never a zero-length bar, and a real zero is a drawn, labeled bar.
    The popular-vote series is drawn only in a year T3 treats as having popular votes.
    ``cells`` are each row's :func:`_nation_cells`, the strings T3 shows. Total over
    every body T3 renders: it reads the served shares only through
    :func:`explore.labels.finite` and :func:`explore.labels.share` (:func:`_plotted`),
    and each name and slug as ``str``, escaped (:func:`_escaped`).
    """
    n = len(summary)
    positions = list(range(n))
    names = [_escaped(str(row["candidate"])) for row in summary]
    slugs = [_escaped(str(row["candidate_slug"])) for row in summary]
    offsets = (
        {"ec_share_full": -_SLOT, "pv_share": _SLOT}
        if has_popular_vote
        else {"ec_share_full": 0.0}
    )
    marks: list[tuple[float, str, str, str]] = []  # (y, label, hover, id)
    no_figure = False
    bars = []
    for field, color, hover in (
        ("ec_share_full", "var(--chart-1)", labels.C1_EC_HOVER),
        ("pv_share", "var(--chart-2)", labels.C1_PV_HOVER),
    ):
        if field not in offsets:
            continue
        xs: list[float | None] = []
        texts: list[str] = []
        hovers: list[str] = []
        for i, (row, cell) in enumerate(zip(summary, cells, strict=True)):
            shown = cell[field]
            x = _plotted(row[field], shown)
            xs.append(x)
            texts.append(shown if x is not None else "")
            hovers.append(
                hover.format(
                    candidate=names[i],
                    share=shown,
                    counted=cell["national_electoral_votes_counted"],
                    appointed=cell["national_electoral_denominator"],
                    votes=cell["national_pv_votes"],
                )
            )
            if x is None:
                label, hover_cell = _marker(field, shown)
                no_figure = no_figure or label == labels.C1_NO_FIGURE
                marks.append(
                    (
                        i + offsets[field],
                        label,
                        labels.C1_NO_FIGURE_HOVER.format(
                            candidate=names[i], cell=hover_cell
                        ),
                        f"{slugs[i]}/{field}",
                    )
                )
        marker: dict[str, Any] = {"color": color}
        if field == "pv_share":
            marker["pattern"] = {
                "shape": "/",
                "fillmode": "overlay",
                "fgcolor": "var(--page)",
            }
        bars.append(
            {
                "type": "bar",
                "orientation": "h",
                "name": labels.LABELS[field],
                "offsetgroup": field,
                "ids": slugs,
                "x": xs,
                "y": positions,
                "text": texts,
                "textposition": "outside",
                "textfont": {"color": "var(--text)"},
                "cliponaxis": False,
                "marker": marker,
                "hovertext": hovers,
                "hovertemplate": "%{hovertext}<extra></extra>",
                "showlegend": has_popular_vote,
            }
        )
    data: list[dict[str, Any]] = list(bars)
    if marks:
        data.append(
            {
                "type": "scatter",
                "mode": "markers+text",
                "name": labels.C1_NO_FIGURE_SERIES,
                "showlegend": False,
                "ids": [mark[3] for mark in marks],
                "x": [0] * len(marks),
                "y": [mark[0] for mark in marks],
                "text": [mark[1] for mark in marks],
                "textposition": "middle right",
                "textfont": {"color": "var(--text)"},
                "cliponaxis": False,
                "marker": {"symbol": "x", "size": 10, "color": "var(--text)"},
                "hovertext": [mark[2] for mark in marks],
                "hovertemplate": "%{hovertext}<extra></extra>",
            }
        )
    title = labels.C1_TITLE if has_popular_vote else labels.C1_TITLE_NO_PV
    top = _TOP_PX[has_popular_vote]
    layout: dict[str, Any] = {
        "title": {"text": title.format(year=year)},
        "height": _ROW_PX * max(n, 1) + top + _BOTTOM_PX,
        "margin": {"t": top, "b": _BOTTOM_PX, "r": 56},
        "xaxis": {
            "range": [0, 1],
            "tickformat": ".0%",
            "dtick": 0.25,
            "title": {"text": labels.C1_X_AXIS},
        },
        "yaxis": {
            "tickvals": positions,
            "ticktext": names,
            "autorange": "reversed",
            "showgrid": False,
            "zeroline": False,
        },
        "shapes": [
            {
                "type": "line",
                "xref": "x",
                "x0": 0.5,
                "x1": 0.5,
                "yref": "paper",
                "y0": 0,
                "y1": 1,
                "layer": "below",
                "line": {"dash": "dash", "width": 2, "color": "var(--chart-reference)"},
            }
        ],
        "annotations": [
            {
                "text": labels.C1_MAJORITY_LINE,
                "xref": "x",
                "x": 0.5,
                "yref": "paper",
                "y": 1,
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"color": "var(--text)", "size": 12},
            }
        ],
    }
    if has_popular_vote:
        layout["legend"] = {
            "orientation": "h",
            "yref": "container",
            "y": 1,
            "yanchor": "top",
            "x": 0,
            "xanchor": "left",
        }
    return {"data": data, "layout": layout}, no_figure


def _pv_window(coverage: dict[str, Any]) -> dict[str, Any]:
    """The popular-vote window as :data:`NO_PV_SENTENCE` and
    :data:`labels.C1_NO_PV_CAPTION` both write it: from ``coverage``, never a
    literal."""
    return {"first": coverage["pv_year_min"], "last": coverage["pv_year_max"]}


def _c1_caption(
    has_popular_vote: bool, no_figure: bool, year: int, coverage: dict[str, Any]
) -> str:
    """C1's caption (#433): what each share counts and what the line marks; in a year
    with popular votes, which bar is which and, where a marker is drawn, what it means;
    otherwise why no popular-vote share is drawn. ``components.chart`` adds the table
    pointer."""
    if has_popular_vote:
        parts = [
            labels.C1_BASES,
            labels.C1_MAJORITY_NOTE,
            labels.C1_LINE_EC_ONLY,
            labels.C1_ROW_ORDER,
        ]
        if no_figure:
            parts.append(labels.C1_NO_FIGURE_NOTE.format(label=labels.C1_NO_FIGURE))
    else:
        parts = [
            labels.C1_EC_BASIS,
            labels.C1_MAJORITY_NOTE,
            labels.C1_NO_PV_CAPTION.format(year=year, **_pv_window(coverage)),
        ]
    return " ".join(parts)


def _download(
    year: int, table: str, name: str, body: dict[str, Any], chosen: Filters
) -> export.Download:
    """A table's download: the file named for the view and the table, the provenance of
    the response its rows come from, and the view's URL with the filters applied."""
    return export.Download(
        filename=f"election-{year}-{table}.csv",
        name=name,
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST, f"/election/{year}", applied_search(chosen)
        ),
    )


def _rows(value: Any, year: int, name: str, path: str | None = None) -> list[Any]:
    """A non-empty list of the year's rows from ``path`` (``/v1/elections/{year}`` by
    default), each naming that year, or ``TypeError``.

    A served year always has state rows, and the API treats a year with no national
    summary as a build regression, so an empty list is a malformed body: rendering it
    would show the success marker over an empty table. Each row's year is checked
    against the validated one, so no row of another year (or of no year) is shown,
    and the cells read the validated year rather than the row's.
    """
    path = path or f"/v1/elections/{year}"
    if not isinstance(value, list) or not value:
        raise TypeError(f"{path} carries no list of {name}")
    if any(_row_year(row) != year for row in value):
        raise TypeError(f"{path} carries {name} of another year")
    return value


def _election(value: Any, year: int) -> dict[str, Any] | None:
    """The year's ``election`` block, ``None`` where the API serves none, or
    ``TypeError``.

    The API serves ``election: null`` on a build gap while the rows beside it stay
    correct, so a null is the panel's own unavailable state, never the page's. Any
    other shape, or a block naming another year (checked as :func:`_rows` checks a
    row's), is a malformed body.
    """
    if value is None:
        return None
    if not isinstance(value, dict) or _row_year(value) != year:
        raise TypeError(f"/v1/elections/{year} carries no election block of that year")
    return value


def _panel_cells(block: dict[str, Any], year: int, coverage: Any) -> dict[str, str]:
    """Each panel field's cell. The Electoral College fields and ``pv_coverage`` exist
    for every year, so a null there names no cause; a null popular-vote or hybrid field
    outside the window (from ``coverage``) reads :data:`labels.NOT_APPLICABLE`, and a
    value is shown whatever the year."""
    applicable = labels.in_pv_window(year, coverage)
    determinative = block["ec_determinative"]
    return {
        "ec_winner": labels.winner(block["ec_winner"], True),
        "pv_winner": labels.winner(block["pv_winner"], applicable),
        "hybrid_winner": labels.winner(block["hybrid_winner"], applicable),
        "pv_flip": labels.flip(
            block["pv_flip"], "popular-vote", applicable, determinative=determinative
        ),
        "hybrid_flip": labels.flip(
            block["hybrid_flip"], "hybrid", applicable, determinative=determinative
        ),
        "ec_margin": labels.margin(block["ec_margin"], True),
        "pv_margin": labels.margin(block["pv_margin"], applicable),
        "hybrid_margin": labels.margin(block["hybrid_margin"], applicable),
        "ec_determinative": labels.ec_majority(determinative),
        "pv_coverage": labels.share_cell(block["pv_coverage"]),
    }


def _panel(block: dict[str, Any] | None, year: int, coverage: Any) -> list[Any]:
    """The election panel (#308): each field's label (its raw name as the tooltip, as
    a column header's is) beside its cell, the hybrid's and the margins' help text,
    and a glossary. ``ec_winner``'s label follows ``ec_determinative`` (#355), from one
    label map the list and the glossary share."""
    heading = html.H2("Under each method")
    if block is None:
        return [
            heading,
            html.P(PANEL_UNAVAILABLE, id=PANEL_UNAVAILABLE_ID, className="note"),
        ]
    cells = _panel_cells(block, year, coverage)
    shown = {field: labels.LABELS[field] for field in PANEL_FIELDS} | {
        "ec_winner": labels.ec_winner_label(block["ec_determinative"])
    }
    return [
        heading,
        html.Div(
            [
                html.Dl(
                    [
                        item
                        for field in PANEL_FIELDS
                        for item in (
                            html.Dt(shown[field], title=field),
                            labels.cell(cells[field], html.Dd),
                        )
                    ]
                ),
                html.P(labels.HYBRID_NOTE, className="note"),
                html.P(labels.MARGIN_NOTE, className="note"),
                labels.glossary(PANEL_FIELDS, "Field names", shown),
            ],
            id=PANEL_ID,
            className="panel",
        ),
    ]


def _per_capita_rows(value: Any, year: int) -> list[dict[str, Any]]:
    """T6's rows sorted by state name, or ``TypeError``.

    As :func:`_rows` reads the year's rows: a non-empty list, each naming the validated
    year, so an empty list or a row of another year is a malformed body. Each must name
    a USPS code too, which the state filter and the state link read. A null cell is not
    malformed: :func:`explore.labels.per_capita_cells` says why it is null.
    """
    path = f"/v1/elections/{year}/per-capita"
    rows = _rows(value, year, "rows", path)
    for row in rows:
        usps = row.get("state_usps")
        if not isinstance(usps, str) or not query.USPS_RE.fullmatch(usps):
            raise TypeError(f"{path} carries a bad state code")
    return sorted(rows, key=lambda r: str(r["state"]))


def _per_capita_section(
    rows: list[dict[str, Any]], chosen: Filters, download: export.Download
) -> list[Any]:
    """T6: every state's persons per electoral vote, narrowed by T2's resolved state."""
    shown = [r for r in rows if chosen.state in (None, r["state_usps"])]
    return [
        html.H2("People per electoral vote"),
        html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
        *components.table(
            shown,
            lambda r: html.Tr([components.state_cell(r), *labels.per_capita_cells(r)]),
            PER_CAPITA_FIELDS,
            PER_CAPITA_TABLE_ID,
            download,
            extra=PER_CAPITA_EXTRA,
            notes=(
                PER_CAPITA_FILTER_NOTE,
                labels.GOVERNING_CENSUS_NOTE,
                labels.BOUNDARY_NOTE,
            ),
        ),
        labels.glossary(PER_CAPITA_FIELDS),
    ]


def _nav(around: Neighbours) -> list[Any]:
    """The links to the earlier and later served years, unfiltered (owner, #324's plan
    gate); a side with no year has no link, and with neither there is no landmark."""
    links = [
        dcc.Link(text.format(year=year), href=f"/election/{year}", id=link_id)
        for year, text, link_id in (
            (around.earlier, EARLIER_LINK, EARLIER_ID),
            (around.later, LATER_LINK, LATER_ID),
        )
        if year is not None
    ]
    if not links:
        return []
    # Dash takes ``aria-*`` as keyword arguments its stubs do not name.
    aria: dict[str, Any] = {"aria-label": ELECTION_NAV_LABEL}
    return [html.Nav(links, id=NAV_ID, **aria)]


def render(
    body: dict[str, Any],
    index_row: dict[str, Any],
    pairs: list[tuple[str, str]],
    per_capita: dict[str, Any],
    around: Neighbours,
) -> html.Div:
    """The page body for one ``/v1/elections/{year}`` response, the year's row of
    ``/v1/elections`` and its ``/per-capita`` response (all read through the same
    view), this page's filter pairs and the year's served neighbours. The response's
    ``election`` key is required, though its value may be null (:func:`_election`)."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    # The popular-vote window, checked once before any cell reads it, whatever the
    # ``election`` block holds: two years, the first no later than the last (#308).
    query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
    year = _row_year(index_row)
    if year is None:
        raise TypeError("the index row names no year")
    rows = _rows(body["data"], year, "state rows")
    summary = _rows(body["summary"], year, "candidates")
    per_capita_rows = _per_capita_rows(per_capita["data"], year)
    block = _election(body["election"], year)
    has_popular_vote = index_row["has_popular_vote"] is True
    chosen = filters(pairs, rows)
    shown = select(rows, chosen)
    nation: list[Any] = [html.H2("National results")]
    if not has_popular_vote:
        nation.append(
            html.P(
                NO_PV_SENTENCE.format(year=year, **_pv_window(coverage)),
                id=NO_PV_ID,
                className="note",
            )
        )
    cells = [_nation_cells(row, has_popular_vote) for row in summary]
    by_row = {id(row): row_cells for row, row_cells in zip(summary, cells, strict=True)}
    figure, no_figure = _c1_figure(summary, cells, has_popular_vote, year)
    nation += [
        components.chart(
            C1_ID,
            figure,
            NATION_TABLE_ID,
            _c1_caption(has_popular_vote, no_figure, year, coverage),
        ),
        *components.table(
            summary,
            lambda r: _nation_row(r, by_row[id(r)]),
            NATION_FIELDS,
            NATION_TABLE_ID,
            _download(year, "national", "the national results", body, chosen),
            extra=NATION_EXTRA,
            notes=(
                labels.PARTY_NOTE,
                labels.PARTY_NULL_NOTE,
                labels.HYBRID_NOTE,
            ),
        ),
        *labels.party_notes(summary),
        labels.glossary(NATION_GLOSSARY),
    ]
    return html.Div(
        [
            dcc.Location(id=URL_ID, refresh="callback-nav"),
            *_nav(around),
            *_panel(block, year, coverage),
            # National results (H2, C1, T3) come before Results by state, so the chart
            # sits near the top on a phone (owner, #433's plan gate).
            *nation,
            html.H2("Results by state"),
            _controls(rows, chosen),
            html.P(f"Showing {len(shown)} of {len(rows)} rows", className="count"),
            *components.table(
                shown,
                lambda r: _state_row(r, year, coverage),
                STATE_FIELDS,
                STATES_TABLE_ID,
                _download(year, "by-state", "the results by state", body, chosen),
                extra=STATE_EXTRA,
                notes=(labels.PARTY_NOTE, labels.PARTY_NULL_NOTE),
            ),
            *labels.party_notes(shown),
            labels.glossary(STATE_GLOSSARY),
            *_per_capita_section(
                per_capita_rows,
                chosen,
                _download(
                    year,
                    "per-capita",
                    "people per electoral vote",
                    per_capita,
                    chosen,
                ),
            ),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def index_row(index: dict[str, Any], year: str) -> dict[str, Any]:
    """The year's row of ``/v1/elections``; ``KeyError`` if it has none."""
    for row in _year_rows(index):
        if _row_year(row) == int(year):
            return dict(row)
    raise KeyError(year)


def not_found() -> html.Div:
    """A year the dataset does not serve: said plainly, with the way back, under
    :data:`NOT_FOUND_HEADING` and no lede (#325)."""
    return html.Div(
        [
            html.P(NOT_FOUND_SENTENCE),
            dcc.Link("Browse every election in the dataset", href="/elections"),
        ],
        id=NOT_FOUND_ID,
    )


def layout(year: Any = None, **params: Any) -> html.Div:
    heading = "Election"
    lede: str | None = LEDE
    try:
        with api.CLIENT.view() as view:
            # Validated from the prefetched index before it is formatted (#312).
            if not api.accepted(view.get, VALIDATE, {"year": year}):
                heading, lede, content = NOT_FOUND_HEADING, None, not_found()
            else:
                body = view.get(f"/v1/elections/{year}")
                per_capita = view.get(f"/v1/elections/{year}/per-capita")
                index = view.get(api.ELECTIONS_PATH)
                content = render(
                    body,
                    index_row(index, year),
                    parse_filters(params),
                    per_capita,
                    neighbours(index, int(year)),
                )
                heading = f"The {year} election"
                lede = f"{LEDE} {FILTER_SENTENCE}"
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
