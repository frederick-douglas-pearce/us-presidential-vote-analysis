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

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from usvote.api import routes
from usvote.api.cache import NotModified, cache_dependency, not_modified_handler
from usvote.api.config import ApiSettings
from usvote.api.models import ErrorBody, ErrorDetail
from usvote.api.repository import SnapshotRepository
from usvote.api.routes import ResourceNotFound

#: ``Cache-Control`` for the liveness probe — never cached, unlike the ``/v1`` surface.
_HEALTH_CACHE_CONTROL = "no-store"

#: ``Cache-Control`` for a 404: a not-found body must never be cached as if it were the
#: resource (the #97 architect note — a 404 is not a representation of the URL).
_ERROR_CACHE_CONTROL = "no-store"


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
        title="US Presidential Vote API",
        version="0.1.0",
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

    @app.get("/health", tags=["ops"])
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

    @v1.get("/meta", tags=["meta"])
    def meta() -> dict[str, object]:
        """The snapshot provenance block (version, coverage, source/license).

        Minimal, but a real ``/v1`` response: it inherits the ETag / ``Cache-Control`` /
        conditional-304 behavior from the router dependency, so that machinery is wired
        and testable in E8-S2 before the S3 data endpoints land.
        """
        return _meta_block(app.state.repository)

    app.include_router(v1)
    # The data endpoints (E8-S3) live on their own router: they must NOT carry the
    # blanket ``cache_dependency`` (which would 304 an unknown resource before the
    # handler's 404 check), so each calls it manually after existence. See routes.py.
    app.include_router(routes.router, prefix=settings.version_prefix)
    return app
