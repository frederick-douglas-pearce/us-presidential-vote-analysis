"""The dashboard's behaviour: rendering, the degraded state, the cache and the redirect.

Offline: every test runs against the recorded ``/v1/meta`` fixture through a fake fetch,
and the autouse fixture below replaces the process client so no request to the app can
start a refresher that reaches the network. The structural guards (no ``usvote`` at
runtime, one API host, no data files, ``app.yaml`` pins) are in
``test_dashboard_guards.py``.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import http.client
import http.server
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import dash
import pytest
from dash.development.base_component import Component

from explore import api
from explore import app as appmod

#: Written out rather than imported from ``explore.config``: a test that read the host
#: from the module under test would move with it.
CANONICAL_HOST = "explore.us-presidential-election-center.org"
PUBLIC_API_BASE = "https://api.us-presidential-election-center.org"

#: The process client as the app built it, captured before any fixture replaces it.
PROCESS_CLIENT = api.CLIENT

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "dashboard" / "v1_meta.json"
META: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
VERSION: str = META["provenance"]["snapshot_version"]

#: Every recorded public API response, by path: what the registry coverage check
#: serves a page's reads from.
RECORDED: dict[str, dict[str, Any]] = {
    path: json.loads((FIXTURE.parent / name).read_text(encoding="utf-8"))
    for path, name in {
        "/v1/meta": "v1_meta.json",
        "/v1/elections": "v1_elections.json",
        "/v1/elections/1824": "v1_elections_1824.json",
    }.items()
}

#: The concrete value each templated page is rendered at, one per path variable. Each
#: must make the page read a path in :data:`RECORDED`.
PATH_VALUES = {"year": "1824"}

#: The Pages routing callback — the POST a browser makes to render a page's content.
ROUTING_POST: dict[str, Any] = {
    "output": ".._pages_content.children..._pages_store.data..",
    "outputs": [
        {"id": "_pages_content", "property": "children"},
        {"id": "_pages_store", "property": "data"},
    ],
    "inputs": [
        {"id": "_pages_location", "property": "pathname", "value": "/"},
        {"id": "_pages_location", "property": "search", "value": ""},
    ],
    "changedPropIds": ["_pages_location.pathname"],
    "state": [],
}


def home_layout() -> Any:
    return dash.page_registry["pages.home"]["layout"]


def home_module() -> Any:
    return dash.page_registry["pages.home"]["layout"].__globals__


def texts(node: Any) -> list[str]:
    """Every string in a rendered component tree, depth-first."""
    if node is None:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, (int, float)):
        return [str(node)]
    if isinstance(node, (list, tuple)):
        return [t for child in node for t in texts(child)]
    if isinstance(node, Component):
        return texts(getattr(node, "children", None))
    raise TypeError(f"unexpected node {node!r}")


def hrefs(node: Any) -> list[str]:
    if isinstance(node, (list, tuple)):
        return [h for child in node for h in hrefs(child)]
    if isinstance(node, Component):
        href = getattr(node, "href", None)
        own = [href] if href else []
        return own + hrefs(getattr(node, "children", None))
    return []


def fake_fetch(
    bodies: dict[str, dict[str, Any]], version: str = VERSION
) -> tuple[Any, list[str]]:
    calls: list[str] = []

    def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        calls.append(path)
        return api.Response(body=bodies[path], version=version)

    return fetch, calls


def failing_fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
    raise api.ApiUnavailable(f"GET {path}: HTTP 503 upstream said SECRET-DETAIL")


def offline_client(fetch: Any = None, **kwargs: Any) -> api.Client:
    if fetch is None:
        fetch, _ = fake_fetch({api.META_PATH: META})
    kwargs.setdefault("bucket", api.TokenBucket(per_minute=6000, burst=1000))
    kwargs.setdefault("max_request_wait", 1.0)
    # Long by default, so a refresher left running by a failing test sleeps quietly.
    kwargs.setdefault("retry_backoff", 3600)
    return api.Client(fetch=fetch, **kwargs)


class RecordingBucket(api.TokenBucket):
    """A real bucket that also records every acquire and the wait it was allowed."""

    def __init__(self) -> None:
        super().__init__(per_minute=6000, burst=1000)
        self.waits: list[float | None] = []

    def acquire(self, max_wait: float | None) -> None:
        self.waits.append(max_wait)
        super().acquire(max_wait)


@pytest.fixture(autouse=True)
def _offline_process_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "CLIENT", offline_client())


# --- rendering ---------------------------------------------------------------------


def sentinel_meta() -> dict[str, Any]:
    """META with a distinct value for every provenance field the page shows."""
    meta = copy.deepcopy(META)
    p = meta["provenance"]
    for key in (
        "ec_source_name",
        "ec_license",
        "source_name",
        "license",
        "census_source_name",
        "census_license",
    ):
        p[key] = f"SENTINEL-{key}"
    for key in ("ec_license_url", "license_url", "census_license_url"):
        p[key] = f"https://sentinel.example/{key}"
    p["snapshot_version"] = "SENTINEL-version"
    return meta


def list_items(node: Any) -> list[Any]:
    if isinstance(node, (list, tuple)):
        return [li for child in node for li in list_items(child)]
    if isinstance(node, Component):
        own = [node] if type(node).__name__ == "Li" else []
        return own + list_items(getattr(node, "children", None))
    return []


class TestRender:
    def test_each_source_line_pairs_its_name_with_its_own_license_link(self) -> None:
        """Every value comes from the response, and each link sits on its own line."""
        tree = home_module()["render"](sentinel_meta())
        by_label = {texts(li)[0]: li for li in list_items(tree) if "SENTINEL" in str(li)}
        expected = {
            "Electoral votes: ": ("ec_source_name", "ec_license", "ec_license_url"),
            "Popular votes: ": ("source_name", "license", "license_url"),
            "Population: ": ("census_source_name", "census_license", "census_license_url"),
        }
        assert set(by_label) == set(expected)
        for label, (name, lic, url) in expected.items():
            li = by_label[label]
            assert f"SENTINEL-{name} (" in texts(li)
            assert f"SENTINEL-{lic}" in texts(li)  # the link's text is the license
            assert hrefs(li) == [f"https://sentinel.example/{url}"]

    def test_coverage_years_are_read_from_the_response_not_literals(self) -> None:
        meta = copy.deepcopy(META)
        meta["provenance"]["coverage"] = {
            "year_min": 1788,
            "year_max": 2032,
            "pv_year_min": 1824,
            "pv_year_max": 2028,
        }
        text = " ".join(texts(home_module()["render"](meta)))
        assert "1788–2032" in text
        assert "1824–2028" in text
        assert "1976" not in text

    def test_shows_the_snapshot_version(self) -> None:
        assert "SENTINEL-version" in texts(home_module()["render"](sentinel_meta()))

    def test_the_link_preview_text_states_no_years(self) -> None:
        """The index never waits on the API, so it cannot carry a second coverage copy."""
        description = dash.page_registry["pages.home"]["description"]
        assert not any(ch.isdigit() for ch in description)

    def test_a_value_of_an_unexpected_type_renders_as_text(self) -> None:
        meta = copy.deepcopy(META)
        meta["provenance"]["license"] = {"not": "a string"}
        tree = home_module()["render"](meta)
        assert "{'not': 'a string'}" in texts(tree)

    def test_the_page_renders_through_the_routing_callback(self) -> None:
        client = appmod.server.test_client()
        response = client.post("/_dash-update-component", json=ROUTING_POST)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert VERSION in body
        assert META["provenance"]["source_name"] in body


class TestIndex:
    def test_the_index_carries_canonical_link_and_og_url(self) -> None:
        html = appmod.server.test_client().get("/").get_data(as_text=True)
        url = f"https://{CANONICAL_HOST}/"
        assert f'<link rel="canonical" href="{url}">' in html
        assert f'<meta property="og:url" content="{url}">' in html
        assert html.count('property="og:title"') == 1  # Pages emits it; we do not repeat

    def test_the_index_carries_no_data_and_never_calls_the_api(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch, calls = fake_fetch({api.META_PATH: META})
        client = offline_client(fetch)
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        html = appmod.server.test_client().get("/").get_data(as_text=True)
        assert VERSION not in html
        assert "validation_layout" not in html
        assert calls == []

    @pytest.mark.parametrize(
        "path",
        [
            '/%22%3E%3Cscript%3Ealert(1)%3C/script%3E%3Cx%20a=%22',
            "/%3Cimg%20src=x%20onerror=alert(1)%3E",
            "/'%3E%3Csvg%20onload=alert(1)%3E",
        ],
    )
    def test_a_hostile_path_is_never_reflected_as_markup(self, path: str) -> None:
        response = appmod.server.test_client().get(path)
        body = response.get_data(as_text=True)
        # The whole body, so Dash's own tags are covered as well as ours.
        for marker in ("<script>alert", "<img src=x", "<svg onload", '"><script'):
            assert marker not in body
        canonical = [ln for ln in body.splitlines() if 'rel="canonical"' in ln]
        assert len(canonical) == 1
        assert canonical[0].count('"') == 4  # rel="…" href="…": no quote broke out

    def test_responses_are_compressed(self) -> None:
        response = appmod.server.test_client().get(
            "/", headers={"Accept-Encoding": "gzip"}
        )
        assert response.headers.get("Content-Encoding") == "gzip"


# --- the degraded state ------------------------------------------------------------


class TestDegraded:
    @pytest.mark.parametrize(
        "error",
        [
            api.ApiUnavailable("GET /v1/meta: connection refused SECRET-DETAIL"),
            api.ApiUnavailable("GET /v1/meta: HTTP 503 SECRET-DETAIL"),
            api.ApiUnavailable("throttled: next fill in 9.0s SECRET-DETAIL"),
        ],
    )
    def test_an_unreadable_api_shows_a_plain_message(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            raise error

        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        text = " ".join(texts(home_layout()()))
        assert home_module()["UNAVAILABLE_MESSAGE"] in text
        assert "SECRET-DETAIL" not in text
        assert "Traceback" not in text

    def test_a_malformed_meta_body_shows_the_plain_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        broken = {"provenance": {"snapshot_version": VERSION}}  # no sources, no coverage
        fetch, _ = fake_fetch({api.META_PATH: broken})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        assert home_module()["UNAVAILABLE_MESSAGE"] in " ".join(texts(home_layout()()))

    def test_the_routing_callback_answers_200_with_the_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = offline_client(failing_fetch)
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        response = appmod.server.test_client().post(
            "/_dash-update-component", json=ROUTING_POST
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "isn't responding" in body
        assert "SECRET-DETAIL" not in body

    def test_a_warm_cache_keeps_serving_when_the_api_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        good, _ = fake_fetch({api.META_PATH: META})
        state = {"fetch": good}
        client = offline_client(lambda path, timeout: state["fetch"](path, timeout))
        client.refresh()
        state["fetch"] = failing_fetch
        monkeypatch.setattr(api, "CLIENT", client)
        assert VERSION in texts(home_layout()())


# --- fetch: the one outbound chokepoint ----------------------------------------------


class TestBuildUrl:
    @pytest.mark.parametrize(
        "path",
        ["/v1/meta", "/v1/elections", "/v1/elections/2000/summary", "/v1/states/OH"],
    )
    def test_builds_on_the_public_host(self, path: str) -> None:
        assert api.build_url(path) == PUBLIC_API_BASE + path

    def test_the_host_check_refuses_a_base_that_moved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scheme/host check, not only the path pattern, keeps requests on the host."""
        monkeypatch.setattr(api, "API_BASE", "https://usvote-api-x.a.run.app")
        with pytest.raises(ValueError):
            api.build_url("/v1/meta")
        monkeypatch.setattr(api, "API_BASE", "http://api.us-presidential-election-center.org")
        with pytest.raises(ValueError):
            api.build_url("/v1/meta")

    @pytest.mark.parametrize(
        "path",
        [
            "//evil.example/v1/meta",
            "https://usvote-api-abc.a.run.app/v1/meta",
            "v1/meta",
            "/v2/meta",
            "/health",
            "/v1//meta",
            "/v1/../health",
            "/v1/meta@evil.example",
            "/v1/meta#frag",
        ],
    )
    def test_refuses_anything_that_could_leave_the_host(self, path: str) -> None:
        with pytest.raises(ValueError):
            api.build_url(path)


class _FakeRaw:
    def __init__(
        self,
        status: int,
        body: bytes,
        etag: str | None,
        read_error: BaseException | None = None,
    ) -> None:
        self.status = status
        self.headers = {"ETag": etag} if etag else {}
        self._body = body
        self._read_error = read_error

    def read(self) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        return self._body

    def __enter__(self) -> _FakeRaw:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeOpener:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def open(self, request: urllib.request.Request, timeout: float) -> Any:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class TestFetch:
    def test_parses_the_body_and_the_etag_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = _FakeOpener(_FakeRaw(200, json.dumps(META).encode(), f'W/"{VERSION}"'))
        monkeypatch.setattr(api, "_OPENER", opener)
        response = api.fetch("/v1/meta")
        assert response.body == META
        assert response.version == VERSION
        assert opener.requests[0].full_url == api.build_url("/v1/meta")

    def test_sends_its_own_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The API's Cloudflare front answers 403 to urllib's default
        # "Python-urllib/3.x" User-Agent (observed 2026-09-30), so the header is
        # load-bearing, not cosmetic.
        opener = _FakeOpener(_FakeRaw(200, b"{}", None))
        monkeypatch.setattr(api, "_OPENER", opener)
        api.fetch("/v1/meta")
        agent = opener.requests[0].get_header("User-agent")
        assert agent == "usvote-explore"

    @pytest.mark.parametrize(
        "result",
        [
            urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None),  # type: ignore[arg-type]
            urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None),  # type: ignore[arg-type]
            urllib.error.HTTPError("u", 302, "Found", {}, None),  # type: ignore[arg-type]
            urllib.error.URLError("connection refused"),
            TimeoutError("timed out"),
            _FakeRaw(200, b"<html>not json</html>", None),
            _FakeRaw(200, b"[1, 2]", None),
            _FakeRaw(204, b"", None),
            # http.client errors urllib re-raises unwrapped (not OSError):
            http.client.BadStatusLine("garbage"),
            http.client.LineTooLong("header line"),
            _FakeRaw(200, b"{}", None, read_error=http.client.IncompleteRead(b"{")),
            RuntimeError("anything else at the I/O boundary"),
        ],
    )
    def test_every_failure_becomes_api_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, result: Any
    ) -> None:
        monkeypatch.setattr(api, "_OPENER", _FakeOpener(result))
        with pytest.raises(api.ApiUnavailable):
            api.fetch("/v1/meta")

    def test_every_fetch_is_bounded_by_the_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener = _FakeOpener(_FakeRaw(200, b"{}", None))
        monkeypatch.setattr(api, "_OPENER", opener)
        api.fetch("/v1/meta")
        api.fetch("/v1/meta", timeout=1.5)
        assert opener.timeouts == [15.0, 1.5]
        assert api.FETCH_TIMEOUT_S == 15.0

    def test_an_off_host_path_is_a_loud_error_not_an_unavailable_api(self) -> None:
        with pytest.raises(ValueError):
            api.fetch("//evil.example/v1/meta")

    @pytest.mark.parametrize(
        ("etag", "version"),
        [(f'"{VERSION}"', VERSION), (f'W/"{VERSION}"', VERSION), (None, None), ("", None)],
    )
    def test_etag_version(self, etag: str | None, version: str | None) -> None:
        assert api.etag_version(etag) == version


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 — the stdlib's name
        _RedirectHandler.hits.append(self.path)
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

    def log_message(self, *args: object) -> None:
        return None


@pytest.fixture
def redirect_server() -> Iterator[str]:
    _RedirectHandler.hits = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class TestOpener:
    def test_follows_no_redirect(self, redirect_server: str) -> None:
        with pytest.raises(urllib.error.HTTPError) as caught:
            api._OPENER.open(f"{redirect_server}/start", timeout=5)
        assert caught.value.code == 302
        assert _RedirectHandler.hits == ["/start"]  # /elsewhere was never requested

    def test_the_process_opener_has_no_proxy_and_no_redirect_handling(self) -> None:
        """The opener fetch uses: no ProxyHandler at all, and only the refusing redirect."""
        handlers = api._OPENER.handlers  # type: ignore[attr-defined]
        assert not [h for h in handlers if isinstance(h, urllib.request.ProxyHandler)]
        redirects = [
            h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)
        ]
        assert redirects and all(isinstance(h, api._NoRedirect) for h in redirects)

    def test_honours_no_proxy_variable(
        self, monkeypatch: pytest.MonkeyPatch, redirect_server: str
    ) -> None:
        # The local server doubles as a proxy that records what reaches it.
        monkeypatch.setenv("http_proxy", redirect_server)
        monkeypatch.setenv("HTTP_PROXY", redirect_server)
        with pytest.raises(urllib.error.URLError):
            api.build_opener().open("http://unresolvable.invalid/probe", timeout=5)
        assert _RedirectHandler.hits == []

    def test_the_proxy_check_can_fail(
        self, monkeypatch: pytest.MonkeyPatch, redirect_server: str
    ) -> None:
        """Non-vacuity: urllib's default opener does route through the same proxy."""
        monkeypatch.setenv("http_proxy", redirect_server)
        monkeypatch.setenv("HTTP_PROXY", redirect_server)
        urllib.request.build_opener().open("http://unresolvable.invalid/probe", timeout=5)
        assert _RedirectHandler.hits == ["http://unresolvable.invalid/probe"]


# --- the cache -----------------------------------------------------------------------


class TestCache:
    def test_a_cold_get_is_filled_by_the_refresher_then_served_from_cache(self) -> None:
        threads: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            threads.append(threading.current_thread().name)
            return api.Response(body=META, version=VERSION)

        client = offline_client(fetch, ttl=3600)
        assert client.get(api.META_PATH) == META
        assert client.get(api.META_PATH) == META
        assert threads == ["explore-refresher"]  # never on the visitor's thread

    def test_a_cold_view_sets_no_wake_up(self) -> None:
        """AC6: no wake-up from a cold visitor, so a cold start costs one /v1/meta.

        The test above cannot see a second /v1/meta: after a successful refresh a
        wake-up is answered only after ``min_recheck`` (30 s). This one watches the
        wake-up itself.
        """
        setters: list[str] = []

        class RecordingEvent(threading.Event):
            def set(self) -> None:
                setters.append(threading.current_thread().name)
                super().set()

        client = offline_client(ttl=3600)
        client._wake = RecordingEvent()
        assert client.get(api.META_PATH) == META
        assert setters == []

    def test_a_cold_get_with_a_dead_api_gives_up_within_the_bound(self) -> None:
        threads: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            threads.append(threading.current_thread().name)
            raise api.ApiUnavailable("down")

        client = offline_client(fetch, max_request_wait=0.3, retry_backoff=3600)
        started = time.monotonic()
        with pytest.raises(api.ApiUnavailable):
            client.get(api.META_PATH)
        assert time.monotonic() - started < 1.0
        assert set(threads) == {"explore-refresher"}

    def test_cold_visitors_are_not_serialized_behind_a_slow_api(self) -> None:
        """Eight visitors against an API that hangs: each gives up at the bound."""
        release = threading.Event()

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            release.wait(10)
            raise api.ApiUnavailable("slow, then down")

        client = offline_client(fetch, max_request_wait=0.3, retry_backoff=3600)
        elapsed: list[float] = []
        lock = threading.Lock()

        def visit() -> None:
            started = time.monotonic()
            with contextlib.suppress(api.ApiUnavailable):
                client.get(api.META_PATH)
            with lock:
                elapsed.append(time.monotonic() - started)

        visitors = [threading.Thread(target=visit) for _ in range(8)]
        for v in visitors:
            v.start()
        for v in visitors:
            v.join(5)
        release.set()
        assert len(elapsed) == 8
        assert max(elapsed) < 1.5  # serialized, they would take 8 × the hang

    def test_a_new_version_prefetches_into_a_new_snapshot_and_swaps_once(self) -> None:
        bodies = {api.META_PATH: META, "/v1/elections": {"data": []}}
        state = {"version": VERSION}
        calls: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls.append(path)
            body = copy.deepcopy(bodies[path])
            if path == api.META_PATH:
                body["provenance"]["snapshot_version"] = state["version"]
            return api.Response(body=body, version=state["version"])

        client = offline_client(fetch, prefetch_paths=lambda: ["/v1/elections"])
        first = client.refresh()
        assert set(first.responses) == {api.META_PATH, "/v1/elections"}
        assert client.refresh() is first  # same version: no prefetch, no swap
        assert calls == [api.META_PATH, "/v1/elections", api.META_PATH]

        state["version"] = "next-version"
        second = client.refresh()
        assert second is not first
        assert client.snapshot is second
        assert second.version == "next-version"
        assert first.version == VERSION  # the old snapshot was replaced, not mutated

    def test_the_swap_happens_once_after_every_prefetch_succeeds(self) -> None:
        """Two prefetch paths, the second failing: nothing half-filled is ever served."""
        state = {"version": VERSION}
        failing = {"on": False}
        seen_during_prefetch: list[Any] = []
        holder: dict[str, api.Client] = {}

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path != api.META_PATH:
                seen_during_prefetch.append(holder["client"].snapshot)
                if path == "/v1/two" and failing["on"]:
                    raise api.ApiUnavailable("boom")
            body: dict[str, Any] = (
                copy.deepcopy(META) if path == api.META_PATH else {"path": path}
            )
            if path == api.META_PATH:
                body["provenance"]["snapshot_version"] = state["version"]
            return api.Response(body=body, version=state["version"])

        client = offline_client(fetch, prefetch_paths=lambda: ["/v1/one", "/v1/two"])
        holder["client"] = client
        first = client.refresh()
        assert set(first.responses) == {api.META_PATH, "/v1/one", "/v1/two"}
        assert seen_during_prefetch == [None, None]  # not swapped in mid-loop

        seen_during_prefetch.clear()
        state["version"] = "next-version"
        failing["on"] = True
        with pytest.raises(api.ApiUnavailable):
            client.refresh()
        assert client.snapshot is first
        assert all(snap is first for snap in seen_during_prefetch)

    def test_a_failed_prefetch_leaves_the_old_snapshot_serving(self) -> None:
        state = {"version": VERSION}
        failing = {"on": False}

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == "/v1/elections" and failing["on"]:
                raise api.ApiUnavailable("boom")
            body = copy.deepcopy(META) if path == api.META_PATH else {"data": []}
            if path == api.META_PATH:
                body["provenance"]["snapshot_version"] = state["version"]
            return api.Response(body=body, version=state["version"])

        client = offline_client(fetch, prefetch_paths=lambda: ["/v1/elections"])
        first = client.refresh()
        state["version"] = "next-version"
        failing["on"] = True
        with pytest.raises(api.ApiUnavailable):
            client.refresh()
        assert client.snapshot is first

    def test_a_prefetch_answering_for_another_version_is_not_swapped_in(self) -> None:
        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == api.META_PATH:
                return api.Response(body=META, version=VERSION)
            return api.Response(body={"data": []}, version="some-other-version")

        client = offline_client(fetch, prefetch_paths=lambda: ["/v1/elections"])
        with pytest.raises(api.ApiUnavailable):
            client.refresh()
        assert client.snapshot is None

    def test_a_fill_on_miss_is_stored_only_under_its_own_version(self) -> None:
        state = {"version": VERSION}

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            body = META if path == api.META_PATH else {"path": path}
            return api.Response(body=body, version=state["version"])

        client = offline_client(fetch)
        client.refresh()
        client.get("/v1/elections")
        assert client.snapshot is not None
        assert "/v1/elections" in client.snapshot.responses

        state["version"] = "next-version"
        with pytest.raises(api.ApiUnavailable):  # never a foreign-version body
            client.get("/v1/elections/2000")
        assert "/v1/elections/2000" not in client.snapshot.responses
        assert client._wake.is_set()  # the refresher is nudged to swap in the new version

    def test_the_process_client_prefetches_what_pages_register(self) -> None:
        assert PROCESS_CLIENT._prefetch_paths is api.registered_prefetch_paths
        assert api.registered_prefetch_paths() == [api.META_PATH]

    def test_every_fill_passes_the_bucket_with_the_right_wait(self) -> None:
        bucket = RecordingBucket()
        fetch, calls = fake_fetch(
            {api.META_PATH: META, "/v1/one": {"x": 1}, "/v1/miss": {"x": 2}}
        )
        client = offline_client(
            fetch, bucket=bucket, prefetch_paths=lambda: ["/v1/one"]
        )
        client.refresh()
        assert bucket.waits == [None, None]  # the refresher waits as long as it needs
        client.get("/v1/miss")
        assert bucket.waits[:2] == [None, None]
        visitor_wait = bucket.waits[2]
        # What is left of the render's deadline: bounded, never unlimited.
        assert visitor_wait is not None
        assert 0 < visitor_wait <= client._max_request_wait
        assert len(bucket.waits) == len(calls)  # one acquire per API call

    def test_the_process_client_uses_the_pinned_bucket(self) -> None:
        bucket = PROCESS_CLIENT._bucket
        assert (bucket._rate, bucket._burst) == (30.0 / 60.0, 10.0)
        assert PROCESS_CLIENT._max_request_wait == 2.0
        assert (api.FILLS_PER_MINUTE, api.FILL_BURST, api.MAX_REQUEST_WAIT_S) == (
            30.0,
            10.0,
            2.0,
        )


def component_ids(node: Any) -> set[str]:
    """Every ``id`` in a rendered component tree."""
    if isinstance(node, (list, tuple)):
        return {i for child in node for i in component_ids(child)}
    if isinstance(node, Component):
        own = getattr(node, "id", None)
        return ({own} if isinstance(own, str) else set()) | component_ids(
            getattr(node, "children", None)
        )
    return set()


def concrete_values(page: dict[str, Any]) -> dict[str, str]:
    """The path variables a templated page is rendered with; ``{}`` for a plain page."""
    names = re.findall(r"<(.*?)>", page.get("path_template") or "")
    return {name: PATH_VALUES[name] for name in names}


class RecordingView:
    """A view that serves recorded responses by path, and records every read."""

    def __init__(self, reads: list[str]) -> None:
        self.reads = reads

    def __enter__(self) -> RecordingView:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, path: str) -> dict[str, Any]:
        self.reads.append(path)
        if path not in RECORDED:
            raise api.ApiUnavailable(f"no recorded response for {path}")
        return copy.deepcopy(RECORDED[path])


class RecordingClient:
    """Exposes only ``view()``: a page reading ``CLIENT.get`` directly fails here."""

    def __init__(self) -> None:
        self.reads: list[str] = []
        self.views = 0

    def view(self) -> RecordingView:
        self.views += 1
        return RecordingView(self.reads)


def coverage_problems(
    page: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], list[str]]:
    """Render one page from recorded responses; return its problems and its reads."""
    client = RecordingClient()
    monkeypatch.setattr(api, "CLIENT", client)
    values = concrete_values(page)
    rendered = page["layout"](**values)
    declared = set(page.get("prefetch", ())) | {
        template.format(**values) for template in page.get("on_miss", ())
    }
    problems = [f"undeclared read {path}" for path in client.reads if path not in declared]
    if client.views > 1:  # each view pins its own snapshot: one render, one view
        problems.append(f"opened {client.views} views")
    marker = page.get("success")
    if not marker:
        problems.append("no success marker declared")
    elif marker not in component_ids(rendered):
        problems.append(f"success marker {marker!r} not rendered")
    return problems, client.reads


def _fake_year_layout(year: str | None = None, **_query: Any) -> Any:
    # Formats the path variable unvalidated: fine for a coverage check at a known value,
    # but not a pattern to copy. A real page validates it first (#312, item 6).
    with api.CLIENT.view() as view:
        body = view.get(f"/v1/elections/{year}")
    return dash.html.Div(str(len(body)), id="fake-year")


FAKE_YEAR_PAGE: dict[str, Any] = {
    "path": "/election/none",
    "path_template": "/election/<year>",
    "prefetch": (),
    "on_miss": ("/v1/elections/{year}",),
    "success": "fake-year",
    "layout": _fake_year_layout,
}


class TestRegistryCoverage:
    """AC5: every path a render reads is declared, as prefetched or filled on a miss."""

    def test_every_registered_page_reads_only_what_it_declares(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads: list[str] = []
        for name, page in dash.page_registry.items():
            problems, page_reads = coverage_problems(page, monkeypatch)
            assert problems == [], (name, problems)
            reads += page_reads
        assert reads, "no page read anything; the check would be vacuous"

    def test_every_path_variable_has_a_concrete_value(self) -> None:
        for page in dash.page_registry.values():
            names = re.findall(r"<(.*?)>", page.get("path_template") or "")
            assert set(names) <= set(PATH_VALUES), page["module"]

    def test_the_process_client_prefetches_only_declared_paths(self) -> None:
        declared = {p for page in dash.page_registry.values() for p in page["prefetch"]}
        assert set(api.registered_prefetch_paths()) == declared

    def test_a_templated_page_is_rendered_at_a_concrete_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        problems, reads = coverage_problems(FAKE_YEAR_PAGE, monkeypatch)
        assert problems == []
        assert reads == ["/v1/elections/1824"]  # rendered, not skipped

    @pytest.mark.parametrize(
        ("change", "problem"),
        [
            ({"on_miss": ()}, "undeclared read /v1/elections/1824"),
            ({"success": None}, "no success marker declared"),
            ({"success": "absent-id"}, "success marker 'absent-id' not rendered"),
        ],
    )
    def test_the_check_fails_an_undeclared_read_or_a_missing_marker(
        self, monkeypatch: pytest.MonkeyPatch, change: dict[str, Any], problem: str
    ) -> None:
        problems, _ = coverage_problems({**FAKE_YEAR_PAGE, **change}, monkeypatch)
        assert problems == [problem]

    def test_a_page_opening_two_views_in_one_render_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def layout(**_query: Any) -> Any:
            first = api.CLIENT.view().get(api.META_PATH)
            second = api.CLIENT.view().get(api.META_PATH)  # may be another snapshot
            return dash.html.Div([str(len(first)), str(len(second))], id="two-views")

        page = {
            "path": "/two-views",
            "prefetch": (api.META_PATH,),
            "on_miss": (),
            "success": "two-views",
            "layout": layout,
        }
        problems, _ = coverage_problems(page, monkeypatch)
        assert problems == ["opened 2 views"]

    def test_a_page_reading_client_get_directly_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def layout(**_query: Any) -> Any:
            return api.CLIENT.get(api.META_PATH)

        page = {**FAKE_YEAR_PAGE, "path_template": None, "layout": layout}
        with pytest.raises(AttributeError):
            coverage_problems(page, monkeypatch)


# --- pages read only through a view (AC1) ---------------------------------------------

PAGES = sorted((Path(api.__file__).parent / "pages").rglob("*.py"))


#: The ``api.<name>`` a page may use. None of them reads data except ``CLIENT``, and
#: that only as the receiver of ``.view``. ``fetch``, ``Client``, ``View``, ``_OPENER``
#: and ``build_url`` would read past the view, the cache and the throttle.
PAGE_API_NAMES = {"CLIENT", "ApiUnavailable", "META_PATH", "ELECTIONS_PATH"}


def client_misuses(source: str) -> list[int]:
    """Lines where a page reaches ``explore.api`` other than through ``CLIENT.view``.

    Pages import the module (``from explore import api``) and name what they use as
    ``api.<name>``. Flagged: a name outside :data:`PAGE_API_NAMES`; ``CLIENT`` other
    than as the receiver of ``.view``; ``api`` other than as the receiver of an
    attribute (``getattr(api, …)``, ``f = api``); any ``from explore.api import …``,
    absolute or relative; and any ``import explore.api``. A module imported under
    another name (``from explore import api as x``) is not tracked.
    """
    tree = ast.parse(source)
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    lines: list[int] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.ImportFrom) and (
            node.module == "explore.api"
            or (node.level > 0 and (node.module or "").split(".")[-1] == "api")
        ):
            lines.append(line)
            continue
        if isinstance(node, ast.Import) and any(
            alias.name == "explore.api" for alias in node.names
        ):
            lines.append(line)
            continue
        if (
            isinstance(node, ast.Name)
            and node.id == "api"
            and not isinstance(parents.get(node), ast.Attribute)
        ):
            lines.append(line)
            continue
        if isinstance(node, ast.alias) and "CLIENT" in (node.name, node.asname):
            lines.append(line)
            continue
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "api"
            and node.attr not in PAGE_API_NAMES
        ):
            lines.append(line)
            continue
        named = (isinstance(node, ast.Name) and node.id == "CLIENT") or (
            isinstance(node, ast.Attribute) and node.attr == "CLIENT"
        )
        if not named:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.attr == "view":
            continue
        lines.append(line)
    return lines


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_pages_read_only_through_a_render_scoped_view(path: Path) -> None:
    assert client_misuses(path.read_text(encoding="utf-8")) == []


def test_the_pages_lint_sees_at_least_one_page() -> None:
    assert any("CLIENT.view" in p.read_text(encoding="utf-8") for p in PAGES)


@pytest.mark.parametrize(
    ("source", "misused"),
    [
        ("with api.CLIENT.view() as v:\n    v.get(p)\n", False),
        ("api.CLIENT.view().get(p)\n", False),
        ("api.CLIENT.get(p)\n", True),
        ("c = api.CLIENT\nc.get(p)\n", True),
        ("from explore.api import CLIENT\n", True),
        ("getattr(api.CLIENT, 'get')(p)\n", True),
        ("CLIENT.get(p)\n", True),
        ("try:\n    pass\nexcept api.ApiUnavailable:\n    pass\n", False),
        ("v.get(api.META_PATH)\n", False),
        ("api.fetch(p)\n", True),
        ("api.Client().get(p)\n", True),
        ("api._OPENER.open(r)\n", True),
        ("api.build_url(p)\n", True),
        ("from explore.api import fetch\n", True),
        ("from explore import api\n", False),
        ("from ..api import fetch\n", True),
        ("import explore.api\nexplore.api.fetch(p)\n", True),
        ("getattr(api, 'fetch')(p)\n", True),
        ("f = api\nf.fetch(p)\n", True),
    ],
)
def test_the_pages_lint_flags_what_it_should(source: str, misused: bool) -> None:
    assert bool(client_misuses(source)) is misused


# --- one snapshot per render (AC1) and one deadline per render (AC3) ------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def versioned_fetch(
    state: dict[str, Any], calls: list[tuple[str, float]] | None = None
) -> Callable[..., api.Response]:
    """Answers every path for ``state["version"]``; ``/v1/meta`` names it too."""

    def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        if calls is not None:
            calls.append((path, timeout))
        if path == api.META_PATH:
            body = copy.deepcopy(META)
            body["provenance"]["snapshot_version"] = state["version"]
        else:
            body = {"path": path, "version": state["version"]}
        return api.Response(body=body, version=state["version"])

    return fetch


class TestView:
    def test_two_reads_answer_from_the_snapshot_the_render_started_with(self) -> None:
        state = {"version": VERSION}
        client = offline_client(
            versioned_fetch(state), prefetch_paths=lambda: ["/v1/a", "/v1/b"]
        )
        client.refresh()
        with client.view() as view:
            first = view.get("/v1/a")
            state["version"] = "next-version"
            client.refresh()  # the swap lands between the render's two reads
            assert client.snapshot is not None
            assert client.snapshot.version == "next-version"
            second = view.get("/v1/b")
        assert first["version"] == second["version"] == VERSION
        assert view.version == VERSION

    def test_a_miss_for_the_pinned_version_is_stored_in_the_pinned_snapshot(
        self,
    ) -> None:
        state = {"version": VERSION}
        client = offline_client(versioned_fetch(state))
        client.refresh()
        with client.view() as view:
            body = view.get("/v1/miss")
        assert client.snapshot is not None
        assert client.snapshot.responses["/v1/miss"] is body

    def test_a_miss_answering_another_version_raises_and_wakes_the_refresher(
        self,
    ) -> None:
        state = {"version": VERSION}
        client = offline_client(versioned_fetch(state))
        client.refresh()
        pinned = client.snapshot
        assert pinned is not None
        view = client.view()
        state["version"] = "next-version"  # the edge has moved on; the cache has not
        with pytest.raises(api.ApiUnavailable):
            view.get("/v1/miss")
        assert "/v1/miss" not in pinned.responses
        assert client._wake.is_set()

    def test_a_render_pinned_before_a_swap_hands_its_miss_to_the_new_snapshot(
        self,
    ) -> None:
        state = {"version": VERSION}
        client = offline_client(versioned_fetch(state))
        client.refresh()
        view = client.view()
        state["version"] = "next-version"
        client.refresh()
        with pytest.raises(api.ApiUnavailable):  # still never mixed into this render
            view.get("/v1/miss")
        assert client.snapshot is not None
        assert client.snapshot.responses["/v1/miss"]["version"] == "next-version"
        assert client._wake.is_set()  # still woken, as AC1 asks

    def test_a_cold_view_with_a_dead_api_raises_within_the_deadline(self) -> None:
        client = offline_client(failing_fetch, max_request_wait=0.3)
        started = time.monotonic()
        with pytest.raises(api.ApiUnavailable):
            client.view()
        assert time.monotonic() - started < 1.0


class TestRenderDeadline:
    def test_misses_in_one_render_share_one_deadline(self) -> None:
        clock = FakeClock()
        calls: list[tuple[str, float]] = []
        state = {"version": VERSION}
        bucket = RecordingBucket()
        client = offline_client(
            versioned_fetch(state, calls),
            bucket=bucket,
            clock=clock,
            max_request_wait=api.MAX_REQUEST_WAIT_S,
        )
        client.refresh()
        calls.clear()
        bucket.waits.clear()

        view = client.view()  # deadline = 0 + MAX_REQUEST_WAIT_S (2.0)
        view.get("/v1/one")
        clock.now = 1.2  # the first miss took most of the budget
        view.get("/v1/two")
        clock.now = 1.6  # 0.4 left: under MIN_USEFUL_FETCH_S, so not even tried
        with pytest.raises(api.ApiUnavailable):
            view.get("/v1/three")
        assert [path for path, _ in calls] == ["/v1/one", "/v1/two"]  # never fetched
        assert calls[0][1] == api.VISITOR_FETCH_TIMEOUT_S  # the cap, 1.5 < 2.0 left
        assert calls[1][1] == pytest.approx(0.8)  # what remained of the render
        # Each token wait leaves MIN_USEFUL_FETCH_S of the deadline for its fetch.
        assert bucket.waits == [pytest.approx(1.5), pytest.approx(0.3)]

    def advancing_client(
        self, per_minute: float, calls: list[tuple[str, float]]
    ) -> tuple[api.Client, FakeClock, api.TokenBucket]:
        """A warm client whose emptied bucket sleeps by advancing the fake clock."""
        clock = FakeClock()
        client = offline_client(
            versioned_fetch({"version": VERSION}, calls),
            clock=clock,
            max_request_wait=api.MAX_REQUEST_WAIT_S,
        )
        client.refresh()
        calls.clear()

        def advance(seconds: float) -> None:
            clock.now += seconds

        bucket = api.TokenBucket(
            per_minute=per_minute, burst=1, clock=clock, sleep=advance
        )
        bucket.acquire(None)  # empty: the next token comes at the bucket's rate
        client._bucket = bucket
        return client, clock, bucket

    def test_the_token_wait_and_the_fetch_share_the_deadline(self) -> None:
        calls: list[tuple[str, float]] = []
        client, clock, _ = self.advancing_client(60.0, calls)  # a token per second
        client.view().get("/v1/miss")
        assert clock.now == pytest.approx(1.0)  # waited for the token
        assert [path for path, _ in calls] == ["/v1/miss"]
        assert calls[0][1] == pytest.approx(1.0)  # 2.0 − 1.0, not the 1.5 cap

    def test_a_token_wait_past_the_floor_takes_no_token_and_fetches_nothing(
        self,
    ) -> None:
        calls: list[tuple[str, float]] = []
        # One token per 1.67 s: inside the render's 2.0 s, so only the floor refuses it.
        client, clock, bucket = self.advancing_client(36.0, calls)
        with pytest.raises(api.ApiUnavailable):
            client.view().get("/v1/miss")  # 1.67 s > 2.0 − MIN_USEFUL_FETCH_S
        assert calls == []
        assert clock.now == 0.0  # did not wait
        assert bucket._tokens == pytest.approx(0.0)  # reserved nothing

    def test_the_cold_wait_draws_on_the_render_deadline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = FakeClock()
        calls: list[tuple[str, float]] = []
        client = offline_client(
            versioned_fetch({"version": VERSION}, calls),
            clock=clock,
            max_request_wait=api.MAX_REQUEST_WAIT_S,
        )
        waits: list[float | None] = []

        class ColdReady:
            """The refresher's first snapshot arrives 1.2 s into the render."""

            def wait(self, timeout: float | None = None) -> bool:
                waits.append(timeout)
                clock.now += 1.2
                client.refresh()
                return True

            def set(self) -> None:
                pass

        monkeypatch.setattr(client, "_ready", ColdReady())
        monkeypatch.setattr(client, "ensure_refresher", lambda: None)
        view = client.view()
        calls.clear()
        view.get("/v1/miss")
        assert waits == [api.MAX_REQUEST_WAIT_S]
        assert [path for path, _ in calls] == ["/v1/miss"]
        assert calls[0][1] == pytest.approx(0.8)  # 2.0 − 1.2, not 1.5

    def test_the_refresher_keeps_the_long_timeout(self) -> None:
        calls: list[tuple[str, float]] = []
        client = offline_client(
            versioned_fetch({"version": VERSION}, calls),
            prefetch_paths=lambda: ["/v1/a"],
        )
        client.refresh()
        assert calls == [
            (api.META_PATH, api.FETCH_TIMEOUT_S),
            ("/v1/a", api.FETCH_TIMEOUT_S),
        ]

    def test_the_visitor_bounds_fit_the_first_data_budget(self) -> None:
        # D071(g): first data within 3 s, and a visitor's fill gives up sooner than the
        # refresher's.
        assert api.VISITOR_FETCH_TIMEOUT_S < api.FETCH_TIMEOUT_S
        assert api.VISITOR_FETCH_TIMEOUT_S <= api.MAX_REQUEST_WAIT_S < 3.0
        assert PROCESS_CLIENT._visitor_fetch_timeout == api.VISITOR_FETCH_TIMEOUT_S
        assert api.MIN_USEFUL_FETCH_S == 0.5 < api.VISITOR_FETCH_TIMEOUT_S


# --- wake-ups after a successful refresh (AC2, AC6) -----------------------------------


class TestWakeInterval:
    def make(self, clock: FakeClock, sleeps: list[float], **kwargs: Any) -> api.Client:
        # Short, so a regression that drops a wake-up fails at once instead of
        # blocking for the 300 s TTL. A wake-up that is set returns immediately.
        kwargs.setdefault("ttl", 0.05)
        return offline_client(
            versioned_fetch({"version": VERSION}),
            clock=clock,
            sleep=sleeps.append,
            min_recheck=30.0,
            **kwargs,
        )

    def test_refresh_stamps_the_start_of_its_meta_check(self) -> None:
        clock = FakeClock()
        sleeps: list[float] = []
        inner = versioned_fetch({"version": VERSION})

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == api.META_PATH:
                clock.now += 3.0  # the check takes 3 s
            return inner(path, timeout)

        client = offline_client(fetch, clock=clock, sleep=sleeps.append)
        clock.now = 7.0
        client.refresh()
        assert client._last_check == 7.0  # its start, not 10.0
        clock.now = 50.0
        client.refresh()  # same version: still a successful check
        assert client._last_check == 50.0

    def test_a_failed_refresh_does_not_stamp(self) -> None:
        clock = FakeClock()
        client = offline_client(failing_fetch, clock=clock)
        with pytest.raises(api.ApiUnavailable):
            client.refresh()
        assert client._last_check is None

    def test_an_early_wake_waits_out_the_interval_and_is_not_dropped(self) -> None:
        clock = FakeClock()
        sleeps: list[float] = []
        client = self.make(clock, sleeps)
        client.refresh()  # last check at t=0
        clock.now = 5.0
        client._wake.set()  # a visitor's mismatched miss
        client._wait_after(failed=False)
        assert sleeps == [25.0]  # one recheck per 30 s, not one per visit
        assert client._wake.is_set()  # left for the next cycle to answer

    def test_a_wake_after_the_interval_is_answered_at_once(self) -> None:
        clock = FakeClock()
        sleeps: list[float] = []
        client = self.make(clock, sleeps)
        client.refresh()
        clock.now = 31.0
        client._wake.set()
        client._wait_after(failed=False)
        assert sleeps == []

    def test_no_wake_waits_for_the_ttl_without_sleeping(self) -> None:
        clock = FakeClock()
        sleeps: list[float] = []
        client = self.make(clock, sleeps, ttl=0.01)
        client.refresh()
        client._wait_after(failed=False)
        assert sleeps == []

    def test_a_failed_cycle_still_backs_off_for_the_retry_interval(self) -> None:
        clock = FakeClock()
        sleeps: list[float] = []
        client = self.make(clock, sleeps, retry_backoff=17.0)  # not min_recheck's 30
        client._wake.set()
        client._wait_after(failed=True)
        assert sleeps == [17.0]

    def test_a_wake_set_during_a_successful_refresh_is_answered_after_it(self) -> None:
        """AC6, on the real thread: the wake-up survives the cycle it arrived in."""
        metas: list[float] = []
        holder: dict[str, api.Client] = {}

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == api.META_PATH:
                metas.append(time.monotonic())
                if len(metas) == 2:
                    holder["client"]._wake.set()  # a visitor's miss, mid-refresh
            return api.Response(body=META, version=VERSION)

        client = offline_client(fetch, ttl=3600, min_recheck=0.05)
        holder["client"] = client
        client.ensure_refresher()
        assert client._ready.wait(5)
        client._wake.set()  # cycle 2, during which the visitor's wake-up arrives
        deadline = time.monotonic() + 5
        while len(metas) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(metas) >= 3, "the mid-refresh wake-up waited for the TTL"

    def test_repeated_wakes_cost_one_meta_per_interval_on_the_real_thread(self) -> None:
        metas: list[float] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            metas.append(time.monotonic())
            return api.Response(body=META, version=VERSION)

        client = offline_client(fetch, ttl=3600, min_recheck=0.3)
        client.ensure_refresher()
        assert client._ready.wait(5)
        stop = time.monotonic() + 1.0
        while time.monotonic() < stop:  # visitors missing on a stale edge path
            client._wake.set()
            time.sleep(0.01)
        # One cold check, then at most one per 0.3 s over the second of wake-ups.
        assert 2 <= len(metas) <= 6, len(metas)

    def test_the_process_client_uses_the_pinned_interval(self) -> None:
        assert api.MIN_RECHECK_INTERVAL_S == 30.0
        assert PROCESS_CLIENT._min_recheck == api.MIN_RECHECK_INTERVAL_S


class TestTokenBucket:
    def make(
        self, advance: bool = True
    ) -> tuple[api.TokenBucket, list[float], dict[str, float]]:
        now = {"t": 0.0}
        slept: list[float] = []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            if advance:
                now["t"] += seconds

        bucket = api.TokenBucket(
            per_minute=30, burst=10, clock=lambda: now["t"], sleep=sleep
        )
        return bucket, slept, now

    def test_the_burst_is_free_then_fills_are_paced_at_the_rate(self) -> None:
        bucket, slept, _ = self.make()
        for _ in range(10):
            bucket.acquire(max_wait=None)
        assert slept == []
        bucket.acquire(max_wait=None)
        assert slept == [pytest.approx(2.0)]  # 30/min = one every 2 s

    def test_a_request_waits_only_briefly_then_gives_up(self) -> None:
        # Callers arriving at the same instant: the clock does not move while they wait.
        bucket, slept, _ = self.make(advance=False)
        for _ in range(10):
            bucket.acquire(max_wait=2.0)
        bucket.acquire(max_wait=2.0)  # 2.0 s wait: allowed
        with pytest.raises(api.ApiUnavailable):
            bucket.acquire(max_wait=2.0)  # would need 4.0 s
        assert slept == [pytest.approx(2.0)]

    def test_sustained_fills_never_exceed_the_rate(self) -> None:
        bucket, _, now = self.make()
        for _ in range(100):
            bucket.acquire(max_wait=None)
        # 100 fills from a full burst of 10 take at least (100 - 10) / 0.5 s.
        assert now["t"] >= 180.0 - 1e-9


# --- the refresher ---------------------------------------------------------------------


class TestRefresher:
    def test_warmup_refreshes_on_its_own_thread_then_starts_the_refresher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        threads: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            threads.append(threading.current_thread().name)
            return api.Response(body=META, version=VERSION)

        client = offline_client(fetch, ttl=3600)
        monkeypatch.setattr(api, "CLIENT", client)
        response = appmod.server.test_client().get("/_ah/warmup")
        assert response.status_code == 200
        assert client.snapshot is not None and client.snapshot.version == VERSION
        assert client.refresher_running
        time.sleep(0.2)  # give a wrongly eager refresher time to fetch again
        # Exactly one /v1/meta, made synchronously by warmup, not by the refresher.
        assert threads == [threading.current_thread().name]

    def test_warmup_answers_200_even_when_the_api_is_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = offline_client(failing_fetch, ttl=3600)
        monkeypatch.setattr(api, "CLIENT", client)
        assert appmod.server.test_client().get("/_ah/warmup").status_code == 200
        assert client.snapshot is None

    def test_a_request_restarts_a_stopped_refresher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = offline_client(ttl=3600)
        monkeypatch.setattr(api, "CLIENT", client)
        assert not client.refresher_running
        appmod.server.test_client().get("/")
        assert client.refresher_running

    def test_the_refresher_survives_a_failing_cycle(self) -> None:
        attempts = threading.Semaphore(0)
        calls = {"n": 0}

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls["n"] += 1
            attempts.release()
            if calls["n"] == 1:
                raise api.ApiUnavailable("down")
            return api.Response(body=META, version=VERSION)  # recovered: goes idle

        client = offline_client(fetch, ttl=3600, retry_backoff=0.01)
        client.ensure_refresher()
        assert attempts.acquire(timeout=5)
        assert attempts.acquire(timeout=5)  # a second cycle ran after the failure
        assert client.refresher_running
        deadline = time.monotonic() + 5
        while client.snapshot is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.snapshot is not None

    def test_a_failed_cycle_backs_off_whatever_wakes_it(self) -> None:
        attempts: list[float] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            attempts.append(time.monotonic())
            raise api.ApiUnavailable("down")

        client = offline_client(fetch, retry_backoff=0.5)
        client.ensure_refresher()
        deadline = time.monotonic() + 0.4
        while time.monotonic() < deadline:  # visitors hammering a cold cache
            client._wake.set()
            time.sleep(0.02)
        assert len(attempts) == 1

    def test_ensure_refresher_is_idempotent(self) -> None:
        client = offline_client(ttl=3600)
        client.ensure_refresher()
        thread = client._thread
        client.ensure_refresher()
        assert client._thread is thread


# --- the canonical host --------------------------------------------------------------


class TestRedirect:
    @pytest.mark.parametrize(
        ("host", "path", "query", "target"),
        [
            ("uspv-explore.uw.r.appspot.com", "/", "", f"https://{CANONICAL_HOST}/"),
            (
                "uspv-explore.uw.r.appspot.com",
                "/election/2000",
                "state=OH",
                f"https://{CANONICAL_HOST}/election/2000?state=OH",
            ),
            ("USPV-EXPLORE.UW.R.APPSPOT.COM:443", "/", "", f"https://{CANONICAL_HOST}/"),
            ("uspv-explore.uw.r.appspot.com", "/_ah/warmup", "", None),
            ("abc123-r7-dot-uspv-explore.uw.r.appspot.com", "/", "", None),
            ("uspv-explore.appspot.com.", "/", "", f"https://{CANONICAL_HOST}/"),
            (
                "uspv-explore.uw.r.appspot.com",
                "/a?b#c",
                "x=1",
                f"https://{CANONICAL_HOST}/a%3Fb%23c?x=1",
            ),
            (
                "uspv-explore.uw.r.appspot.com",
                "/a\r\nSet-Cookie: x=1",
                "",
                f"https://{CANONICAL_HOST}/a%0D%0ASet-Cookie%3A%20x%3D1",
            ),
            (CANONICAL_HOST, "/", "", None),
            ("localhost:8050", "/", "", None),
        ],
    )
    def test_redirect_target(
        self, host: str, path: str, query: str, target: str | None
    ) -> None:
        assert appmod.redirect_target(host, path, query) == target

    def test_the_vendor_host_301s_to_the_canonical_host(self) -> None:
        response = appmod.server.test_client().get(
            "/election/2000?state=OH",
            headers={"Host": "uspv-explore.uw.r.appspot.com"},
        )
        assert response.status_code == 301
        assert response.headers["Location"] == (
            f"https://{CANONICAL_HOST}/election/2000?state=OH"
        )

    def test_a_line_break_in_the_path_redirects_instead_of_failing(self) -> None:
        response = appmod.server.test_client().get(
            "/a%0d%0aSet-Cookie:%20x=1",
            headers={"Host": "uspv-explore.uw.r.appspot.com"},
        )
        assert response.status_code == 301
        assert "\n" not in response.headers["Location"]
        assert "Set-Cookie" not in response.headers or "x=1" not in str(
            response.headers.get("Set-Cookie")
        )

    def test_the_canonical_host_is_served(self) -> None:
        response = appmod.server.test_client().get("/", headers={"Host": CANONICAL_HOST})
        assert response.status_code == 200
