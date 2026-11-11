"""One election's overview (#307, #465): the election panel (#308), the winner under
each method, and National results, chart C1 (#433) and T3.

Since #465 the year's results by state (T2) and people per electoral vote (T6) are
pages of their own, ``/election/<year>/states`` and ``/election/<year>/per-capita``
(``pages/election_states.py``, ``pages/election_per_capita.py``); what the three pages
share is in :mod:`explore.election_view`. The overview reads one response,
``/v1/elections/{year}`` (its ``election`` block, ``data`` and ``summary``), filled on
a miss, so opening it makes one request. The year is the path (``/election/<year>``,
an item singular as the index is plural); it is validated from the ``/v1/elections``
the page prefetches before it is formatted into an API path (#312), so a year the
dataset does not serve is not found, at the index (404) and in the page.

It reads no filter, so its ``og:url`` names no query. A link that carries one of T2's
filters (shared before #465) is redirected by the index to the states page with them
(``moved=``, app.py). It follows the elections index's conventions
(``pages/elections.py``): labels from :mod:`explore.labels`, the provenance footer
from the response's own ``meta.provenance``, and every table through
:func:`explore.components.table`, which offers its rows as a CSV (#309) built from the
same list as its body. T3 is never filtered: it is the year's national result, as the
API's ``summary`` is. The panel is never filtered either.
"""

from __future__ import annotations

from typing import Any

import dash
from dash import html

from explore import api, charts, components, election_view, export, labels, query
from explore.config import CANONICAL_HOST, SITE_TITLE

#: The wrapper every successful render carries.
PAGE_ID = "election"
#: The wrapper of the not-found state: a year the dataset does not serve, or a section
#: the site does not have, which the greedy ``<year>`` brings here
#: (``/election/1824/x``).
NOT_FOUND_ID = "election-not-found"
NATION_TABLE_ID = "election-nation"
NO_PV_ID = "election-no-pv"
PANEL_ID = "election-panel"
#: The panel's place when the API serves ``election: null`` (a build gap).
PANEL_UNAVAILABLE_ID = "election-panel-unavailable"

#: T3's columns, in display order, by public field name.
NATION_FIELDS = (
    "candidate",
    "nominating_party",
    "national_electoral_votes",
    "national_electoral_votes_counted",
    "national_electoral_denominator",
    "electoral_rank",
    "took_office",
    "national_pv_votes",
    "ec_share_full",
    "pv_share",
    "hybrid_score",
)
#: The fields T3's column-name list names: its columns and the party note (#389).
NATION_GLOSSARY = (*NATION_FIELDS, "nominating_party_note")
#: What T3's CSV adds after its columns (#309): the party note and the party's per-row
#: source (#389), then the candidate's key and the year.
NATION_EXTRA = (
    "nominating_party_note",
    "nominating_party_source",
    "candidate_slug",
    "year",
)

#: The election panel's fields, in display order, by public field name (#308): who led
#: under each method, whether the popular-vote or the hybrid winner differs from the
#: Electoral College result, the three margins, whether anyone won a majority of
#: electors, and the share of electors appointed by states that held a popular vote.
PANEL_FIELDS = (
    "ec_winner",
    "pv_winner",
    "hybrid_winner",
    "pv_flip",
    "hybrid_flip",
    "ec_margin",
    "pv_margin",
    "hybrid_margin",
    "ec_determinative",
    "pv_coverage",
)

#: The panel's sentence when the API serves no ``election`` block for the year.
PANEL_UNAVAILABLE = "The comparison across methods is not available for this year."

#: Chart C1 (#433): each candidate's electoral share beside their popular-vote share,
#: with the majority line, beside T3.
C1_ID = "C1"

#: The year's popular-vote sentence above C1 and T3, when the dataset holds none for it.
NO_PV_SENTENCE = (
    "This dataset has no popular-vote figures for {year}; its popular-vote figures "
    "cover {first}–{last}."
)

#: The not-found state (#325), shared by the three election pages (#465).
NOT_FOUND = api.NotFound(
    labels.ELECTION_NOT_FOUND_HEADING, labels.ELECTION_NOT_FOUND_SENTENCE
)

#: The lede (ba spec, approved at #465's plan gate, 2026-11-10): what the overview
#: shows, in page order. It has no filter sentence: the overview has no filters.
LEDE = (
    "Who led under the Electoral College, the popular vote and the hybrid, and the "
    "national result for each candidate."
)

#: A served year's heading, the browser tab's title before the site title, and the
#: ``H1`` that ``render`` builds on a successful render (#464).
HEADING = "The {year} election"


VALIDATE: api.Validate = (api.ELECTIONS_PATH, election_view.served_year)


def title(year: Any = None, **_vars: Any) -> str:
    """The page title. app.py calls it only with a year the page's ``validate``
    accepted, or with none while that is unchecked (#325, D083); it is total anyway,
    reads no API, and names the year only when the year is four ASCII digits."""
    if isinstance(year, str) and query.YEAR_RE.fullmatch(year):
        return f"{HEADING.format(year=year)} — {SITE_TITLE}"
    return f"Election — {SITE_TITLE}"


dash.register_page(
    __name__,
    path_template=election_view.template(election_view.OVERVIEW),
    title=title,
    # No years: the index HTML never waits on the API, so this cannot read the span.
    description=(
        "One US presidential election: who led under the Electoral College, the "
        "popular vote and the hybrid, and the national result for each candidate."
    ),
    prefetch=(api.ELECTIONS_PATH,),
    on_miss=("/v1/elections/{year}",),
    success=PAGE_ID,
    validate=VALIDATE,
    not_found=NOT_FOUND,
    # The query keys that moved to the states page (#465): a document request
    # carrying one is redirected there by the index (302), with the states page's
    # parser normalizing the query.
    moved=(
        election_view.STATES_KEYS,
        election_view.template(election_view.STATES),
    ),
    # The site navigation link this page marks (#448):
    # a one-election view marks its index, Elections.
    nav="elections",
)


def _national_pv(value: Any, has_popular_vote: bool, as_share: bool) -> str:
    """A T3 cell that needs the popular vote: :data:`labels.NOT_APPLICABLE` in a year
    with no popular vote (T3's year rule, from the index row), the panel's wording for
    the same cause (#352), and inside it a null (or a blank, #355) is a candidate with
    no popular-vote figure."""
    if not has_popular_vote:
        return labels.NOT_APPLICABLE
    if labels.is_blank(value):
        return labels.NO_NATIONAL_FIGURE
    return labels.share(value) if as_share else labels.number(value)


#: The T3 fields :func:`_nation_cells` words, in T3's order: every column but the
#: candidate and the party, which are cells of their own (a link, a note).
NATION_WORDED = NATION_FIELDS[2:]


def _nation_cells(row: dict[str, Any], has_popular_vote: bool) -> dict[str, str]:
    """T3's cell text for each of :data:`NATION_WORDED`: the one source of the strings
    T3 shows and C1 draws (#433), so the chart writes each number as the table does."""
    return {
        "national_electoral_votes": labels.number(row["national_electoral_votes"]),
        "national_electoral_votes_counted": labels.number(
            row["national_electoral_votes_counted"]
        ),
        "national_electoral_denominator": labels.number(
            row["national_electoral_denominator"]
        ),
        "electoral_rank": labels.number(row["electoral_rank"]),
        "took_office": labels.yes_no(row["took_office"]),
        "national_pv_votes": _national_pv(
            row["national_pv_votes"], has_popular_vote, False
        ),
        # Nullable in the API's schema, though real for every served year.
        "ec_share_full": labels.share_cell(row["ec_share_full"]),
        "pv_share": _national_pv(row["pv_share"], has_popular_vote, True),
        # On T3's year rule, so the row agrees with itself.
        "hybrid_score": _national_pv(row["hybrid_score"], has_popular_vote, True),
    }


def _nation_row(row: dict[str, Any], cells: dict[str, str]) -> html.Tr:
    """A T3 row from its :func:`_nation_cells`, computed once per render and shared
    with C1."""
    return html.Tr(
        [
            components.candidate_cell(row),
            labels.nominating_party_cell(row),
            *(labels.cell(cells[field]) for field in NATION_WORDED),
        ]
    )


def _plotted(value: Any, cell: str) -> float | None:
    """The value C1 draws for a share, or ``None`` for a marker: only a number
    :func:`explore.labels.finite` accepts whose T3 cell is a share (#433). The chart
    computes no share; it draws the served value and labels it with T3's cell."""
    number = labels.finite(value)
    is_share = cell != labels.UNRECOGNIZED and cell == labels.share(value)
    return number if number is not None and is_share else None


#: Where a marker sits in a row (#433): the center of the slot of the bar it stands
#: for, from the template's ``bargap`` (one source), as plotly places two grouped bars
#: at a quarter of the row's bar band either side of its center. With one series the
#: bar is centered. The e2e test ``test_c1_on_2016_is_readable_at_390_px`` observes it
#: against a drawn bar.
_SLOT = (1 - charts.TEMPLATE["layout"]["bargap"]) / 4

#: Pixels per row and the margins around the plot (#433): two bars and their labels
#: per row at 390 px; the top margin holds the legend and the majority line's label.
_ROW_PX = 56
_TOP_PX = {True: 96, False: 56}
_BOTTOM_PX = 48


def _marker(field: str, cell: str) -> tuple[str, str]:
    """A marker's label and its hover cell, for a value T3 does not show as a share
    (#433): a missing popular-vote figure, a null or blank electoral share (named by its
    series, as T3's header names that cell), or an unrecognized value with its note."""
    if cell == labels.NO_NATIONAL_FIGURE:
        return labels.C1_NO_FIGURE, cell
    if field == "ec_share_full" and cell == labels.NOT_IN_DATASET:
        return labels.C1_NO_SHARE, f"{labels.LABELS[field]}: {cell}"
    if cell == labels.UNRECOGNIZED:
        return cell, f"{cell}<br>{labels.UNRECOGNIZED_NOTE}"
    return cell, cell


def _c1_figure(
    summary: list[dict[str, Any]],
    cells: list[dict[str, str]],
    has_popular_vote: bool,
    year: int,
) -> tuple[dict[str, Any], bool]:
    """C1's figure (#433), from T3's rows in T3's order, and whether it draws a
    :data:`labels.C1_NO_FIGURE` marker.

    One row per T3 row, at its position (0…n−1, reversed so T3's first is on top),
    labeled with the candidate's name as T3 shows it. Each bar is the served share,
    labeled with T3's cell for it; a share T3 does not show as one gets a labeled marker
    in its bar's slot, never a zero-length bar, and a real zero is a drawn, labeled bar.
    The popular-vote series is drawn only in a year T3 treats as having popular votes.
    ``cells`` are each row's :func:`_nation_cells`, the strings T3 shows. Total over
    every body T3 renders: it reads the served shares only through
    :func:`explore.labels.finite` and :func:`explore.labels.share` (:func:`_plotted`),
    and each name and slug as ``str``, escaped (:func:`explore.charts.escaped`).
    """
    n = len(summary)
    positions = list(range(n))
    names = [charts.escaped(str(row["candidate"])) for row in summary]
    slugs = [charts.escaped(str(row["candidate_slug"])) for row in summary]
    offsets = (
        {"ec_share_full": -_SLOT, "pv_share": _SLOT}
        if has_popular_vote
        else {"ec_share_full": 0.0}
    )
    marks: list[tuple[float, str, str, str]] = []  # (y, label, hover, id)
    no_figure = False
    bars = []
    for field, color, hover in (
        ("ec_share_full", "var(--chart-1)", labels.C1_EC_HOVER),
        ("pv_share", "var(--chart-2)", labels.C1_PV_HOVER),
    ):
        if field not in offsets:
            continue
        xs: list[float | None] = []
        texts: list[str] = []
        hovers: list[str] = []
        for i, (row, cell) in enumerate(zip(summary, cells, strict=True)):
            shown = cell[field]
            x = _plotted(row[field], shown)
            xs.append(x)
            texts.append(shown if x is not None else "")
            hovers.append(
                hover.format(
                    candidate=names[i],
                    share=shown,
                    counted=cell["national_electoral_votes_counted"],
                    appointed=cell["national_electoral_denominator"],
                    votes=cell["national_pv_votes"],
                )
            )
            if x is None:
                label, hover_cell = _marker(field, shown)
                no_figure = no_figure or label == labels.C1_NO_FIGURE
                marks.append(
                    (
                        i + offsets[field],
                        label,
                        labels.C1_NO_FIGURE_HOVER.format(
                            candidate=names[i], cell=hover_cell
                        ),
                        f"{slugs[i]}/{field}",
                    )
                )
        marker: dict[str, Any] = {"color": color}
        if field == "pv_share":
            marker["pattern"] = {
                "shape": "/",
                "fillmode": "overlay",
                "fgcolor": "var(--page)",
            }
        bars.append(
            {
                "type": "bar",
                "orientation": "h",
                "name": labels.LABELS[field],
                "offsetgroup": field,
                "ids": slugs,
                "x": xs,
                "y": positions,
                "text": texts,
                "textposition": "outside",
                "textfont": {"color": "var(--text)"},
                "cliponaxis": False,
                "marker": marker,
                "hovertext": hovers,
                "hovertemplate": "%{hovertext}<extra></extra>",
                "showlegend": has_popular_vote,
            }
        )
    data: list[dict[str, Any]] = list(bars)
    if marks:
        data.append(
            {
                "type": "scatter",
                "mode": "markers+text",
                "name": labels.C1_NO_FIGURE_SERIES,
                "showlegend": False,
                "ids": [mark[3] for mark in marks],
                "x": [0] * len(marks),
                "y": [mark[0] for mark in marks],
                "text": [mark[1] for mark in marks],
                "textposition": "middle right",
                "textfont": {"color": "var(--text)"},
                "cliponaxis": False,
                "marker": {"symbol": "x", "size": 10, "color": "var(--text)"},
                "hovertext": [mark[2] for mark in marks],
                "hovertemplate": "%{hovertext}<extra></extra>",
            }
        )
    title = labels.C1_TITLE if has_popular_vote else labels.C1_TITLE_NO_PV
    top = _TOP_PX[has_popular_vote]
    layout: dict[str, Any] = {
        "title": {"text": title.format(year=year)},
        "height": _ROW_PX * max(n, 1) + top + _BOTTOM_PX,
        "margin": {"t": top, "b": _BOTTOM_PX, "r": 56},
        "xaxis": {
            "range": [0, 1],
            "tickformat": ".0%",
            "dtick": 0.25,
            "title": {"text": labels.C1_X_AXIS},
        },
        "yaxis": {
            "tickvals": positions,
            "ticktext": names,
            "autorange": "reversed",
            "showgrid": False,
            "zeroline": False,
        },
        "shapes": [
            {
                "type": "line",
                "xref": "x",
                "x0": 0.5,
                "x1": 0.5,
                "yref": "paper",
                "y0": 0,
                "y1": 1,
                "layer": "below",
                "line": {"dash": "dash", "width": 2, "color": "var(--chart-reference)"},
            }
        ],
        "annotations": [
            {
                "text": labels.C1_MAJORITY_LINE,
                "xref": "x",
                "x": 0.5,
                "yref": "paper",
                "y": 1,
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"color": "var(--text)", "size": 12},
            }
        ],
    }
    if has_popular_vote:
        layout["legend"] = {
            "orientation": "h",
            "yref": "container",
            "y": 1,
            "yanchor": "top",
            "x": 0,
            "xanchor": "left",
        }
    return {"data": data, "layout": layout}, no_figure


def _pv_window(coverage: dict[str, Any]) -> dict[str, Any]:
    """The popular-vote window as :data:`NO_PV_SENTENCE` and
    :data:`labels.C1_NO_PV_CAPTION` both write it: from ``coverage``, never a
    literal."""
    return {"first": coverage["pv_year_min"], "last": coverage["pv_year_max"]}


def _c1_caption(
    has_popular_vote: bool, no_figure: bool, year: int, coverage: dict[str, Any]
) -> str:
    """C1's caption (#433): what each share counts and what the line marks; in a year
    with popular votes, which bar is which and, where a marker is drawn, what it means;
    otherwise why no popular-vote share is drawn. ``components.chart`` adds the table
    pointer."""
    if has_popular_vote:
        parts = [
            labels.C1_BASES,
            labels.C1_MAJORITY_NOTE,
            labels.C1_LINE_EC_ONLY,
            labels.C1_ROW_ORDER,
        ]
        if no_figure:
            parts.append(labels.C1_NO_FIGURE_NOTE.format(label=labels.C1_NO_FIGURE))
    else:
        parts = [
            labels.C1_EC_BASIS,
            labels.C1_MAJORITY_NOTE,
            labels.C1_NO_PV_CAPTION.format(year=year, **_pv_window(coverage)),
        ]
    return " ".join(parts)


def _download(year: int, body: dict[str, Any]) -> export.Download:
    """T3's download: the file named for the view and the table, the provenance of the
    response its rows come from, and the overview's URL, which carries no filter."""
    return export.Download(
        filename=f"election-{year}-national.csv",
        name="the national results",
        provenance=body["meta"]["provenance"],
        view_url=export.view_url(
            CANONICAL_HOST, election_view.path(year, election_view.OVERVIEW), ""
        ),
    )


def _election(value: Any, year: int) -> dict[str, Any] | None:
    """The year's ``election`` block, ``None`` where the API serves none, or
    ``TypeError``.

    The API serves ``election: null`` on a build gap while the rows beside it stay
    correct, so a null is the panel's own unavailable state, never the page's. Any
    other shape, or a block naming another year (checked as
    :func:`explore.election_view.rows` checks a row's), is a malformed body.
    """
    if value is None:
        return None
    if not isinstance(value, dict) or election_view.row_year(value) != year:
        raise TypeError(f"/v1/elections/{year} carries no election block of that year")
    return value


def _panel_cells(block: dict[str, Any], year: int, coverage: Any) -> dict[str, str]:
    """Each panel field's cell. The Electoral College fields and ``pv_coverage`` exist
    for every year, so a null there names no cause; a null popular-vote or hybrid field
    outside the window (from ``coverage``) reads :data:`labels.NOT_APPLICABLE`, and a
    value is shown whatever the year."""
    applicable = labels.in_pv_window(year, coverage)
    determinative = block["ec_determinative"]
    return {
        "ec_winner": labels.winner(block["ec_winner"], True),
        "pv_winner": labels.winner(block["pv_winner"], applicable),
        "hybrid_winner": labels.winner(block["hybrid_winner"], applicable),
        "pv_flip": labels.flip(
            block["pv_flip"], "popular-vote", applicable, determinative=determinative
        ),
        "hybrid_flip": labels.flip(
            block["hybrid_flip"], "hybrid", applicable, determinative=determinative
        ),
        "ec_margin": labels.margin(block["ec_margin"], True),
        "pv_margin": labels.margin(block["pv_margin"], applicable),
        "hybrid_margin": labels.margin(block["hybrid_margin"], applicable),
        "ec_determinative": labels.ec_majority(determinative),
        "pv_coverage": labels.share_cell(block["pv_coverage"]),
    }


def _panel(block: dict[str, Any] | None, year: int, coverage: Any) -> list[Any]:
    """The election panel (#308): each field's label (its raw name as the tooltip, as
    a column header's is) beside its cell, the hybrid's and the margins' help text,
    and a glossary. ``ec_winner``'s label follows ``ec_determinative`` (#355), from one
    label map the list and the glossary share."""
    heading = html.H2("Under each method")
    if block is None:
        return [
            heading,
            html.P(PANEL_UNAVAILABLE, id=PANEL_UNAVAILABLE_ID, className="note"),
        ]
    cells = _panel_cells(block, year, coverage)
    shown = {field: labels.LABELS[field] for field in PANEL_FIELDS} | {
        "ec_winner": labels.ec_winner_label(block["ec_determinative"])
    }
    return [
        heading,
        html.Div(
            [
                html.Dl(
                    [
                        item
                        for field in PANEL_FIELDS
                        for item in (
                            html.Dt(shown[field], title=field),
                            labels.cell(cells[field], html.Dd),
                        )
                    ]
                ),
                html.P(labels.HYBRID_NOTE, className="note"),
                html.P(labels.MARGIN_NOTE, className="note"),
                labels.glossary(PANEL_FIELDS, "Field names", shown),
            ],
            id=PANEL_ID,
            className="panel",
        ),
    ]


def render(
    body: dict[str, Any],
    index_row: dict[str, Any],
    around: election_view.Neighbours,
) -> html.Div:
    """The overview for one ``/v1/elections/{year}`` response, the year's row of
    ``/v1/elections`` (read through the same view) and the year's served neighbours.
    The response's ``election`` key is required, though its value may be null
    (:func:`_election`). Its state rows are checked though not shown, so a malformed
    body degrades here as on the states page.

    It builds the page's heading and lede too, after the earlier and later links, so
    the links come before the ``H1`` (#464); :func:`layout` builds them only for the
    not-found and degraded states, which have no links."""
    provenance = body["meta"]["provenance"]
    coverage = provenance["coverage"]
    # The popular-vote window, checked once before any cell reads it, whatever the
    # ``election`` block holds: two years, the first no later than the last (#308).
    query.year_span(coverage["pv_year_min"], coverage["pv_year_max"])
    year = election_view.row_year(index_row)
    if year is None:
        raise TypeError("the index row names no year")
    source = f"/v1/elections/{year}"
    election_view.rows(body["data"], year, "state rows", source)
    summary = election_view.rows(body["summary"], year, "candidates", source)
    block = _election(body["election"], year)
    has_popular_vote = index_row["has_popular_vote"] is True
    nation: list[Any] = [html.H2("National results")]
    if not has_popular_vote:
        nation.append(
            html.P(
                NO_PV_SENTENCE.format(year=year, **_pv_window(coverage)),
                id=NO_PV_ID,
                className="note",
            )
        )
    cells = [_nation_cells(row, has_popular_vote) for row in summary]
    by_row = {id(row): row_cells for row, row_cells in zip(summary, cells, strict=True)}
    figure, no_figure = _c1_figure(summary, cells, has_popular_vote, year)
    nation += [
        components.chart(
            C1_ID,
            figure,
            NATION_TABLE_ID,
            _c1_caption(has_popular_vote, no_figure, year, coverage),
        ),
        *components.table(
            summary,
            lambda r: _nation_row(r, by_row[id(r)]),
            NATION_FIELDS,
            NATION_TABLE_ID,
            _download(year, body),
            extra=NATION_EXTRA,
            notes=(
                labels.PARTY_NOTE,
                labels.PARTY_NULL_NOTE,
                labels.HYBRID_NOTE,
            ),
        ),
        *labels.party_notes(summary),
        labels.glossary(NATION_GLOSSARY),
    ]
    return html.Div(
        [
            *election_view.neighbor_nav(around, election_view.OVERVIEW),
            html.H1(HEADING.format(year=year)),
            html.P(LEDE, className="lede"),
            election_view.section_nav(year, election_view.OVERVIEW),
            *_panel(block, year, coverage),
            *nation,
            components.provenance_footer(provenance),
        ],
        id=PAGE_ID,
    )


def layout(year: Any = None, **_params: Any) -> html.Div:
    """The overview. On success, :func:`render`'s body is the whole page: it holds the
    links, then the heading, the lede and the section links (#464, #465). The
    not-found and degraded states get their heading here, heading first, and the
    degraded state its lede. Query keys are ignored: the overview reads no filter."""
    heading = "Election"
    lede: str | None = LEDE
    try:
        with api.CLIENT.view() as view:
            # Validated from the prefetched index before it is formatted (#312).
            if not api.accepted(view.get, VALIDATE, {"year": year}):
                heading, lede = labels.ELECTION_NOT_FOUND_HEADING, None
                content = election_view.not_found(NOT_FOUND_ID)
            else:
                body = view.get(f"/v1/elections/{year}")
                index = view.get(api.ELECTIONS_PATH)
                return render(
                    body,
                    election_view.index_row(index, year),
                    election_view.neighbours(index, int(year)),
                )
    except (api.ApiUnavailable, KeyError, TypeError):
        content = components.unavailable()
    lead = [] if lede is None else [html.P(lede, className="lede")]
    return html.Div([html.H1(heading), *lead, content])
