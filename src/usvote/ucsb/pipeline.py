"""Top-level UCSB orchestration — snapshot -> parse -> transform -> reconcile -> load.

The UCSB analogue of :func:`usvote.mit.pipeline.run_mit_pipeline`, wiring the merged
stage stories (#35 parse, #36 transform, #38 reconcile) into one runnable path and
loading through the shared, source-neutral :mod:`usvote.pv.load` seam. Each PV source
owns its own pipeline (the EC ``pipeline.py`` docstring's design), so this lives under
``usvote/ucsb/``.

**``__main__`` means *snapshot*, not *run this pipeline*.** Unlike the EC spine —
where ``python -m usvote`` runs the whole pipeline — ``python -m usvote.ucsb`` runs
:func:`usvote.ucsb.scrape.snapshot_elections` (the D023 reproducible network refresh).
This module is driven directly (like ``run_mit_pipeline``, whose ``__main__`` entry
point is likewise deferred); the integration test is its caller. The asymmetry is
principled: MIT reads a local CSV and has no network stage to snapshot, so only UCSB
carries a snapshot command.

**Two tables, one ``replace``, and a non-atomic gap.** A UCSB run loads *both* shared
PV tables — the ``dwh.pv_votes`` fact and the ``dwh.pv_state_status`` roster — the two
frames :func:`usvote.ucsb.transform.transform_ucsb` emits. One ``replace`` flag drives
both loads (never two knobs). The roster loads **first**: its ``state`` FK targets
``dwh.state`` (tautologically safe once the EC spine is loaded), and the surviving
partial state after an interrupted run — a roster with no facts — is *obviously*
incomplete, whereas facts-with-no-roster is indistinguishable from a valid MIT-shaped
load. The two writes are **not** one transaction (``DBC`` commits per statement), so a
crash between them can leave the D024 two-way invariant broken in the database, where
no ``assert_roster_covers_facts`` runs. That is an accepted limitation of this story;
follow-up #84 adds ``DBC.transaction()`` and wraps both loads. The likeliest symptom of
a re-run over already-loaded data is a unique-constraint violation on the second table
after the first committed — the intended non-destructive guard, not silent corruption.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

import pandas as pd

from usvote.db import DBC
from usvote.pv.load import load_pv_records, load_pv_status
from usvote.spine import read_ec_getters, read_ec_participation
from usvote.ucsb.parse import parse_election_years
from usvote.ucsb.reconcile import reconcile_ucsb
from usvote.ucsb.scrape import read_snapshot_html
from usvote.ucsb.transform import transform_ucsb, ucsb_ingest_years


def run_ucsb_pipeline(
    dbc: DBC,
    html_dir: str | Path | None = None,
    *,
    years: Collection[int] | None = None,
    environ: Mapping[str, str] | None = None,
    replace: bool = False,
    close: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the end-to-end UCSB PV ingestion and return the loaded frames.

    Reads the saved snapshot (``html_dir`` explicit, or resolved from
    ``USVOTE_UCSB_HTML_DIR`` via ``environ`` when ``None``), parses each page, derives
    the roster from the EC ``votes`` participation frame, transforms onto the D018
    shared shape + D024 roster, reconciles ``candidate`` onto the canonical keys against
    the EC president-EV getters, and loads both into ``dwh`` alongside (never
    overwriting) the EC spine and MIT data.

    ``years`` scopes every stage to a subset of elections (e.g. ``{2016, 2020}`` to
    match the EC fixture years); it is resolved **once** here — defaulting to
    :func:`~usvote.ucsb.transform.ucsb_ingest_years` — and threaded to the snapshot
    read, transform, reconcile, and both spine reads, so a partial run never reports
    unprocessed years as violations and the roster/getter guards see the same year set.

    ``replace`` gates the table-level rebuild of **both** PV tables (never the schema;
    the EC spine survives); it drives one flag to both loads. ``close`` closes the
    connection after the last load — the pipeline owns it, so it is not threaded into
    the individual loaders.

    Returns ``(pv_votes, roster)`` — the reconciled fact frame (as inserted, without
    ``pv_id``) and the roster frame (as inserted, without ``status_id``). Raises the
    UCSB stage errors (:class:`~usvote.ucsb.transform.UCSBTransformError` and
    subclasses) on any validation failure, or
    :class:`~usvote.ucsb.scrape.UCSBScrapeError` on a structurally broken snapshot.
    """
    in_scope = frozenset(ucsb_ingest_years() if years is None else years)

    html_by_year = read_snapshot_html(html_dir, years=in_scope, environ=environ)
    parsed_years = parse_election_years(html_by_year)

    ec_participation = read_ec_participation(dbc, years=in_scope)
    pv_votes, roster = transform_ucsb(parsed_years, ec_participation, years=in_scope)

    ec_getters = read_ec_getters(dbc, years=in_scope)
    reconciled = reconcile_ucsb(pv_votes, roster, ec_getters, years=in_scope)

    # Roster first: its state FK is safe the moment the EC spine is loaded, and a
    # roster-without-facts is obviously incomplete if the run dies between the two
    # writes. Both loads share the single ``replace`` flag; ``close`` fires only on the
    # last one (the pipeline, not a loader, owns the connection lifetime).
    loaded_roster = load_pv_status(dbc, roster, replace=replace)
    loaded_pv = load_pv_records(dbc, reconciled, replace=replace, close=close)
    return loaded_pv, loaded_roster
