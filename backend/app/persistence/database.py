"""
Database session and engine.
SQLite with structured schema; single source of truth for control plane.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=settings.debug,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency: yield DB session for request scope."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call on startup."""
    from app.persistence import models  # noqa: F401 - trigger model registration
    Base.metadata.create_all(bind=engine)
