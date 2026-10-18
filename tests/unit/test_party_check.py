"""Unit tests for ``usvote.party_check``, the MIT party check (#385, D077).

Each branch of :func:`assert_mit_party_agrees` fires on a bad frame and passes on a
good one. The SQL reads run against a live warehouse in the integration tests that
build through ``run_warehouse``, which calls the check: ``tests/integration/
test_ec_pv_join.py``, ``test_hybrid_views.py`` and ``test_snapshot_build.py``. AC4's
automated coverage, the check passing on the full current warehouse, is
``test_hybrid_views.py::test_hybrid_views_over_a_real_full_warehouse``, which builds
every year and needs the local corpora, so it cannot run in CI.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from usvote.mit.transform import EC_GETTER_PARTIES
from usvote.party import NOMINATING_PARTIES
from usvote.party_check import (
    MIT_PARTY_COMPARISON_COLUMNS,
    MIT_PARTY_CROSSWALK,
    MIT_PARTY_EXCEPTIONS,
    MIT_PARTY_FLOOR_COLUMNS,
    PartyCheckError,
    assert_db_mit_party_agrees,
    assert_mit_party_agrees,
)


def _comparison(*rows: tuple[Any, ...]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(MIT_PARTY_COMPARISON_COLUMNS))


def _floor(*rows: tuple[int, int, str]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(MIT_PARTY_FLOOR_COLUMNS))


#: Two candidates in two states, both sides agreeing.
CLEAN = _comparison(
    (2016, "Ohio", "Donald J. Trump", "REPUBLICAN", 1, "republican"),
    (2016, "Ohio", "Hillary Clinton", "DEMOCRAT", 2, "democratic"),
    (2016, "Iowa", "Donald J. Trump", "REPUBLICAN", 1, "republican"),
    (2016, "Iowa", "Hillary Clinton", "DEMOCRAT", 2, "democratic"),
)
FLOOR = _floor((2016, 1, "Donald J. Trump"), (2016, 2, "Hillary Clinton"))


def test_the_crosswalk_keys_are_mits_own_party_scope() -> None:
    """Pinned to MIT's constant so a new D019 spelling cannot be added on one side."""
    assert set(MIT_PARTY_CROSSWALK) == set(EC_GETTER_PARTIES)
    assert set(MIT_PARTY_CROSSWALK.values()) <= NOMINATING_PARTIES


def test_the_exceptions_seam_is_empty() -> None:
    """#384 found no disagreement from 1976 on (research doc §9)."""
    assert dict(MIT_PARTY_EXCEPTIONS) == {}


def test_agreeing_rows_pass() -> None:
    assert_mit_party_agrees(CLEAN, FLOOR, {2016})


# --- agreement ---------------------------------------------------------------


def test_a_one_state_disagreement_fails() -> None:
    """Per (year, state, candidate): one state is enough, which a rollup could hide."""
    bad = CLEAN.copy()
    bad.loc[2, "mit_party"] = "DEMOCRAT"
    with pytest.raises(
        PartyCheckError, match=r"disagrees .*\(2016, 'Iowa', 'Donald J. Trump'\)"
    ):
        assert_mit_party_agrees(bad, FLOOR, {2016})


def test_a_named_exception_lets_a_disagreement_pass() -> None:
    bad = CLEAN.copy()
    bad.loc[2, "mit_party"] = "DEMOCRAT"
    assert_mit_party_agrees(
        bad,
        FLOOR,
        {2016},
        exceptions={(2016, "Iowa", "Donald J. Trump"): "a sourced reason"},
    )


def test_a_joint_code_agrees_with_any_of_its_components() -> None:
    joint = _comparison(
        (2016, "Ohio", "Pat Doe", "DEMOCRAT", 1, "democratic_populist"),
    )
    assert_mit_party_agrees(joint, _floor((2016, 1, "Pat Doe")), {2016})


def test_a_stale_exception_fails() -> None:
    with pytest.raises(PartyCheckError, match="match no disagreeing row"):
        assert_mit_party_agrees(
            CLEAN,
            FLOOR,
            {2016},
            exceptions={(2016, "Ohio", "Hillary Clinton"): "no longer true"},
        )


def test_an_exception_in_a_year_mit_did_not_load_is_not_stale() -> None:
    assert_mit_party_agrees(
        CLEAN, FLOOR, {2016}, exceptions={(2020, "Ohio", "X"): "another year"}
    )


# --- crosswalk closure -------------------------------------------------------


def test_an_mit_value_outside_the_crosswalk_fails() -> None:
    bad = CLEAN.copy()
    bad.loc[0, "mit_party"] = "LIBERTARIAN"
    with pytest.raises(PartyCheckError, match="outside the crosswalk"):
        assert_mit_party_agrees(bad, FLOOR, {2016})


def test_an_unmapped_mit_value_fails_even_with_no_nominating_party() -> None:
    """Closure is checked before rows null on one side are skipped."""
    unmatched = _comparison(
        *CLEAN.itertuples(index=False, name=None),
        (2016, "Utah", "Evan McMullin", "INDEPENDENT", None, None),
    )
    with pytest.raises(PartyCheckError, match="INDEPENDENT"):
        assert_mit_party_agrees(unmatched, FLOOR, {2016})


def test_rows_null_on_either_side_are_skipped() -> None:
    with_nulls = _comparison(
        *CLEAN.itertuples(index=False, name=None),
        (2016, "Utah", "Evan McMullin", None, 7, "no_nomination"),
        (2016, "Utah", "Someone Else", "DEMOCRAT", None, None),
    )
    assert_mit_party_agrees(with_nulls, FLOOR, {2016})


# --- the floor ---------------------------------------------------------------


def test_an_archives_candidate_year_with_no_compared_row_fails() -> None:
    """A name join that silently lost a candidate's MIT rows fails here."""
    lost = CLEAN[CLEAN["candidate"] != "Hillary Clinton"]
    with pytest.raises(PartyCheckError, match=r"no MIT row compared .*Hillary Clinton"):
        assert_mit_party_agrees(lost, FLOOR, {2016})


def test_a_floor_row_compared_in_one_state_passes() -> None:
    one_state = CLEAN[CLEAN["state"] == "Ohio"]
    assert_mit_party_agrees(one_state, FLOOR, {2016})


def test_a_build_with_1976_on_archives_rows_and_nothing_compared_fails() -> None:
    with pytest.raises(PartyCheckError, match="compared no MIT row"):
        assert_mit_party_agrees(_comparison(), _floor(), {2016, 2020})


def test_a_build_with_no_1976_on_archives_rows_may_compare_nothing() -> None:
    assert_mit_party_agrees(_comparison(), _floor(), set())


# --- the DB wrapper ----------------------------------------------------------


class _StubDBC:
    """Answers the three reads by which table their ``FROM`` names first."""

    def __init__(self, comparison: pd.DataFrame, floor: pd.DataFrame, years: set[int]):
        self.queries: list[str] = []
        self._comparison = comparison
        self._floor = floor
        self._years = years

    def select_query_to_df(self, query: str) -> pd.DataFrame:
        self.queries.append(query)
        if query.startswith("SELECT p.year"):
            return self._comparison
        if query.startswith("SELECT cp.year"):
            return self._floor
        return pd.DataFrame({"year": sorted(self._years)})


def test_the_db_wrapper_reads_the_floor_by_its_own_query() -> None:
    stub = _StubDBC(CLEAN, FLOOR, {2016})
    assert_db_mit_party_agrees(stub)  # type: ignore[arg-type]

    comparison, floor, years = stub.queries
    assert "LEFT JOIN dwh.candidate c" in comparison
    assert "WHERE p.source = 'MIT'" in comparison
    # The floor is a separate read of candidate_party, scoped to the years MIT loaded.
    assert "FROM dwh.candidate_party cp" in floor
    assert "nominating_party_source = 'NARA'" in floor
    assert "cp.year >= 1976" in floor
    assert "FROM dwh.pv_votes WHERE source = 'MIT'" in floor
    assert "year >= 1976" in years


def test_the_db_wrapper_raises_on_a_disagreement() -> None:
    bad = CLEAN.copy()
    bad.loc[0, "mit_party"] = "DEMOCRAT"
    with pytest.raises(PartyCheckError):
        assert_db_mit_party_agrees(_StubDBC(bad, FLOOR, {2016}))  # type: ignore[arg-type]
