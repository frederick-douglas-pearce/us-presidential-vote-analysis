"""Unit tests for ``usvote.parse``.

These run fully offline. Two real Archives year pages captured under
``tests/fixtures/`` are replayed through the scrape module's ``fetch`` seam and
parsed:

- **2020** — a structurally-simple modern year (two candidate columns).
- **2016** — an anomaly year that widens Table 2 to four ``For President``
  columns (Trump, Other, Clinton, Other) with faithless/"Other" electors, so it
  exercises the variable-candidate-count logic, the ``Other`` home-state=None
  case, and the ``<th>Total`` totals row.

Crafted inline HTML covers the structural error paths that raise
:class:`ParseError`.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag

from tests._helpers import FIXTURES_DIR, STATE_NAMES
from usvote.parse import (
    ParsedYear,
    ParseError,
    _assert_candidate_columns_consistent,
    _clean_label,
    _is_totals_label,
    parse_election_years,
    parse_t1_candidate_party,
    parse_t2_num_candidates,
    parse_t2_votes_by_state,
    strip_footnotes,
)
from usvote.scrape import fetch_from_dir, get_html_tables


def _year_tables(year: int) -> list[Tag]:
    """Load a saved year page's two raw ``<table>`` elements from fixtures."""
    fetch = fetch_from_dir(FIXTURES_DIR)
    return get_html_tables(
        f"https://www.archives.gov/electoral-college/{year}",
        find_all=True,
        fetch=fetch,
    )


@pytest.fixture(scope="module")
def parsed() -> dict[int, ParsedYear]:
    """Parse the 2016 and 2020 fixtures once; key the per-year records by year."""
    data_tables = {year: _year_tables(year) for year in (2016, 2020)}
    return {py["year"]: py for py in parse_election_years(data_tables, STATE_NAMES)}


# --- top-level structure ---------------------------------------------------


def test_parse_election_years_shape(parsed: dict[int, ParsedYear]) -> None:
    # Every per-year record carries the notebook's t1 / t2 / year keys, and t2
    # splits into candidate_state + votes_by_state.
    for year in (2016, 2020):
        rec = parsed[year]
        assert set(rec) == {"t1", "t2", "year"}
        assert rec["year"] == year
        assert set(rec["t2"]) == {
            "candidate_state",
            "votes_by_state",
            "contested_cells",
        }
        # No modern year prints a parenthesized (contested) vote cell.
        assert rec["t2"]["contested_cells"] == []


# --- 2020: simple modern year ----------------------------------------------


def test_2020_table1_candidates_and_parties(parsed: dict[int, ParsedYear]) -> None:
    assert parsed[2020]["t1"] == [
        {"president_candidate_name": "Joseph R. Biden Jr.", "president_candidate_party": "D"},
        {"president_candidate_name": "Donald J. Trump", "president_candidate_party": "R"},
    ]


def test_2020_two_candidate_columns(parsed: dict[int, ParsedYear]) -> None:
    assert parsed[2020]["t2"]["candidate_state"] == [
        {"president_candidate_name": "Joseph R. Biden Jr.", "col_ind": 1, "president_candidate_state": "Delaware"},
        {"president_candidate_name": "Donald J. Trump", "col_ind": 2, "president_candidate_state": "Florida"},
    ]


def test_2020_votes_by_state(parsed: dict[int, ParsedYear]) -> None:
    votes = parsed[2020]["t2"]["votes_by_state"]
    # 50 states + DC + one Totals row; the trailing Notes row is dropped.
    assert len(votes) == 52
    assert votes[0] == {"state": "Alabama", "total_electoral_votes": 9, 1: 0, 2: 9}
    by_state = {v["state"]: v for v in votes}
    assert by_state["District of Columbia"] == {
        "state": "District of Columbia", "total_electoral_votes": 3, 1: 3, 2: 0,
    }
    assert by_state["Totals"] == {
        "state": "Totals", "total_electoral_votes": 538, 1: 306, 2: 232,
    }


# --- 2016: anomaly year (variable candidate count + "Other") ---------------


def test_2016_widens_to_four_president_columns(parsed: dict[int, ParsedYear]) -> None:
    # The faithless/"Other" electors give Table 2 a colspan-4 "For President"
    # header — the variable-candidate-count path.
    assert len(parsed[2016]["t2"]["candidate_state"]) == 4


def test_2016_other_column_has_no_home_state(parsed: dict[int, ParsedYear]) -> None:
    cols = parsed[2016]["t2"]["candidate_state"]
    assert cols == [
        {"president_candidate_name": "Donald Trump", "col_ind": 1, "president_candidate_state": "New York"},
        {"president_candidate_name": "Other", "col_ind": 2, "president_candidate_state": None},
        {"president_candidate_name": "Hillary Clinton", "col_ind": 3, "president_candidate_state": "New York"},
        {"president_candidate_name": "Other", "col_ind": 4, "president_candidate_state": None},
    ]


def test_2016_votes_span_all_four_candidate_columns(parsed: dict[int, ParsedYear]) -> None:
    votes = parsed[2016]["t2"]["votes_by_state"]
    assert len(votes) == 52
    by_state = {v["state"]: v for v in votes}
    # Trump 304, Other 2, Clinton 227, Other 5 = the four president columns.
    assert by_state["Totals"] == {
        "state": "Totals", "total_electoral_votes": 538, 1: 304, 2: 2, 3: 227, 4: 5,
    }
    # A '-' cell reads as 0 (Alabama went entirely to column 1).
    assert by_state["Alabama"] == {
        "state": "Alabama", "total_electoral_votes": 9, 1: 9, 2: 0, 3: 0, 4: 0,
    }


# --- parse_t2_votes_by_state row disambiguation ----------------------------


def test_votes_by_state_plain_td_totals_row() -> None:
    # Older years (pre-modern markup) label the totals row with a plain
    # <td>Total rather than a <th>Total header. Neither the 2016 nor 2020 fixture
    # exercises this branch, so cover it with a crafted row: the window keeps the
    # same start_ind=1 as a state row (the label sits in a <td>).
    rows = BeautifulSoup(
        "<table><tr><td>Total</td><td>538</td><td>306</td><td>232</td></tr></table>",
        "html.parser",
    ).find_all("tr")
    assert parse_t2_votes_by_state(rows, 2, STATE_NAMES) == (
        [{"state": "Totals", "total_electoral_votes": 538, 1: 306, 2: 232}],
        [],
    )


def test_votes_by_state_skips_non_state_rows() -> None:
    # A row whose column 0 is neither a known state nor a totals label (e.g. the
    # trailing Notes row) is dropped — the parse-time state-name validation.
    rows = BeautifulSoup(
        "<table><tr><td>Notes</td><td>see below</td></tr></table>", "html.parser"
    ).find_all("tr")
    assert parse_t2_votes_by_state(rows, 2, STATE_NAMES) == ([], [])


# --- parse_t2_num_candidates -----------------------------------------------


def test_num_candidates_reads_colspan(parsed: dict[int, ParsedYear]) -> None:
    assert parse_t2_num_candidates(_year_tables(2020)[1].find_all("tr")[0]) == 2
    assert parse_t2_num_candidates(_year_tables(2016)[1].find_all("tr")[0]) == 4


def _row(html: str) -> Tag:
    """Parse a single ``<tr>`` fragment, narrowed from ``Tag | None`` for mypy."""
    row = BeautifulSoup(html, "html.parser").find("tr")
    assert isinstance(row, Tag)
    return row


def test_num_candidates_missing_header_raises() -> None:
    with pytest.raises(ParseError, match="no 'For President'"):
        parse_t2_num_candidates(_row("<tr><th>State</th></tr>"))


def test_num_candidates_missing_colspan_raises() -> None:
    with pytest.raises(ParseError, match="no colspan"):
        parse_t2_num_candidates(_row("<tr><th>For President</th></tr>"))


# --- parse_t1_candidate_party error paths ----------------------------------


def _t1_rows(html: str) -> list[Tag]:
    return BeautifulSoup(html, "html.parser").find_all("tr")


def test_t1_wrong_header_raises() -> None:
    rows = _t1_rows("<tr><th>Runner Up</th><td>Someone [X]</td></tr>")
    with pytest.raises(ParseError, match="expected 'President'"):
        parse_t1_candidate_party(rows, 0, "President")


def test_t1_missing_th_raises() -> None:
    rows = _t1_rows("<tr><td>Someone [X]</td></tr>")
    with pytest.raises(ParseError, match="no <th> header"):
        parse_t1_candidate_party(rows, 0, "President")


def test_t1_parses_name_and_party() -> None:
    rows = _t1_rows("<tr><th>President</th><td>George Washington [None] *</td></tr>")
    assert parse_t1_candidate_party(rows, 0, "President") == {
        "president_candidate_name": "George Washington",
        "president_candidate_party": "None",
    }


# --- 1824: pre-1892 drift (footnotes, "Others", plural <th>Totals>) ---------


@pytest.fixture(scope="module")
def parsed_1824() -> ParsedYear:
    """Parse the 1824 fixture once: <sup> footnotes, an "Others" column, and a
    plural ``<th>Totals</th>`` totals row — the three drifts #32 handles."""
    tables = {1824: _year_tables(1824)}
    return next(iter(parse_election_years(tables, STATE_NAMES)))


def test_1824_strips_sup_footnotes_from_state_names(parsed_1824: ParsedYear) -> None:
    # <td>Connecticut<sup>3</sup></td> must parse to the bare state name; left in,
    # "Connecticut3" fails the state-name match and the row is silently dropped — so
    # its mere presence as a key is the footnote-strip regression.
    by_state = {str(v["state"]): v for v in parsed_1824["t2"]["votes_by_state"]}
    assert "Connecticut" in by_state
    assert by_state["Connecticut"]["total_electoral_votes"] == 8


def test_1824_others_column_marked_stateless(parsed_1824: ParsedYear) -> None:
    # colspan-3 For President: Jackson, Adams, and the aggregate "Others" column
    # (Crawford + Clay), which has no single home state.
    cols = parsed_1824["t2"]["candidate_state"]
    assert [c["president_candidate_name"] for c in cols] == [
        "Andrew Jackson", "John Quincy Adams", "Others",
    ]
    assert cols[2]["president_candidate_state"] is None


def test_1824_recognizes_plural_th_totals_row(parsed_1824: ParsedYear) -> None:
    # The 1824 totals row is <th>Totals</th> (plural); a singular-only check drops it
    # and empties the votes fact downstream (electoral rank derives from it). Values
    # are post-<sup>-strip: Jackson 99, Adams 84, Others 78 (= Crawford 41 + Clay 37).
    by_state = {v["state"]: v for v in parsed_1824["t2"]["votes_by_state"]}
    assert by_state["Totals"] == {
        "state": "Totals", "total_electoral_votes": 261, 1: 99, 2: 84, 3: 78,
    }


def test_th_totals_plural_header_recognized() -> None:
    # Crafted regression for the plural <th> totals branch, isolated from a fixture.
    rows = BeautifulSoup(
        "<table><tr><th>Totals</th><td>261</td><td>99</td><td>84</td></tr></table>",
        "html.parser",
    ).find_all("tr")
    assert parse_t2_votes_by_state(rows, 2, STATE_NAMES) == (
        [{"state": "Totals", "total_electoral_votes": 261, 1: 99, 2: 84}],
        [],
    )


def test_strip_footnotes_removes_sup_markers_and_digits() -> None:
    table = _row(
        "<tr><td>Connecticut<sup>3</sup></td><td>261<sup>13</sup></td></tr>"
    ).parent
    assert isinstance(table, Tag)
    strip_footnotes(table)
    assert [c.get_text() for c in table.find_all("td")] == ["Connecticut", "261"]


def test_column_crosscheck_raises_on_vote_column_mismatch() -> None:
    # colspan says 2 president candidates but a vote row exposes only 1 -> a window
    # misalignment the melt would otherwise map to the wrong candidate.
    with pytest.raises(ParseError, match="candidate vote columns"):
        _assert_candidate_columns_consistent(
            2,
            [
                {"president_candidate_name": "A", "col_ind": 1,
                 "president_candidate_state": "X"},
                {"president_candidate_name": "B", "col_ind": 2,
                 "president_candidate_state": "Y"},
            ],
            [{"state": "Ohio", "total_electoral_votes": 3, 1: 3}],
        )


def test_column_crosscheck_raises_on_candidate_count_mismatch() -> None:
    with pytest.raises(ParseError, match="candidates, expected"):
        _assert_candidate_columns_consistent(2, [], [])


# --- 2024: modern footnote format (non-breaking space) ---------------------


def test_clean_label_strips_nbsp_and_asterisk() -> None:
    assert _clean_label("Oregon\xa0") == "Oregon"  # trailing nbsp left by a <sup>
    assert _clean_label("Oregon *") == "Oregon"  # trailing footnote asterisk
    assert _clean_label("\xa0 Totals \xa0") == "Totals"
    assert _clean_label("California") == "California"


def test_2024_footnoted_state_is_not_dropped() -> None:
    # Oregon's 2024 cell is `<a>Oregon</a>\xa0<sup>1</sup>`; after strip_footnotes
    # removes the <sup>, a non-breaking space remains that `.strip(" ")` would miss,
    # dropping Oregon (8 EC, all Harris). All 51 states + Totals must survive.
    tables = {2024: _year_tables(2024)}
    parsed = next(iter(parse_election_years(tables, STATE_NAMES)))
    by_state = {v["state"]: v for v in parsed["t2"]["votes_by_state"]}
    assert "Oregon" in by_state
    assert by_state["Oregon"]["total_electoral_votes"] == 8
    assert len(parsed["t2"]["votes_by_state"]) == 52  # 50 states + DC + Totals


def test_vote_cell_non_numeric_raises_parse_error() -> None:
    # An un-modelled electoral-vote notation must raise a typed, located ParseError
    # rather than a bare int() ValueError. This guard predates 1868 (whose "(9)" it used
    # to catch, before #143 modelled it) and stays: it is what makes the *next*
    # un-modelled marking surface at the row that carried it.
    rows = BeautifulSoup(
        "<table><tr><td>Georgia</td><td>9</td><td>9?</td><td>-</td></tr></table>",
        "html.parser",
    ).find_all("tr")
    with pytest.raises(ParseError, match="un-modelled vote notation"):
        parse_t2_votes_by_state(rows, 2, STATE_NAMES)


def test_mixed_parenthesized_vote_cell_still_raises() -> None:
    """``176 (175)`` is appointed-then-cast, not a contested count — it must NOT parse.

    The negative half of the ``(9)`` rule. The pre-1824 pages carry this notation in the
    totals cell, and reading it as either number would silently pick one of two different
    facts. Only a *wholly* parenthesized cell is a contested-vote marking.
    """
    rows = BeautifulSoup(
        "<table><tr><td>Georgia</td><td>176 (175)</td><td>9</td><td>-</td></tr></table>",
        "html.parser",
    ).find_all("tr")
    with pytest.raises(ParseError, match="un-modelled vote notation"):
        parse_t2_votes_by_state(rows, 2, STATE_NAMES)


# --- 1868: the contested-count year (#143) ---------------------------------


@pytest.fixture(scope="module")
def parsed_1868() -> ParsedYear:
    """The 1868 page: two totals rows, a parenthesized ``(9)``, three dash allotments."""
    tables = {1868: _year_tables(1868)}
    return next(iter(parse_election_years(tables, STATE_NAMES)))


def test_1868_parses_the_contested_parenthesized_votes(parsed_1868: ParsedYear) -> None:
    # Georgia's row is ['Georgia*', '9', '-', '(9)', ...]: nine electors appointed, none
    # for Grant, nine cast for Seymour with their counting in question. The parser reads
    # the number; usvote.transform.COUNT_STATUS_OVERRIDES decides what it means (D043 §3).
    by_state = {v["state"]: v for v in parsed_1868["t2"]["votes_by_state"]}
    assert by_state["Georgia"]["total_electoral_votes"] == 9
    assert (by_state["Georgia"][1], by_state["Georgia"][2]) == (0, 9)


def test_1868_dash_in_the_allotment_column_is_a_real_zero(
    parsed_1868: ParsedYear,
) -> None:
    # Mississippi/Texas/Virginia print '-' in *Electoral Vote of Each State*, not just in
    # the vote columns: not readmitted, no electors appointed, so they genuinely
    # contribute 0 — the fact usvote.pv.absences' zero-EV cross-check keys on.
    by_state = {v["state"]: v for v in parsed_1868["t2"]["votes_by_state"]}
    for state in ("Mississippi", "Texas", "Virginia"):
        assert by_state[state]["total_electoral_votes"] == 0
        assert (by_state[state][1], by_state[state][2]) == (0, 0)


def test_1868_selects_the_totals_row_that_reconciles_with_its_own_state_rows(
    parsed_1868: ParsedYear,
) -> None:
    """The dual-totals resolution (D044): 294, because the state rows say 294.

    The page prints ``Totals (excluding Georgia's votes) 285`` and ``Totals (including
    Georgia's votes) 294`` and marks neither authoritative. Exactly one survives, and it
    is chosen by agreeing with the per-state allotments the same page prints — not by
    position, and not by a curated literal. Verified independently: the 37 state rows sum
    to 294 / Grant 214 / Seymour 80.
    """
    rows = parsed_1868["t2"]["votes_by_state"]
    totals = [v for v in rows if v["state"] == "Totals"]
    assert len(totals) == 1, "exactly one totals row may survive"
    assert totals[0]["total_electoral_votes"] == 294
    assert (totals[0][1], totals[0][2]) == (214, 80)

    states = [v for v in rows if v["state"] != "Totals"]
    assert len(states) == 37
    assert sum(int(v["total_electoral_votes"]) for v in states) == 294
    assert sum(int(v[1]) for v in states) == 214
    assert sum(int(v[2]) for v in states) == 80


def test_1868_recognizes_both_totals_rows_before_choosing_one() -> None:
    """Pins *recognition*, which the surviving-row test alone cannot.

    With a single totals row `_select_totals_row` returns it unvalidated, so a regression
    that left the 285 row **unrecognised** — rather than recognised-and-rejected — would
    still leave 294 surviving and the sibling test green. The dangerous direction (a 285
    row surviving) is caught by `assert_totals_equal_state_sum`; this closes the other
    one, so "two candidates were considered" is asserted rather than assumed.
    """
    rows = _year_tables(1868)[1].find_all("tr")
    for row in rows:
        strip_footnotes(row)
    labels = [
        _clean_label(th.get_text())
        for row in rows
        for th in row.find_all("th")
        if _is_totals_label(th.get_text())
    ]
    assert labels == [
        "Totals (excluding Georgia's votes)",
        "Totals (including Georgia's votes)",
    ]


def test_multiple_totals_rows_none_reconciling_raises() -> None:
    """Never guess. Two totals rows and no agreement with the states is a parse failure.

    The failure this protects against is silent and consequential: picking the wrong
    totals row answers Congress's 1868 question by accident, in whichever direction the
    parser leaned.
    """
    rows = BeautifulSoup(
        "<table>"
        "<tr><td>Ohio</td><td>10</td><td>10</td><td>-</td></tr>"
        "<tr><th>Totals (one way)</th><td>11</td><td>11</td><td>-</td></tr>"
        "<tr><th>Totals (another)</th><td>12</td><td>12</td><td>-</td></tr>"
        "</table>",
        "html.parser",
    ).find_all("tr")
    with pytest.raises(ParseError, match="0 of them match the per-state allotment sum"):
        parse_t2_votes_by_state(rows, 2, STATE_NAMES)


def test_multiple_totals_rows_both_reconciling_raises() -> None:
    """Two rows agreeing with the allotment sum is equally un-resolvable — also raises."""
    rows = BeautifulSoup(
        "<table>"
        "<tr><td>Ohio</td><td>10</td><td>10</td><td>-</td></tr>"
        "<tr><th>Totals (one way)</th><td>10</td><td>10</td><td>-</td></tr>"
        "<tr><th>Totals (another)</th><td>10</td><td>-</td><td>10</td></tr>"
        "</table>",
        "html.parser",
    ).find_all("tr")
    with pytest.raises(ParseError, match="2 of them match the per-state allotment sum"):
        parse_t2_votes_by_state(rows, 2, STATE_NAMES)


def test_a_single_totals_row_is_kept_without_reconciling() -> None:
    """A lone totals row is never subjected to the sum rule — 1832 is the reason.

    1832's totals row carries 288 electors **appointed** while only 286 votes were *cast*
    (two Maryland electors did not vote — ``ELECTORAL_VOTE_SHORTFALLS``). Its allotment
    column still reconciles, but the rule must not be reached at all when there is nothing
    to disambiguate, or a future shortfall year with a genuinely off-by-N total would be
    rejected outright rather than handled by the documented shortfall mechanism.
    """
    tables = {1832: _year_tables(1832)}
    parsed_1832 = next(iter(parse_election_years(tables, STATE_NAMES)))
    rows = parsed_1832["t2"]["votes_by_state"]
    totals = [v for v in rows if v["state"] == "Totals"]
    assert len(totals) == 1
    assert totals[0]["total_electoral_votes"] == 288
    states = [v for v in rows if v["state"] != "Totals"]
    # The allotment column reconciles; the *cast* votes are 2 short, which is the
    # separate ELECTORAL_VOTE_SHORTFALLS mechanism, not a totals-selection problem.
    assert sum(int(v["total_electoral_votes"]) for v in states) == 288
    cast = sum(
        int(votes)
        for v in states
        for key, votes in v.items()
        if isinstance(key, int)
    )
    assert cast == 286


def test_1868_reports_georgia_as_a_contested_cell(parsed_1868: ParsedYear) -> None:
    """The parenthesized cell is *reported*, not merely read (the #143 review's finding).

    Reading `(9)` as 9 without reporting it makes the relaxation global: a parenthesized
    cell in any year with no `COUNT_STATUS_OVERRIDES` entry would load as an ordinary
    counted vote, where before #143 it raised. `transform.assert_contested_cells_
    catalogued` is the reciprocal check, and this is the signal it consumes.
    """
    assert parsed_1868["t2"]["contested_cells"] == [{"state": "Georgia", "col_ind": 2}]


def test_a_totals_row_with_no_vote_cells_raises_a_located_error() -> None:
    """A ragged row must raise ParseError, not a bare KeyError naming nothing.

    `_select_totals_row` runs before `_assert_candidate_columns_consistent` can speak,
    and the 1868 page already interleaves an empty `<tr>` between its two totals rows —
    so ragged rows in exactly this region are real, not hypothetical.
    """
    rows = BeautifulSoup(
        "<table>"
        "<tr><td>Ohio</td><td>10</td><td>10</td><td>-</td></tr>"
        "<tr><th>Totals (one way)</th></tr>"
        "<tr><th>Totals (another)</th><td>10</td><td>10</td><td>-</td></tr>"
        "</table>",
        "html.parser",
    ).find_all("tr")
    with pytest.raises(ParseError, match="carry no electoral-vote cells"):
        parse_t2_votes_by_state(rows, 2, STATE_NAMES)


def test_a_notes_row_opening_with_total_is_not_read_as_a_totals_row() -> None:
    """The column-0 `<td>` path stays an EXACT match; only `<th>` labels are prefixed.

    On a page whose Notes row carries no `<th>`, column 0 is the notes *prose*. A prefix
    match there would slice that prose into the vote window and feed it to
    `_parse_vote_cell`. Widening only the `<th>` path confines the blast radius to cells
    that carry a row label and never prose.
    """
    rows = BeautifulSoup(
        "<table><tr><td>Total electoral votes cast: see below</td>"
        "<td>irrelevant</td><td>prose</td></tr></table>",
        "html.parser",
    ).find_all("tr")
    assert parse_t2_votes_by_state(rows, 2, STATE_NAMES) == ([], [])
