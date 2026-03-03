"""
VISHWAAS Agent - Request authentication and authorization.

All agent API endpoints (except /health) require X-VISHWAAS-TOKEN.
Reject unknown IPs optional; token check is mandatory.
"""

from fastapi import Header, Request, HTTPException, status

from app.config import get_master_token
from app.logger import log_suspicious


def require_master_token(
    x_vishwaas_token: str | None = Header(None, alias="X-VISHWAAS-TOKEN"),
) -> None:
    """
    Dependency: require valid X-VISHWAAS-TOKEN.
    Reject with 401 if missing or wrong.
    """
    expected = get_master_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent not configured with master token",
        )
    if not x_vishwaas_token or x_vishwaas_token != expected:
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
