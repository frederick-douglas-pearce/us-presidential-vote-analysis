"""The dashboard's own summaries over served rows (#437, D097): the one module that
computes them, so the rule they follow is enforced in one place.

The rule (D097, owner-approved 2026-11-05): inputs are served fields of one grain,
from the render's pinned view; only count, sum and mean over rows, never a ratio of
fields and never a recomputed served figure; a mean excludes nulls and shows its N; a
sum with any null reads no figure; a null flag is never counted as false; and wherever
a served figure exists, the metric reconciles to it. D112 (#569) amends it for the
pages #569 adds figures to; the counts of a served flag here are its first.

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
    """One metric: its kind (one of :data:`KINDS`), the served field it reads and, for
    a ``flag_count``, the flag value it counts (``None`` for every other kind)."""

    kind: str
    source: Source
    counted: bool | None = None


#: The metric kinds, a closed set, each computed by the function of the same name here
#: (``count``, ``mean``, ``flag_count``; #569, D112).
KINDS = ("count", "mean", "flag_count")


#: Every metric, keyed by metric key, never renamed or reused. The page reads the field
#: each mean averages from here, so this table drives the code. The count's source is
#: the grain key of the rows it counts: the ``/v1/elections`` rows T1 shows.
METRICS: dict[str, Metric] = {
    "elections_shown": Metric("count", Source("YearListItem", "year")),
    "ec_margin_mean": Metric("mean", Source("ElectionSummary", "ec_margin")),
    "pv_margin_mean": Metric("mean", Source("ElectionSummary", "pv_margin")),
    # The counts on /elections/majority (#569, D112): elections whose Electoral College
    # leader had no majority (the flag false), and elections whose popular-vote winner
    # differs from that leader (the flip true).
    "ec_no_majority_count": Metric(
        "flag_count", Source("ElectionSummary", "ec_determinative"), counted=False
    ),
    "pv_flip_count": Metric(
        "flag_count", Source("ElectionSummary", "pv_flip"), counted=True
    ),
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


@dataclass(frozen=True)
class FlagCount:
    """How many elections hold one value of a served flag, out of N, and the years that
    entered N (#569, D112).

    Three states, and no other can be built: a count (``n`` ≥ 1, 0 ≤ ``count`` ≤
    ``n``, ``first`` ≤ ``last``, both years); no contributing flag (``count`` and ``n``
    0, no years); and unrecognized (a value that is no flag was among the inputs: no
    count, no N, no years).
    """

    count: int
    n: int
    first: int | None
    last: int | None
    unrecognized: bool = False

    def __post_init__(self) -> None:
        empty = (
            self.count == 0 and self.n == 0 and self.first is None and self.last is None
        )
        if self.unrecognized or self.n == 0:
            ok = empty
        else:
            ok = (
                type(self.count) is int
                and type(self.n) is int
                and 0 <= self.count <= self.n
                and type(self.first) is int
                and type(self.last) is int
                and self.first <= self.last
            )
        if not ok:
            raise ValueError(f"not a flag count: {self!r}")


#: The count of inputs that hold a value no flag can be.
UNRECOGNIZED_COUNT = FlagCount(0, 0, None, None, unrecognized=True)
#: The count of no contributing flag.
NO_COUNT = FlagCount(0, 0, None, None)


def flag_count(pairs: Iterable[tuple[int, object]], counted: bool) -> FlagCount:
    """How many of the flags in ``(year, flag)`` pairs, already joined on the year, are
    ``counted``, out of the flags that are a value (#569, D112).

    Only ``None`` is null: it is left out of N and never read as false (D097(a)). Any
    other value that is not a ``bool`` (a blank string, a number, ``1`` for true) makes
    the whole count :data:`UNRECOGNIZED_COUNT`: leaving it out would drop a year and
    misstate N. Each pair is one election; the caller passes each year once.
    """
    hits = 0
    years: list[int] = []
    for year, value in pairs:
        if value is None:
            continue
        if type(value) is not bool:
            return UNRECOGNIZED_COUNT
        hits += value is counted
        years.append(year)
    if not years:
        return NO_COUNT
    return FlagCount(hits, len(years), min(years), max(years))
