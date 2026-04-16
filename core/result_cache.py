"""
core/result_cache.py
====================

SQLite-backed async result cache for Anthropic API calls.
Zero external dependencies — uses only stdlib sqlite3 + hashlib + asyncio.

WIRING (one-liner):
    from core.result_cache import ResultCache
    cache = ResultCache()                  # default: ~/.eaa_cache/results.db
    key = cache.make_key(model=model, system_prompt=system, user_prompt=user,
                         schema=schema, tool_name=tool_name, thinking_budget=0)
    hit = await cache.get(key)
    if hit is None:
        result = await ai.structured(...)
        await cache.put(key, {"data": result.data, "tokens_in": result.input_tokens,
                               "tokens_out": result.output_tokens})

Cache key is sha256 of the tuple:
    (model, system_prompt, user_prompt, schema_json, tool_name, thinking_budget)

LRU eviction fires when total on-disk size exceeds ``max_bytes`` (default 500MB).
Eviction removes the oldest-accessed rows in batches of 5% until under limit.

Schema (table: results):
    key          TEXT PRIMARY KEY
    response_json TEXT NOT NULL
    input_tokens  INTEGER
    output_tokens INTEGER
    created_at   REAL   (unix timestamp)
    last_hit_at  REAL
    ttl_seconds  REAL
    hit_count    INTEGER DEFAULT 0
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_DEFAULT_DB_PATH = Path.home() / ".eaa_cache" / "results.db"
_DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MB
_EVICT_FRACTION = 0.05                  # remove 5% oldest rows per eviction pass
_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# CachedResult
# ---------------------------------------------------------------------------

@dataclass
class CachedResult:
    """A result retrieved from the cache.

    Attributes
    ----------
    key : str
        The sha256 cache key.
    response_json : str
        Raw JSON string of the stored response (caller parses).
    input_tokens : int
    output_tokens : int
    created_at : float
        Unix timestamp of original insertion.
    hit_count : int
        How many times this entry has been returned.
    """

    key: str
    response_json: str
    input_tokens: int
    output_tokens: int
    created_at: float
    hit_count: int

    @property
    def data(self) -> Any:
        """Deserialise response_json on demand."""
        return json.loads(self.response_json)


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------

@dataclass
class CacheStats:
    hit_rate: float          # hits / (hits + misses) in this process session
    entries_count: int
    bytes_on_disk: int
    evictions: int

    def __str__(self) -> str:
        mb = self.bytes_on_disk / 1024 / 1024
        return (
            f"CacheStats(hit_rate={self.hit_rate:.1%}, "
            f"entries={self.entries_count}, "
            f"size={mb:.1f}MB, evictions={self.evictions})"
        )


# ---------------------------------------------------------------------------
# ResultCache
# ---------------------------------------------------------------------------

class ResultCache:
    """Async SQLite result cache for Anthropic API calls.

    All public methods are coroutines and safe to call from asyncio.
    SQLite I/O runs in the default executor (thread pool) so it never
    blocks the event loop.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file. Created on first use.
    max_bytes:
        Total on-disk cap before LRU eviction fires (default 500MB).
    default_ttl:
        Default time-to-live in seconds for new entries (default 24h).
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        default_ttl: int = 86_400,
    ) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._max_bytes = max_bytes
        self._default_ttl = default_ttl
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Session-level counters (not persisted)
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._initialized = False
        self._init_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict | None = None,
        tool_name: str = "",
        thinking_budget: int = 0,
    ) -> str:
        """Compute a deterministic sha256 cache key.

        All six dimensions are included so that changing ANY of them
        produces a cache miss (correct behaviour).
        """
        payload = json.dumps(
            {
                "model": model,
                "system": system_prompt,
                "user": user_prompt,
                "schema": schema or {},
                "tool": tool_name,
                "budget": thinking_budget,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def get(self, key: str) -> Optional[CachedResult]:
        """Return a cached result or None if absent / expired.

        Also updates ``last_hit_at`` and ``hit_count`` on a hit.
        """
        await self._ensure_init()
        now = time.time()

        def _read(conn: sqlite3.Connection) -> Optional[tuple]:
            row = conn.execute(
                """
                SELECT response_json, input_tokens, output_tokens,
                       created_at, hit_count, ttl_seconds
                FROM results
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
            if row is None:
                return None
            resp_json, in_tok, out_tok, created_at, hit_count, ttl = row
            # TTL check
            if ttl and (now - created_at) > ttl:
                conn.execute("DELETE FROM results WHERE key = ?", (key,))
                conn.commit()
                return None
            # Update hit metadata
            conn.execute(
                """
                UPDATE results
                SET last_hit_at = ?, hit_count = hit_count + 1
                WHERE key = ?
                """,
                (now, key),
            )
            conn.commit()
            return resp_json, in_tok, out_tok, created_at, hit_count

        row = await self._run_sync(_read)
        if row is None:
            self._misses += 1
            return None
        self._hits += 1
        resp_json, in_tok, out_tok, created_at, hit_count = row
        return CachedResult(
            key=key,
            response_json=resp_json,
            input_tokens=in_tok or 0,
            output_tokens=out_tok or 0,
            created_at=created_at,
            hit_count=hit_count + 1,
        )

    async def put(
        self,
        key: str,
        result: dict[str, Any],
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Insert or replace a cache entry.

        Parameters
        ----------
        key:
            Value from ``make_key()``.
        result:
            Dict with at minimum ``{"data": ..., "tokens_in": int, "tokens_out": int}``.
            The full dict is serialised as response_json.
        ttl_seconds:
            Override the instance default TTL.
        """
        await self._ensure_init()
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        response_json = json.dumps(result, default=str)
        in_tok = result.get("tokens_in", 0)
        out_tok = result.get("tokens_out", 0)

        def _write(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT OR REPLACE INTO results
                  (key, response_json, input_tokens, output_tokens,
                   created_at, last_hit_at, ttl_seconds, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (key, response_json, in_tok, out_tok, now, now, float(ttl)),
            )
            conn.commit()

        await self._run_sync(_write)
        # Evict asynchronously — don't block the caller
        asyncio.get_event_loop().call_soon(lambda: asyncio.ensure_future(self._maybe_evict()))

    async def delete(self, key: str) -> bool:
        """Delete a single entry. Returns True if it existed."""
        await self._ensure_init()

        def _del(conn: sqlite3.Connection) -> int:
            c = conn.execute("DELETE FROM results WHERE key = ?", (key,))
            conn.commit()
            return c.rowcount

        rows = await self._run_sync(_del)
        return rows > 0

    async def clear(self) -> int:
        """Delete all entries. Returns count removed."""
        await self._ensure_init()

        def _clear(conn: sqlite3.Connection) -> int:
            c = conn.execute("DELETE FROM results")
            conn.commit()
            return c.rowcount

        return await self._run_sync(_clear)

    async def stats(self) -> CacheStats:
        """Return hit rate, entry count, on-disk bytes, eviction count."""
        await self._ensure_init()

        def _stats(conn: sqlite3.Connection) -> tuple[int, int]:
            count = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            return count, page_count * page_size

        count, db_bytes = await self._run_sync(_stats)
        total_lookups = self._hits + self._misses
        hit_rate = self._hits / total_lookups if total_lookups else 0.0
        return CacheStats(
            hit_rate=hit_rate,
            entries_count=count,
            bytes_on_disk=db_bytes,
            evictions=self._evictions,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_init(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await self._run_sync(self._create_schema)
            self._initialized = True

    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                key           TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                input_tokens  INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                created_at    REAL NOT NULL,
                last_hit_at   REAL NOT NULL,
                ttl_seconds   REAL,
                hit_count     INTEGER DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_last_hit ON results (last_hit_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON results (created_at)")
        conn.commit()

    async def _maybe_evict(self) -> None:
        """Check size and evict LRU rows if over limit."""
        def _check_and_evict(conn: sqlite3.Connection) -> int:
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            db_bytes = page_count * page_size
            if db_bytes <= self._max_bytes:
                return 0
            # Count rows to remove
            total = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
            to_remove = max(1, int(total * _EVICT_FRACTION))
            conn.execute(
                """
                DELETE FROM results
                WHERE key IN (
                    SELECT key FROM results
                    ORDER BY last_hit_at ASC
                    LIMIT ?
                )
                """,
                (to_remove,),
            )
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
            return to_remove

        removed = await self._run_sync(_check_and_evict)
        if removed:
            self._evictions += removed

    async def _run_sync(self, fn):
        """Run a blocking sqlite3 function in the default executor."""
        loop = asyncio.get_event_loop()
        db_path = str(self._db_path)

        def _wrapper():
            conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
            try:
                return fn(conn)
            finally:
                conn.close()

        return await loop.run_in_executor(None, _wrapper)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_SHARED_CACHE: ResultCache | None = None


def get_cache(db_path: Path | str | None = None) -> ResultCache:
    """Return the process-wide shared ResultCache."""
    global _SHARED_CACHE
    if _SHARED_CACHE is None:
        _SHARED_CACHE = ResultCache(db_path)
    return _SHARED_CACHE
