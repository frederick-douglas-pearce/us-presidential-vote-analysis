"""View pieces every page shares: the provenance footer, the degraded state (#306), the
year-range slider every year-filtered table uses (#279), the candidate history's
single-choice year control (#331), the linked state and candidate cells (#279, #331),
the table itself with its CSV download (#309), the theme control and the id of the
store holding the theme in effect (#359), which charts read (#432), the site
navigation (#448), and the chart builder (#432).

Pure functions of what a page already read, so they read no API: a page reads through
its own render-scoped view and hands them what it read. The one side effect is the
chart builder's error log when a figure breaks the chart rules and is not drawn (#467,
D095).
``TestSharedPieces.test_the_shared_modules_read_no_api`` (in
``test_dashboard_elections.py``) checks that this module imports nothing from
``explore`` but the other shared modules, and names no ``api`` or ``CLIENT``.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Sequence
from typing import Any

from dash import dcc, html

from explore import charts, export, labels, query

log = logging.getLogger(__name__)

#: How many of a figure's problems the not-drawn log line lists (#467): a problem can
#: repr a served value, and one per row on C3 would be 51.
LOGGED_PROBLEMS = 3

#: The id of the theme toggle's group (#359, #447), in ``app.layout`` on every page.
THEME_CONTROL_ID = "theme-control"

#: Each theme button's id, keyed by its choice (#447): the one source for the layout,
#: the theme callback's inputs and outputs, its id-to-choice map, and the selectors in
#: ``style.css`` that show the selected position (pinned by
#: ``test_the_selected_rules_name_exactly_the_button_ids``). The ids are static, so the
#: toggle renders once per document.
THEME_BUTTON_IDS: dict[str, str] = {
    value: f"theme-{value}" for value in labels.THEME_CHOICES
}

#: The id of the ``dcc.Store`` holding the theme in effect (#359): ``"light"`` or
#: ``"dark"``, never the reader's choice, which can also be Auto. A chart's callback
#: takes it as an input to re-template without a reload (#432), on the terms of the
#: store's contract in ``dashboard/CLAUDE.md`` (the ``app.py`` bullet), its one
#: statement.
THEME_STORE_ID = "theme-in-effect"

#: The id of the paragraph carrying the snapshot version.
SNAPSHOT_ID = "snapshot-version"

#: The id of the footer's list of sources.
PROVENANCE_ID = "provenance"

#: The four sources, in display order: what each supplies, and the provenance keys
#: naming it and its license. The CSV preamble names the same triples (#309); the
#: fourth, parties the National Archives does not print, arrived with #389.
SOURCES: tuple[tuple[str, str, str, str], ...] = (
    export.EC_SOURCE,
    export.PV_SOURCE,
    export.CENSUS_SOURCE,
    export.USGOV_SOURCE,
)

#: The degraded state's sentence. ``scripts/probe_dashboard.sh`` greps the routed root
#: page for "isn't responding", so the wording is load-bearing.
UNAVAILABLE_MESSAGE = (
    "The election data service isn't responding right now, so there is nothing to "
    "show yet. Please try again in a minute."
)


def provenance_footer(provenance: dict[str, Any]) -> html.Footer:
    """Each source named with its license linked, and the snapshot version.

    Built from a response's ``provenance`` (``/v1/meta``'s, or the ``meta.provenance``
    every other ``/v1`` response carries), so it cannot drift from the snapshot served.
    """
    return html.Footer(
        [
            html.H2("Where the data comes from"),
            html.Ul(
                [
                    html.Li(
                        [
                            html.Span(f"{label}: ", className="label"),
                            f"{provenance[name]} (",
                            # str(): a value of an unexpected type renders as text,
                            # rather than failing in Dash's serializer, outside the
                            # page layout's try.
                            html.A(str(provenance[lic]), href=str(provenance[url])),
                            ")",
                        ]
                    )
                    for label, name, lic, url in SOURCES
                ],
                id=PROVENANCE_ID,
            ),
            html.P(
                ["Data version ", html.Code(str(provenance["snapshot_version"]))],
                className="snapshot",
                id=SNAPSHOT_ID,
            ),
        ],
        className="provenance-footer",
    )


def unavailable() -> html.Div:
    """The degraded state: a plain sentence, never an exception or a blank page."""
    return html.Div(
        html.P(UNAVAILABLE_MESSAGE), className="unavailable", id="unavailable"
    )


#: Years between slider labels; an interior label nearer an end than half of this is
#: dropped, so the end labels never run into it on a phone.
MARK_STEP = 40


def year_marks(first: int, last: int) -> dict[int, str]:
    """A range slider's labels: both ends, and every :data:`MARK_STEP` years between."""
    interior = range((first // MARK_STEP + 1) * MARK_STEP, last, MARK_STEP)
    keep = [y for y in interior if min(y - first, last - y) >= MARK_STEP // 2]
    return {year: str(year) for year in sorted({first, last, *keep})}


def year_slider(
    slider_id: str, first: int, last: int, chosen: tuple[int, int]
) -> dcc.RangeSlider:
    """The year-range control over a served span ``first``–``last``.

    No ``persistence``: it would override the URL, which is where the range lives.
    """
    return dcc.RangeSlider(
        id=slider_id,
        min=first,
        max=last,
        step=1,
        value=list(chosen),
        allowCross=False,
        allow_direct_input=False,
        marks=year_marks(first, last),
        tooltip={"placement": "bottom"},
    )


#: The value of :func:`year_buttons`' first option, every year: never a year, and never
#: shown (a radio item renders its label, not its value).
ALL_YEARS_VALUE = ""


def year_buttons(
    control_id: str,
    legend: str,
    all_label: str,
    years: Sequence[int],
    chosen: int | None,
    *,
    hidden: bool = False,
) -> html.Fieldset:
    """A single-choice year control (#331): ``all_label`` first, then one button per
    year, as an inline radio group named by ``legend``.

    ``chosen`` is the one year applied, or ``None`` for every year. With ``hidden`` the
    group is still rendered, so a page's one filter callback keeps all its inputs, but
    not shown. No ``persistence``: it would override the URL, which is where the year
    lives.
    """
    return html.Fieldset(
        [
            html.Legend(legend, className="label"),
            dcc.RadioItems(
                id=control_id,
                options=[
                    {"label": all_label, "value": ALL_YEARS_VALUE},
                    *({"label": str(year), "value": str(year)} for year in years),
                ],
                value=ALL_YEARS_VALUE if chosen is None else str(chosen),
                inline=True,
                className="year-buttons",
            ),
        ],
        className="filter",
        hidden=hidden,
    )


def theme_control() -> html.Div:
    """The theme toggle (#359, #447): one button per :data:`labels.THEME_CHOICES`, in
    the order Dark, Auto, Light, in a group named by :data:`labels.THEME_CONTROL`.

    Each button's accessible name is its choice's text, visually hidden inside it; its
    icon is decorative and hidden from assistive technology, and its tooltip is
    :data:`labels.THEME_TITLES`. ``aria-pressed`` exposes the selected position: Auto
    here, as the strings ``"true"`` and ``"false"``; the theme callback in ``app.py``
    corrects it from ``<html data-theme>`` on its first call. The visible selection is
    drawn by ``style.css`` from ``<html data-theme>`` itself, which the head script sets
    before first paint, so it is right on the first frame.

    Buttons with ``aria-pressed``, not a radio group: ``dash.html`` has no ``Input``,
    and ``dcc.RadioItems`` renders an unnamed ``role=listbox`` (#444), so a radio group
    would need hand-written arrow-key handling in the inline callback (architect ruling,
    #447). Accepted residuals: three Tab stops rather than one; activating the
    pressed button again leaves it pressed; and until the theme callback's first call,
    about one render after the header mounts, assistive technology hears Auto as
    pressed even where a saved choice is already applied and visibly selected (owner
    decision, #447's review: leaving ``aria-pressed`` off until then would change the
    buttons' role mid-load, and telling the server the choice would break "the theme
    never reaches the server"). The ids are static
    (:data:`THEME_BUTTON_IDS`), so the toggle renders once per document: a navigation
    bar (#448) places this one and never a copy.
    """
    buttons = []
    for value, label in labels.THEME_CHOICES.items():
        # aria-* props have no Python keyword: a typed dict, as pages/election.py does.
        hidden: dict[str, Any] = {"aria-hidden": "true"}
        pressed: dict[str, Any] = {
            "aria-pressed": "true" if value == labels.THEME_AUTO else "false"
        }
        buttons.append(
            html.Button(
                [
                    html.Span(className=f"theme-icon theme-icon-{value}", **hidden),
                    html.Span(label, className="visually-hidden"),
                ],
                id=THEME_BUTTON_IDS[value],
                type="button",
                title=labels.THEME_TITLES[value],
                **pressed,
            )
        )
    named: dict[str, Any] = {"aria-label": labels.THEME_CONTROL}
    return html.Div(
        buttons, id=THEME_CONTROL_ID, role="group", className="theme-control", **named
    )


#: The id of the site navigation (#448), the ``nav`` landmark in the site header.
SITE_NAV_ID = "site-nav"

#: The site navigation's in-app links (#448), in order: each link's key (what a page's
#: ``nav=`` may name in ``dash.register_page``), its id and its path, which
#: :func:`site_nav`, app.py's current-page table and its callback all read. The order,
#: the labels and the site-name link's form are :func:`site_nav`'s own;
#: ``test_in_app_links_are_dcc_links_to_their_paths`` (``test_dashboard_nav.py``) fails
#: if the bar and this table diverge. The ids are static: the bar renders once per
#: document, in ``app.layout``.
NAV_LINKS: dict[str, tuple[str, str]] = {
    "home": ("nav-home", "/"),
    "elections": ("nav-elections", "/elections"),
    "states": ("nav-states", "/states"),
}

#: Each in-app link's key, mapped to its id (#448): the one projection of
#: :data:`NAV_LINKS` the callback and the tests read.
NAV_LINK_IDS: dict[str, str] = {key: link_id for key, (link_id, _) in NAV_LINKS.items()}

#: The id of the API docs link, the bar's one link off this site (#448).
NAV_API_DOCS_ID = "nav-api-docs"


def site_nav(docs_href: str) -> html.Nav:
    """The site navigation (#448): the site name, linked home, then Elections, States
    and API docs, as the ``nav`` landmark's direct children.

    ``docs_href`` is the API's ``/docs`` address, which app.py builds from
    ``config.API_BASE``: this module imports nothing from ``explore`` but the shared
    modules. The bar reads no data. The in-app links are ``dcc.Link``, so they navigate
    client-side; API docs is an ordinary same-tab link that the dashboard never fetches.
    ``dcc.Link`` renders no ``aria-*`` attribute, so the current-page marker
    (``aria-current``) is written onto the links in the browser by app.py's
    ``NAV_CALLBACK``, which reports the link it marked in the nav's ``data-current``.
    The layout renders no ``data-current``, so its presence shows the callback ran.
    The site name's accessible name is the full name at every width: the short form is
    always shown and the rest is visually hidden on a narrow screen, never
    ``display: none`` (WCAG 2.5.3). The theme toggle is the header's next child, not
    part of this landmark, which holds only links.
    """
    home, elections, states = (NAV_LINKS[k] for k in ("home", "elections", "states"))
    named: dict[str, Any] = {"aria-label": labels.SITE_NAV_LABEL}
    return html.Nav(
        [
            dcc.Link(
                # One inline span, so the link (a flex container) has one item and the
                # space that opens the rest of the name is kept, not trimmed.
                html.Span(
                    [
                        labels.SITE_NAME_SHORT,
                        html.Span(labels.SITE_NAME_REST, className="site-name-rest"),
                    ]
                ),
                href=home[1],
                id=home[0],
                className="site-name",
            ),
            dcc.Link(labels.NAV_ELECTIONS, href=elections[1], id=elections[0]),
            dcc.Link(labels.NAV_STATES, href=states[1], id=states[0]),
            html.A(
                labels.NAV_API_DOCS,
                href=docs_href,
                id=NAV_API_DOCS_ID,
                title=labels.NAV_API_DOCS_TITLE,
            ),
        ],
        id=SITE_NAV_ID,
        className="site-nav",
        **named,
    )


def state_cell(row: dict[str, Any]) -> html.Td:
    """The state's name, linked to its history (#279) when its code is a USPS code."""
    usps = row["state_usps"]
    if isinstance(usps, str) and query.USPS_RE.fullmatch(usps):
        return html.Td(dcc.Link(str(row["state"]), href=f"/state/{usps}"))
    return html.Td(str(row["state"]))


def candidate_cell(row: dict[str, Any]) -> html.Td:
    """The candidate's name, linked to their history (#331) when the row's slug is a
    slug and the name is text with something in it (an empty link is invisible).

    A slug of any other type is text too: :func:`explore.query.is_slug` takes a
    ``str``, so a null slug must not reach it, or a page that renders today degrades.
    """
    slug, name = row["candidate_slug"], row["candidate"]
    if isinstance(slug, str) and query.is_slug(slug) and labels.has_text(name):
        return html.Td(dcc.Link(name, href=f"/candidate/{slug}"))
    return html.Td(str(name))


#: A table's sentence when its filters leave no rows.
NO_ROWS = "No rows match these filters."


def table(
    rows: Sequence[dict[str, Any]],
    render_row: Callable[[dict[str, Any]], html.Tr],
    fields: tuple[str, ...],
    table_id: str,
    download: export.Download,
    *,
    extra: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    empty: str = NO_ROWS,
) -> list[Any]:
    """A table, its CSV download and its notes (#309).

    Every table goes through here: ``TestEveryTable`` in ``test_dashboard_export.py``
    records each call while rendering every registered page and fails a rendered table
    it did not build. The body and the CSV are built from the one list ``rows``, so the
    file holds exactly the rows the table shows, in the same order. The CSV's columns
    are the table's ``fields`` in display order, then ``extra`` (the count reason a cell
    shows, the party note the page shows under the table, the party's per-row source
    (#389: per-row provenance, the one ``extra`` column that is neither shown nor a
    key, so a reader can tell which rows the curated source supplies), and the keys a
    filter or another year needs, which the table shows only inside a cell or not at
    all). ``notes`` are shown under the table and written into
    the file's preamble, so what they explain is explained in both. With no rows, there
    is no table and nothing to download: ``empty`` says so. The link is the scroll
    box's next sibling, outside it, so it never scrolls away with the table.
    """
    shown = [html.P(note, className="note") for note in notes]
    if not rows:
        return [html.P(empty, className="empty"), *shown]
    text = export.csv_text((*fields, *extra), rows, download, notes)
    return [
        # Wider than a phone: the table scrolls sideways inside its box, the page never.
        html.Div(
            html.Table(
                [
                    html.Thead(html.Tr([labels.header(field) for field in fields])),
                    html.Tbody([render_row(row) for row in rows]),
                ],
                id=table_id,
            ),
            className="table-scroll",
        ),
        export.link(table_id, download, text),
        *shown,
    ]


def chart(
    chart_id: str, figure: dict[str, Any], table_id: str, caption: str
) -> html.Figure:
    """A chart (#432): the one way to build one, as :func:`table` is for tables.

    ``chart_id`` is a live ID in :data:`explore.charts.CHARTS`, read at call time, and
    ``table_id`` its registered companion table. ``figure`` is a plain Plotly figure
    dict that passes :func:`explore.charts.figure_problems` (colors only as token
    references, its own hover text, series told apart by more than color) and carries
    its chart title, plain text, in ``layout.title.text``. ``caption`` is the chart's
    caption, which may state a finding.

    It renders an HTML ``figure`` with the chart's DOM id (``c1``, also a fragment
    link): the chart title as page text (a paragraph, since a chart cannot know the
    page's outline), so it shows and wraps when plotly.js cannot load; the chart's
    mount point, a ``role="img"`` wrapper named by that title, which hides the
    drawing's SVG from assistive technology; the store holding the unresolved figure;
    and the caption, ending with :data:`labels.CHART_TABLE_POINTER`, a link to the
    companion table. The mount point is rendered empty, never with a ``dcc.Graph``
    (#452): ``charts.CHART_MOUNT_CALLBACK`` puts the graph in it, hidden and with no
    figure, only once plotly.js has loaded, and ``charts.CHART_CALLBACK`` then draws it
    in the theme in effect and shows it, so it never flashes plotly's own colors and a
    blocked CDN leaves the mount point empty, with no loop.

    A figure that :func:`explore.charts.figure_problems` refuses is **not drawn**
    (#467, D095): served data can reach those rules (a name, a value), so the chart
    must cost only itself. It is logged at error level, naming the chart, its page and
    its problems, and the figure is returned with its title and caption but no mount
    point and no store, so no callback runs for it and plotly.js is not fetched for it;
    the page keeps its tables and its other charts. The unit suite fails on that log
    line (the unit suite's ``no_undeclared_chart_failure``, D095). An unregistered or
    retired ID, another table, an empty caption or a title that is not plain text
    raises ``ValueError``: only a code change reaches those, so they are a page's bug,
    never a reader's input.
    """
    row = charts.CHARTS.get(chart_id)
    if row is None or row.retired:
        raise ValueError(f"{chart_id!r} is not a live registered chart")
    if table_id != row.table:
        raise ValueError(f"{chart_id}'s companion table is {row.table!r}")
    if not labels.has_text(caption):
        raise ValueError(f"{chart_id} has no caption")
    source = copy.deepcopy(figure)
    layout = source.get("layout") if isinstance(source, dict) else None
    title = layout.pop("title", None) if isinstance(layout, dict) else None
    text = title.get("text") if isinstance(title, dict) else None
    if not (isinstance(text, str) and labels.has_text(text)) or "<" in text:
        raise ValueError(f"{chart_id} has no plain-text chart title")
    dom = charts.dom_id(chart_id)
    title_id = f"{dom}-title"
    named: dict[str, Any] = {"aria-labelledby": title_id}
    heading = html.P(text, id=title_id, className="chart-title")
    pointer = html.Figcaption(
        [caption, " ", html.A(labels.CHART_TABLE_POINTER, href=f"#{table_id}"), "."]
    )
    problems = charts.figure_problems(source)
    if problems:
        log.error(
            "%s on %s not drawn: %d figure problem(s): %r",
            chart_id,
            row.page,
            len(problems),
            problems[:LOGGED_PROBLEMS],
            extra={"chart_id": chart_id},
        )
        return html.Figure([heading, pointer], id=dom, className="chart")
    return html.Figure(
        [
            heading,
            html.Div(
                id=charts.mount_id(dom),
                role="img",
                className="chart-graph",
                **named,
            ),
            dcc.Store(id=charts.source_id(dom), data=source),
            pointer,
        ],
        id=dom,
        className="chart",
    )
