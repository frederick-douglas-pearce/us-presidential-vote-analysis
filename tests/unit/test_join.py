"""Unit tests for the EC<->PV participant join (``usvote.join``, #69 / D026).

Two kinds of check, both offline (mirroring ``tests/unit/test_pv_views.py``):

- **SQL structure** — the builder emits the FULL OUTER participant join D026 mandates
  (reads a *resolved* PV view, never the raw ``pv_votes`` union; the guarded EC-0 CASE;
  national context from the ``is_total`` rows), threads the schema, and shapes both views.
- **Frame oracle** — :func:`usvote.join.join_ec_pv` on a small, fabricated EC+PV scenario
  covering the three D026 row types (winner+PV, loser-in-state with EC=0, getter-without-PV
  with NULL PV), a **split-vote state** (ME/NE-style — each getter keeps its real count),
  and the four guards (no-fan-out, dim-coverage, no-fabricated-EC-zero, winner-has-PV).

The oracle is the same policy the live view runs; the live behavioral check is in
``tests/integration/test_ec_pv_join.py``.
"""

from __future__ import annotations

from typing import cast

import pandas as pd
import pytest

from usvote.join import (
    EC_PV_COLUMNS,
    EC_PV_PREFERRED_VIEW,
    EC_PV_REDISTRIBUTABLE_VIEW,
    JoinError,
    assert_ec_dims_cover_pv,
    assert_no_fabricated_ec_zero,
    assert_no_fan_out,
    assert_winners_have_pv,
    build_ec_pv_join_sql,
    coverage_report,
    join_ec_pv,
)
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, build_pv_source_frame
from usvote.pv.views import PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW

# --- SQL structure ----------------------------------------------------------


def test_view_names_are_prefixed_apart_from_the_resolved_pv_views() -> None:
    assert EC_PV_PREFERRED_VIEW == "ec_pv_preferred"
    assert EC_PV_REDISTRIBUTABLE_VIEW == "ec_pv_redistributable"
    # Distinct from the resolved PV views they wrap.
    assert EC_PV_PREFERRED_VIEW != PV_PREFERRED_VIEW


def test_builder_reads_a_resolved_view_never_the_raw_union() -> None:
    # D017/D026: the join MUST read a resolved single-row series, never dwh.pv_votes —
    # joining the raw union fans the 1976–2024 overlap out 2× and double-counts.
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    assert "FULL OUTER JOIN dwh.pv_preferred p" in sql
    assert "pv_votes" not in sql


def test_builder_is_a_full_outer_with_guarded_ec_zero() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    assert "FULL OUTER JOIN" in sql
    # EC on neither side is dropped; the key COALESCEs across both sides.
    assert "COALESCE(e.year, p.year) AS year" in sql
    # Guarded 0-fill: actual EV if there's an EC row; else 0 only in a contested state.
    assert "WHEN e.candidate_id IS NOT NULL THEN e.ec_state_ev" in sql
    assert "WHEN ctx.total_electoral_votes IS NOT NULL THEN 0" in sql
    assert "ELSE NULL END AS president_electoral_votes" in sql
    # has_ec_state_row is exposed explicitly (not overloaded onto president_electoral_votes).
    assert "(e.candidate_id IS NOT NULL) AS has_ec_state_row" in sql


def test_builder_excludes_is_total_from_state_grain_carries_national_context() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    # ec_state is state rows only (is_total excluded); national context comes from the
    # is_total rows via the getter CTE and rides every participant row.
    assert "WHERE v.state IS NOT NULL" in sql
    assert "getter AS" in sql
    assert "g.national_electoral_votes, g.president_electoral_rank, g.took_office" in sql


def test_builder_resolves_loser_candidate_id_by_name_and_carries_redistributable() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    # A PV-only loser row has no EC candidate_id; resolve it by canonical name.
    assert "LEFT JOIN dwh.candidate cd" in sql
    assert "cd.name = COALESCE(e.candidate, p.candidate)" in sql
    # redistributable is carried from the pv_source reference table.
    assert "LEFT JOIN dwh.pv_source s ON s.source = p.source" in sql


def test_builder_targets_the_redistributable_view() -> None:
    sql = build_ec_pv_join_sql(PV_REDISTRIBUTABLE_VIEW)
    assert "FULL OUTER JOIN dwh.pv_redistributable p" in sql


def test_builder_threads_the_schema() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW, schema="mart", pv_schema="mart")
    assert "mart.votes" in sql
    assert "mart.pv_preferred" in sql
    assert "mart.pv_source" in sql


# --- frame oracle: a fabricated EC + PV scenario ----------------------------

# Candidate dim. Every PV candidate is an EC getter (D007/D025), so all resolve here.
_CANDIDATES = pd.DataFrame(
    [
        {"candidate_id": 1, "name": "Winner A"},
        {"candidate_id": 2, "name": "Loser B"},
        {"candidate_id": 4, "name": "Faithless F"},
    ]
)

_STATE_NAMES = frozenset({"Texas", "California", "Nebraska", "Washington"})


def _votes() -> pd.DataFrame:
    """A fabricated ``dwh.votes`` frame: winners' state rows + national is_total rows.

    2020 with A winning Texas (38) and Washington (11), B winning California (55),
    **Nebraska split** A=4 / B=1 (both real rows — the case that must not collapse to 0),
    and a faithless getter F winning 1 EV in Washington with no popular-vote row.
    """
    state_rows = [
        # year, state, candidate_id, total_ev, president_ev
        (2020, "Texas", 1, 38, 38),
        (2020, "California", 2, 55, 55),
        (2020, "Nebraska", 1, 5, 4),   # split
        (2020, "Nebraska", 2, 5, 1),   # split — B keeps its real 1 EV, not 0
        (2020, "Washington", 1, 12, 11),
        (2020, "Washington", 4, 12, 1),  # faithless getter, no PV
    ]
    rows = [
        {
            "year": y, "state": s, "is_total": False, "candidate_id": c,
            "total_electoral_votes": tev, "president_electoral_votes": pev,
            "president_electoral_rank": 0, "took_office": False,
        }
        for (y, s, c, tev, pev) in state_rows
    ]
    # National is_total rows (state None): A=53, B=56, F=1 → B rank 1 nationally.
    totals = [(1, 53, 2, False), (2, 56, 1, True), (4, 1, 3, False)]
    for cid, nev, rank, took in totals:
        rows.append({
            "year": 2020, "state": None, "is_total": True, "candidate_id": cid,
            "total_electoral_votes": 538, "president_electoral_votes": nev,
            "president_electoral_rank": rank, "took_office": took,
        })
    return pd.DataFrame(rows)


def _pv_row(state: str, candidate: str, votes: int, total: int) -> dict:
    return {
        "source": SOURCE_MIT, "year": 2020, "state": state, "candidate": candidate,
        "party": "DEMOCRAT", "candidate_votes": votes, "state_total_votes": total,
        "reliability": "exact",
    }


def _pv() -> pd.DataFrame:
    """Resolved PV: both majors in every contested state (so each has a loser-in-state
    row somewhere); no PV for faithless F (a getter-without-PV row)."""
    return pd.DataFrame([
        _pv_row("Texas", "Winner A", 100, 250),
        _pv_row("Texas", "Loser B", 150, 250),        # loser-in-state (EC=0)
        _pv_row("California", "Winner A", 80, 200),    # loser-in-state (EC=0)
        _pv_row("California", "Loser B", 120, 200),
        _pv_row("Nebraska", "Winner A", 30, 60),
        _pv_row("Nebraska", "Loser B", 28, 60),        # split — EC=1, not 0
        _pv_row("Washington", "Winner A", 40, 70),
        _pv_row("Washington", "Loser B", 25, 70),      # loser-in-state (EC=0)
    ])[list(SHARED_PV_COLUMNS)]


def _joined() -> pd.DataFrame:
    return join_ec_pv(_votes(), _CANDIDATES, _pv(), build_pv_source_frame())


def _by_key(joined: pd.DataFrame) -> dict[tuple, pd.Series]:
    return {(r.year, r.state, r.candidate): r for r in joined.itertuples()}


def test_oracle_output_is_on_the_declared_shape_and_grain() -> None:
    joined = _joined()
    assert list(joined.columns) == list(EC_PV_COLUMNS)
    # Union of ec_state keys and pv keys = 9 participant rows, one per (year,state,cand).
    assert len(joined) == 9
    assert_no_fan_out(joined)  # does not raise


def test_split_state_keeps_each_getters_real_ec_votes() -> None:
    # The invariant Fred flagged: a split-vote state must NOT lose a candidate's real EC
    # count to the 0-fill. Nebraska: A=4, B=1 both preserved (B is not a 0 despite losing
    # the state's plurality), and they sum to the state's allotment.
    rows = _by_key(_joined())
    ne_a = rows[(2020, "Nebraska", "Winner A")]
    ne_b = rows[(2020, "Nebraska", "Loser B")]
    assert ne_a.president_electoral_votes == 4
    assert ne_b.president_electoral_votes == 1
    assert bool(ne_a.has_ec_state_row) and bool(ne_b.has_ec_state_row)
    assert ne_a.president_electoral_votes + ne_b.president_electoral_votes == 5


def test_loser_in_state_is_zero_ec_with_pv_carried() -> None:
    # Loser B in Texas: no EC row → EC=0 (contested state), PV present, national context
    # (B's national 56 EV / rank 1) carried onto the loser row for flip detection.
    r = _by_key(_joined())[(2020, "Texas", "Loser B")]
    assert not bool(r.has_ec_state_row)
    assert r.president_electoral_votes == 0
    assert r.candidate_votes == 150
    assert r.candidate_id == 2                    # resolved by name
    assert r.national_electoral_votes == 56
    assert r.president_electoral_rank == 1
    assert bool(r.took_office)


def test_getter_without_pv_is_an_honest_null_gap() -> None:
    # Faithless F won 1 EV in Washington but has no PV → EC actual, PV NULL (D005 gap,
    # never a fabricated 0 on the PV side).
    r = _by_key(_joined())[(2020, "Washington", "Faithless F")]
    assert bool(r.has_ec_state_row)
    assert r.president_electoral_votes == 1
    assert pd.isna(r.candidate_votes)
    assert pd.isna(r.state_total_votes)


def test_winner_plus_pv_carries_the_provided_denominator() -> None:
    # Winner A in Texas: EC actual + PV, and state_total_votes carried through so a margin
    # pins to the source's provided denominator, not a re-sum (D017).
    r = _by_key(_joined())[(2020, "Texas", "Winner A")]
    assert r.president_electoral_votes == 38
    assert r.candidate_votes == 100
    assert r.state_total_votes == 250
    assert r.source == SOURCE_MIT
    assert bool(r.redistributable)


def test_coverage_report_surfaces_both_directions() -> None:
    report = coverage_report(_joined())
    # ec_only: the one getter-without-PV row (F in WA).
    ec_only = cast(pd.DataFrame, report["ec_only"])
    assert ec_only.values.tolist() == [[2020, "Washington", "Faithless F"]]
    # pv_only: the three loser-in-state rows (TX B, CA A, WA B) — counted, not listed.
    assert report["pv_only_n"] == 3


# --- guards -----------------------------------------------------------------


def test_dim_coverage_passes_when_every_pv_value_is_in_the_ec_dims() -> None:
    assert_ec_dims_cover_pv(_pv(), set(_CANDIDATES["name"]), _STATE_NAMES)  # no raise


def test_dim_coverage_raises_on_an_unreconciled_candidate() -> None:
    bad = pd.concat([_pv(), pd.DataFrame([_pv_row("Texas", "Ghost", 1, 2)])])
    with pytest.raises(JoinError, match="Ghost"):
        assert_ec_dims_cover_pv(bad, set(_CANDIDATES["name"]), _STATE_NAMES)


def test_dim_coverage_raises_on_an_unreconciled_state() -> None:
    bad = pd.concat([_pv(), pd.DataFrame([_pv_row("Atlantis", "Winner A", 1, 2)])])
    with pytest.raises(JoinError, match="Atlantis"):
        assert_ec_dims_cover_pv(bad, set(_CANDIDATES["name"]), _STATE_NAMES)


def test_no_fabricated_ec_zero_passes_on_clean_data() -> None:
    assert_no_fabricated_ec_zero(_joined())  # every PV row sits in a contested state


def test_no_fabricated_ec_zero_raises_on_a_roster_leak() -> None:
    # A PV row for a (year, state) with NO EC contest at all → total_electoral_votes NULL,
    # EC left NULL (not a fabricated 0) — but PV present there is a D024 roster leak.
    votes = _votes()
    cands = pd.concat(
        [_CANDIDATES, pd.DataFrame([{"candidate_id": 9, "name": "Orphan O"}])],
        ignore_index=True,
    )
    leak_pv = pd.concat(
        [_pv(), pd.DataFrame([
            {"source": SOURCE_MIT, "year": 1900, "state": "Ohio", "candidate": "Orphan O",
             "party": "X", "candidate_votes": 50, "state_total_votes": 100,
             "reliability": "exact"},
        ])],
        ignore_index=True,
    )[list(SHARED_PV_COLUMNS)]
    joined = join_ec_pv(votes, cands, leak_pv, build_pv_source_frame())
    # The leak row itself: EC stays NULL (never fabricated 0), and the guard fires.
    leak = _by_key(joined)[(1900, "Ohio", "Orphan O")]
    assert pd.isna(leak.president_electoral_votes)
    assert pd.isna(leak.total_electoral_votes)
    with pytest.raises(JoinError, match="roster leak"):
        assert_no_fabricated_ec_zero(joined)


def test_winner_has_pv_raises_on_a_reconciliation_miss() -> None:
    # Faithless F is an EC winner in 2020 (a PV-covered year) with no PV. Unexempted, that
    # reads as a name-reconciliation miss and must fail loud.
    with pytest.raises(JoinError, match="no matching PV"):
        assert_winners_have_pv(_joined())


def test_winner_has_pv_passes_with_the_getter_exempted() -> None:
    # Exempt the legitimately-PV-less faithless getter → the guard is quiet, and it
    # returns the count of in-window EC-winner rows it inspected (all 6 state rows: TX/A,
    # CA/B, NE/A, NE/B, WA/A, WA/F) — the vacuity floor a caller asserts against.
    inspected = assert_winners_have_pv(_joined(), exemptions={(2020, "Faithless F")})
    assert inspected == 6


def test_oracle_without_pv_source_leaves_redistributable_null() -> None:
    # pv_source_df is optional (the redistributable attribute is a nice-to-have for the
    # offline oracle); omitting it yields an all-NA redistributable column, not an error.
    joined = join_ec_pv(_votes(), _CANDIDATES, _pv())
    assert joined["redistributable"].isna().all()


def test_no_fan_out_raises_on_a_duplicated_key() -> None:
    # A duplicated (year, state, candidate) — the shape a raw-union double-count would
    # produce — must fail loud.
    joined = _joined()
    dup = pd.concat([joined, joined.iloc[[0]]], ignore_index=True)
    with pytest.raises(JoinError, match="fanned out"):
        assert_no_fan_out(dup)
