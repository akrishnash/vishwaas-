"""Authentication endpoints: login, me, logout."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, require_auth, verify_password, revoke_token
from app.persistence.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    """Exchange credentials for a JWT. Bypassed when no password hash is configured."""
    if not settings.admin_password_hash:
        # Dev mode: accept any credentials
        return TokenResponse(access_token=create_access_token(body.username))

    if body.username != settings.admin_username or not verify_password(
        body.password, settings.admin_password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return TokenResponse(access_token=create_access_token(body.username))


@router.get("/me")
def me(claims: dict = Depends(require_auth)):
    """Return the authenticated username."""
    return {"username": claims.get("sub", "unknown")}


@router.post("/logout")
def logout(claims: dict = Depends(require_auth), db: Session = Depends(get_db)):
    """Invalidate the current JWT by adding its jti to the revocation blacklist."""
    jti = claims.get("jti")
    exp = claims.get("exp")
    if jti and exp:
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        revoke_token(jti, expires_at, db)
        db.commit()
    return {"ok": True}
