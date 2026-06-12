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
    """
    Run pending Alembic migrations on startup.

    For a fresh database this creates all tables.
    For an existing database it applies any new migrations.

    First-time upgrade from create_all:
        cd controller/backend && alembic stamp head
    """
    from pathlib import Path
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config()
    alembic_cfg.set_main_option(
        "script_location",
        str(Path(__file__).parent.parent.parent / "alembic"),
    )
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")
