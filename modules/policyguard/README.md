# PolicyGuard — IaC Governance & Policy Checker

Paste Terraform HCL or CloudFormation YAML. Claude returns policy violations with CRITICAL/HIGH/MEDIUM severity and exact remediation code snippets.

## What It Checks

| Category | Policies |
|----------|----------|
| S3 | Public ACL, bucket policy, no block public access, missing versioning |
| Security Groups | 0.0.0.0/0 on SSH (22), RDP (3389), DB ports (3306, 5432) |
| RDS | Unencrypted, public access, no multi-AZ, hardcoded password |
| IAM | No MFA enforcement, wildcard permissions, admin inline policies |
| EC2 | IMDSv1 (missing IMDSv2), unencrypted EBS, public IP on private instances |
| Secrets | Hardcoded passwords, API keys in IaC files |
| Tagging | Missing required tags (Environment, Owner, CostCenter) |

## Run It

```bash
cd modules/policyguard
uvicorn app:app --reload --port 8003
# Open http://localhost:8003
```

## Example Output

```json
{
  "compliance_score": 34,
  "violations": [
    {
      "severity": "CRITICAL",
      "rule": "S3-PUBLIC-ACL",
      "resource": "aws_s3_bucket.user_data",
      "description": "S3 bucket has public-read ACL — exposes user data to the internet",
      "fix": "acl = \"private\"\n\nresource \"aws_s3_bucket_public_access_block\" \"user_data\" {\n  bucket = aws_s3_bucket.user_data.id\n  block_public_acls = true\n  block_public_policy = true\n}"
    },
    {
      "severity": "CRITICAL",
      "rule": "SG-OPEN-SSH",
      "resource": "aws_security_group.web",
      "description": "SSH port 22 open to 0.0.0.0/0 — brute force attack surface",
      "fix": "cidr_blocks = [\"10.0.0.0/8\"]  # Restrict to VPN/bastion CIDR"
    }
  ],
  "remediation_days": 3
}
```
