"""Shared, non-fixture test helpers.

Plain helpers (fake connections, ``DBC`` builders, the state-name set, the
fixtures-dir path) live here rather than in ``conftest.py`` so tests at any
depth — ``tests/unit/`` and ``tests/integration/`` alike — can import them via
a stable absolute path (``from tests._helpers import ...``) without importing
from a conftest module (a pytest anti-pattern). ``conftest.py`` is reserved for
fixtures, which pytest discovers automatically.

The recording fake connection lets unit tests assert on the SQL strings ``DBC``
builds without a live Postgres; the EC and future ``usvote/ucsb`` /
``usvote/mit`` load stages all construct a ``DBC`` and will want the same seam.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pandas as pd
import pytest

import usvote.db as db_module
from usvote.db import DBC

# Saved Archives HTML replayed offline; centralized here so tests at any depth
# reference the one path instead of recomputing ``Path(__file__).parent`` per
# file (which shifts under ``tests/integration/``).
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# The valid US state names Table 2 rows are matched against — the package
# equivalent of the notebook's geopandas ``NAME`` set (50 states + DC). Shared by
# the parse tests (the state-name filter) and the transform tests (the geo
# dimension set), so the two stay in lockstep — the SSOT coupling #31 externalizes.
STATE_NAMES = frozenset({
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
})


class RecordingCursor:
    """Cursor that appends every executed query to a shared log.

    Implements the context-manager protocol so it works inside
    ``with conn.cursor() as curs:``.
    """

    def __init__(self, executed: list[str]) -> None:
        self._executed = executed

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        return False

    def execute(self, query: str, vars: object = None) -> None:
        self._executed.append(query)


class RecordingConnection:
    """Fake psycopg2 connection that records SQL and its own close state.

    Supports the context-manager protocol (``with self.conn as conn``) the way
    psycopg2 connections do — yielding the connection itself.
    """

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self.executed)

    def __enter__(self) -> RecordingConnection:
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        return False

    def close(self) -> None:
        self.closed = True


def make_dbc(conn: RecordingConnection) -> DBC:
    """Build a :class:`DBC` wired to a fake connection instead of a real Postgres.

    Shared by every load-path test (db / load / pipeline), which all construct a
    ``DBC`` over the recording connection to assert on the SQL it builds.
    """
    return DBC({"dbname": "test"}, connect=lambda **_: conn)


def record_inserts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Patch ``usvote.db.execute_values`` to capture ``(sql, argslist)``; return the log.

    ``insert_df_into_table`` routes through the module-level ``execute_values``
    rather than ``cursor.execute``, so the recording cursor never sees the INSERTs
    — patch at the ``usvote.db`` lookup site to record them.
    """
    calls: list[tuple[str, Any]] = []

    def fake_execute_values(cur: object, sql: str, argslist: Any, **_: object) -> None:
        calls.append((sql, argslist))

    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)
    return calls


def fake_state_geo() -> pd.DataFrame:
    """A plain-pandas stand-in for ``transform.load_state_geo`` output.

    All 50 states + DC, plus Puerto Rico to prove territories are dropped, with
    REGION/DIVISION as strings (TIGER ships them so) to prove the astype-to-int in
    ``build_state_dim``. Shared by the transform, load, and pipeline tests so none
    of them needs the real TIGER shapefile.
    """
    rows = []
    for i, name in enumerate(sorted(STATE_NAMES)):
        rows.append({
            "NAME": name, "REGION": str(i % 4 + 1), "DIVISION": str(i % 9 + 1),
            "STATENS": f"{i:08d}", "GEOID": f"{i:02d}", "STUSPS": name[:2].upper(),
            "ALAND": 1000 + i, "AWATER": i,
            "INTPTLAT": f"+{30 + i % 20}.0", "INTPTLON": f"-{70 + i % 40}.0",
        })
    rows.append({
        "NAME": "Puerto Rico", "REGION": "9", "DIVISION": "9", "STATENS": "72000000",
        "GEOID": "72", "STUSPS": "PR", "ALAND": 1, "AWATER": 1,
        "INTPTLAT": "+18.0", "INTPTLON": "-66.0",
    })
    return pd.DataFrame(rows)
