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
:mod:`usvote.census.pipeline`. Nothing in this module names ``dwh.votes``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import NamedTuple

import pandas as pd

from usvote.apportionment import governing_census_year
from usvote.census.schema import BASIS_AS_ENUMERATED, SERIES_RESIDENT

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
ELECTION_POPULATION_COLUMNS: tuple[str, ...] = (
    "election_year",
    "state",
    "governing_census_year",
    "total_electoral_votes",
    "population",
    "boundary_basis",
    "coverage",
)

#: Whether a figure is on the borders **in force at the election**.
#:
#: **This is not the census ``basis`` and must not be conflated with it** (#182
#: architect review, C2d). ``census_population.basis`` answers "borders at census time
#: vs modern". At election grain the question is "borders at *this election*", and the
#: two disagree exactly where this module works: for the elections 1824-1860 Virginia's
#: **restated** (``as_enumerated``) figure is borders-at-election, but for 1864 and 1868
#: the **published** (``present_day``) figure is *also* borders-at-election, because
#: West Virginia is a separate state by then. Carrying the census label through would
#: stamp 1864 Virginia ``present_day`` — an honesty warning — on the figure that is in
#: fact correct for that election.
#:
#: ``present_day`` is the honest default and says only "this is the published figure; we
#: have not asserted it is the as-at-election one". Asserting ``at_election`` for all
#: fifty states is precisely the unverified claim **#208** exists to settle, so today
#: the only rows carrying it are Virginia 1824-1868.
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
#: entirely, so Virginia's restated figure is correct there and is left alone.
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
#: population-change table, which publishes all 51 jurisdictions for each. These three
#: are the complete set — every mid-decade admission the epic
#: worried about is covered (1864 Kansas/Nevada/West Virginia from 1860, 1876 Colorado
#: from 1870, the 1892 six and 1896 Utah from 1890, 1908 Oklahoma from 1900, 1912
#: Arizona/New Mexico from 1910), and so is DC, whose series runs from 1800. Population
#: for these rows is an honest **NULL** with provenance — never a zero, never an
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
    CoverageException(
        election_year=1960,
        state="Alaska",
        kind=KIND_PRESENT_BUT_UNPARSED,
        reason=(
            "The 1960 election is governed by the 1950 census. Alaska's 1950 resident "
            "population (128,643) IS published in tabs15-65.xlsx, but on the sheet's "
            "second table, which is transposed — race per row, census year across "
            "columns — and carries neither the NUMBER nor the PERCENT marker that "
            "parse_resident_1790_1990 keys on, so it is never read. Alaska was "
            "admitted 3 January 1959 (Pub. L. 85-508) and cast 3 electoral votes in "
            "1960. Fixable; tracked as the #182 follow-up."
        ),
    ),
    CoverageException(
        election_year=1960,
        state="Hawaii",
        kind=KIND_PRESENT_BUT_UNPARSED,
        reason=(
            "As Alaska: Hawaii's 1950 resident population (499,794) is published in "
            "the same transposed second table and is unread for the same reason. Note "
            "the year header sits in a different column than Alaska's (C29 against "
            "B29), so a fix must locate it by content rather than by index. Hawaii was "
            "admitted 21 August 1959 (Pub. L. 86-3) and cast 3 electoral votes in "
            "1960."
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
    """
    if pd.api.types.is_bool_dtype(column) or pd.api.types.is_integer_dtype(column):
        return
    raise CensusConformError(
        f"EC participation 'is_total' has dtype {column.dtype}, which "
        f"astype(bool) would misread — a 't'/'f' string column becomes all-True, "
        f"marking every row a totals row and dropping the whole spine. Expected bool "
        f"or 0/1 int (what usvote.spine.read_ec_participation returns from psycopg2)."
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
    return resident[["census_year", "state", "population", "basis"]].rename(
        columns={"census_year": "governing_census_year"}
    )


def build_election_population(
    census: pd.DataFrame,
    ec_participation: pd.DataFrame,
    *,
    successions: Collection[BoundarySuccession] = BOUNDARY_SUCCESSIONS,
) -> pd.DataFrame:
    """Return population at ``(election_year, state)`` grain, conformed to the EC spine.

    **Spine-left by construction**: the row set is exactly what ``ec_participation``
    says participated, so the population source never votes on statehood — the
    acceptance criterion's own words. A participating state the census cannot cover
    keeps a NULL population and is labelled :data:`COVERAGE_NO_GOVERNING_FIGURE`; a
    census row for a state that did not participate that year simply has no election row
    to attach to.

    Returns :data:`ELECTION_POPULATION_COLUMNS`. This is #184's input; it is **not**
    persisted — #182 adds no table and no view.
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
            f"(and, for a 'present_but_unparsed' kind, close its follow-up)."
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
        published_text = "null" if source_value is None else f"{source_value:,}"
        raise CensusConformError(
            f"{row.state} in election {int(row.election_year)} carries population "
            f"{value:,}, which is neither the published {key[0]} figure "
            f"({published_text}) nor a declared BOUNDARY_SUCCESSIONS restatement. A "
            f"value that is neither is synthesized, which D005 forbids."
        )


def assert_conforms_to_spine(
    census: pd.DataFrame, ec_participation: pd.DataFrame
) -> None:
    """Run every conformance guard over the census frame about to be loaded.

    The one seam :mod:`usvote.census.pipeline` calls, so the load path gets all four
    checks or none — an individually-wired subset is how one of them quietly stops
    running.

    It builds the election-grain frame and throws it away: #182 persists nothing, and
    the guards are the deliverable. #184 will build the same frame for real via
    :func:`build_election_population`.

    Placed **before** the load rather than after, so a corpus that has lost a state or
    changed layout fails with nothing written, rather than leaving a warehouse that is
    short a state and a caller who has to know to re-run with ``replace=True``.

    **Which of the four can fail on data, and which are regression guards on the
    builder** — worth writing down, because "four guards" invites the reading that all
    four are watching the corpus (#182 review, GE-F1/GE-F5):

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
    * :func:`assert_election_population_shape` is mostly the same kind of regression
      guard, with two branches that would catch a real dtype or vocabulary slip.

    All four are called here so that the load path cannot drift into a subset, and
    ``test_the_seam_runs_every_guard`` pins exactly that.
    """
    frame = build_election_population(census, ec_participation)
    assert_election_population_shape(frame)
    assert_spine_states_covered(frame)
    assert_no_double_count(frame)
    assert_no_interpolated_population(frame, census)


def assert_election_population_shape(frame: pd.DataFrame) -> None:
    """Assert the frame is on the contract #183 and #184 inherit.

    Column set and order, both closed vocabularies, and non-null on everything except
    ``population`` — which carries genuine NULLs by design, and must stay a **nullable
    integer** dtype so "no published figure" and "zero" remain distinguishable (the same
    reason :func:`usvote.census.schema.assert_census_shape` checks it).
    """
    if list(frame.columns) != list(ELECTION_POPULATION_COLUMNS):
        raise CensusConformError(
            f"Election-population frame columns {list(frame.columns)} != contract "
            f"{list(ELECTION_POPULATION_COLUMNS)}"
        )
    for column in ELECTION_POPULATION_COLUMNS:
        if column == "population":
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
    for column, vocabulary in (
        ("boundary_basis", BOUNDARY_BASIS_VALUES),
        ("coverage", COVERAGE_VALUES),
    ):
        unknown = sorted(set(frame[column].dropna().unique()) - set(vocabulary))
        if unknown:
            raise CensusConformError(
                f"Election-population column {column!r} carries value(s) {unknown} "
                f"outside its closed vocabulary {list(vocabulary)}"
            )
