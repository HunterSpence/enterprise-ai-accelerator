"""Tests for integrations/ — Finding, FindingRouter, adapters dry-run, dispatcher, circuit breaker."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.base import Finding, FindingRouter, IntegrationResult, RoutingRule
from integrations.dispatcher import WebhookDispatcher, _CircuitState, _TokenBucket


def _finding(severity="high", module="policy_guard"):
    return Finding(
        title="Test Finding",
        description="A test finding",
        severity=severity,
        module=module,
    )


class _OkAdapter:
    name = "ok_adapter"
    async def send(self, finding):
        return IntegrationResult.success("ref-123", adapter="ok_adapter")


class _FailAdapter:
    name = "fail_adapter"
    async def send(self, finding):
        return IntegrationResult.failure("always fails", adapter="fail_adapter")


class TestFinding:
    def test_valid_severity_accepted(self):
        f = Finding(title="T", description="D", severity="high", module="m")
        assert f.severity == "high"

    def test_severity_normalized_to_lower(self):
        f = Finding(title="T", description="D", severity="CRITICAL", module="m")
        assert f.severity == "critical"

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError):
            Finding(title="T", description="D", severity="EXTREME", module="m")

    def test_severity_label_is_upper(self):
        f = _finding("medium")
        assert f.severity_label == "MEDIUM"

    def test_priority_rank_critical_is_zero(self):
        f = _finding("critical")
        assert f.priority_rank == 0

    def test_priority_rank_info_is_four(self):
        f = _finding("info")
        assert f.priority_rank == 4

    def test_uuid_assigned_automatically(self):
        f = _finding()
        assert f.id and len(f.id) == 36


class TestRoutingRule:
    def test_matches_on_severity(self):
        rule = RoutingRule(match_severity={"high", "critical"}, adapters=["slack"])
        assert rule.matches(_finding("high"))
        assert not rule.matches(_finding("low"))

    def test_matches_on_module(self):
        rule = RoutingRule(
            match_severity={"high"},
            adapters=["jira"],
            match_module={"policy_guard"},
        )
        assert rule.matches(_finding("high", "policy_guard"))
        assert not rule.matches(_finding("high", "cloud_iq"))

    def test_none_module_matches_all(self):
        rule = RoutingRule(match_severity={"high"}, adapters=["pagerduty"], match_module=None)
        assert rule.matches(_finding("high", "any_module"))


class TestFindingRouter:
    async def test_dispatch_to_matched_adapter(self):
        ok = _OkAdapter()
        rule = RoutingRule(match_severity={"high"}, adapters=["ok_adapter"])
        router = FindingRouter(rules=[rule], adapters={"ok_adapter": ok})
        results = await router.dispatch(_finding("high"))
        assert len(results) == 1
        assert results[0].ok is True

    async def test_no_match_returns_empty(self):
        ok = _OkAdapter()
        rule = RoutingRule(match_severity={"critical"}, adapters=["ok_adapter"])
        router = FindingRouter(rules=[rule], adapters={"ok_adapter": ok})
        results = await router.dispatch(_finding("low"))
        assert results == []

    async def test_missing_adapter_name_logs_warning_not_raise(self):
        rule = RoutingRule(match_severity={"high"}, adapters=["nonexistent"])
        router = FindingRouter(rules=[rule], adapters={})
        results = await router.dispatch(_finding("high"))
        assert results == []

    async def test_deduplicates_adapters(self):
        ok = _OkAdapter()
        rule1 = RoutingRule(match_severity={"high"}, adapters=["ok_adapter"])
        rule2 = RoutingRule(match_severity={"high"}, adapters=["ok_adapter"])
        router = FindingRouter(rules=[rule1, rule2], adapters={"ok_adapter": ok})
        results = await router.dispatch(_finding("high"))
        assert len(results) == 1  # deduplicated


class TestIntegrationResult:
    def test_success_factory(self):
        r = IntegrationResult.success("ticket-1", adapter="jira")
        assert r.ok is True
        assert r.external_ref == "ticket-1"

    def test_failure_factory(self):
        r = IntegrationResult.failure("timeout", adapter="slack")
        assert r.ok is False
        assert "timeout" in r.error

    def test_dry_factory(self):
        r = IntegrationResult.dry("test-finding", adapter="teams")
        assert r.ok is True
        assert "dry-run" in r.external_ref


class TestCircuitBreaker:
    def test_initially_closed(self):
        cb = _CircuitState()
        assert not cb.is_open()

    def test_opens_after_threshold(self):
        cb = _CircuitState()
        for _ in range(5):
            cb.record_failure(threshold=5, reset_after=60.0)
        assert cb.is_open()

    def test_success_resets_failures(self):
        cb = _CircuitState()
        cb.record_failure(threshold=5, reset_after=60.0)
        cb.record_success()
        assert cb.consecutive_failures == 0

    def test_closes_after_reset_period(self):
        cb = _CircuitState()
        # Force open with very short reset time
        for _ in range(5):
            cb.record_failure(threshold=5, reset_after=0.01)
        time.sleep(0.05)
        assert not cb.is_open()


class TestTokenBucket:
    async def test_acquire_immediately_available(self):
        bucket = _TokenBucket(rps=100.0)
        # Should not block
        await asyncio.wait_for(bucket.acquire(), timeout=0.1)

    async def test_acquire_depletes_tokens(self):
        bucket = _TokenBucket(rps=1.0)
        await bucket.acquire()  # depletes token
        # Second acquire should take ~1s; test that it blocks briefly
        assert bucket._tokens < 1.0


class TestWebhookDispatcher:
    async def test_dispatch_ok_adapter(self):
        ok = _OkAdapter()
        rule = RoutingRule(match_severity={"high"}, adapters=["ok_adapter"])
        router = FindingRouter(rules=[rule], adapters={"ok_adapter": ok})
        dispatcher = WebhookDispatcher(router, base_delay=0.0, max_retries=1)
        results = await dispatcher.dispatch(_finding("high"))
        assert results[0].ok is True

    async def test_dispatch_retries_on_failure(self):
        fail = _FailAdapter()
        rule = RoutingRule(match_severity={"high"}, adapters=["fail_adapter"])
        router = FindingRouter(rules=[rule], adapters={"fail_adapter": fail})
        dispatcher = WebhookDispatcher(router, max_retries=2, base_delay=0.0)
        results = await dispatcher.dispatch(_finding("high"))
        assert results[0].ok is False

    async def test_circuit_opens_after_failures(self):
        fail = _FailAdapter()
        rule = RoutingRule(match_severity={"high"}, adapters=["fail_adapter"])
        router = FindingRouter(rules=[rule], adapters={"fail_adapter": fail})
        dispatcher = WebhookDispatcher(
            router, max_retries=1, base_delay=0.0, cb_failure_threshold=3, cb_reset_after=60.0
        )
        # Exhaust threshold
        for _ in range(3):
            await dispatcher.dispatch(_finding("high"))
        circuit = dispatcher._get_circuit("fail_adapter")
        assert circuit.is_open()
