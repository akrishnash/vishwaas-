"""
Tests for the connection lifecycle:
  - approve_connection: atomic add_peer on both agents; rollback if B fails
  - reject_connection
  - terminate_connection_and_teardown
  - Connection request endpoints (auth enforcement)
"""
import pytest
from unittest.mock import patch, AsyncMock, call

from app.persistence.models import Node, ConnectionRequest, Connection
from app.domain.enums import NodeStatus, ConnectionStatus, ConnectionRequestStatus
from app.services.connection_service import (
    approve_connection,
    reject_connection,
    terminate_connection,
    terminate_connection_and_teardown,
)
from tests.conftest import KEY_A, KEY_B


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_active_node(db, name, key, vpn_ip, url="http://10.0.0.1:7070"):
    node = Node(
        name=name,
        public_key=key,
        agent_url=url,
        vpn_ip=vpn_ip,
        status=NodeStatus.ACTIVE,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _make_connection_request(db, node_a, node_b):
    cr = ConnectionRequest(
        requester_id=node_a.id,
        target_id=node_b.id,
        status=ConnectionRequestStatus.PENDING,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


# ---------------------------------------------------------------------------
# approve_connection (service)
# ---------------------------------------------------------------------------

class TestApproveConnectionService:
    @pytest.mark.asyncio
    async def test_approve_creates_active_connection(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        cr = _make_connection_request(db_session, node_a, node_b)

        with patch("app.services.connection_service.add_peer", new_callable=AsyncMock, return_value=True), \
             patch("app.services.connection_service._endpoint_from_agent_url", return_value="10.0.0.1:51820"):
            conn = await approve_connection(db_session, cr.id)

        assert conn is not None
        assert conn.status == ConnectionStatus.ACTIVE
        assert conn.node_a_id == node_a.id
        assert conn.node_b_id == node_b.id

    @pytest.mark.asyncio
    async def test_approve_calls_both_agents(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        cr = _make_connection_request(db_session, node_a, node_b)

        with patch("app.services.connection_service.add_peer", new_callable=AsyncMock, return_value=True) as mock_add, \
             patch("app.services.connection_service._endpoint_from_agent_url", return_value="10.0.0.1:51820"):
            await approve_connection(db_session, cr.id)

        assert mock_add.call_count == 2

    @pytest.mark.asyncio
    async def test_approve_rolls_back_node_a_if_node_b_fails(self, db_session):
        """Atomic guarantee: if add_peer(B) fails, remove_peer(A) is called — no half-broken state."""
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        cr = _make_connection_request(db_session, node_a, node_b)

        # First call (node_a) succeeds, second call (node_b) fails
        add_side_effects = [True, False]

        with patch("app.services.connection_service.add_peer", new_callable=AsyncMock,
                   side_effect=add_side_effects) as mock_add, \
             patch("app.services.connection_service.remove_peer", new_callable=AsyncMock) as mock_remove, \
             patch("app.services.connection_service._endpoint_from_agent_url", return_value="10.0.0.1:51820"):
            conn = await approve_connection(db_session, cr.id)

        assert conn is None  # no connection record created
        mock_remove.assert_called_once()  # rollback: remove peer from node_a

    @pytest.mark.asyncio
    async def test_approve_no_connection_created_if_node_a_fails(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        cr = _make_connection_request(db_session, node_a, node_b)

        with patch("app.services.connection_service.add_peer", new_callable=AsyncMock, return_value=False), \
             patch("app.services.connection_service.remove_peer", new_callable=AsyncMock) as mock_remove, \
             patch("app.services.connection_service._endpoint_from_agent_url", return_value="10.0.0.1:51820"):
            conn = await approve_connection(db_session, cr.id)

        assert conn is None
        mock_remove.assert_not_called()  # node_a never got a peer so nothing to roll back

    @pytest.mark.asyncio
    async def test_approve_nonexistent_request_returns_none(self, db_session):
        with patch("app.services.connection_service.add_peer", new_callable=AsyncMock, return_value=True), \
             patch("app.services.connection_service._endpoint_from_agent_url", return_value="10.0.0.1:51820"):
            conn = await approve_connection(db_session, 99999)
        assert conn is None

    @pytest.mark.asyncio
    async def test_approve_marks_connection_request_approved(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        cr = _make_connection_request(db_session, node_a, node_b)

        with patch("app.services.connection_service.add_peer", new_callable=AsyncMock, return_value=True), \
             patch("app.services.connection_service._endpoint_from_agent_url", return_value="10.0.0.1:51820"):
            await approve_connection(db_session, cr.id)

        db_session.refresh(cr)
        assert cr.status == ConnectionRequestStatus.APPROVED


# ---------------------------------------------------------------------------
# reject_connection (service)
# ---------------------------------------------------------------------------

class TestRejectConnectionService:
    def test_reject_marks_request_rejected(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        cr = _make_connection_request(db_session, node_a, node_b)

        result = reject_connection(db_session, cr.id)
        db_session.commit()

        assert result is True
        db_session.refresh(cr)
        assert cr.status == ConnectionRequestStatus.REJECTED

    def test_reject_nonexistent_returns_false(self, db_session):
        assert reject_connection(db_session, 99999) is False

    def test_cannot_reject_already_rejected(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        cr = _make_connection_request(db_session, node_a, node_b)

        reject_connection(db_session, cr.id)
        db_session.commit()
        result = reject_connection(db_session, cr.id)
        assert result is False


# ---------------------------------------------------------------------------
# terminate_connection_and_teardown (service)
# ---------------------------------------------------------------------------

class TestTerminateConnectionService:
    @pytest.mark.asyncio
    async def test_terminate_marks_connection_terminated(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        conn = Connection(node_a_id=node_a.id, node_b_id=node_b.id, status=ConnectionStatus.ACTIVE)
        db_session.add(conn)
        db_session.commit()

        with patch("app.services.connection_service.remove_peer", new_callable=AsyncMock):
            result = await terminate_connection_and_teardown(db_session, conn.id)

        assert result is True
        db_session.refresh(conn)
        assert conn.status == ConnectionStatus.TERMINATED

    @pytest.mark.asyncio
    async def test_terminate_calls_remove_peer_on_both_agents(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        conn = Connection(node_a_id=node_a.id, node_b_id=node_b.id, status=ConnectionStatus.ACTIVE)
        db_session.add(conn)
        db_session.commit()

        with patch("app.services.connection_service.remove_peer", new_callable=AsyncMock) as mock_remove:
            await terminate_connection_and_teardown(db_session, conn.id)

        assert mock_remove.call_count == 2

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_returns_false(self, db_session):
        with patch("app.services.connection_service.remove_peer", new_callable=AsyncMock):
            result = await terminate_connection_and_teardown(db_session, 99999)
        assert result is False

    @pytest.mark.asyncio
    async def test_terminate_already_terminated_returns_false(self, db_session):
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        conn = Connection(node_a_id=node_a.id, node_b_id=node_b.id, status=ConnectionStatus.TERMINATED)
        db_session.add(conn)
        db_session.commit()

        with patch("app.services.connection_service.remove_peer", new_callable=AsyncMock):
            result = await terminate_connection_and_teardown(db_session, conn.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_nodes_keep_vpn_ip_after_termination(self, db_session):
        """WireGuard interface stays up — node retains its VPN IP after peer removal."""
        node_a = _make_active_node(db_session, "node-a", KEY_A, "10.10.10.2", "http://10.0.0.1:7070")
        node_b = _make_active_node(db_session, "node-b", KEY_B, "10.10.10.3", "http://10.0.0.2:7070")
        conn = Connection(node_a_id=node_a.id, node_b_id=node_b.id, status=ConnectionStatus.ACTIVE)
        db_session.add(conn)
        db_session.commit()

        with patch("app.services.connection_service.remove_peer", new_callable=AsyncMock):
            await terminate_connection_and_teardown(db_session, conn.id)

        db_session.refresh(node_a)
        db_session.refresh(node_b)
        assert node_a.vpn_ip == "10.10.10.2"  # VPN IP unchanged
        assert node_b.vpn_ip == "10.10.10.3"
        assert node_a.status == NodeStatus.ACTIVE  # still on VPN
        assert node_b.status == NodeStatus.ACTIVE
