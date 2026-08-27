"""The D017 layer-3 overlap-validation gate — MIT vs. UCSB agreement (#167, D051).

D017 §3 made the 1976-2024 MIT/UCSB overlap a **validation gate** — "disagreements
beyond a tolerance are flagged with provenance, not silently resolved" — but named no
tolerance and shipped no check, deferring both to a research task. That task (#70,
:file:`.claude/specs/research-pv-overlap.md`) measured the overlap; **D051** adopted its
§6 thresholds. This module is the code those two documents were waiting for.

**Two of the three thresholds live here; the third does not.** D051 splits them by
grain, and the split is about *where the code lives*:

- **Gates 1 and 2** — the exact-match-rate floor and the per-cell relative ceiling — run
  at the ``(year, state, candidate)`` cell grain over the PV union, so they belong here.
- **Gate 3** — the national margin-difference ceiling — is the E7 trustworthiness check
  and lives in :mod:`usvote.hybrid`, beside the computation it protects. That placement
  is **forced, not preferred**: it is derived with
  :func:`usvote.hybrid.roll_up_national`, and a home here would need a ``pv -> hybrid``
  import, which ``tests/unit/test_layering.py`` forbids.

**Why this module sits under** ``usvote/pv/`` **at all.** It compares two sources, so it
cannot live in either source's subpackage (D015 forbids source-to-source). It is the
same shelf as :mod:`usvote.pv.validate` — invariants over data *values*, not the D018
column contract — and it names no ``dwh.votes``, so the greppable EC-knowledge invariant
holds.

**What the gate reads, and what it must never read.** The two shipped D017 single-source
views, ``dwh.pv_redistributable`` (MIT today) and ``dwh.pv_ucsb`` — **never** the raw
``dwh.pv_votes`` union, which carries both sources' rows per overlap key and would fan
the comparison out 2x. :func:`read_overlap_frames` is the one place that read is
expressed.

**No magnitude ever leaves this module.** Gate 2's flag list is a list of *keys*
(:class:`OverlapKey`), and that is a licensing constraint rather than a style choice.
UCSB is ``redistributable=false`` (D016) and this repository is public, so the operative
test (research §2) is *"does this figure let a reader reconstruct an individual record
they would otherwise have to get from UCSB?"* — **not** "is this a UCSB integer?".
MIT is CC0 and exactly reproducible, so an attributed *relative* delta inverts via
``UCSB = MIT / (1 +/- rel)``. :class:`OverlapKey` therefore has no field that could
carry a delta or an absolute magnitude: the leak is impossible by type rather than by
discipline.

*(This is also where* :file:`.claude/specs/research-pv-overlap.sql`'s *"KNOWN
LIMITATION" is resolved rather than inherited. That script's 500-vote absolute floor
existed to decide which divergent cells were safe to publish* with a magnitude. *This
gate publishes no magnitude at all, so the predicate has no analogue here and none is
carried over.)*

**Dual expression, as everywhere else in this package.** :func:`compute_overlap_report`
is a pure-pandas oracle over two frames; :func:`assert_db_overlap_within_tolerance` is
the live-DB form that reads the views and hands them to it — the
:func:`usvote.join.assert_pv_matches_ec` / :func:`usvote.join.assert_db_pv_matches_ec`
precedent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from usvote.db import DBC
from usvote.pv.schema import PV_SCHEMA
from usvote.pv.source import MIT_PV_YEAR_MIN
from usvote.pv.views import (
    PV_REDISTRIBUTABLE_VIEW,
    PV_UCSB_VIEW,
    RESOLVED_KEY,
)
from usvote.years import ec_ingest_years

__all__ = [
    "CELL_RELPCT_FAIL",
    "CELL_RELPCT_FLAG",
    "EXACT_MATCH_FLOOR_OVERALL",
    "EXACT_MATCH_FLOOR_PER_YEAR",
    "SKIP_ALL_YEARS_AT_FRONTIER",
    "SKIP_NO_OVERLAP_CELLS",
    "SKIP_UCSB_ABSENT",
    "OverlapKey",
    "OverlapReport",
    "PVOverlapError",
    "assert_db_overlap_within_tolerance",
    "assert_overlap_within_tolerance",
    "compute_overlap_report",
    "read_overlap_frames",
]


# --- the D051 thresholds ----------------------------------------------------
#
# Every value below is adopted verbatim from D051, which adopted
# `.claude/specs/research-pv-overlap.md` §6. The observed figure beside each is what §6
# records as of 2026-08-22, and is what `tests/unit/test_pv_overlap.py` pins by
# hand-written literal so a silent retune is visible in a diff (AC-7).

#: Gate 1, overall: minimum share of overlap cells whose two sources agree **exactly**,
#: as a percentage. D051 / research §6 threshold 1; observed **93.44%**. This is the
#: instrument for the failure that matters most — *many* cells drifting slightly, a
#: methodology step — which no per-cell ceiling loose enough to tolerate a real canvass
#: revision could ever catch.
EXACT_MATCH_FLOOR_OVERALL = 90.0

#: Gate 1, per year: the same floor applied to **each single year**. D051 / research §6
#: threshold 1; worst observed **84.31%** (1976). D051 flags this as the tightest
#: threshold in the table on purpose — in *cells* it allows about 4 of slack against
#: 1976's observed count — because it is the instrument for a *localized* regression
#: that would move one year, and slack defeats it. **Expect this to be the first
#: threshold to need review.**
EXACT_MATCH_FLOOR_PER_YEAR = 80.0

#: Gate 2, flag: per-cell relative delta above which a cell joins the D005 reliability
#: list. D051 / research §6 threshold 2; **7 of 87 divergent cells** flag today.
#: Flagging is **not** a failure — the list is reported, never raised on.
CELL_RELPCT_FLAG = 1.0

#: Gate 2, fail: per-cell relative delta above which the gate **raises**. D051 /
#: research §6 threshold 2. Deliberately 15% rather than 10%: no divergent cell exceeds
#: 10% today and one exceeds 5%, so a 10% line sits close enough to live data to redden
#: on an ordinary canvass revision. 15% still catches an order-of-magnitude error, which
#: is what a hard fail should be for.
CELL_RELPCT_FAIL = 15.0

#: Skip reason: no UCSB rows at all, so there is no overlap to validate. A public clone
#: builds EC + MIT only (``warehouse.py`` gates UCSB explicitly), and this gate must not
#: redden that build (AC-3).
SKIP_UCSB_ABSENT = "pv_ucsb is empty — UCSB is not loaded, so there is no overlap"

#: Skip reason: **at least one** source has no rows in the overlap window, so there is
#: no pairing to measure. Kept distinct from :data:`SKIP_UCSB_ABSENT` on purpose — that
#: one is the live seam's specific finding ("UCSB is not loaded"), this one is what the
#: oracle can see from two frames alone, and an exact-match *rate* over an empty
#: population is 0/0, not 100%: reporting it as a pass would be the silent vacuous-green
#: this gate exists to prevent.
SKIP_NO_OVERLAP_CELLS = (
    f"no {MIT_PV_YEAR_MIN}+ overlap cells — at least one source has no rows "
    "in the window"
)

#: Skip reason: both sources have rows in the window, but every in-window year either
#: of them carries sits at or beyond the spine frontier, so all are excluded as refresh
#: and nothing is left to compare. Kept distinct from :data:`SKIP_NO_OVERLAP_CELLS`
#: because that one asserts a source is *empty*, which is false here — and a reason that
#: misreports which of the two states was reached sends an operator to the wrong place.
SKIP_ALL_YEARS_AT_FRONTIER = (
    "no comparable years — every in-window year either source carries sits at or "
    "beyond the spine frontier"
)


class PVOverlapError(RuntimeError):
    """A D017 layer-3 overlap tolerance (D051 gate 1 or gate 2) was breached.

    Sibling of :class:`usvote.pv.views.PVViewError` and
    :class:`usvote.pv.validate.PVValidationError`: a typed failure for one shared PV
    invariant. Raised only by :func:`assert_overlap_within_tolerance` — never by the
    report computation, which measures without judging.
    """


@dataclass(frozen=True)
class OverlapKey:
    """One ``(year, state, candidate)`` overlap cell, with its party for display.

    **The identity is the first three fields** — :data:`usvote.pv.views.RESOLVED_KEY`,
    the canonical PV key. ``party`` is a *carried display attribute*, not part of the
    key, and joining on it would be a bug rather than a refinement: MIT spells parties
    ``REPUBLICAN``/``DEMOCRAT`` where UCSB spells them ``Republican``/``Democratic``
    across the entire overlap (the live-corpus finding recorded in #124, which is why
    ``usvote.hybrid`` resolves ``party`` by ``min`` rather than requiring it constant).
    A four-column join would make **every** cell one-sided and collapse the exact-match
    rate to zero. The value carried is MIT's spelling, falling back to UCSB's where MIT
    has no row for the key. Research §3 does the same: it joins on the three-column key
    and merely prints party.

    **This type deliberately has no numeric field**, and that is the D030/D022 licensing
    constraint made structural — see the module docstring. Adding a delta or a magnitude
    here would republish a UCSB record; ``test_pv_overlap.py`` asserts the field set to
    stop that happening by accident.
    """

    year: int
    state: str
    candidate: str
    #: ``compare=False`` so it is excluded from ``__eq__``/``__hash__`` — the docstring
    #: above says the identity is the first three fields, and a generated equality over
    #: all four would contradict it on exactly the case this class exists to handle:
    #: two spellings of one party would compare unequal and hash apart, so any consumer
    #: deduping or diffing flagged lists across surfaces would get party-sensitive
    #: behaviour the type promises it does not have.
    party: str | None = field(compare=False, default=None)


@dataclass(frozen=True)
class OverlapReport:
    """What the cell-grain gates measured — the structured result, magnitude-free.

    A ``skipped`` report carries no measurements and asserts nothing: every count is
    zero and every list empty, so a caller that ignores ``skipped`` reads a *skip* as an
    empty measurement rather than as a clean one. Check ``skipped`` before reading any
    other field.
    """

    skipped: bool = False
    skip_reason: str | None = None
    cells: int = 0
    exact: int = 0
    exact_pct: float = 0.0
    exact_pct_by_year: dict[int, float] = field(default_factory=dict)
    one_sided: tuple[OverlapKey, ...] = ()
    flagged: tuple[OverlapKey, ...] = ()
    failed: tuple[OverlapKey, ...] = ()
    #: Years reached by only one source **at or beyond the spine frontier**
    #: (``max(ec_ingest_years())``), excluded from every count above as ordinary
    #: asymmetric refresh. A one-sided year *below* the frontier is a regression and
    #: does **not** appear here — it stays in the population and trips gate 1. See
    #: :func:`compute_overlap_report`.
    uncovered_years: tuple[int, ...] = ()


def _keys(rows: pd.DataFrame) -> tuple[OverlapKey, ...]:
    """Build the ordered :class:`OverlapKey` tuple for ``rows`` of the merged frame."""
    ordered = rows.sort_values(list(RESOLVED_KEY), kind="stable")
    return tuple(
        OverlapKey(
            year=int(row.year),
            state=str(row.state),
            candidate=str(row.candidate),
            party=None if pd.isna(row.party) else str(row.party),
        )
        for row in ordered.itertuples(index=False)
    )


def compute_overlap_report(
    mit_df: pd.DataFrame, ucsb_df: pd.DataFrame, *, spine_max: int | None = None
) -> OverlapReport:
    """Measure MIT-vs-UCSB cell agreement over the overlap window — the pure oracle.

    ``mit_df``/``ucsb_df`` are :data:`usvote.pv.schema.SHARED_PV_COLUMNS`-shaped frames,
    normally read from ``pv_redistributable``/``pv_ucsb`` by
    :func:`read_overlap_frames`. Both are filtered to ``year >= MIT_PV_YEAR_MIN`` here
    as well as at the read, so the oracle is correct when called directly from a test.
    ``spine_max`` overrides the frontier below and is a **test seam only** — no caller
    under ``src/`` passes it, and a test that needs the *derived* frontier to move must
    patch :func:`usvote.years.ec_ingest_years` instead, since injecting a value here
    would pass whether the default is derived or hardcoded.

    **The population is the FULL OUTER key set**, mirroring research query 1, which
    counts one-sided rows directly rather than filtering them away. A key present in
    only one source counts as **not exact** and is listed in
    :attr:`OverlapReport.one_sided`; its relative delta is undefined, so it enters
    neither gate-2 list. An inner join would instead *raise* the exact-match rate by
    dropping exactly the rows a regression would create — the inner-join-silent-drop
    hazard, one level up from where this package already guards it.

    **A year only one source covers is excluded ONLY at or beyond the spine frontier**
    — ``max(usvote.years.ec_ingest_years())``, the newest election the EC spine knows
    about — and an excluded year is listed in :attr:`OverlapReport.uncovered_years`.

    - **At or beyond the frontier**: ordinary asymmetric refresh. MIT is a CSV drop and
      the UCSB corpus is a manual snapshot, so one source reaching the newest election
      first is expected; "not loaded yet" and "lost" are indistinguishable there, and
      for the frontier election "not yet" is the honest reading. The bound is inclusive
      because the frontier year is *precisely* the one legitimately one-sided mid-cycle.
    - **Below the frontier**: a regression. It stays in the population, its cells count
      as one-sided, its year rate reads 0%, and gate 1's per-year floor trips. Every
      year below the frontier is an election both sources have had a full cycle to
      publish, so there is no benign reading of one of them dropping it.

    **The frontier is the EC spine's, not the data's, and that is the whole point.** An
    earlier form of this rule took the ceiling from the frames themselves
    (``min(max MIT year, max UCSB year)``) and was **circular** — it let the data define
    the boundary that is supposed to detect the data being wrong. A truncated MIT drop
    covering only 1976-1996 pulled the ceiling down to 1996 with it, excluded seven
    elections, and reported **100% agreement** on what was left while 2000-2024 vanished
    from ``ec_pv_redistributable`` and, downstream, the public API. The spine is the
    external authority for "what counts as a real, known election" — the same reason
    :data:`~usvote.pv.source.MIT_PV_YEAR_MIN` is a constant rather than an observed
    ``min()``, applied to the top edge.

    Deriving it from ``ec_ingest_years()`` rather than from
    :data:`~usvote.years.LATEST_ELECTION_YEAR` directly is deliberate: if a year at the
    top end were ever gated back into ``UNSUPPORTED_EC_YEARS``, the frontier must fall
    back to the newest *supported* year, which is what "a year the spine knows about"
    means. This adds **no new thing to maintain** — the cycle bump already required by
    the spine, UCSB's ingest scope and the snapshot window moves this frontier too, so a
    stale constant fails all of them together rather than leaving one boundary behind.

    **What it still cannot see, stated rather than hidden:** a source dropping a year
    **at or beyond the frontier**. MIT losing 2024 is excluded by the same clause that
    lets a mid-refresh 2024 through — that is the exemption, not a hole in it — so this
    gate stays green. It takes one malformed CSV, nothing more. Nothing *below* the
    frontier is ever excluded, whatever else the source carries. The honest owner is a
    guard beside MIT's own invariants, not a second clause here: "did MIT lose a year it
    used to have?" is a single-source question, and answering it here would drag the
    circular data ceiling back into the module that just dropped it.

    **That owner now exists** (#177):
    :func:`usvote.mit.validate.assert_mit_year_coverage` refuses such a CSV at the MIT
    read seam, so on the shipped build path
    (:func:`usvote.warehouse.run_warehouse`, where it defaults on) the year no longer
    reaches the snapshot with a silently-null popular vote — the build fails instead.
    **Nothing about this gate changed**, and the exemption above is still exactly as
    stated: the guard sits upstream, is single-source, and is off by default at
    :func:`usvote.mit.pipeline.run_mit_pipeline` itself, so a caller driving that
    function directly with ``validate_coverage=False`` still reaches the limit described
    here.

    **Do not look for a second owner of the below-frontier case — MIT has none.** MIT's
    D024 roster/fact guard cannot see a wholly-missing MIT year, because
    :mod:`usvote.mit.pipeline` derives its in-scope years from the rows MIT actually
    loaded, so a year that vanished entirely is never compared against anything. **UCSB
    is different, and the difference is why this is a MIT-shaped problem**: it derives
    its scope from the spine (``ucsb_ingest_years()``) and
    :func:`usvote.ucsb.transform._scope_years` *raises* on any in-scope year with no
    parsed page, long before the warehouse is built. Gate 3 inner-joins on year and
    skips every one-sided year either way. So gates 1-2 are the only instrument pointed
    at a MIT coverage hole.

    **The window-level carve-out is separate, and stays narrow.** A source with no rows
    *at all* in the window skips outright — that is what a UCSB-less warehouse looks
    like from here (AC-3), and without it AC-3's "skipped, not failed" would hold only
    for callers routed through :func:`read_overlap_frames`. Neither carve-out ever
    excludes a *partial* year: a source that lost only some of a year's rows still
    scores them one-sided, so they count against both floors — which is what the
    per-year floor is for, since one year's loss can hide inside the overall rate.

    **The relative delta is** ``|MIT - UCSB| / max(UCSB, 1) * 100`` — **UCSB is the
    denominator** (D051, research §2). The measure is asymmetric, so this is part of the
    decision and not an implementation detail: read as ``/ MIT`` or ``/ mean``, the 1%
    and 15% lines are different lines. ``max(..., 1)`` mirrors the reference script's
    ``greatest(ucsb, 1)`` and keeps a hypothetical zero-vote cell finite.

    Both gate-2 comparisons are **strict** ``>``, matching research query 4's
    ``relpct > 1.0`` and query 2's tail counts, so a published list and a published
    count can never disagree about a cell sitting exactly on a line.
    """
    key = list(RESOLVED_KEY)
    mit = mit_df.loc[mit_df["year"] >= MIT_PV_YEAR_MIN]
    ucsb = ucsb_df.loc[ucsb_df["year"] >= MIT_PV_YEAR_MIN]
    if mit.empty or ucsb.empty:
        return OverlapReport(skipped=True, skip_reason=SKIP_NO_OVERLAP_CELLS)
    # Plain ints, so ``uncovered_years`` carries ints rather than numpy scalars.
    mit_years = {int(y) for y in mit["year"].unique()}
    ucsb_years = {int(y) for y in ucsb["year"].unique()}
    # A one-sided year is refresh only AT OR BEYOND the spine frontier; below it, it is
    # a regression and stays in the population -- see the docstring.
    frontier = max(ec_ingest_years()) if spine_max is None else spine_max
    one_sided_years = mit_years ^ ucsb_years
    uncovered = tuple(sorted(y for y in one_sided_years if y >= frontier))
    scored = (mit_years | ucsb_years) - set(uncovered)
    if not scored:
        # Every year either source carries sits at or beyond the frontier, so there is
        # genuinely nothing to compare -- a real skip, not a laundered failure. Unlike
        # the data-derived ceiling this replaces, the frontier does not move with the
        # data, so this state is reachable (two sources whose only years are the
        # frontier election and a beyond-spine year) rather than dead code -- and it is
        # what keeps an empty population from reading as a pass, since the rate would
        # otherwise be ``NaN`` and ``NaN < floor`` is ``False``. Below this line
        # ``merged`` cannot be empty: ``scored`` is non-empty and drawn from the two
        # year sets, so at least one frame survives its filter.
        return OverlapReport(
            skipped=True,
            skip_reason=SKIP_ALL_YEARS_AT_FRONTIER,
            uncovered_years=uncovered,
        )
    mit = mit.loc[mit["year"].isin(scored)]
    ucsb = ucsb.loc[ucsb["year"].isin(scored)]

    merged = mit[[*key, "party", "candidate_votes"]].merge(
        ucsb[[*key, "party", "candidate_votes"]],
        on=key,
        how="outer",
        suffixes=("_mit", "_ucsb"),
    )
    # MIT's party spelling, falling back to UCSB's on a MIT-less key -- display only.
    merged["party"] = merged["party_mit"].fillna(merged["party_ucsb"])
    both = (
        merged["candidate_votes_mit"].notna()
        & merged["candidate_votes_ucsb"].notna()
    )
    merged["exact"] = both & (
        merged["candidate_votes_mit"] == merged["candidate_votes_ucsb"]
    )

    paired = merged.loc[both].copy()
    paired["relpct"] = (
        (paired["candidate_votes_mit"] - paired["candidate_votes_ucsb"]).abs()
        / paired["candidate_votes_ucsb"].clip(lower=1)
        * 100
    )

    by_year = merged.groupby("year")["exact"].mean().mul(100)
    return OverlapReport(
        uncovered_years=uncovered,
        cells=len(merged),
        exact=int(merged["exact"].sum()),
        exact_pct=float(merged["exact"].mean() * 100),
        exact_pct_by_year={int(y): float(p) for y, p in by_year.items()},
        one_sided=_keys(merged.loc[~both]),
        flagged=_keys(paired.loc[paired["relpct"] > CELL_RELPCT_FLAG]),
        failed=_keys(paired.loc[paired["relpct"] > CELL_RELPCT_FAIL]),
    )


def assert_overlap_within_tolerance(
    report: OverlapReport, *, error_cls: type[Exception] = PVOverlapError
) -> None:
    """Raise when gate 1 or gate 2 is breached; a flagged cell is **not** a breach.

    Gate 1 fails when the overall exact-match rate is below
    :data:`EXACT_MATCH_FLOOR_OVERALL` **or** any single year is below
    :data:`EXACT_MATCH_FLOOR_PER_YEAR` — the two floors are separate instruments
    (D051), and a localized regression can pass the first while failing the second.
    Gate 2 fails when any cell's relative delta exceeds :data:`CELL_RELPCT_FAIL`.

    :attr:`OverlapReport.flagged` is the D005 reliability list, reported and never
    raised on; a ``skipped`` report asserts nothing at all (AC-3).

    The failure message names **keys only**, never deltas — the module docstring's
    licensing constraint applies to what this raises as much as to what it returns.
    """
    if report.skipped:
        return

    breaches: list[str] = []
    if report.exact_pct < EXACT_MATCH_FLOOR_OVERALL:
        # Name the one-sided count alongside the rate. A breach has two very different
        # causes -- cells that disagree, and cells one source stopped carrying -- and
        # the rate alone cannot tell them apart, so a reader would start in the wrong
        # place. This is the only path that surfaces ``one_sided`` in a *raised*
        # message; a green build reports it too, via ``WarehouseResult.overlap`` and
        # the CLI completion line.
        one_sided_note = (
            f"; {len(report.one_sided)} of them are carried by only one source"
            if report.one_sided
            else ""
        )
        breaches.append(
            f"gate 1 (overall): {report.exact_pct:.2f}% of {report.cells} overlap "
            f"cells agree exactly, below the {EXACT_MATCH_FLOOR_OVERALL}% floor"
            f"{one_sided_note}"
        )
    low_years = [
        f"{year} at {pct:.2f}%"
        for year, pct in sorted(report.exact_pct_by_year.items())
        if pct < EXACT_MATCH_FLOOR_PER_YEAR
    ]
    if low_years:
        breaches.append(
            f"gate 1 (per year): {', '.join(low_years)} — below the "
            f"{EXACT_MATCH_FLOOR_PER_YEAR}% floor"
        )
    if report.failed:
        breaches.append(
            f"gate 2: {len(report.failed)} cell(s) diverge by more than "
            f"{CELL_RELPCT_FAIL}% of the UCSB value: "
            f"{[(k.year, k.state, k.candidate) for k in report.failed]}"
        )
    if breaches:
        raise error_cls(
            "MIT/UCSB popular-vote overlap breached the D017 layer-3 tolerance "
            "(D051; see .claude/specs/research-pv-overlap.md §6): "
            + "; ".join(breaches)
        )


def read_overlap_frames(
    dbc: DBC, *, schema: str = PV_SCHEMA
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Read the two D017 single-source views for the window, or ``None`` to skip.

    **The one place the overlap read is expressed.** All three of the things it does are
    AC-pinned behaviour (#167), so :mod:`usvote.hybrid`'s gate 3 calls this rather than
    keeping a second copy that could drift from it:

    1. it reads ``pv_redistributable`` and ``pv_ucsb`` — **never** the raw
       ``pv_votes`` union, which would fan the overlap 2x (AC-2);
    2. it restricts both to ``year >= MIT_PV_YEAR_MIN``, the overlap window's floor,
       derived rather than re-spelled as ``1976``;
    3. it decides the **AC-3 skip**.

    **The skip probe is** ``pv_ucsb`` **emptiness, asked of the UNFILTERED view** — "is
    UCSB loaded at all?", a question about the source rather than about the window.
    A ``dwh.pv_source`` lookup cannot answer it: :data:`usvote.pv.source.PV_SOURCE_ROWS`
    seeds **both** source rows unconditionally, so that table says which sources are
    *known*, never which are *loaded*.

    **A limitation this probe has and does not guard:** it cannot distinguish "UCSB was
    never loaded" from "UCSB was loaded and produced zero rows". Failing loud on a
    zero-row parse is the UCSB pipeline's responsibility; this gate would simply skip.
    Stated rather than guarded — no check here covers it.

    Takes a :class:`~usvote.db.DBC` like every other live seam under ``usvote/pv/``
    (:mod:`usvote.pv.load` types all five of its write seams that way). ``usvote.db`` is
    the generic psycopg2 wrapper, not EC-domain knowledge, so importing it crosses none
    of the D015 boundaries — the enforced ones are ``dwh.votes`` and no back-import of
    ``usvote.warehouse``/``usvote.hybrid``, and this module trips neither.
    """
    select = dbc.select_query_to_df
    if select(f"SELECT 1 FROM {schema}.{PV_UCSB_VIEW} LIMIT 1").empty:
        return None
    window = f"WHERE year >= {MIT_PV_YEAR_MIN}"
    mit_df = select(f"SELECT * FROM {schema}.{PV_REDISTRIBUTABLE_VIEW} {window}")
    ucsb_df = select(f"SELECT * FROM {schema}.{PV_UCSB_VIEW} {window}")
    return mit_df, ucsb_df


def assert_db_overlap_within_tolerance(
    dbc: DBC, *, schema: str = PV_SCHEMA
) -> OverlapReport:
    """Live-DB form of gates 1 and 2 — read, measure, assert, return the report.

    The dual-expression pattern this package already uses
    (:func:`usvote.join.assert_db_pv_matches_ec` over
    :func:`usvote.join.assert_pv_matches_ec`): the measurement and the judgement are
    pure and unit-tested, and this adds only the read.

    Returns the :class:`OverlapReport` so a caller can surface
    :attr:`~OverlapReport.flagged` — the D005 reliability list — which is reported,
    never raised on. Returns a ``skipped`` report when UCSB is absent, raising nothing.
    """
    frames = read_overlap_frames(dbc, schema=schema)
    if frames is None:
        return OverlapReport(skipped=True, skip_reason=SKIP_UCSB_ABSENT)
    report = compute_overlap_report(*frames)
    assert_overlap_within_tolerance(report)
    return report
