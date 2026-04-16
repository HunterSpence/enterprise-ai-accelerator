"""
integrations/base.py — Core abstractions for enterprise integration layer.

Finding, IntegrationAdapter ABC, IntegrationResult, RoutingRule, FindingRouter.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Finding dataclass — mirrors ai_audit_trail emission shape
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}


@dataclass
class Finding:
    """A normalized security/compliance finding emitted by any scanner module."""

    title: str
    description: str
    severity: str  # critical | high | medium | low | info
    module: str    # e.g. "policy_guard", "cloud_iq", "ai_audit_trail"

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_id: str | None = None
    remediation: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        sev = self.severity.lower()
        if sev not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {VALID_SEVERITIES}, got {sev!r}")
        self.severity = sev

    @property
    def severity_label(self) -> str:
        return self.severity.upper()

    @property
    def priority_rank(self) -> int:
        """Lower = more urgent."""
        return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(
            self.severity, 99
        )


# ---------------------------------------------------------------------------
# Integration result
# ---------------------------------------------------------------------------


@dataclass
class IntegrationResult:
    ok: bool
    external_ref: str | None = None
    error: str | None = None
    adapter: str = ""

    @classmethod
    def success(cls, external_ref: str, adapter: str = "") -> IntegrationResult:
        return cls(ok=True, external_ref=external_ref, adapter=adapter)

    @classmethod
    def failure(cls, error: str, adapter: str = "") -> IntegrationResult:
        return cls(ok=False, error=error, adapter=adapter)

    @classmethod
    def dry(cls, label: str, adapter: str = "") -> IntegrationResult:
        return cls(ok=True, external_ref=f"dry-run:{label}", adapter=adapter)


# ---------------------------------------------------------------------------
# IntegrationAdapter ABC
# ---------------------------------------------------------------------------


class IntegrationAdapter(ABC):
    """Base class for all destination adapters."""

    name: str = "unknown"
    dry_run: bool = False

    @abstractmethod
    async def send(self, finding: Finding) -> IntegrationResult:
        """Dispatch finding to the destination. Must never raise — return failure result."""
        ...

    def _safe_wrap(self, coro):
        """Utility: adapters may call this to centralize exception swallowing."""
        return coro


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@dataclass
class RoutingRule:
    """
    Maps a set of severities (and optionally modules) to a list of adapter names.

    Example::

        RoutingRule(
            match_severity={"critical", "high"},
            match_module={"policy_guard", "cloud_iq"},
            adapters=["slack", "jira", "pagerduty"],
        )
    """

    match_severity: set[str]
    adapters: list[str]
    match_module: set[str] | None = None  # None = match all modules

    def matches(self, finding: Finding) -> bool:
        sev_match = finding.severity in self.match_severity
        mod_match = (
            self.match_module is None or finding.module in self.match_module
        )
        return sev_match and mod_match


class FindingRouter:
    """
    Fans a Finding out to all matching adapters concurrently.

    Usage::

        router = FindingRouter(rules=[...], adapters={"slack": SlackWebhookAdapter(...)})
        results = await router.dispatch(finding)
    """

    def __init__(
        self,
        rules: list[RoutingRule],
        adapters: dict[str, IntegrationAdapter],
    ) -> None:
        self.rules = rules
        self.adapters = adapters

    def _resolve_adapters(self, finding: Finding) -> list[IntegrationAdapter]:
        """Return de-duplicated list of adapters matched by any rule."""
        seen: set[str] = set()
        matched: list[IntegrationAdapter] = []
        for rule in self.rules:
            if rule.matches(finding):
                for name in rule.adapters:
                    if name not in seen and name in self.adapters:
                        seen.add(name)
                        matched.append(self.adapters[name])
                    elif name not in self.adapters:
                        logger.warning(
                            "RoutingRule references adapter %r which is not registered", name
                        )
        return matched

    async def dispatch(self, finding: Finding) -> list[IntegrationResult]:
        """
        Send finding to all matched adapters concurrently.
        Always returns a list (never raises).
        """
        targets = self._resolve_adapters(finding)
        if not targets:
            logger.debug("No adapters matched finding %s (severity=%s)", finding.id, finding.severity)
            return []

        tasks = [self._safe_send(adapter, finding) for adapter in targets]
        results: list[IntegrationResult] = await asyncio.gather(*tasks)
        return list(results)

    @staticmethod
    async def _safe_send(adapter: IntegrationAdapter, finding: Finding) -> IntegrationResult:
        try:
            result = await adapter.send(finding)
            result.adapter = adapter.name
            return result
        except Exception as exc:
            logger.exception("Adapter %r raised unexpectedly: %s", adapter.name, exc)
            return IntegrationResult.failure(str(exc), adapter=adapter.name)
