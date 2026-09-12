"""Transform stage — stitch, scope, label, and correct the parsed population rows.

Every decision the parsers deliberately did not make lives here, and each one is a named
constant with a test rather than an inline condition:

* **the stitch** (:data:`SOURCE_SPANS`) — which file supplies which census;
* **the vintage pin** (:data:`SOURCE_VINTAGES`) — which published tabulation a figure
  came from, recorded per row because the two disagree by amounts no assert can catch;
* **scope** (:data:`NON_STATE_AREAS`) — which published rows are aggregates rather than
  jurisdictions;
* **the boundary correction** (:data:`VIRGINIA_CORRECTION_CENSUSES`) — the one hazard in
  this source that produces plausible wrong numbers instead of a load error.

The EC spine is read for the jurisdiction check, injected as a frame the way
:mod:`usvote.ucsb.transform` takes ``ec_participation`` — the D006-allowed direction
(a source reads the spine; the spine never reads a source).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

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

#: The censuses whose Virginia figure is restated onto the borders then in force.
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

#: The censuses where the restated Virginia figure has an **independent** cross-check:
#: the file's own Virginia + West Virginia sum reproduces the separately-published
#: enumerated Virginia exactly (S1 §4 — 1790 = 747,610; 1850 = 1,421,661;
#: 1860 = 1,596,318).
#:
#: The other censuses in the window are computed by the same arithmetic but were **not**
#: re-verified against a primary source, and S1 says so rather than implying otherwise.
#: The distinction is recorded here, and in ``docs/corrections.md``, instead of letting
#: a uniformly-confident correction imply evidence it does not have. The fifty-state
#: residual sweep — whether Virginia is the only material case — is #208.
VIRGINIA_VERIFIED_CENSUSES: frozenset[int] = frozenset({1790, 1850, 1860})

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
    frame["population"] = frame["population"].astype("Int64")
    frame["census_year"] = frame["census_year"].astype(int)
    frame["redistributable"] = frame["redistributable"].astype(bool)
    return frame.sort_values(
        ["census_year", "state"], kind="stable", ignore_index=True
    )[list(CENSUS_COLUMNS)]


def apply_virginia_boundary_correction(frame: pd.DataFrame) -> pd.DataFrame:
    """Restate pre-1863 Virginia onto the borders in force at each census.

    The corrected figure is Virginia + West Virginia **as the file itself publishes
    them**, which is why this needs no external source: the file proves the arithmetic
    on its own at the censuses that have an independent cross-check (1790, 1850, 1860 —
    S1 §4), where the sum reproduces the separately-published enumerated Virginia
    exactly.

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
        evidence = (
            "independently cross-checked against the separately-published enumerated "
            "Virginia"
            if census_year in VIRGINIA_VERIFIED_CENSUSES
            else "computed by the same arithmetic, but not re-verified against a "
            "primary source for this census (see #208)"
        )
        corrected.loc[va_mask, "population"] = total
        corrected.loc[va_mask, "basis"] = BASIS_AS_ENUMERATED
        corrected.loc[va_mask, "note"] = (
            f"Restated onto the borders in force at the {census_year} census. The "
            f"published figure ({int(published_va):,}) is on present-day footprints "
            f"and omits the counties that became West Virginia in 1863; the restated "
            f"figure adds the published West Virginia ({int(published_wv):,}) back, "
            f"and is {evidence}."
        )
    return corrected
