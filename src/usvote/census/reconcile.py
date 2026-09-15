"""Reconcile published House seats against the recorded electoral allotment (#183).

The allotment implied by an apportionment is already in
``dwh.votes.total_electoral_votes``, so the census-derived seat count can be checked
against it across the whole series. This is the epic's strongest validation (#129) and
it has the two-way shape :func:`usvote.pv.absences.assert_catalog_matches_spine` and
:func:`usvote.census.conform.assert_spine_states_covered` already use.

**Where the disagreements win, and the one place that is not the whole story.** The
recorded electoral votes are authoritative (D006: the Archives are the spine), so a
disagreement is a **documented correction**, never a silent adjustment of the fact —
:data:`SEAT_RECONCILIATION_EXCEPTIONS` is that document, catalogued in
``docs/corrections.md``, and an **undeclared** disagreement fails the build.

**But "the record wins" is a rule about precedence, not a claim that every recorded
value is right.** One catalogued row — ``(1864, Nevada)`` — is a case where the record
is *known* to disagree with the repo's own D041 contract, and the catalog says so in as
many words rather than recording the register as correct there. That is what
:data:`KIND_RECORD_UNDERSTATES_ALLOTMENT` exists for, and why it is a separate kind:
laundering a known defect into "the record is authoritative here" is exactly the
inversion D046 warns about.

**The rule, and the wrong-easy-answer it is not.** A state's electoral allotment is its
apportioned House seats **plus two** for its senators::

    expected = seats(governing_census_year(election_year), state) + 2

Reconciling raw seats against ``total_electoral_votes`` is off by exactly 2 for every
state in every year, and wholly wrong for the District of Columbia, whose three votes
come from the Twenty-third Amendment and are **not apportioned from any census**. DC is
handled in the derivation rather than as 16 near-identical catalog rows; the catalog is
for genuine *disagreements*, and DC is a rule.

**The spine is dense, and that decides which direction catches what.** The Archives
print an explicit ``0`` for a state that cast no electoral votes rather than omitting it
(the property D026 rests on, guarded by ``transform.assert_rectangular_state_grain``).
So a Reconstruction state excluded from the count, and West Virginia holding votes the
1860 apportionment never gave it, are **both** rows that exist and disagree — both
caught by :func:`_assert_every_allotment_is_explained`, iterating the electoral record.
Describing the *reverse* direction as the West Virginia catcher (as an earlier draft of
this story's plan did) gets the mechanism backwards, and a reverse guard was written and
then **removed**: on a dense spine it could not fire at all, because both of its inputs
derived from one call to :func:`spine_participation` over one frame. A guard whose
difference is empty for every possible input is not a backstop; it is a comment that
raises.

**The check with real teeth is the stale-declaration reciprocal**
(:func:`_assert_no_stale_exception`): a declared exception that starts *reconciling*
must fail. Nothing else reads that claim, so without it ``docs/corrections.md`` could go
on asserting a discrepancy that no longer exists.

**Layering.** The EC spine arrives as an **injected frame**, exactly as
:func:`usvote.census.transform.transform_census` and
:func:`usvote.census.conform.assert_conforms_to_spine` take it — the D006-allowed
direction. No **code** here names the EC fact table — the invariant is enforced by
``test_no_lower_subpackage_names_the_ec_votes_fact_in_code[census]``, which #183 added
``census`` to after finding the claim was convention rather than enforcement — and
the DB read stays in :mod:`usvote.census.pipeline`.

It consumes :func:`usvote.census.conform.spine_participation` rather than the fuller
:func:`usvote.census.conform.build_election_population`: the thinner seam carries
exactly ``(election_year, state, total_electoral_votes)`` off the same injected frame,
so there is still no second spine read, while a population-side failure — a
boundary-pin drift, #208 — cannot block a **seat** reconciliation that never looks at
population.
"""

from __future__ import annotations

from typing import NamedTuple

import pandas as pd

from usvote.apportionment import governing_census_year
from usvote.census.conform import spine_participation
from usvote.census.seats import SEATS_BY_CENSUS

#: Every state's two senatorial electors, the constant difference between an
#: apportionment and an allotment (U.S. Const. art. II, § 1, cl. 2).
SENATORIAL_ELECTORAL_VOTES = 2

#: The District of Columbia's allotment under the Twenty-third Amendment, and the first
#: presidential election it applied to. The Amendment was ratified 29 March 1961 and
#: caps DC at "the least populous State", which has been three throughout. These votes
#: are **not** apportioned from any census — DC is ``(X)`` in every apportionment table.
DC_STATE_NAME = "District of Columbia"
DC_ELECTORAL_VOTES = 3
DC_FIRST_ELECTION = 1964

#: A state that held apportioned seats but whose electoral votes were **not counted**.
#: A fact about Reconstruction, not a defect in any source.
KIND_ELECTORAL_VOTES_WITHHELD = "electoral_votes_withheld"

#: A state that held electoral votes with **no apportioned seats** under the governing
#: census — admitted mid-decade, after the apportionment. The case a one-sided
#: "missing state" guard silently passes.
KIND_SEATS_NOT_APPORTIONED = "seats_not_apportioned"

#: A row where the **recorded allotment is a cast figure**, not the appointed one — so
#: the electoral record, not the census, is the side that is wrong.
#:
#: **This kind is deliberately uncomfortable, and it is separate for that reason.** The
#: other two record a real historical fact; this one records a **known defect in the
#: spine** that this repo has not yet corrected. Folding it into either of the others
#: would file a defect as a fact. Declaring it under a bare "the record is
#: authoritative" framing would be worse still: it would enter, in a corrections
#: catalog, the claim that a cast figure *is* the allotment — the exact inversion of
#: D041/D046's ``appointed >= cast >= counted`` ladder.
#:
#: **It is self-cleaning.** When the spine correction lands, the row reconciles, and
#: :func:`_assert_no_stale_exception`'s first branch fires and forces this entry's
#: removal. The catalog cannot quietly outlive the defect it describes.
KIND_RECORD_UNDERSTATES_ALLOTMENT = "electoral_record_understates_allotment"

#: The closed vocabulary, on the :data:`usvote.census.conform.EXCEPTION_KINDS`
#: precedent.
SEAT_EXCEPTION_KINDS: tuple[str, ...] = (
    KIND_ELECTORAL_VOTES_WITHHELD,
    KIND_SEATS_NOT_APPORTIONED,
    KIND_RECORD_UNDERSTATES_ALLOTMENT,
)


class SeatReconciliationError(RuntimeError):
    """Raised when the seat series and the electoral record disagree undeclarably."""


class SeatException(NamedTuple):
    """One declared disagreement between the seat series and the electoral record.

    ``recorded_electoral_votes`` is pinned so the exception describes a *specific*
    disagreement rather than licensing any value: if the recorded allotment changes, the
    declaration stops matching and the build fails, which is what stops this catalog
    becoming a blanket waiver for a whole ``(year, state)``. ``citation`` is a
    public-domain source, exactly as :class:`usvote.pv.absences.PVAbsence` requires.
    """

    election_year: int
    state: str
    kind: str
    recorded_electoral_votes: int
    citation: str
    note: str


_REBELLION_1864 = (
    "Joint Resolution (H.R. 126, 38th Cong.), adopted before the 8 February 1865 "
    "count, declared the states in rebellion ineligible to cast electoral votes. The "
    "states had been apportioned seats under the Act of 4 March 1862 (12 Stat. 353) "
    "implementing the 1860 census; the seats existed and the electoral votes did not."
)

_NOT_READMITTED_1868 = (
    "Mississippi, Texas and Virginia were not readmitted to representation in time to "
    "appoint electors in 1868: the Omnibus Act, 15 Stat. 73 (25 June 1868), readmitted "
    "other reconstructed states but not these three, which were readmitted in 1870 "
    "(Virginia, 16 Stat. 62, 26 January 1870; Mississippi, 16 Stat. 67, 23 February "
    "1870; Texas, 16 Stat. 80, 30 March 1870). They held apportioned seats under the "
    "1860 census throughout."
)

_WEST_VIRGINIA_ADMISSION = (
    "West Virginia was admitted 20 June 1863 under the Act of 31 December 1862 (12 "
    "Stat. 633), after the 1860 apportionment had been enacted (Act of 4 March 1862, "
    "12 Stat. 353). Its representation came from the admission statute rather than "
    "from that apportionment, which is why the published apportionment table records "
    "(X) for West Virginia in the 1860 column while the state demonstrably appointed "
    "electors in 1864 and 1868."
)

_NEVADA_1864_ADMISSION = (
    "Nevada was admitted 31 October 1864 by presidential proclamation (13 Stat. 749) "
    "under the Enabling Act of 21 March 1864 (13 Stat. 30), eight days before the "
    "election, and was apportioned one representative under the 1860 census. One "
    "representative plus two senators is an appointed allotment of three; the National "
    "Archives table prints two in its allotment column, and its 1864 national total of "
    "233 is likewise a count of votes cast."
)

#: Every ``(election_year, state)`` where the published seats and the recorded allotment
#: disagree, with the cause. **Seventeen rows, in three kinds.** Two of them are facts
#: about history — seats without electoral votes, and electoral votes without seats —
#: and the third records a known defect in the electoral record itself.
#:
#: The 14 withheld rows are **1864 and 1868 only** — 11 states in 1864, three in 1868.
#: 1872 has none: by then every state was readmitted, and Arkansas's and Louisiana's
#: refused votes are a ``count_status`` matter (D046) rather than an allotment one,
#: since their allotments are restored to reach the 366 denominator Congress announced.
#:
#: **Georgia 1868 is deliberately not here.** Its nine votes were counted as
#: ``disputed`` (D044) rather than withheld, and its allotment is intact, so it
#: reconciles as an ordinary row. Whether those votes counted is a different question
#: from how many the state was allotted, and only the second is this module's business.
SEAT_RECONCILIATION_EXCEPTIONS: tuple[SeatException, ...] = (
    *(
        SeatException(
            election_year=1864,
            state=state,
            kind=KIND_ELECTORAL_VOTES_WITHHELD,
            recorded_electoral_votes=0,
            citation=_REBELLION_1864,
            note=(
                f"{state} held apportioned seats under the governing 1860 census and "
                f"cast no electoral votes in 1864."
            ),
        )
        for state in (
            "Alabama",
            "Arkansas",
            "Florida",
            "Georgia",
            "Louisiana",
            "Mississippi",
            "North Carolina",
            "South Carolina",
            "Tennessee",
            "Texas",
            "Virginia",
        )
    ),
    *(
        SeatException(
            election_year=1868,
            state=state,
            kind=KIND_ELECTORAL_VOTES_WITHHELD,
            recorded_electoral_votes=0,
            citation=_NOT_READMITTED_1868,
            note=(
                f"{state} held apportioned seats under the governing 1860 "
                f"census — 1868 still ran on it, the 1870 census first governing "
                f"1872 — and cast no electoral votes."
            ),
        )
        for state in ("Mississippi", "Texas", "Virginia")
    ),
    *(
        SeatException(
            election_year=year,
            state="West Virginia",
            kind=KIND_SEATS_NOT_APPORTIONED,
            recorded_electoral_votes=5,
            citation=_WEST_VIRGINIA_ADMISSION,
            note=(
                "West Virginia is (X) in the 1860 seats column yet appointed electors "
                "in this election. Its five votes are three representatives from the "
                "admission statute plus two senators."
            ),
        )
        for year in (1864, 1868)
    ),
    SeatException(
        election_year=1864,
        state="Nevada",
        kind=KIND_RECORD_UNDERSTATES_ALLOTMENT,
        recorded_electoral_votes=2,
        citation=_NEVADA_1864_ADMISSION,
        note=(
            "The recorded 2 is a count of votes CAST; the appointed allotment is 3 "
            "(one representative under the 1860 census, plus two senators). This is "
            "the same appointed-exceeds-cast situation as 1832 Maryland and 2000 DC, "
            "which this repo records in ELECTORAL_VOTE_SHORTFALLS; it differs only in "
            "which figure the Archives printed in the allotment column — the appointed "
            "one there, the cast one here. So the recorded allotment carries a cast "
            "figure in a column D041 defines as appointed. Correcting the spine "
            "moves the 1864 denominator from 233 to 234 and so changes ec_share_full "
            "and the public API snapshot content hash, which is an EC-domain change "
            "deferred to its own issue rather than made inside a census validation "
            "story — it is tracked as #243. When it lands this row will reconcile and "
            "the stale-declaration guard will require this entry's removal."
        ),
    ),
)


def _exception_index() -> dict[tuple[int, str], SeatException]:
    index: dict[tuple[int, str], SeatException] = {}
    for exception in SEAT_RECONCILIATION_EXCEPTIONS:
        key = (exception.election_year, exception.state)
        if key in index:
            raise SeatReconciliationError(
                f"SEAT_RECONCILIATION_EXCEPTIONS declares {key} twice; a duplicate "
                f"makes the catalog's own meaning ambiguous."
            )
        if exception.kind not in SEAT_EXCEPTION_KINDS:
            raise SeatReconciliationError(
                f"SEAT_RECONCILIATION_EXCEPTIONS entry {key} has kind "
                f"{exception.kind!r}, outside the closed vocabulary "
                f"{list(SEAT_EXCEPTION_KINDS)}"
            )
        index[key] = exception
    return index


def expected_electoral_votes(election_year: int, state: str) -> int | None:
    """Return the allotment the published apportionment implies, or ``None``.

    ``None`` means *the published series states this jurisdiction had no apportioned
    seats* — the source's own ``(X)`` — and never "unknown": a state missing from the
    curated series raises instead, via :func:`assert_seats_series_complete`.

    The District of Columbia is answered from the Twenty-third Amendment rather than
    from any census, since it is ``(X)`` in every apportionment table.
    """
    if state == DC_STATE_NAME:
        return DC_ELECTORAL_VOTES if election_year >= DC_FIRST_ELECTION else 0
    census_year = governing_census_year(election_year)
    seats = SEATS_BY_CENSUS[census_year][state]
    if seats is None:
        return None
    return seats + SENATORIAL_ELECTORAL_VOTES


def assert_seats_series_complete(participation: pd.DataFrame) -> None:
    """Assert the curated seats cover every ``(governing census, participating state)``.

    **A seat cell has three states, not two**, and collapsing the last two is how a
    curation omission cements itself into the catalog:

    ==============  ======================================  ========================
    cell            meaning                                 effect
    ==============  ======================================  ========================
    a digit         apportioned seats                       ``seats + 2``
    explicit None   the source's ``(X)``: no seats          needs a declared exception
    **key absent**  **a curation omission**                 **fails, unconditionally**
    ==============  ======================================  ========================

    Without this, a state forgotten from :data:`usvote.census.seats.SEATS_BY_CENSUS`
    would be indistinguishable from a legitimate ``(X)``, would need only a
    plausible-looking exception declaration to pass, and the acceptance criterion that
    an **unexplained** gap fails the build would quietly stop being true.

    Spine-left, like every guard in this package: the census never votes on which states
    existed (D006). A census jurisdiction that did not participate is simply not tested.
    """
    missing: list[tuple[int, str]] = []
    for row in participation.itertuples(index=False):
        state = str(row.state)
        if state == DC_STATE_NAME:
            continue
        census_year = governing_census_year(int(row.election_year))
        by_state = SEATS_BY_CENSUS.get(census_year)
        if by_state is None or state not in by_state:
            missing.append((census_year, state))
    if missing:
        unique = sorted(set(missing))
        raise SeatReconciliationError(
            f"The curated seat series is missing {len(unique)} "
            f"(census_year, state) cell(s) that the electoral record needs: "
            f"{unique[:10]}{' …' if len(unique) > 10 else ''}. An absent key is a "
            f"curation omission, not the source's (X) — add the cell to "
            f"usvote/census/seats.py (scripts/extract_census_seats.py renders the "
            f"published table to compare against) rather than declaring an exception "
            f"for it."
        )


def build_seat_reconciliation(ec_participation: pd.DataFrame) -> pd.DataFrame:
    """Return one row per participating ``(election_year, state)`` with both allotments.

    Columns: ``election_year``, ``state``, ``governing_census_year``, ``seats``,
    ``expected_electoral_votes``, ``total_electoral_votes``, ``reconciles``.
    ``seats`` and ``expected_electoral_votes`` are nullable integers so the source's
    ``(X)`` stays distinguishable from zero.
    """
    participation = spine_participation(ec_participation)
    assert_seats_series_complete(participation)

    records = []
    for row in participation.itertuples(index=False):
        state = str(row.state)
        year = int(row.election_year)
        census_year = governing_census_year(year)
        seats = (
            None
            if state == DC_STATE_NAME
            else SEATS_BY_CENSUS[census_year][state]
        )
        expected = expected_electoral_votes(year, state)
        recorded = int(row.total_electoral_votes)
        records.append(
            {
                "election_year": year,
                "state": state,
                "governing_census_year": census_year,
                "seats": seats,
                "expected_electoral_votes": expected,
                "total_electoral_votes": recorded,
                "reconciles": expected is not None and expected == recorded,
            }
        )
    frame = pd.DataFrame.from_records(records)
    frame["seats"] = frame["seats"].astype("Int64")
    frame["expected_electoral_votes"] = frame["expected_electoral_votes"].astype(
        "Int64"
    )
    return frame


def _assert_every_allotment_is_explained(frame: pd.DataFrame) -> None:
    """Direction 1 — every recorded allotment is seats + 2, DC, or a declared exception.

    This is the direction that catches **both** live exception classes, because the
    spine is dense: a Reconstruction state excluded from the count is an explicit
    ``0``-vote row, and West Virginia is a row whose seats are ``(X)``. Both are present
    and both disagree here.
    """
    index = _exception_index()
    unexplained = []
    for row in frame.itertuples(index=False):
        if row.reconciles:
            continue
        key = (int(row.election_year), str(row.state))
        exception = index.get(key)
        if exception is not None and (
            exception.recorded_electoral_votes == int(row.total_electoral_votes)
        ):
            continue
        expected = (
            "no apportioned seats"
            if pd.isna(row.expected_electoral_votes)
            else int(row.expected_electoral_votes)
        )
        unexplained.append(
            f"{key[1]} in {key[0]}: published apportionment implies {expected}, "
            f"record says {int(row.total_electoral_votes)}"
        )
    if unexplained:
        raise SeatReconciliationError(
            f"{len(unexplained)} electoral allotment(s) the published apportionment "
            f"does not explain and no exception declares: "
            f"{unexplained[:10]}{' …' if len(unexplained) > 10 else ''}. The recorded "
            f"electoral votes win (D006) — add a SEAT_RECONCILIATION_EXCEPTIONS entry "
            f"with a public-domain citation and a docs/corrections.md row, or fix the "
            f"seat series. Do not round the difference away."
        )


def _assert_no_stale_exception(frame: pd.DataFrame) -> None:
    """The reciprocal, and the one with real teeth.

    A declared exception whose ``(year, state)`` now **reconciles** is a false claim in
    ``docs/corrections.md``, and nothing else in the pipeline reads that claim — exactly
    the direction :func:`usvote.census.conform.assert_spine_states_covered` exists for.
    It checks **one** thing, deliberately. An earlier version also re-checked that a
    declaration's ``recorded_electoral_votes`` still matched the record — but that
    condition is precisely what makes :func:`_assert_every_allotment_is_explained`
    refuse the exception and raise, and that guard runs first, so the branch was
    unreachable through the seam. The pinning it was meant to provide is real and still
    holds; it is
    enforced *there*, where the exception is matched, not here.
    """
    reconciling = {
        (int(row.election_year), str(row.state)): bool(row.reconciles)
        for row in frame.itertuples(index=False)
    }
    # **Scoped to the pairs the frame actually carries, and that bound is load-bearing
    # rather than lazy.** This guard runs on whatever frame it is handed, and a frame
    # can legitimately be partial — a spine loaded for a subset of years, a test over
    # one state. So an *absent* pair is genuinely ambiguous here: it may mean the state
    # did not participate (stale) or merely that the frame does not reach it (fine),
    # and nothing in the frame distinguishes them. An earlier version of this guard
    # read absence as stale and duly reported twelve 1864 declarations as false the
    # first time it met a ten-election frame.
    #
    # **The membership claim is therefore asserted where completeness is guaranteed
    # instead of guessed**: offline against the committed EC roster in
    # ``tests/unit/test_census_reconcile.py::TestTheRosterFixtureAgrees``, and against
    # the live spine in ``tests/integration/test_census_reconcile.py``. What is checked
    # *here* is what a partial frame can soundly answer — that no declared disagreement
    # has quietly become an agreement.
    stale = []
    for exception in SEAT_RECONCILIATION_EXCEPTIONS:
        key = (exception.election_year, exception.state)
        if key not in reconciling:
            continue
        if reconciling[key]:
            stale.append(f"{key[1]} in {key[0]} now reconciles without an exception")
    if stale:
        raise SeatReconciliationError(
            f"{len(stale)} stale SEAT_RECONCILIATION_EXCEPTIONS entr(ies): {stale}. A "
            f"declared exception that no longer describes a real disagreement is a "
            f"false entry in docs/corrections.md — remove it there and here."
        )


def assert_seats_reconcile(ec_participation: pd.DataFrame) -> None:
    """Run every seat-reconciliation guard. The one seam its callers use.

    Both guards or neither, so an individually-wired subset cannot quietly stop
    running — the reasoning :func:`usvote.census.conform.assert_conforms_to_spine`
    already applies. ``TestTheSeam`` in ``tests/unit/test_census_reconcile.py`` pins it
    for *this* seam, which matters because a guard call **was** silently droppable until
    that test existed: the suite stayed green with one removed.

    It reads only the injected spine, so :func:`usvote.warehouse.run_warehouse` can call
    it with no census corpus present — which is the call site that matters (D063).

    **What "before the write" does and does not mean here, because the two call sites
    differ.** From :func:`usvote.census.pipeline.run_census_pipeline` it runs before
    that pipeline's own transaction, so a breach leaves ``dwh.census_population``
    unwritten. From ``run_warehouse`` it runs **after** every source pipeline has
    committed its own transaction (the per-source atomicity of #84a) and **before**
    ``rebuild_views``, so a breach there leaves the loaded facts in place and no join or
    hybrid views — the same recovery shape a census failure already has. Saying it
    "leaves nothing written" would be true of the first and false of the second.
    """
    frame = build_seat_reconciliation(ec_participation)
    _assert_every_allotment_is_explained(frame)
    _assert_no_stale_exception(frame)
