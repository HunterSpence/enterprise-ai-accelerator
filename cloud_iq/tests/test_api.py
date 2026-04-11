"""
FastAPI endpoint tests using httpx async client.

All tests run against the in-process FastAPI app — no server required.
Uses mock data only, no cloud credentials needed.
"""

from __future__ import annotations

import asyncio

import pytest
pytest_asyncio = pytest.importorskip("pytest_asyncio", reason="pytest-asyncio not installed")
pytest.importorskip("fastapi", reason="fastapi not compatible with installed pydantic version", exc_type=ImportError)
from httpx import AsyncClient, ASGITransport

from cloud_iq.api import app


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_has_required_fields(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "dependencies" in data
        assert data["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_health_status_is_valid(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        data = response.json()
        assert data["status"] in ("ok", "degraded", "unhealthy")


class TestScanEndpoints:
    @pytest.mark.asyncio
    async def test_trigger_scan_returns_202(self, client: AsyncClient) -> None:
        response = await client.post(
            "/scan",
            json={"provider": "aws", "dry_run": True},
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_trigger_scan_returns_job_id(self, client: AsyncClient) -> None:
        response = await client.post(
            "/scan",
            json={"provider": "aws", "dry_run": True},
        )
        data = response.json()
        assert "job_id" in data
        assert len(data["job_id"]) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_get_scan_returns_404_for_unknown(self, client: AsyncClient) -> None:
        response = await client.get("/scan/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_scan_returns_running_or_queued(self, client: AsyncClient) -> None:
        # Trigger a scan
        post_response = await client.post(
            "/scan",
            json={"provider": "aws", "dry_run": True},
        )
        job_id = post_response.json()["job_id"]

        # Immediately poll — should be queued or running
        get_response = await client.get(f"/scan/{job_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["status"] in ("queued", "running", "completed")
        assert data["job_id"] == job_id


class TestRecommendationsEndpoint:
    @pytest.mark.asyncio
    async def test_recommendations_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/recommendations")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_recommendations_has_items(self, client: AsyncClient) -> None:
        response = await client.get("/recommendations")
        data = response.json()
        assert "items" in data
        assert data["total"] >= 5
        assert len(data["items"]) > 0

    @pytest.mark.asyncio
    async def test_recommendations_pagination(self, client: AsyncClient) -> None:
        response = await client.get("/recommendations?page=1&page_size=2")
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    @pytest.mark.asyncio
    async def test_recommendations_severity_filter(self, client: AsyncClient) -> None:
        response = await client.get("/recommendations?severity=critical")
        data = response.json()
        for item in data["items"]:
            assert item["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_recommendations_have_required_fields(self, client: AsyncClient) -> None:
        response = await client.get("/recommendations")
        data = response.json()
        for item in data["items"]:
            assert "id" in item
            assert "monthly_waste_usd" in item
            assert item["monthly_waste_usd"] > 0
            assert "severity" in item
            assert item["severity"] in ("critical", "high", "medium", "low")


class TestNLQueryEndpoint:
    @pytest.mark.asyncio
    async def test_query_returns_200_in_demo_mode(self, client: AsyncClient) -> None:
        response = await client.post(
            "/query",
            json={"question": "Which resources are wasting the most money?"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_query_returns_session_id(self, client: AsyncClient) -> None:
        response = await client.post(
            "/query",
            json={"question": "What is the total monthly waste?"},
        )
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    @pytest.mark.asyncio
    async def test_query_short_question_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/query",
            json={"question": "hi"},
        )
        assert response.status_code == 422
