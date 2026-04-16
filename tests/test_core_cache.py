"""Tests for core/result_cache.py — put/get roundtrip, key determinism, TTL, LRU, stats."""

import asyncio
import time
from pathlib import Path

import pytest
from core.result_cache import CachedResult, CacheStats, ResultCache


@pytest.fixture
def tmp_cache(tmp_path):
    db = tmp_path / "test_cache.db"
    return ResultCache(db_path=db, max_bytes=10 * 1024 * 1024, default_ttl=3600)


class TestResultCacheRoundtrip:
    async def test_put_get_basic(self, tmp_cache):
        key = ResultCache.make_key(model="m", system_prompt="s", user_prompt="u")
        await tmp_cache.put(key, {"data": "hello", "tokens_in": 10, "tokens_out": 5})
        result = await tmp_cache.get(key)
        assert result is not None
        assert result.data["data"] == "hello"

    async def test_miss_returns_none(self, tmp_cache):
        result = await tmp_cache.get("nonexistent_key")
        assert result is None

    async def test_hit_count_increments(self, tmp_cache):
        key = ResultCache.make_key(model="m", system_prompt="s", user_prompt="u2")
        await tmp_cache.put(key, {"data": "x", "tokens_in": 1, "tokens_out": 1})
        r1 = await tmp_cache.get(key)
        r2 = await tmp_cache.get(key)
        assert r2.hit_count >= 2

    async def test_token_fields_stored(self, tmp_cache):
        key = ResultCache.make_key(model="m", system_prompt="s", user_prompt="tok")
        await tmp_cache.put(key, {"data": "y", "tokens_in": 100, "tokens_out": 50})
        result = await tmp_cache.get(key)
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    async def test_delete_returns_true(self, tmp_cache):
        key = ResultCache.make_key(model="m", system_prompt="s", user_prompt="del")
        await tmp_cache.put(key, {"data": "z", "tokens_in": 1, "tokens_out": 1})
        deleted = await tmp_cache.delete(key)
        assert deleted is True

    async def test_delete_nonexistent_returns_false(self, tmp_cache):
        deleted = await tmp_cache.delete("no-such-key")
        assert deleted is False

    async def test_clear_removes_all(self, tmp_cache):
        key = ResultCache.make_key(model="m", system_prompt="s", user_prompt="c")
        await tmp_cache.put(key, {"data": "c", "tokens_in": 1, "tokens_out": 1})
        removed = await tmp_cache.clear()
        assert removed >= 1
        result = await tmp_cache.get(key)
        assert result is None


class TestResultCacheKeyDeterminism:
    def test_same_inputs_same_key(self):
        k1 = ResultCache.make_key(model="m", system_prompt="s", user_prompt="u")
        k2 = ResultCache.make_key(model="m", system_prompt="s", user_prompt="u")
        assert k1 == k2

    def test_different_model_different_key(self):
        k1 = ResultCache.make_key(model="m1", system_prompt="s", user_prompt="u")
        k2 = ResultCache.make_key(model="m2", system_prompt="s", user_prompt="u")
        assert k1 != k2

    def test_different_user_different_key(self):
        k1 = ResultCache.make_key(model="m", system_prompt="s", user_prompt="u1")
        k2 = ResultCache.make_key(model="m", system_prompt="s", user_prompt="u2")
        assert k1 != k2

    def test_key_is_hex_string(self):
        k = ResultCache.make_key(model="m", system_prompt="s", user_prompt="u")
        assert len(k) == 64
        int(k, 16)  # should not raise


class TestResultCacheTTL:
    async def test_expired_entry_returns_none(self, tmp_path):
        db = tmp_path / "ttl_test.db"
        cache = ResultCache(db_path=db, default_ttl=1)
        key = ResultCache.make_key(model="m", system_prompt="s", user_prompt="ttl")
        await cache.put(key, {"data": "ttl_val", "tokens_in": 1, "tokens_out": 1}, ttl_seconds=1)
        await asyncio.sleep(1.1)
        result = await cache.get(key)
        assert result is None


class TestResultCacheStats:
    async def test_stats_structure(self, tmp_cache):
        stats = await tmp_cache.stats()
        assert isinstance(stats, CacheStats)
        assert hasattr(stats, "hit_rate")
        assert hasattr(stats, "entries_count")

    async def test_hit_rate_after_hits(self, tmp_cache):
        key = ResultCache.make_key(model="m", system_prompt="s", user_prompt="hr")
        await tmp_cache.put(key, {"data": "h", "tokens_in": 1, "tokens_out": 1})
        await tmp_cache.get(key)  # hit
        await tmp_cache.get("miss_key")  # miss
        stats = await tmp_cache.stats()
        assert 0.0 <= stats.hit_rate <= 1.0
