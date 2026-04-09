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
from app.services.agent_client import add_peer, remove_peer, enable_ip_forward, _endpoint_from_agent_url

logger = logging.getLogger(__name__)


def _vpn_subnet(vpn_ip: str) -> str:
    """Derive the /24 subnet from a VPN IP (e.g. 10.10.10.5 -> 10.10.10.0/24)."""
    if not vpn_ip:
        return "10.10.10.0/24"
    parts = vpn_ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    return "10.10.10.0/24"


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

    # Hub-and-spoke routing:
    # - If node_b is gateway hub: node_a (spoke) gets subnet route 0.0.0.0/0 or the VPN /24 via hub,
    #   and hub gets /32 for this spoke.
    # - If node_a is gateway hub: node_b (spoke) gets subnet route, hub gets /32.
    # - Neither is hub: standard /32 peer-to-peer.
    vpn_subnet = _vpn_subnet(node_a.vpn_ip or node_b.vpn_ip)
    if node_b.is_gateway:
        # node_a is a spoke; it routes all VPN traffic through hub (node_b)
        allowed_for_a = vpn_subnet  # spoke learns full VPN subnet via hub
        allowed_for_b = None        # hub gets /32 for this spoke (default)
        await enable_ip_forward(node_b.agent_url)
        logger.info("approve_connection: node_b=%s is gateway hub; spoke allowed_ips=%s", node_b.name, allowed_for_a)
    elif node_a.is_gateway:
        # node_b is a spoke; node_a is hub
        allowed_for_a = None        # hub gets /32 for this spoke
        allowed_for_b = vpn_subnet  # spoke learns full VPN subnet via hub
        await enable_ip_forward(node_a.agent_url)
        logger.info("approve_connection: node_a=%s is gateway hub; spoke allowed_ips=%s", node_a.name, allowed_for_b)
    else:
        allowed_for_a = None  # default /32
        allowed_for_b = None  # default /32

    # Call both agents atomically: if node_b fails, roll back node_a's peer.
    ok_a = await add_peer(node_a.agent_url, node_b.public_key, node_b.vpn_ip, peer_endpoint=endpoint_b, allowed_ips=allowed_for_a)
    if not ok_a:
        logger.error(
            "approve_connection: add_peer to node_a=%s failed — aborting, no connection created",
            node_a.name,
        )
        return None

    ok_b = await add_peer(node_b.agent_url, node_a.public_key, node_a.vpn_ip, peer_endpoint=endpoint_a, allowed_ips=allowed_for_b)
    if not ok_b:
        logger.error(
            "approve_connection: add_peer to node_b=%s failed — rolling back node_a peer",
            node_b.name,
        )
        await remove_peer(node_a.agent_url, node_b.public_key)
        return None

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
    Remove the peer keys from both agents and mark the connection TERMINATED.
    The WireGuard interface stays up on both nodes — they remain on the VPN with
    their assigned IPs, just no longer peered with each other (same state as
    approved-but-no-connection).
    Returns True if the connection was active and teardown was run.
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
    return True
