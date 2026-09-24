"""Conform census population to the EC participation roster, at election grain (#182).

The census dimension is keyed on ``(census_year, state)``; every consumer in E10 is
keyed on ``(election_year, state)``. This module crosses that grain, and crossing it is
where three classes of silent wrongness live:

* **which census governed** — an apportionment-law fact, not arithmetic
  (:mod:`usvote.apportionment`);
* **which borders a figure is on** — a restatement correct for one election is wrong for
  the next (:data:`BOUNDARY_SUCCESSIONS`);
* **which states the source cannot cover at all** — and whether that is a fact about
  history or a defect in this repo (:data:`CENSUS_COVERAGE_EXCEPTIONS`).

None of the three produces a load error. Each produces a plausible wrong number, which
is why each is a named constant with a guard rather than an inline condition.

**Why this is its own module and not more of** :mod:`usvote.census.transform`. That
module works at ``(census_year, state)`` grain and its ``assert_known_jurisdictions`` is
explicitly *name* validity — it deliberately does **not** filter on participation,
because doing so at load time would delete this module's input. This module works at
``(election_year, state)`` grain, which does not exist until the mapping does. One grain
per module.

**The EC spine arrives as an injected frame**, exactly as
:func:`usvote.census.transform.transform_census` takes ``ec_participation`` — the
D006-allowed direction (a source reads the spine; the spine never reads a source). So
everything here is pure and offline, and the DB read stays in
:mod:`usvote.census.pipeline`. **No code in this module names ``dwh.votes``** — the
prose below does, where it explains where a NULL allotment comes from, and that is the
distinction the guard draws: ``code_only`` strips docstrings and comments precisely so
accurate documentation is not punished (``test_no_lower_subpackage_names_the_ec_votes_
fact_in_code``, which covers ``census`` as of #183).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import NamedTuple

import numpy as np
import pandas as pd

from usvote.apportionment import governing_census_year
from usvote.census.schema import (
    BASIS_AS_ENUMERATED,
    CENSUS_SCHEMA,
    SERIES_RESIDENT,
    SERIES_VALUES,
    build_series_check,
)
from usvote.census.transform import ALEXANDRIA_RETROCESSION, Retrocession
from usvote.years import ec_ingest_years

#: The frame contract #183 and #184 both inherit — **append-only**.
#:
#: Pinned to a hand-written literal in
#: ``tests/unit/test_census_conform.py::TestTheFrameContract``, on the ``EC_PV_COLUMNS``
#: / ``HYBRID_SUMMARY_COLUMNS`` precedent: the
#: frame is built with ``columns=list(ELECTION_POPULATION_COLUMNS)``, so any assert
#: comparing the frame against this tuple is circular and passes under a reorder or a
#: mid-list insert alike. If #184 later materializes this as a view, ``CREATE OR
#: REPLACE`` can only add trailing columns, so append-only is a hard constraint rather
#: than a style.
#:
#: ``total_electoral_votes`` is carried because #183 reconciles seats against the
#: **appointed** allotment and it is already in the injected participation frame — free
#: here, a second spine read there (#182 architect review, C2a).
#:
#: ``population_series`` was **appended** by #184, which is what "append-only" is for.
#: It reads better beside ``population`` and is deliberately not put there: this tuple
#: is now the column order of :data:`ELECTION_POPULATION_TABLE` *and* of the view over
#: it, where ``CREATE OR REPLACE VIEW`` can only add trailing columns. Cosmetic order is
#: not worth a migration. It is spelled ``population_series`` rather than ``series``
#: because at election grain a bare ``series`` sits next to ``boundary_basis`` and
#: ``coverage`` and reads as if it might label either of them; the census dimension has
#: no such neighbours and keeps the short name.
ELECTION_POPULATION_COLUMNS: tuple[str, ...] = (
    "election_year",
    "state",
    "governing_census_year",
    "total_electoral_votes",
    "population",
    "boundary_basis",
    "coverage",
    # Appended, never inserted -- see the ordering note above.
    "population_series",
)

#: The two columns that carry genuine NULLs. Both describe the *same* absence — a
#: participating state with no governing-census figure — so they are nullable together
#: and :func:`assert_election_population_shape` asserts they are null in the same rows.
NULLABLE_ELECTION_POPULATION_COLUMNS: tuple[str, ...] = (
    "population",
    "population_series",
)

#: The election-grain table #184 persists (D064).
#:
#: **Why this frame is a table and not a view over** ``dwh.census_population`` **×**
#: ``dwh.votes``. Expressed as SQL, the derivation below would become a *second*
#: expression of policy this module already assembles behind its guards — and one of
#: the two things it would have to re-express is not recoverable from the warehouse at
#: all. D059 keeps ``basis`` out of the census natural key, so ``dwh.census_population``
#: holds only the **restated** Virginia row; the published 1860 figure survives solely
#: as the pinned literal in :data:`BOUNDARY_SUCCESSIONS`. A SQL view would therefore
#: either surface the wrong Virginia population for 1864 and 1868, or copy that literal
#: into a query — a second copy of a constant whose entire purpose is to *check* the
#: first. Persisting the frame keeps one derivation, in pandas, run once.
ELECTION_POPULATION_TABLE = "election_population"

#: One row per participating ``(election_year, state)`` — the grain, and the whole key.
#: Unlike the census dimension there is no ``source`` component: this frame is built
#: from the EC spine plus the one resident series, not assembled from several sources.
ELECTION_POPULATION_NATURAL_KEY: tuple[str, ...] = ("election_year", "state")


#: Whether a figure is on the borders **in force at the election**.
#:
#: **Borders-at-the-election is the governing criterion** for this frame and for
#: ``dwh.election_per_capita`` (D066). It is one of **three** axes a per-capita
#: denominator sits on, and conflating any two of them is the standing hazard:
#: *vintage* — which census supplies the figure — is
#: :func:`usvote.apportionment.governing_census_year`; *footprint* — which territory the
#: figure describes — is this column; and *denominator provenance* — where
#: ``total_electoral_votes`` came from — is an apportionment artifact. Axes 1 and 3 are
#: apportionment facts and this one is not, because they answer different questions:
#: whose allotment is this, versus whose people are these.
#:
#: **This is also not the census ``basis``** (#182 architect review, C2d).
#: ``census_population.basis`` answers "borders at census time vs modern". At election
#: grain the question is "borders at *this election*", and the two disagree exactly
#: where this module works: for the elections **1824-1868** Virginia's figure is
#: borders-at-election by three different routes — the **restated**
#: (``as_enumerated``) census figure for 1824-1844 and 1852-1860, that figure with
#: Alexandria County added back for 1848 (:data:`BOUNDARY_RETROCESSIONS`), and for 1864
#: and 1868 the **published** (``present_day``) figure, because West Virginia is a
#: separate state by then. Carrying the census label through would stamp 1864 Virginia
#: ``present_day`` — an honesty warning — on the figure that is in fact correct for
#: that election.
#:
#: **1824-1844 joined that span with #251.** #208 established that the restated figure
#: also included **Alexandria County**, District of Columbia until its retrocession to
#: Virginia on 7 September 1846, so for those six elections it was 0.79%-0.91% high.
#: Between #253/D066 and #251 the label therefore had a third state in practice —
#: established *not* to be as-at-election — carried as ``at_election`` on purpose rather
#: than downgraded; #251 removed Alexandria at census grain
#: (:func:`usvote.census.transform.apply_alexandria_retrocession`), which made the label
#: true and retired that state. ``present_day`` remains the honest default: "this is the
#: published figure; we have not asserted it is the as-at-election one".
#:
#: Today the only rows carrying ``at_election`` are Virginia 1824-1868.
BOUNDARY_AT_ELECTION = "at_election"
BOUNDARY_PRESENT_DAY = "present_day"
BOUNDARY_BASIS_VALUES: tuple[str, ...] = (BOUNDARY_AT_ELECTION, BOUNDARY_PRESENT_DAY)

#: Whether this ``(election_year, state)`` has a governing-census figure at all.
#:
#: A closed vocabulary, as ``basis``, ``pv_status`` and ``count_status`` are — not a
#: free label, so #184 branches on a constant rather than on a string literal (#182
#: architect review, C2c).
COVERAGE_COVERED = "covered"
COVERAGE_NO_GOVERNING_FIGURE = "no_governing_figure"
COVERAGE_VALUES: tuple[str, ...] = (COVERAGE_COVERED, COVERAGE_NO_GOVERNING_FIGURE)

#: Why a participating state has no governing-census figure. **Two kinds, and the
#: distinction is load-bearing rather than descriptive.**
#:
#: ``absent_from_source`` is a fact about history — the figure does not exist and no
#: code change can produce it. ``present_but_unparsed`` is a defect in *this* repo — the
#: figure is in the published file and a parser cannot reach it yet. Recording the
#: second as the first would be a false entry in a corrections catalog; recording the
#: first as the second would promise a fix that cannot exist.
KIND_ABSENT_FROM_SOURCE = "absent_from_source"
KIND_PRESENT_BUT_UNPARSED = "present_but_unparsed"
EXCEPTION_KINDS: tuple[str, ...] = (KIND_ABSENT_FROM_SOURCE, KIND_PRESENT_BUT_UNPARSED)


class CensusConformError(RuntimeError):
    """Raised when census population cannot be conformed to the EC spine."""


class BoundarySuccession(NamedTuple):
    """A state that split off another, and the predecessor's pre-split published figure.

    ``published_population`` maps a census year to the predecessor's figure **as the
    source published it**, before
    :func:`usvote.census.transform.apply_virginia_boundary_correction` restated it. It
    is an **independently pinned literal**, not a recomputation of ``restated -
    successor``, for two reasons (#182 architect review, C3): the recomputation is what
    this constant is used to *check*, so deriving it would be circular; and because
    ``basis`` is deliberately not in the census natural key (D059), the published figure
    is not recoverable from the table at all — the table holds only the restated row,
    and ``transform.py`` embeds the published value in note prose.

    Only census years actually needed appear here: a succession matters only for an
    election at or after ``effective_year`` whose governing census precedes it.
    """

    predecessor: str
    successor: str
    effective_year: int
    published_population: Mapping[int, int]
    citation: str


#: Boundary successions inside the EC span. One today.
#:
#: **The elections this reaches are 1864 and 1868, and only those.** Both are governed
#: by the 1860 census, which precedes the 1863 separation, and in both West Virginia is
#: a separate state holding electoral votes. 1872 onward is governed by the 1870 census,
#: which is post-separation, so it needs nothing; 1824-1860 precede the separation
#: entirely, so Virginia's restated figure is correct there **as to the West Virginia
#: counties** and is left alone *by this constant*.
#:
#: **Read that qualifier as load-bearing, not hedging** (#253/D066). It is correct only
#: on the West Virginia axis, which is this constant's whole subject. On a *second*
#: axis the same figure is wrong for part of that span: it also carries **Alexandria
#: County**, District of Columbia until its retrocession to Virginia on 7 September
#: 1846, so for the six elections **1824-1844** the restated figure is 0.79%-0.91% high
#: and is not the borders-at-election one. That is a different mechanism (1846, DC->VA)
#: from this constant's job (1863, VA->WV), and it is corrected elsewhere — at census
#: grain by :func:`usvote.census.transform.apply_alexandria_retrocession`, with 1848's
#: reversal in :data:`BOUNDARY_RETROCESSIONS` — never by this constant.
#: :func:`assert_boundary_corrections_disjoint` asserts the two never touch the same
#: census or election.
#:
#: Without the correction, an election-year total counts West Virginia's population
#: twice — once inside restated Virginia and once as West Virginia. Virginia holds
#: **zero** electoral votes in both years (Reconstruction), so no per-state
#: persons-per-EV is affected today; the defect is live for any **aggregate** over an
#: election year, which is one step from #184.
BOUNDARY_SUCCESSIONS: tuple[BoundarySuccession, ...] = (
    BoundarySuccession(
        predecessor="Virginia",
        successor="West Virginia",
        effective_year=1863,
        published_population={1860: 1_219_630},
        citation=(
            "West Virginia was admitted 20 June 1863 under the Act of 31 December 1862 "
            "(12 Stat. 633) and President Lincoln's proclamation of 20 April 1863. The "
            "1860 census enumerated the counties concerned as part of Virginia; "
            "tabs15-65.xlsx reports them on present-day footprints, so its published "
            "Virginia (1,219,630) already excludes them and its West Virginia "
            "(376,688) holds them separately. 1,219,630 + 376,688 = 1,596,318, the "
            "separately published enumerated Virginia total for 1860."
        ),
    ),
)

#: Retrocessions whose census-grain correction must be **reversed** at election grain.
#: One today, built from the census-side constant so the figures have a single source.
#:
#: :func:`usvote.census.transform.apply_alexandria_retrocession` removes Alexandria
#: County from Virginia's 1800-1840 census rows, which makes them the borders at those
#: censuses. An election inherits its governing census's figure, so that is right for
#: every election **held before** 7 September 1846 (D066(f)'s *correction* set:
#: 1824-1844 in the EC span) and wrong for an election held **after** it on a census
#: taken before it (the *reversal* set: 1848, governed by 1840 while Alexandria was
#: Virginia's again). :func:`apply_boundary_retrocessions` adds the pinned figure back
#: for that set. Both sets are **derived** over the spine
#: (:func:`retrocession_correction_elections`, :func:`retrocession_reversal_elections`),
#: never listed: widen the spine below 1824 and the correction set grows to 1804-1820
#: while the reversal set stays {1848}.
#:
#: **Unlike a succession, the reversal has no counterparty to check against** (D066(h),
#: H2): the District of Columbia does not participate in 1848, and its census row
#: already excludes Alexandria. The census side and this side read the same constant,
#: so any cross-check between them is a consistency check, never an independent one —
#: :func:`assert_retrocession_restored` is labelled accordingly.
BOUNDARY_RETROCESSIONS: tuple[Retrocession, ...] = (ALEXANDRIA_RETROCESSION,)


def retrocession_correction_elections(
    retrocession: Retrocession, election_years: Collection[int] | None = None
) -> set[int]:
    """Elections whose inherited census figure has the transferred territory removed.

    Held before the effective date, and governed by a census the constant corrects.
    Derived over ``ec_ingest_years()`` by default (D066(f)).
    """
    years = ec_ingest_years() if election_years is None else election_years
    _assert_no_election_in_effective_year(retrocession, years)
    effective = retrocession.effective_date.year
    return {
        year
        for year in years
        if year < effective and governing_census_year(year) in retrocession.population
    }


def retrocession_reversal_elections(
    retrocession: Retrocession, election_years: Collection[int] | None = None
) -> set[int]:
    """Elections that must have the transferred territory **added back**.

    ``governing_census_year(Y) < effective < Y``: held after the effective date on a
    census taken before it. The complement of the correction set within the elections
    the corrected censuses govern (D066(f)).
    """
    years = ec_ingest_years() if election_years is None else election_years
    _assert_no_election_in_effective_year(retrocession, years)
    effective = retrocession.effective_date.year
    return {
        year for year in years if governing_census_year(year) < effective < year
    }


def _assert_no_election_in_effective_year(
    retrocession: Retrocession, election_years: Collection[int]
) -> None:
    """Refuse the one case year-grain comparison cannot decide.

    The windows compare years, which is exact only while no election falls in the
    effective year itself — then the answer would turn on the day. None does
    (1846 is not an election year); this makes that a checked fact.
    """
    effective = retrocession.effective_date.year
    if effective in set(election_years):
        raise CensusConformError(
            f"An election falls in {effective}, the year {retrocession.donor}'s "
            f"territory passed to {retrocession.recipient} "
            f"({retrocession.effective_date.isoformat()}). The retrocession windows "
            f"compare years and cannot place that election; compare dates instead."
        )


def assert_boundary_corrections_disjoint(
    successions: Collection[BoundarySuccession] = BOUNDARY_SUCCESSIONS,
    retrocessions: Collection[Retrocession] = BOUNDARY_RETROCESSIONS,
    election_years: Collection[int] | None = None,
) -> None:
    """Assert no succession and retrocession edit the same state's census or election.

    Both kinds edit Virginia today, by different mechanisms on different censuses
    (#251, AC-10): Alexandria corrects 1800-1840 and reverses at 1848; West Virginia's
    succession pins 1860 and acts at 1864/1868. Disjoint by the history, and asserted
    rather than assumed — an overlap would let one correction's drift check read the
    other's output.
    """
    years = ec_ingest_years() if election_years is None else election_years
    for succession in successions:
        succession_elections = {
            year
            for year in years
            if year >= succession.effective_year
            and governing_census_year(year) < succession.effective_year
        }
        for retrocession in retrocessions:
            if succession.predecessor != retrocession.recipient:
                continue
            censuses = set(succession.published_population) & set(
                retrocession.population
            )
            elections = succession_elections & (
                retrocession_reversal_elections(retrocession, years)
                | retrocession_correction_elections(retrocession, years)
            )
            if censuses or elections:
                raise CensusConformError(
                    f"The {succession.successor} succession and the "
                    f"{retrocession.donor} retrocession both edit "
                    f"{succession.predecessor} at census(es) {sorted(censuses)} / "
                    f"election(s) {sorted(elections)}. They are built to act on "
                    f"disjoint censuses and elections; an overlap needs a design "
                    f"decision, not a silent composition."
                )


class CoverageException(NamedTuple):
    """A participating state with no governing-census figure, and why."""

    election_year: int
    state: str
    kind: str
    reason: str


#: Every ``(election_year, state)`` that participates but has no governing-census
#: figure.
#:
#: **Measured, not estimated** (#182): every one of the **2,204** participating
#: ``(election_year, state)`` pairs across the 51 elections 1824-2024 was tested against
#: its governing census. The measurement reads two files, because the stitch does:
#: **1,898** pairs resolve to a governing census of 1990 or earlier and were checked
#: against ``tabs15-65.xlsx`` parsed in full, and the remaining **306** — the six
#: elections 2004-2024, governed by the 2000/2010/2020 censuses — against the
#: population-change table, which publishes all 51 jurisdictions for each. Three pairs
#: had no governing-census figure when that measurement was taken.
#:
#: **Two of those three were retired by #234**, which taught
#: :func:`usvote.census.parse.parse_resident_1790_1990` to read the transposed second
#: table on Alaska's and Hawaii's sheets. Their 1950 figures (128,643 and 499,794) are
#: now parsed, so ``(1960, Alaska)`` and ``(1960, Hawaii)`` are covered and their
#: entries had to go: :func:`assert_spine_states_covered`'s stale-declaration direction
#: raises on a declared exception that turns out covered, precisely so a corrections
#: catalog cannot keep claiming a figure is unreachable after someone reaches it.
#:
#: **The remaining entry is the one no code change can ever retire**, which is the
#: distinction :data:`KIND_PRESENT_BUT_UNPARSED` exists to draw — and that kind stays
#: defined with no current member, because "no instance today" is not "the concept does
#: not exist".
#:
#: The measurement found nothing else: every mid-decade admission the epic
#: worried about is covered (1864 Kansas/Nevada/West Virginia from 1860, 1876 Colorado
#: from 1870, the 1892 six and 1896 Utah from 1890, 1908 Oklahoma from 1900, 1912
#: Arizona/New Mexico from 1910), and so is DC, whose series runs from 1800. Population
#: for the remaining row is an honest **NULL** with provenance — never a zero, never an
#: interpolation (D005).
CENSUS_COVERAGE_EXCEPTIONS: tuple[CoverageException, ...] = (
    CoverageException(
        election_year=1848,
        state="Texas",
        kind=KIND_ABSENT_FROM_SOURCE,
        reason=(
            "The 1848 election is governed by the 1840 census, when Texas was the "
            "independent Republic of Texas and was not enumerated by the United "
            "States. Texas was annexed by joint resolution of 1 March 1845 (5 Stat. "
            "797) and admitted 29 December 1845 (9 Stat. 108), so its first US census "
            "is 1850. The figure does not exist and no parser change can produce it. "
            "Texas cast 4 electoral votes in 1848, so this is a real gap in any "
            "per-capita series, not a technicality."
        ),
    ),
)

_PARTICIPATION_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "is_total",
    "total_electoral_votes",
)


def _assert_is_total_is_boolean(column: pd.Series) -> None:
    """Raise unless ``is_total`` is a representation ``.astype(bool)`` reads correctly.

    :func:`usvote.spine.read_ec_participation` **deliberately does not coerce** a
    non-int ``is_total``: its docstring says a blanket ``.astype(bool)`` "would
    silently map every non-empty ``'t'``/``'f'`` string to ``True`` — treating every row
    as a totals row", and leaves the rejection to its consumer. UCSB does that in
    ``_assert_participation_shape``; this is census's equivalent. Without it the
    coercion below would drop **every** row and then report "the spine must be loaded",
    which is the opposite of the truth on a fully-loaded spine.

    Census gets its own check rather than sharing UCSB's: a census module importing from
    ``usvote/ucsb/`` is the source-to-source dependency D015 forbids.

    **Checked by value, not by dtype** (#182 review, D-1). A dtype test gets this wrong
    in both directions. It **under**-accepts: psycopg2 can hand back an ``object``
    column of real ``bool`` values, which UCSB accepts for that exact reason, and
    rejecting it would refuse a perfectly good spine. And it **over**-rejects the empty
    case: a zero-row frame has ``object`` dtype for every column because nothing was
    inferred, so a dtype test turns "the spine has not been loaded" — which the caller
    reports precisely and truthfully a few lines later — into a spurious complaint about
    types. That is the mirror image of the defect this guard exists to prevent, so the
    empty frame returns early and is left to the caller's own message.

    One **deliberate** divergence from UCSB: 0/1 integers are accepted here and rejected
    there. ``read_ec_participation`` coerces an integer ``is_total`` to ``bool`` itself,
    so on the live path it cannot arrive — and a consumer refusing what its own reader
    normalizes buys nothing. Note what is accepted is integer *values*, never nulls: the
    null check below runs **before** that early return, so a nullable ``Int64`` carrying
    ``pd.NA`` is rejected like any other null instead of slipping through it.
    """
    if column.empty:
        # Not a dtype problem. `spine_participation` reports the real one.
        return
    # The null check goes FIRST, above the integer early-return (#182 review, F-1).
    # Reversed, an `Int64` column carrying `pd.NA` takes the integer return and dies
    # later at `.astype(bool)` with a bare `ValueError` -- the nullable-column failure
    # this branch exists to report. Reachable only through an injected frame, which is
    # how #184 will call this, so it is a live path rather than a hypothetical one.
    if column.isna().any():
        raise CensusConformError(
            "EC participation 'is_total' has null value(s), so totals rows cannot be "
            "excluded — and a totals row carries a NULL state, which would enter the "
            "frame as a phantom jurisdiction."
        )
    if pd.api.types.is_integer_dtype(column):
        return
    non_bool = column.map(lambda value: not isinstance(value, bool | np.bool_))
    if non_bool.any():
        offenders = sorted({repr(value) for value in column[non_bool]})[:5]
        raise CensusConformError(
            f"EC participation 'is_total' holds non-boolean value(s) {offenders} "
            f"(dtype {column.dtype}). astype(bool) would misread them — a 't'/'f' "
            f"string column becomes all-True, marking every row a totals row and "
            f"dropping the whole spine. Expected genuine booleans, as "
            f"usvote.spine.read_ec_participation returns."
        )


def _assert_one_allotment_per_pair(frame: pd.DataFrame) -> None:
    """Raise if a ``(year, state)`` carries more than one ``total_electoral_votes``.

    The participation frame is per ``(year, state, candidate)``, so the de-duplication
    below keeps one row per pair — and would keep an **arbitrary** allotment if the
    candidate rows ever disagreed. That column is carried specifically so #183 can
    reconcile seats against the appointed allotment, so an arbitrary value there would
    propagate into the reconciliation base rather than failing. This is what makes the
    "free here, a second spine read there" trade safe.
    """
    counts = frame.groupby(["year", "state"])["total_electoral_votes"].nunique()
    offenders = counts[counts > 1]
    if not offenders.empty:
        raise CensusConformError(
            f"{len(offenders)} (year, state) pair(s) carry more than one "
            f"total_electoral_votes, so de-duplicating would keep an arbitrary "
            f"allotment: {offenders.index.tolist()[:5]}. The appointed allotment is "
            f"per (year, state); a disagreement means a partial load, or a "
            f"per-candidate correction this frame cannot hold."
        )


def spine_participation(ec_participation: pd.DataFrame) -> pd.DataFrame:
    """Return one row per participating ``(year, state)`` from the injected spine frame.

    Totals rows are dropped — they are an aggregate, not a jurisdiction. **States
    holding zero electoral votes are kept**: the Archives print an explicit ``0`` rather
    than omitting a state (the dense-fact property D026 rests on), and a Reconstruction
    state excluded from the count still existed and still had a population. Dropping
    them here would silently narrow #184's population base and hide the Virginia
    succession case entirely, since Virginia is zero-EV in both affected years.
    """
    missing = [
        column for column in _PARTICIPATION_COLUMNS if column not in ec_participation
    ]
    if missing:
        raise CensusConformError(
            f"EC participation frame is missing column(s) {missing}; got "
            f"{list(ec_participation.columns)}"
        )
    _assert_is_total_is_boolean(ec_participation["is_total"])
    frame = ec_participation.loc[~ec_participation["is_total"].astype(bool)]
    frame = frame.loc[frame["state"].notna()]
    _assert_one_allotment_per_pair(frame)
    participation = (
        frame[["year", "state", "total_electoral_votes"]]
        .drop_duplicates(subset=["year", "state"])
        .rename(columns={"year": "election_year"})
        .reset_index(drop=True)
    )
    if participation.empty:
        raise CensusConformError(
            "EC participation frame yielded no state rows; the spine must be loaded "
            "before census population can be conformed to it."
        )
    return participation


def _resident_population(census: pd.DataFrame) -> pd.DataFrame:
    """Return the resident series as a ``(census_year, state)``-unique lookup frame.

    Narrowed to ``series == 'resident'`` explicitly rather than trusting that the table
    holds one series: the ``series`` column exists precisely so a second one can be
    added as data (D059), and an unnarrowed merge would then fan out every election row
    silently. A residual duplicate — two sources for one cell, say — raises instead of
    letting the merge pick one.
    """
    for column in ("census_year", "state", "population", "basis", "series"):
        if column not in census:
            raise CensusConformError(
                f"Census frame is missing column {column!r}; got "
                f"{list(census.columns)}"
            )
    resident = census.loc[census["series"] == SERIES_RESIDENT]
    duplicated = resident.duplicated(subset=["census_year", "state"])
    if duplicated.any():
        offenders = resident.loc[duplicated, ["census_year", "state"]].head(5)
        raise CensusConformError(
            f"Census frame has {int(duplicated.sum())} duplicate "
            f"(census_year, state) cells in the resident series; a join on them would "
            f"fan out every election row. First few:\n{offenders}"
        )
    # ``series`` travels with the figure rather than being re-asserted downstream. It
    # is constant today -- this function narrows to `resident` two lines up -- and
    # carrying it anyway is what makes #184's series label a **fact about the row**
    # instead of a literal in a view that would keep saying "resident" on the day a
    # second series is admitted as data (D059's whole reason for the column).
    return resident[["census_year", "state", "population", "basis", "series"]].rename(
        columns={"census_year": "governing_census_year", "series": "population_series"}
    )


def build_election_population(
    census: pd.DataFrame,
    ec_participation: pd.DataFrame,
    *,
    successions: Collection[BoundarySuccession] = BOUNDARY_SUCCESSIONS,
    retrocessions: Collection[Retrocession] = BOUNDARY_RETROCESSIONS,
) -> pd.DataFrame:
    """Return population at ``(election_year, state)`` grain, conformed to the EC spine.

    **Spine-left by construction**: the row set is exactly what ``ec_participation``
    says participated, so the population source never votes on statehood — the
    acceptance criterion's own words. A participating state the census cannot cover
    keeps a NULL population and is labelled :data:`COVERAGE_NO_GOVERNING_FIGURE`; a
    census row for a state that did not participate that year simply has no election row
    to attach to.

    Returns :data:`ELECTION_POPULATION_COLUMNS`. Since #184 this frame **is** persisted,
    as :data:`ELECTION_POPULATION_TABLE`, and a view over that table is what exposes
    persons-per-electoral-vote (:mod:`usvote.census.per_capita`). #182, which wrote this
    function, built it only to assert over it and threw it away.
    """
    participation = spine_participation(ec_participation)
    resident = _resident_population(census)

    participation["governing_census_year"] = participation["election_year"].map(
        governing_census_year
    )
    frame = participation.merge(
        resident, on=["governing_census_year", "state"], how="left"
    )
    frame["boundary_basis"] = BOUNDARY_PRESENT_DAY
    frame.loc[frame["basis"] == BASIS_AS_ENUMERATED, "boundary_basis"] = (
        BOUNDARY_AT_ELECTION
    )
    frame = apply_boundary_successions(frame, successions=successions)
    frame = apply_boundary_retrocessions(frame, retrocessions=retrocessions)
    frame = frame.drop(columns=["basis"])

    frame["coverage"] = COVERAGE_COVERED
    frame.loc[frame["population"].isna(), "coverage"] = COVERAGE_NO_GOVERNING_FIGURE
    frame["population"] = frame["population"].astype("Int64")
    frame["election_year"] = frame["election_year"].astype(int)
    frame["governing_census_year"] = frame["governing_census_year"].astype(int)
    return frame.sort_values(
        ["election_year", "state"], kind="stable", ignore_index=True
    )[list(ELECTION_POPULATION_COLUMNS)]


def _describe(value: object) -> str:
    """Render a possibly-absent population for an error message."""
    if value is None:
        return "absent"
    if pd.isna(value):
        return "null"
    return f"{int(value):,}"  # type: ignore[call-overload]


def apply_boundary_successions(
    frame: pd.DataFrame,
    *,
    successions: Collection[BoundarySuccession] = BOUNDARY_SUCCESSIONS,
) -> pd.DataFrame:
    """Put a predecessor state's figure back on the borders in force at the election.

    Applies where an election is **at or after** a succession while its governing census
    **precedes** it — the window in which the census still described the combined
    territory but the successor is already a separate participating state.

    The corrected value is the independently pinned published figure, and the pin is
    **checked, not trusted**: this asserts ``restated - successor == published``. A
    mismatch means
    :func:`~usvote.census.transform.apply_virginia_boundary_correction` no longer
    computes what this constant records — the drift #208 could introduce — and raises
    rather than silently shipping one of the two.

    **The pin is never written where it cannot be checked.** If the predecessor's cell
    is NULL, or the successor has no row or a NULL one, this raises instead of filling
    the value in. An earlier form skipped the check in those cases and wrote the literal
    anyway, putting a plausible number in the frame with its own validation bypassed —
    the failure this module exists to refuse, and the one place it was not holding its
    own thesis.
    """
    corrected = frame.copy()
    for succession in successions:
        window = (
            (corrected["election_year"] >= succession.effective_year)
            & (corrected["governing_census_year"] < succession.effective_year)
            & (corrected["state"] == succession.predecessor)
        )
        if not window.any():
            continue
        for index in corrected.index[window]:
            census_year = int(corrected.at[index, "governing_census_year"])
            published = succession.published_population.get(census_year)
            if published is None:
                raise CensusConformError(
                    f"Election {int(corrected.at[index, 'election_year'])} needs "
                    f"{succession.predecessor}'s published {census_year} population "
                    f"(the census precedes the {succession.effective_year} "
                    f"separation of {succession.successor}), but "
                    f"BOUNDARY_SUCCESSIONS pins no figure "
                    f"for that census. Add it as an independently sourced literal — it "
                    f"cannot be recovered from the table, which holds only the "
                    f"restated row (D059)."
                )
            election_year = int(corrected.at[index, "election_year"])
            restated = corrected.at[index, "population"]
            successor_rows = corrected.loc[
                (corrected["election_year"] == election_year)
                & (corrected["state"] == succession.successor),
                "population",
            ]
            successor_population = (
                None if successor_rows.empty else successor_rows.iloc[0]
            )
            # The pin is only ever written where it can be CHECKED. Filling a NULL, or
            # an unverifiable cell, from the literal would put a plausible number in
            # the frame with the check that validates it silently bypassed — the one
            # thing this module claims never to do (#182 review, CR-F3 / GE-F5).
            unverifiable = (
                pd.isna(restated)
                or successor_population is None
                or pd.isna(successor_population)
            )
            if unverifiable:
                raise CensusConformError(
                    f"{succession.predecessor} in election {election_year} needs its "
                    f"published {census_year} figure, but the pin cannot be verified: "
                    f"{succession.predecessor} is "
                    f"{_describe(restated)} and {succession.successor} is "
                    f"{_describe(successor_population)}. Refusing to write "
                    f"BOUNDARY_SUCCESSIONS' {published:,} unchecked: a corpus that "
                    f"has lost either cell is a defect to fix, not a gap to paper "
                    f"over with a literal."
                )
            restated_value = int(restated)
            successor_value = int(successor_population)  # type: ignore[arg-type]
            implied = restated_value - successor_value
            if implied != published:
                raise CensusConformError(
                    f"{succession.predecessor}'s restated {census_year} figure "
                    f"({restated_value:,}) minus {succession.successor} "
                    f"({successor_value:,}) is {implied:,}, but "
                    f"BOUNDARY_SUCCESSIONS pins the published figure at "
                    f"{published:,}. The census correction and this constant "
                    f"disagree; one of them has drifted."
                )
            corrected.at[index, "population"] = published
            corrected.at[index, "boundary_basis"] = BOUNDARY_AT_ELECTION
    return corrected


def assert_spine_states_covered(
    frame: pd.DataFrame,
    *,
    exceptions: Collection[CoverageException] = CENSUS_COVERAGE_EXCEPTIONS,
) -> None:
    """Assert every participating state has a governing-census figure.

    **Two-way, and the second direction is the one with teeth.** An undeclared gap
    raises, which is the obvious half. A *declared* exception that turns out to be
    covered also raises: an exception is a row in a corrections catalog claiming the
    source cannot supply a figure, so a stale one is a false published claim, and
    nothing else would ever notice it. The reciprocal check is scoped to election years
    actually present in ``frame`` so a deliberately narrowed warehouse does not read as
    a stale catalog.
    """
    declared = {(item.election_year, item.state) for item in exceptions}
    missing = {
        (int(row.election_year), str(row.state))
        for row in frame.itertuples()
        if row.coverage == COVERAGE_NO_GOVERNING_FIGURE
    }
    undeclared = sorted(missing - declared)
    if undeclared:
        raise CensusConformError(
            f"{len(undeclared)} participating (election_year, state) pair(s) have no "
            f"governing-census population and are not declared in "
            f"CENSUS_COVERAGE_EXCEPTIONS: {undeclared}. Either the census corpus is "
            f"short a state, the governing-census mapping is wrong, or a genuine new "
            f"gap needs a catalog entry with its kind and citation — refusing to ship "
            f"a silent null."
        )
    years_present = {int(year) for year in frame["election_year"].unique()}
    stale = sorted(
        key for key in declared - missing if key[0] in years_present
    )
    if stale:
        raise CensusConformError(
            f"{len(stale)} declared coverage exception(s) are no longer missing: "
            f"{stale}. A coverage exception claims the source cannot supply a "
            f"figure, so "
            f"a stale one is a false claim in docs/corrections.md — remove the entry "
            f"(and, for a {KIND_PRESENT_BUT_UNPARSED!r} kind, close its follow-up)."
        )


def apply_boundary_retrocessions(
    frame: pd.DataFrame,
    *,
    retrocessions: Collection[Retrocession] = BOUNDARY_RETROCESSIONS,
) -> pd.DataFrame:
    """Add retroceded territory back for elections held after it was transferred.

    Applies to the recipient's rows in the reversal set
    (:func:`retrocession_reversal_elections` over this frame's elections). The
    governing census has had the territory removed at census grain, which is right for
    that census and wrong for an election held after the transfer. The label stays
    ``at_election``: the result is the borders-at-election figure.

    A NULL figure is left NULL — there is nothing to add to, and filling it would
    invent a value (D005). A reversal-set election whose governing census the constant
    pins no figure for **raises**: that census was never corrected, so there is nothing
    to reverse, and an election in the reversal set with no pinned census means the
    constant and the window disagree about the history.
    """
    corrected = frame.copy()
    election_years = {int(year) for year in corrected["election_year"].unique()}
    for retrocession in retrocessions:
        reversal = retrocession_reversal_elections(retrocession, election_years)
        window = corrected["election_year"].isin(reversal) & (
            corrected["state"] == retrocession.recipient
        )
        for index in corrected.index[window]:
            census_year = int(corrected.at[index, "governing_census_year"])
            transferred = retrocession.population.get(census_year)
            if transferred is None:
                raise CensusConformError(
                    f"Election {int(corrected.at[index, 'election_year'])} is in "
                    f"{retrocession.recipient}'s reversal set for the "
                    f"{retrocession.donor} retrocession, but its governing "
                    f"{census_year} census has no pinned figure: nothing was removed "
                    f"at census grain, so there is nothing to add back."
                )
            population = corrected.at[index, "population"]
            if pd.isna(population):
                continue
            corrected.at[index, "population"] = int(population) + transferred
            corrected.at[index, "boundary_basis"] = BOUNDARY_AT_ELECTION
    return corrected


def assert_retrocession_restored(
    frame: pd.DataFrame,
    census: pd.DataFrame,
    *,
    retrocessions: Collection[Retrocession] = BOUNDARY_RETROCESSIONS,
) -> None:
    """Assert the reversal restored exactly the pinned figure, to exactly its set.

    A **consistency** check, not a verification: both sides read the same constant,
    and the reversal has no counterparty to verify against (D066(h), H2). What it does
    pin is the mechanism's footprint — every recipient row in the reversal set is its
    governing census figure plus the transferred figure, and no recipient row outside
    the set is — so an applier that skips 1848, or leaks into 1844, fails here.
    """
    published = {
        (int(row.census_year), str(row.state)): row.population
        for row in census.loc[census["series"] == SERIES_RESIDENT].itertuples()
    }
    election_years = {int(year) for year in frame["election_year"].unique()}
    for retrocession in retrocessions:
        reversal = retrocession_reversal_elections(retrocession, election_years)
        rows = frame.loc[frame["state"] == retrocession.recipient]
        for row in rows.itertuples():
            census_year = int(row.governing_census_year)
            transferred = retrocession.population.get(census_year)
            raw = published.get((census_year, retrocession.recipient))
            if transferred is None or pd.isna(row.population) or raw is None:
                continue
            if pd.isna(raw):
                continue
            restored = int(row.population) - int(raw) == transferred
            in_reversal = int(row.election_year) in reversal
            if in_reversal and not restored:
                raise CensusConformError(
                    f"{retrocession.recipient} in election {int(row.election_year)} "
                    f"was held after {retrocession.donor}'s territory returned "
                    f"({retrocession.effective_date.isoformat()}) on the {census_year} "
                    f"census, so it should carry that census's figure ({int(raw):,}) "
                    f"plus {transferred:,}; it carries {int(row.population):,}."
                )
            if not in_reversal and restored:
                raise CensusConformError(
                    f"{retrocession.recipient} in election {int(row.election_year)} "
                    f"carries the retroceded {transferred:,} on top of the "
                    f"{census_year} census figure, but that election is outside the "
                    f"reversal set {sorted(reversal)}."
                )


def assert_no_double_count(
    frame: pd.DataFrame,
    *,
    successions: Collection[BoundarySuccession] = BOUNDARY_SUCCESSIONS,
) -> None:
    """Assert no state's figure includes another participating state's people.

    Checks the mechanism rather than the outcome: for each election in a succession's
    window it recomputes ``published + successor`` and raises if the predecessor's
    figure equals it, which is what a restated figure left in place looks like.
    Asserting only that the number "looks reasonable" would pass on exactly the
    uncorrected input this exists to catch.

    **It cannot fire on the path that calls it today, and that is worth stating rather
    than hiding** (#182 review, GE-F5). Inside :func:`assert_conforms_to_spine`,
    :func:`build_election_population` has already run :func:`apply_boundary_successions`
    over the *same* constant and the *same* window predicate, so where the window is
    non-empty the corrector wrote ``published`` and this equality is false by
    construction. The load path's real protection against a wrong-side restatement is
    that function's **drift assert**, which is independent. This one earns its place as
    a standalone guard — its unit test runs it on an uncorrected frame, and #184 will
    build the frame separately — not as detection in the seam.
    """
    for succession in successions:
        window = frame.loc[
            (frame["election_year"] >= succession.effective_year)
            & (frame["governing_census_year"] < succession.effective_year)
            & (frame["state"] == succession.predecessor)
        ]
        for row in window.itertuples():
            published = succession.published_population.get(
                int(row.governing_census_year)
            )
            if published is None or pd.isna(row.population):
                continue
            successor = frame.loc[
                (frame["election_year"] == row.election_year)
                & (frame["state"] == succession.successor),
                "population",
            ]
            if successor.empty or pd.isna(successor.iloc[0]):
                continue
            if int(row.population) == published + int(successor.iloc[0]):
                raise CensusConformError(
                    f"{succession.predecessor}'s {int(row.election_year)} population "
                    f"({int(row.population):,}) is the restated figure, which already "
                    f"contains {succession.successor} "
                    f"({int(successor.iloc[0]):,}) — and {succession.successor} is a "
                    f"separate participating state that election, so its people are "
                    f"counted twice. The published figure is {published:,}."
                )


def assert_no_interpolated_population(
    frame: pd.DataFrame,
    census: pd.DataFrame,
    *,
    successions: Collection[BoundarySuccession] = BOUNDARY_SUCCESSIONS,
    retrocessions: Collection[Retrocession] = BOUNDARY_RETROCESSIONS,
) -> None:
    """Assert every population is a published figure or a declared restatement (D005).

    An election year that is not a census year takes its **governing-census** figure
    unchanged — the staleness is stated by ``governing_census_year``, never smoothed
    away — so every value must be either the census table's own figure for that cell or
    a :data:`BOUNDARY_SUCCESSIONS` published literal. Anything else is synthesized.

    The second branch is not a loophole for the first: the pinned literals are a closed,
    cited set of restatements, and the succession guard above already checks each one
    against the table's arithmetic. Without that branch this assert would fire on
    exactly the corrected rows, whose value is deliberately *not* in the table (D059
    keeps ``basis`` out of the natural key, so the table holds only the restated row).

    **Retrocession reversals are admitted at election grain**, ``(election_year,
    state)``, where succession pins are keyed on the census. The difference is D066(h)
    H1: one census (1840) governs both 1844, which takes its figure unchanged, and 1848,
    which takes it plus Alexandria — so a census-keyed pin would license the 1848 value
    for 1844 too. Successions stay census-keyed because the elections a pin serves
    (1864, 1868) want the same value.
    """
    published = {
        (int(row.census_year), str(row.state)): row.population
        for row in census.loc[census["series"] == SERIES_RESIDENT].itertuples()
    }
    allowed_restatements = {
        (census_year, succession.predecessor): value
        for succession in successions
        for census_year, value in succession.published_population.items()
    }
    election_years = {int(year) for year in frame["election_year"].unique()}
    allowed_reversals: dict[tuple[int, str], int] = {}
    for retrocession in retrocessions:
        for election_year in retrocession_reversal_elections(
            retrocession, election_years
        ):
            census_year = governing_census_year(election_year)
            base = published.get((census_year, retrocession.recipient))
            transferred = retrocession.population.get(census_year)
            if base is None or pd.isna(base) or transferred is None:
                continue
            allowed_reversals[(election_year, retrocession.recipient)] = (
                int(base) + transferred
            )
    for row in frame.itertuples():
        if pd.isna(row.population):
            continue
        key = (int(row.governing_census_year), str(row.state))
        value = int(row.population)
        raw = published.get(key)
        source_value = None if raw is None or pd.isna(raw) else int(raw)
        if source_value is not None and value == source_value:
            continue
        if allowed_restatements.get(key) == value:
            continue
        if allowed_reversals.get((int(row.election_year), str(row.state))) == value:
            continue
        published_text = "null" if source_value is None else f"{source_value:,}"
        raise CensusConformError(
            f"{row.state} in election {int(row.election_year)} carries population "
            f"{value:,}, which is neither the published {key[0]} figure "
            f"({published_text}) nor a declared BOUNDARY_SUCCESSIONS or "
            f"BOUNDARY_RETROCESSIONS restatement. A "
            f"value that is neither is synthesized, which D005 forbids."
        )


def assert_conforms_to_spine(
    census: pd.DataFrame, ec_participation: pd.DataFrame
) -> None:
    """Run every conformance guard over the census frame about to be loaded.

    The one seam :mod:`usvote.census.pipeline` calls, so the load path gets all six
    checks or none — an individually-wired subset is how one of them quietly stops
    running.

    It builds the election-grain frame and throws it away. **That is now the wrapper's
    only job**: since #184 the frame *is* persisted, and the pipeline calls
    :func:`build_and_validate_election_population` — this function is the same seam with
    the return value dropped, kept because a caller that only wants the assertion
    should not have to hold a frame to get it, and because its guard-coverage test is
    the one that proves the seam cannot drift into a subset.

    Placed **before** the load rather than after, so a corpus that has lost a state or
    changed layout fails with nothing written, rather than leaving a warehouse that is
    short a state and a caller who has to know to re-run with ``replace=True``.

    **Which of the six can fail on data, and which are regression guards on the
    builder** — worth writing down, because "six guards" invites the reading that all
    six are watching the corpus (#182 review, GE-F1/GE-F5):

    * :func:`assert_spine_states_covered` is the one that genuinely fires on a
      **corpus** defect — a state whose governing-census figure has gone missing, or a
      declared exception that has gone stale. On the load path this is the data check.
    * :func:`apply_boundary_successions`' **drift assert**, inside the builder rather
      than listed here, is the other real data check: it is what catches a wrong-side
      restatement.
    * :func:`assert_no_double_count` and :func:`assert_no_interpolated_population`
      cannot fail here **by construction**: the builder has already applied the same
      succession constant, and it sources every value from the census frame or a pinned
      restatement, so both assertions are true of anything it produces. They are guards
      against a future change to :func:`build_election_population`, and they are the
      guards #184 needs when it builds this frame itself. Keeping them in the seam is
      deliberate; believing they watch the corpus would not be.
    * :func:`assert_election_population_shape` is **split**, and calling it a regression
      guard understates it (#182 review, D-3). Its **non-null branch is a data check
      with the same standing as** :func:`assert_spine_states_covered`: a NULL
      ``total_electoral_votes`` arriving from ``dwh.votes`` travels through the merge
      untouched and fires it, which is an upstream EC-load defect rather than a builder
      slip — UCSB carries a dedicated guard for exactly that case. Its other checks —
      the column set, the ``population`` dtype, and the two closed vocabularies — are
      regression guards on the builder.
    * :func:`assert_boundary_corrections_disjoint` (#251) reads only the two constants
      and the spine's year set, so it guards a future **edit to a constant**, never the
      corpus; it runs first because the others assume it.
    * :func:`assert_retrocession_restored` (#251) cannot fail here by construction
      either — the builder applied the same constant — and it is a **consistency**
      check, not a verification: the 1848 reversal has no counterparty to verify against
      (D066(h), H2). It pins the reversal's footprint against a future builder change.

    All six are called here so that the load path cannot drift into a subset, and
    ``test_the_seam_runs_every_guard`` pins exactly that — against **both** spellings,
    since the guard list now lives in the function below and this one would otherwise be
    pinned by nothing.
    """
    build_and_validate_election_population(census, ec_participation)


def assert_election_population_shape(frame: pd.DataFrame) -> None:
    """Assert the frame is on the contract #183 and #184 inherit.

    Column set and order, all three closed vocabularies, and non-null on everything
    except the two columns that carry genuine NULLs by design — ``population``, which
    must stay a **nullable integer** dtype so "no published figure" and "zero" remain
    distinguishable (the same reason :func:`usvote.census.schema.assert_census_shape`
    checks it), and ``population_series``, which is NULL in exactly the same rows.

    **The series label is coupled to the figure, and the coupling is asserted in both
    directions.** A row with a population must say which series it came from; a row with
    none must not claim one. Writing ``'resident'`` beside a NULL would assert the
    provenance of a value that does not exist — the D005 discipline applied to a label
    rather than to a number — and the reverse, a figure whose label went missing, is
    what a merge that dropped the column looks like while every other check still
    passes.
    """
    if list(frame.columns) != list(ELECTION_POPULATION_COLUMNS):
        raise CensusConformError(
            f"Election-population frame columns {list(frame.columns)} != contract "
            f"{list(ELECTION_POPULATION_COLUMNS)}"
        )
    for column in ELECTION_POPULATION_COLUMNS:
        if column in NULLABLE_ELECTION_POPULATION_COLUMNS:
            continue
        if frame[column].isna().any():
            raise CensusConformError(
                f"Election-population column {column!r} has null value(s) "
                f"(required non-null)"
            )
    if not pd.api.types.is_integer_dtype(frame["population"]):
        raise CensusConformError(
            f"Election-population 'population' must be a nullable integer dtype (e.g. "
            f"Int64), got {frame['population'].dtype}. A float dtype means the NULLs "
            f"became NaN and the counts became floats."
        )
    mismatched = frame["population"].isna() != frame["population_series"].isna()
    if mismatched.any():
        offenders = frame.loc[
            mismatched, ["election_year", "state", "population", "population_series"]
        ].head(5)
        raise CensusConformError(
            f"{int(mismatched.sum())} row(s) have a population without a series label "
            f"or a series label without a population; the label describes the figure, "
            f"so one cannot exist without the other. First few:\n{offenders}"
        )
    for column, vocabulary in (
        ("boundary_basis", BOUNDARY_BASIS_VALUES),
        ("coverage", COVERAGE_VALUES),
        ("population_series", SERIES_VALUES),
    ):
        unknown = sorted(set(frame[column].dropna().unique()) - set(vocabulary))
        if unknown:
            raise CensusConformError(
                f"Election-population column {column!r} carries value(s) {unknown} "
                f"outside its closed vocabulary {list(vocabulary)}"
            )


# --- the persisted election-grain table (#184 / D064) -----------------------
#
# **Why the DDL for this table lives here and not in** :mod:`usvote.census.schema`,
# which owns every other census DDL. That module is imported *by* this one, for
# ``SERIES_RESIDENT`` and the ``basis`` vocabulary; the CHECK constraints below are
# built from ``BOUNDARY_BASIS_VALUES`` and ``COVERAGE_VALUES``, which are defined
# **here** because they are election-grain vocabularies deliberately distinct from the
# census ones (see ``BOUNDARY_BASIS_VALUES``' own note). Putting the builders in
# ``schema.py`` would make it import this module back, and the cycle is real rather
# than stylistic. The convention that module states — a closed vocabulary lives where
# neither of its two callers has to depend on the other — is honoured, not abandoned:
# here that place is this module, which assigns the values, while
# :mod:`usvote.census.load` builds the CHECKs from them.


def build_boundary_basis_check(column: str = "boundary_basis") -> str:
    """Return the ``boundary_basis`` CHECK built from :data:`BOUNDARY_BASIS_VALUES`."""
    values = ", ".join(f"'{value}'" for value in BOUNDARY_BASIS_VALUES)
    return f"CHECK ({column} IN ({values}))"


def build_coverage_check(column: str = "coverage") -> str:
    """Return the ``coverage`` CHECK built from :data:`COVERAGE_VALUES`."""
    values = ", ".join(f"'{value}'" for value in COVERAGE_VALUES)
    return f"CHECK ({column} IN ({values}))"


def build_election_population_column_defs(
    schema: str = CENSUS_SCHEMA,
) -> list[tuple[str, ...]]:
    """Return the ``election_population`` column defs as ``DBC.create_table`` tuples.

    A function rather than a constant because the ``state`` FK embeds ``schema``, the
    same reason :func:`usvote.census.schema.build_census_column_defs` is one.

    Three column types carry an argument:

    * ``population`` is ``integer``, never ``smallint`` — the same overflow the census
      dimension's own DDL note explains, one table over.
    * ``total_electoral_votes`` is ``smallint`` because it really is an electoral-vote
      count, matching the EC fact it was read from.
    * ``population`` and ``population_series`` are the only nullable columns
      (:data:`NULLABLE_ELECTION_POPULATION_COLUMNS`). Their NULLs are the honest gap a
      participating state with no governing-census figure leaves (D005), and the
      database is where that guarantee stops being a pandas dtype and starts being a
      constraint.
    """
    return [
        ("election_population_id", "integer", "generated always as identity",
         "primary key"),
        ("election_year", "smallint", "not null"),
        ("state", "varchar", "not null", f"REFERENCES {schema}.state"),
        ("governing_census_year", "smallint", "not null"),
        ("total_electoral_votes", "smallint", "not null"),
        ("population", "integer"),
        ("boundary_basis", "varchar", "not null", build_boundary_basis_check()),
        ("coverage", "varchar", "not null", build_coverage_check()),
        ("population_series", "varchar", build_series_check("population_series")),
        (
            "CONSTRAINT",
            f"{ELECTION_POPULATION_TABLE}_natural_key",
            "UNIQUE",
            f"({', '.join(ELECTION_POPULATION_NATURAL_KEY)})",
        ),
    ]


def build_and_validate_election_population(
    census: pd.DataFrame, ec_participation: pd.DataFrame
) -> pd.DataFrame:
    """Build the election-grain frame, run every conformance guard, and return it.

    The seam :func:`assert_conforms_to_spine` is the discarding wrapper around — and the
    one :mod:`usvote.census.pipeline` calls now that the frame is persisted (#184). The
    guards it runs, and which of them can fail on data, are documented on that function;
    they are not repeated here, because one statement of that is the point.

    **One derivation, one read.** Before #184 the pipeline called the seam, which built
    this frame and threw it away, and #184 would then have built it again to load it.
    Two builds of the same frame from the same inputs is the shape a divergence hides
    in, and it costs a second pass over the whole 2,204-row conformance for nothing.
    """
    assert_boundary_corrections_disjoint()
    frame = build_election_population(census, ec_participation)
    assert_election_population_shape(frame)
    assert_spine_states_covered(frame)
    assert_no_double_count(frame)
    assert_no_interpolated_population(frame, census)
    assert_retrocession_restored(frame, census)
    return frame
