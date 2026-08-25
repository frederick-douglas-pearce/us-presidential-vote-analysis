"""Top-level MIT orchestration — read -> transform -> reconcile -> load.

The MIT analogue of :mod:`usvote.pipeline`'s :func:`run_ec_pipeline`, wiring the four
MIT stages into one runnable path. Each PV source owns its own pipeline (the EC
``pipeline.py`` docstring's design), so this lives under ``usvote/mit/`` and loads
through the shared, source-neutral :mod:`usvote.pv.load` seams — both of them: the
``pv_votes`` fact (:func:`~usvote.pv.load.load_pv_records`) and, since #127, the D024
``pv_state_status`` roster (:func:`~usvote.pv.load.load_pv_status`), written together in
one transaction exactly as UCSB writes its pair.

Kept thin and injectable: ``path``/``environ`` drive the read the same way
:func:`usvote.mit.read.load_mit_president_csv` does (so a test replays a fixture CSV
offline), and ``years`` scopes the load to a subset of elections — the MIT analogue
of ``run_ec_pipeline``'s ``years`` — which the integration test uses to load only the
years the EC fixtures also cover (so the ``state`` FK resolves). Year filtering runs
on the raw frame *before* transform, keeping every ``(year, state)`` group whole, so
transform's pre-filter totals reconciliation still holds.

``python -m usvote.mit load`` (bare ``python -m usvote.mit`` — ``load`` is the default
subcommand) runs this via :mod:`usvote.mit.__main__` (#84b); the whole-warehouse build
(:func:`usvote.warehouse.run_warehouse`) also calls it. There is no ``snapshot``
subcommand — MIT reads a local CSV, so unlike UCSB it has no network stage to reproduce.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

import pandas as pd

from usvote.db import DBC
from usvote.mit.read import load_mit_president_csv
from usvote.mit.reconcile import reconcile_mit
from usvote.mit.transform import MITTransformError, transform_mit
from usvote.pv.load import load_pv_records, load_pv_status
from usvote.pv.source import SOURCE_MIT
from usvote.pv.status import assert_roster_covers_facts, build_popular_vote_roster
from usvote.spine import read_ec_participation


class MITRosterError(MITTransformError):
    """Raised when MIT's roster and its loaded facts disagree (D024 §7).

    MIT's typed wrapper around :class:`usvote.pv.status.PVRosterError`, mirroring the
    UCSB stage errors so a roster failure is separable by type, not only by message.
    """


def run_mit_pipeline(
    dbc: DBC,
    path: str | Path | None = None,
    *,
    years: Collection[int] | None = None,
    environ: Mapping[str, str] | None = None,
    replace: bool = False,
    close: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the end-to-end MIT PV ingestion and return the loaded frames.

    Reads the MIT ``1976-2024-president.csv`` (``path`` explicit, or resolved from
    ``USVOTE_MIT_CSV_PATH`` via ``environ`` when ``path`` is ``None``), optionally
    filters to ``years``, then transforms onto the D018 shared shape, reconciles
    ``state``/``candidate`` onto the canonical keys, and loads **both** shared PV tables
    — the ``dwh.pv_votes`` fact via :func:`usvote.pv.load.load_pv_records` and the D024
    ``dwh.pv_state_status`` roster via :func:`usvote.pv.load.load_pv_status`.

    **The roster load is #127's backfill, and it is mechanical.** MIT covers 1976–2024,
    where every state held a popular vote, so the roster is a ``SELECT DISTINCT`` over
    the **EC spine's** participating ``(year, state)`` keys tagged ``popular_vote``
    (:func:`usvote.pv.status.build_popular_vote_roster`) — none of UCSB's absence
    derivation, exactly as D024 §Rationale anticipated. Without it the roster held *no*
    MIT rows at all, so :func:`usvote.hybrid.build_hybrid_from_db` — which scopes its
    roster read to the sources present in the surface it is computing — read an empty
    roster on the MIT-only ``ec_pv_redistributable`` view and reported ``pv_coverage``
    NULL ("unknown") for 1976–2024, the years whose true EV-weighted coverage is a clean
    ``1.0``.

    **Why the spine and not MIT's own facts.** D024's clarification names ``dwh.votes``
    (totals rows excluded) as the roster input for *both* PV sources, and the reason is
    the guard: a roster built from the frame it is then checked against is a tautology,
    so a ``(year, state)`` dropped during transform would vanish from both sides and the
    year would quietly report ``pv_coverage`` below ``1.0``. Derived from the spine,
    that same drop is a ``popular_vote`` state with no vote rows and fails loudly. And
    else covers it — #69's join-side guard is a PV→EC anti-join, the opposite direction.
    This costs MIT one spine read; it is the only DB read before the load.

    ``years`` scopes the ingest to a subset of elections (e.g. ``{2016, 2020}`` to
    match the EC fixture years); ``None`` loads every year in the file. It is a
    **filter, not a demand** — a requested year the CSV does not cover is simply absent,
    which is why the D024 assert's in-scope set is taken from the loaded frame rather
    than from ``years`` (see the comment at the call site). ``replace`` gates the
    **table**-level rebuild of both PV tables with one flag (never the schema; the EC
    spine survives), matching
    :func:`usvote.ucsb.pipeline.run_ucsb_pipeline`. Returns ``(pv_votes, roster)`` as
    inserted, for inspection/validation.
    """
    raw = load_mit_president_csv(path, environ=environ)
    if years is not None:
        matched = raw["year"].isin(years)
        if not matched.any():
            # Only materialize the diagnostic on the error path. .tolist() converts the
            # numpy scalars to native ints so the message renders as [2000, 2016].
            available = sorted(raw["year"].unique().tolist())
            raise ValueError(
                f"run_mit_pipeline: no MIT rows for requested years {sorted(years)}; "
                f"the file covers {available}."
            )
        raw = raw.loc[matched].copy()

    shaped = transform_mit(raw)
    reconciled = reconcile_mit(shaped)

    # In-scope years come from the frame MIT actually loaded, NOT from ``years``.
    # ``years`` is documented as a *filter* ("scopes the ingest to a subset"), not a
    # demand that every requested year exist: run_warehouse threads one year set to
    # every source, and the MIT CSV legitimately covers a different span than the EC
    # spine (tests/integration/test_ec_pv_join.py relies on exactly that — years=
    # {2016, 2020} against a sample holding no 2020). Asserting over the requested set
    # would turn that documented filter into a failure.
    in_scope = frozenset(reconciled["year"].unique().tolist())
    # The roster derives from the EC spine, NOT from ``reconciled`` — that independence
    # is what makes the assert below a real silent-drop guard rather than a frame
    # compared against itself (D024 §7; see build_popular_vote_roster). Read outside the
    # transaction, like every other pipeline's spine reads.
    ec_participation = read_ec_participation(dbc, years=in_scope)
    roster = build_popular_vote_roster(
        ec_participation, source=SOURCE_MIT, years=in_scope, error_cls=MITRosterError
    )
    assert_roster_covers_facts(
        reconciled,
        roster,
        source=SOURCE_MIT,
        years=in_scope,
        error_cls=MITRosterError,
    )

    # Both writes in ONE transaction, matching run_ucsb_pipeline (#84a): every pipeline
    # owns its DB-write transaction so the #84b orchestrator can sequence them without
    # ever nesting one, and the D024 two-way roster/fact invariant can never be left
    # half-written in the database. The fact load also does create-schema +
    # create-table + insert, so the transaction makes those all-or-nothing too. The
    # roster loads first (its ``state`` FK targets ``dwh.state``, safe once the EC spine
    # is loaded) — a readability choice mirroring UCSB, not a blast-radius guard, now
    # that the pair commits together. ``close`` fires after the commit.
    with dbc.transaction():
        loaded_roster = load_pv_status(dbc, roster, replace=replace)
        loaded = load_pv_records(dbc, reconciled, replace=replace)
    if close:
        dbc.close_connection()
    return loaded, loaded_roster
