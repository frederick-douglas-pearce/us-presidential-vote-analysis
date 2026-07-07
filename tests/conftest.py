"""Shared test fixtures.

The recording fake connection lets unit tests assert on the SQL strings ``DBC``
builds without a live Postgres. It is defined here (not in ``test_db.py``)
because the EC and future ``usvote/ucsb`` / ``usvote/mit`` load stages all
construct a ``DBC`` and will want the same seam.
"""

from __future__ import annotations

from typing import Literal

import pytest


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
