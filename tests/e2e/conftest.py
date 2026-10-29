"""Fixtures for the dashboard's browser tests (#321).

``dashboard_server`` starts ``serve.py`` once per session on a free loopback port and
stops it at session end; ``base_url`` points Playwright's ``page.goto`` at it. Every
test also gets :func:`_browser_guard`, which fails it on a request off the loopback host
or on a console error, at the 390 × 844 phone viewport #306 was checked at.

pytest imports this module on every run, the default one included, so nothing here
starts a process or touches the network at import.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import BrowserContext, ConsoleMessage, Page, Route

from tests.e2e.dashboard_pages import VIEWPORT
from tests.e2e.serve import NETWORK_SENTINEL, READY_LINE

REPO = Path(__file__).resolve().parents[2]
DASHBOARD = REPO / "dashboard"

#: The server imports Dash and fills its cache before it listens.
START_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 0.2
STOP_TIMEOUT_S = 5.0

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


@pytest.fixture(autouse=True)
def _browser_guard(context: BrowserContext, page: Page) -> Iterator[None]:
    """Fails the test on any request off the loopback host or any console error.

    The route is on the context, so it covers every page the test opens. It sees only
    what the browser requests; ``serve.py``'s audit hook covers the server.
    """
    off_host: list[str] = []
    errors: list[str] = []

    def refuse(route: Route) -> None:
        off_host.append(route.request.url)
        route.abort()

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    context.route(_off_host, refuse)
    page.on("console", on_console)
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield
    assert not off_host, f"requests off the loopback host: {off_host}"
    assert not errors, f"console errors: {errors}"
