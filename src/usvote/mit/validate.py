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

**D052 owns the rationale** — why two checks rather than one, why the high-water
comparison is an equality raising in both directions, why the floor stays with
:func:`usvote.pv.source.assert_mit_year_floor` rather than being folded in here, and
the limit no mechanical check can close. It is stated there once; this module does not
restate it. The dependency runs ``mit -> pv.source`` and ``mit -> years``, both the
allowed direction (D006/D015).
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

    Raises ``error_cls`` when the election years ``observed_years`` carries are holed,
    do not reach ``expected_max``, or overshoot it; when a value is not an integer
    (a blank cell types the column ``float64`` with NaN, and the read stage returns the
    CSV verbatim); and when there are no election years at all. **Every problem found
    is reported in one error**, never the first one only — the message is this guard's
    entire product, and a stray year must not be able to hide a truncation behind it.

    ``expected_max`` is injectable so both high-water branches are testable offline
    without moving the shipped constant; no caller under ``src/`` passes it. See D052
    for why each check is shaped the way it is.
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

    # Split strays out BEFORE deriving the bounds, so a single typo'd year cannot
    # redefine the span it is measured against: taking ``high`` from the raw maximum
    # makes a stray 2022 print as "the newest covered election", over a contiguity
    # range of "from 1976 to 2022".
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
