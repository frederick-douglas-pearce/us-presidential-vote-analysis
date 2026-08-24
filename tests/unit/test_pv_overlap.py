"""Offline tests for the D017 layer-3 overlap gate (#167, D051).

Covers :mod:`usvote.pv.overlap` — gates 1 and 2 at the cell grain — plus the AC-7
threshold pin, which reaches across to :mod:`usvote.hybrid` for gate 3's constant so a
half-table retune cannot hide.

**One fixture here exists for a defect no other test in this file could see.**
``test_a_party_spelling_difference_does_not_make_a_cell_one_sided`` spells MIT's
``REPUBLICAN`` against UCSB's ``Republican`` on the same key. Every other fixture agrees
on party — as any hand-written pair naturally would — so a regression that put ``party``
back into the join key would pass all of them while collapsing the real-corpus
exact-match rate to zero. That is the shape this project keeps naming: a test that
passes for the wrong reason.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

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


class _StubDBC:
    """A minimal ``DBC`` stand-in answering by the relation named in the query.

    Deliberately not a mock: the point is to prove the read seam issues the reads it
    claims — the two D017 single-source views and never the raw union — so it has to
    serve real frames and record what it was asked for.
    """

    def __init__(self, mit: pd.DataFrame, ucsb: pd.DataFrame) -> None:
        self.mit = mit
        self.ucsb = ucsb
        self.queries: list[str] = []

    def select_query_to_df(self, query: str) -> pd.DataFrame:
        self.queries.append(query)
        if "pv_ucsb" in query:
            return self.ucsb.copy()
        return self.mit.copy()


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
        """AC-6: the basis is ``|MIT - UCSB| / UCSB``, and the measure is asymmetric.

        Engineered so the two readings straddle the flag line: MIT 1030 against UCSB
        1000 is **3.00%** on the UCSB basis and **2.91%** on the MIT basis. Both flag,
        so a straddle at 1% cannot discriminate — this pins the *value* instead, which
        is what makes the basis observable rather than merely documented.
        """
        report = self._one_cell(1_030, 1_000)
        assert [k.state for k in report.flagged] == ["ZZ"]
        # 30/1000 = 3.00% (UCSB basis) -- fails a 2.95% line; 30/1030 = 2.913% passes it.
        strict = compute_overlap_report(
            _frame([_row(SOURCE_MIT, 1976, "ZZ", "Nominee", 1_030)]),
            _frame([_row(SOURCE_UCSB, 1976, "ZZ", "Nominee", 1_000)]),
        )
        assert strict.flagged  # sanity: the single cell diverges at all
        mit_basis = abs(1_030 - 1_000) / 1_030 * 100
        ucsb_basis = abs(1_030 - 1_000) / 1_000 * 100
        assert mit_basis < 2.95 < ucsb_basis  # the two bases really do differ here

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
        dbc = _StubDBC(mit, ucsb)
        assert read_overlap_frames(dbc) is not None
        joined = " ".join(dbc.queries)
        assert "pv_redistributable" in joined
        assert "pv_ucsb" in joined
        assert "pv_votes" not in joined

    def test_it_filters_both_reads_to_the_overlap_window(self) -> None:
        dbc = _StubDBC(*_pair([], [_row(SOURCE_UCSB, 1976, "Ohio", "C", 1)]))
        read_overlap_frames(dbc)
        assert sum("year >= 1976" in q for q in dbc.queries) == 2

    def test_an_empty_pv_ucsb_skips_rather_than_reading_further(self) -> None:
        """AC-3: a public EC + MIT clone must not be reddened by this gate."""
        dbc = _StubDBC(*_pair([_row(SOURCE_MIT, 1976, "Ohio", "Carter", 1)], []))
        assert read_overlap_frames(dbc) is None
        # It stopped at the probe -- no window reads were issued.
        assert len(dbc.queries) == 1

    def test_the_probe_asks_the_unfiltered_view(self) -> None:
        """"Is UCSB loaded?" is a question about the source, not about the window.

        Probing the *filtered* view would skip whenever UCSB happened to carry no
        1976+ rows, which is a different fact and takes a different skip reason.
        """
        dbc = _StubDBC(*_pair([], [_row(SOURCE_UCSB, 1900, "Ohio", "Bryan", 1)]))
        read_overlap_frames(dbc)
        assert "year >=" not in dbc.queries[0]

    def test_the_live_form_returns_a_skipped_report_when_ucsb_is_absent(self) -> None:
        dbc = _StubDBC(*_pair([_row(SOURCE_MIT, 1976, "Ohio", "Carter", 1)], []))
        report = assert_db_overlap_within_tolerance(dbc)
        assert report.skipped
        assert report.skip_reason == SKIP_UCSB_ABSENT

    def test_the_live_form_measures_and_raises_over_real_frames(self) -> None:
        mit_rows, ucsb_rows = _agreeing(1976, 1)
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZZ", "Nominee", 100))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZZ", "Nominee", 101))
        dbc = _StubDBC(_frame(mit_rows), _frame(ucsb_rows))
        with pytest.raises(PVOverlapError):
            assert_db_overlap_within_tolerance(dbc)

    def test_the_live_form_returns_the_flag_list_on_a_passing_population(self) -> None:
        """Gate 2's D005 list is *returned*, not raised on — AC-4's "feeding" half."""
        mit_rows, ucsb_rows = _agreeing(1976, 19)
        mit_rows.append(_row(SOURCE_MIT, 1976, "ZZ", "Nominee", 10_200))
        ucsb_rows.append(_row(SOURCE_UCSB, 1976, "ZZ", "Nominee", 10_000))
        dbc = _StubDBC(_frame(mit_rows), _frame(ucsb_rows))
        report = assert_db_overlap_within_tolerance(dbc)
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
