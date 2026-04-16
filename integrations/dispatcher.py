"""
integrations/dispatcher.py — WebhookDispatcher with retry, circuit breaker, rate limiting.

Wraps FindingRouter with production-grade reliability:
  - Exponential backoff retry (max 3 attempts, base 1s, cap 30s)
  - Per-adapter circuit breaker (open after 5 consecutive failures, reset after 60s)
  - Token bucket rate limiting (per-adapter, configurable rps)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from integrations.base import Finding, FindingRouter, IntegrationAdapter, IntegrationResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry config
# ---------------------------------------------------------------------------

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY = 1.0    # seconds
_DEFAULT_MAX_DELAY = 30.0    # seconds
_DEFAULT_BACKOFF = 2.0       # multiplier


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    open_until: float = 0.0   # epoch timestamp; 0 = closed

    def is_open(self) -> bool:
        if self.open_until == 0.0:
            return False
        if time.monotonic() > self.open_until:
            # Reset: half-open → allow next attempt
            self.open_until = 0.0
            self.consecutive_failures = 0
            return False
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.open_until = 0.0

    def record_failure(self, threshold: int, reset_after: float) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= threshold:
            self.open_until = time.monotonic() + reset_after
            logger.warning(
                "Circuit breaker OPEN for %ds after %d consecutive failures",
                int(reset_after), self.consecutive_failures,
            )


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------

@dataclass
class _TokenBucket:
    rps: float           # tokens per second
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = self.rps
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.rps, self._tokens + elapsed * self.rps)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            wait = (1.0 - self._tokens) / self.rps
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# WebhookDispatcher
# ---------------------------------------------------------------------------


class WebhookDispatcher:
    """
    Production wrapper around FindingRouter.

    Features:
    - Retries each adapter send with exponential backoff (transient failures only)
    - Per-adapter circuit breaker prevents hammering a dead endpoint
    - Per-adapter token bucket limits outbound rate

    Args:
        router:             Configured FindingRouter.
        max_retries:        Max send attempts per adapter per finding.
        base_delay:         Initial retry delay (seconds).
        max_delay:          Retry delay cap (seconds).
        backoff_factor:     Exponential backoff multiplier.
        cb_failure_threshold: Consecutive failures before circuit opens.
        cb_reset_after:     Seconds the circuit stays open.
        default_rps:        Token bucket rate per adapter (requests/second).
    """

    def __init__(
        self,
        router: FindingRouter,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        base_delay: float = _DEFAULT_BASE_DELAY,
        max_delay: float = _DEFAULT_MAX_DELAY,
        backoff_factor: float = _DEFAULT_BACKOFF,
        cb_failure_threshold: int = 5,
        cb_reset_after: float = 60.0,
        default_rps: float = 2.0,
    ) -> None:
        self.router = router
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.cb_failure_threshold = cb_failure_threshold
        self.cb_reset_after = cb_reset_after
        self.default_rps = default_rps

        # Per-adapter state (keyed by adapter.name)
        self._circuits: dict[str, _CircuitState] = {}
        self._buckets: dict[str, _TokenBucket] = {}

    def _get_circuit(self, name: str) -> _CircuitState:
        if name not in self._circuits:
            self._circuits[name] = _CircuitState()
        return self._circuits[name]

    def _get_bucket(self, name: str) -> _TokenBucket:
        if name not in self._buckets:
            self._buckets[name] = _TokenBucket(rps=self.default_rps)
        return self._buckets[name]

    async def _send_with_retry(
        self, adapter: IntegrationAdapter, finding: Finding
    ) -> IntegrationResult:
        name = adapter.name
        circuit = self._get_circuit(name)
        bucket = self._get_bucket(name)

        if circuit.is_open():
            msg = f"Circuit breaker open for adapter {name!r} — skipping"
            logger.warning("WebhookDispatcher: %s", msg)
            return IntegrationResult.failure(msg, adapter=name)

        await bucket.acquire()

        delay = self.base_delay
        last_error: str = "unknown"

        for attempt in range(1, self.max_retries + 1):
            try:
                result = await adapter.send(finding)
            except Exception as exc:
                result = IntegrationResult.failure(str(exc), adapter=name)

            if result.ok:
                circuit.record_success()
                if attempt > 1:
                    logger.info(
                        "WebhookDispatcher: %s succeeded on attempt %d", name, attempt
                    )
                return result

            last_error = result.error or "unknown error"
            circuit.record_failure(self.cb_failure_threshold, self.cb_reset_after)

            if attempt < self.max_retries:
                logger.warning(
                    "WebhookDispatcher: %s attempt %d/%d failed: %s — retrying in %.1fs",
                    name, attempt, self.max_retries, last_error, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * self.backoff_factor, self.max_delay)

        logger.error(
            "WebhookDispatcher: %s exhausted %d retries. Last error: %s",
            name, self.max_retries, last_error,
        )
        return IntegrationResult.failure(
            f"Exhausted {self.max_retries} retries: {last_error}", adapter=name
        )

    async def dispatch(self, finding: Finding) -> list[IntegrationResult]:
        """
        Dispatch a finding to all matched adapters with retry/CB/rate-limit.
        Never raises. Always returns list of results.

        Usage in orchestrator::

            dispatcher = WebhookDispatcher(router=router)
            results = await dispatcher.dispatch(finding)
        """
        targets = self.router._resolve_adapters(finding)
        if not targets:
            return []

        tasks = [self._send_with_retry(adapter, finding) for adapter in targets]
        results: list[IntegrationResult] = await asyncio.gather(*tasks)
        return list(results)
