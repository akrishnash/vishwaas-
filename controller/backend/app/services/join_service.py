"""
Join flow: request -> approve/reject.
On approve: assign next free VPN IP, insert node, push config to agent.
Optional: when agent sent no public_key, controller generates keypair and pushes private_key to agent.
"""
import subprocess
from sqlalchemy.orm import Session

from app.persistence.models import Node, JoinRequest
from app.domain.enums import NodeStatus, JoinRequestStatus, NotificationType, LogEventType


def _generate_keypair() -> tuple[str, str] | None:
    """Generate WireGuard keypair via wg. Returns (private_key, public_key) or None."""
    try:
        priv = subprocess.run(
            ["wg", "genkey"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        priv_key = priv.stdout.strip()
        if not priv_key:
            return None
        pub = subprocess.run(
            ["wg", "pubkey"],
            input=priv_key,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        pub_key = pub.stdout.strip()
        return (priv_key, pub_key) if pub_key else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_next_vpn_ip(db: Session, network: str, start: int, end: int) -> str | None:
    """Return next free IP in range network.{start..end}."""
    used = {
        int(n.vpn_ip.rsplit(".", 1)[-1])
        for n in db.query(Node).filter(Node.vpn_ip.isnot(None)).all()
        if n.vpn_ip and n.vpn_ip.startswith(f"{network}.")
    }
    for i in range(start, end + 1):
        if i not in used:
            return f"{network}.{i}"
    return None


def approve_join(
    db: Session,
    join_request_id: int,
    network: str,
    start: int,
    end: int,
) -> Node | None:
    """
    1. Assign next free VPN IP
    2. Insert into nodes with status ACTIVE
    3. Update join request status
    4. Log event and create notification (caller adds log/notification records)
    """
    jr = db.query(JoinRequest).filter(JoinRequest.id == join_request_id).first()
    if not jr or jr.status != JoinRequestStatus.PENDING:
        return None

    vpn_ip = get_next_vpn_ip(db, network, start, end)
    if not vpn_ip:
        return None

    node = Node(
        name=jr.node_name,
        public_key=jr.public_key,
        agent_url=jr.agent_url,
        vpn_ip=vpn_ip,
        status=NodeStatus.APPROVED,
    )
    db.add(node)
    db.flush()

    jr.status = JoinRequestStatus.APPROVED
    return node


def approve_join_with_issued_key(
    db: Session,
    join_request_id: int,
    network: str,
    start: int,
    end: int,
) -> tuple[Node | None, str | None]:
    """
    Approve join: assign VPN IP, create node. If join request had no public_key,
    generate keypair and return (node, private_key) so caller can push to agent.
    Otherwise return (node, None).
    """
    jr = db.query(JoinRequest).filter(JoinRequest.id == join_request_id).first()
    if not jr or jr.status != JoinRequestStatus.PENDING:
        return None, None

    vpn_ip = get_next_vpn_ip(db, network, start, end)
    if not vpn_ip:
        return None, None

    issued_private_key: str | None = None
    if not (jr.public_key and jr.public_key.strip()):
        # Controller-issued keys: generate keypair for this node
        keypair = _generate_keypair()
        if not keypair:
            return None, None
        priv_key, pub_key = keypair
        issued_private_key = priv_key
        public_key = pub_key
    else:
        public_key = jr.public_key.strip()

    # Status starts as APPROVED; caller upgrades to ACTIVE after agent confirms receipt.
    node = Node(
        name=jr.node_name,
        public_key=public_key,
        agent_url=jr.agent_url,
        vpn_ip=vpn_ip,
        status=NodeStatus.APPROVED,
    )
    db.add(node)
    db.flush()
    jr.status = JoinRequestStatus.APPROVED
    return node, issued_private_key


def reject_join(db: Session, join_request_id: int) -> bool:
    """Mark join request as rejected."""
    jr = db.query(JoinRequest).filter(JoinRequest.id == join_request_id).first()
    if not jr or jr.status != JoinRequestStatus.PENDING:
        return False
    jr.status = JoinRequestStatus.REJECTED
    return True
