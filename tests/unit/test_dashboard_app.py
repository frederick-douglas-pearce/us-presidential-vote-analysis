"""The dashboard's behaviour: rendering, the degraded state, the cache and the redirect.

Offline: every test runs against the recorded ``/v1/meta`` fixture through a fake fetch,
and the autouse fixture below replaces the process client so no request to the app can
start a refresher that reaches the network. The structural guards (no ``usvote`` at
runtime, one API host, no data files, ``app.yaml`` pins) are in
``test_dashboard_guards.py``.
"""

from __future__ import annotations

import contextlib
import copy
import http.client
import http.server
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import dash
import pytest
from dash.development.base_component import Component

from explore import api
from explore import app as appmod

#: Written out rather than imported from ``explore.config``: a test that read the host
#: from the module under test would move with it (r1.guard-efficacy.16).
CANONICAL_HOST = "explore.us-presidential-election-center.org"
PUBLIC_API_BASE = "https://api.us-presidential-election-center.org"

#: The process client as the app built it, captured before any fixture replaces it.
PROCESS_CLIENT = api.CLIENT

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "dashboard" / "v1_meta.json"
META: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
VERSION: str = META["provenance"]["snapshot_version"]

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

    def fetch(path: str) -> api.Response:
        calls.append(path)
        return api.Response(body=bodies[path], version=version)

    return fetch, calls


def failing_fetch(path: str) -> api.Response:
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
        def fetch(path: str) -> api.Response:
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
        client = offline_client(lambda path: state["fetch"](path))
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
        assert opener.timeouts == [15.0]
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

        def fetch(path: str) -> api.Response:
            threads.append(threading.current_thread().name)
            return api.Response(body=META, version=VERSION)

        client = offline_client(fetch, ttl=3600)
        assert client.get(api.META_PATH) == META
        assert client.get(api.META_PATH) == META
        assert threads == ["explore-refresher"]  # never on the visitor's thread

    def test_a_cold_get_with_a_dead_api_gives_up_within_the_bound(self) -> None:
        threads: list[str] = []

        def fetch(path: str) -> api.Response:
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

        def fetch(path: str) -> api.Response:
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

        def fetch(path: str) -> api.Response:
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

        def fetch(path: str) -> api.Response:
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

        def fetch(path: str) -> api.Response:
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
        def fetch(path: str) -> api.Response:
            if path == api.META_PATH:
                return api.Response(body=META, version=VERSION)
            return api.Response(body={"data": []}, version="some-other-version")

        client = offline_client(fetch, prefetch_paths=lambda: ["/v1/elections"])
        with pytest.raises(api.ApiUnavailable):
            client.refresh()
        assert client.snapshot is None

    def test_a_fill_on_miss_is_stored_only_under_its_own_version(self) -> None:
        state = {"version": VERSION}

        def fetch(path: str) -> api.Response:
            body = META if path == api.META_PATH else {"path": path}
            return api.Response(body=body, version=state["version"])

        client = offline_client(fetch)
        client.refresh()
        client.get("/v1/elections")
        assert client.snapshot is not None
        assert "/v1/elections" in client.snapshot.responses

        state["version"] = "next-version"
        assert client.get("/v1/elections/2000") == {"path": "/v1/elections/2000"}
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
        assert bucket.waits == [None, None, client._max_request_wait]
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


class TestRegistryCoverage:
    def test_every_path_a_page_reads_is_prefetched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A page that forgets to register a path brings back the 9.1 s cold read."""
        read: list[str] = []

        class Recorder:
            def get(self, path: str) -> dict[str, Any]:
                read.append(path)
                return META

        monkeypatch.setattr(api, "CLIENT", Recorder())
        for page in dash.page_registry.values():
            page["layout"]()
        assert read, "no page read anything; the check would be vacuous"
        assert set(read) <= set(api.registered_prefetch_paths())


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

        def fetch(path: str) -> api.Response:
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

        def fetch(path: str) -> api.Response:
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

        def fetch(path: str) -> api.Response:
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
