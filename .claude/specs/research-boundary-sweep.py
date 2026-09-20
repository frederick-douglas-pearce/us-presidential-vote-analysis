"""#208 — boundary sweep: the empirical half of `research-boundary-sweep.md` §4.

Runs fully **offline** against the two local corpora — no network, no database:

    USVOTE_CENSUS_CORPUS_DIR/tabs15-65.xlsx   (resident population 1790-1990)
    USVOTE_EC_HTML_DIR/<year>.html            (the Archives corpus, #89)

    uv run python .claude/specs/research-boundary-sweep.py

Three checks, in the order §4 reports them:

A. **National-total reconciliation.** Sums all 51 file areas per census against a
   published US total. Its power is deliberately narrow and §4.2 says so: a
   state-to-state transfer is *conservative* at the national level, so this can
   NOT surface an unlisted reassignment between two states — the Virginia/West
   Virginia case passes it silently. What it does establish is that the
   jurisdiction set is complete and non-duplicated, and that no population
   crossed the *US* boundary unaccounted.

B. **Parent/child reconciliation.** The #180 technique, extended with the
   Alexandria term.

C. **Rank diagnostic.** Virginia's persons-per-electoral-vote rank with and
   without the Alexandria term, across the six elections the 1820/1830/1840
   censuses govern.
"""

from __future__ import annotations

import os
from pathlib import Path

from usvote import parse, scrape
from usvote.apportionment import governing_census_year
from usvote.census.parse import parse_resident_1790_1990

_FALLBACK = Path.home() / "Documents/Projects/data/presidential_vote_analysis"

CENSUS_FILE = (
    Path(os.environ.get("USVOTE_CENSUS_CORPUS_DIR", str(_FALLBACK / "census_corpus")))
    / "tabs15-65.xlsx"
)
EC_DIR = os.environ.get("USVOTE_EC_HTML_DIR", str(_FALLBACK / "ec_raw"))

#: Alexandria County, D.C., per census. Derived here as ``enumerated_DC -
#: file_DC``; §5 sources it independently, which is what makes check B's second
#: identity a test rather than a restatement of the first.
ALEXANDRIA = {1800: 5_949, 1810: 8_552, 1820: 9_703, 1830: 9_573, 1840: 9_967}

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

#: The elections the Alexandria-affected censuses govern.
ELECTIONS = (1824, 1828, 1832, 1836, 1840, 1844, 1848)

Population = dict[str, dict[int, int | None]]


def load_population() -> Population:
    rows = parse_resident_1790_1990(
        CENSUS_FILE.read_bytes(), source_id="resident_1790_1990"
    )
    pop: Population = {}
    for row in rows:
        pop.setdefault(row.area, {})[row.census_year] = row.population
    return pop


def load_electoral_votes(
    years: tuple[int, ...], state_names: set[str]
) -> dict[int, dict[str, int]]:
    fetch = scrape.fetch_from_corpus(EC_DIR)
    links = scrape.scrape_election_links(fetch=fetch)
    raw = scrape.scrape_raw_election_tables(links, set(years), fetch=fetch)
    return {
        py["year"]: {
            r["state"]: r["total_electoral_votes"]
            for r in py["t2"]["votes_by_state"]
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
    assert va is not None and wv is not None
    total = va + wv
    return total if with_alexandria else total - ALEXANDRIA[census]


def persons_per_ev(
    pop: Population, census: int, ev: dict[str, int], *, with_alexandria: bool
) -> list[tuple[float, str]]:
    """Every participating state's ratio, ascending. Rank 1 = fewest per EV."""
    ranked = []
    for state, votes in ev.items():
        if not votes:
            continue
        if state == "Virginia":
            people: int | None = virginia(
                pop, census, with_alexandria=with_alexandria
            )
        else:
            people = pop.get(state, {}).get(census)
        if people is None:
            continue
        ranked.append((people / votes, state))
    return sorted(ranked)


def check_a(pop: Population) -> None:
    print("A. NATIONAL-TOTAL RECONCILIATION")
    print("   (jurisdiction set + US-boundary movement only — see §4.2)\n")
    censuses = {y for d in pop.values() for y in d} - set(OFF_CYCLE.values())
    for census in sorted(censuses):
        vals = [v for d in pop.values() if (v := d.get(census)) is not None]
        total, note = sum(vals), ""
        if census in OFF_CYCLE:
            off = OFF_CYCLE[census]
            add = sum(v for d in pop.values() if (v := d.get(off)) is not None)
            total += add
            note = f" (+ Alaska {off} = {add:,})"
        published = NATIONAL[census]
        verdict = "EXACT" if total == published else f"DIFF {total - published:+,}"
        print(
            f"   {census}: {len(vals):2d}/51 areas  file {total:>12,}{note:<26}"
            f" published {published:>12,}  -> {verdict}"
        )


def check_b(pop: Population) -> None:
    print("\n\nB. PARENT/CHILD — Virginia / West Virginia, and Alexandria\n")
    va, wv, dc = (
        pop["Virginia"], pop["West Virginia"], pop["District of Columbia"]
    )
    for census in (1790, 1800, 1810, 1820, 1830, 1840, 1850, 1860):
        a, b = va[census], wv[census]
        assert a is not None and b is not None
        head = f"   {census}: VA {a:>9,} + WV {b:>7,} = {a + b:>9,}"
        if census in ALEXANDRIA:
            alex, district = ALEXANDRIA[census], dc[census]
            assert district is not None
            print(
                f"{head} | file DC {district:>6,} | Alexandria {alex:>6,}"
                f" | as enumerated {a + b - alex:>9,}"
            )
        else:
            why = (
                "District did not exist"
                if census == 1790
                else "retroceded to VA in 1846"
            )
            print(f"{head} | no Alexandria term ({why})")


def check_c(pop: Population) -> None:
    print("\n\nC. RANK DIAGNOSTIC — rank 1 = FEWEST persons per EV\n")
    evs = load_electoral_votes(ELECTIONS, set(pop))
    print(
        f"   {'elec':>5} {'cens':>5} {'EV':>3} |"
        f" {'with Alex':>11} {'per EV':>8} {'rank':>6} |"
        f" {'enumerated':>11} {'per EV':>8} {'rank':>6} | {'shift':>8}"
    )
    for election in ELECTIONS:
        census = governing_census_year(election)
        ev = evs[election]
        out = {}
        for with_alex in (True, False):
            ranked = persons_per_ev(pop, census, ev, with_alexandria=with_alex)
            place = next(i for i, (_, s) in enumerate(ranked, 1) if s == "Virginia")
            ratio = next(r for r, s in ranked if s == "Virginia")
            people = virginia(pop, census, with_alexandria=with_alex)
            out[with_alex] = (people, ratio, place, len(ranked))
        (pw, rw, kw, n), (po, ro, ko, _) = out[True], out[False]
        shift = "same" if kw == ko else f"{kw} -> {ko}"
        print(
            f"   {election:>5} {census:>5} {ev['Virginia']:>3} |"
            f" {pw:>11,} {rw:>8,.0f} {f'{kw}/{n}':>6} |"
            f" {po:>11,} {ro:>8,.0f} {f'{ko}/{n}':>6} | {shift:>8}"
        )


def main() -> None:
    pop = load_population()
    check_a(pop)
    check_b(pop)
    check_c(pop)


if __name__ == "__main__":
    main()
