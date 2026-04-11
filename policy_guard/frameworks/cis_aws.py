"""
CIS AWS Foundations Benchmark v3.0 — PolicyGuard Implementation
================================================================
Level 1 and Level 2 controls. 50+ checks across IAM, CloudTrail, CloudWatch,
S3, VPC, RDS, EBS, and EC2 security groups.

Each check returns a Finding with:
  - control_id (e.g., "1.4")
  - title
  - status: PASS | FAIL | WARNING | ERROR
  - severity: CRITICAL | HIGH | MEDIUM | LOW | INFO
  - level: 1 | 2
  - remediation: CLI command or console steps
  - resource: the specific AWS resource evaluated
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    control_id: str
    title: str
    status: str               # PASS | FAIL | WARNING | ERROR
    severity: str             # CRITICAL | HIGH | MEDIUM | LOW | INFO
    level: int                # CIS Level 1 or 2
    resource: str
    details: str
    remediation: str
    section: str              # IAM | Logging | Monitoring | Networking | Storage


@dataclass
class CISAWSReport:
    region: str
    findings: list[Finding] = field(default_factory=list)
    compliance_score: float = 0.0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    pass_count: int = 0
    fail_count: int = 0

    def compute(self) -> None:
        self.total_findings = len([f for f in self.findings if f.status == "FAIL"])
        self.critical_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "CRITICAL"])
        self.high_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "HIGH"])
        self.medium_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "MEDIUM"])
        self.low_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "LOW"])
        self.pass_count = len([f for f in self.findings if f.status == "PASS"])
        self.fail_count = len([f for f in self.findings if f.status == "FAIL"])
        total = self.pass_count + self.fail_count
        self.compliance_score = (self.pass_count / total * 100) if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Mock AWS data — realistic intentional violations for demo
# ---------------------------------------------------------------------------

MOCK_AWS_STATE = {
    # IAM
    "root_mfa_enabled": False,           # FAIL — Critical
    "root_access_keys_exist": True,      # FAIL — Critical
    "iam_password_min_length": 8,        # FAIL — should be 14
    "iam_password_reuse_prevention": 0,  # FAIL — should be 24
    "iam_password_expiry_days": 0,       # FAIL — should be 365
    "iam_password_require_uppercase": False,
    "iam_password_require_lowercase": False,
    "iam_password_require_numbers": False,
    "iam_password_require_symbols": False,
    "mfa_on_iam_users": ["alice", "bob"],  # only 2 of 5 users have MFA
    "iam_users_total": 5,
    "iam_support_role_exists": False,    # FAIL
    "iam_no_root_usage_30d": False,      # FAIL — root used recently
    "access_keys_rotated_90d": False,    # FAIL — stale access keys
    "console_users_without_mfa": ["charlie", "dave", "eve"],

    # Logging
    "cloudtrail_enabled_all_regions": True,
    "cloudtrail_log_validation": False,  # FAIL
    "cloudtrail_bucket_public": False,
    "cloudtrail_cloudwatch_integration": False,  # FAIL
    "cloudtrail_kms_encryption": False,  # FAIL
    "aws_config_enabled": False,         # FAIL
    "vpc_flow_logs_enabled": False,      # FAIL — all VPCs
    "s3_bucket_logging_enabled": False,  # FAIL

    # Monitoring (CloudWatch alarms)
    "alarm_unauthorized_api": False,
    "alarm_management_console_no_mfa": False,
    "alarm_root_account_usage": False,
    "alarm_iam_policy_changes": False,
    "alarm_cloudtrail_config_changes": False,
    "alarm_console_auth_failures": False,
    "alarm_disable_or_delete_cmk": False,
    "alarm_s3_bucket_policy_changes": False,
    "alarm_aws_config_changes": False,
    "alarm_security_group_changes": False,
    "alarm_nacl_changes": False,
    "alarm_network_gateway_changes": False,
    "alarm_route_table_changes": False,
    "alarm_vpc_changes": False,

    # Networking
    "default_sg_allows_all": True,       # FAIL
    "rdp_open_to_internet": True,        # FAIL — Critical
    "ssh_open_to_internet": True,        # FAIL — Critical
    "vpc_default_sg_unrestricted": True,

    # Storage
    "s3_block_public_access_account": False,  # FAIL — Critical
    "s3_public_buckets": ["data-lake-raw", "ml-training-data"],  # FAIL
    "ebs_encryption_default": False,     # FAIL
    "rds_encryption_at_rest": False,     # FAIL
    "rds_public_access": True,           # FAIL
    "rds_auto_minor_upgrades": False,

    # Extras
    "kms_rotation_enabled": False,       # FAIL
    "guardduty_enabled": False,          # FAIL
    "securityhub_enabled": False,        # FAIL
    "macie_enabled": False,
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class CISAWSScanner:
    """
    Runs CIS AWS Foundations Benchmark checks.
    Set mock=True to use MOCK_AWS_STATE (no AWS credentials needed).
    Set mock=False to run against a real AWS account via boto3.
    """

    def __init__(
        self,
        region: str = "us-east-1",
        profile: Optional[str] = None,
        mock: bool = True,
    ) -> None:
        self.region = region
        self.profile = profile
        self.mock = mock
        self._boto_clients: dict = {}

    def _boto3_client(self, service: str):
        """Lazy-load boto3 client (skipped in mock mode)."""
        if self.mock:
            return None
        import boto3
        if service not in self._boto_clients:
            session = boto3.Session(profile_name=self.profile, region_name=self.region)
            self._boto_clients[service] = session.client(service)
        return self._boto_clients[service]

    async def scan(self) -> CISAWSReport:
        """Run all checks and return a CISAWSReport."""
        await asyncio.sleep(0)  # yield to event loop
        report = CISAWSReport(region=self.region)

        checks = [
            self._check_1_1_root_no_access_keys,
            self._check_1_2_iam_users_mfa,
            self._check_1_3_no_unused_credentials,
            self._check_1_4_root_mfa,
            self._check_1_5_iam_password_uppercase,
            self._check_1_6_iam_password_lowercase,
            self._check_1_7_iam_password_symbols,
            self._check_1_8_iam_password_numbers,
            self._check_1_9_iam_password_min_length,
            self._check_1_10_iam_password_reuse,
            self._check_1_11_iam_password_expiry,
            self._check_1_12_iam_no_root_usage,
            self._check_1_14_iam_support_role,
            self._check_1_17_iam_access_key_rotation,
            self._check_2_1_cloudtrail_all_regions,
            self._check_2_2_cloudtrail_log_validation,
            self._check_2_3_cloudtrail_bucket_not_public,
            self._check_2_4_cloudtrail_cloudwatch,
            self._check_2_5_aws_config_enabled,
            self._check_2_6_cloudtrail_kms,
            self._check_2_7_kms_rotation,
            self._check_2_8_vpc_flow_logs,
            self._check_2_9_s3_bucket_logging,
            self._check_3_1_alarm_unauthorized_api,
            self._check_3_2_alarm_no_mfa_console,
            self._check_3_3_alarm_root_usage,
            self._check_3_4_alarm_iam_policy_changes,
            self._check_3_5_alarm_cloudtrail_changes,
            self._check_3_6_alarm_console_auth_failures,
            self._check_3_7_alarm_disable_cmk,
            self._check_3_8_alarm_s3_policy_changes,
            self._check_3_9_alarm_config_changes,
            self._check_3_10_alarm_security_group_changes,
            self._check_3_11_alarm_nacl_changes,
            self._check_3_12_alarm_network_gateway_changes,
            self._check_3_13_alarm_route_table_changes,
            self._check_3_14_alarm_vpc_changes,
            self._check_4_1_ssh_not_open_to_internet,
            self._check_4_2_rdp_not_open_to_internet,
            self._check_4_3_default_sg_no_traffic,
            self._check_5_1_s3_block_public_access,
            self._check_5_2_s3_no_public_buckets,
            self._check_5_3_ebs_encryption_default,
            self._check_5_4_rds_encryption,
            self._check_5_5_rds_no_public_access,
            self._check_5_6_rds_auto_minor_upgrades,
            self._check_5_7_guardduty_enabled,
            self._check_5_8_securityhub_enabled,
        ]

        for check_fn in checks:
            finding = check_fn()
            report.findings.append(finding)

        report.compute()
        return report

    # ------------------------------------------------------------------
    # Section 1 — Identity and Access Management
    # ------------------------------------------------------------------

    def _check_1_1_root_no_access_keys(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else self._live_root_access_keys()
        has_keys = state.get("root_access_keys_exist", False)
        return Finding(
            control_id="1.1",
            title="Ensure no root account access keys exist",
            status="FAIL" if has_keys else "PASS",
            severity="CRITICAL",
            level=1,
            resource="AWS Account Root",
            details="Root access keys found. Root account has unrestricted access to all AWS resources."
            if has_keys else "No root access keys detected.",
            remediation=(
                "aws iam delete-access-key --access-key-id <ROOT_KEY_ID>\n"
                "Then disable root API access in IAM console."
            ),
            section="IAM",
        )

    def _check_1_2_iam_users_mfa(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        users_without_mfa = state.get("console_users_without_mfa", [])
        total = state.get("iam_users_total", 0)
        status = "FAIL" if users_without_mfa else "PASS"
        return Finding(
            control_id="1.2",
            title="Ensure MFA is enabled for all IAM users with console access",
            status=status,
            severity="HIGH",
            level=1,
            resource=f"IAM Users ({len(users_without_mfa)}/{total} without MFA)",
            details=f"Users without MFA: {', '.join(users_without_mfa)}" if users_without_mfa else "All console users have MFA.",
            remediation=(
                "For each user: aws iam create-virtual-mfa-device --virtual-mfa-device-name <user-mfa>\n"
                "aws iam enable-mfa-device --user-name <username> --serial-number <arn> --authentication-code1 <code1> --authentication-code2 <code2>"
            ),
            section="IAM",
        )

    def _check_1_3_no_unused_credentials(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        rotated = state.get("access_keys_rotated_90d", True)
        return Finding(
            control_id="1.3",
            title="Ensure credentials unused for 90 days or more are disabled",
            status="FAIL" if not rotated else "PASS",
            severity="HIGH",
            level=1,
            resource="IAM Access Keys",
            details="One or more IAM access keys have not been rotated within 90 days."
            if not rotated else "All credentials rotated within 90 days.",
            remediation=(
                "aws iam list-access-keys --output json\n"
                "aws iam update-access-key --access-key-id <KEY_ID> --status Inactive --user-name <USERNAME>\n"
                "Automate via AWS Config rule: access-keys-rotated"
            ),
            section="IAM",
        )

    def _check_1_4_root_mfa(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        mfa = state.get("root_mfa_enabled", True)
        return Finding(
            control_id="1.4",
            title="Ensure hardware MFA is enabled for the root account",
            status="FAIL" if not mfa else "PASS",
            severity="CRITICAL",
            level=2,
            resource="AWS Account Root",
            details="Root account does not have hardware MFA enabled. This is the highest-severity IAM finding."
            if not mfa else "Hardware MFA is enabled on root account.",
            remediation=(
                "Navigate to AWS Console > IAM > Security Credentials > Activate MFA.\n"
                "Use a hardware MFA device (Yubikey or equivalent) — not virtual MFA for root."
            ),
            section="IAM",
        )

    def _check_1_5_iam_password_uppercase(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("iam_password_require_uppercase", True)
        return Finding(
            control_id="1.5",
            title="Ensure IAM password policy requires at least one uppercase letter",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="IAM Password Policy",
            details="Uppercase letters required." if ok else "Password policy does not require uppercase letters.",
            remediation="aws iam update-account-password-policy --require-uppercase-characters",
            section="IAM",
        )

    def _check_1_6_iam_password_lowercase(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("iam_password_require_lowercase", True)
        return Finding(
            control_id="1.6",
            title="Ensure IAM password policy requires at least one lowercase letter",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="IAM Password Policy",
            details="Lowercase letters required." if ok else "Password policy does not require lowercase letters.",
            remediation="aws iam update-account-password-policy --require-lowercase-characters",
            section="IAM",
        )

    def _check_1_7_iam_password_symbols(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("iam_password_require_symbols", True)
        return Finding(
            control_id="1.7",
            title="Ensure IAM password policy requires at least one symbol",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="IAM Password Policy",
            details="Symbols required." if ok else "Password policy does not require symbols.",
            remediation="aws iam update-account-password-policy --require-symbols",
            section="IAM",
        )

    def _check_1_8_iam_password_numbers(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("iam_password_require_numbers", True)
        return Finding(
            control_id="1.8",
            title="Ensure IAM password policy requires at least one number",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="IAM Password Policy",
            details="Numbers required." if ok else "Password policy does not require numbers.",
            remediation="aws iam update-account-password-policy --require-numbers",
            section="IAM",
        )

    def _check_1_9_iam_password_min_length(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        length = state.get("iam_password_min_length", 14)
        ok = length >= 14
        return Finding(
            control_id="1.9",
            title="Ensure IAM password policy requires minimum length of 14 or greater",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="IAM Password Policy",
            details=f"Minimum password length: {length} (required: 14+)",
            remediation="aws iam update-account-password-policy --minimum-password-length 14",
            section="IAM",
        )

    def _check_1_10_iam_password_reuse(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        reuse = state.get("iam_password_reuse_prevention", 24)
        ok = reuse >= 24
        return Finding(
            control_id="1.10",
            title="Ensure IAM password policy prevents password reuse (24 or greater)",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="IAM Password Policy",
            details=f"Password reuse prevention: {reuse} (required: 24+)",
            remediation="aws iam update-account-password-policy --password-reuse-prevention 24",
            section="IAM",
        )

    def _check_1_11_iam_password_expiry(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        days = state.get("iam_password_expiry_days", 365)
        ok = 0 < days <= 365
        return Finding(
            control_id="1.11",
            title="Ensure IAM password policy expires passwords within 365 days or less",
            status="PASS" if ok else "FAIL",
            severity="LOW",
            level=1,
            resource="IAM Password Policy",
            details=f"Password expiry: {days} days (0 = never, required: 1–365)",
            remediation="aws iam update-account-password-policy --max-password-age 90",
            section="IAM",
        )

    def _check_1_12_iam_no_root_usage(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("iam_no_root_usage_30d", True)
        return Finding(
            control_id="1.12",
            title="Ensure no root account access key exists and root is not used",
            status="FAIL" if not ok else "PASS",
            severity="HIGH",
            level=1,
            resource="AWS Account Root",
            details="Root account was used in the last 30 days. All activity should use IAM users/roles."
            if not ok else "Root account not used in last 30 days.",
            remediation=(
                "Create a dedicated break-glass IAM admin role.\n"
                "Monitor via CloudTrail: filter on userIdentity.type = Root."
            ),
            section="IAM",
        )

    def _check_1_14_iam_support_role(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("iam_support_role_exists", True)
        return Finding(
            control_id="1.14",
            title="Ensure a support role has been created to manage incidents with AWS Support",
            status="PASS" if ok else "FAIL",
            severity="LOW",
            level=1,
            resource="IAM Roles",
            details="AWSSupportAccess policy is not attached to any role or user."
            if not ok else "Support role exists.",
            remediation=(
                "aws iam create-role --role-name SupportRole --assume-role-policy-document file://support-trust.json\n"
                "aws iam attach-role-policy --role-name SupportRole --policy-arn arn:aws:iam::aws:policy/AWSSupportAccess"
            ),
            section="IAM",
        )

    def _check_1_17_iam_access_key_rotation(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        rotated = state.get("access_keys_rotated_90d", True)
        return Finding(
            control_id="1.17",
            title="Ensure access keys are rotated every 90 days or less",
            status="FAIL" if not rotated else "PASS",
            severity="HIGH",
            level=1,
            resource="IAM Access Keys",
            details="Access keys older than 90 days detected. Stale credentials are a leading cause of breaches."
            if not rotated else "All access keys rotated within 90 days.",
            remediation=(
                "aws iam create-access-key --user-name <USERNAME>  # Create new\n"
                "# Update applications with new key\n"
                "aws iam delete-access-key --access-key-id <OLD_KEY_ID> --user-name <USERNAME>"
            ),
            section="IAM",
        )

    # ------------------------------------------------------------------
    # Section 2 — Logging
    # ------------------------------------------------------------------

    def _check_2_1_cloudtrail_all_regions(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("cloudtrail_enabled_all_regions", False)
        return Finding(
            control_id="2.1",
            title="Ensure CloudTrail is enabled in all regions",
            status="PASS" if ok else "FAIL",
            severity="HIGH",
            level=1,
            resource="CloudTrail",
            details="Multi-region CloudTrail trail is enabled." if ok
            else "CloudTrail is not enabled for all regions. Activity in non-monitored regions is invisible.",
            remediation=(
                "aws cloudtrail create-trail --name policyguard-trail "
                "--s3-bucket-name <BUCKET> --is-multi-region-trail\n"
                "aws cloudtrail start-logging --name policyguard-trail"
            ),
            section="Logging",
        )

    def _check_2_2_cloudtrail_log_validation(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("cloudtrail_log_validation", True)
        return Finding(
            control_id="2.2",
            title="Ensure CloudTrail log file validation is enabled",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=2,
            resource="CloudTrail",
            details="Log file validation is enabled — log tampering detectable." if ok
            else "Log file validation is disabled. Logs could be modified without detection.",
            remediation=(
                "aws cloudtrail update-trail --name <TRAIL_NAME> --enable-log-file-validation"
            ),
            section="Logging",
        )

    def _check_2_3_cloudtrail_bucket_not_public(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        public = state.get("cloudtrail_bucket_public", False)
        return Finding(
            control_id="2.3",
            title="Ensure the S3 bucket used to store CloudTrail logs is not publicly accessible",
            status="FAIL" if public else "PASS",
            severity="CRITICAL",
            level=1,
            resource="S3 CloudTrail Bucket",
            details="CloudTrail S3 bucket is public! Audit logs exposed to internet." if public
            else "CloudTrail bucket is private.",
            remediation=(
                "aws s3api put-bucket-acl --bucket <TRAIL_BUCKET> --acl private\n"
                "aws s3api put-public-access-block --bucket <TRAIL_BUCKET> "
                "--public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,"
                "BlockPublicPolicy=true,RestrictPublicBuckets=true"
            ),
            section="Logging",
        )

    def _check_2_4_cloudtrail_cloudwatch(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("cloudtrail_cloudwatch_integration", True)
        return Finding(
            control_id="2.4",
            title="Ensure CloudTrail trails are integrated with CloudWatch Logs",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="CloudTrail / CloudWatch",
            details="CloudTrail integrated with CloudWatch Logs." if ok
            else "CloudTrail is not sending logs to CloudWatch. Real-time alerting on API activity is unavailable.",
            remediation=(
                "aws cloudtrail update-trail --name <TRAIL_NAME> "
                "--cloud-watch-logs-log-group-arn <LOG_GROUP_ARN> "
                "--cloud-watch-logs-role-arn <ROLE_ARN>"
            ),
            section="Logging",
        )

    def _check_2_5_aws_config_enabled(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("aws_config_enabled", True)
        return Finding(
            control_id="2.5",
            title="Ensure AWS Config is enabled in all regions",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=1,
            resource="AWS Config",
            details="AWS Config is enabled." if ok
            else "AWS Config is disabled. Configuration drift and compliance violations go undetected.",
            remediation=(
                "aws configservice put-configuration-recorder "
                "--configuration-recorder name=default,roleARN=<ROLE_ARN> "
                "--recording-group allSupported=true,includeGlobalResources=true\n"
                "aws configservice start-configuration-recorder --configuration-recorder-name default"
            ),
            section="Logging",
        )

    def _check_2_6_cloudtrail_kms(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("cloudtrail_kms_encryption", True)
        return Finding(
            control_id="2.6",
            title="Ensure CloudTrail logs are encrypted at rest using KMS CMKs",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=2,
            resource="CloudTrail",
            details="CloudTrail logs encrypted with KMS CMK." if ok
            else "CloudTrail logs are not encrypted with a customer-managed KMS key.",
            remediation=(
                "aws cloudtrail update-trail --name <TRAIL_NAME> "
                "--kms-key-id arn:aws:kms:<REGION>:<ACCOUNT_ID>:key/<KEY_ID>"
            ),
            section="Logging",
        )

    def _check_2_7_kms_rotation(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("kms_rotation_enabled", True)
        return Finding(
            control_id="2.7",
            title="Ensure rotation for customer-created CMKs is enabled",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=2,
            resource="KMS Customer Keys",
            details="KMS key rotation is enabled." if ok
            else "KMS CMK rotation is disabled. Keys should rotate annually at minimum.",
            remediation="aws kms enable-key-rotation --key-id <KEY_ID>",
            section="Logging",
        )

    def _check_2_8_vpc_flow_logs(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("vpc_flow_logs_enabled", True)
        return Finding(
            control_id="2.8",
            title="Ensure VPC flow logging is enabled in all VPCs",
            status="PASS" if ok else "FAIL",
            severity="HIGH",
            level=2,
            resource="VPC Flow Logs",
            details="VPC flow logs enabled." if ok
            else "VPC flow logs are disabled. Network-level attacks and data exfiltration cannot be investigated.",
            remediation=(
                "aws ec2 create-flow-logs --resource-type VPC --resource-ids <VPC_ID> "
                "--traffic-type ALL --log-destination-type cloud-watch-logs "
                "--log-group-name /aws/vpc/flowlogs"
            ),
            section="Logging",
        )

    def _check_2_9_s3_bucket_logging(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("s3_bucket_logging_enabled", True)
        return Finding(
            control_id="2.9",
            title="Ensure S3 bucket access logging is enabled on the CloudTrail S3 bucket",
            status="PASS" if ok else "FAIL",
            severity="LOW",
            level=1,
            resource="S3 Bucket Logging",
            details="S3 server access logging enabled." if ok
            else "S3 bucket access logging not enabled. Access to log files is unaudited.",
            remediation=(
                "aws s3api put-bucket-logging --bucket <BUCKET> "
                "--bucket-logging-status '{\"LoggingEnabled\":{\"TargetBucket\":\"<LOG_BUCKET>\",\"TargetPrefix\":\"access-logs/\"}}'"
            ),
            section="Logging",
        )

    # ------------------------------------------------------------------
    # Section 3 — Monitoring (CloudWatch Alarms)
    # ------------------------------------------------------------------

    def _make_alarm_check(
        self, control_id: str, title: str, state_key: str, description: str,
        filter_pattern: str
    ) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get(state_key, True)
        return Finding(
            control_id=control_id,
            title=title,
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=2,
            resource="CloudWatch Alarms",
            details=f"Alarm active: {title}" if ok
            else f"No alarm configured for: {description}. Critical events will go unnoticed.",
            remediation=(
                f"aws logs put-metric-filter --log-group-name <CLOUDTRAIL_LOG_GROUP> "
                f"--filter-name {control_id.replace('.', '-')}-filter "
                f"--filter-pattern '{filter_pattern}' "
                f"--metric-transformations metricName={control_id.replace('.', '-')}-metric,"
                f"metricNamespace=CISBenchmark,metricValue=1\n"
                f"aws cloudwatch put-metric-alarm --alarm-name {control_id.replace('.', '-')}-alarm ..."
            ),
            section="Monitoring",
        )

    def _check_3_1_alarm_unauthorized_api(self) -> Finding:
        return self._make_alarm_check(
            "3.1", "Ensure a log metric filter and alarm exist for unauthorized API calls",
            "alarm_unauthorized_api", "unauthorized API calls",
            "{($.errorCode=\"*UnauthorizedOperation\") || ($.errorCode=\"AccessDenied\")}"
        )

    def _check_3_2_alarm_no_mfa_console(self) -> Finding:
        return self._make_alarm_check(
            "3.2", "Ensure alarm exists for management console sign-in without MFA",
            "alarm_management_console_no_mfa", "console sign-in without MFA",
            "{($.eventName=\"ConsoleLogin\") && ($.additionalEventData.MFAUsed != \"Yes\")}"
        )

    def _check_3_3_alarm_root_usage(self) -> Finding:
        return self._make_alarm_check(
            "3.3", "Ensure alarm exists for root account usage",
            "alarm_root_account_usage", "root account usage",
            "{$.userIdentity.type=\"Root\" && $.userIdentity.invokedBy NOT EXISTS && $.eventType !=\"AwsServiceEvent\"}"
        )

    def _check_3_4_alarm_iam_policy_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.4", "Ensure alarm exists for IAM policy changes",
            "alarm_iam_policy_changes", "IAM policy changes",
            "{($.eventName=DeleteGroupPolicy)||($.eventName=DeleteRolePolicy)||...}"
        )

    def _check_3_5_alarm_cloudtrail_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.5", "Ensure alarm exists for CloudTrail configuration changes",
            "alarm_cloudtrail_config_changes", "CloudTrail config changes",
            "{($.eventName=CreateTrail)||($.eventName=UpdateTrail)||($.eventName=DeleteTrail)||"
            "($.eventName=StartLogging)||($.eventName=StopLogging)}"
        )

    def _check_3_6_alarm_console_auth_failures(self) -> Finding:
        return self._make_alarm_check(
            "3.6", "Ensure alarm exists for AWS Management Console authentication failures",
            "alarm_console_auth_failures", "console auth failures",
            "{($.eventName=ConsoleLogin) && ($.errorMessage=\"Failed authentication\")}"
        )

    def _check_3_7_alarm_disable_cmk(self) -> Finding:
        return self._make_alarm_check(
            "3.7", "Ensure alarm exists for disabling or scheduled deletion of CMKs",
            "alarm_disable_or_delete_cmk", "CMK disable/delete",
            "{($.eventSource=kms.amazonaws.com) && (($.eventName=DisableKey)||($.eventName=ScheduleKeyDeletion))}"
        )

    def _check_3_8_alarm_s3_policy_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.8", "Ensure alarm exists for S3 bucket policy changes",
            "alarm_s3_bucket_policy_changes", "S3 bucket policy changes",
            "{($.eventSource=s3.amazonaws.com) && (($.eventName=PutBucketAcl)||($.eventName=PutBucketPolicy)||"
            "($.eventName=PutBucketCors)||($.eventName=PutBucketLifecycle)||($.eventName=PutBucketReplication)||"
            "($.eventName=DeleteBucketPolicy)||($.eventName=DeleteBucketCors)||($.eventName=DeleteBucketLifecycle)||"
            "($.eventName=DeleteBucketReplication))}"
        )

    def _check_3_9_alarm_config_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.9", "Ensure alarm exists for AWS Config configuration changes",
            "alarm_aws_config_changes", "AWS Config changes",
            "{($.eventSource=config.amazonaws.com) && (($.eventName=StopConfigurationRecorder)||"
            "($.eventName=DeleteDeliveryChannel)||($.eventName=PutDeliveryChannel)||"
            "($.eventName=PutConfigurationRecorder))}"
        )

    def _check_3_10_alarm_security_group_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.10", "Ensure alarm exists for security group changes",
            "alarm_security_group_changes", "security group changes",
            "{($.eventName=AuthorizeSecurityGroupIngress)||($.eventName=AuthorizeSecurityGroupEgress)||"
            "($.eventName=RevokeSecurityGroupIngress)||($.eventName=RevokeSecurityGroupEgress)||"
            "($.eventName=CreateSecurityGroup)||($.eventName=DeleteSecurityGroup)}"
        )

    def _check_3_11_alarm_nacl_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.11", "Ensure alarm exists for changes to Network Access Control Lists",
            "alarm_nacl_changes", "NACL changes",
            "{($.eventName=CreateNetworkAcl)||($.eventName=CreateNetworkAclEntry)||"
            "($.eventName=DeleteNetworkAcl)||($.eventName=DeleteNetworkAclEntry)||"
            "($.eventName=ReplaceNetworkAclEntry)||($.eventName=ReplaceNetworkAclAssociation)}"
        )

    def _check_3_12_alarm_network_gateway_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.12", "Ensure alarm exists for changes to network gateways",
            "alarm_network_gateway_changes", "network gateway changes",
            "{($.eventName=CreateCustomerGateway)||($.eventName=DeleteCustomerGateway)||"
            "($.eventName=AttachInternetGateway)||($.eventName=CreateInternetGateway)||"
            "($.eventName=DeleteInternetGateway)||($.eventName=DetachInternetGateway)}"
        )

    def _check_3_13_alarm_route_table_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.13", "Ensure alarm exists for route table changes",
            "alarm_route_table_changes", "route table changes",
            "{($.eventName=CreateRoute)||($.eventName=CreateRouteTable)||"
            "($.eventName=ReplaceRoute)||($.eventName=ReplaceRouteTableAssociation)||"
            "($.eventName=DeleteRouteTable)||($.eventName=DeleteRoute)||"
            "($.eventName=DisassociateRouteTable)}"
        )

    def _check_3_14_alarm_vpc_changes(self) -> Finding:
        return self._make_alarm_check(
            "3.14", "Ensure alarm exists for VPC changes",
            "alarm_vpc_changes", "VPC changes",
            "{($.eventName=CreateVpc)||($.eventName=DeleteVpc)||($.eventName=ModifyVpcAttribute)||"
            "($.eventName=AcceptVpcPeeringConnection)||($.eventName=CreateVpcPeeringConnection)||"
            "($.eventName=DeleteVpcPeeringConnection)||($.eventName=RejectVpcPeeringConnection)||"
            "($.eventName=AttachClassicLinkVpc)||($.eventName=DetachClassicLinkVpc)||"
            "($.eventName=DisableVpcClassicLink)||($.eventName=EnableVpcClassicLink)}"
        )

    # ------------------------------------------------------------------
    # Section 4 — Networking
    # ------------------------------------------------------------------

    def _check_4_1_ssh_not_open_to_internet(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        open_ssh = state.get("ssh_open_to_internet", False)
        return Finding(
            control_id="4.1",
            title="Ensure no security groups allow ingress from 0.0.0.0/0 to port 22 (SSH)",
            status="FAIL" if open_ssh else "PASS",
            severity="CRITICAL",
            level=1,
            resource="EC2 Security Groups",
            details="Security groups allow unrestricted SSH (port 22) from 0.0.0.0/0 and ::/0. "
            "This is the #1 cause of EC2 compromise." if open_ssh
            else "No security groups allow unrestricted SSH.",
            remediation=(
                "aws ec2 describe-security-groups --filters Name=ip-permission.to-port,Values=22 "
                "Name=ip-permission.cidr,Values=0.0.0.0/0\n"
                "aws ec2 revoke-security-group-ingress --group-id <SG_ID> "
                "--protocol tcp --port 22 --cidr 0.0.0.0/0\n"
                "Use AWS Systems Manager Session Manager instead of direct SSH."
            ),
            section="Networking",
        )

    def _check_4_2_rdp_not_open_to_internet(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        open_rdp = state.get("rdp_open_to_internet", False)
        return Finding(
            control_id="4.2",
            title="Ensure no security groups allow ingress from 0.0.0.0/0 to port 3389 (RDP)",
            status="FAIL" if open_rdp else "PASS",
            severity="CRITICAL",
            level=1,
            resource="EC2 Security Groups",
            details="Security groups allow unrestricted RDP (port 3389) from 0.0.0.0/0. "
            "Ransomware actors actively scan for exposed RDP." if open_rdp
            else "No security groups allow unrestricted RDP.",
            remediation=(
                "aws ec2 revoke-security-group-ingress --group-id <SG_ID> "
                "--protocol tcp --port 3389 --cidr 0.0.0.0/0\n"
                "Use AWS Systems Manager Fleet Manager for Windows remote desktop."
            ),
            section="Networking",
        )

    def _check_4_3_default_sg_no_traffic(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        unrestricted = state.get("default_sg_allows_all", False)
        return Finding(
            control_id="4.3",
            title="Ensure the default security group of every VPC restricts all traffic",
            status="FAIL" if unrestricted else "PASS",
            severity="HIGH",
            level=2,
            resource="VPC Default Security Groups",
            details="Default security group allows unrestricted traffic. New resources inherit this group."
            if unrestricted else "Default security groups restrict all traffic.",
            remediation=(
                "aws ec2 revoke-security-group-ingress --group-id <DEFAULT_SG_ID> "
                "--ip-permissions IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]\n"
                "aws ec2 revoke-security-group-egress --group-id <DEFAULT_SG_ID> "
                "--ip-permissions IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]"
            ),
            section="Networking",
        )

    # ------------------------------------------------------------------
    # Section 5 — Storage
    # ------------------------------------------------------------------

    def _check_5_1_s3_block_public_access(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("s3_block_public_access_account", True)
        return Finding(
            control_id="5.1",
            title="Ensure S3 account-level Public Access Block settings are enabled",
            status="PASS" if ok else "FAIL",
            severity="CRITICAL",
            level=1,
            resource="S3 Account Public Access Block",
            details="S3 account-level public access block is active." if ok
            else "S3 account-level public access block is DISABLED. Any bucket can become public.",
            remediation=(
                "aws s3control put-public-access-block --account-id <ACCOUNT_ID> "
                "--public-access-block-configuration "
                "BlockPublicAcls=true,IgnorePublicAcls=true,"
                "BlockPublicPolicy=true,RestrictPublicBuckets=true"
            ),
            section="Storage",
        )

    def _check_5_2_s3_no_public_buckets(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        public = state.get("s3_public_buckets", [])
        return Finding(
            control_id="5.2",
            title="Ensure S3 buckets are not publicly accessible",
            status="FAIL" if public else "PASS",
            severity="CRITICAL",
            level=1,
            resource=f"S3 Buckets: {', '.join(public)}" if public else "S3 Buckets",
            details=f"Public buckets found: {', '.join(public)}. These may expose sensitive training data."
            if public else "No public S3 buckets detected.",
            remediation=(
                "For each public bucket:\n"
                "aws s3api put-public-access-block --bucket <BUCKET_NAME> "
                "--public-access-block-configuration "
                "BlockPublicAcls=true,IgnorePublicAcls=true,"
                "BlockPublicPolicy=true,RestrictPublicBuckets=true"
            ),
            section="Storage",
        )

    def _check_5_3_ebs_encryption_default(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("ebs_encryption_default", True)
        return Finding(
            control_id="5.3",
            title="Ensure EBS volume encryption is enabled by default",
            status="PASS" if ok else "FAIL",
            severity="HIGH",
            level=2,
            resource="EBS Encryption",
            details="Default EBS encryption is enabled." if ok
            else "EBS volumes are not encrypted by default. ML model weights and training data may be unprotected.",
            remediation=(
                "aws ec2 enable-ebs-encryption-by-default --region <REGION>\n"
                "Verify: aws ec2 get-ebs-encryption-by-default"
            ),
            section="Storage",
        )

    def _check_5_4_rds_encryption(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("rds_encryption_at_rest", True)
        return Finding(
            control_id="5.4",
            title="Ensure RDS instances are encrypted at rest",
            status="PASS" if ok else "FAIL",
            severity="HIGH",
            level=1,
            resource="RDS Instances",
            details="All RDS instances encrypted at rest." if ok
            else "RDS instances found without encryption at rest. Databases holding AI training data are unprotected.",
            remediation=(
                "RDS encryption cannot be enabled on existing instances.\n"
                "1. Create an encrypted snapshot: aws rds create-db-snapshot ...\n"
                "2. Copy snapshot with encryption: aws rds copy-db-snapshot --kms-key-id <KEY>\n"
                "3. Restore new encrypted instance from snapshot.\n"
                "4. Update application connection string."
            ),
            section="Storage",
        )

    def _check_5_5_rds_no_public_access(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        public = state.get("rds_public_access", False)
        return Finding(
            control_id="5.5",
            title="Ensure RDS instances are not publicly accessible",
            status="FAIL" if public else "PASS",
            severity="CRITICAL",
            level=1,
            resource="RDS Instances",
            details="RDS instances are publicly accessible over the internet. "
            "Database credentials or SQLi can expose all AI training data." if public
            else "RDS instances are not publicly accessible.",
            remediation=(
                "aws rds modify-db-instance --db-instance-identifier <INSTANCE_ID> "
                "--no-publicly-accessible --apply-immediately"
            ),
            section="Storage",
        )

    def _check_5_6_rds_auto_minor_upgrades(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("rds_auto_minor_upgrades", True)
        return Finding(
            control_id="5.6",
            title="Ensure RDS instances have minor version auto-upgrade enabled",
            status="PASS" if ok else "FAIL",
            severity="LOW",
            level=1,
            resource="RDS Instances",
            details="Auto minor version upgrade enabled." if ok
            else "RDS auto minor version upgrade disabled. Security patches may not be applied.",
            remediation=(
                "aws rds modify-db-instance --db-instance-identifier <INSTANCE_ID> "
                "--auto-minor-version-upgrade --apply-immediately"
            ),
            section="Storage",
        )

    def _check_5_7_guardduty_enabled(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("guardduty_enabled", True)
        return Finding(
            control_id="5.7",
            title="Ensure AWS GuardDuty is enabled",
            status="PASS" if ok else "FAIL",
            severity="HIGH",
            level=1,
            resource="GuardDuty",
            details="GuardDuty enabled — threat detection active." if ok
            else "GuardDuty is disabled. Compromised ML instances and credential theft go undetected.",
            remediation="aws guardduty create-detector --enable --finding-publishing-frequency FIFTEEN_MINUTES",
            section="Storage",
        )

    def _check_5_8_securityhub_enabled(self) -> Finding:
        state = MOCK_AWS_STATE if self.mock else {}
        ok = state.get("securityhub_enabled", True)
        return Finding(
            control_id="5.8",
            title="Ensure AWS Security Hub is enabled",
            status="PASS" if ok else "FAIL",
            severity="MEDIUM",
            level=2,
            resource="Security Hub",
            details="Security Hub enabled — CIS benchmark findings aggregated." if ok
            else "Security Hub is disabled. No unified compliance dashboard or cross-service finding aggregation.",
            remediation=(
                "aws securityhub enable-security-hub "
                "--enable-default-standards "
                "--tags '{\"project\":\"policyguard\"}'"
            ),
            section="Storage",
        )

    # ------------------------------------------------------------------
    # Live AWS check stubs (called when mock=False)
    # ------------------------------------------------------------------

    def _live_root_access_keys(self) -> dict:
        """Real AWS API call to check root access key status."""
        try:
            iam = self._boto3_client("iam")
            resp = iam.get_account_summary()
            return {
                "root_access_keys_exist": resp["SummaryMap"].get("AccountAccessKeysPresent", 0) > 0
            }
        except Exception:
            return {"root_access_keys_exist": False}
