"""The one label table: a plain-language header for each public API field (#306).

Every table labels its columns from :data:`LABELS`, keyed by the field name the public
``/v1`` API returns, never by a snapshot column name. Later tables add rows here rather
than labelling inline. The table is flat, so a key means one thing in every table that
shows it, and a field name the API uses with two meanings needs a qualified key for the
second. ``candidate_count`` already is one: here it is a ``/v1/elections`` row's count
of one year's candidates, while ``/v1/meta``'s counts the snapshot's distinct
candidates, so a table showing the latter needs its own key. ``coverage`` is next: a
per-capita row's and the provenance block's differ.

The raw field name stays on hand because these tables double as the debugging view: as
each header's tooltip, and in a "Column names" glossary under the table, which works
where hovering does not. Like ``components``, this module reads no API.

The cells a null or a closed value can reach live here too (#307), so a later table
(S4's state and candidate histories) shows the same thing the one-election view does:
a null is never bare, and each closed value of ``pv_status`` and
``electoral_count_status`` has its plain label.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dash import html

#: Plain label for each public field name (approved by the owner, 2026-10-01).
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


def header(field: str) -> html.Th:
    """A column header: the plain label, with the raw field name as its tooltip."""
    return html.Th(LABELS[field], title=field, scope="col")


def glossary(fields: Iterable[str]) -> html.Details:
    """Each column's plain label beside the API field name it shows."""
    return html.Details(
        [
            html.Summary("Column names"),
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
    """A share as a percentage to one decimal place; anything else as text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value * 100:.1f}%"
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
