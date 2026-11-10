"""Fixtures for the dashboard's browser tests (#321).

``dashboard_server`` starts ``serve.py`` once per session on a free loopback port and
stops it at session end; ``base_url`` points Playwright's ``page.goto`` at it. Every
test also gets :func:`_browser_guard`, which fails it on a request off the loopback host
or on a console error, at the 390 × 844 phone viewport #306 was checked at. The one
off-host address it answers is plotly.js's on its CDN (#432), fulfilled from the
installed file and counted: a test of a chart names exactly how many fetches it expects
with :data:`PLOTLYJS_FETCHES`, and every other test is held to a bound derived from the
chart registry (#433, D091): at most one fetch per document, and only from a path a
live registered chart's page template matches, whatever state the page rendered there.

pytest imports this module on every run, the default one included, so nothing here
starts a process or touches the network at import.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import BrowserContext, ConsoleMessage, Page, Route

from tests.e2e.dashboard_pages import CHUNK_ERROR_PREFIX, RESOURCE_ERROR, VIEWPORT
from tests.e2e.serve import NETWORK_SENTINEL, READY_LINE

REPO = Path(__file__).resolve().parents[2]
DASHBOARD = REPO / "dashboard"

#: The server imports Dash and fills its cache before it listens.
START_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 0.2
STOP_TIMEOUT_S = 5.0

#: The marker a test names a console error it causes on purpose with, in full, once per
#: occurrence: the guard below requires the test's console errors to be exactly the
#: named ones, each as many times as it is named, and no other (#325: a page whose own
#: document answers 404 logs Chrome's resource error once).
EXPECTED_CONSOLE_ERROR = "expected_console_error"


#: The marker a test names its plotly.js fetches with (#432): exactly how many requests
#: for the CDN address it expects, and ``abort=True`` to refuse them, as a blocked CDN
#: would, rather than fulfill them from the installed file. Without it, the guard
#: derives the bound (:func:`derived_fetch_problems`, #433), so a test that only passes
#: through a chart page needs no marker.
PLOTLYJS_FETCHES = "plotlyjs_fetches"

#: The marker a test aborts one of dcc's lazily loaded chunks with (#456), by its file
#: stem (``async-graph``, ``async-slider``), never by its webpack id: every request
#: from the app for that file is aborted and counted. The guard then holds the
#: requests and the ``ChunkLoadError`` lines each to between one and
#: :data:`CHUNK_ERROR_BOUND`, and takes one resource error per aborted request as
#: explained, rather than the test naming them, since how many a bounded failure makes
#: is Dash's and webpack's own detail.
ABORTED_CHUNK = "aborted_chunk"

#: The most requests, and the most ``ChunkLoadError`` lines, a failed chunk may make
#: (#456, D089). Dash 4.4.1 logged about 25 lines a second without end (D088); 4.5.0
#: makes one request and logs two. A different small number after a Dash upgrade
#: means re-read the failure, not a regression.
CHUNK_ERROR_BOUND = 4


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{EXPECTED_CONSOLE_ERROR}(text): one occurrence of a console error a "
        "browser test causes on purpose, matched in full",
    )
    config.addinivalue_line(
        "markers",
        f"{PLOTLYJS_FETCHES}(count, abort=False): how many times the test fetches "
        "plotly.js from its CDN address, fulfilled from the installed file or aborted",
    )
    config.addinivalue_line(
        "markers",
        f"{ABORTED_CHUNK}(stem): abort the app's requests for one of dcc's lazily "
        "loaded chunks, and hold its ChunkLoadError lines to CHUNK_ERROR_BOUND",
    )


def plotlyjs_url() -> str:
    """The CDN address the app sends graphs to: Dash's, from the installed plotly."""
    from explore import app as appmod

    url: str = appmod.app._plotlyjs_url
    return url


def plotlyjs_file() -> Path:
    """The installed plotly.js, which the guard serves for the CDN address."""
    import plotly  # type: ignore[import-untyped]

    return Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


#: Schemes a page uses without a request to any host: the CSV download link is a
#: ``data:`` URL (#309).
LOCAL_SCHEMES = frozenset({"data", "blob", "about"})


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture(scope="session")
def dashboard_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The dashboard served from recorded responses; yields its base URL.

    Ready means ``serve.py`` wrote :data:`READY_LINE` with this port: it writes that
    only once its cache is filled and its socket is bound, so another process that took
    the port in between fails the start (the child exits) instead of answering.
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    ready = f"{READY_LINE} {port}"
    stderr_path = tmp_path_factory.mktemp("e2e-server") / "stderr.log"
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(DASHBOARD), str(REPO)]),
    }
    with stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            [sys.executable, "-m", "tests.e2e.serve", str(port)],
            cwd=DASHBOARD,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
        )
        try:
            deadline = time.monotonic() + START_TIMEOUT_S
            while ready not in stderr_path.read_text(errors="replace"):
                if proc.poll() is not None:
                    pytest.fail(
                        f"the e2e server exited ({proc.returncode}) before it was ready:\n"
                        + stderr_path.read_text(errors="replace")
                    )
                if time.monotonic() > deadline:
                    pytest.fail(
                        f"the e2e server was not ready within {START_TIMEOUT_S}s:\n"
                        + stderr_path.read_text(errors="replace")
                    )
                time.sleep(POLL_INTERVAL_S)
            yield base
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=STOP_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    log = stderr_path.read_text(errors="replace")
    if NETWORK_SENTINEL in log:
        pytest.fail(f"the e2e server tried to reach the network:\n{log}")


@pytest.fixture(scope="session")
def base_url(dashboard_server: str) -> str:
    """Overrides pytest-playwright's ``base_url``, so ``page.goto("/")`` is ours."""
    return dashboard_server


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    return {**browser_context_args, "viewport": VIEWPORT}


def _off_host(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme not in LOCAL_SCHEMES and parts.hostname != "127.0.0.1"


def guard_problems(
    off_host: list[str],
    fetches: int,
    expected_fetches: int | None,
    errors: list[str],
    named: list[str],
) -> list[str]:
    """What the browser guard fails a test on, as a pure function so it can be tested
    without a browser (#432's acceptance gate, ``test_dashboard_e2e_guard.py``): a
    request off the loopback host; a plotly.js fetch count other than the test
    declared (``None``: the test declared none, and :func:`derived_fetch_problems`
    holds its fetches instead); and console errors other than those it named. A named
    error must occur exactly as often as it is named, so a second error with an
    expected text (another 404, or a repeat a loop would log, #452) fails too."""
    problems = []
    if off_host:
        problems.append(f"requests off the loopback host: {off_host}")
    if expected_fetches is not None and fetches != expected_fetches:
        problems.append(f"plotly.js fetched {fetches} times; expected {expected_fetches}")
    expected = Counter(named)
    seen = Counter(errors)
    if seen != expected:
        problems.append(
            f"console errors: {dict(seen)}; expected exactly: {dict(expected)}"
        )
    return problems


def page_pattern(template: str) -> re.Pattern[str]:
    """A Dash path template (``/election/<year>``) as a pattern over URL paths: each
    ``<variable>`` takes one or more characters, as Dash's greedy variable does."""
    parts = re.split(r"<[^>]+>", template)
    return re.compile(".+".join(re.escape(part) for part in parts))


def chart_page_patterns() -> list[re.Pattern[str]]:
    """The pages a live registered chart renders on (#433): from ``charts.CHARTS``."""
    from explore import charts

    return [
        page_pattern(row.page) for row in charts.CHARTS.values() if not row.retired
    ]


def derived_fetch_problems(
    fetches: Iterable[tuple[int, str]], chart_pages: Iterable[re.Pattern[str]]
) -> list[str]:
    """The plotly.js bound for a test that declares no count (#433, D091): each fetch,
    given as the document it was made in (a count of the main frame's document loads)
    and the path that document showed, must come from a path a live ``CHARTS`` row's
    template matches, whatever state the page rendered there, and no document may fetch
    twice (the mount callback loads plotly.js once per document, D088). So a test that
    only passes through a chart page needs no marker, and a path no chart's template
    matches may fetch nothing. A not-found or degraded render at a chart path is not
    told apart here: a test of one declares ``plotlyjs_fetches(0)`` (owner, #433)."""
    patterns = list(chart_pages)
    problems = []
    seen: set[int] = set()
    for document, path in fetches:
        if not any(pattern.fullmatch(path) for pattern in patterns):
            problems.append(f"plotly.js fetched by {path!r}, which renders no chart")
        if document in seen:
            problems.append(f"plotly.js fetched twice by one document ({path!r})")
        seen.add(document)
    return problems


def is_chunk(url: str, stem: str) -> bool:
    """Whether ``url`` is the app's request for dcc's chunk ``stem`` (its file is
    ``<stem>.js``, or ``<stem>.<fingerprint>.js`` where Dash fingerprints it)."""
    parts = urlsplit(url)
    name = parts.path.rsplit("/", 1)[-1]
    return (
        not _off_host(url)
        and "/dcc/" in parts.path
        and name.endswith(".js")
        and name.split(".", 1)[0] == stem
    )


def chunk_problems(
    stem: str | None, aborted: int, errors: list[str]
) -> tuple[list[str], list[str]]:
    """What the guard fails a test that aborts a chunk on, and the console errors left
    for :func:`guard_problems` to hold to the named ones (#456). Without the marker:
    nothing, and every error. With it: the chunk requested never, or more than
    :data:`CHUNK_ERROR_BOUND` times; fewer resource errors than aborted requests (one
    per aborted request is taken as explained, and removed); and no ``ChunkLoadError``
    line, or more than :data:`CHUNK_ERROR_BOUND`. The ``ChunkLoadError`` lines are
    removed too; anything else is left."""
    if stem is None:
        return [], errors
    problems = []
    if aborted == 0:
        problems.append(f"the {stem} chunk was never requested")
    if aborted > CHUNK_ERROR_BOUND:
        problems.append(
            f"the {stem} chunk was requested {aborted} times; "
            f"at most {CHUNK_ERROR_BOUND} (D089)"
        )
    chunk = [e for e in errors if e.startswith(CHUNK_ERROR_PREFIX)]
    rest = [e for e in errors if not e.startswith(CHUNK_ERROR_PREFIX)]
    explained = 0
    kept = []
    for error in rest:
        if error == RESOURCE_ERROR and explained < aborted:
            explained += 1
        else:
            kept.append(error)
    if explained < aborted:
        problems.append(
            f"{aborted} aborted {stem} requests but {explained} resource errors"
        )
    if not chunk:
        problems.append(f"the aborted {stem} chunk logged no ChunkLoadError")
    if len(chunk) > CHUNK_ERROR_BOUND:
        problems.append(
            f"the aborted {stem} chunk logged {len(chunk)} ChunkLoadError lines; "
            f"at most {CHUNK_ERROR_BOUND} (D089)"
        )
    return problems, kept


@pytest.fixture(autouse=True)
def _browser_guard(
    context: BrowserContext, page: Page, request: pytest.FixtureRequest
) -> Iterator[None]:
    """Fails the test on any request off the loopback host or any console error,
    except the ones it names with :data:`EXPECTED_CONSOLE_ERROR`, which must then occur
    exactly as many times as they are named.

    The route is on the context, so it covers every page the test opens. It sees only
    what the browser requests; ``serve.py``'s audit hook covers the server.
    """
    off_host: list[str] = []
    errors: list[str] = []
    cdn = plotlyjs_url()
    marker = request.node.get_closest_marker(PLOTLYJS_FETCHES)
    expected_fetches = marker.args[0] if marker else None
    abort = bool(marker and marker.kwargs.get("abort", False))
    fetches: list[tuple[int, str]] = []
    documents = [0]

    def on_document(_: Page) -> None:
        documents[0] += 1

    def refuse(route: Route) -> None:
        if route.request.url == cdn:
            frame = route.request.frame
            fetches.append((documents[0], urlsplit(frame.url).path))
            if abort:
                route.abort()
            else:
                route.fulfill(
                    path=plotlyjs_file(), content_type="application/javascript"
                )
            return
        off_host.append(route.request.url)
        route.abort()

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    context.route(_off_host, refuse)
    chunk_marker = request.node.get_closest_marker(ABORTED_CHUNK)
    stem: str | None = chunk_marker.args[0] if chunk_marker else None
    aborted: list[str] = []
    if stem is not None:

        def abort_chunk(route: Route) -> None:
            aborted.append(route.request.url)
            route.abort()

        context.route(lambda url: is_chunk(url, stem), abort_chunk)
    page.on("domcontentloaded", on_document)
    page.on("console", on_console)
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield
    named = [m.args[0] for m in request.node.iter_markers(EXPECTED_CONSOLE_ERROR)]
    problems, rest = chunk_problems(stem, len(aborted), errors)
    problems += guard_problems(off_host, len(fetches), expected_fetches, rest, named)
    if expected_fetches is None:
        problems += derived_fetch_problems(fetches, chart_page_patterns())
    assert problems == [], problems
