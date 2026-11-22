"""The dashboard's own summaries over served rows (#437, D097): the one module that
computes them, so the rule they follow is enforced in one place.

The rule (D097, owner-approved 2026-11-05): inputs are served fields of one grain,
from the render's pinned view; only count, sum and mean over rows, never a ratio of
fields and never a recomputed served figure; a mean excludes nulls and shows its N; a
sum with any null reads no figure; a null flag is never counted as false; and wherever
a served figure exists, the metric reconciles to it. D112 (#569) amends it for the
pages #569 adds figures to; the counts of a served flag here are its first, the
select (#600, D114) its second, and the sum (#601, D115) its third.

Numbers only: the wording is :mod:`explore.labels`' (``METRIC_LABELS``,
``metric_mean``), except that a select carries each value's companion-table cell, so
the figure shows exactly what the table shows (D114, widening D097(f)). Pure and
shared: it reads no API and imports only ``labels``, whose
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
    """One metric: its kind (one of :data:`KINDS`), the served field it reads, for a
    ``flag_count`` the flag value it counts and for a ``select`` the value it picks (one
    of :data:`PICKS`), each ``None`` for every other kind; and whether it is read
    against the popular-vote window (#600, D114), so a page asks the metric rather than
    keeping a table of its own."""

    kind: str
    source: Source
    counted: bool | None = None
    pick: str | None = None
    reads_pv_window: bool = False


#: The metric kinds, a closed set, each computed by the function of the same name here
#: (``count``, ``mean``, ``flag_count``; #569, D112; ``select``, #600, D112(d), D114;
#: ``sum``, #601, D115).
KINDS = ("count", "mean", "flag_count", "select", "sum")
#: What a ``select`` picks: the earliest or latest year with a value, or the lowest or
#: highest value (#600, D112(d)).
PICKS = ("first", "latest", "lowest", "highest")


#: Every metric, keyed by metric key, never renamed or reused. The page reads the field
#: each mean averages from here, so this table drives the code. A count's source is the
#: field that decides which rows it counts: for ``elections_shown`` the grain key of the
#: ``/v1/elections`` rows T1 shows (#601, D115).
METRICS: dict[str, Metric] = {
    "elections_shown": Metric("count", Source("YearListItem", "year")),
    "ec_margin_mean": Metric("mean", Source("ElectionSummary", "ec_margin")),
    "pv_margin_mean": Metric(
        "mean", Source("ElectionSummary", "pv_margin"), reads_pv_window=True
    ),
    # The counts on /elections/majority (#569, D112): elections whose Electoral College
    # leader had no majority (the flag false), and elections whose popular-vote winner
    # differs from that leader (the flip true).
    "ec_no_majority_count": Metric(
        "flag_count", Source("ElectionSummary", "ec_determinative"), counted=False
    ),
    "pv_flip_count": Metric(
        "flag_count",
        Source("ElectionSummary", "pv_flip"),
        counted=True,
        reads_pv_window=True,
    ),
    # The figures on /elections/over-time (#600, D112(d)): the electors appointed and
    # the total popular vote in the earliest and latest years shown with a value.
    "ec_appointed_first": Metric(
        "select", Source("ElectionSummary", "electoral_denominator"), pick="first"
    ),
    "ec_appointed_latest": Metric(
        "select", Source("ElectionSummary", "electoral_denominator"), pick="latest"
    ),
    "pv_total_first": Metric(
        "select",
        Source("NationalSummaryRow", "national_pv_denominator"),
        pick="first",
        reads_pv_window=True,
    ),
    "pv_total_latest": Metric(
        "select",
        Source("NationalSummaryRow", "national_pv_denominator"),
        pick="latest",
        reads_pv_window=True,
    ),
    # The figures on /state/<usps>/per-capita (#600): the state's lowest and highest
    # people per electoral vote among the years shown.
    "state_per_capita_lowest": Metric(
        "select", Source("PerCapitaRow", "persons_per_electoral_vote"), pick="lowest"
    ),
    "state_per_capita_highest": Metric(
        "select", Source("PerCapitaRow", "persons_per_electoral_vote"), pick="highest"
    ),
    # The figures on /state/<usps> (#601, D112(e), D115): the elections in which the
    # state appointed electors (an allotment above 0), and in how many of them its
    # electors cast a vote for the candidate who took office (a flag the page derives:
    # ``took_office`` picks the row, its ``electoral_votes`` decides).
    "state_elections_count": Metric(
        "count", Source("EcPvRow", "state_electoral_votes")
    ),
    "state_took_office_count": Metric(
        "flag_count", Source("EcPvRow", "took_office"), counted=True
    ),
    # The figures on /candidate/<slug> (#601, D112(f), D115): the elections in which
    # electors cast a vote for the candidate, and the national electoral votes cast and
    # counted for them, one value per year.
    "candidate_elections_count": Metric("count", Source("EcPvRow", "year")),
    "candidate_ev_cast_total": Metric(
        "sum", Source("EcPvRow", "national_electoral_votes")
    ),
    "candidate_ev_counted_total": Metric(
        "sum", Source("EcPvRow", "national_electoral_votes_counted")
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

    A null or a blank (:func:`explore.labels.is_blank`, the module's one rule of what is
    null, which the table cells follow too) is left out of N and never read as false
    (D097(a)). Any other value that is not a ``bool`` (a number, ``1`` for true, a
    word) makes the whole count :data:`UNRECOGNIZED_COUNT`: leaving it out would drop a
    year and misstate N. Each pair is one election; the caller passes each year once.
    """
    hits = 0
    years: list[int] = []
    for year, value in pairs:
        if labels.is_blank(value):
            continue
        if type(value) is not bool:
            return UNRECOGNIZED_COUNT
        hits += value is counted
        years.append(year)
    if not years:
        return NO_COUNT
    return FlagCount(hits, len(years), min(years), max(years))


@dataclass(frozen=True)
class Selection:
    """The earliest, latest, lowest and highest of one served field over the years
    shown, each as the companion table's own cell, with N, the years with a value
    (#600, D112(d), D114).

    ``first`` and ``latest`` are ``(year, cell)``; ``lowest`` and ``highest`` are
    ``(cell, years)``, naming every year whose cell equals the extreme's (a tie by the
    cell the table shows, owner at #600's plan gate). Three states, and no other can be
    built: values (``n`` ≥ 1, every pick set, the first year no later than the latest,
    each extreme naming at least one year in ascending order); no value (``n`` 0, no
    picks); and unrecognized (no ``n``, no picks).
    """

    n: int
    first: tuple[int, str] | None
    latest: tuple[int, str] | None
    lowest: tuple[str, tuple[int, ...]] | None
    highest: tuple[str, tuple[int, ...]] | None
    unrecognized: bool = False

    def __post_init__(self) -> None:
        picks = (self.first, self.latest, self.lowest, self.highest)
        if self.unrecognized or self.n == 0:
            ok = self.n == 0 and all(p is None for p in picks)
        else:
            ok = (
                type(self.n) is int
                and self.n >= 1
                and _year_cell(self.first)
                and _year_cell(self.latest)
                and _cell_years(self.lowest)
                and _cell_years(self.highest)
            )
            if ok:
                assert self.first is not None and self.latest is not None
                ok = self.first[0] <= self.latest[0]
        if not ok:
            raise ValueError(f"not a selection: {self!r}")


def _year_cell(pick: object) -> bool:
    return (
        isinstance(pick, tuple)
        and len(pick) == 2
        and type(pick[0]) is int
        and isinstance(pick[1], str)
    )


def _cell_years(pick: object) -> bool:
    if not (isinstance(pick, tuple) and len(pick) == 2 and isinstance(pick[0], str)):
        return False
    years = pick[1]
    return (
        isinstance(years, tuple)
        and len(years) >= 1
        and all(type(y) is int for y in years)
        and list(years) == sorted(set(years))
    )


#: The selection over inputs that hold a value no figure can show.
UNRECOGNIZED_SELECTION = Selection(0, None, None, None, None, unrecognized=True)
#: The selection of no year with a value.
NO_SELECTION = Selection(0, None, None, None, None)


def select(triples: Iterable[tuple[int, object, str]]) -> Selection:
    """The earliest, latest, lowest and highest of the values in ``(year, value,
    cell)`` triples, already joined on the year, ``cell`` being the companion table's
    own string for that value (#600, D112(d), D114).

    A null or a blank (:func:`explore.labels.is_blank`) is left out and is never an
    extreme, whatever its cell says: a cell reading :data:`explore.labels.UNRECOGNIZED`
    on a null names why the value is missing (an unknown cause code), not a value, and N
    counts only years with one (owner, #609's review; D114(a)). Any other value
    :func:`explore.labels.finite` refuses, or a value whose own cell reads
    :data:`explore.labels.UNRECOGNIZED` (a number the table cannot show, such as a float
    allotment), makes the whole selection :data:`UNRECOGNIZED_SELECTION`: leaving it out
    would drop a year and misstate N. The extremes are chosen by value; each names every
    year whose cell equals the chosen one's, so the figure never names one year where
    the table shows two equal cells. Each triple is one election; the caller passes each
    year once (the per-capita page refuses a body that names a year twice, D114(g)), and
    a repeated year tied at an extreme makes :class:`Selection` raise ``ValueError``.
    """
    kept: list[tuple[int, float, str]] = []
    for year, value, cell in triples:
        if labels.is_blank(value):
            continue
        number = labels.finite(value)
        if number is None or cell == labels.UNRECOGNIZED:
            return UNRECOGNIZED_SELECTION
        kept.append((year, number, cell))
    if not kept:
        return NO_SELECTION
    kept.sort(key=lambda row: row[0])

    def every_year(chosen: tuple[int, float, str]) -> tuple[str, tuple[int, ...]]:
        return chosen[2], tuple(year for year, _, cell in kept if cell == chosen[2])

    return Selection(
        len(kept),
        (kept[0][0], kept[0][2]),
        (kept[-1][0], kept[-1][2]),
        every_year(min(kept, key=lambda row: row[1])),
        every_year(max(kept, key=lambda row: row[1])),
    )


@dataclass(frozen=True)
class Total:
    """A sum of one served integer field over elections, one value per year, with N
    and the years that entered it (#601, D115).

    Three states, and no other can be built: a total (``value`` an ``int`` ≥ 0, ``n`` ≥
    1, ``first`` ≤ ``last``, both years); no figure (a null among the inputs, D097: a
    sum with any null reads no figure; no value, no N, no years); and unrecognized (a
    value no total can hold was among the inputs: no value, no N, no years).
    """

    value: int | None
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
                type(self.value) is int
                and self.value >= 0
                and type(self.n) is int
                and self.n >= 1
                and type(self.first) is int
                and type(self.last) is int
                and self.first <= self.last
            )
        if not ok:
            raise ValueError(f"not a total: {self!r}")


#: The total over inputs that hold a value no total can hold.
UNRECOGNIZED_TOTAL = Total(None, 0, None, None, unrecognized=True)
#: The total with a null among its inputs, or with no input at all.
NO_TOTAL = Total(None, 0, None, None)


def sum(pairs: Iterable[tuple[int, object]]) -> Total:
    """The sum of the values in ``(year, value)`` pairs, already joined on the year
    (#601, D115): one pair per year, the per-year one-value check being the page's
    (D098's pattern, through ``over_time.same``). Named for its kind (:data:`KINDS`),
    so it shadows the builtin in this module, which never calls the builtin.

    A null or a blank (:func:`explore.labels.is_blank`) among the values makes the whole
    sum :data:`NO_TOTAL` (D097: a sum with any null reads no figure), unless a value no
    total can hold comes too, which wins. A value that is not an ``int`` at or above 0
    (a bool, a float, text, a negative) makes it :data:`UNRECOGNIZED_TOTAL`. No pair at
    all is :data:`NO_TOTAL`. Zero is a value (Greeley's counted votes in 1872).
    """
    total = 0
    years: list[int] = []
    null = False
    for year, value in pairs:
        if labels.is_blank(value):
            null = True
            continue
        if type(value) is not int or value < 0:
            return UNRECOGNIZED_TOTAL
        total += value
        years.append(year)
    if null or not years:
        return NO_TOTAL
    return Total(total, len(years), min(years), max(years))
