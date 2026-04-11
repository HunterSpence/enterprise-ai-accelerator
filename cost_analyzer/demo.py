"""
CostAnalyzer Demo — Finds savings in a sample enterprise AWS environment.
Run: python cost_analyzer/demo.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cost_analyzer import CostAnalyzer

SAMPLE_INFRA = """
AWS Production — Global Manufacturing Corp
Monthly spend: ~$67,000

Compute:
- 12x m5.4xlarge (16 vCPU / 64GB) — average CPU utilization: 8%, peak: 22%
- 4x r5.8xlarge (32 vCPU / 256GB) database servers — average 14% CPU
- 1x c5.18xlarge for batch jobs — runs 3 hours/day (billed 24/7)
- All instances on On-Demand pricing. No Reserved Instances. No Savings Plans.
- 6 instances running in us-east-1 and us-west-2 simultaneously (disaster recovery)
  that haven't been tested in 14 months

Storage:
- 45TB S3 (Standard tier) — access logs show 60% not accessed in 12+ months
- 12TB EBS — 40% snapshots older than 90 days never deleted
- No lifecycle policies configured on any S3 bucket
- Versioning enabled on all buckets with no expiration rules

Database:
- RDS Aurora MySQL: Multi-AZ, 2x db.r5.4xlarge — development team queries it
  directly (no query optimization, no read replicas for reporting)
- RDS PostgreSQL: db.r5.2xlarge for analytics — 80% of queries are full table scans
- ElastiCache Redis: 3x cache.r5.xlarge — hit rate 23% (very low)

Networking:
- NAT Gateway: 8TB/month outbound through NAT
- Data Transfer: 15TB/month cross-region (us-east-1 to us-west-2 primarily)
- CloudFront not enabled for any static assets (all served directly from S3)

Other:
- 4 unused Elastic IP addresses (unattached)
- 3 idle load balancers with no registered targets
- CloudWatch detailed monitoring on all instances (basic would suffice for most)
- Multiple unused VPC endpoints incurring hourly charges
"""

def main():
    print("CostAnalyzer — Enterprise Cloud Cost Optimization")
    print("=" * 60)
    print("Analyzing Global Manufacturing Corp AWS environment...\n")
    
    analyzer = CostAnalyzer()
    result = analyzer.analyze(SAMPLE_INFRA, monthly_spend=67000)
    result.print_summary()
    
    import json
    from pathlib import Path
    Path("output").mkdir(exist_ok=True)
    with open("output/cost_analysis_demo.json", "w") as f:
        json.dump({
            "total_monthly_spend": result.total_monthly_spend,
            "total_savings_monthly": result.total_savings_monthly,
            "total_savings_annual": result.total_savings_annual,
            "savings_percentage": result.savings_percentage,
            "quick_wins_count": len(result.quick_wins),
            "roi_months": result.roi_months,
            "three_year_savings": result.three_year_savings,
            "executive_summary": result.executive_summary,
            "financial_narrative": result.financial_narrative
        }, f, indent=2)
    print(f"\nFull analysis saved to output/cost_analysis_demo.json")

if __name__ == "__main__":
    main()
