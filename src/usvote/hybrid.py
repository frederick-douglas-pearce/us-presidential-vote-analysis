"""The three-method national outcomes — EC / PV / hybrid (E7-S2, #121).

The project's own contribution, computed: for each candidate in an election, take their
**share of the electoral votes** and their **share of the national popular vote**,
average the two ratios, and the highest average wins (**D037**). Alongside it, the two
outcomes it averages — so the thesis question (D001) becomes a number: would this
election have gone differently under the popular vote, or under the hybrid?

A **top-level EC-domain module**, in the ``spine.py``/``years.py``/``join.py``/
``snapshot.py``/``warehouse.py`` family: it names ``dwh.ec_pv_preferred`` and
``dwh.pv_state_status``, so the same greppable invariant that keeps ``join.py`` out of
``usvote/pv/`` keeps this here (D006/D015). Nothing under ``usvote/{mit,ucsb,pv}/`` may
import it, and ``usvote/api/`` must never reach it — it imports pandas, which the D028
serve-time boundary forbids (both enforced by tests).

**Two grains, two builders.** :func:`build_hybrid_frame` is per ``(year, candidate)`` —
the scores; :func:`build_hybrid_summary` is per ``(year)`` — the winners, the D041
``ec_determinative`` flag, the coverage flag, and — as of **#123** — the two flips
(``pv_flip`` / ``hybrid_flip``, each method's winner against the EC baseline) and the
three percentage-point margins. **#124** materialized both as warehouse views.

**The module ships SQL as of #124, and the pandas builders became its tested oracle**
(D050) — the dual-expression pattern of ``join.py`` and ``pv/views.py``:
:func:`build_hybrid_candidate_sql` and :func:`build_hybrid_summary_sql` drive the four
live views, while :func:`build_hybrid_frame` / :func:`build_hybrid_summary` are re-run
against frames read back from them by a differential integration test.

It shipped **no** SQL until then, deliberately (architect ruling, Fred 2026-07-28): #121
performed no DB write, so a builder would have been dead code. That deferral is why the
translation was mechanical when it came, and the two constraints it imposed are still
live and still load-bearing — every step stays relationally expressible (group-by
aggregate, join, rank), and **the tie check is a separate ``assert_*``, never embedded
in a winner column**, because a view cannot ``raise``. The winners are a window rank and
:func:`assert_no_winner_tie` is a view-creation precondition
(:func:`create_hybrid_views`).

**What the guards do and do not cover.** Those preconditions run over the *pandas* side,
so a drift between the two expressions passes every one of them; only the differential
test (``tests/integration/test_hybrid_views.py::
test_the_live_views_match_the_pandas_oracle``) covers that, which is why it is
deliberately not corpus-gated.

**The EC share is split in two, and that split is a safety property** (D037/A). Both
denominators below look parallel and are not:

- ``ec_denominator`` is the **appointed** allotment — each state's
  ``total_electoral_votes`` counted once. It includes a ``legislature_chosen`` state's
  electoral votes, because that state really did appoint electors. Nothing about
  popular-vote coverage trims it.
- ``national_pv_denominator`` is the source's **provided** per-state total (D017), which
  is simply absent for a state that held no popular vote — so those states drop out.

``ec_share_full`` divides by the first and is **policy-invariant**; it is the *only*
input to ``ec_determinative``. ``ec_share_hybrid`` is the policy-selected share that
feeds ``hybrid_score`` and can never reach ``ec_determinative``. That is what stops a
coverage policy from manufacturing a constitutional majority that never existed. The
failure it guards against is the **naive** restriction — trimming 1824's denominator to
the popular-vote states while leaving the numerator alone, which reads Jackson at
99/190 = 0.52, over the line, when the real answer is 99/261 = 0.379 and the House
decided the election. Policy (c) as implemented does *not* make that mistake (it
restricts both halves, giving 84/190 = 0.442 — see :data:`COVERAGE_POLICIES`), but the
split is what makes the mistake **unable to matter** even if some future policy commits
it: ``ec_determinative`` simply does not read that column.

**The majority basis is the appointed allotment** (D041), exactly the 12th Amendment's
"majority of the whole number of Electors **appointed**", while the numerators are votes
actually **counted** (#144, D046). Those are three different quantities and they form a
ladder — **appointed ≥ cast ≥ counted** — with a documented gap at each step:
``ELECTORAL_VOTE_SHORTFALLS`` opens the first (appointed, never cast: the 2000 DC
abstention, 1832 Maryland) and ``count_status`` opens the second (cast, never counted:
1868's disputed nine, 1872's rejected seventeen).

So Σ ``national_counted_electoral_votes`` can be *less* than ``ec_denominator`` and
candidate shares sum to **≤ 1.0, never == 1.0** — correct, not a bug
(:func:`assert_ec_shares_le_one`). 2000 is Bush **271 of 538 appointed**, not 269 of
537 cast; 1872 is Grant **286 of 366 appointed** against the 184 Congress announced,
not 286 of the 352 its own table totals.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Literal

import pandas as pd

from usvote.count_status import COUNTED_VOTES_COLUMN
from usvote.db import DBC
from usvote.join import (
    EC_PV_PREFERRED_VIEW,
    EC_PV_REDISTRIBUTABLE_VIEW,
)
from usvote.join import assert_no_fan_out as assert_join_no_fan_out
from usvote.load import SCHEMA
from usvote.pv.overlap import read_overlap_frames
from usvote.pv.source import MIT_PV_YEAR_MIN, SOURCE_MIT
from usvote.pv.status import (
    PV_STATUS_POPULAR_VOTE,
    ROSTER_SCHEMA,
    ROSTER_TABLE,
)

__all__ = [
    "CARRIED_CANDIDATE_COLUMNS",
    "COVERAGE_POLICIES",
    "COVERAGE_POLICY_MISMATCHED",
    "COVERAGE_POLICY_RESTRICTED",
    "HYBRID_CANDIDATE_COLUMNS",
    "HYBRID_CANDIDATE_GRAIN",
    "HYBRID_PREFERRED_VIEW",
    "HYBRID_REDISTRIBUTABLE_VIEW",
    "HYBRID_SUMMARY_COLUMNS",
    "HYBRID_SUMMARY_GRAIN",
    "HYBRID_SUMMARY_PREFERRED_VIEW",
    "HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW",
    "HYBRID_SURFACES",
    "MARGIN_DIFF_MAX_PP",
    "REQUIRED_JOIN_COLUMNS",
    "CoveragePolicy",
    "HybridError",
    "apply_coverage_policy",
    "assert_carried_columns_constant",
    "assert_db_margin_agreement",
    "assert_ec_shares_le_one",
    "assert_ec_winner_matches_rank",
    "assert_margin_agreement",
    "assert_no_fan_out",
    "assert_no_winner_tie",
    "assert_redistributable_only_source",
    "build_hybrid_candidate_sql",
    "build_hybrid_frame",
    "build_hybrid_from_db",
    "build_hybrid_from_frames",
    "build_hybrid_summary",
    "build_hybrid_summary_sql",
    "create_hybrid_views",
    "ec_denominator_by_year",
    "national_pv_margin_by_year",
    "pv_coverage_by_year",
    "read_ec_pv_join",
    "read_pv_status_roster",
    "roll_up_national",
]

#: The ``Literal`` alias, so mypy rejects a misspelled policy at the call site rather
#: than leaving it to the runtime ``HybridError`` (which stays, for untyped callers).
#: Declared before the constants so each can be annotated with it — a bare ``str``
#: constant would not satisfy the ``Literal``-typed parameters below.
CoveragePolicy = Literal["mismatched", "restricted"]

#: The two honest denominator treatments for a partial-coverage year (D038), and
#: deliberately only two — rule (a), withholding the hybrid entirely, is **rejected**
#: because it would suppress precisely the no-EC-majority elections the hybrid exists to
#: speak to. ``mismatched`` (b) is **settled and shipped**: compute the EC share over
#: all EC-casting states and the PV share over the popular-vote states, and *flag* the
#: mismatch with ``pv_coverage < 1.0``. ``restricted`` (c) narrows **both halves of the
#: EC share** to the popular-vote states so both denominators span one sub-electorate.
#: (c) is reachable only by an explicit argument; neither ``warehouse.py`` nor the SQL
#: builders pass one — the views materialize (b) alone (D050 §2) — which is what makes
#: the public surface's treatment fixed rather than configurable (the property #102
#: relies on).
COVERAGE_POLICY_MISMATCHED: CoveragePolicy = "mismatched"
COVERAGE_POLICY_RESTRICTED: CoveragePolicy = "restricted"
COVERAGE_POLICIES: tuple[CoveragePolicy, ...] = (
    COVERAGE_POLICY_MISMATCHED,
    COVERAGE_POLICY_RESTRICTED,
)

#: The per-candidate frame's grain — one row per election candidate. ``candidate_id``
#: (the warehouse-internal key), never the public ``candidate_slug``: minting that is a
#: snapshot concern (#102), consistent with how ``ec_pv`` is handled today (D006).
HYBRID_CANDIDATE_GRAIN: tuple[str, ...] = ("year", "candidate_id")

#: The per-election summary's grain.
HYBRID_SUMMARY_GRAIN: tuple[str, ...] = ("year",)

#: The per-candidate frame's column contract, in order. Identity first, then the EC half
#: (carried national total → appointed denominator → policy-invariant share), then the
#: PV half (votes → provided denominator → share), then the policy-selected outputs and
#: the hybrid, then the EC-spine context carried through for the downstream stories.
HYBRID_CANDIDATE_COLUMNS: tuple[str, ...] = (
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

#: The per-election summary's column contract, in order: identity, the three winners and
#: the two E7-S2 flags, then #123's flips and margins.
#:
#: **Append, never insert**, and the order is pinned by a hand-written literal in
#: ``TestShape.test_the_summary_column_order_is_pinned_to_a_literal`` — the twin of the
#: ``EC_PV_COLUMNS[:15]`` pin in ``tests/unit/test_join.py``. It has to be a literal:
#: this frame is built with ``columns=list(HYBRID_SUMMARY_COLUMNS)`` below, so any
#: assert comparing the frame against the constant is circular and passes under a
#: reorder or a mid-list insert alike. #124 materialized this tuple as the
#: ``hybrid_summary_preferred`` / ``hybrid_summary_redistributable`` views, so the D047
#: constraint on
#: :data:`usvote.join.EC_PV_COLUMNS` applies here too — ``CREATE OR REPLACE VIEW`` can
#: only add trailing columns, so a mid-list insert breaks a rebuild against an existing
#: warehouse — and with a summary view reading a candidate view, a breaking change now
#: needs an explicit ``DROP ... CASCADE`` migration rather than a ``CREATE OR REPLACE``
#: (D050). The literal pin is what catches the drift before the DDL does.
HYBRID_SUMMARY_COLUMNS: tuple[str, ...] = (
    "year",
    "ec_denominator",
    "ec_winner",
    "pv_winner",
    "hybrid_winner",
    "ec_determinative",
    "pv_coverage",
    "pv_flip",
    "hybrid_flip",
    "ec_margin",
    "pv_margin",
    "hybrid_margin",
)

#: The four materialized hybrid views (#124), two per resolved surface. Named to mirror
#: the join views they wrap (:data:`usvote.join.EC_PV_PREFERRED_VIEW` etc.) with the
#: ``ec_pv_`` prefix dropped, so a hybrid view is never confused with its input.
#: ``hybrid_preferred`` is the analysis surface (full 1824-2024 history when UCSB is
#: loaded); ``hybrid_redistributable`` is the public API surface (#102 / D039) and —
#: because it wraps the *independently defined* ``ec_pv_redistributable`` (D017) — can
#: never carry a UCSB-derived number, which is the structural half of D030.
HYBRID_PREFERRED_VIEW = "hybrid_preferred"
HYBRID_REDISTRIBUTABLE_VIEW = "hybrid_redistributable"

#: The per-election companions. D039 names the seam ``hybrid_redistributable`` "+ its
#: per-election ``hybrid_summary``" without pinning the summary's spelling, and #124's
#: acceptance criteria require **one per surface** — a single ``hybrid_summary`` cannot
#: be both — so the surface is carried in the name (D050).
HYBRID_SUMMARY_PREFERRED_VIEW = "hybrid_summary_preferred"
HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW = "hybrid_summary_redistributable"

#: ``(join view, per-candidate view, per-election view)`` — one entry per surface, so
#: :func:`create_hybrid_views` loops rather than repeating itself and a third surface
#: would be one row here.
#:
#: **Each row's two outputs must carry its own input's surface suffix**, pinned offline
#: by ``TestViewConstants.test_each_output_name_matches_its_own_input_join_view``
#: (#166). Without it, swapping the two output-name *pairs* between rows — each row
#: keeping its input, emitting the other's names — builds ``hybrid_redistributable``
#: over ``ec_pv_preferred``, i.e. over UCSB-provenanced rows, while it keeps the name
#: the public path trusts; the entire offline suite passed under exactly that swap
#: before #166.
#:
#: **That test pins this table and nothing else.** Two further links complete the chain,
#: each pinned by its own test in ``tests/unit/test_hybrid.py``: that
#: :func:`create_hybrid_views` issues each row's SQL under that row's name, by
#: ``TestTheCreatorIssuesEachSurfacesSqlUnderItsOwnName``; and that a builder's SQL
#: reads the join view it was given and never the sibling surface's, by
#: ``TestRedistributableLeakGuardIsStructural``.
HYBRID_SURFACES: tuple[tuple[str, str, str], ...] = (
    (EC_PV_PREFERRED_VIEW, HYBRID_PREFERRED_VIEW, HYBRID_SUMMARY_PREFERRED_VIEW),
    (
        EC_PV_REDISTRIBUTABLE_VIEW,
        HYBRID_REDISTRIBUTABLE_VIEW,
        HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW,
    ),
)

#: Columns that must be **constant within** :data:`HYBRID_CANDIDATE_GRAIN`, checked by
#: :func:`assert_carried_columns_constant` as a view-creation precondition. Each is
#: structurally constant — ``candidate`` is joined on ``candidate_id``, the two national
#: totals are window sums over exactly this partition, and the rank and ``took_office``
#: are broadcast per candidate-year by the transform — so a variation is an assembly
#: bug, not a data property, and must fail loud rather than be quietly tie-broken.
#:
#: **``party`` is deliberately not in this set**, and that is a finding rather than an
#: omission: on the UCSB-bearing preferred surface it genuinely varies, because the two
#: sources *spell the same party differently* (``REPUBLICAN``/``Republican``,
#: ``DEMOCRAT``/``Democratic``) and ``pv_preferred`` keeps a UCSB row wherever MIT has
#: none for that key (D017 resolves the overlap **per key**, not per year). Requiring
#: constancy there would fail every real two-source build over a capitalization
#: difference. It is resolved deterministically instead — see :func:`_resolved_party`.
CARRIED_CANDIDATE_COLUMNS: tuple[str, ...] = (
    "candidate",
    "national_electoral_votes",
    "national_counted_electoral_votes",
    "president_electoral_rank",
    "took_office",
)

#: The columns this module reads off the resolved join view. A strict subset of
#: :data:`usvote.join.EC_PV_COLUMNS` (pinned by a test) — the shape this module *reads*,
#: as distinct from :data:`HYBRID_CANDIDATE_COLUMNS`, the shape it produces.
REQUIRED_JOIN_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "candidate_id",
    "candidate",
    "party",
    "total_electoral_votes",
    "president_electoral_votes",
    "national_electoral_votes",
    "national_counted_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "candidate_votes",
    "state_total_votes",
    # Per-row, and distinct from the national sum above: policy (c) re-sums the counted
    # measure over a restricted state set, which the national total cannot give it.
    COUNTED_VOTES_COLUMN,
)

#: What :func:`roll_up_national` derives itself; a ``carry`` entry may not shadow one.
_DERIVED_ROLLUP_COLUMNS: frozenset[str] = frozenset(
    {"national_pv_votes", "national_pv_denominator"}
)


class HybridError(RuntimeError):
    """Raised when the hybrid computation's inputs or outputs violate a #121 invariant.

    The ``join.py``/``pv.status`` analogue: a malformed roster (cross-source status
    disagreement), a state whose electoral allotment varies by candidate row (which
    would make the deduped denominator ambiguous), EC shares summing past 1.0 (a
    denominator bug), a genuine winner tie, or a winner disagreeing with the EC spine's
    own rank.
    """


# --- the shared national-aggregation primitive ------------------------------


def roll_up_national(
    df: pd.DataFrame,
    *,
    key: Sequence[str],
    carry: Mapping[str, str],
) -> pd.DataFrame:
    """Roll state-grain join-view rows up to national per-``key`` totals.

    **The single-sourced national-aggregation primitive** (D037/F, OQ4-resolved):
    :func:`usvote.snapshot.build_national_rollup` calls this rather than keeping a
    second hand-written copy, because two copies of the two subtleties below will drift.

    ``key`` is the group key and must contain ``year`` (the PV denominator is per-year).
    The hybrid frame passes ``("year", "candidate_id")``; the snapshot passes
    ``("year", "candidate_slug")`` — it drops the internal id for the public slug
    (D006). ``carry`` maps output column → source column, each taken as ``first``
    (constant within the group). The denominator half takes **no** key: it always groups
    ``(year, state) → year``, whatever the candidate key is.

    Two subtleties, both load-bearing, both preserved verbatim:

    - **``min_count=1`` twice.** On the per-candidate PV sum, so a getter with **no** PV
      stays NULL rather than becoming a fabricated ``0`` (D005/D026 §2); and on the
      per-year denominator sum, so an **all-NULL-PV year** keeps a NULL denominator
      instead of ``0`` — which would otherwise divide by zero on every pre-1976 year of
      the MIT-only redistributable surface.
    - **Per-``(year, state)`` ``max`` before the year sum.** The source broadcasts one
      per-state denominator onto every candidate row in the state, but a no-PV getter (a
      faithless elector) carries a NULL ``state_total_votes``. ``max`` skips NA and
      keeps the state; a plain ``drop_duplicates(["year", "state"])`` keeps the *first*
      row in sort order, which is that NULL row whenever the getter sorts first —
      silently dropping the whole state from the national denominator.
    """
    keys = list(key)
    if "year" not in keys:
        raise HybridError(
            "roll_up_national key must contain 'year' (the popular-vote "
            f"denominator is per-year); got {keys}"
        )
    shadowed = sorted(set(carry) & _DERIVED_ROLLUP_COLUMNS)
    if shadowed:
        raise HybridError(
            f"carry may not shadow the columns roll_up_national derives: {shadowed}"
        )

    per_candidate = df.groupby(keys, as_index=False).agg(
        **{out: (src, "first") for out, src in carry.items()},
        national_pv_votes=("candidate_votes", lambda s: s.sum(min_count=1)),
    )
    per_state = df.groupby(["year", "state"], as_index=False)["state_total_votes"].max()
    denominator = (
        per_state.groupby("year", as_index=False)["state_total_votes"]
        .sum(min_count=1)
        .rename(columns={"state_total_votes": "national_pv_denominator"})
    )
    return per_candidate.merge(denominator, on="year", how="left")


# --- D051 gate 3: the cross-source margin-agreement check (#167) -------------
#
# D017 layer 3's third threshold. Gates 1 and 2 run at the cell grain over the PV union
# and live in `usvote.pv.overlap`; this one is the **E7 trustworthiness check** and
# lives here, beside the computation it protects (D051). That placement is forced rather
# than preferred: the derivation below calls `roll_up_national`, and a home under
# `usvote/pv/` would need a `pv -> hybrid` import, which `test_layering.py` forbids.

#: Gate 3: the largest tolerated difference, in **percentage points**, between the
#: national popular-vote margin computed from MIT and the same margin computed from
#: UCSB, in any overlap year. D051 / `.claude/specs/research-pv-overlap.md` §6
#: threshold 3; observed maximum **0.0337 pp**.
#:
#: **Percentage points, not a ratio** — that is the unit the claim is made in. 0.25 pp
#: sits about 2x below the smallest actual margin in the measured window (0.5113 pp), so
#: within that range a passing gate leaves no margin close enough to flip. It is **not a
#: guarantee on unseen data**: a future election decided by 0.2 pp would pass this gate
#: and could still be source-sensitive.
MARGIN_DIFF_MAX_PP = 0.25


def national_pv_margin_by_year(pv_df: pd.DataFrame) -> pd.DataFrame:
    """Per-year national popular-vote margin, in percentage points, for one source.

    Takes a :data:`usvote.pv.schema.SHARED_PV_COLUMNS`-shaped single-source frame (a
    read of ``pv_redistributable`` or ``pv_ucsb``) and returns ``year``/``pv_margin``.

    **The denominator is the source's own PROVIDED state totals**, never a re-sum of
    candidate rows, and that is a D017 rule rather than a preference — which is why this
    calls :func:`roll_up_national` instead of summing here. D007 scopes candidates to
    the EC-getters, so a re-sum differs *systematically* between two sources that cover
    minor candidates differently. #70 hit it in practice: an early draft re-summed and
    read 1992's margin as 6.96 pp against the universally published ~5.6 pp, failing a
    reader's first sanity check. On the provided denominator the maximum cross-source
    delta moved 0.0498 -> 0.0337 pp — the verdict came back *stronger* (D051).

    The top-2 gap itself is :func:`_margin`, shared with the summary frame's three
    margins, so "percentage points, over that method's own non-NULL scores, ``None``
    under fewer than two candidates" has one definition rather than two.
    """
    rolled = roll_up_national(pv_df, key=("year", "candidate"), carry={})
    rolled["share"] = rolled["national_pv_votes"] / rolled["national_pv_denominator"]
    margins = [
        {"year": int(year), "pv_margin": _margin(group["share"])}
        for year, group in rolled.groupby("year", sort=True)
    ]
    return pd.DataFrame(margins, columns=["year", "pv_margin"])


def assert_margin_agreement(
    mit_df: pd.DataFrame,
    ucsb_df: pd.DataFrame,
    *,
    error_cls: type[Exception] = HybridError,
) -> pd.DataFrame:
    """Raise when any overlap year's two national margins differ by > the D051 ceiling.

    Returns the per-year comparison frame (``year``, ``mit_margin``, ``ucsb_margin``,
    ``diff_pp``) so a caller can report it; raises :class:`HybridError` on a breach.

    Both frames are re-filtered to the overlap window here as well as at the read, so
    the oracle is correct when called directly from a test — the same self-defense
    :func:`usvote.pv.overlap.compute_overlap_report` applies, and for the same reason.

    **Years either source cannot score are skipped, not failed.**
    :func:`national_pv_margin_by_year` returns ``None`` for a year with fewer than two
    scored candidates, and a missing margin is a coverage gap — comparing it against
    anything would invent a difference out of an absence (the same reasoning that makes
    :func:`_flip` NULL rather than ``True`` on an all-NULL year).
    """
    mit_df = mit_df.loc[mit_df["year"] >= MIT_PV_YEAR_MIN]
    ucsb_df = ucsb_df.loc[ucsb_df["year"] >= MIT_PV_YEAR_MIN]
    merged = national_pv_margin_by_year(mit_df).merge(
        national_pv_margin_by_year(ucsb_df),
        on="year",
        how="inner",
        suffixes=("_mit", "_ucsb"),
    )
    comparable = merged.loc[
        merged["pv_margin_mit"].notna() & merged["pv_margin_ucsb"].notna()
    ].copy()
    comparable["diff_pp"] = (
        comparable["pv_margin_mit"] - comparable["pv_margin_ucsb"]
    ).abs()
    breaches = comparable.loc[comparable["diff_pp"] > MARGIN_DIFF_MAX_PP]
    if not breaches.empty:
        offenders = [
            f"{int(row.year)}: {row.diff_pp:.4f} pp"
            for row in breaches.itertuples(index=False)
        ]
        raise error_cls(
            "the national popular-vote margin is source-sensitive beyond the D051 "
            f"gate-3 ceiling of {MARGIN_DIFF_MAX_PP} pp "
            "(see .claude/specs/research-pv-overlap.md §6): " + "; ".join(offenders)
        )
    return comparable.rename(
        columns={"pv_margin_mit": "mit_margin", "pv_margin_ucsb": "ucsb_margin"}
    ).reset_index(drop=True)


def assert_db_margin_agreement(
    dbc: DBC, *, schema: str = ROSTER_SCHEMA
) -> pd.DataFrame | None:
    """Live-DB form of gate 3; ``None`` when UCSB is absent (AC-3), raising nothing.

    Reads through :func:`usvote.pv.overlap.read_overlap_frames`, which is the single
    expression of the two-view read, the overlap-window filter and the UCSB skip probe —
    all three AC-pinned — so this gate and the cell-grain gates beside it cannot drift
    apart on any of them. ``schema`` is forwarded for the same reason its cell-grain
    twin :func:`usvote.pv.overlap.assert_db_overlap_within_tolerance` takes one: a
    non-default-schema caller must not silently validate a different warehouse.
    """
    frames = read_overlap_frames(dbc, schema=schema)
    if frames is None:
        return None
    return assert_margin_agreement(*frames)


# --- the appointed electoral allotment --------------------------------------


def ec_denominator_by_year(ec_pv_df: pd.DataFrame) -> pd.DataFrame:
    """Per-year Σ ``total_electoral_votes``, each state counted **once**.

    The **appointed** allotment (D041). Deduped over ``(year, state)`` — a bare
    aggregate over the joined rows would multiply every state's allotment by the
    candidate count, since the join view is at ``(year, state, candidate)`` grain.
    Includes a ``legislature_chosen`` state's electoral votes: that state really did
    appoint electors, so no popular-vote coverage question trims this denominator
    (contrast ``national_pv_denominator``, which those states simply do not contribute
    to).

    ``total_electoral_votes`` is a per-state allotment broadcast onto each candidate
    row, so it must be constant within ``(year, state)``. If it ever is not, the deduped
    denominator becomes ambiguous — so this raises rather than silently picking a value.
    """
    per_state = ec_pv_df.groupby(["year", "state"], as_index=False)[
        "total_electoral_votes"
    ].agg(["nunique", "max"])
    inconsistent = per_state.loc[per_state["nunique"] != 1]
    if not inconsistent.empty:
        offenders = inconsistent[["year", "state"]].values.tolist()
        raise HybridError(
            "total_electoral_votes is not constant within (year, state) — the deduped "
            f"appointed denominator would be ambiguous: {offenders}"
        )
    return (
        per_state.groupby("year", as_index=False)["max"]
        .sum()
        .rename(columns={"max": "ec_denominator"})
    )


# --- the roster read + the coverage derivation ------------------------------


def _resolve_roster(roster_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the ``(source, year, state)`` roster to one status per state-year.

    ``dwh.pv_state_status`` is keyed on ``(source, year, state)`` (D024 §3), so the
    1976-2024 overlap carries a MIT row *and* a UCSB row for every state. Where the
    sources agree — the normal case, since every state in those years held a popular
    vote — the roster collapses cleanly; double-counting instead would inflate the
    coverage numerator by a state's electoral votes. A genuine disagreement is a data
    bug, not something to break arbitrarily, so it raises.
    """
    if roster_df.empty:
        # Reached when a caller passes an empty roster, or when the roster read is
        # scoped to a source with no rows (read_pv_status_roster's `sources`). NOT the
        # EC-only-warehouse case: dwh.pv_state_status is created only by a PV source
        # load (usvote/pv/load.py), so on an EC-only build the relation does not exist
        # and the read raises UndefinedTable long before this. Coverage stays unknown.
        return pd.DataFrame({"year": [], "state": [], "pv_status": []})
    statuses = roster_df.groupby(["year", "state"], as_index=False)["pv_status"].agg(
        ["nunique", "first"]
    )
    conflicting = statuses.loc[statuses["nunique"] != 1]
    if not conflicting.empty:
        offenders = conflicting[["year", "state"]].values.tolist()
        raise HybridError(
            "PV sources disagree on pv_status for these (year, state) — resolve the "
            f"roster before deriving coverage: {offenders}"
        )
    return statuses.rename(columns={"first": "pv_status"})[
        ["year", "state", "pv_status"]
    ]


def pv_coverage_by_year(
    ec_pv_df: pd.DataFrame, roster_df: pd.DataFrame
) -> pd.DataFrame:
    """Per-year **electoral-vote-weighted** popular-vote coverage (D024 §8).

    Numerator: Σ ``total_electoral_votes`` over the year's ``popular_vote`` states.
    Denominator: the full :func:`ec_denominator_by_year` (every EC-casting state). So a
    year where every state voted is exactly ``1.0``, and 1824 — six legislature-chosen
    states holding 71 of 261 electoral votes — is 190/261 = 0.728. EV-weighted, **not**
    state-count-weighted: by state count 1824 would read 18/24 = 0.75, close enough to
    pass a loose check while being the wrong quantity.

    **The roster drives this, and a NULL ``candidate_votes`` never may.** Inferring
    coverage from a missing PV cell conflates a ``legislature_chosen`` state (where no
    popular vote was ever held) with a state the source simply does not cover — exactly
    the distinction D024's no-``unknown`` design exists to preserve. So the two cases
    have an identical *data* shape and only the roster tells them apart.

    A year the roster says nothing about gets **NULL** coverage, not ``0.0``: unknown is
    not "no state voted" (D005). That is the honest answer for a warehouse whose roster
    does not reach that year.

    Returns ``covered_electoral_votes`` alongside the ratio, because it is exactly
    policy (c)'s restricted EC denominator (#122). Carrying it out rather than
    recomputing it there keeps **one** derivation of "the electoral weight of the
    popular-vote states" — two would drift, and the drift would be invisible: both would
    still produce plausible ratios. Note the two are on different footings — it is NULL
    for a roster-absent year (unknown) and a real ``0`` for a year the roster reaches
    with no popular-vote state (known, and known to be none), a distinction (c)'s divide
    has to respect.
    """
    denominators = ec_denominator_by_year(ec_pv_df)
    resolved = _resolve_roster(roster_df)
    allotments = ec_pv_df.groupby(["year", "state"], as_index=False)[
        "total_electoral_votes"
    ].max()
    covered = allotments.merge(resolved, on=["year", "state"], how="inner")
    numerator = (
        covered.loc[covered["pv_status"] == PV_STATUS_POPULAR_VOTE]
        .groupby("year", as_index=False)["total_electoral_votes"]
        .sum()
        .rename(columns={"total_electoral_votes": "covered_electoral_votes"})
    )

    out = denominators.merge(numerator, on="year", how="left")
    # A year the roster reaches but with no popular-vote state is a real 0.0; a year the
    # roster does not reach at all stays NULL. The distinction is the whole point.
    roster_years = set(resolved["year"])
    in_roster = out["year"].isin(roster_years)
    out["covered_electoral_votes"] = out["covered_electoral_votes"].where(
        ~in_roster | out["covered_electoral_votes"].notna(), 0
    )
    out["pv_coverage"] = out["covered_electoral_votes"] / out["ec_denominator"]
    out.loc[~in_roster, "pv_coverage"] = pd.NA
    return out[["year", "ec_denominator", "covered_electoral_votes", "pv_coverage"]]


# --- the coverage policy (D038: (b) is settled) -----------------------------


def _restricted_ec_numerator(
    ec_pv_df: pd.DataFrame, roster_df: pd.DataFrame, key: Sequence[str]
) -> pd.DataFrame:
    """Per-``key`` Σ counted electoral votes, ``popular_vote`` states only.

    Policy (c)'s EC numerator, and it must be **recomputed from the state rows** — the
    carried ``national_electoral_votes`` is a window SUM over *every* state, so pairing
    it with the restricted denominator would silently mix a full numerator with a
    partial one. On 1824 that mistake reads Jackson at 99/190 = 0.52 rather than
    84/190 = 0.442 — a fabricated majority, exactly the failure mode the D037/A split
    makes harmless (``ec_determinative`` never reads this column) and that this function
    must not commit anyway.

    No dedup, unlike :func:`ec_denominator_by_year`: the measure is genuinely per
    ``(state, candidate)``, not a per-state allotment broadcast across candidate rows,
    so a straight sum over the restricted state set is correct.

    Sums the **counted** measure, matching ``ec_share_full`` (#144, D046). A policy
    chooses which *states* count toward the share, never which *basis* — pairing a cast
    numerator with a counted one would make (c) and (b) disagree in 1872 for a reason
    that has nothing to do with coverage. (Immaterial numerically today: both anomaly
    years have full popular-vote coverage, so (c) restricts nothing there.)
    """
    resolved = _resolve_roster(roster_df)
    pv_states = resolved.loc[
        resolved["pv_status"] == PV_STATUS_POPULAR_VOTE, ["year", "state"]
    ]
    restricted = ec_pv_df.merge(pv_states, on=["year", "state"], how="inner")
    return (
        restricted.groupby(list(key), as_index=False)[COUNTED_VOTES_COLUMN]
        .sum()
        .rename(columns={COUNTED_VOTES_COLUMN: "restricted_electoral_votes"})
    )


def apply_coverage_policy(
    national: pd.DataFrame,
    ec_pv_df: pd.DataFrame,
    roster_df: pd.DataFrame,
    *,
    policy: CoveragePolicy = COVERAGE_POLICY_MISMATCHED,
    key: Sequence[str] = HYBRID_CANDIDATE_GRAIN,
) -> pd.DataFrame:
    """Own both hybrid numerators and both hybrid denominators — (b) or (c).

    The hybrid averages an EC share against a PV share, and for a partial-coverage year
    those shares are computed over differently-sized electorates. Rule (a) — withhold
    the hybrid for such years — is **rejected** (D038): it would suppress precisely the
    no-EC-majority, House-contingent elections the hybrid exists to speak to. Of the two
    honest treatments, **(b) is settled and shipped** (D038, Fred 2026-07-28); (c)
    exists so the rejected alternative is *executable* rather than merely asserted —
    #125's methodology note can state what it would have produced.

    - **(b) ``mismatched``, the default:** ``ec_share_hybrid == ec_share_full`` — the EC
      share is not restricted — and the mismatch is *flagged* by ``pv_coverage < 1.0``.
    - **(c) ``restricted``:** both halves of the EC share narrow to the ``popular_vote``
      states — numerator via :func:`_restricted_ec_numerator`, denominator the
      ``covered_electoral_votes`` that :func:`pv_coverage_by_year` already computed as
      its own numerator. ``pv_share`` is **untouched**: its denominator is the source's
      provided per-state totals, which a no-popular-vote state never contributed to, so
      it is already restricted. (c) therefore moves the EC half alone.

    Both branches keep every step relationally expressible (group-by aggregate, join),
    which is what kept #124's translation to SQL mechanical.

    ``key`` is the grain ``national`` is on, and exists for the same reason
    :func:`roll_up_national` takes one: (c)'s numerator must be grouped by *whatever*
    candidate key the caller rolled up on, so a future slug-grained caller (D006) is a
    parameter rather than a fork. (b) never touches it.

    **The empty restricted set yields NULL, never a divide-by-zero — and it needs no
    zero-denominator guard to do so.** Two paths reach it, and they differ in what
    ``pv_coverage`` reports, not in how the share becomes NULL: a year the roster does
    not cover has a NULL ``covered_electoral_votes`` (coverage *unknown*), while a year
    the roster *does* cover with no ``popular_vote`` state has a real ``0`` (coverage
    known, and known to be none). Either way :func:`_restricted_ec_numerator` finds no
    rows, so the merged numerator is NULL and the division propagates NULL on its own.
    An earlier draft replaced a ``0`` denominator with NULL defensively; it was
    **unreachable** — a non-NULL numerator over a zero denominator would require
    ``popular_vote`` states whose allotments sum to zero, which the join view cannot
    produce — and a guard no mutation can kill is dead code, so it is gone (AC-verify,
    #122). On the MIT-only redistributable surface that first path is now exactly the
    **pre-1976** years: since #127 the roster carries MIT's own rows for 1976-2024, so
    (c) is a no-op there (every state is ``popular_vote``, so restricting changes
    nothing) and returns NULL only for the years MIT does not reach. Before the
    backfill the roster held no MIT rows at all and (c) returned NULL throughout.

    ``ec_share_full`` and ``ec_determinative`` are deliberately **outside this
    function's reach** (D037/A) — policy-invariant, computed in
    :func:`build_hybrid_frame` before this is called and read by
    :func:`build_hybrid_summary` — so no coverage policy can move them. That is what
    makes (c) safe to ship at all.
    """
    if policy not in COVERAGE_POLICIES:
        raise HybridError(
            f"{policy!r} is not a known coverage policy (expected one of "
            f"{COVERAGE_POLICIES}); (b) {COVERAGE_POLICY_MISMATCHED!r} is the shipped "
            "rule (D038) and (c) is reachable only by an explicit argument."
        )
    coverage = pv_coverage_by_year(ec_pv_df, roster_df)
    out = national.merge(
        coverage[["year", "covered_electoral_votes", "pv_coverage"]],
        on="year",
        how="left",
    )
    if policy == COVERAGE_POLICY_MISMATCHED:
        out["ec_share_hybrid"] = out["ec_share_full"]
    else:
        out = out.merge(
            _restricted_ec_numerator(ec_pv_df, roster_df, key), on=list(key), how="left"
        )
        # No zero-denominator guard: an empty restricted set leaves the numerator NULL,
        # which is what carries the NULL through (see the docstring). Float64 (nullable)
        # so the NULL survives the division rather than becoming a NaN sentinel.
        denominator = out["covered_electoral_votes"].astype("Float64")
        numerator = out.get(
            "restricted_electoral_votes", pd.Series(pd.NA, index=out.index)
        ).astype("Float64")
        out["ec_share_hybrid"] = (numerator / denominator).astype("float64")
        out = out.drop(columns=["restricted_electoral_votes"], errors="ignore")
    out["pv_share"] = out["national_pv_votes"] / out["national_pv_denominator"]
    return out.drop(columns=["covered_electoral_votes"])


# --- the two builders -------------------------------------------------------


def _resolved_party(ec_pv_df: pd.DataFrame) -> pd.DataFrame:
    """Per-``(year, candidate_id)`` party, resolved deterministically by ``min``.

    **Not carried through** :func:`roll_up_national`, whose ``first`` would be
    order-dependent here, and **not** required constant by
    :func:`assert_carried_columns_constant`, because on the UCSB-bearing preferred
    surface it genuinely is not: MIT writes ``REPUBLICAN``/``DEMOCRAT`` (its
    ``party_simplified``) while UCSB writes ``Republican``/``Democratic``, and
    ``pv_preferred`` keeps a UCSB row wherever MIT has none for that key — D017
    resolves the 1976-2024 overlap **per key**, not per year, so a getter MIT's D019
    filter drops in one state keeps its UCSB spelling there.

    So the two values are one party under two spellings, and any pick is arbitrary. What
    matters is that the pick is **the same on both sides of the seam**: ``min`` is
    stable, needs no ordering a view cannot express, and skips nulls (returning null
    for an all-null group) in pandas and SQL alike, so a getter with no popular vote
    anywhere keeps a NULL party rather than a fabricated one.

    **The two are only the same pick under a byte-ordered collation, and the SQL says so
    explicitly.** Python's ``min`` compares codepoints; Postgres ``min(text)`` compares
    under the database collation, and on the usual ``en_US.UTF-8`` it returns
    ``'Republican'`` where this function returns ``'REPUBLICAN'`` — a silent
    disagreement on precisely the mixed-spelling case this resolution exists for. So
    :func:`build_hybrid_candidate_sql` emits ``min(party COLLATE "C")``. Found at code
    review, after both this docstring and D050 had asserted the two were identical.

    Deliberately *not* "the party of the plurality of votes", which reads better and is
    a different quantity: it would make a candidate's displayed party depend on vote
    counts, so a recount could change it — a worse failure than an arbitrary-but-stable
    label.
    """
    grain = list(HYBRID_CANDIDATE_GRAIN)
    return ec_pv_df.groupby(grain, as_index=False)["party"].min()


def build_hybrid_frame(
    ec_pv_df: pd.DataFrame,
    roster_df: pd.DataFrame,
    *,
    policy: CoveragePolicy = COVERAGE_POLICY_MISMATCHED,
) -> pd.DataFrame:
    """Per-``(year, candidate)`` EC / PV / hybrid scores over a resolved join view.

    ``ec_pv_df`` is ``ec_pv_preferred``-shaped (analysis, full history) or
    ``ec_pv_redistributable``-shaped (the MIT-only public surface) — the same builder
    over either, which is what makes #102's surface a parameter rather than a fork.
    ``roster_df`` is ``dwh.pv_state_status``-shaped and is **load-bearing**: which
    states are ``legislature_chosen`` lives only there (``EC_PV_COLUMNS`` carries
    ``total_electoral_votes`` but not ``pv_status``), so ``pv_coverage`` cannot be
    derived without it and must never be inferred from a NULL ``candidate_votes``.

    The EC-getter scope is inherited for free — the join view holds only getters, and
    ``pv_preferred`` is already D007/D019/D025-scoped — so no candidate filtering
    happens here. Shares stay **exact ratios**: no rounding before comparison, since
    rounding is a presentation concern (D001) and the ``> 0.5`` majority test is on the
    exact value.

    A candidate with no popular vote anywhere keeps a NULL ``pv_share`` and hence a NULL
    ``hybrid_score`` — honest per D005, never a fabricated 0 — and simply does not
    compete for the PV or hybrid winner. On an EC+MIT-only warehouse (UCSB is optional)
    that is every pre-1976 candidate: ``hybrid_preferred`` becomes a 1976-only surface
    and does
    **not** assert UCSB presence (settled, Fred 2026-07-28).

    ``policy`` selects the D038 denominator treatment and defaults to the shipped (b);
    see :func:`apply_coverage_policy`. It is threaded here so a caller can build a
    *whole frame* either way — the comparison #125's methodology note needs — rather
    than only the policy function's output in isolation.
    """
    national = roll_up_national(
        ec_pv_df,
        key=HYBRID_CANDIDATE_GRAIN,
        carry={
            "candidate": "candidate",
            "national_electoral_votes": "national_electoral_votes",
            "national_counted_electoral_votes": "national_counted_electoral_votes",
            "president_electoral_rank": "president_electoral_rank",
            "took_office": "took_office",
        },
    )
    # party is resolved, not carried -- roll_up_national's ``first`` is order-dependent
    # and the two sources spell one party two ways. See _resolved_party.
    national = national.merge(
        _resolved_party(ec_pv_df), on=list(HYBRID_CANDIDATE_GRAIN), how="left"
    )
    national = national.merge(ec_denominator_by_year(ec_pv_df), on="year", how="left")
    # Counted, not cast (#144, D046): who won is settled by the votes Congress counted,
    # so the share that feeds ec_determinative divides the counted total by the
    # appointed allotment — exactly the 12th Amendment's test. Identical to the cast
    # basis in every year but 1868 and 1872.
    national["ec_share_full"] = (
        national["national_counted_electoral_votes"] / national["ec_denominator"]
    )
    frame = apply_coverage_policy(
        national, ec_pv_df, roster_df, policy=policy, key=HYBRID_CANDIDATE_GRAIN
    )
    # D037: the average of the two ratios. NULL-propagating by construction, so a
    # candidate with no popular vote scores NULL rather than half an EC share.
    frame["hybrid_score"] = (frame["ec_share_hybrid"] + frame["pv_share"]) / 2
    return (
        frame[list(HYBRID_CANDIDATE_COLUMNS)]
        .sort_values(list(HYBRID_CANDIDATE_GRAIN), kind="stable")
        .reset_index(drop=True)
    )


def _winner(scores: pd.Series, names: pd.Series) -> str | None:
    """The name maximizing ``scores`` over **non-NULL** entries; ``None`` if all NULL.

    Deliberately does **not** raise on a tie — :func:`assert_no_winner_tie` owns that,
    kept separate so #124 could translate this to a SQL window rank (a view cannot
    ``raise``) and make the tie check a view-creation precondition.
    """
    ranked = scores.dropna()
    if ranked.empty:
        return None
    return str(names.loc[ranked.idxmax()])


def _flip(method_winner: str | None, ec_winner: str | None) -> object:
    """``True`` when a method names a different winner than the EC baseline; else NULL.

    **Guarded explicitly rather than written as ``method_winner != ec_winner``**, and
    the difference is not stylistic. :func:`_winner` returns a Python ``None`` for an
    all-NULL year, not ``pd.NA``, so ``!=`` does **not** propagate to NULL the way it
    would over a pandas column — ``None != "Trump"`` is plain ``True``. A bare ``!=``
    would therefore report a *flip* for every year carrying no popular vote at all:
    worse than the ``false`` #123 forbids, because it invents a headline result out of
    a coverage gap.

    A NULL ``ec_winner`` is likewise NULL, not ``True`` — a flip is defined against the
    EC baseline, and with no baseline there is nothing to differ from. That branch is
    **defensive and unreachable on real data**: the EC fact is dense (``parse.py`` reads
    the Archives' ``-`` as ``0``, so a loser is an explicit 0-EV row) and the appointed
    denominator is positive, so every in-scope year resolves an EC winner.
    """
    if method_winner is None or ec_winner is None:
        return pd.NA
    return method_winner != ec_winner


def _margin(scores: pd.Series) -> float | None:
    """The top-2 gap in ``scores``, in percentage points; ``None`` under fewer than two.

    Percentage points only (D037) — the scores are already ratios, so the gap is scaled
    by 100 exactly once. 2000's electoral margin reads ``0.93``, never ``0.0093``.

    **Computed over that method's own non-NULL entries**, which is why each margin takes
    its own series rather than sharing one filtered frame: the three methods' top-2 sets
    genuinely differ within a single year. 2016 is the live case — five of its seven
    rows are faithless-elector and "Other" candidates carrying electoral votes but no
    popular vote, so the EC gap is taken over seven candidates and the popular-vote gap
    over two.

    **Fewer than two scored candidates yields ``None``**, covering both the all-NULL
    year (a warehouse built without UCSB has no pre-1976 popular vote) and the
    lone-candidate year. A "top-2 gap" is undefined with one entry, and falling back
    to ``top1 - 0`` would report a *share* under a column named margin — a wrong number
    rather than an absent one.
    """
    ranked = scores.dropna().sort_values(ascending=False)
    if len(ranked) < 2:
        return None
    return float((ranked.iloc[0] - ranked.iloc[1]) * 100.0)


def build_hybrid_summary(hybrid_frame: pd.DataFrame) -> pd.DataFrame:
    """Per-election winners, the D041 ``ec_determinative`` flag, and the coverage flag.

    Each winner is the candidate maximizing that method's score **over non-NULL
    scores**; an all-NULL year (no popular vote loaded) resolves to a **NULL winner,
    gracefully** — that is a coverage gap, not a failure, and the tie guard's carve-out
    exists so it is never mistaken for a dead heat.

    ``ec_determinative`` is ``true`` only when the EC winner holds a **strict** majority
    of the appointed allotment (``ec_share_full > 0.5``). ``false`` means **no EC
    majority** — a populated, expected state and the hybrid's whole motivating case
    (Fred's intent: let the people decide when the EC is very close, instead of the
    House deciding), never a null-because-broken. The EC winner column stays populated
    there: it is the plurality / rank-1 leader, exactly as 1824's Jackson was.
    ``ec_determinative`` and ``pv_coverage`` are **orthogonal** — 1824 is both "EC not
    determinative" and "partial PV coverage", two separate true facts.

    **The flips** (#123) answer the thesis question (D001) per election: did this method
    name a different winner than the Electoral College? The EC baseline is the rank-1
    electoral-vote leader — ``argmax(ec_share_full)``, which
    :func:`assert_ec_winner_matches_rank` cross-checks against the spine's
    ``president_electoral_rank == 1`` — and deliberately **not** ``took_office``, which
    diverges in a contingent election (1824's rank-1 was Jackson; the House installed
    Adams). A flip whose method has no winner is NULL, never ``false`` — see
    :func:`_flip` for why that needs an explicit guard.

    **The three margins** are each method's top-2 gap in percentage points, over that
    method's own non-NULL scores (:func:`_margin`). ``ec_margin`` reads
    ``ec_share_full``, not the policy-selected ``ec_share_hybrid``, so it stays
    coherent with the
    ``ec_winner`` and ``ec_determinative`` computed from the same column: under coverage
    policy (c) the hybrid share can re-rank candidates, which would leave a reported EC
    margin describing a different ordering than the reported EC winner. On the shipped
    default (b) the two columns are numerically identical, so this only bites under (c).
    ``hybrid_margin`` reads ``hybrid_score`` and therefore tracks the D037 formula
    automatically; the asymmetry between the two is deliberate, because they measure
    different things.

    Note it reads ``ec_share_full``, never ``ec_share_hybrid`` (D037/A). The SQL twin is
    :func:`build_hybrid_summary_sql`.
    """
    rows: list[dict[str, object]] = []
    for year, group in hybrid_frame.groupby("year", sort=True):
        ec_winner = _winner(group["ec_share_full"], group["candidate"])
        pv_winner = _winner(group["pv_share"], group["candidate"])
        hybrid_winner = _winner(group["hybrid_score"], group["candidate"])
        determinative: object = pd.NA
        if ec_winner is not None:
            leader = group.loc[group["candidate"] == ec_winner, "ec_share_full"].iloc[0]
            determinative = bool(leader > 0.5)
        rows.append({
            "year": year,
            "ec_denominator": group["ec_denominator"].iloc[0],
            "ec_winner": ec_winner,
            "pv_winner": pv_winner,
            "hybrid_winner": hybrid_winner,
            "ec_determinative": determinative,
            "pv_coverage": group["pv_coverage"].iloc[0],
            "pv_flip": _flip(pv_winner, ec_winner),
            "hybrid_flip": _flip(hybrid_winner, ec_winner),
            "ec_margin": _margin(group["ec_share_full"]),
            "pv_margin": _margin(group["pv_share"]),
            "hybrid_margin": _margin(group["hybrid_score"]),
        })
    # ``columns=`` follows the constant rather than validating against it (unlike
    # ``build_hybrid_frame``'s ``frame[list(...)]``, which raises on a declared-but-
    # unproduced column). The order is backstopped by the literal-tuple assert named
    # on HYBRID_SUMMARY_COLUMNS above, which no builder spelling could provide.
    return pd.DataFrame(rows, columns=list(HYBRID_SUMMARY_COLUMNS))


# --- guards (run as automated tests) ----------------------------------------


def assert_ec_shares_le_one(
    hybrid_frame: pd.DataFrame,
    *,
    tolerance: float = 1e-9,
    error_cls: type[Exception] = HybridError,
) -> None:
    """Assert per-year Σ ``ec_share_full`` ≤ 1.0 — **never** that it equals 1.0 (D041).

    The denominator is the **appointed** allotment; the numerators are votes **counted**
    (#144). Both gaps in the appointed ≥ cast ≥ counted ladder make the sum strictly
    less than 1.0 — 2000 is 537 of 538 cast, 1872 is 349 of 366 counted — so an
    ``== 1.0`` assertion would fail on correct data. Exceeding 1.0, though, means a
    denominator bug: dividing by *cast* or *counted* rather than *appointed*, or a
    denominator that lost a state. Widening the numerator's basis can only shrink each
    share, so this guard is strictly safer under the counted basis than it was under
    cast.
    """
    totals = hybrid_frame.groupby("year")["ec_share_full"].sum()
    over = totals.loc[totals > 1.0 + tolerance]
    if not over.empty:
        raise error_cls(
            "per-year electoral-vote shares sum to more than 1.0 — the appointed "
            f"denominator is wrong (each state counted once?): {over.to_dict()}"
        )


def assert_no_winner_tie(
    hybrid_frame: pd.DataFrame,
    score_column: str,
    *,
    error_cls: type[Exception] = HybridError,
) -> None:
    """Assert no year has two candidates sharing the maximum ``score_column``.

    A genuine dead heat should not occur on real data (no in-scope year has a
    first-place electoral tie, and identical popular-vote-derived ratios are vanishingly
    unlikely), so it fails loud rather than resolving arbitrarily.

    **An all-NULL year is explicitly not a tie** — it is a coverage gap (a warehouse
    built without UCSB has no pre-1976 popular vote at all), and conflating the two
    would turn the settled "accept the NULLs" decision into a build failure on every
    such year.

    Kept **separate from the winner derivation** on purpose (architect ruling, Fred
    2026-07-28), and #124 is where that paid off: the winners are now a SQL window rank,
    where a tie would surface as two rank-1 rows and be broken arbitrarily, so this runs
    as a :func:`create_hybrid_views` precondition instead. A ``raise`` baked into a
    winner column could not have survived that translation.
    """
    for year, group in hybrid_frame.groupby("year", sort=True):
        scored = group[score_column].dropna()
        if scored.empty:
            continue
        tied = group.loc[group[score_column] == scored.max(), "candidate"]
        if len(tied) > 1:
            raise error_cls(
                f"{year}: {score_column} tie between {sorted(tied)} — the winner is "
                "undefined; resolve the tie policy rather than breaking it arbitrarily."
            )


def assert_ec_winner_matches_rank(
    hybrid_frame: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    error_cls: type[Exception] = HybridError,
) -> None:
    """Assert the EC winner is the candidate the spine already ranks first.

    ``argmax(ec_share_full)`` and ``president_electoral_rank == 1`` are two independent
    paths to one fact — both monotonic in ``national_counted_electoral_votes``, one
    derived here and one carried from ``dwh.votes``. They must agree; a disagreement
    means the frame assembly misaligned candidates, which no per-column check would
    catch.

    The two share a **basis**, and that is load-bearing rather than incidental: the rank
    switched to the counted measure in #144 for the same reason this share did, and had
    only one of them moved, 1872 alone would have been enough to fire this guard.

    Not a claim about who took office: 1824's rank-1 was Jackson while the House
    installed Adams (``took_office``), and both are correct.
    """
    ranked = (
        hybrid_frame.loc[hybrid_frame["president_electoral_rank"] == 1]
        .groupby("year")["candidate"]
        .agg(set)
    )
    mismatched = {
        int(row.year): (row.ec_winner, sorted(ranked.get(row.year, set())))
        for row in summary.itertuples()
        if row.ec_winner is not None
        and row.ec_winner not in ranked.get(row.year, set())
    }
    if mismatched:
        raise error_cls(
            "the computed EC winner disagrees with the spine's "
            f"president_electoral_rank == 1 (year: (computed, rank-1)): {mismatched}"
        )


# --- DB readers (build-time only; never reached at serve time, D028) --------


def read_ec_pv_join(
    dbc: object,
    *,
    view: str = EC_PV_PREFERRED_VIEW,
    schema: str = SCHEMA,
) -> pd.DataFrame:
    """Read a **resolved** join view — ``ec_pv_preferred`` or the MIT-only sibling.

    Parameterized on the view rather than duplicated per surface, mirroring
    :func:`usvote.join.build_ec_pv_join_sql`. It must be one of the two *resolved*
    views: reading the raw ``dwh.pv_votes`` union instead would fan the 1976-2024
    overlap out 2x (D017) and double every popular-vote total.
    """
    allowed = (EC_PV_PREFERRED_VIEW, EC_PV_REDISTRIBUTABLE_VIEW)
    if view not in allowed:
        raise HybridError(
            f"{view!r} is not a resolved EC<->PV join view (expected one of "
            f"{allowed}); "
            "reading the raw pv_votes union would fan out the 1976-2024 overlap (D017)."
        )
    query = f"SELECT * FROM {schema}.{view}"
    return dbc.select_query_to_df(query)  # type: ignore[attr-defined]


def read_pv_status_roster(
    dbc: object,
    *,
    sources: Collection[str] | None = None,
    schema: str = ROSTER_SCHEMA,
    table: str = ROSTER_TABLE,
) -> pd.DataFrame:
    """Read ``dwh.pv_state_status``, optionally scoped to ``sources``.

    ``sources=None`` reads every source's rows. Where sources overlap their statuses
    agree, and :func:`_resolve_roster` collapses them — raising on a genuine
    disagreement, which reading only one source would silently hide. So the *unscoped*
    read is the right default for the widest analysis surface.

    **But the roster must match the surface being computed** (code review, #126). The
    roster is keyed on ``(source, year, state)`` while the coverage denominator is the
    EC allotment, so pointing a UCSB-bearing roster at the MIT-only
    ``ec_pv_redistributable`` view would report ``pv_coverage == 1.0`` for, say, 1900 —
    a year that surface carries no popular vote for at all. That is the exact inverse of
    what the flag means. :func:`build_hybrid_from_db` therefore scopes this read to the
    sources actually present in the chosen view.
    """
    query = f"SELECT source, year, state, pv_status FROM {schema}.{table}"
    roster = dbc.select_query_to_df(query)  # type: ignore[attr-defined]
    if sources is None:
        return roster
    return roster.loc[roster["source"].isin(set(sources))].reset_index(drop=True)


def build_hybrid_from_db(
    dbc: object,
    *,
    view: str = EC_PV_PREFERRED_VIEW,
    schema: str = SCHEMA,
    roster_schema: str = ROSTER_SCHEMA,
    policy: CoveragePolicy = COVERAGE_POLICY_MISMATCHED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the join view + roster; return ``(candidate frame, election summary)``.

    Local Postgres is required here, at **build time only** — the served API never opens
    this connection (D028). #124 materialized the result as
    ``hybrid_preferred``/``hybrid_redistributable`` plus their ``hybrid_summary_*``
    companions (:func:`create_hybrid_views`) and wired the rebuild into
    ``usvote.warehouse``.

    **The roster read is scoped to the surface** — the sources actually present in
    ``view`` — so the MIT-only redistributable surface is not handed UCSB's roster and
    made to claim full coverage for years it holds no popular vote for (code review,
    #126). A view with no PV at all yields an empty source set, hence NULL coverage.

    **On ``ec_pv_redistributable`` that scope now matches MIT's own rows** (#127,
    landed): ``run_mit_pipeline`` calls ``load_pv_status``, so 1976-2024 reports the
    true EV-weighted ``1.0`` and pre-1976 stays NULL — no PV *and* no MIT roster row
    reaches those years, which is the honest reading of an absent roster rather than a
    fabricated ``0.0``. Before the backfill this scope matched **nothing**, so the
    public surface reported NULL for *every* year including the fully-covered modern
    ones; that was the bug #127 fixed, not a flaw in this scoping.

    ``policy`` defaults to the shipped (b) (D038) and **no production caller passes
    anything else** — the views are built from this default and ``warehouse.py`` never
    names a policy, which is why the public surface's treatment is fixed rather than
    configurable (a test pins that no other module even mentions the constants).

    **The guards run here, not only in tests** (code review, #126). They exist to catch
    a denominator bug or a real dead heat, and on live warehouse data build time is the
    only place either can arise — the same reason
    :func:`usvote.join.create_ec_pv_views` runs
    :func:`usvote.join.assert_db_pv_matches_ec` as a precondition rather than trusting
    its upstream. :func:`create_hybrid_views` runs this function for exactly that
    reason, inheriting all four as its view-creation preconditions.

    **The build-and-guard half lives in** :func:`build_hybrid_from_frames` **(#102)**,
    so the snapshot build can run the identical guard set on frames it already holds
    without opening this connection. All this function adds is the two reads.
    """
    ec_pv_df = read_ec_pv_join(dbc, view=view, schema=schema)
    surface_sources = set(ec_pv_df["source"].dropna().unique())
    roster_df = read_pv_status_roster(
        dbc, sources=surface_sources, schema=roster_schema
    )
    return build_hybrid_from_frames(ec_pv_df, roster_df, policy=policy)


def build_hybrid_from_frames(
    ec_pv_df: pd.DataFrame,
    roster_df: pd.DataFrame,
    *,
    policy: CoveragePolicy = COVERAGE_POLICY_MISMATCHED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build both hybrid grains from frames, running the four guards. **DB-free.**

    The guarded core :func:`build_hybrid_from_db` wraps — extracted in #102 so the
    snapshot build gets the *same* validation without a database. Returns
    ``(candidate frame, election summary)``.

    **Why this is an extraction and not a convenience wrapper.** #102 computes the
    public surface's hybrid in-process from the frames
    :func:`usvote.snapshot.build_snapshot` already holds, rather than reading
    ``hybrid_redistributable`` — so it never passes
    through :func:`create_hybrid_views` and would otherwise inherit **none** of that
    function's preconditions. Four of the seven are these; the other three
    (:func:`assert_redistributable_only_source`,
    :func:`assert_carried_columns_constant`, :func:`usvote.join.assert_no_fan_out` on
    the input) are the caller's, because they constrain the *input* frame rather than
    the derivation, and the snapshot's equivalents differ
    (:func:`usvote.snapshot.assert_redistributable_only` covers the first).

    **:func:`assert_no_winner_tie` is the one that must not be skipped.**
    :func:`build_hybrid_summary` deliberately does **not** raise on a tie — a view
    cannot ``raise``, so #124 split the check out (see that function) — which means a
    caller that builds the summary without this guard ships an **arbitrary** winner on a
    genuine dead heat, silently. That is precisely the shape a second, unguarded build
    path would have introduced.

    The roster needs only ``(year, state, pv_status)``: :func:`_resolve_roster` groups
    on ``(year, state)`` and never reads ``source``, so a single-source roster — the
    in-repo curated one (:func:`usvote.pv.absences.build_curated_roster`) as much as a
    warehouse read — satisfies it unchanged.
    """
    frame = build_hybrid_frame(ec_pv_df, roster_df, policy=policy)
    summary = build_hybrid_summary(frame)

    assert_ec_shares_le_one(frame)
    for score in ("ec_share_full", "pv_share", "hybrid_score"):
        assert_no_winner_tie(frame, score)
    assert_ec_winner_matches_rank(frame, summary)
    return frame, summary


# --- SQL builders (drive the live views, #124) ------------------------------


def _candidate_sql_cte(ec_pv_view: str, schema: str, roster_ref: str) -> str:
    """The CTE block shared by the per-candidate builder — one per oracle step.

    Split out so :func:`build_hybrid_candidate_sql` reads as the projection it is, and
    so each CTE can be named after the pure function it mirrors.
    """
    src = f"{schema}.{ec_pv_view}"
    return (
        # ec_denominator_by_year: dedup (year, state) first -- a bare aggregate over the
        # joined rows would multiply each state's allotment by the candidate count.
        "WITH allot AS ("
        " SELECT year, state, max(total_electoral_votes) AS state_electoral_votes"
        f" FROM {src} GROUP BY year, state"
        "), ec_denom AS ("
        " SELECT year, sum(state_electoral_votes) AS ec_denominator"
        " FROM allot GROUP BY year"
        # _resolve_roster, scoped to the sources this surface actually carries -- the
        # scoping build_hybrid_from_db does, so the MIT-only surface is never handed
        # UCSB's roster and made to claim coverage for a year it holds no PV for.
        "), roster AS ("
        " SELECT year, state, min(pv_status) AS pv_status"
        f" FROM {roster_ref}"
        f" WHERE source IN (SELECT DISTINCT source FROM {src}"
        " WHERE source IS NOT NULL)"
        " GROUP BY year, state"
        # pv_coverage_by_year's numerator. The CASE is load-bearing: a bare FILTER sum
        # returns NULL both for a year the roster does not reach (coverage *unknown*)
        # and for a year it reaches with no popular-vote state (a real 0). Collapsing
        # those is exactly what D024's no-`unknown` design exists to prevent.
        "), coverage AS ("
        " SELECT a.year, CASE WHEN NOT EXISTS"
        " (SELECT 1 FROM roster r2 WHERE r2.year = a.year) THEN NULL ELSE"
        " coalesce(sum(a.state_electoral_votes)"
        f" FILTER (WHERE r.pv_status = '{PV_STATUS_POPULAR_VOTE}'), 0)"
        " END AS covered_electoral_votes"
        " FROM allot a LEFT JOIN roster r ON r.year = a.year AND r.state = a.state"
        " GROUP BY a.year"
        # roll_up_national's denominator half: per-(year, state) max BEFORE the year
        # sum.
        # max skips NULL, so a no-PV getter's NULL row cannot silently drop the state.
        "), pv_state AS ("
        " SELECT year, state, max(state_total_votes) AS state_total_votes"
        f" FROM {src} GROUP BY year, state"
        "), pv_denom AS ("
        " SELECT year, sum(state_total_votes) AS national_pv_denominator"
        " FROM pv_state GROUP BY year"
        # roll_up_national's per-candidate half. sum() over an all-NULL group returns
        # NULL, which *is* pandas min_count=1: a getter with no PV anywhere stays NULL
        # rather than becoming a fabricated 0.
        "), national AS ("
        " SELECT year, candidate_id, min(candidate) AS candidate,"
        # COLLATE "C" is load-bearing, not decoration: Postgres min(text) is
        # collation-dependent, and under the usual en_US.UTF-8 it returns 'Republican'
        # where Python's codepoint min in _resolved_party returns 'REPUBLICAN' -- a
        # silent disagreement on exactly the mixed-spelling case party is resolved for.
        # min(candidate) needs no such cast: assert_carried_columns_constant proves it
        # constant within the group, and min over one distinct value is
        # collation-independent.
        ' min(party COLLATE "C") AS party,'
        " max(national_electoral_votes) AS national_electoral_votes,"
        " max(national_counted_electoral_votes)"
        " AS national_counted_electoral_votes,"
        " min(president_electoral_rank) AS president_electoral_rank,"
        " bool_or(took_office) AS took_office,"
        " sum(candidate_votes) AS national_pv_votes"
        f" FROM {src} GROUP BY year, candidate_id"
        ")"
    )


def build_hybrid_candidate_sql(
    ec_pv_view: str,
    *,
    schema: str = SCHEMA,
    roster_schema: str = ROSTER_SCHEMA,
    roster_table: str = ROSTER_TABLE,
) -> str:
    """Return the per-``(year, candidate)`` SELECT over ``ec_pv_view`` — coverage (b).

    The SQL expression of :func:`build_hybrid_frame`, emitting exactly
    :data:`HYBRID_CANDIDATE_COLUMNS` in order. One builder for both surfaces
    (``ec_pv_view`` is ``ec_pv_preferred`` or ``ec_pv_redistributable``), mirroring
    :func:`usvote.join.build_ec_pv_join_sql` and :func:`usvote.pv.views
    .build_pv_preferred_sql` — the house dual-expression pattern, where this string
    drives the live view and the pandas builder is the oracle a differential
    integration test re-runs against it.

    **Coverage policy (b) only, and that is a property rather than a limitation**
    (D038/D050). (c) stays reachable only from Python, which is what makes the public
    surface's denominator treatment *fixed* rather than configurable — the property
    #102 relies on. See :func:`apply_coverage_policy`.

    **Every ratio casts its numerator to ``double precision`` first.** Postgres
    integer-divides two integers, so ``national_counted_electoral_votes /
    ec_denominator`` would silently read ``0`` for every candidate in every year — a
    plausible-looking column of zeros rather than an error. This is checked
    numerically, not by string shape (a string assert cannot survive a rewording).
    """
    ctes = _candidate_sql_cte(
        ec_pv_view, schema, f"{roster_schema}.{roster_table}"
    )
    ec_share = (
        "n.national_counted_electoral_votes::double precision / d.ec_denominator"
    )
    pv_share = "n.national_pv_votes::double precision / p.national_pv_denominator"
    return (
        f"{ctes}"
        " SELECT n.year, n.candidate_id, n.candidate, n.party,"
        " n.national_electoral_votes, n.national_counted_electoral_votes,"
        " d.ec_denominator,"
        f" {ec_share} AS ec_share_full,"
        " n.national_pv_votes, p.national_pv_denominator,"
        f" {pv_share} AS pv_share,"
        # Policy (b): the EC share is NOT restricted; the mismatch is flagged by
        # pv_coverage < 1.0 instead. ec_share_hybrid is therefore ec_share_full here.
        f" {ec_share} AS ec_share_hybrid,"
        " c.covered_electoral_votes::double precision / d.ec_denominator"
        " AS pv_coverage,"
        # D037: the average of the two ratios, NULL-propagating by construction.
        f" ({ec_share} + {pv_share}) / 2 AS hybrid_score,"
        " n.president_electoral_rank, n.took_office"
        " FROM national n"
        " JOIN ec_denom d ON d.year = n.year"
        " LEFT JOIN pv_denom p ON p.year = n.year"
        " LEFT JOIN coverage c ON c.year = n.year"
    )


def build_hybrid_summary_sql(hybrid_view: str, *, schema: str = SCHEMA) -> str:
    """Return the per-``(year)`` SELECT over ``hybrid_view`` — winners, flips, margins.

    The SQL expression of :func:`build_hybrid_summary`, emitting exactly
    :data:`HYBRID_SUMMARY_COLUMNS` in order.

    Three translations carry the whole correctness argument:

    - **The winner is a window rank, not a ``raise``-bearing argmax.** ``row_number()
      ... DESC NULLS LAST`` plus ``FILTER (WHERE rn = 1 AND <score> IS NOT NULL)``
      reproduces :func:`_winner`: an all-NULL year sorts a NULL row to rank 1, and the
      ``IS NOT NULL`` is what turns that into a NULL winner instead of an arbitrary
      candidate. A *tie* would make the pick arbitrary, which is precisely why
      :func:`assert_no_winner_tie` runs as a view-creation precondition (a view cannot
      ``raise``) rather than as logic inside this column.
    - **The margin is rank-1 minus rank-2 and needs no explicit arity check.** With
      fewer than two scored candidates the rank-2 term is NULL — either because no such
      row exists or because its score is NULL — so the whole expression is NULL. Never
      ``top1 - 0``, which would report a *share* under a column named margin.
    - **The flip is an explicit ``CASE``, not ``<>``.** Same reason :func:`_flip` is
      guarded: with no winner there is no baseline to differ from, and a method with no
      winner must read NULL rather than inventing a headline result out of a coverage
      gap.

    ``ec_margin`` reads ``ec_share_full``, never the policy-selected
    ``ec_share_hybrid``, so it stays coherent with the ``ec_winner`` and
    ``ec_determinative`` derived from that same column.
    """
    src = f"{schema}.{hybrid_view}"
    ranks = ", ".join(
        f"row_number() OVER (PARTITION BY year ORDER BY {score} DESC NULLS LAST)"
        f" AS {alias}_rn"
        for alias, score in (
            ("ec", "ec_share_full"),
            ("pv", "pv_share"),
            ("hybrid", "hybrid_score"),
        )
    )
    winners = ", ".join(
        f"max(candidate) FILTER (WHERE {alias}_rn = 1 AND {score} IS NOT NULL)"
        f" AS {alias}_winner"
        for alias, score in (
            ("ec", "ec_share_full"),
            ("pv", "pv_share"),
            ("hybrid", "hybrid_score"),
        )
    )
    margins = ", ".join(
        f"(max({score}) FILTER (WHERE {alias}_rn = 1)"
        f" - max({score}) FILTER (WHERE {alias}_rn = 2)) * 100.0 AS {alias}_margin"
        for alias, score in (
            ("ec", "ec_share_full"),
            ("pv", "pv_share"),
            ("hybrid", "hybrid_score"),
        )
    )
    flips = ", ".join(
        f"CASE WHEN {alias}_winner IS NULL OR ec_winner IS NULL THEN NULL"
        f" ELSE {alias}_winner <> ec_winner END AS {alias}_flip"
        for alias in ("pv", "hybrid")
    )
    return (
        "WITH ranked AS ("
        " SELECT year, candidate, ec_denominator, pv_coverage,"
        " ec_share_full, pv_share, hybrid_score,"
        f" {ranks}"
        f" FROM {src}"
        "), agg AS ("
        " SELECT year, max(ec_denominator) AS ec_denominator,"
        " max(pv_coverage) AS pv_coverage,"
        f" {winners},"
        # The leader's own share, so a strict > 0.5 is the 12th Amendment's test on the
        # appointed allotment. NULL (not false) where there is no EC winner at all.
        " bool_or(ec_share_full > 0.5)"
        " FILTER (WHERE ec_rn = 1 AND ec_share_full IS NOT NULL)"
        " AS ec_determinative,"
        f" {margins}"
        " FROM ranked GROUP BY year"
        ")"
        " SELECT year, ec_denominator, ec_winner, pv_winner, hybrid_winner,"
        " ec_determinative, pv_coverage,"
        f" {flips},"
        " ec_margin, pv_margin, hybrid_margin"
        " FROM agg"
    )


# --- view-creation preconditions + the creator (#124) -----------------------


def assert_carried_columns_constant(
    ec_pv_df: pd.DataFrame, *, error_cls: type[Exception] = HybridError
) -> None:
    """Assert each :data:`CARRIED_CANDIDATE_COLUMNS` entry is constant per
    candidate-year.

    The guard that keeps the SQL builder and the pandas oracle honest with each other.
    :func:`roll_up_national` carries these with pandas ``first`` while
    :func:`build_hybrid_candidate_sql` carries them with ``min``/``max``/``bool_or``,
    and the two agree **only** where the column does not vary within
    :data:`HYBRID_CANDIDATE_GRAIN`.

    Every column in that set is **structurally** constant, so a variation is an assembly
    bug rather than a property of the data: ``candidate`` is joined on ``candidate_id``,
    the two national totals are window sums over exactly this partition, and the rank
    and ``took_office`` are broadcast per candidate-year by the transform.

    A divergence would be **silent in both directions**, which is why this raises rather
    than being noted in a comment: pandas ``first`` reads the first non-null row of an
    unordered ``SELECT``, so the oracle would not merely differ from the SQL — it would
    not be deterministic either. The same shape as
    :func:`ec_denominator_by_year`'s allotment check, and for the same reason.

    ``party`` is **not** in the set; it varies legitimately and is resolved instead
    (:func:`_resolved_party`).
    """
    present = [c for c in CARRIED_CANDIDATE_COLUMNS if c in ec_pv_df.columns]
    grouped = ec_pv_df.groupby(list(HYBRID_CANDIDATE_GRAIN))
    counts = grouped[present].nunique(dropna=True)
    offenders = {}
    for col in present:
        keys = counts.index[counts[col] > 1]
        if not len(keys):
            continue
        # Name the values, not just the key: "party varies in (2016, 3)" sends the
        # reader hunting, while the two spellings usually identify the cause outright.
        offenders[col] = {
            key: sorted(
                {str(v) for v in grouped.get_group(key)[col].dropna().unique()}
            )
            for key in list(keys)[:5]
        }
    if offenders:
        raise error_cls(
            "carried column(s) vary within (year, candidate_id), so the SQL view and "
            "the pandas oracle would disagree (and 'first' would not even be "
            f"deterministic): {offenders}"
        )


def assert_redistributable_only_source(
    ec_pv_df: pd.DataFrame, *, error_cls: type[Exception] = HybridError
) -> None:
    """Assert no ``redistributable = false`` / non-MIT row is on the public surface.

    #124's "defense in depth" data guard, the sibling of
    :func:`usvote.snapshot.assert_redistributable_only` — **reimplemented here rather
    than imported**, because :mod:`usvote.snapshot` already imports *from* this module
    (``HybridError``, ``ec_denominator_by_year``, ``roll_up_national``), so importing it
    back would be a circular import.

    It runs on the **input join frame, pre-aggregation**: after the roll-up to
    ``(year, candidate)`` there is no ``source``/``redistributable`` column left to
    assert on. And it runs against **live data**, as a view-creation precondition — a
    clean assertion over a hand-authored fixture would prove nothing, which is the
    vacuity the structural view-definition test exists to cover instead.

    A getter MIT does not cover has NULL PV (NULL ``source`` and ``redistributable``),
    which is fine — an honest D005 gap. Only an explicit ``False`` or a non-MIT
    ``source`` is a violation.
    """
    if "redistributable" in ec_pv_df.columns:
        bad = ec_pv_df["redistributable"] == False  # noqa: E712 -- NULL must NOT match
        if bool(bad.any()):
            cols = ["year", "state", "candidate"]
            raise error_cls(
                "redistributable=false row(s) reached the redistributable hybrid "
                "surface (D030) — the guard exists for exactly this regression: "
                f"{ec_pv_df.loc[bad, cols].head().values.tolist()}"
            )
    non_mit = ec_pv_df["source"].dropna().ne(SOURCE_MIT)
    if bool(non_mit.any()):
        offenders = sorted(ec_pv_df["source"].dropna()[non_mit].unique())
        raise error_cls(
            f"non-MIT source(s) {offenders} reached the redistributable hybrid "
            "surface (D016/D030) — only MIT is redistributable."
        )


def assert_no_fan_out(
    df: pd.DataFrame,
    key: Sequence[str],
    *,
    error_cls: type[Exception] = HybridError,
) -> None:
    """Assert one row per ``key`` — the :func:`usvote.join.assert_no_fan_out` analogue.

    Called at both grains: :data:`HYBRID_CANDIDATE_GRAIN` for the per-candidate view and
    :data:`HYBRID_SUMMARY_GRAIN` for the summary.

    **Be precise about what this can and cannot catch, because the obvious reading is
    wrong.** Both frames it inspects are group-by outputs, so duplicate keys are
    impossible *by construction* today — it is a contract check against a future builder
    that stops aggregating, not a live tripwire. In particular it does **not** catch the
    failure it is naturally assumed to: a raw ``dwh.pv_votes`` union leaking into the
    join view (two rows per 1976-2024 overlap key) still collapses to one row per key
    here, and surfaces instead as a **doubled** ``national_pv_votes`` — the denominator
    is protected by the per-``(year, state)`` ``max``, so ``pv_share`` doubles while
    this guard sees nothing. That failure is caught upstream, at the grain where it is
    expressible, by :func:`usvote.join.assert_no_fan_out` on the input join frame, which
    :func:`create_hybrid_views` runs as a precondition. An earlier version of this
    docstring claimed the coverage this one disclaims (code review, #124).
    """
    dupes = df.loc[df.duplicated(list(key), keep=False)]
    if not dupes.empty:
        raise error_cls(
            f"hybrid frame fanned out (>1 row per {tuple(key)}): "
            f"{dupes[list(key)].values.tolist()}"
        )


def _relation_exists(dbc: DBC, schema: str, name: str) -> bool:
    """Return whether ``schema.name`` exists, via ``to_regclass`` (NULL when absent).

    The same cheap non-raising probe :func:`usvote.join.create_ec_pv_views` uses, kept
    local for the reason that one is: a module does not reach into another's private
    helper.
    """
    got = dbc.select_query_to_df(f"SELECT to_regclass('{schema}.{name}') AS relation")
    return got["relation"].iloc[0] is not None


def create_hybrid_views(
    dbc: DBC,
    *,
    schema: str = SCHEMA,
    roster_schema: str = ROSTER_SCHEMA,
    replace: bool = True,
    close: bool = False,
) -> None:
    """Create all four hybrid views, after the per-surface preconditions pass.

    Mirrors :func:`usvote.join.create_ec_pv_views`: probe **every** input, then per
    surface run the guards as **preconditions** and create. The per-candidate view is
    created first and its summary second, because the summary reads it.

    **All probing happens before any creation, and that ordering is the point.** This
    function opens no transaction and ``DBC`` commits per statement, so a probe inside
    the loop would let a failure on the second surface leave the first surface's pair
    created and committed — a warehouse advertising two of four hybrid views. The guards
    themselves stay per-surface (they need that surface's data), so this narrows the
    window rather than closing it; what it removes is the *foreseeable* half-build,
    where an input is simply absent.

    **Seven preconditions run before anything is created**, over exactly the data the
    views will express. Three are checked here directly, on the input join frame:

    - :func:`assert_redistributable_only_source` — redistributable surface only (D030);
    - :func:`assert_carried_columns_constant` — the columns the SQL carries with
      ``min``/``max``/``bool_or`` really are constant per candidate-year;
    - :func:`usvote.join.assert_no_fan_out` — at the **input** grain, the one grain
      where a raw-union leak is expressible (see :func:`assert_no_fan_out` for why the
      two output-grain checks cannot see it).

    Four more come from calling :func:`build_hybrid_from_db`, which is what that
    function promised #124 would inherit: ``assert_ec_shares_le_one``,
    ``assert_no_winner_tie`` on all three scores, ``assert_ec_winner_matches_rank``, and
    (inside ``_resolve_roster``) the cross-source status-disagreement check. The tie
    check matters most: a view cannot ``raise``, and a genuine dead heat would otherwise
    make the window-rank winner an arbitrary pick.

    **Know what these guards do and do not cover.** They validate the *pandas*
    derivation, not the emitted SQL, so a SQL/oracle drift passes every one of them.
    What covers that is the differential integration test, which reads both grains
    back from the live views and compares them to the oracle. Stated here
    because the asymmetry is easy to forget when adding a guard later.

    ``replace`` defaults to ``True`` (``CREATE OR REPLACE VIEW`` — idempotent and
    non-destructive). Note the consequence of the new view-on-view dependency (D050): a
    *breaking* column change to a per-candidate view now needs an explicit
    ``DROP ... CASCADE`` migration, since its summary depends on it.
    """
    # EVERY input is probed before ANY view is created. DBC commits per statement and
    # this function opens no transaction, so probing inside the loop below would let a
    # failure on the second surface leave the first surface's pair created and
    # committed -- a warehouse advertising two of four hybrid views. The sibling
    # usvote.join.create_ec_pv_views probes both of its inputs up front for exactly this
    # reason. The roster is probed too: it is a required input (read_pv_status_roster),
    # and without this its absence surfaces mid-loop as a raw psycopg2 UndefinedTable,
    # which also aborts the connection -- the opacity the probe exists to prevent.
    for join_view, _, _ in HYBRID_SURFACES:
        if not _relation_exists(dbc, schema, join_view):
            raise HybridError(
                f"{schema}.{join_view} does not exist — run "
                "usvote.join.create_ec_pv_views (or usvote.warehouse.rebuild_views) "
                "before create_hybrid_views."
            )
    if not _relation_exists(dbc, roster_schema, ROSTER_TABLE):
        raise HybridError(
            f"{roster_schema}.{ROSTER_TABLE} does not exist — load a popular-vote "
            "source (which writes the D024 roster) before create_hybrid_views; "
            "pv_coverage cannot be derived without it."
        )

    for join_view, candidate_view, summary_view in HYBRID_SURFACES:
        # Licensing and carried-column guards first, so a leak or a SQL/oracle
        # divergence fails before the (more expensive) derivation runs.
        ec_pv_df = read_ec_pv_join(dbc, view=join_view, schema=schema)
        if join_view == EC_PV_REDISTRIBUTABLE_VIEW:
            assert_redistributable_only_source(ec_pv_df)
        assert_carried_columns_constant(ec_pv_df)
        # At the INPUT grain, where a raw-union leak is actually expressible: two rows
        # per 1976-2024 overlap key would double national_pv_votes while collapsing
        # invisibly at the output grains below (see assert_no_fan_out).
        assert_join_no_fan_out(ec_pv_df)
        frame, summary = build_hybrid_from_db(
            dbc, view=join_view, schema=schema, roster_schema=roster_schema
        )
        assert_no_fan_out(frame, HYBRID_CANDIDATE_GRAIN)
        assert_no_fan_out(summary, HYBRID_SUMMARY_GRAIN)
        dbc.create_view(
            schema,
            candidate_view,
            build_hybrid_candidate_sql(
                join_view, schema=schema, roster_schema=roster_schema
            ),
            replace=replace,
        )
        dbc.create_view(
            schema,
            summary_view,
            build_hybrid_summary_sql(candidate_view, schema=schema),
            replace=replace,
        )
    if close:
        dbc.close_connection()
