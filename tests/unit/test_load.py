"""Unit tests for ``usvote.load``.

Crafted units over the SQL the load stage emits — the column definitions (FK
``REFERENCES`` embed the schema), the create/insert order (state -> candidate ->
votes -> candidate_party, the #385 / D077 nominating-party table), the party CHECKs, and
the ``replace`` guard (no ``DROP`` unless opted in) — all against the
recording fake connection, no live Postgres. The full-pipeline load into a real
database lives in ``tests/integration/test_load.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc, record_inserts
from usvote import count_status, party
from usvote.count_status import (
    COUNT_STATUS_COLUMN,
    COUNT_STATUS_REASON_COLUMN,
    COUNT_STATUS_VALUES,
    build_count_status_check,
)
from usvote.load import SCHEMA, TABLE_NAMES, build_table_column_defs, load_dataframes
from usvote.party import (
    ARCHIVES_CODE_COLUMN,
    CANDIDATE_PARTY_COLUMNS,
    NOTE_COLUMN,
    PARTY_COLUMN,
    SOURCE_COLUMN,
    build_party_source_check,
    build_party_source_code_check,
    build_party_value_check,
)

# --- column definitions ----------------------------------------------------


def test_column_defs_embed_schema_in_fk_references() -> None:
    state, candidate, votes, candidate_party = (
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
    # candidate_party references the candidate dimension in the same schema.
    party_fks = [c for col in candidate_party for c in col if "REFERENCES" in c]
    assert party_fks == ["REFERENCES mart.candidate"]


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
    # SQL the load stage emits. Read through build_table_column_defs, not the builder
    # alone: a CHECK hand-written in load.py that lists today's three values would pass
    # a test of the builder, and the test above, forever.
    monkeypatch.setattr(count_status, "COUNT_STATUS_VALUES", ("counted", "invented"))
    votes = dict(zip(TABLE_NAMES, build_table_column_defs(), strict=True))["votes"]
    status = next(col for col in votes if col[0] == COUNT_STATUS_COLUMN)
    assert status[-1] == "CHECK (count_status IN ('counted', 'invented'))"


def _candidate_party_defs() -> dict[str, tuple[str, ...]]:
    defs = dict(zip(TABLE_NAMES, build_table_column_defs(), strict=True))
    return {
        col[1] if col[0] == "CONSTRAINT" else col[0]: col
        for col in defs["candidate_party"]
    }


def test_candidate_party_columns_follow_the_party_contract_in_load_order() -> None:
    by_name = _candidate_party_defs()
    columns = [name for name, col in by_name.items() if col[0] != "CONSTRAINT"]
    assert tuple(columns) == CANDIDATE_PARTY_COLUMNS
    for required in ("year", "candidate_id", PARTY_COLUMN, SOURCE_COLUMN):
        assert "not null" in by_name[required], required
    # Null on curated rows, and null when no note was recorded.
    for nullable in (ARCHIVES_CODE_COLUMN, NOTE_COLUMN):
        assert "not null" not in by_name[nullable], nullable


def test_candidate_party_checks_are_built_from_the_party_constants() -> None:
    """The vocabulary and the two sources have one definition each, in usvote.party."""
    by_name = _candidate_party_defs()
    assert by_name[PARTY_COLUMN][-1] == build_party_value_check()
    assert by_name[SOURCE_COLUMN][-1] == build_party_source_check()
    assert by_name["candidate_party_source_code_check"] == (
        "CONSTRAINT", "candidate_party_source_code_check",
        build_party_source_code_check(),
    )
    for code in party.NOMINATING_PARTIES:
        assert f"'{code}'" in build_party_value_check()
    assert build_party_source_check() == (
        "CHECK (nominating_party_source IN ('NARA', 'USGOV'))"
    )
    assert build_party_source_code_check() == (
        "CHECK ((nominating_party_source = 'NARA') = "
        "(archives_party_code IS NOT NULL))"
    )


def test_candidate_party_has_a_named_composite_primary_key() -> None:
    assert _candidate_party_defs()["candidate_party_pkey"] == (
        "CONSTRAINT", "candidate_party_pkey", "PRIMARY KEY", "(year, candidate_id)",
    )


def test_party_value_check_tracks_the_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Adding a code must change the SQL the load stage emits. Read through
    # build_table_column_defs: a CHECK hand-written in load.py would pass a test of the
    # builder alone.
    monkeypatch.setattr(party, "PARTY_COMPONENTS", {"democratic": (), "invented": ()})
    assert _candidate_party_defs()[PARTY_COLUMN][-1] == (
        "CHECK (nominating_party IN ('democratic', 'invented'))"
    )


def test_party_source_check_tracks_the_source_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(party, "PARTY_SOURCES", ("NARA", "INVENTED"))
    assert _candidate_party_defs()[SOURCE_COLUMN][-1] == (
        "CHECK (nominating_party_source IN ('NARA', 'INVENTED'))"
    )


# --- load_dataframes: order + inserts --------------------------------------


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "state_df": pd.DataFrame({"state": ["Ohio"]}),
        "candidates_df": pd.DataFrame({"candidate_id": [1], "name": ["X"]}),
        "votes_df": pd.DataFrame({"votes_id": [1], "candidate_id": [1]}),
        "candidate_party_df": pd.DataFrame({"year": [2020], "candidate_id": [1]}),
    }


def test_load_creates_and_inserts_in_fk_order(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = record_inserts(monkeypatch)
    load_dataframes(make_dbc(recording_conn), **_frames())

    creates = [q for q in recording_conn.executed if q.startswith("CREATE TABLE")]
    order = [
        f"{SCHEMA}.state",
        f"{SCHEMA}.candidate",
        f"{SCHEMA}.votes",
        f"{SCHEMA}.candidate_party",
    ]
    # state -> candidate -> votes -> candidate_party, the FK-dependency order.
    assert [q.split()[5] for q in creates] == order
    # One insert per table, in the same order.
    assert [sql.split()[2] for sql, _ in inserts] == order


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
