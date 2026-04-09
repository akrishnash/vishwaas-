"""
Heartbeat loop: periodically ping all ACTIVE/APPROVED agents.

Marks nodes OFFLINE after OFFLINE_THRESHOLD_SECONDS of no response.
Restores nodes to ACTIVE when they come back online.
Updates Prometheus gauges after each sweep.
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.persistence.database import SessionLocal
from app.persistence.models import Node, JoinRequest
from app.domain.enums import NodeStatus, JoinRequestStatus

logger = logging.getLogger("vishwaas.heartbeat")

HEARTBEAT_INTERVAL = 60           # seconds between sweeps
OFFLINE_THRESHOLD_SECONDS = 90   # mark OFFLINE if silent for this long
DELETE_THRESHOLD_SECONDS = 300   # auto-delete node if offline for this long (5 min)
STALE_JOIN_REQUEST_SECONDS = 120 # expire PENDING join requests if agent unreachable for this long


async def _ping(url: str, timeout: float = 5.0) -> bool:
    """Return True if agent /health responds with HTTP 2xx."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"{url.rstrip('/')}/health")
            return r.is_success
    except Exception:
        return False


async def heartbeat_loop() -> None:
    """Run forever; sweep once per HEARTBEAT_INTERVAL. First sweep runs immediately on startup."""
    logger.info(
        "Heartbeat loop started (interval=%ss, offline_threshold=%ss)",
        HEARTBEAT_INTERVAL,
        OFFLINE_THRESHOLD_SECONDS,
    )
    # Immediate sweep on startup — use aggressive mode so nodes that don't respond
    # are marked OFFLINE right away instead of waiting 90s
    await _sweep(startup=True)
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        await _sweep()


async def _sweep(startup: bool = False) -> None:
    """One heartbeat sweep: ping all active/approved nodes, update status.
    startup=True: mark unreachable nodes OFFLINE immediately (no threshold wait)."""
    db = SessionLocal()
    try:
        nodes = (
            db.query(Node)
            .filter(Node.status.in_((NodeStatus.ACTIVE, NodeStatus.APPROVED, NodeStatus.OFFLINE)))
            .all()
        )
        if not nodes:
            return

        results = await asyncio.gather(*[_ping(n.agent_url) for n in nodes], return_exceptions=True)
        now = datetime.now(timezone.utc)

        for node, alive in zip(nodes, results):
            if isinstance(alive, Exception):
                alive = False

            if alive:
                node.last_seen = now
                if node.status == NodeStatus.OFFLINE:
                    logger.info("heartbeat: node %s (%s) is back ONLINE", node.name, node.agent_url)
                    node.status = NodeStatus.ACTIVE
            else:
                if startup:
                    # On controller startup: immediately mark unreachable nodes OFFLINE
                    # so the dashboard reflects reality instead of showing stale ACTIVE nodes
                    if node.status != NodeStatus.OFFLINE:
                        logger.info(
                            "heartbeat startup: node %s unreachable — marking OFFLINE immediately",
                            node.name,
                        )
                        node.status = NodeStatus.OFFLINE
                    continue

                last = node.last_seen
                if last is None:
                    # Never seen — node was just approved; give it time to come up
                    continue
                seconds_since = (now - last).total_seconds()
                if seconds_since > DELETE_THRESHOLD_SECONDS:
                    # Stage 2: been offline too long — auto-delete
                    logger.warning(
                        "heartbeat: node %s offline for %.0fs (>%ss) — auto-deleting",
                        node.name, seconds_since, DELETE_THRESHOLD_SECONDS,
                    )
                    from app.persistence.models import Connection, ConnectionRequest
                    from sqlalchemy import or_
                    db.query(Connection).filter(
                        or_(Connection.node_a_id == node.id, Connection.node_b_id == node.id)
                    ).delete(synchronize_session=False)
                    db.query(ConnectionRequest).filter(
                        or_(ConnectionRequest.requester_id == node.id, ConnectionRequest.target_id == node.id)
                    ).delete(synchronize_session=False)
                    db.delete(node)
                elif seconds_since > OFFLINE_THRESHOLD_SECONDS and node.status != NodeStatus.OFFLINE:
                    # Stage 1: mark OFFLINE so admin can see it on dashboard
                    logger.warning(
                        "heartbeat: node %s (%s) unreachable for %.0fs — marking OFFLINE",
                        node.name, node.agent_url, seconds_since,
                    )
                    node.status = NodeStatus.OFFLINE

        db.commit()

        # Expire stale PENDING join requests where the agent is no longer reachable
        await _expire_stale_join_requests(db, now)

        _update_gauges(db)

    except Exception:
        logger.exception("heartbeat: sweep failed")
        db.rollback()
    finally:
        db.close()


async def _expire_stale_join_requests(db, now) -> None:
    """
    Ping agents with PENDING join requests. If the agent is unreachable and the
    request is older than STALE_JOIN_REQUEST_SECONDS, mark it REJECTED so it
    doesn't clutter the dashboard after the machine goes offline.
    """
    pending = db.query(JoinRequest).filter(JoinRequest.status == JoinRequestStatus.PENDING).all()
    if not pending:
        return

    results = await asyncio.gather(
        *[_ping(jr.agent_url) for jr in pending],
        return_exceptions=True,
    )
    for jr, alive in zip(pending, results):
        if isinstance(alive, Exception):
            alive = False
        if alive:
            continue
        age = (now - jr.requested_at).total_seconds() if jr.requested_at else float("inf")
        if age > STALE_JOIN_REQUEST_SECONDS:
            logger.info(
                "heartbeat: join request id=%s (%s) agent unreachable for %.0fs — expiring",
                jr.id, jr.node_name, age,
            )
            jr.status = JoinRequestStatus.REJECTED
    db.commit()


def _update_gauges(db) -> None:
    """Refresh Prometheus gauges with current counts."""
    try:
        from app.core.metrics import nodes_active, nodes_offline, join_requests_pending
        nodes_active.set(db.query(Node).filter(Node.status == NodeStatus.ACTIVE).count())
        nodes_offline.set(db.query(Node).filter(Node.status == NodeStatus.OFFLINE).count())
        join_requests_pending.set(
            db.query(JoinRequest).filter(JoinRequest.status == JoinRequestStatus.PENDING).count()
        )
    except Exception:
        pass
