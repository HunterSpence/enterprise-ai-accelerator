"""
Reverse Terraform generator.

Takes an InfrastructureSnapshot and produces production-quality, modular
Terraform with security best practices, proper tagging, and AI-enhanced
descriptions generated via Claude Haiku.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cloud_iq.scanner import (
    EC2Instance,
    EKSCluster,
    ElastiCacheCluster,
    InfrastructureSnapshot,
    LambdaFunction,
    RDSInstance,
    S3Bucket,
    VPC,
)

logger = logging.getLogger(__name__)

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TerraformModule:
    name: str
    path: str
    files: dict[str, str] = field(default_factory=dict)


@dataclass
class TerraformOutput:
    root_dir: Path
    modules: list[TerraformModule] = field(default_factory=list)
    total_resources: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------


def _sanitize_name(name: str) -> str:
    """Convert arbitrary strings to valid Terraform resource name identifiers."""
    result = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if result and result[0].isdigit():
        result = "r_" + result
    return result.lower()


def _tags_block(tags: dict[str, str], extra: dict[str, str] | None = None) -> str:
    merged = {**tags, **(extra or {})}
    if not merged:
        return "  tags = var.common_tags"
    lines = ["  tags = merge(var.common_tags, {"]
    for k, v in sorted(merged.items()):
        v_escaped = v.replace('"', '\\"')
        lines.append(f'    "{k}" = "{v_escaped}"')
    lines.append("  })")
    return "\n".join(lines)


def _variables_tf() -> str:
    return '''\
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment (production, staging, development)"
  type        = string
  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "environment must be one of: production, staging, development"
  }
}

variable "common_tags" {
  description = "Tags applied to every resource managed by this module"
  type        = map(string)
  default     = {}
}
'''


def _providers_tf(regions: list[str]) -> str:
    primary = regions[0] if regions else "us-east-1"
    lines = [
        'terraform {',
        '  required_version = ">= 1.5.0"',
        '  required_providers {',
        '    aws = {',
        '      source  = "hashicorp/aws"',
        '      version = "~> 5.0"',
        '    }',
        '  }',
        '}',
        '',
        f'provider "aws" {{',
        f'  region = var.aws_region',
        f'}}',
    ]
    return "\n".join(lines)


def _outputs_tf(resources: list[str]) -> str:
    if not resources:
        return "# No outputs defined\n"
    lines: list[str] = []
    for r in resources:
        lines.append(
            f'output "{r}_id" {{\n  description = "ID of {r}"\n  value       = aws_{r}.this.id\n}}\n'
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-service HCL generators
# ---------------------------------------------------------------------------


def _ec2_hcl(instances: list[EC2Instance]) -> str:
    if not instances:
        return ""
    blocks: list[str] = []
    for inst in instances:
        name = _sanitize_name(
            inst.tags.get("Name", inst.instance_id)
        )
        sg_list = (
            '["' + '", "'.join(inst.security_groups) + '"]'
            if inst.security_groups
            else "[]"
        )
        block = f'''\
resource "aws_instance" "{name}" {{
  ami           = data.aws_ami.{name}.id
  instance_type = "{inst.instance_type}"
  subnet_id     = "{inst.subnet_id or ""}"
  vpc_security_group_ids = {sg_list}

  # Security best practice: require IMDSv2 to prevent SSRF-based credential theft
  metadata_options {{
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }}

  root_block_device {{
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }}

{_tags_block(inst.tags, {{"Name": inst.tags.get("Name", inst.instance_id)}})}
}}

data "aws_ami" "{name}" {{
  most_recent = true
  owners      = ["amazon"]
  filter {{
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }}
}}
'''
        blocks.append(block)
    return "\n".join(blocks)


def _rds_hcl(instances: list[RDSInstance]) -> str:
    if not instances:
        return ""
    blocks: list[str] = []
    for inst in instances:
        name = _sanitize_name(inst.db_instance_id)
        block = f'''\
resource "aws_db_instance" "{name}" {{
  identifier     = "{inst.db_instance_id}"
  engine         = "{inst.engine}"
  engine_version = "{inst.engine_version}"
  instance_class = "{inst.db_instance_class}"

  allocated_storage     = {inst.allocated_storage_gb}
  max_allocated_storage = {max(inst.allocated_storage_gb * 2, 100)}
  storage_type          = "gp3"
  storage_encrypted     = true

  # Security best practices
  publicly_accessible  = false
  deletion_protection  = true
  skip_final_snapshot  = false
  final_snapshot_identifier = "{inst.db_instance_id}-final-snapshot"

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  performance_insights_enabled = true

  multi_az = {str(inst.multi_az).lower()}

{_tags_block(inst.tags)}
}}
'''
        blocks.append(block)
    return "\n".join(blocks)


def _s3_hcl(buckets: list[S3Bucket]) -> str:
    if not buckets:
        return ""
    blocks: list[str] = []
    for bucket in buckets:
        name = _sanitize_name(bucket.name)
        block = f'''\
resource "aws_s3_bucket" "{name}" {{
  bucket = "{bucket.name}"

{_tags_block(bucket.tags)}
}}

resource "aws_s3_bucket_versioning" "{name}" {{
  bucket = aws_s3_bucket.{name}.id
  versioning_configuration {{
    status = "{bucket.versioning if bucket.versioning != "Disabled" else "Enabled"}"
  }}
}}

resource "aws_s3_bucket_server_side_encryption_configuration" "{name}" {{
  bucket = aws_s3_bucket.{name}.id
  rule {{
    apply_server_side_encryption_by_default {{
      sse_algorithm = "aws:kms"
    }}
    bucket_key_enabled = true
  }}
}}

resource "aws_s3_bucket_public_access_block" "{name}" {{
  bucket = aws_s3_bucket.{name}.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}}

resource "aws_s3_bucket_lifecycle_configuration" "{name}" {{
  bucket = aws_s3_bucket.{name}.id
  rule {{
    id     = "transition-to-ia"
    status = "Enabled"
    transition {{
      days          = 30
      storage_class = "STANDARD_IA"
    }}
    transition {{
      days          = 90
      storage_class = "GLACIER"
    }}
  }}
}}
'''
        blocks.append(block)
    return "\n".join(blocks)


def _vpc_hcl(vpcs: list[VPC]) -> str:
    if not vpcs:
        return ""
    blocks: list[str] = []
    for vpc in vpcs:
        name = _sanitize_name(
            vpc.tags.get("Name", vpc.vpc_id)
        )
        nat_count = len(vpc.nat_gateways)
        subnet_blocks: list[str] = []
        for i, subnet in enumerate(vpc.subnets[:6]):
            sub_name = f"{name}_subnet_{i}"
            subnet_blocks.append(
                f'''\
resource "aws_subnet" "{sub_name}" {{
  vpc_id            = aws_vpc.{name}.id
  cidr_block        = "{subnet["cidr"]}"
  availability_zone = "{subnet["az"]}"
  map_public_ip_on_launch = {str(subnet.get("public", False)).lower()}

  tags = merge(var.common_tags, {{
    Name = "{sub_name}"
    Tier = "{("public" if subnet.get("public") else "private")}"
  }})
}}
'''
            )

        block = f'''\
resource "aws_vpc" "{name}" {{
  cidr_block           = "{vpc.cidr_block}"
  enable_dns_hostnames = true
  enable_dns_support   = true

{_tags_block(vpc.tags, {{"Name": vpc.tags.get("Name", vpc.vpc_id)}})}
}}

{"".join(subnet_blocks)}
'''
        blocks.append(block)
    return "\n".join(blocks)


def _lambda_hcl(functions: list[LambdaFunction]) -> str:
    if not functions:
        return ""
    blocks: list[str] = []
    for fn in functions:
        name = _sanitize_name(fn.function_name)
        block = f'''\
resource "aws_lambda_function" "{name}" {{
  function_name = "{fn.function_name}"
  runtime       = "{fn.runtime}"
  handler       = "handler.main"
  role          = aws_iam_role.{name}_execution.arn

  filename         = "${{path.module}}/packages/{fn.function_name}.zip"
  source_code_hash = filebase64sha256("${{path.module}}/packages/{fn.function_name}.zip")

  memory_size = {fn.memory_mb}
  timeout     = {fn.timeout_seconds}

  # Security: encrypt environment variables at rest
  kms_key_arn = aws_kms_key.lambda.arn

  environment {{
    variables = {{
      ENVIRONMENT = var.environment
    }}
  }}

{_tags_block(fn.tags)}
}}

resource "aws_iam_role" "{name}_execution" {{
  name = "{fn.function_name}-execution"
  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {{ Service = "lambda.amazonaws.com" }}
    }}]
  }})
{_tags_block(fn.tags)}
}}

resource "aws_iam_role_policy_attachment" "{name}_basic" {{
  role       = aws_iam_role.{name}_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}}
'''
        blocks.append(block)
    return "\n".join(blocks)


def _eks_hcl(clusters: list[EKSCluster]) -> str:
    if not clusters:
        return ""
    blocks: list[str] = []
    for cluster in clusters:
        name = _sanitize_name(cluster.cluster_name)
        block = f'''\
resource "aws_eks_cluster" "{name}" {{
  name    = "{cluster.cluster_name}"
  version = "{cluster.kubernetes_version}"
  role_arn = aws_iam_role.{name}_cluster.arn

  vpc_config {{
    endpoint_private_access = true
    endpoint_public_access  = false
    subnet_ids              = var.{name}_subnet_ids
  }}

  # Enable envelope encryption for Kubernetes secrets
  encryption_config {{
    resources = ["secrets"]
    provider {{
      key_arn = aws_kms_key.eks_{name}.arn
    }}
  }}

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

{_tags_block(cluster.tags)}

  depends_on = [
    aws_iam_role_policy_attachment.{name}_cluster_policy,
    aws_iam_role_policy_attachment.{name}_vpc_resource,
  ]
}}

resource "aws_iam_role" "{name}_cluster" {{
  name = "{cluster.cluster_name}-cluster-role"
  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {{ Service = "eks.amazonaws.com" }}
    }}]
  }})
}}

resource "aws_iam_role_policy_attachment" "{name}_cluster_policy" {{
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.{name}_cluster.name
}}

resource "aws_iam_role_policy_attachment" "{name}_vpc_resource" {{
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.{name}_cluster.name
}}

resource "aws_kms_key" "eks_{name}" {{
  description             = "KMS key for EKS {cluster.cluster_name} secret encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
{_tags_block(cluster.tags)}
}}
'''
        blocks.append(block)
    return "\n".join(blocks)


def _elasticache_hcl(clusters: list[ElastiCacheCluster]) -> str:
    if not clusters:
        return ""
    blocks: list[str] = []
    for cluster in clusters:
        name = _sanitize_name(cluster.cluster_id)
        block = f'''\
resource "aws_elasticache_cluster" "{name}" {{
  cluster_id           = "{cluster.cluster_id}"
  engine               = "{cluster.engine}"
  engine_version       = "{cluster.engine_version}"
  node_type            = "{cluster.node_type}"
  num_cache_nodes      = {cluster.num_nodes}
  parameter_group_name = "default.{cluster.engine}{cluster.engine_version[:3]}"
  port                 = {"6379" if cluster.engine == "redis" else "11211"}

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  snapshot_retention_limit = 7
  snapshot_window          = "03:00-05:00"

{_tags_block(cluster.tags)}
}}
'''
        blocks.append(block)
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# AI enhancement
# ---------------------------------------------------------------------------


def _enhance_with_claude(
    hcl_content: str,
    resource_summary: str,
    api_key: str | None = None,
) -> str:
    """Use Claude Haiku to add inline documentation and apply best practices."""
    if not _ANTHROPIC_AVAILABLE:
        return hcl_content

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return hcl_content

    try:
        client = anthropic.Anthropic(api_key=key)
        prompt = (
            f"You are a senior AWS infrastructure engineer. Review this Terraform HCL "
            f"generated from a live AWS environment scan. Add clear inline comments "
            f"explaining what each resource does and why each security setting is "
            f"configured that way. Do NOT change any resource names, IDs, or "
            f"configuration values. Only add or improve comments. Return only the "
            f"improved HCL with no extra explanation.\n\n"
            f"Context: {resource_summary}\n\n"
            f"```hcl\n{hcl_content}\n```"
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        enhanced = response.content[0].text
        # Strip markdown code fences if present
        if "```" in enhanced:
            match = re.search(r"```(?:hcl)?\n(.*?)```", enhanced, re.DOTALL)
            if match:
                enhanced = match.group(1)
        return enhanced.strip()
    except Exception as exc:
        logger.warning("Claude enhancement skipped: %s", exc)
        return hcl_content


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class TerraformGenerator:
    """
    Generates production-quality modular Terraform from an InfrastructureSnapshot.

    Outputs a structured directory:
        terraform/
            main.tf           — Root module calling all sub-modules
            variables.tf      — Shared variables
            providers.tf      — Provider and version constraints
            modules/
                ec2/          — EC2 instances
                rds/          — RDS instances
                s3/           — S3 buckets
                vpc/          — VPCs and networking
                lambda/       — Lambda functions
                eks/          — EKS clusters
                elasticache/  — ElastiCache clusters
    """

    def __init__(
        self,
        output_dir: str | Path,
        anthropic_api_key: str | None = None,
        enhance_with_ai: bool = True,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._api_key = anthropic_api_key
        self._enhance = enhance_with_ai

    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.debug("Wrote %s (%d bytes)", path, len(content))

    def _generate_module(
        self,
        module_name: str,
        main_hcl: str,
        resource_summary: str,
    ) -> TerraformModule:
        module = TerraformModule(
            name=module_name,
            path=str(self._output_dir / "modules" / module_name),
        )
        if self._enhance and main_hcl.strip():
            main_hcl = _enhance_with_claude(main_hcl, resource_summary, self._api_key)
        module.files["main.tf"] = main_hcl
        module.files["variables.tf"] = _variables_tf()
        return module

    def _root_main_tf(self, snapshot: InfrastructureSnapshot, modules: list[str]) -> str:
        region = snapshot.regions[0] if snapshot.regions else "us-east-1"
        lines = [
            f'# CloudIQ Generated Terraform — Account {snapshot.account_id}',
            f'# Scanned at: {snapshot.scanned_at.isoformat()}',
            f'# Regions: {", ".join(snapshot.regions)}',
            f'# Total resources: {sum(snapshot.resource_counts.values())}',
            '',
        ]
        for mod in modules:
            lines += [
                f'module "{mod}" {{',
                f'  source      = "./modules/{mod}"',
                f'  aws_region  = var.aws_region',
                f'  environment = var.environment',
                f'  common_tags = var.common_tags',
                f'}}',
                '',
            ]
        return "\n".join(lines)

    def generate(self, snapshot: InfrastructureSnapshot) -> TerraformOutput:
        """
        Generate the full Terraform module tree from a snapshot.

        Returns a TerraformOutput describing what was written to disk.
        """
        output = TerraformOutput(root_dir=self._output_dir)

        service_map: dict[str, tuple[str, Any]] = {
            "ec2": (
                "EC2 Instances",
                _ec2_hcl(snapshot.ec2_instances),
            ),
            "rds": (
                "RDS Instances",
                _rds_hcl(snapshot.rds_instances),
            ),
            "s3": (
                "S3 Buckets",
                _s3_hcl(snapshot.s3_buckets),
            ),
            "vpc": (
                "VPC Networking",
                _vpc_hcl(snapshot.vpcs),
            ),
            "lambda": (
                "Lambda Functions",
                _lambda_hcl(snapshot.lambda_functions),
            ),
            "eks": (
                "EKS Clusters",
                _eks_hcl(snapshot.eks_clusters),
            ),
            "elasticache": (
                "ElastiCache Clusters",
                _elasticache_hcl(snapshot.elasticache_clusters),
            ),
        }

        active_modules: list[str] = []
        total_resources = 0

        for mod_name, (summary, hcl) in service_map.items():
            if not hcl.strip():
                continue
            module = self._generate_module(mod_name, hcl, summary)
            module_path = self._output_dir / "modules" / mod_name
            for filename, content in module.files.items():
                self._write_file(module_path / filename, content)
            output.modules.append(module)
            active_modules.append(mod_name)
            resource_count = hcl.count('\nresource "')
            total_resources += resource_count

        # Root files
        self._write_file(
            self._output_dir / "main.tf",
            self._root_main_tf(snapshot, active_modules),
        )
        self._write_file(
            self._output_dir / "variables.tf",
            _variables_tf(),
        )
        self._write_file(
            self._output_dir / "providers.tf",
            _providers_tf(snapshot.regions),
        )
        self._write_file(
            self._output_dir / "terraform.tfvars.example",
            (
                f'aws_region  = "{snapshot.regions[0] if snapshot.regions else "us-east-1"}"\n'
                f'environment = "production"\n'
                f'common_tags = {{\n'
                f'  ManagedBy   = "terraform"\n'
                f'  GeneratedBy = "cloudiq"\n'
                f'}}\n'
            ),
        )

        output.total_resources = total_resources
        return output
