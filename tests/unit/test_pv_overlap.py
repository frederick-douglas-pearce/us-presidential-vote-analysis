"""Offline tests for the D017 layer-3 overlap gate (#167, D051).

Covers :mod:`usvote.pv.overlap` — gates 1 and 2 at the cell grain — plus the AC-7
threshold pin, which reaches across to :mod:`usvote.hybrid` for gate 3's constant so a
half-table retune cannot hide.

**Two fixtures here exist for a defect the rest of the file could not see.**
``test_a_party_spelling_difference_does_not_make_a_cell_one_sided`` and
``test_the_carried_party_is_mits_spelling`` both spell MIT's ``REPUBLICAN`` against
UCSB's ``Republican`` on one key. Every *other* fixture agrees on party — as any
hand-written pair naturally would — so a regression that put ``party`` back into the
join key would pass all of those while collapsing the real-corpus exact-match rate to
zero. That is the shape this project keeps naming: a test that passes for the wrong
reason.
"""

from __future__ import annotations

import dataclasses
from typing import cast

import pandas as pd
import pytest

from tests._helpers import QueryDispatchDBC
from usvote.db import DBC
from usvote.hybrid import MARGIN_DIFF_MAX_PP
from usvote.pv.overlap import (
    CELL_RELPCT_FAIL,
    CELL_RELPCT_FLAG,
    EXACT_MATCH_FLOOR_OVERALL,
    EXACT_MATCH_FLOOR_PER_YEAR,
    SKIP_NO_OVERLAP_CELLS,
    SKIP_UCSB_ABSENT,
    OverlapKey,
    OverlapReport,
    PVOverlapError,
    assert_db_overlap_within_tolerance,
    assert_overlap_within_tolerance,
    compute_overlap_report,
    read_overlap_frames,
)
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, SOURCE_UCSB


def _row(
    source: str,
    year: int,
    state: str,
    candidate: str,
    votes: int,
    *,
    party: str = "DEMOCRAT",
    total: int | None = None,
) -> dict[str, object]:
    return {
        "source": source,
        "year": year,
        "state": state,
        "candidate": candidate,
        "party": party,
        "candidate_votes": votes,
        "state_total_votes": total if total is not None else votes * 2,
        "reliability": "exact",
    }


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(SHARED_PV_COLUMNS))


def _pair(
    mit_rows: list[dict[str, object]], ucsb_rows: list[dict[str, object]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _frame(mit_rows), _frame(ucsb_rows)


def _agreeing(year: int, n: int, *, start: int = 0) -> list[list[dict[str, object]]]:
    """``n`` cells in ``year`` where both sources agree exactly — one list per source."""
    mit = [
        _row(SOURCE_MIT, year, f"State{start + i}", "Nominee", 1000 + i)
        for i in range(n)
    ]
    ucsb = [
        _row(SOURCE_UCSB, year, f"State{start + i}", "Nominee", 1000 + i)
        for i in range(n)
    ]
    return [mit, ucsb]


def _stub(mit: pd.DataFrame, ucsb: pd.DataFrame) -> QueryDispatchDBC:
    """The shared read-only ``DBC`` double, routed by relation name."""
    return QueryDispatchDBC({"pv_ucsb": ucsb}, mit)


class TestThresholds:
    """AC-1 / AC-7 — the numbers, pinned against what research §6 records."""

    def test_each_threshold_matches_the_value_research_section_6_records(self) -> None:
        """AC-7: five hand-written literals, in one test, across both modules.

        **Literal by necessity, not by style.** An assert that re-derived these from the
        constants themselves would be circular and would pass under any retune — the
        lesson ``HYBRID_SUMMARY_COLUMNS``'s own pin records. And all five sit in one
        test *because* D051 splits them across two modules: a per-module pin would let
        gate 3 be retuned with gates 1-2 left alone and nothing in a single diff showing
        the table had come apart.
        """
        assert EXACT_MATCH_FLOOR_OVERALL == 90.0
        assert EXACT_MATCH_FLOOR_PER_YEAR == 80.0
        assert CELL_RELPCT_FLAG == 1.0
        assert CELL_RELPCT_FAIL == 15.0
        assert MARGIN_DIFF_MAX_PP == 0.25

    def test_the_flag_line_sits_below_the_fail_line(self) -> None:
        """A flag that fired at or above the fail line could never be *only* a flag."""
        assert CELL_RELPCT_FLAG < CELL_RELPCT_FAIL


class TestReportShape:
    """AC-4 — the D030/D022 licensing constraint, made structural."""

    def test_the_reported_key_carries_no_delta_or_magnitude(self) -> None:
        """``OverlapKey`` has exactly the four documented fields and nothing numeric.

        This is the whole of AC-4's "must not carry exact per-cell deltas or absolute
        magnitudes". Asserting the *field set* rather than spot-checking one list is
        what makes it impossible to add a magnitude later without a test going red:
        MIT is CC0 and exactly reproducible, so an attributed relative delta inverts to
        the UCSB integer via ``UCSB = MIT / (1 +/- rel)``.
        """
        fields = {f.name for f in dataclasses.fields(OverlapKey)}
        assert fields == {"year", "state", "candidate", "party"}

    def test_a_skipped_report_carries_no_measurements(self) -> None:
        """A skip must not read as a clean measurement to a caller that ignores it."""
        report = compute_overlap_report(
            _frame([_row(SOURCE_MIT, 1976, "Ohio", "N", 10)]), _frame([])
        )
        assert report.skipped
        assert report.cells == 0
        assert report.exact_pct == 0.0
        assert report.flagged == () and report.failed == () and report.one_sided == ()


class TestPopulation:
    """The full-outer key set, the overlap window, and the party-spelling trap."""

    def test_a_party_spelling_difference_does_not_make_a_cell_one_sided(self) -> None:
        """The join key is ``(year, state, candidate)`` — **never** including party.

        MIT spells ``REPUBLICAN`` where UCSB spells ``Republican`` across the entire
        real overlap (#124's live-corpus finding, which is why ``usvote.hybrid``
        resolves party by ``min`` rather than requiring it constant). Joining on party
        would make *every* real cell one-sided and drive the exact-match rate to zero —
        while passing every other fixture in this file, all of which spell both sides
        the same way.
        """
        mit, ucsb = _pair(
            [_row(SOURCE_MIT, 1976, "Ohio", "Ford", 500, party="REPUBLICAN")],
            [_row(SOURCE_UCSB, 1976, "Ohio", "Ford", 500, party="Republican")],
        )
        report = compute_overlap_report(mit, ucsb)
        assert report.cells == 1
        assert report.exact == 1
        assert report.one_sided == ()

    def test_the_carried_party_is_mits_spelling(self) -> None:
        """Party is a display attribute; MIT's spelling wins, as research §3 prints it."""
        mit, ucsb = _pair(
            [_row(SOURCE_MIT, 1976, "Ohio", "Ford", 500, party="REPUBLICAN")],
            [_row(SOURCE_UCSB, 1976, "Ohio", "Ford", 400, party="Republican")],
        )
        report = compute_overlap_report(mit, ucsb)
        assert [k.party for k in report.flagged] == ["REPUBLICAN"]

    def test_a_one_sided_key_counts_as_not_exact_and_is_reported_by_key(self) -> None:
        """AC / fork (c): full outer, and ``one_sided`` carries keys, not a bare count.

        An inner join would *raise* the exact-match rate by dropping exactly the rows a
        regression creates — the inner-join-silent-drop hazard one level up from where
        this package already guards it. A bare count would say a source dropped rows
        without saying which.
        """
        mit, ucsb = _pair(
            [
                _row(SOURCE_MIT, 1976, "Ohio", "Carter", 100),
                _row(SOURCE_MIT, 1976, "Iowa", "Carter", 200),
            ],
            [_row(SOURCE_UCSB, 1976, "Ohio", "Carter", 100)],
        )
        report = compute_overlap_report(mit, ucsb)
        assert report.cells == 2
        assert report.exact == 1
        assert report.exact_pct == 50.0
        assert report.one_sided == (
            OverlapKey(year=1976, state="Iowa", candidate="Carter", party="DEMOCRAT"),
        )
        # Its relative delta is undefined, so it enters neither gate-2 list.
        assert report.flagged == () and report.failed == ()

    def test_years_before_the_overlap_window_are_excluded(self) -> None:
        """Pre-1976 is UCSB-only by construction; counting it would be all one-sided."""
        mit, ucsb = _pair(
            [_row(SOURCE_MIT, 1976, "Ohio", "Carter", 100)],
            [
                _row(SOURCE_UCSB, 1900, "Ohio", "Bryan", 50),
                _row(SOURCE_UCSB, 1976, "Ohio", "Carter", 100),
            ],
        )
        report = compute_overlap_report(mit, ucsb)
        assert report.cells == 1
        assert set(report.exact_pct_by_year) == {1976}

    def test_an_empty_overlap_window_skips_rather_than_dividing_by_zero(self) -> None:
        """Zero cells is a *skip* with its own reason — never a 100% pass, never a 0/0."""
        mit, ucsb = _pair(
            [_row(SOURCE_MIT, 1976, "Ohio", "Carter", 100)],
            [_row(SOURCE_UCSB, 1900, "Ohio", "Bryan", 50)],
        )
        report = compute_overlap_report(mit, ucsb)
        assert report.skipped
        assert report.skip_reason == SKIP_NO_OVERLAP_CELLS
        assert report.skip_reason != SKIP_UCSB_ABSENT

    def test_a_year_only_one_source_covers_is_excluded_not_scored_zero(self) -> None:
        """The asymmetric-refresh case, which must not break a build.

        MIT is a CSV drop and the UCSB corpus is a manual snapshot, so one reaching a
        new election first is the *ordinary* case, not a regression. Scored, that year
        reads 0% and gate 1 raises at the end of an otherwise complete build; the window
        has a floor and deliberately no ceiling, so nothing else would stop it. Gate 3
        already skips such a year (it inner-joins on year), so this also makes the two
        gates agree about what a coverage gap is.
        """
        mit_rows, ucsb_rows = _agreeing(1976, 10)
        extra_mit, _ = _agreeing(2028, 4, start=100)
        mit_rows += extra_mit  # MIT reached 2028; the UCSB snapshot has not

        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))

        assert report.uncovered_years == (2028,)
        assert 2028 not in report.exact_pct_by_year
        assert report.cells == 10, "2028's cells must not enter the population"
        assert report.exact_pct == 100.0
        assert report.one_sided == ()
        assert_overlap_within_tolerance(report)  # must not raise

    def test_the_exclusion_is_per_year_and_does_not_swallow_a_partial_year(
        self,
    ) -> None:
        """The carve-out is whole-year only — this is what keeps it from disabling gate 1.

        A year one source reaches *partially* is a regression, not a coverage gap, so it
        stays in the population and its missing cells count as one-sided. Without this
        the previous test's exclusion could quietly widen into "any year with missing
        rows is skipped", which would switch the gate off on exactly the failure it
        exists to catch.
        """
        mit_rows, ucsb_rows = _agreeing(1976, 46)
        extra_mit, extra_ucsb = _agreeing(1980, 4, start=100)
        mit_rows += extra_mit
        ucsb_rows += extra_ucsb[:1]  # UCSB reached 1980, but lost 3 of its 4 cells

        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))

        assert report.uncovered_years == (), "1980 IS covered by both sources"
        assert report.exact_pct_by_year[1980] == 25.0
        assert len(report.one_sided) == 3
        with pytest.raises(PVOverlapError, match="gate 1 .per year.*1980"):
            assert_overlap_within_tolerance(report)

    def test_the_breach_message_names_the_one_sided_count(self) -> None:
        """``one_sided`` must surface on a real build, and a breach is where it can.

        It is not on either floor's own arithmetic, so without this a breach caused by a
        source dropping rows reads identically to one caused by cells disagreeing — and
        a reader starts in the wrong place.
        """
        mit_rows, ucsb_rows = _agreeing(1976, 20)
        del ucsb_rows[:5]

        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))
        with pytest.raises(PVOverlapError) as excinfo:
            assert_overlap_within_tolerance(report)

        assert "5 of them are carried by only one source" in str(excinfo.value)

    def test_a_source_that_lost_only_some_rows_still_trips_the_gate(self) -> None:
        """The empty-side skip is narrow **on purpose** — this is what keeps it honest.

        A source that lost *every* row looks like a warehouse built without it (AC-3) and
        skips. A source that lost *some* rows is a regression, and every lost row counts
        as one-sided and therefore not exact. Without this test the widened skip could
        creep into "any partial loss is a skip", which would silently disable the gate on
        exactly the failure it exists to catch.
        """
        mit_rows, ucsb_rows = _agreeing(1976, 20)
        del ucsb_rows[:5]  # UCSB lost a quarter of the window
        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))
        assert not report.skipped
        assert len(report.one_sided) == 5
        assert report.exact_pct == 75.0
        with pytest.raises(PVOverlapError, match="gate 1"):
            assert_overlap_within_tolerance(report)

    def test_a_source_that_lost_one_whole_year_trips_the_per_year_floor(self) -> None:
        """The empty-side skip is per-*window*, never per-year: a lost year still fires."""
        mit_rows, ucsb_rows = _agreeing(1976, 46)
        extra_mit, extra_ucsb = _agreeing(1980, 4, start=100)
        mit_rows += extra_mit
        ucsb_rows += extra_ucsb[:1]  # UCSB lost 3 of 1980's 4 cells
        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))
        assert not report.skipped
        assert report.exact_pct > EXACT_MATCH_FLOOR_OVERALL  # diluted away overall
        assert report.exact_pct_by_year[1980] == 25.0
        with pytest.raises(PVOverlapError, match="gate 1 .per year.*1980"):
            assert_overlap_within_tolerance(report)


class TestGateOneExactMatchFloor:
    """D051 threshold 1 — the two floors are separate instruments."""

    def test_an_overall_rate_below_the_floor_raises(self) -> None:
        mit_rows, ucsb_rows = _agreeing(1976, 8)
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZA", "Nominee", 100))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZA", "Nominee", 101))
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZB", "Nominee", 100))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZB", "Nominee", 101))
        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))
        assert report.exact_pct == 80.0
        with pytest.raises(PVOverlapError, match="gate 1 .overall."):
            assert_overlap_within_tolerance(report)

    def test_one_bad_year_raises_even_when_the_overall_rate_passes(self) -> None:
        """The discriminating case, and the reason gate 1 carries two floors.

        A localized regression — one year's canvass re-parsed wrong — is diluted by
        every other year in the overall rate. Here the overall rate is 92% (above the
        90% floor) while 1980 sits at 50%, and the gate must still fire. Without the
        per-year floor this passes, which is precisely the D051 rationale
        ("the per-year floor is the instrument for exactly the *localized* regression").
        """
        mit_rows, ucsb_rows = _agreeing(1976, 46)
        mit_rows += [
            _row(SOURCE_MIT, 1980, "ZA", "Nominee", 100),
            _row(SOURCE_MIT, 1980, "ZB", "Nominee", 100),
            _row(SOURCE_MIT, 1980, "ZC", "Nominee", 100),
            _row(SOURCE_MIT, 1980, "ZD", "Nominee", 100),
        ]
        ucsb_rows += [
            _row(SOURCE_UCSB, 1980, "ZA", "Nominee", 100),
            _row(SOURCE_UCSB, 1980, "ZB", "Nominee", 100),
            _row(SOURCE_UCSB, 1980, "ZC", "Nominee", 101),
            _row(SOURCE_UCSB, 1980, "ZD", "Nominee", 101),
        ]
        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))
        assert report.exact_pct == 96.0
        assert report.exact_pct > EXACT_MATCH_FLOOR_OVERALL
        assert report.exact_pct_by_year[1980] == 50.0
        with pytest.raises(PVOverlapError, match="gate 1 .per year.*1980"):
            assert_overlap_within_tolerance(report)

    def test_a_clean_population_raises_nothing(self) -> None:
        mit_rows, ucsb_rows = _agreeing(1976, 10)
        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))
        assert report.exact_pct == 100.0
        assert_overlap_within_tolerance(report)

    def test_a_skipped_report_asserts_nothing(self) -> None:
        """AC-3: a skip must never raise, even though every count reads zero."""
        mit, ucsb = _pair([_row(SOURCE_MIT, 1976, "Ohio", "Carter", 1)], [])
        assert_overlap_within_tolerance(compute_overlap_report(mit, ucsb))


class TestGateTwoPerCellCeiling:
    """D051 threshold 2 — strict comparisons, and the UCSB denominator."""

    @staticmethod
    def _one_cell(mit_votes: int, ucsb_votes: int) -> OverlapReport:
        mit_rows, ucsb_rows = _agreeing(1976, 19)
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZZ", "Nominee", mit_votes))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZZ", "Nominee", ucsb_votes))
        return compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))

    def test_a_cell_exactly_on_the_flag_line_is_not_flagged(self) -> None:
        """Strict ``>``, matching research query 4's ``relpct > 1.0``.

        The published list and the published count are aligned on the same strict
        comparison so they can never disagree about a cell sitting on the line.
        """
        report = self._one_cell(10_100, 10_000)  # exactly 1.00%
        assert report.flagged == ()

    def test_a_cell_above_the_flag_line_flags_but_does_not_fail(self) -> None:
        report = self._one_cell(10_200, 10_000)  # 2.00%
        assert [k.state for k in report.flagged] == ["ZZ"]
        assert report.failed == ()
        assert_overlap_within_tolerance(report)  # flagging is not a breach

    def test_a_cell_above_the_fail_line_raises_and_is_also_flagged(self) -> None:
        """The two lists nest: everything failing is also flagged."""
        report = self._one_cell(11_600, 10_000)  # 16.00%
        assert [k.state for k in report.failed] == ["ZZ"]
        assert [k.state for k in report.flagged] == ["ZZ"]
        with pytest.raises(PVOverlapError, match="gate 2"):
            assert_overlap_within_tolerance(report)

    def test_the_relative_delta_is_taken_against_the_ucsb_value(self) -> None:
        """AC-6: the basis is ``|MIT - UCSB| / UCSB``, and it must be able to FAIL.

        **The fixture straddles the flag line, and that is the whole test.** MIT 10,050
        against UCSB 9,950 is ``100/9950 = 1.005%`` on the UCSB basis — flagged — and
        ``100/10050 = 0.995%`` on the MIT basis — not flagged. So swapping the
        denominator in ``compute_overlap_report`` turns this red.

        An earlier version of this test used a pair that flagged under *both* bases and
        then asserted arithmetic over literals, which pinned nothing: it would have
        passed with the denominator swapped. Any ``99d < UCSB < 100d`` pair straddles
        the line; keep one here rather than relying on the fail-line tests, whose
        straddle is incidental and evaporates if ``CELL_RELPCT_FAIL`` is ever retuned.
        """
        report = self._one_cell(10_050, 9_950)
        assert [k.state for k in report.flagged] == ["ZZ"], (
            "MIT 10050 vs UCSB 9950 is 1.005% of the UCSB value and must flag; "
            "0.995% of the MIT value would not, so an empty list means the basis "
            "was taken against MIT"
        )

    def test_a_zero_ucsb_value_does_not_divide_by_zero(self) -> None:
        """``max(UCSB, 1)`` mirrors the reference script's ``greatest(ucsb, 1)``."""
        report = self._one_cell(5, 0)
        assert [k.state for k in report.failed] == ["ZZ"]


class TestTheReadSeam:
    """AC-2 / AC-3 — which relations are read, and when the gate skips."""

    def test_it_reads_the_two_single_source_views_and_never_the_raw_union(self) -> None:
        """AC-2: reading ``pv_votes`` would fan the overlap 2x (D017 §Consequence)."""
        mit, ucsb = _pair(
            [_row(SOURCE_MIT, 1976, "Ohio", "Carter", 100)],
            [_row(SOURCE_UCSB, 1976, "Ohio", "Carter", 100)],
        )
        dbc = _stub(mit, ucsb)
        assert read_overlap_frames(cast(DBC, dbc)) is not None
        joined = " ".join(dbc.queries)
        assert "pv_redistributable" in joined
        assert "pv_ucsb" in joined
        assert "pv_votes" not in joined

    def test_it_filters_both_reads_to_the_overlap_window(self) -> None:
        dbc = _stub(*_pair([], [_row(SOURCE_UCSB, 1976, "Ohio", "C", 1)]))
        read_overlap_frames(cast(DBC, dbc))
        assert sum("year >= 1976" in q for q in dbc.queries) == 2

    def test_an_empty_pv_ucsb_skips_rather_than_reading_further(self) -> None:
        """AC-3: a public EC + MIT clone must not be reddened by this gate."""
        dbc = _stub(*_pair([_row(SOURCE_MIT, 1976, "Ohio", "Carter", 1)], []))
        assert read_overlap_frames(cast(DBC, dbc)) is None
        # It stopped at the probe -- no window reads were issued.
        assert len(dbc.queries) == 1

    def test_the_probe_asks_the_unfiltered_view(self) -> None:
        """"Is UCSB loaded?" is a question about the source, not about the window.

        Probing the *filtered* view would skip whenever UCSB happened to carry no
        1976+ rows, which is a different fact and takes a different skip reason.
        """
        dbc = _stub(*_pair([], [_row(SOURCE_UCSB, 1900, "Ohio", "Bryan", 1)]))
        read_overlap_frames(cast(DBC, dbc))
        assert "year >=" not in dbc.queries[0]

    def test_the_live_form_returns_a_skipped_report_when_ucsb_is_absent(self) -> None:
        dbc = _stub(*_pair([_row(SOURCE_MIT, 1976, "Ohio", "Carter", 1)], []))
        report = assert_db_overlap_within_tolerance(cast(DBC, dbc))
        assert report.skipped
        assert report.skip_reason == SKIP_UCSB_ABSENT

    def test_the_live_form_measures_and_raises_over_real_frames(self) -> None:
        mit_rows, ucsb_rows = _agreeing(1976, 1)
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZZ", "Nominee", 100))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZZ", "Nominee", 101))
        dbc = _stub(_frame(mit_rows), _frame(ucsb_rows))
        with pytest.raises(PVOverlapError):
            assert_db_overlap_within_tolerance(cast(DBC, dbc))

    def test_the_live_form_returns_the_flag_list_on_a_passing_population(self) -> None:
        """Gate 2's D005 list is *returned*, not raised on — AC-4's "feeding" half."""
        mit_rows, ucsb_rows = _agreeing(1976, 19)
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZZ", "Nominee", 10_200))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZZ", "Nominee", 10_000))
        dbc = _stub(_frame(mit_rows), _frame(ucsb_rows))
        report = assert_db_overlap_within_tolerance(cast(DBC, dbc))
        assert not report.skipped
        assert [k.state for k in report.flagged] == ["ZZ"]


class TestFailureMessage:
    """The raise is subject to the same licensing constraint as the return value."""

    def test_the_message_names_keys_and_no_magnitudes(self) -> None:
        mit_rows, ucsb_rows = _agreeing(1976, 19)
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZZ", "Nominee", 11_600))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZZ", "Nominee", 10_000))
        report = compute_overlap_report(_frame(mit_rows), _frame(ucsb_rows))
        with pytest.raises(PVOverlapError) as excinfo:
            assert_overlap_within_tolerance(report)
        message = str(excinfo.value)
        assert "ZZ" in message
        assert "11600" not in message and "10000" not in message
