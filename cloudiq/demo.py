"""
CloudIQ Demo — Analyzes a sample enterprise AWS configuration.
Run: python cloudiq/demo.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cloudiq import CloudIQAnalyzer

# Sample AWS configuration representing a typical mid-size enterprise
# with intentional security gaps and cost inefficiencies
SAMPLE_CONFIG = """
AWS Architecture — ACME Corp Production Environment

EC2 Instances:
- 4x m5.4xlarge web servers (avg CPU: 12%, avg memory: 18%)
- 2x r5.2xlarge database servers (running MySQL 5.7, EoL)
- 1x c5.9xlarge batch processing server (runs 2 hours/day)

Storage:
- 3 S3 buckets: prod-data (public read enabled), prod-backups, prod-assets
- EBS volumes: 8TB total, 60% utilized
- No lifecycle policies configured
- Backups: manual, weekly

Networking:
- VPC with /16 CIDR, single AZ
- Security groups: web servers allow 0.0.0.0/0 on port 22
- No WAF configured
- NAT Gateway in single AZ

Database:
- RDS MySQL 5.7 (End-of-Life Oct 2023), Multi-AZ: No
- Encryption at rest: No
- Automated backups: 1-day retention
- Parameter group: default

IAM:
- 12 IAM users with console access
- 3 users with AdministratorAccess policy
- No MFA enforced
- Access keys: 4 keys older than 365 days
- No SCPs configured

Monitoring:
- CloudWatch: basic monitoring only
- No CloudTrail in 2 regions
- No GuardDuty
- No SecurityHub

Cost:
- Monthly spend: ~$28,000
- Reserved instances: None
- Savings Plans: None
"""

def main():
    print("CloudIQ — Enterprise Cloud Architecture Analysis")
    print("=" * 60)
    print("Analyzing ACME Corp production environment...\n")
    
    analyzer = CloudIQAnalyzer()
    result = analyzer.analyze(SAMPLE_CONFIG, context="Mid-size enterprise, financial services, SOC2 compliance required")
    result.print_summary()
    
    print("\n" + "=" * 60)
    print(f"Analysis complete. Full report saved to output/cloudiq_demo.json")
    
    import json
    from pathlib import Path
    Path("output").mkdir(exist_ok=True)
    with open("output/cloudiq_demo.json", "w") as f:
        json.dump({
            "security_score": result.security_score,
            "cost_score": result.cost_score,
            "migration_readiness": result.migration_readiness,
            "critical_findings": result.critical_findings,
            "cost_waste_monthly": result.cost_waste_monthly,
            "recommendations": result.recommendations,
            "executive_summary": result.executive_summary
        }, f, indent=2)

if __name__ == "__main__":
    main()
