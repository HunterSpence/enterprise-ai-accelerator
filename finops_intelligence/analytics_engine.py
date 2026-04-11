"""
analytics_engine.py — DuckDB-powered columnar analytics engine for FinOps Intelligence V2.

Replaces in-memory pandas aggregations with sub-second DuckDB queries on millions of rows.
Supports CUR Parquet files (local or S3), async wrapper, and Redis query caching.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

@dataclass
class ServiceBreakdown:
    service: str
    total_cost: float
    avg_daily_cost: float
    pct_of_total: float
    region_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class TagAllocationResult:
    team_breakdown: dict[str, float]
    env_breakdown: dict[str, float]
    project_breakdown: dict[str, float]
    untagged_spend: float
    total_spend: float
    untagged_pct: float


@dataclass
class UntaggedResource:
    service: str
    region: str
    estimated_monthly_cost: float
    days_untagged: int


@dataclass
class QueryResult:
    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    query_time_ms: float
    cache_hit: bool = False


# ---------------------------------------------------------------------------
# DuckDB Analytics Engine
# ---------------------------------------------------------------------------

class AnalyticsEngine:
    """
    DuckDB-backed analytics engine for cloud cost data.

    Can load data from:
      - In-memory pandas DataFrames (from CostTracker)
      - Local Parquet files
      - S3 CUR Parquet (via DuckDB httpfs extension)

    Usage:
        engine = AnalyticsEngine()
        engine.load_dataframe(spend_data.df)
        result = await engine.query_service_breakdown(days=30)
        result = await engine.query_tag_allocation()
    """

    def __init__(
        self,
        redis_url: str | None = None,
        cache_ttl_seconds: int = 3600,
        max_workers: int = 4,
    ) -> None:
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._redis_url = redis_url
        self._cache_ttl = cache_ttl_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._table_loaded = False
        self._in_memory_cache: dict[str, tuple[QueryResult, float]] = {}  # key -> (result, expire_ts)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(":memory:")
            # Install httpfs for S3 access
            try:
                self._conn.execute("INSTALL httpfs; LOAD httpfs;")
            except Exception:
                pass  # httpfs may already be installed
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_dataframe(self, df: pd.DataFrame) -> "AnalyticsEngine":
        """
        Load a pandas DataFrame into DuckDB as the 'costs' table.
        Expected columns: date, service, amount, region, account_id
        """
        conn = self._get_conn()

        # Ensure date column is proper date type
        df = df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        # Add tag columns if missing (for allocation queries)
        for tag_col in ["tag_team", "tag_environment", "tag_project", "tag_owner"]:
            if tag_col not in df.columns:
                df[tag_col] = None

        conn.execute("DROP TABLE IF EXISTS costs")
        conn.execute("CREATE TABLE costs AS SELECT * FROM df")
        self._table_loaded = True
        return self

    def load_parquet(self, path: str) -> "AnalyticsEngine":
        """
        Load CUR Parquet file(s) into DuckDB directly.
        path can be:
          - Local: '/data/cur/*.parquet'
          - S3: 's3://bucket/cur/*.parquet'
        """
        conn = self._get_conn()
        conn.execute("DROP TABLE IF EXISTS costs")
        conn.execute(f"""
            CREATE TABLE costs AS
            SELECT
                CAST(COALESCE("lineItem/UsageStartDate", "BillingPeriodStartDate") AS DATE) AS date,
                COALESCE("product/ProductName", "ServiceName", 'Unknown') AS service,
                CAST(COALESCE("lineItem/UnblendedCost", "BilledCost", '0') AS DOUBLE) AS amount,
                COALESCE("product/region", "Region", 'global') AS region,
                COALESCE("lineItem/UsageAccountId", '') AS account_id,
                '' AS tag_team,
                '' AS tag_environment,
                '' AS tag_project,
                '' AS tag_owner
            FROM read_parquet('{path}', union_by_name=true)
            WHERE CAST(COALESCE("lineItem/UnblendedCost", "BilledCost", '0') AS DOUBLE) > 0
        """)
        row_count = conn.execute("SELECT COUNT(*) FROM costs").fetchone()[0]
        self._table_loaded = True
        return self

    def get_row_count(self) -> int:
        """Return number of rows in the loaded cost table."""
        if not self._table_loaded:
            return 0
        return self._get_conn().execute("SELECT COUNT(*) FROM costs").fetchone()[0]  # type: ignore[index]

    def get_date_range(self) -> tuple[date, date]:
        """Return (min_date, max_date) of loaded data."""
        if not self._table_loaded:
            today = date.today()
            return today - timedelta(days=90), today
        row = self._get_conn().execute("SELECT MIN(date), MAX(date) FROM costs").fetchone()
        return row[0], row[1]  # type: ignore[index]

    # ------------------------------------------------------------------
    # Async wrapper
    # ------------------------------------------------------------------

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous DuckDB function in the thread pool executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, lambda: func(*args, **kwargs))

    async def execute_query(self, sql: str, params: list[Any] | None = None) -> QueryResult:
        """Execute an arbitrary SQL query against the cost table. Async, cached."""
        cache_key = self._cache_key(sql, params)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        def _run() -> QueryResult:
            conn = self._get_conn()
            start = time.perf_counter()
            if params:
                result = conn.execute(sql, params)
            else:
                result = conn.execute(sql)
            rows_raw = result.fetchall()
            columns = [desc[0] for desc in result.description] if result.description else []
            elapsed_ms = (time.perf_counter() - start) * 1000
            rows = [dict(zip(columns, row)) for row in rows_raw]
            return QueryResult(
                rows=rows,
                columns=columns,
                row_count=len(rows),
                query_time_ms=round(elapsed_ms, 2),
            )

        qr = await self._run_sync(_run)
        self._set_cached(cache_key, qr)
        return qr

    # ------------------------------------------------------------------
    # High-level analytics queries
    # ------------------------------------------------------------------

    async def query_service_breakdown(
        self,
        days: int = 30,
        top_n: int = 20,
    ) -> list[ServiceBreakdown]:
        """Top services by cost over the last N days."""
        result = await self.execute_query(f"""
            SELECT
                service,
                SUM(amount) AS total_cost,
                AVG(amount) AS avg_daily_cost,
                SUM(amount) / NULLIF((SELECT SUM(amount) FROM costs WHERE date >= CURRENT_DATE - {days}), 0) * 100 AS pct_of_total
            FROM costs
            WHERE date >= CURRENT_DATE - {days}
            GROUP BY service
            ORDER BY total_cost DESC
            LIMIT {top_n}
        """)
        return [
            ServiceBreakdown(
                service=row["service"],
                total_cost=round(float(row["total_cost"] or 0), 2),
                avg_daily_cost=round(float(row["avg_daily_cost"] or 0), 2),
                pct_of_total=round(float(row["pct_of_total"] or 0), 1),
            )
            for row in result.rows
        ]

    async def query_daily_totals(self, days: int = 90) -> dict[date, float]:
        """Daily aggregated totals — fast even on millions of rows."""
        result = await self.execute_query(f"""
            SELECT date, SUM(amount) AS daily_total
            FROM costs
            WHERE date >= CURRENT_DATE - {days}
            GROUP BY date
            ORDER BY date
        """)
        return {row["date"]: round(float(row["daily_total"] or 0), 2) for row in result.rows}

    async def query_tag_allocation(self, days: int = 30) -> TagAllocationResult:
        """Cost allocation by tag: team, environment, project."""
        team_result = await self.execute_query(f"""
            SELECT COALESCE(tag_team, 'untagged') AS team, SUM(amount) AS cost
            FROM costs
            WHERE date >= CURRENT_DATE - {days}
            GROUP BY team ORDER BY cost DESC
        """)
        env_result = await self.execute_query(f"""
            SELECT COALESCE(tag_environment, 'untagged') AS env, SUM(amount) AS cost
            FROM costs
            WHERE date >= CURRENT_DATE - {days}
            GROUP BY env ORDER BY cost DESC
        """)
        proj_result = await self.execute_query(f"""
            SELECT COALESCE(tag_project, 'untagged') AS project, SUM(amount) AS cost
            FROM costs
            WHERE date >= CURRENT_DATE - {days}
            GROUP BY project ORDER BY cost DESC
        """)
        total_result = await self.execute_query(f"""
            SELECT SUM(amount) AS total,
                   SUM(CASE WHEN tag_team IS NULL OR tag_team = '' THEN amount ELSE 0 END) AS untagged
            FROM costs WHERE date >= CURRENT_DATE - {days}
        """)

        total = float(total_result.rows[0]["total"] or 0) if total_result.rows else 0.0
        untagged = float(total_result.rows[0]["untagged"] or 0) if total_result.rows else 0.0

        return TagAllocationResult(
            team_breakdown={r["team"]: round(float(r["cost"] or 0), 2) for r in team_result.rows},
            env_breakdown={r["env"]: round(float(r["cost"] or 0), 2) for r in env_result.rows},
            project_breakdown={r["project"]: round(float(r["cost"] or 0), 2) for r in proj_result.rows},
            untagged_spend=round(untagged, 2),
            total_spend=round(total, 2),
            untagged_pct=round(untagged / total * 100 if total > 0 else 0, 1),
        )

    async def query_untagged_resources(self, days: int = 30) -> list[UntaggedResource]:
        """Identify services with no tags — FinOps compliance gap."""
        result = await self.execute_query(f"""
            SELECT
                service,
                region,
                SUM(amount) / NULLIF(COUNT(DISTINCT date), 0) * 30 AS estimated_monthly_cost,
                COUNT(DISTINCT date) AS days_in_window
            FROM costs
            WHERE
                date >= CURRENT_DATE - {days}
                AND (tag_team IS NULL OR tag_team = '')
                AND (tag_environment IS NULL OR tag_environment = '')
            GROUP BY service, region
            HAVING estimated_monthly_cost > 10
            ORDER BY estimated_monthly_cost DESC
            LIMIT 50
        """)
        return [
            UntaggedResource(
                service=row["service"],
                region=row["region"] or "global",
                estimated_monthly_cost=round(float(row["estimated_monthly_cost"] or 0), 2),
                days_untagged=int(row["days_in_window"] or 0),
            )
            for row in result.rows
        ]

    async def query_region_breakdown(self, days: int = 30) -> dict[str, float]:
        """Cost by region."""
        result = await self.execute_query(f"""
            SELECT region, SUM(amount) AS cost
            FROM costs
            WHERE date >= CURRENT_DATE - {days}
            GROUP BY region
            ORDER BY cost DESC
        """)
        return {row["region"]: round(float(row["cost"] or 0), 2) for row in result.rows}

    async def query_week_over_week(self, service: str | None = None) -> dict[str, float]:
        """Compare this week vs. last week by service."""
        svc_filter = f"AND service = '{service}'" if service else ""
        result = await self.execute_query(f"""
            SELECT
                service,
                SUM(CASE WHEN date >= CURRENT_DATE - 7 THEN amount ELSE 0 END) AS this_week,
                SUM(CASE WHEN date >= CURRENT_DATE - 14 AND date < CURRENT_DATE - 7 THEN amount ELSE 0 END) AS last_week
            FROM costs
            WHERE date >= CURRENT_DATE - 14
            {svc_filter}
            GROUP BY service
            ORDER BY this_week DESC
        """)
        return {
            row["service"]: round(
                (float(row["this_week"] or 0) - float(row["last_week"] or 0)) /
                max(float(row["last_week"] or 1), 1) * 100,
                1
            )
            for row in result.rows
        }

    async def query_cost_per_day_per_service(
        self,
        service: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Daily cost series for a single service."""
        result = await self.execute_query(f"""
            SELECT date, SUM(amount) AS cost
            FROM costs
            WHERE service = ? AND date >= CURRENT_DATE - {days}
            GROUP BY date
            ORDER BY date
        """, [service])
        return [{"date": row["date"], "cost": round(float(row["cost"] or 0), 2)} for row in result.rows]

    async def query_anomaly_context(
        self,
        service: str,
        anomaly_date: date,
        window_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Get cost context window around an anomaly date for root cause analysis."""
        result = await self.execute_query(f"""
            SELECT date, service, SUM(amount) AS cost
            FROM costs
            WHERE
                date >= DATE '{anomaly_date}' - {window_days}
                AND date <= DATE '{anomaly_date}' + {window_days}
            GROUP BY date, service
            ORDER BY date, cost DESC
        """)
        return [
            {"date": row["date"], "service": row["service"], "cost": round(float(row["cost"] or 0), 2)}
            for row in result.rows
        ]

    async def query_ingest_stats(self) -> dict[str, Any]:
        """Quick stats about the loaded dataset."""
        if not self._table_loaded:
            return {"row_count": 0, "date_range_days": 0, "service_count": 0, "total_spend": 0.0}

        result = await self.execute_query("""
            SELECT
                COUNT(*) AS row_count,
                COUNT(DISTINCT service) AS service_count,
                MIN(date) AS min_date,
                MAX(date) AS max_date,
                SUM(amount) AS total_spend
            FROM costs
        """)
        row = result.rows[0] if result.rows else {}
        min_date = row.get("min_date")
        max_date = row.get("max_date")
        days = (max_date - min_date).days + 1 if min_date and max_date else 0
        return {
            "row_count": int(row.get("row_count") or 0),
            "service_count": int(row.get("service_count") or 0),
            "date_range_days": days,
            "min_date": str(min_date) if min_date else None,
            "max_date": str(max_date) if max_date else None,
            "total_spend": round(float(row.get("total_spend") or 0), 2),
            "query_time_ms": result.query_time_ms,
        }

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, sql: str, params: list[Any] | None) -> str:
        raw = f"{sql}|{json.dumps(params or [], default=str)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> QueryResult | None:
        now = time.time()
        if key in self._in_memory_cache:
            result, expire_ts = self._in_memory_cache[key]
            if now < expire_ts:
                result.cache_hit = True
                return result
            del self._in_memory_cache[key]

        # Try Redis if configured
        if self._redis_url:
            try:
                import redis as redis_lib
                r = redis_lib.from_url(self._redis_url)
                data = r.get(f"finops:query:{key}")
                if data:
                    d = json.loads(data)
                    qr = QueryResult(**d)
                    qr.cache_hit = True
                    return qr
            except Exception:
                pass
        return None

    def _set_cached(self, key: str, result: QueryResult) -> None:
        expire_ts = time.time() + self._cache_ttl
        self._in_memory_cache[key] = (result, expire_ts)

        if self._redis_url:
            try:
                import redis as redis_lib
                r = redis_lib.from_url(self._redis_url)
                data = json.dumps({
                    "rows": result.rows,
                    "columns": result.columns,
                    "row_count": result.row_count,
                    "query_time_ms": result.query_time_ms,
                    "cache_hit": False,
                }, default=str)
                r.setex(f"finops:query:{key}", self._cache_ttl, data)
            except Exception:
                pass

    def clear_cache(self) -> None:
        self._in_memory_cache.clear()
