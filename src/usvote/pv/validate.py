"""Shared PV frame invariants both sources check — grain + totals (#82).

The third sibling of :mod:`usvote.pv.schema` and :mod:`usvote.pv.status`, and
source-neutral for the same reason: MIT and UCSB each assert *one row per*
``(year, state, candidate)`` and *candidate votes never exceed the state total*, and
sibling PV sources must not import each other (D015), so the only correct home for a
check both need is here. The dependency runs ``source -> pv``, never source-to-source.

**Why these live here and not in :mod:`usvote.pv.schema`.** ``schema.py`` owns the D018
*column contract* — which columns, in what order, with what dtypes — and
:func:`~usvote.pv.schema.assert_pv_shape` enforces exactly the constants defined beside
it. The two checks here are **invariants over the data values**: grain is a uniqueness
property of the natural key, and totals-not-exceeded is vote arithmetic. A frame can
satisfy the D018 shape perfectly and still violate both. Keeping them apart is what
stops ``schema.py`` from becoming "the shape contract *and* the business rules".

**Not equality, for totals.** Both sources legitimately drop rows before this check —
MIT scopes to the D007 EC-getters, UCSB drops the aggregate "OTHERS" columns — so the
retained candidates sum to *less* than the published state total. Only an **excess**
over the total signals a bug. Each source's own exact reconciliation against its
published totals runs earlier, on the complete pre-drop candidate set.

**Parameterization (#82).** ``error_cls`` keeps the failure typed to the calling stage
(the pattern :func:`~usvote.pv.schema.assert_pv_shape` established in #36), and
``source``/``stage`` keep the message naming the source and pipeline stage that
actually failed — so consolidating costs no diagnostic precision at the call site.
"""

from __future__ import annotations

import pandas as pd

#: The D018 natural key *within* a single source. ``source`` is excluded on purpose:
#: these validators run on one source's frame, where it is constant. The full
#: cross-source key (``source``, year, state, candidate) is the union's grain and is
#: checked in :mod:`usvote.pv.views`.
PV_GRAIN_COLUMNS: tuple[str, ...] = ("year", "state", "candidate")


class PVValidationError(RuntimeError):
    """A shared PV frame invariant (grain or totals) was violated.

    The default for both validators below. In practice every in-tree call site passes
    its own ``error_cls`` so the failure surfaces as that source's/stage's typed error;
    this default exists so the shared functions are usable standalone (and in tests)
    without inventing a source.
    """


def assert_pv_grain(
    df: pd.DataFrame,
    *,
    error_cls: type[Exception] = PVValidationError,
    source: str,
    stage: str = "transform",
) -> None:
    """Assert one row per ``(year, state, candidate)`` (``source`` is constant here).

    The shared implementation behind ``usvote.mit.transform.assert_unique_grain`` and
    ``usvote.ucsb.transform.assert_pv_grain``. Both sources re-run it after their
    reconcile stage rewrites candidate names (#38/#67) — the rewrite is exactly where a
    two-name-to-one-name collapse would silently create a duplicate — so ``stage``
    distinguishes which run failed, and ``error_cls`` types it to that stage's error.

    Note this is deliberately **not** the same check as
    :func:`usvote.transform.assert_unique_grain`, which asserts single-column
    uniqueness on the EC dimension frames and is unrelated despite the similar name.
    """
    dupes = df.loc[df.duplicated(list(PV_GRAIN_COLUMNS), keep=False)]
    if not dupes.empty:
        raise error_cls(
            f"{source} {stage} grain violated — duplicate (year, state, candidate): "
            f"{dupes[list(PV_GRAIN_COLUMNS)].values.tolist()}"
        )


def assert_totals_not_exceeded(
    df: pd.DataFrame,
    *,
    error_cls: type[Exception] = PVValidationError,
    source: str,
) -> None:
    """Assert ``sum(candidate_votes) <= state_total_votes`` per ``(year, state)``.

    The shared implementation behind both sources' ``assert_totals_not_exceeded``. See
    the module docstring for why this is an inequality and not an equality: retained
    candidates are a subset, so a shortfall is expected and only an excess is a bug.
    """
    grouped = df.groupby(["year", "state"], as_index=False).agg(
        csum=("candidate_votes", "sum"),
        total=("state_total_votes", "first"),
    )
    over = grouped.loc[grouped["csum"] > grouped["total"]]
    if not over.empty:
        raise error_cls(
            f"{source} candidate votes exceed the state total for "
            f"{len(over)} (year, state) cell(s): {over.values.tolist()}"
        )
