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
"""

from __future__ import annotations

from collections.abc import Iterable

from dash import html

#: Plain label for each public field name (approved by the owner, 2026-10-01).
LABELS: dict[str, str] = {
    "year": "Election year",
    "candidate_count": "Candidates",
    "has_popular_vote": "Popular vote in this dataset",
}

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
