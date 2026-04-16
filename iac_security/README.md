# iac_security — IaC Security, SBOM, CVE, and Drift Detection

Scans Terraform and Pulumi infrastructure-as-code for security policy violations, generates a CycloneDX SBOM, checks for CVEs in declared dependencies via OSV.dev, detects drift between declared IaC state and live cloud state, and exports all findings as SARIF 2.1.0 for upload to the GitHub Security tab.

---

## Policy Catalog

20 built-in policies. Each policy has an ID, framework reference, severity, and auto-generated remediation.

| ID | Policy | Severity | Framework |
|---|---|---|---|
| IAC-001 | S3 bucket public read/write ACL | CRITICAL | CIS AWS 2.1.5 |
| IAC-002 | S3 bucket versioning disabled | HIGH | CIS AWS 2.1.3 |
| IAC-003 | S3 bucket server-side encryption disabled | HIGH | CIS AWS 2.1.1 |
| IAC-004 | S3 bucket logging disabled | MEDIUM | CIS AWS 2.1.2 |
| IAC-005 | EC2 instance with public IP | HIGH | CIS AWS 5.1 |
| IAC-006 | Security group allows 0.0.0.0/0 inbound | CRITICAL | CIS AWS 5.2 |
| IAC-007 | Security group allows SSH from 0.0.0.0/0 | CRITICAL | CIS AWS 5.3 |
| IAC-008 | RDS instance publicly accessible | CRITICAL | CIS AWS 2.3.2 |
| IAC-009 | RDS storage encryption disabled | HIGH | PCI-DSS 3.4 |
| IAC-010 | RDS multi-AZ disabled | MEDIUM | SOC 2 A1.2 |
| IAC-011 | EKS cluster logging disabled | HIGH | CIS AWS EKS 2.1 |
| IAC-012 | IAM policy with wildcard actions | HIGH | CIS AWS 1.16 |
| IAC-013 | Lambda function with VPC disabled | MEDIUM | SOC 2 CC6.1 |
| IAC-014 | CloudTrail logging disabled | CRITICAL | CIS AWS 3.1 |
| IAC-015 | KMS key rotation disabled | HIGH | CIS AWS 3.7 |
| IAC-016 | VPC flow logs disabled | HIGH | CIS AWS 2.9 |
| IAC-017 | EBS volume encryption disabled | HIGH | HIPAA §164.312(a)(2)(iv) |
| IAC-018 | ALB HTTP listener without HTTPS redirect | MEDIUM | PCI-DSS 4.1 |
| IAC-019 | DynamoDB table without point-in-time recovery | MEDIUM | SOC 2 A1.3 |
| IAC-020 | ECS task definition with privileged=true | HIGH | CIS AWS ECS 5.2 |

Custom policies can be added by extending `policies.py` — see "Adding a Policy" below.

---

## SBOM Flow

`SBOMGenerator` builds a [CycloneDX](https://cyclonedx.org/) BOM from the IaC dependency graph:

1. `TerraformParser` or `PulumiParser` extracts declared provider versions and module sources
2. Generator creates CycloneDX BOM in JSON format (spec 1.5)
3. Each component has: `name`, `version`, `purl` (Package URL), `type` (library / container / infrastructure)
4. BOM is written to `sbom.cdx.json`

```bash
python -m iac_security --sbom ./terraform/ --sbom-output sbom.cdx.json
```

---

## CVE Flow

`OSVScanner` submits the SBOM package list to [OSV.dev](https://osv.dev) in batch:

1. SBOM package list extracted as `{name, version, ecosystem}` tuples
2. Batch POST to `https://api.osv.dev/v1/querybatch`
3. Results mapped back to SBOM components with CVE IDs, severity, and descriptions
4. Critical and High CVEs attached to SARIF findings

No API key required. OSV.dev is free.

---

## Drift Detection

`DriftDetector` compares IaC declared state against live cloud state:

1. Run `TerraformParser` to extract declared resources (type + key config fields)
2. Run `AWSAdapter` (or `AzureAdapter` / `GCPAdapter`) to fetch live resource state
3. Diff: missing resources, extra resources, config mismatches
4. Output: list of `DriftFinding` with resource ID, field, declared value, actual value

```bash
python -m iac_security --drift ./terraform/ --provider aws
```

Requires cloud credentials for the live state query.

---

## SARIF Integration with GitHub

`SARIFExporter` produces SARIF 2.1.0 output with:
- `runs[].tool.driver.rules` — one rule per policy ID
- `runs[].results` — one result per finding with `level`, `message`, `locations` (file + line)
- `runs[].results[].fixes` — remediation text

Upload to GitHub Security tab via CI:

```yaml
# .github/workflows/iac-scan.yml
- name: IaC Security Scan
  run: python -m iac_security . --sarif iac-findings.sarif

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: iac-findings.sarif
```

---

## CLI Usage

```bash
# Full scan: policies + SBOM + CVE + SARIF output
python -m iac_security ./terraform/

# Scan with drift detection
python -m iac_security ./terraform/ --drift --provider aws

# SBOM only
python -m iac_security ./terraform/ --sbom-only --sbom-output sbom.cdx.json

# SARIF output for GitHub upload
python -m iac_security ./terraform/ --sarif findings.sarif

# JSON output
python -m iac_security ./terraform/ --format json
```

---

## Adding a Policy

```python
# iac_security/policies.py
POLICIES.append(PolicyDefinition(
    id="IAC-021",
    name="ElastiCache at-rest encryption disabled",
    severity="HIGH",
    framework="PCI-DSS 3.4",
    resource_types=["aws_elasticache_replication_group"],
    check=lambda resource: resource.get("at_rest_encryption_enabled") is not True,
    remediation="Set at_rest_encryption_enabled = true",
))
```

---

## Programmatic Usage

```python
from iac_security.scanner import IaCScanner

scanner = IaCScanner("./terraform/")
results = scanner.scan()

print(f"{results.total_findings} findings: "
      f"{results.critical} critical, {results.high} high")

# Export SARIF
scanner.export_sarif("findings.sarif")

# Export SBOM
scanner.export_sbom("sbom.cdx.json")
```
