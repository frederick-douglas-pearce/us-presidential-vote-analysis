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
from usvote.api.origin_guard import install_origin_guard
from usvote.api.repository import SnapshotRepository
from usvote.api.routes import ResourceNotFound
from usvote.snapshot_schema import EC_LICENSE, EC_SOURCE

#: ``Cache-Control`` for the liveness probe — never cached, unlike the ``/v1`` surface.
_HEALTH_CACHE_CONTROL = "no-store"

#: ``Cache-Control`` for a 404: a not-found body must never be cached as if it were the
#: resource (the #97 architect note — a 404 is not a representation of the URL).
_ERROR_CACHE_CONTROL = "no-store"

# --- OpenAPI metadata (E8-S4, #98) --------------------------------------------
# The "advertising surface" the epic (#94/D031) chose REST+OpenAPI for. Titles, a
# real description, grouped tags, and a first-class provenance/licensing statement,
# so the docs are hand-off-ready (e.g. to the MIT Election Lab).

#: D016 policy defaults, used only for the *static fallback* schema (the constructor
#: description + license block, served if the schema is somehow built before the
#: snapshot is open). The **served** schema re-derives source/license/coverage from the
#: loaded snapshot in :func:`_install_live_openapi`, so the advertised provenance always
#: matches ``meta.provenance`` rather than a literal that could drift.
_MIT = provenance.source_display("MIT")
_CC0 = provenance.license_display("CC0-1.0")
# Imported, not re-typed: `snapshot_schema` is where the build gets these codes, so a
# change there moves the fallback schema with it. Re-typing them would let the static
# OpenAPI block advertise one code while every live response 500'd on the other.
_NARA = provenance.source_display(EC_SOURCE)
_US_PD = provenance.license_display(EC_LICENSE)

#: The popular-vote window quoted in the **static fallback** description only — the path
#: taken when the schema is built before the lifespan opens the snapshot. The served
#: schema reads the real numbers off the snapshot (:func:`_install_live_openapi`), so
#: these literals never reach a running deployment. They will go stale when a new
#: election is ingested; that is tolerable precisely because they are unreachable in
#: production, and preferable to a fallback that says nothing about coverage at all.
_FALLBACK_PV_WINDOW = (1976, 2024)

API_TITLE = "US Presidential Vote API"

#: Bumped 0.2.0 -> 0.3.0 by #139. The **served contract changed**, so leaving it would
#: have told a pinned consumer nothing had: pre-1976 years went from 404 to 200,
#: ``info.license`` flipped from CC0 to the EC public-domain statement, and ``EcPvRow``
#: gained four required fields. ``SNAPSHOT_SCHEMA_VERSION`` moved for the same event —
#: this is the half of it external consumers can actually see.
#:
#: 0.3.0 -> 0.4.0 by #102, on the same rule: ``NationalSummaryRow`` gained five hybrid
#: fields, both year endpoints gained an ``election`` object, and ``/summary`` returns a
#: new response model. Additive, hence minor. ``SNAPSHOT_SCHEMA_VERSION`` moved 2 -> 3
#: for the same event.
API_VERSION = "0.4.0"

API_SUMMARY = (
    "Electoral College vs. popular vote for every US presidential election from 1824."
)

#: Tokens filled per-schema by :func:`_render_description` — from the loaded snapshot
#: for the served schema, or the D016 defaults for the static fallback.
_COVERAGE_TOKEN = "{coverage_window}"
_NOTE_TOKEN = "{provenance_note}"

#: A plain template, **not** an f-string: the literal ``{data, meta}`` must survive, and
#: the two tokens above are filled by :func:`_render_description`.
_DESCRIPTION_TEMPLATE = """\
A read-only HTTP API over a joined **Electoral College + popular vote** dataset for US
presidential elections, at the `(year, state, candidate)` grain plus a per-year national
roll-up.

It exists to make one comparison easy to inspect: **who won the Electoral College
vs. who won the national popular vote** — including the elections where those diverge,
when a candidate loses the national popular vote yet still takes office. Each
candidate's national electoral-vote total, finishing rank, and whether they took
office sit alongside the popular-vote totals.

**Three methods, compared for you.** Each election also carries an `election` object
giving the winner under three methods — the Electoral College, the national popular
vote, and a **hybrid** (the average of the two shares) — with a flag for whether the
popular vote or the hybrid would have flipped the electoral-college result, and each
method's top-two margin in percentage points. Precomputed, so the comparison does
not depend on a consumer re-deriving it from the raw totals.

**Coverage:** {coverage_window} (US presidential elections).

**Data provenance & licensing.** {provenance_note} Every response carries the exact
source, license, coverage window, and snapshot version under `meta.provenance`; the same
block, with build details, is at `GET /v1/meta`.

**Getting started.** Browse the interactive docs at `/docs` (Swagger UI) or `/redoc`
(ReDoc). Every response is JSON in a `{data, meta}` envelope and carries an `ETag` and
`Cache-Control` for conditional requests.
"""


def _render_description(coverage_window: str, provenance_note: str) -> str:
    """Fill the description template's coverage + provenance-note tokens."""
    return _DESCRIPTION_TEMPLATE.replace(_COVERAGE_TOKEN, coverage_window).replace(
        _NOTE_TOKEN, provenance_note
    )


#: The static fallback description — valid standalone (a generic coverage phrase + the
#: D016 note). The served schema overwrites it with live snapshot values.
API_DESCRIPTION = _render_description(
    "every US presidential election from 1824 onward",
    provenance.redistributable_note(
        _MIT,
        _CC0,
        ec_source=_NARA,
        ec_license=_US_PD,
        pv_year_min=_FALLBACK_PV_WINDOW[0],
        pv_year_max=_FALLBACK_PV_WINDOW[1],
    ),
)

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

#: The OpenAPI ``license`` block advertises the **data** license — this API serves
#: public-domain data and carries no separate API terms.
#:
#: OpenAPI's ``info.license`` holds exactly one entry, and this surface has two data
#: licenses (CC0 for the popular vote, U.S. Government public domain for the electoral
#: college). The **electoral-college** license is the one advertised here, because it
#: covers every row while CC0 covers only the popular-vote window; both are stated in
#: full in the description's provenance note and in every response's
#: ``meta.provenance``. Advertising CC0 as *the* license — as this did before #139 —
#: would put the narrower claim on the broader dataset.
API_LICENSE_INFO = {"name": _US_PD.name, "url": _US_PD.url}


def _install_live_openapi(app: FastAPI) -> None:
    """Override ``app.openapi()`` so provenance + coverage are read from the snapshot.

    Delegates to FastAPI's own ``openapi()`` — so every constructor option is honored
    and nothing is silently dropped — then overwrites only the dynamic bits (the
    description's coverage window + provenance note, and the license block) with values
    resolved from the loaded snapshot, so the advertised provenance matches
    ``meta.provenance`` exactly.

    FastAPI builds the schema lazily on the first ``/openapi.json`` / ``/docs`` /
    ``/redoc`` request — normally **after** the lifespan opened the snapshot. If it is
    somehow built first (e.g. ``create_app(...).openapi()`` offline, with no lifespan),
    the repository is absent and the **static fallback** schema is served, never a 500.
    """
    base_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        # Builds + caches app.openapi_schema from the constructor config (this same dict
        # object is what we patch and return, so the cache holds the live version).
        schema = base_openapi()
        repo: SnapshotRepository | None = getattr(app.state, "repository", None)
        if repo is not None:
            meta = repo.meta()
            src = provenance.source_display(meta.source)
            lic = provenance.license_display(meta.license)
            ec_src = provenance.source_display(meta.ec_source)
            ec_lic = provenance.license_display(meta.ec_license)
            info = schema["info"]
            info["description"] = _render_description(
                f"{meta.year_min}–{meta.year_max}",
                provenance.redistributable_note(
                    src,
                    lic,
                    ec_source=ec_src,
                    ec_license=ec_lic,
                    pv_year_min=meta.pv_year_min,
                    pv_year_max=meta.pv_year_max,
                ),
            )
            # The EC license, for the reason API_LICENSE_INFO gives: it is the one that
            # covers every row.
            info["license"] = {"name": ec_lic.name, "url": ec_lic.url}
        return schema

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
        "coverage": {
            "year_min": meta.year_min,
            "year_max": meta.year_max,
            "pv_year_min": meta.pv_year_min,
            "pv_year_max": meta.pv_year_max,
        },
        "source": meta.source,
        "license": meta.license,
        "ec_source": meta.ec_source,
        "ec_license": meta.ec_license,
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
    # Origin lock-down (D034): reject direct-to-run.app /v1 hits that skip Cloudflare.
    # Opt-in + fail-open — active only when the secret is configured (deployed env); the
    # returned flag is surfaced on /health so the posture is observable, never silent.
    app.state.origin_guard_enforced = install_origin_guard(
        app, secret=settings.origin_secret, protected_prefix=settings.version_prefix
    )

    @app.get("/health", tags=["Ops"])
    def health() -> JSONResponse:
        """Liveness + snapshot-loaded status (uncached; an infra probe, not the API)."""
        repo: SnapshotRepository = app.state.repository
        origin_guard = "enforced" if app.state.origin_guard_enforced else "open"
        return JSONResponse(
            content={
                "status": "ok",
                "snapshot_loaded": True,
                "origin_guard": origin_guard,
                **_meta_block(repo),
            },
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
