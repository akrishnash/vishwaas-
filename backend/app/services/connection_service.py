"""
Connection flow: request -> approve/reject.
On approve: call agent A and B to add peer, create connection record, log, notify.
On terminate: remove peers from both agents, mark TERMINATED, then down wg0 on each node if it has no other ACTIVE connections.
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.persistence.models import Node, ConnectionRequest, Connection
from app.domain.enums import ConnectionStatus, ConnectionRequestStatus
from app.services.agent_client import add_peer, remove_peer, wg_down, _endpoint_from_agent_url

logger = logging.getLogger(__name__)


async def approve_connection(
    db: Session,
    connection_request_id: int,
) -> Connection | None:
    """
    1. Call agent A -> add peer B
    2. Call agent B -> add peer A
    3. Create connection record (ACTIVE)
    4. Update connection request status
    Caller is responsible for log and notification.
    """
    cr = (
        db.query(ConnectionRequest)
        .filter(ConnectionRequest.id == connection_request_id)
        .first()
    )
    if not cr or cr.status != ConnectionRequestStatus.PENDING:
        return None

    node_a = db.query(Node).filter(Node.id == cr.requester_id).first()
    node_b = db.query(Node).filter(Node.id == cr.target_id).first()
    if not node_a or not node_b:
        return None

    logger.info("approve_connection: adding peers node_a=%s (%s) <-> node_b=%s (%s)", node_a.name, node_a.agent_url, node_b.name, node_b.agent_url)
    # WireGuard endpoint so each node knows where to send UDP (peer's agent host + :51820)
    endpoint_b = _endpoint_from_agent_url(node_b.agent_url)
    endpoint_a = _endpoint_from_agent_url(node_a.agent_url)
    # Call both agents to add the peer (best-effort; we still record connection)
    ok_a = await add_peer(node_a.agent_url, node_b.public_key, node_b.vpn_ip, peer_endpoint=endpoint_b)
    ok_b = await add_peer(node_b.agent_url, node_a.public_key, node_a.vpn_ip, peer_endpoint=endpoint_a)
    if not ok_a:
        logger.warning("approve_connection: add_peer to node_a=%s failed", node_a.name)
    if not ok_b:
        logger.warning("approve_connection: add_peer to node_b=%s failed", node_b.name)

    conn = Connection(
        node_a_id=cr.requester_id,
        node_b_id=cr.target_id,
        status=ConnectionStatus.ACTIVE,
    )
    db.add(conn)
    cr.status = ConnectionRequestStatus.APPROVED
    db.flush()
    return conn


def reject_connection(db: Session, connection_request_id: int) -> bool:
    """Mark connection request as rejected."""
    cr = db.query(ConnectionRequest).filter(ConnectionRequest.id == connection_request_id).first()
    if not cr or cr.status != ConnectionRequestStatus.PENDING:
        return False
    cr.status = ConnectionRequestStatus.REJECTED
    return True


def terminate_connection(db: Session, connection_id: int) -> bool:
    """Set connection status to TERMINATED. Agent peer removal can be async."""
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn or conn.status != ConnectionStatus.ACTIVE:
        return False
    conn.status = ConnectionStatus.TERMINATED
    return True


async def terminate_connection_and_teardown(db: Session, connection_id: int) -> bool:
    """
    Remove peers from both agents, set connection TERMINATED, then for each node
    if it has no other ACTIVE connections call wg_down on that agent.
    Returns True if connection was active and teardown was run.
    """
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn or conn.status != ConnectionStatus.ACTIVE:
        return False

    node_a = db.query(Node).filter(Node.id == conn.node_a_id).first()
    node_b = db.query(Node).filter(Node.id == conn.node_b_id).first()
    if not node_a or not node_b:
        conn.status = ConnectionStatus.TERMINATED
        db.flush()
        return True

    logger.info(
        "terminate_connection_and_teardown: remove peers node_a=%s (%s) node_b=%s (%s)",
        node_a.name, node_a.agent_url, node_b.name, node_b.agent_url,
    )
    await remove_peer(node_a.agent_url, node_b.public_key)
    await remove_peer(node_b.agent_url, node_a.public_key)
    conn.status = ConnectionStatus.TERMINATED
    db.flush()

    def other_active_connections_for(node_id: int) -> int:
        return (
            db.query(Connection)
            .filter(Connection.status == ConnectionStatus.ACTIVE)
            .filter(or_(Connection.node_a_id == node_id, Connection.node_b_id == node_id))
            .count()
        )

    if other_active_connections_for(node_a.id) == 0:
        logger.info("terminate_connection_and_teardown: wg_down %s (%s)", node_a.name, node_a.agent_url)
        await wg_down(node_a.agent_url)
    if other_active_connections_for(node_b.id) == 0:
        logger.info("terminate_connection_and_teardown: wg_down %s (%s)", node_b.name, node_b.agent_url)
        await wg_down(node_b.agent_url)
    return True
