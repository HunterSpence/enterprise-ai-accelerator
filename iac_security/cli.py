"""
iac_security/cli.py
=====================

Command-line interface for the IaC Security module.

Usage:
  python -m iac_security scan <path> [--format json|sarif|md] [--out FILE]
  python -m iac_security sbom <path> [--out sbom.cdx.json]
  python -m iac_security cve  <path> [--out FILE]

Invoked via __main__.py (python -m iac_security).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Subcommand: scan
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> int:
    """Run IaC policy scan and emit findings."""
    from iac_security.scanner import IaCScanner

    path = Path(args.path).resolve()
    if not path.exists():
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        return 1

    scanner = IaCScanner()
    report = scanner.scan(path)

    fmt = (args.format or "json").lower()

    if fmt == "json":
        output = json.dumps(report.to_dict(), indent=2)
    elif fmt == "sarif":
        from iac_security.sarif_exporter import export_sarif
        output = export_sarif(report)
    elif fmt in {"md", "markdown"}:
        output = report.to_markdown()
    else:
        print(f"ERROR: unknown format '{fmt}'. Use json, sarif, or md.", file=sys.stderr)
        return 1

    out_path = args.out
    if out_path:
        Path(out_path).write_text(output, encoding="utf-8")
        print(f"Scan report written to {out_path}")
    else:
        print(output)

    # Exit code: 1 if any CRITICAL or HIGH, 0 otherwise
    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# Subcommand: sbom
# ---------------------------------------------------------------------------


def cmd_sbom(args: argparse.Namespace) -> int:
    """Generate a CycloneDX 1.5 SBOM for a repository."""
    from iac_security.sbom_generator import SBOMGenerator

    path = Path(args.path).resolve()
    if not path.exists():
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        return 1

    gen = SBOMGenerator()
    sbom = gen.generate(path)

    out_path = args.out or "sbom.cdx.json"
    Path(out_path).write_text(json.dumps(sbom, indent=2), encoding="utf-8")
    comp_count = len(sbom.get("components", []))
    print(f"SBOM written to {out_path} ({comp_count} components)")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: cve
# ---------------------------------------------------------------------------


def cmd_cve(args: argparse.Namespace) -> int:
    """Scan detected dependencies in a repo for CVEs via OSV.dev."""
    from iac_security.sbom_generator import SBOMGenerator, DetectedComponent
    from iac_security.osv_scanner import CVEScanner

    path = Path(args.path).resolve()
    if not path.exists():
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        return 1

    # Generate SBOM first to get the component list
    gen = SBOMGenerator()
    sbom = gen.generate(path)
    comp_count = len(sbom.get("components", []))
    print(f"Detected {comp_count} components. Querying OSV.dev...", file=sys.stderr)

    cve_scanner = CVEScanner()
    vulns = cve_scanner.scan_from_sbom(sbom)

    results = {
        "scan_path": str(path),
        "component_count": comp_count,
        "vulnerability_count": len(vulns),
        "critical": sum(1 for v in vulns if v.severity == "CRITICAL"),
        "high": sum(1 for v in vulns if v.severity == "HIGH"),
        "medium": sum(1 for v in vulns if v.severity == "MEDIUM"),
        "low": sum(1 for v in vulns if v.severity in {"LOW", ""}),
        "vulnerabilities": [v.to_dict() for v in vulns],
    }

    output = json.dumps(results, indent=2)
    out_path = args.out
    if out_path:
        Path(out_path).write_text(output, encoding="utf-8")
        print(f"CVE results written to {out_path}")
    else:
        print(output)

    critical_count = results["critical"]
    high_count = results["high"]
    return 0 if (critical_count == 0 and high_count == 0) else 1


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m iac_security",
        description="IaC Security + SBOM + CVE scanner for the Enterprise AI Accelerator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = sub.add_parser("scan", help="Run IaC policy checks against a Terraform/Pulumi path")
    p_scan.add_argument("path", help="Path to IaC root directory or single .tf file")
    p_scan.add_argument(
        "--format", choices=["json", "sarif", "md"], default="json",
        help="Output format (default: json)"
    )
    p_scan.add_argument("--out", metavar="FILE", help="Write output to FILE instead of stdout")

    # sbom
    p_sbom = sub.add_parser("sbom", help="Generate CycloneDX 1.5 SBOM for a repository")
    p_sbom.add_argument("path", help="Repository root path")
    p_sbom.add_argument("--out", metavar="FILE", default="sbom.cdx.json",
                        help="Output file path (default: sbom.cdx.json)")

    # cve
    p_cve = sub.add_parser("cve", help="Scan repo dependencies against OSV.dev for CVEs")
    p_cve.add_argument("path", help="Repository root path")
    p_cve.add_argument("--out", metavar="FILE", help="Write JSON results to FILE instead of stdout")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        sys.exit(cmd_scan(args))
    elif args.command == "sbom":
        sys.exit(cmd_sbom(args))
    elif args.command == "cve":
        sys.exit(cmd_cve(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
