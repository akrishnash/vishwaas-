"""
Health and readiness endpoints.

These routes are public (no auth) and must be registered before the auth
dependency guard is applied in main.py.

  GET /health       — liveness probe: returns 200 if the process is up.
  GET /ready        — readiness probe: checks DB connectivity; returns 503 if unhealthy.
  GET /system-logs  — last N lines from controller log file (auth required).
  GET /backup       — download SQLite DB file (auth required).
"""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.security import require_auth

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


@router.get("/system-logs")
def system_logs(
    n: int = Query(default=200, ge=1, le=2000),
    _current_user: dict = Depends(require_auth),
):
    """Return last N lines from the controller rotating log file."""
    from app.core.config import settings
    log_path = Path(settings.log_file)
    if not log_path.exists():
        return {"lines": [], "total": 0, "file": str(log_path)}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = [line.rstrip("\n") for line in all_lines[-n:]]
        return {"lines": tail, "total": len(all_lines), "file": str(log_path)}
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backup")
def download_backup(_current_user: dict = Depends(require_auth)):
    """Stream the SQLite database file as a download."""
    from app.core.config import settings
    import re
    # Extract file path from sqlite:///./path or sqlite:////abs/path
    db_url = settings.database_url
    match = re.match(r"sqlite:///(.+)", db_url)
    if not match:
        raise HTTPException(status_code=400, detail="Backup only supported for SQLite databases")
    db_path = Path(match.group(1))
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"vishwaas-backup-{timestamp}.db"
    return FileResponse(
        path=str(db_path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
