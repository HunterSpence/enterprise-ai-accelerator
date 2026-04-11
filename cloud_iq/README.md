# CloudIQ — AI-Powered Cloud Infrastructure Intelligence

> Consulting firms charge $150,000–$500,000 for what this does in 60 seconds.

CloudIQ discovers your entire AWS infrastructure, identifies cost waste, detects
configuration drift against Terraform state, generates production-quality IaC, and
answers questions about your infrastructure in plain English.

---

## What It Does vs. What Consulting Firms Charge

| Capability | Accenture / Deloitte | CloudIQ |
|---|---|---|
| Infrastructure discovery | 4–8 weeks, $150K+ | 60 seconds |
| Cost waste detection | Manual Excel analysis | Automated, dollar-quantified |
| Rightsizing recommendations | Consultant report | CloudWatch-backed with confidence scores |
| Shadow IT detection | Not included | Compares live AWS vs Terraform state |
| Reverse Terraform generation | Not automated (consultants write it) | Full modular output with security best practices |
| Natural language queries | Email your account manager | `cloudiq --query "Why did my bill spike?"` |
| HTML stakeholder report | $10K deliverable | `cloudiq --report output.html` |

---

## Architecture

```
cloud_iq/
├── scanner.py           Async AWS discovery (13 services, parallel scan)
├── cost_analyzer.py     Cost Explorer + CloudWatch waste detection
├── terraform_generator.py  Reverse IaC with AI-enhanced documentation
├── nl_query.py          Claude-powered natural language interface
├── dashboard.py         Rich terminal dashboard + HTML export
└── demo.py              Self-contained demo (no AWS creds required)

AWS Services Scanned:
  EC2 → RDS → Lambda → S3 → EBS → EKS → ECS
  VPC → IAM → CloudFront → ElastiCache → DynamoDB → SQS → SNS
```

---

## Installation

```bash
pip install boto3 anthropic rich
```

For AWS access, ensure your environment has valid credentials:
```bash
export AWS_DEFAULT_REGION=us-east-1
aws configure  # or use instance profile / IAM role
```

For AI features (natural language queries, Terraform enhancement):
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

### Run the demo (no AWS credentials required)
```bash
python -m cloud_iq.demo
```

### Scan your AWS account
```python
from cloud_iq import InfrastructureScanner, CostAnalyzer, Dashboard

scanner = InfrastructureScanner(regions=["us-east-1", "us-west-2"])
snapshot = scanner.scan()

analyzer = CostAnalyzer()
report = analyzer.analyze(snapshot)

dashboard = Dashboard(snapshot, report)
dashboard.render()
dashboard.export_html("cloudiq-report.html")
```

### Ask questions about your infrastructure
```python
from cloud_iq import NLQueryEngine

engine = NLQueryEngine(snapshot, report)

result = engine.query("Why did my AWS bill spike last week?")
print(result.answer)

result = engine.query("Which instances should I terminate right now?")
print(result.answer)
```

### Generate Terraform from live infrastructure
```python
from cloud_iq import TerraformGenerator

gen = TerraformGenerator(
    output_dir="./terraform",
    enhance_with_ai=True,  # Uses Claude Haiku to add inline docs
)
output = gen.generate(snapshot)
print(f"Generated {output.total_resources} resources across {len(output.modules)} modules")
```

### Shadow IT detection
```python
analyzer = CostAnalyzer(terraform_state_path="./terraform/terraform.tfstate")
report = analyzer.analyze(snapshot)

for item in report.shadow_it_items:
    print(f"{item.resource_id}: {item.description}")
```

---

## What Gets Detected

### Waste Detection
- Idle EC2 instances (avg CPU < 2%, max CPU < 5% over 14 days)
- Unattached EBS volumes
- Idle Elastic IPs ($3.60/mo each)
- Over-provisioned RDS instances (CPU < 20% max)
- NAT Gateway overuse (consolidation + VPC endpoint recommendations)
- Old EBS snapshots (> 180 days, no lifecycle policy)
- gp2 volumes eligible for gp3 migration (20% cost reduction)

### Security Findings
- Unencrypted RDS instances at rest
- Publicly accessible RDS instances
- S3 buckets without public access block
- IAM users without MFA
- Access keys not rotated in 90 days
- Roles with AdministratorAccess policy

### Rightsizing
- EC2 instances with CloudWatch utilization below threshold
- RDS instances over-provisioned for current workload
- Confidence scoring: HIGH / MEDIUM / LOW based on max CPU headroom
- Dollar-quantified monthly and annual savings per recommendation

### Shadow IT
- EC2 and RDS resources present in AWS but absent from Terraform state
- Quantified monthly cost of each unmanaged resource

---

## Terraform Output Structure

```
terraform/
├── main.tf                 Root module with all sub-module calls
├── variables.tf            Shared variable definitions
├── providers.tf            AWS provider + version constraints
├── terraform.tfvars.example
└── modules/
    ├── ec2/
    │   ├── main.tf         EC2 instances with IMDSv2, gp3, encryption
    │   └── variables.tf
    ├── rds/
    │   ├── main.tf         RDS with deletion protection, backups, encryption
    │   └── variables.tf
    ├── s3/
    │   ├── main.tf         S3 with versioning, KMS, lifecycle, public access block
    │   └── variables.tf
    ├── vpc/
    ├── lambda/
    ├── eks/
    └── elasticache/
```

Security defaults baked into every generated resource:
- EC2: IMDSv2 required, gp3 encrypted root volume
- RDS: StorageEncrypted=true, PubliclyAccessible=false, DeletionProtection=true
- S3: KMS encryption, public access block, lifecycle rules, versioning enabled
- EKS: Private endpoint, secrets encryption, all control plane logs enabled
- Lambda: KMS-encrypted environment variables, least-privilege execution role
- ElastiCache: at-rest + in-transit encryption, snapshot retention

---

## Technical Details

- Python 3.12+
- Async scanning with `asyncio.gather` — parallel service discovery per region
- Typed dataclasses throughout — no dicts masquerading as structs
- Rich for all terminal output — no plain print() calls
- Claude Haiku (`claude-haiku-4-5-20251001`) for NL queries and Terraform enhancement
- Handles AWS API pagination for all services
- Graceful degradation: scan errors are captured per-service, not fatal
- IAM credential report parsing for MFA and key rotation analysis

---

## License

MIT
