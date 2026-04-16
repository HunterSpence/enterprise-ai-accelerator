"""
finops_intelligence/cli.py
===========================

CLI entry point for the FinOps Intelligence module.

Usage::

    python -m finops_intelligence.cli analyze \\
        --cur s3://my-bucket/cur/ \\
        --start 2025-01-01 --end 2025-03-31 \\
        --spend 340000 \\
        --out report.md

    python -m finops_intelligence.cli analyze \\
        --cur /data/cur_exports/ \\
        --out report.json --format json
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Date must be YYYY-MM-DD, got: {s}")


async def _run_analysis(args: argparse.Namespace) -> None:
    from .cur_ingestor import CURIngestor
    from .ri_sp_optimizer import RISPOptimizer
    from .right_sizer import RightSizer
    from .carbon_tracker import CarbonTracker
    from .savings_reporter import SavingsReporter

    cur_path: str = args.cur
    out_path: Optional[str] = args.out
    out_format: str = args.format
    lookback: int = args.lookback
    spend: float = args.spend

    print(f"[finops] Loading CUR data from: {cur_path}")
    async with CURIngestor() as cur:
        if cur_path.startswith("s3://"):
            # Parse s3://bucket/prefix
            path_no_scheme = cur_path[5:]
            parts = path_no_scheme.split("/", 1)
            bucket = parts[0]
            prefix = parts[1] if len(parts) > 1 else ""
            start_date = _parse_date(args.start) if args.start else date(2025, 1, 1)
            end_date = _parse_date(args.end) if args.end else date.today()
            rows = await cur.ingest_from_s3(bucket, prefix, start_date, end_date)
        else:
            rows = await cur.ingest_from_local(Path(cur_path))
        print(f"[finops] Loaded {rows:,} cost records")
        min_dt, max_dt = cur.date_range()
        if min_dt:
            print(f"[finops] Date range: {min_dt} -> {max_dt}")

        # RI/SP analysis
        print(f"[finops] Running RI/SP analysis (lookback={lookback}d)...")
        optimizer = RISPOptimizer()
        ri_analysis = optimizer.recommend(cur, lookback_days=lookback)
        print(f"[finops]   {len(ri_analysis.recommendations)} RI/SP recommendations, "
              f"${ri_analysis.total_projected_savings_monthly:,.0f}/mo projected savings")

    # Right-sizing — requires workloads; skip if no source configured
    rs_recs = []
    if args.instance_ids:
        print(f"[finops] Running right-sizing for {len(args.instance_ids)} instances...")

        class _SimpleWorkload:
            def __init__(self, resource_id: str, instance_type: str, region: str, account_id: str = ""):
                self.resource_id = resource_id
                self.instance_type = instance_type
                self.region = region
                self.account_id = account_id

        workloads = [
            _SimpleWorkload(iid, args.instance_type or "m5.xlarge", args.region or "us-east-1")
            for iid in args.instance_ids
        ]
        sizer = RightSizer()
        rs_recs = await sizer.recommend(workloads)
        print(f"[finops]   {len(rs_recs)} right-sizing recommendations")
    else:
        print("[finops] Skipping right-sizing (no --instance-ids provided)")

    # Carbon estimate
    carbon_report = None
    if args.carbon:
        print("[finops] Estimating carbon footprint...")
        tracker = CarbonTracker(cloud=args.cloud)
        # Use a placeholder fleet from CUR regions for demo
        cur_services = []  # In real use: derive workloads from CUR
        print("[finops] Carbon tracking requires workload objects. "
              "Integrate with cloud_iq adapters for per-instance estimates.")
    else:
        print("[finops] Skipping carbon estimation (pass --carbon to enable)")

    # Generate report
    print("[finops] Generating savings report...")
    ai_client = None
    if not args.no_ai:
        try:
            from core.ai_client import AIClient
            ai_client = AIClient()
        except Exception as exc:
            print(f"[finops] AI narrative unavailable: {exc}")

    reporter = SavingsReporter(ai_client=ai_client)
    report = await reporter.generate(
        ri_recs=ri_analysis.recommendations,
        rightsize_recs=rs_recs,
        carbon_report=carbon_report,
        current_monthly_spend=spend,
    )

    # Output
    if out_format == "json":
        content = report.render_json()
    else:
        content = report.render_markdown()

    if out_path:
        Path(out_path).write_text(content, encoding="utf-8")
        print(f"[finops] Report written to: {out_path}")
    else:
        print("\n" + content)

    print(f"\n[finops] Done. Total achievable savings: "
          f"${report.total_achievable_savings_usd:,.0f}/mo ({report.savings_pct:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="finops_intelligence.cli",
        description="FinOps Intelligence — open-source cloud cost optimization",
    )
    sub = parser.add_subparsers(dest="command")

    # analyze sub-command
    analyze = sub.add_parser("analyze", help="Analyze CUR data and generate savings report")
    analyze.add_argument("--cur", required=True, help="CUR path: s3://bucket/prefix or local dir/file")
    analyze.add_argument("--start", default=None, help="Start date YYYY-MM-DD (S3 only)")
    analyze.add_argument("--end", default=None, help="End date YYYY-MM-DD (S3 only)")
    analyze.add_argument("--lookback", type=int, default=90, help="RI/SP lookback days (default 90)")
    analyze.add_argument("--spend", type=float, default=0.0, help="Known total monthly spend USD")
    analyze.add_argument("--out", default=None, help="Output file path (stdout if omitted)")
    analyze.add_argument("--format", choices=["markdown", "json"], default="markdown")
    analyze.add_argument("--instance-ids", nargs="*", dest="instance_ids", help="EC2 instance IDs for right-sizing")
    analyze.add_argument("--instance-type", default=None, help="Default instance type for right-sizing")
    analyze.add_argument("--region", default="us-east-1", help="AWS region (default us-east-1)")
    analyze.add_argument("--cloud", default="AWS", choices=["AWS", "Azure", "GCP"])
    analyze.add_argument("--carbon", action="store_true", help="Enable carbon footprint estimation")
    analyze.add_argument("--no-ai", action="store_true", help="Skip Haiku AI narrative generation")
    analyze.add_argument("--profile", default=None, help="AWS profile name")
    analyze.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "analyze":
        asyncio.run(_run_analysis(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
