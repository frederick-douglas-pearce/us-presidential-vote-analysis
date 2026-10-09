"""The one label table: a plain-language header for each public API field (#306).

Every table labels its columns from :data:`LABELS`, keyed by the field name the public
``/v1`` API returns, never by a snapshot column name. Later tables add rows here rather
than labelling inline. The table is flat, so a key means one thing in every table that
shows it, and a field name the API uses with two meanings needs a qualified key for the
second. ``candidate_count`` already is one: here it is a ``/v1/elections`` row's count
of one year's candidates, while ``/v1/meta``'s counts the snapshot's distinct
candidates, so a table showing the latter needs its own key. ``coverage`` is another:
the plain key is a per-capita row's (#280), whether a census figure governs that
election, so a table showing the provenance block's year windows needs its own key.

The raw field name stays on hand because these tables double as the debugging view: as
each header's tooltip, and in a "Column names" glossary under the table, which works
where hovering does not. Like ``components``, this module reads no API.

The cells a null or a closed value can reach live here too (#307), so a later table
(S4's state and candidate histories) shows the same thing the one-election view does:
a null is never bare, and each closed value of ``pv_status`` and
``electoral_count_status`` has its plain label. The per-capita tables' cells and help
text (#280) follow the same rule: a null ratio or population is never bare: it says
why it is null where the row explains it, and names no cause where it does not. So do
the election panel's cells and the hybrid's help text (#308): a popular-vote or hybrid
field outside the popular-vote window is not applicable, never "No".
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from dash import html

#: Plain label for each public field name (approved by the owner, 2026-10-01; the
#: per-capita rows, 2026-10-08).
LABELS: dict[str, str] = {
    "year": "Election year",
    "candidate_count": "Candidates",
    "has_popular_vote": "Popular vote in this dataset",
    # The one-election view (#307). Series wording: appointed / cast / counted.
    "state": "State",
    "candidate": "Candidate",
    "party": "Party",
    "state_electoral_votes": "Electors appointed (state)",
    "electoral_votes": "Electoral votes cast",
    "electoral_votes_counted": "Electoral votes counted",
    "electoral_count_status": "Count status",
    "electoral_count_status_reason": "Count status: the Archives' reason",
    "pv_status": "Popular vote in this state",
    "popular_votes": "Popular votes",
    "national_electoral_votes": "Electoral votes cast (nation)",
    "national_electoral_votes_counted": "Electoral votes counted (nation)",
    "national_electoral_denominator": "Electors appointed (nation)",
    "electoral_rank": "Electoral rank (counted votes)",
    "took_office": "Took office",
    "national_pv_votes": "Popular votes (nation)",
    "ec_share_full": "Electoral share (counted ÷ appointed)",
    "pv_share": "Popular-vote share",
    # The per-capita tables (#280). ``state_electoral_votes`` above is the same
    # appointed allotment, so it keeps its label.
    "governing_census_year": "Census in force",
    "population": "Population (census in force)",
    "boundary_basis": "Borders counted",
    "coverage": "Census figure",
    "persons_per_electoral_vote": "People per electoral vote",
    # The election panel (#308), from a ``/v1/elections/{year}`` response's
    # ``election`` block. ``ec_winner`` is the largest counted share, not who took
    # office (1824: Jackson led and the House chose Adams), so it is not "Winner".
    "ec_winner": "Most electoral votes counted",
    "pv_winner": "Winner: popular vote",
    "hybrid_winner": "Winner: hybrid",
    "pv_flip": "Popular vote changes the winner",
    "hybrid_flip": "Hybrid changes the winner",
    "ec_margin": "Electoral margin (percentage points)",
    "pv_margin": "Popular-vote margin (percentage points)",
    "hybrid_margin": "Hybrid margin (percentage points)",
    "ec_determinative": "Electoral College majority",
    "pv_coverage": "Share of electors appointed by states that held a popular vote",
    # T3's hybrid columns (#308). ``pv_coverage`` above means the same on a summary row.
    "ec_share_hybrid": "Electoral share in the hybrid",
    "hybrid_score": "Hybrid score",
}

#: Each closed ``pv_status`` value, as a filter option reads it.
PV_STATUS: dict[str, str] = {
    "popular_vote": "Popular vote",
    "legislature_chosen": "State legislature chose",
    "not_participating": "Took no part",
}

#: Each closed ``electoral_count_status`` value: its label, and for a value other than
#: ``counted``, what it means.
COUNT_STATUS: dict[str, tuple[str, str | None]] = {
    "counted": ("Counted", None),
    "not_counted": ("Not counted", "Congress refused the votes"),
    "disputed": ("Disputed", "Congress never resolved the question"),
}

#: Each closed ``boundary_basis`` value of a per-capita row (#280).
BOUNDARY_BASIS: dict[str, str] = {
    "at_election": "Borders at the election",
    "present_day": "Present-day footprint",
}

#: The per-capita ``coverage`` value that explains a null population and ratio.
NO_GOVERNING_FIGURE = "no_governing_figure"

#: Each closed ``coverage`` value of a per-capita row (#280).
PER_CAPITA_COVERAGE: dict[str, str] = {
    "covered": "Available",
    NO_GOVERNING_FIGURE: "No census figure governs this election",
}

#: A null ratio's cell when the state's allotment is zero (its votes were withheld).
NO_ELECTORAL_VOTES = "No electoral votes this election"

#: Why each election reads the census it does: one line under each per-capita table.
GOVERNING_CENSUS_NOTE = (
    "Each election uses the census whose apportionment set its electoral votes, not "
    "the nearest one: 2020 uses the 2010 census, and 1924 and 1928 use 1910, because "
    "Congress made no apportionment from the 1920 census."
)

#: What each ``boundary_basis`` value describes. Neutral about the Census Bureau's
#: tabulation, which this dataset reports as published.
BOUNDARY_NOTE = (
    "At the election: the people inside the state's borders when the election was "
    "held. Present-day footprint: the Census Bureau's figure for the state as its "
    "table reports it, which this dataset does not claim matches the state's borders "
    "at that election."
)

#: The popular-vote cells for a null figure (the null table in #307).
LEGISLATURE_CHOSE = "No popular vote: the state legislature chose the electors"
TOOK_NO_PART = "Took no part in this election"
BEFORE_WINDOW = "Popular vote held; not in this dataset before {pv_year_min}"
AFTER_WINDOW = "Popular vote held; not in this dataset yet"
NO_FIGURE = "No popular-vote figure for this candidate in this state"
NO_NATIONAL_FIGURE = "No popular-vote figure for this candidate"

#: Why ``party`` is often null: help text beside a null party cell.
PARTY_NOTE = (
    "Party comes from the popular-vote source, so it is recorded only where a "
    "popular-vote figure is."
)

#: What ``has_popular_vote: false`` means: this dataset holds no popular vote for that
#: year, not that none was held. Never "No".
NOT_IN_DATASET = "Not in this dataset"


#: A popular-vote or hybrid figure for a year outside the popular-vote window (#308).
NOT_APPLICABLE = "Not applicable: no popular vote in this dataset for this year"

#: A flip that happened; ``method`` is ``popular-vote`` or ``hybrid``.
FLIP_YES = "Yes: the {method} winner differs from the Electoral College winner"

#: Each ``ec_determinative`` value: a real outcome either way, never a missing value.
EC_MAJORITY = "A candidate won a majority of electors appointed"
NO_EC_MAJORITY = "No candidate reached a majority of electors appointed"

#: The hybrid's one line of help text: what it computes, and nothing about its merits.
HYBRID_NOTE = (
    "The hybrid score is the average of a candidate's electoral share and popular-vote "
    "share; the candidate with the highest score wins it."
)


def header(field: str) -> html.Th:
    """A column header: the plain label, with the raw field name as its tooltip."""
    return html.Th(LABELS[field], title=field, scope="col")


def glossary(fields: Iterable[str], summary: str = "Column names") -> html.Details:
    """Each column's plain label beside the API field name it shows. A list that is no
    table (the election panel) names its ``summary`` otherwise."""
    return html.Details(
        [
            html.Summary(summary),
            html.Dl(
                [
                    item
                    for field in fields
                    for item in (html.Dt(LABELS[field]), html.Dd(html.Code(field)))
                ]
            ),
        ],
        className="glossary",
    )


def has_popular_vote(value: object) -> str:
    """The cell for ``has_popular_vote``.

    ``True`` reads "Yes" and ``False`` :data:`NOT_IN_DATASET`; anything else renders as
    text rather than as a claim about the dataset.
    """
    if value is True:
        return "Yes"
    if value is False:
        return NOT_IN_DATASET
    return str(value)


def number(value: object) -> str:
    """An integer with thousands separators; anything else as text."""
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def share(value: object) -> str:
    """A share as a percentage to one decimal place; anything else as text.

    Total: a number no float can hold (``json`` parses integers of any size) renders
    as text too, rather than raising ``OverflowError`` past the page's degraded state.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            percent = float(value) * 100
        except OverflowError:
            return str(value)
        if math.isfinite(percent):
            return f"{percent:.1f}%"
    return str(value)


def yes_no(value: object) -> str:
    """A known boolean fact (``took_office``): "Yes" or "No"; anything else as text."""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return str(value)


def party(value: object) -> str:
    """A party, or :data:`NOT_IN_DATASET` for a null one (see :data:`PARTY_NOTE`)."""
    return NOT_IN_DATASET if value is None else str(value)


def party_cell(value: object) -> html.Td:
    """A party cell: :func:`party`, and for a null one :data:`PARTY_NOTE` as its help
    text."""
    if value is None:
        return html.Td(party(value), title=PARTY_NOTE)
    return html.Td(party(value))


def popular_votes(
    value: object, pv_status: object, year: int, coverage: dict[str, Any]
) -> str:
    """A state's popular-vote cell: the figure, or why there is none.

    A null is never bare: a legislature's choice and a state taking no part say so
    whatever the year; a held popular vote with no figure says whether the year lies
    before the dataset's popular-vote window, after it (a snapshot whose Electoral
    College data runs ahead of its popular vote), or inside it. An unknown status
    renders as text rather than as a claim. The window comes from ``coverage``, never
    a literal.
    """
    if value is not None:
        return number(value)
    if pv_status == "legislature_chosen":
        return LEGISLATURE_CHOSE
    if pv_status == "not_participating":
        return TOOK_NO_PART
    if pv_status != "popular_vote":
        return str(pv_status)
    if year < coverage["pv_year_min"]:
        return BEFORE_WINDOW.format(pv_year_min=coverage["pv_year_min"])
    if year > coverage["pv_year_max"]:
        return AFTER_WINDOW
    return NO_FIGURE


def pv_status(value: object) -> str:
    """A ``pv_status`` value's label; an unknown value as text."""
    return PV_STATUS.get(value, str(value)) if isinstance(value, str) else str(value)


def count_status(status: object, reason: object) -> list[Any]:
    """A count-status cell: the label, and for a vote not counted, its meaning and the
    Archives' reason sentence verbatim. An unknown value renders as text."""
    if not isinstance(status, str) or status not in COUNT_STATUS:
        return [str(status)]
    label, meaning = COUNT_STATUS[status]
    if meaning is None:
        return [label]
    cell: list[Any] = [html.Strong(label), f" ({meaning})"]
    if reason is not None:
        cell += [html.Br(), html.Span(str(reason), className="reason")]
    return cell


def _closed_value(value: object, table: dict[str, str]) -> str:
    """A closed value's label. An unknown non-blank string renders as text rather than
    as a claim; anything else (a null, a blank, a non-string) is no value the row
    explains, so it names none: :data:`NOT_IN_DATASET`, never a bare cell."""
    if isinstance(value, str) and value.strip():
        return table.get(value, value)
    return NOT_IN_DATASET


def boundary_basis(value: object) -> str:
    """A ``boundary_basis`` value's label (#280); see :func:`_closed_value`."""
    return _closed_value(value, BOUNDARY_BASIS)


def per_capita_coverage(value: object) -> str:
    """A per-capita ``coverage`` value's label (#280); see :func:`_closed_value`."""
    return _closed_value(value, PER_CAPITA_COVERAGE)


def _null_per_capita(coverage: object) -> str:
    """Why a per-capita figure is null, as far as ``coverage`` says.

    No governing census figure reads as such; an unknown non-blank value renders as
    text rather than as a claim; ``covered``, a blank or a non-string gives no cause,
    so the cell names none (:data:`NOT_IN_DATASET`).
    """
    if coverage == "covered":
        return NOT_IN_DATASET
    return per_capita_coverage(coverage)


def population(value: object, coverage: object) -> str:
    """A per-capita population cell: the figure, or why there is none (#280)."""
    return _null_per_capita(coverage) if value is None else number(value)


def persons_per_electoral_vote(
    value: object, coverage: object, allotment: object
) -> str:
    """A persons-per-electoral-vote cell: the figure to a whole person, or why there is
    none (#280). Never bare, and never an infinity: a null ratio over a zero allotment
    reads as such, and a non-finite figure names no cause.

    The single statement of which cause explains a null ratio. A missing census figure
    comes first, so a row carrying both causes reads as that; then a zero allotment (the
    state's votes were withheld). A null with neither cause names none. A non-finite
    number is no figure either, so it names none too. Total, as :func:`share` is: an
    integer no float can hold, or a value of no numeric type (a bool, a string), renders
    as text.
    """
    if value is None:
        if coverage == NO_GOVERNING_FIGURE:
            return PER_CAPITA_COVERAGE[NO_GOVERNING_FIGURE]
        if allotment == 0 and not isinstance(allotment, bool):
            return NO_ELECTORAL_VOTES
        return _null_per_capita(coverage)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number_ = float(value)
        except OverflowError:
            return str(value)
        if not math.isfinite(number_):
            return NOT_IN_DATASET
        return f"{round(number_):,}"
    return str(value)


#: The per-capita columns both tables share, in display order, after each table's own
#: first column (T6 the state, T7 the year).
PER_CAPITA_FIELDS = (
    "governing_census_year",
    "state_electoral_votes",
    "population",
    "boundary_basis",
    "coverage",
    "persons_per_electoral_vote",
)


def per_capita_cells(row: dict[str, Any]) -> list[html.Td]:
    """A per-capita row's cells for :data:`PER_CAPITA_FIELDS` (#280).

    The boundary-basis cell carries :data:`BOUNDARY_NOTE` as its help text, as a null
    party cell carries its note.
    """
    coverage = row["coverage"]
    allotment = row["state_electoral_votes"]
    return [
        # A year, so no thousands separator.
        html.Td(str(row["governing_census_year"])),
        html.Td(number(allotment)),
        html.Td(population(row["population"], coverage)),
        html.Td(boundary_basis(row["boundary_basis"]), title=BOUNDARY_NOTE),
        html.Td(per_capita_coverage(coverage)),
        html.Td(
            persons_per_electoral_vote(
                row["persons_per_electoral_vote"], coverage, allotment
            )
        ),
    ]


def in_pv_window(year: int, coverage: dict[str, Any]) -> bool:
    """Whether ``year`` lies inside the popular-vote window ``coverage`` names (#308).

    The window comes from ``coverage``, never a literal. A malformed ``coverage`` raises
    (``KeyError``, ``TypeError``), so the page degrades, as :func:`popular_votes` does:
    a guess either way would be a claim about the year.
    """
    return bool(coverage["pv_year_min"] <= year <= coverage["pv_year_max"])


def _null(applicable: bool) -> str:
    """A null panel figure: not applicable outside the window; inside it, no cause."""
    return NOT_IN_DATASET if applicable else NOT_APPLICABLE


def winner(value: object, applicable: bool) -> str:
    """A winner cell (#308): the name, or why there is none.

    ``applicable`` is whether the method has a winner this year: always for the
    Electoral College, inside the popular-vote window for the other two. A value is
    shown whatever the year, as :func:`popular_votes` shows one.
    """
    return _null(applicable) if value is None else str(value)


def flip(value: object, method: str, applicable: bool) -> str:
    """A flip cell (#308): only ``True`` and ``False`` read Yes and No; a null is never
    "No" (see :func:`winner`); anything else renders as text."""
    if value is True:
        return FLIP_YES.format(method=method)
    if value is False:
        return "No"
    return _null(applicable) if value is None else str(value)


def margin(value: object, applicable: bool) -> str:
    """A margin cell (#308), already in percentage points in the API, to one decimal.

    A null reads as :func:`winner`'s does. Total, as :func:`share` is: an integer no
    float can hold, or a value of no numeric type, renders as text, and a non-finite
    number is no figure, so it names no cause.
    """
    if value is None:
        return _null(applicable)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            points = float(value)
        except OverflowError:
            return str(value)
        if not math.isfinite(points):
            return NOT_IN_DATASET
        return f"{points:.1f} percentage points"
    return str(value)


def ec_majority(value: object) -> str:
    """An ``ec_determinative`` cell (#308): ``False`` is a real outcome, never a gap;
    a null names no cause; anything else renders as text."""
    if value is True:
        return EC_MAJORITY
    if value is False:
        return NO_EC_MAJORITY
    return NOT_IN_DATASET if value is None else str(value)


def share_cell(value: object) -> str:
    """A share the schema makes nullable though the API fills it for every year
    (``ec_share_full``, ``ec_share_hybrid``, ``pv_coverage``): a null names no cause."""
    return NOT_IN_DATASET if value is None else share(value)
