"""The FastAPI application factory (E8-S2, #96) — skeleton, config, health, ``/v1``.

:func:`create_app` builds an app that loads the read-only SQLite snapshot at startup and
serves it with **no live DB** (D028). This story is the skeleton: centralized config,
the
:class:`~usvote.api.repository.SnapshotRepository` seam, a root ``/health`` probe, and a
minimal ``/v1/meta`` endpoint that exercises the ETag/``Cache-Control`` machinery. The
data endpoints (by year / state / candidate + national summary) are E8-S3.

Import boundary (D028, enforced by ``tests/unit/test_api_import_graph.py``): everything
under ``usvote/api/`` imports only the snapshot artifact + the thin repository +
stdlib-only contract modules — never :mod:`usvote.db`, psycopg2, :mod:`usvote.snapshot`,
or pandas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from usvote.api import provenance, routes
from usvote.api.cache import NotModified, cache_dependency, not_modified_handler
from usvote.api.config import ApiSettings
from usvote.api.models import (
    ErrorBody,
    ErrorDetail,
    Provenance,
    SnapshotMetaResponse,
)
from usvote.api.repository import SnapshotRepository
from usvote.api.routes import ResourceNotFound

#: ``Cache-Control`` for the liveness probe — never cached, unlike the ``/v1`` surface.
_HEALTH_CACHE_CONTROL = "no-store"

#: ``Cache-Control`` for a 404: a not-found body must never be cached as if it were the
#: resource (the #97 architect note — a 404 is not a representation of the URL).
_ERROR_CACHE_CONTROL = "no-store"

# --- OpenAPI metadata (E8-S4, #98) --------------------------------------------
# The "advertising surface" the epic (#94/D031) chose REST+OpenAPI for. Titles, a
# real description, grouped tags, and a first-class provenance/licensing statement,
# so the docs are hand-off-ready (e.g. to the MIT Election Lab).

#: The public data source + license, resolved once from the code→display mappings so
#: the names in this prose can't drift from what rides in every ``meta.provenance``.
_MIT = provenance.source_display("MIT")
_CC0 = provenance.license_display("CC0-1.0")

API_TITLE = "US Presidential Vote API"

API_VERSION = "0.2.0"

API_SUMMARY = (
    "Electoral College vs. popular vote for US presidential elections, over the "
    "redistributable modern era."
)

#: Replaced at ``/openapi.json`` build time with the loaded snapshot's real year
#: window (:func:`_install_live_openapi`), so the headline coverage line always
#: matches the data actually served rather than a hard-coded span that could go stale.
_COVERAGE_PLACEHOLDER = "{coverage_window}"

API_DESCRIPTION = f"""\
A read-only HTTP API over a joined **Electoral College + popular vote** dataset for US
presidential elections, at the `(year, state, candidate)` grain plus a per-year national
roll-up.

It exists to make one comparison easy to inspect: **who won the Electoral College
vs. who won the national popular vote** — including the elections where those diverge,
when a candidate loses the national popular vote yet still takes office. Each
candidate's national electoral-vote total, finishing rank, and whether they took
office sit alongside the popular-vote totals.

**Coverage:** {_COVERAGE_PLACEHOLDER} (US presidential elections).

**Data provenance & licensing.** {provenance.redistributable_note(_MIT, _CC0)} Every
response carries the exact source, license, coverage window, and snapshot version under
`meta.provenance`; the same block, with build details, is at `GET /v1/meta`.

**Getting started.** Browse the interactive docs at `/docs` (Swagger UI) or `/redoc`
(ReDoc). Every response is JSON in a `{{data, meta}}` envelope and carries an `ETag` and
`Cache-Control` for conditional requests.
"""

#: Tag groups, ordered as they should read in Swagger UI / ReDoc.
_OPENAPI_TAGS: list[dict[str, Any]] = [
    {
        "name": "Elections",
        "description": "Covered years, per-state rows, and national roll-ups.",
    },
    {
        "name": "States",
        "description": "One state's EC + PV rows across every covered year.",
    },
    {
        "name": "Candidates",
        "description": (
            "One candidate's EC + PV rows across every covered year, keyed by the "
            "durable public slug."
        ),
    },
    {
        "name": "Meta",
        "description": "Snapshot provenance: source, license, coverage, and version.",
    },
    {
        "name": "Ops",
        "description": (
            "Operational probes (liveness). Not part of the versioned `/v1` data API."
        ),
    },
]

API_CONTACT = {
    "name": "us_presidential_vote_analysis on GitHub",
    "url": "https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis",
}

#: The OpenAPI ``license`` block advertises the **data** license (CC0) — this API serves
#: public-domain data and carries no separate API terms.
API_LICENSE_INFO = {"name": _CC0.name, "url": _CC0.url}


def _install_live_openapi(app: FastAPI) -> None:
    """Override ``app.openapi()`` so the description's coverage window is read live.

    FastAPI builds the schema lazily on the first ``/openapi.json`` (or ``/docs`` /
    ``/redoc``) request — always **after** the lifespan opened the snapshot — so reading
    ``app.state.repository`` here is safe and never double-opens. The built schema is
    cached on ``app.openapi_schema`` as FastAPI's default does, so this runs once.
    """

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        meta = app.state.repository.meta()
        window = f"{meta.year_min}–{meta.year_max}"
        app.openapi_schema = get_openapi(
            title=API_TITLE,
            version=API_VERSION,
            summary=API_SUMMARY,
            description=API_DESCRIPTION.replace(_COVERAGE_PLACEHOLDER, window),
            routes=app.routes,
            tags=_OPENAPI_TAGS,
            contact=API_CONTACT,
            license_info=API_LICENSE_INFO,
        )
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def resource_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`~usvote.api.routes.ResourceNotFound` as a typed, uncached 404."""
    assert isinstance(exc, ResourceNotFound)
    body = ErrorBody(error=ErrorDetail(code=exc.code, message=exc.message))
    return JSONResponse(
        status_code=404,
        content=body.model_dump(),
        headers={"Cache-Control": _ERROR_CACHE_CONTROL},
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the snapshot repository at startup; expose it on ``app.state``.

    Opening validates the snapshot (meta row present, ``schema_version`` compatible) and
    caches the immutable provenance — so a bad snapshot fails **loud at boot**, not per
    request. No teardown: connections are per-read (see the repository), so there is no
    long-lived handle to close.
    """
    settings: ApiSettings = app.state.settings
    app.state.repository = SnapshotRepository.open(settings.snapshot_path)
    yield


def _meta_block(repo: SnapshotRepository) -> dict[str, object]:
    """The provenance ``meta`` block shared by ``/health`` and ``/v1/meta``."""
    meta = repo.meta()
    return {
        "snapshot_version": meta.snapshot_version,
        "schema_version": meta.schema_version,
        "row_count": meta.row_count,
        "candidate_count": meta.candidate_count,
        "coverage": {"year_min": meta.year_min, "year_max": meta.year_max},
        "source": meta.source,
        "license": meta.license,
        "build_timestamp": meta.build_timestamp,
    }


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the FastAPI app, resolving config from the environment if not injected.

    Config is resolved **eagerly** here (``ApiSettings.from_env`` with
    ``must_exist=True`` when ``settings`` is ``None``): an unset/missing snapshot raises
    the typed :class:`usvote.config.ConfigError` before the server starts, never a
    request-time 500. ``settings`` is injectable so tests drive a synthetic snapshot
    without touching the process environment.
    """
    settings = settings or ApiSettings.from_env()

    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        summary=API_SUMMARY,
        description=API_DESCRIPTION,
        contact=API_CONTACT,
        license_info=API_LICENSE_INFO,
        openapi_tags=_OPENAPI_TAGS,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.add_exception_handler(NotModified, not_modified_handler)
    app.add_exception_handler(ResourceNotFound, resource_not_found_handler)
    # No credentials mode: this is unauthenticated, read-only public data with no
    # cookies, so `allow_credentials` buys nothing — and enabling it turns an operator's
    # explicit `USVOTE_API_CORS_ORIGINS=*` into reflect-any-origin-*with-credentials*
    # (Starlette echoes the caller's Origin instead of a static `*`), the exact silent-
    # wildcard hazard D031 forbids. With credentials off, an explicit `*` degrades to a
    # plain `Access-Control-Allow-Origin: *` — the correct, safe behavior for a public
    # reference API. Methods are GET-only; no custom request headers are needed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
    )

    @app.get("/health", tags=["Ops"])
    def health() -> JSONResponse:
        """Liveness + snapshot-loaded status (uncached; an infra probe, not the API)."""
        repo: SnapshotRepository = app.state.repository
        return JSONResponse(
            content={"status": "ok", "snapshot_loaded": True, **_meta_block(repo)},
            headers={"Cache-Control": _HEALTH_CACHE_CONTROL},
        )

    v1 = APIRouter(
        prefix=settings.version_prefix,
        dependencies=[Depends(cache_dependency)],
    )

    @v1.get(
        "/meta",
        tags=["Meta"],
        response_model=SnapshotMetaResponse,
        summary="Snapshot provenance and build details.",
    )
    def meta() -> SnapshotMetaResponse:
        """Full snapshot provenance (source/license/coverage/version) + build details.

        The ``provenance`` block here is identical to the one in every data response's
        ``meta``; the extra fields are operational (schema version, counts, build time).
        Inherits the ETag / ``Cache-Control`` / conditional-304 behavior from the router
        dependency.
        """
        m = app.state.repository.meta()
        return SnapshotMetaResponse(
            provenance=Provenance.from_snapshot_meta(m),
            schema_version=m.schema_version,
            row_count=m.row_count,
            candidate_count=m.candidate_count,
            build_timestamp=m.build_timestamp,
        )

    app.include_router(v1)
    # The data endpoints (E8-S3) live on their own router: they must NOT carry the
    # blanket ``cache_dependency`` (which would 304 an unknown resource before the
    # handler's 404 check), so each calls it manually after existence. See routes.py.
    app.include_router(routes.router, prefix=settings.version_prefix)
    # Override openapi() so the docs' coverage line reflects the live snapshot (E8-S4).
    _install_live_openapi(app)
    return app
