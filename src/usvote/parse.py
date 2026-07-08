"""Parse stage — turn raw Archives HTML into structured per-year records.

Maps to notebook Section 2 (the pure half). These functions take already-fetched
``<table>`` elements (see :mod:`usvote.scrape`) and do no network access, which
makes them the natural first fixture-based unit-test target. The output is
``parsed_election_years``: a list of per-year dicts with keys ``t1``,
``t2.candidate_state`` and ``t2.votes_by_state`` that :mod:`usvote.transform`
(#26) later feeds to ``pd.json_normalize``.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S2 (#25). The parser
family lands here unchanged in behavior — ``parse_election_years``,
``parse_election_year_tables``, ``parse_table1``, ``parse_t1_candidate_party``,
``parse_table2``, ``parse_t2_num_candidates``, ``parse_t2_candidate_state``,
``parse_t2_votes_by_state`` — with two deliberate changes that mirror the
``scrape``/``db`` ports:

- **Typed failures.** Where the notebook printed an error and returned ``None``
  on a malformed table (a bad Table 1 header, a missing ``For President``
  colspan), this raises :class:`ParseError`. Returning ``None`` there silently
  poisoned the downstream ``json_normalize``; a typed, message-carrying
  exception names what was wrong instead.
- **Modern bs4 lookups.** ``find(..., string=)`` replaces the deprecated
  ``text=`` keyword; behavior against the Archives markup is identical (verified
  against saved 2016/2020 fixtures).

Each per-year page has two tables. **Table 1** gives the top-two candidates and
their parties. **Table 2** carries the candidate home states plus a
variable-width votes-by-state matrix — the number of candidate columns is read
from the ``For President`` header's ``colspan`` (:func:`parse_t2_num_candidates`),
which is how anomaly years with faithless/"Other" electors (e.g. 2016) widen the
table.

Note the ``votes_by_state`` records intentionally mix key types: the string keys
``'state'`` and ``'total_electoral_votes'`` alongside integer candidate-column
indices (``1``, ``2``, …). This is the exact shape ``json_normalize`` expects
downstream, so the port preserves it rather than tidying it.
"""

from __future__ import annotations

from collections.abc import Container, Iterable, Sequence
from typing import TypedDict

from bs4.element import Tag

# Table 1 row layout: row 0 is the winning President, row 1 the main opponent.
# Kept as parallel (index, expected-header) pairs exactly as the notebook walked
# them, so a header drift trips the check in parse_t1_candidate_party.
T1_ROW_INDS = (0, 1)
T1_ROW_HEADERS = ("President", "Main Opponent")

# Column-0 labels that mark the electoral-vote totals row rather than a state.
TOTALS_LABELS = frozenset({"Total", "Totals"})


class CandidateParty(TypedDict):
    """One Table 1 candidate: display name (commas stripped) and party code."""

    president_candidate_name: str
    president_candidate_party: str


class CandidateState(TypedDict):
    """One Table 2 candidate column: name, 1-based column index, home state.

    ``president_candidate_state`` is ``None`` for the "Other" aggregate column
    (faithless / minor electors), which has no single home state.
    """

    president_candidate_name: str
    col_ind: int
    president_candidate_state: str | None


# A votes-by-state record: 'state' -> name, 'total_electoral_votes' -> int, and
# integer candidate-column indices -> that candidate's electoral votes. The mixed
# key/value types are load-bearing for the downstream json_normalize (see module
# docstring); this alias documents the shape without narrowing it.
StateVotes = dict[str | int, str | int]


class ParsedTable2(TypedDict):
    """Table 2 parsed into its two parts: candidate home states + vote matrix."""

    candidate_state: list[CandidateState]
    votes_by_state: list[StateVotes]


class ParsedYear(TypedDict):
    """One election year: Table 1 candidates/parties, Table 2, and the year."""

    t1: list[CandidateParty]
    t2: ParsedTable2
    year: int


class ParseError(RuntimeError):
    """Raised when an Archives table does not match the expected structure.

    The notebook printed a message and returned ``None`` on a malformed Table 1
    header or a missing ``For President`` colspan, letting the bad value flow into
    ``json_normalize``. Raising a typed, message-carrying exception instead
    surfaces the problem at the row that caused it.
    """


def parse_election_years(
    data_tables: dict[int, list[Tag]], state_names: Container[str]
) -> list[ParsedYear]:
    """Parse every scraped election year into a :class:`ParsedYear` record.

    ``data_tables`` maps a year to its two raw ``<table>`` elements (the output
    of :func:`usvote.scrape.scrape_raw_election_tables`); ``state_names`` is the
    set of valid US state names used to tell state rows from the totals/notes
    rows at the foot of Table 2.
    """
    parsed_years: list[ParsedYear] = []
    for ind, year in enumerate(data_tables):
        print(f"Working on Election Year = {year} ({ind})")
        parsed = parse_election_year_tables(data_tables[year], state_names)
        parsed_years.append({"t1": parsed["t1"], "t2": parsed["t2"], "year": year})
    return parsed_years


class _YearTables(TypedDict):
    t1: list[CandidateParty]
    t2: ParsedTable2


def parse_election_year_tables(
    year_tables: Sequence[Tag], state_names: Container[str]
) -> _YearTables:
    """Dispatch a single year's two tables to the Table 1 / Table 2 parsers."""
    return {
        "t1": parse_table1(year_tables[0].find_all("tr")),
        "t2": parse_table2(year_tables[1].find_all("tr"), state_names),
    }


def parse_table1(t1_rows: Sequence[Tag]) -> list[CandidateParty]:
    """Parse Table 1's President and Main-Opponent rows into name/party dicts."""
    return [
        parse_t1_candidate_party(t1_rows, ri, rh)
        for ri, rh in zip(T1_ROW_INDS, T1_ROW_HEADERS)
    ]


def parse_t1_candidate_party(
    t1_rows: Sequence[Tag], row_ind: int, row_header: str
) -> CandidateParty:
    """Parse one Table 1 row into its candidate name and party code.

    The candidate cell reads ``Name [Party]``; the name has commas and leading/
    trailing ``*`` (footnote markers) stripped. Raises :class:`ParseError` if the
    row's header is not ``row_header`` (the notebook printed and returned
    ``None``).
    """
    header = t1_rows[row_ind].find("th")
    if header is None:
        raise ParseError(
            f"Table 1 row {row_ind} has no <th> header (expected {row_header!r})"
        )
    if header.get_text() != row_header:
        raise ParseError(
            f"Table 1 row {row_ind} header is {header.get_text()!r}, "
            f"expected {row_header!r}"
        )
    cell = t1_rows[row_ind].find("td")
    if cell is None:
        raise ParseError(f"Table 1 row {row_ind} ({row_header}) has no <td> data cell")
    candidate, party = cell.get_text().split(" [")
    return {
        "president_candidate_name": candidate.strip(" *").replace(",", ""),
        "president_candidate_party": party.strip(" *]"),
    }


def parse_table2(t2_rows: Sequence[Tag], state_names: Container[str]) -> ParsedTable2:
    """Parse Table 2 into candidate home states and the votes-by-state matrix.

    Row 0 is the header (its ``For President`` colspan sets the candidate count),
    row 1 the candidate/home-state row, and rows 2+ the per-state vote rows.
    """
    num_candidates = parse_t2_num_candidates(t2_rows[0])
    return {
        "candidate_state": parse_t2_candidate_state(t2_rows[1], num_candidates),
        "votes_by_state": parse_t2_votes_by_state(
            t2_rows[2:], num_candidates, state_names
        ),
    }


def parse_t2_num_candidates(header_row: Tag) -> int:
    """Return the candidate-column count from the ``For President`` colspan.

    This is the variable-width hinge: anomaly years with faithless or "Other"
    electors publish extra columns, and every downstream slice keys off this
    count. Raises :class:`ParseError` if the header or its colspan is absent.
    """
    header = header_row.find("th", string="For President")
    if header is None:
        raise ParseError("Table 2 header row has no 'For President' <th>")
    colspan = header.get("colspan")
    if colspan is None:
        raise ParseError("Table 2 'For President' <th> has no colspan")
    # bs4 may hand back a multi-valued attribute as a list; take the first, as
    # scrape._href does for hrefs.
    return int(colspan if isinstance(colspan, str) else colspan[0])


def parse_t2_candidate_state(
    cs_row: Tag, num_candidates: int
) -> list[CandidateState]:
    """Parse the candidate/home-state row into ``num_candidates`` records.

    Each cell reads ``Name, of State``; the "Other" aggregate column has no home
    state and yields ``president_candidate_state=None``. Cells that split a name
    across a ``<br>`` are joined on whitespace before parsing.
    """
    cs_cols = cs_row.find_all("td")
    candidate_state: list[CandidateState] = []
    for ci, cs in enumerate(cs_cols[:num_candidates]):
        if cs.find("br"):
            text = " ".join(cs.stripped_strings)
        else:
            text = cs.get_text()
        if text == "Other":
            candidate, state = text, None
        else:
            candidate, state = text.split(" of ")
            candidate = candidate.strip(", *").replace(",", "")
            state = state.strip(" *").replace(",", "")
        candidate_state.append(
            {
                "president_candidate_name": candidate,
                "col_ind": ci + 1,
                "president_candidate_state": state,
            }
        )
    return candidate_state


def parse_t2_votes_by_state(
    states_rows: Iterable[Tag],
    num_candidates: int,
    state_names: Container[str],
) -> list[StateVotes]:
    """Parse the per-state vote rows into ``{state, votes...}`` records.

    Resolving column 0 tells three row kinds apart: a state name (present in
    ``state_names``), a ``Total``/``Totals`` label in column 0, or a ``<th>Total``
    header row — the last shifts the column window left by one since it has no
    state ``<td>``. Any other row (e.g. the trailing Notes row) has no valid
    state and is skipped, which is the notebook's parse-time state-name check.

    Within a kept row, column 0 of the vote window is the state's electoral-vote
    total (stored under ``'total_electoral_votes'``); the remaining columns are
    per-candidate electoral votes keyed by integer column index, with ``'-'``
    read as ``0``.
    """
    votes_by_state: list[StateVotes] = []
    for sr in states_rows:
        state_cols = sr.find_all("td")
        # An empty `if state_cols` yields col-0 "" which resolves to no state and
        # is skipped — a deliberate softening of the notebook's IndexError on a
        # cell-less row, so a stray blank/separator row can't crash a full run.
        col_0_text = state_cols[0].get_text().strip(" *") if state_cols else ""
        state: str | None
        if col_0_text in state_names:
            state = col_0_text
            start_ind, end_ind = 1, num_candidates + 2
        elif col_0_text in TOTALS_LABELS:
            state = "Totals"
            start_ind, end_ind = 1, num_candidates + 2
        elif sr.find("th", string="Total"):
            state = "Totals"
            start_ind, end_ind = 0, num_candidates + 1
        else:
            state = None
        # Only keep the row if column 0 resolved to a valid state (or the totals
        # row): this validates the parse and skips the trailing Notes row.
        if state is not None:
            state_votes: StateVotes = {"state": state}
            for si, sv in enumerate(state_cols[start_ind:end_ind]):
                votes = sv.get_text()
                key: str | int = "total_electoral_votes" if si == 0 else si
                state_votes[key] = int(votes) if votes != "-" else 0
            votes_by_state.append(state_votes)
    return votes_by_state
