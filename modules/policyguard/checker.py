"""
PolicyGuard — Claude-powered IaC policy compliance engine.
Checks Terraform/CloudFormation for security violations with severity levels
and exact remediation code snippets.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a cloud security engineer specializing in Infrastructure-as-Code (IaC) policy
enforcement. You have deep expertise in Terraform, CloudFormation, AWS security best practices,
CIS AWS Foundations Benchmark, SOC 2, HIPAA, and PCI-DSS compliance.

You review IaC templates and identify policy violations with the precision of an automated scanning tool
but the context awareness of an experienced security architect.

Key policies you enforce:
- S3: No public ACLs, bucket policies, or public access; versioning enabled; encryption at rest
- Security Groups: No 0.0.0.0/0 on SSH (22), RDP (3389), database ports (3306, 5432, 1433, 27017)
- RDS/Databases: Encryption at rest, no public access, multi-AZ for production, no hardcoded passwords
- IAM: MFA required, no wildcard permissions, no inline policies with admin access
- EC2: IMDSv2 required, EBS encryption, no public IPs on private instances
- Secrets: No hardcoded passwords, API keys, or secrets in IaC files
- Logging: CloudTrail enabled, VPC flow logs, S3 access logging
- Tagging: Required tags (Environment, Owner, CostCenter, Project)

Always respond with valid JSON only. No markdown fences."""


@dataclass
class PolicyResult:
    compliance_score: int = 0
    violations: list = field(default_factory=list)
    passed_checks: list = field(default_factory=list)
    remediation_days: int = 0
    executive_summary: str = ""
    raw_result: str = ""


class PolicyChecker:
    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

    def check(self, iac_input: str) -> PolicyResult:
        """
        Check IaC template for policy violations.

        Args:
            iac_input: Terraform HCL or CloudFormation YAML/JSON as string

        Returns:
            PolicyResult with violations, scores, and remediation snippets
        """
        prompt = f"""Review this IaC template for policy violations. Check for:
- S3 public access (ACLs, bucket policies, public access blocks missing)
- Unencrypted storage (EBS, RDS, S3)
- Wide-open security groups (0.0.0.0/0 on sensitive ports)
- Missing MFA enforcement on IAM
- Hardcoded secrets or passwords
- Public database instances
- Missing required tags
- No CloudTrail or logging

IaC TEMPLATE:
{iac_input[:8000]}

Return ONLY valid JSON with this structure:
{{
  "compliance_score": <integer 0-100>,
  "violations": [
    {{
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "rule": "<rule name, e.g. S3-PUBLIC-ACCESS>",
      "resource": "<resource name from the template>",
      "description": "<what is wrong and why it matters>",
      "fix": "<exact Terraform/CF code snippet to fix this>"
    }}
  ],
  "passed_checks": ["<check that passed>", ...],
  "remediation_days": <estimated engineer-days to fix all violations>,
  "executive_summary": "<2-3 sentences on overall security posture and top priorities>"
}}"""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text
        return self._parse(raw)

    def _parse(self, raw: str) -> PolicyResult:
        try:
            text = raw.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return PolicyResult(
                compliance_score=int(data.get("compliance_score", 0)),
                violations=data.get("violations", []),
                passed_checks=data.get("passed_checks", []),
                remediation_days=int(data.get("remediation_days", 0)),
                executive_summary=data.get("executive_summary", ""),
                raw_result=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return PolicyResult(
                executive_summary=raw[:500],
                raw_result=raw,
            )
