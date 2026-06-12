"""
Unit tests for service-layer functions.
These test pure DB logic with no HTTP layer — fast and deterministic.
"""
import pytest
from app.persistence.models import Node, JoinRequest
from app.domain.enums import NodeStatus, JoinRequestStatus
from app.services.join_service import (
    get_next_vpn_ip,
    approve_join,
    reject_join,
)

from tests.conftest import KEY_A, KEY_B, KEY_C


def _make_join_request(db, name="node-1", key=KEY_A, url="http://10.0.0.1:7070"):
    jr = JoinRequest(
        node_name=name,
        public_key=key,
        agent_url=url,
        status=JoinRequestStatus.PENDING,
    )
    db.add(jr)
    db.commit()
    db.refresh(jr)
    return jr


# ---------------------------------------------------------------------------
# get_next_vpn_ip
# ---------------------------------------------------------------------------

class TestGetNextVpnIp:
    def test_first_ip_is_pool_start(self, db_session):
        ip = get_next_vpn_ip(db_session, "10.10.10", start=2, end=254)
        assert ip == "10.10.10.2"

    def test_skips_already_used_ip(self, db_session):
        node = Node(
            name="existing",
            public_key=KEY_A,
            agent_url="http://10.0.0.1:7070",
            vpn_ip="10.10.10.2",
            status=NodeStatus.ACTIVE,
        )
        db_session.add(node)
        db_session.commit()

        ip = get_next_vpn_ip(db_session, "10.10.10", start=2, end=254)
        assert ip == "10.10.10.3"

    def test_returns_none_when_pool_exhausted(self, db_session):
        for i in range(2, 6):
            db_session.add(Node(
                name=f"node-{i}",
                public_key=f"{'a' * 42}{i}=",
                agent_url=f"http://10.0.0.{i}:7070",
                vpn_ip=f"10.10.10.{i}",
                status=NodeStatus.ACTIVE,
            ))
        db_session.commit()

        ip = get_next_vpn_ip(db_session, "10.10.10", start=2, end=5)
        assert ip is None

    def test_sequential_allocation(self, db_session):
        ips = []
        for i, key in enumerate([KEY_A, KEY_B, KEY_C]):
            ip = get_next_vpn_ip(db_session, "10.10.10", start=2, end=254)
            db_session.add(Node(
                name=f"node-{i}",
                public_key=key,
                agent_url=f"http://10.0.0.{i}:7070",
                vpn_ip=ip,
                status=NodeStatus.ACTIVE,
            ))
            db_session.commit()
            ips.append(ip)

        assert ips == ["10.10.10.2", "10.10.10.3", "10.10.10.4"]


# ---------------------------------------------------------------------------
# approve_join (service function)
# ---------------------------------------------------------------------------

class TestApproveJoinService:
    def test_creates_node_with_approved_status(self, db_session):
        jr = _make_join_request(db_session)
        node = approve_join(db_session, jr.id, "10.10.10", 2, 254)
        assert node is not None
        assert node.status == NodeStatus.APPROVED

    def test_assigns_vpn_ip(self, db_session):
        jr = _make_join_request(db_session)
        node = approve_join(db_session, jr.id, "10.10.10", 2, 254)
        assert node.vpn_ip == "10.10.10.2"

    def test_marks_join_request_approved(self, db_session):
        jr = _make_join_request(db_session)
        approve_join(db_session, jr.id, "10.10.10", 2, 254)
        db_session.flush()
        assert jr.status == JoinRequestStatus.APPROVED

    def test_returns_none_for_nonexistent_request(self, db_session):
        result = approve_join(db_session, 99999, "10.10.10", 2, 254)
        assert result is None

    def test_returns_none_for_already_approved_request(self, db_session):
        jr = _make_join_request(db_session)
        approve_join(db_session, jr.id, "10.10.10", 2, 254)
        db_session.commit()
        result = approve_join(db_session, jr.id, "10.10.10", 2, 254)
        assert result is None

    def test_node_inherits_join_request_fields(self, db_session):
        jr = _make_join_request(db_session, name="my-node", key=KEY_B, url="http://1.2.3.4:7070")
        node = approve_join(db_session, jr.id, "10.10.10", 2, 254)
        assert node.name == "my-node"
        assert node.public_key == KEY_B
        assert node.agent_url == "http://1.2.3.4:7070"


# ---------------------------------------------------------------------------
# reject_join (service function)
# ---------------------------------------------------------------------------

class TestRejectJoinService:
    def test_marks_request_rejected(self, db_session):
        jr = _make_join_request(db_session)
        result = reject_join(db_session, jr.id)
        db_session.commit()
        assert result is True
        db_session.refresh(jr)
        assert jr.status == JoinRequestStatus.REJECTED

    def test_returns_false_for_nonexistent(self, db_session):
        assert reject_join(db_session, 99999) is False

    def test_cannot_reject_already_approved(self, db_session):
        jr = _make_join_request(db_session)
        approve_join(db_session, jr.id, "10.10.10", 2, 254)
        db_session.commit()
        result = reject_join(db_session, jr.id)
        assert result is False

    def test_cannot_reject_twice(self, db_session):
        jr = _make_join_request(db_session)
        reject_join(db_session, jr.id)
        db_session.commit()
        result = reject_join(db_session, jr.id)
        assert result is False
