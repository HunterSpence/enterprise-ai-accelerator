"""
iac_security/policies.py
=========================

18 built-in IaC policy checks covering the most common AWS misconfigurations.
No external tool dependency — all logic is plain Python operating on the
TerraformResource / PulumiResource attribute dictionaries.

Each policy is a class with:
  - id          : unique check identifier (IAC-NNN)
  - severity    : "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
  - title       : one-line description
  - description : remediation guidance
  - compliance_refs : list of compliance control mappings
  - resource_types  : set of Terraform resource types this check applies to
  - check(resource) -> CheckResult | None

Returns None if the resource passes (or does not apply).
Returns a CheckResult with detail message when the check fires.

Coverage:
  S3   (5 checks) — ACL, encryption, versioning, MFA delete, block-public-access
  EC2  (3 checks) — EBS encrypted, no public IP, IMDSv2
  RDS  (4 checks) — encrypted, no public, backup retention, multi-AZ
  SG   (1 check)  — no 0.0.0.0/0 on sensitive ports
  IAM  (2 checks) — no wildcard, no admin
  KMS  (1 check)  — key rotation
  CloudTrail (1 check) — multi-region + log validation
  VPC  (1 check)  — flow logs
  ---- subtotal: 18 checks ----
  Plus: Lambda wildcard, ALB HTTPS-only (bonus checks)
  Total: 20 checks defined.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result returned when a policy fires (i.e. the check FAILS)."""

    policy_id: str
    severity: str
    title: str
    description: str
    compliance_refs: list[str]
    resource_address: str
    detail: str  # human-readable explanation of what specifically failed


@runtime_checkable
class Resource(Protocol):
    """Duck-type protocol accepted by all policy checks."""

    kind: str
    resource_type: str
    name: str
    attributes: dict[str, Any]
    source_file: str
    source_line: int

    def get(self, key: str, default: Any = None) -> Any: ...

    @property
    def address(self) -> str: ...


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class PolicyCheck:
    """Abstract base for all IaC policy checks."""

    id: str = "IAC-000"
    severity: str = "HIGH"
    title: str = "Unnamed check"
    description: str = ""
    compliance_refs: list[str] = []
    resource_types: set[str] = set()  # empty = applies to all

    def applies_to(self, resource: Resource) -> bool:
        if not self.resource_types:
            return True
        return resource.resource_type in self.resource_types

    def check(self, resource: Resource) -> Optional[CheckResult]:
        raise NotImplementedError

    def _result(self, resource: Resource, detail: str) -> CheckResult:
        return CheckResult(
            policy_id=self.id,
            severity=self.severity,
            title=self.title,
            description=self.description,
            compliance_refs=list(self.compliance_refs),
            resource_address=resource.address,
            detail=detail,
        )


# ---------------------------------------------------------------------------
# S3 Checks (IAC-001 – IAC-005)
# ---------------------------------------------------------------------------


class S3NoPublicACL(PolicyCheck):
    id = "IAC-001"
    severity = "CRITICAL"
    title = "S3 bucket must not use a public ACL"
    description = (
        "Set 'acl' to 'private' or omit it entirely. "
        "Enable S3 Block Public Access at the bucket or account level."
    )
    compliance_refs = ["CIS AWS 2.1.1", "PCI-DSS 3.4", "SOC 2 CC6.1", "NIST 800-53 AC-3"]
    resource_types = {"aws_s3_bucket", "aws:s3/bucket:Bucket"}

    PUBLIC_ACLS = {"public-read", "public-read-write", "authenticated-read"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        acl = resource.get("acl", "private") or "private"
        if acl in self.PUBLIC_ACLS:
            return self._result(resource, f"acl is '{acl}' — this grants public read access")
        return None


class S3EncryptionEnabled(PolicyCheck):
    id = "IAC-002"
    severity = "HIGH"
    title = "S3 bucket must enable server-side encryption"
    description = (
        "Add 'aws_s3_bucket_server_side_encryption_configuration' with AES256 or aws:kms. "
        "For sensitive data, prefer aws:kms with a customer-managed key."
    )
    compliance_refs = ["CIS AWS 2.1.2", "PCI-DSS 3.5", "SOC 2 CC6.7", "HIPAA 164.312(a)(2)(iv)"]
    resource_types = {"aws_s3_bucket", "aws:s3/bucket:Bucket"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        # Modern: separate resource aws_s3_bucket_server_side_encryption_configuration
        # Legacy inline: server_side_encryption_configuration block
        sse = resource.get("server_side_encryption_configuration")
        if sse is None:
            return self._result(resource, "No server_side_encryption_configuration block found")
        # If it's a list (hcl2 wraps in list), unwrap
        if isinstance(sse, list):
            sse = sse[0] if sse else None
        if not sse:
            return self._result(resource, "server_side_encryption_configuration is empty")
        return None


class S3VersioningEnabled(PolicyCheck):
    id = "IAC-003"
    severity = "MEDIUM"
    title = "S3 bucket should enable versioning"
    description = (
        "Enable versioning to protect against accidental deletion and provide "
        "object-level audit history. Required by CIS and NIST for data integrity."
    )
    compliance_refs = ["CIS AWS 2.1.3", "SOC 2 A1.2", "NIST 800-53 CP-9"]
    resource_types = {"aws_s3_bucket", "aws:s3/bucket:Bucket"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        versioning = resource.get("versioning")
        if isinstance(versioning, list):
            versioning = versioning[0] if versioning else {}
        if not versioning:
            return self._result(resource, "No versioning block found")
        enabled = versioning.get("enabled", False)
        if not enabled:
            return self._result(resource, "versioning.enabled is false")
        return None


class S3MFADeleteEnabled(PolicyCheck):
    id = "IAC-004"
    severity = "MEDIUM"
    title = "S3 bucket versioning should require MFA delete"
    description = (
        "Set mfa_delete = 'Enabled' in the versioning block. "
        "Prevents accidental or malicious permanent object deletion."
    )
    compliance_refs = ["CIS AWS 2.1.3", "SOC 2 CC6.6"]
    resource_types = {"aws_s3_bucket", "aws:s3/bucket:Bucket"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        versioning = resource.get("versioning")
        if isinstance(versioning, list):
            versioning = versioning[0] if versioning else {}
        if not versioning:
            return None  # No versioning block at all — IAC-003 will catch it
        mfa_delete = versioning.get("mfa_delete", "Disabled")
        if str(mfa_delete).lower() not in {"enabled", "true"}:
            return self._result(resource, f"versioning.mfa_delete is '{mfa_delete}'")
        return None


class S3BlockPublicAccess(PolicyCheck):
    id = "IAC-005"
    severity = "HIGH"
    title = "S3 bucket must have Block Public Access settings enabled"
    description = (
        "Add aws_s3_bucket_public_access_block with all four settings set to true: "
        "block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets."
    )
    compliance_refs = ["CIS AWS 2.1.5", "SOC 2 CC6.1", "PCI-DSS 1.3"]
    resource_types = {"aws_s3_bucket_public_access_block"}

    _REQUIRED = [
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ]

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        failed = [
            k for k in self._REQUIRED if not resource.get(k, False)
        ]
        if failed:
            return self._result(
                resource,
                f"Block Public Access settings not enabled: {', '.join(failed)}",
            )
        return None


# ---------------------------------------------------------------------------
# EC2 Checks (IAC-006 – IAC-008)
# ---------------------------------------------------------------------------


class EC2EBSEncrypted(PolicyCheck):
    id = "IAC-006"
    severity = "HIGH"
    title = "EC2 EBS volumes must be encrypted"
    description = (
        "Set 'encrypted = true' on aws_ebs_volume and all root_block_device / "
        "ebs_block_device blocks in aws_instance. Use KMS CMK for compliance workloads."
    )
    compliance_refs = ["CIS AWS 2.2.1", "PCI-DSS 3.4", "HIPAA 164.312(a)(2)(iv)", "SOC 2 CC6.7"]
    resource_types = {"aws_ebs_volume", "aws_instance"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        if resource.resource_type == "aws_ebs_volume":
            if not resource.get("encrypted", False):
                return self._result(resource, "encrypted is not set to true")
        elif resource.resource_type == "aws_instance":
            # Check root block device
            rbd = resource.get("root_block_device")
            if isinstance(rbd, list):
                rbd = rbd[0] if rbd else {}
            if rbd and not rbd.get("encrypted", False):
                return self._result(resource, "root_block_device.encrypted is false")
            # Check any additional EBS block devices
            ebs_devs = resource.get("ebs_block_device") or []
            if isinstance(ebs_devs, dict):
                ebs_devs = [ebs_devs]
            for dev in ebs_devs:
                if isinstance(dev, dict) and not dev.get("encrypted", False):
                    devname = dev.get("device_name", "unknown")
                    return self._result(
                        resource, f"ebs_block_device '{devname}' encrypted is false"
                    )
        return None


class EC2NoPublicIP(PolicyCheck):
    id = "IAC-007"
    severity = "MEDIUM"
    title = "EC2 instances should not have a public IP by default"
    description = (
        "Set 'associate_public_ip_address = false'. "
        "Route internet access via NAT Gateway or Application Load Balancer."
    )
    compliance_refs = ["CIS AWS 5.2", "SOC 2 CC6.6", "NIST 800-53 SC-7"]
    resource_types = {"aws_instance"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        if resource.get("associate_public_ip_address", False):
            return self._result(resource, "associate_public_ip_address is true")
        return None


class EC2IMDSv2Required(PolicyCheck):
    id = "IAC-008"
    severity = "HIGH"
    title = "EC2 instances must require IMDSv2 (token-required)"
    description = (
        "Set metadata_options.http_tokens = 'required' to prevent SSRF-based "
        "credential theft from the instance metadata service."
    )
    compliance_refs = ["CIS AWS 5.6", "SOC 2 CC6.8", "NIST 800-53 IA-3"]
    resource_types = {"aws_instance"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        md = resource.get("metadata_options")
        if isinstance(md, list):
            md = md[0] if md else {}
        if not md:
            return self._result(resource, "metadata_options block is absent — defaults to IMDSv1")
        if md.get("http_tokens", "optional") != "required":
            return self._result(
                resource,
                f"metadata_options.http_tokens is '{md.get('http_tokens', 'optional')}' — must be 'required'",
            )
        return None


# ---------------------------------------------------------------------------
# RDS Checks (IAC-009 – IAC-012)
# ---------------------------------------------------------------------------


class RDSEncrypted(PolicyCheck):
    id = "IAC-009"
    severity = "HIGH"
    title = "RDS instances must have storage encryption enabled"
    description = (
        "Set 'storage_encrypted = true'. "
        "Encryption at rest is required by HIPAA, PCI-DSS, and CIS."
    )
    compliance_refs = ["CIS AWS 2.3.1", "PCI-DSS 3.4", "HIPAA 164.312(a)(2)(iv)"]
    resource_types = {"aws_db_instance", "aws_rds_cluster"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        if not resource.get("storage_encrypted", False):
            return self._result(resource, "storage_encrypted is not true")
        return None


class RDSNotPublic(PolicyCheck):
    id = "IAC-010"
    severity = "CRITICAL"
    title = "RDS instances must not be publicly accessible"
    description = (
        "Set 'publicly_accessible = false'. "
        "Access DB only via VPC-internal connections or VPN."
    )
    compliance_refs = ["CIS AWS 2.3.2", "PCI-DSS 1.3", "SOC 2 CC6.6"]
    resource_types = {"aws_db_instance", "aws_rds_cluster"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        if resource.get("publicly_accessible", False):
            return self._result(resource, "publicly_accessible is true")
        return None


class RDSBackupRetention(PolicyCheck):
    id = "IAC-011"
    severity = "MEDIUM"
    title = "RDS backup retention period must be at least 7 days"
    description = (
        "Set 'backup_retention_period' to 7 or higher. "
        "Required for point-in-time recovery and PCI-DSS compliance."
    )
    compliance_refs = ["CIS AWS 2.3.3", "PCI-DSS 12.10.1", "SOC 2 A1.2"]
    resource_types = {"aws_db_instance", "aws_rds_cluster"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        retention = resource.get("backup_retention_period", 0)
        try:
            retention = int(retention)
        except (TypeError, ValueError):
            retention = 0
        if retention < 7:
            return self._result(
                resource, f"backup_retention_period is {retention} — minimum is 7"
            )
        return None


class RDSMultiAZProduction(PolicyCheck):
    id = "IAC-012"
    severity = "MEDIUM"
    title = "RDS instances tagged 'prod' should enable Multi-AZ"
    description = (
        "Set 'multi_az = true' for production RDS instances. "
        "Tag the resource with Environment=prod to trigger this check."
    )
    compliance_refs = ["SOC 2 A1.1", "SOC 2 A1.2"]
    resource_types = {"aws_db_instance"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        tags = resource.get("tags") or {}
        env = tags.get("Environment", tags.get("environment", "")).lower()
        if env not in {"prod", "production"}:
            return None  # Not a prod instance — skip
        if not resource.get("multi_az", False):
            return self._result(
                resource, "Instance is tagged Environment=prod but multi_az is false"
            )
        return None


# ---------------------------------------------------------------------------
# Security Group Checks (IAC-013)
# ---------------------------------------------------------------------------


class SGNoOpenIngress(PolicyCheck):
    id = "IAC-013"
    severity = "CRITICAL"
    title = "Security group must not allow unrestricted ingress on sensitive ports"
    description = (
        "Remove ingress rules with cidr_blocks containing 0.0.0.0/0 or ::/0 "
        "for ports 22 (SSH), 3389 (RDP), or all ports (-1). "
        "Use VPN, bastion host, or AWS Systems Manager Session Manager."
    )
    compliance_refs = ["CIS AWS 5.2", "CIS AWS 5.3", "PCI-DSS 1.2", "SOC 2 CC6.6"]
    resource_types = {"aws_security_group", "aws_security_group_rule"}

    SENSITIVE_PORTS = {22, 3389}
    OPEN_CIDRS = {"0.0.0.0/0", "::/0"}

    def _is_open(self, cidr_list: Any) -> bool:
        if not cidr_list:
            return False
        if isinstance(cidr_list, str):
            cidr_list = [cidr_list]
        return any(c in self.OPEN_CIDRS for c in cidr_list)

    def _check_ingress_rule(self, rule: dict) -> Optional[str]:
        if not isinstance(rule, dict):
            return None
        from_port = int(rule.get("from_port", 0) or 0)
        to_port = int(rule.get("to_port", 0) or 0)
        protocol = str(rule.get("protocol", "tcp")).lower()
        cidrs = rule.get("cidr_blocks", []) or []
        ipv6_cidrs = rule.get("ipv6_cidr_blocks", []) or []
        all_cidrs = list(cidrs) + list(ipv6_cidrs)

        if not self._is_open(all_cidrs):
            return None

        # All-traffic rule (protocol -1 or "all")
        if protocol in {"-1", "all"}:
            return f"All-traffic ingress open to {all_cidrs}"

        # Port-specific check
        for port in self.SENSITIVE_PORTS:
            if from_port <= port <= to_port:
                return f"Port {port} ingress open to {all_cidrs}"

        # All ports open (from 0 to 65535)
        if from_port == 0 and to_port == 65535:
            return f"All ports ingress open to {all_cidrs}"

        return None

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        if resource.resource_type == "aws_security_group":
            ingress_rules = resource.get("ingress") or []
            if isinstance(ingress_rules, dict):
                ingress_rules = [ingress_rules]
            for rule in ingress_rules:
                msg = self._check_ingress_rule(rule)
                if msg:
                    return self._result(resource, msg)
        elif resource.resource_type == "aws_security_group_rule":
            rtype = resource.get("type", "")
            if rtype != "ingress":
                return None
            msg = self._check_ingress_rule(resource.attributes)
            if msg:
                return self._result(resource, msg)
        return None


# ---------------------------------------------------------------------------
# IAM Checks (IAC-014 – IAC-015)
# ---------------------------------------------------------------------------


class IAMNoWildcardPolicy(PolicyCheck):
    id = "IAC-014"
    severity = "CRITICAL"
    title = "IAM policy must not use wildcard Action and Resource simultaneously"
    description = (
        "Replace 'Action: *' with the specific actions required. "
        "Replace 'Resource: *' with specific ARNs. "
        "Applying both grants full AWS account access — equivalent to root."
    )
    compliance_refs = ["CIS AWS 1.16", "PCI-DSS 7.1", "SOC 2 CC6.3", "NIST 800-53 AC-6"]
    resource_types = {"aws_iam_policy", "aws_iam_policy_document", "aws_iam_role_policy"}

    def _has_wildcard_statement(self, policy_doc: Any) -> bool:
        if isinstance(policy_doc, str):
            import json as _json
            try:
                policy_doc = _json.loads(policy_doc)
            except Exception:
                return False
        if isinstance(policy_doc, dict):
            statements = policy_doc.get("Statement", [])
        elif isinstance(policy_doc, list):
            statements = policy_doc
        else:
            return False
        for stmt in statements:
            if not isinstance(stmt, dict):
                continue
            effect = stmt.get("Effect", "Allow")
            if effect != "Allow":
                continue
            action = stmt.get("Action", [])
            resource = stmt.get("Resource", [])
            if isinstance(action, str):
                action = [action]
            if isinstance(resource, str):
                resource = [resource]
            if "*" in action and "*" in resource:
                return True
        return False

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        # Inline document
        policy = resource.get("policy") or resource.get("document")
        if policy and self._has_wildcard_statement(policy):
            return self._result(resource, "Policy contains Statement with Action:* and Resource:*")
        # aws_iam_policy_document data source has 'statement' blocks
        statements = resource.get("statement") or []
        if isinstance(statements, dict):
            statements = [statements]
        for stmt in statements:
            if not isinstance(stmt, dict):
                continue
            actions = stmt.get("actions", stmt.get("action", []))
            resources = stmt.get("resources", stmt.get("resource", []))
            if isinstance(actions, str):
                actions = [actions]
            if isinstance(resources, str):
                resources = [resources]
            effect = stmt.get("effect", "Allow")
            if effect == "Allow" and "*" in actions and "*" in resources:
                return self._result(
                    resource, "Policy statement has actions=['*'] and resources=['*']"
                )
        return None


class IAMNoAdminPolicy(PolicyCheck):
    id = "IAC-015"
    severity = "HIGH"
    title = "IAM role/user should not attach AdministratorAccess managed policy"
    description = (
        "Remove the AdministratorAccess managed policy attachment. "
        "Create a least-privilege policy with only the permissions required."
    )
    compliance_refs = ["CIS AWS 1.16", "SOC 2 CC6.3", "PCI-DSS 7.1"]
    resource_types = {
        "aws_iam_role_policy_attachment",
        "aws_iam_user_policy_attachment",
        "aws_iam_group_policy_attachment",
    }

    ADMIN_POLICY_ARN = "arn:aws:iam::aws:policy/AdministratorAccess"

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        policy_arn = resource.get("policy_arn", "")
        if self.ADMIN_POLICY_ARN in str(policy_arn):
            return self._result(
                resource,
                f"AdministratorAccess managed policy attached to {resource.address}",
            )
        return None


# ---------------------------------------------------------------------------
# KMS Checks (IAC-016)
# ---------------------------------------------------------------------------


class KMSKeyRotation(PolicyCheck):
    id = "IAC-016"
    severity = "MEDIUM"
    title = "KMS customer-managed keys must have automatic key rotation enabled"
    description = (
        "Set 'enable_key_rotation = true' on aws_kms_key resources. "
        "AWS rotates the key material annually when enabled."
    )
    compliance_refs = ["CIS AWS 3.7", "PCI-DSS 3.6", "SOC 2 CC6.7"]
    resource_types = {"aws_kms_key"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        if not resource.get("enable_key_rotation", False):
            return self._result(resource, "enable_key_rotation is not true")
        return None


# ---------------------------------------------------------------------------
# CloudTrail Checks (IAC-017)
# ---------------------------------------------------------------------------


class CloudTrailMultiRegion(PolicyCheck):
    id = "IAC-017"
    severity = "HIGH"
    title = "CloudTrail must be multi-region with log file validation enabled"
    description = (
        "Set 'is_multi_region_trail = true' and 'enable_log_file_validation = true'. "
        "Multi-region trails capture API calls in all regions including global services."
    )
    compliance_refs = ["CIS AWS 3.1", "CIS AWS 3.2", "SOC 2 CC7.2", "PCI-DSS 10.5"]
    resource_types = {"aws_cloudtrail"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        issues = []
        if not resource.get("is_multi_region_trail", False):
            issues.append("is_multi_region_trail is false")
        if not resource.get("enable_log_file_validation", False):
            issues.append("enable_log_file_validation is false")
        if issues:
            return self._result(resource, "; ".join(issues))
        return None


# ---------------------------------------------------------------------------
# VPC Checks (IAC-018)
# ---------------------------------------------------------------------------


class VPCFlowLogsEnabled(PolicyCheck):
    id = "IAC-018"
    severity = "MEDIUM"
    title = "VPC must have flow logs enabled"
    description = (
        "Create an aws_flow_log resource referencing the VPC. "
        "Flow logs are required for network traffic analysis and incident response."
    )
    compliance_refs = ["CIS AWS 3.9", "SOC 2 CC7.2", "NIST 800-53 AU-2"]
    resource_types = {"aws_vpc"}

    # This check is structural — it requires cross-resource context.
    # The scanner passes the full resource list and calls check_with_context.
    # check() returns a finding if the VPC appears to have no flow log defined
    # in the same file (best-effort; full cross-file analysis is in scanner.py).

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        # Basic signal: check for a flow_log_destination attribute (non-standard
        # but some modules inline it). Real cross-resource check is in scanner.py.
        if not resource.get("enable_flow_log", None) and not resource.get(
            "flow_log_destination", None
        ):
            return self._result(
                resource,
                "No VPC flow log configuration detected for this VPC resource "
                "(verify aws_flow_log exists referencing this VPC)",
            )
        return None


# ---------------------------------------------------------------------------
# Bonus Checks: Lambda + ALB (IAC-019 – IAC-020)
# ---------------------------------------------------------------------------


class LambdaNoWildcardPermission(PolicyCheck):
    id = "IAC-019"
    severity = "HIGH"
    title = "Lambda function permission must not use wildcard principal"
    description = (
        "Scope 'principal' in aws_lambda_permission to a specific AWS account, "
        "service, or ARN rather than '*'."
    )
    compliance_refs = ["CIS AWS 1.16", "SOC 2 CC6.3", "NIST 800-53 AC-6"]
    resource_types = {"aws_lambda_permission"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        principal = resource.get("principal", "")
        if principal == "*":
            return self._result(resource, "principal is '*' — any principal can invoke this Lambda")
        return None


class ALBHTTPSOnly(PolicyCheck):
    id = "IAC-020"
    severity = "HIGH"
    title = "ALB listener must use HTTPS (not plain HTTP to the internet)"
    description = (
        "Change the listener protocol to 'HTTPS' and configure an SSL certificate. "
        "Add a redirect rule on port 80 → 443 for any remaining HTTP listeners."
    )
    compliance_refs = ["CIS AWS 2.1", "PCI-DSS 4.1", "SOC 2 CC6.7"]
    resource_types = {"aws_alb_listener", "aws_lb_listener"}

    def check(self, resource: Resource) -> Optional[CheckResult]:
        if not self.applies_to(resource):
            return None
        protocol = resource.get("protocol", "HTTPS")
        port = resource.get("port", 443)
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 443
        if protocol == "HTTP" and port != 80:
            return self._result(
                resource, f"Listener uses HTTP on port {port} — use HTTPS"
            )
        if protocol == "HTTP":
            # Port 80 is acceptable IF default_action is redirect to HTTPS
            default_action = resource.get("default_action")
            if isinstance(default_action, list):
                default_action = default_action[0] if default_action else {}
            if isinstance(default_action, dict):
                action_type = default_action.get("type", "")
                if action_type != "redirect":
                    return self._result(
                        resource,
                        "HTTP listener on port 80 with non-redirect action — add redirect to HTTPS",
                    )
        return None


# ---------------------------------------------------------------------------
# Policy registry
# ---------------------------------------------------------------------------


ALL_POLICIES: list[PolicyCheck] = [
    S3NoPublicACL(),
    S3EncryptionEnabled(),
    S3VersioningEnabled(),
    S3MFADeleteEnabled(),
    S3BlockPublicAccess(),
    EC2EBSEncrypted(),
    EC2NoPublicIP(),
    EC2IMDSv2Required(),
    RDSEncrypted(),
    RDSNotPublic(),
    RDSBackupRetention(),
    RDSMultiAZProduction(),
    SGNoOpenIngress(),
    IAMNoWildcardPolicy(),
    IAMNoAdminPolicy(),
    KMSKeyRotation(),
    CloudTrailMultiRegion(),
    VPCFlowLogsEnabled(),
    LambdaNoWildcardPermission(),
    ALBHTTPSOnly(),
]


def run_all_policies(resource: Resource) -> list[CheckResult]:
    """Run every applicable policy against a single resource."""
    results: list[CheckResult] = []
    for policy in ALL_POLICIES:
        if not policy.applies_to(resource):
            continue
        try:
            result = policy.check(resource)
            if result is not None:
                results.append(result)
        except Exception as exc:
            logger.warning(
                "Policy %s raised an exception on %s: %s",
                policy.id,
                resource.address,
                exc,
            )
    return results
