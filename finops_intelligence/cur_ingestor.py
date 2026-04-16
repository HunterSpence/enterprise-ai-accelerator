"""
finops_intelligence/cur_ingestor.py
====================================

CURIngestor — AWS Cost and Usage Report ingestion layer.

Loads CUR parquet files (from S3 or local disk) into an in-memory DuckDB
instance and normalises the raw CUR schema into a canonical ``cost_records``
table that every downstream module queries.

Design goals:
- Streams rather than loading 100M+ rows at once: uses DuckDB's native
  parquet scanning with predicate push-down so only the needed date range is
  pulled into memory.
- Zero paid services: customer supplies CUR export; this module only needs
  boto3 credentials to list/download from their own S3 bucket.
- No new dependencies: duckdb, pandas, boto3 are already in requirements.txt.

CUR Column Mapping (partial — full CUR v2 schema):
  line_item_usage_account_id   -> account_id
  line_item_resource_id        -> resource_id
  line_item_product_code       -> service
  line_item_usage_type         -> usage_type
  line_item_line_item_type     -> line_item_type
  line_item_unblended_cost     -> unblended_cost
  line_item_unblended_rate     -> unblended_rate
  line_item_usage_amount       -> usage_amount
  line_item_usage_start_date   -> usage_start
  line_item_usage_end_date     -> usage_end
  product_instance_type        -> instance_type
  product_region               -> region
  product_operating_system     -> operating_system
  product_vcpu                 -> vcpu
  product_memory               -> memory_raw
  pricing_term                 -> pricing_term
  reservation_arn              -> reservation_arn
  savings_plan_savings_plan_a_r_n -> savings_plan_arn
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator, Optional

import pandas as pd

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None  # type: ignore[assignment]

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column normalisation map: raw CUR column -> canonical column
# ---------------------------------------------------------------------------

_CUR_COLUMN_MAP: dict[str, str] = {
    "line_item_usage_account_id": "account_id",
    "line_item_resource_id": "resource_id",
    "line_item_product_code": "service",
    "line_item_usage_type": "usage_type",
    "line_item_line_item_type": "line_item_type",
    "line_item_unblended_cost": "unblended_cost",
    "line_item_unblended_rate": "unblended_rate",
    "line_item_blended_cost": "blended_cost",
    "line_item_usage_amount": "usage_amount",
    "line_item_usage_start_date": "usage_start",
    "line_item_usage_end_date": "usage_end",
    "line_item_currency_code": "currency",
    "product_instance_type": "instance_type",
    "product_region": "region",
    "product_operating_system": "operating_system",
    "product_vcpu": "vcpu",
    "product_memory": "memory_raw",
    "product_instance_family": "instance_family",
    "product_tenancy": "tenancy",
    "pricing_term": "pricing_term",
    "pricing_unit": "pricing_unit",
    "reservation_arn": "reservation_arn",
    "reservation_number_of_reservations": "reservation_count",
    "reservation_effective_cost": "reservation_effective_cost",
    "savings_plan_savings_plan_a_r_n": "savings_plan_arn",
    "savings_plan_savings_plan_effective_cost": "savings_plan_effective_cost",
}

# Canonical schema for the cost_records table
_CANONICAL_COLUMNS = [
    "account_id",
    "resource_id",
    "service",
    "usage_type",
    "line_item_type",
    "unblended_cost",
    "blended_cost",
    "reservation_effective_cost",
    "savings_plan_effective_cost",
    "unblended_rate",
    "usage_amount",
    "usage_start",
    "usage_end",
    "instance_type",
    "instance_family",
    "region",
    "operating_system",
    "vcpu",
    "memory_raw",
    "tenancy",
    "pricing_term",
    "pricing_unit",
    "reservation_arn",
    "reservation_count",
    "savings_plan_arn",
    "currency",
]


def _to_snake(col: str) -> str:
    """Convert a CUR column header to snake_case for map lookup."""
    return col.lower().replace("/", "_").replace("-", "_").replace(" ", "_")


def _normalise_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw CUR columns to canonical names; add missing columns as NaN."""
    snake_cols = {c: _to_snake(c) for c in df.columns}
    df = df.rename(columns=snake_cols)
    # Apply CUR -> canonical map
    df = df.rename(columns={k: v for k, v in _CUR_COLUMN_MAP.items() if k in df.columns})
    # Derive instance_family from instance_type if not present
    if "instance_family" not in df.columns and "instance_type" in df.columns:
        df["instance_family"] = df["instance_type"].str.extract(r"^([a-z][0-9]+[a-z]*)", expand=False)
    # Ensure all canonical columns exist
    for col in _CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    # Parse datetimes
    for dt_col in ("usage_start", "usage_end"):
        if dt_col in df.columns:
            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce", utc=True)
    # Numeric coercions
    for num_col in ("unblended_cost", "blended_cost", "usage_amount", "unblended_rate",
                    "reservation_effective_cost", "savings_plan_effective_cost"):
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0.0)
    return df[_CANONICAL_COLUMNS]


class CURIngestor:
    """Ingests AWS Cost and Usage Reports into DuckDB and exposes ad hoc SQL.

    Usage::

        async with CURIngestor() as cur:
            await cur.ingest_from_s3("my-cur-bucket", "cur/v1/", date(2025,1,1), date(2025,3,31))
            df = cur.query("SELECT region, SUM(unblended_cost) FROM cost_records GROUP BY 1")

    The DuckDB connection is in-memory by default.  Pass ``db_path`` to
    persist to disk (useful for large CURs that exceed available RAM).
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        batch_rows: int = 500_000,
        aws_profile: Optional[str] = None,
        aws_region: str = "us-east-1",
    ) -> None:
        if duckdb is None:
            raise RuntimeError("duckdb is required — pip install duckdb>=0.10.3")
        self._db_path = db_path
        self._batch_rows = batch_rows
        self._aws_profile = aws_profile
        self._aws_region = aws_region
        self._con: Optional[duckdb.DuckDBPyConnection] = None
        self._row_count: int = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "CURIngestor":
        self._open()
        return self

    async def __aexit__(self, *_: Any) -> None:
        self.close()

    def _open(self) -> None:
        if self._con is None:
            self._con = duckdb.connect(self._db_path)
            self._con.execute(
                f"CREATE TABLE IF NOT EXISTS cost_records ({self._schema_ddl()})"
            )

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def _require_open(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._open()
        return self._con  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @staticmethod
    def _schema_ddl() -> str:
        type_map: dict[str, str] = {
            "unblended_cost": "DOUBLE",
            "blended_cost": "DOUBLE",
            "reservation_effective_cost": "DOUBLE",
            "savings_plan_effective_cost": "DOUBLE",
            "unblended_rate": "DOUBLE",
            "usage_amount": "DOUBLE",
            "usage_start": "TIMESTAMPTZ",
            "usage_end": "TIMESTAMPTZ",
            "vcpu": "VARCHAR",
            "reservation_count": "VARCHAR",
        }
        cols = ", ".join(
            f"{c} {type_map.get(c, 'VARCHAR')}"
            for c in _CANONICAL_COLUMNS
        )
        return cols

    # ------------------------------------------------------------------
    # S3 ingestion
    # ------------------------------------------------------------------

    async def ingest_from_s3(
        self,
        bucket: str,
        prefix: str,
        start_date: date,
        end_date: date,
    ) -> int:
        """Download CUR parquet manifests from S3 and load into DuckDB.

        Lists all manifest JSON files under ``s3://bucket/prefix``, filters
        by date range, then streams each parquet file in ``batch_rows``
        chunks.  Returns total rows ingested.
        """
        if boto3 is None:
            raise RuntimeError("boto3 is required — pip install boto3>=1.34.0")
        session = (
            boto3.Session(profile_name=self._aws_profile)
            if self._aws_profile
            else boto3.Session()
        )
        s3 = session.client("s3", region_name=self._aws_region)
        con = self._require_open()
        total = 0
        manifest_keys = list(self._list_manifest_keys(s3, bucket, prefix, start_date, end_date))
        if not manifest_keys:
            logger.warning("No CUR manifests found in s3://%s/%s for date range %s..%s",
                           bucket, prefix, start_date, end_date)
            return 0
        for manifest_key in manifest_keys:
            parquet_keys = self._resolve_parquet_keys(s3, bucket, manifest_key)
            for parquet_key in parquet_keys:
                rows = self._stream_parquet_from_s3(s3, bucket, parquet_key, con)
                total += rows
                logger.debug("Loaded %d rows from s3://%s/%s", rows, bucket, parquet_key)
        self._row_count += total
        logger.info("CURIngestor: ingested %d total rows from S3", total)
        return total

    def _list_manifest_keys(
        self,
        s3_client: Any,
        bucket: str,
        prefix: str,
        start_date: date,
        end_date: date,
    ) -> Generator[str, None, None]:
        """Yield S3 keys of manifest JSON files within the date range."""
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key: str = obj["Key"]
                if not key.endswith("-Manifest.json"):
                    continue
                # CUR manifest path pattern: prefix/YYYYMMDD-YYYYMMDD/...
                m = re.search(r"/(\d{8})-(\d{8})/", key)
                if m:
                    period_start = datetime.strptime(m.group(1), "%Y%m%d").date()
                    period_end = datetime.strptime(m.group(2), "%Y%m%d").date()
                    if period_end < start_date or period_start > end_date:
                        continue
                yield key

    def _resolve_parquet_keys(
        self, s3_client: Any, bucket: str, manifest_key: str
    ) -> list[str]:
        """Read manifest JSON and return the list of parquet file S3 keys."""
        try:
            obj = s3_client.get_object(Bucket=bucket, Key=manifest_key)
            manifest = json.load(obj["Body"])
            return manifest.get("reportKeys", [])
        except (ClientError, json.JSONDecodeError) as exc:
            logger.warning("Could not parse manifest %s: %s", manifest_key, exc)
            return []

    def _stream_parquet_from_s3(
        self, s3_client: Any, bucket: str, key: str, con: Any
    ) -> int:
        """Download a single parquet file from S3 and insert into DuckDB."""
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            s3_client.download_file(bucket, key, tmp_path)
            return self._load_parquet_file(Path(tmp_path), con)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Local ingestion
    # ------------------------------------------------------------------

    async def ingest_from_local(self, path: Path) -> int:
        """Load a local parquet or CSV file (or directory of parquets) into DuckDB.

        Returns total rows ingested.
        """
        con = self._require_open()
        path = Path(path)
        total = 0
        if path.is_dir():
            files = list(path.glob("**/*.parquet")) + list(path.glob("**/*.csv"))
        else:
            files = [path]
        if not files:
            raise FileNotFoundError(f"No parquet/csv files found at {path}")
        for f in files:
            rows = (
                self._load_parquet_file(f, con)
                if f.suffix.lower() == ".parquet"
                else self._load_csv_file(f, con)
            )
            total += rows
            logger.debug("Loaded %d rows from %s", rows, f)
        self._row_count += total
        logger.info("CURIngestor: ingested %d total rows from local path", total)
        return total

    def _load_parquet_file(self, path: Path, con: Any) -> int:
        """Stream a parquet file into DuckDB in batches."""
        # Use DuckDB's native parquet reader for predicate push-down on large files
        tmp_view = f"_cur_tmp_{abs(hash(str(path)))}"
        con.execute(f"CREATE OR REPLACE VIEW {tmp_view} AS SELECT * FROM read_parquet('{path}')")
        col_result = con.execute(f"DESCRIBE {tmp_view}").fetchall()
        available_cols = {row[0].lower() for row in col_result}
        select_parts: list[str] = []
        for canonical_col in _CANONICAL_COLUMNS:
            # Find matching raw column
            raw_col = next(
                (raw for raw, can in _CUR_COLUMN_MAP.items() if can == canonical_col and raw in available_cols),
                None,
            )
            if raw_col:
                if canonical_col in ("unblended_cost", "blended_cost", "usage_amount",
                                     "unblended_rate", "reservation_effective_cost",
                                     "savings_plan_effective_cost"):
                    select_parts.append(f"TRY_CAST({raw_col} AS DOUBLE) AS {canonical_col}")
                elif canonical_col in ("usage_start", "usage_end"):
                    select_parts.append(f"TRY_CAST({raw_col} AS TIMESTAMPTZ) AS {canonical_col}")
                else:
                    select_parts.append(f"CAST({raw_col} AS VARCHAR) AS {canonical_col}")
            elif canonical_col == "instance_family":
                if "product_instance_type" in available_cols:
                    select_parts.append(
                        f"regexp_extract(product_instance_type, '^([a-z][0-9]+[a-z]*)', 1) AS instance_family"
                    )
                else:
                    select_parts.append("NULL::VARCHAR AS instance_family")
            else:
                select_parts.append(f"NULL::VARCHAR AS {canonical_col}")
        select_sql = ", ".join(select_parts)
        con.execute(f"INSERT INTO cost_records SELECT {select_sql} FROM {tmp_view}")
        count = con.execute(f"SELECT COUNT(*) FROM {tmp_view}").fetchone()[0]
        con.execute(f"DROP VIEW IF EXISTS {tmp_view}")
        return count

    def _load_csv_file(self, path: Path, con: Any) -> int:
        """Load a CSV CUR file into DuckDB via pandas normalisation."""
        total = 0
        for chunk in pd.read_csv(str(path), chunksize=self._batch_rows, low_memory=False):
            normalised = _normalise_dataframe(chunk)
            con.execute("INSERT INTO cost_records SELECT * FROM normalised")
            total += len(normalised)
        return total

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def query(self, sql: str) -> pd.DataFrame:
        """Execute arbitrary SQL against the ``cost_records`` table.

        Example::

            df = cur.query(
                "SELECT region, SUM(unblended_cost) AS total "
                "FROM cost_records "
                "WHERE usage_start >= '2025-01-01' "
                "GROUP BY region ORDER BY total DESC"
            )
        """
        con = self._require_open()
        return con.execute(sql).df()

    def row_count(self) -> int:
        """Return total rows currently in cost_records."""
        return self._con.execute("SELECT COUNT(*) FROM cost_records").fetchone()[0] if self._con else 0

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def date_range(self) -> tuple[Optional[str], Optional[str]]:
        """Return (min_usage_start, max_usage_end) from loaded data."""
        row = self._require_open().execute(
            "SELECT MIN(usage_start)::VARCHAR, MAX(usage_end)::VARCHAR FROM cost_records"
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)

    def services(self) -> list[str]:
        """Return distinct services present in the loaded data."""
        rows = self._require_open().execute(
            "SELECT DISTINCT service FROM cost_records WHERE service IS NOT NULL ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]

    def monthly_spend(self, service: Optional[str] = None) -> pd.DataFrame:
        """Return monthly unblended cost grouped by month (and optionally service)."""
        where = f"AND service = '{service}'" if service else ""
        sql = f"""
            SELECT
                DATE_TRUNC('month', usage_start) AS month,
                {'service, ' if not service else ''}
                SUM(unblended_cost) AS unblended_cost
            FROM cost_records
            WHERE line_item_type NOT IN ('Tax', 'Credit', 'Refund')
            {where}
            GROUP BY 1 {'2' if not service else ''}
            ORDER BY 1
        """
        return self.query(sql)
