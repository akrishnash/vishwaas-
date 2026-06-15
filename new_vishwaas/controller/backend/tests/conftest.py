"""
Shared fixtures for VISHWAAS controller test suite.

Strategy:
  - Each test function gets a fresh in-memory SQLite DB using StaticPool
    so create_all() and sessions share the same connection (required for
    in-memory SQLite — each connection otherwise gets an empty database).
  - Rate limiter storage is cleared after each test to prevent 429 bleed.
  - FastAPI TestClient mocks out Alembic init, heartbeat task, and the
    SessionLocal used directly in lifespan + /ready endpoint.
  - All agent HTTP calls (set_vpn_address, add_peer, remove_peer) must be
    mocked individually in tests that trigger approval flows.
"""
import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.persistence.database import Base, get_db
from app.main import app

# ------------------------------------------------------------------
# Structurally valid WireGuard public keys for tests (44-char base64)
# ------------------------------------------------------------------
KEY_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa="
KEY_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb="
KEY_C = "ccccccccccccccccccccccccccccccccccccccccccc="


async def _noop_heartbeat():
    """Heartbeat stub that exits immediately — no background sweep in tests."""


@pytest.fixture()
def db_engine():
    # StaticPool: all sessions reuse the same connection so create_all()
    # and query sessions see the same in-memory SQLite database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(db_session, db_engine):
    """TestClient with all external dependencies mocked out."""
    from app.core.rate_limiter import limiter

    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Disable rate limiting before TestClient starts so fixture-level HTTP calls
    # (auth_headers, pending_join) are not counted against the rate limit window.
    # Both flags target the single shared limiter in app.core.rate_limiter.
    limiter.enabled = False
    limiter._storage.reset()

    with (
        patch("app.main.init_db"),
        patch("app.core.heartbeat.heartbeat_loop", side_effect=_noop_heartbeat),
        patch("app.persistence.database.SessionLocal", Session),
    ):
        with TestClient(app) as c:
            yield c

    from app.core.rate_limiter import limiter as _limiter
    _limiter._storage.reset()
    _limiter.enabled = True
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """JWT for the admin user using dev-mode login (no password hash configured)."""
    resp = client.post("/auth/login", json={"username": "admin", "password": "test"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def with_auth(monkeypatch):
    """
    Enable auth enforcement for tests that verify 401 behaviour.
    Patches settings.admin_password_hash to a real bcrypt hash so require_auth
    actually checks JWTs instead of bypassing in dev mode.
    Returns the plaintext password so callers can log in.
    """
    import bcrypt as _bc
    from app.core.config import settings
    TEST_PW = "testpw"
    # Use rounds=4 for speed in tests (bcrypt default is 12)
    hashed = _bc.hashpw(TEST_PW.encode(), _bc.gensalt(rounds=4)).decode()
    monkeypatch.setattr(settings, "admin_password_hash", hashed)
    monkeypatch.setattr(settings, "admin_username", "admin")
    return TEST_PW


@pytest.fixture()
def pending_join(client):
    """Create a PENDING join request and return the response JSON."""
    resp = client.post("/request-join", json={
        "node_name": "node-alpha",
        "agent_url": "http://192.168.10.16:7070",
        "public_key": KEY_A,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()
