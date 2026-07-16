"""Unit tests for the shared PV schema + loader (``usvote.pv``).

Crafted units over the DDL the loader emits, the ``pv_id`` assignment, the boundary
shape guard, and — most load-bearing — the guard that a PV ``replace`` drops only the
``pv_votes`` table and **never** the ``dwh`` schema (which would wipe the EC spine
sharing it). All against the recording fake connection, no live Postgres; the
full-pipeline load into a real database lives in ``tests/integration/test_pv_load.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc, record_inserts
from usvote.pv.load import load_pv_records
from usvote.pv.schema import (
    PV_SCHEMA,
    PV_TABLE,
    RELIABILITY_VALUES,
    SHARED_PV_COLUMNS,
    PVShapeError,
    assert_pv_shape,
    build_pv_column_defs,
)

# --- column definitions ----------------------------------------------------


def test_column_defs_embed_schema_in_state_fk() -> None:
    defs = {col[0]: col for col in build_pv_column_defs("mart")}
    # The only FK is state -> <schema>.state (no candidate FK — the EC candidate PK
    # is candidate_id, not the name string this shape carries).
    assert "REFERENCES mart.state" in defs["state"]
    fk_cols = [name for name, col in defs.items() if any("REFERENCES" in c for c in col)]
    assert fk_cols == ["state"]


def test_column_defs_default_to_dwh_schema() -> None:
    defs = {col[0]: col for col in build_pv_column_defs()}
    assert f"REFERENCES {PV_SCHEMA}.state" in defs["state"]


def test_column_defs_pv_id_is_db_generated_identity_pk() -> None:
    # pv_id must be a DB-assigned IDENTITY PK, not a value the loader supplies — so
    # ids stay unique across separate loads (MIT then UCSB) instead of restarting at 1.
    first = build_pv_column_defs()[0]
    assert first[0] == "pv_id"
    assert "primary key" in first
    assert "generated always as identity" in first


def test_column_defs_reliability_check_lists_the_enum() -> None:
    check = next(c for col in build_pv_column_defs() for c in col if "CHECK" in c)
    for value in RELIABILITY_VALUES:
        assert f"'{value}'" in check


def test_column_defs_carry_natural_key_unique_constraint() -> None:
    constraint = build_pv_column_defs()[-1]
    assert constraint[0] == "CONSTRAINT"
    assert f"{PV_TABLE}_natural_key" in constraint
    assert "UNIQUE" in constraint
    assert "(source, year, state, candidate)" in constraint


def test_column_defs_define_pv_id_then_shared_shape() -> None:
    # The DDL defines pv_id (DB-generated) first, then every SHARED_PV_COLUMNS column,
    # before the trailing table constraint. The loader inserts only SHARED_PV_COLUMNS —
    # pv_id is filled by the identity sequence (see the INSERT-columns test below).
    names = [col[0] for col in build_pv_column_defs()[:-1]]
    assert names == ["pv_id", *SHARED_PV_COLUMNS]


# --- assert_pv_shape (boundary guard) --------------------------------------


def _valid_frame() -> pd.DataFrame:
    """A minimal valid shared-shape frame, rows deliberately out of key order."""
    rows = [
        {
            "source": "MIT", "year": 2016, "state": "New York",
            "candidate": "Donald J. Trump", "party": "REPUBLICAN",
            "candidate_votes": 2814589, "state_total_votes": 7889703,
            "reliability": "exact",
        },
        {
            "source": "MIT", "year": 2016, "state": "New York",
            "candidate": "Hillary Clinton", "party": "DEMOCRAT",
            "candidate_votes": 4556124, "state_total_votes": 7889703,
            "reliability": "exact",
        },
        {
            "source": "MIT", "year": 2016, "state": "California",
            "candidate": "Hillary Clinton", "party": "DEMOCRAT",
            "candidate_votes": 8753788, "state_total_votes": 14181595,
            "reliability": "exact",
        },
    ]
    return pd.DataFrame(rows)[list(SHARED_PV_COLUMNS)]


def test_assert_pv_shape_accepts_valid_frame() -> None:
    assert_pv_shape(_valid_frame())  # does not raise


def test_assert_pv_shape_rejects_wrong_columns() -> None:
    bad = _valid_frame().drop(columns=["reliability"])
    with pytest.raises(PVShapeError, match="shared PV shape"):
        assert_pv_shape(bad)


def test_assert_pv_shape_rejects_reordered_columns() -> None:
    cols = list(SHARED_PV_COLUMNS)
    cols[0], cols[1] = cols[1], cols[0]
    with pytest.raises(PVShapeError, match="shared PV shape"):
        assert_pv_shape(_valid_frame()[cols])


def test_assert_pv_shape_rejects_null_natural_key() -> None:
    bad = _valid_frame()
    bad.loc[0, "candidate"] = None
    with pytest.raises(PVShapeError, match="candidate"):
        assert_pv_shape(bad)


def test_assert_pv_shape_allows_null_party() -> None:
    # party is nullable (UCSB forward-compat) — not in REQUIRED_NON_NULL.
    ok = _valid_frame()
    ok.loc[0, "party"] = None
    assert_pv_shape(ok)  # does not raise


def test_assert_pv_shape_rejects_float_vote_counts() -> None:
    # A source whose transform left candidate_votes as float64 would otherwise be
    # inserted into the integer DDL column (silent rounding / opaque psycopg2 error).
    # The shared guard must reject it — mirroring MIT's own transform.assert_shape.
    bad = _valid_frame()
    bad["candidate_votes"] = bad["candidate_votes"].astype("float64")
    with pytest.raises(PVShapeError, match="must be integer"):
        assert_pv_shape(bad)


# --- load_pv_records: ordering + insert ------------------------------------


def test_load_inserts_rows_in_natural_key_order(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    loaded = load_pv_records(make_dbc(recording_conn), _valid_frame())

    # Rows sorted by (source, year, state, candidate): California sorts before New
    # York, and within New York "Donald..." before "Hillary...". pv_id is NOT in the
    # returned frame — the database assigns it (identity), so nothing here can depend
    # on a per-call 1..n numbering.
    assert "pv_id" not in loaded.columns
    assert loaded[["state", "candidate"]].values.tolist() == [
        ["California", "Hillary Clinton"],
        ["New York", "Donald J. Trump"],
        ["New York", "Hillary Clinton"],
    ]


def test_load_insert_omits_pv_id_so_the_db_generates_it(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame())

    # The INSERT column list is exactly SHARED_PV_COLUMNS — pv_id is absent, so the
    # GENERATED ALWAYS AS IDENTITY sequence fills it (a supplied pv_id would both
    # collide across loads and be rejected by the ALWAYS identity).
    (sql, _argslist) = inserts[0]
    expected_cols = ",".join(SHARED_PV_COLUMNS)
    assert sql == f"INSERT INTO {PV_SCHEMA}.{PV_TABLE} ({expected_cols}) VALUES %s"
    assert "pv_id" not in sql


# --- load_pv_records: the replace footgun ----------------------------------


def test_load_non_destructive_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame())

    assert not any("DROP" in q for q in recording_conn.executed)
    assert any(
        q.startswith("CREATE SCHEMA IF NOT EXISTS") for q in recording_conn.executed
    )
    assert any(
        q.startswith(f"CREATE TABLE IF NOT EXISTS {PV_SCHEMA}.{PV_TABLE}")
        for q in recording_conn.executed
    )


def test_load_replace_drops_only_the_table_never_the_schema(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # THE guard: a PV replace must not cascade-drop the dwh schema (which would wipe
    # the EC spine sharing it). Exactly one drop, and it is the pv_votes table.
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame(), replace=True)

    drops = [q for q in recording_conn.executed if q.startswith("DROP")]
    assert drops == [f"DROP TABLE IF EXISTS {PV_SCHEMA}.{PV_TABLE} Cascade"]
    assert not any("DROP SCHEMA" in q for q in recording_conn.executed)


# --- load_pv_records: connection ownership ---------------------------------


def test_load_close_flag_closes_connection(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame(), close=True)
    assert recording_conn.closed is True


def test_load_defaults_to_leaving_connection_open(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame())
    assert recording_conn.closed is False
