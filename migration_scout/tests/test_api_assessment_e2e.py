"""
Tests for migration_scout/api.py — request/model/implementation contract
(P0-09) and the shared auth gate (P0-01).

Runs entirely offline: no network/LLM calls. The AI-enrichment path is
disabled via ``use_ai_enrichment=False`` in the fixture portfolio, and
WorkloadAssessor also auto-disables AI when ANTHROPIC_API_KEY is unset —
both apply here, so this never reaches core.ai_client.

Not registered in pyproject's `testpaths` (migration_scout/tests isn't
listed there and this module doesn't own pyproject.toml) — run explicitly:
    pytest migration_scout/tests/test_api_assessment_e2e.py
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from migration_scout.api import _jobs, _progress_queues, _run_assessment, app
from migration_scout.models import AssessmentRequest


def _fixture_portfolio() -> dict:
    """A tiny, deterministic offline portfolio fixture."""
    return {
        "inventory": [
            {
                "id": "wl-1",
                "name": "Legacy CRM",
                "workload_type": "web_app",
                "language": "Java",
                "database_type": "postgresql",
                "age_years": 6,
                "team_size": 4,
                "business_criticality": "high",
            },
            {
                "id": "wl-2",
                "name": "Nightly Batch Reporting",
                "workload_type": "batch_job",
                "language": "Python",
                "age_years": 2,
                "team_size": 2,
                "business_criticality": "low",
            },
        ],
        "use_ai_enrichment": False,
        "project_name": "E2E Fixture Portfolio",
    }


@pytest.fixture(autouse=True)
def _clean_jobs():
    """Isolate the module-level job store between tests."""
    _jobs.clear()
    _progress_queues.clear()
    yield
    _jobs.clear()
    _progress_queues.clear()


# ---------------------------------------------------------------------------
# P0-09: request/model/implementation contract — drive the real assessment
# path directly (deterministic/offline) and assert a valid persisted result.
# ---------------------------------------------------------------------------

async def test_run_assessment_end_to_end_persists_valid_result():
    request = AssessmentRequest(**_fixture_portfolio())
    job_id = "test-job-e2e"
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "created_at": "2026-01-01T00:00:00Z",
        "workload_count": len(request.inventory),
        "project_name": request.project_name,
    }
    _progress_queues[job_id] = __import__("asyncio").Queue()

    await _run_assessment(job_id, request)

    job = _jobs[job_id]
    assert job["status"] == "completed", job.get("error")

    assessments = job["assessments"]
    assert len(assessments) == 2
    assert {a.workload.id for a in assessments} == {"wl-1", "wl-2"}

    dep_graph = job["dep_graph"]
    assert len(dep_graph.nodes) == 2

    wave_plan = job["wave_plan"]
    assert wave_plan.waves
    assert wave_plan.monte_carlo.p50_weeks >= 0

    tco = job["tco"]
    assert tco.annual_savings == tco.annual_savings  # not NaN
    assert tco.total_investment_usd >= 0


# ---------------------------------------------------------------------------
# P0-01: shared auth gate — business routes fail closed, /health stays open.
#
# NOTE: full HTTP-level behavior (GET /health -> 200, POST /assessments
# without a key -> 503, with EAA_DEV_MODE -> 202) cannot be asserted here.
# core/api_key_auth.py's `api_key_dependency()` imports `Request` *locally*
# inside the outer function while the module also has
# `from __future__ import annotations` — that combination makes every
# annotation a lazily-evaluated string, and FastAPI resolves them via
# `typing.get_type_hints(fn)` against `fn.__globals__` only (not the
# enclosing closure), so `Request` can't be found. FastAPI then fails to
# recognize `request: Request` as its special auto-injected type and treats
# it as a required query/body field instead — every request (including
# exempt paths like /health) 422s with "field required: query.request",
# regardless of EAA_API_KEY/EAA_DEV_MODE. Reproduced in isolation, not
# introduced by this change. core/api_key_auth.py is explicitly out of
# scope to edit (owned by a different fix track) — flagged in risk_notes.
# These tests instead verify the wiring api.py is responsible for: the gate
# is mounted, and /health matches the gate's own exemption contract.
# ---------------------------------------------------------------------------

def test_auth_gate_is_mounted_as_app_level_dependency():
    from core.api_key_auth import api_key_dependency

    qualnames = {
        d.dependency.__qualname__
        for d in app.router.dependencies
        if hasattr(d.dependency, "__qualname__")
    }
    assert api_key_dependency().__qualname__ in qualnames


def test_health_route_matches_gates_own_exempt_prefixes():
    from core.api_key_auth import _EXEMPT_PREFIXES

    assert any("/health".startswith(p) for p in _EXEMPT_PREFIXES)
    health_paths = {r.path for r in app.routes if getattr(r, "path", "") == "/health"}
    assert health_paths == {"/health"}


def test_assessments_route_fails_closed_without_auth_configured(monkeypatch):
    monkeypatch.delenv("EAA_API_KEY", raising=False)
    monkeypatch.delenv("EAA_DEV_MODE", raising=False)
    client = TestClient(app)
    resp = client.post("/assessments", json=_fixture_portfolio())
    assert resp.status_code == 503
