"""
Shared httpx.AsyncClient for all controller → agent HTTP calls.

A single client with connection pooling is more efficient than creating
a new client per request. Call init_client() on startup and close_client()
on shutdown (both wired in main.py lifespan).
"""
import logging

import httpx

logger = logging.getLogger("vishwaas.http_client")

_client: httpx.AsyncClient | None = None


async def init_client() -> None:
    """Create the shared client. Called from lifespan startup."""
    global _client
    _client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        timeout=10.0,
    )
    logger.debug("Shared httpx client initialized")


async def close_client() -> None:
    """Close the shared client. Called from lifespan shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.debug("Shared httpx client closed")


def get_client() -> httpx.AsyncClient:
    """Return the shared client. Raises RuntimeError if not yet initialised."""
    if _client is None:
        raise RuntimeError(
            "HTTP client not initialized. Ensure init_client() was called in lifespan."
        )
    return _client
