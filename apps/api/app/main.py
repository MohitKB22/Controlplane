"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.db import engine
from app.core.errors import http_error_response, register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    MaxBodySizeMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from app.providers.registry import provider_summary

logger = get_logger(__name__)

# Paths that always belong to the API, never to the single-page app.
API_PATH_PREFIXES = ("/api/", "/health/", "/assets/", "/docs", "/redoc", "/openapi.json")

DESCRIPTION = """
Enterprise control plane for AI agents, RAG pipelines, models, prompts,
evaluations, guardrails, cost and Azure service health.

**Authentication** — `POST /api/v1/auth/login` returns a bearer token. CI and
automation can use a long-lived key in the `X-API-Key` header instead.

**Provider modes** — every external dependency is behind a provider interface.
`local` runs deterministic in-process implementations with no Azure account;
`azure` uses the real services. The active mode is reported by `/api/v1/overview`
and `/health/ready`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO")
    problems = settings.validate_production()
    if problems:
        for problem in problems:
            logger.error("configuration_error", extra={"problem": problem})
        if settings.environment == "production":
            raise RuntimeError(
                "Refusing to start in production with an invalid configuration: "
                + "; ".join(problems)
            )
    logger.info(
        "startup",
        extra={
            "environment": settings.environment,
            "demo_mode": settings.demo_mode,
            "providers": provider_summary(),
        },
    )
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Order matters. Starlette wraps in reverse: the middleware added LAST is the
    # outermost and runs first. Resulting request order:
    #   CORS -> RequestContext -> RateLimit -> MaxBodySize -> routes
    # so 429/413 short-circuit responses still carry CORS headers, a request ID
    # and the security headers.
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Correlation-ID"],
        expose_headers=["X-Request-ID", "X-Correlation-ID"],
        max_age=600,
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    def live() -> dict:
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"], summary="Readiness probe")
    def ready() -> dict:
        """Readiness requires a working database connection."""
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            database_ok = True
        except Exception as exc:
            logger.error("readiness_failed", extra={"reason": str(exc)[:200]})
            database_ok = False
        return {
            "status": "ready" if database_ok else "not_ready",
            "database": "up" if database_ok else "down",
            "environment": settings.environment,
            "demo_mode": settings.demo_mode,
            "providers": provider_summary(),
        }

    web_dist = _web_dist()

    # HEAD as well as GET: uptime monitors commonly probe the root with HEAD.
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False, response_model=None)
    def root() -> dict | Response:
        if web_dist is not None:
            return _spa_index(web_dist)
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs",
            "api": settings.api_v1_prefix,
        }

    if web_dist is not None:
        _mount_web(app, web_dist)

    return app


# ------------------------------------------------------------------ web app


class _ImmutableStaticFiles(StaticFiles):
    """Vite emits content-hashed asset names, so they can be cached forever."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _web_dist() -> Path | None:
    if not settings.web_dist_dir:
        return None
    dist = Path(settings.web_dist_dir).resolve()
    if not (dist / "index.html").is_file():
        logger.error("web_dist_missing", extra={"path": str(dist)})
        return None
    return dist


def _spa_index(dist: Path) -> FileResponse:
    # index.html must never be cached, or a deploy would strand clients on
    # asset hashes that no longer exist.
    return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})


def _mount_web(app: FastAPI, dist: Path) -> None:
    """Serve the built UI on the API's origin.

    Client-side routes (/agents, /runs/<id>, …) are not known to the server, so
    a GET that would otherwise 404 outside the API namespace returns index.html
    and React Router takes over. API paths keep their JSON 404 envelope.
    """
    if (dist / "assets").is_dir():
        app.mount("/assets", _ImmutableStaticFiles(directory=dist / "assets"), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException) -> Response:
        path = request.url.path
        if (
            exc.status_code == 404
            and request.method in {"GET", "HEAD"}
            and not path.startswith(API_PATH_PREFIXES)
        ):
            # Top-level files in dist (e.g. a favicon) are served as-is.
            candidate = (dist / path.lstrip("/")).resolve()
            if candidate.is_file() and dist in candidate.parents:
                return FileResponse(candidate)
            return _spa_index(dist)
        return http_error_response(request, exc)


app = create_app()
