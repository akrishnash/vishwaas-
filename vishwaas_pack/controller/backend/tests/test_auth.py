"""Tests for authentication: login, logout, JWT revocation, protected route enforcement."""


class TestLogin:
    def test_dev_mode_accepts_any_credentials(self, client):
        resp = client.post("/auth/login", json={"username": "admin", "password": "anything"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_dev_mode_any_username(self, client):
        resp = client.post("/auth/login", json={"username": "whoever", "password": "x"})
        assert resp.status_code == 200

    def test_returns_three_segment_jwt(self, client):
        resp = client.post("/auth/login", json={"username": "admin", "password": "pw"})
        token = resp.json()["access_token"]
        assert token.count(".") == 2

    def test_wrong_credentials_rejected_when_hash_set(self, client, with_auth):
        resp = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_correct_credentials_accepted_when_hash_set(self, client, with_auth):
        resp = client.post("/auth/login", json={"username": "admin", "password": with_auth})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_wrong_username_rejected_when_hash_set(self, client, with_auth):
        resp = client.post("/auth/login", json={"username": "notadmin", "password": with_auth})
        assert resp.status_code == 401


class TestMe:
    def test_me_no_token_returns_401_when_auth_enforced(self, client, with_auth):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_returns_username_with_valid_token(self, client, auth_headers):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert "username" in resp.json()

    def test_me_bad_token_rejected_when_auth_enforced(self, client, with_auth):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
        assert resp.status_code == 401

    def test_me_dev_mode_no_token_returns_dev_user(self, client):
        # In dev mode (no password hash), require_auth bypasses — this is expected
        resp = client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "dev"


class TestLogout:
    def test_logout_succeeds(self, client, auth_headers):
        resp = client.post("/auth/logout", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_revoked_token_rejected_when_auth_enforced(self, client, with_auth):
        # Log in with the real password to get a real JWT
        login_resp = client.post("/auth/login", json={"username": "admin", "password": with_auth})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Logout revokes the JTI
        client.post("/auth/logout", headers=headers)

        # Same token must now be rejected
        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 401

    def test_logout_no_token_rejected_when_auth_enforced(self, client, with_auth):
        resp = client.post("/auth/logout")
        assert resp.status_code == 401


class TestProtectedRoutes:
    def test_nodes_list_requires_auth_when_enforced(self, client, with_auth):
        resp = client.get("/nodes")
        assert resp.status_code == 401

    def test_join_requests_list_requires_auth_when_enforced(self, client, with_auth):
        resp = client.get("/join-requests")
        assert resp.status_code == 401

    def test_approve_join_requires_auth_when_enforced(self, client, with_auth, pending_join):
        resp = client.post(f"/join-requests/{pending_join['id']}/approve")
        assert resp.status_code == 401

    def test_reject_join_requires_auth_when_enforced(self, client, with_auth, pending_join):
        resp = client.post(f"/join-requests/{pending_join['id']}/reject")
        assert resp.status_code == 401

    def test_authenticated_can_access_nodes(self, client, auth_headers):
        resp = client.get("/nodes", headers=auth_headers)
        assert resp.status_code == 200

    def test_authenticated_can_list_join_requests(self, client, auth_headers):
        resp = client.get("/join-requests", headers=auth_headers)
        assert resp.status_code == 200

    def test_request_join_is_public_even_when_auth_enforced(self, client, with_auth):
        """BUG-01 regression: /request-join must work without JWT even in production."""
        resp = client.post("/request-join", json={
            "node_name": "agent-node",
            "agent_url": "http://10.0.0.1:7070",
            "public_key": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=",
        })
        assert resp.status_code == 200, (
            "/request-join rejected without JWT — BUG-01 regression!"
        )
