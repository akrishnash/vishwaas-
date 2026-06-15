"""Tests for health/readiness/root endpoints (all public)."""


class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status_ok(self, client):
        resp = client.get("/health")
        assert resp.json()["status"] == "ok"

    def test_health_no_auth_needed(self, client):
        # Must be accessible without token — used by load balancers
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_timestamp(self, client):
        resp = client.get("/health")
        assert "ts" in resp.json()


class TestReady:
    def test_ready_returns_200_when_db_up(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200

    def test_ready_no_auth_needed(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200

    def test_ready_has_db_field(self, client):
        resp = client.get("/ready")
        assert resp.json()["db"] is True


class TestRoot:
    def test_root_returns_service_name(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "service" in resp.json()
