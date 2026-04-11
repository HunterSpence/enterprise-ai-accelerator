"""
agent_ops/demo.py

Demo runner for AgentOps — no real AWS credentials required.
Uses realistic sample data to demonstrate the full multi-agent pipeline.

Run:
    python -m agent_ops.demo
    # or with an explicit API key:
    ANTHROPIC_API_KEY=sk-ant-... python -m agent_ops.demo
"""

from __future__ import annotations

import asyncio
import os
import sys

import anthropic
from rich.console import Console
from rich.panel import Panel

from agent_ops.dashboard import Dashboard
from agent_ops.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Sample enterprise data (realistic but fictional)
# ---------------------------------------------------------------------------

DEMO_TASK = (
    "Analyze our AWS environment and produce a board-ready transformation report. "
    "We need to understand our infrastructure risk posture, plan workload migrations "
    "to modernize our stack, check compliance gaps before our SOC 2 audit next quarter, "
    "and give the board clear priorities for the next 90 days."
)

DEMO_CONFIG = {
    "aws_config": {
        "account_id": "123456789012",
        "regions": ["us-east-1", "us-west-2"],
        "resources": {
            "ec2_instances": [
                {
                    "id": "i-0a1b2c3d4e5f",
                    "type": "m5.xlarge",
                    "region": "us-east-1",
                    "name": "prod-web-01",
                    "os": "Amazon Linux 2",
                    "public_ip": "54.210.100.1",
                    "security_groups": ["sg-open-all-traffic"],
                    "avg_cpu_util_pct": 8,
                    "storage_gb": 500,
                    "storage_util_pct": 12,
                    "tags": {"Environment": "prod", "Owner": "ops-team"},
                },
                {
                    "id": "i-0b2c3d4e5f6g",
                    "type": "r5.2xlarge",
                    "region": "us-east-1",
                    "name": "prod-db-01",
                    "os": "RHEL 7",
                    "public_ip": None,
                    "security_groups": ["sg-db-access"],
                    "avg_cpu_util_pct": 15,
                    "storage_gb": 2000,
                    "storage_util_pct": 72,
                    "tags": {"Environment": "prod", "Owner": "data-team"},
                },
                {
                    "id": "i-0c3d4e5f6g7h",
                    "type": "t3.micro",
                    "region": "us-west-2",
                    "name": "dev-batch-runner",
                    "os": "Ubuntu 18.04",
                    "public_ip": "52.88.200.5",
                    "security_groups": ["sg-dev-wide-open"],
                    "avg_cpu_util_pct": 3,
                    "storage_gb": 100,
                    "storage_util_pct": 5,
                    "tags": {"Environment": "dev"},
                },
            ],
            "s3_buckets": [
                {
                    "name": "acme-prod-customer-data",
                    "region": "us-east-1",
                    "public_access_blocked": False,
                    "versioning": False,
                    "encryption": "AES-256",
                    "size_gb": 850,
                    "object_count": 2400000,
                },
                {
                    "name": "acme-backups",
                    "region": "us-east-1",
                    "public_access_blocked": True,
                    "versioning": True,
                    "encryption": "aws:kms",
                    "size_gb": 3200,
                    "object_count": 180000,
                },
            ],
            "rds_instances": [
                {
                    "id": "db-prod-postgres-01",
                    "engine": "postgres 11.18",
                    "instance_class": "db.r5.large",
                    "multi_az": False,
                    "publicly_accessible": False,
                    "storage_gb": 500,
                    "automated_backups": True,
                    "backup_retention_days": 3,
                },
            ],
            "iam": {
                "root_mfa_enabled": False,
                "users_without_mfa": 12,
                "overly_permissive_policies": ["AcmePowerUser", "DevAdminFull"],
                "access_keys_over_90_days": 8,
            },
            "load_balancers": [
                {
                    "id": "alb-prod-001",
                    "type": "application",
                    "scheme": "internet-facing",
                    "listeners": [{"port": 80, "protocol": "HTTP"}],
                }
            ],
        },
    },
    "workload_inventory": [
        {
            "name": "Customer Portal",
            "type": "web_application",
            "stack": "Java 8 / Spring Boot / Oracle DB",
            "deployment": "EC2 + RDS (Oracle)",
            "business_criticality": "critical",
            "monthly_cost_usd": 4200,
            "dependencies": ["payments-api", "notification-service"],
            "notes": "Legacy Java 8, Oracle license expensive, team wants to modernize",
        },
        {
            "name": "Payments API",
            "type": "microservice",
            "stack": "Node.js 14 / PostgreSQL",
            "deployment": "EC2 Auto Scaling",
            "business_criticality": "critical",
            "monthly_cost_usd": 2800,
            "dependencies": ["stripe-gateway"],
            "notes": "PCI-DSS in scope. Could containerize.",
        },
        {
            "name": "Data Warehouse",
            "type": "analytics",
            "stack": "Redshift + Glue ETL",
            "deployment": "Managed AWS",
            "business_criticality": "high",
            "monthly_cost_usd": 8500,
            "dependencies": ["customer-db", "product-catalog"],
            "notes": "Already on managed service. Optimize partitioning.",
        },
        {
            "name": "Email Campaign Service",
            "type": "batch_processing",
            "stack": "Python 3.8 / SES",
            "deployment": "EC2 cron jobs",
            "business_criticality": "medium",
            "monthly_cost_usd": 600,
            "dependencies": ["ses", "customer-db"],
            "notes": "Cron-based, ideal Lambda candidate",
        },
        {
            "name": "Internal HR Portal",
            "type": "web_application",
            "stack": "PHP 7.2 / MySQL",
            "deployment": "Single EC2 instance",
            "business_criticality": "low",
            "monthly_cost_usd": 350,
            "dependencies": ["okta-sso"],
            "notes": "Vendor offers SaaS version (BambooHR). Could retire self-hosted.",
        },
        {
            "name": "Legacy Reporting Tool",
            "type": "reporting",
            "stack": "SSRS / SQL Server",
            "deployment": "On-prem VM (not yet in AWS)",
            "business_criticality": "low",
            "monthly_cost_usd": 0,
            "dependencies": ["finance-db"],
            "notes": "Team uses it twice a month. Business wants to retire by Q4.",
        },
    ],
    "iac_config": {
        "tool": "Terraform",
        "version": "1.5.7",
        "resources": [
            {
                "type": "aws_security_group",
                "name": "sg-open-all-traffic",
                "rules": [
                    {"type": "ingress", "from_port": 0, "to_port": 65535, "protocol": "-1", "cidr": "0.0.0.0/0"},
                    {"type": "egress", "from_port": 0, "to_port": 65535, "protocol": "-1", "cidr": "0.0.0.0/0"},
                ],
            },
            {
                "type": "aws_s3_bucket_public_access_block",
                "name": "acme-prod-customer-data",
                "block_public_acls": False,
                "block_public_policy": False,
                "ignore_public_acls": False,
                "restrict_public_buckets": False,
            },
            {
                "type": "aws_iam_policy",
                "name": "AcmePowerUser",
                "actions": ["*"],
                "resources": ["*"],
                "condition": None,
            },
            {
                "type": "aws_alb_listener",
                "name": "alb-prod-http",
                "port": 80,
                "protocol": "HTTP",
                "default_action": "forward",
                "note": "No HTTPS redirect configured",
            },
            {
                "type": "aws_db_instance",
                "name": "db-prod-postgres-01",
                "multi_az": False,
                "backup_retention_period": 3,
                "deletion_protection": False,
                "storage_encrypted": True,
                "engine_version": "11.18",
                "note": "PostgreSQL 11.x EOL Dec 2023",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

async def run_demo() -> None:
    console = Console()

    console.print()
    console.print(
        Panel(
            "[bold white]AgentOps — Multi-Agent Claude Orchestration[/bold white]\n\n"
            "[dim]Coordinator:[/dim]  [bold magenta]Claude Opus 4.6[/bold magenta]  (complex reasoning + task decomposition)\n"
            "[dim]Sub-agents:[/dim]   [bold cyan]Claude Haiku 4.5[/bold cyan]  (cost-efficient parallel workers)\n\n"
            "[dim]Agents:[/dim]  ArchitectureAgent  |  MigrationAgent  |  ComplianceAgent  |  ReportAgent\n"
            "[dim]Mode:[/dim]   asyncio.gather — all analysis agents run in parallel",
            title="[bold white on dark_blue]  enterprise-ai-accelerator  [/bold white on dark_blue]",
            border_style="dark_blue",
        )
    )
    console.print()
    console.print(f"[bold yellow]Task:[/bold yellow] {DEMO_TASK}\n")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[bold red]ERROR:[/bold red] ANTHROPIC_API_KEY environment variable not set.\n"
            "Set it and re-run:\n\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "  python -m agent_ops.demo\n"
        )
        sys.exit(1)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    dashboard = Dashboard(console=console)

    with dashboard.live_context():
        orchestrator = Orchestrator(client, on_activity=dashboard.on_activity)
        result = await orchestrator.run_pipeline(DEMO_TASK, DEMO_CONFIG)

    dashboard.render_final(result)


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
