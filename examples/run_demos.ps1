# examples/run_demos.ps1
# Run every module's CLI against sample data — zero setup required.
# Usage: .\examples\run_demos.ps1
# From repo root: .\examples\run_demos.ps1

$ErrorActionPreference = "Continue"  # keep going even if a demo exits non-zero

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Sep { Write-Host "`n" + ("━" * 50) -ForegroundColor DarkGray }
function Ok($msg) { Write-Host "[OK]  $msg" -ForegroundColor Green }

Sep
Write-Host "=== Demo 1: App Portfolio Scan ===" -ForegroundColor Cyan
Write-Host "Analyzes examples/sample_repo for language, deps, CI maturity, container score"
Sep
python -m app_portfolio.cli examples/sample_repo --out json --no-ai --no-cve
Ok "App Portfolio scan complete"

Sep
Write-Host "=== Demo 2: IaC Security Scan ===" -ForegroundColor Cyan
Write-Host "Finds 7 deliberate Terraform violations in examples/sample_terraform"
Sep
python -m iac_security scan examples/sample_terraform --format md
Ok "IaC Security scan complete (non-zero exit expected — violations found)"

Sep
Write-Host "=== Demo 3: IaC SBOM Generation ===" -ForegroundColor Cyan
Write-Host "Generates a CycloneDX 1.5 SBOM for examples/sample_repo"
Sep
python -m iac_security sbom examples/sample_repo --out $env:TEMP\sbom-demo.cdx.json
Ok "SBOM written to $env:TEMP\sbom-demo.cdx.json"

Sep
Write-Host "=== Demo 4: FinOps CUR Analysis ===" -ForegroundColor Cyan
Write-Host "Analyzes examples/sample_cur.csv for RI/SP savings and anomalies"
Sep
# Uses examples/finops_demo.py wrapper — bypasses broken stub import in __init__.py
python examples/finops_demo.py analyze `
    --cur examples/sample_cur.csv `
    --spend 15000 `
    --no-ai
Ok "FinOps analysis complete"

Sep
Write-Host "`nAll demos finished." -ForegroundColor Green
