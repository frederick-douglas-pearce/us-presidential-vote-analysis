"""Unit tests for :mod:`usvote.census.transform` (#181).

This is where every policy decision the parsers deliberately deferred gets checked: the
stitch, the scope rule, the jurisdiction guard, the Virginia boundary correction and the
D005 null discipline. The EC spine arrives as an injected frame, so these run offline.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import (
    CENSUS_POPCHANGE_XLSX,
    CENSUS_TABS_TRIMMED_XLSX,
    ec_participation_frame,
)
from usvote.census import transform
from usvote.census.parse import PopulationRow, parse_population_change
from usvote.census.schema import (
    BASIS_AS_ENUMERATED,
    BASIS_PRESENT_DAY,
    CENSUS_COLUMNS,
    SERIES_RESIDENT,
    SOURCE_CENSUS_BUREAU,
)
from usvote.census.transform import (
    ALEXANDRIA_RETROCESSION,
    NON_STATE_AREAS,
    SOURCE_SPANS,
    VERIFIED_BY_PUBLISHED_COMPONENTS,
    VERIFIED_BY_PUBLISHED_TOTAL,
    VIRGINIA_CORRECTION_CENSUSES,
    VIRGINIA_VERIFICATION,
    CensusTransformError,
    apply_alexandria_retrocession,
    apply_virginia_boundary_correction,
    assert_known_jurisdictions,
    assert_stitch_is_unambiguous,
    known_states,
    transform_census,
)

_SPINE = ec_participation_frame()


def _census_record(
    year: int, state: str, pop: int | None, basis: str = BASIS_PRESENT_DAY
) -> dict[str, object]:
    return {
        "source": SOURCE_CENSUS_BUREAU,
        "census_year": year,
        "state": state,
        "series": SERIES_RESIDENT,
        "basis": basis,
        "population": pop,
        "vintage": "v",
        "source_file": "f",
        "redistributable": True,
        "note": None,
    }


def _row(year: int, area: str, pop: int | None, source: str) -> PopulationRow:
    return PopulationRow(census_year=year, area=area, population=pop, source_id=source)


def _minimal_rows(
    *, old: list[PopulationRow] | None = None, new: list[PopulationRow] | None = None
) -> dict[str, list[PopulationRow]]:
    """The smallest input that satisfies the stitch's "all sources present" rule."""
    return {
        "resident_1790_1990": old
        if old is not None
        else [_row(1850, "Connecticut", 370_792, "resident_1790_1990")],
        "resident_1910_2020": new
        if new is not None
        else [_row(2020, "Connecticut", 3_605_944, "resident_1910_2020")],
    }


class TestStitch:
    def test_the_shipped_stitch_covers_every_census_exactly_once(self) -> None:
        assert_stitch_is_unambiguous()  # must not raise

    def test_an_overlapping_stitch_is_refused(self) -> None:
        # The acceptance criterion is that each census comes from exactly one file. An
        # overlap introduced by widening a span would otherwise surface much later as a
        # duplicate-key error with no clue which source won.
        with pytest.raises(CensusTransformError, match="claimed by both"):
            assert_stitch_is_unambiguous(
                {"a": range(1790, 2000, 10), "b": range(1990, 2030, 10)}
            )

    def test_a_stitch_with_a_hole_in_it_is_refused(self) -> None:
        with pytest.raises(CensusTransformError, match="uncovered"):
            assert_stitch_is_unambiguous(
                {"a": range(1790, 1900, 10), "b": range(1910, 1920, 10)}
            )

    def test_each_census_is_taken_from_the_file_the_stitch_assigns(self) -> None:
        """The overlap must be resolved by the rule, not by iteration order.

        Both files publish 1910-1990. Here each supplies a *different* value for 1950,
        so the test can say which one won rather than merely that one did — an
        order-dependent implementation passes a "no duplicates" check happily.
        """
        rows = _minimal_rows(
            old=[_row(1950, "Connecticut", 2_007_280, "resident_1790_1990")],
            new=[
                _row(1950, "Connecticut", 999_999, "resident_1910_2020"),
                _row(2020, "Connecticut", 3_605_944, "resident_1910_2020"),
            ],
        )
        frame = transform_census(rows, _SPINE)
        row_1950 = frame[frame["census_year"] == 1950].iloc[0]
        assert row_1950["population"] == 2_007_280
        assert row_1950["source_file"] == "tabs15-65.xlsx"

    def test_the_two_spans_meet_at_the_stitch_year_without_a_gap(self) -> None:
        old, new = (
            SOURCE_SPANS["resident_1790_1990"],
            SOURCE_SPANS["resident_1910_2020"],
        )
        assert max(old) == 1990
        assert min(new) == 2000


class TestJurisdictionScope:
    def test_a_declared_aggregate_is_excluded_rather_than_raising(self) -> None:
        # Applied literally, "raise on anything that is not one of the 51" rejects a
        # correct file: the population-change table publishes regions, a national total
        # and Puerto Rico. This is the regression test for that.
        assert_known_jurisdictions(
            ["Connecticut", "United States1", "Puerto Rico", "South Region"],
            recognized={"Connecticut"},
        )

    def test_an_unrecognized_area_raises_and_names_itself(self) -> None:
        with pytest.raises(CensusTransformError, match="Atlantis"):
            assert_known_jurisdictions(
                ["Connecticut", "Atlantis"], recognized={"Connecticut"}
            )

    def test_both_spellings_of_the_national_row_are_excluded(self) -> None:
        """The trap this constant exists for.

        The table prints the national row as ``United States1`` in its first block and
        ``United States`` in the others, so an exclusion written as the obvious
        ``== "United States"`` passes every test that only exercises the second
        spelling and then raises on a correct file.
        """
        assert "United States" in NON_STATE_AREAS
        assert "United States1" in NON_STATE_AREAS

    def test_the_real_published_file_passes_the_jurisdiction_guard(self) -> None:
        # The end-to-end version of the two tests above, against the bytes the Bureau
        # actually publishes rather than a hand-built list.
        rows = parse_population_change(
            CENSUS_POPCHANGE_XLSX.read_bytes(), source_id="resident_1910_2020"
        )
        assert_known_jurisdictions(
            [row.area for row in rows], recognized=known_states(_SPINE)
        )

    def test_no_aggregate_survives_into_the_frame(self) -> None:
        rows = _minimal_rows(
            new=[
                _row(2020, "Connecticut", 3_605_944, "resident_1910_2020"),
                _row(2020, "Puerto Rico", 3_285_874, "resident_1910_2020"),
                _row(2020, "United States1", 331_449_281, "resident_1910_2020"),
            ]
        )
        frame = transform_census(rows, _SPINE)
        assert not set(frame["state"]) & NON_STATE_AREAS

    def test_a_backfilled_pre_participation_row_survives_the_load(self) -> None:
        """#182's input must not be deleted here.

        The source backfills states to their modern footprint's first countable census
        — West Virginia at 1790, decades before it was a state. Filtering on whether the
        EC spine gives that state electoral votes in that era is participation
        conformance, which is #182's job; doing it here would silently destroy the rows
        #182 exists to reconcile.
        """
        rows = _minimal_rows(
            old=[_row(1790, "West Virginia", 55_873, "resident_1790_1990")]
        )
        frame = transform_census(rows, _SPINE)
        assert (
            frame[(frame.state == "West Virginia") & (frame.census_year == 1790)].shape[
                0
            ]
            == 1
        )

    def test_known_states_ignores_the_totals_rows(self) -> None:
        """The `is_total` filter is exercised directly, not through `dropna()`.

        A Class B mutation pass killed the previous version of this test by deleting the
        filter entirely: the real spine's totals rows carry `state` NULL, so
        `known_states`' trailing `.dropna()` removes them whether or not the filter runs,
        and `assert "Totals" not in ...` was **vacuously true** — the string was never a
        value in that column at all.

        So the frame below gives its totals row a **non-null** state. That is not the
        shape `dwh.votes` actually stores (CLAUDE.md: `state` is "null for totals rows"),
        which makes the filter defence-in-depth rather than load-bearing — but a guard
        worth keeping is a guard worth exercising, and this is the only input that tells
        the two implementations apart.
        """
        spine = pd.DataFrame(
            [
                {
                    "year": 2020,
                    "state": "Virginia",
                    "is_total": False,
                    "total_electoral_votes": 13,
                },
                {
                    "year": 2020,
                    "state": "Totals",
                    "is_total": True,
                    "total_electoral_votes": 538,
                },
            ]
        )
        recognized = known_states(spine)
        assert recognized == {"Virginia"}
        assert "Totals" not in recognized

    def test_known_states_still_drops_a_null_state_totals_row(self) -> None:
        # The shape the spine really stores, kept alongside the one above so neither
        # mechanism can be removed silently: here `dropna()` is what does the work.
        spine = pd.DataFrame(
            [
                {
                    "year": 2020,
                    "state": "Virginia",
                    "is_total": False,
                    "total_electoral_votes": 13,
                },
                {
                    "year": 2020,
                    "state": None,
                    "is_total": True,
                    "total_electoral_votes": 538,
                },
            ]
        )
        assert known_states(spine) == {"Virginia"}


class TestVirginiaBoundaryCorrection:
    def test_the_corrected_figure_reproduces_the_enumerated_virginia(self) -> None:
        """The three censuses S1 cross-checked against a separate publication.

        This is the whole evidential basis of the correction: the file's own Virginia +
        West Virginia sum equals the separately-published enumerated Virginia exactly,
        which is why the correction needs no external source.
        """
        rows = _minimal_rows(
            old=[
                _row(1790, "Virginia", 691_737, "resident_1790_1990"),
                _row(1790, "West Virginia", 55_873, "resident_1790_1990"),
                _row(1850, "Virginia", 1_119_348, "resident_1790_1990"),
                _row(1850, "West Virginia", 302_313, "resident_1790_1990"),
                _row(1860, "Virginia", 1_219_630, "resident_1790_1990"),
                _row(1860, "West Virginia", 376_688, "resident_1790_1990"),
            ]
        )
        frame = transform_census(rows, _SPINE)
        virginia = frame[frame.state == "Virginia"].set_index("census_year")
        assert virginia.loc[1790, "population"] == 747_610
        assert virginia.loc[1850, "population"] == 1_421_661
        assert virginia.loc[1860, "population"] == 1_596_318

    def test_the_corrected_row_is_labelled_as_enumerated(self) -> None:
        # The label is what stops a corrected figure and a published one being
        # indistinguishable — the D005 problem in a new place.
        rows = _minimal_rows(
            old=[
                _row(1850, "Virginia", 1_119_348, "resident_1790_1990"),
                _row(1850, "West Virginia", 302_313, "resident_1790_1990"),
            ]
        )
        frame = transform_census(rows, _SPINE)
        assert frame.loc[frame.state == "Virginia", "basis"].iloc[0] == (
            BASIS_AS_ENUMERATED
        )
        assert frame.loc[frame.state == "West Virginia", "basis"].iloc[0] == (
            BASIS_PRESENT_DAY
        )

    def test_west_virginias_own_figure_is_left_untouched(self) -> None:
        # Zeroing or deleting it would destroy #182's input and fabricate data. It is a
        # real population for that territory; what it is not is a state at the time.
        rows = _minimal_rows(
            old=[
                _row(1850, "Virginia", 1_119_348, "resident_1790_1990"),
                _row(1850, "West Virginia", 302_313, "resident_1790_1990"),
            ]
        )
        frame = transform_census(rows, _SPINE)
        assert (
            frame.loc[frame.state == "West Virginia", "population"].iloc[0] == 302_313
        )

    def test_virginia_after_the_separation_is_not_corrected(self) -> None:
        # From 1870 the two are separate in the record and in the file alike, so adding
        # them would double-count. The window closing is as load-bearing as it opening.
        rows = _minimal_rows(
            old=[
                _row(1870, "Virginia", 1_225_163, "resident_1790_1990"),
                _row(1870, "West Virginia", 442_014, "resident_1790_1990"),
            ]
        )
        frame = transform_census(rows, _SPINE)
        virginia = frame[frame.state == "Virginia"].iloc[0]
        assert virginia["population"] == 1_225_163
        assert virginia["basis"] == BASIS_PRESENT_DAY

    def test_the_window_covers_every_census_before_the_separation(self) -> None:
        assert min(VIRGINIA_CORRECTION_CENSUSES) == 1790
        assert max(VIRGINIA_CORRECTION_CENSUSES) == 1860
        assert 1870 not in VIRGINIA_CORRECTION_CENSUSES

    def test_the_note_distinguishes_how_each_census_is_confirmed(self) -> None:
        """The correction must not imply evidence it does not have (#251, AC-8).

        1850 is confirmed against a separately-published Virginia total; 1820 is
        composed from three published components, one of them external to the file.
        A uniformly confident note would launder the second into the first.
        """
        rows = _minimal_rows(
            old=[
                _row(1820, "Virginia", 938_261, "resident_1790_1990"),
                _row(1820, "West Virginia", 136_808, "resident_1790_1990"),
                _row(1850, "Virginia", 1_119_348, "resident_1790_1990"),
                _row(1850, "West Virginia", 302_313, "resident_1790_1990"),
            ]
        )
        frame = transform_census(rows, _SPINE).set_index(["state", "census_year"])
        assert "cross-checked" in frame.loc[("Virginia", 1850), "note"]
        assert "Alexandria" not in frame.loc[("Virginia", 1850), "note"]
        assert "three published components" in frame.loc[("Virginia", 1820), "note"]

    def test_the_verification_map_has_three_states_pinned_to_a_literal(self) -> None:
        # A third state, not wider membership (AC-8): 1800-1840 are confirmed, but
        # by composition from published components rather than against a total.
        assert dict(VIRGINIA_VERIFICATION) == {
            1790: "published_total",
            1800: "published_components",
            1810: "published_components",
            1820: "published_components",
            1830: "published_components",
            1840: "published_components",
            1850: "published_total",
            1860: "published_total",
        }
        assert VERIFIED_BY_PUBLISHED_TOTAL == "published_total"
        assert VERIFIED_BY_PUBLISHED_COMPONENTS == "published_components"

    def test_a_census_missing_from_the_map_reads_as_unverified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The third state is absence, and it must stay expressible: a census in the
        # window with no entry says "not re-verified" rather than borrowing a claim.
        frame = pd.DataFrame(
            [
                _census_record(1860, "Virginia", 1_219_630),
                _census_record(1860, "West Virginia", 376_688),
            ],
            columns=list(CENSUS_COLUMNS),
        )
        without_1860 = {k: v for k, v in VIRGINIA_VERIFICATION.items() if k != 1860}
        monkeypatch.setattr(transform, "VIRGINIA_VERIFICATION", without_1860)
        corrected = apply_virginia_boundary_correction(frame)
        note = corrected.loc[corrected.state == "Virginia", "note"].iloc[0]
        assert "not re-verified" in note

    def test_a_missing_part_leaves_the_published_figure_alone(self) -> None:
        # A corrected figure built from a missing part would be exactly the fabricated
        # value D005 forbids, so the correction declines rather than guessing.
        frame = pd.DataFrame(
            [
                {
                    "source": "US_CENSUS_BUREAU",
                    "census_year": 1850,
                    "state": "Virginia",
                    "series": SERIES_RESIDENT,
                    "basis": BASIS_PRESENT_DAY,
                    "population": 1_119_348,
                    "vintage": "v",
                    "source_file": "f",
                    "redistributable": True,
                    "note": None,
                },
                {
                    "source": "US_CENSUS_BUREAU",
                    "census_year": 1850,
                    "state": "West Virginia",
                    "series": SERIES_RESIDENT,
                    "basis": BASIS_PRESENT_DAY,
                    "population": None,
                    "vintage": "v",
                    "source_file": "f",
                    "redistributable": True,
                    "note": None,
                },
            ],
            columns=list(CENSUS_COLUMNS),
        )
        corrected = apply_virginia_boundary_correction(frame)
        virginia = corrected[corrected.state == "Virginia"].iloc[0]
        assert virginia["population"] == 1_119_348
        assert virginia["basis"] == BASIS_PRESENT_DAY


#: The file's own Virginia / West Virginia rows at the five Alexandria censuses, and the
#: enumerated Virginia each composes to — ``research-boundary-sweep.md`` §4.1, typed
#: here by hand as the oracle rather than recomputed from the constant under test.
_ALEXANDRIA_CASES = (
    (1800, 807_557, 78_592, 880_200),
    (1810, 877_683, 105_469, 974_600),
    (1820, 938_261, 136_808, 1_065_366),
    (1830, 1_044_054, 176_924, 1_211_405),
    (1840, 1_025_227, 224_537, 1_239_797),
)


class TestAlexandriaRetrocession:
    """#251 — Alexandria County was District of Columbia from 1801 until 1846."""

    def test_the_constant_holds_the_bureaus_five_figures(self) -> None:
        # Pinned to a literal: 8,552 for 1810, not the printed note's 8,852.
        assert dict(ALEXANDRIA_RETROCESSION.population) == {
            1800: 5_949,
            1810: 8_552,
            1820: 9_703,
            1830: 9_573,
            1840: 9_967,
        }
        assert ALEXANDRIA_RETROCESSION.recipient == "Virginia"
        assert ALEXANDRIA_RETROCESSION.donor == "District of Columbia"
        assert ALEXANDRIA_RETROCESSION.effective_date.isoformat() == "1846-09-07"
        assert "Virginia Note 2" in ALEXANDRIA_RETROCESSION.citation

    @pytest.mark.parametrize(("year", "va", "wv", "enumerated"), _ALEXANDRIA_CASES)
    def test_each_census_composes_to_the_enumerated_virginia(
        self, year: int, va: int, wv: int, enumerated: int
    ) -> None:
        rows = _minimal_rows(
            old=[
                _row(year, "Virginia", va, "resident_1790_1990"),
                _row(year, "West Virginia", wv, "resident_1790_1990"),
            ]
        )
        virginia = transform_census(rows, _SPINE).set_index("state").loc["Virginia"]
        assert virginia["population"] == enumerated
        assert virginia["basis"] == BASIS_AS_ENUMERATED
        note = str(virginia["note"])
        assert "Alexandria County" in note
        assert "West Virginia" in note
        assert f"{enumerated:,}" in note

    @pytest.mark.parametrize("year", [1790, 1850, 1860])
    def test_censuses_outside_the_district_era_carry_no_term(self, year: int) -> None:
        # 1790 predates the District; 1850/1860 postdate the retrocession. The window
        # closing is as load-bearing as it opening.
        va, wv = {1790: (691_737, 55_873), 1850: (1_119_348, 302_313)}.get(
            year, (1_219_630, 376_688)
        )
        rows = _minimal_rows(
            old=[
                _row(year, "Virginia", va, "resident_1790_1990"),
                _row(year, "West Virginia", wv, "resident_1790_1990"),
            ]
        )
        virginia = transform_census(rows, _SPINE).set_index("state").loc["Virginia"]
        assert virginia["population"] == va + wv
        assert "Alexandria" not in str(virginia["note"])

    def test_the_district_of_columbia_row_is_left_as_published(self) -> None:
        # The source publishes it correctly for the District's own footprint, which
        # already excludes Alexandria (the Bureau's District note), so it is not restated
        # (D067(e)). Alexandria's people land in no row for these censuses.
        rows = _minimal_rows(
            old=[
                _row(1840, "Virginia", 1_025_227, "resident_1790_1990"),
                _row(1840, "West Virginia", 224_537, "resident_1790_1990"),
                _row(1840, "District of Columbia", 33_745, "resident_1790_1990"),
            ]
        )
        frame = transform_census(rows, _SPINE).set_index("state")
        assert frame.loc["District of Columbia", "population"] == 33_745
        assert frame.loc["District of Columbia", "basis"] == BASIS_PRESENT_DAY

    def test_it_is_a_separate_step_from_the_west_virginia_restatement(self) -> None:
        # AC-2: the West Virginia step alone still yields the file's own sum; only the
        # second step touches the external figure.
        frame = pd.DataFrame(
            [
                _census_record(1840, "Virginia", 1_025_227),
                _census_record(1840, "West Virginia", 224_537),
            ],
            columns=list(CENSUS_COLUMNS),
        )
        after_wv = apply_virginia_boundary_correction(frame)
        va = after_wv.loc[after_wv.state == "Virginia", "population"].iloc[0]
        assert va == 1_249_764
        # The intermediate note reads the verification map's published_components
        # branch: it must say Alexandria is still in the figure, not claim a check.
        note = after_wv.loc[after_wv.state == "Virginia", "note"].iloc[0]
        assert "still includes Alexandria County" in note
        assert "cross-checked" not in note
        assert "not re-verified" not in note
        after_both = apply_alexandria_retrocession(after_wv)
        va = after_both.loc[after_both.state == "Virginia", "population"].iloc[0]
        assert va == 1_239_797

    def test_the_final_note_records_the_verification_state(self) -> None:
        rows = _minimal_rows(
            old=[
                _row(1830, "Virginia", 1_044_054, "resident_1790_1990"),
                _row(1830, "West Virginia", 176_924, "resident_1790_1990"),
            ]
        )
        virginia = transform_census(rows, _SPINE).set_index("state").loc["Virginia"]
        assert "(verification: published_components)" in str(virginia["note"])
        assert "1846-09-07" in str(virginia["note"])

    def test_a_census_the_map_does_not_record_as_composed_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The map and the correction must agree on which censuses were composed; a
        # third state that changes nothing persisted would be decoration.
        patched = dict(VIRGINIA_VERIFICATION)
        patched[1830] = VERIFIED_BY_PUBLISHED_TOTAL
        monkeypatch.setattr(transform, "VIRGINIA_VERIFICATION", patched)
        frame = pd.DataFrame(
            [_census_record(1830, "Virginia", 1_220_978, BASIS_AS_ENUMERATED)],
            columns=list(CENSUS_COLUMNS),
        )
        with pytest.raises(CensusTransformError, match="disagree"):
            apply_alexandria_retrocession(frame)

    def test_a_row_the_west_virginia_step_did_not_restate_is_refused(self) -> None:
        # Subtracting Alexandria from the present-day figure would give a number that
        # is neither published nor enumerated.
        frame = pd.DataFrame(
            [_census_record(1840, "Virginia", 1_025_227)],
            columns=list(CENSUS_COLUMNS),
        )
        with pytest.raises(CensusTransformError, match="still 'present_day'"):
            apply_alexandria_retrocession(frame)

    def test_a_missing_west_virginia_part_fails_loud_end_to_end(self) -> None:
        # The sibling skips a census whose West Virginia cell is NULL, leaving Virginia
        # present_day; this step must then refuse rather than subtract.
        rows = _minimal_rows(
            old=[
                _row(1840, "Virginia", 1_025_227, "resident_1790_1990"),
                _row(1840, "West Virginia", None, "resident_1790_1990"),
            ]
        )
        with pytest.raises(CensusTransformError, match="did not run"):
            transform_census(rows, _SPINE)

    def test_an_absent_or_null_virginia_is_skipped(self) -> None:
        null_frame = pd.DataFrame(
            [_census_record(1840, "Virginia", None, BASIS_AS_ENUMERATED)],
            columns=list(CENSUS_COLUMNS),
        )
        out = apply_alexandria_retrocession(null_frame)
        assert pd.isna(out.loc[0, "population"])
        empty = pd.DataFrame(
            [_census_record(1840, "Maryland", 470_019)], columns=list(CENSUS_COLUMNS)
        )
        assert apply_alexandria_retrocession(empty).equals(empty)

    def test_the_real_fixture_reproduces_every_enumerated_virginia(self) -> None:
        from usvote.census.parse import parse_resident_1790_1990

        rows = {
            "resident_1790_1990": parse_resident_1790_1990(
                CENSUS_TABS_TRIMMED_XLSX.read_bytes(), source_id="resident_1790_1990"
            ),
            "resident_1910_2020": parse_population_change(
                CENSUS_POPCHANGE_XLSX.read_bytes(), source_id="resident_1910_2020"
            ),
        }
        frame = transform_census(rows, _SPINE)
        virginia = frame[frame.state == "Virginia"].set_index("census_year")
        for year, _va, _wv, enumerated in _ALEXANDRIA_CASES:
            assert virginia.loc[year, "population"] == enumerated


class TestFrameShape:
    def test_the_frame_is_on_the_census_columns_in_order(self) -> None:
        assert list(transform_census(_minimal_rows(), _SPINE).columns) == list(
            CENSUS_COLUMNS
        )

    def test_population_is_a_nullable_integer_not_a_float(self) -> None:
        # A plain int64 column widens to float64 the moment a NULL appears, which turns
        # counts into floats and NULLs into NaN — the distinction D005 exists to keep.
        rows = _minimal_rows(
            old=[
                _row(1850, "Connecticut", 370_792, "resident_1790_1990"),
                _row(1860, "Connecticut", None, "resident_1790_1990"),
            ]
        )
        frame = transform_census(rows, _SPINE)
        assert str(frame["population"].dtype) == "Int64"
        assert frame["population"].isna().sum() == 1

    def test_an_absent_figure_carries_provenance_rather_than_a_zero(self) -> None:
        rows = _minimal_rows(
            old=[_row(1860, "Connecticut", None, "resident_1790_1990")]
        )
        frame = transform_census(rows, _SPINE)
        missing = frame[frame.census_year == 1860].iloc[0]
        assert pd.isna(missing["population"])
        assert "No published figure" in missing["note"]

    def test_every_row_carries_the_affirmative_licensing_flag(self) -> None:
        frame = transform_census(_minimal_rows(), _SPINE)
        assert frame["redistributable"].all()
        assert (frame["series"] == SERIES_RESIDENT).all()

    def test_a_missing_source_is_refused_rather_than_silently_short(self) -> None:
        # Loading with only one file would produce a frame quietly missing a century.
        with pytest.raises(CensusTransformError, match="resident_1910_2020"):
            transform_census(
                {"resident_1790_1990": [_row(1850, "Connecticut", 1, "x")]}, _SPINE
            )

    def test_the_end_to_end_transform_over_the_real_fixtures(self) -> None:
        from usvote.census.parse import parse_resident_1790_1990

        rows = {
            "resident_1790_1990": parse_resident_1790_1990(
                CENSUS_TABS_TRIMMED_XLSX.read_bytes(), source_id="resident_1790_1990"
            ),
            "resident_1910_2020": parse_population_change(
                CENSUS_POPCHANGE_XLSX.read_bytes(), source_id="resident_1910_2020"
            ),
        }
        frame = transform_census(rows, _SPINE)
        assert frame["census_year"].min() == 1790
        assert frame["census_year"].max() == 2020
        # The five trimmed sheets supply 1790-1990 (Hawaii joined them in #234); the
        # whole popchange file supplies 2000-2020 for all 51, so the state count is the
        # union rather than five.
        assert frame[frame.census_year <= 1990]["state"].nunique() == 5
        assert frame[frame.census_year >= 2000]["state"].nunique() == 51
        virginia = frame[(frame.state == "Virginia") & (frame.census_year == 1850)]
        assert virginia["population"].iloc[0] == 1_421_661

    def test_the_span_drops_alaskas_off_cycle_censuses(self) -> None:
        """AC-3, the half that lives at THIS layer (#234).

        The parser emits Alaska's 1939 and 1929 faithfully, because relabelling them to
        1940/1930 would file a figure under a census that never happened (D005) and
        ``census_year`` is part of the natural key. Excluding them is a
        which-censuses-are-in-scope decision, which this module owns via
        :data:`SOURCE_SPANS` -- and it needs no new code, since that span is already
        ``range(1790, 2000, 10)``.

        Splitting the property across the two layers is what makes it falsifiable. A
        single "1939 is absent" assertion cannot distinguish a parser that skipped it
        from one that relabelled it to 1940 and then deduplicated -- and the second
        would put 72,524 people in the wrong census while every test stayed green.
        """
        from usvote.census.parse import parse_resident_1790_1990

        parsed = parse_resident_1790_1990(
            CENSUS_TABS_TRIMMED_XLSX.read_bytes(), source_id="resident_1790_1990"
        )
        # The parser is faithful: the off-cycle years ARE in its output.
        assert {row.census_year for row in parsed if row.area == "Alaska"} >= {1929, 1939}

        frame = transform_census(
            {
                "resident_1790_1990": parsed,
                "resident_1910_2020": parse_population_change(
                    CENSUS_POPCHANGE_XLSX.read_bytes(), source_id="resident_1910_2020"
                ),
            },
            _SPINE,
        )
        alaska = set(frame[frame.state == "Alaska"]["census_year"])
        # ...and the span drops them here, without inventing the decennial years they
        # were taken "instead of".
        assert 1929 not in alaska
        assert 1939 not in alaska
        assert 1940 not in alaska
        assert 1930 not in alaska
        assert alaska == {y for y in alaska if y % 10 == 0}
        # The figure the whole story is about survives the span untouched.
        hawaii = frame[(frame.state == "Hawaii") & (frame.census_year == 1950)]
        assert hawaii["population"].iloc[0] == 499_794


class TestProvenanceIsSingleSourced:
    """#181 review, F2/F10: a constant documented as authoritative, bound to nothing.

    ``SOURCE_FILENAMES`` and ``SOURCE_VINTAGES`` used to be literal maps restating
    values that the fetch stage owns. Nothing tied them, so a rename would have updated
    the download and silently falsified every loaded row's provenance while the suite
    stayed green — and the vintage, which the module calls "the only defence" against
    two tabulations that differ by amounts no assert can catch, had no authority to be
    checked against at all.
    """

    def test_the_filename_and_vintage_maps_derive_from_the_source_catalog(self) -> None:
        # Derivation, not duplication: these must BE the catalog's values, so a rename
        # cannot update one and leave the other behind.
        from usvote.census.sources import CENSUS_SOURCES

        for source in CENSUS_SOURCES:
            assert transform.SOURCE_FILENAMES[source.source_id] == source.filename
            assert transform.SOURCE_VINTAGES[source.source_id] == source.vintage

    def test_the_shipped_vintage_values_are_pinned(self) -> None:
        """The pin D059 §5 claims exists.

        Swapping the two vintage strings is a change no other test notices: both files
        parse, every number is right, and the only casualty is that each row now claims
        the wrong published tabulation. That is precisely the class of error the vintage
        column exists to make visible, so the values are pinned to literals here rather
        than compared against the constant they come from.
        """
        assert transform.SOURCE_VINTAGES == {
            "resident_1790_1990": "census-bureau-pop-twps0056-2002",
            "resident_1910_2020": "census-bureau-apportionment-2020",
            "seats_1789_2010": "census-bureau-cph-2-1-table-3",
            "seats_2020": "census-bureau-apportionment-2020",
        }

    def test_the_two_2020_release_files_share_a_vintage_on_purpose(self) -> None:
        """Not a copy-paste slip, and worth pinning so nobody "fixes" it.

        ``population-change-data-table.xlsx`` and ``apportionment.csv`` are two files
        from the *same* 2020 apportionment release, so they genuinely carry the same
        published tabulation. The consequence is that the pin above cannot catch a swap
        between **those two** by value — ``SOURCE_FILENAMES`` is what separates them, and
        the swap that pin exists for (the two *resident* files, whose vintages differ)
        is still caught.
        """
        assert (
            transform.SOURCE_VINTAGES["resident_1910_2020"]
            == transform.SOURCE_VINTAGES["seats_2020"]
        )
        assert (
            transform.SOURCE_FILENAMES["resident_1910_2020"]
            != transform.SOURCE_FILENAMES["seats_2020"]
        )

    def test_every_loaded_row_carries_its_own_files_vintage(self) -> None:
        # The end-to-end version: a row's vintage must match the file the stitch
        # actually took it from, not merely be non-null.
        rows = _minimal_rows()
        frame = transform.transform_census(rows, _SPINE)
        for _, row in frame.iterrows():
            expected = {
                "tabs15-65.xlsx": "census-bureau-pop-twps0056-2002",
                "population-change-data-table.xlsx": "census-bureau-apportionment-2020",
            }[row["source_file"]]
            assert row["vintage"] == expected

    def test_the_source_token_value_is_asserted_not_merely_non_null(self) -> None:
        # REQUIRED_NON_NULL rejects nulls, not empty strings — verified: a frame with
        # source="" passes assert_census_shape. So the value needs its own pin.
        frame = transform.transform_census(_minimal_rows(), _SPINE)
        assert (frame["source"] == SOURCE_CENSUS_BUREAU).all()
        assert frame["source"].str.len().gt(0).all()
