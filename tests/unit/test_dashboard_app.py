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
import html.parser
import http.client
import http.server
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import dash
import pytest
from dash._pages import (
    _page_meta_tags,
    _parse_path_variables,
    _parse_query_string,
    _path_to_page,
)
from dash.development.base_component import Component

from explore import api, components
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
        **{
            f"/v1/elections/{year}": f"v1_elections_{year}.json"
            for year in (1824, 1860, 1868, 1872, 2016, 2024)
        },
        "/v1/states/GA": "v1_states_GA.json",
    }.items()
}

#: The concrete value each templated page is rendered at, one per path variable. Each
#: must make the page read a path in :data:`RECORDED`.
PATH_VALUES = {"year": "1824", "usps": "GA"}

#: The coverage variables (``api.COVERAGE_VARS``) as the recorded index resolves them:
#: what an ``on_miss`` template or a ``validate`` source naming one is formatted with.
COVERAGE_VALUES = api.coverage_vars(RECORDED["/v1/elections"])

#: A well-formed value each path variable's page does not serve: what the hostile
#: renders put in the path (#279, so a page validating only syntax is caught).
UNSERVED_VALUES = {"year": "1825", "usps": "ZZ"}


def resolved(source: str) -> str:
    """A ``validate`` source or ``on_miss`` path with its coverage variables filled."""
    return source.format(**COVERAGE_VALUES) if api.placeholders(source) else source


def source_paths(source: str) -> list[str]:
    """What must be cached for a ``validate`` source to judge: the source and, for a
    template, the index it is resolved from."""
    path = resolved(source)
    return [api.ELECTIONS_PATH, path] if path != source else [source]


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

    @pytest.mark.parametrize(
        "module",
        sorted(m for m, p in dash.page_registry.items() if not p.get("path_template")),
    )
    def test_the_link_preview_text_states_no_years(self, module: str) -> None:
        """An untemplated page's card text is static, and the index never waits on the
        API, so it cannot carry a second coverage copy. (A templated page's callable
        title may name its own path variable, such as a year.)"""
        page = dash.page_registry[module]
        for text in (page["description"], page["title"]):
            assert isinstance(text, str), module
            assert not any(ch.isdigit() for ch in text), (module, text)

    @pytest.mark.parametrize(
        "module",
        sorted(m for m, p in dash.page_registry.items() if p.get("path_template")),
    )
    def test_a_templated_page_s_static_description_states_no_years(
        self, module: str
    ) -> None:
        """The same rule for a templated page's static description (#307). Its title
        may be callable and name its own path variable; called with none, it names no
        year either."""
        page = dash.page_registry[module]
        texts_ = [page["description"]]
        texts_.append(page["title"]() if callable(page["title"]) else page["title"])
        for text in texts_:
            assert isinstance(text, str), module
            assert not any(ch.isdigit() for ch in text), (module, text)

    def test_every_page_s_path_routes_to_that_page(self) -> None:
        """Dash's router takes the first match, so a page whose concrete path routes
        to another page is never rendered (#307)."""
        for module, page in dash.page_registry.items():
            if page["module"].split(".")[-1] == "not_found_404":
                continue
            routed, _ = _path_to_page(concrete_page_path(page).strip("/"))
            assert routed.get("module") == page["module"], module

    def test_the_register_fixture_refuses_a_fake_at_a_routed_path(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        # A different template string, the same URLs as the real /election/<year>.
        with pytest.raises(AssertionError, match="pages.election"):
            register("fake_shadow", **{**YEAR_PAGE, "path_template": "/election/<yr>"})
        assert "fake_shadow" not in dash.page_registry
        # A variable where the real page has a fixed segment: "x/x" routes nowhere,
        # yet the template matches /election/1824.
        with pytest.raises(AssertionError, match="pages.election"):
            register("fake_wide", **{**YEAR_PAGE, "path_template": "/<kind>/<year>"})
        assert "fake_wide" not in dash.page_registry

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


# --- the canonical link, og:url and the 404 (#312) -----------------------------------

#: The years the recorded ``/v1/elections`` serves; 1825 is not one of them.
SERVED_YEARS = {str(row["year"]) for row in RECORDED[api.ELECTIONS_PATH]["data"]}


def known_year(path_vars: dict[str, Any], body: dict[str, Any]) -> bool:
    """The fake year pages' judge: the year is one ``/v1/elections`` lists. Total."""
    rows = body.get("data")
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict) and str(row.get("year")) == path_vars.get("year")
        for row in rows
    )


FAKE_VALIDATE: api.Validate = (api.ELECTIONS_PATH, known_year)

#: The filters the fake filtered page keeps; everything else is dropped.
FAKE_FILTERS = ("party", "state")


def fake_parser(params: dict[str, Any]) -> list[tuple[str, str]]:
    """The fake filtered page's query parser: kept keys, every value, de-duplicated."""
    pairs: set[tuple[str, str]] = set()
    for key in FAKE_FILTERS:
        value = params.get(key)
        values = value if isinstance(value, list) else [value]
        pairs |= {(key, v) for v in values if isinstance(v, str) and v}
    return sorted(pairs)


def _validated_year_layout(year: Any = None, **query: Any) -> Any:
    # The pattern a templated page follows: accept what the layout received, then format.
    with api.CLIENT.view() as view:
        if not api.accepted(view.get, FAKE_VALIDATE, {"year": year}):
            return dash.html.P("No such election.", id="fake-year-missing")
        body = view.get(f"/v1/elections/{year}")
        filters = fake_parser(query)
    return dash.html.Div(
        [dash.html.Span(str(len(body))), dash.html.Code(repr(filters), id="filters")],
        id="fake-year",
    )


def _unvalidated_year_layout(year: Any = None, **_query: Any) -> Any:
    # The defect the hostile render exists to catch: the variable formatted unvalidated.
    with api.CLIENT.view() as view:
        body = view.get(f"/v1/elections/{year}")
    return dash.html.Div(str(len(body)), id="fake-year")


YEAR_PAGE: dict[str, Any] = {
    "path_template": "/fake-election/<year>",
    "layout": _validated_year_layout,
    "prefetch": (api.ELECTIONS_PATH,),
    "on_miss": ("/v1/elections/{year}",),
    "success": "fake-year",
    "validate": FAKE_VALIDATE,
}


@pytest.fixture
def register() -> Iterator[Callable[..., dict[str, Any]]]:
    """Register fake pages for one test, and remove them after it."""
    modules: list[str] = []

    def add(module: str = "fake_year", **page: Any) -> dict[str, Any]:
        # Dash's router takes the first match, so a fake page sharing any URL with a
        # registered page would silently test that page instead (#307). Checked by
        # route, not by string, both ways: the fake's own path must route nowhere
        # (``/election/<yr>`` matches what ``<year>`` does), and no registered page's
        # concrete path may match the fake's template (``/<kind>/<year>`` matches
        # ``/election/1824``).
        template = page.get("path_template") or page.get("path") or ""
        # Any value: Dash's matcher is greedy, so a variable matches any segment.
        concrete = re.sub(r"<(.*?)>", "x", template)
        routed, _ = _path_to_page(concrete.strip("/"))
        assert not routed, (concrete, routed.get("module"))
        for other in dash.page_registry.values():
            if other["module"].split(".")[-1] == "not_found_404":
                continue
            taken = concrete_page_path(other).strip("/")
            shared = _parse_path_variables(taken, template.strip("/"))
            assert shared is None, (template, other["module"], taken)
        dash.register_page(module, **page)
        modules.append(module)
        registered: dict[str, Any] = dash.page_registry[module]
        return registered

    yield add
    for module in modules:
        dash.page_registry.pop(module, None)


def cached_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    elections: bool = True,
    source: str = api.ELECTIONS_PATH,
) -> tuple[api.Client, list[str], RecordingBucket]:
    """A process client already serving a snapshot, with or without ``source``.

    The returned call list and bucket record only what happens after the refresh.
    """
    fetch, calls = fake_fetch(RECORDED)
    bucket = RecordingBucket()
    client = offline_client(
        fetch,
        bucket=bucket,
        prefetch_paths=lambda: source_paths(source) if elections else [],
    )
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    calls.clear()
    bucket.waits.clear()
    monkeypatch.setattr(api, "CLIENT", client)
    return client, calls, bucket


class Head(html.parser.HTMLParser):
    """Every start tag of a page, as attribute dicts, values unescaped."""

    def __init__(self, body: str) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.feed(body)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def attrs(self, tag: str, key: str, value: str) -> list[dict[str, str | None]]:
        return [a for t, a in self.tags if t == tag and a.get(key) == value]

    def one(self, tag: str, key: str, value: str, attr: str) -> str | None:
        found = self.attrs(tag, key, value)
        assert len(found) <= 1, found
        return found[0][attr] if found else None

    @property
    def canonical(self) -> str | None:
        return self.one("link", "rel", "canonical", "href")

    @property
    def og_url(self) -> str | None:
        return self.one("meta", "property", "og:url", "content")

    @property
    def twitter_url(self) -> str | None:
        return self.one("meta", "property", "twitter:url", "content")

    @property
    def noindex(self) -> bool:
        return self.one("meta", "name", "robots", "content") == "noindex"


def get(path: str, *, unencoded: bool = False, **kwargs: Any) -> tuple[int, Head, str]:
    """GET ``path``. The test client reports the target as sent (``RAW_URI``), escapes
    included; ``unencoded`` reports it decoded instead, as a client sending raw bytes
    would, so the index's encoded-path check passes it."""
    if unencoded:
        sent, _, query = path.partition("?")
        raw = urllib.parse.unquote(sent) + (f"?{query}" if query else "")
        kwargs["environ_overrides"] = {"RAW_URI": raw, "REQUEST_URI": raw}
    response = appmod.server.test_client().get(path, **kwargs)
    body = response.get_data(as_text=True)
    return response.status_code, Head(body), body


def route(pathname: str, search: str = "") -> Any:
    """The routing POST a browser makes for ``pathname`` and ``search``."""
    body = copy.deepcopy(ROUTING_POST)
    body["inputs"][0]["value"] = pathname
    body["inputs"][1]["value"] = search
    return appmod.server.test_client().post("/_dash-update-component", json=body)


def routed_ids(response: Any) -> set[str]:
    def walk(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            props = node.get("props")
            if isinstance(props, dict) and isinstance(props.get("id"), str):
                found.add(props["id"])
            for value in node.values():
                found |= walk(value)
        elif isinstance(node, list):
            for value in node:
                found |= walk(value)
        return found

    return walk(response.get_json())


def url(path: str) -> str:
    return f"https://{CANONICAL_HOST}{path}"


class TestCanonical:
    """Items 1, 3 and 5: matched paths name one canonical URL; og:url adds the filters."""

    def test_the_root_keeps_the_byte_form_the_deploy_probe_greps(self) -> None:
        status, _, body = get("/")
        assert status == 200
        assert f'<link rel="canonical" href="{url("/")}">' in body
        assert f'<meta property="og:url" content="{url("/")}">' in body
        assert body.count('property="og:title"') == 1  # Dash's card, rebuilt once

    @pytest.mark.parametrize("path", ["/?b=2&a=1", "/?a=1"])
    def test_a_page_without_a_parser_drops_the_query(self, path: str) -> None:
        status, head, _ = get(path)
        assert (status, head.canonical, head.og_url) == (200, url("/"), url("/"))

    def test_a_templated_canonical_is_the_template_and_its_variables(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        register(**YEAR_PAGE)
        for path in (
            "/fake-election/1860?state=OH",
            "/fake-election/1860/",
            "/fake-election/1860",
        ):
            status, head, _ = get(path)
            assert status == 200, path
            assert head.canonical == url("/fake-election/1860"), path
            assert head.og_url == head.canonical, path  # no parser: no query

    def test_og_url_carries_the_normalized_query_and_the_canonical_does_not(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        register(**YEAR_PAGE, query=fake_parser)
        expected = url("/fake-election/1860?party=D&state=CA&state=OH")
        for query in (
            "state=OH&party=D&junk=1&state=CA",
            "junk=2&state=CA&state=OH&party=D&state=OH",
        ):
            _, head, _ = get(f"/fake-election/1860?{query}")
            assert head.canonical == url("/fake-election/1860")
            assert head.og_url == expected, query

    def test_a_parser_that_keeps_nothing_leaves_og_url_bare(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        register(**YEAR_PAGE, query=fake_parser)
        _, head, _ = get("/fake-election/1860?junk=1")
        assert head.og_url == url("/fake-election/1860")

    @pytest.mark.parametrize("year", ["1860", "1860/x", "%25", "a%20b"])
    def test_the_canonical_resolves_back_to_the_same_page(
        self, register: Callable[..., dict[str, Any]], year: str
    ) -> None:
        register(**YEAR_PAGE)  # cold: every well-formed variable counts as matched
        _, head, _ = get(f"/fake-election/{year}", unencoded=True)
        assert head.canonical is not None
        path = urllib.parse.unquote(urllib.parse.urlsplit(head.canonical).path)
        page, path_vars = dash._pages._path_to_page(path.strip("/"))
        assert page["module"] == "fake_year"
        assert path_vars == {"year": urllib.parse.unquote(year)}

    def test_a_filtered_og_url_reopens_the_filtered_view(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        register(**YEAR_PAGE, query=fake_parser)
        cached_client(monkeypatch)
        shared = "/fake-election/1824?state=OH&junk=1&party=D&state=CA"
        _, head, _ = get(shared)
        assert head.og_url is not None
        # The attribute was HTML-escaped; Head's parser unescapes it, as a platform would.
        reopened = urllib.parse.urlsplit(head.og_url)
        assert reopened.query == "party=D&state=CA&state=OH"
        original = route("/fake-election/1824", "?state=OH&junk=1&party=D&state=CA")
        again = route(reopened.path, f"?{reopened.query}")
        assert "filters" in routed_ids(original)
        assert original.get_json() == again.get_json()

    def test_twitter_url_is_never_emitted(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        register(**YEAR_PAGE, query=fake_parser)
        cached_client(monkeypatch)
        for path in (
            "/",
            "/?a=1",
            "/fake-election/1860?state=OH",  # matched, with a query
            "/fake-election/1824",  # matched, without one
            "/no-such-view",  # unmatched
            "/fake-election/1825",  # rejected
        ):
            _, head, body = get(path)
            assert head.twitter_url is None, path
            assert "twitter:url" not in body, path
            assert head.one("meta", "property", "twitter:card", "content"), path

    def test_a_page_with_an_image_renders_its_card(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        # Dash builds an image URL from request.root, which only its adapter carries.
        register("fake_imaged", path="/imaged", layout=dash.html.P("x"), image="x.png")
        status, head, _ = get("/imaged")
        assert status == 200
        assert head.one("meta", "property", "og:image", "content") == (
            "http://localhost/assets/x.png"
        )


class TestNotFound:
    """Item 4: unmatched and rejected paths answer 404, noindex, and name no URL."""

    @staticmethod
    def assert_not_found(path: str, **kwargs: Any) -> None:
        status, head, body = get(path, **kwargs)
        assert status == 404, path
        assert head.noindex, path
        assert (head.canonical, head.og_url, head.twitter_url) == (None, None, None)
        assert 'rel="canonical"' not in body
        assert "og:url" not in body

    @pytest.mark.parametrize(
        "path", ["/no-such-view", "/x/y/z", "/_ah/x", "/election"]
    )
    def test_an_unmatched_path(self, path: str) -> None:
        self.assert_not_found(path)

    def test_a_matched_path_says_nothing_about_indexing(self) -> None:
        _, head, _ = get("/")
        assert not head.noindex

    def test_a_rejected_path(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        register(**YEAR_PAGE)
        _, calls, bucket = cached_client(monkeypatch)
        self.assert_not_found("/fake-election/1825")
        self.assert_not_found("/fake-election/1860/x")
        status, head, _ = get("/fake-election/1824")
        assert (status, head.canonical) == (200, url("/fake-election/1824"))
        assert (calls, bucket.waits) == ([], [])

    @pytest.mark.parametrize("cold", ["no snapshot", "no source"])
    def test_a_cold_source_counts_as_matched_and_fetches_nothing(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        cold: str,
    ) -> None:
        register(**YEAR_PAGE)
        if cold == "no snapshot":
            fetch, calls = fake_fetch(RECORDED)
            client = offline_client(fetch)
            client.ensure_refresher = lambda: None  # type: ignore[method-assign]
            client.view = no_view_allowed  # type: ignore[method-assign]
            monkeypatch.setattr(api, "CLIENT", client)
        else:
            client, calls, _ = cached_client(monkeypatch, elections=False)
            client.view = no_view_allowed  # type: ignore[method-assign]
        status, head, _ = get("/fake-election/1825")
        assert (status, head.canonical) == (200, url("/fake-election/1825"))
        assert calls == []

    def test_head_answers_404_too(self) -> None:
        response = appmod.server.test_client().head("/no-such-view")
        assert response.status_code == 404

    def test_the_vendor_host_still_redirects_before_any_404(self) -> None:
        response = appmod.server.test_client().get(
            "/no-such-view", headers={"Host": "uspv-explore.uw.r.appspot.com"}
        )
        assert response.status_code == 301

    def test_warmup_is_not_a_page(self) -> None:
        assert appmod.server.test_client().get("/_ah/warmup").status_code == 200

    def test_each_request_resolves_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        real = appmod.resolve

        def counting(path: str, *args: Any) -> appmod.Resolution:
            calls.append(path)
            return real(path, *args)

        monkeypatch.setattr(appmod, "resolve", counting)
        assert get("/")[0] == 200
        assert get("/no-such-view")[0] == 404
        assert calls == ["/", "/no-such-view"]

    def test_the_tags_are_never_recomputed_outside_index(self) -> None:
        with appmod.server.test_request_context("/"), pytest.raises(RuntimeError):
            appmod.app.interpolate_index()


def no_view_allowed() -> api.View:
    raise AssertionError("the index waited on a view")


@pytest.mark.parametrize(
    "path",
    [
        '/%22%3E%3Cscript%3Ealert(1)%3C/script%3E%3Cx%20a=%22',
        "/%3Cimg%20src=x%20onerror=alert(1)%3E",
        "/'%3E%3Csvg%20onload=alert(1)%3E",
    ],
)
def test_an_unmatched_hostile_path_is_a_404_and_never_markup(path: str) -> None:
    status, head, body = get(path)
    assert status == 404
    assert head.canonical is None
    assert_no_markup(body)


HOSTILE = '"><script>alert(1)</script><x a="'


def assert_no_markup(body: str) -> None:
    # The whole body, so Dash's own tags are covered as well as ours.
    for marker in ("<script>alert", "<img src=x", "<svg onload", '"><script', "<x a="):
        assert marker not in body


def test_hostile_text_where_a_canonical_is_still_emitted(
    register: Callable[..., dict[str, Any]],
) -> None:
    """Item 7: as a templated variable (cold, so matched) and as a kept query value."""
    register(**YEAR_PAGE, query=lambda params: [("state", str(params.get("state")))])
    quoted = urllib.parse.quote(HOSTILE, safe="")
    for path in (f"/fake-election/{quoted}", f"/fake-election/1860?state={quoted}"):
        status, head, body = get(path, unencoded=True)
        assert status == 200, path
        assert head.canonical is not None and head.og_url is not None
        assert_no_markup(body)
        # Every link and meta tag parses with exactly its expected attributes: no
        # quote broke out of a value to add one.
        assert head.attrs("link", "rel", "canonical") == [
            {"rel": "canonical", "href": head.canonical}
        ]
        assert head.attrs("meta", "property", "og:url") == [
            {"property": "og:url", "content": head.og_url}
        ]
        for tag, attrs in head.tags:
            if tag == "meta":
                assert set(attrs) <= {"name", "property", "content", "charset",
                                      "http-equiv"}, attrs
    _, head, _ = get(f"/fake-election/1860?state={quoted}")
    assert head.og_url == url(f"/fake-election/1860?state={quoted}")


def test_card_tags_escape_a_callable_title_that_echoes_the_path(
    register: Callable[..., dict[str, Any]],
) -> None:
    """Dash calls a callable title with the decoded path variables: only ``_tag``'s
    escape stands between them and the card tags."""
    register(
        **YEAR_PAGE,
        title=lambda year=None, **_q: f"Election {year}",
        description=lambda year=None, **_q: f"Results for {year}",
    )
    quoted = urllib.parse.quote(HOSTILE, safe="")
    status, head, body = get(
        f"/fake-election/{quoted}", unencoded=True
    )  # cold: matched
    assert status == 200
    assert_no_markup(body)
    assert head.one("meta", "property", "og:title", "content") == f"Election {HOSTILE}"
    assert head.one("meta", "name", "description", "content") == f"Results for {HOSTILE}"
    for tag, attrs in head.tags:
        if tag == "meta":
            assert set(attrs) <= {"name", "property", "content", "charset", "http-equiv"}


def test_tag_escapes_every_character_that_could_leave_an_attribute() -> None:
    tag = appmod._tag("meta", {"content": "\"'<>&"})
    assert tag == '<meta content="&quot;&#x27;&lt;&gt;&amp;">'


#: Paths whose percent-escapes change them when decoded. Dash's router matches the
#: browser's still-encoded ``location.pathname``, so on each one the decoded path the
#: index sees would match differently from the page the router renders.
ENCODED_PATHS = (
    "/fake-election%2F1824",
    "/%2F",
    "/fake-election/%2F",
    "/fake-election/182%34",
)


class TestEncodedPath:
    """Status and render agree on a path decoding would change (D073)."""

    @pytest.mark.parametrize("path", ENCODED_PATHS)
    def test_a_path_decoding_changes_is_not_found_and_not_rendered(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        path: str,
    ) -> None:
        register(**YEAR_PAGE)
        _, calls, _ = cached_client(monkeypatch)
        TestNotFound.assert_not_found(path)  # the test client sends it encoded
        response = route(path)  # what the browser's router is handed
        assert response.status_code == 200
        assert "fake-year" not in routed_ids(response)
        assert calls == []

    def test_a_leading_double_slash_is_not_an_escape(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # gunicorn hands //fake-election/1824 over unnormalized, in RAW_URI and PATH_INFO
        # alike; Werkzeug's request.path drops the extra slash, and Dash's router
        # renders the page. (The test client would read //fake-election as a host.)
        register(**YEAR_PAGE)
        cached_client(monkeypatch)
        status, head, _ = get(
            "/fake-election/1824",
            environ_overrides={
                "PATH_INFO": "//fake-election/1824",
                "RAW_URI": "//fake-election/1824",
                "REQUEST_URI": "",
            },
        )
        assert (status, head.canonical) == (200, url("/fake-election/1824"))
        assert "fake-year" in routed_ids(route("//fake-election/1824"))

    def test_without_a_raw_target_the_decoded_path_is_used(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        # The twin: the same request with no RAW_URI or REQUEST_URI is matched, so the
        # 404 above comes from the raw-path comparison and nothing else.
        register(**YEAR_PAGE)
        status, head, _ = get(
            "/fake-election%2F1824",
            environ_overrides={"RAW_URI": "", "REQUEST_URI": ""},
        )
        assert (status, head.canonical) == (200, url("/fake-election/1824"))

    @pytest.mark.parametrize(
        ("environ", "expected"),
        [
            ({"RAW_URI": "/fake-election/1824?state=OH"}, "/fake-election/1824"),
            ({"RAW_URI": "/a%2Fb"}, "/a%2Fb"),
            ({"REQUEST_URI": "/x?y"}, "/x"),
            ({"RAW_URI": "https://explore.example/x?y"}, "/x"),
            (
                {"RAW_URI": "//fake-election/1824"},
                "/fake-election/1824",
            ),  # as request.path is
            ({"RAW_URI": "https://explore.example"}, "/"),
            (
                {"RAW_URI": "/fake-election/1824#x"},
                "/fake-election/1824",
            ),  # as gunicorn drops it
            ({"RAW_URI": "/fake-election/1824?a=1#x"}, "/fake-election/1824"),
            ({"RAW_URI": "", "REQUEST_URI": ""}, None),
            ({}, None),
        ],
    )
    def test_raw_path(self, environ: dict[str, Any], expected: str | None) -> None:
        assert appmod.raw_path(environ) == expected


class TestNotFoundPage:
    def test_dash_s_custom_404_page_is_not_served_as_a_page(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        register("not_found_404", path="/not-found-404", layout=dash.html.P("gone"))
        TestNotFound.assert_not_found("/not-found-404")
        _, head, _ = get("/")
        assert head.canonical == url("/")


def test_a_repeated_filter_names_the_same_og_url_as_a_single_one(
    register: Callable[..., dict[str, Any]],
) -> None:
    def keep_every_state(params: dict[str, Any]) -> list[tuple[str, str]]:
        value = params.get("state", [])
        return [("state", v) for v in (value if isinstance(value, list) else [value])]

    register(**YEAR_PAGE, query=keep_every_state)
    _, once, _ = get("/fake-election/1824?state=OH")
    _, twice, _ = get("/fake-election/1824?state=OH&state=OH")
    assert once.og_url == twice.og_url == url("/fake-election/1824?state=OH")


def in_query_order(params: dict[str, Any]) -> list[tuple[str, str]]:
    """A parser that keeps the query's own order: the sort must come from the index."""
    return [(k, v) for k, v in params.items() if k in FAKE_FILTERS and isinstance(v, str)]


def test_og_url_sorts_pairs_a_parser_returns_in_query_order(
    register: Callable[..., dict[str, Any]],
) -> None:
    register(**YEAR_PAGE, query=in_query_order)
    _, one, _ = get("/fake-election/1824?state=OH&party=D")
    _, other, _ = get("/fake-election/1824?party=D&state=OH")
    assert one.og_url == other.og_url == url("/fake-election/1824?party=D&state=OH")


def test_og_url_carries_pairs_a_parser_returns_for_an_empty_query(
    register: Callable[..., dict[str, Any]],
) -> None:
    # AC3: og:url is the canonical plus the parser's output pairs, whatever the query.
    register(**YEAR_PAGE, query=lambda params: [("party", "all")])
    _, head, _ = get("/fake-election/1824")
    assert head.og_url == url("/fake-election/1824?party=all")


def test_an_empty_variable_in_a_multi_variable_template_is_not_found_even_cold(
    register: Callable[..., dict[str, Any]],
) -> None:
    # Dash's greedy matcher gives /pair//b the variables x="" and y="b".
    register(
        "fake_pair",
        path_template="/pair/<x>/<y>",
        layout=dash.html.P("pair"),
        prefetch=(api.ELECTIONS_PATH,),
        validate=(api.ELECTIONS_PATH, lambda path_vars, body: True),
    )
    TestNotFound.assert_not_found("/pair//b")
    assert get("/pair/a/b")[0] == 200


@pytest.mark.parametrize("path_vars", [{}, {"year": ""}, {"year": ["1824"]}])
def test_judge_refuses_malformed_variables_itself(path_vars: dict[str, Any]) -> None:
    # A judge that accepts anything: only judge's own well-formedness check refuses.
    accept_all: api.Validate = (api.ELECTIONS_PATH, lambda _vars, _body: True)
    assert api.judge(accept_all, path_vars, RECORDED[api.ELECTIONS_PATH]) is False


def raising_judge(path_vars: dict[str, Any], body: dict[str, Any]) -> bool:
    raise KeyError("data")


class TestAJudgeThatRaises:
    def test_the_index_answers_404_not_500(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        register(**{**YEAR_PAGE, "validate": (api.ELECTIONS_PATH, raising_judge)})
        cached_client(monkeypatch)
        TestNotFound.assert_not_found("/fake-election/1824")

    def test_the_render_refuses_and_fills_nothing(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        validate: api.Validate = (api.ELECTIONS_PATH, raising_judge)
        with api.CLIENT.view() as view:
            assert api.accepted(view.get, validate, {"year": "1824"}) is False
        assert (calls, bucket.waits) == ([], [])
        assert "validate judge raised" in caplog.text


class AlternatingClient:
    """A process client whose snapshot alternates on every read, and counts them."""

    def __init__(self, snapshots: list[api.Snapshot]) -> None:
        self._snapshots = snapshots
        self.reads = 0

    @property
    def snapshot(self) -> api.Snapshot:
        found = self._snapshots[self.reads % len(self._snapshots)]
        self.reads += 1
        return found

    def ensure_refresher(self) -> None:
        return None


@pytest.mark.parametrize("cold_first", [True, False])
def test_status_and_tags_come_from_one_snapshot_read(
    register: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    cold_first: bool,
) -> None:
    """A swap mid-request cannot give a 404 with a canonical, or a 200 without one."""
    register(**YEAR_PAGE)
    cold = api.Snapshot(version=VERSION, responses={api.META_PATH: META})
    warm = api.Snapshot(
        version=VERSION,
        responses={api.META_PATH: META, api.ELECTIONS_PATH: RECORDED[api.ELECTIONS_PATH]},
    )
    client = AlternatingClient([cold, warm] if cold_first else [warm, cold])
    monkeypatch.setattr(api, "CLIENT", client)
    status, head, _ = get("/fake-election/1825")
    assert client.reads == 1
    assert (status == 200) is (head.canonical is not None)
    assert status == (200 if cold_first else 404)


def concrete_page_path(page: dict[str, Any]) -> str:
    template = page.get("path_template")
    if not template:
        return str(page["path"])
    return re.sub(r"<(.*?)>", lambda m: PATH_VALUES[m.group(1)], template)


def test_every_registered_page_is_found_at_the_index_and_reads_nothing(
    register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2 and the index-time contract, registry-wide: every page Dash renders answers
    200 with a canonical naming it, with or without a trailing slash, and nothing the
    index calls (a parser, a callable title or description, a validate) reads the API.
    Dash's custom-404 module is the one exception: it is never served as a page."""
    register(**YEAR_PAGE, query=fake_parser)
    register("not_found_404", path="/not-found-404", layout=dash.html.P("gone"))

    def no_fetch(path: str, timeout: float = 0) -> api.Response:
        raise AssertionError(f"the index fetched {path}")

    client = offline_client(no_fetch)
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.view = no_view_allowed  # type: ignore[method-assign]
    # Serving, with every page's validate source cached from its recorded response
    # (an unrecorded source fails here), so each validate runs and judges.
    sources = {
        path
        for page in dash.page_registry.values()
        if page.get("validate")
        for path in source_paths(page["validate"][0])
    }
    client._snapshot = api.Snapshot(
        version=VERSION,
        responses={api.META_PATH: META} | {path: RECORDED[path] for path in sources},
    )
    monkeypatch.setattr(api, "CLIENT", client)
    checked = 0
    for page in list(dash.page_registry.values()):
        concrete = concrete_page_path(page)
        if page["module"].split(".")[-1] == "not_found_404":
            TestNotFound.assert_not_found(concrete)
            continue
        for path in {concrete, concrete.rstrip("/") + "/"}:
            status, head, _ = get(f"{path}?state=OH")
            assert status == 200, (page["module"], path)
            assert head.canonical == url(concrete), (page["module"], path)
            found, path_vars = _path_to_page(concrete.strip("/"))
            assert found["module"] == page["module"]
            checked += 1
    assert checked >= 3  # "/", and the fake year page with and without a slash


class TestDashPrivates:
    """Item 2: the three Dash privates app.py relies on, pinned by name and behaviour."""

    def test_the_router_matcher_is_exact_and_greedy(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        register(**YEAR_PAGE)
        cases = {
            "": ("pages.home", None),
            "fake-election/1860": ("fake_year", {"year": "1860"}),
            "fake-election/1860/x": (
                "fake_year",
                {"year": "1860/x"},
            ),  # greedy, as Dash is
            "fake-election": (None, None),
            "fake-electionx/1860": (None, None),
            "no-such-view": (None, None),
        }
        for path, (module, path_vars) in cases.items():
            page, found = _path_to_page(path)
            assert (page.get("module"), found) == (module, path_vars), path

    def test_the_index_strips_the_path_as_the_router_does(self) -> None:
        for path in ("/", "/election/1860/", "//a//"):
            assert appmod.app.strip_relative_path(path) == path.strip("/")

    def test_the_query_parser_collapses_single_values_and_keeps_blanks(self) -> None:
        assert _parse_query_string("?a=1&a=2&b=&c=%3C") == {
            "a": ["1", "2"],
            "b": "",
            "c": "<",
        }
        assert _parse_query_string("") == {}

    def test_the_router_lets_the_query_override_a_path_variable(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        # Why item 6 is enforced at render: the layout receives the query's year.
        seen: list[Any] = []

        def echo(year: Any = None, **_query: Any) -> Any:
            seen.append(year)
            return dash.html.P("x")

        register("fake_echo", path_template="/echo/<year>", layout=echo)
        route("/echo/1860", "?year=..")
        assert seen == [".."]

    def test_the_card_tags_are_exactly_these(self) -> None:
        with appmod.server.test_request_context("/"):
            tags = _page_meta_tags(appmod.app, appmod.app.backend.request_adapter())
        keys = [tag.get("property") or tag.get("name") for tag in tags]
        # A Dash that starts emitting og:url or a canonical from request.url fails here.
        assert keys == [
            "description",
            "twitter:card",
            "twitter:url",
            "twitter:title",
            "twitter:description",
            "twitter:image",
            "og:title",
            "og:type",
            "og:description",
            "og:image",
        ]

    def test_pages_meta_is_off_so_dash_adds_no_second_set(self) -> None:
        assert appmod.app.config.include_pages_meta is False


# --- every templated page validates what its layout receives (#312, item 6) ----------

#: Hostile renders for a page's path variables: (path value, query override). Each
#: names a value the recorded ``/v1/elections`` does not serve, or one that is not a
#: plain string at all.
#: Each hostile path value and query override, rendered for every path variable:
#: ``{unserved}`` is the variable's :data:`UNSERVED_VALUES` entry and ``{served}`` its
#: :data:`PATH_VALUES` one, so an override always sits on a value the page serves.
HOSTILE_RENDERS: tuple[tuple[str, str], ...] = (
    ("{unserved}", ""),
    ("{served}/x", ""),
    ("%", ""),
    ("..", ""),
    ("<script>", ""),
    ("{served}", "?{name}=.."),
    ("{served}", "?{name}=1&{name}=2"),
    ("{served}", "?{name}="),
)


def hostile_render_problems(
    page: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """Render a templated page through the routing POST at every hostile value.

    With its validation source cached, a page that validates what its layout receives
    makes no fetch, takes no fill token, answers 200 and renders no success marker.
    """
    template = page["path_template"]
    names = re.findall(r"<(.*?)>", template)
    problems = []
    for value, override in HOSTILE_RENDERS:
        _, calls, bucket = cached_client(monkeypatch, source=page["validate"][0])
        pathname = template
        for name in names:
            concrete = value.format(
                served=PATH_VALUES[name], unserved=UNSERVED_VALUES[name]
            )
            pathname = pathname.replace(f"<{name}>", concrete)
        search = "".join(override.format(name=name) for name in names)
        try:
            response = route(pathname, search)
        except Exception as exc:  # a failing layout may propagate under the test client
            problems.append(f"{pathname}{search}: raised {type(exc).__name__}")
            continue
        case = f"{pathname}{search}"
        if calls:
            problems.append(f"{case}: fetched {calls}")
        if bucket.waits:
            problems.append(f"{case}: took {len(bucket.waits)} fill tokens")
        if response.status_code != 200:
            problems.append(f"{case}: answered {response.status_code}")
        elif page["success"] in routed_ids(response):
            problems.append(f"{case}: rendered its success marker")
    return problems


def templated_pages() -> list[dict[str, Any]]:
    return [page for page in dash.page_registry.values() if page.get("path_template")]


class TestValidateBeforeFill:
    def test_every_registered_templated_page_refuses_every_hostile_value(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        register(**YEAR_PAGE)  # the generic pattern, beside the real /election page
        for page in templated_pages():
            assert hostile_render_problems(page, monkeypatch) == [], page["module"]

    def test_the_check_fails_a_page_that_formats_unvalidated(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        page = register(**{**YEAR_PAGE, "layout": _unvalidated_year_layout})
        problems = hostile_render_problems(page, monkeypatch)
        flagged = {p.split(": ")[0] for p in problems if "fetched" in p or "raised" in p}
        assert len(flagged) == len(HOSTILE_RENDERS), problems

    def test_an_accepted_value_still_fills_on_a_miss(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        register(**YEAR_PAGE)
        _, calls, _ = cached_client(monkeypatch)
        assert "fake-year" in routed_ids(route("/fake-election/1824"))
        assert calls == ["/v1/elections/1824"]

    def test_a_cold_source_costs_one_fill_of_the_source_only(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Approved reading of item 6 (Fred, 2026-10-03): cold, the render may fill the
        # source itself, never a path built from the variable.
        register(**YEAR_PAGE)
        _, calls, _ = cached_client(monkeypatch, elections=False)
        response = route("/fake-election/1825")
        assert response.status_code == 200
        assert "fake-year-missing" in routed_ids(response)
        assert calls == [api.ELECTIONS_PATH]

    @pytest.mark.parametrize(
        "path_vars",
        [{}, {"year": ""}, {"year": ["1824"]}, {"year": None}, {"year": 1824}],
    )
    def test_a_malformed_variable_is_refused_without_a_read(
        self, path_vars: dict[str, Any]
    ) -> None:
        def get(path: str) -> dict[str, Any]:
            raise AssertionError(f"read {path}")

        assert api.accepted(get, FAKE_VALIDATE, path_vars) is False

    def test_anything_but_true_refuses(self) -> None:
        body = RECORDED[api.ELECTIONS_PATH]
        for verdict in (None, 1, "yes", [True]):

            def judge(_vars: dict[str, Any], _body: Any, verdict: Any = verdict) -> Any:
                return verdict

            validate: api.Validate = (api.ELECTIONS_PATH, judge)
            assert api.accepted(lambda p: body, validate, {"year": "1824"}) is False
        assert api.accepted(lambda p: body, FAKE_VALIDATE, {"year": "1824"}) is True


def validate_problems(page: dict[str, Any]) -> list[str]:
    validate = page.get("validate")
    if validate is None:
        return ["a templated page registers no validate"] if page.get(
            "path_template"
        ) else []
    if not page.get("path_template"):
        # It would judge empty path variables, refuse them, and 404 the page.
        return ["a page with no path variables registers validate"]
    source, judge_fn = validate
    problems = []
    if not callable(judge_fn):
        problems.append("validate's judge is not callable")
    # Prefetched, or declared in on_miss and built from no path variable (#279): a
    # source made from the variable it judges would fill a path from an unjudged value.
    path_vars = set(re.findall(r"<(.*?)>", page.get("path_template") or ""))
    if source not in page.get("prefetch", ()) and source not in page.get(
        "on_miss", ()
    ):
        problems.append(f"validate source {source} is neither prefetched nor on_miss")
    if api.placeholders(source) & path_vars:
        problems.append(f"validate source {source} is built from a path variable")
    return problems


def template_problems(page: dict[str, Any]) -> list[str]:
    """What is wrong with a page's ``on_miss`` templates and ``validate`` source names.

    Each placeholder is a path variable or one of ``api.COVERAGE_VARS`` (resolved from
    the index, never from a request); a page naming a coverage variable prefetches the
    index it is resolved from; and no path variable shares a coverage variable's name.
    """
    path_vars = set(re.findall(r"<(.*?)>", page.get("path_template") or ""))
    coverage = set(api.COVERAGE_VARS)
    problems = [
        f"path variable {n} shadows a coverage variable"
        for n in sorted(path_vars & coverage)
    ]
    validate = page.get("validate")
    templates = [*page.get("on_miss", ()), *([validate[0]] if validate else [])]
    named: set[str] = set()
    for template in templates:
        names = api.placeholders(template)
        named |= names
        problems += [
            f"{template} names {n}, neither a path nor a coverage variable"
            for n in sorted(names - path_vars - coverage)
        ]
    if named & coverage and api.ELECTIONS_PATH not in page.get("prefetch", ()):
        problems.append("a page naming a coverage variable does not prefetch the index")
    return problems


class TestRegistryContracts:
    def test_every_validating_page_prefetches_its_source(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        register(**YEAR_PAGE)
        for page in dash.page_registry.values():
            assert validate_problems(page) == [], page["module"]

    @pytest.mark.parametrize(
        ("change", "problem"),
        [
            (
                {"prefetch": ()},
                "validate source /v1/elections is neither prefetched nor on_miss",
            ),
            ({"validate": None}, "a templated page registers no validate"),
            ({"path_template": None}, "a page with no path variables registers validate"),
        ],
    )
    def test_the_check_fails_what_it_should(
        self, change: dict[str, Any], problem: str
    ) -> None:
        assert validate_problems({**YEAR_PAGE, **change}) == [problem]

    @pytest.mark.parametrize(
        ("change", "problems"),
        [
            # A source declared in on_miss, built from coverage alone: accepted (#279).
            (
                {
                    "validate": (api.ROSTER_PATH, known_year),
                    "on_miss": (api.ROSTER_PATH, "/v1/elections/{year}"),
                },
                [],
            ),
            (
                {"validate": (api.ROSTER_PATH, known_year)},
                [f"validate source {api.ROSTER_PATH} is neither prefetched nor on_miss"],
            ),
            (
                {"validate": ("/v1/elections/{year}", known_year)},
                ["validate source /v1/elections/{year} is built from a path variable"],
            ),
        ],
    )
    def test_a_validate_source_may_be_filled_on_a_miss_but_never_from_the_variable(
        self, change: dict[str, Any], problems: list[str]
    ) -> None:
        assert validate_problems({**YEAR_PAGE, **change}) == problems

    def test_every_page_names_only_path_and_coverage_variables(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        register(**YEAR_PAGE)
        coverage = set(api.COVERAGE_VARS)
        naming = 0
        for page in dash.page_registry.values():
            assert template_problems(page) == [], page["module"]
            naming += any(
                api.placeholders(t) & coverage for t in page.get("on_miss", ())
            )
        assert naming >= 2, "the state page and the picker name {year_max}"

    @pytest.mark.parametrize(
        ("change", "problem"),
        [
            (
                {"on_miss": ("/v1/elections/{year_min}",)},
                "/v1/elections/{year_min} names year_min, neither a path nor a "
                "coverage variable",
            ),
            (
                {"path_template": "/fake-x/<year_max>", "on_miss": ()},
                "path variable year_max shadows a coverage variable",
            ),
            (
                {"prefetch": (), "on_miss": (api.ROSTER_PATH,)},
                "a page naming a coverage variable does not prefetch the index",
            ),
        ],
    )
    def test_the_template_check_fails_what_it_should(
        self, change: dict[str, Any], problem: str
    ) -> None:
        assert template_problems({**YEAR_PAGE, **change}) == [problem]

    def test_every_query_parser_keeps_its_contract(self) -> None:
        pages = [*dash.page_registry.values(), {**YEAR_PAGE, "query": fake_parser}]
        checked = 0
        for page in pages:
            if page.get("query") is not None:
                assert parser_problems(page) == [], page.get("module")
                checked += 1
        assert checked

    @pytest.mark.parametrize(
        ("parser", "problem"),
        [
            (lambda q: 1 / 0, "raised ZeroDivisionError"),
            (lambda q: [("state", 1)], "returned a non-str pair"),
            (lambda q: [("year", "1")], "emits a path-variable key: year"),
            (lambda q: [("n", str(len(q)))], "is not idempotent"),
        ],
    )
    def test_the_parser_check_fails_what_it_should(
        self, parser: Callable[..., Any], problem: str
    ) -> None:
        assert problem in parser_problems({**YEAR_PAGE, "query": parser})


#: Hostile query dicts, in the shape ``_parse_query_string`` hands a parser.
HOSTILE_QUERIES: tuple[dict[str, Any], ...] = (
    {},
    {"state": "OH"},
    {"state": ["OH", "CA", "OH"]},
    {"state": ""},
    {"state": HOSTILE, HOSTILE: HOSTILE},
    {"year": "1860", "party": "D"},
    {"state": ["", "%", "&=#"]},
    # The elections index's keys (#306): repeats, an inverted range, a trailing line
    # break, a value outside the vocabulary, a blank, and non-ASCII digits.
    {"year_from": ["1976", "1980"], "year_to": "1900"},
    {"year_from": "2000", "year_to": "1900"},
    {"year_from": "1976\n"},
    {"pv": ["1", "1"]},
    {"pv": "true"},
    {"year_to": ""},
    {"year_from": "١٩٧٦"},
)


def parser_problems(page: dict[str, Any]) -> list[str]:
    """The ``query=`` contract: total, ``str`` pairs, idempotent, no path variables."""
    parser = page["query"]
    names = set(re.findall(r"<(.*?)>", page.get("path_template") or ""))
    problems: list[str] = []
    for query in HOSTILE_QUERIES:
        try:
            pairs = parser(copy.deepcopy(query))
        except Exception as exc:
            problems.append(f"raised {type(exc).__name__}")
            continue
        if not all(
            isinstance(p, tuple) and len(p) == 2 and all(isinstance(x, str) for x in p)
            for p in pairs
        ):
            problems.append("returned a non-str pair")
            continue
        problems += [f"emits a path-variable key: {k}" for k, _ in pairs if k in names]
        encoded = urllib.parse.urlencode(sorted(pairs), quote_via=urllib.parse.quote)
        again = parser(_parse_query_string(f"?{encoded}") if encoded else {})
        if sorted(set(again)) != sorted(set(pairs)):
            problems.append("is not idempotent")
    return problems


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
        assert components.UNAVAILABLE_MESSAGE in text
        assert "SECRET-DETAIL" not in text
        assert "Traceback" not in text

    def test_a_malformed_meta_body_shows_the_plain_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        broken = {"provenance": {"snapshot_version": VERSION}}  # no sources, no coverage
        fetch, _ = fake_fetch({api.META_PATH: broken})
        monkeypatch.setattr(api, "CLIENT", offline_client(fetch))
        assert components.UNAVAILABLE_MESSAGE in " ".join(texts(home_layout()()))

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
            # Nested past the parser's recursion limit: RecursionError, not ValueError.
            _FakeRaw(200, b"[" * 200_000, None),
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

    def test_a_path_two_pages_register_is_fetched_once(self) -> None:
        # Both elections pages register /v1/elections (#307): one fill, one token.
        fetch, calls = fake_fetch(RECORDED)
        bucket = RecordingBucket()
        client = offline_client(
            fetch,
            bucket=bucket,
            prefetch_paths=lambda: [api.ELECTIONS_PATH, api.META_PATH] * 2,
        )
        client.refresh()
        assert calls == [api.META_PATH, api.ELECTIONS_PATH]
        assert len(bucket.waits) == 2

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
        # D072's MVP prefetch extent, exactly: /v1/meta and the elections index (#306).
        # Both elections pages register the index (#307); the refresher fills a path
        # once however many pages register it.
        paths = api.registered_prefetch_paths()
        assert sorted(set(paths)) == sorted([api.META_PATH, api.ELECTIONS_PATH])

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


def template_values(page: dict[str, Any]) -> dict[str, str]:
    """What a page's ``on_miss`` templates are formatted with: its path variables and
    the coverage variables, which share no name (``TestRegistryContracts``)."""
    return {**COVERAGE_VALUES, **concrete_values(page)}


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
        template.format(**template_values(page)) for template in page.get("on_miss", ())
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


#: The validating fake year page as the coverage check renders it: unregistered, at
#: its concrete value.
FAKE_YEAR_PAGE: dict[str, Any] = {"path": "/fake-election/none", **YEAR_PAGE}


def index_with(**coverage: Any) -> dict[str, Any]:
    """The recorded index with its coverage block changed."""
    index = copy.deepcopy(RECORDED[api.ELECTIONS_PATH])
    index["meta"]["provenance"]["coverage"].update(coverage)
    return index


class TestCoverageVars:
    """#279: a coverage variable is formatted into a path, so it is validated as a path
    variable is: only a year the index itself serves, never a value from a request."""

    def test_the_recorded_index_names_its_latest_served_year(self) -> None:
        years = [row["year"] for row in RECORDED[api.ELECTIONS_PATH]["data"]]
        assert api.coverage_vars(RECORDED[api.ELECTIONS_PATH]) == {
            "year_max": str(max(years))
        }

    @pytest.mark.parametrize(
        "index",
        [
            {},
            [],
            "2024",
            {"meta": {"provenance": {}}, "data": []},
            index_with(year_max=True),
            index_with(year_max=2024.0),
            index_with(year_max="2024"),
            index_with(year_max=None),
            index_with(year_max=99999),
            index_with(year_max=999),
            # In range and four digits, but not a year this index serves.
            index_with(year_max=2028),
            index_with(year_max=1826),
        ],
        ids=repr,
    )
    def test_anything_but_a_served_year_is_a_type_error(self, index: Any) -> None:
        with pytest.raises(TypeError):
            api.coverage_vars(index)

    def test_a_served_year_needs_a_served_row_not_only_the_coverage_block(
        self,
    ) -> None:
        index = copy.deepcopy(RECORDED[api.ELECTIONS_PATH])
        index["data"] = [r for r in index["data"] if r["year"] != 2024]
        with pytest.raises(TypeError):
            api.coverage_vars(index)

    def test_a_literal_source_is_read_as_it_is(self) -> None:
        reads: list[str] = []

        def get(path: str) -> dict[str, Any]:
            reads.append(path)
            return RECORDED[path]

        assert api.source_path(api.ELECTIONS_PATH, get) == api.ELECTIONS_PATH
        assert reads == []

    def test_a_template_source_is_resolved_from_the_index_only(self) -> None:
        reads: list[str] = []

        def get(path: str) -> dict[str, Any]:
            reads.append(path)
            return RECORDED[path]

        assert api.source_path(api.ROSTER_PATH, get) == "/v1/elections/2024"
        assert reads == [api.ELECTIONS_PATH]

    def test_accepted_judges_a_template_source_after_resolving_it(self) -> None:
        reads: list[str] = []
        seen: list[Any] = []

        def get(path: str) -> dict[str, Any]:
            reads.append(path)
            return RECORDED[path]

        def judge_fn(path_vars: dict[str, Any], body: Any) -> bool:
            seen.append(body)
            return True

        assert api.accepted(get, (api.ROSTER_PATH, judge_fn), {"usps": "GA"})
        assert reads == [api.ELECTIONS_PATH, "/v1/elections/2024"]
        assert seen == [RECORDED["/v1/elections/2024"]]

    def test_the_index_resolves_a_cached_source_and_never_fills(self) -> None:
        roster = RECORDED["/v1/elections/2024"]
        index = RECORDED[api.ELECTIONS_PATH]
        both = {api.ELECTIONS_PATH: index, "/v1/elections/2024": roster}
        assert api.cached_source(api.ROSTER_PATH, both) is roster
        assert api.cached_source(api.ELECTIONS_PATH, both) is index
        # Cold, or unresolvable: matched (None), never an error and never a read.
        assert api.cached_source(api.ROSTER_PATH, {api.ELECTIONS_PATH: index}) is None
        assert api.cached_source(api.ROSTER_PATH, {"/v1/elections/2024": roster}) is None
        malformed = {**both, api.ELECTIONS_PATH: index_with(year_max=2028)}
        assert api.cached_source(api.ROSTER_PATH, malformed) is None


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
        # Validated from its prefetched source, then filled: rendered, not skipped.
        assert reads == [api.ELECTIONS_PATH, "/v1/elections/1824"]

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
#: that only as the receiver of ``.view``; ``accepted`` reads only through the view's
#: ``get`` it is handed. ``fetch``, ``Client``, ``View``, ``_OPENER`` and ``build_url``
#: would read past the view, the cache and the throttle.
PAGE_API_NAMES = {
    "CLIENT",
    "ApiUnavailable",
    "META_PATH",
    "ELECTIONS_PATH",
    "ROSTER_PATH",
    "Validate",
    "accepted",
    # A pure function of a body the page already read through its view.
    "coverage_vars",
}


def client_misuses(source: str) -> list[int]:
    """Lines where a page reaches ``explore.api`` other than through ``CLIENT.view``.

    Pages import the module (``from explore import api``) and name what they use as
    ``api.<name>``. Flagged: a name outside :data:`PAGE_API_NAMES`; ``CLIENT`` other
    than as the receiver of ``.view``; ``api`` other than as the receiver of an
    attribute (``getattr(api, …)``, ``f = api``); the module reached as an attribute
    (``explore.api``, ``e.api``); any ``from explore.api import …``, absolute or
    relative; and any ``import explore.api``. A module imported under another name
    (``from explore import api as x``) is not tracked.
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
        if isinstance(node, ast.Attribute) and node.attr == "api":
            lines.append(line)  # explore.api.<name>, past the import rules
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
        ("import explore\nexplore.api.fetch(p)\n", True),
        ("import explore as e\ne.api.fetch(p)\n", True),
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
