"""Unit tests for :mod:`usvote.census.load` and :mod:`usvote.census.schema` (#181).

Offline: the loader runs against the recording fake connection, so these assert the
DDL, the shape guard and the ``replace`` semantics without a database.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc, record_inserts
from usvote.census.load import load_census_population
from usvote.census.schema import (
    BASIS_PRESENT_DAY,
    BASIS_VALUES,
    CENSUS_COLUMNS,
    CENSUS_NATURAL_KEY,
    CENSUS_TABLE,
    SERIES_RESIDENT,
    SERIES_VALUES,
    SOURCE_CENSUS_BUREAU,
    CensusShapeError,
    assert_census_shape,
    build_basis_check,
    build_census_column_defs,
    build_series_check,
)


def _frame(rows: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    rows = rows or [
        {
            "source": SOURCE_CENSUS_BUREAU,
            "census_year": 1850,
            "state": "Connecticut",
            "series": SERIES_RESIDENT,
            "basis": BASIS_PRESENT_DAY,
            "population": 370_792,
            "vintage": "v",
            "source_file": "f.xlsx",
            "redistributable": True,
            "note": None,
        }
    ]
    frame = pd.DataFrame(rows, columns=list(CENSUS_COLUMNS))
    frame["population"] = frame["population"].astype("Int64")
    return frame


def _defs() -> dict[str, tuple[str, ...]]:
    return {d[0]: d for d in build_census_column_defs()}


class TestDDL:
    def test_population_is_integer_never_smallint(self) -> None:
        """The one column type here that is correctness, not style.

        The EC fact types its electoral-vote measures ``smallint`` because a vote count
        fits in one. Copying that reflex overflows at 32,767 against state populations
        reaching ~39 million — and it would not fail loudly at load time on a small
        fixture, only on California.
        """
        assert _defs()["population"][1] == "integer"

    def test_population_is_nullable_so_no_published_figure_stays_distinct_from_zero(
        self,
    ) -> None:
        assert "not null" not in _defs()["population"]

    def test_the_state_fk_embeds_the_schema_it_was_built_for(self) -> None:
        # This is why the defs are a function rather than a constant: the FK names the
        # schema, so a hardcoded "dwh" would silently point a non-default build at the
        # wrong state dimension.
        assert "REFERENCES dwh.state" in _defs()["state"]
        other = {d[0]: d for d in build_census_column_defs("other")}
        assert "REFERENCES other.state" in other["state"]

    def test_the_checks_are_built_from_the_value_tuples(self) -> None:
        # The count_status.py / pv.status.py pattern: one definition, two consumers.
        # Hand-writing the SQL would let the enum and the constraint drift apart.
        for value in SERIES_VALUES:
            assert f"'{value}'" in build_series_check()
        for value in BASIS_VALUES:
            assert f"'{value}'" in build_basis_check()

    def test_the_natural_key_is_a_table_constraint(self) -> None:
        constraint = [d for d in build_census_column_defs() if d[0] == "CONSTRAINT"]
        assert constraint, "no UNIQUE constraint on the natural key"
        assert all(col in constraint[0][3] for col in CENSUS_NATURAL_KEY)

    def test_basis_is_not_part_of_the_natural_key(self) -> None:
        # Shape (a), settled at design review: one row per (source, year, state,
        # series), correction applied in place. Putting basis in the key would let a
        # published and a corrected Virginia coexist and silently double-count in any
        # consumer that forgot to filter.
        assert "basis" not in CENSUS_NATURAL_KEY

    def test_the_identity_column_is_database_assigned(self) -> None:
        assert "generated always as identity" in _defs()["population_id"]
        assert "population_id" not in CENSUS_COLUMNS


class TestShapeGuard:
    def test_a_well_formed_frame_passes(self) -> None:
        assert_census_shape(_frame())

    def test_a_reordered_column_set_is_refused(self) -> None:
        frame = _frame()[list(reversed(CENSUS_COLUMNS))]
        with pytest.raises(CensusShapeError, match="columns"):
            assert_census_shape(frame)

    def test_a_null_in_a_required_column_is_refused(self) -> None:
        frame = _frame()
        frame.loc[0, "vintage"] = None
        with pytest.raises(CensusShapeError, match="vintage"):
            assert_census_shape(frame)

    def test_a_float_population_column_is_refused(self) -> None:
        """The dtype check is a data-integrity check, not type fussiness.

        pandas widens a plain int64 column to float64 the moment a NULL appears, which
        turns 39,538,223 into a float and every "no published figure" into NaN — the
        exact distinction D005 requires the pipeline to preserve.
        """
        frame = _frame()
        frame["population"] = frame["population"].astype("float64")
        with pytest.raises(CensusShapeError, match="nullable integer"):
            assert_census_shape(frame)

    def test_a_duplicated_natural_key_is_refused_before_the_database_sees_it(
        self,
    ) -> None:
        frame = pd.concat([_frame(), _frame()], ignore_index=True)
        with pytest.raises(CensusShapeError, match="duplicate natural keys"):
            assert_census_shape(frame)

    def test_a_null_population_passes_the_guard(self) -> None:
        frame = _frame()
        frame["population"] = pd.array([None], dtype="Int64")
        assert_census_shape(frame)  # D005: absent is a legitimate value


class TestLoad:
    def test_it_creates_the_schema_non_destructively(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        conn = RecordingConnection()
        load_census_population(make_dbc(conn), _frame(), replace=True)
        created = [q for q in conn.executed if "CREATE SCHEMA" in q.upper()]
        assert created, "no schema create issued"
        assert not any("DROP SCHEMA" in q.upper() for q in conn.executed), (
            "replace must never cascade a schema drop — that would wipe the EC spine"
        )

    def test_replace_drops_only_the_census_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        conn = RecordingConnection()
        load_census_population(make_dbc(conn), _frame(), replace=True)
        drops = [q for q in conn.executed if "DROP TABLE" in q.upper()]
        assert drops and all(CENSUS_TABLE in q for q in drops)

    def test_the_default_is_additive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        record_inserts(monkeypatch)
        conn = RecordingConnection()
        load_census_population(make_dbc(conn), _frame())
        assert not any("DROP TABLE" in q.upper() for q in conn.executed)

    def test_rows_are_inserted_in_natural_key_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        frame = _frame(
            [
                {
                    "source": SOURCE_CENSUS_BUREAU,
                    "census_year": year,
                    "state": state,
                    "series": SERIES_RESIDENT,
                    "basis": BASIS_PRESENT_DAY,
                    "population": 1,
                    "vintage": "v",
                    "source_file": "f",
                    "redistributable": True,
                    "note": None,
                }
                for year, state in [(1990, "Wyoming"), (1850, "Alabama")]
            ]
        )
        loaded = load_census_population(make_dbc(RecordingConnection()), frame)
        assert list(loaded["census_year"]) == [1850, 1990]

    def test_the_returned_frame_omits_the_database_assigned_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        loaded = load_census_population(make_dbc(RecordingConnection()), _frame())
        assert "population_id" not in loaded.columns
