"""Transform stage — stitch, scope, label, and correct the parsed population rows.

Every decision the parsers deliberately did not make lives here, and each one is a named
constant with a test rather than an inline condition:

* **the stitch** (:data:`SOURCE_SPANS`) — which file supplies which census;
* **the vintage pin** (:data:`SOURCE_VINTAGES`) — which published tabulation a figure
  came from, recorded per row because the two disagree by amounts no assert can catch;
* **scope** (:data:`NON_STATE_AREAS`) — which published rows are aggregates rather than
  jurisdictions;
* **the boundary corrections** (:data:`VIRGINIA_CORRECTION_CENSUSES` and
  :data:`ALEXANDRIA_RETROCESSION`) — two hazards in this source, on two different axes,
  that produce plausible wrong numbers instead of a load error.

The EC spine is read for the jurisdiction check, injected as a frame the way
:mod:`usvote.ucsb.transform` takes ``ec_participation`` — the D006-allowed direction
(a source reads the spine; the spine never reads a source).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import date
from typing import NamedTuple

import pandas as pd

from usvote.census.parse import PopulationRow
from usvote.census.schema import (
    BASIS_AS_ENUMERATED,
    BASIS_PRESENT_DAY,
    CENSUS_COLUMNS,
    SERIES_RESIDENT,
    SOURCE_CENSUS_BUREAU,
)
from usvote.census.sources import SOURCE_FILENAMES as _SOURCE_FILENAMES
from usvote.census.sources import SOURCE_VINTAGES as _SOURCE_VINTAGES

#: Which source file supplies which censuses — **the stitch rule, written down** (S1
#: §4, an explicit acceptance criterion).
#:
#: The two files overlap on 1910-1990. The rule gives each census to **exactly one** of
#: them, so the overlap is never resolved by accident — and never resolved *differently*
#: on two runs, which is what an implicit "last writer wins" would do. 1790-1990 comes
#: from the working paper; only 2000-2020 comes from the population-change table.
SOURCE_SPANS: dict[str, range] = {
    "resident_1790_1990": range(1790, 2000, 10),
    "resident_1910_2020": range(2000, 2030, 10),
}

#: The first census taken from the second file — the stitch year, pinned.
STITCH_YEAR = 2000

#: The published tabulation each file represents, and the filename it came from — both
#: **derived** from the one source catalog (:mod:`usvote.census.sources`) rather than
#: restated here. They were literal maps until the #181 review: nothing tied them to the
#: authoritative values in the fetch stage, so a rename would have updated the download
#: and silently falsified every row's provenance while the suite stayed green (F10), and
#: the vintage had no authority to be checked against at all (F2).
#:
#: The vintage pin is not bookkeeping. census.gov publishes more than one vintage of
#: resident population and they disagree: for 1910 the population-change table gives
#: **92,228,531** where the original publication gives **92,228,496**, and for 1970
#: **203,211,926** against **203,302,031** (S1 §7). Differences of that size will never
#: trip an assert, so the only defence is to record which tabulation a figure came from
#: — exactly as the EC pipeline pins its Archives corpus. The stitch above means this
#: project takes 1910-1990 from the working paper, so those particular disagreements do
#: not arise in the loaded data; the pin is what makes that statement checkable rather
#: than merely true today.
SOURCE_VINTAGES = _SOURCE_VINTAGES
SOURCE_FILENAMES = _SOURCE_FILENAMES

#: Published rows that are **not** jurisdictions, excluded by name.
#:
#: The acceptance criterion says a row that does not resolve to one of the 50 states +
#: DC must raise. Applied literally to the population-change table that would reject a
#: *correct* file: it publishes four Census regions, a national total and Puerto Rico
#: alongside the 51. So the rule is "raise unless the area is a known jurisdiction
#: **or** a member of this list" — an explicit, reviewable exclusion rather than a
#: silent filter, so a genuinely unexpected label still fails loud.
#:
#: **Both spellings of the national row are here on purpose.** The table prints it as
#: ``United States1`` in its first page-block — the footnote marker is glued to the
#: label — and as ``United States`` in the others. An exclusion written as the obvious
#: ``== "United States"`` would miss the first and raise on a correct file, which is the
#: same trap this constant exists to defuse.
#:
#: Puerto Rico is excluded because it appoints no electors and has no row in the EC
#: spine, so it has nothing to be a denominator *for*. That is a scope decision, not a
#: judgement about the data.
NON_STATE_AREAS: frozenset[str] = frozenset(
    {
        "United States",
        "United States1",
        "Northeast Region",
        "Midwest Region",
        "South Region",
        "West Region",
        "Puerto Rico",
    }
)

#: The censuses whose Virginia figure is restated onto the borders then in force **as to
#: the West Virginia counties**.
#:
#: That qualifier is load-bearing (#251/D066). This restatement is one axis; for the
#: censuses 1800-1840 the figure it produces still carries **Alexandria County**, which
#: was District of Columbia at those censuses, and so is borders-then-in-force only
#: once :func:`apply_alexandria_retrocession` has also run. See
#: :data:`ALEXANDRIA_RETROCESSION`.
#:
#: ``tabs15-65.xlsx`` reports **every** census on present-day state footprints, so for
#: every census before West Virginia's 1863 separation its Virginia omits the counties
#: that became West Virginia. Measured (S1 §4): the understatement runs from 7.5% at the
#: 1790 census to 23.6% at 1860, and across the affected window — the ten elections from
#: 1824 to 1860 — from **12.7%** (1820 census) to **21.3%** (1850), which overstates
#: Virginia's per-capita electoral weight by ~27% at the worst point that actually
#: governs an election.
#:
#: Neither side of this shows up as a load error. That is what makes it the one hazard
#: in this source worth a correction rather than a note.
VIRGINIA_CORRECTION_CENSUSES: tuple[int, ...] = tuple(range(1790, 1870, 10))

#: How each restated Virginia census is confirmed — **three states, not two** (#251).
#:
#: :data:`VERIFIED_BY_PUBLISHED_TOTAL` — the file's own Virginia + West Virginia sum
#: reproduces a **separately-published enumerated Virginia total** exactly (S1 §4 —
#: 1790 = 747,610; 1850 = 1,421,661; 1860 = 1,596,318). Note that this already rests on
#: an external figure: the file cannot confirm itself.
#:
#: :data:`VERIFIED_BY_PUBLISHED_COMPONENTS` — 1800-1840. #208 established that these
#: five are **not** clean: the file's Virginia + West Virginia overshoots the enumerated
#: Virginia by Alexandria County (0.79%-0.91% across the six elections 1824-1844 held
#: before the retrocession; these censuses govern seven, 1824-1848). The residual is
#: explained, quantified and corrected here: the figure is composed from three
#: **published component** series — the file's two rows and the Bureau's Alexandria
#: figures (:data:`ALEXANDRIA_RETROCESSION`). The 1996 volume prints the components,
#: not an enumerated Virginia total, so for **1800, 1830 and 1840** the composition *is*
#: the enumerated figure by construction and is checked against nothing independent
#: (``research-boundary-sweep.md`` §4.1, §5.4). Only **1810 and 1820** have an
#: independently printed total — the original returns, reprinted in the Bureau's *A
#: Century of Population Growth* (1909) — and the composition matches it; §5.4 marks
#: both **CONTRADICTED**, because the 1850 Seventh Census restates them 22 and 13 higher
#: (974,622 / 1,065,379). 1810 is weaker again, since its Alexandria cell is itself
#: settled partly by arithmetic (:data:`ALEXANDRIA_RETROCESSION`). The map and
#: :func:`apply_alexandria_retrocession` are checked against each other in **both**
#: directions there, and the step writes the state into the row note.
#:
#: A census in the window with **no** entry would be computed-but-unverified. None is
#: left, and the state stays expressible so a widened window cannot inherit a
#: confidence it has not earned.
#:
#: **What an exact sum does and does not prove.** The Bureau itself: *"Prior to 1860
#: this cannot be done exactly, because the present Virginia-West Virginia State
#: boundary did not correspond to county boundaries in 1850 or earlier."* An exact
#: reconciliation shows the Virginia/West Virginia split is **exhaustive** — nobody is
#: lost or double-counted between the two rows — not that it is **accurate** county by
#: county. Neither state claims the second.
VERIFIED_BY_PUBLISHED_TOTAL = "published_total"
VERIFIED_BY_PUBLISHED_COMPONENTS = "published_components"
VIRGINIA_VERIFICATION: Mapping[int, str] = {
    1790: VERIFIED_BY_PUBLISHED_TOTAL,
    1800: VERIFIED_BY_PUBLISHED_COMPONENTS,
    1810: VERIFIED_BY_PUBLISHED_COMPONENTS,
    1820: VERIFIED_BY_PUBLISHED_COMPONENTS,
    1830: VERIFIED_BY_PUBLISHED_COMPONENTS,
    1840: VERIFIED_BY_PUBLISHED_COMPONENTS,
    1850: VERIFIED_BY_PUBLISHED_TOTAL,
    1860: VERIFIED_BY_PUBLISHED_TOTAL,
}


class Retrocession(NamedTuple):
    """Territory a state **gained back** from a non-state jurisdiction after a census.

    The inverse shape of :class:`usvote.census.conform.BoundarySuccession`, and
    deliberately not an entry in it (D066(h), H2): a succession is a predecessor
    *losing* people to a participating successor row it can be checked against, while a
    retrocession is a recipient *gaining* from a jurisdiction that may hold no row at
    all. ``population`` maps a census year to the transferred territory's published
    figure; for those censuses the file's recipient figure **includes** it although the
    territory was not the recipient's when enumerated.
    """

    recipient: str
    donor: str
    effective_date: date
    population: Mapping[int, int]
    citation: str


#: Alexandria County — District of Columbia from 1801 until its retrocession to
#: Virginia on 7 September 1846 (#208, #251).
#:
#: ``tabs15-65.xlsx`` credits it to Virginia at every census 1800-1840, so the restated
#: Virginia figure for those censuses is 0.79%-0.91% high. Four of the five figures are
#: the Census Bureau's **own**, as printed: Virginia State Note 2 of *Population of
#: States and Counties of the United States: 1790 to 1990* (March 1996), the companion
#: volume to the working paper the file comes from — *"State totals for 1800-1840
#: include population of the portion of the District of Columbia taken from Virginia
#: (Fairfax County) in 1791 but retroceded to Virginia in 1846"*. Those four are
#: deliberately **not** computed as ``enumerated_DC - file_DC``: that derivation is how
#: #208 found the case, and using it would make the correction depend on a second
#: external series when a published one exists. The same volume's District note and its
#: ``Arlington`` county row agree with them (``research-boundary-sweep.md`` §5.3).
#:
#: **1810 is the exception, and it is not Note 2's figure.** Note 2 prints 8,852, which
#: is a defect in the note (not an OCR artifact, and no longer an open ambiguity). The
#: value used, 8,552, rests on the volume's published ``Arlington`` county row (read at
#: 500 dpi), with the tie against the rival 8,530 broken by the District note — and that
#: tiebreak *is* the ``enumerated_DC - file_DC`` arithmetic avoided for the other four
#: (``24,023 - 15,471 = 8,552``; ``15,471 + 8,530 = 24,001`` fails). It governs
#: elections 1812-1820, outside the EC span, so nothing in the warehouse turns on it.
#:
#: Two traps worth carrying (§5.3): in 1820 the row printed *"County of Alexandria"* is
#: the rural remainder only (1,485), the county total being that plus *"Alexandria"*
#: (8,218); and the continuation of pre-1846 Alexandria County is the ``Arlington``
#: row, not the modern ``Alexandria`` city row. And the subtraction is right **only
#: because** the file's present-day Virginia includes Arlington/Alexandria at these
#: censuses: against a source that excluded them the term must be dropped, not
#: sign-flipped.
#:
#: The retrocession date is ATTRIBUTED, not re-read here (§5.4): Act of 9 July 1846,
#: ch. XXXV, 9 Stat. 35, conditional on a county referendum held 1-2 September 1846,
#: proclaimed in force 7 September 1846. The 1850 census counted Alexandria in
#: Virginia, which is why 1850 and 1860 carry no term.
ALEXANDRIA_RETROCESSION = Retrocession(
    recipient="Virginia",
    donor="District of Columbia",
    effective_date=date(1846, 9, 7),
    population={1800: 5_949, 1810: 8_552, 1820: 9_703, 1830: 9_573, 1840: 9_967},
    citation=(
        "US Census Bureau, Population of States and Counties of the United States: "
        "1790 to 1990 (March 1996), Virginia Note 2: state totals for 1800-1840 "
        "include the portion of the District of Columbia retroceded to Virginia in "
        "1846 (1800: 5,949; 1810: 8,552 -- printed as 8,852, corrected by the same "
        "volume's District note and Arlington row; 1820: 9,703; 1830: 9,573; "
        "1840: 9,967). Retrocession: Act of 9 July 1846, 9 Stat. 35, proclaimed "
        "7 September 1846."
    ),
)

_VIRGINIA = "Virginia"
_WEST_VIRGINIA = "West Virginia"


class CensusTransformError(RuntimeError):
    """Raised when the parsed rows cannot be transformed into the census shape."""


def known_states(ec_participation: pd.DataFrame) -> set[str]:
    """Return the jurisdictions the EC spine recognizes, from an injected frame.

    Totals rows are excluded — they are an aggregate, not a jurisdiction. Taking the
    set from the spine rather than from a constant here is what makes the check mean
    something: it compares the census file against the warehouse's own state dimension,
    which is also what the ``state`` foreign key will be resolved against.
    """
    if "state" not in ec_participation.columns:
        raise CensusTransformError(
            f"EC participation frame has no 'state' column; got "
            f"{list(ec_participation.columns)}"
        )
    frame = ec_participation
    if "is_total" in frame.columns:
        frame = frame.loc[~frame["is_total"].astype(bool)]
    return {str(state) for state in frame["state"].dropna().unique()}


def assert_known_jurisdictions(
    areas: Collection[str], *, recognized: Collection[str]
) -> None:
    """Raise unless every area is a known jurisdiction or a declared aggregate.

    This is the "validate names, not participation" guard (an acceptance criterion,
    revised against S1). It deliberately does **not** filter on whether the EC spine
    gives that state electoral votes in that era: the source backfills states to their
    modern footprint's first countable census — West Virginia at 1790, Alabama and
    Michigan at 1800, Wisconsin at 1820, Arizona and Nevada at 1860 — and those rows
    must survive the load, because conforming them to the participation roster is
    #182's job. A load-time participation filter would delete #182's input.
    """
    recognized_set = set(recognized)
    unknown = sorted(
        area
        for area in set(areas)
        if area not in recognized_set and area not in NON_STATE_AREAS
    )
    if unknown:
        raise CensusTransformError(
            f"{len(unknown)} area(s) in the census source resolve to neither a known "
            f"jurisdiction nor a declared non-state aggregate: {unknown}. Either the "
            f"published layout changed or the parse is wrong — refusing to load rather "
            f"than silently dropping them. If a new aggregate row was added upstream, "
            f"add it to NON_STATE_AREAS with a note saying what it is."
        )


def assert_stitch_is_unambiguous(spans: Mapping[str, range] = SOURCE_SPANS) -> None:
    """Raise unless the stitch gives every covered census to exactly one source.

    Cheap, and it guards the acceptance criterion directly: "each census comes from
    exactly one file, so the 1910-1990 overlap is never resolved by accident". An
    overlap introduced by a future edit — widening one span, adding a third file —
    fails here rather than producing a frame whose duplicate keys are caught much later
    by the loader, with no clue which source won.
    """
    seen: dict[int, str] = {}
    for source_id, span in spans.items():
        for year in span:
            if year in seen:
                raise CensusTransformError(
                    f"Census year {year} is claimed by both {seen[year]!r} and "
                    f"{source_id!r}; the stitch must give each census to exactly one "
                    f"source."
                )
            seen[year] = source_id
    if not seen:
        return
    expected = set(range(min(seen), max(seen) + 10, 10))
    missing = sorted(expected - set(seen))
    if missing:
        raise CensusTransformError(
            f"The stitch leaves census year(s) {missing} uncovered between "
            f"{min(seen)} and {max(seen)}."
        )


def transform_census(
    rows_by_source: Mapping[str, Sequence[PopulationRow]],
    ec_participation: pd.DataFrame,
) -> pd.DataFrame:
    """Build the census frame from parsed rows, applying every policy in this module.

    Returns the :data:`~usvote.census.schema.CENSUS_COLUMNS` shape, one row per
    ``(source, census_year, state, series)``.
    """
    assert_stitch_is_unambiguous()
    missing_sources = sorted(set(SOURCE_SPANS) - set(rows_by_source))
    if missing_sources:
        raise CensusTransformError(
            f"No parsed rows supplied for source(s) {missing_sources}; the stitch "
            f"needs all of {sorted(SOURCE_SPANS)} to cover 1790-2020."
        )

    recognized = known_states(ec_participation)
    records: list[dict[str, object]] = []
    for source_id, span in SOURCE_SPANS.items():
        rows = rows_by_source[source_id]
        assert_known_jurisdictions([row.area for row in rows], recognized=recognized)
        filename = SOURCE_FILENAMES[source_id]
        vintage = SOURCE_VINTAGES[source_id]
        for row in rows:
            if row.census_year not in span or row.area in NON_STATE_AREAS:
                continue
            records.append(
                {
                    "source": SOURCE_CENSUS_BUREAU,
                    "census_year": row.census_year,
                    "state": row.area,
                    "series": SERIES_RESIDENT,
                    "basis": BASIS_PRESENT_DAY,
                    "population": row.population,
                    "vintage": vintage,
                    "source_file": filename,
                    "redistributable": True,
                    "note": (
                        None
                        if row.population is not None
                        else f"No published figure in {filename} for this census."
                    ),
                }
            )

    if not records:
        raise CensusTransformError(
            "No census rows survived the stitch and scope rules."
        )

    frame = pd.DataFrame.from_records(records, columns=list(CENSUS_COLUMNS))
    frame = apply_virginia_boundary_correction(frame)
    frame = apply_alexandria_retrocession(frame)
    frame["population"] = frame["population"].astype("Int64")
    frame["census_year"] = frame["census_year"].astype(int)
    frame["redistributable"] = frame["redistributable"].astype(bool)
    return frame.sort_values(
        ["census_year", "state"], kind="stable", ignore_index=True
    )[list(CENSUS_COLUMNS)]


def apply_virginia_boundary_correction(frame: pd.DataFrame) -> pd.DataFrame:
    """Restate pre-1863 Virginia onto its borders at each census, as to West Virginia.

    The corrected figure is Virginia + West Virginia **as the file itself publishes
    them**, which is why this step needs no external figure to *compute*; confirming it
    does, and :data:`VIRGINIA_VERIFICATION` records against what. At 1790, 1850 and 1860
    the sum reproduces the separately-published enumerated Virginia exactly (S1 §4) —
    which shows the split between the two rows is exhaustive, not that it is accurate
    county by county (the Bureau: before 1860 it "cannot be done exactly").

    **This is one axis of two.** For 1800-1840 the sum still includes Alexandria County,
    which was not Virginia's at those censuses; :func:`apply_alexandria_retrocession`
    removes it, and is kept a separate step because Alexandria's population is **not in
    this file** — folding it in here would launder an external figure under a
    self-computing function, and it is a different mechanism (1846, DC->VA) from this
    one (1863, VA->WV).

    West Virginia's own rows are deliberately **left alone**, at ``present_day`` basis.
    They are a real population for the territory that became West Virginia, and #182 is
    what removes them from any per-capita join for the censuses in which West Virginia
    held no electoral votes. Zeroing or deleting them here would destroy #182's input
    and fabricate data besides.
    """
    corrected = frame.copy()
    for census_year in VIRGINIA_CORRECTION_CENSUSES:
        in_year = corrected["census_year"] == census_year
        va_mask = in_year & (corrected["state"] == _VIRGINIA)
        wv_mask = in_year & (corrected["state"] == _WEST_VIRGINIA)
        if not va_mask.any() or not wv_mask.any():
            continue
        published_va = corrected.loc[va_mask, "population"].iloc[0]
        published_wv = corrected.loc[wv_mask, "population"].iloc[0]
        if pd.isna(published_va) or pd.isna(published_wv):
            # Nothing to add together. Leave the published row and its basis untouched
            # rather than inventing a total — a corrected figure built from a missing
            # part would be exactly the fabricated value D005 forbids.
            continue
        total = int(published_va) + int(published_wv)
        verification = VIRGINIA_VERIFICATION.get(census_year)
        if verification == VERIFIED_BY_PUBLISHED_TOTAL:
            evidence = (
                "independently cross-checked against the separately-published "
                "enumerated Virginia"
            )
        elif verification == VERIFIED_BY_PUBLISHED_COMPONENTS:
            evidence = (
                "one of two restatements for this census: it still includes Alexandria "
                "County, removed in the next step"
            )
        else:
            evidence = (
                "computed by the same arithmetic, but not re-verified against a "
                "primary source for this census"
            )
        corrected.loc[va_mask, "population"] = total
        corrected.loc[va_mask, "basis"] = BASIS_AS_ENUMERATED
        corrected.loc[va_mask, "note"] = (
            f"Restated onto the {census_year} borders as to West Virginia. The "
            f"published figure ({int(published_va):,}) is on present-day footprints "
            f"and omits the counties that became West Virginia in 1863; the restated "
            f"figure adds the published West Virginia ({int(published_wv):,}) back, "
            f"and is {evidence}."
        )
    return corrected


def apply_alexandria_retrocession(
    frame: pd.DataFrame, *, retrocession: Retrocession = ALEXANDRIA_RETROCESSION
) -> pd.DataFrame:
    """Remove Alexandria County from Virginia's 1800-1840 figures (#251).

    Runs **after** :func:`apply_virginia_boundary_correction` and subtracts the Bureau's
    published figure from the West-Virginia-restated row, so the result is
    ``file Virginia + file West Virginia - Alexandria`` — the enumerated Virginia as
    the Bureau composes it from published components (``research-boundary-sweep.md``
    §4.1, §5.4: 880,200 / 974,600 / 1,065,366 / 1,211,405 / 1,239,797). How far that is
    independently confirmed differs by census; :data:`VIRGINIA_VERIFICATION` says how.
    Only then is ``as_enumerated`` true of these rows on both axes.

    The map (read at call time) and this step must agree in **both** directions, or
    this raises: every census this step corrects must be recorded as
    :data:`VERIFIED_BY_PUBLISHED_COMPONENTS`, and every census so recorded must be one
    this step corrects — otherwise the West Virginia step would persist a note saying
    Alexandria is "removed in the next step" for a census where nothing removes it.

    Skips a census whose Virginia row is absent or NULL, as its sibling does — there is
    nothing to correct and nothing may be invented. **Raises** where the row is present
    and still ``present_day``: that means the West Virginia step did not run (a missing
    West Virginia cell, or a reordering), and subtracting Alexandria from the
    present-day figure would produce a number that is neither published nor enumerated.

    Alexandria's people land in **no** row afterwards: the file's District of Columbia
    figure already excludes them (the Bureau's District note says so). DC holds no
    electoral votes until 1964, so no denominator loses them; the cost is that these
    five census years are not sum-consistent — which the West Virginia double-count
    already made true, and which nothing in this package asserts.
    """
    composed = {
        year
        for year, state in VIRGINIA_VERIFICATION.items()
        if state == VERIFIED_BY_PUBLISHED_COMPONENTS
    }
    uncorrected = sorted(composed - set(retrocession.population))
    if uncorrected:
        raise CensusTransformError(
            f"VIRGINIA_VERIFICATION records census(es) {uncorrected} as "
            f"{VERIFIED_BY_PUBLISHED_COMPONENTS!r}, but {retrocession.donor}'s "
            f"retrocession pins no figure for them, so nothing composes them. The map "
            f"and the correction disagree; fix one of them."
        )
    corrected = frame.copy()
    for census_year, transferred in retrocession.population.items():
        mask = (corrected["census_year"] == census_year) & (
            corrected["state"] == retrocession.recipient
        )
        if not mask.any():
            continue
        index = corrected.index[mask][0]
        current = corrected.at[index, "population"]
        if pd.isna(current):
            continue
        if corrected.at[index, "basis"] != BASIS_AS_ENUMERATED:
            raise CensusTransformError(
                f"{retrocession.recipient}'s {census_year} row is still "
                f"{corrected.at[index, 'basis']!r}: the West Virginia restatement did "
                f"not run for this census, so subtracting {retrocession.donor}'s "
                f"retroceded {transferred:,} would yield a figure that is neither "
                f"published nor enumerated. Refusing rather than guessing."
            )
        if VIRGINIA_VERIFICATION.get(census_year) != VERIFIED_BY_PUBLISHED_COMPONENTS:
            raise CensusTransformError(
                f"{retrocession.recipient}'s {census_year} figure is being composed "
                f"from published components, but VIRGINIA_VERIFICATION records "
                f"{VIRGINIA_VERIFICATION.get(census_year)!r} for that census, not "
                f"{VERIFIED_BY_PUBLISHED_COMPONENTS!r}. The map and the correction "
                f"disagree; fix one of them."
            )
        enumerated = int(current) - transferred
        corrected.at[index, "population"] = enumerated
        corrected.at[index, "note"] = (
            f"Restated onto the borders in force at the {census_year} census, on both "
            f"axes. The published figure is on present-day footprints: it omits the "
            f"counties that became West Virginia in 1863, which are added back from "
            f"the file's own West Virginia row, and it includes Alexandria County, "
            f"District of Columbia until its retrocession on "
            f"{retrocession.effective_date.isoformat()}, which is removed using the "
            f"Census Bureau's published figure ({transferred:,}). The result "
            f"({enumerated:,}) is the enumerated Virginia composed from those three "
            f"published components (verification: "
            f"{VERIFIED_BY_PUBLISHED_COMPONENTS})."
        )
    return corrected
