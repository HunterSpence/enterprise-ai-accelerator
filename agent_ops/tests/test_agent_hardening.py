"""
agent_ops/tests/test_agent_hardening.py
=======================================

Offline tests for the agent_ops hardening additions:
  - Retry: exponential backoff on transient errors; no retry on auth errors
  - Budget: abort with BudgetExceededError when token/cost cap is hit
  - Checkpoint + resume: JSON persisted after each stage; resume reads it back
  - HITL: approve path completes pipeline; deny path aborts with partial result
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from types import SimpleNamespace

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agent_ops.agents import AgentResult, AgentStatus
from agent_ops.orchestrator import (
    ApprovalRequest,
    Orchestrator,
    _agent_result_from_dict,
    _is_transient,
)

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def _make_agent_result(name: str, findings: int = 2) -> AgentResult:
    return AgentResult(
        agent_name=name,
        status=AgentStatus.DONE,
        findings=[f"finding-{i}" for i in range(findings)],
        tokens_input=100,
        tokens_output=50,
    )


def _make_failing_agent(exc: Exception) -> SimpleNamespace:
    """Stub agent that always raises."""
    async def run(payload):
        raise exc
    return SimpleNamespace(name="StubAgent", run=run)


def _make_transient_then_ok_agent(fail_count: int, result: AgentResult) -> SimpleNamespace:
    """Stub agent that raises a transient error `fail_count` times then succeeds."""
    calls = {"n": 0}
    async def run(payload):
        calls["n"] += 1
        if calls["n"] <= fail_count:
            raise RuntimeError("rate_limit exceeded, retry after 1s")
        return result
    return SimpleNamespace(name="StubAgent", run=run, _calls=calls)


def _make_always_ok_agent(result: AgentResult) -> SimpleNamespace:
    async def run(payload):
        return result
    return SimpleNamespace(name="StubAgent", run=run)


def _null_tracer():
    """Minimal no-op tracer duck-type so Orchestrator doesn't crash in tests."""
    span = SimpleNamespace(
        set_attribute=lambda *a, **kw: None,
        finish=lambda: None,
    )
    t = SimpleNamespace(
        start_span=lambda *a, **kw: span,
        trace_agent=lambda *a, **kw: span,
        record_agent_result=lambda *a, **kw: None,
        record_pipeline_result=lambda *a, **kw: None,
        finish_span=lambda *a, **kw: None,
    )
    return t


def _null_ai_client(plan_summary: str = "Test plan") -> SimpleNamespace:
    """Minimal AI client that returns a coordinator plan without hitting the API."""
    async def structured(**kwargs):
        return SimpleNamespace(
            data={"plan_summary": plan_summary, "decomposition": []},
            raw_text="",
            input_tokens=50,
            output_tokens=30,
        )
    raw = SimpleNamespace()
    client = SimpleNamespace(structured=structured, raw=raw)
    return client


# ---------------------------------------------------------------------------
# Unit tests: _is_transient helper
# ---------------------------------------------------------------------------

class TestIsTransient:
    def test_rate_limit_is_transient(self):
        assert _is_transient(RuntimeError("rate_limit exceeded"))

    def test_503_is_transient(self):
        assert _is_transient(RuntimeError("503 Service Unavailable"))

    def test_timeout_is_transient(self):
        assert _is_transient(RuntimeError("connection timeout"))

    def test_overloaded_is_transient(self):
        assert _is_transient(RuntimeError("API overloaded"))

    def test_401_not_transient(self):
        assert not _is_transient(RuntimeError("401 authentication failed"))

    def test_403_not_transient(self):
        assert not _is_transient(RuntimeError("403 forbidden"))

    def test_invalid_api_key_not_transient(self):
        assert not _is_transient(RuntimeError("invalid_api_key provided"))


# ---------------------------------------------------------------------------
# Unit tests: _run_agent retry logic
# ---------------------------------------------------------------------------

class TestRunAgentRetry:
    def test_succeeds_on_first_attempt(self):
        result = _make_agent_result("A")
        agent = _make_always_ok_agent(result)

        async def _run():
            return await Orchestrator._run_agent(agent, {})

        r = asyncio.run(_run())
        assert r.status == AgentStatus.DONE

    def test_retries_on_transient_then_succeeds(self):
        result = _make_agent_result("A")
        agent = _make_transient_then_ok_agent(fail_count=2, result=result)

        # Patch asyncio.sleep so the test doesn't actually wait
        original_sleep = asyncio.sleep
        sleep_calls = []

        async def fast_sleep(delay):
            sleep_calls.append(delay)

        asyncio.sleep = fast_sleep
        try:
            async def _run():
                return await Orchestrator._run_agent(agent, {})
            r = asyncio.run(_run())
        finally:
            asyncio.sleep = original_sleep

        assert r.status == AgentStatus.DONE
        assert len(sleep_calls) == 2  # slept twice before success on 3rd call

    def test_no_retry_on_auth_error(self):
        calls = {"n": 0}

        async def run(payload):
            calls["n"] += 1
            raise RuntimeError("401 authentication failed")

        agent = SimpleNamespace(name="AuthFailAgent", run=run)

        async def _run():
            return await Orchestrator._run_agent(agent, {})

        r = asyncio.run(_run())
        assert r.status == AgentStatus.FAILED
        assert calls["n"] == 1  # no retry

    def test_exhausts_all_attempts_on_transient(self):
        calls = {"n": 0}

        async def run(payload):
            calls["n"] += 1
            raise RuntimeError("503 service unavailable")

        agent = SimpleNamespace(name="PersistentFailAgent", run=run)

        original_sleep = asyncio.sleep

        async def fast_sleep(d):
            pass

        asyncio.sleep = fast_sleep
        try:
            async def _run():
                return await Orchestrator._run_agent(agent, {})
            r = asyncio.run(_run())
        finally:
            asyncio.sleep = original_sleep

        assert r.status == AgentStatus.FAILED
        assert calls["n"] == 4  # 1 initial + 3 retries


# ---------------------------------------------------------------------------
# Unit tests: BudgetGuard integration via Orchestrator
# ---------------------------------------------------------------------------

class TestBudgetAbort:
    def _make_orchestrator(self, tmp_path=None):
        """Return an Orchestrator wired to null stubs — no real API calls."""
        orch = object.__new__(Orchestrator)
        orch._on_activity = lambda _: None
        orch._tracer = _null_tracer()

        async def auto_approve(req):
            return True

        orch._approval_handler = auto_approve

        async def _fake_coordinator_plan(task, config, task_budget_tokens=None):
            return ("stub plan", [])

        orch._coordinator_plan = _fake_coordinator_plan

        ok = _make_agent_result("X")
        orch._arch_agent = _make_always_ok_agent(ok)
        orch._mig_agent = _make_always_ok_agent(ok)
        orch._comp_agent = _make_always_ok_agent(ok)
        orch._report_agent = _make_always_ok_agent(_make_agent_result("R"))

        return orch

    def test_token_budget_causes_partial_status(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)
        orch = self._make_orchestrator()

        async def _run():
            return await orch.run_pipeline(
                "test task",
                {},
                max_tokens_budget=1,   # impossibly tight — triggers before workers
            )

        result = asyncio.run(_run())
        # Should abort cleanly with partial status (not crash)
        assert result.status in ("partial", "failed")

    def test_result_has_run_id_on_budget_abort(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)
        orch = self._make_orchestrator()

        async def _run():
            return await orch.run_pipeline(
                "test task",
                {},
                max_tokens_budget=1,
            )

        result = asyncio.run(_run())
        assert result.run_id  # non-empty


# ---------------------------------------------------------------------------
# Unit tests: checkpoint + resume
# ---------------------------------------------------------------------------

class TestCheckpointAndResume:
    def test_checkpoint_written_after_coordination(self, tmp_path, monkeypatch):
        # Redirect checkpoint dir to tmp_path for isolation
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        run_id = str(uuid.uuid4())
        orch_mod._write_checkpoint(run_id, "coordination", {"coordinator_plan": "test plan"})

        cp_file = tmp_path / f"{run_id}.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text())
        assert data["stage"] == "coordination"
        assert data["run_id"] == run_id

    def test_checkpoint_written_after_workers(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        run_id = str(uuid.uuid4())
        orch_mod._write_checkpoint(
            run_id,
            "workers",
            {"ArchitectureAgent": {"agent_name": "ArchitectureAgent", "status": "done"}},
        )

        data = json.loads((tmp_path / f"{run_id}.json").read_text())
        assert data["stage"] == "workers"

    def test_resume_reads_checkpoint(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        run_id = str(uuid.uuid4())
        orch_mod._write_checkpoint(run_id, "workers", {"plan": "xyz"})

        # Build a minimal orchestrator to call resume
        orch = object.__new__(Orchestrator)

        async def _run():
            return await orch.resume(run_id)

        result = asyncio.run(_run())
        assert result["stage"] == "workers"
        assert result["run_id"] == run_id

    def test_resume_raises_for_missing_run_id(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        orch = object.__new__(Orchestrator)

        async def _run():
            return await orch.resume("nonexistent-id")

        try:
            asyncio.run(_run())
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass

    def test_checkpoint_path_rejects_traversal_run_id(self, tmp_path, monkeypatch):
        """OMISSION: run_id is caller-supplied (run_pipeline/resume) and must
        not be able to escape _CHECKPOINT_DIR via '../' or an absolute path."""
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        for bad_run_id in ("../evil", "../../etc/passwd", "/etc/passwd", "a/b", "a\\b", ".."):
            try:
                path = orch_mod._checkpoint_path(bad_run_id)
            except ValueError:
                continue  # rejected outright — acceptable
            # If not rejected outright, it must still resolve inside the checkpoint dir.
            assert tmp_path.resolve() in path.resolve().parents or path.resolve() == tmp_path.resolve()

    def test_resume_rejects_traversal_run_id(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        orch = object.__new__(Orchestrator)

        async def _run():
            return await orch.resume("../evil")

        try:
            asyncio.run(_run())
            assert False, "Should have raised (ValueError or FileNotFoundError)"
        except (ValueError, FileNotFoundError):
            pass

    def test_run_pipeline_rejects_traversal_run_id(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        orch = TestBudgetAbort()._make_orchestrator()

        async def _run():
            return await orch.run_pipeline("task", {}, run_id="../evil")

        try:
            asyncio.run(_run())
            assert False, "Should have raised ValueError for unsafe run_id"
        except ValueError:
            pass

    def test_agent_result_from_dict_roundtrip(self):
        d = {
            "agent_name": "TestAgent",
            "status": "done",
            "findings": ["f1", "f2"],
            "tokens_input": 100,
            "tokens_output": 50,
        }
        r = _agent_result_from_dict(d)
        assert r.agent_name == "TestAgent"
        assert r.status == AgentStatus.DONE
        assert len(r.findings) == 2


# ---------------------------------------------------------------------------
# Unit tests: HITL approve / deny
# ---------------------------------------------------------------------------

class TestHITL:
    def _minimal_orchestrator(self, approval_handler=None):
        orch = object.__new__(Orchestrator)
        orch._on_activity = lambda _: None
        orch._tracer = _null_tracer()

        async def auto_approve(req):
            return True

        orch._approval_handler = approval_handler or auto_approve

        async def _fake_coordinator_plan(task, config, task_budget_tokens=None):
            return ("stub plan", [])

        orch._coordinator_plan = _fake_coordinator_plan

        ok = _make_agent_result("X")
        orch._arch_agent = _make_always_ok_agent(ok)
        orch._mig_agent = _make_always_ok_agent(ok)
        orch._comp_agent = _make_always_ok_agent(ok)
        orch._report_agent = _make_always_ok_agent(_make_agent_result("R"))
        return orch

    def test_auto_approve_pipeline_completes(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        orch = self._minimal_orchestrator()

        async def _run():
            return await orch.run_pipeline("task", {}, run_id="test-approve")

        result = asyncio.run(_run())
        assert result.status in ("success", "partial")

    def test_deny_at_workers_stage_returns_failed(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        async def deny_handler(req: ApprovalRequest) -> bool:
            if req.stage == "workers":
                return False
            return True

        orch = self._minimal_orchestrator(approval_handler=deny_handler)

        async def _run():
            return await orch.run_pipeline("task", {}, run_id="test-deny-workers")

        result = asyncio.run(_run())
        assert result.status == "failed"

    def test_deny_at_report_stage_returns_partial(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        async def deny_report(req: ApprovalRequest) -> bool:
            if req.stage == "report":
                return False
            return True

        orch = self._minimal_orchestrator(approval_handler=deny_report)

        async def _run():
            return await orch.run_pipeline("task", {}, run_id="test-deny-report")

        result = asyncio.run(_run())
        assert result.status == "partial"

    def test_hitl_audit_populated(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        orch = self._minimal_orchestrator()

        async def _run():
            return await orch.run_pipeline("task", {}, run_id="test-audit")

        result = asyncio.run(_run())
        assert len(result.hitl_audit) >= 2  # workers + report gates
        for entry in result.hitl_audit:
            assert "stage" in entry
            assert "approved" in entry
            assert "auto" in entry

    def test_custom_approval_handler_not_marked_auto(self, tmp_path, monkeypatch):
        import agent_ops.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_CHECKPOINT_DIR", tmp_path)

        approved_stages = []

        async def custom_handler(req: ApprovalRequest) -> bool:
            approved_stages.append(req.stage)
            return True

        orch = self._minimal_orchestrator(approval_handler=custom_handler)

        async def _run():
            return await orch.run_pipeline("task", {}, run_id="test-custom-hitl")

        result = asyncio.run(_run())
        # Custom handler is not _default_approval_handler so auto=False
        for entry in result.hitl_audit:
            assert entry["auto"] is False
        assert "workers" in approved_stages
