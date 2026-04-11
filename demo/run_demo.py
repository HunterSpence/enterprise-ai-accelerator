"""
Enterprise AI Accelerator — Full Pipeline Demo

Runs all 4 modules in sequence on sample data:
1. CloudIQ — Architecture analysis
2. MigrationScout — Migration planning  
3. PolicyGuard — Compliance check
4. ExecutiveReport — Board-ready report

Run: python demo/run_demo.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import time

console = Console()

SAMPLE_AWS_CONFIG = """
AWS Production — ACME Financial Services
- 6x m5.4xlarge EC2 (avg CPU: 11%, avg mem: 14%) — running 24/7
- RDS MySQL 5.7 (EoL), Multi-AZ: No, Encryption at rest: No
- 2 S3 buckets with public read access enabled (includes customer data bucket)
- IAM: 4 users with AdministratorAccess, no MFA enforced, 6 stale access keys
- No CloudTrail logging in us-west-2 region
- No GuardDuty or SecurityHub
- Security groups: all EC2 instances allow SSH from 0.0.0.0/0
- Monthly spend: $41,000. No reserved instances. No savings plans.
- Single AZ deployment, no DR plan
"""

SAMPLE_WORKLOADS = [
    {"name": "Billing System", "description": "Legacy Java 8 billing on Oracle 11g, EoL, critical"},
    {"name": "Customer Portal", "description": "React + Spring Boot, modern, customer-facing"},
    {"name": "Data Warehouse", "description": "Teradata on-prem, 15TB, heavy batch reporting"},
    {"name": "Email Gateway", "description": "Postfix on CentOS 6, internal only, low criticality"},
    {"name": "Auth Service", "description": "Active Directory + LDAP, critical dependency for all apps"},
    {"name": "Analytics Pipeline", "description": "Kafka + Spark streaming, modern stack, stateless"},
    {"name": "HR Portal", "description": "PHP 7 + MySQL, internal only, low business value"},
    {"name": "Compliance Archive", "description": "7-year regulatory retention, cold storage, 50TB"},
]

SAMPLE_TERRAFORM = """
resource "aws_s3_bucket" "customer_data" {
  bucket = "acme-customer-data-prod"
  acl    = "public-read"
}

resource "aws_db_instance" "primary" {
  engine            = "mysql"
  engine_version    = "5.7"
  storage_encrypted = false
  multi_az          = false
  backup_retention_period = 1
}

resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_user" "admin" {
  name = "admin"
}

resource "aws_iam_user_policy_attachment" "admin_policy" {
  user       = aws_iam_user.admin.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
"""


def main():
    console.print("\n[bold blue]Enterprise AI Accelerator — Full Pipeline Demo[/bold blue]")
    console.print("=" * 60)
    console.print("Company: ACME Financial Services")
    console.print("Analysis: Architecture + Migration + Compliance + Exec Report\n")
    
    # Step 1: CloudIQ
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]CloudIQ: Analyzing architecture...", total=None)
        
        from cloudiq import CloudIQAnalyzer
        analyzer = CloudIQAnalyzer()
        arch_result = analyzer.analyze(SAMPLE_AWS_CONFIG, context="Financial services, SOC2 + PCI-DSS required")
        
        progress.update(task, description="[green]CloudIQ: Complete")
    
    arch_result.print_summary()
    
    # Step 2: MigrationScout
    console.print("\n")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]MigrationScout: Planning migration...", total=None)
        
        from migration_scout import MigrationPlanner
        planner = MigrationPlanner()
        migration_plan = planner.plan(SAMPLE_WORKLOADS, context="Target AWS, 12-month timeline, 6-person team")
        
        progress.update(task, description="[green]MigrationScout: Complete")
    
    migration_plan.print_summary()
    
    # Step 3: PolicyGuard
    console.print("\n")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]PolicyGuard: Checking compliance...", total=None)
        
        from policy_guard import PolicyChecker
        checker = PolicyChecker(frameworks=["SOC2", "PCI-DSS"])
        compliance_result = checker.check(SAMPLE_TERRAFORM)
        
        progress.update(task, description="[green]PolicyGuard: Complete")
    
    compliance_result.print_summary()
    
    # Step 4: Executive Report
    console.print("\n")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]ExecutiveReport: Generating board report...", total=None)
        
        from executive_report import ReportGenerator
        generator = ReportGenerator()
        report = generator.generate(
            data={},
            company_name="ACME Financial Services",
            audience="board",
            cloudiq_result=arch_result,
            migration_plan=migration_plan,
            compliance_result=compliance_result
        )
        
        output_path = report.save_html()
        progress.update(task, description="[green]ExecutiveReport: Complete")
    
    report.print_summary()
    
    console.print(f"\n[bold green]✅ Pipeline complete!")
    console.print(f"Board report saved: [cyan]{output_path}[/cyan]")
    console.print("\nOpen output/ACME_Financial_Services_report.html in your browser.")


if __name__ == "__main__":
    main()
