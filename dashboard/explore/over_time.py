"""The election-year time series' shared pieces (#560, D106): C4's figure and what it
is built from, moved out of ``pages/elections.py`` so a state's history page can draw
the same one-state series (C7) without importing a page module, which Dash cannot do
(it executes a page before it is in ``sys.modules``).

A shared module: it reads no API and imports only other shared modules (``charts``,
``components`` and ``labels``), so a source's path reaches an error message only as an
argument. C5's figure, its band and the N1/N2 readers stay with their page.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple, TypeVar

from explore import charts, components, labels

#: C4, C5 and C7's height, the same in every mode now that years run along the bottom
#: (#558, D104). Their titles are page text (``components.chart`` takes them out of the
#: figure), so the top margin is the template's; C5 adds room above it for its band
#: labels (``pages/elections.py``), and C4 beside it takes C5's margin, so the pair's
#: plots line up.
HEIGHT_PX = 360
TOP_PX = 16
#: C4's marker series' symbols (#558, D104), which C7 draws too (#560): one series per
#: label, so the chart's key names each cause, and one symbol per meaning across C2, C4,
#: C5 and C7: "took no part" is C5's "x", no figure in this dataset C5's open circle, an
#: unrecognized value the open square; "no electors appointed", C4's and C7's alone, is
#: an open triangle.
C4_SYMBOLS = {
    labels.C4_NO_ELECTORS: "triangle-up-open",
    labels.C4_NO_ELECTORS_TOOK_NO_PART: "x",
    labels.NOT_IN_DATASET: "circle-open",
    labels.UNRECOGNIZED: "square-open",
}


def same(a: Any, b: Any) -> bool:
    """Whether two served values are one value: of one type and equal, so a null beside
    a figure is two values, as D077 and D098 count NULL. A NaN repeated is one value
    (it is unequal to itself), which its cell then reads as unrecognized."""
    if type(a) is not type(b):
        return False
    return bool(a == b) or (isinstance(a, float) and a != a and b != b)


def plain(name: Any) -> str | None:
    """A served state name a title or caption may name (#436): text with something in
    it and nothing ``components.chart`` refuses in a title or plotly could read as
    markup or a token; else ``None``, and the "selected state" form is used."""
    if not isinstance(name, str) or not labels.has_text(name):
        return None
    if "<" in name or "var(" in name:
        return None
    return name


class Point(NamedTuple):
    """One row of C4, C5 and C7 (#436, #560): its year, the served appointed allotment
    and total popular vote, and the companion table's cells for them (and, for one
    state, for its ``pv_status``). C7 draws no total: :func:`appointed_points` leaves
    ``total`` ``None`` and ``total_cell`` empty, which only C5 reads."""

    year: int
    appointed: Any
    appointed_cell: str
    total: Any
    total_cell: str
    status: Any
    status_cell: str | None


def figure_value(value: Any, *, zero: bool) -> int | None:
    """A served count a bar can draw: an ``int`` (never a ``bool``) no larger than
    :data:`explore.charts.MAX_INTEGER`, above zero, or at zero too where ``zero``.
    Anything else is a marker."""
    if type(value) is not int or value > charts.MAX_INTEGER:
        return None
    return value if value > 0 or (zero and value == 0) else None


def noted(cell: str) -> str:
    """A cell as a hover writes it: an unrecognized one adds its note."""
    if cell == labels.UNRECOGNIZED:
        return f"{cell}<br>{labels.UNRECOGNIZED_NOTE}"
    return cell


def point_hover(point: Point, state: str | None, *, total: bool) -> str:
    """A row's hover in C4 (``total`` false) or C5: the table's cells. ``state`` is
    the escaped state name, or ``None`` for all states."""
    year = str(point.year)
    if state is None:
        if total:
            return labels.C5_HOVER.format(year=year, total=noted(point.total_cell))
        return labels.C4_HOVER.format(year=year, appointed=noted(point.appointed_cell))
    status = noted(point.status_cell or labels.UNRECOGNIZED)
    if total:
        return labels.C5_STATE_HOVER.format(
            year=year, state=state, total=noted(point.total_cell), pv_status=status
        )
    return labels.C4_STATE_HOVER.format(
        year=year,
        state=state,
        appointed=noted(point.appointed_cell),
        pv_status=status,
    )


def bar_trace(name: str, drawn: list[tuple[Point, int, str, str]]) -> dict[str, Any]:
    """A series of bars, one per drawn row at its year, kept off the chart's key; no
    bar carries text, and its hover writes the table's cells (#558, D104)."""
    return {
        "type": "bar",
        "name": name,
        "showlegend": False,
        "ids": [str(point.year) for point, _, _, _ in drawn],
        "x": [point.year for point, _, _, _ in drawn],
        "y": [value for _, value, _, _ in drawn],
        "marker": {"color": "var(--chart-1)"},
        "hovertext": [hover for _, _, _, hover in drawn],
        "hovertemplate": "%{hovertext}<extra></extra>",
    }


def marker_trace(
    name: str, symbol: str, years: list[int], hovers: list[str]
) -> dict[str, Any]:
    """A time-series chart's series of markers at zero (C2, C4, C5 and C7), one per year
    with nothing to draw, named by ``name`` in the chart's key (#558, D104: the key
    labels the marker, not a text beside each), drawn whole at the plot's edge."""
    return {
        "type": "scatter",
        "mode": "markers",
        "name": name,
        "showlegend": True,
        "ids": [str(year) for year in years],
        "x": list(years),
        "y": [0] * len(years),
        "cliponaxis": False,
        "marker": {"symbol": symbol, "size": 9, "color": "var(--text)"},
        "hovertext": list(hovers),
        "hovertemplate": "%{hovertext}<extra></extra>",
    }


def series(
    marks: dict[str, list[tuple[Point, str]]], symbols: dict[str, str]
) -> list[dict[str, Any]]:
    """C4's or C5's marker series, one per label in ``symbols``' order."""
    return [
        marker_trace(
            label,
            symbol,
            [point.year for point, _ in marks[label]],
            [hover for _, hover in marks[label]],
        )
        for label, symbol in symbols.items()
        if label in marks
    ]


def time_layout(
    title: str, axis: str, years: list[int], longest: int, *, marked: bool
) -> dict[str, Any]:
    """C4, C5 and C7's shared layout (#558, D104): election year along the bottom, the
    served years' axis in every mode (:func:`explore.components.year_axis`), so a
    state's years before its first election keep their place; the value up the side
    from zero, with a few full-number ticks; and the chart's key where a marker is
    drawn (``marked``)."""
    layout: dict[str, Any] = {
        "title": {"text": title},
        "height": HEIGHT_PX,
        "margin": {"t": TOP_PX},
        "showlegend": marked,
        "xaxis": components.year_axis(years),
        "yaxis": {
            "range": [0, max(longest, 1)],
            "nticks": 4,
            "title": {"text": axis},
        },
    }
    if marked:
        layout["legend"] = components.TIME_SERIES_LEGEND
    return layout


class OverTime(NamedTuple):
    """A chart's figure and what its caption needs to say."""

    figure: dict[str, Any]
    zeros: bool
    missing: bool
    before: bool
    after: bool


def c4_figure(
    points: list[Point], years: list[int], title: str, state: str | None
) -> OverTime:
    """C4's figure (#436, D100): the appointed allotment of each row with one, as a
    bar at its year; a zero allotment is a marker by its cause (the D091 exception),
    and a null or unknown one a marker, each label a series of its own named in the
    chart's key (#558, D104).
    ``state`` is the escaped state name, or ``None`` for all states."""
    drawn: list[tuple[Point, int, str, str]] = []
    marks: dict[str, list[tuple[Point, str]]] = {}
    for point in points:
        hover = point_hover(point, state, total=False)
        value = figure_value(point.appointed, zero=False)
        if value is not None and point.appointed_cell != labels.UNRECOGNIZED:
            drawn.append((point, value, point.appointed_cell, hover))
        elif type(point.appointed) is int and point.appointed == 0:
            label = (
                labels.C4_NO_ELECTORS_TOOK_NO_PART
                if point.status == "not_participating"
                else labels.C4_NO_ELECTORS
            )
            marks.setdefault(label, []).append((point, hover))
        else:
            label = (
                labels.NOT_IN_DATASET
                if point.appointed_cell == labels.NOT_IN_DATASET
                else labels.UNRECOGNIZED
            )
            marks.setdefault(label, []).append((point, hover))
    name = labels.LABELS[
        "electoral_denominator" if state is None else "state_electoral_votes"
    ]
    data: list[dict[str, Any]] = []
    if drawn:
        data.append(bar_trace(name, drawn))
    data += series(marks, C4_SYMBOLS)
    longest = max((value for _, value, _, _ in drawn), default=1)
    layout = time_layout(
        title, labels.C4_VALUE_AXIS, years, longest, marked=bool(marks)
    )
    zeros = bool(
        marks.keys() & {labels.C4_NO_ELECTORS, labels.C4_NO_ELECTORS_TOOK_NO_PART}
    )
    missing = bool(marks.keys() & {labels.NOT_IN_DATASET, labels.UNRECOGNIZED})
    return OverTime({"data": data, "layout": layout}, zeros, missing, False, False)


_Row = TypeVar("_Row")


def state_series(
    by_year: Mapping[int, _Row], served: Iterable[int], source: str, usps: str
) -> list[_Row]:
    """One state's rows in year order from its first served election (#436, D100(c);
    #560): the rule C4's one-state series (``n2_rows``) and C7 share. ``by_year`` maps
    each served year the state has a row in to that row.

    Pure; raises ``TypeError`` for a state with no row, a row for a year not served,
    or a gap: a served year after its first with no row for it. ``source`` is the API
    path its rows came from, and reaches the message only (a shared module reads no
    API).
    """
    if not by_year:
        raise TypeError(f"{source} has no row for {usps}")
    years = sorted(set(served))
    if not set(by_year) <= set(years):
        raise TypeError(f"{source} has a row for {usps} in a year not served")
    expected = [year for year in years if year >= min(by_year)]
    if sorted(by_year) != expected:
        raise TypeError(f"{source} skips a year for {usps}")
    return [by_year[year] for year in expected]


def appointed_points(rows: Iterable[Mapping[str, Any]]) -> list[Point]:
    """One state's electors appointed, a point per row (#560, C7): each row's
    ``year``, ``state_electoral_votes`` and ``pv_status``, worded once as the companion
    table writes them. Carries no total (C5's), so ``total`` is ``None`` and
    ``total_cell`` empty; :func:`c4_figure` never reads them."""
    return [
        Point(
            year=row["year"],
            appointed=row["state_electoral_votes"],
            appointed_cell=labels.number(row["state_electoral_votes"]),
            total=None,
            total_cell="",
            status=row["pv_status"],
            status_cell=labels.pv_status(row["pv_status"]),
        )
        for row in rows
    ]
