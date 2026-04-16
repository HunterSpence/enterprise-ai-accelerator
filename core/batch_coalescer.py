"""
core/batch_coalescer.py
=======================

Auto-coalesces near-in-time structured calls into a single Anthropic Messages
Batch API submission for the 50% batch discount.

WIRING (one-liner):
    from core.batch_coalescer import BatchCoalescer, BatchableRequest
    coalescer = BatchCoalescer(ai=get_client())
    future = await coalescer.submit(BatchableRequest(
        custom_id="job-001", model=MODEL_HAIKU_4_5,
        system="Classify this text.", user="Cloud migration project.",
        schema={"type":"object","properties":{"label":{"type":"string"}}},
    ))
    result = await future  # blocks until the batch round-trip completes

Flush triggers:
    - Background task fires every ``flush_interval_s`` (default 60 s)
    - Immediately when queue reaches ``max_batch_size`` (default 1000)

Shutdown:
    await coalescer.aclose()   # flushes pending queue, awaits in-flight batches

Pricing: 50% off vs real-time API when using messages.batches.create.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BATCH_POLL_INTERVAL = 10.0   # seconds between batch status polls
_BATCH_POLL_TIMEOUT  = 3600.0 # max seconds to wait for a batch to complete


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BatchableRequest:
    """A single request that can be coalesced into a batch submission.

    Attributes
    ----------
    custom_id:
        Unique ID for this request within the batch.  If empty, a UUID4 is
        assigned automatically at submission time.
    model:
        Anthropic model ID (from core.models).
    system:
        System prompt text.
    user:
        User message text.
    schema:
        JSON Schema dict for structured output via tool use. If None, the
        batch request omits tools and expects a plain-text response.
    tool_name:
        Name of the forced tool (default "return_result").
    max_tokens:
        Max output tokens (default 1024).
    extra:
        Additional params forwarded verbatim to the batch params dict.
    """

    model: str
    system: str
    user: str
    custom_id: str = ""
    schema: Optional[dict[str, Any]] = None
    tool_name: str = "return_result"
    max_tokens: int = 1024
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchFuture:
    """Returned by ``BatchCoalescer.submit()``.

    Await it to get the result dict once the batch round-trip completes.
    """

    custom_id: str
    _future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())

    def __await__(self):
        return self._future.__await__()

    @property
    def done(self) -> bool:
        return self._future.done()

    def result(self) -> dict[str, Any]:
        return self._future.result()


# ---------------------------------------------------------------------------
# Internal: pending item
# ---------------------------------------------------------------------------

@dataclass
class _PendingItem:
    request: BatchableRequest
    future: BatchFuture


# ---------------------------------------------------------------------------
# BatchCoalescer
# ---------------------------------------------------------------------------

class BatchCoalescer:
    """Accumulates BatchableRequests and flushes them as Anthropic batch jobs.

    Parameters
    ----------
    ai:
        An ``AIClient`` instance (from core.ai_client).
    flush_interval_s:
        Seconds between automatic flushes (default 60).
    max_batch_size:
        Maximum items per batch before an immediate flush is triggered
        (Anthropic limit is 100,000 but 1000 is a practical sweet spot).
    """

    def __init__(
        self,
        ai: Any,  # AIClient — avoid circular import
        *,
        flush_interval_s: float = 60.0,
        max_batch_size: int = 1000,
    ) -> None:
        self._ai = ai
        self._flush_interval = flush_interval_s
        self._max_batch_size = max_batch_size

        self._queue: list[_PendingItem] = []
        self._queue_lock = asyncio.Lock()

        # Tracks in-flight batch IDs → list of futures that belong to them
        self._in_flight: dict[str, list[_PendingItem]] = {}
        self._in_flight_lock = asyncio.Lock()

        self._closed = False
        self._flush_task: Optional[asyncio.Task] = None
        self._stats = {"submitted": 0, "flushed_batches": 0, "errors": 0}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background flush loop. Call once after construction."""
        if self._flush_task is None:
            self._flush_task = asyncio.ensure_future(self._flush_loop())

    async def aclose(self) -> None:
        """Graceful shutdown: flush pending queue, await all in-flight batches."""
        self._closed = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._do_flush()

        # Wait for in-flight
        async with self._in_flight_lock:
            batch_ids = list(self._in_flight.keys())

        for bid in batch_ids:
            try:
                await self._poll_until_done(bid)
            except Exception as exc:
                logger.error("BatchCoalescer shutdown: error polling %s: %s", bid, exc)

    # ------------------------------------------------------------------
    # Public submit
    # ------------------------------------------------------------------

    async def submit(self, request: BatchableRequest) -> BatchFuture:
        """Enqueue a request. Returns a BatchFuture you can await.

        If the queue hits ``max_batch_size`` this call triggers an immediate
        flush before returning.
        """
        if self._closed:
            raise RuntimeError("BatchCoalescer is closed — cannot accept new requests.")

        if not request.custom_id:
            request.custom_id = str(uuid.uuid4())

        future = BatchFuture(custom_id=request.custom_id)
        item = _PendingItem(request=request, future=future)

        async with self._queue_lock:
            self._queue.append(item)
            queue_len = len(self._queue)

        # Ensure background loop is running
        if self._flush_task is None:
            self.start()

        if queue_len >= self._max_batch_size:
            asyncio.ensure_future(self._do_flush())

        return future

    # ------------------------------------------------------------------
    # Internal flush loop
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._flush_interval)
            await self._do_flush()

    async def _do_flush(self) -> None:
        """Drain current queue into one batch API call."""
        async with self._queue_lock:
            if not self._queue:
                return
            items, self._queue = self._queue, []

        batch_requests = [self._build_batch_params(item.request) for item in items]

        try:
            batch = await self._ai.raw.messages.batches.create(requests=batch_requests)
            batch_id = batch.id
            logger.info("BatchCoalescer: submitted batch %s (%d requests)", batch_id, len(items))
            self._stats["flushed_batches"] += 1
            self._stats["submitted"] += len(items)
        except Exception as exc:
            logger.error("BatchCoalescer: batch create failed: %s", exc)
            self._stats["errors"] += 1
            # Resolve all futures with the error
            for item in items:
                if not item.future._future.done():
                    item.future._future.set_exception(exc)
            return

        async with self._in_flight_lock:
            self._in_flight[batch_id] = items

        # Poll in background
        asyncio.ensure_future(self._poll_until_done(batch_id))

    async def _poll_until_done(self, batch_id: str) -> None:
        """Poll a batch until complete, then resolve all futures."""
        deadline = time.monotonic() + _BATCH_POLL_TIMEOUT

        while time.monotonic() < deadline:
            try:
                batch = await self._ai.raw.messages.batches.retrieve(batch_id)
            except Exception as exc:
                logger.error("BatchCoalescer: retrieve %s failed: %s", batch_id, exc)
                await asyncio.sleep(_BATCH_POLL_INTERVAL)
                continue

            status = getattr(batch, "processing_status", None) or batch.get("processing_status", "")
            if status == "ended":
                await self._collect_results(batch_id)
                return

            await asyncio.sleep(_BATCH_POLL_INTERVAL)

        # Timeout — resolve all remaining futures with a timeout error
        await self._fail_batch(batch_id, TimeoutError(f"Batch {batch_id} did not complete within {_BATCH_POLL_TIMEOUT}s"))

    async def _collect_results(self, batch_id: str) -> None:
        """Stream batch results and resolve per-request futures."""
        async with self._in_flight_lock:
            items = self._in_flight.pop(batch_id, [])

        id_map = {item.request.custom_id: item for item in items}

        try:
            async for result in await self._ai.raw.messages.batches.results(batch_id):
                custom_id = getattr(result, "custom_id", None)
                item = id_map.get(custom_id)
                if item is None:
                    continue

                result_type = getattr(result, "result", None)
                if result_type is None:
                    payload = {}
                elif hasattr(result_type, "type") and result_type.type == "succeeded":
                    msg = result_type.message
                    # Extract tool use if present, otherwise plain text
                    payload = _extract_batch_result(msg)
                else:
                    err = getattr(result_type, "error", {})
                    payload = {"error": str(err)}

                if not item.future._future.done():
                    item.future._future.set_result(payload)

        except Exception as exc:
            logger.error("BatchCoalescer: collect results for %s failed: %s", batch_id, exc)
            for item in id_map.values():
                if not item.future._future.done():
                    item.future._future.set_exception(exc)

    async def _fail_batch(self, batch_id: str, exc: Exception) -> None:
        async with self._in_flight_lock:
            items = self._in_flight.pop(batch_id, [])
        for item in items:
            if not item.future._future.done():
                item.future._future.set_exception(exc)

    # ------------------------------------------------------------------
    # Build Anthropic batch request payload
    # ------------------------------------------------------------------

    @staticmethod
    def _build_batch_params(req: BatchableRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": req.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": req.user}],
        }
        if req.schema:
            params["tools"] = [
                {
                    "name": req.tool_name,
                    "description": "Return the structured result.",
                    "input_schema": req.schema,
                }
            ]
            params["tool_choice"] = {"type": "tool", "name": req.tool_name}
        params.update(req.extra)
        return {
            "custom_id": req.custom_id,
            "params": params,
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return submission counts and in-flight batch count."""
        return {
            **self._stats,
            "in_flight_batches": len(self._in_flight),
            "queued": len(self._queue),
        }


# ---------------------------------------------------------------------------
# Internal helper: extract result from a batch message
# ---------------------------------------------------------------------------

def _extract_batch_result(message: Any) -> dict[str, Any]:
    """Pull tool-use input or plain text from a batch result message."""
    content = getattr(message, "content", []) or []
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "tool_use":
            inp = getattr(block, "input", None) or {}
            return {"data": dict(inp), "type": "tool_use"}
        if btype == "text":
            return {"text": getattr(block, "text", ""), "type": "text"}
    return {"type": "empty"}
