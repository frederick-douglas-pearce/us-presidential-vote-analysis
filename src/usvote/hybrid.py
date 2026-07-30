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
``ec_determinative`` flag, and the coverage flag. Flip detection and the three-method
margins are **#123**, not here; view materialization is **#124**.

**This module ships no SQL, deliberately** (architect ruling, Fred 2026-07-28).
``join.py`` pairs a SQL builder with a pandas oracle because the same epic
materializes the view; #121 performs no DB write, so a builder here would be dead code —
and a view cannot ``raise``, so #124 must express the winners as a window rank plus a
separate precondition query anyway. Two consequences are honoured throughout: every
step stays relationally expressible (group-by aggregate, join, rank), and **the tie
check is a separate ``assert_*``, never embedded in a winner column** — so #124's
translation is mechanical.

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
coverage policy from manufacturing a constitutional majority that never existed:
restricting 1824's EC share to the popular-vote states would put Jackson at
99/190 = 0.52 — over the line — when the real answer is 99/261 = 0.379 and the House
decided the election.

**The majority basis is the appointed allotment** (D041), exactly the 12th Amendment's
"majority of the whole number of Electors **appointed**", while the numerators are votes
actually **cast**. Real shortfalls exist (the 2000 DC abstention, faithless electors),
so Σ ``president_electoral_votes`` can be *less* than ``ec_denominator`` and candidate
shares sum to **≤ 1.0, never == 1.0** — correct, not a bug
(:func:`assert_ec_shares_le_one`). 2000 is Bush **271 of 538 appointed**, not 269 of
537 cast.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

import pandas as pd

from usvote.join import EC_PV_PREFERRED_VIEW, EC_PV_REDISTRIBUTABLE_VIEW
from usvote.load import SCHEMA
from usvote.pv.status import (
    PV_STATUS_POPULAR_VOTE,
    ROSTER_SCHEMA,
    ROSTER_TABLE,
)

__all__ = [
    "HYBRID_CANDIDATE_COLUMNS",
    "HYBRID_CANDIDATE_GRAIN",
    "HYBRID_SUMMARY_COLUMNS",
    "HYBRID_SUMMARY_GRAIN",
    "REQUIRED_JOIN_COLUMNS",
    "HybridError",
    "apply_coverage_policy",
    "assert_ec_shares_le_one",
    "assert_ec_winner_matches_rank",
    "assert_no_winner_tie",
    "build_hybrid_frame",
    "build_hybrid_from_db",
    "build_hybrid_summary",
    "ec_denominator_by_year",
    "pv_coverage_by_year",
    "read_ec_pv_join",
    "read_pv_status_roster",
    "roll_up_national",
]

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

#: The per-election summary's column contract, in order.
HYBRID_SUMMARY_COLUMNS: tuple[str, ...] = (
    "year",
    "ec_denominator",
    "ec_winner",
    "pv_winner",
    "hybrid_winner",
    "ec_determinative",
    "pv_coverage",
)

#: The columns this module reads off the resolved join view. A strict subset of
#: :data:`usvote.join.EC_PV_COLUMNS` (pinned by a test), which is the shape that
#: actually exists — there is no live hybrid view to pin against until #124.
REQUIRED_JOIN_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "candidate_id",
    "candidate",
    "party",
    "total_electoral_votes",
    "president_electoral_votes",
    "national_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "candidate_votes",
    "state_total_votes",
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
    return out[["year", "ec_denominator", "pv_coverage"]]


# --- the coverage policy (D038: (b) is settled) -----------------------------


def apply_coverage_policy(
    national: pd.DataFrame,
    ec_pv_df: pd.DataFrame,
    roster_df: pd.DataFrame,
) -> pd.DataFrame:
    """Own both hybrid numerators and both hybrid denominators — policy **(b)**.

    The hybrid averages an EC share against a PV share, and for a partial-coverage year
    those shares are computed over differently-sized electorates. Rule (a) — withhold
    the hybrid for such years — is **rejected** (D038): it would suppress precisely the
    no-EC-majority, House-contingent elections the hybrid exists to speak to. Of the two
    honest treatments, **(b) is settled** (D038, Fred 2026-07-28): compute with the
    mismatched denominators and *flag* the mismatch with ``pv_coverage < 1.0``.

    Under (b): ``ec_share_hybrid == ec_share_full`` (the EC share is not restricted),
    and
    ``pv_share`` divides the candidate's national PV by the source's provided per-state
    totals, which a no-popular-vote state simply does not contribute to.

    ``ec_share_full`` and ``ec_determinative`` are deliberately **outside this
    function's reach** (D037/A) — they are policy-invariant, computed in
    :func:`build_hybrid_frame`, so no coverage policy can move them.

    **E7-S3 (#122) is where the (c) branch and the ``policy`` argument land.** (c)
    restricts *both* shares' denominators to the ``popular_vote`` states, at which point
    ``ec_share_hybrid`` may diverge from ``ec_share_full``. Keeping the whole policy
    inside one pure function is what makes that a switch rather than a rework of
    denominator logic — and on the MIT-only redistributable surface every state held a
    popular vote, so the policy degrades to identity and ``hybrid_redistributable`` is
    provably policy-invariant either way (the property #102 relies on).
    """
    coverage = pv_coverage_by_year(ec_pv_df, roster_df)
    out = national.merge(coverage[["year", "pv_coverage"]], on="year", how="left")
    out["ec_share_hybrid"] = out["ec_share_full"]
    out["pv_share"] = out["national_pv_votes"] / out["national_pv_denominator"]
    return out


# --- the two builders -------------------------------------------------------


def build_hybrid_frame(
    ec_pv_df: pd.DataFrame, roster_df: pd.DataFrame
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
    """
    national = roll_up_national(
        ec_pv_df,
        key=HYBRID_CANDIDATE_GRAIN,
        carry={
            "candidate": "candidate",
            "party": "party",
            "national_electoral_votes": "national_electoral_votes",
            "president_electoral_rank": "president_electoral_rank",
            "took_office": "took_office",
        },
    )
    national = national.merge(ec_denominator_by_year(ec_pv_df), on="year", how="left")
    national["ec_share_full"] = (
        national["national_electoral_votes"] / national["ec_denominator"]
    )
    frame = apply_coverage_policy(national, ec_pv_df, roster_df)
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
    kept separate so #124 can translate this to a SQL window rank (a view cannot
    ``raise``) and make the tie check a precondition query.
    """
    ranked = scores.dropna()
    if ranked.empty:
        return None
    return str(names.loc[ranked.idxmax()])


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

    Note it reads ``ec_share_full``, never ``ec_share_hybrid`` (D037/A). Flips and
    margins are #123.
    """
    rows: list[dict[str, object]] = []
    for year, group in hybrid_frame.groupby("year", sort=True):
        ec_winner = _winner(group["ec_share_full"], group["candidate"])
        determinative: object = pd.NA
        if ec_winner is not None:
            leader = group.loc[group["candidate"] == ec_winner, "ec_share_full"].iloc[0]
            determinative = bool(leader > 0.5)
        rows.append({
            "year": year,
            "ec_denominator": group["ec_denominator"].iloc[0],
            "ec_winner": ec_winner,
            "pv_winner": _winner(group["pv_share"], group["candidate"]),
            "hybrid_winner": _winner(group["hybrid_score"], group["candidate"]),
            "ec_determinative": determinative,
            "pv_coverage": group["pv_coverage"].iloc[0],
        })
    return pd.DataFrame(rows, columns=list(HYBRID_SUMMARY_COLUMNS))


# --- guards (run as automated tests) ----------------------------------------


def assert_ec_shares_le_one(
    hybrid_frame: pd.DataFrame,
    *,
    tolerance: float = 1e-9,
    error_cls: type[Exception] = HybridError,
) -> None:
    """Assert per-year Σ ``ec_share_full`` ≤ 1.0 — **never** that it equals 1.0 (D041).

    The denominator is the **appointed** allotment; the numerators are votes **cast**.
    Real shortfalls (the 2000 DC abstention, faithless electors) make the sum strictly
    less than
    1.0 in such a year — 2000 is 537 of 538 — so an ``== 1.0`` assertion would fail on
    correct data. Exceeding 1.0, though, means a denominator bug: dividing by *cast*
    rather than *appointed*, or a denominator that lost a state.
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
    2026-07-28): #124 materializes these as SQL views, where a tie surfaces as two
    rank-1 rows and this becomes a precondition query. A ``raise`` baked into a winner
    column could not survive that translation.
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
    paths to one fact — both monotonic in ``national_electoral_votes``, one derived here
    and one carried from ``dwh.votes``. They must agree; a disagreement means the frame
    assembly misaligned candidates, which no per-column check would catch.

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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the join view + roster; return ``(candidate frame, election summary)``.

    Local Postgres is required here, at **build time only** — the served API never opens
    this connection (D028). #124 is what materializes the result as
    ``hybrid_preferred``/``hybrid_redistributable`` plus their ``hybrid_summary``
    companions and wires the rebuild into ``usvote.warehouse``.

    **The roster read is scoped to the surface** — the sources actually present in
    ``view`` — so the MIT-only redistributable surface is not handed UCSB's roster and
    made to claim full coverage for years it holds no popular vote for (code review,
    #126). A view with no PV at all yields an empty source set, hence NULL coverage.

    **The guards run here, not only in tests** (code review, #126). They exist to catch
    a denominator bug or a real dead heat, and on live warehouse data build time is the
    only place either can arise — the same reason
    :func:`usvote.join.create_ec_pv_views` runs
    :func:`usvote.join.assert_db_pv_matches_ec` as a precondition rather than trusting
    its upstream. #124 inherits them as its view-creation preconditions.
    """
    ec_pv_df = read_ec_pv_join(dbc, view=view, schema=schema)
    surface_sources = set(ec_pv_df["source"].dropna().unique())
    roster_df = read_pv_status_roster(dbc, sources=surface_sources)
    frame = build_hybrid_frame(ec_pv_df, roster_df)
    summary = build_hybrid_summary(frame)

    assert_ec_shares_le_one(frame)
    for score in ("ec_share_full", "pv_share", "hybrid_score"):
        assert_no_winner_tie(frame, score)
    assert_ec_winner_matches_rank(frame, summary)
    return frame, summary
