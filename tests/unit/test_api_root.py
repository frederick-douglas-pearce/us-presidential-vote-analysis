"""The API root redirect and the relative-``Location`` rule (#461, D090).

The public hostname is a Cloudflare Worker that forwards to Cloud Run and rewrites the
``Host`` header to the raw ``run.app`` origin (D035). Anything the app builds from the
request's host therefore names that origin, so every ``Location`` the API emits must
be relative. Two consequences are pinned here:

* ``/`` answers ``307`` with ``Location: /docs`` (GET and HEAD), left out of the
  OpenAPI schema, so the bare address that published posts link lands on the docs.
* ``redirect_slashes`` is off. Starlette's trailing-slash redirect is the one place
  that builds an absolute ``Location`` from the host; with it on, ``/v1/meta/``
  through the public host was sent to ``http://<run.app host>/v1/meta``.

The foreign ``Host`` below is a valid hostname on purpose: Starlette's ``URL`` falls
back to the ``testserver`` address for a host it cannot parse, which would test the
fallback rather than the Worker's rewrite.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import usvote.api.app as app_module
from usvote.api import create_app
from usvote.api.config import ApiSettings

RUN_APP_HOST = "usvote-api-x-uw.a.run.app"


def _app_with_docs_url(
    monkeypatch: pytest.MonkeyPatch, settings: ApiSettings, docs_url: str | None
) -> FastAPI:
    """Build the real app with its docs served at ``docs_url`` instead of ``/docs``.

    ``create_app`` takes no docs setting, so the constructor it calls is swapped for
    one that overrides that one keyword and passes every other through unchanged.
    """

    class _DocsAt(FastAPI):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**{**kwargs, "docs_url": docs_url})

    monkeypatch.setattr(app_module, "FastAPI", _DocsAt)
    return create_app(settings)


def test_root_redirects_to_the_docs(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/docs"


def test_root_redirect_stays_relative_under_the_workers_host(client: TestClient) -> None:
    r = client.get("/", headers={"host": RUN_APP_HOST}, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/docs"


def test_root_follows_the_docs_url_rather_than_naming_it(
    monkeypatch: pytest.MonkeyPatch, settings: ApiSettings
) -> None:
    with TestClient(_app_with_docs_url(monkeypatch, settings, "/api-docs")) as c:
        r = c.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/api-docs"


def test_no_root_route_when_the_app_serves_no_docs(
    monkeypatch: pytest.MonkeyPatch, settings: ApiSettings
) -> None:
    app = _app_with_docs_url(monkeypatch, settings, None)
    assert "/" not in {getattr(route, "path", None) for route in app.routes}
    with TestClient(app) as c:
        assert c.get("/", follow_redirects=False).status_code == 404


def test_root_answers_head_with_the_same_redirect(client: TestClient) -> None:
    r = client.head("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/docs"


def test_root_is_not_in_the_openapi_schema(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/" not in paths
    assert "/health" in paths  # the schema is the served one, not an empty stub


def test_following_the_root_reaches_the_swagger_page(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.history and r.history[0].status_code == 307
    assert "swagger-ui" in r.text


def test_redirect_slashes_is_off(settings: ApiSettings) -> None:
    assert create_app(settings).router.redirect_slashes is False


def test_trailing_slash_paths_404_without_a_location(client: TestClient) -> None:
    for path in ("/v1/meta/", "/docs/", "/health/"):
        r = client.get(path, headers={"host": RUN_APP_HOST}, follow_redirects=False)
        assert r.status_code == 404, path
        assert "location" not in r.headers, path


def test_the_foreign_host_setup_reproduces_the_leak_it_guards() -> None:
    """Non-vacuity twin: with Starlette's default, the same request leaks the host.

    If this goes red, Starlette stopped building an absolute ``Location`` for slash
    redirects, and D090's reason for turning ``redirect_slashes`` off should be
    revisited.
    """
    app = FastAPI()

    @app.get("/x")
    def x() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as c:
        r = c.get("/x/", headers={"host": RUN_APP_HOST}, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == f"http://{RUN_APP_HOST}/x"
