"""Unit tests for the shared PV frame invariants (``usvote.pv.validate``, #82).

Direct coverage of the two validators MIT and UCSB used to each implement privately:
grain (one row per ``(year, state, candidate)``) and totals-not-exceeded. The
per-source delegation is proved by the existing ``test_mit_transform.py`` /
``test_ucsb_transform.py`` suites, which call the source-local names and still pass;
these tests pin the shared implementation itself, including the ``error_cls`` /
``source`` / ``stage`` parameterization that lets one implementation report as either
source's typed, stage-named failure.
"""

from __future__ import annotations

import pandas as pd
import pytest

from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, SOURCE_UCSB
from usvote.pv.validate import (
    PV_GRAIN_COLUMNS,
    PVValidationError,
    assert_pv_grain,
    assert_totals_not_exceeded,
)


class _SourceError(RuntimeError):
    """Stand-in for a source's own typed error (MITTransformError et al.)."""


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)[list(SHARED_PV_COLUMNS)]


def _row(
    *,
    state: str = "New York",
    candidate: str = "Hillary Clinton",
    votes: int = 4556124,
    total: int = 7889703,
    year: int = 2016,
) -> dict[str, object]:
    return {
        "source": SOURCE_MIT, "year": year, "state": state,
        "candidate": candidate, "party": "DEMOCRAT",
        "candidate_votes": votes, "state_total_votes": total,
        "reliability": "exact",
    }


# --- assert_pv_grain -------------------------------------------------------


def test_grain_accepts_one_row_per_key() -> None:
    df = _frame([_row(), _row(candidate="Donald J. Trump", votes=2814589)])
    assert_pv_grain(df, source=SOURCE_MIT)  # does not raise


def test_grain_key_excludes_source() -> None:
    # These validators run on ONE source's frame, where source is constant; the
    # cross-source key belongs to the union guard in usvote.pv.views.
    assert PV_GRAIN_COLUMNS == ("year", "state", "candidate")


def test_grain_accepts_same_candidate_in_different_states() -> None:
    df = _frame([_row(), _row(state="California", votes=8753788, total=14181595)])
    assert_pv_grain(df, source=SOURCE_MIT)  # does not raise


def test_grain_rejects_duplicate_key() -> None:
    df = _frame([_row(), _row()])
    with pytest.raises(PVValidationError, match="grain violated"):
        assert_pv_grain(df, source=SOURCE_MIT)


def test_grain_message_names_source_and_stage() -> None:
    df = _frame([_row(), _row()])
    with pytest.raises(PVValidationError, match="UCSB reconcile grain violated"):
        assert_pv_grain(df, source=SOURCE_UCSB, stage="reconcile")


def test_grain_stage_defaults_to_transform() -> None:
    df = _frame([_row(), _row()])
    with pytest.raises(PVValidationError, match="MIT transform grain violated"):
        assert_pv_grain(df, source=SOURCE_MIT)


def test_grain_message_lists_the_offending_keys() -> None:
    df = _frame([_row(), _row()])
    with pytest.raises(PVValidationError, match=r"New York.*Hillary Clinton"):
        assert_pv_grain(df, source=SOURCE_MIT)


def test_grain_honors_error_cls() -> None:
    # The whole point of the parameter: one shared implementation still fails as the
    # calling source's/stage's own typed error.
    df = _frame([_row(), _row()])
    with pytest.raises(_SourceError):
        assert_pv_grain(df, error_cls=_SourceError, source=SOURCE_MIT)


# --- assert_totals_not_exceeded --------------------------------------------


def test_totals_accepts_shortfall() -> None:
    # Not equality: both sources drop rows before this runs (MIT scopes to EC-getters,
    # UCSB drops the "OTHERS" aggregate), so the retained sum is expected to be less.
    df = _frame([_row(votes=1, total=7889703)])
    assert_totals_not_exceeded(df, source=SOURCE_MIT)  # does not raise


def test_totals_accepts_exact_equality() -> None:
    df = _frame([
        _row(votes=4556124),
        _row(candidate="Donald J. Trump", votes=7889703 - 4556124),
    ])
    assert_totals_not_exceeded(df, source=SOURCE_MIT)  # does not raise


def test_totals_rejects_excess() -> None:
    df = _frame([_row(votes=7889704, total=7889703)])
    with pytest.raises(PVValidationError, match="exceed the state total"):
        assert_totals_not_exceeded(df, source=SOURCE_MIT)


def test_totals_sums_candidates_within_a_state() -> None:
    # Each row is individually under the total; only their sum exceeds it.
    df = _frame([
        _row(votes=4000000),
        _row(candidate="Donald J. Trump", votes=4000000),
    ])
    with pytest.raises(PVValidationError, match="exceed the state total"):
        assert_totals_not_exceeded(df, source=SOURCE_MIT)


def test_totals_groups_by_year_and_state() -> None:
    # A different year's rows must not pool into this year's total.
    df = _frame([
        _row(votes=4556124),
        _row(year=2020, votes=5230985, total=8594826),
    ])
    assert_totals_not_exceeded(df, source=SOURCE_MIT)  # does not raise


def test_totals_message_names_source_and_cell_count() -> None:
    df = _frame([
        _row(votes=7889704, total=7889703),
        _row(state="California", votes=99, total=98),
    ])
    with pytest.raises(
        PVValidationError, match=r"UCSB candidate votes exceed.*2 \(year, state\)"
    ):
        assert_totals_not_exceeded(df, source=SOURCE_UCSB)


def test_totals_honors_error_cls() -> None:
    df = _frame([_row(votes=7889704, total=7889703)])
    with pytest.raises(_SourceError):
        assert_totals_not_exceeded(df, error_cls=_SourceError, source=SOURCE_MIT)
