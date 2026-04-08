"""JWT creation/verification, revocation, and FastAPI auth dependency."""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    jti = secrets.token_hex(16)
    return jwt.encode(
        {"sub": username, "exp": expire, "jti": jti},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def revoke_token(jti: str, expires_at: datetime, db: Session) -> None:
    """Add token JTI to the blacklist."""
    from app.persistence.models import RevokedToken
    db.merge(RevokedToken(jti=jti, expires_at=expires_at))


def prune_revoked_tokens(db: Session) -> None:
    """Remove expired tokens from the blacklist (called on startup)."""
    from app.persistence.models import RevokedToken
    try:
        now = datetime.now(timezone.utc)
        db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete()
        db.commit()
    except Exception:
        db.rollback()


def _is_token_revoked(jti: str, db: Session) -> bool:
    """Return True if the token has been blacklisted."""
    from app.persistence.models import RevokedToken
    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None


def _decode_token(token: str, db: Session | None = None) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise ValueError("missing sub")
        if db is not None:
            jti = payload.get("jti")
            if jti and _is_token_revoked(jti, db):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def require_auth(
    token: str | None = Depends(_oauth2),
    db: Session = Depends(lambda: next(__import__("app.persistence.database", fromlist=["get_db"]).get_db())),
) -> dict:
    """Dependency: enforce auth when a password hash is configured.

    If VISHWAAS_ADMIN_PASSWORD_HASH is empty, auth is bypassed (dev mode).
    """
    if not settings.admin_password_hash:
        return {"sub": "dev"}
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(token, db=db)
