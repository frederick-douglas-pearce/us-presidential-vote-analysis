"""Shared test fixtures.

The recording fake connection lets unit tests assert on the SQL strings ``DBC``
builds without a live Postgres. It is defined here (not in ``test_db.py``)
because the EC and future ``usvote/ucsb`` / ``usvote/mit`` load stages all
construct a ``DBC`` and will want the same seam.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
import pytest

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


@pytest.fixture
def recording_conn() -> RecordingConnection:
    """A fresh fake connection whose ``.executed`` list captures SQL strings."""
    return RecordingConnection()


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
