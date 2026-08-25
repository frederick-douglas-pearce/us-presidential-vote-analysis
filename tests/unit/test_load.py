"""Unit tests for ``usvote.load``.

Crafted units over the SQL the load stage emits — the column definitions (FK
``REFERENCES`` embed the schema), the create/insert order (state -> candidate ->
votes), and the ``replace`` guard (no ``DROP`` unless opted in) — all against the
recording fake connection, no live Postgres. The full-pipeline load into a real
database lives in ``tests/integration/test_load.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc, record_inserts
from usvote import count_status
from usvote.count_status import (
    COUNT_STATUS_COLUMN,
    COUNT_STATUS_REASON_COLUMN,
    COUNT_STATUS_VALUES,
    build_count_status_check,
)
from usvote.load import SCHEMA, TABLE_NAMES, build_table_column_defs, load_dataframes

# --- column definitions ----------------------------------------------------


def test_column_defs_embed_schema_in_fk_references() -> None:
    state, candidate, votes = (
        dict(zip(TABLE_NAMES, build_table_column_defs("mart"), strict=True))[t]
        for t in TABLE_NAMES
    )

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
    defs = dict(zip(TABLE_NAMES, build_table_column_defs(), strict=True))
    refs = [c for col in defs["votes"] for c in col if "REFERENCES" in c]
    assert refs == [f"REFERENCES {SCHEMA}.state", f"REFERENCES {SCHEMA}.candidate"]


def test_candidate_name_is_unique() -> None:
    # The canonical candidate key `name` carries a DB-level UNIQUE constraint so the
    # EC<->PV join (usvote.join, #69/D026) can resolve a PV loser row's candidate_id by
    # name unambiguously. Locked here so a DDL edit can't silently drop it and reintroduce
    # a fan-out risk (the transform-time uniqueness assert is the only other guard).
    candidate = dict(zip(TABLE_NAMES, build_table_column_defs(), strict=True))["candidate"]
    name_col = next(col for col in candidate if col[0] == "name")
    assert "unique" in name_col, f"candidate.name must be UNIQUE, got {name_col}"


def test_votes_carries_count_status_with_a_check_built_from_the_value_tuple() -> None:
    """The D043 §3 enum reaches the DDL, and reaches it from its single definition.

    A CHECK spelled out longhand in the DDL is the failure this guards: the enum would
    have two definitions, and a value added in :mod:`usvote.count_status` would be
    accepted by the transform and rejected by the database.
    """
    votes = dict(zip(TABLE_NAMES, build_table_column_defs(), strict=True))["votes"]
    by_name = {col[0]: col for col in votes}

    status = by_name[COUNT_STATUS_COLUMN]
    assert "not null" in status, "every row states its status; null is not 'presumably ok'"
    check = next(c for c in status if c.startswith("CHECK"))
    for value in COUNT_STATUS_VALUES:
        assert f"'{value}'" in check
    assert check == build_count_status_check()

    reason = by_name[COUNT_STATUS_REASON_COLUMN]
    # Nullable by design: null on every ordinary `counted` row.
    assert "not null" not in reason
    assert "text" in reason


def test_count_status_check_tracks_the_value_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The property the test above cannot show on its own: adding a value must change the
    # emitted SQL. Without this, a hand-written CHECK that happens to list today's three
    # values passes forever.
    monkeypatch.setattr(count_status, "COUNT_STATUS_VALUES", ("counted", "invented"))
    assert count_status.build_count_status_check() == (
        "CHECK (count_status IN ('counted', 'invented'))"
    )


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
    inserts = record_inserts(monkeypatch)
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
    record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), **_frames())

    # The guard: no DROP of any kind unless replace=True is passed explicitly.
    assert not any("DROP" in q for q in recording_conn.executed)
    assert any(q.startswith("CREATE SCHEMA IF NOT EXISTS") for q in recording_conn.executed)


def test_load_replace_drops_schema_cascade(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), replace=True, **_frames())

    drops = [q for q in recording_conn.executed if q.startswith("DROP")]
    # Exactly one drop — the schema-level cascade — and no per-table drops (the
    # schema drop already removed the tables).
    assert drops == [f"DROP SCHEMA IF EXISTS {SCHEMA} Cascade"]


def test_load_close_flag_closes_connection(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), close=True, **_frames())
    assert recording_conn.closed is True


def test_load_defaults_to_leaving_connection_open(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), **_frames())
    # The caller owns the dbc, so load must not close it by default.
    assert recording_conn.closed is False
