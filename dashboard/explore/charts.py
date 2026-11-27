"""The chart foundation (#432, E14-S3): the chart registry, the one Plotly template,
the shared config, the rules every chart's figure follows, and the clientside callback
that draws each chart in the theme in effect.

No chart is built here: ``components.chart`` builds every one, from a figure a page
passes it, and checks the figure against :func:`figure_problems`. A figure is a plain
dict (``plotly`` is a banned import, D070(b)'s guard), and it names no color: each color
is a ``var(--token)`` reference to a token in ``style.css``, which
:data:`CHART_CALLBACK` resolves in the browser, so ``style.css`` stays the one source of
every color.

:func:`figure_problems` is total (#484, D099): it returns problems and never raises.
It refuses, alone, a figure that is no JSON value of bounded depth before any other
check reads it, and it refuses a slot holding a kind its check does not expect
(:data:`SLOT_KINDS`); each check guards the kinds it reads, since that refusal gates
none of them.

No ``dcc.Graph`` is ever in a server-rendered layout (#452, D088): ``components.chart``
renders an empty mount point, and :data:`CHART_MOUNT_CALLBACK` puts the graph in it only
once plotly.js has loaded, so dcc's own loader never appends a script or fetches, and a
blocked CDN cannot make Dash loop.

A shared module: it imports nothing from ``explore`` and reads no API
(``TestSharedPieces`` in ``test_dashboard_elections.py``).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator, Mapping
from itertools import combinations
from typing import Any, NamedTuple

from dash import dcc


class Chart(NamedTuple):
    """One registered chart: the path template of the page it renders on, the DOM id of
    its companion table (the table on that page holding its values), whether its ID
    is retired, whether its value axis writes its numbers short
    (:data:`SHORT_TICKFORMAT`; C5, #596, D110, and C10, #582, D113, the two exceptions
    to the numbers-in-full rule), and whether it is the binned map (``map_bins``,
    D121(b), #639: the one chart whose figure is a choropleth, :func:`map_problems`).
    A retired ID is never built and never reused."""

    page: str
    table: str
    retired: bool = False
    short_value_ticks: bool = False
    map_bins: bool = False


#: A chart ID: ``C1``, ``C2``, …, issued in order of story filing.
ID_RE = re.compile(r"C[1-9][0-9]*")

#: The chart registry (#432): every chart ID ever registered, live or retired. An ID is
#: issued when its chart story registers it, is never renumbered or reused, and stays
#: here once retired. C1 (#433) was the first, C3 (#435) the second, C2 (#434) the
#: third, C4 and C5 (#436) the fourth and fifth, C7 (#560) the sixth, C10 (#582) the
#: seventh and C9 (#563) the eighth: IDs follow the stories' filing order, and C6 (#550)
#: and C8 (#561) are filed but not yet registered.
#: ``components.chart`` reads it by attribute at call time. ``ISSUED``, a hand-written
#: literal of every issued ID with its whole row, must equal this
#: (``TestChartRegistry`` in ``test_dashboard_charts.py`` reads it), and
#: ``test_every_row_is_well_formed_and_on_a_registered_page`` checks each row.
CHARTS: Mapping[str, Chart] = {
    # Each candidate's electoral share beside their popular-vote share, with the
    # majority line, on the one-election view, beside T3 (#433).
    "C1": Chart("/election/<year>", "election-nation"),
    # Every state's people per electoral vote, never narrowed by the page's state
    # filter, on an election's People per electoral vote page, beside T6 (#435, D093).
    "C3": Chart("/election/<year>/per-capita", "election-per-capita"),
    # Each election's Electoral College leader's electoral share against the majority
    # line, on its own page, narrowed by its year filters (#596, D110), beside its own
    # companion table (#434, D096; page since #562, D107).
    "C2": Chart("/elections/majority", "elections-leader-table"),
    # Electors appointed and the total popular vote in each election, all states, on
    # their own page, narrowed by its year filters (#596, D110), beside one companion
    # table they share (#436, D100; all states only since #562, D107). C5's value axis
    # writes its numbers short (#596, D110).
    "C4": Chart("/elections/over-time", "elections-over-time-table"),
    "C5": Chart(
        "/elections/over-time", "elections-over-time-table", short_value_ticks=True
    ),
    # One state's electors appointed in each election, on the state's history page
    # (#560, D106), above C10 and the one companion table the two share (#618, D117);
    # the page's Years filter narrows all three together (#620, D119).
    "C7": Chart("/state/<usps>", "state-electors"),
    # The same state's total popular vote in each election, directly below C7 on its
    # page, sharing C7's companion table (#618, D117) and narrowed with it (#620,
    # D119); its value axis writes its numbers short, as C5's does (#582, D113).
    "C10": Chart("/state/<usps>", "state-electors", short_value_ticks=True),
    # How many candidates received electoral votes in each election, on the list of
    # elections, narrowed by its year filters (D110), above T1, its companion table
    # (#563, D116).
    "C9": Chart("/elections", "elections-table"),
}


def registry_problems(registry: Mapping[str, Chart]) -> list[str]:
    """What is wrong with ``registry``: an ID that is not ``C<n>``, or a row that is not
    a :class:`Chart` naming a page and a table."""
    problems = []
    for chart_id, chart in registry.items():
        if not (isinstance(chart_id, str) and ID_RE.fullmatch(chart_id)):
            problems.append(f"{chart_id!r}: not a chart ID")
        if not (
            isinstance(chart, Chart)
            and isinstance(chart.page, str)
            and chart.page.startswith("/")
            and isinstance(chart.table, str)
            and chart.table
            and isinstance(chart.retired, bool)
            and isinstance(chart.short_value_ticks, bool)
            and isinstance(chart.map_bins, bool)
        ):
            problems.append(f"{chart_id!r}: not a chart row")
    return problems


def escaped(text: str) -> str:
    """Served text as plotly's pseudo-HTML shows it as written (#433, #435): a name
    holding ``<`` or ``&`` is drawn, never read as markup, and ``(`` is written as an
    entity, so no served string can spell a ``var(--token)`` reference, which
    :func:`color_problems` refuses outside a color and :data:`CHART_CALLBACK` would
    resolve. plotly draws each entity as its character."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("(", "&#40;")
    )


def dom_id(chart_id: str) -> str:
    """The chart's element id, its ID in lower case (``c1``): also a fragment link
    (``/elections/majority#c2``), which never reaches the server."""
    return chart_id.lower()


#: The pattern-matching id types of a chart's graph and of the store holding its
#: unresolved figure, each keyed by the chart's DOM id.
GRAPH_TYPE = "explore-chart-graph"
SOURCE_TYPE = "explore-chart-source"


def graph_id(dom: Any) -> dict[str, Any]:
    """A chart's graph id; ``dom`` is its DOM id, or Dash's ``MATCH`` in a callback."""
    return {"type": GRAPH_TYPE, "chart": dom}


def source_id(dom: Any) -> dict[str, Any]:
    """The id of a chart's source store, holding its unresolved figure."""
    return {"type": SOURCE_TYPE, "chart": dom}


#: The pattern-matching id type of a chart's mount point (#452): the ``role="img"``
#: wrapper, rendered empty, that :data:`CHART_MOUNT_CALLBACK` puts the graph in.
MOUNT_TYPE = "explore-chart-mount"


def mount_id(dom: Any) -> dict[str, Any]:
    """The id of a chart's mount point, keyed by its DOM id (or ``MATCH``)."""
    return {"type": MOUNT_TYPE, "chart": dom}


#: A token reference, the only form a color takes in a figure or the template.
TOKEN_RE = re.compile(r"var\((--[a-z0-9-]+)\)")

#: The color attributes, whose values must be color-token references.
_COLOR_KEY_RE = re.compile(r".*(?:color|colors|colorway)")

#: The one non-color token a figure may name: the font stack, under ``family`` only,
#: which the page's text reads too.
FONT_TOKEN = "--font-body"

#: Color-scale attributes no chart may set, matched by key name at any depth and
#: refused on any value (#645, D121): each configures a color scale, which maps numbers
#: to colors that are no token, and some draw one, or a colorbar in plotly.js's default
#: colorscale (its ``hasColorscale``: ``showscale: true``, a numeric ``cmin`` and
#: ``cmax``, a ``colorscale``, a ``colorbar``). In plotly.js 4.1.1 they sit on a
#: ``scatter`` or ``bar`` trace's ``marker`` (``showscale`` and ``colorbar`` there
#: only) and ``marker.line``, on the layout (``coloraxis``, ``coloraxis2``, …, and
#: ``colorscale``), and in a scatter's ``fillgradient``; ``zmid`` and ``zauto`` are on
#: no allowed trace type, and are here so that every refusal D121(a) makes for the map
#: is in this one set. ``zmin`` and ``zmax`` are not, since the map sets them.
#: The one exception is the map's (#639, D121(b)): under ``map_bins``, while
#: ``data[0]`` is a choropleth (:func:`_is_map`), :data:`MAP_COLOR_PATHS` on its
#: ``data[0]`` only.
_REFUSED_KEY_RE = re.compile(
    r"(?:.*colorscale|showscale|colorbar|cauto|cmin|cmax|cmid|coloraxis\d*"
    r"|reversescale|fillgradient|zmid|zauto)"
)

#: The refused keys the map may set (#639, D121(b), the #645 amendment), each at
#: exactly this path on ``data[0]`` and only under ``map_bins``: the colorscale (its
#: stops, which inherit its key through :func:`_walk`, are skipped with it and checked
#: by :func:`map_problems`), the colorbar (its own keys are still checked, so its color
#: keys hold tokens) and ``showscale``.
MAP_COLOR_PATHS = ("data[0].colorscale", "data[0].colorbar", "data[0].showscale")

#: Where the map's colorscale sits: it and every path under it are skipped by
#: :func:`color_problems` under ``map_bins``, while ``data[0]`` is a choropleth
#: (:func:`_is_map`).
_MAP_COLORSCALE = MAP_COLOR_PATHS[0]

#: The one Plotly template every chart is drawn with (#432), in both palettes: its color
#: slots name tokens, which :data:`CHART_CALLBACK` resolves from the palette in effect,
#: so "the light template" and "the dark template" are this one resolved against each.
#: Its other values are the shared defaults: no drag or zoom, a legend that is only a
#: key (a click hides nothing), hover text for the nearest point only, numbers written
#: in full with thousands separators (never "80M" or "1.2B", as the tables write them),
#: and bars in groups with a gap on every side (``bargap`` between locations,
#: ``bargroupgap`` within one, never stacked or overlaid), so neighboring bars of
#: different series, whose tokens do not contrast with each other, are always parted by
#: the page's color (WCAG 1.4.11). C1 (#433, D091) made two of these rules: a hover or
#: text template names no number format (:func:`template_problems`), and no bar sets
#: its own ``width`` or ``offset``, which would defeat both gaps (:func:`bar_problems`).
#: Each measure's color token (#593, D109): electoral-vote-derived values red,
#: popular-vote-derived values blue, the hybrid score purple, on every chart. A
#: series takes its measure's token, never one by position.
EC_COLOR = "var(--chart-ec)"
PV_COLOR = "var(--chart-pv)"
HYBRID_COLOR = "var(--chart-hybrid)"

#: The map's bin colors (#639, D121(e)): one ramp of three per measure, bin 0 first,
#: the bins running from nearest the page to farthest from it. A metric derived from the
#: electoral allotment takes the red ramp, the count of popular votes held the blue
#: one. The tokens are the map's alone, never a series token, so a series color change
#: never moves a bin (owner, #639's plan gate). ``CHART_BINS`` in
#: ``test_dashboard_theme.py``, a hand-written literal, must equal this, and measures
#: each bin there.
MAP_RAMPS: tuple[tuple[str, ...], ...] = (
    ("var(--chart-bin-ec-1)", "var(--chart-bin-ec-2)", "var(--chart-bin-ec-3)"),
    ("var(--chart-bin-pv-1)", "var(--chart-bin-pv-2)", "var(--chart-bin-pv-3)"),
)

#: How many bins the map draws (D121(e): three for every metric).
MAP_BIN_COUNT = 3

#: The map's state borders (D121(c)): the trace's ``marker.line.color``, in the page's
#: color, since adjacent bins do not contrast with each other (WCAG 1.4.11);
#: ``test_dashboard_theme.py`` measures every bin against it.
MAP_BORDER = "var(--page)"


def map_colorscale(ramp: tuple[str, ...]) -> list[list[Any]]:
    """The stepwise colorscale that draws each of ``ramp``'s bins as one flat color
    (D121(a)): for bin ``b`` of ``k``, two stops at ``b / k`` and ``(b + 1) / k``, both
    its token. The one builder: :func:`map_problems` requires the map's colorscale to
    equal its output for one of :data:`MAP_RAMPS`, and the map is built from it."""
    k = len(ramp)
    return [
        [position / k, token] for b, token in enumerate(ramp) for position in (b, b + 1)
    ]


TEMPLATE: dict[str, Any] = {
    "layout": {
        "font": {"family": "var(--font-body)", "color": "var(--text)", "size": 14},
        "paper_bgcolor": "var(--page)",
        "plot_bgcolor": "var(--page)",
        "colorway": [EC_COLOR, PV_COLOR, HYBRID_COLOR],
        "hovermode": "closest",
        "dragmode": False,
        "barmode": "group",
        "bargap": 0.2,
        "bargroupgap": 0.15,
        "margin": {"l": 56, "r": 16, "t": 16, "b": 48},
        "xaxis": {
            "fixedrange": True,
            "automargin": True,
            "linecolor": "var(--chart-axis)",
            "tickcolor": "var(--chart-axis)",
            "gridcolor": "var(--chart-grid)",
            "zerolinecolor": "var(--chart-axis)",
            "tickfont": {"color": "var(--text-secondary)"},
            "title": {"font": {"color": "var(--text)"}},
            "separatethousands": True,
            "exponentformat": "none",
        },
        "yaxis": {
            "fixedrange": True,
            "automargin": True,
            "linecolor": "var(--chart-axis)",
            "tickcolor": "var(--chart-axis)",
            "gridcolor": "var(--chart-grid)",
            "zerolinecolor": "var(--chart-axis)",
            "tickfont": {"color": "var(--text-secondary)"},
            "title": {"font": {"color": "var(--text)"}},
            "separatethousands": True,
            "exponentformat": "none",
        },
        "legend": {
            "itemclick": False,
            "itemdoubleclick": False,
            "font": {"color": "var(--text)"},
        },
        "hoverlabel": {
            "bgcolor": "var(--surface)",
            "bordercolor": "var(--border)",
            "font": {"color": "var(--text)"},
        },
        # The map's geo subplot (#639, D121(c)): the lower 48 with Alaska and Hawaii
        # inset, at the resolution of the one outline file the dashboard serves
        # (usa_110m.json, D121(i)), on the page's color, never re-zoomed, with only the
        # states' outlines drawn (the file holds no other layer). A chart with no geo
        # trace draws no geo subplot, so the other charts never see it.
        "geo": {
            "scope": "usa",
            "projection": {"type": "albers usa"},
            "resolution": 110,
            "fitbounds": False,
            "bgcolor": "var(--page)",
            "showland": False,
            "showlakes": False,
            "showrivers": False,
            "showcountries": False,
            "showcoastlines": False,
            "showframe": False,
            "showocean": False,
            "showsubunits": True,
            "subunitcolor": "var(--chart-axis)",
        },
    },
}

#: The config every chart's graph takes, and no chart overrides: no plotly logo, no
#: scroll zoom, and no toolbar (owner, #432's plan gate: the companion table's CSV is
#: the data download), so no plotly.js text reaches a reader; resized with its box.
#: ``topojsonURL`` points a map's outline fetch at the dashboard's own assets, where
#: ``usa_110m.json`` (built from Natural Earth) is served, never at plotly's CDN
#: (D121(i)). The path is absolute, since a relative one would resolve under the page's
#: own path (``/state/TX/``); ``app.py`` refuses any prefix but ``/``.
CHART_CONFIG: dict[str, Any] = {
    "displaylogo": False,
    "scrollZoom": False,
    "displayModeBar": False,
    "responsive": True,
    "topojsonURL": "/assets/",
}

#: The template's defaults no figure may override (#432's review): plotly lets a
#: figure's own ``layout`` win over ``layout.template``, so a chart setting one of these
#: would bring back drag or zoom, a legend click that hides a series inside the
#: ``role="img"`` wrapper, plotly's own unified hover header, shortened numbers
#: ("80M"), or bars that touch. Layout keys, legend keys, and keys of every
#: ``xaxis``/``yaxis`` (``xaxis2`` too). A second legend (``legend2``) is refused
#: outright, since the template's legend does not reach it. A chart may still set its
#: margins, ``automargin`` and font size. ``TestTemplate`` checks each is set in
#: :data:`TEMPLATE`.
FIXED_LAYOUT_KEYS = ("hovermode", "dragmode", "barmode", "bargap", "bargroupgap")
FIXED_LEGEND_KEYS = ("itemclick", "itemdoubleclick")
FIXED_AXIS_KEYS = ("fixedrange", "exponentformat", "separatethousands")
#: Every key :data:`TEMPLATE` sets in the map's ``geo`` (#639, D121(c)). A figure sets
#: no ``layout.geo`` key at all (:func:`override_problems`); these are named as the
#: template's, and ``TestTemplate`` checks each is set there.
FIXED_GEO_KEYS = (
    "scope",
    "projection",
    "resolution",
    "fitbounds",
    "bgcolor",
    "showland",
    "showlakes",
    "showrivers",
    "showcountries",
    "showcoastlines",
    "showframe",
    "showocean",
    "showsubunits",
    "subunitcolor",
)

#: A d3 number format,
#: ``[[fill]align][sign][symbol][0][width][,][.precision][~][type]``, its type
#: captured. An axis ``tickformat`` may use only the types that write a number in
#: full (:data:`_FULL_TYPES`): every other type, and none at all (which d3 reads as
#: ``~g``), can shorten it or write an exponent ("80M", "8e+7"). A format starting
#: ``%`` is a date format, not a number one, and is left alone.
_D3_FORMAT_RE = re.compile(r"(?:.?[<>=^])?[-+( ]?[$#]?0?\d*,?(?:\.\d+)?~?([A-Za-z%]?)")
_FULL_TYPES = frozenset({"d", "f", "r", "%", "p"})
#: The one short format a chart may name, and only on ``layout.yaxis`` of a chart
#: whose registry row sets ``short_value_ticks`` (C5, #596, D110; C10, #582, D113):
#: d3's SI form with trailing zeros trimmed ("50M"). Page-written ``ticktext`` is not
#: checked for shortened numbers; it is wording, as row names are (D110's accepted
#: residual).
SHORT_TICKFORMAT = "~s"


def _shortens(tickformat: str) -> bool:
    if tickformat.startswith("%"):
        return False
    match = _D3_FORMAT_RE.fullmatch(tickformat)
    return match is None or match.group(1) not in _FULL_TYPES


#: A second or later legend, which the template's legend does not reach.
_EXTRA_LEGEND_RE = re.compile(r"legend\d+")

#: A second or later geo subplot, which the template's ``geo`` does not reach.
_EXTRA_GEO_RE = re.compile(r"geo\d+")

_AXIS_RE = re.compile(r"[xy]axis\d*")


#: How deep a figure may nest (#484, D099), in containers counted from the root: the
#: figure is 1, ``data`` 2, a trace 3, its ``marker`` 4 and a ``marker.pattern`` 5,
#: which is as deep as any chart's figure (and :data:`TEMPLATE`) nests; the map's
#: colorscale stops, ``marker.line`` and ``colorbar.title`` (#639) are at 5 too, since
#: :func:`map_problems` admits nothing under them but values. Every check
#: below recurses, and so does the ``copy.deepcopy`` in ``components.chart``, so
#: :func:`json_problems` refuses anything deeper before any of them runs.
MAX_DEPTH = 16

#: The largest integer a figure may hold (#484, D099): JavaScript's largest exact
#: integer, ``Number.MAX_SAFE_INTEGER``, since plotly.js reads every number as a double.
MAX_INTEGER = 2**53 - 1


def _child(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def json_problems(figure: Any) -> list[str]:
    """What keeps ``figure`` from being a JSON value of bounded depth (#484, D099): a
    key that is not a string; a value that is not an object, a list, a string, a finite
    number, a boolean or null (a tuple, a set, NaN and infinity are refused); an integer
    beyond :data:`MAX_INTEGER`, which plotly.js would round and which Python cannot
    write as text past a few thousand digits; and nesting deeper than
    :data:`MAX_DEPTH`. It walks with a stack of its own, never by recursion, and
    descends no further than the bound, so it ends on any input; a container shared or
    cycled into several places is walked once per path to it, so its time grows with
    the number of such paths, which the depth bound keeps finite but which each level
    of sharing multiplies (only code builds one; a parsed API body never shares). Its
    messages name a
    path and a type, never a value's ``repr``. Every other check assumes what this one
    checks: :func:`figure_problems` returns its problems alone, and
    ``components.chart`` runs it before it copies a figure."""
    problems: list[str] = []
    stack: list[tuple[str, Any, int]] = [("", figure, 1)]
    while stack:
        path, value, depth = stack.pop()
        if isinstance(value, (dict, list)):
            if depth > MAX_DEPTH:
                problems.append(f"{path or 'figure'}: nested deeper than {MAX_DEPTH}")
                continue
            inner: list[tuple[str, Any, int]] = []
            if isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(key, str):
                        inner.append((_child(path, key), item, depth + 1))
                    else:
                        problems.append(
                            f"{path or 'figure'}: {type(key).__name__} key,"
                            " not a string"
                        )
            else:
                inner = [
                    (f"{path}[{index}]", item, depth + 1)
                    for index, item in enumerate(value)
                ]
            stack.extend(reversed(inner))
        elif isinstance(value, float):
            if not math.isfinite(value):
                problems.append(f"{path or 'figure'}: not a finite number")
        elif isinstance(value, int) and not isinstance(value, bool):
            # Compared, never written as text, which raises past a few thousand digits.
            if abs(value) > MAX_INTEGER:
                problems.append(f"{path or 'figure'}: an integer beyond 2**53 - 1")
        elif not (value is None or isinstance(value, (str, bool))):
            problems.append(
                f"{path or 'figure'}: {type(value).__name__}, not a JSON value"
            )
    return problems


def _walk(value: Any, path: str = "", key: str = "") -> Iterator[tuple[str, str, Any]]:
    """Every ``(path, key, value)`` under ``value``, a figure or a part of one; a list's
    items carry the list's key (``colorway[0]``'s is ``colorway``). It recurses, so it
    is handed only what :func:`json_problems` accepts."""
    if isinstance(value, dict):
        for name, inner in value.items():
            here = f"{path}.{name}" if path else str(name)
            yield here, str(name), inner
            yield from _walk(inner, here, str(name))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            here = f"{path}[{index}]"
            yield here, key, inner
            yield from _walk(inner, here, key)


def _is_token(value: Any) -> bool:
    return isinstance(value, str) and TOKEN_RE.fullmatch(value) is not None


def _is_map(figure: Mapping[str, Any], map_bins: Any) -> bool:
    """Whether the map's exception applies (#639, D121(b)): the chart's registry row
    sets ``map_bins`` (only ``True``) and ``data[0]`` is a choropleth. The one statement
    of it, which :func:`trace_type_problems` and :func:`color_problems` both read."""
    data = figure.get("data")
    first = data[0] if isinstance(data, list) and data else None
    return (
        map_bins is True
        and isinstance(first, dict)
        and first.get("type") == "choropleth"
    )


def color_problems(figure: Mapping[str, Any], *, map_bins: bool = False) -> list[str]:
    """Where ``figure`` names a color that is not a token reference (#432).

    The allowlist: a key ending ``color``, ``colors`` or ``colorway`` holds a token
    reference other than :data:`FONT_TOKEN`, or (``colorway`` only) a list of them;
    ``family`` may hold only :data:`FONT_TOKEN`; no other string contains ``var(``; no
    key of :data:`_REFUSED_KEY_RE` (a key that configures a color scale or a
    colorbar, #645), on any value. A numeric or list ``color`` is refused, so a trace
    never colors its points one by one: color would then carry categories inside one
    trace, where :func:`color_only_pairs` cannot see it, and a number would pick a
    colorscale's color, which is no token. Whether a named color token exists in
    ``style.css`` is the tests' to check (this module reads no file):
    ``TestEveryChart`` for every rendered chart, ``TestTemplate`` for the template.

    With ``map_bins`` (the map's registry row, #639, D121(b); only ``True``) a refused
    key is admitted at exactly the paths :data:`MAP_COLOR_PATHS` names, and the
    colorscale's stops are skipped with it, :func:`map_problems` checking them; a
    colorbar's own keys are still read, and a refused key at any other path is still
    refused. The exception holds only while ``data[0]`` is a choropleth
    (:func:`_is_map`), the same test :func:`trace_type_problems` admits it by.
    """
    admitted = _is_map(figure, map_bins)
    problems = []
    for path, key, value in _walk(figure):
        if admitted and (
            path in MAP_COLOR_PATHS or path.startswith(f"{_MAP_COLORSCALE}[")
        ):
            continue
        if _REFUSED_KEY_RE.fullmatch(key):
            problems.append(f"{path}: no colorscale or colorbar")
        elif _COLOR_KEY_RE.fullmatch(key):
            if path.endswith("]"):
                continue  # an item of a color list: the list itself is checked
            tokens = value if key == "colorway" and isinstance(value, list) else [value]
            if not tokens or not all(
                _is_token(token) and token != f"var({FONT_TOKEN})" for token in tokens
            ):
                problems.append(f"{path}: {value!r} is not a color token reference")
        elif key == "family":
            if (
                isinstance(value, str)
                and "var(" in value
                and value != f"var({FONT_TOKEN})"
            ):
                problems.append(f"{path}: {value!r} is not the font token")
        elif isinstance(value, str) and "var(" in value:
            problems.append(f"{path}: a token reference outside a color")
    return problems


def tokens_named(figure: Mapping[str, Any]) -> set[str]:
    """Every token a figure or template names."""
    return {
        match.group(1)
        for _, _, value in _walk(figure)
        if isinstance(value, str)
        for match in [TOKEN_RE.fullmatch(value)]
        if match is not None
    }


#: The only markup plotly text may carry (#432's review): a line break, and the hover
#: box's ``<extra>`` part. Anything else (``<span style=…>``, ``<b>``, ``<a href>``)
#: is refused, so no color, emphasis or link enters through a string; a chart story
#: that needs one widens this with a ``ba`` spec.
_ALLOWED_MARKUP_RE = re.compile(r"<(?:br|extra|/extra)>")


def markup_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each string in ``figure`` carrying markup other than ``<br>`` and ``<extra>``."""
    return [
        f"{path}: markup in {value!r}"
        for path, _, value in _walk(figure)
        if isinstance(value, str) and "<" in _ALLOWED_MARKUP_RE.sub("", value)
    ]


def override_problems(
    figure: Mapping[str, Any], *, short_value_ticks: bool = False
) -> list[str]:
    """Each template default ``figure``'s own layout overrides (#432's review): the
    :data:`FIXED_LAYOUT_KEYS`, :data:`FIXED_LEGEND_KEYS` and :data:`FIXED_AXIS_KEYS`,
    a shortening axis ``tickformat``, and a second legend, in the layout or named by a
    trace. With ``short_value_ticks`` (a registry row's, #596) exactly
    :data:`SHORT_TICKFORMAT` on ``layout.yaxis`` is admitted; any other axis or short
    format is still refused. Only ``True`` admits it. And the map's geo (#639,
    D121(c)): every key a figure sets in ``layout.geo`` (none is needed, and one such as
    ``visible`` or ``subunitwidth`` would hide a no-figure state's outline), a second
    geo subplot, in the layout or named by a trace."""
    problems = []
    for index, trace in enumerate(figure.get("data") or []):
        if not isinstance(trace, dict):
            continue
        if trace.get("legend", "legend") != "legend":
            problems.append(
                f"data[{index}].legend: {trace['legend']!r}, not the template's legend"
            )
        if trace.get("geo", "geo") != "geo":
            problems.append(
                f"data[{index}].geo: {trace['geo']!r}, not the template's geo"
            )
    layout = figure.get("layout")
    if not isinstance(layout, dict):
        return problems
    problems += [
        f"layout.{key}: fixed by the template"
        for key in FIXED_LAYOUT_KEYS
        if key in layout
    ]
    problems += [
        f"layout.{key}: a second legend, which the template does not reach"
        for key in layout
        if _EXTRA_LEGEND_RE.fullmatch(key)
    ]
    problems += [
        f"layout.{key}: a second geo, which the template does not reach"
        for key in layout
        if _EXTRA_GEO_RE.fullmatch(key)
    ]
    geo = layout.get("geo")
    if isinstance(geo, dict):
        problems += [
            f"layout.geo.{key}: fixed by the template"
            if key in FIXED_GEO_KEYS
            else f"layout.geo.{key}: the map's geo is the template's"
            for key in geo
        ]
    legend = layout.get("legend")
    if isinstance(legend, dict):
        problems += [
            f"layout.legend.{key}: fixed by the template"
            for key in FIXED_LEGEND_KEYS
            if key in legend
        ]
    for name, axis in layout.items():
        if not (_AXIS_RE.fullmatch(name) and isinstance(axis, dict)):
            continue
        problems += [
            f"layout.{name}.{key}: fixed by the template"
            for key in FIXED_AXIS_KEYS
            if key in axis
        ]
        tickformat = axis.get("tickformat")
        admitted = (
            short_value_ticks is True
            and name == "yaxis"
            and tickformat == SHORT_TICKFORMAT
        )
        if isinstance(tickformat, str) and _shortens(tickformat) and not admitted:
            problems.append(
                f"layout.{name}.tickformat: {tickformat!r} shortens numbers"
            )
    return problems


def _mode(trace: Mapping[str, Any]) -> str:
    mode = trace.get("mode")
    return mode if isinstance(mode, str) else ""


def _placeholder_spans(text: str) -> Iterator[tuple[int, int]]:
    """Where ``text`` holds a ``%{…}`` placeholder, which a template writes and the
    reader never sees as written: each ``%{`` up to the first ``}`` after it, leftmost
    first and never overlapping, the matches of the pattern ``%\\{[^}]*\\}``. Linear
    (#484, D099): a ``%{`` with no ``}`` after it ends the scan, since no later one has
    a ``}`` after it either, where the pattern searched again from every ``%{`` to the
    end, so a long string of them took minutes."""
    start = 0
    while (begin := text.find("%{", start)) >= 0:
        end = text.find("}", begin + 2)
        if end < 0:
            return
        yield begin, end + 1
        start = end + 1


def _placeholders(text: str) -> list[str]:
    """Each placeholder in ``text`` (:func:`_placeholder_spans`)."""
    return [text[begin:end] for begin, end in _placeholder_spans(text)]


def _without_placeholders(text: str) -> str:
    """``text`` with every placeholder removed (:func:`_placeholder_spans`)."""
    parts, start = [], 0
    for begin, end in _placeholder_spans(text):
        parts.append(text[start:begin])
        start = end
    parts.append(text[start:])
    return "".join(parts)


def _drawn_text(trace: Mapping[str, Any]) -> Any:
    """The string that gives ``trace``'s drawn text (#433, D091): its ``texttemplate``
    when set, which plotly draws in place of ``text``, else its ``text``. Placeholders
    are not resolved, so a series named only through ``%{text}`` (or any placeholder but
    ``%{fullData.name}``) is not credited with a direct label: a conservative refusal,
    which can refuse a figure but never passes a color-only pair (#468)."""
    template = trace.get("texttemplate")
    return template if template not in (None, "") else trace.get("text")


def _channels(trace: Mapping[str, Any], names: set[str]) -> dict[str, str]:
    """The non-color encodings ``trace`` draws (#432), each only where its type draws
    it: a marker symbol where a scatter trace draws markers, a line dash where it draws
    lines, a pattern on bars, and a direct label naming the series: an annotation whose
    text is the trace's name, or shown text that, with its placeholders removed, is the
    name, or that writes it with ``%{fullData.name}``. Shown text is read from
    :func:`_drawn_text`, so a ``text`` a ``texttemplate`` replaces names nothing, and
    placeholders are not resolved (#433). A trace of any other type draws none of
    these, so two traces of such a type are reported as differing by color alone,
    by :func:`figure_problems` too, which also refuses each such type outright
    (:data:`TRACE_TYPES`, #638). A numeric symbol or dash is not read here:
    :func:`figure_problems` refuses it, rather than copy plotly's number table."""
    kind = trace.get("type", "scatter")
    found_marker, found_line = trace.get("marker"), trace.get("line")
    marker: dict[str, Any] = found_marker if isinstance(found_marker, dict) else {}
    line: dict[str, Any] = found_line if isinstance(found_line, dict) else {}
    found: dict[str, str] = {}
    if kind == "scatter" and "markers" in _mode(trace):
        found["symbol"] = json.dumps(marker.get("symbol", "circle"))
    if kind == "scatter" and "lines" in _mode(trace):
        found["dash"] = json.dumps(line.get("dash", "solid"))
    if kind == "bar":
        pattern = marker.get("pattern")
        shape = pattern.get("shape") if isinstance(pattern, dict) else None
        found["pattern"] = json.dumps(shape or "")
    name = trace.get("name")
    if kind in ("scatter", "bar") and isinstance(name, str) and name.strip():
        if kind == "scatter":
            shown = "text" in _mode(trace)
        else:
            shown = trace.get("textposition", "auto") != "none"
        text = _drawn_text(trace)
        named = isinstance(text, str) and (
            "%{fullData.name}" in text
            or _without_placeholders(text).strip() == name.strip()
        )
        if name in names or (shown and named):
            found["label"] = json.dumps(name)
    return found


def color_only_pairs(figure: Mapping[str, Any]) -> list[tuple[int, int]]:
    """Each pair of traces that differs by color alone (WCAG 1.4.1, #432): the two are
    of the same type and draw the same shape channels (symbol, dash, pattern), and no
    channel both draw tells them apart. Traces of different types, or drawing different
    shape channels (dots against a line), differ in shape. A direct label is no shape:
    it tells two traces apart only when both carry one, so a label on one of them does
    not excuse the pair."""
    data = figure.get("data") or []
    layout = figure.get("layout")
    notes = layout.get("annotations") if isinstance(layout, dict) else None
    names = {
        note["text"]
        for note in (notes if isinstance(notes, list) else [])
        if isinstance(note, dict) and isinstance(note.get("text"), str)
    }
    traces = [
        (
            trace.get("type", "scatter") if isinstance(trace, dict) else None,
            _channels(trace, names) if isinstance(trace, dict) else {},
        )
        for trace in data
    ]
    pairs = []
    for (i, (kind_i, first)), (j, (kind_j, second)) in combinations(
        enumerate(traces), 2
    ):
        if kind_i != kind_j or set(first) - {"label"} != set(second) - {"label"}:
            continue
        if not any(first[c] != second[c] for c in set(first) & set(second)):
            pairs.append((i, j))
    return pairs


def _is_number(value: Any) -> bool:
    """A number, or a string plotly reads as one (``"0"``, an alias of ``"circle"``)."""
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) or (
        isinstance(value, str) and value.isdigit()
    )


def number_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each numeric marker symbol or line dash (#432's review), alone or in a list, as
    a number or a string of digits: plotly reads ``0`` and ``"0"`` as ``"circle"``, so
    a number would hide two traces' sameness from :func:`color_only_pairs`. And each
    scatter trace with no ``mode``: plotly then picks its mode by its point count, so
    :func:`_channels` could not tell what it draws."""
    problems = []
    for index, trace in enumerate(figure.get("data") or []):
        if not isinstance(trace, dict):
            continue
        for part, key in (("marker", "symbol"), ("line", "dash")):
            holder = trace.get(part)
            value = holder.get(key) if isinstance(holder, dict) else None
            values = value if isinstance(value, list) else [value]
            if any(_is_number(v) for v in values):
                problems.append(f"data[{index}].{part}.{key}: a number, not a name")
        if trace.get("type", "scatter") == "scatter" and not isinstance(
            trace.get("mode"), str
        ):
            problems.append(f"data[{index}].mode: a scatter trace names its mode")
    return problems


#: The trace types a chart may draw (D121(b′), #638): a closed allow-list, so it fails
#: closed as plotly.js adds types. Any other type is refused on every chart, since
#: several (a ``choropleth`` with no ``colorscale``, ``heatmap``, ``histogram2d``,
#: ``densitymap``, ``surface`` and more) color by a number in plotly's default
#: colorscale, which is no token, with no key :func:`color_problems` would see. (A
#: trace naming a ``coloraxis`` is refused by that key too since #645.) A trace with
#: no ``type`` is a ``scatter``, as every check here reads it.
TRACE_TYPES: frozenset[str] = frozenset({"scatter", "bar"})


#: The layout keys whose buttons or steps can restyle, relayout or animate a chart
#: after it is drawn (#638's review): a ``restyle`` arg can set a trace's ``type``, so
#: either would carry a type :func:`trace_type_problems` never reads. No chart uses
#: one; each is refused on any value.
_CONTROL_LAYOUT_KEYS = ("updatemenus", "sliders")


def trace_type_problems(
    figure: Mapping[str, Any], *, map_bins: bool = False
) -> list[str]:
    """Each trace whose type is not in :data:`TRACE_TYPES` (D121(b′), #638): another
    string, a case or spacing variant of an allowed one, or a value that is no string.
    With ``map_bins`` (only ``True``, #639) ``data[0]`` may also be a ``choropleth``,
    whose shape :func:`map_problems` pins; anywhere else it is refused.
    A trace that is not an object is :func:`hover_problems`'. And each way a figure
    could draw a trace its ``data`` does not hold, so that ``data`` is every trace the
    chart ever draws: a top-level ``frames`` list, which ``dcc.Graph`` passes to plotly,
    and a layout's :data:`_CONTROL_LAYOUT_KEYS`, each refused on any value."""
    problems = []
    for index, trace in enumerate(figure.get("data") or []):
        if not isinstance(trace, dict):
            continue
        kind = trace.get("type", "scatter")
        if index == 0 and _is_map(figure, map_bins):
            continue
        if not (isinstance(kind, str) and kind in TRACE_TYPES):
            problems.append(
                f"data[{index}].type: {kind!r}, not a chart trace type (scatter or bar)"
            )
    if "frames" in figure:
        problems.append("frames: a chart draws only the traces in its data")
    layout = figure.get("layout")
    if isinstance(layout, dict):
        problems += [
            f"layout.{key}: no control may restyle a chart"
            for key in _CONTROL_LAYOUT_KEYS
            if key in layout
        ]
    return problems


def hover_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each trace whose hover text would be plotly.js's own (#432): a trace writes its
    whole hover text in a ``hovertemplate``, or turns hover off."""
    problems = []
    for index, trace in enumerate(figure.get("data") or []):
        if not isinstance(trace, dict):
            problems.append(f"data[{index}]: not a trace")
        elif trace.get("hoverinfo") in ("skip", "none"):
            continue
        elif (
            not isinstance(trace.get("hovertemplate"), str)
            or not trace["hovertemplate"].strip()
        ):
            problems.append(f"data[{index}]: no hovertemplate")
    return problems


#: What a ``%{…}`` placeholder in a hover or text template may name (#433, D091): a
#: string the page wrote (``customdata`` or a part of it, ``hovertext``, ``text``) or
#: the trace's name, and never a value or a format (``%{x:.1%}``, ``%{y}``); and every
#: item of a trace's ``text``, ``hovertext`` and ``customdata`` is a string
#: (:func:`template_problems`). So every hover and text label shows a string its page
#: wrote, never plotly's own formatting of a value. That those strings are the companion
#: table's cells is each chart's reconciliation test's to show (C1's: ``TestC1`` in
#: ``test_dashboard_election.py``). Axis tick labels are the exception: plotly writes
#: them, under the template's full-number formats and a chart's ``tickformat``, which
#: :func:`override_problems` holds to the types that write a number in full.
_ALLOWED_PLACEHOLDER_RE = re.compile(
    r"%\{(?:customdata(?:\[\d+\]|\.[A-Za-z0-9_]+)*|hovertext|text|fullData\.name)\}"
)

#: The keys whose strings are templates plotly fills.
_TEMPLATE_KEYS = frozenset({"hovertemplate", "texttemplate"})

#: A trace's keys whose items plotly draws as written or fills into a template: each
#: item must be a string the page wrote, never a value plotly would format itself.
_STRING_KEYS = ("text", "hovertext", "customdata")


def _non_strings(value: Any, path: str) -> Iterator[str]:
    """Each item under ``value`` (a string, or a list or dict of them at any depth)
    that is not a string."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from _non_strings(inner, f"{path}.{key}")
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from _non_strings(inner, f"{path}[{index}]")
    elif not isinstance(value, str):
        yield path


def template_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each template placeholder that names a value or a format rather than a string the
    page wrote (:data:`_ALLOWED_PLACEHOLDER_RE`); each ``hoverformat`` (an axis's, or a
    trace's ``xhoverformat`` and the like), which formats a value plotly then shows; and
    each item of a trace's ``text``, ``hovertext`` or ``customdata`` that is not a
    string, which plotly would format itself (#433, D091)."""
    problems = [
        f"{path}: not a string the page wrote"
        for index, trace in enumerate(figure.get("data") or [])
        if isinstance(trace, dict)
        for key in _STRING_KEYS
        if key in trace
        for path in _non_strings(trace[key], f"data[{index}].{key}")
    ]
    for path, key, value in _walk(figure):
        if key in _TEMPLATE_KEYS and isinstance(value, str):
            problems += [
                f"{path}: {placeholder!r} is not a string the page wrote"
                for placeholder in _placeholders(value)
                if not _ALLOWED_PLACEHOLDER_RE.fullmatch(placeholder)
            ]
        elif key.endswith("hoverformat") and not path.endswith("]"):
            problems.append(f"{path}: no hover format")
    return problems


def bar_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each bar trace setting its own ``width`` or ``offset``, which plotly lets win
    over the template's ``bargap`` and ``bargroupgap``, so bars of different series
    could touch (#432's review, #433, D091); and a layout ``scattergap``, which places
    scatter points against bar slots by a gap of its own."""
    problems = [
        f"data[{index}].{key}: a bar's width and place are the template's"
        for index, trace in enumerate(figure.get("data") or [])
        if isinstance(trace, dict) and trace.get("type", "scatter") == "bar"
        for key in ("width", "offset")
        if key in trace
    ]
    layout = figure.get("layout")
    if isinstance(layout, dict) and "scattergap" in layout:
        problems.append("layout.scattergap: fixed by the template's bar gaps")
    return problems


#: The keys the map's one trace may hold (#639, D121(a)–(d), fail closed as
#: :data:`TRACE_TYPES` does): no ``marker.opacity`` (a bin blended with the page), no
#: ``selectedpoints``, ``selected`` or ``unselected`` (states dimmed by plotly), no
#: ``geojson`` or ``featureidkey`` (outlines from elsewhere), and the rest.
MAP_TRACE_KEYS = frozenset(
    {
        "type",
        "locationmode",
        "locations",
        "z",
        "zmin",
        "zmax",
        "colorscale",
        "showscale",
        "colorbar",
        "marker",
        "hovertemplate",
        "hoverinfo",
        "hovertext",
        "customdata",
        "text",
        "name",
        "geo",
    }
)


#: The keys the map's colorbar may hold (#639, D121(d); code review round 1's scope
#: ruling): one tick per bin with its written range, a title, and no outline
#: (``outlinewidth`` 0, since plotly's default outline is ``#444``, no token). A key
#: that could hide or rewrite the labels (``showticklabels``, ``ticklabelstep``,
#: ``labelalias``, ``tickprefix``, …) stays refused, since the written ranges are how a
#: bin's meaning reaches a reader without color (D121(d)). A placement or size key
#: (``orientation``, ``len``, ``thickness``, ``x``, ``y``, …) is #623's to add, with
#: its bounds, as a chart that needs another slot widens it in its own story.
MAP_COLORBAR_KEYS = frozenset(
    {"tickmode", "tickvals", "ticktext", "title", "outlinewidth"}
)


def _exactly(value: Any, expected: Any) -> bool:
    """``value`` equals ``expected`` kind for kind (``True`` is not ``1``, ``0`` is not
    ``0.0``), through lists."""
    if isinstance(expected, list):
        return (
            isinstance(value, list)
            and len(value) == len(expected)
            and all(_exactly(v, e) for v, e in zip(value, expected, strict=True))
        )
    return type(value) is type(expected) and value == expected


def map_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each way ``figure`` departs from the map's one shape (#639, D121(a), (c), (d)),
    which :func:`figure_problems` checks only on a chart whose registry row sets
    ``map_bins``: exactly one trace, a ``choropleth`` with ``locationmode``
    ``"USA-states"`` holding only :data:`MAP_TRACE_KEYS`; ``z`` a bin index from 0 to
    k − 1 for each of ``locations``, distinct strings (a state with no figure is not
    among them, D121(f)); its colorscale :func:`map_colorscale` of one of
    :data:`MAP_RAMPS` (so every stop is a bin token, and k is
    :data:`MAP_BIN_COUNT`); ``zmin`` −0.5 and ``zmax`` k − 0.5; a colorbar shown,
    holding only :data:`MAP_COLORBAR_KEYS`, with a tick at each bin written as page
    text (``tickmode`` ``"array"``, ``tickvals`` the bin indexes, ``ticktext`` one
    non-blank string per bin, no two alike), no outline (``outlinewidth`` 0), and a
    ``title``, where it has one, holding only its ``text``; and borders in
    :data:`MAP_BORDER` (``marker`` holding only ``line``, which holds only that
    ``color``). The keys D121(a) refuses (``coloraxis``, ``autocolorscale``,
    ``reversescale``, ``zmid``, ``zauto``) are :func:`color_problems`'. Total: it guards
    each kind it reads into."""
    data = figure.get("data") or []
    if len(data) != 1:
        return [f"data: {len(data)} traces, not the map's one"]
    trace = data[0]
    if not isinstance(trace, dict):
        return []  # hover_problems': not a trace
    k = MAP_BIN_COUNT
    problems = [
        f"data[0].{key}: not a key of the map's trace"
        for key in trace
        if key not in MAP_TRACE_KEYS
    ]
    if trace.get("type") != "choropleth":
        problems.append("data[0].type: the map is a choropleth")
    if trace.get("locationmode") != "USA-states":
        problems.append('data[0].locationmode: the map\'s is "USA-states"')
    z, locations = trace.get("z"), trace.get("locations")
    if not (
        isinstance(z, list) and z and all(type(b) is int and 0 <= b < k for b in z)
    ):
        problems.append(f"data[0].z: not a list of bin indexes from 0 to {k - 1}")
    if not (
        isinstance(locations, list)
        and all(isinstance(code, str) for code in locations)
        and len(set(locations)) == len(locations)
    ):
        problems.append("data[0].locations: not a list of distinct strings")
    elif not (isinstance(z, list) and len(z) == len(locations)):
        problems.append("data[0].locations: not one for each bin index in z")
    if not any(
        _exactly(trace.get("colorscale"), map_colorscale(ramp)) for ramp in MAP_RAMPS
    ):
        problems.append("data[0].colorscale: not the stepwise scale of a map ramp")
    for key, bound in (("zmin", -0.5), ("zmax", k - 0.5)):
        if not _exactly(trace.get(key), bound):
            problems.append(f"data[0].{key}: not {bound}")
    if trace.get("showscale") is not True:
        problems.append("data[0].showscale: the map shows its colorbar")
    colorbar = trace.get("colorbar")
    if not isinstance(colorbar, dict):
        problems.append("data[0].colorbar: the map's colorbar is an object")
    else:
        problems += [
            f"data[0].colorbar.{key}: not a key of the map's colorbar"
            for key in colorbar
            if key not in MAP_COLORBAR_KEYS
        ]
        if not _exactly(colorbar.get("outlinewidth"), 0):
            problems.append("data[0].colorbar.outlinewidth: the map's colorbar is 0")
        title = colorbar.get("title")
        if "title" in colorbar and not (
            isinstance(title, dict)
            and set(title) == {"text"}
            and isinstance(title.get("text"), str)
        ):
            problems.append("data[0].colorbar.title: only its text")
        if colorbar.get("tickmode") != "array":
            problems.append('data[0].colorbar.tickmode: the map\'s is "array"')
        if not _exactly(colorbar.get("tickvals"), list(range(k))):
            problems.append(
                f"data[0].colorbar.tickvals: not the bin indexes 0 to {k - 1}"
            )
        ticktext = colorbar.get("ticktext")
        if not (
            isinstance(ticktext, list)
            and len(ticktext) == k
            and all(isinstance(t, str) and t.strip() for t in ticktext)
            and len({t.strip() for t in ticktext}) == k
        ):
            problems.append(
                f"data[0].colorbar.ticktext: not {k} distinct labels the page wrote"
            )
    marker = trace.get("marker")
    line = marker.get("line") if isinstance(marker, dict) else None
    if not (
        isinstance(marker, dict)
        and set(marker) == {"line"}
        and isinstance(line, dict)
        and set(line) == {"color"}
        and line.get("color") == MAP_BORDER
    ):
        problems.append(f"data[0].marker: not only line.color {MAP_BORDER}")
    return problems


#: The JSON kinds a slot may hold (#484, D099), as :func:`_kind` names them.
STRING = frozenset({"a string"})
STRINGS = frozenset({"a string", "a list of strings"})
STRING_LIST = frozenset({"a list of strings"})
OBJECT = frozenset({"an object"})
LIST = frozenset({"a list", "a list of strings"})
NUMBER = frozenset({"a number"})
BOOLEAN = frozenset({"a boolean"})

#: Each slot a check reads by name, and the kinds that check expects there (#484,
#: D099): any other kind is refused (:func:`slot_problems`), never passed silently.
#: Keyed by where the slot sits: ``trace`` is each item of ``data``, ``marker``,
#: ``pattern``, ``marker_line``, ``line``, ``colorbar`` and ``colorbar_title`` are a
#: trace's ``marker``, its ``marker.pattern``, its ``marker.line``, its ``line``, its
#: ``colorbar`` and its ``colorbar.title`` (the map's, #639), ``axis`` is each layout
#: key :data:`_AXIS_RE` matches, ``annotation`` each item of ``layout.annotations``,
#: and ``any`` a key at any depth. Not listed: the
#: slots whose own rule pins the value whatever its kind: a trace's ``legend`` and
#: ``geo`` (refused unless exactly ``"legend"`` and ``"geo"``), a bar's ``width`` and
#: ``offset``, the layout's fixed
#: keys, ``template`` and ``scattergap``, ``updatemenus`` and ``sliders``, and
#: ``config`` and ``frames`` (each refused on any value),
#: and a color key (a token reference only). The items of a trace's ``text``,
#: ``hovertext`` and ``customdata`` are each a string (:func:`template_problems`), and
#: the slots themselves are typed here. Policy, beyond types:
#: ``textposition`` is one string, since a list would credit a direct label that
#: ``["none", …]`` never draws, and a marker symbol and a pattern shape are one
#: string, since a list per point would tell categories apart inside one trace, as
#: :func:`color_problems` refuses a list ``color`` for. A chart that needs another
#: kind widens its slot in its own story. ``EXPECTED_KINDS`` in
#: ``test_dashboard_charts.py``, a hand-written literal, must equal this.
SLOT_KINDS: Mapping[str, Mapping[str, frozenset[str]]] = {
    "trace": {
        "type": STRING,
        "mode": STRING,
        "name": STRING,
        "hoverinfo": STRING,
        "textposition": STRING,
        "text": STRINGS,
        "hovertext": STRINGS,
        "customdata": LIST,
        "marker": OBJECT,
        "line": OBJECT,
        # The map's (#639, D121(b)): map_problems reads them under map_bins, and
        # slot_problems types them on every chart's traces, as every slot here is.
        "locationmode": STRING,
        "locations": STRING_LIST,
        "z": LIST,
        "zmin": NUMBER,
        "zmax": NUMBER,
        "colorscale": LIST,
        "showscale": BOOLEAN,
        "colorbar": OBJECT,
    },
    "marker": {"symbol": STRING, "pattern": OBJECT, "line": OBJECT},
    "pattern": {"shape": STRING},
    "marker_line": {"color": STRING},
    "line": {"dash": STRING},
    "colorbar": {
        "tickmode": STRING,
        "tickvals": LIST,
        "ticktext": STRING_LIST,
        "title": OBJECT,
        "outlinewidth": NUMBER,
    },
    "colorbar_title": {"text": STRING},
    "layout": {"legend": OBJECT, "annotations": LIST, "geo": OBJECT},
    "axis": {"tickformat": STRING},
    "annotation": {"text": STRING},
    "any": {"family": STRING, "hovertemplate": STRINGS, "texttemplate": STRINGS},
}

#: The kind of each item a check reads into by pattern or by index: a layout axis and
#: an annotation are objects (a trace that is not one is :func:`hover_problems`').
ANCHOR_KINDS: Mapping[str, frozenset[str]] = {"axis": OBJECT, "annotation": OBJECT}


def _kind(value: Any) -> str:
    """``value``'s JSON kind, as :data:`SLOT_KINDS` names it."""
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, (int, float)):
        return "a number"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "an object"
    if all(isinstance(item, str) for item in value):
        return "a list of strings"
    return "a list"


def _kinds_problem(path: str, value: Any, kinds: frozenset[str]) -> list[str]:
    kind = _kind(value)
    if kind in kinds:
        return []
    return [f"{path}: {kind}, not {' or '.join(sorted(kinds))}"]


def _slots_problems(holder: Any, anchor: str, path: str) -> list[str]:
    """Each slot of ``anchor`` in ``holder`` (an object, else nothing to read) holding a
    kind :data:`SLOT_KINDS` does not list for it."""
    if not isinstance(holder, dict):
        return []
    return [
        problem
        for key, kinds in SLOT_KINDS[anchor].items()
        if key in holder
        for problem in _kinds_problem(_child(path, key), holder[key], kinds)
    ]


def slot_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each slot a check reads that holds a kind the check does not expect (#484, D099,
    :data:`SLOT_KINDS`): reported, so the figure is refused rather than passed."""
    problems = []
    for index, trace in enumerate(figure.get("data") or []):
        here = f"data[{index}]"
        problems += _slots_problems(trace, "trace", here)
        if not isinstance(trace, dict):
            continue
        marker, line = trace.get("marker"), trace.get("line")
        problems += _slots_problems(marker, "marker", f"{here}.marker")
        if isinstance(marker, dict):
            problems += _slots_problems(
                marker.get("pattern"), "pattern", f"{here}.marker.pattern"
            )
            problems += _slots_problems(
                marker.get("line"), "marker_line", f"{here}.marker.line"
            )
        problems += _slots_problems(line, "line", f"{here}.line")
        colorbar = trace.get("colorbar")
        problems += _slots_problems(colorbar, "colorbar", f"{here}.colorbar")
        if isinstance(colorbar, dict):
            problems += _slots_problems(
                colorbar.get("title"), "colorbar_title", f"{here}.colorbar.title"
            )
    layout = figure.get("layout")
    problems += _slots_problems(layout, "layout", "layout")
    if isinstance(layout, dict):
        for name, axis in layout.items():
            if _AXIS_RE.fullmatch(name):
                here = f"layout.{name}"
                problems += _kinds_problem(here, axis, ANCHOR_KINDS["axis"])
                problems += _slots_problems(axis, "axis", here)
        notes = layout.get("annotations")
        for index, note in enumerate(notes if isinstance(notes, list) else []):
            here = f"layout.annotations[{index}]"
            problems += _kinds_problem(here, note, ANCHOR_KINDS["annotation"])
            problems += _slots_problems(note, "annotation", here)
    for path, key, value in _walk(figure):
        if key in SLOT_KINDS["any"] and not path.endswith("]"):
            problems += _kinds_problem(path, value, SLOT_KINDS["any"][key])
    return problems


def figure_problems(
    figure: Any, *, short_value_ticks: bool = False, map_bins: bool = False
) -> list[str]:
    """Everything that keeps ``figure`` from being a chart's (#432): it is a plain dict
    with a list of traces, each a ``scatter`` or a ``bar`` (:data:`TRACE_TYPES`, #638;
    no ``type`` reads as ``scatter``) and no frames or restyling controls
    (:func:`trace_type_problems`), sets no template or config of its own and
    overrides none of the template's fixed defaults, names colors only as token
    references, carries no markup but ``<br>`` and ``<extra>``, names marker symbols
    and dashes rather than numbering them and names every scatter trace's mode, writes
    its own hover text with no number format, sets no bar's width or offset, and never
    tells two traces apart by color alone. ``short_value_ticks`` is the chart's
    registry row's (#596, D110): see :func:`override_problems`. So is ``map_bins``
    (#639, D121(b)): only ``True`` admits the map's choropleth and its colorscale,
    colorbar and ``showscale`` (:func:`trace_type_problems`, :func:`color_problems`),
    and then the figure must be the map (:func:`map_problems`).

    Total (#484, D099): for any input it returns a list of strings and never raises. A
    figure that is not a JSON value of bounded depth gets :func:`json_problems`' alone,
    since every other check assumes one; a slot holding a kind its check does not
    expect is refused (:func:`slot_problems`). That refusal gates nothing, so every
    check still reads a mistyped slot: a check added here inherits only the structural
    guarantee (JSON kinds, bounded depth, finite numbers in range), must guard the kinds
    it indexes into as each check here does, and must declare in :data:`SLOT_KINDS`
    each slot it reads by name, which
    ``TestSlotKinds.test_every_slot_read_by_name_is_declared`` enforces."""
    if not isinstance(figure, dict) or not isinstance(figure.get("data"), list):
        return ["not a figure dict with a list of traces"]
    structural = json_problems(figure)
    if structural:
        return structural
    problems = [
        *slot_problems(figure),
        *trace_type_problems(figure, map_bins=map_bins),
        *color_problems(figure, map_bins=map_bins),
        *(map_problems(figure) if map_bins is True else []),
        *markup_problems(figure),
        *override_problems(figure, short_value_ticks=short_value_ticks),
        *number_problems(figure),
        *hover_problems(figure),
        *template_problems(figure),
        *bar_problems(figure),
    ]
    layout = figure.get("layout", {})
    if not isinstance(layout, dict):
        problems.append("layout: not a dict")
    elif "template" in layout:
        problems.append("layout.template: the template is the foundation's")
    if "config" in figure:
        problems.append("config: the config is the foundation's")
    problems += [
        f"data[{i}] and data[{j}] differ by color alone"
        for i, j in color_only_pairs(figure)
    ]
    return problems


#: The chart callback (#432), run in the browser for each chart on the page (a MATCH
#: callback over :data:`GRAPH_TYPE` and :data:`SOURCE_TYPE`): its inputs are the chart's
#: unresolved figure, in its source store, and the theme in effect
#: (``components.THEME_STORE_ID``); its outputs are the graph's ``figure`` and
#: ``style``.
#: Dash calls it when a chart's graph mounts (put in by :data:`CHART_MOUNT_CALLBACK`,
#: so its outputs are in no server layout, which ``suppress_callback_exceptions``
#: allows), after a client-side navigation too, and whenever
#: the theme in effect changes, so a theme switch redraws every chart on the page with
#: no reload, no server round trip and no API request. While the store is ``None`` (the
#: theme callback has not run yet) it changes nothing, as the store's contract (b) asks;
#: the graph stays hidden until then. Otherwise it deep-copies the source, never
#: mutating the store's data, replaces every whole-string token reference with the
#: token's value on ``<html>`` (current, by the store's contract (a)), throwing if a
#: token is unset so the e2e suite's console guard fails, attaches the resolved
#: :data:`TEMPLATE`, and shows the graph. It builds no HTML and evaluates nothing.
CHART_CALLBACK = (
    "function (source, theme) {"
    " var clientside = window.dash_clientside;"
    " if (theme === null || theme === undefined || source === null"
    " || source === undefined) {"
    " return [clientside.no_update, clientside.no_update]; }"
    f" var template = {json.dumps(TEMPLATE)};"
    f" var token = new RegExp({json.dumps('^' + TOKEN_RE.pattern + '$')});"
    " var style = window.getComputedStyle(document.documentElement);"
    " function resolve(value) {"
    " if (typeof value === 'string') {"
    " var match = token.exec(value);"
    " if (match === null) { return value; }"
    " var resolved = style.getPropertyValue(match[1]).trim();"
    " if (resolved === '') {"
    " throw new Error('chart token ' + match[1] + ' is unset'); }"
    " return resolved; }"
    " if (Array.isArray(value)) { return value.map(resolve); }"
    " if (value !== null && typeof value === 'object') {"
    " var copy = {};"
    " Object.keys(value).forEach(function (key) { copy[key] = resolve(value[key]); });"
    " return copy; }"
    " return value; }"
    " var figure = resolve(source);"
    " figure.layout = figure.layout || {};"
    " figure.layout.template = resolve(template);"
    ' return [figure, {visibility: "visible"}];'
    " }"
)

#: How long the mount callback waits for plotly.js before it gives up (#452): dcc's
#: own wait. It only ends the wait; a script already fetching is not canceled, and if
#: it lands later, a later mount finds ``window.Plotly`` set.
PLOTLYJS_TIMEOUT_MS = 30_000

#: The one ``window`` property holding the document's plotly.js load (#452): a Promise
#: of ``true`` (loaded) or ``false`` (failed or timed out), set once and never cleared.
PLOTLYJS_MEMO = "__exploreChartPlotlyjs"

#: The graph the mount callback returns, as Dash component JSON (#452): its type and
#: namespace read from ``dcc.Graph`` itself (class attributes, no instance, no literal),
#: the shared :data:`CHART_CONFIG`, hidden until :data:`CHART_CALLBACK` draws it. The
#: callback adds its pattern id (:func:`graph_id` of the mount's chart).
_GRAPH_JSON = {
    "type": dcc.Graph._type,
    "namespace": dcc.Graph._namespace,
    "props": {"config": CHART_CONFIG, "style": {"visibility": "hidden"}},
}

#: The mount callback (#452, D088), run in the browser for each chart on the page (a
#: MATCH callback): its input is the chart's source store, which exists from the
#: chart's first render and is never written (no callback declares it as an output, and
#: nothing but the theme listener calls ``set_props``:
#: ``TestMountCallback.test_no_callback_writes_a_chart_source_store``), so it runs once
#: per mount; its state is the mount point's own id; its output is the mount point's
#: ``children``.
#: It returns a Promise, which Dash awaits. plotly.js is loaded once per document and
#: never retried within it (a reload retries): ``window.Plotly`` is checked first on
#: every call, and otherwise every chart shares one load, kept as a Promise in
#: :data:`PLOTLYJS_MEMO`, set synchronously before anything waits on it, from the
#: address the renderer set from ``_config`` (``window._dashPlotlyJSURL``, D087's).
#: The Promise resolves ``true`` once the script loaded and defined ``window.Plotly``,
#: and ``false`` on its error, on the timeout, or if there is no address (which it
#: logs, once, so the e2e guard sees a renderer change); it never rejects, and the
#: callback never throws, so a blocked CDN costs the browser's one resource error and
#: nothing else. Loaded, the callback returns the graph (:data:`_GRAPH_JSON` with its
#: id), which :data:`CHART_CALLBACK` then draws; dcc's own loader finds
#: ``window.Plotly`` and never appends a script or fetches. Not loaded, it returns
#: ``no_update``: the mount point stays empty and the title, caption, pointer and table
#: are what the reader has. It builds no HTML and evaluates nothing.
CHART_MOUNT_CALLBACK = (
    "function (source, mount) {"
    " var clientside = window.dash_clientside;"
    f" var memo = {json.dumps(PLOTLYJS_MEMO)};"
    f" var graph = {json.dumps(_GRAPH_JSON)};"
    " function load() {"
    " if (window.Plotly) { return Promise.resolve(true); }"
    " if (!window[memo]) {"
    " window[memo] = new Promise(function (resolve) {"
    " var address = window._dashPlotlyJSURL;"
    " if (typeof address !== 'string') {"
    " console.error('chart: no plotly.js address'); resolve(false); return; }"
    " var script = document.createElement('script');"
    " var timer = setTimeout(function () { resolve(false); },"
    f" {PLOTLYJS_TIMEOUT_MS});"
    " script.onload = function () {"
    " clearTimeout(timer); resolve(Boolean(window.Plotly)); };"
    " script.onerror = function () { clearTimeout(timer); resolve(false); };"
    " script.src = address;"
    " script.async = true;"
    " document.body.appendChild(script); }); }"
    " return window[memo]; }"
    " return load().then(function (loaded) {"
    " if (!loaded) { return clientside.no_update; }"
    " var props = JSON.parse(JSON.stringify(graph.props));"
    f" props.id = {{type: {json.dumps(GRAPH_TYPE)}, chart: mount.chart}};"
    " return {type: graph.type, namespace: graph.namespace, props: props}; });"
    " }"
)
