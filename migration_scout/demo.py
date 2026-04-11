"""
MigrationScout Demo — Plans a 20-workload enterprise migration.
Run: python migration_scout/demo.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from migration_scout import MigrationPlanner

SAMPLE_INVENTORY = """
name,description,tech_stack,team_size,criticality
Payroll System,SAP HR payroll processing,SAP on Oracle DB,4,Critical
CRM Platform,Salesforce custom implementation,Salesforce + custom Java,3,High
Legacy Billing,Custom billing system from 2008,Java 8 + Oracle 11g,6,Critical
Email Gateway,Internal email relay server,Postfix on RHEL 7,1,Medium
Data Warehouse,Business intelligence platform,Teradata + Cognos,5,High
HR Portal,Employee self-service web app,PHP 7 + MySQL 5.6,2,Medium
Inventory Management,Real-time inventory tracking,Node.js + MongoDB,3,High
Reporting Engine,Nightly batch reports,Python 2.7 + Oracle,2,Low
Authentication Service,LDAP + Active Directory,OpenLDAP on CentOS 6,2,Critical
Content Management,Internal wiki and docs,Confluence + PostgreSQL,1,Low
API Gateway,Microservices routing layer,nginx + custom scripts,2,High
Customer Portal,External-facing web app,React + Java Spring,4,High
Analytics Pipeline,Real-time event processing,Kafka + Spark,3,High
Document Storage,File server and archival,Windows File Server,1,Low
Monitoring Stack,Application performance monitoring,Nagios + custom,1,Medium
Dev Toolchain,CI/CD and development tools,Jenkins + Artifactory,2,Medium
ERP System,Enterprise resource planning,SAP S/4HANA,8,Critical
Mobile Backend,iOS/Android API backend,Python Django + MySQL,3,High
Legacy ETL,Data transformation pipelines,Informatica + Oracle,4,Medium
Compliance Archive,Regulatory document archival,custom Java + NFS,2,Low
"""

def main():
    print("MigrationScout — Enterprise Cloud Migration Planner")
    print("=" * 60)
    print("Planning migration for 20-workload enterprise environment...\n")
    
    planner = MigrationPlanner()
    plan = planner.plan(
        SAMPLE_INVENTORY,
        context="Target: AWS. Timeline: 18 months. Compliance: SOC2, GDPR. Team: 8 engineers."
    )
    plan.print_summary()
    
    import json
    from pathlib import Path
    Path("output").mkdir(exist_ok=True)
    with open("output/migration_plan_demo.json", "w") as f:
        json.dump({
            "total_workloads": len(plan.workloads),
            "total_effort_weeks": plan.total_effort_weeks,
            "estimated_duration_months": plan.estimated_duration_months,
            "strategy_breakdown": plan.strategy_breakdown(),
            "quick_wins": plan.quick_wins,
            "migration_blockers": plan.migration_blockers,
            "executive_summary": plan.executive_summary,
            "risk_register": plan.risk_register[:5]
        }, f, indent=2)
    
    print(f"\nFull plan saved to output/migration_plan_demo.json")

if __name__ == "__main__":
    main()
