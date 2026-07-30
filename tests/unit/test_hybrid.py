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

import numpy as np
import pandas as pd
import pytest

from usvote import hybrid
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
)

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
    optional (absent → NULL, the honest D005 gap). Derived here so a fixture cannot
    contradict the live view: ``candidate_id`` (stable per name), ``national_electoral_votes``
    (the window SUM), and ``president_electoral_rank`` (dense rank on the national total,
    descending, so rank 1 is the EC leader).

    ``took_office`` maps year → the canonical name of whoever assumed the presidency
    (defaults to the rank-1 candidate, i.e. the non-contingent case).
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

    df["national_electoral_votes"] = df.groupby(["year", "candidate_id"])[
        "president_electoral_votes"
    ].transform("sum")
    df["president_electoral_rank"] = (
        df.groupby("year")["national_electoral_votes"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )
    leaders = (
        df.loc[df["president_electoral_rank"] == 1]
        .groupby("year")["candidate"]
        .first()
        .to_dict()
    )
    took = {**leaders, **(took_office or {})}
    df["took_office"] = df["year"].map(took)

    df["source"] = "test"
    df["reliability"] = "high"
    df["redistributable"] = True
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
        """
        df = ec_pv_frame([
            {"year": 1976, "state": "Ohio", "candidate": "A",
             "total_electoral_votes": 25, "president_electoral_votes": 25,
             "candidate_votes": 60.0, "state_total_votes": 100.0},
            {"year": 1976, "state": "Ohio", "candidate": "B",
             "total_electoral_votes": 25, "president_electoral_votes": 0,
             "candidate_votes": np.nan, "state_total_votes": np.nan},
            {"year": 1976, "state": "Iowa", "candidate": "A",
             "total_electoral_votes": 8, "president_electoral_votes": 0,
             "candidate_votes": 30.0, "state_total_votes": 70.0},
            {"year": 1976, "state": "Iowa", "candidate": "B",
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
        """The property #102 depends on: policy-invariance on the MIT-only surface."""
        df = ec_pv_frame([
            {"year": 2000, "state": s, "candidate": c,
             "total_electoral_votes": ev,
             "president_electoral_votes": ev if c == w else 0,
             "candidate_votes": v, "state_total_votes": 100.0}
            for s, ev, w, votes in (("Ohio", 21, "A", (60.0, 40.0)),
                                    ("Iowa", 7, "B", (45.0, 55.0)))
            for c, v in zip(("A", "B"), votes, strict=True)
        ])
        frame = hybrid.build_hybrid_frame(df, all_popular_vote(df))
        assert (frame["ec_share_hybrid"] == frame["ec_share_full"]).all()
        assert (frame["pv_coverage"] == 1.0).all()


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
        # Yet the House chose Adams — rank 1 and took_office genuinely diverge.
        assert set(frame["took_office"]) == {"Adams"}
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
        assert row["ec_determinative"] is False or row["ec_determinative"] == False  # noqa: E712
        assert pd.notna(row["ec_determinative"])
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
        """
        df, roster = frame_1824()
        frame = hybrid.build_hybrid_frame(df, roster)
        restricted = 99 / (261 - 71)
        assert restricted > 0.5  # the hazard is real, not hypothetical
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
