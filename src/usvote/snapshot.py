"""Materialize ``ec_pv_redistributable`` into a read-only SQLite snapshot (E8-S1, #95).

The API's **only** data source (D028): the snapshot is built here from the local
warehouse, and the running API (``usvote/api/``, E8-S2) reads the artifact with **no
live DB at serve time**. Keeping the build here — a new top-level EC-domain consumer of
``ec_pv_redistributable`` in the :mod:`usvote.spine` / :mod:`usvote.join` /
:mod:`usvote.warehouse` family (composition-root-exempt from D015 per D027) — is what
makes the DB-free property *structural*: ``usvote/api/`` imports the artifact + a thin
repository, never :mod:`usvote.db`. This module names ``ec_pv_redistributable`` (EC
star-schema knowledge), so like :mod:`usvote.join` it stays out of ``usvote/pv/``.

**The serving contract (what E8-S2/S3 consume).** A SQLite file with three tables:

``ec_pv`` — the joined fact, one row per ``(year, state, candidate_slug)`` over the
    **full EC span, 1824–2024** (#139 / D048; it was the MIT-only 1976–2024 window until
    then). Every EC state row is kept (winners *and* 0-EV losers — the dense-fact rows
    the thesis needs, D026); PV columns are NULL wherever no redistributable popular
    vote exists, which after the widening is most of the table. Indexed on ``year`` /
    ``state`` / ``candidate_slug`` for the by-year/by-state/by-candidate endpoints
    (#97). The internal surrogate ``candidate_id`` is **dropped** (D006 /
    ``docs/canonical-keys.md``) and replaced by ``candidate_slug`` — the durable public
    candidate id minted here. ``state_usps`` is carried alongside the full
    ``state`` name as a clean URL/path key for ``/v1/states/{...}`` (#97).

    **A NULL popular vote is never bare.** Every row carries a ``pv_status`` saying
    which kind of nothing it is: ``legislature_chosen`` (the state's legislature
    appointed the electors — no popular vote was ever held), ``not_participating`` (the
    state took no part in the election), or ``popular_vote`` (one was held; whether
    *this* surface carries it is the separate question ``meta.pv_year_min`` answers).
    Widening the window without this column would commit, on the public artifact, the
    exact missing-vs-zero conflation this project exists to describe.

``national_rollup`` — one row per ``(year, candidate_slug)`` with the per-candidate
    national EC total (the view's window sum), its **counted** twin (D046), the year's
    **appointed** electoral denominator (D041), and the national PV total (+ its own
    denominator), so ``/v1/elections/{year}/summary`` (#97) **reads** the roll-up
    instead of computing it in a route handler. Safe to precompute because the
    redistributable PV window is **single-source (MIT)**, so the D017 cross-source
    -denominator caveat does not bite. The EC denominator is here because a counted
    total alone is not checkable — 1872's Grant is 286 *of 366*, and re-deriving the 366
    from the fact table is the multiply-by-candidate-count trap
    :func:`usvote.hybrid.ec_denominator_by_year` exists to prevent.

``snapshot_meta`` — one row of provenance for the API ``meta`` block: the content-hash
    ``snapshot_version``, the schema version, row/candidate counts, the served window
    (``year_min`` / ``year_max``) **and the narrower redistributable-PV sub-window**
    (``pv_year_min`` / ``pv_year_max``), the PV ``source`` = MIT with its ``license``
    (CC0-1.0, read from the ``pv_source`` reference data, not hardcoded), the EC
    ``ec_source`` / ``ec_license`` (the National Archives; a U.S. Government work), and
    an **informational-only** build timestamp. Two provenances, because after #139 the
    surface has two: most of the table is Archives EC data with no popular vote at all,
    and a ``meta`` block naming only MIT would assert MIT covers 1824 (D048).

**Version = content hash, not timestamp (D028).** ``snapshot_version`` is a SHA-256
over the ``ec_pv`` rows in a deterministic ``ORDER BY (year, state, candidate_slug)``
plus the schema version; the build timestamp is excluded from it. This reconciles the
two requirements that would otherwise conflict — byte-reproducibility ("same warehouse,
same version") and the ETag freshness contract ("identical data, identical version") —
and is why the timestamp is metadata only.

**Redistributable-only guaranteed at the source (D030).** The build reads
``ec_pv_redistributable`` (which wraps ``pv_redistributable``, defined independently as
``WHERE redistributable``, D017), and :func:`assert_redistributable_only` re-asserts
that no ``redistributable = false`` / non-MIT row entered the snapshot — the first of
the three defense-in-depth guards (source here, endpoints in #97, regression in #99).

Build it with ``python -m usvote.snapshot`` (needs the local warehouse; writes to
``USVOTE_API_SNAPSHOT_PATH``). The pure builder :func:`build_snapshot` takes an
in-memory ``ec_pv_redistributable``-shaped frame, so the whole contract is unit-tested
offline from a small synthetic frame — no live DB.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from usvote import config
from usvote.config import ConfigError
from usvote.count_status import COUNT_STATUS_REASON_COLUMN
from usvote.db import DBC, DBConnectionError
from usvote.hybrid import (
    HybridError,
    build_hybrid_from_frames,
    ec_denominator_by_year,
    roll_up_national,
)
from usvote.join import EC_PV_REDISTRIBUTABLE_VIEW
from usvote.load import SCHEMA
from usvote.pv.absences import build_curated_roster
from usvote.pv.source import (
    MIT_PV_YEAR_MIN,
    SOURCE_MIT,
    assert_mit_year_floor,
    build_pv_source_frame,
)
from usvote.pv.status import (
    PV_STATUS_POPULAR_VOTE,
    assert_roster_shape,
    assert_unique_roster_grain,
)
from usvote.slug import candidate_slug
from usvote.snapshot_schema import (
    DATA_COLUMNS,
    DATA_TABLE,
    EC_LICENSE,
    EC_SOURCE,
    HYBRID_SUMMARY_TABLE,
    META_TABLE,
    ROLLUP_COLUMNS,
    ROLLUP_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotMeta,
)

# Aliased: usvote.hybrid exports a same-named tuple that names winners by display name
# only; this snapshot tuple adds the three *_slug columns. Tests import both, so the
# alias keeps them distinct.
from usvote.snapshot_schema import (
    HYBRID_SUMMARY_COLUMNS as SNAPSHOT_HYBRID_SUMMARY_COLUMNS,
)
from usvote.spine import read_ec_participation
from usvote.transform import COUNT_STATUS_OVERRIDES
from usvote.years import ec_ingest_years

#: The :data:`~usvote.snapshot_schema.DATA_COLUMNS` entries that are **not**
#: :data:`usvote.join.EC_PV_COLUMNS` names — minted or merged *here* during the build
#: rather than carried through from the view. It lives beside the code that derives them
#: rather than in ``snapshot_schema``: that module is the stdlib-only build↔serve
#: contract the container ships, and this set has no serving-side reader.
#:
#: A test asserts the *safe* direction (every ``DATA_COLUMNS`` entry is either a
#: join-view column or one of these), which catches a hand-typed name that would
#: otherwise ``KeyError`` only against a real warehouse — the synthetic frame is
#: hand-authored too, so the same misspelling in both passes the offline suite.
#: **The reverse direction is forbidden** (D047 §3): do not assert that ``DATA_COLUMNS``
#: covers ``EC_PV_COLUMNS``. Their independence is what let #144 add join-view columns
#: without changing the public payload or the content hash.
DERIVED_DATA_COLUMNS: frozenset[str] = frozenset(
    {"state_usps", "candidate_slug", "pv_status"}
)

#: The name of the EC state dimension the build reads ``state_usps`` from. Reading a
#: second *relation* (not a second path to the join view) is fine — the AC's "reuse the
#: view, no second hand-rolled SQL path" is about the view, and ``state_usps`` is a
#: clean URL/path key for ``/v1/states/{...}`` (#97) the view itself does not carry.
STATE_DIM = "state"

#: The ``source`` value handed to :func:`usvote.pv.absences.build_curated_roster`, which
#: requires the kwarg and deliberately defines no ``SOURCE_CURATED`` literal of its own
#: ("naming a source value would pre-commit a decision that belongs to whoever loads
#: it"). #139 does not *load* the roster — it derives one in memory and throws the
#: column away — so the literal is private here rather than public there.
#:
#: :func:`derive_curated_pv_status_roster` **projects the column off** before the
#: frame is returned; it never reaches ``build_snapshot``, the merge, or SQLite. That is
#: structural, not conventional: :func:`assert_redistributable_only` reads a column
#: literally named ``source``, so a second frame carrying one anywhere near the build is
#: a live hazard, and "we drop it later" is a comment, not a guarantee.
_CURATED_ROSTER_SOURCE = "CURATED"

#: The columns :func:`derive_curated_pv_status_roster` returns — the roster narrowed
#: to what the broadcast needs. Notably **not** ``note``: the curated roster's is null
#: by construction, and the public surface never carries roster free text (D022/D024).
_ROSTER_MERGE_COLUMNS: tuple[str, ...] = ("year", "state", "pv_status")

#: The vocabulary ``count_status_reason`` may draw from — the Archives' own sentences,
#: curated in :data:`usvote.transform.COUNT_STATUS_OVERRIDES`. See
#: :func:`assert_count_status_reasons_are_catalogued` for what pinning to it does and
#: does not prove; the short version is that it bounds *which* sentences ship, not where
#: they came from.
_ALLOWED_COUNT_STATUS_REASONS: frozenset[str] = frozenset(
    reason for _, reason in COUNT_STATUS_OVERRIDES.values()
)

#: Integer-valued columns that the EC-left join returns as float64 (LEFT-JOIN NULLs make
#: NaN). Cast to nullable ``Int64`` before hashing/writing so ``150`` never becomes
#: ``150.0`` (which would make the content hash depend on pandas' float formatting) and
#: so NULLs land as SQL NULL, not the float ``NaN``.
_INTEGER_COLUMNS: tuple[str, ...] = (
    "total_electoral_votes",
    "president_electoral_votes",
    "national_electoral_votes",
    "president_electoral_rank",
    "candidate_votes",
    "state_total_votes",
    # The counted measure (D046). Its national twin is never NULL at state grain
    # (D047's action item says so explicitly), but it costs nothing to normalize both
    # and the cast keeps the content hash independent of pandas' float formatting.
    "president_electoral_votes_counted",
    "national_counted_electoral_votes",
)

#: The deterministic order the content hash and the ``ec_pv`` rows are written in.
_ORDER_BY: tuple[str, ...] = ("year", "state", "candidate_slug")


class SnapshotError(RuntimeError):
    """Raised when the snapshot build violates an E8-S1 invariant.

    Covers a non-redistributable row reaching the build (D030), a slug collision
    (``docs/canonical-keys.md`` same-name residual), or a missing source view — each a
    fail-loud condition rather than a silently degraded snapshot.
    """


def _mit_license() -> str:
    """Return MIT's license from the ``pv_source`` reference data (D017: data not code).

    The redistributable surface is MIT-only, so the snapshot's license is MIT's — read
    from :func:`usvote.pv.source.build_pv_source_frame` rather than duplicating the
    literal, so a license edit stays a one-row change in the reference table.
    """
    src = build_pv_source_frame()
    return str(src.loc[src["source"] == SOURCE_MIT, "license"].iloc[0])


def assert_redistributable_only(ec_pv_df: pd.DataFrame) -> None:
    """Assert no ``redistributable = false`` / non-MIT row is present (D030, guard 1/3).

    The source view ``ec_pv_redistributable`` already wraps ``pv_redistributable``
    (``WHERE redistributable``, D017), so this can only fail on a regression — which is
    exactly when a licensing guard must fail loud rather than trust the upstream. A
    getter MIT does not cover has NULL PV (``source``/``redistributable`` NULL), which
    is fine — an honest D005 gap, not a non-redistributable row; only an explicit
    ``False`` or a non-MIT ``source`` is a violation.
    """
    if "redistributable" in ec_pv_df.columns:
        bad = ec_pv_df["redistributable"] == False  # noqa: E712 — NULL must NOT match
        if bool(bad.any()):
            # ``candidate_slug`` is not minted until after this guard, so report the
            # raw canonical key columns that exist on the source frame here.
            cols = ["year", "state", "candidate"]
            raise SnapshotError(
                "redistributable=false row(s) reached the snapshot build — the "
                "redistributable-only surface (D030) was violated upstream: "
                f"{ec_pv_df.loc[bad, cols].head().values.tolist()}"
            )
    non_mit = ec_pv_df["source"].dropna().ne(SOURCE_MIT)
    if bool(non_mit.any()):
        offenders = sorted(ec_pv_df["source"].dropna()[non_mit].unique())
        raise SnapshotError(
            f"non-MIT source(s) {offenders} reached the redistributable snapshot "
            "(D016/D030) — only MIT is redistributable."
        )


def add_candidate_slug(ec_pv_df: pd.DataFrame) -> pd.DataFrame:
    """Return ``ec_pv_df`` with a ``candidate_slug`` column, failing on a collision.

    The slug is the durable **public** candidate id (D006 / ``docs/canonical-keys.md`` —
    ``candidate_id`` is an internal surrogate that must never leave the warehouse). It
    is derived deterministically from the canonical ``candidate`` name via
    :func:`usvote.slug.candidate_slug`. A **same-name collision** (two distinct
    canonical names mapping to one slug) is the known residual documented in
    ``docs/canonical-keys.md``; it would silently merge two people on the API surface,
    so it raises here rather than being written.
    """
    out = ec_pv_df.copy()
    out["candidate_slug"] = out["candidate"].map(candidate_slug)
    name_to_slug = out[["candidate", "candidate_slug"]].drop_duplicates()
    collisions = name_to_slug[name_to_slug["candidate_slug"].duplicated(keep=False)]
    if not collisions.empty:
        grouped = (
            collisions.groupby("candidate_slug")["candidate"].apply(list).to_dict()
        )
        raise SnapshotError(
            "candidate slug collision — two canonical names share one slug (the "
            f"docs/canonical-keys.md same-name residual): {grouped}"
        )
    empty = out.loc[out["candidate_slug"] == "", "candidate"].unique().tolist()
    if empty:
        raise SnapshotError(f"candidate name(s) produced an empty slug: {empty}")
    return out


def _snapshot_years(ec_pv_df: pd.DataFrame) -> list[int]:
    """The **served** window: every election year in the frame (1824–2024).

    ``ec_pv_redistributable`` is EC-**left**, so it carries every EC state row from 1824
    on with PV attached only where MIT covers it. Until #139 the build filtered those
    rows away and served only the years that had PV; the rows were already arriving, so
    the widening is one deleted filter rather than a new pipeline.

    Serving them is the point of #134/D048: 38 of the 51 in-scope elections had no
    reachable public record here, and the posts that turn on 1824's 261-vote
    denominator or 1872's rejected votes pointed readers at a surface that 404'd. Kept
    honest by the sibling :func:`_pv_years` — the two windows now genuinely differ, and
    ``meta`` says so rather than leaving a reader to infer it from NULLs.
    """
    return sorted(int(y) for y in ec_pv_df["year"].unique())


def _pv_years(ec_pv_df: pd.DataFrame) -> list[int]:
    """The **redistributable popular-vote** sub-window: the years that actually have PV.

    Was ``_covered_years``, and was the whole served window before #139. It still gates
    the "MIT was never loaded" build failure and still supplies ``meta.pv_year_min`` /
    ``pv_year_max`` — it simply no longer decides which rows ship.
    """
    with_pv = ec_pv_df.loc[ec_pv_df["candidate_votes"].notna(), "year"]
    return sorted(int(y) for y in with_pv.unique())


def add_pv_status(ec_pv_df: pd.DataFrame, pv_status_df: pd.DataFrame) -> pd.DataFrame:
    """Broadcast the ``(year, state)`` ``pv_status`` onto every candidate row.

    The column that keeps a NULL ``candidate_votes`` from being bare (D024/D048). It is
    a column on the fact rather than a fourth snapshot table for four reasons, the last
    of which is decisive: the contract is a **row-level sibling pairing**, so a column
    realizes it literally; the repository needs no join; "no bare NULL" becomes a
    ``NOT NULL`` column constraint instead of a cross-table invariant; and the column is
    **covered by the content hash for free**, where a separate table would ship a stale
    ETag on a roster correction that left the facts untouched.

    Three merge properties, each guarding a failure the others cannot see:

    1. ``validate="m:1"`` — a duplicated roster key would otherwise fan the fact out and
       be caught three steps later by the ``PRIMARY KEY`` at INSERT, pointing at the
       symptom rather than the cause.
    2. The merge must add **exactly** ``{"pv_status"}``. This is the structural form of
       "and no ``source`` / ``note`` column came along for the ride" — the one that
       matters, since :func:`assert_redistributable_only` keys on a column named
       ``source`` and roster free text must never reach the public surface.
    3. Every ``(year, state)`` in the fact must find a status — the completeness
       anti-join, read off the merge result rather than a second dry-run merge. It is
       the only guard here that :mod:`usvote.pv.status` cannot provide, because only
       this module knows the fact frame.

    Run **after** :func:`assert_redistributable_only`, which reads ``source``.
    """
    before = set(ec_pv_df.columns)
    try:
        out = ec_pv_df.merge(
            pv_status_df, on=["year", "state"], how="left", validate="m:1"
        )
    except pd.errors.MergeError as e:
        raise SnapshotError(
            f"the pv_status roster is not unique on (year, state): {e}. A duplicated "
            "roster key would fan out the fact table — caught here rather than three "
            "steps later at the ec_pv PRIMARY KEY, which would point at the symptom."
        ) from e
    added = set(out.columns) - before
    if added != {"pv_status"}:
        raise SnapshotError(
            f"the pv_status broadcast added {sorted(added)}, not exactly "
            "{'pv_status'} — the roster frame carried extra columns into the public "
            "fact. Roster provenance and free text must not reach the snapshot "
            "(D022/D030); project the roster in derive_curated_pv_status_roster."
        )
    absent = out.loc[out["pv_status"].isna(), ["year", "state"]].drop_duplicates()
    if not absent.empty:
        raise SnapshotError(
            f"{len(absent)} (year, state) key(s) in the fact have no pv_status: "
            f"{absent.values.tolist()[:10]}. Every served row must say which kind of "
            "'no popular vote' it is (D024/D048) — a bare NULL popular vote is the "
            "missing-vs-zero conflation this column exists to prevent. The roster "
            "derives from the EC spine, so this means the spine and the join view "
            "disagree about which states took part."
        )
    return out


def assert_modern_years_are_popular_vote(data_df: pd.DataFrame) -> None:
    """Assert every row from :data:`MIT_PV_YEAR_MIN` on is ``pv_status='popular_vote'``.

    Free, and it makes structural the reason two rosters can coexist without being
    reconciled by hand. :mod:`usvote.hybrid` reads ``dwh.pv_state_status`` (UCSB + MIT)
    for ``pv_coverage``; the snapshot derives its own from the in-repo catalog. They
    agree over the modern window **by construction** — the catalog's own integrity test
    guarantees no :data:`~usvote.pv.absences.PV_ABSENCE_CATALOG` key falls at or after
    :data:`MIT_PV_YEAR_MIN`, so over those years ``build_curated_roster`` and
    ``build_popular_vote_roster`` are the same derivation with the same empty effective
    absence map.

    "By construction" is a fact about today's catalog, though, not a law. A future
    absence entry in a modern year would silently make the public roster disagree with
    the analysis one, so the property is checked here rather than trusted.
    """
    modern = data_df[data_df["year"] >= MIT_PV_YEAR_MIN]
    bad = modern[modern["pv_status"] != PV_STATUS_POPULAR_VOTE]
    if not bad.empty:
        offenders = bad[["year", "state", "pv_status"]].drop_duplicates()
        raise SnapshotError(
            f"{len(bad)} row(s) at or after {MIT_PV_YEAR_MIN} carry a pv_status other "
            f"than {PV_STATUS_POPULAR_VOTE!r}: {offenders.values.tolist()[:10]}"
            ". The public roster (the in-repo catalog) and the analysis roster "
            "(dwh.pv_state_status) agree over the MIT window only while the catalog "
            "records no absence there — see usvote.pv.absences."
        )


def assert_count_status_reasons_are_catalogued(data_df: pd.DataFrame) -> None:
    """Assert every served ``count_status_reason`` comes from the curated map.

    ``count_status_reason`` is the one free-text column on the public surface. It is
    admissible because it is the **Archives' own sentence** — a U.S. Government work,
    17 U.S.C. § 105 — where ``pv_state_status.note`` is UCSB prose and is not (D022 /
    D044 §3).

    **What this guard does and does not establish** (code review, #139 — an earlier
    draft of this docstring overclaimed). It is a *containment* check: only sentences
    present in :data:`usvote.transform.COUNT_STATUS_OVERRIDES` may reach the snapshot.
    That catches a value arriving from anywhere other than the curated map — a
    hand-edited warehouse, a migration, a future second writer of the column — which is
    real coverage, since the snapshot is built from whatever ``dwh.votes`` holds.

    It is **not** a provenance check, and the analogy to the ``pv_status`` enum only
    goes so far. ``PV_STATUS_VALUES`` is closed in a module no correction workflow
    touches, so a new value cannot appear without a deliberate contract change.
    ``COUNT_STATUS_OVERRIDES`` is the opposite: it is *precisely* where a new correction
    gets added. Paste non-Archives prose there and the transform writes it, this assert
    accepts it, and it ships. So on the ordinary pipeline this check is close to
    tautological, and the thing actually keeping non-public-domain text off the surface
    is review of the catalog itself — where each entry carries its Archives URL in a
    comment. Making that citation machine-checkable (a per-entry source field, asserted
    to be an ``archives.gov`` URL) is the change that would close the gap; it belongs
    with the catalog in :mod:`usvote.transform`, not here.
    """
    reasons = data_df[COUNT_STATUS_REASON_COLUMN].dropna()
    unknown = sorted(set(reasons) - _ALLOWED_COUNT_STATUS_REASONS)
    if unknown:
        raise SnapshotError(
            f"{len(unknown)} count_status_reason value(s) are not in the curated "
            f"Archives vocabulary: {[r[:80] for r in unknown]}. Only the sentences in "
            "usvote.transform.COUNT_STATUS_OVERRIDES may reach the public surface — "
            "they are U.S. Government works and carry no redistribution restriction "
            "(D044 §3). Free text from any other source must not ship (D022/D030)."
        )


def assert_no_pv_below_mit_window(data_df: pd.DataFrame) -> None:
    """Assert no **fact** row below :data:`MIT_PV_YEAR_MIN` carries popular-vote data.

    The fact-level member of the pre-window guard family;
    :func:`assert_no_pv_aggregate_below_mit_window` covers the roll-up and
    :func:`assert_no_hybrid_pv_below_mit_window` the hybrid summary. This one covers the
    table the API actually serves.
    """
    _assert_no_pv_below_window(
        data_df,
        columns=("candidate_votes", "state_total_votes"),
        key_columns=("year", "state", "candidate"),
        kind="fact row",
    )


def assert_no_pv_aggregate_below_mit_window(rollup_df: pd.DataFrame) -> None:
    """Assert the roll-up carries no PV aggregate below :data:`MIT_PV_YEAR_MIN`.

    **The floor is a constant, never derived from the frame** — and that is the single
    most important line in this function. The obvious spelling, "the lowest year that
    has any PV", is *vacuous under exactly the failure a floor guard exists to catch*:
    repoint the build at ``ec_pv_preferred`` and pre-1976 suddenly has UCSB PV, so the
    observed floor slides to 1824 and the assert passes over everything it was meant to
    stop. An external invariant cannot slide. See
    :data:`usvote.pv.source.MIT_PV_YEAR_MIN`.

    **What it uniquely catches is a fabricated zero, not laundered UCSB.** Worth
    stating precisely, or this reads as redundant and gets deleted: against a repoint
    to ``ec_pv_preferred``, :func:`assert_redistributable_only` already fires first,
    because UCSB rows carry ``source='UCSB'``. The failure *nothing else sees* is a
    regression in ``min_count=1`` inside :func:`usvote.hybrid.roll_up_national`, which
    would turn an all-NULL pre-1976 year into a national popular vote of ``0`` — a
    correctness bug, not a licensing one, and one that would publish "in 1860, 0 people
    voted" with every other guard green.

    **``pv_share`` and ``hybrid_score`` joined the guarded set in #102**, and only those
    two of the five new hybrid columns. Both are NULL pre-window because both divide by
    a popular vote that is not there, so a non-null value is the same fabricated zero
    this guard exists to catch, one derivation further on. The other three are
    deliberately **not** guarded: ``ec_share_full`` and ``ec_share_hybrid`` are real
    pre-1976 (the EC record is complete back to 1824, and policy (b) leaves the two
    equal), and ``pv_coverage`` is real there **by design** — deriving it from the
    in-repo catalog instead of the warehouse roster is what #102 changed, so guarding it
    would reject the feature.
    """
    _assert_no_pv_below_window(
        rollup_df,
        columns=(
            "national_pv_votes",
            "national_pv_denominator",
            "pv_share",
            "hybrid_score",
        ),
        key_columns=("year", "candidate_slug"),
        kind="roll-up row",
    )


def _assert_no_pv_below_window(
    df: pd.DataFrame,
    *,
    columns: tuple[str, ...],
    key_columns: tuple[str, ...],
    kind: str,
) -> None:
    """Shared body of the two pre-window guards — same check, two frames.

    Kept as one implementation so the floor semantics, the message and the row-sample
    cap cannot drift between them; the *reasons* the two exist differ and live in their
    respective callers' docstrings, which is where a reader looks.
    """
    pre = df[df["year"] < MIT_PV_YEAR_MIN]
    for col in columns:
        bad = pre[pre[col].notna()]
        if not bad.empty:
            sample = bad[list(key_columns)].head(10).values.tolist()
            raise SnapshotError(
                f"{len(bad)} {kind}(s) below {MIT_PV_YEAR_MIN} carry a non-null "
                f"{col}: {sample}. A year with no popular vote must stay NULL, never "
                "0 — a fabricated zero is the missing-vs-zero error this surface "
                "exists to avoid (D030/D048)."
            )


def build_national_rollup(
    data_df: pd.DataFrame, hybrid_fields: pd.DataFrame
) -> pd.DataFrame:
    """Precompute the per-``(year, candidate_slug)`` national roll-up (#97's summary).

    ``hybrid_fields`` is :func:`build_hybrid_tables`' first return value. Required, not
    optional: a default would let a caller silently emit an all-NULL hybrid roll-up.

    - ``national_electoral_votes`` — the view's window sum, constant per candidate-year,
      so ``first`` is exact.
    - ``national_pv_votes`` — ``sum(candidate_votes)`` over the candidate's state rows,
      with ``min_count=1`` so a getter with **no** PV stays NULL (honest), not a fake 0.
    - ``national_pv_denominator`` — the year's total votes cast: each state's
      ``state_total_votes`` counted **once** then summed. This pins to MIT's *provided*
      per-state denominator, never a re-sum of candidate rows (D017). Single-source
      (MIT) window, so there is no cross-source denominator ambiguity to reconcile.

    The per-state total is taken as the **non-null** ``state_total_votes`` for each
    ``(year, state)`` (``max`` skips NA), *not* an arbitrary deduped row: MIT broadcasts
    the same per-state denominator onto every candidate row in the state, but a no-PV
    getter (a faithless elector) carries a NULL ``state_total_votes``. A plain
    ``drop_duplicates(["year", "state"])`` keeps the first row in ``(year, state,
    candidate_slug)`` order, which is that NULL row whenever the getter's slug sorts
    first — silently dropping the whole state from the national denominator.

    **The derivation itself lives in** :func:`usvote.hybrid.roll_up_national` **(D037/F,
    OQ4-resolved)** — E7's hybrid frame needs the identical roll-up at the identical
    grain, and two hand-written copies of the subtleties above would drift. This
    function keeps ownership of the snapshot's *contract* (the group key is the public
    ``candidate_slug``, D006; the column set is :data:`ROLLUP_COLUMNS`) and delegates
    the arithmetic. The extraction is behaviour-preserving: neither the source view, nor
    the public columns, nor ``SNAPSHOT_SCHEMA_VERSION`` changes.

    Importing ``usvote.hybrid`` here is a build-side import and crosses no boundary —
    this module already carries pandas and the DB stack. It is ``usvote/api/`` that may
    never reach either (D028), which ``tests/unit/test_api_import_graph.py`` enforces.
    """
    rollup = roll_up_national(
        data_df,
        key=("year", "candidate_slug"),
        carry={
            "candidate": "candidate",
            "party": "party",
            "national_electoral_votes": "national_electoral_votes",
            "national_counted_electoral_votes": "national_counted_electoral_votes",
            "president_electoral_rank": "president_electoral_rank",
            "took_office": "took_office",
        },
    )
    # The appointed denominator (D041) — per *year*, not per candidate, so it merges
    # rather than carries. Delegated for the same reason the roll-up itself is: a bare
    # aggregate over the joined rows would multiply every state's allotment by the
    # candidate count, and `ec_denominator_by_year` is the one place that subtlety is
    # already solved. This is what makes the counted total checkable — "286" means
    # nothing without "of 366".
    # `ec_denominator_by_year` raises HybridError — a RuntimeError, not a SnapshotError
    # — when an allotment is inconsistent within a (year, state). Re-raised as ours so
    # `_run_build` reports "Snapshot build failed" and exits 3 rather than dumping a
    # traceback and exiting 1.
    try:
        denominator = ec_denominator_by_year(data_df).rename(
            columns={"ec_denominator": "national_electoral_denominator"}
        )
    except HybridError as e:
        raise SnapshotError(
            f"the appointed electoral denominator could not be derived: {e}"
        ) from e
    rollup = rollup.merge(denominator, on="year", how="left", validate="m:1")
    # `validate="1:1"` rejects a slug that collapses two candidate_ids, which would fan
    # the roll-up out rather than fail.
    try:
        rollup = rollup.merge(
            hybrid_fields, on=["year", "candidate_slug"], how="left", validate="1:1"
        )
    except pd.errors.MergeError as e:
        raise SnapshotError(
            f"the hybrid fields do not join the roll-up one-to-one: {e}"
        ) from e
    return rollup[list(ROLLUP_COLUMNS)]


#: The columns :func:`usvote.hybrid.build_hybrid_frame` contributes to the roll-up
#: (#102).
_HYBRID_ROLLUP_FIELDS: tuple[str, ...] = (
    "ec_share_full",
    "pv_share",
    "ec_share_hybrid",
    "pv_coverage",
    "hybrid_score",
)

#: The three ``(winner name column, winner slug column)`` pairs on the summary (#102).
_WINNER_SLUG_PAIRS: tuple[tuple[str, str], ...] = (
    ("ec_winner", "ec_winner_slug"),
    ("pv_winner", "pv_winner_slug"),
    ("hybrid_winner", "hybrid_winner_slug"),
)


def build_hybrid_tables(
    slugged_df: pd.DataFrame, pv_status_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Derive the hybrid at both grains, keyed on the public ``candidate_slug``.

    Returns ``(per-candidate fields, per-election summary)``.

    Recomputes via :func:`usvote.hybrid.build_hybrid_from_frames` on the **curated**
    roster rather than reading ``hybrid_redistributable``, which keeps ``pv_coverage``
    off the UCSB-derived warehouse roster (D048/D053) and inherits that function's
    guards.

    **The one intended divergence:** before the popular-vote window this
    ``pv_coverage`` is real where the warehouse view's is NULL. Nothing else differs —
    under policy (b) ``pv_coverage`` is the only roster-dependent output.
    """
    # `_run_build` catches only SnapshotError, so an un-wrapped HybridError would
    # escape as a bare traceback and exit 1 rather than exit 3.
    try:
        frame, summary = build_hybrid_from_frames(slugged_df, pv_status_df)
    except HybridError as e:
        raise SnapshotError(f"the hybrid computation failed its own guards: {e}") from e

    id_to_slug = slugged_df[["candidate_id", "candidate_slug"]].drop_duplicates()
    # `m:1`, not `1:1`: the frame's grain is (year, candidate_id), so a candidate who
    # ran twice appears once per year. What must be unique is the RIGHT side.
    try:
        per_candidate = frame.merge(
            id_to_slug, on="candidate_id", how="left", validate="m:1"
        )
    except pd.errors.MergeError as e:
        # `m:1` fails when the RIGHT side is not unique, i.e. one candidate_id maps to
        # more than one slug. (Two ids sharing one slug is a different fault, and
        # `add_candidate_slug` rejects it before this point.)
        raise SnapshotError(
            f"one candidate_id maps to more than one candidate_slug: {e}"
        ) from e
    missing = per_candidate["candidate_slug"].isna()
    if bool(missing.any()):
        # Cannot happen while the frame is built from `slugged_df`; asserted because a
        # silent NaN slug here would merge every unmatched candidate into one roll-up
        # row rather than failing.
        raise SnapshotError(
            "hybrid frame carries candidate_id(s) absent from the slug map: "
            f"{per_candidate.loc[missing, 'candidate_id'].unique().tolist()}"
        )
    per_candidate = per_candidate[
        ["year", "candidate_slug", *_HYBRID_ROLLUP_FIELDS]
    ]

    name_to_slug = dict(
        slugged_df[["candidate", "candidate_slug"]].drop_duplicates().values
    )
    out = summary.copy()
    for name_col, slug_col in _WINNER_SLUG_PAIRS:
        # `.map` on a dict yields NaN for a missing key; a NULL winner (a method with no
        # scored candidate) must stay NULL rather than become the string "nan".
        out[slug_col] = out[name_col].map(name_to_slug).astype("object")
        out.loc[out[name_col].isna(), slug_col] = None
        unmapped = out[slug_col].isna() & out[name_col].notna()
        if bool(unmapped.any()):
            raise SnapshotError(
                "hybrid summary names a winner absent from the slug map: "
                f"{out.loc[unmapped, name_col].unique().tolist()}"
            )
    return per_candidate, out[list(SNAPSHOT_HYBRID_SUMMARY_COLUMNS)]


def assert_no_hybrid_pv_below_mit_window(summary_df: pd.DataFrame) -> None:
    """Assert the hybrid summary carries no PV-derived value below the PV window.

    The third member of the pre-window guard family
    (:func:`assert_no_pv_below_mit_window` covers the fact table,
    :func:`assert_no_pv_aggregate_below_mit_window` the roll-up); #102 added a table
    neither sees.

    **The exclusions are the point.** ``ec_margin``, ``ec_denominator``,
    ``ec_determinative`` and the EC winner are **real** pre-1976 — the electoral-college
    record is complete back to 1824 — and so is ``pv_coverage``, which #102 repointed at
    the in-repo catalog. Guarding any of them would reject the feature this issue
    shipped.
    """
    pre = summary_df[summary_df["year"] < MIT_PV_YEAR_MIN]
    for col in (
        "pv_margin",
        "hybrid_margin",
        "pv_flip",
        "hybrid_flip",
        "pv_winner",
        "pv_winner_slug",
        "hybrid_winner",
        "hybrid_winner_slug",
    ):
        bad = pre[pre[col].notna()]
        if not bad.empty:
            raise SnapshotError(
                f"{len(bad)} hybrid-summary row(s) below {MIT_PV_YEAR_MIN} carry a "
                f"non-null {col}: {bad['year'].head(10).tolist()}. A method with no "
                "popular vote has no winner and no margin — NULL, never 0 and never "
                "False (D005/D048)."
            )


def _to_int64(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Cast ``columns`` to nullable ``Int64`` (LEFT-JOIN floats/NaN → clean ints/NA)."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = out[col].astype("Int64")
    return out


def _rows(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    """DataFrame → native-Python row tuples for :meth:`sqlite3.executemany`.

    Mirrors the NaN/NA → ``None`` + numpy-unbox normalization the DB write boundary does
    (:func:`usvote.db._df_to_sql_rows`); sqlite3 rejects pandas ``NA`` / numpy scalars
    just as psycopg2 does. Kept local (a few lines) rather than importing that module's
    private helper.
    """
    return [
        tuple(
            None if pd.isna(v) else v.item() if isinstance(v, np.generic) else v
            for v in row
        )
        for row in df.itertuples(index=False, name=None)
    ]


def _content_hash(data_df: pd.DataFrame) -> str:
    """SHA-256 of the ``ec_pv`` rows (deterministic order) + the schema version (D028).

    The build timestamp is *not* mixed in — identical warehouse data must yield an
    identical version so the ETag (E8-S2) is content-addressed and the build is
    reproducible. Rows are serialized field-by-field with control-char separators that
    cannot occur in the data, after the integer cast so numeric formatting is stable.
    """
    ordered = data_df.sort_values(list(_ORDER_BY), kind="stable")
    h = hashlib.sha256()
    h.update(f"schema={SNAPSHOT_SCHEMA_VERSION}\x1e".encode())
    for row in _rows(ordered[list(DATA_COLUMNS)]):
        h.update("\x1f".join("" if v is None else str(v) for v in row).encode())
        h.update(b"\x1e")
    return h.hexdigest()


def build_snapshot(
    ec_pv_df: pd.DataFrame,
    out_path: str,
    *,
    pv_status_df: pd.DataFrame,
    build_timestamp: datetime | None = None,
) -> SnapshotMeta:
    """Build the SQLite snapshot from an ``ec_pv_redistributable``-shaped frame.

    ``ec_pv_df`` is the view frame (:data:`usvote.join.EC_PV_COLUMNS`) enriched with
    ``state_usps`` — exactly what :func:`read_redistributable` produces.
    ``pv_status_df`` is the ``(year, state, pv_status)`` roster
    :func:`derive_curated_pv_status_roster` derives. The pure core, unit-tested
    offline from synthetic frames (no DB).

    **Why the roster arrives as an argument rather than being derived here.** The
    obvious simplification — call :func:`~usvote.pv.absences.build_curated_roster`
    inside this function — cannot work, and the reason is worth stating so nobody
    re-introduces it: that derivation runs
    :func:`~usvote.pv.absences.assert_catalog_matches_spine` unconditionally, whose
    phantom-key check fails the moment the spine it is handed is a *synthetic* one.
    A fixture with a pre-1976 year but only two states would make ``(1860, "South
    Carolina")`` a phantom key and kill the build. So the catalog-bound derivation lives
    on the DB side, where it sees the real spine, and the builder takes a frame.

    Steps: assert redistributable-only (D030); broadcast ``pv_status``
    (:func:`add_pv_status`, *after* the redistributable guard, which reads a column
    named ``source``); mint the candidate slug + drop ``candidate_id`` (D006)
    **over the whole frame** — see the note below; derive the hybrid at both grains
    (:func:`build_hybrid_tables`); precompute the national roll-up and run all three
    pre-window guards; content-hash the fact rows (D028); and write the
    four tables to ``out_path`` atomically (temp file + ``os.replace``) so a partial
    write never leaves a corrupt snapshot.

    **The content hash still covers the ``ec_pv`` fact rows only**, so #102's new
    ``hybrid_summary`` table and the roll-up's five new columns are **invisible** to it
    — which is exactly why :data:`SNAPSHOT_SCHEMA_VERSION` had to move by hand (2 → 3).
    Widening the hash to cover the derived tables was considered and rejected: the
    version is a *content* address for the facts, and a derived table that changed while
    the facts did not is a code change, which the schema version is the right instrument
    for.

    **Slugs are minted over every row, and the old ordering is gone.** This used to
    filter to the served window *first* so that a collision between two candidates the
    snapshot would never ship could not fail a build. That rationale evaporated with
    #139: every candidate 1824–2024 now ships, so slug uniqueness must hold across all
    of them, and a collision is a real, build-blocking defect — the same-name residual
    ``docs/canonical-keys.md`` describes, to be resolved there rather than dodged here.

    ``build_timestamp`` is injectable for deterministic tests; it is informational
    metadata only, never part of the version.
    """
    assert_redistributable_only(ec_pv_df)

    years = _snapshot_years(ec_pv_df)
    if not years:
        raise SnapshotError(
            "the source view is empty — the snapshot would have no rows at all; build "
            "the warehouse (run_warehouse) first."
        )
    pv_years = _pv_years(ec_pv_df)
    if not pv_years:
        raise SnapshotError(
            "no redistributable PV rows in the source view — the snapshot would carry "
            "electoral-college data with no popular vote anywhere; build the warehouse "
            "(run_warehouse) with MIT loaded first."
        )
    assert_mit_year_floor(pv_years, error_cls=SnapshotError, caller="build_snapshot")

    with_status = add_pv_status(ec_pv_df, pv_status_df)
    slugged = add_candidate_slug(with_status)

    data_df = _to_int64(slugged, _INTEGER_COLUMNS)[list(DATA_COLUMNS)]
    data_df = data_df.sort_values(list(_ORDER_BY), kind="stable").reset_index(drop=True)
    assert_modern_years_are_popular_vote(data_df)
    assert_count_status_reasons_are_catalogued(data_df)
    assert_no_pv_below_mit_window(data_df)

    # The hybrid is derived from `slugged` (the join-view shape, which still carries
    # `candidate_id`) and the **curated** roster, never from `hybrid_redistributable` —
    # see `build_hybrid_tables` for why, and for the one intended divergence.
    hybrid_fields, hybrid_summary_df = build_hybrid_tables(slugged, pv_status_df)

    rollup_df = _to_int64(
        build_national_rollup(data_df, hybrid_fields),
        (
            "national_electoral_votes",
            "national_counted_electoral_votes",
            "national_electoral_denominator",
            "president_electoral_rank",
            "national_pv_votes",
            "national_pv_denominator",
        ),
    )
    assert_no_pv_aggregate_below_mit_window(rollup_df)
    hybrid_summary_df = _to_int64(hybrid_summary_df, ("ec_denominator",))
    assert_no_hybrid_pv_below_mit_window(hybrid_summary_df)

    ts = build_timestamp if build_timestamp is not None else datetime.now(UTC)
    meta = SnapshotMeta(
        snapshot_version=_content_hash(data_df),
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        row_count=len(data_df),
        candidate_count=int(data_df["candidate_slug"].nunique()),
        year_min=years[0],
        year_max=years[-1],
        pv_year_min=pv_years[0],
        pv_year_max=pv_years[-1],
        source=SOURCE_MIT,
        license=_mit_license(),
        ec_source=EC_SOURCE,
        ec_license=EC_LICENSE,
        build_timestamp=ts.isoformat(),
    )
    _write_sqlite(out_path, data_df, rollup_df, hybrid_summary_df, meta)
    return meta


def _write_sqlite(
    out_path: str,
    data_df: pd.DataFrame,
    rollup_df: pd.DataFrame,
    hybrid_summary_df: pd.DataFrame,
    meta: SnapshotMeta,
) -> None:
    """Write the four tables to a fresh SQLite file at ``out_path``, atomically.

    Built into a temp file in the same directory then ``os.replace``-d over ``out_path``
    so a reader (or a re-run) never sees a half-written snapshot. The file is opened
    fresh each build (idempotent overwrite); the snapshot is immutable once served.
    """
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".sqlite", dir=out_dir)
    os.close(fd)
    try:
        conn = sqlite3.connect(tmp_path)
        try:
            _create_tables(conn)
            conn.executemany(
                f"INSERT INTO {DATA_TABLE} ({','.join(DATA_COLUMNS)}) "
                f"VALUES ({','.join('?' * len(DATA_COLUMNS))})",
                _rows(data_df),
            )
            conn.executemany(
                f"INSERT INTO {ROLLUP_TABLE} ({','.join(ROLLUP_COLUMNS)}) "
                f"VALUES ({','.join('?' * len(ROLLUP_COLUMNS))})",
                _rows(rollup_df),
            )
            cols = SNAPSHOT_HYBRID_SUMMARY_COLUMNS
            conn.executemany(
                f"INSERT INTO {HYBRID_SUMMARY_TABLE} ({','.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})",
                _rows(hybrid_summary_df),
            )
            meta_cols = tuple(asdict(meta))
            conn.execute(
                f"INSERT INTO {META_TABLE} ({','.join(meta_cols)}) "
                f"VALUES ({','.join('?' * len(meta_cols))})",
                tuple(asdict(meta).values()),
            )
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp_path, out_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create the four snapshot tables (+ indexes): ``ec_pv``, ``national_rollup``,
    ``hybrid_summary``, ``snapshot_meta``.
    """
    conn.execute(
        f"CREATE TABLE {DATA_TABLE} ("
        " year INTEGER NOT NULL,"
        " state TEXT NOT NULL,"
        " state_usps TEXT NOT NULL,"
        " candidate TEXT NOT NULL,"
        " candidate_slug TEXT NOT NULL,"
        " total_electoral_votes INTEGER,"
        " president_electoral_votes INTEGER,"
        " national_electoral_votes INTEGER,"
        " president_electoral_rank INTEGER,"
        " took_office INTEGER,"
        " source TEXT,"
        " party TEXT,"
        " candidate_votes INTEGER,"
        " state_total_votes INTEGER,"
        " reliability TEXT,"
        # NOT NULL is the point, not decoration: "a NULL popular vote is never bare"
        # (D048) is a per-row promise, so it is enforced per row by the store rather
        # than by a build-time assert alone.
        " pv_status TEXT NOT NULL,"
        " president_electoral_votes_counted INTEGER,"
        " national_counted_electoral_votes INTEGER,"
        " count_status TEXT NOT NULL,"
        " count_status_reason TEXT,"
        # Canonical grain (D026): one row per (year, state, candidate_slug). A PRIMARY
        # KEY makes a join-view / slug-mapping fan-out fail loud at INSERT (matching
        # national_rollup's own PK guard and the "validation is load-bearing" rule)
        # rather than silently shipping duplicates the content hash would bless.
        " PRIMARY KEY (year, state, candidate_slug))"
    )
    # No separate year index: the (year, ...) PRIMARY KEY already serves year lookups
    # via its leftmost-prefix. state / state_usps / slug each need their own.
    conn.execute(f"CREATE INDEX idx_{DATA_TABLE}_state ON {DATA_TABLE}(state)")
    conn.execute(f"CREATE INDEX idx_{DATA_TABLE}_usps ON {DATA_TABLE}(state_usps)")
    conn.execute(
        f"CREATE INDEX idx_{DATA_TABLE}_slug ON {DATA_TABLE}(candidate_slug)"
    )
    conn.execute(
        f"CREATE TABLE {ROLLUP_TABLE} ("
        " year INTEGER NOT NULL,"
        " candidate TEXT NOT NULL,"
        " candidate_slug TEXT NOT NULL,"
        " party TEXT,"
        " national_electoral_votes INTEGER,"
        " president_electoral_rank INTEGER,"
        " took_office INTEGER,"
        " national_pv_votes INTEGER,"
        " national_pv_denominator INTEGER,"
        " national_counted_electoral_votes INTEGER,"
        " national_electoral_denominator INTEGER,"
        # --- #102: the five per-candidate hybrid fields. REAL, not INTEGER: every one
        # is a ratio in [0, 1]. All five nullable.
        " ec_share_full REAL,"
        " pv_share REAL,"
        " ec_share_hybrid REAL,"
        " pv_coverage REAL,"
        " hybrid_score REAL,"
        " PRIMARY KEY (year, candidate_slug))"
    )
    conn.execute(
        f"CREATE TABLE {HYBRID_SUMMARY_TABLE} ("
        # One row per election -- hence `year` alone as the PRIMARY KEY, which also
        # makes a fan-out from the summary derivation fail loud at INSERT rather than
        # ship duplicate years (the same reasoning as the two tables above).
        " year INTEGER NOT NULL PRIMARY KEY,"
        " ec_denominator INTEGER,"
        # No NOT NULL on ec_winner: it happens to be populated for every year served,
        # but that is a property of the data, and a constraint would turn a future gap
        # into a build crash rather than an honest NULL.
        " ec_winner TEXT,"
        " ec_winner_slug TEXT,"
        " pv_winner TEXT,"
        " pv_winner_slug TEXT,"
        " hybrid_winner TEXT,"
        " hybrid_winner_slug TEXT,"
        # INTEGER because SQLite has no boolean, matching `took_office` above.
        " ec_determinative INTEGER,"
        " pv_coverage REAL,"
        " pv_flip INTEGER,"
        " hybrid_flip INTEGER,"
        " ec_margin REAL,"
        " pv_margin REAL,"
        " hybrid_margin REAL)"
    )
    conn.execute(
        f"CREATE TABLE {META_TABLE} ("
        " snapshot_version TEXT NOT NULL,"
        " schema_version INTEGER NOT NULL,"
        " row_count INTEGER NOT NULL,"
        " candidate_count INTEGER NOT NULL,"
        " year_min INTEGER NOT NULL,"
        " year_max INTEGER NOT NULL,"
        " pv_year_min INTEGER NOT NULL,"
        " pv_year_max INTEGER NOT NULL,"
        " source TEXT NOT NULL,"
        " license TEXT NOT NULL,"
        " ec_source TEXT NOT NULL,"
        " ec_license TEXT NOT NULL,"
        " build_timestamp TEXT NOT NULL)"
    )


# --- live-DB read + CLI -----------------------------------------------------


def _relation_exists(dbc: DBC, schema: str, name: str) -> bool:
    """Return whether ``schema.name`` exists, via ``to_regclass`` (NULL when absent).

    The cheap, non-raising existence probe :func:`read_redistributable` uses to turn a
    missing view into a clear precondition. Kept local — the same idiom as
    :func:`usvote.join._relation_exists` and :func:`usvote.pv.load._relation_exists`, so
    ``usvote.snapshot`` does not reach into another module's private helper (the
    project's established layering convention).
    """
    got = dbc.select_query_to_df(f"SELECT to_regclass('{schema}.{name}') AS relation")
    return got["relation"].iloc[0] is not None


def read_redistributable(dbc: DBC, *, schema: str = SCHEMA) -> pd.DataFrame:
    """Read ``ec_pv_redistributable`` (+ ``state_usps``), failing loud if absent.

    Reuses the ``join.py`` view-name **constant** (no second hand-rolled SQL path to the
    view) and the shared existence probe, turning a missing view into a clear
    precondition pointing the operator at ``run_warehouse`` — not an opaque
    ``OperationalError`` deep in the read. Then left-joins ``state_usps`` from the
    ``dwh.state`` dimension (a different relation, not a second path to the view) so the
    snapshot carries a clean URL/path key for ``/v1/states/{...}`` (#97) that the view
    itself does not expose. Local Postgres is required here, at build time **only**; the
    served API never opens this connection (D028).
    """
    if not _relation_exists(dbc, schema, EC_PV_REDISTRIBUTABLE_VIEW):
        raise SnapshotError(
            f"{schema}.{EC_PV_REDISTRIBUTABLE_VIEW} does not exist — build the "
            "warehouse first (`python -m usvote all`, i.e. usvote.warehouse."
            "run_warehouse, which creates the EC<->PV join views)."
        )
    ec_pv = dbc.select_query_to_df(
        f"SELECT * FROM {schema}.{EC_PV_REDISTRIBUTABLE_VIEW}"
    )
    state_usps = dbc.select_query_to_df(
        f"SELECT state, state_usps FROM {schema}.{STATE_DIM}"
    )
    return ec_pv.merge(state_usps, on="state", how="left")


def derive_curated_pv_status_roster(dbc: DBC, *, schema: str = SCHEMA) -> pd.DataFrame:
    """Derive the ``(year, state, pv_status)`` roster from the EC spine + the catalog.

    **Named "derive", not "read", to keep it distinguishable from
    :func:`usvote.hybrid.read_pv_status_roster`** — which *does* ``SELECT ... FROM
    dwh.pv_state_status`` and is UCSB-inclusive. The two have opposite provenance rules
    and this module already imports from :mod:`usvote.hybrid`, so a shared name would
    leave a future contributor one plausible "simplification" away from pulling the
    warehouse roster into the public build: it would compile, pass, and quietly put
    UCSB-derived values on the public artifact. The layering test cannot catch that —
    it blocks importing ``usvote.ucsb``, not reading a table UCSB populated.

    The public surface's answer to "why is this popular vote NULL?", and it is built
    **without reading ``dwh.pv_state_status`` at all**. That is the whole point (D048,
    implementing #134's option (C)): the warehouse roster's pre-1976 rows are
    UCSB-derived, UCSB grants no redistribution rights (D022), and the artifact being
    built here *is* the public surface. So membership comes from the EC spine (Archives,
    public domain) and the classifications come from :mod:`usvote.pv.absences` — 32
    in-repo entries, each carrying a public-domain citation — with ``popular_vote`` as
    the residual. UCSB's roster is demoted to a cross-source **control** that validates
    this one, never an input to it.

    :func:`~usvote.pv.absences.build_curated_roster` cross-checks the catalog against
    the spine in both directions before deriving, so a typo'd state name or a newly
    zero-EV state cannot slip through as an ordinary ``popular_vote``.

    **Scope is the full ingest span, and a short warehouse fails loud.** Passing
    ``ec_ingest_years()`` means a warehouse missing an election raises here rather than
    yielding a quietly narrower snapshot. That retires the scoped-subset promise
    ``SnapshotMeta`` used to make, deliberately: a snapshot silently missing 1868 is the
    same class of error — a gap rendered as a nonexistence — that the ``pv_status``
    column exists to prevent one level down.

    The ``source`` column is projected off before returning; see
    :data:`_CURATED_ROSTER_SOURCE`.
    """
    participation = read_ec_participation(dbc, schema=schema)
    roster = build_curated_roster(
        participation,
        source=_CURATED_ROSTER_SOURCE,
        years=ec_ingest_years(),
        error_cls=SnapshotError,
    )
    # Both already exist in the shared contract module and are already tested there;
    # calling them is deliberate reuse, not belt-and-braces. `assert_roster_shape` is
    # the closed-enum guard (a pv_status outside the three values cannot ship, which is
    # the structural form of "the enum ships, the expression does not") and needs the
    # full ROSTER_COLUMNS shape, so it runs before the projection below.
    assert_roster_shape(roster, error_cls=SnapshotError)
    assert_unique_roster_grain(roster, error_cls=SnapshotError)
    return roster[list(_ROSTER_MERGE_COLUMNS)]


def build_snapshot_from_db(
    dbc: DBC,
    out_path: str,
    *,
    schema: str = SCHEMA,
    build_timestamp: datetime | None = None,
    close: bool = False,
) -> SnapshotMeta:
    """Read the live view and build the snapshot — the glue behind the CLI."""
    try:
        ec_pv_df = read_redistributable(dbc, schema=schema)
        pv_status_df = derive_curated_pv_status_roster(dbc, schema=schema)
        return build_snapshot(
            ec_pv_df,
            out_path,
            pv_status_df=pv_status_df,
            build_timestamp=build_timestamp,
        )
    finally:
        if close:
            dbc.close_connection()


def _run_build(environ: Mapping[str, str], out_override: str | None) -> int:
    import getpass

    try:
        out_path = out_override or config.snapshot_path_from_env(environ)
        db_config: dict[str, Any] = config.db_config_from_env(environ)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if "password" not in db_config:
        db_config["password"] = getpass.getpass(
            f"Password for {db_config['user']}@{db_config['host']}: "
        )
    try:
        dbc = DBC(db_config)
    except DBConnectionError as e:
        print(e, file=sys.stderr)
        return 1

    try:
        meta = build_snapshot_from_db(dbc, out_path, close=True)
    except SnapshotError as e:
        print(f"Snapshot build failed: {e}", file=sys.stderr)
        return 3
    print(
        f"Wrote snapshot to {out_path} "
        f"(version {meta.snapshot_version[:12]}…, {meta.row_count} rows, "
        f"{meta.candidate_count} candidates, {meta.year_min}–{meta.year_max}; "
        f"popular vote {meta.pv_year_min}–{meta.pv_year_max})."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usvote.snapshot",
        description=(
            "Build the read-only SQLite API snapshot from dwh.ec_pv_redistributable "
            "(E8-S1, D028). Requires the local warehouse at build time only."
        ),
    )
    parser.add_argument(
        "-o",
        "--out",
        default=None,
        help="Output snapshot path (overrides USVOTE_API_SNAPSHOT_PATH).",
    )
    args = parser.parse_args(argv)
    return _run_build(os.environ, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
