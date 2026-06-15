"""
VISHWAAS Agent - Request authentication and authorization.

All agent API endpoints (except /health) require X-VISHWAAS-TOKEN.
Additionally, all token-gated endpoints are IP-restricted to the controller.
"""
import hmac

from fastapi import Header, Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_stored_agent_token
from app.logger import log_suspicious

# Paths exempt from IP allowlisting (monitoring / uptime probes)
_OPEN_PATHS: frozenset[str] = frozenset({"/health"})


class ControllerIPMiddleware(BaseHTTPMiddleware):
    """
    Reject requests from IPs that are not the configured controller.
    /health is exempted so external monitoring tools can poll it.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _OPEN_PATHS:
            return await call_next(request)

        from app.config import get_allowed_controller_ips
        allowed = get_allowed_controller_ips()
        if not allowed:
            return await call_next(request)

        client_ip = request.client.host if request.client else ""
        if client_ip not in allowed:
            log_suspicious(client_ip, "request from non-controller IP")
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied: unauthorized source IP"},
            )
        return await call_next(request)


def require_master_token(
    x_vishwaas_token: str | None = Header(None, alias="X-VISHWAAS-TOKEN"),
) -> None:
    """Dependency: require valid X-VISHWAAS-TOKEN. Reject with 401 if missing or wrong."""
    expected = get_stored_agent_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent not configured with master token",
        )
    if not x_vishwaas_token or not hmac.compare_digest(x_vishwaas_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-VISHWAAS-TOKEN",
        )


def log_unauthorized(request: Request, reason: str = "invalid token") -> None:
    """Log suspicious access from request client IP."""
    client = request.client.host if request.client else "unknown"
    log_suspicious(client, reason)


def get_client_ip(request: Request) -> str:
    """Return client IP for logging."""
    return request.client.host if request.client else "unknown"
