"""
Tests for finops_intelligence/analytics_engine.py — P0-28 stale cache fix.

Regression coverage: query results must never survive a dataset reload.
Before the fix, _cache_key() hashed only (sql, params) — a query issued
against a $1 dataset and a query issued against a $100 dataset (same SQL)
collided in the cache, so the reload silently kept serving the stale total.

Run with:
  python -m pytest finops_intelligence/tests/test_analytics_cache.py -q
"""
from __future__ import annotations

import asyncio
from datetime import date

import pandas as pd
import pytest

from finops_intelligence.analytics_engine import AnalyticsEngine


def _df(total_amount: float) -> pd.DataFrame:
    today = date.today().isoformat()
    return pd.DataFrame([
        {"date": today, "service": "Amazon EC2", "amount": total_amount, "region": "us-east-1", "account_id": "123"},
    ])


class TestCacheInvalidationOnReload:
    def test_reload_returns_fresh_total_not_stale_cache(self):
        engine = AnalyticsEngine()
        try:
            engine.load_dataframe(_df(1.0))
            breakdown = asyncio.run(engine.query_service_breakdown(days=30))
            assert breakdown[0].total_cost == 1.0

            # Reload with a completely different dataset — same SQL shape,
            # same cache key inputs (sql, params) as before the fix.
            engine.load_dataframe(_df(100.0))
            breakdown = asyncio.run(engine.query_service_breakdown(days=30))
            assert breakdown[0].total_cost == 100.0, (
                "query_service_breakdown returned a cached result from the "
                "prior dataset instead of the reloaded one"
            )
        finally:
            engine.close()

    def test_data_version_bumps_on_each_load(self):
        engine = AnalyticsEngine()
        try:
            v0 = engine._data_version
            engine.load_dataframe(_df(1.0))
            v1 = engine._data_version
            engine.load_dataframe(_df(2.0))
            v2 = engine._data_version
            assert v1 > v0
            assert v2 > v1
        finally:
            engine.close()

    def test_cache_key_differs_across_dataset_versions(self):
        engine = AnalyticsEngine()
        try:
            engine.load_dataframe(_df(1.0))
            key_v1 = engine._cache_key("SELECT 1", None)
            engine.load_dataframe(_df(2.0))
            key_v2 = engine._cache_key("SELECT 1", None)
            assert key_v1 != key_v2
        finally:
            engine.close()

    def test_reload_clears_in_memory_cache_dict(self):
        engine = AnalyticsEngine()
        try:
            engine.load_dataframe(_df(1.0))
            asyncio.run(engine.query_service_breakdown(days=30))
            assert len(engine._in_memory_cache) > 0
            engine.load_dataframe(_df(2.0))
            assert len(engine._in_memory_cache) == 0
        finally:
            engine.close()
