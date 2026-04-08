"""
VISHWAAS Master - Control plane entry point.
Clean architecture: API -> services -> persistence -> domain.
"""
import asyncio
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.security import require_auth
from app.persistence.database import init_db
from app.api.routes import join, nodes, connections, monitoring, auth as auth_routes

logger = logging.getLogger("vishwaas.controller")


def _configure_logging() -> None:
    """Configure logging; honours VISHWAAS_LOG_JSON env var."""
    from app.core.logging_config import configure_logging
    configure_logging()


def _validate_controller_config() -> None:
    """Validate controller config; abort in production if insecure defaults detected."""
    if not (getattr(settings, "agent_token", None) or "").strip():
        logger.warning(
            "VISHWAAS_AGENT_TOKEN is not set. Please set it in .env (same value as each agent's master_token) "
            "so the controller can push config and peers to agents. Without it, approve/connection flows will not work."
        )
    if settings.environment == "production":
        if settings.jwt_secret == "change-me-in-production":
            logger.critical(
                "VISHWAAS_JWT_SECRET is set to the default insecure value. "
                "Generate a secret: python3 -c \"import secrets; print(secrets.token_hex(32))\" "
                "and set VISHWAAS_JWT_SECRET in .env before running in production."
            )
            sys.exit(1)
        if "*" in settings.allowed_origins:
            logger.critical(
                "VISHWAAS_ALLOWED_ORIGINS contains '*'. "
                "Set an explicit comma-separated list of allowed origins for production."
            )
            sys.exit(1)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Attach / propagate X-Request-ID on every request."""

    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        from app.core.correlation import set_correlation_id
        set_correlation_id(cid)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Increment HTTP request counters and latency histograms."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path
        try:
            from app.core.metrics import http_requests_total, http_request_duration_seconds
            http_requests_total.labels(
                method=request.method,
                path=path,
                status_code=str(response.status_code),
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method,
                path=path,
            ).observe(duration)
        except Exception:
            pass
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: validate config, init DB, start heartbeat. Shutdown: cancel tasks."""
    _configure_logging()
    logger.info("VISHWAAS controller starting (environment=%s)", settings.environment)
    _validate_controller_config()
    init_db()

    from app.core.http_client import init_client, close_client
    from app.core.heartbeat import heartbeat_loop
    from app.core.security import prune_revoked_tokens
    from app.persistence.database import SessionLocal

    # Prune expired JWT blacklist entries from previous sessions
    _db = SessionLocal()
    try:
        prune_revoked_tokens(_db)
    finally:
        _db.close()

    await init_client()
    hb_task = asyncio.create_task(heartbeat_loop())
    yield
    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass
    await close_client()
    logger.info("VISHWAAS controller shutting down")


_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

# Rate limiter (shared across routes via app.state.limiter)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.app_name,
    description="Enterprise VPN master controller for WireGuard-based nodes",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(CorrelationMiddleware)
app.add_middleware(PrometheusMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Public routes (no auth)
app.include_router(auth_routes.router)
from app.api.routes import health as health_routes  # noqa: E402
app.include_router(health_routes.router)

# Prometheus metrics scrape endpoint (protect via nginx allow/deny in production)
from fastapi.responses import PlainTextResponse  # noqa: E402

@app.get("/metrics", include_in_schema=False)
def metrics():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# All other routes require authentication
_auth = [Depends(require_auth)]
app.include_router(join.router, dependencies=_auth)
app.include_router(nodes.router, dependencies=_auth)
app.include_router(connections.router, dependencies=_auth)
app.include_router(monitoring.router, dependencies=_auth)


@app.get("/")
def root():
    logger.debug("Root / requested")
    return {"service": settings.app_name, "version": "1.0.0"}
