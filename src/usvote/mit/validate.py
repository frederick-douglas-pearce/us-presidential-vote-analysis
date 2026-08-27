"""MIT year-coverage invariants — the guard for a year that silently disappears (#177).

MIT's own shelf for invariants over the **set of election years the file covers**,
kept apart from :mod:`usvote.mit.transform` (which validates the *shape and
arithmetic* of the rows) for the reason :mod:`usvote.pv.validate` is kept apart from
:mod:`usvote.pv.schema`: a frame can satisfy every column contract and every totals
reconciliation perfectly while covering the wrong set of elections.

**The gap this closes.** MIT's loaded year set had no owner. The D024 roster assert
cannot see a missing year, because it derives its in-scope set from the rows MIT
actually loaded (:mod:`usvote.mit.pipeline`) — a frame compared against itself. The
#167/D051 overlap gate sees an *interior* hole, but only when UCSB is present, which a
public EC + MIT clone never is (D022); and it deliberately excludes a one-sided year
**at or beyond the spine frontier**, which is exactly where a dropped newest year
lands. So a MIT CSV that stopped at 2020 built green and 2024's popular vote went
silently null — announced by ``meta.pv_year_max`` and ``has_popular_vote``, never
refused.

**Two failures, two mechanisms, and the second is why this module is not one check.**

- An **interior hole** (1976…1992, 2000…2024 — 1996 simply missing) is a contiguity
  question, answerable from the observed set alone.
- A **dropped newest year** is not. A contiguity run over ``[min(observed),
  max(observed)]`` is *trivially satisfied* when the year that vanished is the one
  that defined the upper bound — contiguity provably cannot reach it. Deciding it
  needs something that remembers MIT used to reach 2024, which is
  :data:`~usvote.pv.source.MIT_PV_YEAR_MAX`.

**Why this is not in** :mod:`usvote.pv`. "Did MIT's own year set change?" is a
**single-source** question. Answering it inside the cross-source overlap gate would
drag back the data-derived ceiling #167 removed precisely because it was circular —
letting the data define the boundary meant to detect the data being wrong. The
dependency runs ``mit -> pv.source`` and ``mit -> years``, both the allowed direction
(D006/D015).

**The floor is deliberately not checked here** (#177's "leave the bottom alone").
:func:`usvote.pv.source.assert_mit_year_floor` owns it and deliberately **passes**
``min(observed) > MIT_PV_YEAR_MIN`` as an ordinary scoped build. Collapsing both
checks into one span equality — ``observed == [MIT_PV_YEAR_MIN, MIT_PV_YEAR_MAX]`` —
looks strictly stronger and is instead *incoherent*: it would demand ``min == 1976``
while the floor guard permits ``min > 1976``, leaving two owners of the same bound
with contradictory semantics. The contiguity check's lower bound is therefore
``min(observed)``, **never** :data:`~usvote.pv.source.MIT_PV_YEAR_MIN`. See D052.
"""

from __future__ import annotations

from collections.abc import Collection

from usvote.mit.transform import MITTransformError
from usvote.pv.source import MIT_PV_YEAR_MAX
from usvote.years import election_years


class MITCoverageError(MITTransformError):
    """Raised when MIT's covered election years are holed, truncated, or overlong.

    MIT's typed wrapper for the year-coverage invariants, mirroring
    :class:`usvote.mit.pipeline.MITRosterError` so a coverage failure is separable by
    type and not only by message.
    """


def assert_mit_year_coverage(
    observed_years: Collection[int],
    *,
    expected_max: int = MIT_PV_YEAR_MAX,
    error_cls: type[Exception] = MITCoverageError,
    caller: str = "assert_mit_year_coverage",
) -> None:
    """Assert MIT's covered election years are contiguous and reach ``expected_max``.

    Two checks, applied in order, over the set of election years ``observed_years``
    carries. **Contiguity is checked first** because its message names the specific
    missing years, which is the more actionable diagnostic on a file that is both
    holed and truncated.

    1. **Contiguity** — the observed set must be exactly the election years in the
       closed range ``[min(observed), max(observed)]``. The lower bound is the
       *observed* minimum, never :data:`~usvote.pv.source.MIT_PV_YEAR_MIN`: the floor
       belongs to :func:`usvote.pv.source.assert_mit_year_floor`, which permits a
       build starting later (see this module's docstring). A year that is not an
       election year at all is reported by the same comparison, from the other side.
    2. **High-water** — ``max(observed) == expected_max``, raising in **both**
       directions. Below is the truncation this guard exists for. Above means MIT
       published a newer cycle while the constant stayed put, which makes every guard
       keyed on it silently one election too weak; the deliberate bump is the fix, and
       forcing it is the point. Unlike the floor there is no benign reading of the
       ``>`` side — a scoped build only ever *lowers* the observed maximum.

    An **empty** ``observed_years`` raises. That is the opposite of
    :func:`~usvote.pv.source.assert_mit_year_floor`'s treatment, and deliberately so:
    a floor question is vacuous on an empty set, while "every year disappeared" is the
    maximal case of precisely the failure this guard is about, and passing it would
    make the guard vacuous under its own worst input.

    ``expected_max`` is injectable so both high-water branches are testable offline
    without moving the shipped constant; no caller under ``src/`` passes it.
    """
    years = sorted({int(y) for y in observed_years})
    if not years:
        raise error_cls(
            f"{caller}: no MIT election years at all. Every year the file should "
            "cover is missing — check the CSV is the full 1976-2024-president.csv "
            "and not an empty or header-only file."
        )

    observed = set(years)
    low, high = years[0], years[-1]

    expected_span = {y for y in election_years(latest=high) if y >= low}
    if observed != expected_span:
        detail = []
        missing = sorted(expected_span - observed)
        unexpected = sorted(observed - expected_span)
        if missing:
            detail.append(f"missing election year(s) {missing}")
        if unexpected:
            detail.append(f"non-election year(s) {unexpected}")
        raise error_cls(
            f"{caller}: MIT's covered years are not a contiguous run of elections "
            f"from {low} to {high} — {'; '.join(detail)}. A hole means the CSV is "
            "truncated or malformed, and nothing downstream would notice: MIT's "
            "roster derives its in-scope years from the rows MIT actually loaded."
        )

    if high < expected_max:
        lost = sorted(y for y in election_years(latest=expected_max) if y > high)
        raise error_cls(
            f"{caller}: MIT's newest covered election is {high}, but the file is "
            f"known to reach MIT_PV_YEAR_MAX={expected_max}. The popular vote for "
            f"{lost} would go silently null — the join is EC-left, so those years "
            "still ship, with no popular vote and no failure. Either the CSV is "
            "truncated, or MIT withdrew a year, in which case update the constant "
            "in usvote/pv/source.py deliberately."
        )
    if high > expected_max:
        raise error_cls(
            f"{caller}: MIT now covers {high}, later than "
            f"MIT_PV_YEAR_MAX={expected_max}. The constant is stale, so every guard "
            "keyed on it is one election too weak — including this one, which would "
            f"no longer notice {high} disappearing. Bump MIT_PV_YEAR_MAX in "
            "usvote/pv/source.py (and re-read LATEST_ELECTION_YEAR in "
            "usvote/years.py, which the same cycle bump touches)."
        )
