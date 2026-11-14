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
import gzip
import html
import html.parser
import http.client
import http.server
import json
import logging
import pkgutil
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import dash
import flask
import plotly  # type: ignore[import-untyped]
import pytest
import werkzeug.exceptions
from dash._pages import (
    _page_meta_tags,
    _parse_path_variables,
    _parse_query_string,
    _path_to_page,
)
from dash.dash import _ID_CONTENT, _ID_LOCATION
from dash.development.base_component import Component

from explore import api, components, labels
from explore import app as appmod
from explore.config import SITE_TITLE
from tests.dashboard_fixtures import RECORDED_FILES

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
    for path, name in RECORDED_FILES.items()
}

#: The concrete value each templated page is rendered at, one per path variable. Each
#: must make the page read a path in :data:`RECORDED`.
PATH_VALUES = {"year": "1824", "usps": "GA", "slug": "andrew-jackson"}

#: The coverage variables (``api.COVERAGE_VARS``) as the recorded index resolves them:
#: what an ``on_miss`` template or a ``validate`` source naming one is formatted with.
COVERAGE_VALUES = api.coverage_vars(RECORDED["/v1/elections"])

#: A well-formed value each path variable's page does not serve: what the hostile
#: renders put in the path (#279, so a page validating only syntax is caught).
UNSERVED_VALUES = {"year": "1825", "usps": "ZZ", "slug": "no-such-candidate"}

#: A value each path variable's page accepts other than its :data:`PATH_VALUES` one:
#: what a conflicting query key names (#326). 1860 is served, the roster lists TX and
#: the candidate index lists ``abraham-lincoln``. Only 1860 has every read its page
#: makes recorded: ``/v1/states/TX`` (TX has only its per-capita table) and
#: ``/v1/candidates/abraham-lincoln`` are not, so a page that let the query win would
#: try to read rows no fixture holds.
OTHER_VALUES = {"year": "1860", "usps": "TX", "slug": "abraham-lincoln"}


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


def conflicting_route(pathname: Any = "/election/1824", search: Any = "?year=1860") -> Any:
    """A routing POST body whose query names its page's path variable (#326)."""
    body = copy.deepcopy(ROUTING_POST)
    body["inputs"][0]["value"] = pathname
    body["inputs"][1]["value"] = search
    return body


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


#: A ``/health`` body, for a fake fetch that serves the keep-warm ping (D076).
HEALTH = {"status": "ok"}
OTHER_HEALTH = {"status": "ok", "snapshot_version": "other"}


def offline_client(fetch: Any = None, **kwargs: Any) -> api.Client:
    if fetch is None:
        fetch, _ = fake_fetch({api.META_PATH: META, api.HEALTH_PATH: HEALTH})
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
        "usgov_source_name",
        "usgov_license",
    ):
        p[key] = f"SENTINEL-{key}"
    for key in (
        "ec_license_url",
        "license_url",
        "census_license_url",
        "usgov_license_url",
    ):
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
            # The curated party source (#389), labeled by what it supplies.
            "Parties the National Archives does not print: ": (
                "usgov_source_name",
                "usgov_license",
                "usgov_license_url",
            ),
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
            if appmod.is_not_found_page(page):
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
        # yet the template matches /election/1824, /candidate/andrew-jackson and
        # /election/1824/states, which the registry reaches first: the election
        # subpages are ordered (#465), and an ordered page precedes every other.
        with pytest.raises(AssertionError, match=r"pages\.election_states"):
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


#: The fake year page's not-found state (#325): every validated page registers one.
FAKE_NOT_FOUND = api.NotFound("Fake election not found", "No such fake election.")

YEAR_PAGE: dict[str, Any] = {
    "path_template": "/fake-election/<year>",
    "layout": _validated_year_layout,
    "prefetch": (api.ELECTIONS_PATH,),
    "on_miss": ("/v1/elections/{year}",),
    "success": "fake-year",
    "validate": FAKE_VALIDATE,
    "not_found": FAKE_NOT_FOUND,
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
            if appmod.is_not_found_page(other):
                continue
            taken = concrete_page_path(other).strip("/")
            shared = _parse_path_variables(taken, template.strip("/"))
            assert shared is None, (template, other["module"], taken)
        dash.register_page(module, **page)
        modules.append(module)
        registered: dict[str, Any] = dash.page_registry[module]
        # As app.py does to every page Dash registered at import (#325).
        appmod.follow_validation(registered)
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


def get(path: str, **kwargs: Any) -> tuple[int, Head, str]:
    """GET ``path``. The test client decodes the path's escapes into ``PATH_INFO``,
    as gunicorn does, so the index sees ``request.path`` decoded (D089)."""
    response = appmod.server.test_client().get(path, **kwargs)
    body = response.get_data(as_text=True)
    return response.status_code, Head(body), body


def route(pathname: str, search: str = "") -> Any:
    """The routing POST a browser makes for ``pathname`` and ``search``."""
    body = copy.deepcopy(ROUTING_POST)
    body["inputs"][0]["value"] = pathname
    body["inputs"][1]["value"] = search
    return appmod.server.test_client().post("/_dash-update-component", json=body)


def routed_ids_of(node: Any) -> set[str]:
    """The component ids in a routing response's JSON body."""
    found: set[str] = set()
    if isinstance(node, dict):
        props = node.get("props")
        if isinstance(props, dict) and isinstance(props.get("id"), str):
            found.add(props["id"])
        for value in node.values():
            found |= routed_ids_of(value)
    elif isinstance(node, list):
        for value in node:
            found |= routed_ids_of(value)
    return found


def routed_ids(response: Any) -> set[str]:
    return routed_ids_of(response.get_json())


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
        _, head, _ = get(f"/fake-election/{year}")
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
        status, head, body = get(path)
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


def page_title(body: str) -> str:
    """The text of a page's ``<title>`` element, entities decoded."""
    found = re.findall(r"<title>(.*?)</title>", body, re.DOTALL)
    assert len(found) == 1, found
    return html.unescape(str(found[0]))


def test_card_tags_and_title_escape_a_callable_title_that_echoes_the_path(
    register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A title names a path value only once ``validate`` accepted it (#325), so the
    hostile value reaches the title here through a judge that accepts anything, with
    its source cached: only ``_tag``'s escape stands between it and the card tags, and
    only app.py's between it and ``<title>``, which Dash interpolates unescaped."""
    register(
        **{
            **YEAR_PAGE,
            "validate": (api.ELECTIONS_PATH, lambda path_vars, body: True),
        },
        title=lambda year=None, **_q: f"Election {year}",
        description=lambda year=None, **_q: f"Results for {year}",
    )
    cached_client(monkeypatch)
    quoted = urllib.parse.quote(HOSTILE, safe="")
    status, head, body = get(f"/fake-election/{quoted}")
    assert status == 200
    assert_no_markup(body)
    # Not vacuous: the hostile text is in every title, as text.
    assert page_title(body) == f"Election {HOSTILE}"
    assert head.one("meta", "property", "og:title", "content") == f"Election {HOSTILE}"
    assert head.one("meta", "property", "twitter:title", "content") == (
        f"Election {HOSTILE}"
    )
    assert head.one("meta", "name", "description", "content") == f"Results for {HOSTILE}"
    for tag, attrs in head.tags:
        if tag == "meta":
            assert set(attrs) <= {"name", "property", "content", "charset", "http-equiv"}


def test_tag_escapes_every_character_that_could_leave_an_attribute() -> None:
    tag = appmod._tag("meta", {"content": "\"'<>&"})
    assert tag == '<meta content="&quot;&#x27;&lt;&gt;&amp;">'


#: Dash's router decodes a pathname once with ``unquote``, then strips and matches it
#: (Dash 4.5.0, plotly/dash#4074; D089): one literal table, which the router, the hook
#: (``appmod.router_key``) and the index each answer to. Each row is a pathname a
#: browser can send, the key the router matches it by, and the ``year`` a page at
#: ``/fake-election/<year>`` receives (``None``: that page is not matched). The comment
#: names the change in Dash the row fails on.
DECODED_PATHS: tuple[tuple[str, str, str | None], ...] = (
    ("/fake-election/182%34", "fake-election/1824", "1824"),  # stops decoding
    ("/fake-election/182%2534", "fake-election/182%34", "182%34"),  # decodes twice
    ("/fake-election/%252F", "fake-election/%2F", "%2F"),  # ... or matches a page then
    ("/%2Ffake-election%2F1824%2F", "fake-election/1824", "1824"),  # strips first
    ("/fake-election%2F1824", "fake-election/1824", "1824"),  # decodes variables only
    ("/%66ake-election/1824", "fake-election/1824", "1824"),  # ... after matching
    ("/fake-election/18+24", "fake-election/18+24", "18+24"),  # unquote_plus
    ("/fake-election/%FF", "fake-election/\ufffd", "\ufffd"),  # strict, or latin-1
    ("/fake-election/18%0A24", "fake-election/18\n24", "18\n24"),  # drops DOTALL
    ("/%2F", "", None),
    ("/fake-election/%2F", "fake-election", None),
    # An election subpage spelled with an encoded slash (#465): decoded once, it is
    # /election/2016/states, a real page the echo page never sees (TestElectionPages).
    ("/election/2016%2Fstates", "election/2016/states", None),
)


def echo_year_page(register: Callable[..., dict[str, Any]]) -> list[Any]:
    """Register a page at ``/fake-election/<year>`` that records the ``year`` its
    layout receives, and return the record."""
    seen: list[Any] = []

    def echo(year: Any = None, **_query: Any) -> Any:
        seen.append(year)
        return dash.html.P("x", id="fake-echo")

    register("fake_echo", path_template="/fake-election/<year>", layout=echo)
    return seen


def path_to_page_calls(
    monkeypatch: pytest.MonkeyPatch, owner: Any
) -> list[tuple[str, dict[str, str] | None]]:
    """Record every call of ``owner._path_to_page`` from now on: the key it was given
    and the path variables it returned."""
    calls: list[tuple[str, dict[str, str] | None]] = []
    real = owner._path_to_page

    def spy(key: str) -> Any:
        page, path_vars = real(key)
        calls.append((key, path_vars))
        return page, path_vars

    monkeypatch.setattr(owner, "_path_to_page", spy)
    return calls


def keys_of(calls: list[tuple[str, dict[str, str] | None]]) -> list[str]:
    return [key for key, _ in calls]


class TestEncodedPath:
    """Status and render agree on a percent-encoded path: the index and the router both
    read it decoded once, as the path it spells (D089, which amends D073)."""

    @pytest.mark.parametrize(
        ("pathname", "key", "_year"),
        [row for row in DECODED_PATHS if "\n" not in row[1]],
    )
    def test_the_index_matches_the_key_the_router_matches(
        self, monkeypatch: pytest.MonkeyPatch, pathname: str, key: str, _year: Any
    ) -> None:
        calls = path_to_page_calls(monkeypatch, appmod)
        get(pathname)
        assert keys_of(calls)[:1] == [key]

    def test_a_decoded_newline_never_reaches_the_index(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Flask's catch-all path converter does not match a newline, so the document
        # request answers Flask's own 404 and the app, its router included, never
        # loads: there is no render to disagree with.
        calls = path_to_page_calls(monkeypatch, appmod)
        status, _, body = get("/fake-election/18%0A24")
        assert status == 404 and calls == []
        assert "<title>404 Not Found</title>" in body

    @pytest.mark.parametrize(
        ("pathname", "status", "canonical", "routed"),
        [
            ("/fake-election/182%34", 200, "/fake-election/1824", "fake-year"),
            ("/fake-election%2F1824", 200, "/fake-election/1824", "fake-year"),
            ("/%2Ffake-election%2F1824%2F", 200, "/fake-election/1824", "fake-year"),
            # Decoded once, the year is "182%34": refused, never decoded again.
            ("/fake-election/182%2534", 404, None, "fake-year-missing"),
            ("/fake-election/18+24", 404, None, "fake-year-missing"),
            ("/fake-election/%FF", 404, None, "fake-year-missing"),
            ("/%2F", 200, "/", "coverage"),  # the home page's success marker
            ("/fake-election/%2F", 404, None, "page-not-found"),
        ],
    )
    def test_status_and_render_agree(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        pathname: str,
        status: int,
        canonical: str | None,
        routed: str,
    ) -> None:
        register(**YEAR_PAGE)
        _, calls, _ = cached_client(monkeypatch)
        got, head, _ = get(pathname)
        assert (got, head.canonical) == (
            status,
            None if canonical is None else url(canonical),
        )
        assert head.noindex is (status == 404)
        ids = routed_ids(route(pathname))
        assert routed in ids, ids
        if routed != "fake-year":
            assert "fake-year" not in ids
            assert calls == []  # a refused value fills nothing

    def test_a_leading_double_slash_matches_as_the_router_strips_it(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # gunicorn hands //fake-election/1824 over unnormalized in PATH_INFO; Werkzeug's
        # request.path drops the extra slash, and Dash's router strips it. (The test
        # client would read //fake-election as a host.)
        register(**YEAR_PAGE)
        cached_client(monkeypatch)
        status, head, _ = get(
            "/fake-election/1824",
            environ_overrides={"PATH_INFO": "//fake-election/1824"},
        )
        assert (status, head.canonical) == (200, url("/fake-election/1824"))
        assert "fake-year" in routed_ids(route("//fake-election/1824"))


class TestNotFoundPage:
    def test_dash_s_custom_404_page_is_not_served_as_a_page(self) -> None:
        TestNotFound.assert_not_found(concrete_page_path(appmod.NOT_FOUND_PAGE))
        _, head, _ = get("/")
        assert head.canonical == url("/")


def h1_text(response: Any) -> list[str]:
    """The text of every ``H1`` in a routing response's rendered page."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "H1":
                found.append(str(node.get("props", {}).get("children")))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(response.get_json()["response"]["_pages_content"])
    return found


def store_title(response: Any) -> str:
    """The title Dash's router hands the client, which sets ``document.title``."""
    return str(response.get_json()["response"]["_pages_store"]["data"]["title"])


def has_lede(response: Any) -> bool:
    return '"className":"lede"' in response.get_data(as_text=True).replace(" ", "")


def validated_pages() -> list[dict[str, Any]]:
    return [page for page in dash.page_registry.values() if page.get("validate")]


class TestNotFoundTitle:
    """#325, D083: a not-found path's title, card and tab read as its body does, and a
    title names a value only once the index has checked it is served."""

    def test_every_validated_page_and_only_those_and_the_404_page_register_one(
        self,
    ) -> None:
        validated = validated_pages()
        assert len(validated) >= 3
        for page in dash.page_registry.values():
            not_found = page.get("not_found")
            if page.get("validate") or appmod.is_not_found_page(page):
                assert isinstance(not_found, api.NotFound), page["module"]
                assert all(isinstance(f, str) and f for f in not_found), page["module"]
            else:
                assert not_found is None, page["module"]
        assert [
            p for p in dash.page_registry.values() if appmod.is_not_found_page(p)
        ] == [appmod.NOT_FOUND_PAGE]

    def test_a_validate_without_a_not_found_fails_at_registration(self) -> None:
        page = {"module": "x", "title": "t", "validate": FAKE_VALIDATE}
        with pytest.raises(RuntimeError, match="no not_found"):
            appmod.follow_validation(page)

    @pytest.mark.parametrize("module", [p["module"] for p in validated_pages()])
    def test_a_refused_value_reads_as_not_found_everywhere(
        self, monkeypatch: pytest.MonkeyPatch, module: str
    ) -> None:
        page = dash.page_registry[module]
        not_found: api.NotFound = page["not_found"]
        cached_client(monkeypatch, source=page["validate"][0])
        concrete = re.sub(
            r"<(.*?)>", lambda m: UNSERVED_VALUES[m.group(1)], page["path_template"]
        )
        status, head, body = get(concrete)
        assert status == 404
        assert page_title(body) == not_found.title
        for tag in ("og:title", "twitter:title"):
            assert head.one("meta", "property", tag, "content") == not_found.title
        assert head.one("meta", "name", "description", "content") == not_found.sentence
        for tag in ("og:description", "twitter:description"):
            assert head.one("meta", "property", tag, "content") == not_found.sentence
        routed = route(concrete)
        assert store_title(routed) == not_found.title
        assert [f"{h} — {SITE_TITLE}" for h in h1_text(routed)] == [not_found.title]
        assert not has_lede(routed)

    @pytest.mark.parametrize(
        "module",
        [
            p["module"]
            for p in validated_pages()
            # A prefetched source is cold only before the first snapshot, which
            # test_before_the_first_snapshot_no_title_names_a_value covers.
            if p["validate"][0] != api.ELECTIONS_PATH
        ],
    )
    def test_a_cold_source_names_no_value_then_the_fill_refuses_it(
        self, monkeypatch: pytest.MonkeyPatch, module: str
    ) -> None:
        page = dash.page_registry[module]
        client, _, _ = cached_client(monkeypatch)
        (source,) = [p for p in source_paths(page["validate"][0]) if p != api.ELECTIONS_PATH]
        assert client.snapshot is not None
        assert source not in client.snapshot.responses  # cold, so not vacuous
        concrete = re.sub(
            r"<(.*?)>", lambda m: UNSERVED_VALUES[m.group(1)], page["path_template"]
        )
        status, head, body = get(concrete)
        generic = appmod.page_text(page, "title", None)
        assert status == 200
        assert page_title(body) == generic
        assert head.one("meta", "property", "og:title", "content") == generic
        assert not any(value in generic for value in UNSERVED_VALUES.values())
        # The layout's fill lands before Dash's router calls the title.
        routed = route(concrete)
        assert source in client.snapshot.responses
        assert store_title(routed) == page["not_found"].title
        assert [f"{h} — {SITE_TITLE}" for h in h1_text(routed)] == [
            page["not_found"].title
        ]

    @pytest.mark.parametrize("module", [p["module"] for p in validated_pages()])
    def test_an_accepted_value_keeps_the_page_s_own_title(
        self, monkeypatch: pytest.MonkeyPatch, module: str
    ) -> None:
        page = dash.page_registry[module]
        cached_client(monkeypatch, source=page["validate"][0])
        concrete = concrete_page_path(page)
        _, path_vars = _path_to_page(concrete.strip("/"))
        own = appmod.page_text(page, "title", path_vars)
        assert own == page[appmod._OWN_TITLE](**path_vars)
        status, head, body = get(concrete)
        assert status == 200
        assert page_title(body) == own
        assert head.one("meta", "property", "og:title", "content") == own
        routed = route(concrete)
        assert store_title(routed) == own
        assert has_lede(routed)  # so the not-found test's "no lede" can fail

    @pytest.mark.parametrize(
        "path",
        [
            "/no-such-view",
            "/election",
            "/no-such-%76iew",  # decoded, still no page
        ],
    )
    def test_a_path_no_page_matches_reads_page_not_found(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        not_found: api.NotFound = appmod.NOT_FOUND_PAGE["not_found"]
        cached_client(monkeypatch)
        status, head, body = get(path)
        assert status == 404
        assert page_title(body) == not_found.title
        assert head.one("meta", "property", "og:title", "content") == not_found.title
        assert "page-not-found" in routed_ids(route(path))

    def test_the_404_page_s_body_and_tab_read_as_its_title(self) -> None:
        not_found: api.NotFound = appmod.NOT_FOUND_PAGE["not_found"]
        routed = route("/no-such-view")
        assert "page-not-found" in routed_ids(routed)
        assert store_title(routed) == not_found.title
        assert [f"{h} — {SITE_TITLE}" for h in h1_text(routed)] == [not_found.title]

    @pytest.mark.parametrize(
        ("encoded", "plain"),
        [
            ("/election%2F1825", "/election/1825"),
            ("/election/18%32%35", "/election/1825"),
            ("/election/18%32%34", "/election/1824"),
            ("/%65lections", "/elections"),
        ],
    )
    def test_an_encoded_path_reads_as_the_path_it_spells(
        self, monkeypatch: pytest.MonkeyPatch, encoded: str, plain: str
    ) -> None:
        """Dash's router decodes the pathname before it matches (D089), so an encoded
        path gets the status, title and render of the path it spells."""
        cached_client(monkeypatch)
        seen = []
        for path in (encoded, plain):
            status, head, body = get(path)
            routed = route(path)
            seen.append(
                (
                    status,
                    head.canonical,
                    page_title(body),
                    store_title(routed),
                    routed_ids(routed),
                )
            )
        assert seen[0] == seen[1]
        if plain == "/election/1825":  # not vacuous: the not-found state is reached
            election = dash.page_registry["pages.election"]
            assert seen[0][0] == 404
            assert seen[0][2] == election["not_found"].title
            assert "election-not-found" in seen[0][4]

    @pytest.mark.parametrize("value", [None, "", ["1824"], "<script>", HOSTILE, "1825"])
    def test_the_wrapped_title_is_total_and_never_names_a_refused_value(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        value: Any,
    ) -> None:
        page = register(**YEAR_PAGE, title=lambda year=None, **_q: f"Election {year}")
        cached_client(monkeypatch)
        title = page["title"](year=value)
        assert title == FAKE_NOT_FOUND.title
        assert page["title"](year="1824") == "Election 1824"
        assert page["title"]() == "Election None"  # no variables: its own title

    @pytest.mark.parametrize("value", [None, "", ["x"], "<script>", HOSTILE, "unserved"])
    @pytest.mark.parametrize("state", ["warm", "no snapshot", "source cold"])
    @pytest.mark.parametrize("module", [p["module"] for p in validated_pages()])
    def test_every_real_page_s_registry_title_is_total_and_names_no_refused_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
        module: str,
        state: str,
        value: Any,
    ) -> None:
        """AC3 on the title Dash's router calls (the registry's, which
        follow_validation wraps), for every validated page, its source warm, before
        any snapshot, and with only the index cached. Called directly, so the
        unchecked branch is reached without a failing fill."""
        page = dash.page_registry[module]
        (var,) = re.findall(r"<(.*?)>", page["path_template"])
        if value == "unserved":
            value = UNSERVED_VALUES[var]
        if state == "warm":
            cached_client(monkeypatch, source=page["validate"][0])
        elif state == "source cold":
            client, _, _ = cached_client(monkeypatch)
            assert client.snapshot is not None
            if page["validate"][0] == api.ELECTIONS_PATH:
                pytest.skip("its source is the prefetched index: cached with it")
        else:
            client = offline_client()
            client.ensure_refresher = lambda: None  # type: ignore[method-assign]
            monkeypatch.setattr(api, "CLIENT", client)
            assert api.CLIENT.snapshot is None
        title = page["title"](**{var: value})
        generic = appmod.page_text(page, "title", None)
        assert isinstance(title, str)
        assert title in {page["not_found"].title, generic}
        if isinstance(value, str) and value:
            assert value not in title.replace(SITE_TITLE, "")
        if state != "warm" and api.well_formed({var: value}):
            assert title == generic  # unchecked: the page's own, with no variables

    @pytest.mark.parametrize("module", [p["module"] for p in validated_pages()])
    def test_before_the_first_snapshot_no_title_names_a_value(
        self, monkeypatch: pytest.MonkeyPatch, module: str
    ) -> None:
        """Every validated page, the election page included: with no snapshot yet,
        a served or unserved value answers 200 with the page's generic title."""
        page = dash.page_registry[module]
        client = offline_client()
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        assert api.CLIENT.snapshot is None
        generic = appmod.page_text(page, "title", None)
        (var,) = re.findall(r"<(.*?)>", page["path_template"])
        for values in (PATH_VALUES, UNSERVED_VALUES):
            concrete = page["path_template"].replace(f"<{var}>", values[var])
            status, head, body = get(concrete)
            assert status == 200, concrete
            assert page_title(body) == generic
            assert head.one("meta", "property", "og:title", "content") == generic
            assert not any(v in generic for v in values.values()), generic

    def test_follow_validation_is_idempotent(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        page = register(**YEAR_PAGE)
        wrapper = page["title"]
        appmod.follow_validation(page)
        assert page["title"] is wrapper


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
        not_found=FAKE_NOT_FOUND,
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
@pytest.mark.parametrize("path", ["/fake-election/1825", "/election/1825"])
def test_status_and_tags_come_from_one_snapshot_read(
    register: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    cold_first: bool,
    path: str,
) -> None:
    """A swap mid-request cannot give a 404 with a canonical, or a 200 without one, or
    a title from the other answer. On a real page too, whose registry title
    follow_validation wraps: the index never calls it (#325)."""
    register(**YEAR_PAGE)
    cold = api.Snapshot(version=VERSION, responses={api.META_PATH: META})
    warm = api.Snapshot(
        version=VERSION,
        responses={api.META_PATH: META, api.ELECTIONS_PATH: RECORDED[api.ELECTIONS_PATH]},
    )
    client = AlternatingClient([cold, warm] if cold_first else [warm, cold])
    monkeypatch.setattr(api, "CLIENT", client)
    status, head, body = get(path)
    assert client.reads == 1
    assert (status == 200) is (head.canonical is not None)
    assert status == (200 if cold_first else 404)
    page, _ = _path_to_page(path.strip("/"))
    expected = (
        appmod.page_text(page, "title", None) if cold_first else page["not_found"].title
    )
    assert page_title(body) == expected
    assert head.one("meta", "property", "og:title", "content") == expected


@pytest.mark.parametrize("warm_first", [True, False])
def test_an_accepted_value_s_title_comes_from_the_same_snapshot_read(
    monkeypatch: pytest.MonkeyPatch, warm_first: bool
) -> None:
    """The accepted path is the one where the registry's wrapped title would read the
    snapshot again (it judges the value): the index calls the page's own title
    instead, so a swap mid-request cannot pair a canonical 200 with a title from the
    other answer (#325's acceptance gate, mutant M17)."""
    page = dash.page_registry["pages.election"]
    cold = api.Snapshot(version=VERSION, responses={api.META_PATH: META})
    warm = api.Snapshot(
        version=VERSION,
        responses={api.META_PATH: META, api.ELECTIONS_PATH: RECORDED[api.ELECTIONS_PATH]},
    )
    client = AlternatingClient([warm, cold] if warm_first else [cold, warm])
    monkeypatch.setattr(api, "CLIENT", client)
    status, head, body = get("/election/1824")
    assert client.reads == 1
    assert status == 200
    path_vars = {"year": "1824"} if warm_first else None
    expected = appmod.page_text(page, "title", path_vars)
    assert ("1824" in expected) is warm_first  # accepted names the year; cold does not
    assert page_title(body) == expected
    assert head.one("meta", "property", "og:title", "content") == expected


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
        if appmod.is_not_found_page(page):
            TestNotFound.assert_not_found(concrete)
            continue
        # A query key the page reads (or ignores); never one it moved to another page,
        # which the index redirects (#465, TestMovedFilters).
        query = "?zz=1" if page.get("moved") else "?state=OH"
        for path in {concrete, concrete.rstrip("/") + "/"}:
            status, head, _ = get(f"{path}{query}")
            assert status == 200, (page["module"], path)
            assert head.canonical == url(concrete), (page["module"], path)
            found, path_vars = _path_to_page(concrete.strip("/"))
            assert found["module"] == page["module"]
            checked += 1
    assert checked >= 3  # "/", and the fake year page with and without a slash


#: dcc's bundled plotly.js, inside the ``plotly`` package, as Dash names it (#430).
#: Written out rather than imported from ``explore.app``, so a test does not move with
#: the module under test.
PLOTLYJS_PACKAGE_PATH = "package_data/plotly.min.js"
PLOTLYJS_SUITE_PATH = f"/_dash-component-suites/plotly/{PLOTLYJS_PACKAGE_PATH}"

#: The installed Dash bundles whose plotly.js loading #432 relies on.
RENDERER_BUILD = Path(dash.__file__).parent / "dash-renderer" / "build"
DCC_JS = Path(dash.__file__).parent / "dcc" / "dash_core_components.js"


class TestDashPrivates:
    """Item 2: the Dash privates app.py relies on, pinned by name and behavior."""

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
            # Dash 4.5.0 matches with DOTALL (plotly/dash#4075): a decoded newline.
            "fake-election/18\n24": ("fake_year", {"year": "18\n24"}),
        }
        for path, (module, path_vars) in cases.items():
            page, found = _path_to_page(path)
            assert (page.get("module"), found) == (module, path_vars), path

    @pytest.mark.parametrize(("pathname", "key", "year"), DECODED_PATHS)
    def test_the_router_decodes_the_pathname_once_before_it_strips_and_matches(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        pathname: str,
        key: str,
        year: str | None,
    ) -> None:
        # Observed in a real routing request carrying a query that names the path
        # variable: the key Dash's router hands its matcher, the key app.py's hook
        # matched by, and the variable the layout receives (the path's, so the hook
        # stripped by the router's key). The site navigation's model follows
        # router_key, which must name the same key.
        seen = echo_year_page(register)
        router = path_to_page_calls(monkeypatch, dash.dash)
        hook = path_to_page_calls(monkeypatch, appmod)
        assert route(pathname, "?year=1860").status_code == 200
        assert keys_of(router) == [key]
        assert keys_of(hook) == [key]
        assert seen == ([] if year is None else [year])
        assert appmod.router_key(pathname) == key

    def test_dash_decompresses_a_callback_body_only_by_its_content_encoding(
        self,
    ) -> None:
        # app.py refuses any Content-Encoding on the dispatch endpoint because this is
        # the one way Dash 4.5.0 reads a body other than get_json() (#3925, D089); a
        # Dash that decompressed on another signal would get past the refusal.
        from dash.backends import _flask

        source = Path(_flask.__file__).read_text(encoding="utf-8")
        assert source.count("decompress_payload(") == 1
        assert (
            "                decompress_payload(request.data)\n"
            '                if "gzip" in request.headers.get("Content-Encoding", "")\n'
            "                else request.get_json()\n"
        ) in source

    def test_no_callback_asks_the_client_to_compress_its_request(self) -> None:
        appmod.server.test_client().get("/")  # Dash registers its router on a request
        assert appmod.ROUTER_OUTPUT in appmod.app.callback_map
        specs = [*appmod.app.callback_map.values(), *appmod.app._callback_list]
        # The key is Dash's own name for it, in both collections: a renamed key would
        # otherwise read as "not set" here while the client compressed.
        assert all("compress_payload" in spec for spec in specs)
        assert not any(spec["compress_payload"] for spec in specs)

    def test_the_mcp_server_is_off_whatever_the_environment_says(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Dash's MCP server runs callbacks through a route of its own, which the
        # routing hook never sees (D089). app.py passes enable_mcp=False, and a
        # constructor argument beats DASH_MCP_ENABLED in Dash's config.
        assert appmod.app._enable_mcp is False
        mcp_path = appmod.app._mcp_path
        assert mcp_path and all(
            mcp_path.strip("/") not in rule.rule
            for rule in appmod.server.url_map.iter_rules()
        )
        source = Path(appmod.__file__).read_text(encoding="utf-8")
        assert "    enable_mcp=False,\n" in source
        monkeypatch.setenv("DASH_MCP_ENABLED", "true")
        assert dash._configs.get_combined_config("mcp_enabled", False, False) is False
        # Not vacuous: with no argument, the variable would turn it on.
        assert dash._configs.get_combined_config("mcp_enabled", None, False) is True

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
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Why app.py strips the routing request (#326, D081): without the hook, the
        # layout receives the query's year.
        without_the_hook(monkeypatch)
        seen: list[Any] = []

        def echo(year: Any = None, **_query: Any) -> Any:
            seen.append(year)
            return dash.html.P("x")

        register("fake_echo", path_template="/echo/<year>", layout=echo)
        route("/echo/1860", "?year=..")
        assert seen == [".."]

    def test_the_hook_hands_the_layout_the_paths_value(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        # The hook writes into Werkzeug's cached body, and Dash's dispatch reads that
        # same object: a Dash that re-parses the body would hand the layout "..".
        seen: list[Any] = []

        def echo(year: Any = None, **query: Any) -> Any:
            seen.append((year, query))
            return dash.html.P("x")

        register("fake_echo", path_template="/echo/<year>", layout=echo)
        route("/echo/1860", "?year=..&state=OH")
        assert seen == [("1860", {"state": "OH"})]

    def test_the_routing_request_is_named_as_the_hook_reads_it(self) -> None:
        appmod.server.test_client().get("/")  # Dash registers its router on a request
        assert ROUTING_POST["output"] == appmod.ROUTER_OUTPUT
        router = appmod.app.callback_map[appmod.ROUTER_OUTPUT]
        # The hook reads pathname and search at these positions. The site navigation's
        # marker follows the same Location's pathname, by its id (#448).
        assert _ID_LOCATION == "_pages_location"
        assert router["inputs"] == [
            {"id": _ID_LOCATION, "property": "pathname"},
            {"id": _ID_LOCATION, "property": "search"},
        ]
        assert router["inputs_state_indices"] == {"pathname_": 0, "search_": 1}
        assert router["state"] == []
        # A routing input merges into the layout's keywords after the query, so one
        # named after a path variable would override the path again.
        assert appmod.app.routing_callback_inputs == {}
        rules = [
            rule
            for rule in appmod.server.url_map.iter_rules()
            if rule.endpoint == appmod.DISPATCH_ENDPOINT
        ]
        assert [(r.rule, "POST" in (r.methods or ())) for r in rules] == [
            ("/_dash-update-component", True)
        ]

    def test_the_routers_location_sits_outside_the_content_it_swaps(self) -> None:
        # The site navigation's callback reads this Location's pathname (#448): it is a
        # direct child of page_container, beside the content the router replaces, so a
        # client-side navigation never re-mounts it.
        children = dash.page_container.children
        location = [c for c in children if getattr(c, "id", None) == _ID_LOCATION]
        assert len(location) == 1
        assert type(location[0]).__name__ == "Location"
        content = [c for c in children if getattr(c, "id", None) == _ID_CONTENT]
        assert len(content) == 1
        inside = getattr(content[0], "children", None) or []
        assert location[0] not in (inside if isinstance(inside, list) else [inside])

    def test_dcc_link_renders_no_aria_attribute(self) -> None:
        # Why NAV_CALLBACK writes aria-current onto the links in the browser rather
        # than as a callback output (#448, D086): dcc.Link takes no aria-* prop. If an
        # upgrade adds one, this fails and the marker can become a declared output.
        link = dash.dcc.Link("x", href="/")
        assert link._valid_wildcard_attributes == []
        assert "aria-current" not in link.available_properties
        with pytest.raises(TypeError, match="aria-current"):
            aria: dict[str, Any] = {"aria-current": "page"}
            dash.dcc.Link("x", href="/", **aria)

    def test_the_card_tags_are_dash_s_without_twitter_url(self) -> None:
        """app.py builds the card tags itself (#325); they stay Dash's set, less the raw
        request URL. Dash's builder is read here as the reference, never at runtime."""
        with appmod.server.test_request_context("/"):
            dash_tags = _page_meta_tags(
                appmod.app, appmod.app.backend.request_adapter()
            )
            resolution = appmod.resolve("/", "", None)
            ours = appmod.card_tags(resolution, flask.request.url_root)
        keys = [tag.get("property") or tag.get("name") for tag in ours]
        # A Dash that starts emitting og:url or a canonical from request.url fails here.
        assert keys == [
            "description",
            "twitter:card",
            "twitter:title",
            "twitter:description",
            "twitter:image",
            "og:title",
            "og:type",
            "og:description",
            "og:image",
        ]
        assert [t for t in dash_tags if t.get("property") != "twitter:url"] == ours

    def test_the_index_never_calls_dash_s_card_builder(self) -> None:
        """Dash's builder calls the registry's title, which follow_validation wraps to
        read the snapshot: the index's one snapshot read would become two (#325)."""
        tree = ast.parse(Path(appmod.__file__).read_text(encoding="utf-8"))
        names = {
            node.id if isinstance(node, ast.Name) else node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Name | ast.Attribute)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "_page_meta_tags" not in names

    def test_pages_meta_is_off_so_dash_adds_no_second_set(self) -> None:
        assert appmod.app.config.include_pages_meta is False

    def test_the_router_reads_the_registry_title_per_request_after_the_layout(
        self, register: Callable[..., dict[str, Any]]
    ) -> None:
        """follow_validation (#325) relies on both: the wrapper put in the registry is
        what the router calls, and a layout's fill on a miss has landed by then."""
        events: list[str] = []

        def layout(**_q: Any) -> Any:
            events.append("layout")
            return dash.html.P("x")

        def title(**_q: Any) -> str:
            events.append("title")
            return "first"

        page = register("fake_order", path="/fake-order", layout=layout, title=title)
        assert store_title(route("/fake-order")) == "first"
        assert events == ["layout", "title"]
        page["title"] = lambda **_q: "replaced"
        assert store_title(route("/fake-order")) == "replaced"

    def test_the_client_sets_the_tab_from_the_router_s_title(self) -> None:
        """The browser tab is the router's title (Dash's clientside callback), with no
        "Updating…" title between: the tab half of #325 rests on both."""
        _, _, body = get("/")
        assert "document.title = data.title" in body
        assert appmod.app.config.update_title is None

    def test_dcc_s_plotlyjs_entry_is_the_one_app_py_marks(self) -> None:
        """#430: the entry ``Dash._setup_plotlyjs`` adds, with app.py's mark. A Dash
        that reshapes it, adds a second one, or stops calling the method app.py
        overrides fails here, before the file could be served again."""
        entries = [e for e in dash.dcc._js_dist if e.get("namespace") == "plotly"]
        assert len(entries) == 1
        (entry,) = entries
        assert set(entry) == {
            "relative_package_path",
            "external_url",
            "namespace",
            "async",
            "external_only",
        }
        assert entry["relative_package_path"] == PLOTLYJS_PACKAGE_PATH
        assert entry["external_only"] is True
        assert entry["async"] == "eager"
        # The one address #432 points graphs at, from the same call.
        assert entry["external_url"] == appmod.app._plotlyjs_url
        assert re.fullmatch(
            r"https://cdn\.plot\.ly/plotly-[0-9.]+\.min\.js", entry["external_url"]
        )

    def test_the_config_points_graphs_at_the_cdn(self) -> None:
        """#432: the client config tells the browser ``serve_locally: false`` and
        carries ``plotlyjs_url``, Dash's own address, while the app still serves its
        other assets locally. A Dash that stops reading these keys fails the bundle
        pins below."""
        config = appmod.app._config()
        assert config["serve_locally"] is False
        assert config["plotlyjs_url"] == appmod.app._plotlyjs_url
        assert appmod.app.config.serve_locally is True
        # The control: Dash's own config sends no address while serving locally,
        # which is why the override must set both keys.
        dash_s = dash.Dash._config(appmod.app)
        assert dash_s["serve_locally"] is True
        assert "plotlyjs_url" not in dash_s

    def test_the_address_is_plotly_s_cdn_for_the_installed_plotlyjs(self) -> None:
        """#432: one address, derived by Dash from the installed plotly: its host is
        ``cdn.plot.ly`` and its version is the installed plotly.js's, as the bundled
        file's own banner names it."""
        from plotly.offline import (  # type: ignore[import-untyped]
            get_plotlyjs_version,
        )

        url = urllib.parse.urlsplit(appmod.app._plotlyjs_url)
        version = get_plotlyjs_version()
        assert (url.scheme, url.netloc) == ("https", "cdn.plot.ly")
        assert url.path == f"/plotly-{version}.min.js"
        assert not url.query and not url.fragment
        bundled = Path(plotly.__file__).parent / PLOTLYJS_PACKAGE_PATH
        with bundled.open(encoding="utf-8") as handle:
            banner = handle.read(200)
        assert re.search(rf"\* plotly\.js v{re.escape(version)}\n", banner), banner

    @pytest.mark.parametrize("bundle", ["dash_renderer.min.js", "dash_renderer.dev.js"])
    def test_the_renderer_chooses_the_plotlyjs_address_from_the_config(
        self, bundle: str
    ) -> None:
        """#432: the renderer reads ``serve_locally`` in one place, to set
        ``window._dashPlotlyJSURL`` to the local package path or to ``plotlyjs_url``,
        in the minified bundle and the development one alike."""
        text = (RENDERER_BUILD / bundle).read_text(encoding="utf-8")
        assert text.count("serve_locally") == 1
        flat = " ".join(text.split())
        local = (
            '"".concat({c}.requests_pathname_prefix, '
            '"_dash-component-suites/plotly/package_data/plotly.min.js")'
        )
        if bundle.endswith(".min.js"):
            match = re.search(
                r'(\w+)\.serve_locally\?window\._dashPlotlyJSURL=""\.concat\(\1\.'
                r'requests_pathname_prefix,"_dash-component-suites/plotly/package_data/'
                r'plotly\.min\.js"\):window\._dashPlotlyJSURL=\1\.plotlyjs_url',
                flat,
            )
            assert match, bundle
        else:
            expected = (
                "if (config.serve_locally) { window._dashPlotlyJSURL = "
                + local.format(c="config")
                + "; } else { window._dashPlotlyJSURL = config.plotlyjs_url; }"
            )
            assert expected in flat

    def test_dcc_loads_plotlyjs_from_that_address_when_a_graph_mounts(self) -> None:
        """#432: dcc's loader, as its text reads: it takes ``window._dashPlotlyJSURL``
        and appends an async script with no ``integrity`` or ``crossOrigin`` (the
        residual D087 records), and only when ``window.Plotly`` is not already loaded.
        That short-circuit is load-bearing since #452 (D088): the app's mount callback
        puts a graph in only once ``window.Plotly`` is set, so this loader never
        appends a script or fetches, and a blocked CDN cannot make Dash loop; if dcc
        dropped the check, a mounted graph would fetch plotly.js a second time
        (``test_one_plotlyjs_script_one_fetch_and_the_apps_load`` and
        ``test_two_charts_on_a_page_share_one_load`` in
        ``tests/e2e/test_dashboard_e2e_charts.py``, which count fetches and scripts).
        This pins the loader's text only, not when it runs: that a page with no chart
        fetches no plotly.js is the browser's to show
        (``test_a_page_with_no_chart_fetches_no_plotlyjs`` in
        ``tests/e2e/test_dashboard_e2e_charts.py``, and the e2e guard's zero-fetch
        default in ``tests/e2e/conftest.py``)."""
        text = DCC_JS.read_text(encoding="utf-8")
        assert text.count("_dashPlotlyJSURL") == 1
        start = text.index("Promise.resolve(window.Plotly||new Promise(")
        loader = text[start : text.index("document.querySelector", start) + 60]
        assert re.search(
            r'(\w)=document\.createElement\("script"\);\1\.src='
            r"window\._dashPlotlyJSURL,\1\.async=!0",
            loader,
        ), loader
        assert "appendChild" in loader
        assert "integrity" not in loader and "crossOrigin" not in loader
        assert "integrity" not in text

    def test_external_only_keeps_only_the_cdn_address(self) -> None:
        """#430: the app's own script filter, with the config it runs on after a
        request (served locally, no eager loading), drops the package path of an
        ``external_only`` entry, so the path is never registered; and keeps it a
        dynamic resource, so no page gains a script tag."""
        (entry,) = [e for e in dash.dcc._js_dist if e.get("namespace") == "plotly"]
        get("/")  # Dash's _setup_server settles the scripts' config on a request
        assert appmod.app.scripts.config.serve_locally is True
        assert appmod.app.scripts.config.eager_loading is False
        resources = appmod.app.scripts._resources
        marked: Any = dict(entry, external_only=True)
        assert resources._filter_resources([marked]) == [
            {
                "external_url": entry["external_url"],
                "dynamic": True,
                "namespace": "plotly",
            }
        ]
        # The control: without the mark, Dash keeps the package path, which is what
        # registers the file and lets the app serve it.
        unmarked: Any = {k: v for k, v in entry.items() if k != "external_only"}
        assert resources._filter_resources([unmarked]) == [
            {
                "relative_package_path": PLOTLYJS_PACKAGE_PATH,
                "dynamic": True,
                "namespace": "plotly",
            }
        ]

    def test_the_suite_route_s_endpoint_is_its_url_rule(self) -> None:
        """#439: app.py wraps the view registered under the component-suite route's
        endpoint, which Dash's Flask backend names after the route's URL rule."""
        (rule,) = [
            r
            for r in appmod.server.url_map.iter_rules()
            if r.rule.startswith("/_dash-component-suites/")
        ]
        assert rule.endpoint == SUITE_ENDPOINT
        assert rule.endpoint == appmod.SUITE_ENDPOINT

    def test_a_registered_missing_file_raises_file_not_found(self) -> None:
        """#439: the component-suite route reads a registered file with
        ``pkgutil.get_data``, which raises ``FileNotFoundError`` for one the package
        does not contain; app.py's wrapper keys on that exception."""
        namespace, path = MISSING_SUITE_FILES[0]
        assert (namespace, path) in registered_suite_paths()
        view = appmod.server.view_functions[SUITE_ENDPOINT]
        assert view is appmod._suite_view
        dash_view = view.__wrapped__  # Dash's own view, which app.py wraps
        with appmod.server.test_request_context(), pytest.raises(FileNotFoundError):
            dash_view(package_name=namespace, fingerprinted_path=path)

    def test_an_unregistered_suite_path_raises_dependency_exception(self) -> None:
        """#430: app.py's 404 handler keys on the exception Dash's component-suite
        route raises for a path it never registered."""
        with pytest.raises(dash.exceptions.DependencyException):
            dash._validate.validate_js_path({"dash": set()}, "dash", "no/such.js")
        with pytest.raises(dash.exceptions.DependencyException):
            dash._validate.validate_js_path({}, "plotly", PLOTLYJS_PACKAGE_PATH)


#: The plotly.js entry ``Dash._setup_plotlyjs`` appends, as the override checks it.
PLOTLYJS_ENTRY = {
    "relative_package_path": PLOTLYJS_PACKAGE_PATH,
    "external_url": "https://cdn.plot.ly/plotly-0.0.0.min.js",
    "namespace": "plotly",
    "async": "eager",
}


class TestPlotlyjsOverride:
    """#430: app.py's ``_setup_plotlyjs`` marks only the one entry Dash's call adds,
    and fails the import on any other addition. Driven against a fake Dash call and
    a throwaway ``dcc._js_dist``, so the shared app is never rebuilt."""

    @staticmethod
    def run_override(
        monkeypatch: pytest.MonkeyPatch, added: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        existing = {"namespace": "dash", "relative_package_path": "dcc/x.js"}
        monkeypatch.setattr(dash.dcc, "_js_dist", [existing])

        def dash_s(_self: Any) -> None:
            dash.dcc._js_dist.extend(copy.deepcopy(added))

        monkeypatch.setattr(dash.Dash, "_setup_plotlyjs", dash_s)
        appmod.ExploreDash._setup_plotlyjs(object.__new__(appmod.ExploreDash))
        return list(dash.dcc._js_dist)

    def test_the_one_added_entry_is_marked_and_nothing_else(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dist = self.run_override(monkeypatch, [PLOTLYJS_ENTRY])
        assert dist[0] == {"namespace": "dash", "relative_package_path": "dcc/x.js"}
        assert dist[1] == {**PLOTLYJS_ENTRY, "external_only": True}

    @pytest.mark.parametrize(
        "added",
        [
            [],
            [PLOTLYJS_ENTRY, PLOTLYJS_ENTRY],
            [{**PLOTLYJS_ENTRY, "relative_package_path": "package_data/other.js"}],
            [{**PLOTLYJS_ENTRY, "namespace": "dash"}],
        ],
        ids=["none", "two", "other-path", "other-namespace"],
    )
    def test_any_other_addition_fails_and_marks_nothing(
        self, monkeypatch: pytest.MonkeyPatch, added: list[dict[str, Any]]
    ) -> None:
        with pytest.raises(RuntimeError, match="unexpected plotly.js entries"):
            self.run_override(monkeypatch, added)
        assert not any("external_only" in entry for entry in dash.dcc._js_dist)


class TestPlotlyjsNotServed:
    """#430: the app serves no copy of plotly.js; graphs fetch it from its CDN (#432)."""

    def test_the_plotlyjs_path_answers_404_and_is_never_registered(self) -> None:
        response = appmod.server.test_client().get(PLOTLYJS_SUITE_PATH)
        assert response.status_code == 404
        assert b"plotly" not in response.data.lower()
        assert len(response.data) < 1000
        assert "plotly" not in appmod.app.registered_paths
        # The control: Dash did register its resources on that request, so the check
        # above is not passing because registration never ran.
        assert "dash" in appmod.app.registered_paths

    def test_any_unregistered_suite_path_answers_404(self) -> None:
        for path in (
            "/_dash-component-suites/dash/no/such.js",
            "/_dash-component-suites/no_such_package/x.js",
        ):
            assert appmod.server.test_client().get(path).status_code == 404, path

    def test_a_registered_suite_file_is_still_served(self) -> None:
        """The handler changes only the refusal: Dash's own bundles still load."""
        _, _, body = get("/")
        srcs = re.findall(r'<script src="([^"]+)"', body)
        suite = [s for s in srcs if s.startswith("/_dash-component-suites/dash/")]
        assert suite
        response = appmod.server.test_client().get(suite[0])
        assert response.status_code == 200
        assert response.data

    def test_the_index_loads_no_plotlyjs_and_names_only_the_cdn_address(self) -> None:
        """The index shell every page shares loads no plotly.js: no script tag names
        it or an off-site host, so it stays off the first data cell's path. The client
        config carries exactly the CDN address with ``serve_locally: false`` (#432),
        which dcc reads only when a graph mounts."""
        _, _, body = get("/")
        srcs = re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", body)
        assert srcs
        for src in srcs:
            assert "plotly" not in src.lower(), src
            assert src.startswith("/") and not src.startswith("//"), src
        config = re.search(
            r'<script id="_dash-config" type="application/json">(.*?)</script>',
            body,
            re.DOTALL,
        )
        assert config is not None
        sent = json.loads(html.unescape(config.group(1)))
        assert sent["serve_locally"] is False
        assert sent["plotlyjs_url"] == appmod.app._plotlyjs_url
        assert body.count("cdn.plot.ly") == 1


#: The component-suite route's Flask endpoint, as Dash's Flask backend names it (its
#: URL rule). Written out rather than imported, as :data:`PLOTLYJS_PACKAGE_PATH` is.
SUITE_ENDPOINT = (
    "/_dash-component-suites/<string:package_name>/<path:fingerprinted_path>"
)

#: The files Dash 4.5.0 registers but does not install (#439), as (namespace, path).
MISSING_SUITE_FILES = (
    ("dash", "dash-renderer/build/dash_renderer.min.js.map"),
    ("dash", "dcc/async-mathjax.js.map"),
)


#: The suite view's warning for a registered file it did not install (#439).
MISSING_FILE_WARNING = "component-suite file registered but not installed"

#: Flask's default 404 body (Werkzeug's ``NotFound``), which #430's handler and the
#: suite view's refusal both answer with.
NOT_FOUND_BODY = werkzeug.exceptions.NotFound().get_response().get_data()

#: A path no Dash release ships, and not a source map: registered by a test to show
#: the 404 follows the read's error, not a list of file names.
SYNTHETIC_MISSING_FILE = ("dash", "dcc/no-such-chunk.js")


def suite_file(namespace: str, path: str) -> Path:
    """Where Dash's component-suite route reads ``path`` from: the directory of the
    package module itself, as ``pkgutil.get_data`` resolves it."""
    module_file = sys.modules[namespace].__file__
    assert module_file is not None
    return Path(module_file).parent / path


def registered_suite_paths() -> list[tuple[str, str]]:
    """Every component-suite path the app has registered, after an index render
    (Dash registers its resources while building the index's script tags)."""
    get("/")
    return sorted(
        (namespace, path)
        for namespace, paths in appmod.app.registered_paths.items()
        for path in paths
    )


def suite_get(namespace: str, path: str) -> Any:
    return appmod.server.test_client().get(
        f"/_dash-component-suites/{namespace}/{path}"
    )


def error_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Records at error level or above, and any record carrying a traceback."""
    return [
        r for r in caplog.records if r.levelno >= logging.ERROR or r.exc_info
    ]


def missing_file_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and MISSING_FILE_WARNING in r.getMessage()
    ]


class TestMissingSuiteFile:
    """#439: a component-suite file Dash registers but did not install answers 404
    and one warning, not 500 with a logged traceback."""

    @pytest.mark.parametrize(("namespace", "path"), MISSING_SUITE_FILES)
    def test_a_registered_missing_file_answers_404_and_warns_once(
        self, caplog: pytest.LogCaptureFixture, namespace: str, path: str
    ) -> None:
        # Its premises: Dash registers the path, so #430's unregistered-path handler
        # does not answer it, and the installed package lacks the file.
        assert (namespace, path) in registered_suite_paths()
        assert not suite_file(namespace, path).exists()
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            response = suite_get(namespace, path)
        assert response.status_code == 404
        assert response.data == NOT_FOUND_BODY
        assert response.mimetype == "text/html"
        assert error_records(caplog) == []
        (warning,) = missing_file_warnings(caplog)
        assert repr(namespace) in warning and repr(path) in warning

    def test_the_404_follows_the_read_s_error_not_a_list_of_names(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A registered path no release ships, and not a source map, is answered
        the same way: the refusal keys on the error, not on the two names."""
        namespace, path = SYNTHETIC_MISSING_FILE
        registered_suite_paths()
        paths = appmod.app.registered_paths[namespace]
        monkeypatch.setitem(appmod.app.registered_paths, namespace, {*paths, path})
        assert not suite_file(namespace, path).exists()
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            response = suite_get(namespace, path)
        assert response.status_code == 404
        assert response.data == NOT_FOUND_BODY
        assert error_records(caplog) == []
        (warning,) = missing_file_warnings(caplog)
        assert repr(path) in warning

    @pytest.mark.parametrize(
        "path",
        ["dcc/dash_core_components.js", "dcc/async-mathjax.js", "dcc/async-graph.js"],
    )
    def test_an_installed_file_is_still_served(self, path: str) -> None:
        """The control: a bundle a page uses, the chunk a chart loads, and the math
        chunk a later ``dcc.Markdown`` page would need all still answer 200."""
        assert ("dash", path) in registered_suite_paths()
        response = suite_get("dash", path)
        assert response.status_code == 200
        assert response.data == suite_file("dash", path).read_bytes()

    def test_no_registered_suite_path_answers_5xx(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Every registered path answers 200 when its file is installed, and 404
        when it is not; and the files that are not are exactly the known two, so a
        Dash upgrade that changes that list fails here until the list is updated."""
        paths = registered_suite_paths()
        assert len(paths) >= 20  # Dash, dcc, html and dash_table's files
        missing = []
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            for namespace, path in paths:
                status = suite_get(namespace, path).status_code
                installed = suite_file(namespace, path).exists()
                assert status == (200 if installed else 404), (namespace, path, status)
                if not installed:
                    missing.append((namespace, path))
        assert error_records(caplog) == []
        assert set(missing) == set(MISSING_SUITE_FILES)
        assert len(missing_file_warnings(caplog)) == len(missing)

    def test_another_error_from_the_read_stays_a_logged_500(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Only ``FileNotFoundError`` is refused: any other error reading an
        installed file stays a 500 with its traceback logged."""

        def refuse(package: str, resource: str) -> bytes:
            raise PermissionError(resource)

        monkeypatch.setattr(pkgutil, "get_data", refuse)
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            response = suite_get("dash", "dcc/dash_core_components.js")
        assert response.status_code == 500
        (record,) = error_records(caplog)
        assert record.exc_info is not None
        assert record.exc_info[0] is PermissionError
        assert missing_file_warnings(caplog) == []

    def test_a_missing_file_in_a_request_hook_stays_a_logged_500(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Only Dash's view is wrapped: a ``FileNotFoundError`` raised before the
        view runs, on a suite request, stays a 500 with its traceback logged."""

        def raise_missing() -> None:
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(api.CLIENT, "ensure_refresher", raise_missing)
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            response = suite_get("dash", "dcc/dash_core_components.js")
        assert response.status_code == 500
        (record,) = error_records(caplog)
        assert record.exc_info is not None
        assert record.exc_info[0] is FileNotFoundError
        assert missing_file_warnings(caplog) == []

    def test_a_missing_file_elsewhere_still_answers_500_and_is_logged(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The refusal is the component-suite route's only: a
        ``FileNotFoundError`` on any other route stays a logged 500."""

        def raise_missing() -> None:
            raise FileNotFoundError("no such file")

        monkeypatch.setitem(appmod.server.view_functions, "_warmup", raise_missing)
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            response = appmod.server.test_client().get("/_ah/warmup")
        assert response.status_code == 500
        (record,) = error_records(caplog)
        assert record.exc_info is not None
        assert record.exc_info[0] is FileNotFoundError


# --- every templated page validates what its layout receives (#312, item 6) ----------

#: Hostile renders for a page's path variables: (path value, query part), each
#: rendered for every path variable. Each puts in the path a value the page does not
#: serve, or one that is not a plain string at all. ``{unserved}`` is the variable's
#: :data:`UNSERVED_VALUES` entry and ``{served}`` its :data:`PATH_VALUES` one. The last
#: adds a query key named after the variable, which app.py drops before the router runs
#: (#326, D081; :class:`TestPathVariableWins`): a served query value cannot rescue an
#: unserved path, and without the hook the page would fill the served value.
HOSTILE_RENDERS: tuple[tuple[str, str], ...] = (
    ("{unserved}", ""),
    ("{served}/x", ""),
    ("%", ""),
    ("..", ""),
    ("<script>", ""),
    ("{unserved}", "{name}={served}"),
)

#: Hostile values delivered by the query, on a path the page serves. app.py's hook
#: keeps them from the layout (D081); these rows are rendered with the hook off, the
#: case ``api.accepted`` stays behind it for, should a Dash upgrade disable it.
QUERY_RENDERS: tuple[tuple[str, str], ...] = (
    ("{served}", "{name}=.."),
    ("{served}", "{name}=1&{name}=2"),
    ("{served}", "{name}="),
)


def without_the_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable app.py's strip: ``_strip_routing_request`` looks it up at call time."""
    monkeypatch.setattr(appmod, "strip_path_variables", lambda _path, search: search)


def hostile_render_problems(
    page: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    rows: tuple[tuple[str, str], ...] = HOSTILE_RENDERS,
) -> list[str]:
    """Render a templated page through the routing POST at every hostile value in
    ``rows``.

    With its validation source cached, a page that validates what its layout receives
    makes no fetch, takes no fill token, answers 200 and renders no success marker.
    """
    template = page["path_template"]
    names = re.findall(r"<(.*?)>", template)
    problems = []
    for value, override in rows:
        _, calls, bucket = cached_client(monkeypatch, source=page["validate"][0])
        pathname = template
        for name in names:
            concrete = value.format(
                served=PATH_VALUES[name], unserved=UNSERVED_VALUES[name]
            )
            pathname = pathname.replace(f"<{name}>", concrete)
        parts = [
            override.format(name=name, served=PATH_VALUES[name])
            for name in names
            if override
        ]
        search = "?" + "&".join(parts) if parts else ""
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

    def test_without_the_hook_every_page_refuses_a_hostile_query_value(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D081's fallback: with app.py's hook disabled the query reaches the layout
        # again, and the page's own validation still refuses it.
        without_the_hook(monkeypatch)
        register(**YEAR_PAGE)
        for page in templated_pages():
            assert hostile_render_problems(page, monkeypatch, QUERY_RENDERS) == [], page[
                "module"
            ]

    def test_the_check_fails_a_page_that_formats_unvalidated(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        page = register(**{**YEAR_PAGE, "layout": _unvalidated_year_layout})

        def flagged(problems: list[str]) -> set[str]:
            return {p.split(": ")[0] for p in problems if "fetched" in p or "raised" in p}

        problems = hostile_render_problems(page, monkeypatch)
        assert len(flagged(problems)) == len(HOSTILE_RENDERS), problems
        without_the_hook(monkeypatch)
        problems = hostile_render_problems(page, monkeypatch, QUERY_RENDERS)
        assert len(flagged(problems)) == len(QUERY_RENDERS), problems

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


# --- the path's value wins over a query key named after it (#326, D081) --------------

#: A filter that is no path variable, sent with and without each conflicting key.
PLAIN_FILTER = "state=OH"


def conflicts(name: str) -> list[str]:
    """Query parts naming the path variable ``name``, as Dash's parser reads them."""
    other = OTHER_VALUES[name]
    encoded = f"%{ord(name[0]):02X}{name[1:]}"  # "%79ear": "year" once decoded
    return [
        f"{name}={other}",
        f"{name}=..",
        f"{name}=1&{name}=2",
        f"{name}=",
        f"{encoded}={other}",
        name,  # no "=": a blank value
    ]


def conflict_problems(
    page: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """Route a templated page at its served value with each conflicting query key.

    The oracle is the same route without the key, each on a fresh client: the status,
    the response, the reads and the fill tokens must all be the same, and the control
    renders the page's success marker.
    """
    pathname = concrete_page_path(page)
    source = page["validate"][0]

    def render(search: str) -> tuple[int, Any, list[str], int]:
        _, calls, bucket = cached_client(monkeypatch, source=source)
        response = route(pathname, search)
        return response.status_code, response.get_json(), list(calls), len(bucket.waits)

    control = render(f"?{PLAIN_FILTER}")
    problems = []
    if control[0] != 200 or page["success"] not in routed_ids_of(control[1]):
        problems.append(f"{pathname}?{PLAIN_FILTER}: did not render")
    for name in re.findall(r"<(.*?)>", page["path_template"]):
        for conflict in conflicts(name):
            search = f"?{conflict}&{PLAIN_FILTER}"
            try:
                seen = render(search)
            except Exception as exc:  # a failing layout may propagate here
                problems.append(f"{pathname}{search}: raised {type(exc).__name__}")
                continue
            if seen != control:
                problems.append(f"{pathname}{search}: differs without the key")
    return problems


def encoded_route(
    pathname: str, search: str, encoding: str = "gzip", body: bytes | None = None
) -> Any:
    """A routing POST whose JSON body is gzip-compressed and sent with
    ``Content-Encoding: encoding``."""
    payload = json.dumps(conflicting_route(pathname, search)).encode()
    return appmod.server.test_client().post(
        "/_dash-update-component",
        data=gzip.compress(payload) if body is None else body,
        headers={"Content-Encoding": encoding, "Content-Type": "application/json"},
    )


class TestEncodedDispatch:
    """#456, D089: Dash 4.5.0 decompresses a gzip callback body (plotly/dash#3925)
    that the routing hook cannot read, so the dispatch endpoint refuses any encoded
    body before Dash reads it."""

    @pytest.mark.parametrize(
        "encoding", ["gzip", "GZIP", " gzip ", "x-gzip", "deflate", "br", "identity, gzip"]
    )
    def test_an_encoded_routing_request_is_refused(
        self, register: Callable[..., dict[str, Any]], encoding: str
    ) -> None:
        seen = echo_year_page(register)
        response = encoded_route("/fake-election/1824", "?year=1860", encoding)
        assert response.status_code == 415
        # Werkzeug's default body: no text of the app's own.
        default = werkzeug.exceptions.UnsupportedMediaType().get_response()
        assert response.get_data() == default.get_data()
        assert seen == []

    def test_without_the_refusal_dash_routes_it_with_the_querys_value(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The control: the bypass is real on this Dash. The hook cannot read the
        # compressed body, so the query's year reaches the layout.
        monkeypatch.setattr(appmod, "refuse_encoded_dispatch", lambda: None)
        seen = echo_year_page(register)
        response = encoded_route("/fake-election/1824", "?year=1860")
        assert response.status_code == 200
        assert seen == ["1860"]

    @pytest.mark.parametrize("encoding", ["", "identity", " Identity "])
    def test_an_identity_body_is_routed_and_stripped(
        self, register: Callable[..., dict[str, Any]], encoding: str
    ) -> None:
        seen = echo_year_page(register)
        payload = json.dumps(conflicting_route("/fake-election/1824", "?year=1860"))
        response = encoded_route(
            "/fake-election/1824", "?year=1860", encoding, payload.encode()
        )
        assert response.status_code == 200
        assert seen == ["1824"]

    def test_only_the_dispatch_endpoint_is_refused(self) -> None:
        # An encoded POST to any other endpoint gets what it would get anyway (the
        # index takes no POST: 405), so a refusal that dropped its endpoint check, and
        # refused every encoded POST, would answer 415 here.
        client = appmod.server.test_client()
        response = client.post(
            "/",
            data=gzip.compress(b"{}"),
            headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
        )
        assert response.status_code == 405


class TestPathVariableWins:
    def test_every_registered_templated_page_renders_the_paths_value(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        register(**YEAR_PAGE)
        pages = templated_pages()
        assert {p["path_template"] for p in pages} >= {
            "/election/<year>",
            "/state/<usps>",
            "/candidate/<slug>",
            "/fake-election/<year>",
        }
        for page in pages:
            assert conflict_problems(page, monkeypatch) == [], page["module"]

    def test_the_check_fails_every_page_without_the_hook(
        self, register: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        without_the_hook(monkeypatch)
        register(**YEAR_PAGE)
        for page in templated_pages():
            names = re.findall(r"<(.*?)>", page["path_template"])
            problems = conflict_problems(page, monkeypatch)
            flagged = [p for p in problems if "did not render" not in p]
            assert len(flagged) == sum(len(conflicts(n)) for n in names), (
                page["module"],
                problems,
            )

    @pytest.mark.parametrize(
        ("pathname", "search", "expected"),
        [
            ("/election/1824", "", ""),
            ("/election/1824", "year=1860", "year=1860"),  # no "?": not a query
            ("/election/1824", "?year=1860", "?"),
            ("/election/1824/", "?year=1860", "?"),  # stripped as the router strips
            (
                "/election/1824",
                "?state=OH&year=1860&candidate=a%20b+c",
                "?state=OH&candidate=a%20b+c",
            ),
            ("/election/1824", "?a=1&&year=2&;b=3&", "?a=1&&;b=3&"),
            ("/election/1824", "?year;x=1", "?year;x=1"),  # ";" is no separator
            ("/election/1824", "?year%3Dx=1", "?year%3Dx=1"),  # the key is "year=x"
            ("/election/1824", "?ye%61r=1&year&yea%72=3&year+=2", "?year+=2"),
            ("/election/1824", "?Year=1860", "?Year=1860"),  # keys are case-sensitive
            ("/elections", "?year=1860", "?year=1860"),  # no path variables
            ("/no-such-view", "?year=1860", "?year=1860"),
            ("/state/GA", "?usps=TX&year=1860", "?year=1860"),
            ("/candidate/andrew-jackson", "?slug=x&state=GA", "?state=GA"),
            # Matched decoded, as the router matches (D089).
            ("/election%2F1824", "?year=1860", "?"),
            ("/%65lection/1824", "?year=1860&state=OH", "?state=OH"),
        ],
    )
    def test_the_strip_reads_keys_as_the_router_does(
        self,
        monkeypatch: pytest.MonkeyPatch,
        pathname: str,
        search: str,
        expected: str,
    ) -> None:
        stripped = appmod.strip_path_variables(pathname, search)
        assert stripped == expected
        # Whatever the router would have read, minus the path variables, and no more:
        # the router's own match, observed in a real routing request with no query,
        # never re-implemented here (#456).
        calls = path_to_page_calls(monkeypatch, dash.dash)
        route(pathname)
        assert len(calls) == 1
        names = set(calls[0][1] or ())
        before = _parse_query_string(search)
        assert _parse_query_string(stripped) == {
            k: v for k, v in before.items() if k not in names
        }

    @pytest.mark.parametrize(
        ("pathname", "year"),
        [
            ("/fake-election%2F1824", "1824"),
            ("/%2Ffake-election/1824", "1824"),
            ("/%66ake-election/1824", "1824"),
            ("/fake-election/182%34", "1824"),
            ("/fake-election/182%2534", "182%34"),
        ],
    )
    @pytest.mark.parametrize("hook", [True, False])
    def test_an_encoded_pathname_still_hands_the_layout_the_paths_value(
        self,
        register: Callable[..., dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        pathname: str,
        year: str,
        hook: bool,
    ) -> None:
        # The hook matches the pathname as the router does, decoded once (D089); with
        # the hook off, each case hands the layout the query's value, so each one
        # exercises the hook.
        if not hook:
            without_the_hook(monkeypatch)
        seen = echo_year_page(register)
        route(pathname, "?year=1860")
        assert seen == [year if hook else "1860"]

    def test_a_pathname_the_routers_strip_refuses_is_left_for_dash(self) -> None:
        # Decoded, it does not start with "/": the router's strip raises, and the hook
        # leaves the request alone rather than raising first.
        with pytest.raises(dash.exceptions.UnsupportedRelativePath):
            appmod.router_key("election/1824")
        assert appmod.strip_path_variables("election/1824", "?year=1") == "?year=1"

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            # Each case is one the hook must leave alone, and each would raise or
            # rewrite the body if the guard named beside it were deleted.
            ("POST", "/", conflicting_route()),  # the endpoint
            # Flask answers OPTIONS itself, but it is routed to the dispatch endpoint.
            ("OPTIONS", "/_dash-update-component", conflicting_route()),  # the method
            (  # the router's output
                "POST",
                "/_dash-update-component",
                {**conflicting_route(), "output": "x.y"},
            ),
            ("POST", "/_dash-update-component", [conflicting_route()]),  # a dict body
            (  # a list of inputs
                "POST",
                "/_dash-update-component",
                {**conflicting_route(), "inputs": {"a": 1, "b": 2}},
            ),
            (  # two inputs
                "POST",
                "/_dash-update-component",
                {**conflicting_route(), "inputs": conflicting_route()["inputs"][:1]},
            ),
            (  # a dict location
                "POST",
                "/_dash-update-component",
                {**conflicting_route(), "inputs": ["/election/1824", {"value": "?"}]},
            ),
            (  # a dict query
                "POST",
                "/_dash-update-component",
                {**conflicting_route(), "inputs": [{"value": "/"}, "?year=1860"]},
            ),
            (  # a str pathname
                "POST",
                "/_dash-update-component",
                conflicting_route(pathname=None),
            ),
            (  # a str search
                "POST",
                "/_dash-update-component",
                conflicting_route(search=7),
            ),
        ],
    )
    def test_the_hook_leaves_anything_but_a_routing_request_alone(
        self, method: str, path: str, body: Any
    ) -> None:
        sent = copy.deepcopy(body)
        with appmod.server.test_request_context(path, method=method, json=body):
            appmod._strip_routing_request()
            assert flask.request.get_json(silent=True) == sent

    @pytest.mark.parametrize(
        ("data", "content_type"),
        [
            ("not json", "application/json"),
            (json.dumps(ROUTING_POST), "text/plain"),
        ],
    )
    def test_a_body_dash_refuses_stays_refused(
        self, data: str, content_type: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The hook parses silently and never with force=True, so Dash's own
        # get_json() still raises on a body it would refuse without the hook.
        with appmod.server.test_request_context(
            "/_dash-update-component",
            method="POST",
            data=data,
            content_type=content_type,
        ):
            appmod._strip_routing_request()
            with pytest.raises(werkzeug.exceptions.HTTPException):
                flask.request.get_json()

        def outcome() -> tuple[int, bytes]:
            response = appmod.server.test_client().post(
                "/_dash-update-component", data=data, content_type=content_type
            )
            return response.status_code, response.get_data()

        hooked = outcome()
        monkeypatch.setattr(appmod, "_strip_routing_request", lambda: None)
        assert hooked == outcome()


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
    def test_no_page_names_the_keep_warm_path(self) -> None:
        """Only the refresher's ping reads ``/health`` (D076); no page declares it."""
        assert dash.page_registry  # the real pages, so this checks something
        for page in dash.page_registry.values():
            named = [*page.get("prefetch", ()), *page.get("on_miss", ())]
            if page.get("validate"):
                named.append(page["validate"][0])
            assert "/health" not in named, page["module"]

    def test_every_validating_page_declares_its_source(
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
            # An unknown name in the validate source alone, which on_miss does not list.
            (
                {
                    "prefetch": (api.ELECTIONS_PATH, "/v1/elections/{year_min}"),
                    "validate": ("/v1/elections/{year_min}", known_year),
                },
                "/v1/elections/{year_min} names year_min, neither a path nor a "
                "coverage variable",
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

    def test_accepts_the_keep_warm_path_on_the_public_host(self) -> None:
        """``/health`` is the one non-``/v1/`` path (D076), on the same public host."""
        assert api.build_url("/health") == PUBLIC_API_BASE + "/health"

    def test_the_health_constant_is_the_literal(self) -> None:
        assert api.HEALTH_PATH == "/health"

    @pytest.mark.parametrize("path", ["/v1/meta", "/health"])
    def test_the_host_check_refuses_a_base_that_moved(
        self, path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scheme/host check, not only the path pattern, keeps requests on the host,
        for the keep-warm literal as for a ``/v1/`` path."""
        monkeypatch.setattr(api, "API_BASE", "https://usvote-api-x.a.run.app")
        with pytest.raises(ValueError):
            api.build_url(path)
        monkeypatch.setattr(api, "API_BASE", "http://api.us-presidential-election-center.org")
        with pytest.raises(ValueError):
            api.build_url(path)

    @pytest.mark.parametrize(
        "path",
        [
            "//evil.example/v1/meta",
            "https://usvote-api-abc.a.run.app/v1/meta",
            "v1/meta",
            "/v2/meta",
            "/v1//meta",
            "/v1/../health",
            "/health?x=1",
            "/health/",
            "/HEALTH",
            "/healthz",
            "/health#x",
            "/health%2F",
            " /health",
            "/health ",
            "//health",
            "health",
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
        calls: list[tuple[str, str]] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls.append((threading.current_thread().name, path))
            return api.Response(body=META, version=VERSION)

        client = offline_client(fetch, ttl=3600)
        assert client.get(api.META_PATH) == META
        assert client.get(api.META_PATH) == META
        # Every fetch, the keep-warm ping's included, never on the visitor's thread.
        # The ping races the reads, so /v1/meta is counted by path.
        assert {thread for thread, _ in calls} == {"explore-refresher"}
        assert [path for _, path in calls].count(api.META_PATH) == 1

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
    if appmod.is_not_found_page(page):
        pass  # reads no data, so it has no success to mark (#325)
    elif not marker:
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
    variable is: only the latest year the index itself serves, never a value from a
    request."""

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
            # Served, but not the latest: the roster would not be every state.
            index_with(year_max=1824),
            index_with(year_max=2020),
        ],
        ids=repr,
    )
    def test_anything_but_the_latest_served_year_is_a_type_error(self, index: Any) -> None:
        with pytest.raises(TypeError):
            api.coverage_vars(index)

    def test_the_latest_year_is_taken_from_checked_row_years_only(self) -> None:
        # A float row year is not a served year, so the latest checked one is 2020
        # and coverage's 2024 is refused, though 2024.0 == 2024.
        index = copy.deepcopy(RECORDED[api.ELECTIONS_PATH])
        for row in index["data"]:
            if row["year"] == 2024:
                row["year"] = 2024.0
        with pytest.raises(TypeError):
            api.coverage_vars(index)

    @pytest.mark.parametrize(
        "junk", [{"year": "2030"}, {"year": 99999}, {"year": True}, 7, "row", None]
    )
    def test_a_malformed_index_row_is_skipped_not_fatal(self, junk: Any) -> None:
        # A row that is not an object, or names no checked year, serves nothing:
        # it neither becomes the latest year nor raises past the page's except.
        index = copy.deepcopy(RECORDED[api.ELECTIONS_PATH])
        index["data"].append(junk)
        assert api.coverage_vars(index) == {"year_max": "2024"}
        both = {api.ELECTIONS_PATH: index, "/v1/elections/2024": {"data": []}}
        assert api.cached_source(api.ROSTER_PATH, both) == {"data": []}

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
    "CANDIDATES_PATH",
    # N1, chart C2's source on the elections index (#434).
    "SUMMARY_PATH",
    # N2, charts C4 and C5's one-state source on the elections index (#436).
    "ELECTION_STATES_PATH",
    "Validate",
    "accepted",
    # A constant pair a page registers as ``not_found=`` (#325); reads nothing.
    "NotFound",
    # Pure functions of a body the page already read through its view.
    "coverage_vars",
    "roster",
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
            if path == api.META_PATH:  # not the keep-warm ping
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
            if path != api.META_PATH:  # the keep-warm ping is not a cycle
                return api.Response(body=HEALTH, version=None)
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
            if path == api.META_PATH:  # not the keep-warm ping
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


# --- the keep-warm ping (D076) ---------------------------------------------------------


class _StopRefresher(BaseException):
    """Ends a synchronously driven ``Client._run``. A ``BaseException``, so the
    refresher's own ``except Exception`` handlers let it through."""


class FakeWake:
    """The refresher's wake-up event on a :class:`FakeClock`, so ``_run`` runs inline.

    ``wakes`` are the times visitors set it. Like a real event it stays set until
    cleared: ``wait`` returns at once if it is set or a wake-up has already arrived,
    otherwise it advances the clock to the next wake-up within ``timeout`` (and
    returns ``True``) or to the timeout (``False``). ``clear`` drops every wake-up at
    or before now. A runaway loop is stopped after ``max_waits`` waits.
    """

    def __init__(
        self, clock: FakeClock, wakes: Iterable[float] = (), max_waits: int = 10_000
    ) -> None:
        self._clock = clock
        self._wakes = sorted(wakes)
        self._set = False
        self._max_waits = max_waits
        self.waits = 0

    def set(self) -> None:
        self._set = True

    def is_set(self) -> bool:
        return self._set or any(t <= self._clock.now for t in self._wakes)

    def clear(self) -> None:
        self._set = False
        self._wakes = [t for t in self._wakes if t > self._clock.now]

    def wait(self, timeout: float | None = None) -> bool:
        self.waits += 1
        if self.waits >= self._max_waits:
            raise _StopRefresher
        assert timeout is not None and timeout >= 0, timeout
        if self.is_set():
            return True
        end = self._clock.now + timeout
        arriving = [t for t in self._wakes if t <= end]
        if arriving:
            self._clock.now = arriving[0]
            return True
        self._clock.now = end
        return False


class TestKeepWarm:
    """The refresher's ``/health`` ping, driven through the real ``_run`` on a fake
    clock: every sleep, wait and fetch advances it, so ping times are exact."""

    TTL = 300.0
    BACKOFF = 30.0
    RECHECK = 30.0
    R = 2.0  # what a /v1/meta check takes
    P = 10.0  # what a ping takes

    def run(
        self,
        wakes: Iterable[float] = (),
        meta_error: BaseException | None = None,
        ping_error: BaseException | None = None,
        warm: bool = False,
        cycles: int = 3,
    ) -> tuple[api.Client, list[tuple[str, float, float]], list[float]]:
        """Run the refresher for ``cycles`` ``/v1/meta`` checks, stopping as the next
        one starts; return the client, every fetch as ``(path, start, timeout)``, and
        every sleep."""
        clock = FakeClock()
        calls: list[tuple[str, float, float]] = []
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock.now += seconds

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == api.META_PATH and len(self.metas(calls)) == cycles:
                raise _StopRefresher
            calls.append((path, clock.now, timeout))
            if path == api.HEALTH_PATH:
                clock.now += self.P
                if ping_error is not None:
                    raise ping_error
                # Names another snapshot, which must never reach the cache.
                return api.Response(body=OTHER_HEALTH, version="other")
            clock.now += self.R
            if meta_error is not None:
                raise meta_error
            return api.Response(body=META, version=VERSION)

        client = offline_client(
            fetch,
            clock=clock,
            sleep=sleep,
            ttl=self.TTL,
            retry_backoff=self.BACKOFF,
            min_recheck=self.RECHECK,
        )
        if warm:
            client.refresh()  # what /_ah/warmup does, before the refresher starts
            calls.clear()
            sleeps.clear()
        client._wake = FakeWake(clock, wakes)  # type: ignore[assignment]
        with pytest.raises(_StopRefresher):
            client._run()
        return client, calls, sleeps

    @staticmethod
    def pings(calls: list[tuple[str, float, float]]) -> list[float]:
        return [start for path, start, _ in calls if path == api.HEALTH_PATH]

    @staticmethod
    def metas(calls: list[tuple[str, float, float]]) -> list[float]:
        return [start for path, start, _ in calls if path == api.META_PATH]

    @property
    def bound(self) -> float:
        """The worst gap between ping starts: a TTL, one unwakeable wait, one refresh."""
        return self.TTL + max(self.BACKOFF, self.RECHECK) + self.R

    def gaps(self, pings: list[float]) -> list[float]:
        return [b - a for a, b in zip(pings, pings[1:], strict=False)]

    def test_the_ping_body_never_reaches_the_cache(self) -> None:
        client, calls, _ = self.run(cycles=3)
        assert len(self.pings(calls)) == 3
        assert client.snapshot is not None
        assert client.snapshot.version == VERSION
        assert client.snapshot.responses == {api.META_PATH: META}

    def test_a_ping_due_cycle_is_not_held_to_the_recheck_interval(self) -> None:
        """Documented, not a defect (D076): the cycle the ping-due wait ends refreshes
        too, so once per TTL a /v1/meta check can follow a woken one sooner than
        ``min_recheck``. The ping-due cycle at 302 comes 5 s after the woken one."""
        _, calls, _ = self.run(wakes=[297.0], cycles=4)
        assert self.metas(calls) == [0.0, 297.0, 302.0, 604.0]
        assert self.pings(calls) == [2.0, 304.0, 606.0]

    def test_a_lazy_start_pings_after_its_first_refresh_then_once_per_cycle(
        self,
    ) -> None:
        _, calls, _ = self.run(cycles=3)
        # Stamped at the start of each ping: a stamp taken at its end would put the
        # next ping P later, at 314.
        assert self.pings(calls) == [2.0, 304.0, 606.0]
        assert self.metas(calls) == [0.0, 302.0, 604.0]

    def test_a_warmup_filled_start_waits_one_ttl_before_its_first_ping(self) -> None:
        _, calls, _ = self.run(warm=True, cycles=2)
        # Warmup's refresh took 0..2; the refresher then waits a whole TTL.
        assert self.pings(calls) == [304.0, 606.0]

    def test_refresh_itself_never_pings(self) -> None:
        state = {"version": VERSION}
        seen: list[tuple[str, float]] = []
        client = offline_client(
            versioned_fetch(state, seen), prefetch_paths=lambda: [api.ELECTIONS_PATH]
        )
        client.refresh()
        state["version"] = "next"
        client.refresh()
        assert api.HEALTH_PATH not in [path for path, _ in seen]

    def test_the_ping_times_out_at_the_refresher_timeout(self) -> None:
        _, calls, _ = self.run(cycles=2)
        timeouts = {t for path, _, t in calls if path == api.HEALTH_PATH}
        assert timeouts == {api.FETCH_TIMEOUT_S}

    def test_a_wake_storm_still_pings_once_per_ttl(self) -> None:
        wakes = [float(t) for t in range(1, 2000)]  # a visitor every second
        _, calls, _ = self.run(wakes=wakes, cycles=31)  # checks at 0, 30, ..., 900
        metas = self.metas(calls)
        assert self.gaps(metas) and all(g == self.RECHECK for g in self.gaps(metas))
        assert self.pings(calls) == [2.0, 302.0, 602.0, 902.0]

    def test_a_wake_just_before_the_ping_is_due_does_not_defer_it_a_ttl(self) -> None:
        """The case a plain debounce fails: the woken cycle skips the ping, and the
        next cycle would come a whole TTL later, nearly 2 x TTL after the last ping."""
        eps = 5.0
        assert eps > self.R  # the woken cycle finishes before the ping is due
        due = 2.0 + self.TTL
        _, calls, _ = self.run(wakes=[due - eps], cycles=4)
        metas, pings = self.metas(calls), self.pings(calls)
        assert due - eps in metas  # the visitor's wake-up ran a cycle...
        assert due - eps not in pings and due - eps + self.R not in pings  # ...no ping
        assert pings[:2] == [2.0, due + self.R]
        assert all(g <= self.bound for g in self.gaps(pings)), self.gaps(pings)

    def test_failure_backoff_keeps_the_gap_under_the_bound(self) -> None:
        _, calls, sleeps = self.run(meta_error=api.ApiUnavailable("down"), cycles=25)
        pings = self.pings(calls)
        assert pings[0] == 2.0  # a refresh that raises still pings
        assert len(pings) >= 2
        assert all(self.TTL <= g <= self.bound for g in self.gaps(pings)), pings
        assert set(sleeps) == {self.BACKOFF}

    def test_a_refresh_that_raises_still_pings(self) -> None:
        client, calls, _ = self.run(meta_error=RuntimeError("bad body"), cycles=1)
        assert [path for path, _, _ in calls] == [api.META_PATH, api.HEALTH_PATH]
        assert client.snapshot is None

    @pytest.mark.parametrize(
        "error", [api.ApiUnavailable("GET /health: HTTP 503"), RuntimeError("boom")]
    )
    def test_a_failed_ping_is_not_a_failed_cycle(self, error: Exception) -> None:
        client, calls, sleeps = self.run(ping_error=error, cycles=3)
        assert sleeps == []  # never the retry backoff: the cycles succeeded
        assert self.metas(calls) == [0.0, 302.0, 604.0]  # the loop went on
        assert client._last_check == 604.0  # the last refresh's start, nothing else

    def test_a_failing_ping_is_debounced_like_a_working_one(self) -> None:
        wakes = [float(t) for t in range(1, 2000)]
        _, calls, _ = self.run(
            wakes=wakes, ping_error=api.ApiUnavailable("down"), cycles=31
        )
        # Stamped when the attempt starts, success or not: one per TTL, not per cycle.
        assert self.pings(calls) == [2.0, 302.0, 602.0, 902.0]

    def test_a_failing_ping_under_failure_backoff_is_debounced(self) -> None:
        _, calls, _ = self.run(
            meta_error=api.ApiUnavailable("down"),
            ping_error=api.ApiUnavailable("down"),
            cycles=25,
        )
        pings = self.pings(calls)
        assert len(pings) >= 2
        assert all(self.TTL <= g <= self.bound for g in self.gaps(pings)), pings

    def test_the_ping_takes_no_token_and_logs_its_own_line(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bucket = RecordingBucket()
        clock = FakeClock()
        calls: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls.append(path)
            return api.Response(body=HEALTH, version=None)

        client = offline_client(fetch, bucket=bucket, clock=clock)
        with caplog.at_level(logging.INFO, logger=api.log.name):
            client._ping()
        assert calls == [api.HEALTH_PATH]
        assert bucket.waits == []
        [record] = [r for r in caplog.records if "api ping" in r.getMessage()]
        assert record.levelno == logging.INFO
        assert record.getMessage().startswith("api ping /health ")
        assert "failed" not in record.getMessage()
        messages = [r.getMessage() for r in caplog.records]
        assert not any(m.startswith("api fetch") for m in messages), messages

    def test_an_unavailable_api_logs_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = offline_client(failing_fetch, clock=FakeClock())
        with caplog.at_level(logging.INFO, logger=api.log.name):
            client._ping()
        [record] = [r for r in caplog.records if "api ping" in r.getMessage()]
        assert record.levelno == logging.WARNING
        assert record.getMessage().startswith("api ping /health failed after ")
        assert record.exc_info is None

    @pytest.mark.parametrize("error", [ValueError("refused"), RuntimeError("boom")])
    def test_any_other_ping_error_is_a_bug_logged_with_its_traceback(
        self, error: Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            raise error

        client = offline_client(fetch, clock=FakeClock())
        with caplog.at_level(logging.INFO, logger=api.log.name):
            client._ping()  # logs, never raises
        [record] = [r for r in caplog.records if "api ping" in r.getMessage()]
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None and record.exc_info[1] is error

    def test_a_ping_goes_through_the_real_fetch(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The other ping tests inject a fetch; this one drives :func:`api.fetch`, so
        a chokepoint that stopped accepting the path would fail here, not just log."""
        opener = _FakeOpener(_FakeRaw(200, json.dumps(OTHER_HEALTH).encode(), None))
        monkeypatch.setattr(api, "_OPENER", opener)
        client = api.Client(clock=FakeClock())
        with caplog.at_level(logging.INFO, logger=api.log.name):
            client._ping()
        assert [r.full_url for r in opener.requests] == [PUBLIC_API_BASE + "/health"]
        assert opener.timeouts == [api.FETCH_TIMEOUT_S]
        [record] = [r for r in caplog.records if "api ping" in r.getMessage()]
        assert record.levelno == logging.INFO

    def test_warmup_never_pings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paths: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            paths.append(path)
            return api.Response(body=META, version=VERSION)

        client = offline_client(fetch, ttl=3600)
        monkeypatch.setattr(api, "CLIENT", client)
        assert appmod.server.test_client().get("/_ah/warmup").status_code == 200
        time.sleep(0.2)  # give a wrongly eager refresher time to ping
        assert paths == [api.META_PATH]

    def test_a_visitors_miss_never_pings(self) -> None:
        state = {"version": VERSION}
        seen: list[tuple[str, float]] = []
        client = offline_client(versioned_fetch(state, seen))
        client.refresh()
        assert client.get("/v1/elections/2000") == {
            "path": "/v1/elections/2000",
            "version": VERSION,
        }
        assert [path for path, _ in seen] == [api.META_PATH, "/v1/elections/2000"]


class TestNoPageReadsHealth:
    """Both fill paths refuse the ping's path before taking a token or fetching."""

    def make(self) -> tuple[api.Client, RecordingBucket, list[str]]:
        bucket = RecordingBucket()
        calls: list[str] = []

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            calls.append(path)
            return api.Response(body=HEALTH, version=VERSION)

        return offline_client(fetch, bucket=bucket), bucket, calls

    def test_the_refresher_fill_refuses_it(self) -> None:
        client, bucket, calls = self.make()
        with pytest.raises(ValueError):
            client._fill("/health", None, api.FETCH_TIMEOUT_S)
        assert bucket.waits == [] and calls == []

    def test_the_visitor_fill_refuses_it(self) -> None:
        client, bucket, calls = self.make()
        with pytest.raises(ValueError):
            client._visitor_fill("/health", time.monotonic() + 2.0)
        assert bucket.waits == [] and calls == []

    def test_a_page_read_refuses_it(self) -> None:
        client, bucket, calls = self.make()
        client._snapshot = api.Snapshot(version=VERSION, responses={})
        with pytest.raises(ValueError):
            client.get("/health")
        assert bucket.waits == [] and calls == []

    def test_a_prefetch_naming_it_fails_the_refresh(self) -> None:
        client, bucket, calls = self.make()
        client._prefetch_paths = lambda: ["/health"]
        client._fetch = versioned_fetch({"version": VERSION})
        with pytest.raises(ValueError):
            client.refresh()
        assert client.snapshot is None


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


# --- the election pages: routing and the moved filters (#465) -------------------------


def _module(path: str) -> tuple[str | None, dict[str, str] | None]:
    page, path_vars = _path_to_page(path)
    return page.get("module"), path_vars


class TestElectionPages:
    """The overview's greedy ``<year>`` would capture a subpage path; the subpages'
    ``order=`` puts them first in the registry Dash's router walks, whatever their
    module names, and ``test_every_page_s_path_routes_to_that_page`` fails any
    shadowing a later page brings."""

    @pytest.mark.parametrize(
        ("path", "module", "year"),
        [
            ("election/1824/states", "pages.election_states", "1824"),
            ("election/1824/per-capita", "pages.election_per_capita", "1824"),
            ("election/1824", "pages.election", "1824"),
            # An unknown section reaches the overview, whose validate refuses it.
            ("election/1824/x", "pages.election", "1824/x"),
        ],
    )
    def test_each_path_reaches_its_page(
        self, path: str, module: str, year: str
    ) -> None:
        assert _module(path) == (module, {"year": year})

    def test_the_precedence_comes_from_order_not_module_names(self) -> None:
        order = {
            module: dash.page_registry[module]["supplied_order"]
            for module in (
                "pages.election",
                "pages.election_states",
                "pages.election_per_capita",
            )
        }
        assert order["pages.election"] is None
        assert isinstance(order["pages.election_states"], int)
        assert isinstance(order["pages.election_per_capita"], int)
        modules = list(dash.page_registry)
        overview = modules.index("pages.election")
        assert modules.index("pages.election_states") < overview
        assert modules.index("pages.election_per_capita") < overview

    def test_an_unknown_section_is_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        status, head, _ = get("/election/1824/x")
        assert (status, head.canonical) == (404, None)
        assert "election-not-found" in routed_ids(route("/election/1824/x"))
        assert calls == []

    @pytest.mark.parametrize("section", ["states", "per-capita"])
    def test_an_unserved_year_is_not_found_on_each_subpage(
        self, monkeypatch: pytest.MonkeyPatch, section: str
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        status, head, body = get(f"/election/1825/{section}")
        assert (status, head.canonical, head.noindex) == (404, None, True)
        assert f"<title>{labels.ELECTION_NOT_FOUND_HEADING} — " in body
        assert f"election-{section}-not-found" in routed_ids(
            route(f"/election/1825/{section}")
        )
        assert calls == []

    def test_an_encoded_subpage_path_is_that_subpage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        response = appmod.server.test_client().get("/election/2016%2Fstates?state=GA")
        assert response.status_code == 200  # the states page: never redirected
        head = Head(response.get_data(as_text=True))
        assert head.canonical == url("/election/2016/states")
        assert head.og_url == url("/election/2016/states?state=GA")

    def test_no_two_callbacks_write_one_output(self) -> None:
        # The per-capita page's control and Location have ids of their own, since
        # Dash keys callbacks by output app-wide (#465).
        graph = appmod.server.test_client().get("/_dash-dependencies").get_json()
        outputs = [c["output"] for c in graph]
        assert len(outputs) == len(set(outputs))
        assert "election-per-capita-url.search" in outputs
        assert "election-url.search" in outputs


def _location(path: str) -> tuple[int, str | None]:
    response = appmod.server.test_client().get(path)
    return response.status_code, response.headers.get("Location")


class TestMovedFilters:
    """A link to the overview carrying one of T2's keys, shared before #465, is
    redirected (302) to the states page with them, normalized by its parser."""

    @pytest.mark.parametrize(
        ("query", "location"),
        [
            ("state=GA", "/election/2016/states?state=GA"),
            (
                "candidate=donald-j-trump",
                "/election/2016/states?candidate=donald-j-trump",
            ),
            ("pv_status=popular_vote", "/election/2016/states?pv_status=popular_vote"),
            (
                "electoral_count_status=counted",
                "/election/2016/states?electoral_count_status=counted",
            ),
            (
                "state=GA&candidate=donald-j-trump&pv_status=popular_vote"
                "&electoral_count_status=counted",
                "/election/2016/states?candidate=donald-j-trump"
                "&electoral_count_status=counted&pv_status=popular_vote&state=GA",
            ),
            # A repeated key: kept when it agrees, dropped when it does not.
            ("state=GA&state=GA", "/election/2016/states?state=GA"),
            ("state=GA&state=OH", "/election/2016/states"),
            # The path's year wins (D081); unknown keys are dropped.
            ("year=1900&state=GA&junk=1", "/election/2016/states?state=GA"),
            # Read as the router reads the query: an escaped key, a blank value.
            ("st%61te=GA", "/election/2016/states?state=GA"),
            ("state=", "/election/2016/states"),
            ("state=ga", "/election/2016/states"),  # not a USPS code: dropped
        ],
    )
    def test_a_moved_key_redirects_to_the_states_page(
        self, monkeypatch: pytest.MonkeyPatch, query: str, location: str
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        # The raw header: relative, never naming a host (D090).
        assert _location(f"/election/2016?{query}") == (302, location)
        # Judged from the snapshot in memory: the redirect reads and fills nothing.
        assert (calls, bucket.waits) == ([], [])

    def test_a_percent_encoded_year_redirects_by_the_year_it_spells(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, bucket = cached_client(monkeypatch)
        assert _location("/election/20%31%36?state=GA") == (
            302,
            "/election/2016/states?state=GA",
        )
        assert (calls, bucket.waits) == ([], [])

    def test_the_location_is_built_from_the_accepted_year_not_the_request_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A trailing slash reaches the overview (D089), but the request path is not
        the year: a Location built from it would read ``/election/2016//states``."""
        _, calls, _ = cached_client(monkeypatch)
        assert _location("/election/2016/?state=GA") == (
            302,
            "/election/2016/states?state=GA",
        )
        assert calls == []

    @pytest.mark.parametrize("query", ["", "junk=1", "year=1900", "statex=GA"])
    def test_no_moved_key_serves_the_overview(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        cached_client(monkeypatch)
        assert _location(f"/election/2016?{query}") == (200, None)

    @pytest.mark.parametrize(
        "path",
        ["/election/1825", "/election/..", "/election/%3Cb%3E", "/election/1824/x"],
    )
    def test_a_refused_year_answers_the_overview_s_404(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        cached_client(monkeypatch)
        assert _location(f"{path}?state=GA") == (404, None)

    def test_before_the_first_snapshot_the_overview_is_served_unfiltered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only a year the snapshot in memory accepted builds a Location; an unchecked
        one is served as the overview, which reads no filter."""

        def no_fetch(path: str, timeout: float = 0) -> api.Response:
            raise AssertionError(f"the index fetched {path}")

        client = offline_client(no_fetch)
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(api, "CLIENT", client)
        assert _location("/election/2016?state=GA") == (200, None)
        assert _location("/election/abc?state=GA") == (200, None)

    def test_a_client_side_route_renders_the_overview_unfiltered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        ids = routed_ids(route("/election/2016", "?state=GA"))
        assert "election" in ids
        assert "election-states" not in ids


class TestMoveContract:
    """``moved=`` is checked as the registry is read (:func:`explore.app.page_move`), so
    a redirect never leads to a page that would refuse the value just accepted."""

    VALIDATE = ("/v1/elections", lambda path_vars, body: True)

    def registry(self, **target: Any) -> dict[str, Any]:
        return {
            "t": {
                "module": "t",
                "path_template": "/x/<year>/y",
                "query": lambda params: [],
                "validate": self.VALIDATE,
                **target,
            }
        }

    def page(self, **page: Any) -> dict[str, Any]:
        return {
            "module": "p",
            "path_template": "/x/<year>",
            "validate": self.VALIDATE,
            "moved": (("a",), "/x/<year>/y"),
            **page,
        }

    def test_a_page_without_moved_has_none(self) -> None:
        assert appmod.page_move({"module": "p"}, {}) is None

    def test_a_valid_move_takes_the_target_s_parser(self) -> None:
        registry = self.registry()
        move = appmod.page_move(self.page(), registry)
        assert move == appmod.Move(("a",), "/x/<year>/y", registry["t"]["query"])

    @pytest.mark.parametrize(
        ("page", "target", "message"),
        [
            ({"moved": (("a",), "/nowhere/<year>")}, {}, "unregistered"),
            ({"path_template": "/x/<yr>"}, {}, "path variables"),
            ({}, {"query": None}, "no query="),
            ({}, {"validate": ("/v1/other", lambda v, b: True)}, "validates"),
            ({"moved": ((), "/x/<year>/y")}, {}, "no keys"),
            # A bare string would read as its letters, never as one key.
            ({"moved": ("a", "/x/<year>/y")}, {}, "not a tuple of names"),
            ({"moved": (("a",), "/x/<year>/y", "extra")}, {}, "is not"),
            ({"moved": [("a",), "/x/<year>/y"]}, {}, "is not"),
            ({"moved": (("",), "/x/<year>/y")}, {}, "no keys"),
            # A key that is not a name, however truthy, is no query key.
            ({"moved": ((1,), "/x/<year>/y")}, {}, "no keys"),
            ({"moved": ((b"state",), "/x/<year>/y")}, {}, "no keys"),
        ],
    )
    def test_a_bad_move_fails_the_import(
        self, page: dict[str, Any], target: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(RuntimeError, match=message):
            appmod.page_move(self.page(**page), self.registry(**target))

    def test_each_path_variable_is_quoted_into_the_location(self) -> None:
        """Every redirect today carries a four-digit year, which quoting leaves alone,
        so the quoting is pinned directly: a value a looser ``validate`` let through
        could never add a path segment, a query or a fragment to the Location."""
        resolution = appmod.Resolution(
            canonical="https://x/",
            og_url="https://x/",
            title="t",
            description="d",
            page={},
            path_vars={"year": "a/b?c#d"},
        )
        move = appmod.Move(("k",), "/x/<year>/y", lambda params: [("k", "v")])
        assert appmod.moved_location(resolution, move, "k=1") == (
            "/x/a%2Fb%3Fc%23d/y?k=v"
        )

    def test_the_registry_s_moves_are_the_overview_s_alone(self) -> None:
        assert set(appmod.MOVES) == {"pages.election"}
        move = appmod.MOVES["pages.election"]
        assert move.keys == ("state", "candidate", "pv_status", "electoral_count_status")
        assert move.template == "/election/<year>/states"
        assert move.parser is dash.page_registry["pages.election_states"]["query"]
