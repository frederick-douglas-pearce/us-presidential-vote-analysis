"""The chart foundation (#432, E14-S3): the chart registry, the one Plotly template,
the shared config, the rules every chart's figure follows, and the clientside callback
that draws each chart in the theme in effect.

No chart is built here: ``components.chart`` builds every one, from a figure a page
passes it, and checks the figure against :func:`figure_problems`. A figure is a plain
dict (``plotly`` is a banned import, D070(b)'s guard), and it names no color: each color
is a ``var(--token)`` reference to a token in ``style.css``, which
:data:`CHART_CALLBACK` resolves in the browser, so ``style.css`` stays the one source of
every color.

No ``dcc.Graph`` is ever in a server-rendered layout (#452, D088): ``components.chart``
renders an empty mount point, and :data:`CHART_MOUNT_CALLBACK` puts the graph in it only
once plotly.js has loaded, so dcc's own loader never runs and a blocked CDN cannot make
Dash loop.

A shared module: it imports nothing from ``explore`` and reads no API
(``TestSharedPieces`` in ``test_dashboard_elections.py``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from itertools import combinations
from typing import Any, NamedTuple

from dash import dcc


class Chart(NamedTuple):
    """One registered chart: the path template of the page it renders on, the DOM id of
    its companion table (the table on that page holding its values), and whether its ID
    is retired. A retired ID is never built and never reused."""

    page: str
    table: str
    retired: bool = False


#: A chart ID: ``C1``, ``C2``, …, issued in order of story filing.
ID_RE = re.compile(r"C[1-9][0-9]*")

#: The chart registry (#432): every chart ID ever registered, live or retired. An ID is
#: issued when its chart story registers it, is never renumbered or reused, and stays
#: here once retired. Empty until C1 (#433) lands; C1–C5 are assigned to #433–#436 by
#: their issues. ``components.chart`` reads it by attribute at call time. ``ISSUED``, a
#: hand-written literal of every issued ID with its whole row, must equal this
#: (``TestChartRegistry`` in ``test_dashboard_charts.py`` reads it), and
#: ``test_every_row_is_well_formed_and_on_a_registered_page`` checks each row.
CHARTS: Mapping[str, Chart] = {}


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
        ):
            problems.append(f"{chart_id!r}: not a chart row")
    return problems


def dom_id(chart_id: str) -> str:
    """The chart's element id, its ID in lower case (``c1``): also a fragment link
    (``/elections#c2``), which never reaches the server."""
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

#: Color attributes no chart may set: a colorscale maps numbers to colors that are no
#: token.
_REFUSED_KEY_RE = re.compile(r".*colorscale")

#: The one Plotly template every chart is drawn with (#432), in both palettes: its color
#: slots name tokens, which :data:`CHART_CALLBACK` resolves from the palette in effect,
#: so "the light template" and "the dark template" are this one resolved against each.
#: Its other values are the shared defaults: no drag or zoom, a legend that is only a
#: key (a click hides nothing), hover text for the nearest point only, numbers written
#: in full with thousands separators (never "80M" or "1.2B", as the tables write them),
#: and bars in groups with a gap on every side (``bargap`` between locations,
#: ``bargroupgap`` within one, never stacked or overlaid), so neighboring bars of
#: different series, whose tokens do not contrast with each other, are always parted by
#: the page's color (WCAG 1.4.11). Not enforced here, and C1's to rule on (#433): a
#: number format inside a hover or text template or an axis ``hoverformat``, and a
#: trace's own bar ``width`` or ``offset``.
TEMPLATE: dict[str, Any] = {
    "layout": {
        "font": {"family": "var(--font-body)", "color": "var(--text)", "size": 14},
        "paper_bgcolor": "var(--page)",
        "plot_bgcolor": "var(--page)",
        "colorway": ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)"],
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
    },
}

#: The config every chart's graph takes, and no chart overrides: no plotly logo, no
#: scroll zoom, and no toolbar (owner, #432's plan gate: the companion table's CSV is
#: the data download), so no plotly.js text reaches a reader; resized with its box.
CHART_CONFIG: dict[str, Any] = {
    "displaylogo": False,
    "scrollZoom": False,
    "displayModeBar": False,
    "responsive": True,
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

#: A d3 number format,
#: ``[[fill]align][sign][symbol][0][width][,][.precision][~][type]``, its type
#: captured. An axis ``tickformat`` may use only the types that write a number in
#: full (:data:`_FULL_TYPES`): every other type, and none at all (which d3 reads as
#: ``~g``), can shorten it or write an exponent ("80M", "8e+7"). A format starting
#: ``%`` is a date format, not a number one, and is left alone.
_D3_FORMAT_RE = re.compile(r"(?:.?[<>=^])?[-+( ]?[$#]?0?\d*,?(?:\.\d+)?~?([A-Za-z%]?)")
_FULL_TYPES = frozenset({"d", "f", "r", "%", "p"})


def _shortens(tickformat: str) -> bool:
    if tickformat.startswith("%"):
        return False
    match = _D3_FORMAT_RE.fullmatch(tickformat)
    return match is None or match.group(1) not in _FULL_TYPES


#: A second or later legend, which the template's legend does not reach.
_EXTRA_LEGEND_RE = re.compile(r"legend\d+")

_AXIS_RE = re.compile(r"[xy]axis\d*")


def _walk(value: Any, path: str = "", key: str = "") -> Iterator[tuple[str, str, Any]]:
    """Every ``(path, key, value)`` under ``value``, a figure or a part of one; a list's
    items carry the list's key (``colorway[0]``'s is ``colorway``)."""
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


def color_problems(figure: Mapping[str, Any]) -> list[str]:
    """Where ``figure`` names a color that is not a token reference (#432).

    The allowlist: a key ending ``color``, ``colors`` or ``colorway`` holds a token
    reference other than :data:`FONT_TOKEN`, or (``colorway`` only) a list of them;
    ``family`` may hold only :data:`FONT_TOKEN`; no other string contains ``var(``; no
    colorscale. A numeric or list ``color`` is refused, so a trace never colors its
    points one by one: color would then carry categories inside one trace, where
    :func:`color_only_pairs` cannot see it, and a number would pick a colorscale's
    color, which is no token. Whether a named color token exists in ``style.css`` is
    the tests' to check (this module reads no file): ``TestEveryChart`` for every
    rendered chart, ``TestTemplate`` for the template.
    """
    problems = []
    for path, key, value in _walk(figure):
        if _REFUSED_KEY_RE.fullmatch(key):
            problems.append(f"{path}: no colorscale")
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


def override_problems(figure: Mapping[str, Any]) -> list[str]:
    """Each template default ``figure``'s own layout overrides (#432's review): the
    :data:`FIXED_LAYOUT_KEYS`, :data:`FIXED_LEGEND_KEYS` and :data:`FIXED_AXIS_KEYS`,
    a shortening axis ``tickformat``, and a second legend, in the layout or named by a
    trace."""
    problems = [
        f"data[{index}].legend: {trace['legend']!r}, not the template's legend"
        for index, trace in enumerate(figure.get("data") or [])
        if isinstance(trace, dict) and trace.get("legend", "legend") != "legend"
    ]
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
        if isinstance(tickformat, str) and _shortens(tickformat):
            problems.append(
                f"layout.{name}.tickformat: {tickformat!r} shortens numbers"
            )
    return problems


def _mode(trace: Mapping[str, Any]) -> str:
    mode = trace.get("mode")
    return mode if isinstance(mode, str) else ""


#: What a template writes that the reader never sees as written: a ``%{…}``
#: placeholder.
_PLACEHOLDER_RE = re.compile(r"%\{[^}]*\}")


def _channels(trace: Mapping[str, Any], names: set[str]) -> dict[str, str]:
    """The non-color encodings ``trace`` draws (#432), each only where its type draws
    it: a marker symbol where a scatter trace draws markers, a line dash where it draws
    lines, a pattern on bars, and a direct label naming the series: an annotation whose
    text is the trace's name, or shown text that, with its placeholders removed, is the
    name, or that writes it with ``%{fullData.name}``. A trace of any other type draws
    none of these, so two traces of such a type are reported as differing by color
    alone until this learns the type. A numeric symbol or dash is not read here:
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
        written = [trace.get("text"), trace.get("texttemplate")]
        named = any(
            isinstance(text, str)
            and (
                "%{fullData.name}" in text
                or _PLACEHOLDER_RE.sub("", text).strip() == name.strip()
            )
            for text in written
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


def figure_problems(figure: Any) -> list[str]:
    """Everything that keeps ``figure`` from being a chart's (#432): it is a plain dict
    with a list of traces, sets no template or config of its own and overrides none of
    the template's fixed defaults, names colors only as token references, carries no
    markup but ``<br>`` and ``<extra>``, names marker symbols and dashes rather than
    numbering them and names every scatter trace's mode, writes its own hover text, and
    never tells two traces apart by color alone."""
    if not isinstance(figure, dict) or not isinstance(figure.get("data"), list):
        return ["not a figure dict with a list of traces"]
    problems = [
        *color_problems(figure),
        *markup_problems(figure),
        *override_problems(figure),
        *number_problems(figure),
        *hover_problems(figure),
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
#: own wait. It only ends the wait; a script already fetching is not cancelled, and if
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
#: chart's first render and never changes, so it runs once per mount; its state is the
#: mount point's own id; its output is the mount point's ``children``.
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
#: ``window.Plotly`` and never runs. Not loaded, it returns ``no_update``: the mount
#: point stays empty and the title, caption, pointer and table are what the reader
#: has. It builds no HTML and evaluates nothing.
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
