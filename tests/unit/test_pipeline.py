"""Unit tests for ``usvote.pipeline``.

Covers the year-set derivation and the full scrape -> parse -> transform -> load
wiring, run offline: the 2016 + 2020 Archives fixtures replay through
``fetch_from_dir``, a fake state-geo frame is injected via ``load_geo``, and the
load lands on the recording fake connection — so the end-to-end wiring #28 adds is
exercised with no network, no TIGER shapefile, and no live Postgres. The
real-database load is covered by the integration test in
``tests/integration/test_load.py``.
"""

from __future__ import annotations

import pytest

from tests._helpers import (
    FIXTURES_DIR,
    RecordingConnection,
    fake_state_geo,
    make_dbc,
    record_inserts,
)
from usvote.load import SCHEMA
from usvote.pipeline import LATEST_ELECTION_YEAR, election_years, run_ec_pipeline
from usvote.scrape import fetch_from_dir

# --- election_years --------------------------------------------------------


def test_election_years_spans_1789_to_latest() -> None:
    years = election_years(2024)
    assert 1789 in years  # the lone off-cycle first election
    assert 1792 in years  # first of the every-four-years cadence
    assert 2024 in years
    assert 2021 not in years  # not an election year
    assert 1790 not in years


def test_election_years_does_not_overshoot_non_election_latest() -> None:
    # A non-election `latest` must not pull in the next cycle: the 4-year cadence
    # from 1792 stops at the last election year <= latest.
    years = election_years(2025)
    assert 2024 in years
    assert 2028 not in years
    assert max(years) == 2024


def test_election_years_defaults_to_module_latest() -> None:
    assert election_years() == election_years(LATEST_ELECTION_YEAR)
    assert max(election_years()) == LATEST_ELECTION_YEAR


# --- full pipeline wiring (offline) ----------------------------------------


def test_run_ec_pipeline_wires_all_stages_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Capture inserts (insert_df_into_table routes through execute_values, which
    # the recording cursor never sees) so we can assert every table was loaded.
    inserts = record_inserts(monkeypatch)

    candidates_df, state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
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
    assert [sql.split()[2] for sql, _ in inserts] == [
        f"{SCHEMA}.state",
        f"{SCHEMA}.candidate",
        f"{SCHEMA}.votes",
    ]


def test_run_ec_pipeline_leaves_connection_open_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    # The caller owns the dbc; the pipeline must not close it by default.
    assert recording_conn.closed is False
