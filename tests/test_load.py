"""Unit + integration tests for ``usvote.load``.

Two layers, mirroring ``test_db``:

- **Crafted units** over the SQL the load stage emits — the column definitions
  (FK ``REFERENCES`` embed the schema), the create/insert order (state ->
  candidate -> votes), and the ``replace`` guard (no ``DROP`` unless opted in) —
  all against the recording fake connection, no live Postgres.
- **One integration test** (``@pytest.mark.integration``, excluded by default)
  driving the *full pipeline* over the 2016 + 2020 Archives fixtures into a real
  Postgres and asserting row counts + grain (PK uniqueness, FK containment). It
  lives here rather than in ``test_pipeline`` because the load into a real
  database is what it verifies; see ``run_ec_pipeline`` for the wiring.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import usvote.db as db_module
from usvote.db import DBC
from usvote.load import SCHEMA, TABLE_NAMES, build_table_column_defs, load_dataframes

from .conftest import RecordingConnection, fake_state_geo

FIXTURES = Path(__file__).parent / "fixtures"


def make_dbc(conn: RecordingConnection) -> DBC:
    """Build a DBC wired to the fake connection instead of a real Postgres."""
    return DBC({"dbname": "test"}, connect=lambda **_: conn)


def _record_inserts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Patch ``execute_values`` to capture (sql, argslist); returns the log.

    ``insert_df_into_table`` routes through the module-level ``execute_values``
    rather than ``cursor.execute``, so the recording cursor never sees the INSERTs
    — patch at the ``usvote.db`` lookup site to record them (test_db.py pattern).
    """
    calls: list[tuple[str, Any]] = []

    def fake_execute_values(cur: object, sql: str, argslist: Any, **_: object) -> None:
        calls.append((sql, argslist))

    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)
    return calls


# --- column definitions ----------------------------------------------------


def test_column_defs_embed_schema_in_fk_references() -> None:
    state, candidate, votes = (dict(zip(TABLE_NAMES, build_table_column_defs("mart")))[t]
                               for t in TABLE_NAMES)

    # The state dimension is a pure dimension: no FK.
    assert not any("REFERENCES" in c for col in state for c in col)
    # candidate.state / state_2 reference the schema's state table.
    fk_cols = {col[0]: col[-1] for col in candidate if "REFERENCES" in col[-1]}
    assert fk_cols["state"] == "REFERENCES mart.state"
    assert fk_cols["state_2"] == "REFERENCES mart.state"
    # votes references both dimensions in the same schema.
    votes_fks = [c for col in votes for c in col if "REFERENCES" in c]
    assert "REFERENCES mart.state" in votes_fks
    assert "REFERENCES mart.candidate" in votes_fks


def test_column_defs_default_to_dwh_schema() -> None:
    defs = dict(zip(TABLE_NAMES, build_table_column_defs()))
    refs = [c for col in defs["votes"] for c in col if "REFERENCES" in c]
    assert refs == [f"REFERENCES {SCHEMA}.state", f"REFERENCES {SCHEMA}.candidate"]


# --- load_dataframes: order + inserts --------------------------------------


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "state_df": pd.DataFrame({"state": ["Ohio"]}),
        "candidates_df": pd.DataFrame({"candidate_id": [1], "name": ["X"]}),
        "votes_df": pd.DataFrame({"votes_id": [1], "candidate_id": [1]}),
    }


def test_load_creates_and_inserts_in_fk_order(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = _record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), **_frames())

    creates = [q for q in recording_conn.executed if q.startswith("CREATE TABLE")]
    # state -> candidate -> votes, the FK-dependency order.
    assert [f"{SCHEMA}.state", f"{SCHEMA}.candidate", f"{SCHEMA}.votes"] == [
        q.split()[5] for q in creates
    ]
    # One insert per table, in the same order.
    assert [sql.split()[2] for sql, _ in inserts] == [
        f"{SCHEMA}.state",
        f"{SCHEMA}.candidate",
        f"{SCHEMA}.votes",
    ]


def test_load_non_destructive_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), **_frames())

    # The guard: no DROP of any kind unless replace=True is passed explicitly.
    assert not any("DROP" in q for q in recording_conn.executed)
    assert any(q.startswith("CREATE SCHEMA IF NOT EXISTS") for q in recording_conn.executed)


def test_load_replace_drops_schema_cascade(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), replace=True, **_frames())

    drops = [q for q in recording_conn.executed if q.startswith("DROP")]
    # Exactly one drop — the schema-level cascade — and no per-table drops (the
    # schema drop already removed the tables).
    assert drops == [f"DROP SCHEMA IF EXISTS {SCHEMA} Cascade"]


def test_load_close_flag_closes_connection(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), close=True, **_frames())
    assert recording_conn.closed is True


def test_load_defaults_to_leaving_connection_open(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), **_frames())
    # The caller owns the dbc, so load must not close it by default.
    assert recording_conn.closed is False


# --- integration: full pipeline into a real Postgres -----------------------


@pytest.mark.integration
def test_fixture_slice_loads_into_real_postgres() -> None:
    """Drive the 2016 + 2020 fixture slice through the whole pipeline into Postgres.

    Configure via env: USVOTE_TEST_DB_{HOST,PORT,NAME,USER,PASSWORD}. Skips if
    unset so the marker runs locally without hard-coded credentials. Replays the
    Archives fixtures offline (``fetch_from_dir``) and injects the fake state-geo
    frame (``load_geo``), so no network or TIGER shapefile is needed — only a live
    database.
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbname = os.environ.get("USVOTE_TEST_DB_NAME")
    if not dbname:
        pytest.skip("USVOTE_TEST_DB_NAME not set; skipping live-Postgres test")

    config = {
        "host": os.environ.get("USVOTE_TEST_DB_HOST", "localhost"),
        "port": int(os.environ.get("USVOTE_TEST_DB_PORT", "5432")),
        "dbname": dbname,
        "user": os.environ.get("USVOTE_TEST_DB_USER", "postgres"),
        "password": os.environ.get("USVOTE_TEST_DB_PASSWORD", ""),
    }
    dbc = DBC(config)
    try:
        # The fixture dir names pages by year; a link-index fixture drives the two
        # snapshotted years (2016, 2020) through the real scrape->load spine.
        candidates_df, state_df, votes_df = run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES),
            load_geo=lambda _p: fake_state_geo(),
        )

        counts = {
            t: dbc.select_query_to_df(
                f"SELECT count(*) AS n FROM {SCHEMA}.{t}"
            )["n"].iloc[0]
            for t in TABLE_NAMES
        }
        # Every built frame lands in full.
        assert counts["state"] == len(state_df) == 51
        assert counts["candidate"] == len(candidates_df)
        assert counts["votes"] == len(votes_df)

        # Grain: primary keys are unique (a broken grain would have raised on the
        # PK constraint at insert, but assert explicitly for a clear signal).
        for table, pk in (("candidate", "candidate_id"), ("votes", "votes_id")):
            dup = dbc.select_query_to_df(
                f"SELECT {pk} FROM {SCHEMA}.{table} "
                f"GROUP BY {pk} HAVING count(*) > 1"
            )
            assert dup.empty, f"{table}.{pk} not unique"

        # FK containment: every votes.candidate_id resolves to a candidate, and
        # every non-null votes.state resolves to a state.
        orphan_cand = dbc.select_query_to_df(
            f"SELECT v.candidate_id FROM {SCHEMA}.votes v "
            f"LEFT JOIN {SCHEMA}.candidate c USING (candidate_id) "
            f"WHERE c.candidate_id IS NULL"
        )
        assert orphan_cand.empty
        orphan_state = dbc.select_query_to_df(
            f"SELECT v.state FROM {SCHEMA}.votes v "
            f"LEFT JOIN {SCHEMA}.state s USING (state) "
            f"WHERE v.state IS NOT NULL AND s.state IS NULL"
        )
        assert orphan_state.empty
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
