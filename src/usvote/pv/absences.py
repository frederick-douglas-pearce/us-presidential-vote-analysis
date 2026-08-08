"""The in-repo pre-1976 popular-vote absence catalog, and its spine cross-check (#140).

**Why this exists.** ``dwh.pv_state_status``'s pre-1976 absence classifications have so
far had exactly one origin: parsing UCSB's markup (``usvote/ucsb/transform.py``). UCSB
grants no reuse rights and this repo is public (D022), and the API snapshot is
redistributable-only *at the source* (D030) — so a public surface that reports a
``pv_status`` for every ``(year, state)`` back to 1824 cannot be built on UCSB-derived
rows. This module is the alternative: the 28 pre-1976 absences, enumerated in code, each
carrying a **public-domain citation**, so the classification is ours to ship.

**On provenance, stated precisely.** The firewall this module establishes is over
*machine* provenance: no UCSB byte, parse, or artifact reaches these classifications,
and :mod:`tests.unit.test_layering` enforces that structurally. It is **not** a claim
that the curator worked in ignorance of UCSB. Each row is independently attested and
independently cited; the fact that the resulting set coincides exactly with UCSB's is
**corroboration**, and :class:`tests.unit.test_ucsb_transform.TestRealCorpus` checks
that coincidence deliberately — with the dependency inverted, so UCSB is the *control*
that validates this catalog rather than its source (the posture D016 already takes for
the PV facts).

**Why a data module lives in ``usvote/pv/``.** The package has so far meant *contracts*
— :mod:`usvote.pv.schema` (shapes), :mod:`usvote.pv.status` (the roster shape + guards),
:mod:`usvote.pv.validate` (frame invariants), :mod:`usvote.pv.load` (write seams). This
module carries **data and a derivation**, which is new here. It belongs anyway, for the
same reason the roster contract does: the classification is source-neutral. It is a fact
about the *election*, not about UCSB or MIT, and both a UCSB run and a future
snapshot-time build must be able to reach it without either importing the other. Putting
it under ``usvote/ucsb/`` would make the control test circular; putting it at the top
level would make it EC-domain, which it is not.

**The dependency runs one way.** ``absences -> status``, never back:
:mod:`usvote.pv.status` imports nothing from ``usvote`` and must not start. Nor does
this module import :mod:`usvote.spine` — the EC participation frame arrives across the
same DI seam every PV roster derivation uses, so ``usvote/pv/`` still names no EC fact
table (D015, enforced in :mod:`tests.unit.test_layering`).

**Scope is explicit, and that is load-bearing.** :data:`CURATED_YEARS` is the set of
years a curator has actually reviewed. Without it, "the catalog is silent about 1868"
and "1868 was reviewed and has no further absences" are indistinguishable — the D024 §3
exceptions-table failure mode, one level up. So :func:`build_curated_roster` **raises**
for any year outside it rather than quietly returning an all-``popular_vote`` roster.
1868 and 1872 sit in the catalog as *catalogued but never consumed*, exactly as
``UCSB_NONPARTICIPATING_STATES`` retains its 1868 trio: the research is recorded so it
is not redone, and :data:`CURATED_YEARS` is what stops it being used.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

import pandas as pd

from usvote.pv.status import (
    PV_ABSENCE_STATUSES,
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    PVRosterError,
    build_roster,
)
from usvote.years import ec_ingest_years

#: The years a curator has reviewed for popular-vote absences. Derived from
#: :func:`usvote.years.ec_ingest_years` rather than re-listing the span, so the
#: 1868/1872 exclusion has one definition (``UNSUPPORTED_EC_YEARS``) and not two.
#:
#: This is the catalog's **scope marker**, not a convenience: outside it, the catalog's
#: silence carries no information, so :func:`build_curated_roster` refuses to derive.
CURATED_YEARS: frozenset[int] = frozenset(ec_ingest_years())

#: Guards against a silent scope change. If a year is ever added to (or removed from)
#: the EC ingest span, :data:`CURATED_YEARS` grows or shrinks with it — and the new year
#: would be *derivable* while nobody has reviewed it for absences. Pinned here, and
#: again as a test, so that change fails loudly and lands on a curator's desk.
CURATED_YEAR_COUNT = 49


@dataclass(frozen=True)
class PVAbsence:
    """One catalogued ``(year, state)`` popular-vote absence and why we believe it.

    ``pv_status`` is one of :data:`usvote.pv.status.PV_ABSENCE_STATUSES` —
    ``popular_vote`` is the *residual* and is never catalogued.

    ``citation`` is a public-domain source, and it is the entire point of the dataclass:
    a bare ``dict[key, status]`` would carry the classification without carrying the
    grounds for it, which is what makes a catalog rot silently. A test asserts every
    entry has a non-empty one.
    """

    pv_status: str
    citation: str


# --- the citations ----------------------------------------------------------
#
# Verified 2026-08-07 against the sources named. All are public domain: a U.S. Supreme
# Court opinion, state constitutions, and acts of Congress.

#: The constitutional authority every ``legislature_chosen`` row rests on. Cited on each
#: such row alongside the source attesting that the state actually used it in that year
#: — the clause permits legislative appointment, it does not evidence it.
_ELECTORS_CLAUSE = (
    "U.S. Const. art. II, § 1, cl. 2 (each state appoints electors "
    '"in such Manner as the Legislature thereof may direct")'
)

#: McPherson v. Blacker's historical survey is the single best public-domain witness for
#: this era: a Supreme Court opinion that enumerates, by state and year, which
#: legislatures appointed electors directly. It attests the 1824 six by name, and South
#: Carolina's run through 1860.
_MCPHERSON_1824 = (
    "McPherson v. Blacker, 146 U.S. 1, 27 (1892): \"In 1824 the electors were chosen "
    "by popular vote, by districts, and by general ticket, in all the states excepting "
    "Delaware, Georgia, Louisiana, New York, South Carolina, and Vermont, where they "
    'were still chosen by the legislature."'
)
_MCPHERSON_SC = (
    "McPherson v. Blacker, 146 U.S. 1, 28 (1892): \"After 1832 electors were chosen by "
    "general ticket in all the states excepting South Carolina, where the legislature "
    'chose them up to and including 1860."'
)

_CITE_1824 = f"{_MCPHERSON_1824} — {_ELECTORS_CLAUSE}."

#: South Carolina 1824-1860. McPherson attests both ends directly — the 1824 six, and
#: "up to and including 1860" — which together cover every South Carolina row in the
#: catalog. Under the S.C. Constitution of 1790 the General Assembly elected the holders
#: of all major state offices, presidential electors among them, and South Carolina was
#: the last state to adopt a popular presidential vote, first holding one in 1868.
_CITE_SC = (
    f"{_MCPHERSON_1824} {_MCPHERSON_SC} Under the S.C. Constitution of 1790 the "
    "General Assembly elected presidential electors along with the state's other major "
    "officers; South Carolina was the last state to adopt a popular presidential vote, "
    f"first holding one in 1868. — {_ELECTORS_CLAUSE}."
)

#: Delaware 1828. The one row McPherson brackets rather than states: it attests
#: legislative appointment in 1824, and general-ticket popular choice only "after 1832".
#: Delaware and South Carolina were the two legislative-appointment states in 1828, and
#: Delaware first chose electors by popular vote in 1832 — the switch that leaves South
#: Carolina alone in McPherson's post-1832 sentence. (The Delaware Constitution of 1792
#: is **not** the instrument: it contains no presidential-elector provision at all, so
#: the appointment was statutory. Checked 2026-08-07 against its text.)
_CITE_DE_1828 = (
    f"{_MCPHERSON_1824} {_MCPHERSON_SC} Delaware and South Carolina were the only two "
    "states whose legislatures appointed electors in 1828; Delaware first chose "
    "electors by popular vote in 1832, which is why McPherson's post-1832 sentence "
    f"leaves South Carolina alone. — {_ELECTORS_CLAUSE}."
)

#: Colorado 1876. Admitted three months before the election, with no time to organize a
#: presidential vote; its own constitution's schedule provided for the one-time
#: legislative appointment. The last time any state chose electors without a
#: popular vote.
_CITE_CO_1876 = (
    "Colo. Const. of 1876, Schedule § 19 (a one-time provision directing the General "
    "Assembly to choose the state's 1876 presidential electors). Colorado was admitted "
    "1 August 1876 by Proclamation No. 230, under the Colorado Enabling Act, ch. 139, "
    "18 Stat. 474 (1875) — three months before the election, leaving no time to "
    "organize one. The last state ever to choose electors without a popular vote. — "
    f"{_ELECTORS_CLAUSE}."
)

#: 1864, the nine seceded states from which no returns were received at all.
_CITE_1864_NO_RETURNS = (
    "In rebellion; the state appointed no electors and no returns were received. "
    "Joint Resolution (H.R. 126, 38th Cong.), adopted before the 8 February 1865 "
    "count, declared the states in insurrection not entitled to representation in the "
    "Electoral College. Independently corroborated by the EC spine itself, which "
    "records zero electoral votes for the state in 1864."
)

#: 1864, Louisiana and Tennessee. Unlike the other nine these *did* submit returns, via
#: Unionist reconstruction governments — and Congress refused to count them. Same
#: classification, materially different history, so it gets its own citation rather than
#: being flattened into the other nine. The outcome is what the roster records: no
#: popular vote of this state took part in this election.
_CITE_1864_RETURNS_REJECTED = (
    "In rebellion; returns submitted by a Unionist reconstruction government were "
    "rejected. The Joint Resolution (H.R. 126, 38th Cong.) adopted before the 8 "
    "February 1865 count named this state as in insurrection and not entitled to "
    "representation in the Electoral College, and its votes were not counted. "
    "Independently corroborated by the EC spine itself, which records zero "
    "electoral votes for the state in 1864."
)

#: 1868, catalogued but **never consumed** — 1868 is in ``UNSUPPORTED_EC_YEARS`` and so
#: outside :data:`CURATED_YEARS`. Recorded so the research is not redone if the
#: Reconstruction elections are ever brought into scope. It needs its own citation
#: precisely because there is no in-repo constant behind it today: UCSB's 1868 Florida
#: row is parser-derived from UCSB markup, which is what this module exists to avoid.
_CITE_FL_1868 = (
    "Readmitted by the Omnibus Act, 15 Stat. 73 (25 June 1868), too late to organize a "
    "presidential election; the Legislature appointed the state's three electors. The "
    "only time Florida's popular vote did not decide a presidential election, and — "
    "with Colorado in 1876 — one of only two such instances after the Civil War. — "
    f"{_ELECTORS_CLAUSE}. NOT CURATED: 1868 is in UNSUPPORTED_EC_YEARS."
)
_CITE_1868_UNREADMITTED = (
    "Not readmitted to representation in time for the 1868 election, so the state "
    "appointed no electors and cast no votes. The Omnibus Act, 15 Stat. 73 (25 June "
    "1868), readmitted six other states; Virginia, Mississippi and Texas were not "
    "readmitted until 1870. NOT CURATED: 1868 is in UNSUPPORTED_EC_YEARS."
)


def _legislature(citation: str) -> PVAbsence:
    return PVAbsence(pv_status=PV_STATUS_LEGISLATURE_CHOSEN, citation=citation)


def _absent(citation: str) -> PVAbsence:
    return PVAbsence(pv_status=PV_STATUS_NOT_PARTICIPATING, citation=citation)


#: The catalog: every ``(year, state)`` in the EC spine at which **no popular vote for
#: president was held**, keyed on the canonical ``dwh.state`` PK (the full state name).
#:
#: 28 entries fall inside :data:`CURATED_YEARS` — 17 ``legislature_chosen`` and 11
#: ``not_participating``. A further 4 sit in 1868 and are catalogued but never consumed.
#:
#: **Only absences are enumerated.** Every other participating state is the residual,
#: and :func:`usvote.pv.status.build_roster` marks it ``popular_vote`` by not finding
#: it here.
PV_ABSENCE_CATALOG: dict[tuple[int, str], PVAbsence] = {
    # 1824 — six legislatures still appointed electors directly.
    (1824, "Delaware"): _legislature(_CITE_1824),
    (1824, "Georgia"): _legislature(_CITE_1824),
    (1824, "Louisiana"): _legislature(_CITE_1824),
    (1824, "New York"): _legislature(_CITE_1824),
    (1824, "South Carolina"): _legislature(_CITE_SC),
    (1824, "Vermont"): _legislature(_CITE_1824),
    # 1828 — only Delaware and South Carolina remain. (New York had moved to districts.)
    (1828, "Delaware"): _legislature(_CITE_DE_1828),
    (1828, "South Carolina"): _legislature(_CITE_SC),
    # 1832-1860 — South Carolina alone, every election through the last before the war.
    (1832, "South Carolina"): _legislature(_CITE_SC),
    (1836, "South Carolina"): _legislature(_CITE_SC),
    (1840, "South Carolina"): _legislature(_CITE_SC),
    (1844, "South Carolina"): _legislature(_CITE_SC),
    (1848, "South Carolina"): _legislature(_CITE_SC),
    (1852, "South Carolina"): _legislature(_CITE_SC),
    (1856, "South Carolina"): _legislature(_CITE_SC),
    (1860, "South Carolina"): _legislature(_CITE_SC),
    # 1864 — the eleven Confederate states. South Carolina appears here too, under a
    # different cause than its 1824-1860 rows: the catalog keys on (year, state) because
    # the *why* is a property of the election, not of the state.
    (1864, "Alabama"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "Arkansas"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "Florida"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "Georgia"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "Louisiana"): _absent(_CITE_1864_RETURNS_REJECTED),
    (1864, "Mississippi"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "North Carolina"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "South Carolina"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "Tennessee"): _absent(_CITE_1864_RETURNS_REJECTED),
    (1864, "Texas"): _absent(_CITE_1864_NO_RETURNS),
    (1864, "Virginia"): _absent(_CITE_1864_NO_RETURNS),
    # 1876 — Colorado, admitted 1 August, too late to hold an election.
    (1876, "Colorado"): _legislature(_CITE_CO_1876),
    # --- beyond CURATED_YEARS: catalogued, never consumed -----------------------
    # 1868 is in UNSUPPORTED_EC_YEARS, so build_curated_roster raises for it. These rows
    # record the research; CURATED_YEARS is what keeps them out of any derivation.
    (1868, "Florida"): _legislature(_CITE_FL_1868),
    (1868, "Mississippi"): _absent(_CITE_1868_UNREADMITTED),
    (1868, "Texas"): _absent(_CITE_1868_UNREADMITTED),
    (1868, "Virginia"): _absent(_CITE_1868_UNREADMITTED),
}


class PVAbsenceCatalogError(PVRosterError):
    """Raised when the catalog and the EC spine disagree.

    A subclass of :class:`usvote.pv.status.PVRosterError` because it is a roster failure
    of the same family, and separately typed because the fix is different: a roster
    mismatch means the pipeline lost rows, while this means the *catalog* is wrong — a
    typo'd state name, a year mis-keyed, or a genuine historical error — and is fixed by
    editing this module.
    """


#: The columns :func:`assert_catalog_matches_spine` requires. Wider than
#: ``build_roster``'s by exactly ``total_electoral_votes``: the cross-check *reads* the
#: EC fact to falsify the catalog against it. It never loads an EV, so D024 §5 holds —
#: the EC fact stays the single source of electoral-vote truth, and this is a
#: consumer of it.
_CROSS_CHECK_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "is_total",
    "total_electoral_votes",
)


def assert_catalog_matches_spine(
    ec_participation: pd.DataFrame,
    *,
    years: Collection[int] | None = None,
    error_cls: type[Exception] = PVAbsenceCatalogError,
) -> None:
    """Falsify the catalog against the EC spine, in **both** directions.

    Three checks, over the catalog rows in scope:

    1. **No phantom keys.** Every in-scope catalog key exists in the spine. A typo'd
       state name would otherwise vanish silently — the entry would simply never match,
       and the state it was meant to describe would fall through to the ``popular_vote``
       residual looking perfectly ordinary.
    2. **Every ``not_participating`` key has zero electoral votes, and no
       ``legislature_chosen`` key does.** A legislature-appointed state *did* cast
       electoral votes; it just held no popular vote. A state that took no part cast
       none. Mixing the two is the most likely way to mis-classify.
    3. **No zero-EV spine state is left ``popular_vote``** — the reverse direction, and
       the one with teeth. Because ``popular_vote`` is the residual, a state that
       becomes zero-EV in the spine (a re-parse, a newly covered year, a correction)
       silently *becomes* ``popular_vote`` with nothing failing. Check 1 cannot see it;
       only this can. Run over every year in scope, not only the years the catalog
       mentions.

    Together these are the in-repo analogue of ``usvote.ucsb.transform``'s
    ``assert_absence_matches_zero_ev``, which has both halves for the same reason.

    ``years`` defaults to :data:`CURATED_YEARS`. Passing a narrower set scopes the check
    to a partial run; passing a year outside :data:`CURATED_YEARS` is allowed here (the
    checks are still meaningful) but :func:`build_curated_roster` will refuse to derive.
    """
    absent = [c for c in _CROSS_CHECK_COLUMNS if c not in ec_participation.columns]
    if absent:
        raise error_cls(
            f"assert_catalog_matches_spine needs the EC participation columns "
            f"{list(_CROSS_CHECK_COLUMNS)}; missing {absent}. Pass "
            "usvote.spine.read_ec_participation's frame."
        )
    in_scope = frozenset(CURATED_YEARS if years is None else years)
    rows = ec_participation[
        (~ec_participation["is_total"].astype(bool))
        & ec_participation["state"].notna()
        & ec_participation["year"].isin(in_scope)
    ]
    spine_ev = {
        (int(year), state): ev
        for year, state, ev in zip(
            rows["year"], rows["state"], rows["total_electoral_votes"], strict=True
        )
    }
    catalog = {
        key: entry for key, entry in PV_ABSENCE_CATALOG.items() if key[0] in in_scope
    }

    phantoms = sorted(key for key in catalog if key not in spine_ev)
    if phantoms:
        raise error_cls(
            f"{len(phantoms)} catalog key(s) are absent from the EC spine: {phantoms}. "
            "Most likely a typo'd or non-canonical state name — the key must be the "
            "canonical dwh.state PK (the full state name). A phantom key never "
            "matches, so the state it describes would quietly fall through to the "
            "'popular_vote' residual."
        )

    miscast = sorted(
        (key, entry.pv_status, int(spine_ev[key]))
        for key, entry in catalog.items()
        if (entry.pv_status == PV_STATUS_NOT_PARTICIPATING) != (spine_ev[key] == 0)
    )
    if miscast:
        raise error_cls(
            f"{len(miscast)} catalog entr(ies) contradict the EC spine's electoral "
            f"votes: {miscast}. A '{PV_STATUS_NOT_PARTICIPATING}' state took no part "
            f"and must have 0 electoral votes; a '{PV_STATUS_LEGISLATURE_CHOSEN}' "
            "state cast electoral votes and merely held no popular vote."
        )

    uncatalogued = sorted(
        key for key, ev in spine_ev.items() if ev == 0 and key not in catalog
    )
    if uncatalogued:
        raise error_cls(
            f"{len(uncatalogued)} spine state(s) cast zero electoral votes but are not "
            f"in the absence catalog: {uncatalogued}. Because "
            f"'{PV_STATUS_POPULAR_VOTE}' is the residual, these would be silently "
            "classified as having held a popular vote. Either catalog them with a "
            "citation, or — if the zero is a parse artifact — fix usvote/parse.py, "
            "which reads the Archives' '-' as 0."
        )


def build_curated_roster(
    ec_participation: pd.DataFrame,
    *,
    source: str,
    years: Collection[int],
    error_cls: type[Exception] = PVAbsenceCatalogError,
) -> pd.DataFrame:
    """Return the roster for ``years`` with :data:`PV_ABSENCE_CATALOG` layered on.

    :func:`usvote.pv.status.build_roster` bound to the catalog: membership from the EC
    spine, absences from the catalog, ``popular_vote`` as the residual. The returned
    frame satisfies ``ROSTER_COLUMNS``, with ``note`` null on every row — an absence's
    cause lives in its citation, in code, and never in the warehouse (D024 §6).

    :func:`assert_catalog_matches_spine` runs **first, always**. A cross-check the
    caller must remember to invoke is a cross-check that gets skipped; and since the
    whole value of this module is that its classifications are trustworthy without UCSB,
    deriving without falsifying would be the wrong default.

    ``source`` is a required keyword with no default. There is no ``SOURCE_CURATED``
    literal here: nothing in #140 writes to ``dwh.pv_state_status``, and naming a source
    value would pre-commit a decision that belongs to whoever loads it.

    Raises ``error_cls`` for any year outside :data:`CURATED_YEARS`. That refusal is the
    point — see the module docstring.
    """
    requested = frozenset(int(y) for y in years)
    uncurated = sorted(requested - CURATED_YEARS)
    if uncurated:
        raise error_cls(
            f"build_curated_roster({source!r}) was asked for year(s) {uncurated}, "
            f"which are outside CURATED_YEARS. The catalog's silence about an "
            "unreviewed year carries no information — deriving anyway would report "
            f"every state as '{PV_STATUS_POPULAR_VOTE}' on no evidence. Curate the "
            "year (add its absences with citations) or narrow `years`."
        )
    assert_catalog_matches_spine(
        ec_participation, years=requested, error_cls=error_cls
    )
    absences = {
        key: entry.pv_status
        for key, entry in PV_ABSENCE_CATALOG.items()
        if key[0] in requested
    }
    return build_roster(
        ec_participation,
        source=source,
        years=requested,
        absences=absences,
        error_cls=error_cls,
    )


__all__ = [
    "CURATED_YEARS",
    "CURATED_YEAR_COUNT",
    "PV_ABSENCE_CATALOG",
    "PV_ABSENCE_STATUSES",
    "PVAbsence",
    "PVAbsenceCatalogError",
    "assert_catalog_matches_spine",
    "build_curated_roster",
]
