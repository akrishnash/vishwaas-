"""
Health and readiness endpoints.

These routes are public (no auth) and must be registered before the auth
dependency guard is applied in main.py.

  GET /health  — liveness probe: returns 200 if the process is up.
  GET /ready   — readiness probe: checks DB connectivity; returns 503 if unhealthy.
"""
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=True)
def health():
    """Liveness probe. Returns 200 as long as the process is running."""
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@router.get("/ready", include_in_schema=True)
def readiness():
    """
    Readiness probe. Executes a trivial DB query to verify connectivity.
    Returns 200 when healthy, 503 when the DB is unreachable.
    """
    from app.persistence.database import SessionLocal
    db: Session = SessionLocal()
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    finally:
        db.close()

    payload = {"status": "ready" if db_ok else "degraded", "db": db_ok}
    return JSONResponse(content=payload, status_code=200 if db_ok else 503)
