"""
app_portfolio/cli.py
=====================

Demo CLI for the app-portfolio analyzer.

Usage:
    python -m app_portfolio.cli <repo_path> [--out json|md] [--no-ai] [--no-cve] [--no-stale]

Examples:
    python -m app_portfolio.cli . --out md
    python -m app_portfolio.cli /path/to/myapp --out json --no-ai
    python -m app_portfolio.cli . --out md --no-cve --no-stale
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Optional rich for pretty terminal output
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    _RICH = True
except ImportError:
    _RICH = False

from app_portfolio.analyzer import RepoAnalyzer
from app_portfolio.report import PortfolioReport


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app_portfolio.cli",
        description="App portfolio analyzer — 6R migration strategy scorer",
    )
    parser.add_argument(
        "repo_path",
        help="Path to the repository to analyze",
    )
    parser.add_argument(
        "--out",
        choices=["json", "md"],
        default="md",
        help="Output format: json or md (default: md)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        default=False,
        help="Skip Opus 4.7 6R scoring (faster, no API key needed)",
    )
    parser.add_argument(
        "--no-cve",
        action="store_true",
        default=False,
        help="Skip OSV.dev CVE scan",
    )
    parser.add_argument(
        "--no-stale",
        action="store_true",
        default=False,
        help="Skip staleness checks (PyPI/npm/etc. lookups)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    return parser


def _print_report(report: PortfolioReport, fmt: str) -> None:
    if fmt == "json":
        print(report.render_json())
        return

    md_text = report.render_markdown()

    if _RICH:
        console = Console()
        console.print(Markdown(md_text))
    else:
        print(md_text)


async def _run(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo_path).expanduser()

    if not repo_path.exists():
        print(f"Error: path does not exist: {repo_path}", file=sys.stderr)
        return 1

    if _RICH and args.out == "md":
        from rich.console import Console
        Console().print(f"\n[bold cyan]Scanning[/] [yellow]{repo_path}[/] …\n")

    analyzer = RepoAnalyzer(
        run_staleness=not args.no_stale,
        run_cve_scan=not args.no_cve,
    )
    report = await analyzer.analyze(repo_path)

    # Optional: 6R scoring via Opus 4.7
    if not args.no_ai:
        try:
            from app_portfolio.six_r_scorer import score_six_r
            from core import get_client
            if _RICH and args.out == "md":
                from rich.console import Console
                Console().print("[bold cyan]Running Opus 4.7 6R scoring…[/]")
            report.six_r_recommendation = await score_six_r(report, get_client())
        except Exception as exc:
            print(
                f"Warning: 6R AI scoring failed ({exc}). "
                "Use --no-ai to suppress this.",
                file=sys.stderr,
            )

    _print_report(report, args.out)

    # Exit code: 1 if critical CVEs found, 0 otherwise
    if report.critical_cve_count > 0:
        if _RICH:
            from rich.console import Console
            Console().print(
                f"\n[bold red]CRITICAL:[/] {report.critical_cve_count} "
                f"CRITICAL/HIGH CVEs found. Review and patch before migration.",
                highlight=False,
            )
        return 1
    return 0


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
