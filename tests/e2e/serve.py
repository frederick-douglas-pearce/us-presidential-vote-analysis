"""Serve the dashboard from recorded API responses, for the browser tests (#321).

Run by ``conftest.py`` as ``python -m tests.e2e.serve <port>``, from ``dashboard/`` (as
``app.yaml`` and the D070(b) guard run the app) with ``dashboard`` and the repository
root on ``PYTHONPATH``. It lives under ``tests/``, never under ``dashboard/``, so the
deploy root's ``.gcloudignore`` allow-list cannot ship it.

The seam is the one ``test_dashboard_app.py``'s offline client uses: the app is
imported, then ``api.CLIENT`` is replaced before it takes traffic. Every runtime module
reads ``api.CLIENT`` when it is called, and the refresher starts on the first request,
so nothing still holds the original client. The guard's fake transport, which runs the
real ``api.fetch``, is the guard's business; this server tests the browser.

No request leaves the machine. Recorded paths answer from ``tests/fixtures/dashboard/``,
and anything else raises ``ApiUnavailable``, so the page shows its degraded state and
never reads live data. Behind that, an audit hook refuses every non-loopback name lookup
and connection. ``api.fetch``'s ``except Exception`` would turn such a refusal into the
degraded page, so the hook also writes :data:`NETWORK_SENTINEL` to stderr, which
``conftest.py`` fails the session on.

One addition the production app lacks, the **theme probe** (#359): a hidden div and one
test-only clientside callback from the store holding the theme in effect to that div,
the shape of a chart's re-template callback (#432). A ``dcc.Store`` is not in the DOM,
so the probe is how a browser test sees the store's value, and it proves that both of
the store's writers (the theme callback's output and its listener's ``set_props``)
trigger a dependent callback, which is what charts rely on. Each call also records the
palette ``<html>`` shows at that moment (its computed ``color-scheme``), so a test can
check the store's contract that it changes only after the palette has. It is purely
additive: it writes only its own div and two ``window`` records, and
``TestThemeControl`` (``tests/unit/test_dashboard_theme.py``) pins the production app's
theme callback without it, as ``CALLBACK_OUTPUTS`` (``test_dashboard_export.py``) pins
every production callback.

A second addition, the **test chart page** (#432): before C1 (#433), no production page
renders a chart, so the browser tests of the chart foundation need one. It registers a
page at :data:`CHART_PAGE` whose layout is a success marker holding one chart built by
``components.chart`` and its companion table, and rebinds ``charts.CHARTS`` in this
process only with one row, :data:`CHART_ID`, outside the ``C<n>`` IDs, so it can never
collide with an issued one. A second, the **two-chart test page** (#452), holds two
charts (``X2``, ``X3``) beside one table, so the tests see two charts share one
plotly.js load. The D070(b) guard and ``TestEveryChart`` run the production
registry in their own processes. Neither page has a site-navigation entry, and the
figure is a plain dict here, never imported from the unit tests.

``conftest.py`` waits for :data:`READY_LINE` with this server's port, written only once
the cache is filled and the socket is bound, so a session never starts against another
process that took the port. A failed start-up check exits with its reason on stderr,
which ``conftest.py`` prints. Nothing here runs at import: ``conftest.py`` imports the
two markers from it.
"""

from __future__ import annotations

import json
import sys
from typing import Any

#: Written to stderr, flushed, whenever the audit hook refuses a non-loopback lookup or
#: connection.
NETWORK_SENTINEL = "E2E-SERVER-NETWORK-REFUSED"

#: Written to stderr once the cache is filled and the server is listening.
READY_LINE = "E2E-SERVER-READY"

#: The theme probe's div; its text is the store's value. ``window`` counts the probe's
#: calls in :data:`THEME_PROBE_CALLS` and records, in :data:`THEME_PROBE_SEEN`, each
#: value it received with the palette ``<html>`` showed when it ran.
THEME_PROBE_ID = "theme-probe"
THEME_PROBE_CALLS = "exploreThemeProbeCalls"
THEME_PROBE_SEEN = "exploreThemeProbeSeen"

#: The test chart page (#432): its path, its success marker, its chart's test-only ID
#: and its companion table's id.
CHART_PAGE = "/e2e-chart"
CHART_SUCCESS = "e2e-chart-ok"
CHART_ID = "X1"
CHART_TABLE = "e2e-chart-table"

#: The two-chart test page (#452): two charts on one page share one plotly.js load (C4
#: and C5 will, #436). Its path, success marker, the charts' test-only IDs and their
#: companion table's id.
TWO_CHARTS_PAGE = "/e2e-two-charts"
TWO_CHARTS_SUCCESS = "e2e-two-charts-ok"
TWO_CHART_IDS = ("X2", "X3")
TWO_CHARTS_TABLE = "e2e-two-charts-table"

#: The test chart's figure: two bar series told apart by a pattern, in the first two
#: series tokens.
CHART_FIGURE: dict[str, Any] = {
    "data": [
        {
            "type": "bar",
            "name": "First",
            "x": ["A", "B"],
            "y": [3, 5],
            "marker": {"color": "var(--chart-1)"},
            "hovertemplate": "%{x}: %{y} first<extra></extra>",
        },
        {
            "type": "bar",
            "name": "Second",
            "x": ["A", "B"],
            "y": [4, 2],
            "marker": {"color": "var(--chart-2)", "pattern": {"shape": "/"}},
            "hovertemplate": "%{x}: %{y} second<extra></extra>",
        },
    ],
    "layout": {"title": {"text": "A test chart"}},
}

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})

#: The keep-warm ping's body (D076). The refresher pings once a TTL has passed.
HEALTH_BODY: dict[str, Any] = {"status": "ok"}

#: The browser tests open a handful of pages; the production bucket (30 fills a minute)
#: would degrade a page now and then, so the bucket is the offline client's.
BUCKET_PER_MINUTE = 6000.0
BUCKET_BURST = 1000.0


def _host(address: Any) -> str | None:
    """The host of a socket address, or None for one with no host (a Unix path)."""
    if isinstance(address, tuple) and address:
        return str(address[0])
    return None


def _audit(event: str, args: tuple[Any, ...]) -> None:
    # Every socket audit event that names a remote host: forward and reverse lookups,
    # then connections and datagrams.
    if event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"):
        host = args[0]
    elif event == "socket.getnameinfo":
        host = _host(args[0])
    elif event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        host = _host(args[1])
    else:
        return
    if host is None:
        return
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host in LOOPBACK:
        return
    sys.stderr.write(f"{NETWORK_SENTINEL} {event} {host!r}\n")
    sys.stderr.flush()
    raise OSError(f"the e2e server refuses {event} to {host!r}")


def _fixture_client() -> Any:
    """A client answering every recorded path from its file, at the meta's version."""
    from explore import api
    from tests.dashboard_fixtures import FIXTURE_DIR, RECORDED_FILES

    on_disk = {path.name for path in FIXTURE_DIR.glob("*.json")}
    mapped = set(RECORDED_FILES.values())
    if mapped != on_disk:
        raise SystemExit(
            "tests/dashboard_fixtures.py and tests/fixtures/dashboard/ disagree: "
            f"unmapped {sorted(on_disk - mapped)}, missing {sorted(mapped - on_disk)}"
        )
    bodies = {
        path: json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        for path, name in RECORDED_FILES.items()
    }
    version = bodies[api.META_PATH]["provenance"]["snapshot_version"]

    def fixture_fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        api.build_url(path)  # a malformed path raises ValueError, as in production
        if path == api.HEALTH_PATH:
            return api.Response(body=HEALTH_BODY, version=None)
        if path not in bodies:
            raise api.ApiUnavailable(f"GET {path}: no recorded response")
        return api.Response(body=bodies[path], version=version)

    return api.Client(
        fetch=fixture_fetch,
        prefetch_paths=api.registered_prefetch_paths,
        bucket=api.TokenBucket(per_minute=BUCKET_PER_MINUTE, burst=BUCKET_BURST),
    )


def _add_theme_probe(appmod: Any) -> None:
    """Mirror the store holding the theme in effect into a hidden div (#359)."""
    from dash import Input, Output, clientside_callback, html

    from explore import components

    appmod.app.layout.children.append(html.Div(id=THEME_PROBE_ID, hidden=True))
    clientside_callback(
        "function (theme) {"
        f" window.{THEME_PROBE_CALLS} = (window.{THEME_PROBE_CALLS} || 0) + 1;"
        " if (theme === null || theme === undefined) {"
        " return window.dash_clientside.no_update; }"
        " var shown = getComputedStyle(document.documentElement).colorScheme;"
        f" window.{THEME_PROBE_SEEN} = (window.{THEME_PROBE_SEEN} || []).concat("
        "[[theme, shown]]);"
        " return theme; }",
        Output(THEME_PROBE_ID, "children"),
        Input(components.THEME_STORE_ID, "data"),
    )


def _add_chart_page() -> None:
    """Register the test chart page and its test-only registry row (#432)."""
    import dash
    from dash import html

    from explore import charts, components

    charts.CHARTS = {**charts.CHARTS, CHART_ID: charts.Chart(CHART_PAGE, CHART_TABLE)}

    def layout(**_query: Any) -> Any:
        return html.Div(
            [
                html.H1("Test chart"),
                components.chart(CHART_ID, CHART_FIGURE, CHART_TABLE, "A caption."),
                html.Table(
                    html.Tbody(html.Tr([html.Td("A"), html.Td("3")])), id=CHART_TABLE
                ),
            ],
            id=CHART_SUCCESS,
        )

    dash.register_page(
        "e2e_chart",
        path=CHART_PAGE,
        layout=layout,
        prefetch=(),
        on_miss=(),
        success=CHART_SUCCESS,
        nav=None,
    )

    charts.CHARTS = {
        **charts.CHARTS,
        **{c: charts.Chart(TWO_CHARTS_PAGE, TWO_CHARTS_TABLE) for c in TWO_CHART_IDS},
    }

    def two_charts(**_query: Any) -> Any:
        built = []
        for n, chart_id in enumerate(TWO_CHART_IDS, start=1):
            figure = json.loads(json.dumps(CHART_FIGURE))
            figure["layout"]["title"]["text"] = f"Test chart {n} of 2"
            built.append(
                components.chart(chart_id, figure, TWO_CHARTS_TABLE, "A caption.")
            )
        return html.Div(
            [
                html.H1("Two test charts"),
                *built,
                html.Table(
                    html.Tbody(html.Tr([html.Td("A"), html.Td("3")])),
                    id=TWO_CHARTS_TABLE,
                ),
            ],
            id=TWO_CHARTS_SUCCESS,
        )

    dash.register_page(
        "e2e_two_charts",
        path=TWO_CHARTS_PAGE,
        layout=two_charts,
        prefetch=(),
        on_miss=(),
        success=TWO_CHARTS_SUCCESS,
        nav=None,
    )


def main(port: int) -> None:
    sys.addaudithook(_audit)

    from werkzeug.serving import make_server

    from explore import api
    from explore import app as appmod

    api.CLIENT = _fixture_client()
    _add_theme_probe(appmod)
    _add_chart_page()

    # Explicit checks, never ``assert``: PYTHONOPTIMIZE, inherited from the parent's
    # environment, would strip them. Warmup always answers 200, even when its refresh
    # fails, so the fill is checked itself: ``refresh`` swaps a snapshot in only once
    # every prefetch path has filled.
    status = appmod.server.test_client().get("/_ah/warmup").status_code
    if status != 200 or api.CLIENT.snapshot is None:
        raise SystemExit(f"warmup ({status}) did not fill the cache from the fixtures")

    server = make_server("127.0.0.1", port, appmod.server, threaded=True)
    sys.stderr.write(f"{READY_LINE} {port}\n")
    sys.stderr.flush()
    server.serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]))
