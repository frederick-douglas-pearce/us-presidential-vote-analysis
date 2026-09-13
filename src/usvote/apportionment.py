"""Which apportionment governed which election — the election→census bridge (#182).

The census dimension :mod:`usvote.census` loaded in #181 is keyed on **census** years.
Every consumer in E10 — #183's seat reconciliation, #184's persons-per-electoral-vote —
is keyed on **election** years. This module is the bridge, and the bridge is not
arithmetic: it is a fact about apportionment law, with one exception that no formula
predicts.

**Why this is top-level and not under ``usvote/census/``** (#182 architect review, C1).
Everything here is keyed on the **election** year and imports only :mod:`usvote.years`;
nothing in it knows anything about census *population*, file layouts, or the Bureau.
"Which apportionment was in force" is an election-domain fact, which makes this module a
member of the :mod:`usvote.years` / :mod:`usvote.count_status` family — the
dependency-free EC-domain modules that sit *underneath* their consumers — rather than a
stage of a source subpackage. Placed inside ``usvote/census/`` it would create a real
layering inversion the first time a non-census consumer needed it: a warehouse query, or
#183 written as an EC-side reconciliation, would have to import
``usvote.census.apportionment`` from the EC side, which is the direction D015 forbids.
Top-level placement makes that import always legal.

The issue's Implementation Notes suggested a ``usvote/census/`` module "in the
dependency-free spirit of ``usvote/years.py``". This keeps the spirit — dependency-free,
read by import, never re-deriving the lag — and changes only the directory. Recorded as
a deliberate deviation, approved by the human at the #182 plan gate.

**This module must stay dependency-free** (stdlib + :mod:`usvote.years`, which is itself
dependency-free): no pandas, no DB, no network. That property is what lets any consumer
import it.
"""

from __future__ import annotations

from usvote.years import ec_ingest_years

#: Years between a census and the first presidential election its apportionment governs.
#: A census taken in year *C* is apportioned into the House elected in the general
#: election of *C+2* (seated the following January), so it governs presidential
#: elections from *C+2* onward. The lag is **2, not 0 and not 4**: where *C+2* is itself
#: a presidential year the new apportionment applies to that very election — 2012 ran on
#: the 2010 census, and Texas went from 34 to 38 electoral votes that year.
APPORTIONMENT_LAG_YEARS = 2

#: The first census that produced an apportionment. Before it, the original allotment
#: was written into the Constitution itself (Art. I, §2, cl. 3), not derived from an
#: enumeration — which is why :func:`governing_census_year` raises below this rather
#: than returning a floor value.
FIRST_APPORTIONMENT_CENSUS = 1790

#: Censuses that produced **no** apportionment, so they never govern an election. **1920
#: is the only one in US history, and it is the whole reason this module exists.**
#: Congress failed to pass an apportionment act after the 1920 census — the sole such
#: failure — so the 1910 apportionment stayed in force for a second decade. The
#: Reapportionment Act of 1929 (ch. 28, 46 Stat. 21) then made apportionment automatic
#: from the 1930 census, which first governed the 1932 election.
#:
#: The consequence is that elections **1924 and 1928 are governed by the 1910 census**,
#: and any decade-lag formula gets both of them wrong. This repo's own fact table shows
#: it: per-state ``total_electoral_votes`` is identical across 1912, 1916, 1920, 1924
#: and 1928, and 32 states move at 1932. The integration test
#: ``test_the_allotment_change_years_match_this_mapping`` is that cross-check, and it is
#: an integration test because the counts exist only in ``dwh.votes``: the committed EC
#: roster fixture deliberately carries no electoral-vote counts (D024 §5), so no offline
#: fixture can show it.
#: Public-domain citations, so this constant ships regardless of any source's licensing,
#: exactly as :mod:`usvote.pv.absences`' citations do.
NO_APPORTIONMENT_CENSUSES: frozenset[int] = frozenset({1920})


class ApportionmentError(RuntimeError):
    """Raised when no apportionment can have governed the requested election."""


def governing_census_year(election_year: int) -> int:
    """Return the census year whose apportionment governed ``election_year``.

    The most recent census at or before ``election_year - APPORTIONMENT_LAG_YEARS`` that
    actually produced an apportionment (:data:`NO_APPORTIONMENT_CENSUSES`).

    **Two wrong-easy-answers this deliberately is not.** Nearest-decade rounding maps
    2020 to 2020; the 2020 census was not apportioned until April 2021 and first
    governed **2024**, so the answer is 2010. And a bare decade lag with no exception
    set maps 1924 to 1920; the 1920 census governed nothing, so the answer is 1910.

    Raises :class:`ApportionmentError` for an election no apportionment governed — 1789,
    whose allotment came from Art. I, §2 of the Constitution rather than from an
    enumeration.
    """
    if election_year < FIRST_APPORTIONMENT_CENSUS + APPORTIONMENT_LAG_YEARS:
        raise ApportionmentError(
            f"No census apportionment governed the {election_year} election: the first "
            f"census was {FIRST_APPORTIONMENT_CENSUS} and its apportionment first "
            f"governed {FIRST_APPORTIONMENT_CENSUS + APPORTIONMENT_LAG_YEARS}. The "
            f"1789 allotment was fixed by Art. I, §2, cl. 3, not by an enumeration."
        )
    candidate = ((election_year - APPORTIONMENT_LAG_YEARS) // 10) * 10
    while candidate in NO_APPORTIONMENT_CENSUSES:
        candidate -= 10
        if candidate < FIRST_APPORTIONMENT_CENSUS:  # pragma: no cover
            raise ApportionmentError(
                f"Every census at or before {election_year - APPORTIONMENT_LAG_YEARS} "
                f"is in NO_APPORTIONMENT_CENSUSES; no apportionment governed "
                f"{election_year}."
            )
    return candidate


def governing_census_by_election(
    years: frozenset[int] | set[int] | None = None,
) -> dict[int, int]:
    """Return ``{election_year: governing_census_year}`` over ``years``.

    Defaults to the EC spine's own ingest scope (:func:`usvote.years.ec_ingest_years`),
    so a year admitted to the spine later — the pre-12th-Amendment epic (D010) is the
    next candidate — appears here with no edit. ``years`` is injectable for testing.
    """
    scope = ec_ingest_years() if years is None else years
    return {year: governing_census_year(year) for year in sorted(scope)}


#: ``{election_year: governing_census_year}`` over the default EC ingest scope.
#:
#: Materialized at import so #183 and #184 read the mapping rather than re-deriving the
#: lag — which is what the issue's Implementation Notes ask for, and what stops the 1920
#: exception being reimplemented (or forgotten) per consumer.
GOVERNING_CENSUS_BY_ELECTION: dict[int, int] = governing_census_by_election()
