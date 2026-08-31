"""Unit tests for :mod:`usvote.hybrid` — the E7-S2 three-method computation (#121).

Offline and pure: every test builds an ``ec_pv_preferred``-shaped frame plus a
``dwh.pv_state_status``-shaped roster in memory. No DB, no network.

**Why a frame *builder* rather than literal frames.** The live join view guarantees
properties the computation leans on — the EC fact is **dense** (every getter has a row in
every state, ``0`` where they won none, D026), and ``national_electoral_votes`` is a window
SUM over the candidate's state rows. A hand-written literal frame can silently violate
both, and then a test proves the computation right against data the view can never
produce. :func:`ec_pv_frame` derives the national EV total and the rank from the state
rows, so a fixture cannot disagree with itself.

The 1824 and 2000/2016 fixtures carry **real** electoral-vote maps (see each docstring for
exactly which parts are real and which are synthesized) — they are the D041/D037 acceptance
fixtures, not illustrations.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest

from tests._helpers import QueryDispatchDBC, non_null_flag
from tests.fixtures.api_snapshot import FIXTURE_NOT_COUNTED_REASON
from usvote import hybrid
from usvote.count_status import (
    COUNT_STATUS_COLUMN,
    COUNT_STATUS_COUNTED,
    COUNT_STATUS_NOT_COUNTED,
    COUNT_STATUS_REASON_COLUMN,
    COUNTED_VOTES_COLUMN,
)
from usvote.join import (
    EC_PV_COLUMNS,
    EC_PV_PREFERRED_VIEW,
    EC_PV_REDISTRIBUTABLE_VIEW,
)
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, SOURCE_UCSB
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    ROSTER_TABLE,
)

#: The shared Archives sentence (see tests/fixtures/api_snapshot.py for why a fixture
#: cannot invent one).
_FIXTURE_REASON = FIXTURE_NOT_COUNTED_REASON

# --- frame builders ---------------------------------------------------------


def ec_pv_frame(
    rows: list[dict[str, object]],
    *,
    took_office: dict[int, str] | None = None,
    party: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Build an ``ec_pv_preferred``-shaped frame from flat per-state-candidate rows.

    Each row needs ``year``, ``state``, ``candidate``, ``total_electoral_votes``,
    ``president_electoral_votes``; ``candidate_votes`` and ``state_total_votes`` are
    optional (absent → NULL, the honest D005 gap). ``president_electoral_votes_counted``
    is optional too and **defaults to the cast value** — the shape of every year but 1868
    and 1872 (#144). Supplying it lets a fixture model cast-but-uncounted votes; both the
    counted window SUM and the rank are then derived from it, exactly as the live view and
    ``transform._add_electoral_rank`` do, so a fixture cannot assert a rank the spine
    would not produce. Derived here so a fixture cannot
    contradict the live view: ``candidate_id`` (stable per name), ``national_electoral_votes``
    (the window SUM), and ``president_electoral_rank`` (dense rank on the national total,
    descending, so rank 1 is the EC leader).

    ``took_office`` maps year → the canonical name of whoever assumed the presidency
    (defaults to the rank-1 candidate, i.e. the non-contingent case). It is written out
    as the **boolean** the real column is — ``transform._add_took_office`` sets
    ``president_electoral_rank == 1`` with a ``candidate_id`` override for contingent
    years, and ``load.py`` declares it ``boolean not null`` — so a fixture cannot assert a
    string contract the live view can never produce.
    """
    df = pd.DataFrame(rows)
    for col in ("candidate_votes", "state_total_votes"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = df[col].astype("float64")

    names = sorted(df["candidate"].unique())
    ids = {name: i + 1 for i, name in enumerate(names)}
    df["candidate_id"] = df["candidate"].map(ids)
    df["party"] = df["candidate"].map(party or {}).fillna("Unknown")

    if COUNTED_VOTES_COLUMN not in df.columns:
        df[COUNTED_VOTES_COLUMN] = df["president_electoral_votes"]
    df[COUNTED_VOTES_COLUMN] = df[COUNTED_VOTES_COLUMN].fillna(
        df["president_electoral_votes"]
    )
    for source_col, out_col in (
        ("president_electoral_votes", "national_electoral_votes"),
        (COUNTED_VOTES_COLUMN, "national_counted_electoral_votes"),
    ):
        df[out_col] = df.groupby(["year", "candidate_id"])[source_col].transform("sum")
    df["president_electoral_rank"] = (
        df.groupby("year")["national_counted_electoral_votes"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )
    leaders = (
        df.loc[df["president_electoral_rank"] == 1]
        .groupby("year")["candidate"]
        .first()
        .to_dict()
    )
    holder = {**leaders, **(took_office or {})}
    df["took_office"] = [
        candidate == holder[year]
        for year, candidate in zip(df["year"], df["candidate"], strict=True)
    ]

    df["source"] = "test"
    df["reliability"] = "high"
    df["redistributable"] = True
    # #139 appended the count status to the view. `usvote.hybrid` reads neither column,
    # but the fixture must still emit exactly EC_PV_COLUMNS — the set-equality assert
    # below exists because a fixture *richer* than the view is what let #144's
    # `policy='restricted'` KeyError through the whole offline suite. Derived from the
    # counted measure rather than accepted as input, so a fixture cannot claim a row was
    # counted while zeroing its counted votes.
    counted_in_full = df[COUNTED_VOTES_COLUMN] == df["president_electoral_votes"]
    df[COUNT_STATUS_COLUMN] = [
        COUNT_STATUS_COUNTED if ok else COUNT_STATUS_NOT_COUNTED
        for ok in counted_in_full
    ]
    df[COUNT_STATUS_REASON_COLUMN] = [
        None if ok else _FIXTURE_REASON for ok in counted_in_full
    ]
    return df.sort_values(["year", "state", "candidate"], kind="stable").reset_index(
        drop=True
    )


def roster_frame(
    statuses: dict[int, dict[str, str]], *, source: str = "test"
) -> pd.DataFrame:
    """Build a ``dwh.pv_state_status``-shaped roster from ``{year: {state: status}}``.

    Columns are declared explicitly so the **empty** roster still carries them — a
    ``SELECT`` against an empty table returns a column-bearing frame, and an
    ``EC``-only warehouse (``python -m usvote`` with no PV source loaded) really does
    produce one.
    """
    return pd.DataFrame(
        [
            {"source": source, "year": year, "state": state,
             "pv_status": status, "note": None}
            for year, per_state in statuses.items()
            for state, status in per_state.items()
        ],
        columns=["source", "year", "state", "pv_status", "note"],
    )


def all_popular_vote(df: pd.DataFrame, **overrides: dict[str, str]) -> pd.DataFrame:
    """A roster marking every ``(year, state)`` in ``df`` ``popular_vote``, bar overrides."""
    statuses: dict[int, dict[str, str]] = {}
    for year, state in df[["year", "state"]].drop_duplicates().itertuples(index=False):
        statuses.setdefault(int(year), {})[state] = PV_STATUS_POPULAR_VOTE
    for year_key, per_state in overrides.items():
        statuses.setdefault(int(year_key), {}).update(per_state)
    return roster_frame(statuses)


# --- the 1824 acceptance fixture --------------------------------------------

#: The **real** 1824 electoral map: all 24 participating states, each state's real
#: allotment, and each candidate's real per-state electoral votes — summing to the real
#: national totals (Jackson 99, Adams 84, Crawford 41, Clay 37) over the real 261-vote
#: appointed allotment. Source: the Archives results the EC spine itself is scraped from.
EC_1824: dict[str, tuple[int, dict[str, int]]] = {
    "New York": (36, {"Jackson": 1, "Adams": 26, "Crawford": 5, "Clay": 4}),
    "Pennsylvania": (28, {"Jackson": 28}),
    "Virginia": (24, {"Crawford": 24}),
    "Ohio": (16, {"Clay": 16}),
    "North Carolina": (15, {"Jackson": 15}),
    "Massachusetts": (15, {"Adams": 15}),
    "Kentucky": (14, {"Clay": 14}),
    "Maryland": (11, {"Jackson": 7, "Adams": 3, "Crawford": 1}),
    "South Carolina": (11, {"Jackson": 11}),
    "Tennessee": (11, {"Jackson": 11}),
    "Georgia": (9, {"Crawford": 9}),
    "Maine": (9, {"Adams": 9}),
    "New Hampshire": (8, {"Adams": 8}),
    "Connecticut": (8, {"Adams": 8}),
    "New Jersey": (8, {"Jackson": 8}),
    "Vermont": (7, {"Adams": 7}),
    "Louisiana": (5, {"Jackson": 3, "Adams": 2}),
    "Indiana": (5, {"Jackson": 5}),
    "Alabama": (5, {"Jackson": 5}),
    "Rhode Island": (4, {"Adams": 4}),
    "Illinois": (3, {"Jackson": 2, "Adams": 1}),
    "Mississippi": (3, {"Jackson": 3}),
    "Missouri": (3, {"Clay": 3}),
    "Delaware": (3, {"Adams": 1, "Crawford": 2}),
}

#: The six states that chose electors by **legislature** in 1824 — no popular vote was
#: ever held there (D024 §1/§4). Real; this is what makes 1824 a partial-coverage year.
LEGISLATURE_CHOSEN_1824 = ("Delaware", "Georgia", "Louisiana", "New York", "Vermont",
                           "South Carolina")

#: Per-state popular vote for 1824. The **national totals are real** (Jackson 151,271;
#: Adams 113,122; Clay 47,531; Crawford 40,856 — 352,780 cast); the allocation across
#: these four states is **synthesized**, because the national outcome is what these tests
#: assert and a real 18-state allocation would add transcription risk without adding
#: coverage. Every *other* ``popular_vote`` state is deliberately left with NULL PV — that
#: is not an oversight, it is the fixture proving ``pv_coverage`` is read from the roster
#: and never inferred from a NULL ``candidate_votes``.
PV_1824: dict[str, dict[str, int]] = {
    "Pennsylvania": {"Jackson": 60000, "Adams": 25000, "Clay": 10000, "Crawford": 5000},
    "Ohio": {"Jackson": 40000, "Adams": 30000, "Clay": 20000, "Crawford": 10000},
    "Tennessee": {"Jackson": 30000, "Adams": 28122, "Clay": 10000, "Crawford": 12856},
    "North Carolina": {"Jackson": 21271, "Adams": 30000, "Clay": 7531, "Crawford": 13000},
}

CANDIDATES_1824 = ("Jackson", "Adams", "Crawford", "Clay")


def frame_1824() -> tuple[pd.DataFrame, pd.DataFrame]:
    """The 1824 joined frame + roster — the D041 no-EC-majority acceptance fixture."""
    rows: list[dict[str, object]] = []
    for state, (total_ev, per_candidate) in EC_1824.items():
        state_pv = PV_1824.get(state)
        state_total = float(sum(state_pv.values())) if state_pv else np.nan
        for candidate in CANDIDATES_1824:
            rows.append({
                "year": 1824,
                "state": state,
                "candidate": candidate,
                "total_electoral_votes": total_ev,
                # Dense fact: a candidate who won nothing here is an explicit 0 row.
                "president_electoral_votes": per_candidate.get(candidate, 0),
                "candidate_votes": (
                    float(state_pv[candidate]) if state_pv else np.nan
                ),
                "state_total_votes": state_total,
            })
    df = ec_pv_frame(rows, took_office={1824: "Adams"})
    roster = roster_frame({
        1824: {
            state: (
                PV_STATUS_LEGISLATURE_CHOSEN
                if state in LEGISLATURE_CHOSEN_1824
                else PV_STATUS_POPULAR_VOTE
            )
            for state in EC_1824
        }
    })
    return df, roster


def full_coverage_frame() -> pd.DataFrame:
    """A two-state, two-candidate year where every state held a popular vote.

    The generic full-coverage shape: pair it with :func:`all_popular_vote` and both
    coverage policies must agree exactly, since there is nothing to restrict.
    """
    return ec_pv_frame([
        {"year": 2000, "state": s, "candidate": c,
         "total_electoral_votes": ev,
         "president_electoral_votes": ev if c == w else 0,
         "candidate_votes": v, "state_total_votes": 100.0}
        for s, ev, w, votes in (("Ohio", 21, "A", (60.0, 40.0)),
                                ("Iowa", 7, "B", (45.0, 55.0)))
        for c, v in zip(("A", "B"), votes, strict=True)
    ])


# --- roll_up_national (the extracted primitive) -----------------------------


class TestRollUpNational:
    def test_pv_sum_keeps_min_count_so_a_no_pv_getter_stays_null(self) -> None:
        """A getter with no PV must stay NULL, never a fabricated 0 (D005/D026 §2)."""
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20,
             "candidate_votes": 100.0, "state_total_votes": 150.0},
            # B is a getter in the same year with no PV anywhere.
            {"year": 2000, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 20, "president_electoral_votes": 0,
             "candidate_votes": np.nan, "state_total_votes": 150.0},
        ])
        out = hybrid.roll_up_national(
            df,
            key=("year", "candidate_id"),
            carry={"candidate": "candidate"},
        )
        b = out.loc[out["candidate"] == "B", "national_pv_votes"]
        assert b.isna().all(), "a no-PV getter must be NULL, not 0"

    def test_denominator_dedups_per_state_and_survives_a_null_bearing_row(self) -> None:
        """Per-``(year, state)`` ``max`` (skip-NA) *then* sum — the snapshot's subtlety.

        A faithless/no-PV getter carries a NULL ``state_total_votes`` on its row. Taking
        the per-state ``max`` skips it, so the state stays in the national denominator; a
        naive first-row dedup would drop the whole state whenever the NULL row sorted
        first.

        **The NULL-bearing getter is named so it sorts first**, which is what lets this
        test fail: with the non-NULL row sorting first, a ``drop_duplicates`` regression
        would keep the good row and the assertion would still pass — pinning the outcome
        on a fixture that cannot express the hazard its own docstring names.
        """
        df = ec_pv_frame([
            {"year": 1976, "state": "Ohio", "candidate": "Zeta",
             "total_electoral_votes": 25, "president_electoral_votes": 25,
             "candidate_votes": 60.0, "state_total_votes": 100.0},
            # Sorts before "Zeta", so a first-row dedup keeps THIS row and loses Ohio.
            {"year": 1976, "state": "Ohio", "candidate": "Aardvark",
             "total_electoral_votes": 25, "president_electoral_votes": 0,
             "candidate_votes": np.nan, "state_total_votes": np.nan},
            {"year": 1976, "state": "Iowa", "candidate": "Zeta",
             "total_electoral_votes": 8, "president_electoral_votes": 0,
             "candidate_votes": 30.0, "state_total_votes": 70.0},
            {"year": 1976, "state": "Iowa", "candidate": "Aardvark",
             "total_electoral_votes": 8, "president_electoral_votes": 8,
             "candidate_votes": 40.0, "state_total_votes": 70.0},
        ])
        out = hybrid.roll_up_national(
            df, key=("year", "candidate_id"), carry={"candidate": "candidate"}
        )
        # 100 + 70 — each state counted ONCE, and Ohio not dropped by its NULL row.
        assert set(out["national_pv_denominator"]) == {170.0}

    def test_all_null_pv_year_keeps_the_denominator_null_not_zero(self) -> None:
        """The **second** ``min_count=1``: an all-NULL-PV year → NULL, never 0.

        Without it the year's denominator becomes ``0`` and every ``pv_share`` divides by
        zero. This is the pre-1976 shape of the MIT-only redistributable surface, so it is
        the common case, not an edge case.
        """
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 23, "president_electoral_votes": 23},
            {"year": 1900, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 23, "president_electoral_votes": 0},
        ])
        out = hybrid.roll_up_national(
            df, key=("year", "candidate_id"), carry={"candidate": "candidate"}
        )
        assert out["national_pv_denominator"].isna().all()
        assert out["national_pv_votes"].isna().all()

    def test_key_is_parameterized_so_the_snapshot_can_group_on_its_public_slug(
        self,
    ) -> None:
        """The whole point of the extraction: same derivation, caller's group key."""
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20,
             "candidate_votes": 90.0, "state_total_votes": 150.0},
            {"year": 2000, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 20, "president_electoral_votes": 0,
             "candidate_votes": 60.0, "state_total_votes": 150.0},
        ])
        df["candidate_slug"] = df["candidate"].str.lower()
        by_id = hybrid.roll_up_national(
            df, key=("year", "candidate_id"), carry={"candidate": "candidate"}
        )
        by_slug = hybrid.roll_up_national(
            df, key=("year", "candidate_slug"), carry={"candidate": "candidate"}
        )
        assert "candidate_slug" in by_slug.columns
        assert "candidate_id" not in by_slug.columns
        for frame in (by_id, by_slug):
            assert sorted(frame["national_pv_votes"]) == [60.0, 90.0]
            assert set(frame["national_pv_denominator"]) == {150.0}

    def test_key_must_contain_year_because_the_denominator_is_per_year(self) -> None:
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20},
        ])
        with pytest.raises(hybrid.HybridError, match="year"):
            hybrid.roll_up_national(
                df, key=("candidate_id",), carry={"candidate": "candidate"}
            )

    def test_carry_may_not_shadow_a_derived_column(self) -> None:
        """A ``carry`` entry named like a derived output would silently win or collide."""
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20},
        ])
        with pytest.raises(hybrid.HybridError, match="national_pv_votes"):
            hybrid.roll_up_national(
                df,
                key=("year", "candidate_id"),
                carry={"national_pv_votes": "candidate_votes"},
            )


# --- ec_denominator ---------------------------------------------------------


class TestEcDenominator:
    def test_counts_each_state_once_not_once_per_candidate(self) -> None:
        """A bare aggregate would multiply each state's allotment by the candidate count."""
        df = ec_pv_frame([
            {"year": 2000, "state": s, "candidate": c,
             "total_electoral_votes": ev, "president_electoral_votes": pev}
            for s, ev, wins in (("Ohio", 21, "A"), ("Iowa", 7, "B"))
            for c, pev in (("A", ev if wins == "A" else 0),
                           ("B", ev if wins == "B" else 0),
                           ("C", 0))
        ])
        out = hybrid.ec_denominator_by_year(df)
        assert out.loc[out["year"] == 2000, "ec_denominator"].iloc[0] == 28
        # The bare-aggregate bug would give 28 * 3 candidates.
        assert df["total_electoral_votes"].sum() == 84

    def test_includes_legislature_chosen_states_allotment(self) -> None:
        """The EC denominator is the **appointed** allotment — coverage never trims it.

        The mirror-image of ``national_pv_denominator``, which *does* drop those states
        (their PV is NULL). The two denominators look parallel and are not; that
        divergence is the entire reason D037 splits the EC share in two.
        """
        df, roster = frame_1824()
        assert hybrid.ec_denominator_by_year(df)["ec_denominator"].iloc[0] == 261
        legislature_ev = sum(
            EC_1824[s][0] for s in LEGISLATURE_CHOSEN_1824
        )
        assert legislature_ev == 71  # real: DE 3 + GA 9 + LA 5 + NY 36 + VT 7 + SC 11
        frame = hybrid.build_hybrid_frame(df, roster)
        # ... while the PV denominator counts only the states that actually voted.
        assert frame["national_pv_denominator"].iloc[0] == 352780.0

    def test_a_state_whose_allotment_varies_by_candidate_row_raises(self) -> None:
        """``total_electoral_votes`` is a per-state allotment broadcast onto every row.

        If that ever stops holding, a DISTINCT-based denominator becomes ambiguous — so it
        fails loud rather than silently picking one value.
        """
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 21, "president_electoral_votes": 21},
            {"year": 2000, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 20, "president_electoral_votes": 0},
        ])
        with pytest.raises(hybrid.HybridError, match="total_electoral_votes"):
            hybrid.ec_denominator_by_year(df)


# --- the roster read + pv_coverage ------------------------------------------


class TestCoverage:
    def test_pv_coverage_is_ev_weighted_not_state_count_weighted(self) -> None:
        """D024 §8: Σ EV over ``popular_vote`` states ÷ the full appointed allotment."""
        df, roster = frame_1824()
        coverage = hybrid.pv_coverage_by_year(df, roster)
        got = coverage.loc[coverage["year"] == 1824, "pv_coverage"].iloc[0]
        assert got == pytest.approx((261 - 71) / 261)
        # State-count weighting would give 18/24 = 0.75 — close enough to the EV-weighted
        # 0.728 to pass a loose assertion, which is why this pins the exact value.
        assert got != pytest.approx(18 / 24)

    def test_a_full_popular_vote_year_is_exactly_one(self) -> None:
        df = ec_pv_frame([
            {"year": 2000, "state": s, "candidate": "A",
             "total_electoral_votes": ev, "president_electoral_votes": ev}
            for s, ev in (("Ohio", 21), ("Iowa", 7))
        ])
        coverage = hybrid.pv_coverage_by_year(df, all_popular_vote(df))
        assert coverage["pv_coverage"].iloc[0] == 1.0

    def test_coverage_is_roster_driven_never_inferred_from_a_null_pv_cell(self) -> None:
        """The forbidden inference (D024's no-``unknown`` design).

        Two states with an identical *data* shape — EV cast, ``candidate_votes`` NULL —
        and opposite roster statuses. Coverage must follow the roster, so the
        ``popular_vote`` state (simply uncovered by the source) must **not** reduce
        coverage, while the ``legislature_chosen`` state (where no popular vote ever
        existed) must.
        """
        df = ec_pv_frame([
            {"year": 1876, "state": s, "candidate": "A",
             "total_electoral_votes": 10, "president_electoral_votes": 10}
            for s in ("Colorado", "Ohio")
        ])
        assert df["candidate_votes"].isna().all()  # identical data shape
        roster = roster_frame({
            1876: {
                "Colorado": PV_STATUS_LEGISLATURE_CHOSEN,
                "Ohio": PV_STATUS_POPULAR_VOTE,
            }
        })
        coverage = hybrid.pv_coverage_by_year(df, roster)
        assert coverage["pv_coverage"].iloc[0] == pytest.approx(0.5)

        flipped = roster_frame({
            1876: {
                "Colorado": PV_STATUS_POPULAR_VOTE,
                "Ohio": PV_STATUS_POPULAR_VOTE,
            }
        })
        assert hybrid.pv_coverage_by_year(df, flipped)["pv_coverage"].iloc[0] == 1.0

    def test_not_participating_states_do_not_count_as_covered(self) -> None:
        df = ec_pv_frame([
            {"year": 1864, "state": s, "candidate": "A",
             "total_electoral_votes": 10, "president_electoral_votes": 10}
            for s in ("Ohio", "Nevada")
        ])
        roster = roster_frame({
            1864: {"Ohio": PV_STATUS_POPULAR_VOTE,
                   "Nevada": PV_STATUS_NOT_PARTICIPATING}
        })
        assert hybrid.pv_coverage_by_year(df, roster)["pv_coverage"].iloc[0] == 0.5

    def test_a_year_absent_from_the_roster_gets_null_coverage_not_zero(self) -> None:
        """Unknown coverage is NULL. ``0.0`` would assert "no state voted" (D005)."""
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 23, "president_electoral_votes": 23},
        ])
        coverage = hybrid.pv_coverage_by_year(df, roster_frame({}))
        assert coverage["pv_coverage"].isna().all()

    def test_multi_source_roster_agreeing_is_collapsed_not_fanned_out(self) -> None:
        """``dwh.pv_state_status`` is keyed on ``(source, year, state)``.

        The 1976-2024 overlap therefore carries MIT *and* UCSB rows per state. Where they
        agree — which is the normal case, every state having voted — the roster collapses
        cleanly instead of double-counting the state's EV into the coverage numerator.
        """
        df = ec_pv_frame([
            {"year": 1976, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 25, "president_electoral_votes": 25},
        ])
        both = pd.concat([
            roster_frame({1976: {"Ohio": PV_STATUS_POPULAR_VOTE}}, source="mit"),
            roster_frame({1976: {"Ohio": PV_STATUS_POPULAR_VOTE}}, source="ucsb"),
        ])
        assert hybrid.pv_coverage_by_year(df, both)["pv_coverage"].iloc[0] == 1.0

    def test_multi_source_roster_disagreeing_raises(self) -> None:
        """A genuine cross-source status disagreement is a data bug, not a tiebreak."""
        df = ec_pv_frame([
            {"year": 1976, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 25, "president_electoral_votes": 25},
        ])
        conflicting = pd.concat([
            roster_frame({1976: {"Ohio": PV_STATUS_POPULAR_VOTE}}, source="mit"),
            roster_frame({1976: {"Ohio": PV_STATUS_LEGISLATURE_CHOSEN}}, source="ucsb"),
        ])
        with pytest.raises(hybrid.HybridError, match="disagree"):
            hybrid.pv_coverage_by_year(df, conflicting)


# --- the coverage policy (b) ------------------------------------------------


class TestCoveragePolicy:
    def test_policy_b_leaves_the_hybrid_ec_share_equal_to_the_full_share(self) -> None:
        """(b, shipped, D038): mismatched denominators, flagged — not restricted."""
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        assert (frame["ec_share_hybrid"] == frame["ec_share_full"]).all()
        assert frame["pv_coverage"].iloc[0] < 1.0

    def test_a_full_coverage_year_degrades_the_policy_to_identity(self) -> None:
        """Where coverage is 1.0 there is nothing to restrict, so (b) is the identity."""
        df = full_coverage_frame()
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        assert (frame["ec_share_hybrid"] == frame["ec_share_full"]).all()
        assert (frame["pv_coverage"] == 1.0).all()


def _national_1824(df: pd.DataFrame) -> pd.DataFrame:
    """The national frame ``apply_coverage_policy`` expects, built the way the builder does."""
    national = hybrid.roll_up_national(
        df,
        key=hybrid.HYBRID_CANDIDATE_GRAIN,
        carry={"candidate": "candidate", "national_electoral_votes":
               "national_electoral_votes"},
    ).merge(hybrid.ec_denominator_by_year(df), on="year", how="left")
    national["ec_share_full"] = (
        national["national_electoral_votes"] / national["ec_denominator"]
    )
    return national


class TestCoveragePolicySwitch:
    """E7-S3 (#122): the ``policy`` argument and the (c) restricted-denominator branch."""

    def test_the_two_policies_are_named_constants_with_a_literal_alias(self) -> None:
        """mypy is enforced, so the switch is a ``Literal``, not a bare string."""
        assert hybrid.COVERAGE_POLICIES == (
            hybrid.COVERAGE_POLICY_MISMATCHED,
            hybrid.COVERAGE_POLICY_RESTRICTED,
        )
        assert hybrid.COVERAGE_POLICY_MISMATCHED != hybrid.COVERAGE_POLICY_RESTRICTED

    def test_the_policy_argument_is_keyword_only(self) -> None:
        """Positional use must fail: the shipped signature is ``(national, ec, roster)``."""
        df, roster = frame_1824()
        national = _national_1824(df)
        with pytest.raises(TypeError):
            hybrid.apply_coverage_policy(  # type: ignore[misc]
                national, df, roster, hybrid.COVERAGE_POLICY_RESTRICTED
            )

    def test_the_default_is_b_the_shipped_rule(self) -> None:
        """D038: (b) is settled and stays the only configured rule."""
        df, roster = frame_1824()
        default = hybrid.build_hybrid_frame(df, roster)
        explicit_b = hybrid.build_hybrid_frame(
            df, roster, policy=hybrid.COVERAGE_POLICY_MISMATCHED
        )
        pd.testing.assert_frame_equal(default, explicit_b)

    def test_an_unrecognized_policy_raises(self) -> None:
        df, roster = frame_1824()
        with pytest.raises(hybrid.HybridError, match="coverage policy"):
            hybrid.build_hybrid_frame(df, roster, policy="restrict-everything")  # type: ignore[arg-type]

    def test_c_restricts_both_halves_of_the_ec_share(self) -> None:
        """1824 under (c): Jackson 84/190, Adams 48/190 — numerator restricted too.

        The six legislature-chosen states hold 71 of 261 electoral votes, so the
        restricted denominator is 190. Jackson holds 15 EV *in those states* (New York 1,
        Louisiana 3, South Carolina 11), so his restricted numerator is 99 - 15 = **84**.
        Adams holds 36 there (New York 26, Louisiana 2, Vermont 7, Delaware 1) → 48.
        """
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(
            df, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        ).set_index("candidate")
        assert frame.loc["Jackson", "ec_share_hybrid"] == pytest.approx(84 / 190)
        assert frame.loc["Adams", "ec_share_hybrid"] == pytest.approx(48 / 190)
        assert frame.loc["Crawford", "ec_share_hybrid"] == pytest.approx(25 / 190)
        assert frame.loc["Clay", "ec_share_hybrid"] == pytest.approx(33 / 190)

    def test_c_does_not_reuse_the_all_states_window_sum_as_its_numerator(self) -> None:
        """The bug the AC names: a full numerator over a restricted denominator.

        ``national_electoral_votes`` is the window SUM over *every* state, so pairing it
        with the 190 denominator would read Jackson at 99/190 = 0.52 — over the majority
        line, and the exact mistake the D037/A split exists to make harmless. Pin that the
        implementation does **not** do it.
        """
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(
            df, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        ).set_index("candidate")
        assert frame.loc["Jackson", "ec_share_hybrid"] != pytest.approx(99 / 190)
        assert frame.loc["Jackson", "ec_share_hybrid"] < 0.5

    def test_1824_same_winner_but_the_margin_nearly_doubles(self) -> None:
        """The whole reason the switch exists: (b) and (c) are not the same answer."""
        df, roster = frame_1824()
        margins = {}
        for policy in hybrid.COVERAGE_POLICIES:
            frame = hybrid.build_hybrid_frame(df, roster, policy=policy)
            top2 = frame["hybrid_score"].nlargest(2)
            summary = hybrid.build_hybrid_summary(frame)
            assert summary["hybrid_winner"].iloc[0] == "Jackson"
            margins[policy] = top2.iloc[0] - top2.iloc[1]
        assert margins[hybrid.COVERAGE_POLICY_MISMATCHED] == pytest.approx(0.0828, abs=1e-4)
        assert margins[hybrid.COVERAGE_POLICY_RESTRICTED] == pytest.approx(0.1488, abs=1e-4)

    def test_pv_share_is_untouched_by_the_policy(self) -> None:
        """(c) restricts the EC half alone — the PV denominator is already PV-only."""
        df, roster = frame_1824()
        b = hybrid.build_hybrid_frame(df, roster)
        c = hybrid.build_hybrid_frame(
            df, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        )
        pd.testing.assert_series_equal(b["pv_share"], c["pv_share"])
        pd.testing.assert_series_equal(b["pv_coverage"], c["pv_coverage"])

    def test_ec_share_full_and_determinative_survive_both_policies(self) -> None:
        """D037/A on the first policy that could break it, asserted directly."""
        df, roster = frame_1824()
        b = hybrid.build_hybrid_frame(df, roster)
        c = hybrid.build_hybrid_frame(
            df, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        )
        pd.testing.assert_series_equal(b["ec_share_full"], c["ec_share_full"])
        for frame in (b, c):
            summary = hybrid.build_hybrid_summary(frame)
            # Populated-and-False, not NULL: 1824 had no EC majority, which is a known
            # fact about the election, never a "we could not tell" (D041). The separate
            # notna() assert that used to guard this line is gone: non_null_flag rejects
            # every NULL spelling itself, so the safety no longer depends on a neighbour.
            assert non_null_flag(
                summary["ec_determinative"].iloc[0], label="1824 ec_determinative"
            ) is False
            assert summary["ec_winner"].iloc[0] == "Jackson"

    def test_a_full_coverage_year_makes_the_two_policies_identical(self) -> None:
        """Property (i): where coverage is 1.0 the restriction is a genuine no-op.

        Surface-independent — a property of the policy function, not of any view. This is
        the real content behind "the redistributable surface is policy-invariant", and it
        holds for every fully-covered year on every surface.
        """
        df = full_coverage_frame()
        roster = all_popular_vote(df)
        pd.testing.assert_frame_equal(
            hybrid.build_hybrid_frame(df, roster),
            hybrid.build_hybrid_frame(
                df, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
            ),
        )

    def test_a_roster_absent_year_yields_null_never_a_divide_by_zero(self) -> None:
        """NULL path (a): the year is not in the roster, so the numerator is already NA.

        Distinct from path (b) below — here ``covered_electoral_votes`` is NA and the
        division propagates NA without the zero-denominator guard ever firing.
        """
        df = full_coverage_frame()
        empty = roster_frame({})
        frame = hybrid.build_hybrid_frame(
            df, empty, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        )
        assert frame["ec_share_hybrid"].isna().all()
        assert frame["hybrid_score"].isna().all()
        assert not np.isinf(frame["ec_share_hybrid"].astype("float64").fillna(0)).any()
        # ...while the policy-invariant half is computed exactly as always.
        assert frame["ec_share_full"].notna().all()

    def test_an_all_absence_year_in_the_roster_yields_null_not_infinity(self) -> None:
        """NULL path (b): the year *is* in the roster, with zero ``popular_vote`` states.

        It differs from the test above in what ``pv_coverage`` **reports** — a real
        ``0.0`` (coverage known, and known to be none) rather than NULL (unknown) — not in
        how the share becomes NULL. Both reach NULL through the *numerator*: the restricted
        state set is empty either way, so ``_restricted_ec_numerator`` returns no rows.

        An earlier commit added a zero-denominator guard for this case and this test
        claimed to exercise it; AC-verify proved the guard **unreachable** (deleting it
        killed no test) and it was removed. Nothing here covers a zero-denominator path,
        because the join view cannot produce a non-NULL numerator over one.
        """
        df = full_coverage_frame()
        roster = roster_frame({
            2000: {
                "Ohio": PV_STATUS_LEGISLATURE_CHOSEN,
                "Iowa": PV_STATUS_NOT_PARTICIPATING,
            }
        })
        frame = hybrid.build_hybrid_frame(
            df, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        )
        # The year IS in the roster, so coverage is a real 0.0 — not NULL. That is what
        # makes this a different path from the test above.
        assert (frame["pv_coverage"] == 0.0).all()
        assert frame["ec_share_hybrid"].isna().all()
        assert not np.isinf(frame["ec_share_hybrid"].astype("float64").fillna(0)).any()
        assert frame["hybrid_score"].isna().all()

    def test_the_two_null_paths_are_genuinely_different_code_paths(self) -> None:
        """Guard the distinction itself: same NULL share, different ``pv_coverage``."""
        df = full_coverage_frame()
        absent = hybrid.build_hybrid_frame(
            df, roster_frame({}), policy=hybrid.COVERAGE_POLICY_RESTRICTED
        )
        all_absence = hybrid.build_hybrid_frame(
            df,
            roster_frame({2000: {"Ohio": PV_STATUS_LEGISLATURE_CHOSEN,
                                 "Iowa": PV_STATUS_LEGISLATURE_CHOSEN}}),
            policy=hybrid.COVERAGE_POLICY_RESTRICTED,
        )
        assert absent["pv_coverage"].isna().all()      # unknown
        assert (all_absence["pv_coverage"] == 0.0).all()  # known, and known to be zero
        assert absent["ec_share_hybrid"].isna().all()
        assert all_absence["ec_share_hybrid"].isna().all()

    def test_the_policy_reaches_the_db_entry_point(self) -> None:
        """Plumbed all the way through, so a whole frame can be built either way.

        Post-#127 the divergence is *year-shaped*, which is a sharper signal than the
        old all-or-nothing one: (c) restricts 1900 (no MIT roster row reaches it) to an
        empty state set while leaving 1976 (fully covered) untouched. If the ``policy``
        argument stopped being forwarded, 1900 would come back populated.
        """
        df, roster = _mixed_surface()
        frame, _ = hybrid.build_hybrid_from_db(
            cast("Any", _StubDBC(df, roster)),
            view="ec_pv_redistributable",
            policy=hybrid.COVERAGE_POLICY_RESTRICTED,
        )
        # Boolean-mask form, not ``.set_index('year').loc[1900]``: the latter returns a
        # scalar (not a Series) the moment a year has a single candidate, and ``.isna()``
        # would raise AttributeError — reading as a broken test, not a policy regression.
        assert frame.loc[frame["year"] == 1900, "ec_share_hybrid"].isna().all()
        assert frame.loc[frame["year"] == 1976, "ec_share_hybrid"].notna().all()

    def test_the_two_policies_agree_exactly_where_the_mit_roster_reaches(self) -> None:
        """Property (ii), resolved by #127 — the canary #122 left has now fired.

        #122 pinned the *pre-backfill* truth: the roster was UCSB-only, so scoping to MIT
        found nothing and (c) restricted to an empty state set in **every** year, making
        the two policies differ everywhere. Its docstring said this assertion "must be
        revisited when #127 backfills MIT's roster rows". It has been.

        The post-backfill truth is the one the original AC actually wanted, now scoped
        honestly: **the policies agree exactly where coverage is complete** — 1976 reads
        ``pv_coverage == 1.0``, so restricting to popular-vote states is a no-op and (b)
        and (c) produce identical shares. They still differ on 1900, and must: no
        MIT-sourced roster row reaches that year, so (c) has no covered states to restrict
        to. Agreement is therefore a *property of coverage*, not of the surface — which is
        why it could never have been the byte-identity the AC first claimed. What
        unblocks #102 remains :func:`test_nothing_configures_a_policy_other_than_b`.
        """
        df, roster = _mixed_surface()
        b, _ = hybrid.build_hybrid_from_db(
            cast("Any", _StubDBC(df, roster)), view="ec_pv_redistributable"
        )
        c, _ = hybrid.build_hybrid_from_db(
            cast("Any", _StubDBC(df, roster)),
            view="ec_pv_redistributable",
            policy=hybrid.COVERAGE_POLICY_RESTRICTED,
        )
        # Fully covered → the restriction is a no-op and the two policies coincide.
        pd.testing.assert_frame_equal(
            b[b["year"] == 1976].reset_index(drop=True),
            c[c["year"] == 1976].reset_index(drop=True),
        )
        # Uncovered → (b) keeps the full EC share, (c) has nothing to restrict to.
        assert b.loc[b["year"] == 1900, "ec_share_hybrid"].notna().all()
        assert c.loc[c["year"] == 1900, "ec_share_hybrid"].isna().all()


#: Every function that actually accepts a ``policy``. A ``policy=`` keyword on anything
#: else is somebody's unrelated kwarg, not a coverage selection.
#:
#: ``build_hybrid_from_frames`` was missing here until #178 and is the one that matters
#: most now: it is the derivation **both** production paths reach — ``create_hybrid_views``
#: since #178, and ``snapshot.build_snapshot`` since #102 — so a
#: ``build_hybrid_from_frames(df, roster, policy=chosen)`` added to ``snapshot.py`` would
#: have shipped policy (c) on the public API with this guard staying green. Its absence
#: predated #178; that change is what moved the load-bearing call onto it.
_POLICY_TAKERS = frozenset({
    "apply_coverage_policy",
    "build_hybrid_frame",
    "build_hybrid_from_db",
    "build_hybrid_from_frames",
})


def _policy_selections(source: str, module: str) -> list[str]:
    """Every place ``source`` selects a coverage policy, as ``module:line`` strings.

    Three ways to select one: name a ``COVERAGE_POLICY_*`` constant, **import** one under
    an alias (which erases the name from every later reference, so the import itself is
    the only place it is visible), or pass ``policy=`` to a function that takes one.
    Parsed rather than grepped — see the guard test below for why both substring attempts
    had holes.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom | ast.Import):
            found += [
                f"{module}:{node.lineno} imports {alias.name}"
                for alias in node.names
                if alias.name.startswith("COVERAGE_POLICY")
            ]
        elif isinstance(node, ast.Name) and node.id.startswith("COVERAGE_POLICY"):
            found.append(f"{module}:{node.lineno} names {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("COVERAGE_POLICY"):
            found.append(f"{module}:{node.lineno} names {node.attr}")
        elif isinstance(node, ast.Call):
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", None)
            )
            if called in _POLICY_TAKERS and any(
                kw.arg == "policy" for kw in node.keywords
            ):
                found.append(f"{module}:{node.lineno} passes policy= to {called}")
    return found


@pytest.mark.parametrize(
    "source",
    [
        'build_hybrid_from_db(dbc, policy="restricted")',
        'build_hybrid_from_db(dbc, policy = "restricted")',  # the whitespace hole
        "hybrid.build_hybrid_frame(df, roster, policy=chosen)",
        "apply_coverage_policy(n, e, r, policy=COVERAGE_POLICY_RESTRICTED)",
        "x = hybrid.COVERAGE_POLICY_RESTRICTED",
        "from usvote.hybrid import COVERAGE_POLICY_RESTRICTED as p\nuse(p)",
    ],
)
def test_the_policy_guard_catches_every_way_of_selecting_one(source: str) -> None:
    """Positive cases — each must be flagged (#122, code review)."""
    assert _policy_selections(source, "m.py")


@pytest.mark.parametrize(
    "source",
    [
        "build_hybrid_from_db(dbc)",
        "build_hybrid_from_db(dbc, view=EC_PV_REDISTRIBUTABLE_VIEW)",
        'fetch(url, retry_policy="aggressive")',  # somebody else's kwarg
        'cache(key, cache_policy="lru")',
        '"""Docs mentioning policy= and COVERAGE_POLICY_RESTRICTED."""',
        "# a comment about policy = restricted",
    ],
)
def test_the_policy_guard_does_not_cry_wolf(source: str) -> None:
    """Negative cases — none configures coverage, so none may fail CI (#122)."""
    assert _policy_selections(source, "m.py") == []


def test_nothing_configures_a_policy_other_than_b() -> None:
    """Property (iii) — what actually unblocks #102 (#122).

    (b) is the shipped rule (D038) and (c) is reachable only by an explicit argument. No
    production call site passes one: #124 materializes the views from the default, and
    ``warehouse.py`` never names a policy. Greppable, in the manner of the repo's other
    layering invariants — a future call site that hardcodes (c) has to defeat this test.

    **Matched on the AST, not on source text**, following the precedent #121 set when its
    back-import guard missed ``from usvote import hybrid``. Two rounds of substring
    matching each had a hole: scanning for the constant names alone let a bare
    ``policy="restricted"`` through (AC-verify), and scanning for the literal ``"policy="``
    missed ``policy = "restricted"`` with spaces — which ruff does **not** reject either,
    since E251 is not in the project's stable ``E`` selection and CI never runs
    ``ruff format --check`` (code review). mypy accepts both, since ``"restricted"`` is a
    valid ``Literal`` member. The argument that #102 needs no policy parameter rests
    entirely on this test, so it may not have a hole that wide.

    Matching the parsed tree also makes it **narrow**: a ``policy=`` keyword counts only on
    a call to one of the functions that actually take one (:data:`_POLICY_TAKERS`), so an
    unrelated
    ``cache_policy=``/``retry_policy=`` elsewhere in the package — or the word in a comment
    or docstring — is not a false accusation of configuring coverage.
    """
    src = Path(hybrid.__file__).parent
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        if path.name == "hybrid.py":
            continue
        offenders += _policy_selections(
            path.read_text(encoding="utf-8"), path.relative_to(src).as_posix()
        )
    assert offenders == [], (
        "these call sites select a coverage policy; (b) is the only shipped rule (D038) "
        f"and no production caller may choose one: {offenders}"
    )


def test_the_policy_functions_own_default_is_b() -> None:
    """Pin the exported function's documented default, not only the builders' (#122).

    ``apply_coverage_policy`` is in ``__all__``, so its default is part of the contract
    even though every in-repo caller passes ``policy=`` explicitly. AC-verify caught that
    flipping it to (c) killed no test.
    """
    df, roster = frame_1824()
    national = _national_1824(df)
    defaulted = hybrid.apply_coverage_policy(national, df, roster)
    assert (defaulted["ec_share_hybrid"] == defaulted["ec_share_full"]).all()
    assert (
        inspect.signature(hybrid.apply_coverage_policy).parameters["policy"].default
        == hybrid.COVERAGE_POLICY_MISMATCHED
    )


# --- the three method scores + winners --------------------------------------


class TestThreeMethodScores:
    def test_hybrid_score_is_the_mean_of_the_two_shares(self) -> None:
        """D037: ``(ec_share_hybrid + pv_share) / 2`` — the average of two ratios."""
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        expected = (frame["ec_share_hybrid"] + frame["pv_share"]) / 2
        pd.testing.assert_series_equal(
            frame["hybrid_score"], expected, check_names=False
        )

    def test_1824_hybrid_winner_is_jackson_with_a_majority_of_neither(self) -> None:
        """The D037/D041 headline fixture: the case the hybrid exists to speak to."""
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        summary = hybrid.build_hybrid_summary(frame)
        row = summary.iloc[0]

        assert row["ec_winner"] == "Jackson"
        assert row["pv_winner"] == "Jackson"
        assert row["hybrid_winner"] == "Jackson"
        # Yet the House chose Adams — rank 1 and took_office genuinely diverge, and
        # took_office is the per-candidate boolean the spine actually carries.
        by_name = frame.set_index("candidate")["took_office"]
        assert non_null_flag(by_name["Adams"], label="1824 Adams took_office") is True
        assert (
            non_null_flag(by_name["Jackson"], label="1824 Jackson took_office") is False
        )
        assert by_name.sum() == 1  # exactly one office-holder
        jackson = frame.loc[frame["candidate"] == "Jackson"].iloc[0]
        assert jackson["president_electoral_rank"] == 1
        # A majority of neither: 99/261 electoral, 151,271/352,780 popular.
        assert jackson["ec_share_full"] == pytest.approx(99 / 261)
        assert jackson["pv_share"] == pytest.approx(151271 / 352780)
        assert not row["ec_determinative"]

    def test_1824_ec_determinative_and_pv_coverage_are_orthogonal(self) -> None:
        """Both are populated, and neither is a null-because-broken (D041)."""
        df, roster = frame_1824()
        summary = hybrid.build_hybrid_summary(hybrid.build_hybrid_frame(df, roster))
        row = summary.iloc[0]
        # One call replaces the old `is False or == False` straddle and the pd.notna line
        # beneath it: the straddle existed only because `np.bool_(False) is False` is
        # False, which the helper's Python-singleton return removes.
        assert (
            non_null_flag(row["ec_determinative"], label="1824 ec_determinative")
            is False
        )
        assert row["pv_coverage"] == pytest.approx(190 / 261)
        assert pd.notna(row["pv_coverage"])

    def test_1824_all_four_getters_carry_a_score(self) -> None:
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        assert set(frame["candidate"]) == set(CANDIDATES_1824)
        assert frame["hybrid_score"].notna().all()
        assert frame["ec_share_full"].sum() == pytest.approx(1.0)  # 261 of 261 cast

    def test_the_internal_candidate_id_is_carried_and_no_slug_is_minted(self) -> None:
        """D006: the public slug is a snapshot concern (#102), not a warehouse one."""
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        assert "candidate_id" in frame.columns
        assert "candidate" in frame.columns
        assert "candidate_slug" not in frame.columns


# --- D041: the appointed allotment and the <= 1.0 property ------------------


class TestAppointedAllotment:
    def test_2000_ec_shares_sum_under_one_because_of_the_dc_abstention(self) -> None:
        """The D041 ``<= 1.0`` fixture, on a **real** 2000 subset.

        Five real states with their real 2000 allotments, including the real DC
        abstention: DC's ``total_electoral_votes`` stays **3** (the allotment) while only
        **2** were cast (``ELECTORAL_VOTE_SHORTFALLS``). So the shares sum to 146/147 —
        strictly under 1.0. Nationally the same shape gives 537 cast of 538 appointed.
        """
        real_2000 = {
            "California": (54, "Gore"),
            "New York": (33, "Gore"),
            "Texas": (32, "Bush"),
            "Florida": (25, "Bush"),
        }
        rows: list[dict[str, object]] = [
            {"year": 2000, "state": state, "candidate": candidate,
             "total_electoral_votes": ev,
             "president_electoral_votes": ev if candidate == winner else 0}
            for state, (ev, winner) in real_2000.items()
            for candidate in ("Bush", "Gore")
        ]
        # DC: allotted 3, cast 2 — one elector abstained.
        rows += [
            {"year": 2000, "state": "District of Columbia", "candidate": "Gore",
             "total_electoral_votes": 3, "president_electoral_votes": 2},
            {"year": 2000, "state": "District of Columbia", "candidate": "Bush",
             "total_electoral_votes": 3, "president_electoral_votes": 0},
        ]
        df = ec_pv_frame(rows)
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))

        assert frame["ec_denominator"].iloc[0] == 147  # appointed
        assert frame["national_electoral_votes"].sum() == 146  # cast
        total_share = frame["ec_share_full"].sum()
        assert total_share < 1.0
        assert total_share == pytest.approx(146 / 147)
        hybrid.assert_ec_shares_le_one(frame)  # the guard must accept this

    def test_ec_share_full_divides_by_appointed_not_by_votes_cast(self) -> None:
        """2000's national arithmetic: Bush is **271 of 538**, not 269 of 537.

        The allotments here are synthesized (two aggregate states) so the national
        totals — 271/267 cast of a 538 appointed allotment — can be pinned exactly; that
        ratio is the real one, and it is what makes the strict-majority test pass.
        """
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "Bush",
             "total_electoral_votes": 271, "president_electoral_votes": 271},
            {"year": 2000, "state": "Ohio", "candidate": "Gore",
             "total_electoral_votes": 271, "president_electoral_votes": 0},
            {"year": 2000, "state": "Iowa", "candidate": "Bush",
             "total_electoral_votes": 267, "president_electoral_votes": 0},
            # 266 cast of 267 allotted — the abstention.
            {"year": 2000, "state": "Iowa", "candidate": "Gore",
             "total_electoral_votes": 267, "president_electoral_votes": 266},
        ])
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        bush = frame.loc[frame["candidate"] == "Bush"].iloc[0]
        assert bush["ec_denominator"] == 538
        assert bush["ec_share_full"] == pytest.approx(271 / 538)
        assert bush["ec_share_full"] != pytest.approx(271 / 537)
        assert bush["ec_share_full"] > 0.5
        summary = hybrid.build_hybrid_summary(frame)
        assert summary["ec_determinative"].iloc[0]

    def test_the_guard_rejects_shares_summing_over_one(self) -> None:
        """A denominator bug (e.g. dividing by *cast*) would breach this."""
        frame = pd.DataFrame({
            "year": [1900, 1900],
            "candidate": ["A", "B"],
            "ec_share_full": [0.6, 0.5],
        })
        with pytest.raises(hybrid.HybridError, match="1.0"):
            hybrid.assert_ec_shares_le_one(frame)

    def test_the_guard_does_not_fire_on_exactly_one(self) -> None:
        frame = pd.DataFrame({
            "year": [1900, 1900],
            "candidate": ["A", "B"],
            "ec_share_full": [0.5, 0.5],
        })
        hybrid.assert_ec_shares_le_one(frame)


# --- ec_determinative boundary ---------------------------------------------


class TestEcDeterminativeBoundary:
    @staticmethod
    def _summary(allocation: dict[str, int], total_ev: int = 538) -> pd.DataFrame:
        """Summary for one 538-vote "state" with ``allocation`` electoral votes each.

        The allocation is given **per candidate explicitly** rather than as
        leader-plus-remainder: a two-way split cannot express "the leader falls just short
        of a majority" at all, because whatever the leader does not take, the runner-up
        does — so the runner-up wins with a majority and the fixture silently tests the
        opposite of its name. Three candidates are needed for the just-under case.
        """
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": candidate,
             "total_electoral_votes": total_ev, "president_electoral_votes": ev}
            for candidate, ev in allocation.items()
        ])
        return hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(df, all_popular_vote(df))
        )

    def test_an_exact_half_is_not_determinative(self) -> None:
        """``> 0.5`` is **strict** — a 269-269 split elects nobody (D041)."""
        assert not self._summary({"A": 269, "B": 269})["ec_determinative"].iloc[0]

    def test_just_under_a_majority_is_not_determinative(self) -> None:
        """269 is the majority threshold's floor; 268 with a third getter is short."""
        summary = self._summary({"A": 268, "B": 267, "C": 3})
        assert summary["ec_winner"].iloc[0] == "A"  # A really is the leader
        assert not summary["ec_determinative"].iloc[0]

    def test_just_over_a_majority_is_determinative(self) -> None:
        assert self._summary({"A": 270, "B": 268})["ec_determinative"].iloc[0]

    def test_the_ec_winner_is_still_populated_when_not_determinative(self) -> None:
        """``false`` means "no EC majority", never "we could not compute a winner"."""
        summary = self._summary({"A": 268, "B": 267, "C": 3})
        assert summary["ec_winner"].iloc[0] == "A"
        assert pd.notna(summary["ec_winner"].iloc[0])

    def test_determinative_reads_the_full_share_never_the_hybrid_share(self) -> None:
        """The D037/A safety property: no coverage policy can manufacture a majority.

        1824's coverage-restricted EC share would push Jackson to 99/190 = 0.52 — over the
        line. ``ec_determinative`` must ignore it and stay ``False`` on 99/261 = 0.379.

        **The two shares are overwritten to diverge before the summary is built.** Under
        the only shipped policy (b) they are equal by construction, so a summary builder
        that read ``ec_share_hybrid`` instead would produce identical output on every
        natural fixture and this test could not fail — it would pin the *outcome* while
        leaving the *mechanism* free. Injecting the divergence is what makes it
        falsifiable, and that matters most **before #122 lands policy (c)**, which is when
        the two columns start differing on real data.
        """
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        restricted = 99 / (261 - 71)
        assert restricted > 0.5  # the hazard is real, not hypothetical

        # Simulate what policy (c) would produce: the EC share restricted to the
        # popular-vote states, which puts Jackson over the line.
        diverged = frame.copy()
        diverged["ec_share_hybrid"] = (
            diverged["national_electoral_votes"] / (261 - 71)
        )
        assert diverged.loc[
            diverged["candidate"] == "Jackson", "ec_share_hybrid"
        ].iloc[0] > 0.5
        summary = hybrid.build_hybrid_summary(diverged)
        assert not summary["ec_determinative"].iloc[0]
        assert summary["ec_winner"].iloc[0] == "Jackson"

        # ...and unmodified, for the same reason.
        assert not hybrid.build_hybrid_summary(frame)["ec_determinative"].iloc[0]


# --- flips (the winners diverging) -----------------------------------------


class TestKnownFlips:
    def test_2016_ec_winner_and_pv_winner_diverge(self) -> None:
        """A real 2016 four-state subset: Trump takes the EC, Clinton the popular vote.

        Real allotments and real two-way per-state popular votes; ``state_total_votes`` is
        the two-way total (the fixture omits third parties), so the shares are two-way
        shares. The *ordering* — the only thing asserted — is the real one.
        """
        real_2016 = {
            "Texas": (38, "Trump", 4685047, 3877868),
            "Florida": (29, "Trump", 4617886, 4504975),
            "Pennsylvania": (20, "Trump", 2970733, 2926441),
            "California": (55, "Clinton", 4483810, 8753788),
        }
        rows: list[dict[str, object]] = []
        for state, (ev, winner, trump_pv, clinton_pv) in real_2016.items():
            total = float(trump_pv + clinton_pv)
            for candidate, pv in (("Trump", trump_pv), ("Clinton", clinton_pv)):
                rows.append({
                    "year": 2016, "state": state, "candidate": candidate,
                    "total_electoral_votes": ev,
                    "president_electoral_votes": ev if candidate == winner else 0,
                    "candidate_votes": float(pv), "state_total_votes": total,
                })
        df = ec_pv_frame(rows)
        summary = hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(df, all_popular_vote(df))
        )
        row = summary.iloc[0]
        assert row["ec_winner"] == "Trump"
        assert row["pv_winner"] == "Clinton"
        # The hybrid does NOT flip 2016 — Trump's EC margin outweighs the PV gap.
        assert row["hybrid_winner"] == "Trump"
        assert row["ec_determinative"]
        # #123: the same two facts, as the per-election flags the thesis reads.
        assert row["pv_flip"]
        assert not row["hybrid_flip"]
        # A flip that is False must be *populated* False, never NULL — "the method
        # agreed" and "the method had nothing to say" are different answers.
        assert pd.notna(row["hybrid_flip"])

    def test_a_hybrid_flip_is_representable(self) -> None:
        """Guard against a computation that can only ever agree with the EC.

        A narrow EC win against a wide PV loss must be able to move the hybrid — else
        ``hybrid_flip`` (#123) would be dead on arrival.
        """
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 51, "president_electoral_votes": 51,
             "candidate_votes": 100.0, "state_total_votes": 1000.0},
            {"year": 1900, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 51, "president_electoral_votes": 0,
             "candidate_votes": 900.0, "state_total_votes": 1000.0},
            {"year": 1900, "state": "Iowa", "candidate": "A",
             "total_electoral_votes": 49, "president_electoral_votes": 0,
             "candidate_votes": 10.0, "state_total_votes": 1000.0},
            {"year": 1900, "state": "Iowa", "candidate": "B",
             "total_electoral_votes": 49, "president_electoral_votes": 49,
             "candidate_votes": 990.0, "state_total_votes": 1000.0},
        ])
        row = hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(df, all_popular_vote(df))
        ).iloc[0]
        assert row["ec_winner"] == "A"
        assert row["pv_winner"] == "B"
        assert row["hybrid_winner"] == "B"
        assert row["pv_flip"]
        assert row["hybrid_flip"]

    def test_2000_pv_flips_the_electoral_outcome(self) -> None:
        """A real 2000 six-state subset: Bush takes the EC, Gore the popular vote.

        Real allotments and real two-way per-state popular votes, taken from this
        project's own MIT-sourced surface (``/v1/elections/2000``) rather than
        transcribed from memory. Bush 90 electoral votes to Gore's 87 over a 177-vote
        appointed subtotal; Gore 18,400,507 popular votes to Bush's 17,279,431.

        **``hybrid_flip`` is deliberately NOT asserted here, and the omission is the
        point.** ``state_total_votes`` is the two-way total (the fixture omits third
        parties), which inflates both shares — and 2000 is the year where that changes
        the hybrid's answer rather than just its precision. On this two-way subset the
        hybrid goes to Gore; on the **real national** figures it does not, because Nader's
        votes sit in the denominator and dilute Gore's popular-vote share
        (Bush (271/538 + 50456169/105593982) / 2 = 0.4908 against Gore's 0.4887). Pinning
        a hybrid flip here would teach the opposite of the real result. The live-warehouse
        hybrid pin belongs to #124; what *is* real and asserted here is the ordering.
        """
        real_2000 = {
            #             EV  winner  Bush pv    Gore pv
            "Texas": (32, "Bush", 3799639, 2433746),
            "Florida": (25, "Bush", 2912790, 2912253),
            "Ohio": (21, "Bush", 2350363, 2183628),
            "Indiana": (12, "Bush", 1245836, 901980),
            "California": (54, "Gore", 4567429, 5861203),
            "New York": (33, "Gore", 2403374, 4107697),
        }
        rows: list[dict[str, object]] = []
        for state, (ev, winner, bush_pv, gore_pv) in real_2000.items():
            total = float(bush_pv + gore_pv)
            for candidate, pv in (("Bush", bush_pv), ("Gore", gore_pv)):
                rows.append({
                    "year": 2000, "state": state, "candidate": candidate,
                    "total_electoral_votes": ev,
                    "president_electoral_votes": ev if candidate == winner else 0,
                    "candidate_votes": float(pv), "state_total_votes": total,
                })
        df = ec_pv_frame(rows)
        row = hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(df, all_popular_vote(df))
        ).iloc[0]
        assert row["ec_winner"] == "Bush"
        assert row["pv_winner"] == "Gore"
        assert row["pv_flip"]
        # 90 vs 87 of 177 appointed — the closest EC margin in the fixture set.
        assert row["ec_margin"] == pytest.approx((90 - 87) / 177 * 100)


# --- NULL handling ---------------------------------------------------------


class TestNullHandling:
    def test_a_ucsb_absent_year_resolves_to_a_null_hybrid_winner_without_raising(
        self,
    ) -> None:
        """SETTLED (Fred, 2026-07-28): accept the NULLs, do not assert UCSB presence.

        ``run_warehouse`` can build EC+MIT only, so every pre-1976 year has NULL PV. The
        all-NULL argmax must resolve to a NULL winner **gracefully** — the tie-raise must
        not fire on it.
        """
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": c,
             "total_electoral_votes": 23,
             "president_electoral_votes": 23 if c == "A" else 0}
            for c in ("A", "B")
        ])
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        assert frame["pv_share"].isna().all()
        assert frame["hybrid_score"].isna().all()

        summary = hybrid.build_hybrid_summary(frame)  # must not raise
        row = summary.iloc[0]
        assert row["ec_winner"] == "A"
        assert pd.isna(row["pv_winner"])
        assert pd.isna(row["hybrid_winner"])
        # The EC half is still fully computed — this is a partial, not a failed, year.
        assert row["ec_determinative"]

    def test_a_no_pv_getter_does_not_compete_and_is_not_a_fabricated_zero(self) -> None:
        """A faithless elector inside a covered year: NULL PV, out of the running."""
        df = ec_pv_frame([
            {"year": 1976, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 25, "president_electoral_votes": 24,
             "candidate_votes": 600.0, "state_total_votes": 1000.0},
            {"year": 1976, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 25, "president_electoral_votes": 0,
             "candidate_votes": 400.0, "state_total_votes": 1000.0},
            # C won a single faithless electoral vote and no popular votes at all.
            {"year": 1976, "state": "Ohio", "candidate": "C",
             "total_electoral_votes": 25, "president_electoral_votes": 1,
             "candidate_votes": np.nan, "state_total_votes": 1000.0},
        ])
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        c = frame.loc[frame["candidate"] == "C"].iloc[0]
        assert pd.isna(c["national_pv_votes"])  # NOT 0
        assert pd.isna(c["pv_share"])
        assert pd.isna(c["hybrid_score"])
        row = hybrid.build_hybrid_summary(frame).iloc[0]
        assert row["pv_winner"] == "A"
        assert row["hybrid_winner"] == "A"
        # ...but C's electoral votes still count toward the appointed denominator's cast
        # total and keep A off a majority basis of its own.
        assert c["ec_share_full"] == pytest.approx(1 / 25)

    def test_a_null_method_winner_yields_a_null_flip_and_never_true(self) -> None:
        """#123 AC-1, and the specific way it is easy to get catastrophically wrong.

        The obvious spelling of a flip is ``pv_winner != ec_winner``. It is wrong here,
        and not in the direction the criterion warns about. ``_winner`` returns a Python
        ``None`` for an all-NULL year — not ``pd.NA`` — so ``!=`` does not propagate to
        NULL the way it would over a pandas column: ``None != "A"`` is plain ``True``.
        A bare ``!=`` would therefore report **a flip** on every pre-1976 year of a
        warehouse built without UCSB, inventing the project's headline result out of a
        coverage gap. The criterion forbids ``False`` here; ``True`` is worse.

        So this asserts all three states explicitly: NULL, and not ``True``, and not
        ``False``.
        """
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": c,
             "total_electoral_votes": 23,
             "president_electoral_votes": 23 if c == "A" else 0}
            for c in ("A", "B")
        ])
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        row = hybrid.build_hybrid_summary(frame).iloc[0]

        assert pd.isna(row["pv_winner"])
        for column in ("pv_flip", "hybrid_flip"):
            assert pd.isna(row[column]), f"{column} must be NULL on a no-PV year"
            assert row[column] is not True
            assert row[column] is not False
        # The EC half is unaffected — a coverage gap in one method does not blank another.
        assert row["ec_winner"] == "A"
        assert pd.notna(row["ec_margin"])


# --- #123: the three percentage-point margins -------------------------------


class TestMargins:
    def test_the_margin_is_percentage_points_not_a_fraction(self) -> None:
        """D037 fixes the unit. A 60/40 split is a **20**-point margin, not 0.2."""
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 10, "president_electoral_votes": 6,
             "candidate_votes": 600.0, "state_total_votes": 1000.0},
            {"year": 1900, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 10, "president_electoral_votes": 4,
             "candidate_votes": 400.0, "state_total_votes": 1000.0},
        ])
        row = hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(df, all_popular_vote(df))
        ).iloc[0]
        assert row["ec_margin"] == pytest.approx(20.0)
        assert row["pv_margin"] == pytest.approx(20.0)
        assert row["hybrid_margin"] == pytest.approx(20.0)

    def test_each_method_takes_its_top_two_from_its_own_non_null_set(self) -> None:
        """The shape real data actually has, and the reason each margin gets its own series.

        A corpus pass over this project's public API found that **4 of the 13
        redistributable years (1976, 1988, 2004, 2016) carry a candidate with electoral
        votes and no popular vote at all** — every one of them a faithless elector's
        recipient, per :data:`usvote.getters.EC_GETTERS_WITHOUT_POPULAR_VOTE`. In 2016
        that is five of the seven rows (Powell 3, Sanders, Ron Paul, Kasich, Faith
        Spotted Eagle), which the Archives Table 2 collapses into unnamed "Other"
        columns — a printing convention for those same faithless votes, not a separate
        kind of candidate (``docs/corrections.md``; the 2016 page's own Notes read "There
        were faithless votes cast for president and vice president in Hawaii, Texas, and
        Washington"). So a year's EC top-2 and PV top-2 are
        genuinely drawn from different candidate sets, and a single filtered frame shared
        across the three margins would silently compute at least one of them over the
        wrong population.

        Here C holds the *second-largest* electoral vote count while carrying no popular
        vote. The EC margin must be A-over-C; the PV margin must skip C entirely and be
        A-over-B.
        """
        df = ec_pv_frame([
            {"year": 1976, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 100, "president_electoral_votes": 60,
             "candidate_votes": 600.0, "state_total_votes": 1000.0},
            {"year": 1976, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 100, "president_electoral_votes": 10,
             "candidate_votes": 400.0, "state_total_votes": 1000.0},
            # Second on electoral votes, absent from the popular vote entirely.
            {"year": 1976, "state": "Ohio", "candidate": "C",
             "total_electoral_votes": 100, "president_electoral_votes": 30,
             "candidate_votes": np.nan, "state_total_votes": 1000.0},
        ])
        row = hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(df, all_popular_vote(df))
        ).iloc[0]
        # EC: A 60 vs C 30 — C is the runner-up, so the gap is 30 points, not A-over-B's 50.
        assert row["ec_margin"] == pytest.approx(30.0)
        # PV: C is not in the running at all, so the gap is A 60% vs B 40%.
        assert row["pv_margin"] == pytest.approx(20.0)

    def test_an_all_null_method_yields_a_null_margin_and_never_a_zero(self) -> None:
        """AC-3's "gracefully": absent, not zero. A 0.0 margin would read as a dead heat."""
        df = ec_pv_frame([
            {"year": 1900, "state": "Ohio", "candidate": c,
             "total_electoral_votes": 23,
             "president_electoral_votes": 23 if c == "A" else 0}
            for c in ("A", "B")
        ])
        row = hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(df, all_popular_vote(df))
        ).iloc[0]
        assert pd.isna(row["pv_margin"])
        assert pd.isna(row["hybrid_margin"])
        assert row["pv_margin"] != 0

    def test_a_lone_scored_candidate_yields_a_null_margin_not_its_own_share(self) -> None:
        """A "top-2 gap" is undefined with one entry.

        The tempting fallback is ``top1 - 0``, which would publish a **share** under a
        column named margin — a wrong number rather than an absent one. Here B holds
        electoral votes but no popular vote, leaving exactly one popular-vote-scored
        candidate, whose share is ~100%: a ``top1 - 0`` implementation would report a
        100-point popular-vote margin for an election nobody contested on that measure.
        """
        df = ec_pv_frame([
            {"year": 1976, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 10, "president_electoral_votes": 6,
             "candidate_votes": 1000.0, "state_total_votes": 1000.0},
            {"year": 1976, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 10, "president_electoral_votes": 4,
             "candidate_votes": np.nan, "state_total_votes": 1000.0},
        ])
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        assert frame["pv_share"].notna().sum() == 1
        row = hybrid.build_hybrid_summary(frame).iloc[0]
        assert pd.isna(row["pv_margin"])
        assert row["pv_margin"] != 100.0
        # The EC measure has two scored candidates, so it still reports.
        assert row["ec_margin"] == pytest.approx(20.0)

    def test_the_ec_margin_reads_the_policy_invariant_share(self) -> None:
        """``ec_margin`` comes from ``ec_share_full``, never the policy-selected share.

        **Built under policy (c), because under (b) this test could not fail.**
        ``mismatched`` sets ``ec_share_hybrid == ec_share_full`` by construction, so a
        builder reading the wrong column produces identical output on every natural
        fixture — the same trap
        :meth:`TestEcDeterminativeBoundary.test_determinative_reads_the_full_share_never_the_hybrid_share`
        documents, and the reason it injects a divergence rather than trusting the
        default.

        Here the divergence comes from the **real seam** rather than an overwrite:
        ``restricted`` narrows both halves of the EC share to 1824's popular-vote states.
        That genuinely re-ranks the field — Clay overtakes Crawford — though **at ranks
        three and four, so the top-2 pair is unchanged**; what moves is the *gap*, 5.75
        points against 18.95. The gap is therefore what discriminates, and asserting the
        top-2 *identity* would prove nothing here.
        """
        df, roster = frame_1824()
        full = hybrid.build_hybrid_frame(df, roster)
        restricted = hybrid.build_hybrid_frame(
            df, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        )
        # The hazard is real on this fixture, not hypothetical: the policy-selected share
        # is a different column with a different ordering below the top two.
        assert not restricted["ec_share_hybrid"].equals(restricted["ec_share_full"])
        by_hybrid = restricted.sort_values("ec_share_hybrid", ascending=False)
        by_full = restricted.sort_values("ec_share_full", ascending=False)
        assert list(by_hybrid["candidate"]) != list(by_full["candidate"])

        row = hybrid.build_hybrid_summary(restricted).iloc[0]
        # 1824: Jackson 99, Adams 84, over the real 261-vote appointed allotment —
        # unchanged by the policy, which is the property under test.
        assert row["ec_margin"] == pytest.approx((99 - 84) / 261 * 100)
        wrong = (
            by_hybrid["ec_share_hybrid"].iloc[0] - by_hybrid["ec_share_hybrid"].iloc[1]
        ) * 100
        assert row["ec_margin"] != pytest.approx(wrong)
        # The policy-invariant answer is identical to the one policy (b) reports.
        assert row["ec_margin"] == pytest.approx(
            hybrid.build_hybrid_summary(full).iloc[0]["ec_margin"]
        )

    def test_1824_computes_both_flips_and_all_three_margins(self) -> None:
        """AC-5: the contingent election is computed **and** flagged, never withheld.

        Jackson leads all three methods, so both flips are a populated ``False`` — which
        is a different statement from the NULL a no-coverage year produces, and the
        distinction is the whole reason flips are nullable. The two orthogonal facts stay
        true beside them: no EC majority, and partial popular-vote coverage.
        """
        df, roster = frame_1824()
        row = hybrid.build_hybrid_summary(hybrid.build_hybrid_frame(df, roster)).iloc[0]
        assert row["ec_winner"] == "Jackson"
        assert row["pv_winner"] == "Jackson"
        assert row["hybrid_winner"] == "Jackson"
        for column in ("pv_flip", "hybrid_flip"):
            assert pd.notna(row[column])
            assert not row[column]
        # Populated, not withheld — and the two orthogonal flags still hold.
        assert not row["ec_determinative"]
        assert row["pv_coverage"] == pytest.approx(190 / 261)
        for column in ("ec_margin", "pv_margin", "hybrid_margin"):
            assert pd.notna(row[column])
            assert row[column] > 0
        # Real 1824 national popular vote: Jackson 151,271 to Adams' 113,122 of 352,780.
        assert row["pv_margin"] == pytest.approx((151271 - 113122) / 352780 * 100)

    def test_a_margin_is_never_negative(self) -> None:
        """Top-2 ordering, not a signed gap against a fixed candidate."""
        df, roster = frame_1824()
        summary = hybrid.build_hybrid_summary(hybrid.build_hybrid_frame(df, roster))
        for column in ("ec_margin", "pv_margin", "hybrid_margin"):
            assert (summary[column].dropna() >= 0).all()

    def test_the_null_filter_is_what_returns_none_not_a_propagated_nan(self) -> None:
        """Calls :func:`hybrid._margin` directly, because the frame cannot tell them apart.

        Dropping the ``dropna()`` survives every frame-level assertion in this file, and
        the mutation pass confirmed it. The reason is that ``sort_values(ascending=False)``
        puts NaNs **last**, so the top-2 slice is identical either way; the only thing that
        changes is the *unscored* case, where the filter returns ``None`` and its absence
        returns a propagated ``nan``. Both land in a DataFrame column as NaN, so
        ``pd.isna`` — which every other margin test uses — cannot distinguish them.

        That is the guard-that-guards-nothing shape: the assertions pin the **outcome**
        while leaving the **mechanism** free. Asserting ``is None`` on the helper itself
        is the smallest thing that observes which implementation ran, and it is worth
        observing: ``_margin`` is annotated ``float | None``, ``None`` is what
        :func:`build_hybrid_summary`'s contract promises, and #124 has to translate
        "fewer than two scored candidates" into a SQL NULL rather than a NaN.
        """
        two_scored = pd.Series([0.6, 0.4], dtype="float64")
        assert hybrid._margin(two_scored) == pytest.approx(20.0)

        for name, values in (
            ("one scored, one null", [1.0, np.nan]),
            ("none scored", [np.nan, np.nan]),
            ("single row", [0.5]),
            ("empty", []),
        ):
            result = hybrid._margin(pd.Series(values, dtype="float64"))
            assert result is None, f"{name}: expected None, got {result!r}"

        # NaNs must not displace a real runner-up either — the property that makes the
        # filter invisible above, asserted rather than assumed.
        assert hybrid._margin(
            pd.Series([0.6, np.nan, 0.3], dtype="float64")
        ) == pytest.approx(30.0)

    def test_hybrid_margin_is_derived_from_the_hybrid_score_not_a_component(self) -> None:
        """Pins ``hybrid_margin`` to a value no component share produces.

        The mutation pass found this one: pointing ``hybrid_margin`` at ``pv_share``
        survived the whole suite, because every other test asserting it either uses a
        fixture where all three margins are coincidentally equal (60/40 gives 20.0 three
        times) or asserts only ``notna`` / ``> 0``. Nothing pinned it to a
        *distinguishing* number — the same defect the ``ec_margin`` guard was written for,
        on the third column.

        1824 distinguishes them: the EC gap is 5.75 points, the popular-vote gap 10.81,
        and the hybrid's 8.28. The assertion is the D037 identity rather than a
        re-implementation — under policy (b) the hybrid score is the mean of the two
        shares, so where the same two candidates lead all three measures (they do here:
        Jackson then Adams), **the hybrid margin is the mean of the other two margins.**
        That is a property of the formula, not of the code, so it fails for any
        implementation reading a single component.
        """
        df, roster = frame_1824()
        row = hybrid.build_hybrid_summary(hybrid.build_hybrid_frame(df, roster)).iloc[0]
        assert row["hybrid_margin"] == pytest.approx(
            (row["ec_margin"] + row["pv_margin"]) / 2
        )
        # ...and the three are genuinely distinct here, so that identity has content.
        assert row["ec_margin"] == pytest.approx((99 - 84) / 261 * 100)
        assert row["pv_margin"] == pytest.approx((151271 - 113122) / 352780 * 100)
        assert row["hybrid_margin"] != pytest.approx(row["pv_margin"])
        assert row["hybrid_margin"] != pytest.approx(row["ec_margin"])


# --- the tie guard (kept separable for #124) --------------------------------


class TestTieGuard:
    def test_a_true_tie_raises(self) -> None:
        frame = pd.DataFrame({
            "year": [1900, 1900],
            "candidate": ["A", "B"],
            "hybrid_score": [0.5, 0.5],
        })
        with pytest.raises(hybrid.HybridError, match="tie"):
            hybrid.assert_no_winner_tie(frame, "hybrid_score")

    def test_an_all_null_score_is_not_a_tie(self) -> None:
        """The explicit carve-out: all-NULL is a coverage gap, not a dead heat."""
        frame = pd.DataFrame({
            "year": [1900, 1900],
            "candidate": ["A", "B"],
            "hybrid_score": [np.nan, np.nan],
        })
        hybrid.assert_no_winner_tie(frame, "hybrid_score")

    def test_a_single_null_scored_candidate_does_not_create_a_tie(self) -> None:
        frame = pd.DataFrame({
            "year": [1900, 1900, 1900],
            "candidate": ["A", "B", "C"],
            "hybrid_score": [0.6, 0.4, np.nan],
        })
        hybrid.assert_no_winner_tie(frame, "hybrid_score")

    def test_the_guard_is_separate_from_the_winner_derivation(self) -> None:
        """Deliberate (architect Q4): a SQL view cannot ``raise``.

        #124 materializes these as views, where a tie surfaces as two rank-1 rows and the
        check has to become a precondition query. Keeping the guard out of the winner
        derivation makes that translation mechanical — so the summary builder must still
        produce a frame for tied input, and only the guard objects.
        """
        df = ec_pv_frame([
            {"year": 1900, "state": s, "candidate": c,
             "total_electoral_votes": 10,
             "president_electoral_votes": 10 if c == w else 0,
             "candidate_votes": 50.0, "state_total_votes": 100.0}
            for s, w in (("Ohio", "A"), ("Iowa", "B"))
            for c in ("A", "B")
        ])
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        assert frame["hybrid_score"].nunique() == 1  # a genuine dead heat
        with pytest.raises(hybrid.HybridError, match="tie"):
            hybrid.assert_no_winner_tie(frame, "hybrid_score")


# --- shape / grain guards --------------------------------------------------


def test_the_fixture_matches_the_live_view_shape() -> None:
    """``ec_pv_frame`` must emit exactly ``EC_PV_COLUMNS`` — no more, no less.

    The helper's docstring promises columns are "derived here so a fixture cannot
    contradict the live view", and until #144 nothing enforced it. That gap is what let
    a real bug through: the fixture emitted ``president_electoral_votes_counted`` while
    the join view did not carry it, so every ``policy='restricted'`` test passed on data
    the warehouse could not produce and ``build_hybrid_from_db(policy=...)`` raised
    ``KeyError`` on the first real run.

    A *superset* is the dangerous direction — a missing column fails loudly on the next
    line, an extra one silently makes the fixture more capable than reality — so this
    asserts set equality rather than containment.
    """
    frame = ec_pv_frame([
        {
            "year": 2020, "state": "Texas", "candidate": "A",
            "total_electoral_votes": 38, "president_electoral_votes": 38,
        }
    ])
    assert set(frame.columns) == set(EC_PV_COLUMNS)


class TestCountedBasis:
    """D046: ``ec_share_full`` and ``ec_determinative`` read **counted**, not cast.

    AC-verify (#144) caught this whole layer untested: reverting ``ec_share_full`` to
    ``national_electoral_votes`` — undoing half of D046 — left the entire suite green,
    because every other fixture defaults counted to cast and none supplies a divergent
    value. So the PR's headline behavioural claim was unpinned exactly where a reader
    would look for it. These cases supply the divergence.
    """

    @staticmethod
    def _1868() -> tuple[pd.DataFrame, pd.DataFrame]:
        """1868 in miniature: Seymour's Georgia nine are cast but never counted.

        Real shape, real numbers — Grant 214 of 294 with every vote counted, Seymour 80
        cast / 71 counted — so the assertions below are the warehouse's actual figures
        rather than invented ones.
        """
        rows = [
            {"year": 1868, "state": "Georgia", "candidate": "Horatio Seymour",
             "total_electoral_votes": 9, "president_electoral_votes": 9,
             # cast, then never counted: the two chambers deadlocked (D044).
             COUNTED_VOTES_COLUMN: 0},
            {"year": 1868, "state": "Georgia", "candidate": "Ulysses S. Grant",
             "total_electoral_votes": 9, "president_electoral_votes": 0,
             COUNTED_VOTES_COLUMN: 0},
            {"year": 1868, "state": "Ohio", "candidate": "Horatio Seymour",
             "total_electoral_votes": 285, "president_electoral_votes": 71,
             COUNTED_VOTES_COLUMN: 71},
            {"year": 1868, "state": "Ohio", "candidate": "Ulysses S. Grant",
             "total_electoral_votes": 285, "president_electoral_votes": 214,
             COUNTED_VOTES_COLUMN: 214},
        ]
        frame = ec_pv_frame(rows, took_office={1868: "Ulysses S. Grant"})
        return frame, all_popular_vote(frame)

    def test_ec_share_full_divides_counted_by_the_appointed_allotment(self) -> None:
        frame, roster = self._1868()
        out = hybrid.build_hybrid_frame(frame, roster).set_index("candidate")
        # 294 appointed (9 + 285), unchanged by the deadlock — D041's denominator is
        # electors *appointed*, and Georgia's nine were appointed beyond dispute.
        assert set(out["ec_denominator"]) == {294}
        # Seymour: 71 counted / 294, NOT the 80 he cast. This is the assertion the whole
        # counted basis rests on, and the one that was missing.
        assert out.loc["Horatio Seymour", "ec_share_full"] == pytest.approx(71 / 294)
        assert out.loc["Horatio Seymour", "national_electoral_votes"] == 80
        assert out.loc["Horatio Seymour", "national_counted_electoral_votes"] == 71
        # Grant's votes all counted, so his share is identical on either basis — which is
        # why no winner or ec_determinative outcome moved when the basis changed.
        assert out.loc["Ulysses S. Grant", "ec_share_full"] == pytest.approx(214 / 294)

    def test_the_winner_and_determinative_flag_are_unmoved_by_the_basis(self) -> None:
        frame, roster = self._1868()
        summary = hybrid.build_hybrid_summary(
            hybrid.build_hybrid_frame(frame, roster)
        ).iloc[0]
        assert summary["ec_winner"] == "Ulysses S. Grant"
        determinative = non_null_flag(
            summary["ec_determinative"], label="1868 ec_determinative"
        )
        assert determinative is True  # 214/294 = 0.728 > 0.5
        # And the rank the spine carries agrees with the share derived here — the two
        # must share a basis or assert_ec_winner_matches_rank fires (D046).
        hybrid.assert_ec_winner_matches_rank(
            hybrid.build_hybrid_frame(frame, roster),
            hybrid.build_hybrid_summary(hybrid.build_hybrid_frame(frame, roster)),
        )

    def test_policy_c_restricts_states_not_the_basis(self) -> None:
        """(c) narrows *which states* count, never *which measure* (D046).

        Pairing a cast numerator with (b)'s counted one would make the two policies
        disagree in 1868/1872 for a reason unrelated to coverage. Here every state is
        ``popular_vote``, so (c) restricts nothing and must reproduce (b) exactly.
        """
        frame, roster = self._1868()
        b = hybrid.build_hybrid_frame(frame, roster).set_index("candidate")
        c = hybrid.build_hybrid_frame(
            frame, roster, policy=hybrid.COVERAGE_POLICY_RESTRICTED
        ).set_index("candidate")
        assert c.loc["Horatio Seymour", "ec_share_hybrid"] == pytest.approx(71 / 294)
        assert c["ec_share_hybrid"].tolist() == pytest.approx(
            b["ec_share_hybrid"].tolist()
        )

    def test_shares_still_sum_to_at_most_one(self) -> None:
        # counted <= cast <= appointed, so the counted basis can only shrink each share:
        # this guard is strictly safer than it was, never at risk of exceeding 1.0.
        frame, roster = self._1868()
        out = hybrid.build_hybrid_frame(frame, roster)
        hybrid.assert_ec_shares_le_one(out)
        assert out["ec_share_full"].sum() == pytest.approx(285 / 294)


class TestShape:
    def test_the_frame_is_one_row_per_year_candidate(self) -> None:
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        assert not frame.duplicated(list(hybrid.HYBRID_CANDIDATE_GRAIN)).any()
        assert len(frame) == len(CANDIDATES_1824)

    def test_the_summary_is_one_row_per_year(self) -> None:
        df, roster = frame_1824()
        summary = hybrid.build_hybrid_summary(hybrid.build_hybrid_frame(df, roster))
        assert list(summary["year"]) == [1824]

    def test_the_frame_carries_exactly_the_declared_columns(self) -> None:
        """Drift guard: the column contract is a constant, not whatever pandas produced."""
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        assert list(frame.columns) == list(hybrid.HYBRID_CANDIDATE_COLUMNS)

    def test_the_summary_carries_exactly_the_declared_columns(self) -> None:
        df, roster = frame_1824()
        summary = hybrid.build_hybrid_summary(hybrid.build_hybrid_frame(df, roster))
        assert list(summary.columns) == list(hybrid.HYBRID_SUMMARY_COLUMNS)

    def test_the_summary_column_order_is_pinned_to_a_literal(self) -> None:
        """The only assert here that can catch a **reorder** of the constant.

        The test above cannot, and neither could any variation on it:
        ``build_hybrid_summary`` emits ``pd.DataFrame(rows, columns=list(
        HYBRID_SUMMARY_COLUMNS))``, so the frame follows whatever order the constant
        declares and comparing the two is circular. Switching the builder to
        ``frame[list(...)]`` — the spelling ``build_hybrid_frame`` uses — would not help
        either: it also follows the constant. Only a **hand-written literal** is
        independent of it.

        Demonstrated, not assumed: with the constant monkeypatched, reordering the
        leading seven passes the assert above, and so does inserting a bogus column
        mid-list (it simply arrives all-NaN).

        This is the twin of
        :func:`tests.unit.test_join.test_the_column_order_is_append_only`'s
        ``EC_PV_COLUMNS[:15] == (...)`` pin, and it exists for the same reason (D047):
        #124 materializes this tuple as the ``hybrid_summary`` view, and
        ``CREATE OR REPLACE VIEW`` can only **add trailing columns** — so a mid-list
        insert would break ``rebuild_views`` against every warehouse whose views already
        exist, while passing the whole offline suite. #144 shipped exactly that mistake
        on ``EC_PV_COLUMNS`` and review, not the suite, caught it.

        A new column is therefore **appended** to the second tuple below.
        """
        # The E7-S2 head must still be the head: nothing was inserted before it.
        assert hybrid.HYBRID_SUMMARY_COLUMNS[:7] == (
            "year",
            "ec_denominator",
            "ec_winner",
            "pv_winner",
            "hybrid_winner",
            "ec_determinative",
            "pv_coverage",
        )
        # ... and #123's flips and margins sit after it, in this order.
        assert hybrid.HYBRID_SUMMARY_COLUMNS[7:] == (
            "pv_flip",
            "hybrid_flip",
            "ec_margin",
            "pv_margin",
            "hybrid_margin",
        )

    def test_every_input_column_the_frame_needs_is_in_the_join_view_contract(
        self,
    ) -> None:
        """The oracle is pinned to ``EC_PV_COLUMNS``, the shape that actually exists.

        (#121 ships no SQL — materialization is #124 — so there is no live hybrid view to
        pin against; the join view's column contract is the real seam.)
        """
        from usvote.join import EC_PV_COLUMNS

        assert set(hybrid.REQUIRED_JOIN_COLUMNS) <= set(EC_PV_COLUMNS)

    def test_multiple_years_are_computed_independently(self) -> None:
        """Denominators are per-year; a cross-year leak would be invisible on one year."""
        rows: list[dict[str, object]] = []
        for year, ev in ((1900, 10), (1904, 100)):
            for candidate in ("A", "B"):
                rows.append({
                    "year": year, "state": "Ohio", "candidate": candidate,
                    "total_electoral_votes": ev,
                    "president_electoral_votes": ev if candidate == "A" else 0,
                    "candidate_votes": 50.0, "state_total_votes": 100.0,
                })
        df = ec_pv_frame(rows)
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        denominators = frame.set_index("year")["ec_denominator"].to_dict()
        assert denominators == {1900: 10, 1904: 100}


# --- the rank cross-check --------------------------------------------------


def test_the_ec_winner_agrees_with_the_spine_electoral_rank() -> None:
    """``argmax(ec_share_full)`` and ``president_electoral_rank == 1`` are two paths
    to the same fact (both monotonic in ``national_electoral_votes``). Asserting they
    agree catches a frame-assembly bug that silently misaligns candidates.
    """
    df, roster = frame_1824()
    frame = hybrid.build_hybrid_frame(df, roster)
    summary = hybrid.build_hybrid_summary(frame)
    hybrid.assert_ec_winner_matches_rank(frame, summary)


def test_the_rank_cross_check_catches_a_misaligned_winner() -> None:
    frame = pd.DataFrame({
        "year": [1900, 1900],
        "candidate": ["A", "B"],
        "president_electoral_rank": [1, 2],
    })
    summary = pd.DataFrame({"year": [1900], "ec_winner": ["B"]})
    with pytest.raises(hybrid.HybridError, match="rank"):
        hybrid.assert_ec_winner_matches_rank(frame, summary)


# --- the DB entry point (code-review fixes, #126) ---------------------------


class _StubDBC:
    """A minimal ``DBC`` stand-in: answers by matching the relation in the query.

    Deliberately not a mock — the point is to prove ``build_hybrid_from_db`` issues the
    reads it claims and wires their results together, so it must serve real frames.
    """

    def __init__(self, ec_pv: pd.DataFrame, roster: pd.DataFrame) -> None:
        self.ec_pv = ec_pv
        self.roster = roster
        self.queries: list[str] = []

    def select_query_to_df(self, query: str) -> pd.DataFrame:
        self.queries.append(query)
        if "pv_state_status" in query:
            return self.roster.copy()
        return self.ec_pv.copy()


def _mixed_surface() -> tuple[pd.DataFrame, pd.DataFrame]:
    """A 1900 (UCSB-only, no PV on the MIT surface) + 1976 (MIT) two-year warehouse.

    **The roster now carries MIT rows for 1976, because that is what the warehouse
    holds** — #127 gave ``run_mit_pipeline`` its ``load_pv_status`` call, so MIT
    contributes one ``popular_vote`` row per ``(year, state)`` it loads. 1900 stays
    UCSB-only: MIT's span starts at 1976, so nothing MIT-sourced attests to it.

    Before #127 the roster held **no** MIT rows at all, and an even earlier version of
    this fixture papered over that by fabricating one — ``source="mit"``, lowercase,
    where the real literal is ``SOURCE_MIT == "MIT"``, so the live source-scoped read
    would have matched it *twice* over — and asserting ``pv_coverage == 1.0`` for 1976.
    It was internally consistent, so it passed green while modelling data the warehouse
    could not produce: the same fixture-disagrees-with-reality class as #121's
    ``took_office`` bug. The row below is the honest version of that row, and it is
    honest because the pipeline now writes it. Every source tag comes from
    :mod:`usvote.pv.source`, never hand-spelled.
    """
    rows: list[dict[str, object]] = []
    for year, pv in ((1900, None), (1976, 600.0)):
        for candidate, ev in (("A", 20), ("B", 0)):
            rows.append({
                "year": year, "state": "Ohio", "candidate": candidate,
                "total_electoral_votes": 20, "president_electoral_votes": ev,
                "candidate_votes": pv if candidate == "A" else (
                    None if pv is None else 400.0
                ),
                "state_total_votes": None if pv is None else 1000.0,
            })
    df = ec_pv_frame(rows)
    # The MIT-only surface: 1900 carries no PV at all, so it carries no source either.
    df["source"] = df["year"].map({1900: None, 1976: SOURCE_MIT})
    roster = pd.concat([
        roster_frame({1900: {"Ohio": PV_STATUS_POPULAR_VOTE}}, source=SOURCE_UCSB),
        roster_frame({1976: {"Ohio": PV_STATUS_POPULAR_VOTE}}, source=SOURCE_UCSB),
        # #127: MIT's own roster row for the year MIT actually covers.
        roster_frame({1976: {"Ohio": PV_STATUS_POPULAR_VOTE}}, source=SOURCE_MIT),
    ])
    return df, roster


def test_the_roster_read_is_scoped_to_the_sources_the_surface_actually_carries() -> None:
    """Code review, #126: a full roster on the MIT-only surface fakes full coverage.

    UCSB's roster marks every 1900 state ``popular_vote``, but ``ec_pv_redistributable``
    carries no 1900 popular vote whatsoever — so an unscoped roster would report
    ``pv_coverage == 1.0`` for a year whose ``pv_share`` and ``hybrid_score`` are entirely
    NULL. That is the exact inverse of what the flag is for, so the read is scoped to the
    sources present in the chosen view.

    **Scoping to MIT now matches MIT's own rows** (#127, landed): 1976 reports a real
    ``1.0`` and 1900 stays NULL. Before the backfill the MIT scope matched *nothing*, so
    coverage came back NULL for both years — honest, but uselessly so: the flag that
    exists to say "this year's PV is partial" said "unknown" for a year that is
    completely covered. This test pins both halves of the fix at once.
    """
    df, roster = _mixed_surface()
    dbc = cast("Any", _StubDBC(df, roster))
    frame, summary = hybrid.build_hybrid_from_db(
        dbc, view="ec_pv_redistributable"
    )
    by_year = summary.set_index("year")
    # 1900: no PV on this surface, and no MIT roster row for it → coverage unknown.
    # NULL, never 0.0 — "we hold nothing for this year", not "nobody voted".
    assert pd.isna(by_year.loc[1900, "pv_coverage"])
    assert pd.isna(by_year.loc[1900, "hybrid_winner"])
    # 1976: MIT carries the popular vote AND the roster row that attests to it (#127).
    assert by_year.loc[1976, "pv_coverage"] == 1.0
    # The hybrid itself is unaffected — (b) never reads coverage to compute a score.
    assert by_year.loc[1976, "hybrid_winner"] == "A"
    # The EC half is computed for both years regardless.
    assert set(frame["ec_denominator"]) == {20}


def test_the_real_builders_output_yields_coverage_1_0_end_to_end() -> None:
    """Close the fixture-vs-reality loop: the roster here is *built*, not hand-written.

    Every other coverage test feeds ``roster_frame`` — a hand-authored frame that merely
    *resembles* what the pipeline writes. That is the shape of the bug #127 was filed to
    close, so at least one test must consume :func:`build_popular_vote_roster`'s actual
    output. A dtype or spelling drift in the builder (a ``StringDtype`` ``year``, a
    differently-cased ``state``) would still match ``read_pv_status_roster``'s ``source``
    filter while missing ``pv_coverage_by_year``'s merge on ``['year', 'state']`` —
    giving NULL coverage in production while every hand-written fixture stayed green.
    """
    from usvote.pv.status import build_popular_vote_roster

    df = ec_pv_frame([
        {"year": 1976, "state": "Ohio", "candidate": "A",
         "total_electoral_votes": 20, "president_electoral_votes": 20,
         "candidate_votes": 600.0, "state_total_votes": 1000.0},
        {"year": 1976, "state": "Iowa", "candidate": "A",
         "total_electoral_votes": 8, "president_electoral_votes": 8,
         "candidate_votes": 300.0, "state_total_votes": 500.0},
    ])
    df["source"] = SOURCE_MIT
    # The roster exactly as run_mit_pipeline derives it: from the EC spine's
    # participation frame, not from the PV facts (D024 / decisions.md).
    spine = pd.DataFrame([
        {"year": 1976, "state": "Ohio", "is_total": False},
        {"year": 1976, "state": "Iowa", "is_total": False},
        {"year": 1976, "state": None, "is_total": True},
    ])
    roster = build_popular_vote_roster(spine, source=SOURCE_MIT, years={1976})

    _, summary = hybrid.build_hybrid_from_db(
        cast("Any", _StubDBC(df, roster)), view="ec_pv_redistributable"
    )
    assert summary.set_index("year").loc[1976, "pv_coverage"] == 1.0


def test_a_populated_roster_still_yields_real_coverage_on_the_preferred_surface() -> None:
    """The coverage-``1.0`` assertion belongs where the roster is real (architect, #122).

    ``ec_pv_preferred`` carries UCSB, whose roster *is* loaded — so scoping the read to
    that surface's sources finds rows and coverage is a genuine ``1.0``. Pairing this with
    the test above is what keeps "scoped read" and "empty MIT roster" as two separately
    visible facts rather than one conflated one.
    """
    df, roster = _mixed_surface()
    df["source"] = SOURCE_UCSB
    frame, summary = hybrid.build_hybrid_from_db(cast("Any", _StubDBC(df, roster)))
    assert summary.set_index("year").loc[1976, "pv_coverage"] == 1.0
    assert not frame.empty


def test_the_unscoped_roster_would_have_claimed_full_coverage() -> None:
    """Pin the bug the scoping fixes, so a regression is visibly a regression."""
    df, roster = _mixed_surface()
    unscoped = hybrid.build_hybrid_summary(
        hybrid.build_hybrid_frame(df, roster)
    ).set_index("year")
    assert unscoped.loc[1900, "pv_coverage"] == 1.0  # the wrong answer
    assert pd.isna(unscoped.loc[1900, "hybrid_winner"])  # ...next to no hybrid at all


def test_the_entry_point_runs_the_guards_not_just_the_tests() -> None:
    """Code review, #126: the asserts must guard live builds, not only fixtures.

    A denominator bug on real warehouse data can only surface at build time, which is
    exactly where nothing was checking. Mirrors ``join.create_ec_pv_views`` running
    ``assert_db_pv_matches_ec`` as a precondition.
    """
    df, roster = _mixed_surface()
    # A dead heat in 1976: both candidates take half the state's electoral votes and half
    # the popular vote, so every method ties.
    df.loc[(df["year"] == 1976), "president_electoral_votes"] = 10
    df.loc[(df["year"] == 1976), "candidate_votes"] = 500.0
    df["national_electoral_votes"] = df.groupby(["year", "candidate_id"])[
        "president_electoral_votes"
    ].transform("sum")
    with pytest.raises(hybrid.HybridError, match="tie"):
        hybrid.build_hybrid_from_db(cast("Any", _StubDBC(df, roster)), view="ec_pv_redistributable")


def test_the_entry_point_rejects_an_unresolved_view() -> None:
    """Reading the raw union would fan the 1976-2024 overlap out 2x (D017)."""
    df, roster = _mixed_surface()
    with pytest.raises(hybrid.HybridError, match="resolved"):
        hybrid.build_hybrid_from_db(cast("Any", _StubDBC(df, roster)), view="pv_votes")


# --- #124: the materialized views -------------------------------------------


def _split_top_level(text: str) -> list[str]:
    """Split ``text`` on commas at paren depth 0 — the projection's column list."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return [p.strip() for p in out if p.strip()]


def projected_aliases(sql: str) -> list[str]:
    """The output column names of ``sql``'s final projection, in order.

    Both builders put the outermost ``SELECT`` **last** (every CTE precedes it), so the
    final ``SELECT`` is the last one in the string. Written as a parser rather than as a
    literal-substring assert because the point is to compare the *emitted contract*
    against the column tuple — a substring check would pass on a SELECT that projected
    the right names in the wrong order, which is the exact failure D047 makes fatal.
    """
    body = sql[sql.rindex(" SELECT ") + len(" SELECT ") :]
    body = body[: body.rindex(" FROM ")] if " FROM " in body else body
    aliases = []
    for part in _split_top_level(body):
        if " AS " in part:
            aliases.append(part.rsplit(" AS ", 1)[1].strip())
        else:
            aliases.append(part.rsplit(".", 1)[-1].strip())
    return aliases


class TestViewConstants:
    """The four view names and the surface table that pairs them (#124 AC-7)."""

    def test_the_four_view_names(self) -> None:
        assert hybrid.HYBRID_PREFERRED_VIEW == "hybrid_preferred"
        assert hybrid.HYBRID_REDISTRIBUTABLE_VIEW == "hybrid_redistributable"
        assert hybrid.HYBRID_SUMMARY_PREFERRED_VIEW == "hybrid_summary_preferred"
        assert (
            hybrid.HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW
            == "hybrid_summary_redistributable"
        )

    def test_each_surface_pairs_a_join_view_with_its_own_two_hybrid_views(self) -> None:
        """One entry per surface, and no name reused across surfaces."""
        assert len(hybrid.HYBRID_SURFACES) == 2
        joins = [s[0] for s in hybrid.HYBRID_SURFACES]
        assert joins == [EC_PV_PREFERRED_VIEW, EC_PV_REDISTRIBUTABLE_VIEW]
        names = [n for surface in hybrid.HYBRID_SURFACES for n in surface[1:]]
        assert len(set(names)) == 4, f"a view name is shared across surfaces: {names}"

    def test_each_output_name_matches_its_own_input_join_view(self) -> None:
        """Link 3 of 3: every output name carries its **input's** surface suffix (#166).

        The gap: swap the two output-name *pairs* between rows — each row keeping its own
        input join view, emitting the other row's two output names — and the whole offline
        suite stayed green (measured before this test existed: 1149 passed). Under that
        swap ``hybrid_redistributable``, the read seam D039 settled for #102 and the
        surface D030 requires be redistributable-only *at source*, is built over
        ``ec_pv_preferred`` — over UCSB-provenanced rows — while carrying the name the
        public path trusts.

        **One leg of a tripod, not a standalone proof of D030's structural half.** It pins
        this table's internal consistency and nothing else. It cannot see a *consistent*
        double-rename (``ec_pv_public`` + ``hybrid_public`` satisfies the relation) — that
        is :meth:`TestViewConstants.test_the_four_view_names`, which pins the literals. It
        says nothing about the SQL a builder emits — that is
        :class:`TestRedistributableLeakGuardIsStructural`. And it says nothing about the
        creator's loop body — that is
        :class:`TestTheCreatorIssuesEachSurfacesSqlUnderItsOwnName`.

        Derived per row rather than enumerated per surface, deliberately: the constant's
        own comment anticipates "a third surface would be one row here", and a
        correctly-formed third row must pass with no edit here.

        Replaces ``test_the_creator_pairs_each_surface_correctly``, removed in #166: two
        of its three asserts were tautologies (the same value on both sides) and the third
        related a row's two *outputs* to each other, which the swap preserves because it
        moves them as a pair.
        """
        for join_view, candidate_view, summary_view in hybrid.HYBRID_SURFACES:
            assert join_view.startswith("ec_pv_"), (
                f"{join_view} does not follow the ec_pv_ naming convention — rejected "
                "by name here rather than through the suffix relation below, which "
                "would silently reinterpret itself: removeprefix returns the string "
                "unchanged, so the relation would become candidate_view == "
                f"'hybrid_{join_view}' and fail for a reason naming nothing useful"
            )
            suffix = join_view.removeprefix("ec_pv_")
            assert candidate_view == f"hybrid_{suffix}", (
                f"{candidate_view} is built over {join_view} but does not carry its "
                f"surface — expected hybrid_{suffix}"
            )
            assert summary_view == f"hybrid_summary_{suffix}", (
                f"{summary_view} is built over {candidate_view}, itself built over "
                f"{join_view}, but does not carry that surface — expected "
                f"hybrid_summary_{suffix}"
            )

    def test_every_view_name_is_exported(self) -> None:
        for name in (
            "HYBRID_PREFERRED_VIEW",
            "HYBRID_REDISTRIBUTABLE_VIEW",
            "HYBRID_SUMMARY_PREFERRED_VIEW",
            "HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW",
            "HYBRID_SURFACES",
        ):
            assert name in hybrid.__all__, f"{name} must be public — #102 reads it"


class TestRedistributableLeakGuardIsStructural:
    """Link 1 of 3 / AC-4 **primary**: the public hybrid view can only ever read the public join view.

    Link 1 of the naming-invariant chain #166 built: this class pins **which join view a
    builder's SQL reads for a given input**, :class:`TestTheCreatorIssuesEachSurfacesSqlUnderItsOwnName`
    (Link 2) pins the name a view is created under against the SQL it is created with, and
    :meth:`TestViewConstants.test_each_output_name_matches_its_own_input_join_view`
    (Link 3) pins that every output name carries its input's surface suffix. Links 2 and 3
    were labelled and this one was not (#174), which left the chain reading as though a
    link were missing.

    This is the guard that cannot pass vacuously. A data assertion over a frame is only
    as good as the frame — if no non-redistributable row happens to be present it says
    nothing — whereas the *definition* naming ``ec_pv_redistributable`` and never
    ``ec_pv_preferred`` is true or false regardless of what data exists. Style borrowed
    from ``tests/unit/test_api_import_graph.py``.
    """

    def test_the_redistributable_view_never_reads_the_preferred_join_view(self) -> None:
        sql = hybrid.build_hybrid_candidate_sql(EC_PV_REDISTRIBUTABLE_VIEW)
        assert EC_PV_REDISTRIBUTABLE_VIEW in sql
        assert EC_PV_PREFERRED_VIEW not in sql, (
            "the public hybrid surface must never name the preferred join view — "
            "that is the structural half of D030"
        )

    def test_the_preferred_view_is_the_mirror(self) -> None:
        sql = hybrid.build_hybrid_candidate_sql(EC_PV_PREFERRED_VIEW)
        assert EC_PV_PREFERRED_VIEW in sql
        assert EC_PV_REDISTRIBUTABLE_VIEW not in sql

    def test_each_summary_reads_only_its_own_candidate_view(self) -> None:
        pub = hybrid.build_hybrid_summary_sql(hybrid.HYBRID_REDISTRIBUTABLE_VIEW)
        assert hybrid.HYBRID_REDISTRIBUTABLE_VIEW in pub
        assert hybrid.HYBRID_PREFERRED_VIEW not in pub
        priv = hybrid.build_hybrid_summary_sql(hybrid.HYBRID_PREFERRED_VIEW)
        assert hybrid.HYBRID_PREFERRED_VIEW in priv
        # No hybrid view name contains another, so neither direction can alias today —
        # pinned by TestTheCreatorIssuesEachSurfacesSqlUnderItsOwnName's containment
        # assert, which is what keeps this leg meaningful under a rename (#166). An
        # earlier comment here asserted the reverse containment was possible; the
        # summary names are strictly longer, so it never was.
        assert hybrid.HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW not in priv


class TestRedistributableDataAssert:
    """AC-4 **defense in depth** — and here we test only that the guard *fires*.

    Its clean-path discharge is deliberately **not** in this file: a clean assertion
    over a frame authored in this very module proves nothing, which is the vacuity the
    structural test above exists to cover instead. It runs for real as a
    :func:`usvote.hybrid.create_hybrid_views` precondition and in the gated real-corpus
    integration test.
    """

    def _frame(self, source: str | None, redistributable: object) -> pd.DataFrame:
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20,
             "candidate_votes": 100.0, "state_total_votes": 150.0},
        ])
        df["source"] = source
        df["redistributable"] = redistributable
        return df

    def test_an_explicit_false_is_a_violation(self) -> None:
        with pytest.raises(hybrid.HybridError, match="redistributable=false"):
            hybrid.assert_redistributable_only_source(
                self._frame(SOURCE_MIT, False)
            )

    def test_a_non_mit_source_is_a_violation(self) -> None:
        with pytest.raises(hybrid.HybridError, match="non-MIT source"):
            hybrid.assert_redistributable_only_source(
                self._frame(SOURCE_UCSB, True)
            )

    def test_a_null_source_is_an_honest_gap_not_a_violation(self) -> None:
        """A getter MIT does not cover has NULL PV — a D005 gap, never a leak."""
        hybrid.assert_redistributable_only_source(self._frame(None, None))


class TestSqlColumnContract:
    """The emitted projections are the column tuples, in order (D047)."""

    def test_the_candidate_projection_is_the_candidate_column_tuple(self) -> None:
        for join_view, _, _ in hybrid.HYBRID_SURFACES:
            sql = hybrid.build_hybrid_candidate_sql(join_view)
            assert projected_aliases(sql) == list(hybrid.HYBRID_CANDIDATE_COLUMNS)

    def test_the_summary_projection_is_the_summary_column_tuple(self) -> None:
        for _, candidate_view, _ in hybrid.HYBRID_SURFACES:
            sql = hybrid.build_hybrid_summary_sql(candidate_view)
            assert projected_aliases(sql) == list(hybrid.HYBRID_SUMMARY_COLUMNS)

    def test_the_candidate_column_order_is_pinned_to_a_literal(self) -> None:
        """The twin of ``test_the_summary_column_order_is_pinned_to_a_literal``.

        The two asserts above compare the SQL against the constant, which catches a
        column the SQL forgot — but **not a reorder of the constant itself**, because
        the SQL is written to follow it. Only a hand-written literal is independent.
        CLAUDE.md recorded this gap as a deferred follow-up after #123; it stops being
        deferrable here, because #124 turns the tuple into a ``CREATE OR REPLACE VIEW``
        column contract where a mid-list insert breaks a rebuild against every existing
        warehouse while passing the whole offline suite.

        A new column is **appended** to the literal below, never inserted.
        """
        assert hybrid.HYBRID_CANDIDATE_COLUMNS == (
            "year",
            "candidate_id",
            "candidate",
            "party",
            "national_electoral_votes",
            "national_counted_electoral_votes",
            "ec_denominator",
            "ec_share_full",
            "national_pv_votes",
            "national_pv_denominator",
            "pv_share",
            "ec_share_hybrid",
            "pv_coverage",
            "hybrid_score",
            "president_electoral_rank",
            "took_office",
        )

    def test_the_alias_parser_would_notice_a_reorder(self) -> None:
        """Non-vacuity: the parser must not return a set-like or sorted answer."""
        got = projected_aliases("WITH x AS (SELECT 1) SELECT a.one, b AS two FROM x")
        assert got == ["one", "two"]

    def test_party_is_minned_under_a_byte_ordered_collation(self) -> None:
        """``min(text)`` is collation-dependent; Python's ``min`` is not.

        Under the usual ``en_US.UTF-8`` Postgres returns ``'Republican'`` from
        ``min('REPUBLICAN','Republican')`` while :func:`usvote.hybrid._resolved_party`
        returns ``'REPUBLICAN'`` — a silent disagreement on exactly the mixed-spelling
        case ``party`` is resolved for, and one no offline comparison can see. The
        ``COLLATE "C"`` is what makes the two the same pick.

        ``min(candidate)`` deliberately carries no such cast:
        :func:`usvote.hybrid.assert_carried_columns_constant` proves it constant within
        the group, and ``min`` over a single distinct value is collation-independent.
        """
        sql = hybrid.build_hybrid_candidate_sql(EC_PV_PREFERRED_VIEW)
        assert 'min(party COLLATE "C") AS party' in sql
        assert "min(party) AS party" not in sql

    def test_every_ratio_casts_before_dividing(self) -> None:
        """Postgres integer-divides ints — an uncast share reads 0 for everyone.

        Shape-checked here and checked **numerically** in the integration test, because
        a string assert cannot survive a rewording of the expression it pins.
        """
        sql = hybrid.build_hybrid_candidate_sql(EC_PV_PREFERRED_VIEW)
        for numerator, denominator in (
            ("n.national_counted_electoral_votes", "d.ec_denominator"),
            ("n.national_pv_votes", "p.national_pv_denominator"),
            ("c.covered_electoral_votes", "d.ec_denominator"),
        ):
            assert f"{numerator} / {denominator}" not in sql, (
                f"{numerator} is divided without a cast — Postgres would truncate"
            )
            assert f"{numerator}::double precision / {denominator}" in sql


class TestCoverageNullEncoding:
    """The roster-absent NULL vs. roster-present-zero distinction, in both expressions."""

    def test_the_sql_distinguishes_the_two_with_an_explicit_case(self) -> None:
        """A bare ``FILTER`` sum would return NULL for both, collapsing the D024 design."""
        sql = hybrid.build_hybrid_candidate_sql(EC_PV_PREFERRED_VIEW)
        assert "CASE WHEN NOT EXISTS" in sql
        assert "coalesce(sum(a.state_electoral_votes)" in sql

    def test_both_schemas_are_threaded_into_the_emitted_sql(self) -> None:
        """The join view and the roster each take their schema from their own argument.

        `create_hybrid_views` carries `schema` **and** `roster_schema` as independent
        defaults, mirroring `usvote.join.create_ec_pv_views`'s `schema`/`pv_schema` pair
        rather than inventing a `None`-fallback idiom this codebase does not use. That
        independence is only safe if both are actually threaded — an argument that is
        accepted and then ignored is worse than one that does not exist, because the
        caller has been told it works. Nothing tested the threading until code review
        asked (#124).
        """
        sql = hybrid.build_hybrid_candidate_sql(
            EC_PV_PREFERRED_VIEW, schema="wh", roster_schema="ref"
        )
        assert f"wh.{EC_PV_PREFERRED_VIEW}" in sql
        assert "ref.pv_state_status" in sql
        assert "dwh." not in sql, "a default leaked past an explicit argument"

    def test_the_summary_builder_needs_only_the_one_schema(self) -> None:
        """It reads the candidate view, which has already resolved the roster."""
        sql = hybrid.build_hybrid_summary_sql(
            hybrid.HYBRID_PREFERRED_VIEW, schema="wh"
        )
        assert f"wh.{hybrid.HYBRID_PREFERRED_VIEW}" in sql
        assert "pv_state_status" not in sql

    def test_the_roster_reach_test_matches_the_oracle_s_own(self) -> None:
        """``EXISTS`` over the roster, not ``count()`` over the joined rows.

        The oracle asks whether the **roster** carries the year at all
        (``roster_years = set(resolved["year"])``). Counting matched rows instead asks
        whether the roster carries the year *for a state the EC spine has that year* —
        the same question only while D024 §6 keeps both derived from one spine. Where
        they part, one side reports a known ``0.0`` and the other an unknown NULL, which
        is exactly the distinction this column exists to preserve. Found at code
        review (#124).
        """
        sql = hybrid.build_hybrid_candidate_sql(EC_PV_PREFERRED_VIEW)
        assert "(SELECT 1 FROM roster r2 WHERE r2.year = a.year)" in sql
        assert "count(r.pv_status) = 0" not in sql

    def test_a_roster_absent_year_is_null_and_an_all_absence_year_is_zero(self) -> None:
        """The oracle the SQL above mirrors — the two paths, side by side."""
        df = ec_pv_frame([
            {"year": 1820, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 8, "president_electoral_votes": 8},
            {"year": 1824, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 8, "president_electoral_votes": 8},
        ])
        # 1824 is in the roster and entirely legislature-chosen; 1820 is absent from it.
        roster = roster_frame({1824: {"Ohio": PV_STATUS_LEGISLATURE_CHOSEN}})
        out = hybrid.pv_coverage_by_year(df, roster).set_index("year")
        assert pd.isna(out.loc[1820, "pv_coverage"]), "absent from roster ⇒ unknown"
        assert out.loc[1824, "covered_electoral_votes"] == 0
        assert out.loc[1824, "pv_coverage"] == 0.0, "known, and known to be none"


class TestFanOutGuards:
    """AC-5 — one row per grain, at both grains."""

    def test_the_candidate_grain_guard_fires_on_a_duplicate(self) -> None:
        frame = pd.DataFrame([
            {"year": 2000, "candidate_id": 1},
            {"year": 2000, "candidate_id": 1},
        ])
        with pytest.raises(hybrid.HybridError, match="fanned out"):
            hybrid.assert_no_fan_out(frame, hybrid.HYBRID_CANDIDATE_GRAIN)

    def test_the_summary_grain_guard_fires_on_a_duplicate(self) -> None:
        summary = pd.DataFrame([{"year": 2000}, {"year": 2000}])
        with pytest.raises(hybrid.HybridError, match="fanned out"):
            hybrid.assert_no_fan_out(summary, hybrid.HYBRID_SUMMARY_GRAIN)

    def test_the_output_grain_guards_cannot_see_a_raw_union_leak(self) -> None:
        """The gap the docstring now discloses, demonstrated rather than asserted.

        A 1976-2024 overlap key present twice doubles ``national_pv_votes`` and hence
        ``pv_share``, yet still collapses to one row per output grain — so neither
        output-grain guard fires. What catches it is
        :func:`usvote.join.assert_no_fan_out` on the **input** frame, which
        :func:`usvote.hybrid.create_hybrid_views` runs as a precondition.
        """
        from usvote.join import JoinError
        from usvote.join import assert_no_fan_out as assert_join_no_fan_out

        clean = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20,
             "candidate_votes": 100.0, "state_total_votes": 150.0},
        ])
        leaked = pd.concat([clean, clean], ignore_index=True)  # the union, un-resolved
        roster = all_popular_vote(clean)

        doubled = hybrid.build_hybrid_frame(leaked, roster)
        honest = hybrid.build_hybrid_frame(clean, roster)
        assert doubled["national_pv_votes"].iloc[0] == 2 * honest[
            "national_pv_votes"
        ].iloc[0], "the leak must actually double the numerator, or this proves nothing"

        # ... and yet both output-grain guards are silent on it.
        hybrid.assert_no_fan_out(doubled, hybrid.HYBRID_CANDIDATE_GRAIN)
        hybrid.assert_no_fan_out(
            hybrid.build_hybrid_summary(doubled), hybrid.HYBRID_SUMMARY_GRAIN
        )
        # The input-grain guard is the one that sees it.
        with pytest.raises(JoinError, match="fanned out"):
            assert_join_no_fan_out(leaked)

    def test_the_real_builders_pass_both_grains(self) -> None:
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        summary = hybrid.build_hybrid_summary(frame)
        hybrid.assert_no_fan_out(frame, hybrid.HYBRID_CANDIDATE_GRAIN)
        hybrid.assert_no_fan_out(summary, hybrid.HYBRID_SUMMARY_GRAIN)


class TestCarriedColumnsConstant:
    """The guard that keeps ``min``/``max`` in SQL honest against pandas ``first``."""

    @staticmethod
    def _two_state_frame() -> pd.DataFrame:
        return ec_pv_frame([
            {"year": 2016, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20,
             "candidate_votes": 10.0, "state_total_votes": 20.0},
            {"year": 2016, "state": "Iowa", "candidate": "A",
             "total_electoral_votes": 8, "president_electoral_votes": 8,
             "candidate_votes": 5.0, "state_total_votes": 10.0},
        ])

    def test_a_varying_structural_column_raises(self) -> None:
        """A national window sum that differs per state row is an assembly bug."""
        df = self._two_state_frame()
        df.loc[df["state"] == "Ohio", "national_electoral_votes"] = 99
        with pytest.raises(hybrid.HybridError, match="vary within"):
            hybrid.assert_carried_columns_constant(df)

    def test_the_error_names_the_conflicting_values_not_just_the_key(self) -> None:
        """A key alone sends the reader hunting; the two values usually name the cause."""
        df = self._two_state_frame()
        df.loc[df["state"] == "Ohio", "national_electoral_votes"] = 99
        with pytest.raises(hybrid.HybridError, match="99"):
            hybrid.assert_carried_columns_constant(df)

    def test_a_varying_party_does_NOT_raise_because_it_legitimately_varies(self) -> None:
        """The real two-source finding: MIT and UCSB spell one party two ways.

        ``pv_preferred`` resolves the 1976-2024 overlap **per key**, not per year (D017),
        so a getter MIT's D019 filter drops in one state keeps its UCSB row — and its
        UCSB spelling — there. Requiring constancy would fail every real two-source
        build over capitalization, which is exactly what it did when this guard first
        ran against the live corpus.
        """
        df = self._two_state_frame()
        df.loc[df["state"] == "Ohio", "party"] = "REPUBLICAN"
        df.loc[df["state"] == "Iowa", "party"] = "Republican"
        hybrid.assert_carried_columns_constant(df)  # must not raise

    def test_party_is_resolved_deterministically_regardless_of_row_order(self) -> None:
        """The property that replaces constancy: same answer from either row order.

        ``roll_up_national``'s ``first`` would return whichever spelling sorted first in
        an unordered ``SELECT``, so the oracle would disagree with the view *and* with
        itself. ``min`` is what both sides of the seam can spell identically.
        """
        df = self._two_state_frame()
        df.loc[df["state"] == "Ohio", "party"] = "REPUBLICAN"
        df.loc[df["state"] == "Iowa", "party"] = "Republican"
        roster = all_popular_vote(df)

        forward = hybrid.build_hybrid_frame(df, roster)["party"].iloc[0]
        reversed_ = hybrid.build_hybrid_frame(
            df.iloc[::-1].reset_index(drop=True), roster
        )["party"].iloc[0]
        assert forward == reversed_ == "REPUBLICAN"

    def test_a_getter_with_no_party_anywhere_stays_null(self) -> None:
        """``min`` over an all-null group is NULL in pandas and in SQL alike."""
        df = self._two_state_frame()
        df["party"] = None
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        assert frame["party"].isna().all(), "a fabricated party is worse than none"

    def test_a_well_formed_frame_passes(self) -> None:
        df, _ = frame_1824()
        hybrid.assert_carried_columns_constant(df)

    def test_a_null_party_on_a_no_pv_getter_is_not_a_variation(self) -> None:
        """``nunique`` skips NA, so an honest D005 gap must not trip the guard."""
        df = ec_pv_frame([
            {"year": 2000, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 20, "president_electoral_votes": 20,
             "candidate_votes": 10.0, "state_total_votes": 20.0},
            {"year": 2000, "state": "Iowa", "candidate": "A",
             "total_electoral_votes": 8, "president_electoral_votes": 8},
        ])
        df.loc[df["state"] == "Ohio", "party"] = "DEMOCRAT"
        df.loc[df["state"] == "Iowa", "party"] = None
        hybrid.assert_carried_columns_constant(df)


class _ProbeStub:
    """A minimal ``DBC`` stand-in that answers ``to_regclass`` probes and records writes.

    Deliberately not the shared ``RecordingConnection``: what is under test is the
    *order* of probes against creations, so the stub has to be able to report a specific
    relation absent while still counting every ``create_view`` that got as far as being
    issued.
    """

    def __init__(self, absent: str) -> None:
        self.absent = absent
        self.created: list[str] = []

    def select_query_to_df(self, query: str) -> pd.DataFrame:
        if not query.startswith("SELECT to_regclass("):
            # Not just unsupported -- this IS the assertion. Any data read means a probe
            # for a *later* input had not run yet, which is the ordering bug itself.
            # Without this the stub would fail on such a query anyway, but with an
            # IndexError that says nothing about what went wrong.
            raise AssertionError(
                f"a data read was issued before every input had been probed: {query!r}"
            )
        relation = query.split("'")[1]  # to_regclass('schema.name')
        found = None if relation.endswith(f".{self.absent}") else relation
        return pd.DataFrame({"relation": [found]})

    def create_view(
        self, schema: str, view_name: str, select_sql: str, replace: bool = False
    ) -> None:
        self.created.append(view_name)


class TestEveryInputIsProbedBeforeAnythingIsCreated:
    """A missing input must leave the warehouse untouched, not half-built.

    ``create_hybrid_views`` opens no transaction and ``DBC`` commits per statement, so
    probing inside the per-surface loop would let a failure on the *second* surface
    leave the first surface's pair created and committed — a warehouse advertising two
    of four hybrid views. ``usvote.join.create_ec_pv_views`` probes both its inputs up
    front for the same reason. Raised at code review (#124).
    """

    def _run(self, absent: str) -> tuple[_ProbeStub, pytest.ExceptionInfo[Exception]]:
        stub = _ProbeStub(absent)
        with pytest.raises(hybrid.HybridError) as excinfo:
            hybrid.create_hybrid_views(cast("Any", stub))
        return stub, excinfo

    def test_a_missing_second_surface_creates_nothing_at_all(self) -> None:
        """The regression that motivated the fix: surface 1 must not be committed."""
        stub, excinfo = self._run(EC_PV_REDISTRIBUTABLE_VIEW)
        assert EC_PV_REDISTRIBUTABLE_VIEW in str(excinfo.value)
        assert stub.created == [], (
            "the first surface's views were created before the second was probed — "
            f"a half-built warehouse: {stub.created}"
        )

    def test_a_missing_roster_is_a_clear_error_not_an_undefined_table(self) -> None:
        """The roster is a required input, so its absence is probed, not stumbled into."""
        stub, excinfo = self._run(ROSTER_TABLE)
        assert ROSTER_TABLE in str(excinfo.value)
        assert "pv_coverage" in str(excinfo.value), "say why it is needed"
        assert stub.created == []

    def test_the_probe_stub_would_let_a_creation_through(self) -> None:
        """Non-vacuity: with nothing absent the stub records creations, so the two
        ``created == []`` asserts above are load-bearing rather than trivially true."""
        stub = _ProbeStub("nothing-is-absent")
        assert stub.select_query_to_df("SELECT to_regclass('dwh.x')")[
            "relation"
        ].iloc[0] == "dwh.x"
        stub.create_view("dwh", "v", "SELECT 1")
        assert stub.created == ["v"]

    def test_the_stub_names_the_ordering_bug_rather_than_erroring_obscurely(
        self,
    ) -> None:
        """How this suite would report a regression to probing inside the loop.

        Under that ordering the first surface is probed, then read — and the read is
        what this stub refuses. Pinning the message keeps the failure self-explaining
        instead of an ``IndexError`` from a query the stub could not parse.
        """
        stub = _ProbeStub(EC_PV_REDISTRIBUTABLE_VIEW)
        with pytest.raises(AssertionError, match="before every input had been probed"):
            stub.select_query_to_df(f"SELECT * FROM dwh.{EC_PV_PREFERRED_VIEW}")


def _redistributable_only_surface() -> tuple[pd.DataFrame, pd.DataFrame]:
    """A one-year MIT-only warehouse that survives **every** creator precondition.

    Shaped so nothing raises on the way to ``create_view``: MIT-sourced and
    ``redistributable`` (so the licensing guard passes on the public surface), one state
    (so the carried columns are constant), unique keys (so both fan-out guards hold), and
    a clear winner on all three scores (so no tie assert fires and the EC winner matches
    the spine's rank 1).

    Its own fixture rather than ``_mixed_surface`` because a single-source, single-year
    frame keeps *this* test's subject legible — the names a view is created under, not
    coverage behaviour. ``_mixed_surface`` would in fact survive the creator too: its
    1900 rows carry a **NULL** source, which
    :func:`usvote.hybrid.assert_redistributable_only_source` explicitly tolerates as an
    honest D005 gap. (An earlier version of this docstring claimed the opposite —
    that it would fail that guard. Measured: it does not. Code review, #166.)
    """
    df = ec_pv_frame([
        {"year": 2000, "state": "Ohio", "candidate": "A",
         "total_electoral_votes": 20, "president_electoral_votes": 20,
         "candidate_votes": 600.0, "state_total_votes": 1000.0},
        {"year": 2000, "state": "Ohio", "candidate": "B",
         "total_electoral_votes": 20, "president_electoral_votes": 0,
         "candidate_votes": 400.0, "state_total_votes": 1000.0},
    ])
    df["source"] = SOURCE_MIT
    df["redistributable"] = True
    roster = all_popular_vote(df)
    roster["source"] = SOURCE_MIT
    return df, roster


class _CreatingStub(_StubDBC):
    """:class:`_StubDBC` plus ``to_regclass`` probes and a record of what was created.

    Extends rather than re-implements: ``_StubDBC`` already answers both of the reads
    by matching the relation in the query, which is exactly what lets the **real**
    derivation run here. What it lacks is the probe answer
    :func:`usvote.hybrid.create_hybrid_views` needs before it will create anything, and
    somewhere to record the creations.

    Deliberately **not** :class:`_ProbeStub`, whose ``select_query_to_df`` *refuses* data
    reads — that refusal is itself an ordering assertion for
    :class:`TestEveryInputIsProbedBeforeAnythingIsCreated` and must not be softened.
    """

    def __init__(self, ec_pv: pd.DataFrame, roster: pd.DataFrame) -> None:
        super().__init__(ec_pv, roster)
        #: ``(view name, the SQL issued under it)``, in creation order.
        self.issued: list[tuple[str, str]] = []

    def select_query_to_df(self, query: str) -> pd.DataFrame:
        if query.startswith("SELECT to_regclass("):
            # Log it before returning: ``_StubDBC.queries`` exists to prove which
            # statements were issued, and an override that answers a probe without
            # recording it would quietly make that log a partial account.
            self.queries.append(query)
            return pd.DataFrame({"relation": [query.split("'")[1]]})
        return super().select_query_to_df(query)

    def create_view(
        self, schema: str, view_name: str, select_sql: str, replace: bool = False
    ) -> None:
        self.issued.append((view_name, select_sql))


class TestTheCreatorIssuesEachSurfacesSqlUnderItsOwnName:
    """Link 2 of 3: the name a view is created under, and the SQL it is created with (#166).

    :meth:`TestViewConstants.test_each_output_name_matches_its_own_input_join_view` pins
    the surface *table*, and :class:`TestRedistributableLeakGuardIsStructural` pins which
    join view a builder's SQL reads for a given input. Neither sees the lines in
    :func:`usvote.hybrid.create_hybrid_views` that join them — so a hardcoded view name, a
    ``build_hybrid_candidate_sql(candidate_view)`` slip, the two ``create_view`` name
    arguments transposed, or a botched tuple unpack would leave the table perfectly
    consistent and keep the offline suite green.

    **The whole creator runs; nothing is stubbed out of it.** The stub is a *connection*,
    not a substitute for the function under test: it answers the probes and serves its
    reads real frames, so **every** view-creation precondition
    :func:`usvote.hybrid.create_hybrid_views` enumerates executes — all of them, on the
    redistributable-only fixture, including the conditional licensing guard — the real
    :func:`usvote.hybrid.build_hybrid_from_frames` derives both grains, and the SQL
    captured below is the SQL that would reach Postgres — both builders being pure
    ``str -> str`` functions of a view name. (This sentence carried a **count** until
    #178, and the count was wrong. It now names no figure at all and defers to the
    creator's own enumeration, which is the whole point: a number restated *here* is a
    number that has to be re-derived in another file to be checked, and was not. The
    redistributable surface runs one guard more than the preferred one, because the
    licensing guard is conditional — which is why no single total was ever right.)

    **What it still does not prove:** that the emitted SQL, executed by Postgres, returns
    what the pandas oracle does. Only
    ``tests/integration/test_hybrid_views.py::test_the_live_views_match_the_pandas_oracle``
    does that — it runs the emitted SQL for real, and it *does* run in CI, in the
    ``integration`` job's ``postgres:16`` service container. This class buys unit-tier
    feedback with no database, not coverage that tier lacked.
    """

    def _issued(self) -> dict[str, str]:
        """Run the real creator against a recording connection; return ``{view: SQL}``."""
        stub = _CreatingStub(*_redistributable_only_surface())
        hybrid.create_hybrid_views(cast("Any", stub))
        issued = dict(stub.issued)
        expected = 2 * len(hybrid.HYBRID_SURFACES)
        assert len(issued) == len(stub.issued) == expected, (
            f"expected {expected} distinct creations, got "
            f"{[name for name, _ in stub.issued]}"
        )
        return issued

    def test_each_candidate_view_is_created_with_its_own_join_views_sql(self) -> None:
        """The public surface's SQL must never name the preferred join view."""
        issued = self._issued()
        pub = issued[hybrid.HYBRID_REDISTRIBUTABLE_VIEW]
        assert EC_PV_REDISTRIBUTABLE_VIEW in pub
        assert EC_PV_PREFERRED_VIEW not in pub, (
            f"{hybrid.HYBRID_REDISTRIBUTABLE_VIEW} was created over the preferred join "
            "view — the name the public path trusts, built over UCSB-provenanced rows"
        )
        priv = issued[hybrid.HYBRID_PREFERRED_VIEW]
        assert EC_PV_PREFERRED_VIEW in priv
        assert EC_PV_REDISTRIBUTABLE_VIEW not in priv

    def test_each_summary_view_is_created_with_its_own_candidate_views_sql(self) -> None:
        """Does **not** fire on #166's swap, which moves a row's summary with its
        candidate view and so leaves that pairing consistent. It guards the neighbouring
        mutation — a transposed or hardcoded summary source.

        The ``not in`` legs are only as strong as the names allow, and today they are
        strong: no hybrid view name contains another (the four pinned below). That
        is a property of the **infix** ``summary_`` placement — rename the summaries to
        ``hybrid_redistributable_summary`` and ``HYBRID_REDISTRIBUTABLE_VIEW in pub``
        starts passing on a summary built over itself. Pinned below so the rename cannot
        weaken this test silently.
        """
        names = (
            hybrid.HYBRID_PREFERRED_VIEW,
            hybrid.HYBRID_REDISTRIBUTABLE_VIEW,
            hybrid.HYBRID_SUMMARY_PREFERRED_VIEW,
            hybrid.HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW,
        )
        assert not [
            (a, b) for a in names for b in names if a != b and a in b
        ], "a hybrid view name contains another — the `not in` asserts below soften"

        issued = self._issued()
        pub = issued[hybrid.HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW]
        assert hybrid.HYBRID_REDISTRIBUTABLE_VIEW in pub
        assert hybrid.HYBRID_PREFERRED_VIEW not in pub
        priv = issued[hybrid.HYBRID_SUMMARY_PREFERRED_VIEW]
        assert hybrid.HYBRID_PREFERRED_VIEW in priv
        assert hybrid.HYBRID_REDISTRIBUTABLE_VIEW not in priv


class TestTheCreatorReadsEachJoinViewExactlyOnce:
    """AC-2 (#178): one read per surface, and the derivation gets the guarded frame.

    **Why this has to assert the mechanism rather than an outcome.** Reading the join
    view twice and reading it once produce *byte-identical views* — that is the whole
    reason #164 sat deferred as a non-defect. So no assertion over the emitted SQL, the
    frames, or the created names can tell the fixed code from the unfixed code. What
    distinguishes them is **how many reads were issued** and **which frame object the
    derivation received**, and those are the two things pinned below.

    The second is the one that was actually filed. ``create_hybrid_views`` opens no
    transaction and ``DBC`` commits per statement, so before #178 the input guards
    ran over a *different* read than the derivation did — a guard verdict that did not
    strictly describe the frame the views were built from.
    """

    @staticmethod
    def _join_reads(queries: list[str], view: str) -> list[str]:
        """The data reads of ``view`` — **never** the ``to_regclass`` probes.

        Matching the full ``SELECT * FROM dwh.<view>`` string rather than the bare view
        name is load-bearing: :class:`_CreatingStub` logs its probes into the *same*
        ``queries`` list, and ``SELECT to_regclass('dwh.ec_pv_preferred')`` contains the
        view name too. A substring count would be inflated by the probe and could hide a
        regression behind it.
        """
        return [q for q in queries if q == f"SELECT * FROM {hybrid.SCHEMA}.{view}"]

    def test_each_join_view_is_read_exactly_once(self) -> None:
        """Two reads total across both surfaces, where there used to be four."""
        stub = _CreatingStub(*_redistributable_only_surface())
        hybrid.create_hybrid_views(cast("Any", stub))
        for join_view, _, _ in hybrid.HYBRID_SURFACES:
            reads = self._join_reads(stub.queries, join_view)
            # == 1, never <= 1: under <=, a reworded query string in read_ec_pv_join
            # would drop this to 0 and the test would pass while asserting nothing.
            assert len(reads) == 1, (
                f"{join_view} was read {len(reads)} times, not once — the guards and the "
                f"derivation are no longer provably reading one snapshot: {reads}"
            )

    def test_the_derivation_receives_the_very_frame_the_guards_ran_over(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The `same frame object` half of AC-2, pinned by **identity**.

        Equality would not do it: two reads of the same stub return equal frames, so an
        ``assert_frame_equal`` passes on the unfixed code. Identity is what fails there.
        """
        guarded: list[int] = []
        derived: list[int] = []
        real_guard = hybrid.assert_carried_columns_constant
        real_build = hybrid.build_hybrid_from_frames

        def spy_guard(df: pd.DataFrame, **kwargs: object) -> None:
            guarded.append(id(df))
            real_guard(df, **kwargs)  # type: ignore[arg-type]

        def spy_build(
            ec_pv_df: pd.DataFrame, roster_df: pd.DataFrame, **kwargs: object
        ) -> tuple[pd.DataFrame, pd.DataFrame]:
            derived.append(id(ec_pv_df))
            return real_build(ec_pv_df, roster_df, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(hybrid, "assert_carried_columns_constant", spy_guard)
        monkeypatch.setattr(hybrid, "build_hybrid_from_frames", spy_build)
        hybrid.create_hybrid_views(cast("Any", _CreatingStub(*_redistributable_only_surface())))

        assert len(guarded) == len(derived) == len(hybrid.HYBRID_SURFACES)
        assert guarded == derived, (
            "the derivation was handed a different frame object than the one the input "
            f"guards ran over (guarded {guarded}, derived {derived})"
        )

    def test_the_stub_would_record_a_second_read(self) -> None:
        """Non-vacuity: the counter above can reach 2, so ``== 1`` is load-bearing.

        Issues the read the pre-#178 creator issued a second time — through the real
        :func:`usvote.hybrid.build_hybrid_from_db`, which still reads the view itself —
        and shows the stub logs both. Without this, a matcher that silently matched
        nothing would satisfy ``== 1`` only by accident and satisfy ``== 0`` happily.
        """
        stub = _CreatingStub(*_redistributable_only_surface())
        view = EC_PV_REDISTRIBUTABLE_VIEW
        hybrid.read_ec_pv_join(cast("Any", stub), view=view)
        hybrid.build_hybrid_from_db(cast("Any", stub), view=view)
        assert len(self._join_reads(stub.queries, view)) == 2


def test_the_db_entry_point_still_reads_and_derives_the_same_result() -> None:
    """#178 rewired ``create_hybrid_views`` past ``build_hybrid_from_db``, not through it.

    That function keeps its signature and its behaviour — it is the live-warehouse seam
    for a policy the SQL views cannot express (D050) and the oracle the integration
    differential test runs against — so pin that the refactor left it composing the same
    two reads into the same answer.
    """
    df, roster = _redistributable_only_surface()
    frame, summary = hybrid.build_hybrid_from_db(
        cast("Any", _StubDBC(df, roster)), view=EC_PV_REDISTRIBUTABLE_VIEW
    )
    direct_frame, direct_summary = hybrid.build_hybrid_from_frames(
        df, hybrid._roster_for_surface(cast("Any", _StubDBC(df, roster)), df)
    )
    pd.testing.assert_frame_equal(frame, direct_frame)
    pd.testing.assert_frame_equal(summary, direct_summary)


def _surface_scopings(source: str) -> list[int]:
    """Line numbers of every ``set(<frame>["source"].dropna().unique())`` expression.

    **Matched on the AST, not counted in source text**, for the two reasons
    :func:`_policy_selections` is — and here both directions bite. A text count misses
    the drift that actually matters, a second copy over a differently-named frame
    (``join_df``, ``surface_df``), since it can only match the spelling it was given.
    And it fails *spuriously* on the same literal quoted in a docstring or comment.
    """
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "set"
            and len(node.args) == 1
        ):
            continue
        unique = node.args[0]  # set( <...>.unique() )
        if not (
            isinstance(unique, ast.Call)
            and isinstance(unique.func, ast.Attribute)
            and unique.func.attr == "unique"
        ):
            continue
        dropna = unique.func.value  # <...>.dropna()
        if not (
            isinstance(dropna, ast.Call)
            and isinstance(dropna.func, ast.Attribute)
            and dropna.func.attr == "dropna"
        ):
            continue
        frame = dropna.func.value  # <frame>["source"]
        if (
            isinstance(frame, ast.Subscript)
            and isinstance(frame.slice, ast.Constant)
            and frame.slice.value == "source"
        ):
            found.append(node.lineno)
    return found


@pytest.mark.parametrize(
    "source",
    [
        'set(ec_pv_df["source"].dropna().unique())',
        # The drift that matters, and the one a source-text count could not see: a
        # second copy over a differently-named frame.
        'set(join_df["source"].dropna().unique())',
        'x = set(surface_df["source"].dropna().unique())',
        'read_pv_status_roster(dbc, sources=set(df["source"].dropna().unique()))',
    ],
)
def test_the_scoping_guard_catches_a_copy_over_any_frame_name(source: str) -> None:
    """Positive cases — each is a second home for the scoping and must be flagged."""
    assert _surface_scopings(source)


@pytest.mark.parametrize(
    "source",
    [
        # Prose is not code. A source-text count failed on these; the AST does not see
        # them at all, which is the second reason the matcher is parsed rather than
        # counted.
        '"""Docs quoting set(ec_pv_df["source"].dropna().unique()) verbatim."""',
        '# a comment about set(ec_pv_df["source"].dropna().unique())',
        # A real neighbour in the tree — this exact expression is what
        # `assert_redistributable_only_source` and `usvote.snapshot`'s licensing guard
        # both spell. The rest below are SYNTHETIC near-misses, written to pin one
        # structural condition each; an earlier version of this comment called them all
        # "real neighbours in the tree", which they are not (code review, #178).
        'sorted(ec_pv_df["source"].dropna()[non_mit].unique())',
        # One per condition, so that deleting any single check in the matcher fails at
        # least one case here. Without these the suite passed with three of the four
        # conditions removed, because the case that *reads* as covering each one is
        # rejected a step earlier for a different reason (code review, #178).
        'list(df["source"].dropna().unique())',  # callee is not `set`
        'set(df["source"].dropna().tolist())',  # tail is not `.unique()`
        'set(df["source"].fillna("x").unique())',  # middle is not `.dropna()`
        'set(df["party"].dropna().unique())',  # column is not "source"
        'set(df["source"].dropna())',  # no tail call at all
    ],
)
def test_the_scoping_guard_does_not_cry_wolf(source: str) -> None:
    """Negative cases — none is a second home, so none may fail CI."""
    assert _surface_scopings(source) == []


def test_the_scoping_guard_states_the_spellings_it_cannot_see() -> None:
    """**The known limit, pinned so it is a documented gap and not a surprise.**

    The matcher requires the exact ``set(<frame>["source"].dropna().unique())`` shape, so
    a drift copy written another way — ``.loc[:, "source"]``, or without the ``dropna``
    — is invisible to it, and with the one true home still present the count stays 1 and
    the suite stays green. Asserting the gap here rather than describing it means a later
    widening of the matcher **fails this test** and has to come and delete it, which is
    how the limit gets revisited instead of forgotten.

    The inverse direction is safe and needs no pin: respelling the *home* drops the count
    to 0, which fails loudly.
    """
    assert _surface_scopings('set(df.loc[:, "source"].dropna().unique())') == []
    assert _surface_scopings('set(df["source"].unique())') == []


#: The one line the scoping may live on — derived from the function that owns it, so
#: moving :func:`usvote.hybrid._roster_for_surface` within the module is not a failure.
#: Only a SECOND home is.
_ROSTER_SCOPING_LINE = (
    inspect.getsourcelines(hybrid._roster_for_surface)[1]
    + inspect.getsource(hybrid._roster_for_surface)
    .splitlines()
    .index('    surface_sources = set(ec_pv_df["source"].dropna().unique())')
)


def test_the_roster_scoping_has_exactly_one_expression() -> None:
    """The #126 scoping is single-sourced in ``_roster_for_surface`` (#178).

    Extraction was chosen over threading a frame through ``build_hybrid_from_db``
    precisely so this derivation exists once. A second inline
    ``set(df["source"].dropna().unique())`` beside the roster read would be the drift
    this guards against — a roster scoped one way and a frame read another is the state
    ``pv_coverage`` reports wrongly rather than loudly.

    **Both trees are swept, not just** ``hybrid.py`` **(code review, #178).** Scanning
    only the module made the guard blind where a copy actually was: the differential
    oracle in ``tests/integration/test_hybrid_views.py`` re-derived the body verbatim,
    which is the worst place for one — a copy there keeps testing the *old* rule after
    the rule changes. Since :func:`usvote.hybrid._roster_for_surface` is importable, a
    test needing the scoping calls it, and the sweep is what holds that.
    """
    root = Path(hybrid.__file__).parents[2]
    # Excluded on the path RELATIVE to root, never on its absolute parts. Testing
    # `path.parts` self-disables the whole sweep whenever the checkout itself lives
    # under one of these names -- which is exactly the layout this repo's agents run in,
    # `.claude/worktrees/<agent>/`, where every swept path contains ".claude" and the
    # sweep silently scans zero files (code review, #178).
    skip = {".venv", ".claude"}
    scanned = [
        path
        for path in sorted(root.rglob("*.py"))
        if not skip & set(path.relative_to(root).parts)
    ]
    # Non-vacuity, and the reason it is an assert rather than a comment: an empty sweep
    # is the one failure this guard cannot distinguish from success by its own result.
    # The equality below does catch it (`[] != [the home]`) -- but only by accident of
    # being an equality; the same guard written `len(homes) <= 1` would have passed
    # vacuously on zero files, which is how the filter bug above went unnoticed.
    assert Path(hybrid.__file__) in scanned, (
        "the sweep reached no source tree, so it proves nothing about a second home; "
        f"scanned {len(scanned)} files under {root}"
    )
    homes = [
        f"{path.relative_to(root)}:{line}"
        for path in scanned
        for line in _surface_scopings(path.read_text(encoding="utf-8"))
    ]
    assert homes == [f"src/usvote/hybrid.py:{_ROSTER_SCOPING_LINE}"], (
        "the surface-source scoping must have exactly one home, _roster_for_surface; "
        f"found: {homes}"
    )


def test_no_module_outside_hybrid_spells_a_hybrid_view_name_in_code() -> None:
    """AC-7: ``snapshot.py`` (#102) must read the names by constant, never re-type them.

    Prose is exempt, for the reason ``tests/unit/test_layering.py`` gives: a docstring
    explaining what ``hybrid_redistributable`` is should not be punished. Only code —
    including string literals, which is where a hand-rolled SQL path would hide.
    """
    from tests.unit.test_layering import PKG_ROOT, code_only

    names = (
        hybrid.HYBRID_PREFERRED_VIEW,
        hybrid.HYBRID_REDISTRIBUTABLE_VIEW,
        hybrid.HYBRID_SUMMARY_PREFERRED_VIEW,
        hybrid.HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW,
    )
    offenders = {
        py.relative_to(PKG_ROOT).as_posix(): [n for n in names if n in code_only(
            py.read_text()
        )]
        for py in sorted(PKG_ROOT.rglob("*.py"))
        if py.name != "hybrid.py"
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, f"these hard-code a hybrid view name: {offenders}"


# --- D051 gate 3: cross-source margin agreement (#167) ------------------------


def _pv_source_row(
    source: str,
    year: int,
    state: str,
    candidate: str,
    votes: int,
    total: int,
) -> dict[str, object]:
    """One ``SHARED_PV_COLUMNS``-shaped row for a single-source PV frame."""
    return {
        "source": source,
        "year": year,
        "state": state,
        "candidate": candidate,
        "party": "DEMOCRAT" if candidate.startswith("D") else "REPUBLICAN",
        "candidate_votes": votes,
        "state_total_votes": total,
        "reliability": "exact",
    }


def _two_way_year(
    source: str, year: int, dem: int, rep: int, *, total: int
) -> list[dict[str, object]]:
    """A one-state year with two candidates and an explicit provided state total."""
    return [
        _pv_source_row(source, year, "Ohio", "Dem", dem, total),
        _pv_source_row(source, year, "Ohio", "Rep", rep, total),
    ]


def _margin_stub(mit: pd.DataFrame, ucsb: pd.DataFrame) -> QueryDispatchDBC:
    """Serves ``pv_redistributable`` / ``pv_ucsb`` reads for the gate-3 live form.

    The same shared double the #167 cell-grain tests use, routed identically — the two
    gates read through one seam (``read_overlap_frames``), so their stubs must not be
    able to drift into disagreeing about what that seam issues.
    """
    return QueryDispatchDBC({"pv_ucsb": ucsb}, mit)


class TestNationalPvMarginByYear:
    """AC-5 — percentage points, on each source's own **provided** denominator."""

    def test_the_margin_is_in_percentage_points(self) -> None:
        """A 10-point gap reads ``10.0``, never ``0.1`` — D037's unit, shared with
        the summary frame's three margins because both go through ``_margin``."""
        frame = pd.DataFrame(
            _two_way_year(SOURCE_MIT, 1976, 5_500, 4_500, total=10_000)
        )
        margins = hybrid.national_pv_margin_by_year(frame)
        margin = margins.loc[margins["year"] == 1976, "pv_margin"].iloc[0]
        assert margin == pytest.approx(10.0)

    def test_the_denominator_is_the_provided_total_and_not_a_resum(self) -> None:
        """The discriminating test for AC-5, and the one D017 forbids getting wrong.

        The provided ``state_total_votes`` is 10,000 while the two candidate rows sum to
        only 8,000 — a 2,000-vote minor-candidate residue, which is exactly the shape
        D007's EC-getter scoping creates and exactly what differs between two sources.
        On the provided denominator the margin is (5000-3000)/10000 = **20.00 pp**; on a
        re-sum it would be (5000-3000)/8000 = 25.00 pp. #70 hit this for real: a re-sum
        read 1992 as 6.96 pp against the published ~5.6 pp.
        """
        frame = pd.DataFrame(
            _two_way_year(SOURCE_MIT, 1976, 5_000, 3_000, total=10_000)
        )
        margin = hybrid.national_pv_margin_by_year(frame)["pv_margin"].iloc[0]
        assert margin == pytest.approx(20.0)
        assert margin != pytest.approx(25.0)

    def test_the_denominator_counts_each_state_once_across_candidates(self) -> None:
        """``state_total_votes`` is broadcast onto every candidate row in a state, so a
        bare sum would multiply the denominator by the candidate count."""
        rows = _two_way_year(SOURCE_MIT, 1976, 6_000, 4_000, total=10_000)
        rows += _two_way_year(SOURCE_MIT, 1976, 1_000, 1_000, total=10_000)
        rows[2]["state"] = rows[3]["state"] = "Iowa"
        margin = hybrid.national_pv_margin_by_year(pd.DataFrame(rows))["pv_margin"]
        # (7000 - 5000) / 20000 = 10.00 pp; a candidate-broadcast denominator of 40000
        # would halve it.
        assert margin.iloc[0] == pytest.approx(10.0)

    def test_a_year_with_one_candidate_yields_no_margin(self) -> None:
        """A top-2 gap is undefined with one entry; ``top1 - 0`` would report a share."""
        frame = pd.DataFrame(
            [_pv_source_row(SOURCE_MIT, 1976, "Ohio", "Dem", 6_000, 10_000)]
        )
        assert hybrid.national_pv_margin_by_year(frame)["pv_margin"].iloc[0] is None


class TestMarginAgreement:
    """D051 threshold 3 — the E7 trustworthiness check."""

    def test_two_sources_inside_the_ceiling_pass(self) -> None:
        mit = pd.DataFrame(_two_way_year(SOURCE_MIT, 1976, 5_500, 4_500, total=10_000))
        ucsb = pd.DataFrame(
            _two_way_year(SOURCE_UCSB, 1976, 5_510, 4_500, total=10_000)
        )
        compared = hybrid.assert_margin_agreement(mit, ucsb)
        # 10.00 pp vs 10.10 pp -- a 0.10 pp difference, inside the 0.25 pp ceiling.
        assert compared["diff_pp"].iloc[0] == pytest.approx(0.10)

    def test_a_difference_above_the_ceiling_raises(self) -> None:
        mit = pd.DataFrame(_two_way_year(SOURCE_MIT, 1976, 5_500, 4_500, total=10_000))
        ucsb = pd.DataFrame(
            _two_way_year(SOURCE_UCSB, 1976, 5_600, 4_400, total=10_000)
        )
        # 10.00 pp vs 12.00 pp.
        with pytest.raises(hybrid.HybridError, match="gate-3 ceiling"):
            hybrid.assert_margin_agreement(mit, ucsb)

    def test_a_difference_exactly_on_the_ceiling_passes(self) -> None:
        """0.25 pp is a ceiling, not an exclusive bound — the gate raises *above* it.

        Scaled to a million-vote state because votes are integers: 10.00 pp against
        10.25 pp cannot be expressed exactly on a 10,000-vote total.
        """
        mit = pd.DataFrame(
            _two_way_year(SOURCE_MIT, 1976, 550_000, 450_000, total=1_000_000)
        )
        ucsb = pd.DataFrame(
            _two_way_year(SOURCE_UCSB, 1976, 551_250, 448_750, total=1_000_000)
        )
        compared = hybrid.assert_margin_agreement(mit, ucsb)
        assert compared["diff_pp"].iloc[0] == pytest.approx(hybrid.MARGIN_DIFF_MAX_PP)

    def test_a_year_only_one_source_can_score_is_skipped_not_failed(self) -> None:
        """A missing margin is a coverage gap; comparing it would invent a difference.

        The same reasoning that makes ``_flip`` NULL rather than ``True`` on an all-NULL
        year — and it matters here because a warehouse legitimately carries years one
        source scores and the other does not.
        """
        mit = pd.DataFrame(
            _two_way_year(SOURCE_MIT, 1976, 5_500, 4_500, total=10_000)
            + [_pv_source_row(SOURCE_MIT, 1980, "Ohio", "Dem", 9_000, 10_000)]
        )
        ucsb = pd.DataFrame(
            _two_way_year(SOURCE_UCSB, 1976, 5_500, 4_500, total=10_000)
            + _two_way_year(SOURCE_UCSB, 1980, 9_000, 1_000, total=10_000)
        )
        compared = hybrid.assert_margin_agreement(mit, ucsb)
        assert list(compared["year"]) == [1976]

    def test_the_live_form_skips_when_ucsb_is_absent(self) -> None:
        """AC-3: gate 3 takes the same skip as the cell-grain gates, via the same seam."""
        mit = pd.DataFrame(_two_way_year(SOURCE_MIT, 1976, 5_500, 4_500, total=10_000))
        empty = pd.DataFrame(columns=list(SHARED_PV_COLUMNS))
        dbc = _margin_stub(mit, empty)
        assert hybrid.assert_db_margin_agreement(cast(Any, dbc)) is None

    def test_the_live_form_reads_the_two_single_source_views(self) -> None:
        """AC-2: never the raw union, which would fan the overlap 2x."""
        mit = pd.DataFrame(_two_way_year(SOURCE_MIT, 1976, 5_500, 4_500, total=10_000))
        ucsb = pd.DataFrame(
            _two_way_year(SOURCE_UCSB, 1976, 5_500, 4_500, total=10_000)
        )
        dbc = _margin_stub(mit, ucsb)
        hybrid.assert_db_margin_agreement(cast(Any, dbc))
        joined = " ".join(dbc.queries)
        assert "pv_redistributable" in joined and "pv_ucsb" in joined
        assert "pv_votes" not in joined

    def test_the_live_form_shares_the_read_seam_with_the_cell_grain_gates(self) -> None:
        """One expression of the read + window + skip, so the two gates cannot drift.

        Pinned by identity rather than by behaviour: ``hybrid`` must call
        ``usvote.pv.overlap.read_overlap_frames`` itself, not keep a second copy that
        happens to agree today.
        """
        from usvote.pv import overlap

        assert hybrid.read_overlap_frames is overlap.read_overlap_frames
