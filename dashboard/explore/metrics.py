"""The dashboard's own summaries over served rows (#437, D097): the one module that
computes them, so the rule they follow is enforced in one place.

The rule (D097, owner-approved 2026-11-05): inputs are served fields of one grain,
from the render's pinned view; only count, sum and mean over rows, never a ratio of
fields and never a recomputed served figure; a mean excludes nulls and shows its N; a
sum with any null reads no figure; a null flag is never counted as false; and wherever
a served figure exists, the metric reconciles to it.

Numbers only: the wording is :mod:`explore.labels`' (``METRIC_LABELS``,
``metric_mean``). Pure and shared: it reads no API and imports only ``labels``, whose
:func:`explore.labels.finite` and :func:`explore.labels.is_blank` are the one rule of
what is a figure and what is null, the same the margin cells use.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sized
from dataclasses import dataclass
from typing import NamedTuple

from explore import labels


class Source(NamedTuple):
    """A metric's input: a field of a public ``/v1`` response model, by name."""

    model: str
    field: str


class Metric(NamedTuple):
    """One metric: its kind (``count`` or ``mean``) and the served field it reads."""

    kind: str
    source: Source


#: Every metric, keyed by metric key, never renamed or reused. The page reads the field
#: each mean averages from here, so this table drives the code. The count's source is
#: the grain key of the rows it counts: the ``/v1/elections`` rows T1 shows.
METRICS: dict[str, Metric] = {
    "elections_shown": Metric("count", Source("YearListItem", "year")),
    "ec_margin_mean": Metric("mean", Source("ElectionSummary", "ec_margin")),
    "pv_margin_mean": Metric("mean", Source("ElectionSummary", "pv_margin")),
}


@dataclass(frozen=True)
class Mean:
    """A mean over election-grain values, its N and the years that entered it.

    Three states, and no other can be built: a number (``value`` finite, ``n`` ≥ 1,
    ``first`` ≤ ``last``, both years); no contributing value (``value`` ``None``,
    ``n`` 0, no years); and unrecognized (a value no figure can show was among the
    inputs, or the mean is no finite number: no value, no N, no years).
    """

    value: float | None
    n: int
    first: int | None
    last: int | None
    unrecognized: bool = False

    def __post_init__(self) -> None:
        empty = self.n == 0 and self.first is None and self.last is None
        if self.unrecognized or self.value is None:
            ok = self.value is None and empty
        else:
            ok = (
                isinstance(self.value, float)
                and math.isfinite(self.value)
                and type(self.n) is int
                and self.n >= 1
                and type(self.first) is int
                and type(self.last) is int
                and self.first <= self.last
            )
        if not ok:
            raise ValueError(f"not a mean: {self!r}")


#: The mean of inputs that hold a value no figure can show.
UNRECOGNIZED = Mean(None, 0, None, None, unrecognized=True)
#: The mean of no contributing value.
NO_AVERAGE = Mean(None, 0, None, None)


def count(rows: Sized) -> int:
    """How many rows: a count over rows, the only figure a row set gives by itself."""
    return len(rows)


def mean(pairs: Iterable[tuple[int, object]]) -> Mean:
    """The mean of the values in ``(year, value)`` pairs, already joined on the year.

    A null or a blank (:func:`explore.labels.is_blank`) is left out, never read as
    zero. Any other value :func:`explore.labels.finite` refuses (a bool, text, a
    non-finite number, an integer no float can hold) makes the whole mean
    :data:`UNRECOGNIZED`: leaving it out would drop a year and misstate N. So does a
    mean that is not finite (a sum that overflows). Each pair is one election; the
    caller passes each year once.
    """
    total = 0.0
    years: list[int] = []
    for year, value in pairs:
        if labels.is_blank(value):
            continue
        number = labels.finite(value)
        if number is None:
            return UNRECOGNIZED
        total += number
        years.append(year)
    if not years:
        return NO_AVERAGE
    value = total / len(years)
    if not math.isfinite(value):
        return UNRECOGNIZED
    return Mean(value, len(years), min(years), max(years))
