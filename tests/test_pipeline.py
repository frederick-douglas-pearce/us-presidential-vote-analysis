"""Unit tests for ``usvote.pipeline``.

Covers the year-set derivation and the full scrape -> parse -> transform -> load
wiring, run offline: the 2016 + 2020 Archives fixtures replay through
``fetch_from_dir``, a fake state-geo frame is injected via ``load_geo``, and the
load lands on the recording fake connection — so the end-to-end wiring #28 adds is
exercised with no network, no TIGER shapefile, and no live Postgres. The
real-database load is covered by the integration test in ``test_load``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import usvote.db as db_module
from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.pipeline import LATEST_ELECTION_YEAR, election_years, run_ec_pipeline
from usvote.scrape import fetch_from_dir

from .conftest import RecordingConnection, fake_state_geo

FIXTURES = Path(__file__).parent / "fixtures"


# --- election_years --------------------------------------------------------


def test_election_years_spans_1789_to_latest() -> None:
    years = election_years(2024)
    assert 1789 in years  # the lone off-cycle first election
    assert 1792 in years  # first of the every-four-years cadence
    assert 2024 in years
    assert 2021 not in years  # not an election year
    assert 1790 not in years


def test_election_years_defaults_to_module_latest() -> None:
    assert election_years() == election_years(LATEST_ELECTION_YEAR)
    assert max(election_years()) == LATEST_ELECTION_YEAR


# --- full pipeline wiring (offline) ----------------------------------------


def test_run_ec_pipeline_wires_all_stages_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Capture inserts (insert_df_into_table routes through execute_values, which
    # the recording cursor never sees) so we can assert every table was loaded.
    inserted: list[str] = []

    def fake_execute_values(cur: object, sql: str, argslist: Any, **_: object) -> None:
        inserted.append(sql.split()[2])  # schema.table

    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)

    dbc = DBC({"dbname": "test"}, connect=lambda **_: recording_conn)
    candidates_df, state_df, votes_df = run_ec_pipeline(
        dbc,
        "unused.shp",
        replace=True,
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES),
        load_geo=lambda _p: fake_state_geo(),
    )

    # The three warehouse frames were built and are non-empty.
    assert list(candidates_df.columns[:2]) == ["candidate_id", "name"]
    assert len(state_df) == 51
    assert {"votes_id", "year", "candidate_id"}.issubset(votes_df.columns)
    assert not votes_df.empty

    # Both fixture years flowed through to the votes fact.
    assert set(votes_df["year"]) == {2016, 2020}

    # All three tables were created and inserted, in FK order.
    assert inserted == [f"{SCHEMA}.state", f"{SCHEMA}.candidate", f"{SCHEMA}.votes"]


def test_run_ec_pipeline_leaves_connection_open_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        db_module, "execute_values", lambda *_a, **_k: None
    )
    dbc = DBC({"dbname": "test"}, connect=lambda **_: recording_conn)
    run_ec_pipeline(
        dbc,
        "unused.shp",
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES),
        load_geo=lambda _p: fake_state_geo(),
    )
    # The caller owns the dbc; the pipeline must not close it by default.
    assert recording_conn.closed is False
