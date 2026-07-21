"""Unit tests for :mod:`usvote.spine` — the EC-spine DB readers (#37).

Offline. The two readers are the DB seam a PV source uses to derive facts from the
loaded EC star schema; the real ``SELECT`` against Postgres runs in the ``#37``
integration test. Here ``select_query_to_df`` is stubbed to capture the SQL each reader
builds and to return a canned result, so the tests pin the two things that are the
readers' whole reason to exist: the ``is_total`` bool cast the roster derivation
requires, and the ``WHERE is_total`` getter grain (one row per candidate, not per
state) plus the year narrowing.
"""

from __future__ import annotations

import pandas as pd

from tests._helpers import RecordingConnection, make_dbc
from usvote.spine import (
    EC_GETTERS_COLUMNS,
    EC_PARTICIPATION_COLUMNS,
    read_ec_getters,
    read_ec_participation,
)


class StubDBC:
    """A ``DBC`` whose ``select_query_to_df`` records the SQL and returns a canned frame.

    ``select_query_to_df`` routes through ``pandas.read_sql``, which the recording fake
    connection cannot serve, so the spine readers are tested by stubbing that one method
    — the SQL string and the post-read reshaping are what these tests care about.
    """

    def __init__(self, result: pd.DataFrame) -> None:
        self._dbc = make_dbc(RecordingConnection())
        self._result = result
        self.queries: list[str] = []

    def select_query_to_df(self, query: str, close: bool = False) -> pd.DataFrame:
        self.queries.append(query)
        return self._result.copy()

    def __getattr__(self, name: str) -> object:
        return getattr(self._dbc, name)


# --- read_ec_participation --------------------------------------------------


def test_participation_returns_the_roster_columns() -> None:
    stub = StubDBC(
        pd.DataFrame({
            "year": [1876, 1876],
            "state": ["Alabama", None],
            "is_total": [False, True],
            "total_electoral_votes": [10, 369],
        })
    )
    out = read_ec_participation(stub)  # type: ignore[arg-type]
    assert list(out.columns) == list(EC_PARTICIPATION_COLUMNS)


def test_participation_casts_is_total_to_genuine_bool() -> None:
    # The DB seam owns the cast: _assert_participation_shape rejects 0/1 ints and
    # 't'/'f' strings (a string is truthy for every row). A driver handing back ints
    # must come out as real bools.
    stub = StubDBC(
        pd.DataFrame({
            "year": [1876, 1876],
            "state": ["Alabama", None],
            "is_total": [0, 1],
            "total_electoral_votes": [10, 369],
        })
    )
    out = read_ec_participation(stub)  # type: ignore[arg-type]
    assert out["is_total"].dtype == bool
    assert out["is_total"].tolist() == [False, True]


def test_participation_year_filter_is_inlined() -> None:
    stub = StubDBC(
        pd.DataFrame({
            "year": [1876], "state": ["Alabama"],
            "is_total": [False], "total_electoral_votes": [10],
        })
    )
    read_ec_participation(stub, years={1876, 1824})  # type: ignore[arg-type]
    (query,) = stub.queries
    assert "WHERE year IN (1824, 1876)" in query


def test_participation_no_year_filter_omits_where() -> None:
    stub = StubDBC(
        pd.DataFrame({
            "year": [1876], "state": ["Alabama"],
            "is_total": [False], "total_electoral_votes": [10],
        })
    )
    read_ec_participation(stub)  # type: ignore[arg-type]
    (query,) = stub.queries
    assert "WHERE" not in query


# --- read_ec_getters --------------------------------------------------------


def test_getters_returns_the_getter_columns() -> None:
    stub = StubDBC(
        pd.DataFrame({
            "year": [1876, 1876],
            "candidate": ["Rutherford B. Hayes", "Samuel J. Tilden"],
            "president_electoral_votes": [185, 184],
        })
    )
    out = read_ec_getters(stub)  # type: ignore[arg-type]
    assert list(out.columns) == list(EC_GETTERS_COLUMNS)


def test_getters_filters_to_totals_rows_for_one_row_per_candidate() -> None:
    # The national EV total sits on each candidate's is_total row; filtering to it is
    # what makes the grain one row per (year, candidate) rather than one per state.
    stub = StubDBC(
        pd.DataFrame({
            "year": [1876], "candidate": ["Rutherford B. Hayes"],
            "president_electoral_votes": [185],
        })
    )
    read_ec_getters(stub)  # type: ignore[arg-type]
    (query,) = stub.queries
    assert "WHERE v.is_total" in query
    assert "JOIN dwh.candidate" in query


def test_getters_year_filter_uses_and_not_a_second_where() -> None:
    # The is_total predicate already occupies WHERE, so the year narrowing must be an
    # AND — a second WHERE would be invalid SQL.
    stub = StubDBC(
        pd.DataFrame({
            "year": [1876], "candidate": ["Rutherford B. Hayes"],
            "president_electoral_votes": [185],
        })
    )
    read_ec_getters(stub, years={1876})  # type: ignore[arg-type]
    (query,) = stub.queries
    assert "WHERE v.is_total AND v.year IN (1876)" in query
    assert query.count("WHERE") == 1
