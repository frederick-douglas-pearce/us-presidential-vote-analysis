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
from pathlib import Path

import pandas as pd
import pytest

from tests._helpers import CENSUS_POPCHANGE_XLSX, ec_participation_frame
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
    def test_the_catalog_holds_three_exceptions_in_two_kinds(self) -> None:
        assert len(CENSUS_COVERAGE_EXCEPTIONS) == 3
        assert {(e.election_year, e.state) for e in CENSUS_COVERAGE_EXCEPTIONS} == {
            (1848, "Texas"),
            (1960, "Alaska"),
            (1960, "Hawaii"),
        }
        by_kind = {e.state: e.kind for e in CENSUS_COVERAGE_EXCEPTIONS}
        # Texas's figure cannot exist; Alaska's and Hawaii's do and are merely unread.
        # Collapsing the two kinds would make one of the catalog rows a false claim.
        assert by_kind["Texas"] == KIND_ABSENT_FROM_SOURCE
        assert by_kind["Alaska"] == KIND_PRESENT_BUT_UNPARSED
        assert by_kind["Hawaii"] == KIND_PRESENT_BUT_UNPARSED

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

    def test_an_undeclared_restatement_raises(self) -> None:
        frame = build_election_population(_SUCCESSION_CENSUS, _SUCCESSION_SPINE)
        with pytest.raises(CensusConformError, match="synthesized"):
            assert_no_interpolated_population(
                frame, _SUCCESSION_CENSUS, successions=()
            )


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
        assert gaps == {(1848, "Texas"), (1960, "Alaska"), (1960, "Hawaii")}
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
