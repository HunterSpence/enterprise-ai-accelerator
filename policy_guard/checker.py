"""
PolicyGuard — AI-Powered IaC Compliance Checker

Checks Terraform, CloudFormation, and raw IaC files against compliance
frameworks (SOC2, HIPAA, PCI-DSS, CIS AWS Foundations) using Claude.
Returns scored findings with exact remediation steps.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ComplianceFinding:
    framework: str
    control_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    resource: str
    finding: str
    remediation: str
    terraform_fix: str = ""  # Exact Terraform code to fix it


@dataclass
class ComplianceResult:
    compliance_score: int  # 0-100
    frameworks_checked: list[str] = field(default_factory=list)
    critical_violations: list[ComplianceFinding] = field(default_factory=list)
    high_violations: list[ComplianceFinding] = field(default_factory=list)
    medium_violations: list[ComplianceFinding] = field(default_factory=list)
    passed_controls: list[str] = field(default_factory=list)
    remediation_priority: list[str] = field(default_factory=list)
    executive_summary: str = ""
    estimated_remediation_days: int = 0

    def print_summary(self):
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        
        console = Console()
        color = "green" if self.compliance_score >= 80 else "yellow" if self.compliance_score >= 60 else "red"
        console.print(Panel(
            f"Compliance Score: [{color}]{self.compliance_score}/100[/{color}]\n\n{self.executive_summary}",
            title="[bold]PolicyGuard Compliance Report",
            border_style="blue"
        ))
        
        if self.critical_violations:
            console.print(f"\n[bold red]Critical Violations ({len(self.critical_violations)}):")
            for v in self.critical_violations[:5]:
                console.print(f"  🔴 [{v.framework} {v.control_id}] {v.finding}")
                console.print(f"     Fix: {v.remediation}")
        
        if self.estimated_remediation_days:
            console.print(f"\n[bold]Estimated remediation: {self.estimated_remediation_days} days")


class PolicyChecker:
    """
    Checks infrastructure-as-code against compliance frameworks using Claude.
    
    Supported frameworks:
    - SOC2 (Type I and II)
    - HIPAA
    - PCI-DSS v4.0
    - CIS AWS Foundations Benchmark
    - NIST 800-53
    """
    
    SUPPORTED_FRAMEWORKS = ["SOC2", "HIPAA", "PCI-DSS", "CIS-AWS", "NIST-800-53"]
    
    SYSTEM_PROMPT = """You are a cloud security and compliance expert specializing in infrastructure-as-code 
security review. You have deep knowledge of SOC2, HIPAA, PCI-DSS, CIS AWS Foundations Benchmark, and NIST 800-53.

When reviewing IaC files you:
1. Map each finding to the specific control ID in the relevant framework
2. Provide exact Terraform/CloudFormation code to remediate each issue
3. Score compliance on a 0-100 scale based on control coverage
4. Prioritize findings by risk and remediation complexity
5. Distinguish between must-fix (blocking) and should-fix (advisory) items

You respond in valid JSON only."""
    
    def __init__(self, frameworks: Optional[list[str]] = None, model: Optional[str] = None):
        self.frameworks = frameworks or ["SOC2", "CIS-AWS"]
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
    
    def check(self, iac_input: str, file_type: str = "terraform") -> ComplianceResult:
        """
        Check IaC content for compliance violations.
        
        Args:
            iac_input: Terraform HCL, CloudFormation YAML/JSON, or file path
            file_type: terraform, cloudformation, or auto
        
        Returns:
            ComplianceResult with scored findings and remediation steps
        """
        if Path(iac_input).exists() if len(iac_input) < 500 else False:
            iac_content = Path(iac_input).read_text()
        else:
            iac_content = iac_input
        
        prompt = self._build_prompt(iac_content, file_type)
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=6144,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return self._parse_response(message.content[0].text)
    
    def check_directory(self, directory: str | Path) -> ComplianceResult:
        """Check all Terraform/CloudFormation files in a directory."""
        dir_path = Path(directory)
        files = list(dir_path.rglob("*.tf")) + list(dir_path.rglob("*.yaml")) + list(dir_path.rglob("*.json"))
        
        combined = "\n\n".join([
            f"# File: {f.name}\n{f.read_text()[:2000]}"
            for f in files[:10]  # Cap at 10 files
        ])
        
        return self.check(combined)
    
    def _build_prompt(self, iac: str, file_type: str) -> str:
        frameworks_str = ", ".join(self.frameworks)
        return f"""Check the following {file_type} code for compliance violations against: {frameworks_str}

IAC CODE:
{iac[:6000]}

Return ONLY valid JSON:
{{
  "compliance_score": <0-100>,
  "frameworks_checked": {json.dumps(self.frameworks)},
  "critical_violations": [
    {{
      "framework": "SOC2",
      "control_id": "CC6.1",
      "severity": "CRITICAL",
      "resource": "aws_s3_bucket.data",
      "finding": "S3 bucket has public read access enabled",
      "remediation": "Set block_public_acls = true and restrict_public_buckets = true",
      "terraform_fix": "resource aws_s3_bucket_public_access_block example {{ bucket = aws_s3_bucket.data.id block_public_acls = true }}"
    }}
  ],
  "high_violations": [],
  "medium_violations": [],
  "passed_controls": ["control descriptions that passed"],
  "remediation_priority": ["ordered list of most important fixes"],
  "executive_summary": "2-3 sentences for CISO/CTO",
  "estimated_remediation_days": <int>
}}"""
    
    def _parse_response(self, raw: str) -> ComplianceResult:
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            
            data = json.loads(clean)
            
            def parse_findings(items):
                return [ComplianceFinding(
                    framework=f.get("framework", ""),
                    control_id=f.get("control_id", ""),
                    severity=f.get("severity", "MEDIUM"),
                    resource=f.get("resource", ""),
                    finding=f.get("finding", ""),
                    remediation=f.get("remediation", ""),
                    terraform_fix=f.get("terraform_fix", "")
                ) for f in items]
            
            return ComplianceResult(
                compliance_score=data.get("compliance_score", 0),
                frameworks_checked=data.get("frameworks_checked", []),
                critical_violations=parse_findings(data.get("critical_violations", [])),
                high_violations=parse_findings(data.get("high_violations", [])),
                medium_violations=parse_findings(data.get("medium_violations", [])),
                passed_controls=data.get("passed_controls", []),
                remediation_priority=data.get("remediation_priority", []),
                executive_summary=data.get("executive_summary", ""),
                estimated_remediation_days=data.get("estimated_remediation_days", 0)
            )
        except (json.JSONDecodeError, KeyError):
            return ComplianceResult(compliance_score=0, executive_summary=raw[:500])
