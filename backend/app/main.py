"""
VISHWAAS Master - Control plane entry point.
Clean architecture: API -> services -> persistence -> domain.
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.persistence.database import init_db
from app.api.routes import join, nodes, connections, monitoring

# Logging: show everywhere (stdout) for debugging agent and controller
logging.basicConfig(
    level=logging.DEBUG if getattr(settings, "debug", False) else logging.INFO,
    # log4j-style: 2026-02-18 12:34:56,789 INFO  logger.name - message
    format="%(asctime)s,%(msecs)03d %(levelname)-5s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("vishwaas.controller")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup."""
    logger.info("VISHWAAS controller starting")
    init_db()
    yield
    logger.info("VISHWAAS controller shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Enterprise VPN master controller for WireGuard-based nodes",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes (paths as per spec)
app.include_router(join.router)
app.include_router(nodes.router)
app.include_router(connections.router)
app.include_router(monitoring.router)


@app.get("/")
def root():
    logger.debug("Root / requested")
    return {"service": settings.app_name, "version": "1.0.0"}
