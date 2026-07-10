"""Unit tests for ``usvote.db.DBC``.

These cover SQL-string construction and control flow (close/replace flags, the
empty-DataFrame guard, connect-failure) without a live Postgres — the fake
connection from ``conftest`` records executed SQL. A single ``integration`` test
at the bottom exercises a real database and is excluded by default.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import psycopg2 as pg
import pytest

import usvote.db as db_module
from usvote.db import DBC, DBConnectionError

from .conftest import RecordingConnection


def make_dbc(conn: RecordingConnection) -> DBC:
    """Build a DBC wired to the fake connection instead of a real Postgres."""
    return DBC({"dbname": "test"}, connect=lambda **_: conn)


# --- connection handling ---------------------------------------------------


def test_init_passes_config_to_connect() -> None:
    captured: dict[str, object] = {}

    def fake_connect(**kwargs: object) -> RecordingConnection:
        captured.update(kwargs)
        return RecordingConnection()

    config = {"host": "localhost", "port": 5432, "dbname": "elections"}
    dbc = DBC(config, connect=fake_connect)

    assert captured == config
    assert dbc.config == config


def test_connect_failure_raises_typed_exception() -> None:
    def boom(**_: object) -> RecordingConnection:
        raise pg.DatabaseError("no server")

    with pytest.raises(DBConnectionError):
        DBC({"dbname": "x"}, connect=boom)


def test_close_connection(recording_conn: RecordingConnection) -> None:
    dbc = make_dbc(recording_conn)
    dbc.close_connection()
    assert recording_conn.closed is True


def test_close_flag_closes_after_query(recording_conn: RecordingConnection) -> None:
    dbc = make_dbc(recording_conn)
    dbc.execute_query("SELECT 1", close=True)
    assert recording_conn.closed is True


def test_no_close_flag_leaves_connection_open(
    recording_conn: RecordingConnection,
) -> None:
    dbc = make_dbc(recording_conn)
    dbc.execute_query("SELECT 1")
    assert recording_conn.closed is False


# --- schema DDL ------------------------------------------------------------


def test_create_schema_sql(recording_conn: RecordingConnection) -> None:
    make_dbc(recording_conn).create_schema("dwh")
    assert recording_conn.executed == ["CREATE SCHEMA IF NOT EXISTS dwh"]


def test_create_schema_replace_drops_then_creates(
    recording_conn: RecordingConnection,
) -> None:
    make_dbc(recording_conn).create_schema("dwh", replace=True)
    assert recording_conn.executed == [
        "DROP SCHEMA IF EXISTS dwh Cascade",
        "CREATE SCHEMA IF NOT EXISTS dwh",
    ]


def test_delete_schema_default_option(recording_conn: RecordingConnection) -> None:
    make_dbc(recording_conn).delete_schema("dwh")
    assert recording_conn.executed == ["DROP SCHEMA IF EXISTS dwh Restrict"]


# --- table DDL -------------------------------------------------------------


def test_create_table_joins_column_defs(recording_conn: RecordingConnection) -> None:
    columns = [("state", "text"), ("geoid", "integer"), ("area", "double precision")]
    make_dbc(recording_conn).create_table("dwh", "state", columns)
    assert recording_conn.executed == [
        "CREATE TABLE IF NOT EXISTS dwh.state "
        "(state text, geoid integer, area double precision)"
    ]


def test_create_table_replace_drops_then_creates(
    recording_conn: RecordingConnection,
) -> None:
    make_dbc(recording_conn).create_table(
        "dwh", "state", [("state", "text")], replace=True
    )
    assert recording_conn.executed == [
        "DROP TABLE IF EXISTS dwh.state Cascade",
        "CREATE TABLE IF NOT EXISTS dwh.state (state text)",
    ]


def test_delete_table_default_option(recording_conn: RecordingConnection) -> None:
    make_dbc(recording_conn).delete_table("dwh", "state")
    assert recording_conn.executed == ["DROP TABLE IF EXISTS dwh.state Restrict"]


def test_copy_csv_with_and_without_header(
    recording_conn: RecordingConnection,
) -> None:
    dbc = make_dbc(recording_conn)
    dbc.copy_csv_to_table("dwh", "state", "/tmp/s.csv", header=True)
    dbc.copy_csv_to_table("dwh", "state", "/tmp/s.csv", header=False)
    assert recording_conn.executed == [
        "COPY dwh.state FROM '/tmp/s.csv' DELIMITER ',' CSV HEADER",
        "COPY dwh.state FROM '/tmp/s.csv' DELIMITER ','",
    ]


# --- insert_df_into_table --------------------------------------------------


def test_insert_df_builds_columns_and_stmt(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, str, Any]] = []

    def fake_execute_values(cur: object, sql: str, argslist: Any, **_: object) -> None:
        calls.append((cur, sql, argslist))

    # Patch at the lookup site (usvote.db), not psycopg2.extras.
    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)

    df = pd.DataFrame({"year": [2020], "candidate_id": [1]})
    make_dbc(recording_conn).insert_df_into_table("dwh", "votes", df)

    assert len(calls) == 1
    _, sql, argslist = calls[0]
    assert sql == "INSERT INTO dwh.votes (year,candidate_id) VALUES %s"
    # Rows are native-Python tuples (not numpy) handed to execute_values.
    assert list(argslist[0]) == [2020, 1]
    assert all(type(v) is int for v in argslist[0])


def test_insert_normalizes_nan_and_numpy_scalars() -> None:
    # The DataFrame->SQL conversion must unbox numpy scalars (psycopg2 can't adapt
    # numpy.int64) and turn every null-like value into None (NOT a literal NaN,
    # which Postgres rejects on NOT NULL / FK columns). Regression for the two
    # failures the live-Postgres integration test surfaced.
    df = pd.DataFrame(
        {
            "n": [1, 2],  # int64 -> python int
            "flag": [True, False],  # bool -> python bool
            "name": pd.array(["Trump", None], dtype="string"),  # StringDtype NA
            "state_2": [float("nan"), "Ohio"],  # float NaN -> None
        }
    )
    rows = db_module._df_to_sql_rows(df)

    assert rows == [(1, True, "Trump", None), (2, False, None, "Ohio")]
    # Every non-None scalar is a builtin Python type, not a numpy scalar.
    for row in rows:
        for v in row:
            assert v is None or type(v).__module__ == "builtins"


def test_insert_empty_df_is_guarded(
    recording_conn: RecordingConnection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called = False

    def fake_execute_values(*_: object, **__: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)

    make_dbc(recording_conn).insert_df_into_table("dwh", "votes", pd.DataFrame())

    assert called is False
    assert recording_conn.executed == []  # no SQL built for an empty frame
    assert "empty" in capsys.readouterr().out.lower()


# --- select_query_to_df ----------------------------------------------------


def test_select_query_to_df_delegates_to_read_sql(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = pd.DataFrame({"n": [1]})
    seen: dict[str, object] = {}

    def fake_read_sql(query: str, conn: object) -> pd.DataFrame:
        seen["query"] = query
        seen["conn"] = conn
        return sentinel

    monkeypatch.setattr(db_module.pd, "read_sql", fake_read_sql)

    dbc = make_dbc(recording_conn)
    result = dbc.select_query_to_df("SELECT n FROM t")

    assert result is sentinel
    assert seen["query"] == "SELECT n FROM t"
    assert seen["conn"] is recording_conn


# --- integration (excluded by default; requires a live Postgres) -----------


@pytest.mark.integration
def test_roundtrip_against_real_postgres() -> None:
    """Smoke test against a real database.

    Configure via env: USVOTE_TEST_DB_{HOST,PORT,NAME,USER,PASSWORD}. Skips if
    unset so the marker can be run locally without hard-coding credentials.
    """
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
        dbc.create_schema("usvote_test", replace=True)
        dbc.create_table("usvote_test", "t", [("id", "integer")])
        dbc.insert_df_into_table("usvote_test", "t", pd.DataFrame({"id": [1, 2]}))
        out = dbc.select_query_to_df("SELECT id FROM usvote_test.t ORDER BY id")
        assert out["id"].tolist() == [1, 2]
    finally:
        dbc.delete_schema("usvote_test", option="Cascade")
        dbc.close_connection()
