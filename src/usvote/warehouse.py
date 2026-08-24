"""Whole-warehouse composition root — build the entire ``dwh`` from every source.

:func:`run_warehouse` sequences the four source/join steps into one runnable build:
the EC spine (:func:`usvote.pipeline.run_ec_pipeline`), the MIT PV source
(:func:`usvote.mit.pipeline.run_mit_pipeline`), optionally the UCSB PV source
(:func:`usvote.ucsb.pipeline.run_ucsb_pipeline`), then the resolved-PV, EC<->PV join
and hybrid views (:func:`rebuild_views`). It is the programmatic entry point behind
``python -m usvote all`` (#84b).

**This is a composition root, not part of the EC spine.** It lives at the top level
alongside the source-namespaced ``usvote/`` modules, but unlike them it imports *from*
every source (EC + both PV subpackages) to wire them together. That is allowed for the
same reason :mod:`usvote.__main__` is: a composition root sits **above** both EC and
PV, so it is exempt from the D015 source-to-source prohibition exactly as ``__main__``
is (D027). The invariant that keeps the exemption honest is the reverse one — nothing
under ``usvote/{mit,ucsb,pv}/`` may import :mod:`usvote.warehouse` (a back-import would
invert D015 into a cycle); a unit test enforces it.

**Transactions: per-source atomic, not globally atomic (#84a).** ``run_warehouse`` opens
**no** transaction of its own. Each pipeline it calls already wraps its own DB writes in
``with dbc.transaction():`` (the #84a uniform-ownership rule), and
:meth:`DBC.transaction` raises on a nested open, so wrapping the sequence here would be
a bug. The consequence is deliberate: a mid-build failure leaves the already-committed
sources in place and the later ones absent. Recovery is **not** a bare re-run — the
PV/EC loaders are create-if-absent/append, so a bare re-run raises a unique-constraint
violation on the first already-loaded source before it reaches the missing one. The
honest recovery path is ``run_warehouse(..., replace=True)`` (a clean full rebuild).
Scrape/network stays outside every transaction (each pipeline already keeps it out), so
no build holds a transaction open across HTTP.

**``replace`` maps EC-destructive, PV-additive.** ``replace=True`` forwards to
``run_ec_pipeline(replace=True)``, which drops and recreates the ``dwh`` schema — and
because the PV tables and all views live in ``dwh``, that ``DROP SCHEMA ... CASCADE``
takes them with it. So the PV loads run with ``replace=False`` (append onto the *fresh*
schema, the only sane mapping and exactly the integration-test order), and the views are
**always rebuilt** as the final step — without that rebuild a ``replace=True`` build
would leave a warehouse with the fact tables but no ``ec_pv_preferred`` /
``ec_pv_redistributable`` for E7/E8 to read, and since #124 no ``hybrid_*`` views
either.

**UCSB is gated explicitly, never by environment magic.** ``ucsb_html_dir=None`` (the
default) **skips** UCSB — this function does not consult ``USVOTE_UCSB_HTML_DIR``
itself; the caller decides and passes a directory to include it. This keeps the
D024/D017 principle — missing data is modeled explicitly, never silent — at the
programmatic seam: the returned :class:`WarehouseResult` names exactly which sources
loaded, so a downstream E7 hybrid step can refuse to compute over a warehouse that
silently lacks the UCSB consistency control, and E8 can assert it only ever built over
redistributable data. The ``python -m usvote all`` CLI may auto-detect the snapshot dir,
but only *loudly* (see :mod:`usvote.__main__`). The alignment worth stating: **EC + MIT
are the redistributable public core; UCSB is the analysis-only control** (the D016
split) — so "a fresh public clone builds EC + MIT, UCSB needs the private snapshot" is
not an arbitrary subset.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from usvote.db import DBC
from usvote.hybrid import assert_db_margin_agreement, create_hybrid_views
from usvote.join import create_ec_pv_views
from usvote.mit.pipeline import run_mit_pipeline
from usvote.pipeline import run_ec_pipeline
from usvote.pv.load import build_pv_union
from usvote.pv.overlap import OverlapReport, assert_db_overlap_within_tolerance
from usvote.scrape import Fetch, fetch_url
from usvote.transform import load_state_geo
from usvote.ucsb.pipeline import run_ucsb_pipeline

#: The source keys a full build loads, in dependency order (EC spine first).
SOURCE_EC = "ec"
SOURCE_MIT = "mit"
SOURCE_UCSB = "ucsb"


@dataclass(frozen=True, kw_only=True)
class WarehouseResult:
    """What a :func:`run_warehouse` build loaded — the structured build receipt.

    ``sources_loaded`` names which of ``{"ec", "mit", "ucsb"}`` were ingested (UCSB is
    absent when ``ucsb_html_dir`` was ``None``). The ``*_rows`` counts are the loaded
    frame lengths; both PV sources now report a fact **and** a roster count, since #127
    gave MIT its D024 ``pv_state_status`` rows too. The two UCSB counts are ``None``
    exactly when UCSB was skipped.
    ``views_built`` records that the resolved-PV, join and hybrid views were
    (re)created — always ``True`` on a successful build, surfaced so a caller need not
    re-probe.

    Kept intentionally minimal: E7/E8 read the persistent views, so "is UCSB present?"
    is a query against ``dwh.pv_source`` / the ``pv_ucsb`` view at analysis time, not an
    in-process field to thread. This receipt answers "what did *this* build do", nothing
    speculative.

    **Keyword-only.** This is the documented programmatic seam downstream E7/E8 callers
    read, and #127 had to insert ``mit_roster_rows`` *between* existing fields to keep
    the per-source pairs together — which silently re-binds every positional
    construction. ``kw_only`` makes any future field addition a non-event instead of a
    shifted-receipt hazard for a caller outside the type-checked set.
    """

    ec_rows: int
    mit_rows: int
    mit_roster_rows: int
    ucsb_pv_rows: int | None
    ucsb_roster_rows: int | None
    sources_loaded: frozenset[str]
    views_built: bool
    #: What the D017 layer-3 cell-grain gates measured (#167) — including gate 2's D005
    #: reliability list in :attr:`~usvote.pv.overlap.OverlapReport.flagged` and the
    #: one-sided cells in ``one_sided``, both as keys carrying **no** magnitudes (the
    #: D030/D022 constraint; see :mod:`usvote.pv.overlap`).
    #:
    #: The whole report rather than just the flag list, because the two things a reader
    #: needs after a green build are *what was flagged* and *what neither floor saw* —
    #: a source can stop carrying ~130 cells and still clear both floors, and only
    #: ``one_sided`` says so.
    #:
    #: ``None`` when the gates did not run at all (``validate_overlap=False``); a
    #: ``skipped`` report when they ran and found nothing to measure (UCSB absent, or
    #: no covered year). Both differ from a populated report with empty lists, which
    #: means "ran, found none". Flagged keys are reported, never a build failure.
    overlap: OverlapReport | None = None


def rebuild_views(dbc: DBC) -> None:
    """(Re)build the resolved-PV, EC<->PV join and hybrid views over current facts.

    **The one place the view ordering is expressed** — ``pv union -> join -> hybrid`` —
    and the ordering is a dependency chain, not a preference:

    1. :func:`usvote.pv.load.build_pv_union` seeds ``dwh.pv_source`` and creates the
       three resolved series (``pv_preferred`` / ``pv_redistributable`` / ``pv_ucsb``).
    2. :func:`usvote.join.create_ec_pv_views` runs its reciprocal anti-join precondition
       and creates ``ec_pv_preferred`` / ``ec_pv_redistributable`` over them.
    3. :func:`usvote.hybrid.create_hybrid_views` (#124) runs the hybrid preconditions
       and creates ``hybrid_preferred`` / ``hybrid_redistributable`` plus their
       ``hybrid_summary_*`` companions over *those*.

    All three are idempotent (``CREATE OR REPLACE VIEW``) and open no transaction of
    their own, so this is safe to call after any PV load and never nests over a
    pipeline's transaction (#84a).

    Because :func:`run_warehouse` always calls this last, a ``replace=True`` build —
    whose ``DROP SCHEMA dwh CASCADE`` takes every view with it — rebuilds the hybrid
    views too, with no extra wiring. That is what leaves E7's analysis surface and
    #102's read seam (D039) populated after a full rebuild.

    **The D017 layer-3 overlap gates (#167) are deliberately NOT here**, and the reason
    is this function's own contract: it makes the views consistent with *whatever facts
    are present*, which is why it is factored out for a future ``views`` subcommand at
    all. Cross-source agreement is a statement about a **complete** build, so it lives
    in :func:`run_warehouse` behind an explicit ``validate_overlap`` flag.

    Factored out of :func:`run_warehouse` so a future ``views`` subcommand — rebuild
    the views without re-scraping the sources — is a thin wrapper over this, not a
    restructuring of the orchestrator (#84 follow-up).
    """
    build_pv_union(dbc)
    create_ec_pv_views(dbc)
    create_hybrid_views(dbc)


def run_warehouse(
    dbc: DBC,
    shapefile_path: str,
    mit_csv_path: str | Path | None = None,
    *,
    ucsb_html_dir: str | Path | None = None,
    years: Collection[int] | None = None,
    replace: bool = False,
    validate_overlap: bool = True,
    environ: Mapping[str, str] | None = None,
    fetch: Fetch = fetch_url,
    load_geo: Callable[[str], pd.DataFrame] = load_state_geo,
    close: bool = False,
) -> WarehouseResult:
    """Build the whole ``dwh`` warehouse from every source and return a build receipt.

    Sequences EC -> MIT -> (optional) UCSB -> views on a single ``dbc``:

    1. :func:`usvote.pipeline.run_ec_pipeline` — the EC spine. ``replace`` is
       forwarded here (and here only): ``replace=True`` drops and recreates the ``dwh``
       schema, which cascades away the PV tables and views, so everything downstream
       rebuilds onto a fresh schema.
    2. :func:`usvote.mit.pipeline.run_mit_pipeline` — the MIT PV source (both its
       ``pv_votes`` facts and, since #127, its ``pv_state_status`` roster rows), always
       ``replace=False`` (append onto the schema EC just built). ``mit_csv_path=None``
       resolves ``USVOTE_MIT_CSV_PATH`` via ``environ`` inside the MIT pipeline.
    3. :func:`usvote.ucsb.pipeline.run_ucsb_pipeline` — the UCSB PV source, only when
       ``ucsb_html_dir`` is not ``None`` (else UCSB is skipped, explicitly — no env
       magic). Also ``replace=False``.
    4. :func:`rebuild_views` — the resolved-PV, EC<->PV join and hybrid views, always
       rebuilt.
    5. the **D017 layer-3 overlap gates** (#167, D051), when ``validate_overlap`` — MIT
       vs. UCSB agreement at the cell grain
       (:func:`usvote.pv.overlap.assert_db_overlap_within_tolerance`) and at the
       national margin grain (:func:`usvote.hybrid.assert_db_margin_agreement`).

    ``years`` scopes every source to the same subset of elections (e.g. ``{2016, 2020}``
    to match the fixtures); ``None`` loads each source's full range. ``environ`` is
    threaded to the two PV pipelines' config resolution (EC takes ``shapefile_path``
    directly). ``fetch`` and ``load_geo`` are the EC stage's offline-injection seams,
    forwarded to :func:`~usvote.pipeline.run_ec_pipeline` untouched (defaults are live
    HTTP + the real shapefile); they let the integration test drive *this* shipped path
    over saved fixtures instead of a hand-wired parallel copy. ``close`` closes ``dbc``
    when the build finishes — on success *after* the views are built, and also if a
    pipeline raises mid-build (in a ``finally``), so a caller passing ``close=True``
    never leaks the connection on a partial build. The orchestrator owns the connection
    across the whole build, so the individual pipelines are called with their default
    ``close=False``.

    ``validate_overlap`` gates step 5 **explicitly, in the same spirit as**
    ``ucsb_html_dir`` — no environment magic, and the default is on, so the shipped
    ``python -m usvote all`` always validates. Two things make the flag necessary rather
    than convenient:

    - **They run after every view exists, because they are the only raising step whose
      threshold is expected to move.** They are not the only step that can raise —
      :func:`usvote.join.create_ec_pv_views` and
      :func:`usvote.hybrid.create_hybrid_views` run raising preconditions of their own —
      but those assert structural facts (a PV row matching no EC row, a dead-heat
      winner), which a rebuild does not change and nobody retunes. D051 says outright of
      gate 1's per-year floor: "expect this to be the first threshold to need review". A
      breach of a *movable* threshold between the builders would leave a warehouse with
      facts but no join/hybrid views, whose only documented recovery — ``replace=True``
      — rebuilds and re-hits the same breach. Running last means a breach reports over a
      complete warehouse instead.
    - **They measure a population, so they are meaningful only on a complete build.** A
      build whose sources are deliberately partial — a state-scoped MIT extract against
      a full UCSB corpus, as ``tests/integration/test_ec_pv_join.py::
      test_join_over_a_real_two_source_load`` does — yields few paired cells, and an
      agreement *rate* over a handful of cells says nothing about either source. That
      one test is the only ``validate_overlap=False`` caller in the tree. A UCSB-less
      build needs nothing, since both gates skip on their own (AC-3).

    Opens no transaction itself; see the module docstring for the per-source-atomic
    model and why a failed build is recovered with ``replace=True``, not a bare re-run.
    """
    try:
        candidates_df, state_df, votes_df = run_ec_pipeline(
            dbc,
            shapefile_path,
            replace=replace,
            years=years,
            fetch=fetch,
            load_geo=load_geo,
        )
        ec_rows = len(votes_df)

        mit_loaded, mit_roster = run_mit_pipeline(
            dbc, mit_csv_path, years=years, environ=environ, replace=False
        )
        mit_rows = len(mit_loaded)
        mit_roster_rows = len(mit_roster)

        sources = {SOURCE_EC, SOURCE_MIT}
        ucsb_pv_rows: int | None = None
        ucsb_roster_rows: int | None = None
        if ucsb_html_dir is not None:
            pv_votes, roster = run_ucsb_pipeline(
                dbc, ucsb_html_dir, years=years, environ=environ, replace=False
            )
            ucsb_pv_rows = len(pv_votes)
            ucsb_roster_rows = len(roster)
            sources.add(SOURCE_UCSB)

        rebuild_views(dbc)

        # The D017 layer-3 gates, last -- after every view exists, and only on a build
        # the caller vouches is complete. Both skip on their own when UCSB is absent.
        overlap: OverlapReport | None = None
        if validate_overlap:
            overlap = assert_db_overlap_within_tolerance(dbc)
            assert_db_margin_agreement(dbc)

        return WarehouseResult(
            ec_rows=ec_rows,
            mit_rows=mit_rows,
            mit_roster_rows=mit_roster_rows,
            ucsb_pv_rows=ucsb_pv_rows,
            ucsb_roster_rows=ucsb_roster_rows,
            sources_loaded=frozenset(sources),
            views_built=True,
            overlap=overlap,
        )
    finally:
        # Close on either exit — success after the views, or a mid-build failure — so a
        # ``close=True`` caller never leaks the connection on a partial build. Each
        # source's commit/rollback is already owned by that pipeline's transaction
        # (#84a); closing here only releases the connection, not affecting atomicity.
        if close:
            dbc.close_connection()
