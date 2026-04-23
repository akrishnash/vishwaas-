"""Stats, notifications, mark-read."""
import asyncio
import csv
import io
import json
from datetime import datetime
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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
    total_nodes = db.query(Node).filter(
        Node.status.in_((NodeStatus.ACTIVE, NodeStatus.APPROVED))
    ).count()
    active_nodes = db.query(Node).filter(
        Node.status.in_((NodeStatus.ACTIVE, NodeStatus.APPROVED))
    ).count()
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


def _apply_log_filters(q, event_type, search, date_from, date_to, performed_by):
    """Apply common log filters to a query."""
    if event_type:
        try:
            q = q.filter(Log.event_type == LogEventType(event_type))
        except ValueError:
            pass
    if search:
        q = q.filter(Log.description.ilike(f"%{search}%"))
    if date_from:
        q = q.filter(Log.created_at >= date_from)
    if date_to:
        q = q.filter(Log.created_at <= date_to)
    if performed_by:
        q = q.filter(Log.performed_by == performed_by)
    return q


@router.get("/logs", response_model=list[LogSchema])
def list_logs(
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    performed_by: Optional[str] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List audit logs (newest first) with optional filters."""
    q = db.query(Log).order_by(Log.created_at.desc())
    q = _apply_log_filters(q, event_type, search, date_from, date_to, performed_by)
    return q.offset(skip).limit(limit).all()


@router.get("/logs/export")
def export_logs(
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    performed_by: Optional[str] = None,
    format: Literal["csv", "json"] = "csv",
    db: Session = Depends(get_db),
):
    """Export audit logs as CSV or JSON (up to 10,000 rows)."""
    q = db.query(Log).order_by(Log.created_at.desc())
    q = _apply_log_filters(q, event_type, search, date_from, date_to, performed_by)
    rows = q.limit(10000).all()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if format == "json":
        data = [
            {
                "id": r.id,
                "event_type": r.event_type.value,
                "description": r.description,
                "performed_by": r.performed_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        content = json.dumps(data, indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="vishwaas-logs-{timestamp}.json"'},
        )

    # CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "event_type", "description", "performed_by", "created_at"])
    for r in rows:
        writer.writerow([
            r.id,
            r.event_type.value,
            r.description,
            r.performed_by or "",
            r.created_at.isoformat() if r.created_at else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="vishwaas-logs-{timestamp}.csv"'},
    )


@router.get("/topology", response_model=TopologySchema)
def get_topology(db: Session = Depends(get_db)):
    """Return graph-style topology: nodes + active connections as edges."""
    nodes_db = db.query(Node).filter(
        Node.status.in_((NodeStatus.ACTIVE, NodeStatus.APPROVED))
    ).all()
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
