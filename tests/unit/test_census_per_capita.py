"""Unit tests for :mod:`usvote.census.per_capita` (#184).

Offline throughout: the SQL builder is asserted as a **string** and the oracle as a
**frame**, so nothing here touches a database.

**Know what this file can and cannot establish**, because the split is the same one
``tests/integration/test_hybrid_views.py`` documents for its own module. This module
holds two expressions of one derivation — the SQL that drives the live view and the
pandas oracle — and *nothing offline can run the emitted SQL*. A string assert proves
the builder still names ``NULLIF`` and still casts; it cannot prove Postgres does with
that string what the oracle does with pandas. The check that closes it is
``tests/integration/test_census_per_capita.py``'s
``test_the_live_view_matches_the_pandas_oracle``,
which reads the view back and compares it row-for-row. Its fixture **must keep a
zero-allotment row**, or the branch both halves are written for is never exercised on
either side; that row is a hand-written literal there, not a consequence of which
election years the fixture seeds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc
from usvote.census.conform import (
    BOUNDARY_PRESENT_DAY,
    COVERAGE_COVERED,
    COVERAGE_NO_GOVERNING_FIGURE,
    ELECTION_POPULATION_COLUMNS,
    ELECTION_POPULATION_TABLE,
)
from usvote.census.per_capita import (
    PER_CAPITA_COLUMN,
    PER_CAPITA_COLUMNS,
    PER_CAPITA_GRAIN,
    PER_CAPITA_VIEW,
    PerCapitaError,
    assert_no_fan_out,
    assert_ratio_null_only_where_explained,
    build_per_capita_frame,
    build_per_capita_sql,
    create_per_capita_view,
    read_per_capita,
)
from usvote.census.schema import CENSUS_SCHEMA, SERIES_RESIDENT
from usvote.db import DBC


def _election_population(
    rows: list[tuple[int, str, int | None, int]],
) -> pd.DataFrame:
    """Build an election-population frame from ``(year, state, population, tev)``.

    ``population_series`` and ``coverage`` follow the population, exactly as
    :func:`usvote.census.conform.build_election_population` sets them, so a fixture
    here cannot accidentally describe a row shape the builder never produces.
    """
    records = [
        {
            "election_year": year,
            "state": state,
            "governing_census_year": year - 4,
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
    frame = pd.DataFrame.from_records(
        records, columns=list(ELECTION_POPULATION_COLUMNS)
    )
    frame["population"] = frame["population"].astype("Int64")
    return frame


class _ProbeDBC:
    """A ``DBC`` whose existence probe answers ``exists`` and whose views are recorded.

    Not a mock of :func:`~usvote.census.per_capita.create_per_capita_view`'s internals:
    the probe really issues its ``to_regclass`` query and that query is recorded, so a
    builder that stopped probing — or probed the wrong relation — fails here rather than
    passing on a stubbed-out boolean.
    """

    def __init__(self, *, exists: bool) -> None:
        self._exists = exists
        self.queries: list[str] = []
        self.views: list[tuple[str, str, str, bool]] = []
        self.closed = False

    def select_query_to_df(self, query: str) -> pd.DataFrame:
        self.queries.append(query)
        return pd.DataFrame({"relation": [ELECTION_POPULATION_TABLE if self._exists
                                          else None]})

    def create_view(
        self,
        schema: str,
        view_name: str,
        select_sql: str,
        replace: bool = False,
        close: bool = False,
    ) -> None:
        self.views.append((schema, view_name, select_sql, replace))

    def close_connection(self) -> None:
        self.closed = True


class TestTheColumnContract:
    def test_the_column_order_is_pinned_to_a_literal(self) -> None:
        # Hand-written, NOT built from ELECTION_POPULATION_COLUMNS. PER_CAPITA_COLUMNS is
        # `(*ELECTION_POPULATION_COLUMNS, PER_CAPITA_COLUMN)`, so an assert derived from
        # either constant is circular: it passes under a reorder of the census contract
        # and under a mid-list insert here alike, which is the exact drift
        # `CREATE OR REPLACE VIEW` cannot absorb.
        assert PER_CAPITA_COLUMNS == (
            "election_year",
            "state",
            "governing_census_year",
            "total_electoral_votes",
            "population",
            "boundary_basis",
            "coverage",
            "population_series",
            "persons_per_electoral_vote",
        )

    def test_the_ratio_is_last_so_a_later_column_can_only_append(self) -> None:
        assert PER_CAPITA_COLUMNS[-1] == PER_CAPITA_COLUMN

    def test_the_grain_is_the_tables_natural_key(self) -> None:
        assert PER_CAPITA_GRAIN == ("election_year", "state")


class TestTheSqlBuilder:
    """String-shape assertions, and they are labelled as such on purpose.

    Each one below pins a *mechanism* the integration test would otherwise be the only
    witness to, and each names the failure it is the tripwire for. None of them proves
    the SQL executes correctly — see this module's docstring.
    """

    def test_the_select_list_is_the_column_contract_in_order(self) -> None:
        sql = build_per_capita_sql()
        # Positions, not membership: a view whose columns are all present but reordered
        # is exactly what `CREATE OR REPLACE VIEW` refuses against an existing warehouse.
        positions = [sql.index(column) for column in ELECTION_POPULATION_COLUMNS]
        assert positions == sorted(positions)
        assert sql.index(PER_CAPITA_COLUMN) > max(positions)

    def test_the_numerator_is_cast_before_the_division(self) -> None:
        # Postgres integer-divides two integers, so without the cast this column would
        # be a floor-divided count -- a plausible-looking whole number, not an error.
        sql = build_per_capita_sql()
        assert "population::double precision /" in sql

    def test_the_denominator_goes_through_nullif(self) -> None:
        # Measured, not assumed: Postgres RAISES `division by zero` on the fourteen
        # zero-allotment cells, and `CREATE VIEW` succeeds while the SELECT is what
        # fails -- so an unguarded view builds green and breaks at read time.
        sql = build_per_capita_sql()
        assert "NULLIF(total_electoral_votes, 0)" in sql

    def test_it_reads_the_persisted_table_and_not_the_census_dimension(self) -> None:
        sql = build_per_capita_sql()
        assert f"FROM {CENSUS_SCHEMA}.{ELECTION_POPULATION_TABLE}" in sql
        # The whole D064 argument: re-deriving this from the census dimension would
        # re-express the governing-census calendar and the Virginia restatement, and the
        # second is not recoverable from that table at all.
        assert "census_population" not in sql

    def test_the_schema_is_a_parameter(self) -> None:
        assert "other.election_population" in build_per_capita_sql(schema="other")


class TestTheOracle:
    def test_it_divides_population_by_the_appointed_allotment(self) -> None:
        frame = build_per_capita_frame(
            _election_population([(2020, "Wyoming", 576_851, 3)])
        )
        assert frame.loc[0, PER_CAPITA_COLUMN] == pytest.approx(576_851 / 3)

    def test_a_zero_allotment_yields_NA_and_never_infinity(self) -> None:
        # numpy divides x/0 to `inf` -- a number, where the view produces an absence.
        # This is the branch the fourteen withheld-vote cells of 1864/1868 land in, and
        # an oracle returning `inf` would disagree with the live view on every one of
        # them while agreeing everywhere else.
        frame = build_per_capita_frame(
            _election_population([(1864, "Virginia", 1_219_630, 0)])
        )
        assert pd.isna(frame.loc[0, PER_CAPITA_COLUMN])
        # `pd.isna` alone does not say the value is not `inf` -- it says it is missing,
        # and an unmasked divide produces `inf`, which is NOT missing. So assert the
        # absence of an infinity directly, over the numeric projection of the column.
        as_float = pd.to_numeric(frame[PER_CAPITA_COLUMN], errors="coerce")
        assert not np.isinf(as_float.to_numpy(dtype=float)).any()

    def test_a_zero_population_over_a_zero_allotment_is_NA_not_nan_by_accident(
        self,
    ) -> None:
        # 0/0 is `nan` in numpy, which *would* compare equal to NA -- so this case would
        # pass even with the mask removed. It is here to pin that the masked result is
        # reached deliberately rather than by numpy's own accident, which is what makes
        # the test above non-redundant.
        frame = build_per_capita_frame(_election_population([(1864, "Texas", 0, 0)]))
        assert pd.isna(frame.loc[0, PER_CAPITA_COLUMN])

    def test_a_missing_population_yields_NA(self) -> None:
        frame = build_per_capita_frame(
            _election_population([(1848, "Texas", None, 4)])
        )
        assert pd.isna(frame.loc[0, PER_CAPITA_COLUMN])

    def test_it_emits_the_column_contract_in_order(self) -> None:
        frame = build_per_capita_frame(
            _election_population([(2020, "Wyoming", 576_851, 3)])
        )
        assert list(frame.columns) == list(PER_CAPITA_COLUMNS)

    def test_it_sorts_on_the_grain(self) -> None:
        frame = build_per_capita_frame(
            _election_population(
                [
                    (2020, "Wyoming", 576_851, 3),
                    (1824, "Ohio", 581_434, 16),
                    (2020, "Alaska", 733_391, 3),
                ]
            )
        )
        assert list(zip(frame.election_year, frame.state, strict=True)) == [
            (1824, "Ohio"),
            (2020, "Alaska"),
            (2020, "Wyoming"),
        ]

    def test_it_does_not_mutate_its_input(self) -> None:
        source = _election_population([(2020, "Wyoming", 576_851, 3)])
        before = list(source.columns)
        build_per_capita_frame(source)
        assert list(source.columns) == before


class TestTheFanOutGuard:
    def test_a_clean_frame_passes(self) -> None:
        # Two rows sharing a year but not a state: the grain is the pair, so a guard
        # keyed on `election_year` alone would refuse this and a guard keyed on `state`
        # alone would refuse the multi-year fixtures above.
        assert_no_fan_out(
            build_per_capita_frame(
                _election_population(
                    [(2020, "Wyoming", 576_851, 3), (2020, "Alaska", 733_391, 3)]
                )
            )
        )

    def test_a_duplicated_key_is_refused(self) -> None:
        duplicated = _election_population(
            [(2020, "Wyoming", 576_851, 3), (2020, "Wyoming", 576_851, 3)]
        )
        with pytest.raises(PerCapitaError, match="fanned out"):
            assert_no_fan_out(build_per_capita_frame(duplicated))

    def test_the_message_names_the_offending_key(self) -> None:
        duplicated = _election_population(
            [(2020, "Wyoming", 576_851, 3), (2020, "Wyoming", 576_851, 3)]
        )
        with pytest.raises(PerCapitaError, match="Wyoming"):
            assert_no_fan_out(build_per_capita_frame(duplicated))


class TestTheNullExplanationGuard:
    """AC-3's check: a NULL ratio must be readable off the row's own operands.

    There is no status column (that was decided at the plan gate), so this guard is the
    thing standing behind the claim that a consumer can always tell *why* a figure is
    missing. Both directions are tested because they fail differently — an unexplained
    NULL breaks the honest-gap promise, while a figure with no operands to compute it
    from means something synthesized a number.
    """

    def test_both_honest_null_causes_pass(self) -> None:
        frame = build_per_capita_frame(
            _election_population(
                [
                    (1848, "Texas", None, 4),  # no governing-census figure
                    (1864, "Virginia", 1_219_630, 0),  # allotment withheld
                    (2020, "Wyoming", 576_851, 3),  # computed
                ]
            )
        )
        assert_ratio_null_only_where_explained(frame)

    def test_an_unexplained_null_is_refused(self) -> None:
        frame = build_per_capita_frame(
            _election_population([(2020, "Wyoming", 576_851, 3)])
        )
        frame.loc[0, PER_CAPITA_COLUMN] = pd.NA
        with pytest.raises(PerCapitaError, match="nothing in the row explains"):
            assert_ratio_null_only_where_explained(frame)

    def test_a_figure_with_no_population_to_compute_it_from_is_refused(self) -> None:
        frame = build_per_capita_frame(
            _election_population([(1848, "Texas", None, 4)])
        )
        frame.loc[0, PER_CAPITA_COLUMN] = 123_456.0
        with pytest.raises(PerCapitaError, match="synthesized"):
            assert_ratio_null_only_where_explained(frame)

    def test_a_figure_over_a_zero_allotment_is_refused(self) -> None:
        frame = build_per_capita_frame(
            _election_population([(1864, "Virginia", 1_219_630, 0)])
        )
        frame.loc[0, PER_CAPITA_COLUMN] = 1_219_630.0
        with pytest.raises(PerCapitaError, match="synthesized"):
            assert_ratio_null_only_where_explained(frame)


class TestTheViewCreator:
    def test_it_creates_the_view_when_the_table_is_present(self) -> None:
        dbc = _ProbeDBC(exists=True)
        created = create_per_capita_view(dbc)  # type: ignore[arg-type]
        assert created is True
        assert [(schema, name) for schema, name, _, _ in dbc.views] == [
            (CENSUS_SCHEMA, PER_CAPITA_VIEW)
        ]

    def test_it_probes_the_table_it_is_about_to_read(self) -> None:
        # A probe of the wrong relation would answer a different question and still
        # return a boolean, so the relation name is what this pins.
        dbc = _ProbeDBC(exists=True)
        create_per_capita_view(dbc)  # type: ignore[arg-type]
        assert any(
            f"'{CENSUS_SCHEMA}.{ELECTION_POPULATION_TABLE}'" in query
            for query in dbc.queries
        )

    def test_it_skips_without_raising_when_the_table_is_absent(self) -> None:
        # Every clone without the private census corpus is this case, and the other view
        # builders RAISE here. The asymmetry is the decision: PV is not optional, census
        # is, and `rebuild_views` promises views over whatever facts are present.
        dbc = _ProbeDBC(exists=False)
        created = create_per_capita_view(dbc)  # type: ignore[arg-type]
        assert created is False
        assert dbc.views == []

    def test_it_replaces_by_default_so_a_rebuild_is_idempotent(self) -> None:
        dbc = _ProbeDBC(exists=True)
        create_per_capita_view(dbc)  # type: ignore[arg-type]
        assert dbc.views[0][3] is True

    def test_close_is_honoured_on_both_paths(self) -> None:
        # The skip path returns early, which is exactly where a `close=True` caller's
        # connection gets leaked if the early return forgets it.
        for exists in (True, False):
            dbc = _ProbeDBC(exists=exists)
            create_per_capita_view(dbc, close=True)  # type: ignore[arg-type]
            assert dbc.closed, f"connection left open on the exists={exists} path"

    def test_the_connection_is_left_open_by_default(self) -> None:
        for exists in (True, False):
            dbc = _ProbeDBC(exists=exists)
            create_per_capita_view(dbc)  # type: ignore[arg-type]
            assert not dbc.closed

    def test_the_created_view_carries_the_builders_sql(self) -> None:
        dbc = _ProbeDBC(exists=True)
        create_per_capita_view(dbc)  # type: ignore[arg-type]
        assert dbc.views[0][2] == build_per_capita_sql()


class TestTheReader:
    def test_it_orders_on_the_grain_so_the_oracle_is_comparable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The differential test compares row-for-row, and a view guarantees no order.

        Without the ORDER BY the integration comparison would be flaky rather than
        wrong, which is worse: it would pass on most runs.
        """
        queries: list[str] = []

        def capture(self: DBC, query: str) -> pd.DataFrame:
            queries.append(query)
            return pd.DataFrame()

        monkeypatch.setattr(DBC, "select_query_to_df", capture)
        read_per_capita(make_dbc(RecordingConnection()))
        assert queries == [
            f"SELECT * FROM {CENSUS_SCHEMA}.{PER_CAPITA_VIEW} "
            "ORDER BY election_year, state"
        ]


def test_the_module_is_not_a_top_level_module() -> None:
    """#184 planned a top-level module; a layering guard made that impossible.

    ``test_no_top_level_module_imports_a_source_subpackage`` forbids a top-level module
    importing ``usvote.census``, and this view cannot be written without that import —
    it needs the table name and the column contract, both of which are census's. Pinned
    here so the placement reads as a decision rather than as where the file happened to
    land; the module docstring carries the argument.
    """
    from usvote.census import per_capita

    assert per_capita.__name__ == "usvote.census.per_capita"


def test_it_names_no_ec_fact_table_in_code() -> None:
    """The layering invariant that makes census placement legal at all (D006/D015).

    A module under ``usvote/census/`` may not name ``dwh.votes``; this one does not need
    to, because the appointed allotment arrives as a *column* on
    ``election_population``. The repo-wide scan in ``test_layering.py`` covers every
    census module including this one — this is the local statement of why this
    particular module passes it, since "reads an EC measure without naming the EC fact"
    is the non-obvious part.
    """
    # `dwh.votes`, the relation -- not the substring "votes", which `total_electoral_
    # votes` legitimately contains. That distinction is the one the repo-wide scan makes
    # too, and a test written the loose way would fail on correct code.
    assert "dwh.votes" not in build_per_capita_sql()
