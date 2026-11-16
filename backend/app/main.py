"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings
from app.db.session import get_engine

logger = logging.getLogger("tenderpilot")


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    # The HTTP client libraries can log request URLs/headers at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    settings = get_settings()
    logger.info(
        "Starting %s (%s), AI provider default: %s, storage: %s", settings.app_name, settings.environment, settings.ai_provider, settings.storage_backend
    )
    if settings.environment != "test":
        try:
            from app.services.ai_workflows import recover_interrupted_runs

            n = recover_interrupted_runs()
            if n:
                logger.warning("Marked %s interrupted analysis run(s) as failed.", n)
        except Exception:  # noqa: BLE001 - never block startup on housekeeping (e.g. before migrations)
            logger.warning("Could not check for interrupted analysis runs (has the database been migrated?).")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TenderPilot AI API",
        version=__version__,
        description="AI-assisted tender and proposal management. All routes are versioned under /api/v1.",
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url="/api/redoc" if settings.docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith(("/api/docs", "/api/redoc")):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/v1"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Return field errors without echoing submitted values (which may contain passwords).
        errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        first = errors[0] if errors else {}
        field = ".".join(str(p) for p in (first.get("loc") or [])[1:]) or "request"
        return JSONResponse(status_code=422, content={"detail": f"Invalid {field}: {first.get('msg', 'invalid value')}", "errors": errors})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred. Please try again."})

    @app.get("/health", tags=["health"])
    @app.get("/api/v1/health", tags=["health"], include_in_schema=False)
    def health() -> dict:
        # "ephemeral_data" lets the frontend warn users that this deployment does not keep data.
        return {"status": "ok", "version": __version__, "ephemeral_data": settings.ephemeral_demo}

    @app.get("/health/ready", tags=["health"])
    @app.get("/api/v1/health/ready", tags=["health"], include_in_schema=False)
    def ready() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.execute(text("SELECT 1 FROM alembic_version LIMIT 1"))
        except Exception:  # noqa: BLE001
            return JSONResponse(status_code=503, content={"status": "unavailable", "database": "error"})
        return JSONResponse({"status": "ok", "database": "ok"})

    app.include_router(api_router)
    return app


app = create_app()
