"""Top-level MIT orchestration — read -> transform -> reconcile -> load.

The MIT analogue of :mod:`usvote.pipeline`'s :func:`run_ec_pipeline`, wiring the four
MIT stages into one runnable path. Each PV source owns its own pipeline (the EC
``pipeline.py`` docstring's design), so this lives under ``usvote/mit/`` and loads
through the shared, source-neutral :func:`usvote.pv.load.load_pv_records` seam.

Kept thin and injectable: ``path``/``environ`` drive the read the same way
:func:`usvote.mit.read.load_mit_president_csv` does (so a test replays a fixture CSV
offline), and ``years`` scopes the load to a subset of elections — the MIT analogue
of ``run_ec_pipeline``'s ``years`` — which the integration test uses to load only the
years the EC fixtures also cover (so the ``state`` FK resolves). Year filtering runs
on the raw frame *before* transform, keeping every ``(year, state)`` group whole, so
transform's pre-filter totals reconciliation still holds.

A user-facing ``python -m usvote.mit`` entry point is intentionally deferred; the
integration test drives :func:`run_mit_pipeline` directly.
"""

from __future__ import annotations

from collections.abc import Container, Mapping
from pathlib import Path

import pandas as pd

from usvote.db import DBC
from usvote.mit.read import load_mit_president_csv
from usvote.mit.reconcile import reconcile_mit
from usvote.mit.transform import transform_mit
from usvote.pv.load import load_pv_records


def run_mit_pipeline(
    dbc: DBC,
    path: str | Path | None = None,
    *,
    years: Container[int] | None = None,
    environ: Mapping[str, str] | None = None,
    replace: bool = False,
    close: bool = False,
) -> pd.DataFrame:
    """Run the end-to-end MIT PV ingestion and return the loaded frame.

    Reads the MIT ``1976-2024-president.csv`` (``path`` explicit, or resolved from
    ``USVOTE_MIT_CSV_PATH`` via ``environ`` when ``path`` is ``None``), optionally
    filters to ``years``, then transforms onto the D018 shared shape, reconciles
    ``state``/``candidate`` onto the canonical keys, and loads into ``dwh.pv_votes``
    via :func:`usvote.pv.load.load_pv_records`.

    ``years`` scopes the ingest to a subset of elections (e.g. ``{2016, 2020}`` to
    match the EC fixture years); ``None`` loads every year in the file. ``replace`` and
    ``close`` are forwarded to the loader — ``replace=True`` rebuilds ``dwh.pv_votes``
    only (never the schema; the EC spine survives). Returns the loaded frame (with
    ``pv_id``) for inspection/validation.
    """
    raw = load_mit_president_csv(path, environ=environ)
    if years is not None:
        raw = raw.loc[raw["year"].isin(years)].copy()

    shaped = transform_mit(raw)
    reconciled = reconcile_mit(shaped)
    return load_pv_records(dbc, reconciled, replace=replace, close=close)
