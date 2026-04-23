"""
Connection request and connection management endpoints.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_auth

from app.persistence.database import get_db
from app.persistence.models import ConnectionRequest, Connection, Node
from app.api.schemas import (
    RequestConnectionBody,
    ConnectionRequestSchema,
    ConnectionRequestWithNodesSchema,
    ConnectionSchema,
    ConnectionWithNodesSchema,
)
from app.domain.enums import ConnectionRequestStatus, ConnectionStatus
from app.services.connection_service import approve_connection, reject_connection, terminate_connection_and_teardown
from app.services.log_notify import log_event, notify
from app.domain.enums import LogEventType, NotificationType

router = APIRouter(tags=["connections"])
logger = logging.getLogger(__name__)


def _connection_request_with_nodes(db: Session, cr: ConnectionRequest) -> ConnectionRequestWithNodesSchema:
    r = db.query(Node).get(cr.requester_id)
    t = db.query(Node).get(cr.target_id)
    return ConnectionRequestWithNodesSchema(
        id=cr.id,
        requester_id=cr.requester_id,
        target_id=cr.target_id,
        status=cr.status,
        requested_at=cr.requested_at,
        requester_name=r.name if r else None,
        target_name=t.name if t else None,
    )


def _connection_with_nodes(db: Session, c: Connection) -> ConnectionWithNodesSchema:
    a = db.query(Node).get(c.node_a_id)
    b = db.query(Node).get(c.node_b_id)
    return ConnectionWithNodesSchema(
        id=c.id,
        node_a_id=c.node_a_id,
        node_b_id=c.node_b_id,
        status=c.status,
        created_at=c.created_at,
        node_a_name=a.name if a else None,
        node_b_name=b.name if b else None,
    )


@router.post("/request-connection", response_model=ConnectionRequestSchema)
def request_connection(body: RequestConnectionBody, db: Session = Depends(get_db), current_user: dict = Depends(require_auth)):
    """Request a connection between two nodes."""
    logger.info("request-connection: requester_id=%s target_id=%s", body.requester_id, body.target_id)
    if body.requester_id == body.target_id:
        raise HTTPException(status_code=400, detail="Requester and target must differ")
    for nid in (body.requester_id, body.target_id):
        if not db.query(Node).filter(Node.id == nid).first():
            raise HTTPException(status_code=404, detail=f"Node {nid} not found")
    # Optional: reject if same pair already pending
    existing = (
        db.query(ConnectionRequest)
        .filter(
            ConnectionRequest.requester_id == body.requester_id,
            ConnectionRequest.target_id == body.target_id,
            ConnectionRequest.status == ConnectionRequestStatus.PENDING,
        )
        .first()
    )
    if existing:
        logger.debug("request-connection: existing pending request id=%s", existing.id)
        return existing
    cr = ConnectionRequest(
        requester_id=body.requester_id,
        target_id=body.target_id,
        status=ConnectionRequestStatus.PENDING,
    )
    db.add(cr)
    log_event(db, LogEventType.CONNECTION_REQUESTED, f"Connection requested: {body.requester_id} -> {body.target_id}", performed_by=current_user.get("sub"))
    db.commit()
    db.refresh(cr)
    logger.info("request-connection: created id=%s", cr.id)
    return cr


@router.get("/connection-requests", response_model=list[ConnectionRequestWithNodesSchema])
def list_connection_requests(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List connection requests with node names (newest first)."""
    rows = db.query(ConnectionRequest).order_by(ConnectionRequest.requested_at.desc()).offset(skip).limit(limit).all()
    return [_connection_request_with_nodes(db, r) for r in rows]


@router.post("/connection-requests/{id}/approve")
async def approve_connection_request(id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_auth)):
    """Approve: call agents, create connection, log, notify."""
    logger.info("approve_connection_request: id=%s", id)
    conn = await approve_connection(db, id)
    if not conn:
        # approve_connection returns None for: not found/pending OR agent call failure
        cr = db.query(ConnectionRequest).filter(ConnectionRequest.id == id).first()
        if not cr or cr.status == ConnectionRequestStatus.PENDING:
            logger.warning("approve_connection_request: id=%s agent configuration failed", id)
            raise HTTPException(
                status_code=502,
                detail="Could not configure one or both nodes; no connection created. Check agent connectivity.",
            )
        logger.warning("approve_connection_request: id=%s not found or not pending", id)
        raise HTTPException(status_code=400, detail="Connection request not found or not pending")
    a = db.query(Node).get(conn.node_a_id)
    b = db.query(Node).get(conn.node_b_id)
    log_event(db, LogEventType.CONNECTION_APPROVED, f"Connection approved: {a.name} <-> {b.name}", performed_by=current_user.get("sub"))
    notify(db, NotificationType.CONNECTION_APPROVED, f"Connection {a.name} <-> {b.name} active")
    db.commit()
    logger.info("approve_connection_request: connection_id=%s %s <-> %s", conn.id, a.name, b.name)
    return {"ok": True, "connection_id": conn.id}


@router.post("/connection-requests/{id}/reject")
def reject_connection_request(id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_auth)):
    """Reject a connection request."""
    logger.info("reject_connection_request: id=%s", id)
    if not reject_connection(db, id):
        raise HTTPException(status_code=400, detail="Connection request not found or not pending")
    log_event(db, LogEventType.CONNECTION_REJECTED, f"Connection request id={id} rejected", performed_by=current_user.get("sub"))
    notify(db, NotificationType.CONNECTION_REJECTED, f"Connection request (id={id}) rejected")
    db.commit()
    return {"ok": True}


@router.get("/connections", response_model=list[ConnectionWithNodesSchema])
def list_connections(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List all connections with node names (newest first)."""
    rows = db.query(Connection).order_by(Connection.created_at.desc()).offset(skip).limit(limit).all()
    return [_connection_with_nodes(db, c) for c in rows]


@router.delete("/connections/{id}")
async def delete_connection(id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_auth)):
    """Terminate connection: remove peers from both agents, mark TERMINATED. Interface stays up on both nodes."""
    logger.info("delete_connection: id=%s", id)
    conn = db.query(Connection).filter(Connection.id == id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    ok = await terminate_connection_and_teardown(db, id)
    if not ok:
        raise HTTPException(status_code=400, detail="Connection not active")
    a = db.query(Node).get(conn.node_a_id)
    b = db.query(Node).get(conn.node_b_id)
    log_event(db, LogEventType.CONNECTION_TERMINATED, f"Connection terminated: {a.name} <-> {b.name}", performed_by=current_user.get("sub"))
    notify(db, NotificationType.CONNECTION_TERMINATED, f"Connection {a.name} <-> {b.name} terminated")
    db.commit()
    logger.info("delete_connection: terminated connection_id=%s %s <-> %s", id, a.name, b.name)
    return {"ok": True}
