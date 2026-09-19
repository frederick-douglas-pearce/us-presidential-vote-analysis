"""Live-Postgres integration tests for the per-capita warehouse view (#184 / D064).

Excluded from the default suite by the ``integration`` marker; run with
``pytest -m integration`` against a real database.

**Why these carry unusual weight**, exactly as ``test_hybrid_views.py`` says of its own
module: :mod:`usvote.census.per_capita` holds *two* expressions of one derivation — the
SQL that drives the live view and the pandas oracle. Nothing offline can run the emitted
SQL, so the unit suite asserts the builder's **string shape** and stops there. A drift
between the two passes every offline check and leaves the view quietly wrong.

Two tests, split by what each needs:

- **``test_the_live_view_matches_the_pandas_oracle``** — the crux, and deliberately
  **not** gated on any corpus, so it runs on any integration box. It seeds the real EC
  spine from the committed page fixtures (which is what gives ``dwh.state`` its rows for
  the foreign key) and then loads a **hand-built** election-population frame shaped so
  every branch is actually exercised rather than assumed: an ordinary ratio, a
  **zero allotment**, a **missing population**, and a 39-million-scale value. The
  zero-allotment row is the one that matters most — Postgres *raises* ``division by
  zero``, so without ``NULLIF`` this test fails on the ``SELECT`` rather than on a
  comparison, and that is the failure mode being pinned.

  The frame is hand-built rather than conformed: this test is about the **ratio**, and
  the conformance layer above it has its own live test
  (``test_census_conform.py::test_the_conformance_guards_pass_over_a_live_warehouse``).
  Mixing the two would make a conformance failure read as a view failure.

- **``test_the_view_over_a_real_full_warehouse``** — the acceptance test, gated on the
  EC **and** census corpora, so it skips in CI. It builds the real 51-election series and
  pins the three population counts #184 measured, plus the named cells behind them.

Config + skip-if-unset come from the shared ``integration_db_config`` fixture.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tests._helpers import FIXTURES_DIR, fake_state_geo
from usvote.census.conform import (
    BOUNDARY_PRESENT_DAY,
    COVERAGE_COVERED,
    COVERAGE_NO_GOVERNING_FIGURE,
    ELECTION_POPULATION_COLUMNS,
    ELECTION_POPULATION_TABLE,
    build_and_validate_election_population,
)
from usvote.census.load import load_election_population
from usvote.census.per_capita import (
    PER_CAPITA_COLUMN,
    PER_CAPITA_COLUMNS,
    PER_CAPITA_VIEW,
    assert_no_fan_out,
    assert_ratio_null_only_where_explained,
    build_per_capita_frame,
    create_per_capita_view,
    read_per_capita,
)
from usvote.census.pipeline import run_census_pipeline
from usvote.census.schema import CENSUS_SCHEMA, SERIES_RESIDENT
from usvote.db import DBC
from usvote.spine import read_ec_participation

#: The two elections that carry **zero-electoral-vote states** in the real record, and
#: the only two in the whole span that do.
#:
#: **They are seeded for realism, not for the mechanism** — say so plainly, because the
#: obvious reading is wrong and would survive a "cleanup" that broke the test. The
#: zero-allotment row this test actually divides by is a hand-written literal in
#: :func:`_hand_built_frame`; seeding these years only populates ``dwh.state`` for the
#: foreign key, and ``fake_state_geo`` fills that with all 50 states + DC whatever years
#: are loaded. What must not be removed is the zero row in that frame — which is why it
#: is asserted directly below rather than left to the fixture set.
_ZERO_EV_FIXTURE_YEARS = (1864, 1868)

#: The three counts #184 measured over the real series, asserted together because they
#: must sum to the whole: 2,204 participating pairs = 2,189 computed + 1 with no
#: governing-census figure + 14 with a withheld allotment. Any one of them alone can
#: drift while the others stay right; the sum is what makes a miscount visible.
_PARTICIPATING_PAIRS = 2_204
_NO_GOVERNING_FIGURE = 1
_ZERO_ALLOTMENT = 14
_COMPUTED = 2_189


def _cells(series: pd.Series) -> list[object]:
    """Return ``series`` as plain Python values with every missing value as ``None``.

    Needed on **both** sides of the comparison, and the reason is not cosmetic:
    ``Series.where(cond, None)`` on a nullable dtype substitutes ``pd.NA``, not ``None``,
    so a list-to-list ``==`` then evaluates ``pd.NA == pd.NA`` and raises
    ``TypeError: boolean value of NA is ambiguous`` rather than comparing anything. The
    first version of this test did exactly that and CI caught it. Normalizing to ``None``
    also makes the two sides comparable across their genuinely different dtypes — psycopg2
    hands back ints and ``str``, the oracle holds ``Int64`` and ``object``.
    """
    return [None if pd.isna(value) else value for value in series]


def _seed_spine_from_fixtures(dbc: DBC, years: set[int]) -> None:
    """Load the EC spine for ``years`` from the committed page fixtures.

    This is what puts rows in ``dwh.state``, which the election-population table's
    ``state`` foreign key needs. ``fake_state_geo`` stands in for the shapefile, as every
    other integration test here does.
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    run_ec_pipeline(
        dbc,
        "unused.shp",
        replace=True,
        years=years,
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )


def _hand_built_frame() -> pd.DataFrame:
    """An election-population frame covering every branch of the ratio.

    Hand-built on purpose — see the module docstring. Each row is named for what it
    exercises, and the states are real so the foreign key resolves.
    """
    rows = [
        # An ordinary ratio.
        (2020, "Wyoming", 563_626, 3),
        # A 39-million-scale numerator: proves the cast produces a real quotient rather
        # than an integer-divided one, and that `integer` (not smallint) holds it.
        (2020, "California", 37_253_956, 55),
        # A ZERO allotment. Postgres RAISES on this row without NULLIF, so an unguarded
        # view fails the SELECT below rather than merely disagreeing.
        (1864, "Virginia", 1_219_630, 0),
        # A MISSING population, the (1848, Texas) shape: NULL propagates on its own.
        (1868, "Texas", None, 6),
    ]
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
    frame = pd.DataFrame(records, columns=list(ELECTION_POPULATION_COLUMNS))
    frame["population"] = frame["population"].astype("Int64")
    return frame


@pytest.mark.integration
def test_the_live_view_matches_the_pandas_oracle(
    integration_db_config: dict[str, Any],
) -> None:
    dbc = DBC(integration_db_config)
    try:
        _seed_spine_from_fixtures(dbc, {*_ZERO_EV_FIXTURE_YEARS, 2020})
        frame = _hand_built_frame()
        load_election_population(dbc, frame, replace=True)

        assert create_per_capita_view(dbc) is True

        # The SELECT itself is half the test: an unguarded ratio raises `division by
        # zero` here, on the 1864 Virginia row, having created the view without
        # complaint.
        live = read_per_capita(dbc)
        oracle = build_per_capita_frame(frame)

        assert list(live.columns) == list(PER_CAPITA_COLUMNS)
        assert len(live) == len(oracle)

        # Compare the ratio numerically, NULLs included, rather than by frame equality:
        # the two sides come back with different dtypes (float8 vs Float64) and a dtype
        # mismatch would mask agreement on the numbers, which is what is under test.
        live_ratio = pd.to_numeric(live[PER_CAPITA_COLUMN], errors="coerce")
        oracle_ratio = pd.to_numeric(oracle[PER_CAPITA_COLUMN], errors="coerce")
        assert list(live_ratio.isna()) == list(oracle_ratio.isna())
        for got, want in zip(
            live_ratio.dropna(), oracle_ratio.dropna(), strict=True
        ):
            assert got == pytest.approx(want)

        # And the carried columns agree cell for cell, so a view that computed the right
        # ratio beside the wrong row still fails.
        for column in ELECTION_POPULATION_COLUMNS:
            assert _cells(live[column]) == _cells(oracle[column]), column

        # The named rows, so a failure says which branch broke rather than "frames
        # differ".
        by_key = {
            (int(r.election_year), str(r.state)): r
            for r in live.itertuples()
        }
        assert by_key[(2020, "Wyoming")].persons_per_electoral_vote == pytest.approx(
            563_626 / 3
        )
        # 37,253,956 / 55 = 677,344.65..., NOT the 677,344 an integer divide gives.
        assert by_key[
            (2020, "California")
        ].persons_per_electoral_vote == pytest.approx(37_253_956 / 55)
        assert by_key[(2020, "California")].persons_per_electoral_vote != 677_344
        assert pd.isna(by_key[(1864, "Virginia")].persons_per_electoral_vote)
        assert pd.isna(by_key[(1868, "Texas")].persons_per_electoral_vote)

        assert_no_fan_out(live)
        assert_ratio_null_only_where_explained(live)
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_the_view_is_skipped_rather_than_failing_without_a_census_load(
    integration_db_config: dict[str, Any],
) -> None:
    """A public EC + MIT clone must still build, and this is the live proof.

    The offline test asserts the skip against a stub probe; this asserts it against a
    real warehouse in which ``dwh.election_population`` genuinely does not exist, which
    is the state every clone without the private census corpus is in.
    """
    dbc = DBC(integration_db_config)
    try:
        _seed_spine_from_fixtures(dbc, {2020})
        assert create_per_capita_view(dbc) is False
        absent = dbc.select_query_to_df(
            f"SELECT to_regclass('{CENSUS_SCHEMA}.{PER_CAPITA_VIEW}') AS relation"
        )
        assert absent["relation"].iloc[0] is None
    finally:
        dbc.close_connection()


def _view_exists(dbc: DBC) -> bool:
    got = dbc.select_query_to_df(
        f"SELECT to_regclass('{CENSUS_SCHEMA}.{PER_CAPITA_VIEW}') AS relation"
    )
    return got["relation"].iloc[0] is not None


def _run_load_against(
    dbc: DBC, census_corpus: Path, config: dict[str, Any], *, replace: bool
) -> None:
    """Run `python -m usvote.census load`'s body against the test connection.

    **Calls `_run_load`, not `run_census_pipeline`** — the repair for the CASCADE
    regression lives in the entry point (D064(c-bis)), so a test that called the
    pipeline would exercise everything except the fix.

    Three seams are pointed at the test database, and the third is the one that bites:
    `_run_load` builds its own `DBC` (stubbed to the caller's), closes it when done
    (neutered, so the assertions afterwards still have a connection), and resolves
    credentials from the standard libpq `PG*` variables — **not** the `USVOTE_TEST_DB_*`
    ones the integration fixture uses. Without `PGPASSWORD` set it falls through to
    `getpass` and blocks on stdin, which is exactly how this helper failed first time.
    """
    from usvote.census import __main__ as census_main

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(census_main, "DBC", lambda _config: dbc)
        monkey.setattr(type(dbc), "close_connection", lambda _self: None)
        monkey.setenv("USVOTE_CENSUS_CORPUS_DIR", str(census_corpus))
        monkey.setenv("PGHOST", str(config["host"]))
        monkey.setenv("PGPORT", str(config["port"]))
        monkey.setenv("PGDATABASE", str(config["dbname"]))
        monkey.setenv("PGUSER", str(config["user"]))
        monkey.setenv("PGPASSWORD", str(config["password"]))
        assert census_main._run_load(replace) == 0
    finally:
        monkey.undo()


def _corpus(variable: str, description: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        pytest.skip(f"{variable} not set; {description}")
    return Path(value)


@pytest.mark.integration
def test_the_view_over_a_real_full_warehouse(
    integration_db_config: dict[str, Any],
) -> None:
    """The acceptance test: the real 51-election series, with its three counts pinned.

    Gated on both corpora, so it skips in CI and running it locally is a merge
    precondition — the same posture the other whole-span census tests take.

    It pins the **partition**, not just a total: every participating pair either has a
    ratio, has no governing-census figure, or had its allotment withheld. A count that
    moves without one of the others moving is a silent change to what the series covers.
    """
    ec_corpus = _corpus("USVOTE_EC_HTML_DIR", "the 51-year EC corpus is not fixtures")
    census_corpus = _corpus(
        "USVOTE_CENSUS_CORPUS_DIR", "the census workbooks are not fixtures"
    )
    dbc = DBC(integration_db_config)
    try:
        from usvote.pipeline import run_ec_pipeline
        from usvote.scrape import fetch_from_corpus

        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            fetch=fetch_from_corpus(ec_corpus),
            load_geo=lambda _p: fake_state_geo(),
        )
        run_census_pipeline(dbc, census_corpus, replace=True)
        assert create_per_capita_view(dbc) is True

        live = read_per_capita(dbc)
        assert len(live) == _PARTICIPATING_PAIRS
        assert_no_fan_out(live)
        assert_ratio_null_only_where_explained(live)

        ratio = pd.to_numeric(live[PER_CAPITA_COLUMN], errors="coerce")
        no_figure = live["population"].isna()
        zero_allotment = pd.to_numeric(live["total_electoral_votes"]) == 0

        assert int(no_figure.sum()) == _NO_GOVERNING_FIGURE
        assert int(zero_allotment.sum()) == _ZERO_ALLOTMENT
        assert int(ratio.notna().sum()) == _COMPUTED
        # The partition: the three sets are disjoint and cover the whole series.
        assert _COMPUTED + _NO_GOVERNING_FIGURE + _ZERO_ALLOTMENT == (
            _PARTICIPATING_PAIRS
        )

        by_key = {
            (int(r.election_year), str(r.state)): r for r in live.itertuples()
        }
        # The one pair no parser change can ever fill: the Republic of Texas was not
        # enumerated by the US in 1840, and Texas cast 4 electoral votes in 1848.
        texas = by_key[(1848, "Texas")]
        assert pd.isna(texas.population)
        assert texas.coverage == COVERAGE_NO_GOVERNING_FIGURE
        assert pd.isna(texas.persons_per_electoral_vote)
        assert pd.isna(texas.population_series)

        # Virginia 1864: a population that IS known, against an allotment of zero. The
        # two null causes must stay distinguishable from the row alone, which is the
        # whole reason no status column was added.
        virginia = by_key[(1864, "Virginia")]
        assert int(virginia.population) == 1_219_630
        assert virginia.coverage == COVERAGE_COVERED
        assert int(virginia.total_electoral_votes) == 0
        assert pd.isna(virginia.persons_per_electoral_vote)

        # Every computed row says which series its denominator came from (AC-2).
        computed = live.loc[ratio.notna()]
        assert set(computed["population_series"]) == {SERIES_RESIDENT}

        # A cardinality check, and stated as one: the view returns exactly as many
        # rows as a fresh build of the election-grain frame, so nothing fanned out
        # or went missing between what the pipeline validated and what the view
        # reads. Row *identity* is carried elsewhere — the per-cell asserts above
        # (Texas 1848, Virginia 1864) and the differential test against the pandas
        # oracle in this module — not by the length comparison below.
        expected = build_and_validate_election_population(
            dbc.select_query_to_df(
                f"SELECT * FROM {CENSUS_SCHEMA}.census_population"
            ),
            read_ec_participation(dbc),
        )
        assert len(expected) == len(live)
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_a_replace_refresh_does_not_leave_the_view_dropped(
    integration_db_config: dict[str, Any],
) -> None:
    """The regression `--replace` introduced, and the order here is the whole test.

    `DBC.create_table(replace=True)` issues `DROP TABLE ... CASCADE`, and the view
    depends on the table, so a `--replace` refresh takes the view with it. The repair is
    in `usvote/census/__main__.py::_run_load`, which rebuilds the view after the
    pipeline returns (D064(c-bis)).

    **The view must already exist when the replace runs, or this test proves nothing.**
    Its first version created the view only *after* both replace loads, so no
    pre-existing view was ever exposed to the CASCADE — it asserted the state it had
    just constructed, while its docstring claimed to catch a rebuild that dropped the
    view. The #184 review caught that; the reordering below is the fix.

    It drives the **entry point**, not the pipeline, because that is where the repair
    lives and where a real operator's `python -m usvote.census load --replace` goes.
    """
    ec_corpus = _corpus("USVOTE_EC_HTML_DIR", "the 51-year EC corpus is not fixtures")
    census_corpus = _corpus(
        "USVOTE_CENSUS_CORPUS_DIR", "the census workbooks are not fixtures"
    )
    dbc = DBC(integration_db_config)
    try:
        from usvote.pipeline import run_ec_pipeline
        from usvote.scrape import fetch_from_corpus

        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            fetch=fetch_from_corpus(ec_corpus),
            load_geo=lambda _p: fake_state_geo(),
        )
        run_census_pipeline(dbc, census_corpus, replace=True)

        # The view EXISTS before the refresh. This line is the test.
        assert create_per_capita_view(dbc) is True
        assert _view_exists(dbc), "precondition: the view should be in place"

        _run_load_against(dbc, census_corpus, integration_db_config, replace=True)

        assert _view_exists(dbc), (
            "a --replace refresh dropped dwh.election_per_capita via CASCADE and left "
            "it dropped — the command exits 0, so nothing else would notice"
        )
        # And the rebuilt view reads, which a view over a re-created table only does if
        # it was genuinely recreated rather than merely still catalogued.
        assert len(read_per_capita(dbc)) == _PARTICIPATING_PAIRS

        # The other half: `replace` really is forwarded to the second loader, or the
        # refresh would append 2,204 rows again and die on the natural key.
        rows = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {CENSUS_SCHEMA}.{ELECTION_POPULATION_TABLE}"
        )
        assert int(rows["n"].iloc[0]) == _PARTICIPATING_PAIRS
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_a_plain_load_creates_the_view_without_usvote_all(
    integration_db_config: dict[str, Any],
) -> None:
    """The second half of the same defect: a plain `census load` never built the view.

    Before the repair the view existed only after `python -m usvote all`, so an operator
    who loaded census on its own got `election_population` with nothing over it and no
    error saying so.
    """
    ec_corpus = _corpus("USVOTE_EC_HTML_DIR", "the 51-year EC corpus is not fixtures")
    census_corpus = _corpus(
        "USVOTE_CENSUS_CORPUS_DIR", "the census workbooks are not fixtures"
    )
    dbc = DBC(integration_db_config)
    try:
        from usvote.pipeline import run_ec_pipeline
        from usvote.scrape import fetch_from_corpus

        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            fetch=fetch_from_corpus(ec_corpus),
            load_geo=lambda _p: fake_state_geo(),
        )
        assert not _view_exists(dbc), "precondition: no view before the census load"

        _run_load_against(dbc, census_corpus, integration_db_config, replace=False)

        assert _view_exists(dbc), (
            "a standalone census load left no per-capita view; it should not take a "
            "whole `python -m usvote all` build to get one"
        )
        assert len(read_per_capita(dbc)) == _PARTICIPATING_PAIRS
    finally:
        dbc.close_connection()
