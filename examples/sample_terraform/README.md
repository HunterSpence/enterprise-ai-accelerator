# sample_terraform — Intentionally Insecure Demo Module

This Terraform module exists **solely** to give the `iac_security` scanner
interesting findings. **Do not apply this to any real AWS account.**

## Intentional Violations

| Policy ID | Severity | Resource | Violation |
|-----------|----------|----------|-----------|
| IAC-001 | CRITICAL | `aws_s3_bucket.public_data` | `acl = "public-read"` — bucket publicly readable |
| IAC-006 | HIGH | `aws_ebs_volume.app_data` | `encrypted = false` — data at rest unprotected |
| IAC-013 | CRITICAL | `aws_security_group.bastion` | Ingress `0.0.0.0/0` on port 22 (SSH) |
| IAC-009 | HIGH | `aws_db_instance.app_db` | `storage_encrypted = false` |
| IAC-010 | CRITICAL | `aws_db_instance.app_db` | `publicly_accessible = true` |
| IAC-016 | MEDIUM | `aws_kms_key.app_key` | `enable_key_rotation = false` |
| IAC-017 | HIGH | `aws_cloudtrail.main` | `enable_log_file_validation = false` + not multi-region |

## Running the Demo Scan

```bash
python -m iac_security scan examples/sample_terraform --format md
```

Expected: 10 findings across CRITICAL / HIGH / MEDIUM severity bands (includes bonus S3 checks for missing encryption and versioning).
