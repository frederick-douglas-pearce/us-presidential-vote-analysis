"""Unit tests for the read-only SQLite snapshot build (``usvote.snapshot``, E8-S1 #95).

All offline (no live DB): the pure builder :func:`usvote.snapshot.build_snapshot` takes an
``ec_pv_redistributable``-shaped frame, so the whole serving contract — table shape,
content-hash version, candidate slug, ``candidate_id`` drop, national roll-up, coverage
window, and the redistributable-only guard — is exercised from a small **synthetic** frame
(D022 posture; this data is EC/MIT/CC0 and carries no UCSB restriction). Any build from
real Postgres is ``@pytest.mark.integration`` and lives elsewhere.

The synthetic scenario (``_ec_pv_frame``) deliberately mixes:
- **1972** — a pre-popular-vote year with all-NULL PV. It used to prove the year was
  *filtered out*; since #139 it proves the opposite — the year is **served**, with its
  electoral-college facts intact, its PV columns null, and a ``pv_status`` on every row
  saying which kind of null it is. Inverting this test was the point of the story.
- **2016** — an "EC winner ≠ PV winner"-shaped year with a **faithless getter** (EC vote,
  no MIT PV), to prove an in-window NULL-PV getter survives with NULL national PV.
- **2020** — an ordinary two-candidate year.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from tests.fixtures.api_snapshot import FIXTURE_NOT_COUNTED_REASON
from usvote import hybrid
from usvote.count_status import COUNT_STATUS_COUNTED, COUNT_STATUS_NOT_COUNTED
from usvote.hybrid import ec_denominator_by_year, roll_up_national
from usvote.join import EC_PV_COLUMNS
from usvote.pv.absences import PV_ABSENCE_CATALOG
from usvote.pv.source import MIT_PV_YEAR_MIN
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
)
from usvote.slug import candidate_slug
from usvote.snapshot import (
    DATA_COLUMNS,
    DATA_TABLE,
    META_TABLE,
    ROLLUP_COLUMNS,
    ROLLUP_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotError,
    SnapshotMeta,
    add_candidate_slug,
    assert_no_hybrid_pv_below_mit_window,
    assert_no_pv_aggregate_below_mit_window,
    build_hybrid_tables,
    build_national_rollup,
    build_snapshot,
    derive_curated_pv_status_roster,
    read_redistributable,
)
from usvote.snapshot_schema import (
    EC_LICENSE,
    EC_SOURCE,
    HYBRID_SUMMARY_TABLE,
)
from usvote.snapshot_schema import (
    HYBRID_SUMMARY_COLUMNS as SNAPSHOT_HYBRID_SUMMARY_COLUMNS,
)
from usvote.years import ec_ingest_years

_TS = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)

#: The one real Archives sentence the fixtures use, defined once in the shared fixture
#: package (with the rationale for why it cannot be invented) and imported here.
_ARCHIVES_REASON = FIXTURE_NOT_COUNTED_REASON

#: The state->USPS enrichment read_redistributable adds from dwh.state; the synthetic
#: frame carries it directly (it is the shape build_snapshot consumes).
_USPS = {"Texas": "TX", "California": "CA", "Washington": "WA"}


def _row(
    year: int,
    state: str,
    candidate_id: int,
    candidate: str,
    president_ev: int,
    national_ev: int,
    rank: int,
    took_office: bool,
    *,
    candidate_votes: int | None,
    state_total: int | None,
    party: str | None = "DEMOCRAT",
    source: str | None = "MIT",
    reliability: str | None = "exact",
    total_ev: int = 38,
    redistributable: bool | None = True,
    counted_ev: int | None = None,
    national_counted_ev: int | None = None,
    count_status: str = COUNT_STATUS_COUNTED,
    count_status_reason: str | None = None,
) -> dict:
    """One ``ec_pv_redistributable`` row. NULL PV (no MIT coverage) ⇒ NULL PV columns."""
    return {
        "year": year,
        "state": state,
        "state_usps": _USPS[state],
        "candidate_id": candidate_id,
        "candidate": candidate,
        "total_electoral_votes": total_ev,
        "president_electoral_votes": president_ev,
        "national_electoral_votes": national_ev,
        "president_electoral_rank": rank,
        "took_office": took_office,
        "source": source,
        "party": party,
        "candidate_votes": candidate_votes,
        "state_total_votes": state_total,
        "reliability": reliability,
        "redistributable": redistributable,
        # counted == cast unless a caller says otherwise. The pair diverges only in
        # 1868/1872 on real data (#144); the fabricated divergence below is what lets
        # the two measures be told apart offline. Ordered last to match EC_PV_COLUMNS,
        # whose new columns are appended, never inserted.
        "president_electoral_votes_counted": (
            president_ev if counted_ev is None else counted_ev
        ),
        "national_counted_electoral_votes": (
            national_ev if national_counted_ev is None else national_counted_ev
        ),
        "count_status": count_status,
        "count_status_reason": count_status_reason,
    }


#: One state → one status, applied to every candidate row in that state-year. 1972
#: exercises all three values; the modern years must be all ``popular_vote`` (the build
#: asserts it — the real catalog records no absence at or after MIT's window).
_STATUS_BY_STATE = {
    (1972, "Texas"): PV_STATUS_POPULAR_VOTE,
    (1972, "California"): PV_STATUS_LEGISLATURE_CHOSEN,
    (1972, "Washington"): PV_STATUS_NOT_PARTICIPATING,
}


def _status_frame(frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """The ``(year, state, pv_status)`` roster matching :func:`_ec_pv_frame`.

    Derived from whatever ``(year, state)`` keys the fact frame carries, so a test that
    edits the frame does not silently leave the roster short and trip the completeness
    anti-join for an unrelated reason.
    """
    src = _ec_pv_frame() if frame is None else frame
    keys = src[["year", "state"]].drop_duplicates()
    keys["pv_status"] = [
        _STATUS_BY_STATE.get((int(y), str(s)), PV_STATUS_POPULAR_VOTE)
        for y, s in zip(keys["year"], keys["state"], strict=True)
    ]
    return keys.reset_index(drop=True)


def _ec_pv_frame() -> pd.DataFrame:
    rows = [
        # --- 1972: pre-PV-window, all PV NULL — SERVED since #139, with pv_status ---
        # McGovern's votes are cast but not counted, so cast (12) and counted (0)
        # diverge on a row the snapshot actually ships. Without a row like this the two
        # measures would be indistinguishable everywhere offline.
        _row(1972, "Texas", 6, "Richard Nixon", 26, 26, 1, True,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None),
        _row(1972, "Texas", 7, "George McGovern", 0, 12, 2, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, national_counted_ev=0),
        _row(1972, "California", 6, "Richard Nixon", 0, 26, 1, True,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=12),
        _row(1972, "California", 7, "George McGovern", 12, 12, 2, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=12,
             counted_ev=0, national_counted_ev=0,
             count_status=COUNT_STATUS_NOT_COUNTED,
             count_status_reason=_ARCHIVES_REASON),
        _row(1972, "Washington", 6, "Richard Nixon", 0, 26, 1, True,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=0),
        _row(1972, "Washington", 7, "George McGovern", 0, 12, 2, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=0,
             national_counted_ev=0),
        # --- 2016: C (49 EV), D wins (55, took office), F faithless (1 EV, no PV) ---
        _row(2016, "Texas", 3, "Cand C", 38, 49, 2, False,
             candidate_votes=4000000, state_total=9000000),
        _row(2016, "Texas", 4, "Cand D", 0, 55, 1, True,
             candidate_votes=3800000, state_total=9000000),
        _row(2016, "Texas", 5, "Faithless F", 0, 1, 3, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None),
        _row(2016, "California", 3, "Cand C", 0, 49, 2, False,
             candidate_votes=3000000, state_total=12000000, total_ev=55),
        _row(2016, "California", 4, "Cand D", 55, 55, 1, True,
             candidate_votes=7000000, state_total=12000000, total_ev=55),
        _row(2016, "California", 5, "Faithless F", 0, 1, 3, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=55),
        _row(2016, "Washington", 3, "Cand C", 11, 49, 2, False,
             candidate_votes=1400000, state_total=3000000, total_ev=12),
        _row(2016, "Washington", 4, "Cand D", 0, 55, 1, True,
             candidate_votes=1300000, state_total=3000000, total_ev=12),
        _row(2016, "Washington", 5, "Faithless F", 1, 1, 3, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=12),
        # --- 2020: A (38 EV), B wins (55, took office) ---
        _row(2020, "Texas", 1, "Cand A", 38, 38, 2, False,
             candidate_votes=5000000, state_total=11000000),
        _row(2020, "Texas", 2, "Cand B", 0, 55, 1, True,
             candidate_votes=5500000, state_total=11000000),
        _row(2020, "California", 1, "Cand A", 0, 38, 2, False,
             candidate_votes=6000000, state_total=17000000, total_ev=55),
        _row(2020, "California", 2, "Cand B", 55, 55, 1, True,
             candidate_votes=11000000, state_total=17000000, total_ev=55),
    ]
    # The enriched shape build_snapshot consumes: the view columns + state_usps.
    return pd.DataFrame(rows)[[*EC_PV_COLUMNS, "state_usps"]]


def _build(
    tmp_path: Path,
    frame: pd.DataFrame | None = None,
    status: pd.DataFrame | None = None,
) -> tuple[Path, SnapshotMeta]:
    out = tmp_path / "snapshot.sqlite"
    fact = _ec_pv_frame() if frame is None else frame
    meta = build_snapshot(
        fact,
        str(out),
        pv_status_df=_status_frame(fact) if status is None else status,
        build_timestamp=_TS,
    )
    return out, meta


def _build_raises(frame: pd.DataFrame, status: pd.DataFrame | None = None) -> None:
    """Run a build that is expected to fail, without writing anything."""
    build_snapshot(
        frame,
        "/dev/null",
        pv_status_df=_status_frame(frame) if status is None else status,
        build_timestamp=_TS,
    )


def _read(out: Path, table: str) -> pd.DataFrame:
    con = sqlite3.connect(str(out))
    try:
        return pd.read_sql(f"SELECT * FROM {table}", con)
    finally:
        con.close()


# --- slug ------------------------------------------------------------------


def test_candidate_slug_is_deterministic_and_ascii_folded() -> None:
    assert candidate_slug("Donald J. Trump") == "donald-j-trump"
    assert candidate_slug("John C. Frémont") == "john-c-fremont"
    assert candidate_slug("  Adlai   Stevenson ") == "adlai-stevenson"
    # Stable regardless of surrounding punctuation.
    assert candidate_slug("J. Strom Thurmond") == "j-strom-thurmond"


def test_empty_slug_fails_loud() -> None:
    # A candidate name with no alphanumeric content slugs to "" — unusable as a public
    # id, so it must fail loud rather than be written.
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "candidate"] = "…"
    with pytest.raises(SnapshotError, match="empty slug"):
        _build_raises(frame)


def test_slug_collision_fails_loud() -> None:
    # Two DISTINCT canonical names that fold to one slug — the docs/canonical-keys.md
    # same-name residual — must raise, not silently merge two people (in-window).
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "candidate"] = "José Foo"
    frame.loc[frame["candidate"] == "Cand B", "candidate"] = "Jose Foo"
    with pytest.raises(SnapshotError, match="slug collision"):
        _build_raises(frame)


def test_pre_window_slug_collision_now_fails_loud() -> None:
    """The inverse of what this test asserted before #139, and deliberately so.

    Slug uniqueness used to be enforced only over the served window, because a
    collision between two pre-1976 candidates the snapshot would never ship should not
    be able to fail a build. Every candidate 1824–2024 ships now, so that reasoning is
    gone and a pre-1976 collision is a real defect — the ``docs/canonical-keys.md``
    same-name residual, to be resolved there rather than dodged by a filter.
    """
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Richard Nixon", "candidate"] = "José Foo"
    frame.loc[frame["candidate"] == "George McGovern", "candidate"] = "Jose Foo"
    with pytest.raises(SnapshotError, match="slug collision"):
        _build_raises(frame)


# --- shape / candidate_id drop ---------------------------------------------


def test_data_columns_drop_candidate_id_and_add_slug() -> None:
    assert "candidate_id" not in DATA_COLUMNS
    assert "candidate_slug" in DATA_COLUMNS
    assert "redistributable" not in DATA_COLUMNS  # constant-true → recorded in meta


def test_snapshot_tables_have_expected_shape(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    data = _read(out, DATA_TABLE)
    assert list(data.columns) == list(DATA_COLUMNS)
    assert "candidate_id" not in data.columns
    # Slug is minted for every row.
    assert (data["candidate_slug"] == data["candidate"].map(candidate_slug)).all()
    # state_usps is carried for the /v1/states/{...} path key (#97).
    assert set(data.loc[data["state"] == "California", "state_usps"]) == {"CA"}
    # The shipped rollup table's columns come from a hand-written CREATE TABLE in
    # usvote.snapshot._create_tables, maintained independently of ROLLUP_COLUMNS.
    # Assert they agree (ec_pv is covered by the DATA_TABLE line above).
    assert list(_read(out, ROLLUP_TABLE).columns) == list(ROLLUP_COLUMNS)


def test_add_candidate_slug_is_pure() -> None:
    frame = _ec_pv_frame()
    slugged = add_candidate_slug(frame)
    assert "candidate_slug" in slugged.columns
    assert "candidate_slug" not in frame.columns  # did not mutate the input


# --- coverage windows (served vs popular-vote) -----------------------------


def test_pre_pv_window_years_are_served(tmp_path: Path) -> None:
    """The headline behaviour change of #139: 1972 ships instead of being dropped.

    It carries its full electoral-college facts and null popular votes — "stop dropping
    rows we already have", which is what made 38 of 51 elections unreachable before.
    """
    out, meta = _build(tmp_path)
    data = _read(out, DATA_TABLE)
    assert set(data["year"]) == {1972, 2016, 2020}
    assert (meta.year_min, meta.year_max) == (1972, 2020)
    pre = data[data["year"] == 1972]
    assert pre["candidate_votes"].isna().all()
    assert pre["president_electoral_votes"].sum() == 38  # EC facts intact


def test_meta_states_the_pv_window_separately(tmp_path: Path) -> None:
    """The two windows differ now, so ``meta`` says both rather than one.

    Without this a consumer would have to infer "popular votes start in 1976" from a
    field of nulls — the inference this whole surface exists to make unnecessary.
    """
    _, meta = _build(tmp_path)
    assert (meta.year_min, meta.year_max) == (1972, 2020)
    assert (meta.pv_year_min, meta.pv_year_max) == (2016, 2020)


def test_every_row_carries_a_pv_status(tmp_path: Path) -> None:
    """No NULL popular vote is ever bare — the central design trap #139 names.

    A pre-1976 state that never held a popular vote must be distinguishable from one
    this source merely does not reach; conflating them on the public artifact is the
    exact missing-vs-zero error the blog series exists to describe.
    """
    out, _ = _build(tmp_path)
    data = _read(out, DATA_TABLE).set_index(["year", "state"])
    assert data["pv_status"].notna().all()
    assert data.loc[(1972, "California"), "pv_status"].eq(
        PV_STATUS_LEGISLATURE_CHOSEN
    ).all()
    assert data.loc[(1972, "Washington"), "pv_status"].eq(
        PV_STATUS_NOT_PARTICIPATING
    ).all()
    # ... and a state that DID hold one, whose votes simply predate MIT's window, is a
    # third, distinct thing — both have null popular_votes, and that is the point.
    assert data.loc[(1972, "Texas"), "pv_status"].eq(PV_STATUS_POPULAR_VOTE).all()
    assert data.loc[(1972, "Texas"), "candidate_votes"].isna().all()


def test_missing_pv_status_fails_loud() -> None:
    """A fact key with no roster row must raise, not ship a bare NULL."""
    frame = _ec_pv_frame()
    status = _status_frame(frame)
    short = status[~((status["year"] == 1972) & (status["state"] == "Texas"))]
    with pytest.raises(SnapshotError, match="have no pv_status"):
        _build_raises(frame, short)


def test_roster_extra_columns_cannot_ride_along() -> None:
    """The broadcast must add exactly ``pv_status`` — no ``source``, no ``note``.

    Roster free text is UCSB-provenanced and must never reach the public surface
    (D022/D030), and a stray column named ``source`` would sit next to the one
    ``assert_redistributable_only`` keys on.
    """
    frame = _ec_pv_frame()
    status = _status_frame(frame)
    status["note"] = "some roster prose"
    with pytest.raises(SnapshotError, match="not exactly"):
        _build_raises(frame, status)


def test_duplicate_roster_key_fails_loud() -> None:
    """A duplicated ``(year, state)`` would fan the fact out; ``validate='m:1'`` stops it.

    Surfaced as a ``SnapshotError`` rather than a bare ``MergeError`` so the CLI reports
    it as a build-invariant violation (exit 3) instead of a traceback.
    """
    frame = _ec_pv_frame()
    status = _status_frame(frame)
    status = pd.concat([status, status.head(1)], ignore_index=True)
    with pytest.raises(SnapshotError, match="not unique on \\(year, state\\)"):
        _build_raises(frame, status)


def test_a_modern_absence_fails_loud() -> None:
    """The public roster and the analysis roster agree over MIT's window, and it is checked.

    They agree *by construction* today — the absence catalog records nothing at or after
    1976 — but "by construction" is a fact about the current catalog, not a law.
    """
    frame = _ec_pv_frame()
    status = _status_frame(frame)
    mask = (status["year"] == 2020) & (status["state"] == "Texas")
    status.loc[mask, "pv_status"] = PV_STATUS_LEGISLATURE_CHOSEN
    with pytest.raises(SnapshotError, match="carry a pv_status other than"):
        _build_raises(frame, status)


# --- the count status + the counted measure (D046/D047) ---------------------


def test_counted_measure_and_status_reach_the_snapshot(tmp_path: Path) -> None:
    """Without these columns the API would report cast votes as if Congress counted them.

    1872 is the real case — Grant at 300 with no way to see 14 were refused — and this
    is its offline stand-in.
    """
    out, _ = _build(tmp_path)
    data = _read(out, DATA_TABLE)
    row = data[
        (data["year"] == 1972)
        & (data["state"] == "California")
        & (data["candidate"] == "George McGovern")
    ].iloc[0]
    assert row["president_electoral_votes"] == 12  # cast
    assert row["president_electoral_votes_counted"] == 0  # counted
    assert row["count_status"] == COUNT_STATUS_NOT_COUNTED
    assert row["count_status_reason"] == _ARCHIVES_REASON
    # An ordinary row carries the status too — complete, not exceptions-only.
    ordinary = data[data["candidate"] == "Cand A"].iloc[0]
    assert ordinary["count_status"] == COUNT_STATUS_COUNTED
    assert pd.isna(ordinary["count_status_reason"])


def test_a_foreign_count_status_reason_fails_loud() -> None:
    """Free text ships here only because it is a **closed** vocabulary of Archives prose.

    ``count_status_reason`` is admissible where ``pv_state_status.note`` is not, on the
    grounds that it is a U.S. Government work (D044 §3). ``dwh.votes`` carries no
    provenance column, so without this guard that distinction would be a docstring
    claim: any sentence at all could ride onto the public surface.
    """
    frame = _ec_pv_frame()
    frame.loc[
        frame["count_status"] == COUNT_STATUS_NOT_COUNTED, "count_status_reason"
    ] = "A sentence from somewhere else entirely."
    with pytest.raises(SnapshotError, match="curated Archives vocabulary"):
        _build_raises(frame)


def test_in_window_null_pv_getter_survives(tmp_path: Path) -> None:
    # A faithless getter (EC vote, no MIT PV) in a covered year stays — with NULL PV.
    out, _ = _build(tmp_path)
    data = _read(out, DATA_TABLE)
    faithless = data[data["candidate"] == "Faithless F"]
    assert len(faithless) == 3  # present in all three 2016 states
    assert faithless["candidate_votes"].isna().all()
    assert faithless["president_electoral_votes"].sum() == 1  # its one real EV


def test_no_pv_anywhere_still_fails_loud() -> None:
    """"MIT was never loaded" must still fail, even though the years now ship.

    The guard is repointed rather than removed: it used to mean "the snapshot would be
    empty", and now means "the snapshot would carry electoral-college data with no
    popular vote anywhere" — still a broken build, just for a different reason.
    """
    frame = _ec_pv_frame()
    frame["candidate_votes"] = None
    with pytest.raises(SnapshotError, match="no redistributable PV"):
        _build_raises(frame)


def test_a_pre_window_popular_vote_fails_loud() -> None:
    """No fact row below MIT's window may carry popular-vote data (D030).

    Uses ``state_total_votes`` rather than ``candidate_votes`` on purpose: a pre-window
    ``candidate_votes`` is caught *earlier*, by the year-floor cross-check (see the next
    test), so the fact-level guard's unique contribution is the denominator column —
    the one that could carry a leaked value without moving the observed PV floor at all.
    """
    frame = _ec_pv_frame()
    frame.loc[frame["year"] == 1972, "state_total_votes"] = 1_000
    with pytest.raises(SnapshotError, match="below 1976 carry a non-null"):
        _build_raises(frame)


def test_the_pre_window_floor_is_a_constant_not_the_observed_minimum() -> None:
    """The guard must key on :data:`MIT_PV_YEAR_MIN`, never on the frame's own floor.

    This is the subtlety the whole guard turns on. Deriving the floor as "the lowest
    year that has any PV" is *vacuous under exactly the failure it exists to catch*:
    give the pre-1976 rows popular votes and the observed floor slides down with them,
    so the assert passes over the very rows it was meant to stop. Here 1972 gets PV and
    the frame's own floor becomes 1972 — a derived guard would see nothing wrong.
    """
    frame = _ec_pv_frame()
    frame.loc[frame["year"] == 1972, "candidate_votes"] = 1_000
    observed_floor = int(frame.loc[frame["candidate_votes"].notna(), "year"].min())
    assert observed_floor == 1972  # a derived floor would be satisfied by construction
    assert MIT_PV_YEAR_MIN == 1976
    with pytest.raises(SnapshotError, match="earlier than MIT_PV_YEAR_MIN"):
        _build_raises(frame)


# --- national roll-up -------------------------------------------------------


def test_national_rollup_ec_and_pv_totals(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    rollup = _read(out, ROLLUP_TABLE).set_index(["year", "candidate_slug"])
    c = rollup.loc[(2016, "cand-c")]
    assert c["national_electoral_votes"] == 49
    assert c["national_pv_votes"] == 4000000 + 3000000 + 1400000
    # Denominator = each state's total counted once: 9M + 12M + 3M = 24M.
    assert c["national_pv_denominator"] == 24000000


def test_denominator_survives_no_pv_getter_sorting_first(tmp_path: Path) -> None:
    # Regression (code-review): national_pv_denominator must count every state once even
    # when the alphabetically-first candidate_slug in a state is a no-PV getter (NULL
    # state_total_votes). Rename the faithless getter so its slug sorts BEFORE the real
    # candidates in every 2016 state; the denominator must stay 9M + 12M + 3M = 24M. With
    # the old drop_duplicates(["year","state"]) this would keep the NULL row per state
    # and understate the denominator (here, drop to 0).
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Faithless F", "candidate"] = "Aardvark Faithless"
    out, _ = _build(tmp_path, frame)
    rollup = _read(out, ROLLUP_TABLE).set_index(["year", "candidate_slug"])
    assert rollup.loc[(2016, "cand-c"), "national_pv_denominator"] == 24000000


def test_rollup_null_pv_getter_has_null_pv_total(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    rollup = _read(out, ROLLUP_TABLE).set_index(["year", "candidate_slug"])
    f = rollup.loc[(2016, "faithless-f")]
    assert f["national_electoral_votes"] == 1
    assert pd.isna(f["national_pv_votes"])  # honest NULL, not a fabricated 0


def test_rollup_one_row_per_year_candidate(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    rollup = _read(out, ROLLUP_TABLE)
    assert not rollup.duplicated(["year", "candidate_slug"]).any()
    assert set(rollup["year"]) == {1972, 2016, 2020}


# --- the shared national-aggregation primitive (D037/F, #121) ---------------


def test_rollup_delegates_to_the_shared_primitive() -> None:
    """The roll-up arithmetic is single-sourced in :mod:`usvote.hybrid` (D037/F).

    Two hand-written copies of the ``min_count=1`` + skip-NA-dedup subtleties would drift,
    and #102 puts both roll-ups under one public artifact. This pins that
    ``build_national_rollup`` is a thin contract wrapper — the snapshot's public group key
    (``candidate_slug``, D006) and column set — over the shared derivation, so the two can
    no longer disagree.
    """
    frame = add_candidate_slug(_ec_pv_frame())
    direct = roll_up_national(
        frame,
        key=("year", "candidate_slug"),
        carry={
            "candidate": "candidate",
            "party": "party",
            "national_electoral_votes": "national_electoral_votes",
            "national_counted_electoral_votes": "national_counted_electoral_votes",
            "president_electoral_rank": "president_electoral_rank",
            "took_office": "took_office",
        },
    ).merge(
        ec_denominator_by_year(frame).rename(
            columns={"ec_denominator": "national_electoral_denominator"}
        ),
        on="year",
        how="left",
    )
    direct = direct.merge(
        build_hybrid_tables(frame, _status_frame(frame))[0],
        on=["year", "candidate_slug"],
        how="left",
    )
    via_snapshot = build_national_rollup(
        frame, build_hybrid_tables(frame, _status_frame(frame))[0]
    )
    # Project the reference onto ROLLUP_COLUMNS, not onto whatever build_national_rollup
    # happened to return — reprojecting onto its own output can never detect a change to
    # the snapshot's column selection or order, which is half of what this pins.
    assert list(via_snapshot.columns) == list(ROLLUP_COLUMNS)
    pd.testing.assert_frame_equal(
        via_snapshot.reset_index(drop=True),
        direct[list(ROLLUP_COLUMNS)].reset_index(drop=True),
    )


def test_rollup_keeps_an_all_null_pv_year_denominator_null_not_zero() -> None:
    """The **second** ``min_count=1``, on the per-year denominator sum.

    A pre-popular-vote year must aggregate to NULL, never ``0``. Losing this
    ``min_count`` would publish "in 1972, 0 people voted" and hand E7's
    ``hybrid_preferred`` — which shares this derivation — a divide-by-zero ``pv_share``
    for every pre-1976 year.

    (This test used to explain itself by saying it had to call the roll-up *directly*
    because ``build_snapshot`` filtered pre-window years away. It no longer does — #139
    serves them — so the year now reaches the roll-up on the real path too, and
    :func:`usvote.snapshot.assert_no_pv_aggregate_below_mit_window` guards it there.)
    """
    slugged = add_candidate_slug(_ec_pv_frame())
    rollup = build_national_rollup(
        slugged, build_hybrid_tables(slugged, _status_frame())[0]
    )
    pre_window = rollup.loc[rollup["year"] == 1972]
    assert not pre_window.empty
    assert pre_window["national_pv_denominator"].isna().all()
    assert (pre_window["national_pv_denominator"] == 0).sum() == 0


# --- metadata / content-hash version ---------------------------------------


def test_meta_records_provenance(tmp_path: Path) -> None:
    out, meta = _build(tmp_path)
    assert meta.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert meta.source == "MIT"
    assert meta.license == "CC0-1.0"
    # Two provenances since #139 — most of the widened table is Archives EC data with
    # no popular vote at all, so a meta block naming only MIT would claim MIT reaches
    # 1824. Recorded in the artifact rather than hardcoded in the serving layer, so the
    # advertised source cannot drift from the one that was actually built.
    assert meta.ec_source == EC_SOURCE
    assert meta.ec_license == EC_LICENSE
    assert meta.build_timestamp == _TS.isoformat()
    data = _read(out, DATA_TABLE)
    assert meta.row_count == len(data)
    assert meta.candidate_count == data["candidate_slug"].nunique()
    meta_tbl = _read(out, META_TABLE)
    assert len(meta_tbl) == 1
    assert meta_tbl["snapshot_version"].iloc[0] == meta.snapshot_version


def test_version_is_content_hash_independent_of_timestamp(tmp_path: Path) -> None:
    # Two builds of the same data with DIFFERENT timestamps ⇒ identical version (D028).
    out_a = tmp_path / "a.sqlite"
    out_b = tmp_path / "b.sqlite"
    meta_a = build_snapshot(
        _ec_pv_frame(), str(out_a), pv_status_df=_status_frame(), build_timestamp=_TS
    )
    meta_b = build_snapshot(
        _ec_pv_frame(),
        str(out_b),
        pv_status_df=_status_frame(),
        build_timestamp=datetime(2030, 1, 1, tzinfo=UTC),
    )
    assert meta_a.snapshot_version == meta_b.snapshot_version
    assert meta_a.build_timestamp != meta_b.build_timestamp


def test_version_changes_when_data_changes(tmp_path: Path) -> None:
    base = build_snapshot(
        _ec_pv_frame(),
        str(tmp_path / "a.sqlite"),
        pv_status_df=_status_frame(),
        build_timestamp=_TS,
    )
    changed = _ec_pv_frame()
    changed.loc[changed["candidate"] == "Cand A", "candidate_votes"] = 42
    other = build_snapshot(
        changed,
        str(tmp_path / "b.sqlite"),
        pv_status_df=_status_frame(),
        build_timestamp=_TS,
    )
    assert base.snapshot_version != other.snapshot_version


# --- redistributable-only guard (D030) -------------------------------------


def test_redistributable_false_row_fails_loud() -> None:
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "redistributable"] = False
    with pytest.raises(SnapshotError, match="redistributable=false"):
        _build_raises(frame)


def test_non_mit_source_fails_loud() -> None:
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "source"] = "UCSB"
    with pytest.raises(SnapshotError, match="non-MIT source"):
        _build_raises(frame)


# --- atomic write -----------------------------------------------------------


def test_duplicate_grain_row_fails_loud(tmp_path: Path) -> None:
    # The ec_pv PRIMARY KEY (year, state, candidate_slug) makes a grain fan-out fail loud
    # at INSERT rather than silently shipping duplicates the content hash would bless.
    frame = _ec_pv_frame()
    dup = frame[
        (frame["year"] == 2020)
        & (frame["state"] == "Texas")
        & (frame["candidate"] == "Cand A")
    ]
    frame = pd.concat([frame, dup], ignore_index=True)
    with pytest.raises(sqlite3.IntegrityError):
        build_snapshot(
            frame,
            str(tmp_path / "snapshot.sqlite"),
            pv_status_df=_status_frame(frame),
            build_timestamp=_TS,
        )


def test_build_is_idempotent_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "snapshot.sqlite"
    first = build_snapshot(
        _ec_pv_frame(), str(out), pv_status_df=_status_frame(), build_timestamp=_TS
    )
    second = build_snapshot(
        _ec_pv_frame(), str(out), pv_status_df=_status_frame(), build_timestamp=_TS
    )
    assert first.snapshot_version == second.snapshot_version
    assert out.exists()


# --- live-DB read probe (offline, via a stub dbc) --------------------------


class _StubDBC:
    """Minimal stand-in exposing the one method ``read_redistributable`` calls."""

    def __init__(self, exists: bool) -> None:
        self._exists = exists
        self.closed = False

    def select_query_to_df(self, query: str, close: bool = False) -> pd.DataFrame:
        if "to_regclass" in query:
            rel = "dwh.ec_pv_redistributable" if self._exists else None
            return pd.DataFrame({"relation": [rel]})
        if "state_usps" in query:  # SELECT state, state_usps FROM dwh.state
            return pd.DataFrame(
                {"state": list(_USPS), "state_usps": list(_USPS.values())}
            )
        # The view read: return the frame WITHOUT the enrichment column (the view
        # itself does not carry state_usps — read_redistributable merges it in).
        return _ec_pv_frame().drop(columns=["state_usps"])

    def close_connection(self) -> None:
        self.closed = True


# --- the pv_status roster derivation (offline, over a full synthetic spine) -


def _full_spine() -> pd.DataFrame:
    """An EC participation frame covering every in-scope year and every catalog key.

    ``build_curated_roster`` cross-checks the catalog against the spine in both
    directions before deriving, so a *partial* spine is not a smaller version of the
    real one — it is one the catalog legitimately rejects. So this fabricates a complete
    one: every ``ec_ingest_years()`` year, every catalogued ``(year, state)`` at the
    electoral-vote count its status implies (``not_participating`` ⇒ 0, everything else
    ⇒ non-zero), plus one ordinary state per year to exercise the residual.
    """
    rows: list[dict[str, object]] = []
    for year in ec_ingest_years():
        rows.append(
            {"year": year, "state": "Ordinaryland", "is_total": False,
             "total_electoral_votes": 7}
        )
        rows.append(
            {"year": year, "state": None, "is_total": True,
             "total_electoral_votes": 100}
        )
    for (year, state), entry in PV_ABSENCE_CATALOG.items():
        rows.append({
            "year": year,
            "state": state,
            "is_total": False,
            "total_electoral_votes": (
                0 if entry.pv_status == PV_STATUS_NOT_PARTICIPATING else 5
            ),
        })
    return pd.DataFrame(rows)


class _RosterStubDBC:
    """Serves the one query ``read_ec_participation`` issues."""

    def __init__(self, spine: pd.DataFrame) -> None:
        self._spine = spine

    def select_query_to_df(self, query: str, close: bool = False) -> pd.DataFrame:
        assert "FROM dwh.votes" in query, query
        return self._spine


def test_roster_derivation_classifies_from_the_catalog_not_the_warehouse() -> None:
    """``derive_curated_pv_status_roster`` derives from the EC spine + the in-repo catalog.

    The licensing property in one test: no ``dwh.pv_state_status`` read happens (the
    stub serves only ``dwh.votes``), ``popular_vote`` is the residual, and the 32
    catalogued absences come back with their curated classifications.
    """
    roster = derive_curated_pv_status_roster(_RosterStubDBC(_full_spine()))  # type: ignore[arg-type]
    assert list(roster.columns) == ["year", "state", "pv_status"]
    by_key = {
        (int(y), str(s)): str(v)
        for y, s, v in zip(
            roster["year"], roster["state"], roster["pv_status"], strict=True
        )
    }
    # Every catalogued absence keeps its curated status ...
    for key, entry in PV_ABSENCE_CATALOG.items():
        assert by_key[key] == entry.pv_status, key
    # ... and everything else is the residual, which is what makes an absence
    # detectable at all: enumerate only the absences and a state that silently vanishes
    # cannot masquerade as one.
    assert by_key[(1824, "Ordinaryland")] == PV_STATUS_POPULAR_VOTE
    # The roster never carries `source` or the free-text `note` off this function.
    assert "source" not in roster.columns
    assert "note" not in roster.columns


def test_roster_derivation_fails_loud_on_a_short_warehouse() -> None:
    """A warehouse missing an election raises rather than yielding a narrower snapshot.

    This is the retired scoped-subset promise, made concrete. A snapshot silently short
    an election is a coverage gap rendered as a nonexistence — the same class of error
    the ``pv_status`` column exists to prevent one level down — so the build refuses.
    """
    short = _full_spine()
    short = short[short["year"] != 1872]
    with pytest.raises(SnapshotError, match="1872"):
        derive_curated_pv_status_roster(_RosterStubDBC(short))  # type: ignore[arg-type]


def test_read_missing_view_fails_loud() -> None:
    with pytest.raises(SnapshotError, match="does not exist"):
        read_redistributable(_StubDBC(exists=False))  # type: ignore[arg-type]


def test_read_present_view_enriches_with_state_usps() -> None:
    df = read_redistributable(_StubDBC(exists=True))  # type: ignore[arg-type]
    assert list(df.columns) == [*EC_PV_COLUMNS, "state_usps"]
    assert set(df["state_usps"]) == {"TX", "CA", "WA"}


def test_build_from_db_reads_then_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The glue: read the (stubbed) live view, build the snapshot, close the connection.

    ``derive_curated_pv_status_roster`` is stubbed out rather than exercised here: it
    cannot run against this module's three-state synthetic spine, because it derives the
    roster through the real absence catalog, whose cross-check requires every catalogued
    ``(year, state)`` to exist in the spine it is handed — so a fabricated spine makes
    every genuine 1860s entry look like a typo. This test owns the read→build→close
    wiring; the derivation itself is covered by the ``_full_spine`` tests above.

    **That gap is now closed (#150).**
    ``tests/integration/test_snapshot_build.py::test_snapshot_from_a_real_full_span_warehouse``
    builds a real 51-year EC+MIT warehouse from the local Archives corpus and snapshots
    it, so the derivation meets the *actual* ``dwh.votes`` — along with slug uniqueness
    over the real 96 candidates and the ``state_usps`` join. It is corpus-gated and
    skips in CI, so it does not cover this wiring on every run; that is what keeps this
    test worth having.
    """
    import usvote.snapshot as snapshot_mod
    from usvote.snapshot import build_snapshot_from_db

    monkeypatch.setattr(
        snapshot_mod, "derive_curated_pv_status_roster", lambda dbc, schema=None: _status_frame()
    )
    stub = _StubDBC(exists=True)
    out = tmp_path / "snapshot.sqlite"
    meta = build_snapshot_from_db(
        stub,  # type: ignore[arg-type]
        str(out),
        build_timestamp=_TS,
        close=True,
    )
    assert out.exists()
    assert meta.year_min == 1972
    assert meta.pv_year_min == 2016
    assert stub.closed


# --- #102 / E8-S8: the hybrid, flip and margin fields -----------------------


def _flipped_frame() -> pd.DataFrame:
    """:func:`_ec_pv_frame` with 2016's popular vote swapped so PV and EC disagree.

    The base fixture has **no flip** — in both 2016 and 2020 the same candidate leads
    the electoral college and the popular vote — so it cannot exercise the fields this
    story exists for. Swapping ``candidate_votes`` between C and D in 2016 makes C the
    popular-vote winner while D keeps the 55 electoral votes and the presidency, which
    is the 2000/2016 shape the acceptance criteria name.

    Built as a *separate* frame rather than by editing :func:`_ec_pv_frame` on purpose:
    the base fixture's content hash is pinned by other tests, and a flip is not the
    ordinary case a fixture should default to.
    """
    frame = _ec_pv_frame().copy()
    is_2016 = frame["year"] == 2016
    c = is_2016 & (frame["candidate"] == "Cand C")
    d = is_2016 & (frame["candidate"] == "Cand D")
    c_votes = frame.loc[c, "candidate_votes"].to_numpy()
    d_votes = frame.loc[d, "candidate_votes"].to_numpy()
    frame.loc[c, "candidate_votes"] = d_votes
    frame.loc[d, "candidate_votes"] = c_votes
    return frame


def _hybrid_summary_rows(out: Path) -> dict[int, dict[str, object]]:
    """Read the snapshot's ``hybrid_summary`` table back, keyed by year."""
    conn = sqlite3.connect(out)
    try:
        conn.row_factory = sqlite3.Row
        cols = ", ".join(SNAPSHOT_HYBRID_SUMMARY_COLUMNS)
        rows = conn.execute(f"SELECT {cols} FROM {HYBRID_SUMMARY_TABLE}").fetchall()
    finally:
        conn.close()
    return {int(r["year"]): dict(r) for r in rows}


def test_the_snapshot_writes_a_hybrid_summary_row_per_election(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    summary = _hybrid_summary_rows(out)
    assert set(summary) == {1972, 2016, 2020}, (
        "one row per served election — the table's grain is the year alone"
    )


def test_the_hybrid_summary_table_carries_the_contract_columns(
    tmp_path: Path,
) -> None:
    """The written table's columns are exactly the contract tuple, in order.

    Pins the DDL against the tuple. Without it a column appended to
    ``snapshot_schema.HYBRID_SUMMARY_COLUMNS`` but not to ``_create_tables`` would fail
    only at INSERT against a real build, and a column reordered in one but not the
    other would silently write values into the wrong fields.
    """
    out, _ = _build(tmp_path)
    conn = sqlite3.connect(out)
    try:
        cols = [r[1] for r in conn.execute(
            f"PRAGMA table_info({HYBRID_SUMMARY_TABLE})"
        ).fetchall()]
    finally:
        conn.close()
    assert tuple(cols) == SNAPSHOT_HYBRID_SUMMARY_COLUMNS


def test_a_popular_vote_flip_is_reported_with_its_margins(tmp_path: Path) -> None:
    """The acceptance criteria's flip case, end to end through the snapshot.

    C leads the popular vote, D holds 55 of the 93 electoral votes and took office, so
    ``pv_flip`` is **true**. This is the assertion the base fixture cannot make.
    """
    out, _ = _build(tmp_path, frame=_flipped_frame())
    row = _hybrid_summary_rows(out)[2016]

    assert row["ec_winner"] == "Cand D"
    assert row["pv_winner"] == "Cand C"
    assert bool(row["pv_flip"]) is True
    # Slugs ship beside the names so a consumer can pivot to /v1/candidates/{slug}
    # without matching on a display name.
    assert row["ec_winner_slug"] == "cand-d"
    assert row["pv_winner_slug"] == "cand-c"
    # Percentage points, and strictly positive: a flip with a zero margin would mean a
    # tie, which `assert_no_winner_tie` rejects before the build gets here.
    assert isinstance(row["pv_margin"], float) and row["pv_margin"] > 0.0
    assert isinstance(row["ec_margin"], float) and row["ec_margin"] > 0.0


def test_a_year_without_a_flip_reports_false_not_null(tmp_path: Path) -> None:
    """The negative leg — ``false`` and ``null`` must not be confused.

    2020's PV and EC winners agree, so ``pv_flip`` is ``False``. Asserting this beside
    the flip case is what stops a regression that returns NULL everywhere from reading
    as "no flips found".
    """
    out, _ = _build(tmp_path)
    row = _hybrid_summary_rows(out)[2020]
    assert row["pv_flip"] is not None, "an agreeing year is False, never NULL"
    assert bool(row["pv_flip"]) is False


def test_the_pre_window_year_has_null_pv_fields_but_real_ec_ones(
    tmp_path: Path,
) -> None:
    """1972 (pre-PV-window): the PV half is NULL, the EC half is real.

    The distinction #102 turns on. A method with no popular vote has no winner, no flip
    and no margin — but the electoral college is fully recorded, so its winner, margin
    and denominator are populated. Collapsing the two halves into "the year is empty"
    is exactly the missing-vs-zero error this surface exists to avoid.
    """
    out, _ = _build(tmp_path)
    row = _hybrid_summary_rows(out)[1972]

    assert row["pv_winner"] is None
    assert row["pv_winner_slug"] is None
    assert row["hybrid_winner"] is None
    assert row["pv_flip"] is None, "no winner ⇒ NULL, never False and never True"
    assert row["hybrid_flip"] is None
    assert row["pv_margin"] is None
    assert row["hybrid_margin"] is None

    assert row["ec_winner"] == "Richard Nixon"
    assert row["ec_winner_slug"] == "richard-nixon"
    assert row["ec_margin"] is not None
    assert row["ec_denominator"] is not None


def test_pv_coverage_is_real_before_the_pv_window(tmp_path: Path) -> None:
    """The point of deriving coverage from the curated roster rather than the warehouse.

    1972's roster marks Washington ``legislature_chosen``, so coverage is a real
    fraction strictly between 0 and 1 — **not** the NULL that
    ``hybrid_redistributable`` reports for every pre-window year, and not a fabricated
    ``0``. This is the one column where the snapshot and the warehouse view diverge on
    purpose (D048's action item for #102).
    """
    out, _ = _build(tmp_path)
    coverage = _hybrid_summary_rows(out)[1972]["pv_coverage"]
    assert isinstance(coverage, float), (
        "coverage comes from the in-repo catalog, which reaches every served year — "
        f"got {coverage!r}"
    )
    assert 0.0 < coverage < 1.0


def test_the_rollup_carries_the_five_per_candidate_hybrid_fields(
    tmp_path: Path,
) -> None:
    """The per-candidate half lands on ``national_rollup``, not a sibling table."""
    out, _ = _build(tmp_path)
    conn = sqlite3.connect(out)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM {ROLLUP_TABLE} WHERE year = 2020"  # noqa: S608
        ).fetchall()
    finally:
        conn.close()
    # dict(), not `in row`: membership on a sqlite3.Row tests VALUES, not column names,
    # so `field in rows[0]` is silently the wrong question (and passed here only
    # because it then failed for the right reason).
    present = dict(rows[0])
    for field in (
        "ec_share_full",
        "pv_share",
        "ec_share_hybrid",
        "pv_coverage",
        "hybrid_score",
    ):
        assert field in present
        assert all(r[field] is not None for r in rows), (
            f"{field} must be populated inside the popular-vote window"
        )


def test_the_two_ec_shares_are_equal_under_the_shipped_policy(
    tmp_path: Path,
) -> None:
    """``ec_share_hybrid == ec_share_full`` — the D037/A safety property, made visible.

    The published coverage policy never restricts the electoral share, so no coverage
    rule can manufacture a majority that did not exist. Both columns ship precisely so
    a consumer can check that rather than take it on trust; this test is the same check
    on the build side.
    """
    out, _ = _build(tmp_path)
    conn = sqlite3.connect(out)
    try:
        rows = conn.execute(
            f"SELECT ec_share_full, ec_share_hybrid FROM {ROLLUP_TABLE}"  # noqa: S608
        ).fetchall()
    finally:
        conn.close()
    assert rows
    for full, hybrid_share in rows:
        assert full == hybrid_share


@pytest.mark.parametrize("column", ["pv_share", "hybrid_score"])
def test_the_rollup_guard_rejects_a_pre_window_hybrid_share(column: str) -> None:
    """The roll-up's pre-window guard reaches the two PV-derived hybrid columns.

    **Exercised on the guard directly, and that is not laziness — it is the only way.**
    The realistic route in (give 1972 a popular vote so its shares become non-null) is
    caught *upstream* by ``assert_mit_year_floor``, which fires on the raw frame before
    the roll-up is ever built. So a build-level test would pass while asserting nothing
    about these two columns: it would be green because a **different** guard stopped it.
    Calling the guard with a frame it would actually see is what pins the column list.

    The sibling ``test_the_hybrid_summary_guard_rejects_a_pre_window_value`` covers the
    other new table for the same reason.
    """
    rollup = pd.DataFrame(
        {
            "year": [1972],
            "candidate_slug": ["someone"],
            "national_pv_votes": [None],
            "national_pv_denominator": [None],
            "pv_share": [None],
            "hybrid_score": [None],
        }
    )
    rollup[column] = [0.5]
    with pytest.raises(SnapshotError, match=column):
        assert_no_pv_aggregate_below_mit_window(rollup)


def test_the_rollup_guard_permits_the_columns_that_are_real_pre_window() -> None:
    """The **exclusions**, which matter as much as the inclusions.

    ``ec_share_full``, ``ec_share_hybrid`` and ``pv_coverage`` are populated for every
    served year and must NOT be guarded — a guard over ``pv_coverage`` in particular
    would reject exactly the thing #102 shipped, since deriving it from the in-repo
    catalog is what makes it real before 1976. Without this test, "guard everything
    that looks PV-ish" is a one-line change that passes its sibling above.
    """
    rollup = pd.DataFrame(
        {
            "year": [1972],
            "candidate_slug": ["someone"],
            "national_pv_votes": [None],
            "national_pv_denominator": [None],
            "pv_share": [None],
            "hybrid_score": [None],
            "ec_share_full": [0.61],
            "ec_share_hybrid": [0.61],
            "pv_coverage": [0.72],
        }
    )
    assert_no_pv_aggregate_below_mit_window(rollup)


_HYBRID_SUMMARY_GUARDED = (
    ("pv_margin", 1.5),
    ("hybrid_margin", 1.5),
    ("pv_flip", True),
    ("hybrid_flip", True),
    ("pv_winner", "Somebody"),
    ("pv_winner_slug", "somebody"),
    ("hybrid_winner", "Somebody"),
    ("hybrid_winner_slug", "somebody"),
)


@pytest.mark.parametrize(("column", "value"), _HYBRID_SUMMARY_GUARDED)
def test_the_hybrid_summary_guard_rejects_a_pre_window_value(
    column: str, value: object
) -> None:
    """:func:`assert_no_hybrid_pv_below_mit_window` fires on each guarded column.

    Exercised directly because the build-level guards upstream of it would catch the
    realistic route in. What this pins is that the summary table has a guard **of its
    own** — the roll-up guard cannot see this table — and that the guard covers every
    column it claims to.

    The four winner columns were added at code review; this leg is what pins them.
    """
    summary = pd.DataFrame(
        {
            "year": [1972],
            **{col: [None] for col, _ in _HYBRID_SUMMARY_GUARDED},
        }
    )
    summary[column] = [value]
    with pytest.raises(SnapshotError, match=column):
        assert_no_hybrid_pv_below_mit_window(summary)


def test_the_hybrid_summary_guard_passes_a_clean_pre_window_row() -> None:
    """The negative leg: an all-NULL pre-window row is fine, so the guard is not vacuous.

    Without this, a guard that raised unconditionally would satisfy every leg above.
    """
    summary = pd.DataFrame(
        {
            "year": [1972],
            **{col: [None] for col, _ in _HYBRID_SUMMARY_GUARDED},
        }
    )
    assert_no_hybrid_pv_below_mit_window(summary)


def test_the_schema_version_moved_for_the_new_shape() -> None:
    """AC-2: the content hash covers ``ec_pv`` only, so the version moves by hand.

    A literal, deliberately. Comparing the constant to itself would pass under any
    value; the whole obligation is that a human moved it when the derived tables
    changed shape, and only a literal records that.
    """
    assert SNAPSHOT_SCHEMA_VERSION == 3


def test_the_summary_tuple_is_contained_by_the_warehouse_tuple() -> None:
    """``snapshot_schema.HYBRID_SUMMARY_COLUMNS`` ⊆ the warehouse tuple + the slugs.

    **The test the schema docstring claimed and this change originally did not write**
    (caught at code review). Without it the one-way containment is a comment, not a
    guard.

    Note precisely what does and does not keep a warehouse column off the public
    payload. **This assert does not** — it subtracts the warehouse tuple, so growing
    that tuple only grows the subtrahend and leaves this green. What denies automatic
    reach is that the snapshot tuple is a **hand-written literal**: a new warehouse
    column arrives on the public surface only when someone types it here too.

    **A subset assert, and the direction is the whole point.** The reverse — asserting
    the snapshot tuple covers the warehouse tuple — is **forbidden** (D047 §3), for the
    same reason it is forbidden for ``DATA_COLUMNS`` against ``EC_PV_COLUMNS``: coupling
    them would undo the decoupling. What this catches is a hand-typed name in the
    snapshot tuple that no warehouse column supplies, which would ``KeyError`` only
    against a real warehouse — on the one machine that has one.
    """
    derived = {"ec_winner_slug", "pv_winner_slug", "hybrid_winner_slug"}
    unexplained = (
        set(SNAPSHOT_HYBRID_SUMMARY_COLUMNS)
        - set(hybrid.HYBRID_SUMMARY_COLUMNS)
        - derived
    )
    assert not unexplained, (
        "hybrid_summary columns that no warehouse column supplies and that are not "
        f"minted by the build: {unexplained}"
    )
    # Non-vacuity: the derived set must actually be needed, or the assert above would
    # pass with `derived` empty and stop pinning anything about the slugs.
    assert derived <= set(SNAPSHOT_HYBRID_SUMMARY_COLUMNS)
    assert not (derived & set(hybrid.HYBRID_SUMMARY_COLUMNS)), (
        "the slug columns are minted by the snapshot build; if the warehouse view "
        "starts carrying them, this test's `derived` allowance is hiding a real overlap"
    )
