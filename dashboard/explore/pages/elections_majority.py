"""Chart C2 and its companion table, on their own page (#434, D096; split by #562,
D107): ``/elections/majority``, each served year's Electoral College leader's share
against the majority line, from N1 (``api.SUMMARY_PATH``, filled on first use) read in
the same view as the index. No filter reaches the page: it has no ``query=`` parser.
A failed or malformed N1 degrades the chart's section only (D096(d)): the heading,
lede and success marker stay.
"""

from __future__ import annotations

from typing import Any

import dash
from dash import dcc, html

from explore import (
    api,
    charts,
    components,
    election_view,
    elections_view,
    export,
    labels,
    over_time,
)
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries, whether or not N1 could be read.
PAGE_ID = "elections-majority"
#: This page's own path, the view URL its download names.
PATH = "/elections/majority"

#: Page-level wording (ba spec, approved by the owner at #562's plan gate, 2026-11-19).
#: The heading was C2's section heading on ``/elections`` (#434's plan gate).
HEADING = "Did the Electoral College leader win a majority?"
LEDE = (
    "For every election in this dataset: the candidate with the most electoral votes "
    "counted, and whether they won more than half of the electors appointed."
)

#: Chart C2 (#434, D096) and its companion table, never narrowed by a filter.
C2_ID = "C2"
LEADER_TABLE_ID = "elections-leader-table"
LEADER_UNAVAILABLE_ID = "elections-leader-unavailable"
#: The companion table's columns, in display order, by public field name: the year's
#: Electoral College leader's national row, with the year's ``ec_determinative`` from
#: N1's ``elections`` item, and ``took_office`` last (owner, #434's plan gate).
LEADER_FIELDS = (
    "year",
    "candidate",
    "national_electoral_votes_counted",
    "national_electoral_denominator",
    "ec_share_full",
    "ec_determinative",
    "took_office",
)
#: The leader table's cells :func:`_leader_cells` words, in :data:`LEADER_FIELDS`
#: order (the year is a link and the candidate a linked name).
LEADER_WORDED = LEADER_FIELDS[2:]
#: Exported though not shown: the key of the candidate's history link.
LEADER_EXTRA = ("candidate_slug",)

C2_TABLE_HEADING = "Each election's Electoral College leader"
#: C2's section when N1 cannot be read or is malformed. Never ``UNAVAILABLE_MESSAGE``'s
#: wording: the D070(b) guard's success run asserts that absent from every page.
#: C2's section when N1 cannot be read or is malformed. Never ``UNAVAILABLE_MESSAGE``'s
#: wording: the D070(b) guard's success run asserts that absent from every page.
C2_UNAVAILABLE = (
    "The chart and table of each election's Electoral College leader can't be shown "
    "right now. Please try again in a minute."
)

#: C2's height, the same for every number of served years now that years run along
#: the bottom (#558, D104). Its title is page text (``components.chart`` takes it out of
#: the figure), so the template's top margin holds nothing above the plot.
_C2_HEIGHT_PX = 360
#: How far below the majority line its label starts: more than C2's point radius.
_C2_LINE_LABEL_SHIFT_PX = 6
#: Each C2 marker series' symbol (#558, D104), so no two differ by color alone; one
#: symbol per meaning across C2, C4 and C5 (an open circle for no figure in this
#: dataset, an open square for an unrecognized value).
_C2_SYMBOLS = {
    labels.C1_NO_SHARE: "circle-open",
    labels.UNRECOGNIZED: "square-open",
}


dash.register_page(
    __name__,
    path=PATH,
    title=f"Electoral College majority — {SITE_TITLE}",
    description=(
        "Whether the Electoral College leader in each US presidential election won a "
        "majority of the electors appointed."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    # N1, filled on first use (D096(c)): a literal (D074(ii)), never prefetched.
    on_miss=(api.SUMMARY_PATH,),
    success=PAGE_ID,
    # The site navigation link this page marks (#448): the elections index's.
    nav="elections",
)


def leaders(index: dict[str, Any], summary: Any) -> list[dict[str, Any]]:
    """Each served year's Electoral College leader, oldest first: N1's one ``data`` row
    with ``electoral_rank`` 1, with the year's ``ec_determinative`` from its one
    ``elections`` item (#434, D096). Derives nothing.

    Pure; raises what :func:`explore.elections_view.n1_items` raises, and ``TypeError``
    for anything else C2 cannot show: a ``data`` row whose year
    :func:`explore.election_view.row_year` refuses or the index does not serve, or a
    served year with no rank-1 row or two (a tie at rank 1 is valid API data,
    D094(iv), but C2 needs one leader per year). ``electoral_rank`` counts only as an
    ``int``, never a ``bool``.
    """
    by_year = elections_view.n1_items(index, summary)
    served = set(by_year)
    rows = summary["data"]
    if not isinstance(rows, list):
        raise TypeError(f"{api.SUMMARY_PATH} carries no list of rows")
    leader: dict[int, dict[str, Any]] = {}
    for row in rows:
        year = election_view.row_year(row)
        if year is None or year not in served:
            raise TypeError(f"{api.SUMMARY_PATH}: a row for a year not served")
        rank = row.get("electoral_rank")
        if type(rank) is int and rank == 1:
            if year in leader:
                raise TypeError(f"{api.SUMMARY_PATH}: two leaders in {year}")
            leader[year] = row
    if set(leader) != served:
        raise TypeError(f"{api.SUMMARY_PATH} misses a served year")
    return [
        {**leader[year], "ec_determinative": by_year[year]["ec_determinative"]}
        for year in sorted(served)
    ]


def _leader_cells(row: dict[str, Any]) -> dict[str, str]:
    """The leader table's worded cells, computed once per row per render and read by
    both the table and C2, so the chart writes every number as the table does."""
    return {
        "national_electoral_votes_counted": labels.number(
            row["national_electoral_votes_counted"]
        ),
        "national_electoral_denominator": labels.number(
            row["national_electoral_denominator"]
        ),
        "ec_share_full": labels.share_cell(row["ec_share_full"]),
        "ec_determinative": labels.ec_majority(row["ec_determinative"]),
        "took_office": labels.yes_no(row["took_office"]),
    }


def _leader_row(row: dict[str, Any], cells: dict[str, str]) -> html.Tr:
    year = row["year"]
    return html.Tr(
        [
            html.Td(dcc.Link(str(year), href=f"/election/{year}")),
            components.candidate_cell(row),
            *(labels.cell(cells[field]) for field in LEADER_WORDED),
        ]
    )


def _majority(cell: str) -> str:
    """The hover's last line, every year: the majority cell itself when it says
    whether anyone won one, else named by its field, as the table's header names it."""
    if cell in (labels.EC_MAJORITY, labels.NO_EC_MAJORITY):
        return cell
    return f"{labels.LABELS['ec_determinative']}: {cell}"


def _c2_figure(
    rows: list[dict[str, Any]], cells: list[dict[str, str]]
) -> tuple[dict[str, Any], bool]:
    """C2's figure (#434, D096, as amended by D104 for #558): election year along the
    bottom (:func:`explore.components.year_axis`), one point per served year at the
    leader's served ``ec_share_full``, against a dashed line at half of each election's
    electors appointed; and whether a marker is drawn.

    No point carries text: its hover writes the table's cells, the share among them. A
    share the table does not show as one is a marker at zero, never a dropped year, in
    a series of its own per label (:data:`explore.labels.C1_NO_SHARE` for a null or
    blank, else :data:`explore.labels.UNRECOGNIZED`), each with its own symbol and named
    in the chart's key. Every hover item is a string the page wrote.
    """
    years = [row["year"] for row in rows]
    xs: list[int] = []
    ys: list[float] = []
    hovers: list[str] = []
    marks: dict[str, list[tuple[int, str]]] = {}  # label -> [(year, hover)]
    for row, cell in zip(rows, cells, strict=True):
        shown = cell["ec_share_full"]
        number = labels.finite(row["ec_share_full"])
        hover = labels.C2_HOVER.format(
            year=str(row["year"]),
            candidate=charts.escaped(str(row["candidate"])),
            share=over_time.noted(shown),
            counted=cell["national_electoral_votes_counted"],
            appointed=cell["national_electoral_denominator"],
            majority=_majority(cell["ec_determinative"]),
        )
        # A finite value whose cell is no share (one whose percentage overflows reads
        # UNRECOGNIZED) is a marker too: the point stands only where the table shows it.
        if number is not None and shown != labels.UNRECOGNIZED:
            xs.append(row["year"])
            ys.append(number)
            hovers.append(hover)
        else:
            label = (
                labels.C1_NO_SHARE
                if shown == labels.NOT_IN_DATASET
                else labels.UNRECOGNIZED
            )
            marks.setdefault(label, []).append((row["year"], hover))
    data: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "markers",
            "name": labels.LABELS["ec_share_full"],
            "showlegend": False,
            "ids": [str(year) for year in xs],
            "x": xs,
            "y": ys,
            # A share near 100% sits at the plot's top edge: drawn whole, not clipped.
            "cliponaxis": False,
            "marker": {"symbol": "circle", "size": 7, "color": "var(--chart-1)"},
            "hovertext": hovers,
            "hovertemplate": "%{hovertext}<extra></extra>",
        }
    ]
    for label, symbol in _C2_SYMBOLS.items():
        if label in marks:
            years_, hovers_ = zip(*marks[label], strict=True)
            data.append(
                over_time.marker_trace(label, symbol, list(years_), list(hovers_))
            )
    layout: dict[str, Any] = {
        "title": {"text": labels.C2_TITLE},
        "height": _C2_HEIGHT_PX,
        "showlegend": bool(marks),
        "xaxis": components.year_axis(years),
        "yaxis": {
            "range": [0, 1],
            "tickformat": ".0%",
            "dtick": 0.25,
            "title": {"text": labels.C2_VALUE_AXIS},
        },
        "shapes": [
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": 0.5,
                "y1": 0.5,
                "layer": "below",
                "line": {
                    "dash": "dash",
                    "width": 2,
                    "color": "var(--chart-reference)",
                },
            }
        ],
        # The line's label just below it at the right (owner, #558's plan gate): the
        # leaders' shares sit above the line there, and the low ones are at the left.
        # Shifted down by more than a marker's radius, so a point just above the line
        # (2000's 50.4%) stays clear of it.
        "annotations": [
            {
                "text": labels.C2_MAJORITY_LINE,
                "xref": "paper",
                "x": 1,
                "xanchor": "right",
                "yref": "y",
                "y": 0.5,
                "yanchor": "top",
                "yshift": -_C2_LINE_LABEL_SHIFT_PX,
                "align": "right",
                "showarrow": False,
                "font": {"color": "var(--text)", "size": 12},
            }
        ],
    }
    if marks:
        layout["legend"] = components.TIME_SERIES_LEGEND
    return {"data": data, "layout": layout}, bool(marks)


def _c2_caption(marked: bool) -> str:
    """C2's caption: which candidate each point is, what the share counts, what the
    line marks, that the leader did not always take office and, where a marker is
    drawn (``marked``), what it means. It names no served text (D095(a));
    ``components.chart`` adds the table pointer."""
    parts = [
        labels.C2_LEADER_POINT,
        labels.C1_EC_BASIS,
        labels.C2_MAJORITY_NOTE,
        labels.C2_TOOK_OFFICE,
    ]
    if marked:
        parts.append(labels.C2_NO_SHARE_NOTE)
    return " ".join(parts)


def _leader_section(index: dict[str, Any], summary: Any) -> list[Any]:
    """C2's section (#434, D096): the chart and its companion table, or, when N1 could
    not be read (``summary`` is ``None``) or is malformed, :data:`C2_UNAVAILABLE` only.
    The page's heading is the section's (#562). The ``try`` covers everything built
    from N1 (the validation, the figure, the cells, and the companion table and its
    download), so no ``KeyError`` or ``TypeError`` from N1 reaches the page; never
    ``components.chart``, which no page catches around (D095(f))."""
    try:
        if summary is None:
            raise TypeError(f"{api.SUMMARY_PATH} is unavailable")
        rows = leaders(index, summary)
        cells = [_leader_cells(row) for row in rows]
        figure, marked = _c2_figure(rows, cells)
        download = export.Download(
            filename="elections-electoral-college-leaders.csv",
            name="the Electoral College leaders",
            provenance=summary["meta"]["provenance"],
            # No filter reaches this table, so its view names none.
            view_url=export.view_url(CANONICAL_HOST, PATH, ""),
        )
        by_row = {id(row): cell for row, cell in zip(rows, cells, strict=True)}
        # Inside the try: the table and its CSV read N1 too (each row's slug, the
        # provenance the preamble names), and a defect there is N1's, not the page's.
        table = components.table(
            rows,
            lambda r: _leader_row(r, by_row[id(r)]),
            LEADER_FIELDS,
            LEADER_TABLE_ID,
            download,
            extra=LEADER_EXTRA,
            notes=(labels.C2_LEADER_ROW, labels.C2_TOOK_OFFICE),
        )
    except (KeyError, TypeError):
        return [
            html.P(C2_UNAVAILABLE, id=LEADER_UNAVAILABLE_ID, className="note"),
        ]
    return [
        components.chart(C2_ID, figure, LEADER_TABLE_ID, _c2_caption(marked)),
        html.H2(C2_TABLE_HEADING),
        *table,
        labels.glossary(LEADER_FIELDS),
    ]


def render(index: dict[str, Any], summary: Any) -> html.Div:
    """The whole page for one ``/v1/elections`` response and N1's body (``None`` when
    it could not be read): the heading and lede, then C2's section, then the footer."""
    provenance = index["meta"]["provenance"]
    return html.Div(
        [
            html.H1(HEADING),
            html.P(LEDE, className="lede"),
            *_leader_section(index, summary),
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(**query: Any) -> html.Div:
    """The Electoral College majority page. The index and then N1 are read in one view;
    a failed N1 degrades only C2's section, a failed index the whole page."""
    try:
        with api.CLIENT.view() as view:
            body = view.get(api.ELECTIONS_PATH)
            try:
                summary = view.get(api.SUMMARY_PATH)
            except api.ApiUnavailable:
                summary = None
        return render(body, summary)
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    return html.Div([html.H1(HEADING), html.P(LEDE, className="lede"), content])
