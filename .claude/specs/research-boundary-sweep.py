"""#208 — boundary sweep: the empirical half of `research-boundary-sweep.md` §4.

Runs fully **offline** against the two local corpora — no network, no database:

    USVOTE_CENSUS_CORPUS_DIR/tabs15-65.xlsx   (resident population 1790-1990)
    USVOTE_EC_HTML_DIR/<year>.html            (the Archives corpus, #89)

    uv run python .claude/specs/research-boundary-sweep.py

**Every check ASSERTS its headline and exits non-zero on failure.** An earlier
revision printed its results and asserted nothing, so a degraded input would have
produced a plausible table rather than an error — the exact failure mode this
report was filed to stop. Three checks, in the order §4 reports them:

A. **National-total reconciliation.** Every census's 51 file areas against a
   published US total. Its power is deliberately narrow and §4.2 says so: a
   state-to-state transfer is *conservative* at the national level, so this can
   NOT surface an unlisted reassignment between two states — the Virginia/West
   Virginia case passes it silently. What it does establish is that the
   jurisdiction set is complete and non-duplicated, and that no population
   crossed the *US* boundary unaccounted.

B. **Parent/child reconciliation.** The #180 technique, extended with the
   Alexandria term, and checked against **independently published** enumerated
   series rather than against itself (§5.2-5.4).

C. **Rank diagnostic.** Virginia's persons-per-electoral-vote rank with and
   without the Alexandria term, across the seven elections the 1820/1830/1840
   censuses govern. Every state excluded from a ranking is named and counted.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from usvote import parse, scrape
from usvote.apportionment import governing_census_year
from usvote.census.parse import parse_resident_1790_1990
from usvote.parse import TOTALS_ROW_STATE

_FALLBACK = Path.home() / "Documents/Projects/data/presidential_vote_analysis"

CENSUS_FILE = (
    Path(os.environ.get("USVOTE_CENSUS_CORPUS_DIR", str(_FALLBACK / "census_corpus")))
    / "tabs15-65.xlsx"
)
EC_DIR = os.environ.get("USVOTE_EC_HTML_DIR", str(_FALLBACK / "ec_raw"))

#: The 51 areas the workbook carries (50 states + DC), asserted rather than assumed.
EXPECTED_AREAS = 51

#: Alexandria County, D.C., per census — **published**, not derived. Bureau of the
#: Census, *Population of States and Counties of the United States: 1790 to 1990*
#: (1996), Virginia **Note 2**. Corroborated three ways in §5: the same volume's
#: District note (``ENUMERATED_DC`` below, minus the file's DC series), its
#: ``Arlington`` county row, and the original enumerations for 1800/1820/1830/1840.
#:
#: **1810 is the one cell with a published disagreement.** Virginia Note 2 prints
#: ``8.852``; the volume's own District note and its Arlington county row both give
#: **8,552**, which is also the only value satisfying *both* identities in check B.
#: 8,552 is used, and the disagreement is recorded rather than silently resolved
#: (§5.3). It governs elections 1812-1820 only, all outside the EC span.
ALEXANDRIA = {1800: 5_949, 1810: 8_552, 1820: 9_703, 1830: 9_573, 1840: 9_967}

#: District of Columbia **as then constituted** (whole District, including
#: Alexandria County). Same volume, District of Columbia note: "Population of the
#: District as then constituted: 1800: 14,093; 1810: 24,023; 1820: 33,039; 1830:
#: 39,834; 1840: 43,712." This is the **independent** series that makes check B's
#: second identity a test rather than a restatement of the first.
ENUMERATED_DC = {
    1800: 14_093, 1810: 24_023, 1820: 33_039, 1830: 39_834, 1840: 43_712,
}

#: Virginia **as then defined** — on the borders in force, i.e. including the
#: counties that became West Virginia and excluding Alexandria. 1790/1850/1860 are
#: the three #180 verified against separately-published totals; 1800-1840 are
#: composed from the volume's two published component series (§5.4).
#:
#: **1810 and 1820 each have two published Bureau values** (§5.4): the original
#: returns give 974,600 and 1,065,366, while the 1850 Seventh Census restatement
#: gives 974,622 and 1,065,379 — differing by 22 and 13. The file's components
#: reproduce the **original-return** pair, so that is the pair used here.
ENUMERATED_VA = {
    1790: 747_610, 1800: 880_200, 1810: 974_600, 1820: 1_065_366,
    1830: 1_211_405, 1840: 1_239_797, 1850: 1_421_661, 1860: 1_596_318,
}

#: Published total US population. 1790-1900 read from census.gov CPH-2 "Table 4.
#: Population: 1790 to 1990"; 1910-1990 from the census.gov population-change
#: table. The two publications disagree for 1910-1940 (§4.2) — these are the
#: modern series, which the file tracks exactly.
NATIONAL = {
    1790: 3_929_214, 1800: 5_308_483, 1810: 7_239_881, 1820: 9_638_453,
    1830: 12_860_702, 1840: 17_063_353, 1850: 23_191_876, 1860: 31_443_321,
    1870: 38_558_371, 1880: 50_189_209, 1890: 62_979_766, 1900: 76_212_168,
    1910: 92_228_531, 1920: 106_021_568, 1930: 123_202_660, 1940: 132_165_129,
    1950: 151_325_798, 1960: 179_323_175, 1970: 203_211_926, 1980: 226_545_805,
    1990: 248_709_873,
}

#: Alaska's off-cycle censuses. The parser emits them faithfully and
#: ``SOURCE_SPANS`` drops them (D061); the 1930 and 1940 national totals only
#: reconcile once they are added back.
OFF_CYCLE = {1930: 1929, 1940: 1939}

#: The elections the Alexandria-affected censuses govern. Derived rather than
#: asserted, so it cannot drift from ``ALEXANDRIA`` (an earlier revision hardcoded
#: six and the constant held seven).
ELECTIONS = tuple(
    y for y in range(1824, 1861, 4) if governing_census_year(y) in ALEXANDRIA
)

Population = dict[str, dict[int, int | None]]


class CheckFailed(AssertionError):
    """A headline this script asserts did not hold."""


def load_population() -> Population:
    rows = parse_resident_1790_1990(
        CENSUS_FILE.read_bytes(), source_id="resident_1790_1990"
    )
    pop: Population = {}
    for row in rows:
        pop.setdefault(row.area, {})[row.census_year] = row.population
    if len(pop) != EXPECTED_AREAS:
        raise CheckFailed(
            f"workbook carries {len(pop)} areas, expected {EXPECTED_AREAS}"
        )
    return pop


def load_electoral_votes(
    years: tuple[int, ...], state_names: set[str]
) -> dict[int, dict[str, int]]:
    """Per-state ``total_electoral_votes`` for ``years``, from the local corpus.

    The Archives' own totals row is dropped **by name**. It was previously removed
    only because the census workbook has no sheet called ``Totals`` — an accident
    that would have put a year's national total into the ranking had the workbook
    ever gained such a sheet.
    """
    fetch = scrape.fetch_from_corpus(EC_DIR)
    wanted = set(years)
    links = [
        link
        for link in scrape.scrape_election_links(fetch=fetch)
        if link.rsplit("/", 1)[-1].isdigit() and int(link.rsplit("/", 1)[-1]) in wanted
    ]
    raw = scrape.scrape_raw_election_tables(links, wanted, fetch=fetch)
    return {
        py["year"]: {
            r["state"]: r["total_electoral_votes"]
            for r in py["t2"]["votes_by_state"]
            if r["state"] != TOTALS_ROW_STATE
        }
        for py in parse.parse_election_years(raw, state_names)
    }


def virginia(pop: Population, census: int, *, with_alexandria: bool) -> int:
    """Virginia restated onto the borders in force at ``census``.

    ``with_alexandria=True`` reproduces the figure that
    ``apply_virginia_boundary_correction`` currently ships; ``False`` is the
    enumerated Virginia of that census.
    """
    va, wv = pop["Virginia"][census], pop["West Virginia"][census]
    if va is None or wv is None:
        raise CheckFailed(f"no Virginia/West Virginia figure for {census}")
    total = va + wv
    if with_alexandria or census not in ALEXANDRIA:
        # Outside 1800-1840 the District held no part of Virginia, so there is no
        # term to remove and the restated figure IS the enumerated one.
        return total
    return total - ALEXANDRIA[census]


def persons_per_ev(
    pop: Population, census: int, ev: dict[str, int], *, with_alexandria: bool
) -> tuple[list[tuple[float, str]], dict[str, str]]:
    """Ratios ascending (rank 1 = fewest per EV), plus every exclusion and its reason.

    The exclusions are returned rather than swallowed: an earlier revision dropped
    them with a bare ``continue``, so 1848 reported ``29/29`` for a 30-state
    election and nothing said which state had left.
    """
    ranked: list[tuple[float, str]] = []
    excluded: dict[str, str] = {}
    for state, votes in ev.items():
        if state == "Virginia":
            people: int | None = virginia(
                pop, census, with_alexandria=with_alexandria
            )
        else:
            people = pop.get(state, {}).get(census)
        if not votes:
            excluded[state] = "zero electoral votes"
        elif people is None:
            excluded[state] = f"no {census} governing-census population"
        else:
            ranked.append((people / votes, state))
    return sorted(ranked), excluded


def check_a(pop: Population) -> None:
    print("A. NATIONAL-TOTAL RECONCILIATION")
    print("   (jurisdiction set + US-boundary movement only — see §4.2)\n")
    censuses = {y for d in pop.values() for y in d} - set(OFF_CYCLE.values())
    missing = set(NATIONAL) - censuses
    if missing:
        raise CheckFailed(f"census years absent from the workbook: {sorted(missing)}")
    failures = []
    for census in sorted(censuses):
        vals = [v for d in pop.values() if (v := d.get(census)) is not None]
        total, note = sum(vals), ""
        if census in OFF_CYCLE:
            off = OFF_CYCLE[census]
            add = sum(v for d in pop.values() if (v := d.get(off)) is not None)
            total += add
            note = f" (+ Alaska {off} = {add:,})"
        published = NATIONAL[census]
        ok = total == published
        if not ok:
            failures.append((census, total, published))
        print(
            f"   {census}: {len(vals):2d}/{EXPECTED_AREAS} areas  file {total:>12,}"
            f"{note:<26} published {published:>12,}  -> "
            f"{'EXACT' if ok else f'DIFF {total - published:+,}'}"
        )
    if failures:
        raise CheckFailed(f"national totals did not reconcile: {failures}")
    print(f"\n   asserted: all {len(NATIONAL)} census years present and EXACT")


def check_b(pop: Population) -> None:
    print("\n\nB. PARENT/CHILD — Virginia / West Virginia, and Alexandria\n")
    va, wv, dc = (
        pop["Virginia"], pop["West Virginia"], pop["District of Columbia"]
    )
    failures = []
    for census in sorted(ENUMERATED_VA):
        a, b = va[census], wv[census]
        if a is None or b is None:
            raise CheckFailed(f"missing VA/WV figure for {census}")
        restated = a + b
        derived = virginia(pop, census, with_alexandria=False)
        expected = ENUMERATED_VA[census]
        ok_va = derived == expected
        line = (
            f"   {census}: VA {a:>9,} + WV {b:>7,} = {restated:>9,}"
            f" -> enumerated {derived:>9,} vs published {expected:>9,}"
            f"  {'EXACT' if ok_va else f'DIFF {derived - expected:+,}'}"
        )
        if not ok_va:
            failures.append(("VA", census, derived, expected))
        if census in ALEXANDRIA:
            # The second, independent identity: the District's own published total
            # must equal its present-day figure plus the Alexandria term.
            here, published_dc = dc[census], ENUMERATED_DC[census]
            if here is None:
                raise CheckFailed(f"missing DC figure for {census}")
            composed = here + ALEXANDRIA[census]
            ok_dc = composed == published_dc
            if not ok_dc:
                failures.append(("DC", census, composed, published_dc))
            line += (
                f" | DC {here:>6,} + {ALEXANDRIA[census]:>5,} = {composed:>6,}"
                f" vs {published_dc:>6,} {'EXACT' if ok_dc else 'DIFF'}"
            )
        print(line)
    if failures:
        raise CheckFailed(f"parent/child identities did not reconcile: {failures}")
    print(
        f"\n   asserted: both identities EXACT at every census"
        f" ({len(ENUMERATED_VA)} Virginia, {len(ALEXANDRIA)} District)"
    )


def check_c(pop: Population) -> None:
    print("\n\nC. RANK DIAGNOSTIC — rank 1 = FEWEST persons per EV\n")
    evs = load_electoral_votes(ELECTIONS, set(pop))
    print(
        f"   {'elec':>5} {'cens':>5} {'EV':>3} |"
        f" {'with Alex':>11} {'per EV':>8} {'rank':>6} |"
        f" {'enumerated':>11} {'per EV':>8} {'rank':>6} | {'shift':>8}"
    )
    all_excluded: dict[int, dict[str, str]] = {}
    for election in ELECTIONS:
        census = governing_census_year(election)
        ev = evs[election]
        out = {}
        for with_alex in (True, False):
            ranked, excluded = persons_per_ev(
                pop, census, ev, with_alexandria=with_alex
            )
            place = next(i for i, (_, s) in enumerate(ranked, 1) if s == "Virginia")
            ratio = next(r for r, s in ranked if s == "Virginia")
            people = virginia(pop, census, with_alexandria=with_alex)
            out[with_alex] = (people, ratio, place, len(ranked))
            all_excluded[election] = excluded
        (pw, rw, kw, n), (po, ro, ko, _) = out[True], out[False]
        shift = "same" if kw == ko else f"{kw} -> {ko}"
        print(
            f"   {election:>5} {census:>5} {ev['Virginia']:>3} |"
            f" {pw:>11,} {rw:>8,.0f} {f'{kw}/{n}':>6} |"
            f" {po:>11,} {ro:>8,.0f} {f'{ko}/{n}':>6} | {shift:>8}"
        )
    print("\n   states excluded from a ranking, named rather than dropped silently:")
    for election in ELECTIONS:
        excluded = all_excluded[election]
        if not excluded:
            print(f"     {election}: none — every participating state ranked")
            continue
        for state, why in sorted(excluded.items()):
            ev_held = evs[election][state]
            print(f"     {election}: {state} ({ev_held} EV) — {why}")


def main() -> int:
    try:
        pop = load_population()
        check_a(pop)
        check_b(pop)
        check_c(pop)
    except CheckFailed as exc:
        print(f"\nCHECK FAILED: {exc}", file=sys.stderr)
        return 1
    print("\nAll checks asserted and passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
