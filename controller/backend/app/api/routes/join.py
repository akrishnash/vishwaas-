"""
Join flow endpoints.
POST /request-join, GET /join-requests, approve, reject.

Simple flow: Agent requests to join → you Approve → controller assigns VPN IP
and pushes config to the agent (with retries). To connect two nodes, approve a connection.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.persistence.database import get_db
from app.persistence.models import JoinRequest, Node
from app.api.schemas import RequestJoinBody, JoinRequestSchema
from app.domain.enums import JoinRequestStatus
from app.core.config import settings
from app.core.security import require_auth
from app.services.join_service import approve_join, reject_join
from app.services.log_notify import log_event, notify
from app.domain.enums import LogEventType, NotificationType

router = APIRouter(tags=["join"])
logger = logging.getLogger(__name__)

# Rate limiter reference — picks up from app.state.limiter registered in main.py
limiter = Limiter(key_func=get_remote_address)

# Background retry when push fails so user doesn't need to click "Push VPN IP"
PUSH_RETRY_DELAY = 5
PUSH_RETRY_COUNT = 4


async def _retry_set_vpn_address(
    agent_url: str,
    vpn_ip: str,
    private_key: str | None,
    node_name: str,
    node_id: int,
):
    """
    Retry set_vpn_address in background (agent may have been starting up).
    On success, upgrade node status from APPROVED to ACTIVE.
    """
    from app.services.agent_client import set_vpn_address
    from app.persistence.database import SessionLocal
    from app.persistence.models import Node
    from app.domain.enums import NodeStatus

    for attempt in range(1, PUSH_RETRY_COUNT + 1):
        await asyncio.sleep(PUSH_RETRY_DELAY)
        ok = await set_vpn_address(agent_url, vpn_ip, private_key=private_key)
        if ok:
            logger.info("retry_set_vpn_address: success for %s after attempt %s", node_name, attempt)
            db = SessionLocal()
            try:
                node = db.query(Node).filter(Node.id == node_id).first()
                if node and node.status.value in ("APPROVED",):
                    node.status = NodeStatus.ACTIVE
                    db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            return
        logger.warning("retry_set_vpn_address: attempt %s/%s failed for %s", attempt, PUSH_RETRY_COUNT, node_name)


@router.post("/request-join")
@limiter.limit("10/minute")
async def request_join(request: Request, body: RequestJoinBody, db: Session = Depends(get_db)):
    """
    Node agent calls this on every startup.

    Industry-grade lifecycle:
    - If this public key already exists as an ACTIVE/APPROVED node (i.e. agent restarted):
        → tear down its old connections on peer agents (best-effort)
        → delete the stale node record so admin must re-approve
        → create a fresh PENDING join request
    - If a PENDING request already exists for this key/agent → return it (idempotent retry)
    - Otherwise → create a new PENDING join request
    Admin must always explicitly approve before the node becomes active.
    """
    from app.services.agent_client import remove_peer
    from app.domain.enums import ConnectionStatus
    from app.persistence.models import Connection, ConnectionRequest
    from sqlalchemy import or_

    has_key = body.public_key and body.public_key.strip()
    pk_short = (body.public_key[:12] + "...") if has_key and len(body.public_key) > 12 else (body.public_key or "(no key)")
    logger.info("request-join: node_name=%s agent_url=%s public_key=%s", body.node_name, body.agent_url, pk_short)

    # If node already exists with this public key → it restarted. Force re-approval.
    if has_key:
        existing_node = db.query(Node).filter(Node.public_key == body.public_key.strip()).first()
        if existing_node:
            logger.info(
                "request-join: known node %s (id=%s) restarted — tearing down connections, forcing re-approval",
                existing_node.name, existing_node.id,
            )
            # Remove this node as a peer from all currently connected nodes
            active_conns = (
                db.query(Connection)
                .filter(Connection.status == ConnectionStatus.ACTIVE)
                .filter(or_(Connection.node_a_id == existing_node.id, Connection.node_b_id == existing_node.id))
                .all()
            )
            for conn in active_conns:
                peer_id = conn.node_b_id if conn.node_a_id == existing_node.id else conn.node_a_id
                peer = db.query(Node).filter(Node.id == peer_id).first()
                if peer and peer.agent_url and existing_node.public_key:
                    await remove_peer(peer.agent_url, existing_node.public_key)
                    logger.info("request-join: removed stale peer %s from node %s", pk_short, peer.name)

            # Clean up DB records for this node
            db.query(Connection).filter(
                or_(Connection.node_a_id == existing_node.id, Connection.node_b_id == existing_node.id)
            ).delete(synchronize_session=False)
            db.query(ConnectionRequest).filter(
                or_(ConnectionRequest.requester_id == existing_node.id, ConnectionRequest.target_id == existing_node.id)
            ).delete(synchronize_session=False)
            db.delete(existing_node)
            db.flush()
            logger.info("request-join: removed stale node id=%s", existing_node.id)

    # Idempotency: if a PENDING request already exists for this key/agent, return it
    existing_jr = (
        db.query(JoinRequest)
        .filter(JoinRequest.status == JoinRequestStatus.PENDING)
        .filter(
            (JoinRequest.public_key == (body.public_key or "").strip())
            | ((JoinRequest.node_name == body.node_name) & (JoinRequest.agent_url == body.agent_url))
        )
        .first()
    )
    if existing_jr:
        logger.debug("request-join: existing pending request id=%s -> PENDING", existing_jr.id)
        return JoinRequestSchema.model_validate(existing_jr)

    jr = JoinRequest(
        node_name=body.node_name,
        public_key=(body.public_key or "").strip(),
        agent_url=body.agent_url,
        status=JoinRequestStatus.PENDING,
    )
    db.add(jr)
    log_event(db, LogEventType.JOIN_REQUESTED, f"Join requested: {body.node_name}", performed_by="agent")
    db.commit()
    db.refresh(jr)
    logger.info("request-join: new join request id=%s -> PENDING", jr.id)
    return JoinRequestSchema.model_validate(jr)


@router.get("/join-requests", response_model=list[JoinRequestSchema])
def list_join_requests(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List join requests (newest first). Use skip/limit for pagination."""
    rows = db.query(JoinRequest).order_by(JoinRequest.requested_at.desc()).offset(skip).limit(limit).all()
    logger.debug("join-requests list: skip=%s limit=%s count=%s", skip, limit, len(rows))
    return rows


@router.post("/join-requests/{id}/approve")
async def approve_join_request(id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_auth)):
    """
    Approve join — two-phase:
      Phase 1: DB writes (node APPROVED, join request marked, log, notify) → commit.
      Phase 2: Push VPN config to agent → upgrade to ACTIVE on success.
    If the agent is unreachable, schedule background retries that also set ACTIVE on success.
    """
    from app.services.agent_client import set_vpn_address
    from app.services.join_service import approve_join_with_issued_key
    from app.domain.enums import NodeStatus
    from datetime import datetime, timezone

    logger.info("approve_join_request: id=%s", id)

    # Phase 1 — all DB writes in one transaction; node starts as APPROVED
    node, issued_private_key = approve_join_with_issued_key(
        db, id,
        settings.vpn_network,
        settings.vpn_start,
        settings.vpn_end,
    )
    if not node:
        logger.warning("approve_join_request: id=%s not found or not pending", id)
        raise HTTPException(status_code=400, detail="Join request not found or not pending")

    # Stamp last_seen so heartbeat doesn't immediately auto-delete a newly approved node
    # (heartbeat treats last_seen=None as "offline forever" → instant delete)
    node.last_seen = datetime.now(timezone.utc)

    log_event(db, LogEventType.JOIN_APPROVED, f"Join approved: {node.name} -> {node.vpn_ip}", performed_by=current_user.get("sub"))
    notify(db, NotificationType.JOIN_APPROVED, f"Node {node.name} approved with IP {node.vpn_ip}")
    db.commit()  # node.status == APPROVED at this point

    logger.info("approve_join_request: node_id=%s name=%s vpn_ip=%s agent_url=%s", node.id, node.name, node.vpn_ip, node.agent_url)

    # Phase 2 — push to agent; upgrade to ACTIVE only on success
    ok = await set_vpn_address(node.agent_url, node.vpn_ip, private_key=issued_private_key)
    if ok:
        node.status = NodeStatus.ACTIVE
        db.commit()
        logger.info("approve_join_request: node_id=%s now ACTIVE", node.id)
    else:
        logger.warning("approve_join_request: set_vpn_address failed, scheduling background retry")
        node_id = node.id
        asyncio.create_task(
            _retry_set_vpn_address(node.agent_url, node.vpn_ip, issued_private_key, node.name, node_id)
        )
    return {"ok": True, "node_id": node.id, "vpn_ip": node.vpn_ip}


@router.post("/join-requests/{id}/reject")
def reject_join_request(id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_auth)):
    """Reject a join request."""
    logger.info("reject_join_request: id=%s", id)
    if not reject_join(db, id):
        logger.warning("reject_join_request: id=%s not found or not pending", id)
        raise HTTPException(status_code=400, detail="Join request not found or not pending")
    log_event(db, LogEventType.JOIN_REJECTED, f"Join rejected: id={id}", performed_by=current_user.get("sub"))
    notify(db, NotificationType.JOIN_REJECTED, f"Join request (id={id}) rejected")
    db.commit()
    return {"ok": True}
