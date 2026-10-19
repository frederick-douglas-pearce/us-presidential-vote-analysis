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
why it is null where the row explains it, and names no cause where it does not. The
election panel's cells (#308) follow it too: a null popular-vote or hybrid field outside
the popular-vote window reads :data:`NOT_APPLICABLE`, never "No"; a value is shown
whatever the year, as :func:`popular_votes` shows one. The wording follows the project
glossary (``docs/glossary.md``) and its wording rules (#352): no underscore or raw field
name in a label, cell or note, and "counted" only for vote counts. No cell this module
words shows a raw value either (#355): a null or blank names no cause
(:data:`NOT_IN_DATASET`), and a value it has no wording for reads :data:`UNRECOGNIZED`,
with :data:`UNRECOGNIZED_NOTE` as its help text (:func:`cell`). Candidate and state
names are shown as served: an open vocabulary the API types as text, not codes (#367).
The party is the nominating party (#389, D077): a closed vocabulary, each code read
from :data:`NOMINATING_PARTY`, never word-cased from the code.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from dash import html

#: Plain label for each public field name (approved by the owner, 2026-10-01; the
#: per-capita rows and the election panel's rows (#308), 2026-10-08; reworded to the
#: glossary's decisions, #352).
LABELS: dict[str, str] = {
    "year": "Election year",
    "candidate_count": "Candidates with electoral votes",
    "has_popular_vote": "Popular vote in this dataset",
    # The one-election view (#307). Series wording: appointed / cast / counted.
    "state": "State",
    "candidate": "Candidate",
    # The nominating party (#389, D077): the one party a table shows, in every year.
    "nominating_party": "Party",
    "nominating_party_note": "Party note",
    "state_electoral_votes": "Electors appointed (state)",
    "electoral_votes": "Electoral votes cast",
    "electoral_votes_counted": "Electoral votes counted",
    "electoral_count_status": "Count status",
    "electoral_count_status_reason": "Count status: the National Archives' reason",
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
    "governing_census_year": "Census used",
    "population": "Population (from that census)",
    "boundary_basis": "Borders used",
    "coverage": "Census figure",
    "persons_per_electoral_vote": "People per electoral vote",
    # The election panel (#308), from a ``/v1/elections/{year}`` response's
    # ``election`` block. ``ec_winner`` is the largest counted share, not who took
    # office (1824: Jackson led and the House chose Adams), so its label follows
    # ``ec_determinative`` (#355, :func:`ec_winner_label`); this one claims neither a
    # majority nor its absence, for wherever no ``ec_determinative`` is in hand.
    "ec_winner": "Electoral College leader",
    "pv_winner": "Popular-vote winner",
    "hybrid_winner": "Hybrid winner",
    "pv_flip": "Popular-vote winner differs from the Electoral College result",
    "hybrid_flip": "Hybrid winner differs from the Electoral College result",
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
    "popular_vote": "Popular vote held",
    "legislature_chosen": "State legislature chose the electors",
    "not_participating": "Took no part",
}

#: Each closed ``electoral_count_status`` value: its label, and for a value other than
#: ``counted``, what it means.
COUNT_STATUS: dict[str, tuple[str, str | None]] = {
    "counted": ("Counted", None),
    "not_counted": ("Not counted", "Congress decided not to count them"),
    "disputed": ("Disputed", "Congress never reached a decision"),
}

#: Each closed ``boundary_basis`` value of a per-capita row (#280).
BOUNDARY_BASIS: dict[str, str] = {
    "at_election": "Borders at the election",
    "present_day": "Present-day borders",
}

#: The per-capita ``coverage`` value that explains a null population and ratio.
NO_GOVERNING_FIGURE = "no_governing_figure"

#: Each closed ``coverage`` value of a per-capita row (#280).
PER_CAPITA_COVERAGE: dict[str, str] = {
    "covered": "Available",
    NO_GOVERNING_FIGURE: "No census figure for this state at this election",
}

#: A null ratio's cell when the state's allotment is zero (its votes were withheld).
NO_ELECTORAL_VOTES = "No electoral votes this election"

#: Why each election reads the census it does: one line under each per-capita table.
GOVERNING_CENSUS_NOTE = (
    "Each election uses the census that set the state's electoral votes, not the "
    "nearest one: 2020 uses the 2010 census, and 1924 and 1928 use 1910, because "
    "Congress did not redistribute House seats after the 1920 census."
)

#: What each ``boundary_basis`` value describes. Neutral about the Census Bureau's
#: tabulation, which this dataset reports as published.
BOUNDARY_NOTE = (
    "At the election: the people inside the state's borders when the election was "
    "held. Present-day borders: the Census Bureau's figure for the state as its "
    "table reports it, which this dataset does not claim matches the state's borders "
    "at that election."
)

#: The popular-vote cells for a null figure (the null table in #307).
LEGISLATURE_CHOSE = "No popular vote: the state legislature chose the electors"
TOOK_NO_PART = "Took no part in this election"
BEFORE_WINDOW = "Popular vote held; not in this dataset before {pv_year_min}"
AFTER_WINDOW = "Popular vote held; not in this dataset yet"
NO_FIGURE = "No popular-vote figure in this dataset for this candidate in this state"
NO_NATIONAL_FIGURE = "No popular-vote figure in this dataset for this candidate"

#: What the party column shows (#389): a table note under T2–T5 and in their
#: downloads. The second sentence keeps the rule-2 years true (D077).
PARTY_NOTE = (
    "The party column shows the party that nominated the candidate for President in "
    "that election. In 1824 and 1828, for a candidate no national convention or caucus "
    "nominated, and in 1836, for a Whig candidate, it shows the party this dataset's "
    "source names for them."
)

#: A null party's one cause (#389, D077): a null cell's help text and a table note.
#: Dataset-first, with no promise; it is not "without a nomination".
PARTY_NULL_NOTE = (
    'A party shown as "Not in this dataset" (an empty cell in the download) means this '
    "dataset records no party for that candidate in that election. It does not say "
    "whether a party nominated them."
)

#: The ``no_nomination`` cell (#389): distinct from the null, never "no party", and
#: never saying a withdrawn nominee was not nominated (D077).
NO_NOMINATION = "Without a party's nomination for President when the electors voted"

#: Help text on a ``no_nomination`` cell: it says what the ``nominating_party`` field
#: descriptions in ``src/usvote/api/models.py`` say, in the dashboard's wording (ba
#: spec, #389).
NO_NOMINATION_NOTE = (
    "Either no party nominated this candidate for President, or the nomination was "
    "withdrawn before the electors voted. It does not mean the candidate had no party."
)

#: The visible list of row notes under T2–T5 (#389): its heading, and one item per
#: candidate-year shown. Not written into a download, which carries the column.
PARTY_NOTES_HEADING = "Party notes"
PARTY_NOTE_ITEM = "{candidate}, {year}: {note}"

#: What ``has_popular_vote: false`` means: this dataset holds no popular vote for that
#: year, not that none was held. Never "No".
NOT_IN_DATASET = "Not in this dataset"

#: A value this module has no wording for (#355): an unknown closed-vocabulary code, a
#: value of the wrong type, a non-finite number, or one too large to show as a share,
#: margin or ratio. Never the raw value, and
#: never :data:`NOT_IN_DATASET`, which means the dataset holds nothing here. A download
#: writes the value as served.
UNRECOGNIZED = "Unrecognized value"

#: The help text every :data:`UNRECOGNIZED` cell carries (#355, drafted with the
#: glossary for the owner's review in place). One sentence, true on the panel too, which
#: has no download.
UNRECOGNIZED_NOTE = "This dataset holds a value that this page has no label for."


#: What ``has_popular_vote``'s ``false`` means (#309): shown under T1, whose cells read
#: :data:`NOT_IN_DATASET`, and written into its downloaded file, where the cell is the
#: raw ``false``. It says nothing about whether a popular vote was held.
HAS_POPULAR_VOTE_NOTE = (
    'A false in the popular-vote column, shown as "Not in this dataset", means this '
    "dataset holds no popular-vote figure for that year. It does not say whether a "
    "popular vote was held."
)

#: A popular-vote or hybrid cell with no figure because the year lies outside the
#: popular-vote window (#308): the panel's null there, and T3's popular-vote columns
#: and hybrid score (``national_pv_votes``, ``pv_share``, ``hybrid_score``) in a year
#: with no popular vote. One wording for that cause in the panel and T3 (#352). A null
#: party has nothing to do with the window: in any year it reads :data:`NOT_IN_DATASET`
#: with :data:`PARTY_NULL_NOTE` (#389). T2 and T4 name the window's side
#: (:data:`BEFORE_WINDOW`, :data:`AFTER_WINDOW`).
NOT_APPLICABLE = "Not in this dataset: no popular-vote figures for this year"

#: A flip that happened; ``method`` is ``popular-vote`` or ``hybrid``, and ``role`` is
#: ``winner`` with an Electoral College majority, else ``leader`` (#355).
FLIP_YES = "Yes: the {method} winner is not the Electoral College {role}"

#: The panel's ``ec_winner`` label when ``ec_determinative`` is true, and when it is
#: false (#355); a null or unknown one reads ``LABELS["ec_winner"]``.
EC_WINNER = "Electoral College winner"
EC_LEADER_NO_MAJORITY = "Electoral College leader (no majority)"

#: Each ``ec_determinative`` value: a real outcome either way, never a missing value.
EC_MAJORITY = "A candidate won a majority of electors appointed"
NO_EC_MAJORITY = "No candidate reached a majority of electors appointed"

#: The hybrid's one line of help text: what it computes, and nothing about its merits.
HYBRID_NOTE = (
    "The hybrid score is the average of a candidate's electoral share and popular-vote "
    "share; the candidate with the highest score wins it."
)

#: What the panel's three margins measure (#352; drafted for the owner's review in
#: place).
MARGIN_NOTE = (
    "A margin is the gap, in percentage points, between the first- and second-place "
    "candidates under that method. Each method ranks the candidates on its own."
)

#: Why T3 shows the electoral share twice (#352; drafted for the owner's review in
#: place). True by configuration: the only coverage policy is (b) (D038, D042 §2).
EC_SHARE_HYBRID_NOTE = (
    "The hybrid uses each candidate's electoral share as it is, so the hybrid's "
    "electoral share repeats it. Both are shown so you can check that."
)


#: Each nominating-party code's display form (#389, D077; owner approval at #389's plan
#: gate). A closed table: a code outside it reads :data:`UNRECOGNIZED`, and
#: ``TestPartyDisplay.test_every_code_has_a_display_form`` (the one-election view's test
#: module) pins its keys to ``usvote.party.NOMINATING_PARTIES``, so a new code fails
#: until it has a form here. A joint nomination names its components in code order,
#: joined by "and", never a hyphen, which would read as one party's name.
NOMINATING_PARTY: dict[str, str] = {
    "democratic_republican": "Democratic-Republican",
    "national_republican": "National Republican",
    "democratic": "Democratic",
    "anti_masonic": "Anti-Masonic",
    "whig": "Whig",
    "american": "American (Know-Nothing)",
    "republican": "Republican",
    "southern_democratic": "Southern Democratic",
    "constitutional_union": "Constitutional Union",
    "liberal_republican": "Liberal Republican",
    "populist": "Populist",
    "progressive_1912": "Progressive (1912)",
    "progressive_1924": "Progressive (1924)",
    "states_rights_democratic": "States' Rights Democratic",
    "american_independent": "American Independent",
    "libertarian": "Libertarian",
    "liberal_republican_democratic": "Liberal Republican and Democratic",
    "democratic_populist": "Democratic and Populist",
    "american_whig": "American (Know-Nothing) and Whig",
    "no_nomination": NO_NOMINATION,
}


def _ec_role_is_winner(determinative: object) -> bool:
    """The one test of whether the Electoral College's top candidate is its winner:
    only a true ``ec_determinative`` (a majority of electors appointed); otherwise it
    is its leader."""
    return determinative is True


def ec_winner_label(determinative: object) -> str:
    """The panel's ``ec_winner`` label for the block's ``ec_determinative`` (#355)."""
    if _ec_role_is_winner(determinative):
        return EC_WINNER
    if determinative is False:
        return EC_LEADER_NO_MAJORITY
    return LABELS["ec_winner"]


def is_blank(value: object) -> bool:
    """A null or blank text: no value, so a cell names no cause for it, or the cause
    its row gives (#355). Every other value is a value."""
    return value is None or (isinstance(value, str) and not value.strip())


def _finite(value: object) -> float | None:
    """A number as a finite float, or ``None`` for anything else: a bool, a value of no
    numeric type, an integer no float can hold, or a non-finite number. Each of those
    that is a value reads :data:`UNRECOGNIZED` (:func:`_unknown`), never a figure."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number_ = float(value)
    except OverflowError:
        return None
    return number_ if math.isfinite(number_) else None


def _unknown(value: object, null: str = NOT_IN_DATASET) -> str:
    """A value a cell has no wording for: ``null`` for no value, else
    :data:`UNRECOGNIZED`. Never the raw value."""
    return null if is_blank(value) else UNRECOGNIZED


def cell(children: Any, tag: Any = html.Td, title: str | None = None) -> Any:
    """A cell (``tag``, a ``Td`` or a panel ``Dd``) holding ``children``; an
    :data:`UNRECOGNIZED` cell carries :data:`UNRECOGNIZED_NOTE` as its help text, else
    ``title`` where one is given."""
    if children == UNRECOGNIZED or children == [UNRECOGNIZED]:
        title = UNRECOGNIZED_NOTE
    return tag(children) if title is None else tag(children, title=title)


def header(field: str) -> html.Th:
    """A column header: the plain label, with the raw field name as its tooltip."""
    return html.Th(LABELS[field], title=field, scope="col")


def glossary(
    fields: Iterable[str],
    summary: str = "Column names",
    chosen: Mapping[str, str] | None = None,
) -> html.Details:
    """Each column's plain label beside the API field name it shows. A list that is no
    table (the election panel) names its ``summary`` otherwise, and a label that
    depends on the data (``ec_winner``'s, #355) comes from ``chosen``."""
    shown = {**LABELS, **(chosen or {})}
    return html.Details(
        [
            html.Summary(summary),
            html.Dl(
                [
                    item
                    for field in fields
                    for item in (html.Dt(shown[field]), html.Dd(html.Code(field)))
                ]
            ),
        ],
        className="glossary",
    )


def has_popular_vote(value: object) -> str:
    """The cell for ``has_popular_vote``.

    ``True`` reads "Yes" and ``False`` :data:`NOT_IN_DATASET`. A null or a blank names
    no cause, so it reads :data:`NOT_IN_DATASET` too (:data:`HAS_POPULAR_VOTE_NOTE`
    explains only ``False``); any other value reads :data:`UNRECOGNIZED`.
    """
    if value is True:
        return "Yes"
    if value is False:
        return NOT_IN_DATASET
    return _unknown(value)


def number(value: object) -> str:
    """An integer with thousands separators, however large; a null or a blank names no
    cause, and anything else (a float, a bool, a string) reads :data:`UNRECOGNIZED`."""
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return _unknown(value)


def share(value: object) -> str:
    """A share as a percentage to one decimal place.

    Total: a null or a blank names no cause; any other value no percentage can show
    reads :data:`UNRECOGNIZED` (see :func:`_finite`), including a finite one whose
    percentage overflows, rather than raising ``OverflowError`` past the page's degraded
    state (``json`` parses integers of any size).
    """
    number_ = _finite(value)
    if number_ is None or not math.isfinite(number_ * 100):
        return _unknown(value)
    return f"{number_ * 100:.1f}%"


def yes_no(value: object) -> str:
    """A known boolean fact (``took_office``): "Yes" or "No"; a null or a blank names
    no cause, and anything else reads :data:`UNRECOGNIZED`."""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return _unknown(value)


def nominating_party(value: object) -> str:
    """A nominating party's display form (#389); see :func:`_closed_value`. Exact
    match: a code is never stripped or re-cased."""
    return _closed_value(value, NOMINATING_PARTY)


def _note_text(value: object) -> str | None:
    """A row note as served, or ``None`` when it is not text with something in it."""
    return value if isinstance(value, str) and value.strip() else None


def nominating_party_cell(row: Mapping[str, Any]) -> html.Td:
    """A row's party cell (#389): :func:`nominating_party`, with the one help text that
    explains it. An unrecognized value carries :data:`UNRECOGNIZED_NOTE`
    (:func:`cell`); a row with a note carries the note as served, after
    :data:`NO_NOMINATION_NOTE` on a ``no_nomination`` row and after
    :data:`PARTY_NULL_NOTE` on a null or blank party (defensive: the API serves no such
    row); a ``no_nomination`` row without one carries :data:`NO_NOMINATION_NOTE`; a
    null or blank party carries :data:`PARTY_NULL_NOTE`; a party with no note carries
    none."""
    value = row.get("nominating_party")
    shown = nominating_party(value)
    note = _note_text(row.get("nominating_party_note"))
    # The rule keys on the code and the null, never on a display label.
    lead = (
        NO_NOMINATION_NOTE
        if value == "no_nomination"
        else PARTY_NULL_NOTE
        if is_blank(value)
        else None
    )
    title = note if lead is None else lead if note is None else f"{lead} {note}"
    td: html.Td = cell(shown, title=title)
    return td


def party_notes(rows: Iterable[Mapping[str, Any]]) -> list[html.Div]:
    """The visible Party notes list under a table (#389): one item per candidate-year
    among ``rows`` whose note is text with something in it, in first-seen order, each
    candidate-year once however many state rows repeat it (keyed on the year, the slug
    and the name, so two candidates whose slug is missing never merge). A list, empty
    when there is none, so a page splices it in place (``*party_notes(rows)``).
    The candidate's name is shown as served; a null or blank one reads
    :data:`NOT_IN_DATASET` and one that is not text reads :data:`UNRECOGNIZED`
    (:func:`_unknown`), never the raw value."""
    items: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        note = _note_text(row.get("nominating_party_note"))
        name = row.get("candidate")
        key = (repr(row.get("year")), repr(row.get("candidate_slug")), repr(name))
        if note is None or key in seen:
            continue
        seen.add(key)
        items.append(
            PARTY_NOTE_ITEM.format(
                candidate=name
                if isinstance(name, str) and not is_blank(name)
                else _unknown(name),
                year=row.get("year"),
                note=note,
            )
        )
    if not items:
        return []
    return [
        html.Div(
            [
                html.P(html.Strong(PARTY_NOTES_HEADING), className="note"),
                html.Ul([html.Li(item) for item in items]),
            ],
            className="party-notes",
        )
    ]


def popular_votes(
    value: object, pv_status: object, year: int, coverage: dict[str, Any]
) -> str:
    """A state's popular-vote cell: the figure, or why there is none.

    A null (or a blank, #355) is never bare: a legislature's choice and a state taking
    no part say so whatever the year; a held popular vote with no figure says whether
    the year lies before the dataset's popular-vote window, after it (a snapshot whose
    Electoral College data runs ahead of its popular vote), or inside it. An unknown
    status names no cause it cannot vouch for: see :func:`_unknown`. The window comes
    from ``coverage``, never a literal.
    """
    if not is_blank(value):
        return number(value)
    if pv_status == "legislature_chosen":
        return LEGISLATURE_CHOSE
    if pv_status == "not_participating":
        return TOOK_NO_PART
    if pv_status != "popular_vote":
        return _unknown(pv_status)
    if year < coverage["pv_year_min"]:
        return BEFORE_WINDOW.format(pv_year_min=coverage["pv_year_min"])
    if year > coverage["pv_year_max"]:
        return AFTER_WINDOW
    return NO_FIGURE


def pv_status(value: object) -> str:
    """A ``pv_status`` value's label; see :func:`_closed_value`."""
    return _closed_value(value, PV_STATUS)


def count_status(status: object, reason: object) -> list[Any]:
    """A count-status cell: the label, and for a vote not counted, its meaning and the
    National Archives' reason sentence verbatim, shown only when it is text with
    something in it (the download keeps it as served). Any other status: see
    :func:`_unknown`."""
    if not isinstance(status, str) or status not in COUNT_STATUS:
        return [_unknown(status)]
    label, meaning = COUNT_STATUS[status]
    if meaning is None:
        return [label]
    parts: list[Any] = [html.Strong(label), f" ({meaning})"]
    if isinstance(reason, str) and reason.strip():
        parts += [html.Br(), html.Span(reason, className="reason")]
    return parts


def _closed_value(value: object, table: dict[str, str]) -> str:
    """A closed value's label. A null or a blank is no value the row explains, so it
    names none (:data:`NOT_IN_DATASET`, never a bare cell); any other value outside
    ``table`` reads :data:`UNRECOGNIZED`, never the raw value (#355)."""
    if isinstance(value, str) and value in table:
        return table[value]
    return _unknown(value)


def boundary_basis(value: object) -> str:
    """A ``boundary_basis`` value's label (#280); see :func:`_closed_value`."""
    return _closed_value(value, BOUNDARY_BASIS)


def per_capita_coverage(value: object) -> str:
    """A per-capita ``coverage`` value's label (#280); see :func:`_closed_value`."""
    return _closed_value(value, PER_CAPITA_COVERAGE)


def _null_per_capita(coverage: object) -> str:
    """Why a per-capita figure is null, as far as ``coverage`` says.

    No governing census figure reads as such; ``covered``, a null or a blank gives no
    cause, so the cell names none (:data:`NOT_IN_DATASET`); any other value reads
    :data:`UNRECOGNIZED` (see :func:`_closed_value`).
    """
    if coverage == "covered":
        return NOT_IN_DATASET
    return per_capita_coverage(coverage)


def population(value: object, coverage: object) -> str:
    """A per-capita population cell: the figure, or why there is none (#280); a blank
    is no figure (#355)."""
    return _null_per_capita(coverage) if is_blank(value) else number(value)


def persons_per_electoral_vote(
    value: object, coverage: object, allotment: object
) -> str:
    """A persons-per-electoral-vote cell: the figure to a whole person, or why there is
    none (#280). Never bare, and never an infinity: a null ratio over a zero allotment
    reads as such.

    The single statement of which cause explains a null (or blank, #355) ratio. A
    missing census figure comes first, so a row carrying both causes reads as that;
    then a zero allotment (the state's votes were withheld), which wins over an
    unrecognized ``coverage``; then ``coverage`` as :func:`_null_per_capita` reads it.
    Total, as :func:`share` is: any other value no figure can show (a non-finite
    number, an integer no float can hold, a bool, a string) reads
    :data:`UNRECOGNIZED`.
    """
    if is_blank(value):
        if coverage == NO_GOVERNING_FIGURE:
            return PER_CAPITA_COVERAGE[NO_GOVERNING_FIGURE]
        if allotment == 0 and not isinstance(allotment, bool):
            return NO_ELECTORAL_VOTES
        return _null_per_capita(coverage)
    number_ = _finite(value)
    return _unknown(value) if number_ is None else f"{round(number_):,}"


def census_year(value: object) -> str:
    """A census year (#280): the year, with no thousands separator; otherwise see
    :func:`_unknown`."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _unknown(value)


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
    party cell carries its note; an unrecognized cell carries :data:`UNRECOGNIZED_NOTE`.
    """
    coverage = row["coverage"]
    allotment = row["state_electoral_votes"]
    return [
        cell(census_year(row["governing_census_year"])),
        cell(number(allotment)),
        cell(population(row["population"], coverage)),
        cell(boundary_basis(row["boundary_basis"]), title=BOUNDARY_NOTE),
        cell(per_capita_coverage(coverage)),
        cell(
            persons_per_electoral_vote(
                row["persons_per_electoral_vote"], coverage, allotment
            )
        ),
    ]


def in_pv_window(year: int, coverage: dict[str, Any]) -> bool:
    """Whether ``year`` lies inside the popular-vote window ``coverage`` names (#308).

    The window comes from ``coverage``, never a literal. This module reads no
    :mod:`explore.query`, so it does not check the window: the page does, once, with
    ``query.year_span`` before any cell reads it (a bool, a float, a reversed window or
    a missing bound would otherwise decide the answer silently). Unchecked, this raises
    only on a missing key or an incomparable type.
    """
    return bool(coverage["pv_year_min"] <= year <= coverage["pv_year_max"])


def _null(applicable: bool) -> str:
    """A null panel figure: :data:`NOT_APPLICABLE` outside the window; inside it, no
    cause."""
    return NOT_IN_DATASET if applicable else NOT_APPLICABLE


def winner(value: object, applicable: bool) -> str:
    """A winner cell (#308): the name, or why there is none.

    ``applicable`` is whether the method has a winner this year: always for the
    Electoral College, inside the popular-vote window for the other two. A name is
    shown whatever the year, as :func:`popular_votes` shows a figure; a blank is no
    name, and a value that is not text reads :data:`UNRECOGNIZED`.
    """
    if isinstance(value, str) and not is_blank(value):
        return value
    return _unknown(value, _null(applicable))


def flip(value: object, method: str, applicable: bool, *, determinative: object) -> str:
    """A flip cell (#308): only ``True`` and ``False`` read Yes and No; a null or a
    blank is never "No" (see :func:`winner`); anything else reads
    :data:`UNRECOGNIZED`. A flip names the Electoral College's winner only with a
    majority (``determinative``), else its leader (#355)."""
    if value is True:
        role = "winner" if _ec_role_is_winner(determinative) else "leader"
        return FLIP_YES.format(method=method, role=role)
    if value is False:
        return "No"
    return _unknown(value, _null(applicable))


def margin(value: object, applicable: bool) -> str:
    """A margin cell (#308), already in percentage points in the API, to one decimal.

    A null or a blank reads as :func:`winner`'s does. Total, as :func:`share` is: any
    other value no figure can show (a non-finite number, an integer no float can hold,
    a value of no numeric type) reads :data:`UNRECOGNIZED`.
    """
    points = _finite(value)
    if points is None:
        return _unknown(value, _null(applicable))
    return f"{points:.1f} percentage points"


def ec_majority(value: object) -> str:
    """An ``ec_determinative`` cell (#308): ``False`` is a real outcome, never a gap;
    a null or a blank names no cause; anything else reads :data:`UNRECOGNIZED`."""
    if value is True:
        return EC_MAJORITY
    if value is False:
        return NO_EC_MAJORITY
    return _unknown(value)


def share_cell(value: object) -> str:
    """A share the schema makes nullable though the API fills it for every year
    (``ec_share_full``, ``ec_share_hybrid``, ``pv_coverage``): a null names no cause,
    as :func:`share` reads one."""
    return share(value)
