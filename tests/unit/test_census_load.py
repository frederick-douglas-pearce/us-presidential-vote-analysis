"""Unit tests for :mod:`usvote.census.load` and :mod:`usvote.census.schema` (#181).

Offline: the loader runs against the recording fake connection, so these assert the
DDL, the shape guard and the ``replace`` semantics without a database.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc, record_inserts
from usvote.census.conform import (
    BOUNDARY_BASIS_VALUES,
    BOUNDARY_PRESENT_DAY,
    COVERAGE_COVERED,
    COVERAGE_NO_GOVERNING_FIGURE,
    COVERAGE_VALUES,
    ELECTION_POPULATION_COLUMNS,
    ELECTION_POPULATION_TABLE,
    NULLABLE_ELECTION_POPULATION_COLUMNS,
    CensusConformError,
    build_boundary_basis_check,
    build_coverage_check,
    build_election_population_column_defs,
)
from usvote.census.load import load_census_population, load_election_population
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
        """The duplicate differs OUTSIDE the key, which is the whole point.

        A Class B mutation pass killed the previous version by broadening the check from
        `CENSUS_NATURAL_KEY` to `CENSUS_COLUMNS`: that version built its duplicate as two
        **wholly identical** rows, on which the two subsets are indistinguishable, so the
        broadened check still flagged them and the test stayed green.

        The pair below is the one that actually matters, and it is the case
        `schema.py` excludes `basis` from the key *for*: a published and a corrected
        Virginia row share `(source, census_year, state, series)` and differ in `basis`,
        `population` and `note`. Under the broadened check they pass this guard and only
        the database's UNIQUE stops them — as the opaque mid-insert psycopg2 error this
        guard exists to pre-empt.
        """
        published, corrected = _frame(), _frame()
        corrected.loc[0, "basis"] = "as_enumerated"
        corrected.loc[0, "population"] = 1_421_661
        corrected.loc[0, "note"] = "Restated onto the borders then in force."
        frame = pd.concat([published, corrected], ignore_index=True)

        # Precondition: they really do differ outside the key, or this is the old test.
        assert frame["basis"].nunique() == 2
        assert frame.duplicated(subset=list(CENSUS_COLUMNS)).sum() == 0

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


# --- the election-grain table (#184 / D064) ---------------------------------


def _election_frame(
    rows: list[tuple[int, str, int | None, int]] | None = None,
) -> pd.DataFrame:
    rows = rows or [(2020, "Wyoming", 576_851, 3)]
    records = [
        {
            "election_year": year,
            "state": state,
            "governing_census_year": 2010,
            "total_electoral_votes": tev,
            "population": population,
            "boundary_basis": BOUNDARY_PRESENT_DAY,
            "coverage": (
                COVERAGE_NO_GOVERNING_FIGURE
                if population is None
                else COVERAGE_COVERED
            ),
            "population_series": None if population is None else SERIES_RESIDENT,
        }
        for year, state, population, tev in rows
    ]
    frame = pd.DataFrame(records, columns=list(ELECTION_POPULATION_COLUMNS))
    frame["population"] = frame["population"].astype("Int64")
    return frame


def _election_defs() -> dict[str, tuple[str, ...]]:
    return {d[0]: d for d in build_election_population_column_defs()}


class TestElectionPopulationDDL:
    def test_population_is_integer_never_smallint(self) -> None:
        # The same overflow the census dimension's own DDL note explains, one table
        # over: a state population reaches ~39M and smallint tops out at 32,767. The
        # reflex to copy the EC fact's vote-measure type is what this pins against.
        assert _election_defs()["population"][1] == "integer"

    def test_the_allotment_is_smallint_because_it_really_is_a_vote_count(self) -> None:
        assert _election_defs()["total_electoral_votes"][1] == "smallint"

    def test_only_the_two_nullable_columns_are_nullable(self) -> None:
        """D005 at the database boundary, and the *direction* is what matters.

        A NOT NULL on ``population`` would make a participating state with no
        governing-census figure unloadable, forcing a zero or an interpolation — the
        one substitution this whole epic refuses. A missing NOT NULL anywhere else lets
        a half-built row land.
        """
        defs = _election_defs()
        nullable = {
            name
            for name, spec in defs.items()
            if name != "CONSTRAINT"
            and "not null" not in spec
            and "primary key" not in spec
        }
        assert nullable == set(NULLABLE_ELECTION_POPULATION_COLUMNS)

    def test_the_state_fk_embeds_the_schema_it_was_built_for(self) -> None:
        defs = {d[0]: d for d in build_election_population_column_defs("other")}
        assert "REFERENCES other.state" in defs["state"]

    def test_the_checks_are_built_from_the_value_tuples(self) -> None:
        # Built from the constants, never hand-written: a value added to a vocabulary
        # and not to its CHECK is a row the transform emits and the database refuses.
        defs = _election_defs()
        assert build_boundary_basis_check() in defs["boundary_basis"]
        assert build_coverage_check() in defs["coverage"]
        assert build_series_check("population_series") in defs["population_series"]

    def test_every_vocabulary_member_appears_in_its_check(self) -> None:
        # Non-vacuity for the test above: it compares two calls of the same builder, so
        # it would pass on a builder that emitted an empty IN list.
        for value in BOUNDARY_BASIS_VALUES:
            assert f"'{value}'" in build_boundary_basis_check()
        for value in COVERAGE_VALUES:
            assert f"'{value}'" in build_coverage_check()

    def test_the_natural_key_is_a_table_constraint(self) -> None:
        constraint = next(
            d for d in build_election_population_column_defs() if d[0] == "CONSTRAINT"
        )
        assert constraint[2] == "UNIQUE"
        assert "(election_year, state)" in constraint[3]

    def test_the_identity_column_is_database_assigned(self) -> None:
        assert "generated always as identity" in _election_defs()[
            "election_population_id"
        ]


class TestElectionPopulationLoad:
    def test_it_creates_the_schema_non_destructively(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        conn = RecordingConnection()
        load_election_population(make_dbc(conn), _election_frame(), replace=True)
        assert any("CREATE SCHEMA" in q.upper() for q in conn.executed)
        assert not any("DROP SCHEMA" in q.upper() for q in conn.executed), (
            "replace must never cascade a schema drop — that would wipe the EC spine"
        )

    def test_replace_drops_only_the_election_population_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        conn = RecordingConnection()
        load_election_population(make_dbc(conn), _election_frame(), replace=True)
        drops = [q for q in conn.executed if "DROP TABLE" in q.upper()]
        assert drops and all(ELECTION_POPULATION_TABLE in q for q in drops)
        assert not any(CENSUS_TABLE in q for q in drops)

    def test_the_default_is_additive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        record_inserts(monkeypatch)
        conn = RecordingConnection()
        load_election_population(make_dbc(conn), _election_frame())
        assert not any("DROP TABLE" in q.upper() for q in conn.executed)

    def test_rows_are_inserted_in_natural_key_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        frame = _election_frame(
            [(2020, "Wyoming", 576_851, 3), (1824, "Ohio", 581_434, 16)]
        )
        loaded = load_election_population(make_dbc(RecordingConnection()), frame)
        assert list(zip(loaded.election_year, loaded.state, strict=True)) == [
            (1824, "Ohio"),
            (2020, "Wyoming"),
        ]

    def test_the_returned_frame_omits_the_database_assigned_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_inserts(monkeypatch)
        loaded = load_election_population(
            make_dbc(RecordingConnection()), _election_frame()
        )
        assert "election_population_id" not in loaded.columns

    def test_the_write_boundary_re_runs_the_shape_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The loader does not trust its caller, and this is the falsifiable statement.

        The pipeline validates before calling, so the guard here is redundant *today*;
        it stops being redundant the moment a second caller appears, which is how a
        write boundary quietly loses its check.
        """
        record_inserts(monkeypatch)
        broken = _election_frame().drop(columns=["coverage"])
        with pytest.raises(CensusConformError, match="!="):
            load_election_population(make_dbc(RecordingConnection()), broken)

    def test_a_null_population_reaches_the_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # (1848, Texas) is this row in production: the Republic of Texas was not
        # enumerated by the US in 1840, and it cast 4 electoral votes.
        record_inserts(monkeypatch)
        loaded = load_election_population(
            make_dbc(RecordingConnection()),
            _election_frame([(1848, "Texas", None, 4)]),
        )
        assert loaded["population"].isna().all()
