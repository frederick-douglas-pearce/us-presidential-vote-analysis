"""Live-Postgres integration tests for the #182 conformance layer.

Excluded by default via the ``integration`` marker; run with ``pytest -m integration``.

These exist for one thing the offline suite **structurally cannot do**: check the
governing-census mapping against real electoral-vote allotments.
``total_electoral_votes`` lives only in ``dwh.votes`` — the committed EC roster fixture
deliberately carries no counts (D024 §5) — so the independent oracle for
:data:`~usvote.apportionment.NO_APPORTIONMENT_CENSUSES` is reachable only from a real
warehouse. That oracle is what produced the 1920 finding in the first place, and without a
test it would be a fact recorded in a docstring and checked by nobody.

Both tests need the **local Archives corpus** (``USVOTE_EC_HTML_DIR``), because the years
that matter here (1912-1932) are not among the committed page fixtures, and they skip
cleanly when it is absent. The second additionally needs the census corpus. So neither runs
in CI, and running them locally is a merge precondition for a change to the mapping.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tests._helpers import CENSUS_POPCHANGE_XLSX, fake_state_geo
from usvote.apportionment import (
    GOVERNING_CENSUS_BY_ELECTION,
    NO_APPORTIONMENT_CENSUSES,
    governing_census_year,
)
from usvote.census.conform import (
    BOUNDARY_AT_ELECTION,
    COVERAGE_NO_GOVERNING_FIGURE,
    assert_conforms_to_spine,
    assert_election_population_shape,
    assert_no_double_count,
    assert_no_interpolated_population,
    assert_spine_states_covered,
    build_election_population,
)
from usvote.db import DBC
from usvote.spine import read_ec_participation

#: The span the 1920 gap lives in: the last election on the 1900 apportionment through the
#: first on the 1930 one.
_APPORTIONMENT_SPAN = (1908, 1912, 1916, 1920, 1924, 1928, 1932, 1936)


def _ec_corpus() -> Path:
    corpus = os.environ.get("USVOTE_EC_HTML_DIR")
    if not corpus:
        pytest.skip("USVOTE_EC_HTML_DIR not set; the 1912-1932 pages are not fixtures")
    path = Path(corpus)
    missing = [y for y in _APPORTIONMENT_SPAN if not (path / f"{y}.html").is_file()]
    if missing:
        pytest.skip(f"EC corpus is missing {missing}")
    return path


def _seed_spine(dbc: DBC, years: set[int]) -> None:
    """Load the EC spine for ``years`` from the #89 local corpus.

    ``fetch_from_corpus``, not ``fetch_from_dir``: the two read different layouts and only
    the corpus one has whole-span coverage. ``fetch_from_dir`` resolves a URL to the
    ``www_archives_gov_...`` name used by the handful of committed page fixtures, which is
    why the 1912-1932 pages are not reachable through it.
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_corpus

    run_ec_pipeline(
        dbc,
        "unused.shp",
        replace=True,
        years=years,
        fetch=fetch_from_corpus(_ec_corpus()),
        load_geo=lambda _p: fake_state_geo(),
    )


def _allotments(participation: pd.DataFrame, year: int) -> dict[str, int]:
    rows = participation.loc[
        (participation["year"] == year) & (~participation["is_total"].astype(bool))
    ]
    return {
        str(row.state): int(row.total_electoral_votes)
        for row in rows.itertuples()
        if row.state is not None and not pd.isna(row.state)
    }


@pytest.mark.integration
def test_the_allotment_change_years_match_this_mapping(
    integration_db_config: dict[str, Any],
) -> None:
    """The independent oracle for the 1920 exception — and the reason it is not a formula.

    A new apportionment shows up in the fact as a **change in per-state
    ``total_electoral_votes``**. So the mapping is right only if it changes value at exactly
    the elections where the allotment changes. This compares the two directly, over the span
    where a decade-lag formula and the truth disagree.
    """
    dbc = DBC(integration_db_config)
    try:
        _seed_spine(dbc, set(_APPORTIONMENT_SPAN))
        participation = read_ec_participation(dbc)
        allotment = {year: _allotments(participation, year) for year in _APPORTIONMENT_SPAN}
        for year in _APPORTIONMENT_SPAN:
            assert allotment[year], f"no state rows loaded for {year}"

        # The 1910 apportionment held for FIVE elections, because the 1920 census produced
        # no apportionment act. Per-state allotments are therefore identical across all of
        # them -- this is the observation the exception encodes.
        baseline = allotment[1912]
        for year in (1916, 1920, 1924, 1928):
            assert allotment[year] == baseline, (
                f"{year} differs from 1912, so the 1910 apportionment did not hold "
                f"through it — NO_APPORTIONMENT_CENSUSES is wrong"
            )

        # And it did end: the 1930 apportionment moved states at 1932. The COUNT is
        # asserted, not just the inequality, because "32 states move at 1932" is quoted as
        # evidence in `apportionment.py`, `docs/corrections.md`, `CLAUDE.md` and D060 — and
        # a named test that does not actually check the number it is offered for is a
        # citation the reader is less likely to verify (#182 review, GE-F8).
        moved = [
            state
            for state in set(allotment[1928]) & set(allotment[1932])
            if allotment[1928][state] != allotment[1932][state]
        ]
        assert len(moved) == 32, sorted(moved)
        assert allotment[1908] != baseline  # the 1900 apportionment, before the span

        # Now the direct comparison. An allotment change among *existing* states is the
        # signature of a new apportionment; the mapping must change value at exactly those
        # elections. (New states joining also change the row set, which is why this compares
        # only states present in both years.)
        for previous, current in zip(
            _APPORTIONMENT_SPAN, _APPORTIONMENT_SPAN[1:], strict=False
        ):
            shared = set(allotment[previous]) & set(allotment[current])
            changed = any(
                allotment[previous][state] != allotment[current][state]
                for state in shared
            )
            mapping_changed = (
                governing_census_year(previous) != governing_census_year(current)
            )
            assert changed == mapping_changed, (
                f"between {previous} and {current}: the fact "
                f"{'changed' if changed else 'did not change'} while the mapping "
                f"{'changed' if mapping_changed else 'did not change'} "
                f"({governing_census_year(previous)} -> "
                f"{governing_census_year(current)})"
            )
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_no_election_in_the_span_is_governed_by_a_census_that_apportioned_nothing(
    integration_db_config: dict[str, Any],
) -> None:
    """The narrow restatement of the above, kept separate because it can fail alone.

    If someone empties :data:`NO_APPORTIONMENT_CENSUSES`, 1924 and 1928 start reading 1920
    while the fact still shows the 1910 allotment. The test above would catch it via the
    change-year comparison; this says the same thing in the vocabulary of the constant, so a
    failure points straight at it.
    """
    dbc = DBC(integration_db_config)
    try:
        _seed_spine(dbc, set(_APPORTIONMENT_SPAN))
        participation = read_ec_participation(dbc)
        loaded = {int(y) for y in participation["year"].unique()}
        governed = {
            year: GOVERNING_CENSUS_BY_ELECTION[year]
            for year in loaded
            if year in GOVERNING_CENSUS_BY_ELECTION
        }
        assert governed, "no in-scope years loaded"
        assert not set(governed.values()) & NO_APPORTIONMENT_CENSUSES
        assert governed[1924] == 1910
        assert governed[1928] == 1910
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_the_conformance_guards_pass_over_a_live_warehouse(
    integration_db_config: dict[str, Any],
) -> None:
    """The guards against a real spine read out of Postgres, not an injected fixture frame.

    The offline suite drives ``build_election_population`` from a frame built in the test;
    this drives it from :func:`usvote.spine.read_ec_participation`, so a mismatch between
    what the reader returns and what the conform layer expects — a dtype, a NULL state, the
    ``is_total`` representation — fails here rather than on someone's warehouse rebuild.

    Needs the census corpus as well, since the guards are whole-series by nature.
    """
    corpus = os.environ.get("USVOTE_CENSUS_CORPUS_DIR")
    if not corpus:
        pytest.skip("USVOTE_CENSUS_CORPUS_DIR not set")
    tabs = Path(corpus) / "tabs15-65.xlsx"
    if not tabs.is_file():
        pytest.skip(f"{tabs} is not present in the corpus")

    from usvote.census.parse import parse_population_change, parse_resident_1790_1990
    from usvote.census.transform import transform_census
    from usvote.years import ec_ingest_years

    dbc = DBC(integration_db_config)
    try:
        _seed_spine(dbc, ec_ingest_years())
        participation = read_ec_participation(dbc)
        census = transform_census(
            {
                "resident_1790_1990": parse_resident_1790_1990(
                    tabs.read_bytes(), source_id="resident_1790_1990"
                ),
                "resident_1910_2020": parse_population_change(
                    CENSUS_POPCHANGE_XLSX.read_bytes(),
                    source_id="resident_1910_2020",
                ),
            },
            participation,
        )

        frame = build_election_population(census, participation)
        assert_election_population_shape(frame)
        assert_spine_states_covered(frame)
        assert_no_double_count(frame)
        assert_no_interpolated_population(frame, census)
        # The single seam the pipeline calls, so the wiring is exercised too.
        assert_conforms_to_spine(census, participation)

        # The one coverage gap, against a real spine rather than the roster fixture.
        # Was three until #234 taught the parser to read Alaska's and Hawaii's
        # transposed second table. This is the twin of the unit-side TestRealCorpus
        # assertion and has to move with it: both need USVOTE_CENSUS_CORPUS_DIR, and
        # this one also needs the integration marker, so a stale literal here goes
        # unnoticed by CI.
        gaps = {
            (int(row.election_year), str(row.state))
            for row in frame.itertuples()
            if row.coverage == COVERAGE_NO_GOVERNING_FIGURE
        }
        assert gaps == {(1848, "Texas")}

        # Virginia 1864/1868 carry the published figure, not the restated one -- the
        # double-count fix, checked against the real 0-EV Reconstruction rows.
        by_key = frame.set_index(["election_year", "state"])
        for year in (1864, 1868):
            assert by_key.loc[(year, "Virginia"), "population"] == 1_219_630
            assert by_key.loc[(year, "Virginia"), "boundary_basis"] == (
                BOUNDARY_AT_ELECTION
            )
            assert by_key.loc[(year, "Virginia"), "total_electoral_votes"] == 0
            assert by_key.loc[(year, "West Virginia"), "population"] == 376_688
    finally:
        dbc.close_connection()
