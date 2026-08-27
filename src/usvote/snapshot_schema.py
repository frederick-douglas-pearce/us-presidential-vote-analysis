"""The API snapshot's serving contract — table names, columns, version, meta shape.

Deliberately **dependency-free** (stdlib only, like :mod:`usvote.slug`): it imports
neither :mod:`usvote.db` nor pandas. That is the point. The snapshot *build*
(:mod:`usvote.snapshot`) needs Postgres and pandas, but the *serving* layer
(``usvote/api/``, E8-S2) must not — D028 makes "no live DB at serve time" a **structural
import-graph invariant** (a test there asserts nothing under ``usvote/api/`` imports
``usvote.db``/psycopg2). Both sides need the same column names, table names, schema
version, and ``meta`` shape, so those live here where either can import them without
dragging the DB stack across the API's import boundary.

Only the *contract* lives here — the names and shapes E8-S2/S3 must agree on. Build-time
mechanics (the content-hash order, the integer-cast set, the SQL/SQLite writers) stay in
:mod:`usvote.snapshot`, which imports these.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Bump when the snapshot's table shape or the roll-up's derivation logic changes. A
#: consumer keys compatibility off it, and :mod:`usvote.snapshot` folds it into the
#: content hash so a shape change forces a new ``snapshot_version``. **Because the hash
#: covers only the ``ec_pv`` data rows (not the derived roll-up), a change to how the
#: roll-up is computed with identical underlying data would NOT move the hash on
#: its own — so a roll-up-logic change MUST bump this version.**
#:
#: ``2`` (#139 / D048) — the served window widened from the MIT-only 1976–2024 to the
#: full EC span 1824–2024; ``ec_pv`` gained ``pv_status``, the counted electoral-vote
#: measure and the count status; ``national_rollup`` gained the counted national total
#: and the appointed denominator; ``snapshot_meta`` gained the PV sub-window and the EC
#: source/license. A snapshot and the image that serves it must cut over **together**
#: (D034) — :meth:`usvote.api.repository.SnapshotRepository.open` hard-fails on a
#: mismatch, which is the intended fail-loud, not a deploy bug.
#:
#: ``3`` (#102 / E8-S8) — the three-method comparison ships. ``national_rollup`` gained
#: the five per-candidate hybrid fields (the two EC shares, the PV share, the coverage
#: flag and the hybrid score); a new ``hybrid_summary`` table carries the per-election
#: grain (three winners, two flips, three margins). Nothing was removed and no existing
#: column changed meaning.
SNAPSHOT_SCHEMA_VERSION = 3

#: The **electoral-college** provenance codes (#139 / D048), written into
#: ``snapshot_meta`` by every build. The PV codes are read from the ``pv_source``
#: reference table (D017: data, not code) because they vary per source and a license
#: grant is a one-row edit; the EC side has exactly one source that cannot change
#: without the whole pipeline changing, and no reference table to read it from, so the
#: codes are constants here — beside the contract that carries them, and stdlib-only so
#: the serving layer can name them too.
#:
#: Archives pages are works of the U.S. Government and so carry no copyright
#: (17 U.S.C. § 105) — which is *why* ``count_status_reason`` may ship the Archives' own
#: sentence where ``pv_state_status.note`` (UCSB prose) may not (D022/D044 §3).
EC_SOURCE = "NARA"
EC_LICENSE = "US-PD"

#: The four snapshot tables (the serving contract E8-S2/S3 read).
DATA_TABLE = "ec_pv"
ROLLUP_TABLE = "national_rollup"
#: The per-**election** grain (#102 / E8-S8). A fourth table rather than more columns on
#: ``national_rollup``, because its grain is ``year`` alone: the three winners, the two
#: flips and the three margins are properties of the *election*, and broadcasting them
#: across a per-candidate table would repeat one year's answer once per candidate and
#: invite a consumer to group by the wrong key.
HYBRID_SUMMARY_TABLE = "hybrid_summary"
META_TABLE = "snapshot_meta"

#: The ``ec_pv`` fact columns, in order. This is ``usvote.join.EC_PV_COLUMNS`` with the
#: internal ``candidate_id`` **dropped** (D006), ``candidate_slug`` inserted after the
#: canonical ``candidate`` name, ``state_usps`` carried alongside the full ``state``
#: name (a clean URL/path key for ``/v1/states/{...}``, #97), and ``redistributable``
#: dropped (constant-true here — recorded once in ``snapshot_meta.source``).
DATA_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "state_usps",
    "candidate",
    "candidate_slug",
    "total_electoral_votes",
    "president_electoral_votes",
    "national_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "source",
    "party",
    "candidate_votes",
    "state_total_votes",
    "reliability",
    # --- #139 / D048: appended, never inserted ------------------------------
    # ``pv_status`` is the sibling that keeps a NULL ``candidate_votes`` from being
    # bare: it says *why* there is no popular vote here (D024's three-value enum),
    # distinguishing "this state's legislature appointed the electors" from "no source
    # reaches this far back". Derived in-process from the in-repo absence catalog
    # (:mod:`usvote.pv.absences`) over the EC spine — never from
    # ``dwh.pv_state_status``, so no UCSB-provenanced value is on the public path
    # (D022/D030).
    "pv_status",
    # The counted twin of ``president_electoral_votes`` and its national window sum
    # (D046). ``count_status`` is *why* they differ; its reason is the Archives' own
    # sentence, drawn from a closed vocabulary (D044 §3, D047).
    "president_electoral_votes_counted",
    "national_counted_electoral_votes",
    "count_status",
    "count_status_reason",
)

#: The precomputed national roll-up columns, one row per ``(year, candidate_slug)``.
ROLLUP_COLUMNS: tuple[str, ...] = (
    "year",
    "candidate",
    "candidate_slug",
    "party",
    "national_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "national_pv_votes",
    "national_pv_denominator",
    # --- #139 / D048: appended, never inserted ------------------------------
    # The counted national total (D046) — this is where a reader of 1872 meets
    # "Grant, 300 cast" and needs "286 counted" beside it, and where 1868 Seymour's
    # 80/71 becomes legible. Constant within ``(year, candidate_slug)`` (a window sum),
    # so the roll-up carries it as ``first``.
    "national_counted_electoral_votes",
    # The year's **appointed** allotment — the 12th Amendment's "whole number of
    # Electors appointed" (D041), each state counted once. Without it the counted total
    # is unverifiable: 286 against what? A consumer's only recourse would be to re-sum
    # the fact's ``total_electoral_votes``, which multiplies every state's allotment by
    # the candidate count — the exact bug :func:`usvote.hybrid.ec_denominator_by_year`
    # exists to prevent, so the surface answers it rather than delegating it.
    "national_electoral_denominator",
    # --- #102 / E8-S8: appended, never inserted -----------------------------
    # The five per-candidate hybrid fields. They live here rather than in a sibling
    # ``hybrid_rollup`` table because this table's grain IS the hybrid frame's public
    # grain: ``ROLLUP_COLUMNS`` and ``usvote.hybrid.HYBRID_CANDIDATE_COLUMNS`` already
    # share nine names, and ``national_electoral_denominator`` above is
    # ``ec_denominator`` under another name — so a sibling would duplicate ten columns
    # at the same key and give a consumer two tables to join for one row.
    #
    # **The EC share is split in two, and the split is a safety property** (D037/A).
    # ``ec_share_full`` is policy-invariant and is the only input to the winner and to
    # "was there an EC majority"; ``ec_share_hybrid`` is the policy-selected value that
    # feeds ``hybrid_score`` alone. Under the shipped policy (b) they are equal, which
    # is exactly why shipping both matters: a consumer who sees one column cannot tell
    # that the guarantee exists.
    "ec_share_full",
    "pv_share",
    "ec_share_hybrid",
    # Σ electoral votes over the year's ``popular_vote`` states ÷ the appointed
    # denominator (D024 §8) — EV-weighted, not state-count-weighted. **Derived from the
    # in-repo absence catalog, never from ``dwh.pv_state_status``** (D048's action item
    # for #102), so it is real for all 51 years — 1824 reads 190/261 = 0.728 — where
    # the warehouse view reads NULL before 1976. See ``usvote.snapshot`` for why the
    # two differ on purpose.
    "pv_coverage",
    # ``(ec_share_hybrid + pv_share) / 2`` — the average of two ratios, highest wins
    # (D037). NULL wherever the popular vote is, i.e. every year before the PV window.
    "hybrid_score",
)

#: The per-election hybrid summary's columns, in order (#102 / E8-S8).
#:
#: **An independent explicit projection of**
#: :data:`usvote.hybrid.HYBRID_SUMMARY_COLUMNS` **, not an alias of it** — the same
#: one-way containment :data:`DATA_COLUMNS` keeps against ``usvote.join.EC_PV_COLUMNS``
#: (D047 §3). Aliasing the warehouse tuple would
#: make every future column added to the *view* reach the public payload automatically,
#: which is the property that decoupling exists to deny. A test asserts this tuple is a
#: subset of the warehouse tuple plus the three derived slug columns
#: (``test_snapshot.py::test_the_summary_tuple_is_contained_by_the_warehouse_tuple``);
#: **the reverse assert is forbidden**, for the same reason it is forbidden for
#: ``DATA_COLUMNS``.
#:
#: The three winners arrive from the hybrid summary as candidate **names** (
#: :func:`usvote.hybrid._winner` returns a name), and each ships beside a
#: ``*_slug`` minted by the build so a consumer can pivot straight to
#: ``/v1/candidates/{slug}`` without a name-matching round trip (D006). A NULL winner
#: yields a NULL slug — never an empty string.
HYBRID_SUMMARY_COLUMNS: tuple[str, ...] = (
    "year",
    "ec_denominator",
    "ec_winner",
    "ec_winner_slug",
    "pv_winner",
    "pv_winner_slug",
    "hybrid_winner",
    "hybrid_winner_slug",
    # True only on a **strict** majority of the appointed electors. ``False`` means *no
    # EC majority* — a populated, expected state (the hybrid's motivating case, and the
    # reason 1824 went to the House), never a null-because-broken.
    "ec_determinative",
    "pv_coverage",
    # NULL, never False, where a method has no winner — a method with no popular vote
    # cannot be said to agree *or* disagree with the electoral college.
    "pv_flip",
    "hybrid_flip",
    # Top-2 gaps in **percentage points**, each taken over that method's own non-NULL
    # scores — necessary, not fastidious, because a candidate can hold electoral votes
    # and no popular vote (faithless electors), so the three top-2 sets genuinely differ
    # within one year. Fewer than two scored candidates yields NULL, never ``top1 - 0``.
    "ec_margin",
    "pv_margin",
    "hybrid_margin",
)


@dataclass(frozen=True)
class SnapshotMeta:
    """The provenance row written to ``snapshot_meta`` and returned by the build.

    ``snapshot_version`` is the content hash (D028); ``build_timestamp`` is
    informational only and **excluded** from that hash, so two builds of the same
    warehouse data share a version even though their timestamps differ.

    **Two windows, because since #139 they genuinely differ.** ``year_min`` /
    ``year_max`` are the **served** window — every election the snapshot contains
    (1824–2024); ``pv_year_min`` / ``pv_year_max`` are the **redistributable popular
    vote** sub-window (1976–2024, MIT's span). Saying it once here is the point: a
    consumer learns "the surface is 1824–2024 but PV only reaches 1976" from ``meta``
    rather than inferring it from a field of NULLs. Per-state, the sibling ``pv_status``
    on ``ec_pv`` says *why* a given NULL is NULL.

    **The scoped-subset promise is retired (#139 / D048).** This docstring used to read
    "a warehouse built over a scoped subset of years yields a narrower window". It no
    longer does: the build derives ``pv_status`` from the in-repo absence catalog over
    ``usvote.years.ec_ingest_years()`` and **fails loud** if the warehouse is short a
    year, rather than quietly emitting a snapshot missing an election. Fail-loud is the
    deliberate trade — a silently 50-year snapshot is the same class of error the
    ``pv_status`` column exists to prevent, one level up.

    **Two provenances, because since #139 the surface has two** (D048). ``source`` /
    ``license`` describe the **popular-vote** data (MIT / CC0-1.0) and keep their
    original names for backward compatibility; ``ec_source`` / ``ec_license`` describe
    the **electoral-college** data (the National Archives, a work of the U.S.
    Government). Before the widening the distinction was invisible — every row had MIT
    PV attached — but the snapshot is now majority pre-1976, where the only data is the
    Archives'. Codes only; their public display lives in
    :mod:`usvote.api.provenance` (D016/D028: the snapshot stores the drift-proof code,
    the serving layer annotates it).
    """

    snapshot_version: str
    schema_version: int
    row_count: int
    candidate_count: int
    year_min: int
    year_max: int
    pv_year_min: int
    pv_year_max: int
    source: str
    license: str
    ec_source: str
    ec_license: str
    build_timestamp: str
