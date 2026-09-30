"""The dashboard's behaviour: rendering, the degraded state, the cache and the redirect.

Offline: every test runs against the recorded ``/v1/meta`` fixture through a fake fetch,
and the autouse fixture below replaces the process client so no request to the app can
start a refresher that reaches the network. The structural guards (no ``usvote`` at
runtime, one API host, no data files, ``app.yaml`` pins) are in
``test_dashboard_guards.py``.
"""

from __future__ import annotations

import copy
import http.server
import json
import threading
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
from explore.config import CANONICAL_HOST

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
    return api.Client(fetch=fetch, **kwargs)


@pytest.fixture(autouse=True)
def _offline_process_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "CLIENT", offline_client())


# --- rendering ---------------------------------------------------------------------


class TestRender:
    def test_names_all_three_sources_and_links_each_license(self) -> None:
        tree = home_module()["render"](META)
        text = " ".join(texts(tree))
        p = META["provenance"]
        for name in (p["ec_source_name"], p["source_name"], p["census_source_name"]):
            assert name in text
        assert sorted(hrefs(tree)) == sorted(
            [p["ec_license_url"], p["license_url"], p["census_license_url"]]
        )

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
        assert VERSION in texts(home_module()["render"](META))

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
    def test_builds_on_the_public_host(self) -> None:
        assert (
            api.build_url("/v1/meta")
            == "https://api.us-presidential-election-center.org/v1/meta"
        )

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
    def __init__(self, status: int, body: bytes, etag: str | None) -> None:
        self.status = status
        self.headers = {"ETag": etag} if etag else {}
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeRaw:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeOpener:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, timeout: float) -> Any:
        self.requests.append(request)
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
        ],
    )
    def test_every_failure_becomes_api_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, result: Any
    ) -> None:
        monkeypatch.setattr(api, "_OPENER", _FakeOpener(result))
        with pytest.raises(api.ApiUnavailable):
            api.fetch("/v1/meta")

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
    def test_first_get_refreshes_then_serves_from_cache(self) -> None:
        fetch, calls = fake_fetch({api.META_PATH: META})
        client = offline_client(fetch)
        assert client.get(api.META_PATH) == META
        assert client.get(api.META_PATH) == META
        assert calls == [api.META_PATH]

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
        assert api.registered_prefetch_paths() == [api.META_PATH]


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
    def test_warmup_refreshes_and_starts_the_refresher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch, calls = fake_fetch({api.META_PATH: META})
        client = offline_client(fetch, ttl=3600)
        monkeypatch.setattr(api, "CLIENT", client)
        response = appmod.server.test_client().get("/_ah/warmup")
        assert response.status_code == 200
        assert client.snapshot is not None and client.snapshot.version == VERSION
        assert client.refresher_running

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

        def fetch(path: str) -> api.Response:
            attempts.release()
            raise api.ApiUnavailable("down")

        client = offline_client(fetch, ttl=0.01)
        client.ensure_refresher()
        assert attempts.acquire(timeout=5)
        assert attempts.acquire(timeout=5)  # a second cycle ran after the failure
        assert client.refresher_running

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

    def test_the_canonical_host_is_served(self) -> None:
        response = appmod.server.test_client().get("/", headers={"Host": CANONICAL_HOST})
        assert response.status_code == 200
