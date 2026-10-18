"""The MIT party check: MIT's party must agree with the nominating party (#385, D077).

D077 amends D018: the authority for a candidate's party in an election is
``dwh.candidate_party``, and MIT's ``party`` — the plurality ballot line in each state
(D018), scoped to the D019 EC-getter set — is a **check, not a source**. MIT adds no
rows and fills no gaps. From 1976 on, the build fails if a state's MIT row names a
party that disagrees with the candidate-year's nominating party, unless that state is
a named exception with its reason.

**Grain: per (year, state, candidate)**, over the raw ``dwh.pv_votes`` MIT rows rather
than any rollup (research doc §9): a national rollup resolves party by ``min``, which
could hide a one-state disagreement.

**What it can and cannot see.** MIT's transform keeps only the D019 parties
(``usvote.mit.transform._filter_ec_getters``), so a state where a candidate ran on
another line arrives as a *missing* row, not a disagreeing one. The check's power is
therefore a Democratic/Republican swap, plus the floor below. MIT's year completeness
is :func:`usvote.mit.validate.assert_mit_year_coverage`'s job (D052); this check's floor
guards the join, not the source.

**Why a top-level module.** It reads ``dwh.pv_votes`` and the EC star schema by SQL
name and imports nothing from ``usvote.mit`` (D015): the MIT spellings it needs are
the two in :data:`MIT_PARTY_CROSSWALK`, pinned to MIT's own constant by a test. The
precedent is :mod:`usvote.spine`. It is called from the composition root,
:func:`usvote.warehouse.run_warehouse`.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.party import PARTY_COMPONENTS, SOURCE_ARCHIVES
from usvote.pv.source import MIT_PV_YEAR_MIN, SOURCE_MIT

#: MIT's party spellings, mapped to the vocabulary code each names. Closed: an MIT
#: value outside it fails the check rather than being skipped, so a new MIT spelling
#: cannot pass unexamined. Its keys equal ``usvote.mit.transform.EC_GETTER_PARTIES``
#: (``tests/unit/test_party_check.py`` pins that).
MIT_PARTY_CROSSWALK: Mapping[str, str] = {
    "DEMOCRAT": "democratic",
    "REPUBLICAN": "republican",
}

#: States where MIT's party may legitimately differ from the nominating party, keyed
#: ``(year, state, candidate name)`` with the reason as the value. Empty: #384 found
#: no disagreement in any 1976+ Table 1 row (research doc §9). A new entry needs its
#: provenance, like any correction.
MIT_PARTY_EXCEPTIONS: Mapping[tuple[int, str, str], str] = {}

#: The comparison frame's columns, one row per MIT ``(year, state, candidate)``.
MIT_PARTY_COMPARISON_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "candidate",
    "mit_party",
    "candidate_id",
    "nominating_party",
)

#: The floor frame's columns: the candidate-years that must be compared at least once.
MIT_PARTY_FLOOR_COLUMNS: tuple[str, ...] = ("year", "candidate_id", "candidate")


class PartyCheckError(RuntimeError):
    """Raised when MIT's party disagrees with the nominating party."""


def read_mit_party_comparison(dbc: DBC, *, schema: str = SCHEMA) -> pd.DataFrame:
    """Read every MIT ``(year, state, candidate)`` row beside its nominating party.

    A **left** join from the MIT side, so an MIT row whose candidate or candidate-year
    has no match still arrives (with nulls) for the crosswalk check to see.
    """
    df = dbc.select_query_to_df(
        "SELECT p.year, p.state, p.candidate, p.party AS mit_party, "
        "c.candidate_id, cp.nominating_party "
        f"FROM {schema}.pv_votes p "
        f"LEFT JOIN {schema}.candidate c ON c.name = p.candidate "
        f"LEFT JOIN {schema}.candidate_party cp "
        "ON cp.year = p.year AND cp.candidate_id = c.candidate_id "
        f"WHERE p.source = '{SOURCE_MIT}'"
    )
    return df[list(MIT_PARTY_COMPARISON_COLUMNS)]


def read_mit_party_floor(dbc: DBC, *, schema: str = SCHEMA) -> pd.DataFrame:
    """Read the Archives candidate-years the check must compare at least once.

    Every ``NARA`` row of ``dwh.candidate_party`` from :data:`MIT_PV_YEAR_MIN` on, in a
    year MIT loaded. A query of its own rather than a projection of the comparison
    frame, so a join that silently loses rows cannot also shrink what it is held to.
    Scoped to MIT's loaded years so a deliberately partial build (the integration
    tests load one MIT state of one year) is held only to what it loaded.
    """
    df = dbc.select_query_to_df(
        "SELECT cp.year, cp.candidate_id, c.name AS candidate "
        f"FROM {schema}.candidate_party cp "
        f"JOIN {schema}.candidate c ON c.candidate_id = cp.candidate_id "
        f"WHERE cp.nominating_party_source = '{SOURCE_ARCHIVES}' "
        f"AND cp.year >= {MIT_PV_YEAR_MIN} "
        "AND cp.year IN (SELECT DISTINCT year "
        f"FROM {schema}.pv_votes WHERE source = '{SOURCE_MIT}')"
    )
    return df[list(MIT_PARTY_FLOOR_COLUMNS)]


def read_archives_years_from_mit_floor(
    dbc: DBC, *, schema: str = SCHEMA
) -> set[int]:
    """The years from :data:`MIT_PV_YEAR_MIN` on that carry an Archives party row."""
    df = dbc.select_query_to_df(
        f"SELECT DISTINCT year FROM {schema}.candidate_party "
        f"WHERE nominating_party_source = '{SOURCE_ARCHIVES}' "
        f"AND year >= {MIT_PV_YEAR_MIN}"
    )
    return {int(year) for year in df["year"]}


def assert_mit_party_agrees(
    comparison: pd.DataFrame,
    floor: pd.DataFrame,
    archives_years_from_mit_floor: set[int],
    *,
    crosswalk: Mapping[str, str] = MIT_PARTY_CROSSWALK,
    exceptions: Mapping[tuple[int, str, str], str] = MIT_PARTY_EXCEPTIONS,
) -> None:
    """Raise unless every comparable MIT row agrees with the nominating party.

    In order:

    1. **Crosswalk closure** — every non-null MIT party is a crosswalk key. Checked
       before any row is skipped, so an unknown spelling on a row with no nominating
       party still fails.
    2. **Agreement** — on rows non-null on both sides, the crosswalked code equals the
       nominating party or is one of its components (1872's joint code would pass
       for its Democratic half; none prints from 1976 on). A disagreement passes only
       as a key of ``exceptions``.
    3. **No stale exception** — an exception key in a compared year must match a
       disagreeing row.
    4. **Floor** — every ``floor`` candidate-year has at least one compared row.
    5. **Not vacuous** — a build with an Archives row from 1976 on must compare at
       least one row.
    """
    mit = comparison["mit_party"]
    unmapped = sorted(
        (int(r.year), r.state, r.candidate, r.mit_party)
        for r in comparison[mit.notna() & ~mit.isin(list(crosswalk))].itertuples()
    )
    if unmapped:
        raise PartyCheckError(
            f"MIT party values outside the crosswalk {sorted(crosswalk)}: {unmapped}"
        )

    compared = comparison[mit.notna() & comparison["nominating_party"].notna()]
    disagreeing: set[tuple[int, str, str]] = set()
    for r in compared.itertuples():
        code = crosswalk[r.mit_party]
        nominating = str(r.nominating_party)
        if code != nominating and code not in PARTY_COMPONENTS.get(nominating, ()):
            disagreeing.add((int(r.year), str(r.state), str(r.candidate)))
    unexplained = sorted(disagreeing - set(exceptions))
    if unexplained:
        raise PartyCheckError(
            "MIT's party disagrees with the nominating party, with no named exception "
            f"(year, state, candidate): {unexplained}"
        )

    compared_years = {int(year) for year in compared["year"]}
    stale = sorted(
        key for key in exceptions if key[0] in compared_years and key not in disagreeing
    )
    if stale:
        raise PartyCheckError(
            f"MIT party exceptions that match no disagreeing row: {stale}"
        )

    compared_keys = {
        (int(year), int(candidate_id))
        for year, candidate_id in zip(
            compared["year"], compared["candidate_id"], strict=True
        )
    }
    uncompared = sorted(
        (int(r.year), str(r.candidate))
        for r in floor.itertuples()
        if (int(r.year), int(r.candidate_id)) not in compared_keys
    )
    if uncompared:
        raise PartyCheckError(
            "Archives candidate-years in a year MIT loaded with no MIT row compared "
            f"(year, candidate): {uncompared}. Check the name join between "
            "dwh.pv_votes and dwh.candidate."
        )

    if archives_years_from_mit_floor and compared.empty:
        raise PartyCheckError(
            f"the build has Archives party rows from {MIT_PV_YEAR_MIN} on "
            f"({sorted(archives_years_from_mit_floor)}) but compared no MIT row"
        )


def assert_db_mit_party_agrees(dbc: DBC, *, schema: str = SCHEMA) -> None:
    """Run :func:`assert_mit_party_agrees` over the loaded warehouse."""
    assert_mit_party_agrees(
        read_mit_party_comparison(dbc, schema=schema),
        read_mit_party_floor(dbc, schema=schema),
        read_archives_years_from_mit_floor(dbc, schema=schema),
    )
