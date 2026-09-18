"""Unit tests for :mod:`usvote.census.conform` (#182).

Offline throughout: the spine comes from the committed EC roster fixture and the census
frames are built here, so nothing touches a DB or the network.

Every guard in this module protects against a **plausible wrong number** rather than a
crash, so each test below is written to fail on the wrong-but-passing input — the
uncorrected Virginia figure, a stale catalog entry, a synthesized value — rather than only
on an obviously broken one. A guard that cannot fail is the defect this repo names as Class
B, and these were checked against that standard by running each on bad input.

The one thing these tests cannot establish is that
:data:`~usvote.census.conform.CENSUS_COVERAGE_EXCEPTIONS` is **complete** — that needs all
51 published sheets. ``TestRealCorpus`` does it and **skips when
``USVOTE_CENSUS_CORPUS_DIR`` is unset**, so running it is a merge precondition rather than
something CI proves.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from tests._helpers import CENSUS_POPCHANGE_XLSX, ec_participation_frame
from usvote.census import conform as conform_module
from usvote.census.conform import (
    BOUNDARY_AT_ELECTION,
    BOUNDARY_PRESENT_DAY,
    BOUNDARY_SUCCESSIONS,
    CENSUS_COVERAGE_EXCEPTIONS,
    COVERAGE_COVERED,
    COVERAGE_NO_GOVERNING_FIGURE,
    ELECTION_POPULATION_COLUMNS,
    EXCEPTION_KINDS,
    KIND_ABSENT_FROM_SOURCE,
    KIND_PRESENT_BUT_UNPARSED,
    BoundarySuccession,
    CensusConformError,
    CoverageException,
    apply_boundary_successions,
    assert_conforms_to_spine,
    assert_election_population_shape,
    assert_no_double_count,
    assert_no_interpolated_population,
    assert_spine_states_covered,
    build_election_population,
    spine_participation,
)
from usvote.census.schema import (
    BASIS_AS_ENUMERATED,
    BASIS_PRESENT_DAY,
    CENSUS_COLUMNS,
    SERIES_RESIDENT,
    SOURCE_CENSUS_BUREAU,
)

# The two figures the Virginia/West Virginia succession turns on, from the published file.
VA_1860_PUBLISHED = 1_219_630
WV_1860_PUBLISHED = 376_688
VA_1860_RESTATED = VA_1860_PUBLISHED + WV_1860_PUBLISHED  # 1,596,318


def _census(cells: list[tuple[int, str, int | None, str]]) -> pd.DataFrame:
    """Build a census frame from ``(census_year, state, population, basis)`` tuples."""
    records = [
        {
            "source": SOURCE_CENSUS_BUREAU,
            "census_year": year,
            "state": state,
            "series": SERIES_RESIDENT,
            "basis": basis,
            "population": population,
            "vintage": "test",
            "source_file": "test.xlsx",
            "redistributable": True,
            "note": None,
        }
        for year, state, population, basis in cells
    ]
    frame = pd.DataFrame.from_records(records, columns=list(CENSUS_COLUMNS))
    frame["population"] = frame["population"].astype("Int64")
    return frame


def _spine(rows: list[tuple[int, str, int]]) -> pd.DataFrame:
    """Build a ``dwh.votes``-shaped participation frame, totals row per year included."""
    records: list[dict[str, object]] = []
    for year, state, votes in rows:
        records.append(
            {
                "year": year,
                "state": state,
                "is_total": False,
                "total_electoral_votes": votes,
            }
        )
    for year in sorted({row[0] for row in rows}):
        records.append(
            {
                "year": year,
                "state": None,
                "is_total": True,
                "total_electoral_votes": 99,
            }
        )
    return pd.DataFrame(records)


# The Virginia/West Virginia scenario, which is the module's hardest case: 1860 is governed
# by the 1850 census (pre-separation, restated), 1864/1868 by the 1860 census (still
# pre-separation, but West Virginia is a separate state by then), 1872 by the 1870 census.
_SUCCESSION_SPINE = _spine(
    [
        (1860, "Virginia", 15),
        (1864, "Virginia", 0),
        (1864, "West Virginia", 5),
        (1868, "Virginia", 0),
        (1868, "West Virginia", 5),
        (1872, "Virginia", 11),
        (1872, "West Virginia", 5),
    ]
)
_SUCCESSION_CENSUS = _census(
    [
        (1850, "Virginia", 1_421_661, BASIS_AS_ENUMERATED),
        (1850, "West Virginia", 302_313, BASIS_PRESENT_DAY),
        (1860, "Virginia", VA_1860_RESTATED, BASIS_AS_ENUMERATED),
        (1860, "West Virginia", WV_1860_PUBLISHED, BASIS_PRESENT_DAY),
        (1870, "Virginia", 1_225_163, BASIS_PRESENT_DAY),
        (1870, "West Virginia", 442_014, BASIS_PRESENT_DAY),
    ]
)


class TestTheFrameContract:
    def test_the_column_order_is_pinned_to_a_literal(self) -> None:
        # Hand-written, NOT `list(ELECTION_POPULATION_COLUMNS)`. The frame is built with
        # `columns=list(ELECTION_POPULATION_COLUMNS)`, so an assert derived from the
        # constant is circular and would pass under a reorder or a mid-list insert alike.
        # #183 and #184 both inherit this tuple, and a view over it could only ever append.
        assert ELECTION_POPULATION_COLUMNS == (
            "election_year",
            "state",
            "governing_census_year",
            "total_electoral_votes",
            "population",
            "boundary_basis",
            "coverage",
            # #184 APPENDED this; it does not read `population_series` into the middle
            # beside `population` where it belongs semantically, because the tuple is now
            # the column order of a table and of the view over it.
            "population_series",
        )

    def test_the_frame_is_on_the_contract(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        assert list(frame.columns) == list(ELECTION_POPULATION_COLUMNS)
        assert_election_population_shape(frame)

    def test_population_keeps_a_nullable_integer_dtype(self) -> None:
        spine = _spine([(1848, "Texas", 4), (1848, "Ohio", 23)])
        census = _census([(1840, "Ohio", 1_519_467, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        # A float dtype here would mean the NULL became NaN and 1519467 became a float.
        assert pd.api.types.is_integer_dtype(frame["population"])
        assert frame.loc[frame.state == "Texas", "population"].isna().all()

    def test_a_wrong_column_set_is_rejected(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        with pytest.raises(CensusConformError, match="!="):
            assert_election_population_shape(frame.drop(columns=["coverage"]))

    def test_a_value_outside_a_closed_vocabulary_is_rejected(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        frame.loc[0, "boundary_basis"] = "modern-ish"
        with pytest.raises(CensusConformError, match="closed vocabulary"):
            assert_election_population_shape(frame)


class TestSpineLeftConstruction:
    def test_the_row_set_is_exactly_what_the_spine_says_participated(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        assert set(zip(frame.election_year, frame.state, strict=True)) == {
            (1860, "Virginia"),
            (1864, "Virginia"),
            (1864, "West Virginia"),
            (1868, "Virginia"),
            (1868, "West Virginia"),
            (1872, "Virginia"),
            (1872, "West Virginia"),
        }

    def test_a_census_row_for_a_non_participating_state_is_not_invented(self) -> None:
        # West Virginia has an 1850 census row, but did not exist as a state in 1860.
        # The population source must never vote on statehood.
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        assert not ((frame.election_year == 1860) & (frame.state == "West Virginia")).any()

    def test_zero_ev_states_are_kept(self) -> None:
        # Virginia holds 0 electoral votes in 1864/1868 (Reconstruction). Dropping zero-EV
        # rows would hide the whole succession case, since those are exactly the two years
        # the correction applies to.
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        zero = frame[frame.total_electoral_votes == 0]
        assert sorted(zero.election_year) == [1864, 1868]

    def test_totals_rows_are_dropped(self) -> None:
        participation = spine_participation(_SUCCESSION_SPINE)
        assert participation["state"].notna().all()
        assert len(participation) == 7

    def test_a_missing_participation_column_raises(self) -> None:
        with pytest.raises(CensusConformError, match="missing column"):
            spine_participation(_SUCCESSION_SPINE.drop(columns=["total_electoral_votes"]))

    def test_a_spine_with_no_state_rows_raises(self) -> None:
        totals_only = _SUCCESSION_SPINE[_SUCCESSION_SPINE["is_total"]]
        with pytest.raises(CensusConformError, match="no state rows"):
            spine_participation(totals_only)


class TestGoverningCensusAttachment:
    def test_each_election_takes_its_governing_census_figure(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE).set_index(
            ["election_year", "state"]
        )
        assert frame.loc[(1860, "Virginia"), "governing_census_year"] == 1850
        assert frame.loc[(1864, "Virginia"), "governing_census_year"] == 1860
        assert frame.loc[(1868, "Virginia"), "governing_census_year"] == 1860
        assert frame.loc[(1872, "Virginia"), "governing_census_year"] == 1870

    def test_a_second_series_would_not_fan_out_the_join(self) -> None:
        # `series` exists so a second series can arrive as data (D059). An unnarrowed merge
        # would then duplicate every election row silently.
        census = _SUCCESSION_CENSUS.copy()
        other = census.copy()
        other["series"] = "apportionment"
        both = pd.concat([census, other], ignore_index=True)
        assert len(build_election_population(both, _SUCCESSION_SPINE)) == 7

    def test_a_duplicate_census_cell_raises_rather_than_being_picked_from(self) -> None:
        doubled = pd.concat(
            [_SUCCESSION_CENSUS, _SUCCESSION_CENSUS.head(1)], ignore_index=True
        )
        with pytest.raises(CensusConformError, match="duplicate"):
            build_election_population(doubled, _SUCCESSION_SPINE)


class TestBoundarySuccession:
    """The 1864/1868 Virginia case — a restatement correct for one era, wrong for the next."""

    def test_the_catalog_holds_the_one_known_succession(self) -> None:
        assert len(BOUNDARY_SUCCESSIONS) == 1
        (succession,) = BOUNDARY_SUCCESSIONS
        assert succession.predecessor == "Virginia"
        assert succession.successor == "West Virginia"
        assert succession.effective_year == 1863
        assert succession.published_population == {1860: VA_1860_PUBLISHED}
        assert succession.citation

    def test_the_pinned_figure_is_an_independent_literal_not_a_recomputation(self) -> None:
        # The whole point of the pin: it is stated, so it can CHECK the census
        # correction's arithmetic instead of inheriting it.
        (succession,) = BOUNDARY_SUCCESSIONS
        assert succession.published_population[1860] == 1_219_630
        assert VA_1860_RESTATED == 1_596_318

    def test_post_separation_elections_take_the_published_figure(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE).set_index(
            ["election_year", "state"]
        )
        for year in (1864, 1868):
            assert frame.loc[(year, "Virginia"), "population"] == VA_1860_PUBLISHED
            assert frame.loc[(year, "Virginia"), "boundary_basis"] == BOUNDARY_AT_ELECTION

    def test_pre_separation_elections_keep_the_restated_figure(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE).set_index(
            ["election_year", "state"]
        )
        # 1860 is governed by the 1850 census and West Virginia does not yet exist, so the
        # restated figure IS the as-at-election one.
        assert frame.loc[(1860, "Virginia"), "population"] == 1_421_661
        assert frame.loc[(1860, "Virginia"), "boundary_basis"] == BOUNDARY_AT_ELECTION

    def test_a_post_separation_census_needs_no_correction(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE).set_index(
            ["election_year", "state"]
        )
        assert frame.loc[(1872, "Virginia"), "population"] == 1_225_163
        assert frame.loc[(1872, "Virginia"), "boundary_basis"] == BOUNDARY_PRESENT_DAY

    def test_the_successors_own_rows_are_untouched(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE).set_index(
            ["election_year", "state"]
        )
        assert frame.loc[(1864, "West Virginia"), "population"] == WV_1860_PUBLISHED

    def test_the_corrector_writes_the_label_itself(self) -> None:
        """Survivor 2 (#182 Class B): deleting the corrector's `boundary_basis` write survived.

        Every assertion that mentions the label was satisfied by a **different, upstream**
        mechanism: `build_election_population` already sets `at_election` for any row whose
        census basis is `as_enumerated`, and Virginia's 1860 row *is* the restated one. So on
        every input the suite supplied, a corrector that labels and one that does not are
        indistinguishable — the outcome is reached either way.

        It bites for real the moment a predecessor's census row is **not** already
        `as_enumerated` — a restatement #208 relabels, or a source that publishes
        as-enumerated without this repo restating. Then a corrected at-election figure would
        ship stamped `present_day`, the exact mislabel `BOUNDARY_AT_ELECTION` exists to
        prevent.

        Driving `apply_boundary_successions` directly is what isolates the two writers; going
        through the builder would re-introduce the upstream one.
        """
        frame = pd.DataFrame(
            [
                {
                    "election_year": 1864,
                    "state": "Virginia",
                    "governing_census_year": 1860,
                    "total_electoral_votes": 0,
                    "population": VA_1860_RESTATED,
                    # The point of the test: NOT already at_election.
                    "boundary_basis": BOUNDARY_PRESENT_DAY,
                },
                {
                    "election_year": 1864,
                    "state": "West Virginia",
                    "governing_census_year": 1860,
                    "total_electoral_votes": 5,
                    "population": WV_1860_PUBLISHED,
                    "boundary_basis": BOUNDARY_PRESENT_DAY,
                },
            ]
        )
        corrected = apply_boundary_successions(frame).set_index(
            ["election_year", "state"]
        )
        assert corrected.loc[(1864, "Virginia"), "population"] == VA_1860_PUBLISHED
        assert (
            corrected.loc[(1864, "Virginia"), "boundary_basis"] == BOUNDARY_AT_ELECTION
        )
        # The successor is untouched in both value and label.
        assert (
            corrected.loc[(1864, "West Virginia"), "boundary_basis"]
            == BOUNDARY_PRESENT_DAY
        )

    def test_drift_between_the_pin_and_the_census_correction_raises(self) -> None:
        # If `apply_virginia_boundary_correction` ever computes something else (#208 is the
        # story that might), this must fail rather than silently shipping one of the two.
        drifted = (
            BoundarySuccession(
                predecessor="Virginia",
                successor="West Virginia",
                effective_year=1863,
                published_population={1860: VA_1860_PUBLISHED + 1},
                citation="x",
            ),
        )
        with pytest.raises(CensusConformError, match="disagree; one of them has drifted"):
            build_election_population(
                _SUCCESSION_CENSUS, _SUCCESSION_SPINE, successions=drifted
            )

    def test_a_null_predecessor_cell_raises_rather_than_filling_from_the_pin(
        self,
    ) -> None:
        # The pin is only written where it can be CHECKED (#182 review, CR-F3/GE-F5).
        # Filling a NULL from the literal would put 1,219,630 in the frame with
        # `coverage == 'covered'` while the drift assert that validates it never ran --
        # a plausible number with its own guard bypassed, which is the one thing this
        # module claims never to do.
        census = _SUCCESSION_CENSUS.copy()
        va_1860 = (census.census_year == 1860) & (census.state == "Virginia")
        census.loc[va_1860, "population"] = pd.NA
        with pytest.raises(CensusConformError, match="cannot be verified"):
            build_election_population(census, _SUCCESSION_SPINE)

    def test_a_missing_successor_row_raises_for_the_same_reason(self) -> None:
        # Same hazard reached the other way: with no West Virginia row the drift check has
        # nothing to compare against, so the pin must not be applied.
        spine = _spine([(1864, "Virginia", 0)])
        with pytest.raises(CensusConformError, match="cannot be verified"):
            build_election_population(_SUCCESSION_CENSUS, spine)

    def test_a_succession_with_no_pinned_figure_raises(self) -> None:
        unpinned = (
            BoundarySuccession("Virginia", "West Virginia", 1863, {}, "x"),
        )
        with pytest.raises(CensusConformError, match="pins no figure"):
            build_election_population(
                _SUCCESSION_CENSUS, _SUCCESSION_SPINE, successions=unpinned
            )


class TestDoubleCount:
    def test_the_corrected_frame_does_not_double_count(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        assert_no_double_count(frame)

    def test_the_uncorrected_frame_does(self) -> None:
        # The guard's reason to exist: with the succession disabled, Virginia 1864 carries
        # the restated figure while West Virginia is separately present, so West Virginia's
        # 376,688 people are counted twice. This is the input the guard must fail on.
        uncorrected = build_election_population(
            _SUCCESSION_CENSUS, _SUCCESSION_SPINE, successions=()
        )
        with pytest.raises(CensusConformError, match="counted twice"):
            assert_no_double_count(uncorrected)


class TestCoverage:
    def test_the_catalog_holds_one_exception_and_it_is_the_permanent_kind(self) -> None:
        # Was three entries in two kinds until #234. Alaska's and Hawaii's 1950 figures
        # are published in a transposed second table the parser now reads, so their
        # `present_but_unparsed` entries became false claims and were retired.
        # This is the CI-visible half of that cleanup: `assert_spine_states_covered`
        # enforces it too, but only when the corpus is present, and TestRealCorpus
        # skips without it. Re-adding either state turns this red with no corpus.
        assert len(CENSUS_COVERAGE_EXCEPTIONS) == 1
        assert {(e.election_year, e.state) for e in CENSUS_COVERAGE_EXCEPTIONS} == {
            (1848, "Texas"),
        }
        by_kind = {e.state: e.kind for e in CENSUS_COVERAGE_EXCEPTIONS}
        # Texas's figure cannot exist — the Republic was not enumerated by the US in
        # 1840 — so this one is permanent in a way the retired two never were.
        assert by_kind["Texas"] == KIND_ABSENT_FROM_SOURCE

    def test_the_present_but_unparsed_kind_survives_having_no_members(self) -> None:
        """The vocabulary outlives its last instance, deliberately (#234).

        With Alaska and Hawaii retired, no entry references KIND_PRESENT_BUT_UNPARSED,
        so nothing else in the suite would fail if a "remove the unused constant"
        cleanup deleted it — and deleting it would collapse the distinction D060 turns
        on, between a figure history never recorded and one this repo cannot yet reach.
        "No instance today" is not "the concept does not exist".
        """
        assert KIND_PRESENT_BUT_UNPARSED in EXCEPTION_KINDS
        assert KIND_ABSENT_FROM_SOURCE in EXCEPTION_KINDS
        # And the VALUES, not just the names. With no member left, nothing else in the
        # suite reaches these strings -- yet they are what `docs/corrections.md`'s Kind
        # column prints and what `assert_spine_states_covered` interpolates into its
        # stale-exception message, so a rename would desync both in silence (#234 review).
        assert KIND_PRESENT_BUT_UNPARSED == "present_but_unparsed"
        assert KIND_ABSENT_FROM_SOURCE == "absent_from_source"

    def test_every_exception_has_a_known_kind_and_a_reason(self) -> None:
        for exception in CENSUS_COVERAGE_EXCEPTIONS:
            assert exception.kind in EXCEPTION_KINDS
            assert exception.reason.strip()

    def test_a_covered_state_reads_covered(self) -> None:
        spine = _spine([(1848, "Ohio", 23)])
        census = _census([(1840, "Ohio", 1_519_467, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        assert frame.loc[0, "coverage"] == COVERAGE_COVERED

    def test_a_declared_gap_is_a_null_not_a_zero(self) -> None:
        spine = _spine([(1848, "Texas", 4)])
        census = _census([(1850, "Texas", 212_592, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        assert frame.loc[0, "coverage"] == COVERAGE_NO_GOVERNING_FIGURE
        assert pd.isna(frame.loc[0, "population"])
        assert_spine_states_covered(frame)

    def test_an_undeclared_gap_raises(self) -> None:
        spine = _spine([(1848, "Ohio", 23)])
        frame = build_election_population(_census([]), spine)
        with pytest.raises(CensusConformError, match="not declared"):
            assert_spine_states_covered(frame)

    def test_a_stale_exception_raises(self) -> None:
        # The direction with teeth: a catalog entry claiming the source cannot supply a
        # figure, for a cell that is in fact covered, is a false published claim and
        # nothing else would notice it.
        spine = _spine([(1848, "Ohio", 23)])
        census = _census([(1840, "Ohio", 1_519_467, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        stale = (
            CoverageException(1848, "Ohio", KIND_ABSENT_FROM_SOURCE, "not actually true"),
        )
        with pytest.raises(CensusConformError, match="no longer missing"):
            assert_spine_states_covered(frame, exceptions=stale)

    def test_a_narrowed_warehouse_does_not_read_as_a_stale_catalog(self) -> None:
        # The reciprocal check is scoped to years present in the frame, so a spine that
        # simply does not carry 1848 must not make the Texas entry look stale.
        spine = _spine([(1852, "Ohio", 23)])
        census = _census([(1850, "Ohio", 1_980_329, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        assert_spine_states_covered(frame)


class TestDistrictOfColumbia:
    """AC3 names DC as a hard case; this is where that is discharged visibly.

    DC is **not** a state, holds no census-apportioned House seats, and has cast 3 electoral
    votes since the 23rd Amendment took effect for 1964. For *this* story that needs no
    correction at all — the source publishes DC's population from 1800, and the spine-left
    construction attaches it for exactly the elections DC participated in. Asserting it
    rather than reasoning about it is the point: a reviewer should not have to infer that an
    acceptance criterion was considered.

    What *is* special about DC belongs to #183: its 3 votes are not apportioned, so the
    ``seats + 2`` identity does not hold for it at all.
    """

    def test_dc_needs_no_population_correction_and_is_simply_covered(self) -> None:
        spine = _spine([(1960, "District of Columbia", 0), (1964, "District of Columbia", 3)])
        census = _census(
            [
                (1950, "District of Columbia", 802_178, BASIS_PRESENT_DAY),
                (1960, "District of Columbia", 763_956, BASIS_PRESENT_DAY),
            ]
        )
        frame = build_election_population(census, spine).set_index(
            ["election_year", "state"]
        )
        # 1964 is governed by the 1960 census, 1960 by the 1950 one -- the ordinary rule,
        # with no boundary or coverage exception anywhere near it.
        assert frame.loc[(1964, "District of Columbia"), "population"] == 763_956
        assert frame.loc[(1960, "District of Columbia"), "population"] == 802_178
        assert (
            frame.loc[(1964, "District of Columbia"), "coverage"] == COVERAGE_COVERED
        )
        assert (
            frame.loc[(1964, "District of Columbia"), "boundary_basis"]
            == BOUNDARY_PRESENT_DAY
        )

    def test_dc_is_in_no_correction_catalog(self) -> None:
        # If DC ever needs an entry, that is a finding rather than a detail -- it would mean
        # the source stopped publishing it, or the spine changed its participation.
        assert "District of Columbia" not in {
            s.predecessor for s in BOUNDARY_SUCCESSIONS
        } | {s.successor for s in BOUNDARY_SUCCESSIONS}
        assert "District of Columbia" not in {
            e.state for e in CENSUS_COVERAGE_EXCEPTIONS
        }


class TestNoInterpolation:
    def test_a_between_census_election_takes_the_governing_figure_unchanged(self) -> None:
        spine = _spine([(1836, "Ohio", 21), (1840, "Ohio", 21)])
        census = _census([(1830, "Ohio", 937_903, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        # Both elections take the 1830 figure verbatim. Nothing is averaged toward 1840.
        assert list(frame["population"]) == [937_903, 937_903]
        assert_no_interpolated_population(frame, census)

    def test_the_corrected_succession_rows_pass(self) -> None:
        # The corrected Virginia value is deliberately NOT in the census table (D059 keeps
        # `basis` out of the natural key), so a naive "must be in the table" assert would
        # fire on exactly the rows the correction fixed.
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        assert_no_interpolated_population(frame, _SUCCESSION_CENSUS)

    def test_a_synthesized_value_raises(self) -> None:
        spine = _spine([(1836, "Ohio", 21)])
        census = _census([(1830, "Ohio", 937_903, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        frame.loc[0, "population"] = 950_000
        with pytest.raises(CensusConformError, match="synthesized"):
            assert_no_interpolated_population(frame, census)

    def test_a_wrong_value_on_a_restated_cell_raises(self) -> None:
        """Survivor 3 (#182 Class B), and the sharpest of the four.

        Turning the restatement branch from a **value** check into a **key-membership** check
        survived the whole suite — i.e. any number at all on a
        `(governing_census_year, predecessor)` cell passed the D005 "never synthesized" guard,
        which is precisely the loophole its docstring says it is not.

        No test supplied the one input that separates the two implementations: a *wrong value*
        on a restated cell. The synthesized-value test perturbs an Ohio cell, which is not in
        `allowed_restatements` and so exercises only the first branch; the undeclared-restatement
        test passes `successions=()`, which empties the map so the second branch is never
        reached; and the positive test asserts an outcome both implementations reach.

        These are the rows this module hand-writes a literal into — the highest-risk cells in
        the frame — and this is the guard meant to catch a wrong one.
        """
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        target = frame.index[
            (frame.election_year == 1864) & (frame.state == "Virginia")
        ][0]
        # Neither the pinned published figure nor the table's restated one.
        assert VA_1860_PUBLISHED != 1_300_000 != VA_1860_RESTATED
        frame.loc[target, "population"] = 1_300_000
        with pytest.raises(CensusConformError, match="synthesized"):
            assert_no_interpolated_population(frame, _SUCCESSION_CENSUS)

    def test_an_undeclared_restatement_raises(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        with pytest.raises(CensusConformError, match="synthesized"):
            assert_no_interpolated_population(
                frame, _SUCCESSION_CENSUS, successions=()
            )


def _seam_missing_the_coverage_guard(
    census: pd.DataFrame, ec_participation: pd.DataFrame
) -> None:
    """A copy of ``assert_conforms_to_spine``'s body with one guard call removed.

    Stands in for the state of the tree if that line were deleted from the real seam. Its
    only job is to be a seam with a call missing, so drift from the real body is harmless —
    what matters is that it calls three of the four.
    """
    frame = conform_module.build_election_population(census, ec_participation)
    conform_module.assert_election_population_shape(frame)
    # assert_spine_states_covered deliberately omitted
    conform_module.assert_no_double_count(frame)
    conform_module.assert_no_interpolated_population(frame, census)


class TestTheSeam:
    """`assert_conforms_to_spine` is the only thing the load path calls, so its
    *composition* is a contract — and nothing pinned it before (#182 review, GE-F1).

    Its own docstring says the reason it exists is that "the load path gets all four
    checks or none — an individually-wired subset is how one of them quietly stops
    running". Deleting any one of the four from its body used to leave the whole suite
    green: the unit tests call the four guards directly, the pipeline tests stub the seam,
    and the integration test only ever hands it good data. That is the
    outcome-versus-mechanism failure exactly — a working seam and a crippled one produce
    an identical result on the only input any test gave it.
    """

    #: The guard names `assert_conforms_to_spine` must invoke, in the order it invokes
    #: them. Hand-written, so removing a call from the seam fails here rather than
    #: silently passing; deriving it from the function's source would be circular.
    EXPECTED_CALLS = (
        "assert_election_population_shape",
        "assert_spine_states_covered",
        "assert_no_double_count",
        "assert_no_interpolated_population",
    )

    @staticmethod
    def _record_guard_calls(
        monkeypatch: pytest.MonkeyPatch,
        seam: Callable[[pd.DataFrame, pd.DataFrame], None],
    ) -> tuple[str, ...]:
        """Run ``seam`` with all four guards replaced by recorders; return the call order.

        The seam resolves each guard as a module global at call time, so patching
        ``conform_module`` observes exactly the calls its body makes. ``monkeypatch.setattr``
        also raises if a name is absent, so a guard moving out of this namespace fails
        loudly at collection rather than quietly reducing what is recorded.
        """
        called: list[str] = []
        for name in TestTheSeam.EXPECTED_CALLS:

            def record(*_args: object, _name: str = name, **_kwargs: object) -> None:
                called.append(_name)

            monkeypatch.setattr(conform_module, name, record)
        seam(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        return tuple(called)

    @classmethod
    def _assert_ran_every_guard(cls, calls: tuple[str, ...]) -> None:
        """The single assertion both tests below exercise.

        Shared deliberately: the non-vacuity test's whole job is to show that **this**
        assertion fails for a seam missing a call, and it can only show that if it runs the
        same one.
        """
        assert calls == cls.EXPECTED_CALLS

    def test_the_seam_runs_every_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The test that closes the hole: it observes *which* guards run.

        A negative-data test can only reach the guards that can fail on data, and two of
        the four cannot by construction (the seam docstring says which and why). So the
        only way to catch a deleted call is to record the calls.
        """
        self._assert_ran_every_guard(
            self._record_guard_calls(monkeypatch, assert_conforms_to_spine)
        )

    def test_the_same_assertion_fails_for_a_seam_missing_a_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuity, done properly this time (#182 review, D-2).

        The first version of this test compared a 3-tuple against a 4-tuple and was
        therefore unequal **by arity** — it passed even with all four guard calls deleted
        from the seam, so it could not tell a seam running three guards from one running
        none. A test that advertises itself as a non-vacuity proof while proving nothing is
        the exact defect class this story is about, so it is worth replacing rather than
        deleting.

        The falsifiable form runs :meth:`_assert_ran_every_guard` — the *same* assertion the
        test above relies on — against a seam known to be missing a call, and requires it to
        raise.
        """
        calls = self._record_guard_calls(monkeypatch, _seam_missing_the_coverage_guard)
        with pytest.raises(AssertionError):
            self._assert_ran_every_guard(calls)

    def test_the_returning_seam_runs_every_guard_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#184 made ``build_and_validate_election_population`` the load path's seam.

        The pipeline calls **that** function now, so pinning only the discarding wrapper
        would leave the composition that actually runs before a write unpinned — the
        precise hole this class was written to close, reopened one refactor later.
        """
        self._assert_ran_every_guard(
            self._record_guard_calls(
                monkeypatch, conform_module.build_and_validate_election_population
            )
        )

    def test_the_wrapper_delegates_rather_than_repeating_the_guard_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two seams must not become two guard lists.

        If ``assert_conforms_to_spine`` kept its own copy of the four calls, a guard
        added to one would be missing from the other and both tests above would still
        pass. This pins the delegation itself.
        """
        called: list[str] = []

        def record(*_args: object, **_kwargs: object) -> pd.DataFrame:
            called.append("delegated")
            return pd.DataFrame()

        monkeypatch.setattr(
            conform_module, "build_and_validate_election_population", record
        )
        assert_conforms_to_spine(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        assert called == ["delegated"]

    def test_the_returning_seam_hands_back_the_frame_it_validated(self) -> None:
        """The frame the guards ran over is the frame that gets written (#184).

        Returning a *fresh* build would satisfy every other test here while
        reintroducing the two-derivations gap: the guards would certify one object and
        the loader would write another built from the same inputs.
        """
        frame = conform_module.build_and_validate_election_population(
            _SUCCESSION_CENSUS, _SUCCESSION_SPINE
        )
        assert list(frame.columns) == list(ELECTION_POPULATION_COLUMNS)
        assert not frame.empty

    def test_the_seam_raises_on_a_corpus_short_a_state(self) -> None:
        """The one guard that fires on a real corpus defect, reached through the seam.

        An undeclared gap is what a corpus that lost a state actually looks like, and this
        is the assertion the pipeline's "fails here with nothing written" claim rests on.
        """
        spine = _spine([(1848, "Ohio", 23)])
        with pytest.raises(CensusConformError, match="not declared"):
            assert_conforms_to_spine(_census([]), spine)

    def test_the_seam_passes_on_good_data(self) -> None:
        assert_conforms_to_spine(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)


class TestParticipationFrameGuards:
    """The two guards added after review (#182, CR-F2 and CR-F5)."""

    def test_a_string_is_total_column_is_rejected_not_coerced(self) -> None:
        # `read_ec_participation` deliberately passes a non-int `is_total` through so its
        # consumer can reject it. A blanket .astype(bool) maps 't' AND 'f' to True,
        # marking every row a totals row, dropping the whole spine, and then reporting
        # "the spine must be loaded" on a fully-loaded spine.
        frame = _SUCCESSION_SPINE.copy()
        frame["is_total"] = frame["is_total"].map({True: "t", False: "f"})
        with pytest.raises(CensusConformError, match="astype\\(bool\\) would misread"):
            spine_participation(frame)

    def test_a_bool_is_total_column_is_accepted(self) -> None:
        assert len(spine_participation(_SUCCESSION_SPINE)) == 7

    def test_an_int_is_total_column_is_accepted(self) -> None:
        # psycopg2 yields real bools, but `read_ec_participation` also tolerates 0/1 ints.
        frame = _SUCCESSION_SPINE.copy()
        frame["is_total"] = frame["is_total"].astype(int)
        assert len(spine_participation(frame)) == 7

    def test_an_empty_spine_reports_the_spine_not_the_dtype(self) -> None:
        """#182 review, D-1 — the guard must not misfire on the case it looks like.

        A zero-row frame has ``object`` dtype for every column, because nothing was
        inferred from no rows. A dtype-based check therefore raised a complaint about types
        on a genuinely unloaded spine, making the truthful message unreachable — the mirror
        image of the defect the guard was added to prevent.
        """
        empty = pd.DataFrame(
            {
                "year": pd.Series(dtype=object),
                "state": pd.Series(dtype=object),
                "is_total": pd.Series(dtype=object),
                "total_electoral_votes": pd.Series(dtype=object),
            }
        )
        with pytest.raises(CensusConformError, match="spine must be loaded"):
            spine_participation(empty)

    def test_an_object_column_of_real_bools_is_accepted(self) -> None:
        # The other direction a dtype check gets wrong: psycopg2 can hand back an object
        # column of genuine bools, which UCSB accepts for exactly this reason. Rejecting it
        # would refuse a perfectly good spine.
        frame = _SUCCESSION_SPINE.copy()
        frame["is_total"] = frame["is_total"].astype(object)
        assert frame["is_total"].dtype == object
        assert len(spine_participation(frame)) == 7

    def test_a_null_is_total_is_rejected(self) -> None:
        # A null cannot be excluded as a totals row, and a totals row carries a NULL state,
        # which would enter the frame as a phantom jurisdiction.
        # Cast first: a bool-dtype column refuses a None outright, so a null only ever
        # arrives in a column that can hold one.
        frame = _SUCCESSION_SPINE.copy()
        frame["is_total"] = frame["is_total"].astype(object)
        frame.loc[0, "is_total"] = None
        with pytest.raises(CensusConformError, match="null value"):
            spine_participation(frame)

    @pytest.mark.parametrize(
        ("dtype", "null"),
        [
            ("object", None),
            ("boolean", pd.NA),
            ("Int64", pd.NA),
            ("float64", float("nan")),
        ],
        ids=["object", "boolean", "Int64", "float64"],
    )
    def test_a_null_is_rejected_in_every_dtype_that_can_hold_one(
        self, dtype: str, null: object
    ) -> None:
        """#182 review, F-1 — the null check must not be reachable only for some dtypes.

        The first version of this guard ordered the **integer** early-return above the null
        check, so a nullable ``Int64`` carrying ``pd.NA`` slipped past it and died at
        ``.astype(bool)`` with a bare ``ValueError`` — the nullable-column failure the null
        branch exists to report. The comment above this test also claimed object and
        nullable-boolean were the only columns a null could arrive in, which was true of the
        live path and false for an injected frame — and an injected frame is exactly how
        #184 will call this function.

        Parameterised rather than written for ``Int64`` alone, because the defect was an
        *ordering* one: any future early-return placed above the null check reintroduces it
        for whichever dtype that branch covers.
        """
        # The null sentinel is per-dtype: float64 holds `nan`, not `pd.NA`, and object
        # holds `None`. Hard-coding one makes the *test* fail to construct rather than the
        # guard fail to fire, which is a different thing and would have hidden this.
        frame = _SUCCESSION_SPINE.copy()
        frame["is_total"] = pd.Series(
            [null] + [False] * (len(frame) - 1), dtype=dtype, index=frame.index
        )
        with pytest.raises(CensusConformError, match="null value"):
            spine_participation(frame)

    def test_disagreeing_allotments_for_one_pair_raise(self) -> None:
        # The frame is per (year, state, candidate); de-duplication keeps one row, so
        # disagreeing candidate rows would silently hand #183's reconciliation an
        # arbitrary appointed allotment.
        frame = pd.concat(
            [
                _SUCCESSION_SPINE,
                pd.DataFrame(
                    [{
                        "year": 1872,
                        "state": "Virginia",
                        "is_total": False,
                        "total_electoral_votes": 99,
                    }]
                ),
            ],
            ignore_index=True,
        )
        with pytest.raises(CensusConformError, match="more than one"):
            spine_participation(frame)

    def test_agreeing_duplicate_candidate_rows_are_fine(self) -> None:
        frame = pd.concat(
            [_SUCCESSION_SPINE, _SUCCESSION_SPINE], ignore_index=True
        )
        assert len(spine_participation(frame)) == 7


class TestTheShapeGuardNegatives:
    """The two `assert_election_population_shape` branches that had no negative test."""

    def test_a_null_in_a_required_column_is_rejected(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        frame.loc[0, "coverage"] = None
        with pytest.raises(CensusConformError, match="required non-null"):
            assert_election_population_shape(frame)

    def test_a_float_population_dtype_is_rejected(self) -> None:
        # A float dtype is what happens if the nullable-integer discipline lapses: the
        # NULLs become NaN and the counts become floats, so "no figure" and 0 stop being
        # distinguishable on the way to the database.
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        frame["population"] = frame["population"].astype("float64")
        with pytest.raises(CensusConformError, match="nullable integer dtype"):
            assert_election_population_shape(frame)


class TestRealCorpus:
    """The only check that proves the coverage-exception catalog is COMPLETE.

    Needs all 51 published sheets, so it reads the snapshotted corpus and **skips when
    ``USVOTE_CENSUS_CORPUS_DIR`` is unset**. CI therefore does not prove the catalog; running
    this locally is a merge precondition, exactly as ``TestRealCorpus`` in
    ``test_ucsb_parse.py`` is for the UCSB parser.
    """

    @staticmethod
    def _corpus_census() -> pd.DataFrame:
        corpus = os.environ.get("USVOTE_CENSUS_CORPUS_DIR")
        if not corpus:
            pytest.skip("USVOTE_CENSUS_CORPUS_DIR is unset")
        tabs = Path(corpus) / "tabs15-65.xlsx"
        if not tabs.is_file():
            pytest.skip(f"{tabs} is not present in the corpus")

        from usvote.census.parse import (
            parse_population_change,
            parse_resident_1790_1990,
        )
        from usvote.census.transform import transform_census

        spine = ec_participation_frame()
        return transform_census(
            {
                "resident_1790_1990": parse_resident_1790_1990(
                    tabs.read_bytes(), source_id="resident_1790_1990"
                ),
                "resident_1910_2020": parse_population_change(
                    CENSUS_POPCHANGE_XLSX.read_bytes(),
                    source_id="resident_1910_2020",
                ),
            },
            spine,
        )

    def test_the_declared_exceptions_are_exactly_the_real_gaps(self) -> None:
        census = self._corpus_census()
        spine = ec_participation_frame()
        frame = build_election_population(census, spine)
        gaps = {
            (int(row.election_year), str(row.state))
            for row in frame.itertuples()
            if row.coverage == COVERAGE_NO_GOVERNING_FIGURE
        }
        # ONE gap across all 2,204 participating pairs. It was three until #234 taught
        # the parser to read Alaska's and Hawaii's transposed second table; those two
        # were `present_but_unparsed` — the figure was published and unreachable — and
        # reaching it is what retired them. Texas 1848 is `absent_from_source`: the
        # Republic of Texas was not enumerated by the United States in 1840, so no
        # parser change can ever produce that figure and this entry is permanent.
        assert gaps == {(1848, "Texas")}
        # Both directions at once: no undeclared gap, and no stale entry.
        assert_spine_states_covered(frame)

    def test_every_guard_passes_over_the_whole_series(self) -> None:
        census = self._corpus_census()
        spine = ec_participation_frame()
        frame = build_election_population(census, spine)
        assert_election_population_shape(frame)
        assert_no_double_count(frame)
        assert_no_interpolated_population(frame, census)
        assert len(frame) == 2204

    def test_dc_is_covered_for_every_election_it_participated_in(self) -> None:
        """AC3, over the real series rather than a two-row fixture."""
        census = self._corpus_census()
        frame = build_election_population(census, ec_participation_frame())
        dc = frame[frame.state == "District of Columbia"]
        assert not dc.empty, "DC is absent from the spine — the roster fixture is wrong"
        assert (dc.coverage == COVERAGE_COVERED).all()
        assert dc.population.notna().all()
        # DC enters with the 23rd Amendment, so its first election is 1964.
        assert int(dc.election_year.min()) == 1964

    def test_only_virginia_carries_an_at_election_basis(self) -> None:
        # Twelve rows: Virginia's elections 1824-1868. Everything else is `present_day`,
        # which is the honest default until #208 sweeps the other forty-nine states.
        census = self._corpus_census()
        frame = build_election_population(census, ec_participation_frame())
        at_election = frame[frame.boundary_basis == BOUNDARY_AT_ELECTION]
        assert set(at_election.state) == {"Virginia"}
        assert sorted(at_election.election_year) == list(range(1824, 1872, 4))
        assert len(at_election) == 12


class TestThePopulationSeriesLabel:
    """AC-2: the view must say which population series its denominator came from.

    The label is carried as a **column on the row** rather than asserted as a literal by
    the view, so it cannot keep saying ``resident`` on the day a second series is
    admitted as data — which D059 built the census ``series`` column to allow.
    """

    def test_a_row_with_a_population_carries_the_series_it_came_from(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        populated = frame.loc[frame["population"].notna()]
        assert not populated.empty
        assert set(populated["population_series"]) == {SERIES_RESIDENT}

    def test_a_row_with_no_population_carries_no_series(self) -> None:
        # Writing 'resident' here would assert the provenance of a value that does not
        # exist -- the D005 discipline applied to a label instead of to a number.
        spine = _spine([(1848, "Texas", 4), (1848, "Ohio", 23)])
        census = _census([(1840, "Ohio", 1_519_467, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        texas = frame.loc[frame["state"] == "Texas"]
        assert texas["population"].isna().all()
        assert texas["population_series"].isna().all()

    def test_a_figure_whose_label_went_missing_is_refused(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        frame.loc[frame["population"].notna(), "population_series"] = None
        with pytest.raises(CensusConformError, match="without a series label"):
            assert_election_population_shape(frame)

    def test_a_label_with_no_figure_behind_it_is_refused(self) -> None:
        spine = _spine([(1848, "Texas", 4), (1848, "Ohio", 23)])
        census = _census([(1840, "Ohio", 1_519_467, BASIS_PRESENT_DAY)])
        frame = build_election_population(census, spine)
        frame.loc[frame["population"].isna(), "population_series"] = SERIES_RESIDENT
        with pytest.raises(CensusConformError, match="without a population"):
            assert_election_population_shape(frame)

    def test_a_series_outside_the_closed_vocabulary_is_refused(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        frame.loc[0, "population_series"] = "apportionment"
        with pytest.raises(CensusConformError, match="closed vocabulary"):
            assert_election_population_shape(frame)

    def test_only_the_resident_series_reaches_the_election_grain(self) -> None:
        """The narrowing is in ``_resident_population``, and this is what it buys.

        Without it a second series would fan every election row out silently; with it,
        an apportionment row in the census frame simply does not appear here.
        """
        census = _census([(1840, "Ohio", 1_519_467, BASIS_PRESENT_DAY)])
        other = census.copy()
        other["series"] = "apportionment"
        other["population"] = pd.array([999_999], dtype="Int64")
        frame = build_election_population(
            pd.concat([census, other], ignore_index=True),
            _spine([(1848, "Ohio", 23)]),
        )
        assert len(frame) == 1
        assert int(frame.loc[0, "population"]) == 1_519_467
        assert frame.loc[0, "population_series"] == SERIES_RESIDENT
