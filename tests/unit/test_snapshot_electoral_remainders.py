"""The two per-election electoral-vote tallies on ``hybrid_summary`` (#570).

``electoral_votes_outside_top_two`` sums votes **cast** over candidates whose rank,
ordered by votes **counted**, is above 2; ``electors_without_a_counted_vote`` is the
electors appointed minus the votes counted. Both are computed by
:func:`usvote.snapshot.add_electoral_remainders` from the built national roll-up and
checked by :func:`usvote.snapshot.assert_electoral_remainders_are_consistent`.

Every expected value below is a **hand-written literal**. The six historical years are
the live API's national rows (read 2026-11-21) typed in by hand. Which case catches
which wrong implementation is named on each test, because the historical years alone
cannot tell "rank by counted" from "rank by cast" (#570's architect review, I4).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import usvote.snapshot as snapshot_module
from tests.fixtures.api_snapshot import (
    synthetic_ec_pv_frame,
    synthetic_party_keys_frame,
    synthetic_per_capita_frame,
    synthetic_pv_status_frame,
)
from usvote.api.models import ElectionSummary
from usvote.count_status import COUNTED_VOTES_COLUMN
from usvote.snapshot import (
    SnapshotError,
    add_electoral_remainders,
    assert_electoral_remainders_are_consistent,
    build_snapshot,
)
from usvote.snapshot_schema import HYBRID_SUMMARY_COLUMNS

#: (slug, cast, counted, rank on the counted basis) per year, with the year's appointed
#: electors. Only candidates who received electoral votes are listed.
_YEARS: dict[int, tuple[int, list[tuple[str, int, int, int]]]] = {
    # Two Maryland electors never voted (ELECTORAL_VOTE_SHORTFALLS).
    1832: (
        288,
        [
            ("andrew-jackson", 219, 219, 1),
            ("henry-clay", 49, 49, 2),
            ("john-floyd", 11, 11, 3),
            ("william-wirt", 7, 7, 4),
        ],
    ),
    # One Nevada elector never voted; seceded states appointed none.
    1864: (234, [("abraham-lincoln", 212, 212, 1), ("george-b-mcclellan", 21, 21, 2)]),
    # Seymour: 80 cast, 71 counted (Georgia's 9 disputed).
    1868: (294, [("ulysses-s-grant", 214, 214, 1), ("horatio-seymour", 80, 71, 2)]),
    1872: (
        366,
        [
            ("ulysses-s-grant", 300, 286, 1),
            ("thomas-a-hendricks", 42, 42, 2),
            ("benjamin-gratz-brown", 18, 18, 3),
            ("charles-j-jenkins", 2, 2, 4),
            ("david-davis", 1, 1, 5),
            # Ranks 6 on 0 counted, but his 3 cast votes are in the sum.
            ("horace-greeley", 3, 0, 6),
        ],
    ),
    # One District of Columbia elector never voted.
    2000: (538, [("george-w-bush", 271, 271, 1), ("albert-gore-jr", 266, 266, 2)]),
    2016: (
        538,
        [
            ("donald-j-trump", 304, 304, 1),
            ("hillary-clinton", 227, 227, 2),
            ("colin-powell", 3, 3, 3),
            ("bernie-sanders", 1, 1, 4),
            ("faith-spotted-eagle", 1, 1, 4),
            ("john-kasich", 1, 1, 4),
            ("ron-paul", 1, 1, 4),
        ],
    ),
}

#: year -> (electoral_votes_outside_top_two, electors_without_a_counted_vote).
_EXPECTED: dict[int, tuple[int, int]] = {
    1832: (18, 2),
    1864: (0, 1),
    1868: (0, 9),
    1872: (24, 17),
    2000: (0, 1),
    2016: (7, 0),
}


def _frames(
    years: dict[int, tuple[int, list[tuple[str, int, int, int]]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A (summary, roll-up) pair shaped as ``build_snapshot`` holds them."""
    rollup = pd.DataFrame(
        [
            {
                "year": year,
                "candidate_slug": slug,
                "national_electoral_votes": cast,
                "national_counted_electoral_votes": counted,
                "president_electoral_rank": rank,
                "national_electoral_denominator": appointed,
            }
            for year, (appointed, rows) in years.items()
            for slug, cast, counted, rank in rows
        ]
    )
    summary = pd.DataFrame(
        [
            {
                c: None
                for c in HYBRID_SUMMARY_COLUMNS
                if c
                not in (
                    "electoral_votes_outside_top_two",
                    "electors_without_a_counted_vote",
                )
            }
            | {"year": year, "ec_denominator": appointed}
            for year, (appointed, _) in years.items()
        ]
    )
    return summary, rollup


def _tallies(
    years: dict[int, tuple[int, list[tuple[str, int, int, int]]]],
) -> dict[int, tuple[int, int]]:
    summary, rollup = _frames(years)
    out = add_electoral_remainders(summary, rollup)
    assert_electoral_remainders_are_consistent(out, rollup)
    return {
        int(r.year): (
            int(r.electoral_votes_outside_top_two),
            int(r.electors_without_a_counted_vote),
        )
        for r in out.itertuples()
    }


# --- the six historical years ------------------------------------------------------


@pytest.mark.parametrize("year", sorted(_EXPECTED))
def test_each_historical_year_serves_its_literal_values(year: int) -> None:
    """1832, 1864, 1868, 1872, 2000 and 2016 against hand-written literals.

    What each year catches: **summing counted instead of cast** fails only 1872 (21, for
    Greeley's 3 cast and 0 counted); **subtracting cast instead of counted** fails 1868
    (0 for 9) and 1872 (0 for 17); 1832, 1864 and 2000 pin votes never cast, which a
    cast-based subtraction also gets right, so they pin the appointed denominator.
    """
    assert _tallies({year: _YEARS[year]})[year] == _EXPECTED[year]


def test_all_six_years_together_keep_their_own_values() -> None:
    """Grouping is per year: computing the years together changes nothing."""
    assert _tallies(_YEARS) == _EXPECTED


def test_the_output_is_projected_to_the_summary_contract_in_order() -> None:
    summary, rollup = _frames(_YEARS)
    out = add_electoral_remainders(summary, rollup)
    assert tuple(out.columns) == HYBRID_SUMMARY_COLUMNS


def test_the_snapshot_summary_column_order_is_pinned_to_a_literal() -> None:
    """The append-only order, as a literal: the two #570 columns come last.

    A literal, because comparing the tuple with anything built from it is circular.
    """
    assert HYBRID_SUMMARY_COLUMNS == (
        "year",
        "ec_denominator",
        "ec_winner",
        "ec_winner_slug",
        "pv_winner",
        "pv_winner_slug",
        "hybrid_winner",
        "hybrid_winner_slug",
        "ec_determinative",
        "pv_coverage",
        "pv_flip",
        "hybrid_flip",
        "ec_margin",
        "pv_margin",
        "hybrid_margin",
        "electoral_votes_outside_top_two",
        "electors_without_a_counted_vote",
    )


# --- synthetic cases that discriminate the mechanism -------------------------------


def test_the_top_two_are_ranked_by_counted_votes_not_cast() -> None:
    """B is second by votes cast (6) but third by votes counted (2): B is outside.

    Ranks are supplied on the counted basis, as the served rank is. The right answer
    sums B's 6 cast votes; an implementation that re-ranked by votes cast would put C
    (4 cast) outside instead and return 4.
    """
    year = {1900: (20, [("a", 10, 10, 1), ("b", 6, 2, 3), ("c", 4, 4, 2)])}
    assert _tallies(year)[1900] == (6, 4)


def test_a_tie_at_rank_two_keeps_every_tied_candidate_inside() -> None:
    """B and C share rank 2, so only D (rank 3) is outside: 1.

    A "top two by position" implementation (``nlargest(2)``) would put one of B or C
    outside and return 6.
    """
    year = {1900: (21, [("a", 10, 10, 1), ("b", 5, 5, 2), ("c", 5, 5, 2), ("d", 1, 1, 3)])}
    assert _tallies(year)[1900] == (1, 0)


def test_a_tie_at_rank_one_makes_the_next_candidate_second() -> None:
    """A and B share rank 1; C is rank 2 (dense) and inside; only D is outside."""
    year = {1900: (21, [("a", 8, 8, 1), ("b", 8, 8, 1), ("c", 4, 4, 2), ("d", 1, 1, 3)])}
    assert _tallies(year)[1900] == (1, 0)


# --- the guard: each identity fires on its own -------------------------------------


def _built() -> tuple[pd.DataFrame, pd.DataFrame]:
    summary, rollup = _frames(_YEARS)
    return add_electoral_remainders(summary, rollup), rollup


def test_the_guard_passes_the_built_frames() -> None:
    out, rollup = _built()
    assert_electoral_remainders_are_consistent(out, rollup)


def test_guard_a_refuses_a_summary_denominator_that_differs_from_the_rollup() -> None:
    out, rollup = _built()
    out.loc[out["year"] == 1872, "ec_denominator"] = 367
    out.loc[out["year"] == 1872, "electors_without_a_counted_vote"] = 18  # keeps (b′)
    with pytest.raises(SnapshotError, match=r"\(a\).*\[1872\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


def test_guard_a_refuses_a_null_denominator() -> None:
    out, rollup = _built()
    out["ec_denominator"] = out["ec_denominator"].astype("Int64")
    out.loc[out["year"] == 2000, "ec_denominator"] = pd.NA
    with pytest.raises(SnapshotError, match=r"\(a\).*\[2000\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


def test_guard_b_refuses_counted_above_cast() -> None:
    out, rollup = _built()
    hit = (rollup["year"] == 2000) & (rollup["candidate_slug"] == "albert-gore-jr")
    rollup.loc[hit, "national_counted_electoral_votes"] = 267
    out.loc[out["year"] == 2000, "electors_without_a_counted_vote"] = 0  # keeps (b′)
    with pytest.raises(SnapshotError, match=r"\(b\).*\[2000\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


def test_guard_b_refuses_cast_above_appointed() -> None:
    """The other half of (b): 2016 cast 539 of 538 appointed. Only (b) can fire.

    Trump's rank stays 1, so (c) and (c′) hold; counted is unchanged, so (b′) holds.
    """
    out, rollup = _built()
    hit = (rollup["year"] == 2016) & (rollup["candidate_slug"] == "donald-j-trump")
    rollup.loc[hit, "national_electoral_votes"] = 305
    with pytest.raises(SnapshotError, match=r"\(b\).*\[2016\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


def test_guard_b_prime_refuses_a_wrong_served_count() -> None:
    out, rollup = _built()
    out.loc[out["year"] == 1868, "electors_without_a_counted_vote"] = 0
    with pytest.raises(SnapshotError, match=r"\(b'\).*\[1868\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


@pytest.mark.parametrize("bad", [999, -1])
def test_guard_c_refuses_an_outside_value_out_of_range(bad: int) -> None:
    out, rollup = _built()
    out.loc[out["year"] == 2016, "electoral_votes_outside_top_two"] = bad
    with pytest.raises(SnapshotError, match=r"\(c\).*\[2016\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


@pytest.mark.parametrize(("year", "wrong"), [(2016, 6), (1832, 0)])
def test_guard_c_prime_refuses_an_in_range_value_that_disagrees(
    year: int, wrong: int
) -> None:
    """(c′): a served value inside 0..cast but not the roll-up's sum (2016 is 7, 1832
    is 18). A range check alone would accept both."""
    out, rollup = _built()
    out.loc[out["year"] == year, "electoral_votes_outside_top_two"] = wrong
    with pytest.raises(SnapshotError, match=rf"\(c'\).*\[{year}\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


def test_guard_d_refuses_a_null_tally() -> None:
    out, rollup = _built()
    out["electoral_votes_outside_top_two"] = out[
        "electoral_votes_outside_top_two"
    ].astype("Int64")
    out.loc[out["year"] == 1864, "electoral_votes_outside_top_two"] = pd.NA
    with pytest.raises(SnapshotError, match=r"NULL electoral-vote tally.*\[1864\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


def test_guard_d_refuses_a_duplicate_year() -> None:
    out, rollup = _built()
    out = pd.concat([out, out[out["year"] == 1832]], ignore_index=True)
    with pytest.raises(SnapshotError, match=r"more than one row.*\[1832\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


@pytest.mark.parametrize(
    "column",
    [
        "president_electoral_rank",
        "national_electoral_votes",
        "national_counted_electoral_votes",
    ],
)
def test_guard_e_refuses_a_null_rollup_input(column: str) -> None:
    """A NULL rank is not ``> 2`` and ``sum`` skips a NULL vote: both undercount."""
    out, rollup = _built()
    rollup[column] = rollup[column].astype("Int64")
    hit = (rollup["year"] == 1872) & (rollup["candidate_slug"] == "horace-greeley")
    rollup.loc[hit, column] = pd.NA
    with pytest.raises(SnapshotError, match=r"lack a rank.*\[1872\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


def test_a_duplicate_summary_year_is_refused_at_the_merge() -> None:
    """``validate="1:1"`` refuses it, reported as ours rather than a pandas error."""
    summary, rollup = _frames(_YEARS)
    summary = pd.concat([summary, summary[summary["year"] == 1832]], ignore_index=True)
    with pytest.raises(SnapshotError, match="do not join the summary one-to-one"):
        add_electoral_remainders(summary, rollup)


def test_a_summary_year_that_will_not_merge_is_reported_as_ours() -> None:
    """A ``year`` of another dtype fails the merge as a SnapshotError (exit 3)."""
    summary, rollup = _frames(_YEARS)
    summary["year"] = summary["year"].astype(str)
    with pytest.raises(SnapshotError, match="do not join the summary one-to-one"):
        add_electoral_remainders(summary, rollup)


def test_a_summary_year_missing_from_the_rollup_is_refused_not_dropped() -> None:
    """The merge is left on the summary, so a missing year surfaces as NULL tallies."""
    summary, rollup = _frames(_YEARS)
    rollup = rollup[rollup["year"] != 2000]
    out = add_electoral_remainders(summary, rollup)
    assert 2000 in set(out["year"])
    with pytest.raises(SnapshotError, match=r"NULL electoral-vote tally.*\[2000\]"):
        assert_electoral_remainders_are_consistent(out, rollup)


# --- end to end: state-level rows through the real build ---------------------------


def test_the_built_snapshot_serves_the_tallies_from_state_level_rows(
    snapshot_path: str,
) -> None:
    """The synthetic frame through ``build_snapshot``, read back from the SQLite file.

    1860 has four states. Nevada took no part and was appointed no electors, so it adds
    nothing: appointed is Texas 6 + California 8 + Vermont 4 = 18. Cand D's 8 votes
    were cast but not counted, so 8 electors have no counted vote (a cast-based
    subtraction would give 0). No candidate ranks below second in any year.
    """
    conn = sqlite3.connect(snapshot_path)
    try:
        rows = conn.execute(
            "SELECT year, ec_denominator, electoral_votes_outside_top_two, "
            "electors_without_a_counted_vote FROM hybrid_summary ORDER BY year"
        ).fetchall()
        types = {
            r[1]: (r[2], r[3])
            for r in conn.execute("PRAGMA table_info(hybrid_summary)").fetchall()
        }
    finally:
        conn.close()
    assert rows == [(1860, 18, 0, 8), (2016, 93, 0, 0), (2020, 93, 0, 0)]
    assert types["electoral_votes_outside_top_two"] == ("INTEGER", 1)
    assert types["electors_without_a_counted_vote"] == ("INTEGER", 1)


def test_a_candidate_ranked_third_reaches_the_built_snapshot(tmp_path: Path) -> None:
    """A non-zero tally through the real build, from state-level rows.

    The synthetic 2020 is re-cut so that Cand C takes 5 of California's 55 from Cand B
    (B 50, A 38, C 5): C ranks third, so 5 votes are outside the top two. The other
    tests that build a snapshot see 0 there in every year, so a build that zeroed the
    tally, or read the wrong rank, would pass them.
    """
    frame = synthetic_ec_pv_frame()
    b = (frame["year"] == 2020) & (frame["candidate"] == "Cand B")
    frame.loc[b, ["national_electoral_votes", "national_counted_electoral_votes"]] = 50
    b_ca = b & (frame["state"] == "California")
    frame.loc[b_ca, ["president_electoral_votes", COUNTED_VOTES_COLUMN]] = 50
    c = frame[b].copy()
    c["candidate_id"] = 9
    c["candidate"] = "Cand C"
    c["national_electoral_votes"] = 5
    c["national_counted_electoral_votes"] = 5
    c["president_electoral_rank"] = 3
    c["took_office"] = False
    c["president_electoral_votes"] = [0 if s == "Texas" else 5 for s in c["state"]]
    c[COUNTED_VOTES_COLUMN] = c["president_electoral_votes"]
    c["candidate_votes"] = [100_000, 200_000]
    frame = pd.concat([frame, c], ignore_index=True)

    out = str(tmp_path / "rank3.sqlite")
    build_snapshot(
        frame,
        out,
        pv_status_df=synthetic_pv_status_frame(),
        per_capita_df=synthetic_per_capita_frame(),
        party_keys_df=synthetic_party_keys_frame(frame),
    )
    conn = sqlite3.connect(out)
    try:
        rows = conn.execute(
            "SELECT year, electoral_votes_outside_top_two, "
            "electors_without_a_counted_vote FROM hybrid_summary ORDER BY year"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [(1860, 0, 8), (2016, 0, 0), (2020, 5, 0)]


def test_the_build_runs_the_consistency_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``build_snapshot`` itself refuses a tally that disagrees with the roll-up.

    The guard's fire-tests call it directly, so they would stay green if the build
    stopped calling it. Here the builder is made to serve an in-range wrong value
    (1860's 0 becomes 1, still <= cast), which only (c′) — run by the build — refuses.
    """
    real = snapshot_module.add_electoral_remainders

    def wrong(summary_df: pd.DataFrame, rollup_df: pd.DataFrame) -> pd.DataFrame:
        out = real(summary_df, rollup_df)
        out.loc[out["year"] == 1860, "electoral_votes_outside_top_two"] = 1
        return out

    monkeypatch.setattr(snapshot_module, "add_electoral_remainders", wrong)
    frame = synthetic_ec_pv_frame()
    with pytest.raises(SnapshotError, match=r"\(c'\).*\[1860\]"):
        build_snapshot(
            frame,
            str(tmp_path / "bad.sqlite"),
            pv_status_df=synthetic_pv_status_frame(),
            per_capita_df=synthetic_per_capita_frame(),
            party_keys_df=synthetic_party_keys_frame(frame),
        )


@pytest.mark.parametrize(
    "field", ["electoral_votes_outside_top_two", "electors_without_a_counted_vote"]
)
def test_the_published_schema_declares_each_tally_a_required_integer(
    field: str,
) -> None:
    """The /docs contract: a required, non-nullable integer (no ``null`` branch).

    The served values would be unchanged by ``int | None``, so only the schema shows
    whether the model still promises "never null".
    """
    schema = ElectionSummary.model_json_schema()
    assert field in schema["required"]
    assert schema["properties"][field]["type"] == "integer"
    assert "anyOf" not in schema["properties"][field]


# --- served on the API -------------------------------------------------------------


def test_every_elections_item_and_election_block_serves_both_as_integers(
    client: TestClient,
) -> None:
    items = client.get("/v1/elections/summary").json()["elections"]
    assert [
        (
            e["year"],
            e["electoral_votes_outside_top_two"],
            e["electors_without_a_counted_vote"],
        )
        for e in items
    ] == [(1860, 0, 8), (2016, 0, 0), (2020, 0, 0)]
    for path in ("/v1/elections/1860", "/v1/elections/1860/summary"):
        election = client.get(path).json()["election"]
        assert election["electoral_votes_outside_top_two"] == 0
        assert election["electors_without_a_counted_vote"] == 8
        assert type(election["electors_without_a_counted_vote"]) is int
