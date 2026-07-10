"""
PolicyGuard V2 — FastAPI endpoint tests
Uses httpx.AsyncClient against the ASGI app directly (no server needed).
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi.testclient import TestClient
    from httpx import AsyncClient, ASGITransport
    from api import app
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


@pytest.fixture(autouse=True)
def _dev_mode_auth(monkeypatch):
    # P0-01: business routes are fail-closed (503) unless EAA_API_KEY or
    # EAA_DEV_MODE is set — these tests exercise the routes directly, not
    # the auth gate, so run them in dev mode.
    monkeypatch.setenv("EAA_DEV_MODE", "true")
    monkeypatch.delenv("EAA_API_KEY", raising=False)


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestAuthGate:
    """P0-01: business routes must be fail-closed without EAA_API_KEY/EAA_DEV_MODE."""

    def test_unconfigured_business_route_returns_503(self, monkeypatch):
        monkeypatch.delenv("EAA_DEV_MODE", raising=False)
        monkeypatch.delenv("EAA_API_KEY", raising=False)
        client = TestClient(app)
        resp = client.get("/dashboard/summary")
        assert resp.status_code == 503

    def test_health_stays_open_without_auth(self, monkeypatch):
        monkeypatch.delenv("EAA_DEV_MODE", raising=False)
        monkeypatch.delenv("EAA_API_KEY", raising=False)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_configured_key_required_when_not_dev_mode(self, monkeypatch):
        monkeypatch.delenv("EAA_DEV_MODE", raising=False)
        monkeypatch.setenv("EAA_API_KEY", "test-secret")
        client = TestClient(app)
        assert client.get("/dashboard/summary").status_code == 401
        assert client.get(
            "/dashboard/summary", headers={"X-API-Key": "test-secret"}
        ).status_code == 200


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestHealthEndpoint:
    def test_health_returns_200(self):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestScanEndpoints:
    def test_post_scan_returns_202(self):
        client = TestClient(app)
        payload = {
            "system_name": "TestAI",
            "frameworks": ["eu_ai_act", "nist_ai_rmf"],
        }
        resp = client.post("/scans", json=payload)
        assert resp.status_code == 202
        data = resp.json()
        assert "scan_id" in data
        assert data["status"] == "pending"

    def test_get_scan_status(self):
        client = TestClient(app)
        # Create a scan first
        create_resp = client.post("/scans", json={
            "system_name": "TestAI",
            "frameworks": ["eu_ai_act"],
        })
        scan_id = create_resp.json()["scan_id"]

        # Fetch status
        status_resp = client.get(f"/scans/{scan_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["scan_id"] == scan_id
        assert "status" in data

    def test_get_nonexistent_scan_returns_404(self):
        client = TestClient(app)
        resp = client.get("/scans/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestAISystemEndpoints:
    def test_register_ai_system(self):
        client = TestClient(app)
        payload = {
            "name": "HiringAI-Test",
            "use_domain": "hiring",
            "description": "Hiring recommendation system",
        }
        resp = client.post("/ai-systems/register", json=payload)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "system_id" in data

    def test_risk_tier_endpoint(self):
        client = TestClient(app)
        # Register first
        reg_resp = client.post("/ai-systems/register", json={
            "name": "HiringAI-Tier-Test",
            "use_domain": "general",
            "description": "Tier test system",
        })
        system_id = reg_resp.json()["system_id"]

        # Get risk tier
        tier_resp = client.get(f"/ai-systems/{system_id}/risk-tier")
        assert tier_resp.status_code == 200
        data = tier_resp.json()
        assert "risk_tier" in data
        assert data["risk_tier"] in (
            "Unacceptable", "High-Risk", "Limited Risk", "Minimal Risk",
            "GPAI (General Purpose AI)", "unknown",
        )


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestDashboardEndpoint:
    def test_dashboard_summary(self):
        client = TestClient(app)
        resp = client.get("/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_compliance_score" in data
        assert "days_to_high_risk_deadline" in data
