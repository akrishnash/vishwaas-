"""Stats, notifications, mark-read."""
import asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.persistence.database import get_db
from app.persistence.models import Node, JoinRequest, ConnectionRequest, Connection, Notification, Log
from app.api.schemas import (
    StatsSchema,
    StatsDetailedSchema,
    NodeStatsSchema,
    PeerStatsSchema,
    NotificationSchema,
    LogSchema,
    TopologySchema,
)
from app.domain.enums import (
    NodeStatus,
    JoinRequestStatus,
    ConnectionRequestStatus,
    ConnectionStatus,
    LogEventType,
)
from app.services.agent_client import fetch_wg_status

router = APIRouter(tags=["monitoring"])

# Limit concurrent outbound calls to agents during stats collection
_STATS_SEMAPHORE = asyncio.Semaphore(20)


@router.get("/stats", response_model=StatsSchema)
def get_stats(db: Session = Depends(get_db)):
    """Dashboard overview counts."""
    total_nodes = db.query(Node).count()
    active_nodes = db.query(Node).filter(Node.status == NodeStatus.ACTIVE).count()
    pending_join_requests = (
        db.query(JoinRequest).filter(JoinRequest.status == JoinRequestStatus.PENDING).count()
    )
    pending_connection_requests = (
        db.query(ConnectionRequest)
        .filter(ConnectionRequest.status == ConnectionRequestStatus.PENDING)
        .count()
    )
    active_connections = (
        db.query(Connection).filter(Connection.status == ConnectionStatus.ACTIVE).count()
    )
    unread_notifications = db.query(Notification).filter(Notification.is_read == 0).count()
    return StatsSchema(
        total_nodes=total_nodes,
        active_nodes=active_nodes,
        pending_join_requests=pending_join_requests,
        pending_connection_requests=pending_connection_requests,
        active_connections=active_connections,
        unread_notifications=unread_notifications,
    )


@router.get("/stats/detailed", response_model=StatsDetailedSchema)
async def get_stats_detailed(db: Session = Depends(get_db)):
    """Fetch WireGuard stats from each active node's agent and aggregate bandwidth/connectivity."""
    nodes_db = db.query(Node).filter(
        Node.status.in_((NodeStatus.ACTIVE, NodeStatus.APPROVED))
    ).all()
    if not nodes_db:
        return StatsDetailedSchema(nodes=[], total_rx=0, total_tx=0)

    async def fetch_one(n: Node) -> NodeStatsSchema:
        async with _STATS_SEMAPHORE:
            wg = await fetch_wg_status(n.agent_url, timeout=3.0)
        if wg and wg.get("success"):
            peers = [
                PeerStatsSchema(
                    public_key=p.get("public_key", ""),
                    allowed_ips=p.get("allowed_ips", ""),
                    transfer_rx=p.get("transfer_rx", 0),
                    transfer_tx=p.get("transfer_tx", 0),
                    latest_handshake_ago=p.get("latest_handshake_ago"),
                )
                for p in wg.get("peers", [])
            ]
            tr = wg.get("total_rx", 0)
            tt = wg.get("total_tx", 0)
            return NodeStatsSchema(
                node_id=n.id,
                node_name=n.name,
                vpn_ip=n.vpn_ip,
                agent_url=n.agent_url,
                reachable=True,
                total_rx=tr,
                total_tx=tt,
                peers=peers,
            )
        return NodeStatsSchema(
            node_id=n.id,
            node_name=n.name,
            vpn_ip=n.vpn_ip,
            agent_url=n.agent_url,
            reachable=False,
            total_rx=0,
            total_tx=0,
            peers=[],
        )

    results = await asyncio.gather(*[fetch_one(n) for n in nodes_db])
    nodes_list = list(results)
    total_rx = sum(n.total_rx for n in nodes_list)
    total_tx = sum(n.total_tx for n in nodes_list)
    return StatsDetailedSchema(nodes=nodes_list, total_rx=total_rx, total_tx=total_tx)


@router.get("/notifications", response_model=list[NotificationSchema])
def list_notifications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List notifications (newest first)."""
    return db.query(Notification).order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/notifications/{id}/mark-read")
def mark_notification_read(id: int, db: Session = Depends(get_db)):
    """Mark a notification as read."""
    n = db.query(Notification).filter(Notification.id == id).first()
    if n:
        n.is_read = 1
        db.commit()
    return {"ok": True}


@router.get("/logs", response_model=list[LogSchema])
def list_logs(
    event_type: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List audit logs (newest first); optional filter by event_type (e.g. JOIN_APPROVED)."""
    q = db.query(Log).order_by(Log.created_at.desc())
    if event_type:
        try:
            et = LogEventType(event_type)
            q = q.filter(Log.event_type == et)
        except ValueError:
            pass
    return q.offset(skip).limit(limit).all()


@router.get("/topology", response_model=TopologySchema)
def get_topology(db: Session = Depends(get_db)):
    """Return graph-style topology: nodes + active connections as edges."""
    nodes_db = db.query(Node).all()
    conns_db = db.query(Connection).filter(Connection.status == ConnectionStatus.ACTIVE).all()
    nodes = [
        {
            "id": n.id,
            "name": n.name,
            "vpn_ip": n.vpn_ip,
            "status": n.status,
            "is_gateway": n.is_gateway,
        }
        for n in nodes_db
    ]
    edges = [
        {
            "id": c.id,
            "source_id": c.node_a_id,
            "target_id": c.node_b_id,
            "status": c.status,
        }
        for c in conns_db
    ]
    return TopologySchema(nodes=nodes, edges=edges)
