"""Live-Postgres integration test for the census load (#181).

Excluded by default via the ``integration`` marker; run with ``pytest -m integration``
against a real database. It exists for the checks a fake connection structurally cannot
make — the ones where the *database* is the thing under test:

- the ``state`` foreign key actually resolves against ``dwh.state``, which is the whole
  point of conforming (D021) and the failure a recording fake happily accepts;
- the ``series`` and ``basis`` ``CHECK`` constraints really reject an out-of-enum value,
  so the value tuples in :mod:`usvote.census.schema` are load-bearing rather than
  decorative;
- ``population`` survives a round trip as a **39-million-scale integer**. This is the
  regression test for the ``smallint`` reflex the EC fact uses for vote counts: on a
  small fixture that mistake is invisible, and only a real column type catches it;
- a NULL population comes back as NULL rather than ``0`` (D005);
- the natural-key ``UNIQUE`` refuses a second load instead of duplicating rows.

Unlike the UCSB integration test this one needs no second env gate: Census data is
public domain (S1 §3), so the fixtures are real bytes committed to the repo and CI could
run this if a database were available.
"""

from __future__ import annotations

from typing import Any

import psycopg2
import pytest

from tests._helpers import (
    CENSUS_POPCHANGE_XLSX,
    CENSUS_TABS_TRIMMED_XLSX,
    FIXTURES_DIR,
    fake_state_geo,
)
from usvote.census.load import load_census_population
from usvote.census.parse import parse_population_change, parse_resident_1790_1990
from usvote.census.schema import CENSUS_SCHEMA, CENSUS_TABLE
from usvote.census.transform import transform_census
from usvote.db import DBC
from usvote.spine import read_ec_participation


def _frame(dbc: DBC) -> Any:
    rows = {
        "resident_1790_1990": parse_resident_1790_1990(
            CENSUS_TABS_TRIMMED_XLSX.read_bytes(), source_id="resident_1790_1990"
        ),
        "resident_1910_2020": parse_population_change(
            CENSUS_POPCHANGE_XLSX.read_bytes(), source_id="resident_1910_2020"
        ),
    }
    return transform_census(rows, read_ec_participation(dbc))


def _seed_spine(dbc: DBC) -> None:
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    run_ec_pipeline(
        dbc,
        "unused.shp",
        replace=True,
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )


@pytest.mark.integration
def test_census_population_loads_alongside_the_ec_spine(
    integration_db_config: dict[str, Any],
) -> None:
    dbc = DBC(integration_db_config)
    try:
        _seed_spine(dbc)
        frame = _frame(dbc)
        loaded = load_census_population(dbc, frame, replace=True)

        got = dbc.select_query_to_df(
            f"SELECT census_year, state, series, basis, population, redistributable "
            f"FROM {CENSUS_SCHEMA}.{CENSUS_TABLE} ORDER BY census_year, state"
        )
        assert len(got) == len(loaded)

        # The FK resolved — every loaded state is in dwh.state, or the insert would
        # have raised. Asserting it explicitly makes the intent visible rather than
        # implicit in "the insert did not blow up".
        orphans = dbc.select_query_to_df(
            f"SELECT c.state FROM {CENSUS_SCHEMA}.{CENSUS_TABLE} c "
            f"LEFT JOIN {CENSUS_SCHEMA}.state s ON s.state = c.state "
            f"WHERE s.state IS NULL"
        )
        assert orphans.empty

        # A 39-million-scale value round-trips intact. smallint would have refused the
        # insert; this is the column-type regression test.
        california = got[(got.state == "California") & (got.census_year == 2020)]
        assert california["population"].iloc[0] == 39_538_223

        # The Virginia correction survives into the database, labelled.
        virginia = got[(got.state == "Virginia") & (got.census_year == 1850)]
        assert virginia["population"].iloc[0] == 1_421_661
        assert virginia["basis"].iloc[0] == "as_enumerated"

        assert bool(got["redistributable"].all())
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_the_enum_checks_and_natural_key_are_enforced_by_the_database(
    integration_db_config: dict[str, Any],
) -> None:
    dbc = DBC(integration_db_config)
    try:
        _seed_spine(dbc)
        frame = _frame(dbc)
        load_census_population(dbc, frame, replace=True)

        # The basis CHECK is real. Note the shape guard does *not* validate the enum —
        # it checks columns, nulls, dtype and grain — so this frame passes every
        # Python-side check and is stopped only by the database. That is the division
        # of labour the CHECK-from-a-value-tuple pattern exists to create, and this is
        # the test that proves the constraint is carrying its half.
        bad_basis = frame.copy()
        bad_basis.loc[bad_basis.index[0], "basis"] = "guessed"
        with pytest.raises(psycopg2.errors.CheckViolation):
            load_census_population(dbc, bad_basis, replace=True)

        # Same for the series enum, which has only one legal value today — the column
        # that would otherwise look like decoration.
        bad_series = frame.copy()
        bad_series.loc[bad_series.index[0], "series"] = "apportionment"
        with pytest.raises(psycopg2.errors.CheckViolation):
            load_census_population(dbc, bad_series, replace=True)

        # Restore a good table for the uniqueness check below.
        load_census_population(dbc, frame, replace=True)

        # Re-running the load without replace hits the natural-key UNIQUE rather than
        # silently doubling every row — the intended non-destructive guard.
        with pytest.raises(psycopg2.errors.UniqueViolation):
            load_census_population(dbc, frame, replace=False)
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_a_missing_population_round_trips_as_null_not_zero(
    integration_db_config: dict[str, Any],
) -> None:
    """D005 at the one boundary where it can actually be violated.

    pandas NA, numpy NaN and SQL NULL are three different things, and the conversion
    happens in ``insert_df_into_table``. A frame that looks right in memory can still
    land as ``0`` — which would silently claim a state had no people rather than no
    published figure.
    """
    dbc = DBC(integration_db_config)
    try:
        _seed_spine(dbc)
        frame = _frame(dbc)
        target = (frame["state"] == "Connecticut") & (frame["census_year"] == 1850)
        assert target.any(), "fixture no longer contains the row this test mutates"
        frame.loc[target, "population"] = None
        frame.loc[target, "note"] = "No published figure in the fixture."
        load_census_population(dbc, frame, replace=True)

        got = dbc.select_query_to_df(
            f"SELECT population, note FROM {CENSUS_SCHEMA}.{CENSUS_TABLE} "
            f"WHERE state = 'Connecticut' AND census_year = 1850"
        )
        assert got["population"].isna().all()
        assert (got["population"] == 0).sum() == 0
        assert "No published figure" in got["note"].iloc[0]
    finally:
        dbc.close_connection()
