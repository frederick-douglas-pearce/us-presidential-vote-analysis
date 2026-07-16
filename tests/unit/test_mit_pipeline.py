"""Unit tests for the MIT pipeline wiring (``usvote.mit.pipeline``).

Drives read -> transform -> reconcile -> load over the offline fusion fixture against
the recording fake connection (no live Postgres), asserting the four stages compose:
the raw CSV becomes reconciled, canonical-key PV rows loaded into ``dwh.pv_votes``,
correctly scoped by ``years`` and stamped with MIT provenance. The load into a real
database lives in ``tests/integration/test_pv_load.py``.
"""

from __future__ import annotations

import pytest

from tests._helpers import (
    MIT_FUSION_SAMPLE_CSV,
    RecordingConnection,
    make_dbc,
    record_inserts,
)
from usvote.mit.pipeline import run_mit_pipeline
from usvote.pv.schema import PV_SCHEMA, PV_TABLE, SHARED_PV_COLUMNS


def test_pipeline_scopes_to_years_and_reconciles(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    # Scoped to 2016 → the fusion fixture's New York rows only. After the D019
    # {DEMOCRAT, REPUBLICAN} scope + fusion aggregation that is exactly Clinton and
    # Trump, reconciled onto the canonical EC names.
    loaded = run_mit_pipeline(
        make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016}
    )

    assert loaded["year"].unique().tolist() == [2016]
    assert set(loaded["candidate"]) == {"Hillary Clinton", "Donald J. Trump"}
    assert set(loaded["state"]) == {"New York"}
    # Provenance stamped; every row exact (MIT).
    assert set(loaded["source"]) == {"MIT"}
    assert set(loaded["reliability"]) == {"exact"}
    # Clinton's fusion lines summed into her main total (4379789 + 140041 + 36294).
    clinton = loaded.loc[loaded["candidate"] == "Hillary Clinton", "candidate_votes"]
    assert clinton.iloc[0] == 4556124


def test_pipeline_creates_pv_table_and_inserts(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = record_inserts(monkeypatch)
    run_mit_pipeline(make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016})

    assert any(
        q.startswith(f"CREATE TABLE IF NOT EXISTS {PV_SCHEMA}.{PV_TABLE}")
        for q in recording_conn.executed
    )
    assert [sql.split()[2] for sql, _ in inserts] == [f"{PV_SCHEMA}.{PV_TABLE}"]


def test_pipeline_without_year_filter_loads_all_years(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    loaded = run_mit_pipeline(make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV)

    # The fixture covers 2000 FL (Bush, Gore) + 2016 NY (Clinton, Trump) — four D/R
    # rows after scoping, spanning both years.
    assert set(loaded["year"]) == {2000, 2016}
    assert list(loaded.columns) == ["pv_id", *SHARED_PV_COLUMNS]
    assert loaded["pv_id"].tolist() == [1, 2, 3, 4]
