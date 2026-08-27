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

    Two checks over the set of election years ``observed_years`` carries, plus a
    non-election-year screen. **Every problem found is reported in one error**, rather
    than raising on the first: the message is this guard's entire product, and
    short-circuiting hides the worst case behind the mildest one. A file with a
    typo'd ``2022`` row *and* 2024 truncated would otherwise report only the stray
    year — because a raw maximum of 2022 makes the span look complete at 2020 — and
    never mention that 2024, the year whose popular vote actually goes null, is gone.
    Strays are therefore split out **before** the bounds are derived.

    1. **Contiguity** — the observed *election* years must be exactly the election
       years in the closed range ``[min(election), max(election)]``. Both bounds are
       taken from the years that survived the stray screen, **not** from the raw input:
       that is what stops a single typo'd year from redefining the span (see above).
       The lower bound is in particular never
       :data:`~usvote.pv.source.MIT_PV_YEAR_MIN` — the floor belongs to
       :func:`usvote.pv.source.assert_mit_year_floor`, which permits a build starting
       later (see this module's docstring). A year that is not an election year at all
       is **not** reported by this comparison: the screen catches it first, and
       ``missing`` is a one-directional difference whose other side is empty by
       construction.
    2. **High-water** — ``max(observed) == expected_max``, raising in **both**
       directions. Below is the truncation this guard exists for. Above means MIT
       published a newer cycle while the constant stayed put, which makes every guard
       keyed on it silently one election too weak; the deliberate bump is the fix, and
       forcing it is the point. Unlike the floor there is no benign reading of the
       ``>`` side — a scoped build only ever *lowers* the observed maximum.

    A year that is **not an integer** — a blank cell types the column ``float64`` with
    NaN, and the read stage returns the CSV verbatim — raises ``error_cls`` too, rather
    than letting a bare ``ValueError`` escape from the conversion. This guard runs
    before ``transform_mit``, so it now meets such a row first.

    An **empty** ``observed_years`` raises. That is the opposite of
    :func:`~usvote.pv.source.assert_mit_year_floor`'s treatment, and deliberately so:
    a floor question is vacuous on an empty set, while "every year disappeared" is the
    maximal case of precisely the failure this guard is about, and passing it would
    make the guard vacuous under its own worst input.

    ``expected_max`` is injectable so both high-water branches are testable offline
    without moving the shipped constant; no caller under ``src/`` passes it.
    """
    try:
        years = sorted({int(y) for y in observed_years})
    except (TypeError, ValueError) as exc:
        # A blank ``year`` cell makes pandas type the column float64 with NaN, and the
        # read stage returns the CSV verbatim (no dtype coercion), so this guard is the
        # first thing to touch it — running before ``transform_mit``'s coercion, which
        # used to be where such a row surfaced. Keep the failure inside the typed
        # contract rather than letting a bare ValueError escape from a set
        # comprehension.
        raise error_cls(
            f"{caller}: MIT's year column carries a value that is not an integer "
            f"({exc}). A blank or malformed year cell does this; the CSV is malformed."
        ) from exc

    if not years:
        raise error_cls(
            f"{caller}: no MIT election years at all. Every year the file should "
            "cover is missing — check the CSV is the full 1976-2024-president.csv "
            "and not an empty or header-only file."
        )

    # Split strays out BEFORE deriving the bounds. Taking ``high`` from the raw maximum
    # lets a single typo'd year both mislabel itself and silence the high-water check: a
    # file with a stray 2022 and 2024 truncated would report only "non-election year
    # [2022]" and never mention that 2024 — the year whose popular vote actually goes
    # null — is gone, because ``election_years(latest=2022)`` stops at 2020 and the
    # span then looks complete. The message is this guard's entire product, so it
    # reports every problem it found rather than the first.
    calendar = set(election_years(latest=max(years)))
    stray = sorted(set(years) - calendar)
    election = sorted(set(years) & calendar)

    if not election:
        raise error_cls(
            f"{caller}: no MIT election years at all — the file carries "
            f"{stray}, none of which is an election year. Check the CSV is the full "
            "1976-2024-president.csv and that its year column is intact."
        )

    low, high = election[0], election[-1]
    problems: list[str] = []

    if stray:
        problems.append(
            f"non-election year(s) {stray}, which no US presidential election falls on"
        )

    expected_span = {y for y in election_years(latest=high) if y >= low}
    missing = sorted(expected_span - set(election))
    if missing:
        problems.append(
            f"not a contiguous run of elections from {low} to {high} — missing "
            f"election year(s) {missing}. A hole means the CSV is truncated or "
            "malformed, and nothing downstream would notice: MIT's roster derives its "
            "in-scope years from the rows MIT actually loaded"
        )

    if high < expected_max:
        lost = sorted(y for y in election_years(latest=expected_max) if y > high)
        problems.append(
            f"the newest covered election is {high}, but the file is known to reach "
            f"MIT_PV_YEAR_MAX={expected_max} — the popular vote for {lost} would go "
            "silently null, since the join is EC-left so those years still ship, with "
            "no popular vote and no failure. Either the CSV is truncated, or MIT "
            "withdrew a year, in which case update the constant in usvote/pv/source.py "
            "deliberately"
        )
    elif high > expected_max:
        problems.append(
            f"MIT now covers {high}, later than MIT_PV_YEAR_MAX={expected_max}. The "
            "constant is stale, so every guard keyed on it is one election too weak — "
            f"including this one, which would no longer notice {high} disappearing. "
            "Bump MIT_PV_YEAR_MAX in usvote/pv/source.py (and re-read "
            "LATEST_ELECTION_YEAR in usvote/years.py, which the same cycle bump "
            "touches)"
        )

    if problems:
        detail = "; ".join(problems)
        raise error_cls(f"{caller}: MIT's covered years are wrong — {detail}.")
