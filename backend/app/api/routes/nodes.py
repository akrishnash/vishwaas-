"""Node management: list, get, delete, push VPN IP."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.persistence.database import get_db
from app.persistence.models import Node, Connection, ConnectionRequest
from app.api.schemas import NodeSchema, NodeUpdateBody
from app.domain.enums import NodeStatus, ConnectionStatus
from app.services.log_notify import log_event
from app.services.agent_client import set_vpn_address, remove_peer, remove_node
from app.domain.enums import LogEventType

router = APIRouter(prefix="/nodes", tags=["nodes"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[NodeSchema])
def list_nodes(db: Session = Depends(get_db)):
    """List all nodes."""
    rows = db.query(Node).order_by(Node.created_at.desc()).all()
    logger.debug("list_nodes: count=%s", len(rows))
    return rows


@router.post("/{id}/push-vpn-address")
async def push_vpn_address(id: int, db: Session = Depends(get_db)):
    """Tell the agent at this node to set its WireGuard interface to the assigned VPN IP (and bring up wg0)."""
    logger.info("push-vpn-address: node_id=%s", id)
    node = db.query(Node).filter(Node.id == id).first()
    if not node:
        logger.warning("push-vpn-address: node_id=%s not found", id)
        raise HTTPException(status_code=404, detail="Node not found")
    logger.info("push-vpn-address: node_id=%s name=%s agent_url=%s vpn_ip=%s", id, node.name, node.agent_url, node.vpn_ip)
    ok = await set_vpn_address(node.agent_url, node.vpn_ip)
    if not ok:
        logger.warning("push-vpn-address: set_vpn_address failed for node_id=%s agent_url=%s", id, node.agent_url)
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach agent at {node.agent_url}. Check agent_advertise_url and that the agent is running.",
        )
    logger.info("push-vpn-address: success node_id=%s vpn_ip=%s", id, node.vpn_ip)
    return {"ok": True, "message": f"VPN IP {node.vpn_ip} pushed to {node.name}"}


@router.get("/{id}", response_model=NodeSchema)
def get_node(id: int, db: Session = Depends(get_db)):
    """Get a single node by id."""
    logger.debug("get_node: id=%s", id)
    node = db.query(Node).filter(Node.id == id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.patch("/{id}", response_model=NodeSchema)
def update_node(id: int, body: NodeUpdateBody, db: Session = Depends(get_db)):
    """Update node's agent_url and/or name. Use when agent_advertise_url was wrong at join."""
    node = db.query(Node).filter(Node.id == id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if body.agent_url is not None:
        node.agent_url = body.agent_url
        logger.info("update_node: id=%s agent_url=%s", id, body.agent_url)
    if body.name is not None:
        node.name = body.name
        logger.info("update_node: id=%s name=%s", id, body.name)
    db.commit()
    db.refresh(node)
    return node


@router.delete("/{id}")
async def delete_node(id: int, db: Session = Depends(get_db)):
    """
    Remove a node: send remove_peer to other nodes for each active connection,
    then send remove_node to this node's agent (deletes wg0), then remove from DB.
    Allowed only when node status is ACTIVE, OFFLINE, or APPROVED.
    """
    logger.info("delete_node: id=%s", id)
    node = db.query(Node).filter(Node.id == id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if node.status not in (NodeStatus.ACTIVE, NodeStatus.OFFLINE, NodeStatus.APPROVED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove node with status {node.status.value}; only ACTIVE, OFFLINE, or APPROVED",
        )
    name = node.name
    # For each ACTIVE connection involving this node, remove this node's peer from the other node's agent
    active_conns = (
        db.query(Connection)
        .filter(Connection.status == ConnectionStatus.ACTIVE)
        .filter((Connection.node_a_id == id) | (Connection.node_b_id == id))
        .all()
    )
    for conn in active_conns:
        other_id = conn.node_b_id if conn.node_a_id == id else conn.node_a_id
        other = db.query(Node).filter(Node.id == other_id).first()
        if other and other.agent_url:
            await remove_peer(other.agent_url, node.public_key)
            logger.info("delete_node: removed peer from other node %s for connection %s", other.name, conn.id)
    # Tell this node's agent to remove interface and clean up
    if node.agent_url:
        await remove_node(node.agent_url)
    # Delete connections and connection requests that reference this node, then the node
    db.query(Connection).filter(
        (Connection.node_a_id == id) | (Connection.node_b_id == id)
    ).delete(synchronize_session=False)
    db.query(ConnectionRequest).filter(
        (ConnectionRequest.requester_id == id) | (ConnectionRequest.target_id == id)
    ).delete(synchronize_session=False)
    db.delete(node)
    log_event(db, LogEventType.NODE_REMOVED, f"Node removed: {name} (id={id})")
    db.commit()
    logger.info("delete_node: removed name=%s id=%s", name, id)
    return {"ok": True}
