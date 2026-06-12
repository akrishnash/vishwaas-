"""
Tests for the join flow:
  POST /request-join        — public (BUG-01 regression test)
  GET  /join-requests       — auth required
  POST /join-requests/{id}/approve
  POST /join-requests/{id}/reject
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import KEY_A, KEY_B, KEY_C


# ---------------------------------------------------------------------------
# /request-join — must be PUBLIC (agents have no JWT)
# ---------------------------------------------------------------------------

class TestRequestJoinPublicAccess:
    def test_no_auth_header_returns_200(self, client):
        """Regression for BUG-01: /request-join must not require a JWT."""
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 200, (
            "/request-join returned non-200 without auth — BUG-01 regression!"
        )

    def test_returns_pending_status(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.json()["status"] == "PENDING"

    def test_response_has_expected_fields(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        data = resp.json()
        assert all(k in data for k in ("id", "node_name", "agent_url", "status", "requested_at"))


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestRequestJoinValidation:
    def test_invalid_node_name_spaces(self, client):
        resp = client.post("/request-join", json={
            "node_name": "has space",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 422

    def test_invalid_node_name_special_chars(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node@bad!",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 422

    def test_invalid_node_name_empty(self, client):
        resp = client.post("/request-join", json={
            "node_name": "",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 422

    def test_node_name_allows_hyphens_and_dots(self, client):
        resp = client.post("/request-join", json={
            "node_name": "my-node.01",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 200

    def test_invalid_public_key_too_short(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": "tooshort=",
        })
        assert resp.status_code == 422

    def test_invalid_public_key_no_padding(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": "a" * 44,  # 44 chars but no trailing =
        })
        assert resp.status_code == 422

    def test_invalid_agent_url_no_scheme(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "192.168.10.16:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 422

    def test_invalid_agent_url_ftp_scheme(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "ftp://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 422

    def test_agent_url_https_accepted(self, client):
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "https://10.0.0.1:7070",
            "public_key": KEY_A,
        })
        assert resp.status_code == 200

    def test_empty_public_key_accepted(self, client):
        """Empty/omitted public_key is valid — controller will issue keys on approve."""
        resp = client.post("/request-join", json={
            "node_name": "node-1",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": "",
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Idempotency: same agent re-submitting creates one pending request
# ---------------------------------------------------------------------------

class TestRequestJoinIdempotency:
    def test_same_key_returns_same_request(self, client):
        body = {"node_name": "node-1", "agent_url": "http://10.0.0.1:7070", "public_key": KEY_A}
        r1 = client.post("/request-join", json=body)
        r2 = client.post("/request-join", json=body)
        assert r1.json()["id"] == r2.json()["id"]

    def test_same_url_and_name_returns_same_request(self, client):
        body = {"node_name": "node-1", "agent_url": "http://10.0.0.1:7070", "public_key": ""}
        r1 = client.post("/request-join", json=body)
        r2 = client.post("/request-join", json=body)
        assert r1.json()["id"] == r2.json()["id"]

    def test_different_key_creates_new_request(self, client):
        r1 = client.post("/request-join", json={
            "node_name": "node-1", "agent_url": "http://10.0.0.1:7070", "public_key": KEY_A,
        })
        r2 = client.post("/request-join", json={
            "node_name": "node-2", "agent_url": "http://10.0.0.2:7070", "public_key": KEY_B,
        })
        assert r1.json()["id"] != r2.json()["id"]


# ---------------------------------------------------------------------------
# Restart handling: re-join with known key tears down stale connections
# ---------------------------------------------------------------------------

class TestRequestJoinRestart:
    def test_restart_clears_stale_node(self, client, db_session, auth_headers):
        """If a node re-joins after being ACTIVE, old node is deleted and a fresh PENDING is created."""
        from app.persistence.models import Node, JoinRequest
        from app.domain.enums import NodeStatus, JoinRequestStatus

        # Manually insert an ACTIVE node with KEY_A
        node = Node(
            name="node-alpha",
            public_key=KEY_A,
            agent_url="http://10.0.0.1:7070",
            vpn_ip="10.10.10.2",
            status=NodeStatus.ACTIVE,
        )
        db_session.add(node)
        db_session.commit()

        # Agent restarts and posts a new join request with the same key
        # remove_peer is imported locally inside the handler, so patch at its source.
        with patch("app.services.agent_client.remove_peer", new_callable=AsyncMock) as mock_remove:
            resp = client.post("/request-join", json={
                "node_name": "node-alpha",
                "agent_url": "http://10.0.0.1:7070",
                "public_key": KEY_A,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PENDING"

        # The old node must be gone
        remaining = db_session.query(Node).filter(Node.public_key == KEY_A).all()
        assert len(remaining) == 0

        # A new PENDING join request must exist
        pending = db_session.query(JoinRequest).filter(
            JoinRequest.public_key == KEY_A,
            JoinRequest.status == JoinRequestStatus.PENDING,
        ).first()
        assert pending is not None


# ---------------------------------------------------------------------------
# List join requests
# ---------------------------------------------------------------------------

class TestListJoinRequests:
    def test_list_requires_auth(self, client, with_auth):
        resp = client.get("/join-requests")
        assert resp.status_code == 401

    def test_list_returns_array(self, client, auth_headers):
        resp = client.get("/join-requests", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_shows_submitted_request(self, client, auth_headers, pending_join):
        resp = client.get("/join-requests", headers=auth_headers)
        ids = [r["id"] for r in resp.json()]
        assert pending_join["id"] in ids

    def test_list_pagination(self, client, auth_headers):
        for i in range(3):
            client.post("/request-join", json={
                "node_name": f"node-{i}",
                "agent_url": f"http://10.0.0.{i+1}:7070",
                "public_key": [KEY_A, KEY_B, KEY_C][i],
            })
        resp = client.get("/join-requests?limit=2", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 2


# ---------------------------------------------------------------------------
# Approve join request
# ---------------------------------------------------------------------------

class TestApproveJoinRequest:
    def test_approve_creates_node(self, client, auth_headers, pending_join, db_session):
        from app.persistence.models import Node

        with patch("app.services.agent_client.set_vpn_address", new_callable=AsyncMock, return_value=True):
            resp = client.post(
                f"/join-requests/{pending_join['id']}/approve",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "vpn_ip" in data

        node = db_session.query(Node).filter(Node.name == "node-alpha").first()
        assert node is not None
        assert node.vpn_ip.startswith("10.10.10.")

    def test_approve_assigns_vpn_ip_from_pool(self, client, auth_headers, pending_join):
        with patch("app.services.agent_client.set_vpn_address", new_callable=AsyncMock, return_value=True):
            resp = client.post(
                f"/join-requests/{pending_join['id']}/approve",
                headers=auth_headers,
            )
        vpn_ip = resp.json()["vpn_ip"]
        parts = vpn_ip.split(".")
        assert len(parts) == 4
        assert 2 <= int(parts[3]) <= 254

    def test_approve_requires_auth(self, client, with_auth, pending_join):
        resp = client.post(f"/join-requests/{pending_join['id']}/approve")
        assert resp.status_code == 401

    def test_approve_nonexistent_request_returns_400(self, client, auth_headers):
        with patch("app.services.agent_client.set_vpn_address", new_callable=AsyncMock, return_value=True):
            resp = client.post("/join-requests/99999/approve", headers=auth_headers)
        assert resp.status_code == 400

    def test_approve_already_approved_returns_400(self, client, auth_headers, pending_join):
        with patch("app.services.agent_client.set_vpn_address", new_callable=AsyncMock, return_value=True):
            client.post(f"/join-requests/{pending_join['id']}/approve", headers=auth_headers)
            resp = client.post(f"/join-requests/{pending_join['id']}/approve", headers=auth_headers)
        assert resp.status_code == 400

    def test_approve_second_node_gets_next_ip(self, client, auth_headers, db_session):
        """Two nodes approved sequentially must get distinct sequential VPN IPs."""
        for key, name, url in [
            (KEY_A, "node-1", "http://10.0.0.1:7070"),
            (KEY_B, "node-2", "http://10.0.0.2:7070"),
        ]:
            r = client.post("/request-join", json={
                "node_name": name, "agent_url": url, "public_key": key,
            })
            jid = r.json()["id"]
            with patch("app.services.agent_client.set_vpn_address", new_callable=AsyncMock, return_value=True):
                client.post(f"/join-requests/{jid}/approve", headers=auth_headers)

        from app.persistence.models import Node
        nodes = db_session.query(Node).all()
        ips = [n.vpn_ip for n in nodes]
        assert len(set(ips)) == 2  # both IPs must be unique


# ---------------------------------------------------------------------------
# Reject join request
# ---------------------------------------------------------------------------

class TestRejectJoinRequest:
    def test_reject_succeeds(self, client, auth_headers, pending_join, db_session):
        from app.persistence.models import JoinRequest
        from app.domain.enums import JoinRequestStatus

        resp = client.post(
            f"/join-requests/{pending_join['id']}/reject",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        jr = db_session.query(JoinRequest).filter(JoinRequest.id == pending_join["id"]).first()
        assert jr.status == JoinRequestStatus.REJECTED

    def test_reject_requires_auth(self, client, with_auth, pending_join):
        resp = client.post(f"/join-requests/{pending_join['id']}/reject")
        assert resp.status_code == 401

    def test_reject_nonexistent_returns_400(self, client, auth_headers):
        resp = client.post("/join-requests/99999/reject", headers=auth_headers)
        assert resp.status_code == 400

    def test_cannot_reject_already_rejected(self, client, auth_headers, pending_join):
        client.post(f"/join-requests/{pending_join['id']}/reject", headers=auth_headers)
        resp = client.post(f"/join-requests/{pending_join['id']}/reject", headers=auth_headers)
        assert resp.status_code == 400
