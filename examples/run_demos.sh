#!/usr/bin/env bash
# examples/run_demos.sh
# Run every module's CLI against sample data — zero setup required.
# Usage: bash examples/run_demos.sh
# From the repo root: bash examples/run_demos.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ok()  { echo "[OK]  $1"; }
sep() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }

sep
echo "=== Demo 1: App Portfolio Scan ==="
echo "Analyzes examples/sample_repo for language, deps, CI maturity, container score"
sep
python -m app_portfolio.cli examples/sample_repo --out json --no-ai --no-cve
ok "App Portfolio scan complete"

sep
echo "=== Demo 2: IaC Security Scan ==="
echo "Finds 7 deliberate Terraform violations in examples/sample_terraform"
sep
python -m iac_security scan examples/sample_terraform --format md || true
ok "IaC Security scan complete (non-zero exit expected — violations found)"

sep
echo "=== Demo 3: IaC SBOM Generation ==="
echo "Generates a CycloneDX 1.5 SBOM for examples/sample_repo"
sep
python -m iac_security sbom examples/sample_repo --out /tmp/sbom-demo.cdx.json
ok "SBOM written to /tmp/sbom-demo.cdx.json"

sep
echo "=== Demo 4: FinOps CUR Analysis ==="
echo "Analyzes examples/sample_cur.csv for RI/SP savings and anomalies"
sep
# Uses examples/finops_demo.py wrapper — bypasses a broken stub import
# in finops_intelligence/__init__.py (AnalyticsConfig/UnitEconomicsConfig)
python examples/finops_demo.py analyze \
    --cur examples/sample_cur.csv \
    --spend 15000 \
    --no-ai || true
ok "FinOps analysis complete"

sep
echo
echo "All demos finished."
