"""
Join flow endpoints.
POST /request-join, GET /join-requests, approve, reject.

Simple flow: Agent requests to join → you Approve → controller assigns VPN IP
and pushes config to the agent (with retries). To connect two nodes, approve a connection.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.persistence.database import get_db
from app.persistence.models import JoinRequest, Node
from app.api.schemas import RequestJoinBody, JoinRequestSchema
from app.domain.enums import JoinRequestStatus
from app.core.config import settings
from app.services.join_service import approve_join, reject_join
from app.services.log_notify import log_event, notify
from app.domain.enums import LogEventType, NotificationType

router = APIRouter(tags=["join"])
logger = logging.getLogger(__name__)

# Background retry when push fails so user doesn't need to click "Push VPN IP"
PUSH_RETRY_DELAY = 5
PUSH_RETRY_COUNT = 4


async def _retry_set_vpn_address(agent_url: str, vpn_ip: str, private_key: str | None, node_name: str):
    """Retry set_vpn_address in background (agent may have been starting up)."""
    from app.services.agent_client import set_vpn_address
    for attempt in range(1, PUSH_RETRY_COUNT + 1):
        await asyncio.sleep(PUSH_RETRY_DELAY)
        ok = await set_vpn_address(agent_url, vpn_ip, private_key=private_key)
        if ok:
            logger.info("retry_set_vpn_address: success for %s after attempt %s", node_name, attempt)
            return
        logger.warning("retry_set_vpn_address: attempt %s/%s failed for %s", attempt, PUSH_RETRY_COUNT, node_name)


@router.post("/request-join")
def request_join(body: RequestJoinBody, db: Session = Depends(get_db)):
    """Register a new join request (node wants to join the VPN).
    If agent sends public_key and it's already a node -> return APPROVED with vpn_ip.
    If agent sends no public_key (controller-issued keys), create pending request; on approve we generate keys and push.
    Otherwise return PENDING (join request created or existing).
    """
    has_key = body.public_key and body.public_key.strip()
    pk_short = (body.public_key[:12] + "...") if has_key and len(body.public_key) > 12 else (body.public_key or "(no key)")
    logger.info("request-join: node_name=%s agent_url=%s public_key=%s", body.node_name, body.agent_url, pk_short)

    # Already a node? (only when agent sent a public_key)
    if has_key:
        node = db.query(Node).filter(Node.public_key == body.public_key.strip()).first()
    else:
        node = None
    if node:
        node.agent_url = body.agent_url
        db.commit()
        logger.info("request-join: existing node id=%s vpn_ip=%s -> APPROVED", node.id, node.vpn_ip)
        return {"status": "APPROVED", "vpn_ip": node.vpn_ip, "node_id": node.id}

    # Idempotency: same (node_name+agent_url) or same public_key pending -> return existing
    existing = (
        db.query(JoinRequest)
        .filter(JoinRequest.status == JoinRequestStatus.PENDING)
        .filter(
            (JoinRequest.public_key == (body.public_key or "").strip())
            | ((JoinRequest.node_name == body.node_name) & (JoinRequest.agent_url == body.agent_url))
        )
        .first()
    )
    if existing:
        logger.debug("request-join: existing pending request id=%s -> PENDING", existing.id)
        return JoinRequestSchema.model_validate(existing)
    jr = JoinRequest(
        node_name=body.node_name,
        public_key=(body.public_key or "").strip(),
        agent_url=body.agent_url,
        status=JoinRequestStatus.PENDING,
    )
    db.add(jr)
    log_event(db, LogEventType.JOIN_REQUESTED, f"Join requested: {body.node_name}")
    db.commit()
    db.refresh(jr)
    logger.info("request-join: new join request id=%s -> PENDING", jr.id)
    return JoinRequestSchema.model_validate(jr)


@router.get("/join-requests", response_model=list[JoinRequestSchema])
def list_join_requests(db: Session = Depends(get_db)):
    """List all join requests (dashboard: filter PENDING in UI if needed)."""
    rows = db.query(JoinRequest).order_by(JoinRequest.requested_at.desc()).all()
    logger.debug("join-requests list: count=%s", len(rows))
    return rows


@router.post("/join-requests/{id}/approve")
async def approve_join_request(id: int, db: Session = Depends(get_db)):
    """Approve join: assign VPN IP, create node, push config to agent (with background retries)."""
    from app.services.agent_client import set_vpn_address
    from app.services.join_service import approve_join_with_issued_key

    logger.info("approve_join_request: id=%s", id)
    # Support controller-issued keys: if join request had no public_key, we generate and push private_key too
    node, issued_private_key = approve_join_with_issued_key(
        db, id,
        settings.vpn_network,
        settings.vpn_start,
        settings.vpn_end,
    )
    if not node:
        logger.warning("approve_join_request: id=%s not found or not pending", id)
        raise HTTPException(status_code=400, detail="Join request not found or not pending")
    log_event(db, LogEventType.JOIN_APPROVED, f"Join approved: {node.name} -> {node.vpn_ip}")
    notify(db, NotificationType.JOIN_APPROVED, f"Node {node.name} approved with IP {node.vpn_ip}")
    db.commit()
    logger.info("approve_join_request: node_id=%s name=%s vpn_ip=%s agent_url=%s", node.id, node.name, node.vpn_ip, node.agent_url)
    # Push config to agent (VPN IP, and private key if we issued one)
    ok = await set_vpn_address(node.agent_url, node.vpn_ip, private_key=issued_private_key)
    if not ok:
        logger.warning("approve_join_request: set_vpn_address failed, will retry in background")
        asyncio.create_task(_retry_set_vpn_address(node.agent_url, node.vpn_ip, issued_private_key, node.name))
    return {"ok": True, "node_id": node.id, "vpn_ip": node.vpn_ip}


@router.post("/join-requests/{id}/reject")
def reject_join_request(id: int, db: Session = Depends(get_db)):
    """Reject a join request."""
    logger.info("reject_join_request: id=%s", id)
    if not reject_join(db, id):
        logger.warning("reject_join_request: id=%s not found or not pending", id)
        raise HTTPException(status_code=400, detail="Join request not found or not pending")
    log_event(db, LogEventType.JOIN_REJECTED, f"Join rejected: id={id}")
    notify(db, NotificationType.JOIN_REJECTED, f"Join request (id={id}) rejected")
    db.commit()
    return {"ok": True}
