"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import time

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.dependencies import get_limiter
from src.api.routes.health import router as health_router
from src.api.routes.auth import router as auth_router
from src.api.routes.jobs import router as jobs_router
from src.api.routes.mcp_test import router as mcp_test_router
from src.api.routes.repositories import router as repositories_router
from src.api.routes.search import router as search_router
from src.api.routes.symbols import router as symbols_router
from src.api.routes.workers import router as workers_router
from src.api.routes.statistics import router as statistics_router
from src.api.routes.analysis import router as analysis_router
from src.api.routes.enrichment import router as enrichment_router
from src.config.settings import get_settings
from src.database.models import Base
from src.database.session import engine
from src.utils.logging_config import configure_logging, get_logger
from src.utils.metrics import api_request_duration, api_requests_total


configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def _lifespan(_: FastAPI):
    logger.info("application_startup", environment=settings.environment)

    if "*" in settings.api_cors_origins:
        logger.warning(
            "cors_wildcard_configured",
            message="API_CORS_ORIGINS contains '*'; credentialed browser requests are disabled by design. "
                    "Set explicit origins to enable cookies/auth headers in browsers."
        )

    # Validate auth configuration
    if settings.auth_enabled and not settings.admin_api_key and not settings.read_only_api_keys:
        logger.warning(
            "auth_misconfiguration",
            message="AUTH_ENABLED=true but no API keys configured! "
                    "Set ADMIN_API_KEY or disable auth with AUTH_ENABLED=false"
        )

    # Validate MCP HTTP auth posture
    if settings.mcp_transport == "http" and not settings.mcp_auth_enabled:
        logger.warning(
            "mcp_http_auth_disabled",
            message="MCP HTTP transport is running without MCP auth. This should only be used for trusted local development. "
                    "Set MCP_AUTH_ENABLED=true for shared or network-exposed deployments."
        )

    # Validate JWT configuration
    if not settings.jwt_secret_key:
        logger.error(
            "jwt_secret_key_missing",
            message="JWT_SECRET_KEY is required! Generate with: "
                    "python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
        raise RuntimeError("JWT_SECRET_KEY not configured")

    # Setup Azure DevOps git credentials on startup
    try:
        from src.azuredevops.repository_manager import setup_git_credentials
        setup_git_credentials()
    except Exception as exc:
        logger.warning("startup_git_credentials_setup_failed", error=str(exc))

    # Initialize database tables on first startup
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("database_extension_enabled", extension="vector")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("database_tables_initialized")
    except Exception as exc:
        logger.error("database_initialization_failed", error=str(exc))

    # Run auto-migrations
    try:
        from scripts.auto_migrate import run_all_migrations
        success = await run_all_migrations()
        if success:
            logger.info("auto_migrations_applied_successfully")
        else:
            logger.warning("auto_migrations_failed_but_continuing")
    except Exception as exc:
        logger.error("auto_migrations_error", error=str(exc))

    # Reset any interrupted jobs from previous run
    try:
        from src.database.session import AsyncSessionLocal
        from src.workers.job_monitor import JobMonitor

        async with AsyncSessionLocal() as session:
            monitor = JobMonitor(session)
            reset_count = await monitor.reset_running_jobs_on_startup()
            if reset_count > 0:
                logger.warning("interrupted_jobs_reset_on_startup", count=reset_count)
    except Exception as exc:
        logger.error("startup_job_cleanup_failed", error=str(exc))

    try:
        yield
    finally:
        logger.info("application_shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="MCP Server for semantic code search and analysis",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=_lifespan,
)

limiter = get_limiter()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins = settings.api_cors_origins
_cors_has_wildcard = "*" in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=not _cors_has_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    """Collect request metrics and structured logs."""

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        logger.error("api_request_failed", path=request.url.path, method=request.method, error=str(exc))
        raise

    duration = time.perf_counter() - start
    api_requests_total.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    api_request_duration.labels(method=request.method, endpoint=request.url.path).observe(duration)
    response.headers["X-Process-Time"] = f"{duration:.6f}"

    logger.info(
        "api_request_completed",
        path=request.url.path,
        method=request.method,
        status=response.status_code,
        duration=duration,
    )
    return response


@app.exception_handler(404)
async def _not_found_handler(_: Request, __: Exception):
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})


@app.exception_handler(500)
async def _internal_error_handler(request: Request, exc: Exception):
    logger.error("internal_server_error", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_router, prefix="/api/v1", tags=["Health"])
app.include_router(auth_router, prefix="/api/v1", tags=["Auth"])
app.include_router(search_router, prefix="/api/v1", tags=["Search"])
app.include_router(repositories_router, prefix="/api/v1", tags=["Repositories"])
app.include_router(symbols_router, prefix="/api/v1", tags=["Symbols"])
app.include_router(jobs_router, prefix="/api/v1", tags=["Jobs"])
app.include_router(workers_router, prefix="/api/v1", tags=["Workers"])
app.include_router(statistics_router, prefix="/api/v1", tags=["Statistics"])
app.include_router(analysis_router, prefix="/api/v1", tags=["Analysis"])
app.include_router(enrichment_router, prefix="/api/v1", tags=["Enrichment"])
app.include_router(mcp_test_router, prefix="/api/v1", tags=["MCP Testing"])

# MCP HTTP transport endpoint (no prefix - root level)
# Import lazily only when HTTP transport is enabled to reduce API startup/import overhead
# for the default stdio deployment mode.
if settings.mcp_transport == "http":
    from src.api.routes.mcp_http import router as mcp_http_router

    app.include_router(mcp_http_router, tags=["MCP HTTP Transport"])


