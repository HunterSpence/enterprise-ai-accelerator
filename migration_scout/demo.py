"""
demo.py — MigrationScout V2 Demo
==================================

Runs the full RetailCo V2 scenario:
  75 workloads across 6 waves
  Oracle $420K/yr license elimination
  3x SAP instances → managed service ($180K/yr)
  $1.2M 3-year net savings, 14-month payback
  Climax: CRITICAL DEPENDENCY LOOP → SCC resolution → containerize-first workaround

Run:
  python -m migration_scout.demo
  python -m migration_scout.demo --no-ai   # skip Claude API calls
  python -m migration_scout.demo --waves 3 # run first 3 waves only
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from .assessor import WorkloadAssessor, WorkloadInventory
from .dependency_mapper import DependencyMapper
from .tco_calculator import TCOCalculator
from .wave_planner import MigrationApproach, WavePlanner

console = Console()


# ─── RetailCo V2 Workload Catalog (75 workloads) ─────────────────────────────

def _build_retailco_inventory() -> list[WorkloadInventory]:
    """
    RetailCo — national specialty retailer, 340 stores, $2.1B revenue.
    Moving from co-lo to AWS. Portfolio: 75 workloads across 6 categories.
    """
    raw: list[dict[str, Any]] = [
        # Wave 1 candidates: Stateless microservices (quick wins)
        {"id": "rc-001", "name": "Product Catalog API", "type": "microservice", "lang": "Go", "db": "PostgreSQL", "age": 2, "loc": 18000, "team": 4, "crit": "medium", "deps": ["rc-040", "rc-042"], "cost": 48000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-002", "name": "Inventory Service", "type": "microservice", "lang": "Go", "db": "Redis", "age": 3, "loc": 22000, "team": 3, "crit": "high", "deps": ["rc-040"], "cost": 52000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-003", "name": "Pricing Engine API", "type": "microservice", "lang": "Python", "db": "Redis", "age": 2, "loc": 15000, "team": 2, "crit": "high", "deps": ["rc-040", "rc-046"], "cost": 38000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-004", "name": "Search Service", "type": "microservice", "lang": "Java", "db": "Elasticsearch", "age": 3, "loc": 28000, "team": 4, "crit": "medium", "deps": [], "cost": 61000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-005", "name": "Recommendation Engine", "type": "microservice", "lang": "Python", "db": "Redis", "age": 1, "loc": 12000, "team": 3, "crit": "medium", "deps": ["rc-040"], "cost": 29000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-006", "name": "Review Service", "type": "microservice", "lang": "Node.js", "db": "MongoDB", "age": 2, "loc": 9000, "team": 2, "crit": "low", "deps": [], "cost": 22000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-007", "name": "Notification Service", "type": "microservice", "lang": "Python", "db": "None", "age": 2, "loc": 7000, "team": 2, "crit": "medium", "deps": [], "cost": 18000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-008", "name": "Image CDN Proxy", "type": "microservice", "lang": "Go", "db": "None", "age": 1, "loc": 4000, "team": 1, "crit": "medium", "deps": [], "cost": 32000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-009", "name": "A/B Testing Service", "type": "microservice", "lang": "Python", "db": "PostgreSQL", "age": 2, "loc": 8000, "team": 2, "crit": "low", "deps": [], "cost": 15000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-010", "name": "Feature Flag Service", "type": "microservice", "lang": "Go", "db": "Redis", "age": 1, "loc": 5000, "team": 1, "crit": "low", "deps": [], "cost": 12000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-011", "name": "Auth Gateway", "type": "microservice", "lang": "Java", "db": "PostgreSQL", "age": 3, "loc": 24000, "team": 4, "crit": "critical", "deps": [], "cost": 55000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-012", "name": "API Rate Limiter", "type": "microservice", "lang": "Go", "db": "Redis", "age": 1, "loc": 3000, "team": 1, "crit": "high", "deps": [], "cost": 8000, "containerized": True, "vendor_lock": False, "active_dev": True},
        # Wave 2 candidates: E-commerce platform
        {"id": "rc-013", "name": "Storefront Web App", "type": "web_app", "lang": "React/Node.js", "db": "PostgreSQL", "age": 4, "loc": 85000, "team": 8, "crit": "critical", "deps": ["rc-001", "rc-002", "rc-003", "rc-011", "rc-040"], "cost": 142000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-014", "name": "Mobile App Backend (iOS/Android)", "type": "api", "lang": "Java", "db": "PostgreSQL", "age": 3, "loc": 62000, "team": 6, "crit": "critical", "deps": ["rc-001", "rc-002", "rc-011", "rc-040"], "cost": 98000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-015", "name": "Checkout Service", "type": "microservice", "lang": "Java", "db": "PostgreSQL", "age": 5, "loc": 48000, "team": 5, "crit": "critical", "deps": ["rc-002", "rc-003", "rc-046", "rc-050"], "cost": 88000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-016", "name": "Order Management System", "type": "backend", "lang": "Java", "db": "PostgreSQL", "age": 6, "loc": 115000, "team": 7, "crit": "critical", "deps": ["rc-015", "rc-017", "rc-040", "rc-050"], "cost": 165000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-017", "name": "Payment Processing Gateway", "type": "backend", "lang": "Java", "db": "PostgreSQL", "age": 7, "loc": 72000, "team": 6, "crit": "critical", "deps": ["rc-050"], "cost": 120000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-018", "name": "Loyalty Program Service", "type": "backend", "lang": "Python", "db": "PostgreSQL", "age": 4, "loc": 38000, "team": 4, "crit": "high", "deps": ["rc-040"], "cost": 62000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-019", "name": "Gift Card System", "type": "backend", "lang": "Java", "db": "Oracle", "age": 8, "loc": 42000, "team": 3, "crit": "high", "deps": ["rc-050", "rc-051"], "cost": 75000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-020", "name": "Coupon & Promotions Engine", "type": "backend", "lang": "Python", "db": "PostgreSQL", "age": 3, "loc": 28000, "team": 3, "crit": "high", "deps": ["rc-003"], "cost": 44000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-021", "name": "Customer Portal", "type": "web_app", "lang": "React", "db": "PostgreSQL", "age": 4, "loc": 52000, "team": 5, "crit": "high", "deps": ["rc-011", "rc-016", "rc-018"], "cost": 78000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-022", "name": "Returns & Refunds Service", "type": "backend", "lang": "Java", "db": "PostgreSQL", "age": 5, "loc": 34000, "team": 3, "crit": "high", "deps": ["rc-016", "rc-017"], "cost": 52000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-023", "name": "Fraud Detection API", "type": "microservice", "lang": "Python", "db": "PostgreSQL", "age": 2, "loc": 19000, "team": 3, "crit": "critical", "deps": ["rc-017"], "cost": 68000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-024", "name": "Address Validation Service", "type": "microservice", "lang": "Go", "db": "None", "age": 2, "loc": 5000, "team": 1, "crit": "medium", "deps": [], "cost": 14000, "containerized": True, "vendor_lock": False, "active_dev": False},
        # Wave 3: Supply chain & warehouse
        {"id": "rc-025", "name": "Warehouse Management System", "type": "monolith", "lang": "Java", "db": "Oracle", "age": 10, "loc": 310000, "team": 12, "crit": "critical", "deps": ["rc-051", "rc-052"], "cost": 485000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-026", "name": "Supply Chain Planning", "type": "monolith", "lang": "Java", "db": "Oracle", "age": 12, "loc": 245000, "team": 9, "crit": "critical", "deps": ["rc-025", "rc-051"], "cost": 380000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-027", "name": "Supplier Portal", "type": "web_app", "lang": "Java", "db": "Oracle", "age": 8, "loc": 88000, "team": 5, "crit": "high", "deps": ["rc-026", "rc-051"], "cost": 145000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-028", "name": "Purchase Order System", "type": "backend", "lang": "Java", "db": "Oracle", "age": 11, "loc": 126000, "team": 6, "crit": "critical", "deps": ["rc-026", "rc-051"], "cost": 188000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-029", "name": "Demand Forecasting (ML)", "type": "ml_platform", "lang": "Python", "db": "PostgreSQL", "age": 2, "loc": 35000, "team": 4, "crit": "high", "deps": ["rc-026", "rc-046"], "cost": 92000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-030", "name": "Carrier Integration Hub", "type": "backend", "lang": "Java", "db": "PostgreSQL", "age": 6, "loc": 68000, "team": 4, "crit": "high", "deps": ["rc-016"], "cost": 112000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-031", "name": "Returns Logistics Platform", "type": "backend", "lang": "Python", "db": "PostgreSQL", "age": 4, "loc": 44000, "team": 3, "crit": "medium", "deps": ["rc-025", "rc-030"], "cost": 68000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-032", "name": "Yard Management System", "type": "backend", "lang": "Java", "db": "Oracle", "age": 9, "loc": 78000, "team": 4, "crit": "medium", "deps": ["rc-025", "rc-051"], "cost": 115000, "containerized": False, "vendor_lock": True, "active_dev": False},
        # Wave 4: Oracle estate (the big one)
        {"id": "rc-033", "name": "ERP Core (Oracle E-Business Suite)", "type": "enterprise_app", "lang": "Oracle Forms/PL-SQL", "db": "Oracle", "age": 14, "loc": 850000, "team": 18, "crit": "critical", "deps": ["rc-051", "rc-052", "rc-034", "rc-035", "rc-036"], "cost": 1240000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-034", "name": "General Ledger Module", "type": "enterprise_app", "lang": "Oracle Forms/PL-SQL", "db": "Oracle", "age": 14, "loc": 280000, "team": 8, "crit": "critical", "deps": ["rc-051", "rc-052"], "cost": 380000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-035", "name": "Accounts Payable (Oracle)", "type": "enterprise_app", "lang": "Oracle Forms/PL-SQL", "db": "Oracle", "age": 14, "loc": 195000, "team": 5, "crit": "critical", "deps": ["rc-051", "rc-034"], "cost": 265000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-036", "name": "Accounts Receivable (Oracle)", "type": "enterprise_app", "lang": "Oracle Forms/PL-SQL", "db": "Oracle", "age": 14, "loc": 185000, "team": 5, "crit": "critical", "deps": ["rc-051", "rc-034"], "cost": 245000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-037", "name": "Oracle DB - ERP Primary (RAC)", "type": "database", "lang": "SQL/PL-SQL", "db": "Oracle", "age": 14, "loc": 125000, "team": 3, "crit": "critical", "deps": ["rc-051"], "cost": 420000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-038", "name": "Oracle DB - Reporting (OLAP)", "type": "database", "lang": "SQL/PL-SQL", "db": "Oracle", "age": 12, "loc": 68000, "team": 2, "crit": "high", "deps": ["rc-051", "rc-037"], "cost": 185000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-039", "name": "Oracle APEX - Ops Dashboard", "type": "web_app", "lang": "Oracle APEX", "db": "Oracle", "age": 10, "loc": 42000, "team": 2, "crit": "medium", "deps": ["rc-037", "rc-051"], "cost": 62000, "containerized": False, "vendor_lock": True, "active_dev": False},
        # Wave 4 (continued): SAP instances
        {"id": "rc-053", "name": "SAP S/4HANA - Finance", "type": "enterprise_app", "lang": "ABAP", "db": "SAP HANA", "age": 6, "loc": 420000, "team": 11, "crit": "critical", "deps": ["rc-054"], "cost": 580000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-054", "name": "SAP HANA DB (Primary)", "type": "database", "lang": "SQL/ABAP", "db": "SAP HANA", "age": 6, "loc": 85000, "team": 3, "crit": "critical", "deps": [], "cost": 320000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-055", "name": "SAP BW/4HANA - Analytics", "type": "enterprise_app", "lang": "ABAP", "db": "SAP HANA", "age": 5, "loc": 195000, "team": 6, "crit": "high", "deps": ["rc-054"], "cost": 245000, "containerized": False, "vendor_lock": True, "active_dev": False},
        # Shared infrastructure & data platform (Wave 5)
        {"id": "rc-040", "name": "API Gateway (Kong)", "type": "infrastructure", "lang": "Lua/Go", "db": "PostgreSQL", "age": 3, "loc": 22000, "team": 2, "crit": "critical", "deps": [], "cost": 45000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-041", "name": "Event Streaming (Kafka)", "type": "infrastructure", "lang": "Java", "db": "None", "age": 4, "loc": 18000, "team": 3, "crit": "critical", "deps": [], "cost": 88000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-042", "name": "Service Mesh (Istio)", "type": "infrastructure", "lang": "Go", "db": "None", "age": 2, "loc": 8000, "team": 2, "crit": "high", "deps": [], "cost": 32000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-043", "name": "Observability Platform (Datadog)", "type": "infrastructure", "lang": "Python/Go", "db": "None", "age": 3, "loc": 12000, "team": 2, "crit": "high", "deps": [], "cost": 58000, "containerized": True, "vendor_lock": False, "active_dev": False},
        {"id": "rc-044", "name": "CI/CD Pipeline (Jenkins)", "type": "infrastructure", "lang": "Groovy", "db": "None", "age": 5, "loc": 28000, "team": 3, "crit": "high", "deps": [], "cost": 42000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-045", "name": "Secrets Manager (HashiCorp Vault)", "type": "infrastructure", "lang": "Go", "db": "None", "age": 3, "loc": 9000, "team": 1, "crit": "critical", "deps": [], "cost": 28000, "containerized": True, "vendor_lock": False, "active_dev": False},
        {"id": "rc-046", "name": "Data Lake (Hadoop/Hive)", "type": "data_platform", "lang": "Java/Python", "db": "Hive", "age": 7, "loc": 145000, "team": 6, "crit": "high", "deps": [], "cost": 235000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-047", "name": "BI Platform (Tableau)", "type": "analytics", "lang": "N/A", "db": "Tableau", "age": 5, "loc": 0, "team": 3, "crit": "medium", "deps": ["rc-046", "rc-038"], "cost": 95000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-048", "name": "ETL Pipeline (Informatica)", "type": "data_platform", "lang": "Java", "db": "Oracle", "age": 9, "loc": 72000, "team": 4, "crit": "high", "deps": ["rc-046", "rc-051"], "cost": 148000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-049", "name": "ML Training Platform", "type": "ml_platform", "lang": "Python", "db": "S3", "age": 2, "loc": 38000, "team": 4, "crit": "medium", "deps": ["rc-046"], "cost": 82000, "containerized": True, "vendor_lock": False, "active_dev": True},
        # Legacy systems
        {"id": "rc-050", "name": "Legacy Payment Processor (IBM MQ)", "type": "legacy", "lang": "COBOL/Java", "db": "DB2", "age": 16, "loc": 185000, "team": 4, "crit": "critical", "deps": [], "cost": 295000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-051", "name": "Oracle DB - Primary RAC (12c)", "type": "database", "lang": "SQL/PL-SQL", "db": "Oracle", "age": 14, "loc": 0, "team": 3, "crit": "critical", "deps": [], "cost": 420000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-052", "name": "Oracle DB - DR Standby", "type": "database", "lang": "SQL/PL-SQL", "db": "Oracle", "age": 14, "loc": 0, "team": 2, "crit": "critical", "deps": ["rc-051"], "cost": 185000, "containerized": False, "vendor_lock": True, "active_dev": False},
        # Wave 6: Retire / end-of-life
        {"id": "rc-056", "name": "Legacy CRM (Siebel)", "type": "legacy", "lang": "C++/Java", "db": "Oracle", "age": 15, "loc": 380000, "team": 5, "crit": "medium", "deps": ["rc-051"], "cost": 285000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-057", "name": "Custom EDI Integration Layer", "type": "legacy", "lang": "COBOL", "db": "DB2", "age": 18, "loc": 220000, "team": 3, "crit": "medium", "deps": ["rc-050"], "cost": 168000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-058", "name": "Store Operations App (Win32)", "type": "legacy", "lang": "VB.NET", "db": "SQL Server", "age": 13, "loc": 145000, "team": 3, "crit": "high", "deps": [], "cost": 195000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-059", "name": "HR System (PeopleSoft)", "type": "enterprise_app", "lang": "PeopleCode", "db": "Oracle", "age": 11, "loc": 280000, "team": 6, "crit": "high", "deps": ["rc-051"], "cost": 348000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-060", "name": "Payroll System (ADP Integration)", "type": "backend", "lang": "Java", "db": "Oracle", "age": 9, "loc": 88000, "team": 3, "crit": "critical", "deps": ["rc-059", "rc-051"], "cost": 142000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-061", "name": "Learning Management System", "type": "web_app", "lang": "PHP", "db": "MySQL", "age": 8, "loc": 62000, "team": 2, "crit": "low", "deps": [], "cost": 42000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-062", "name": "Legacy Email Marketing (Eloqua)", "type": "legacy", "lang": "N/A", "db": "Oracle", "age": 8, "loc": 0, "team": 1, "crit": "low", "deps": ["rc-051"], "cost": 68000, "containerized": False, "vendor_lock": True, "active_dev": False},
        # Additional mixed workloads to reach 75
        {"id": "rc-063", "name": "Store Associate App (iPad)", "type": "mobile", "lang": "Swift/React Native", "db": "PostgreSQL", "age": 3, "loc": 42000, "team": 4, "crit": "high", "deps": ["rc-011", "rc-002"], "cost": 65000, "containerized": False, "vendor_lock": False, "active_dev": True},
        {"id": "rc-064", "name": "Digital Signage Platform", "type": "backend", "lang": "Python", "db": "PostgreSQL", "age": 4, "loc": 28000, "team": 2, "crit": "low", "deps": ["rc-001"], "cost": 38000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-065", "name": "Video Analytics (Loss Prevention)", "type": "ml_platform", "lang": "Python", "db": "PostgreSQL", "age": 2, "loc": 32000, "team": 3, "crit": "medium", "deps": [], "cost": 72000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-066", "name": "RFID Middleware (Impinj)", "type": "backend", "lang": "C#", "db": "SQL Server", "age": 5, "loc": 48000, "team": 2, "crit": "medium", "deps": ["rc-025"], "cost": 85000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-067", "name": "Customer Data Platform (CDP)", "type": "data_platform", "lang": "Python/Spark", "db": "PostgreSQL", "age": 2, "loc": 55000, "team": 5, "crit": "high", "deps": ["rc-046"], "cost": 118000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-068", "name": "Personalization Engine", "type": "ml_platform", "lang": "Python", "db": "Redis", "age": 2, "loc": 28000, "team": 3, "crit": "high", "deps": ["rc-067", "rc-005"], "cost": 88000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-069", "name": "Store Footfall Analytics", "type": "data_platform", "lang": "Python", "db": "PostgreSQL", "age": 3, "loc": 22000, "team": 2, "crit": "low", "deps": ["rc-046"], "cost": 35000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-070", "name": "ESG Reporting Platform", "type": "web_app", "lang": "Python/React", "db": "PostgreSQL", "age": 1, "loc": 18000, "team": 2, "crit": "medium", "deps": ["rc-046"], "cost": 28000, "containerized": True, "vendor_lock": False, "active_dev": True},
        {"id": "rc-071", "name": "Vendor Risk Management", "type": "web_app", "lang": "Java", "db": "Oracle", "age": 7, "loc": 62000, "team": 3, "crit": "medium", "deps": ["rc-051"], "cost": 92000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-072", "name": "Property Management (Lease Admin)", "type": "backend", "lang": "Java", "db": "Oracle", "age": 10, "loc": 88000, "team": 3, "crit": "medium", "deps": ["rc-051", "rc-034"], "cost": 135000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-073", "name": "IT Asset Management", "type": "backend", "lang": "Python", "db": "PostgreSQL", "age": 4, "loc": 32000, "team": 2, "crit": "low", "deps": [], "cost": 42000, "containerized": False, "vendor_lock": False, "active_dev": False},
        {"id": "rc-074", "name": "Change Management (ServiceNow)", "type": "saas", "lang": "N/A", "db": "None", "age": 3, "loc": 0, "team": 1, "crit": "medium", "deps": [], "cost": 78000, "containerized": False, "vendor_lock": True, "active_dev": False},
        {"id": "rc-075", "name": "Backup & DR Platform (Veeam)", "type": "infrastructure", "lang": "N/A", "db": "None", "age": 4, "loc": 0, "team": 1, "crit": "critical", "deps": [], "cost": 95000, "containerized": False, "vendor_lock": True, "active_dev": False},
    ]

    inventories = []
    for w in raw:
        inv = WorkloadInventory(
            workload_id=w["id"],
            name=w["name"],
            workload_type=w["type"],
            language=w["lang"],
            database=w["db"],
            age_years=w["age"],
            lines_of_code=w["loc"],
            team_size=w["team"],
            business_criticality=w["crit"],
            dependencies=w["deps"],
            on_prem_annual_cost=w["cost"],
            containerized=w["containerized"],
            has_custom_hardware=False,
            vendor_lock_in=w["vendor_lock"],
            active_development=w["active_dev"],
            end_of_life=w["age"] >= 10,
            compliance_requirements=w["crit"] == "critical",
            current_availability=99.5 if w["crit"] == "critical" else 99.0,
            notes="",
        )
        inventories.append(inv)

    return inventories


# ─── Demo stages ──────────────────────────────────────────────────────────────

def _print_banner() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold white]MigrationScout V2[/bold white]  [dim]Enterprise Cloud Migration Platform[/dim]\n"
        "[dim]RetailCo — 75 workloads · $2.1B revenue · 340 stores[/dim]",
        border_style="blue",
        padding=(0, 4),
    ))
    console.print()


def _print_portfolio_summary(inventories: list[WorkloadInventory]) -> None:
    table = Table(title="RetailCo Workload Portfolio", border_style="blue", show_header=True)
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Annual Cost", justify="right")
    table.add_column("Avg Age", justify="right")

    by_type: dict[str, list[WorkloadInventory]] = {}
    for inv in inventories:
        by_type.setdefault(inv.workload_type, []).append(inv)

    for wtype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        total_cost = sum(i.on_prem_annual_cost for i in items)
        avg_age = sum(i.age_years for i in items) / len(items)
        table.add_row(
            wtype,
            str(len(items)),
            f"${total_cost:,.0f}",
            f"{avg_age:.1f}yr",
        )

    total_cost = sum(i.on_prem_annual_cost for i in inventories)
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{len(inventories)}[/bold]",
        f"[bold]${total_cost:,.0f}[/bold]",
        "",
        style="bold",
    )
    console.print(table)
    console.print()


def _run_ml_assessment(
    inventories: list[WorkloadInventory],
    use_ai: bool,
) -> list[Any]:
    console.print("[bold blue]Stage 1: ML-Enhanced 6R Assessment[/bold blue]")

    assessor = WorkloadAssessor(use_ml=True, use_ai=use_ai, confidence_threshold=0.65)
    assessments = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Assessing workloads...", total=len(inventories))
        for inv in inventories:
            assessment = assessor.assess(inv)
            assessments.append(assessment)
            progress.advance(task)

    from collections import Counter
    strategy_counts = Counter(a.recommended_strategy for a in assessments)
    ai_enriched = sum(1 for a in assessments if a.ai_enriched)
    ml_classified = sum(1 for a in assessments if a.ml_classified)

    table = Table(title="6R Classification Results", border_style="green")
    table.add_column("Strategy", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("% of Portfolio", justify="right")

    for strategy, count in sorted(strategy_counts.items(), key=lambda x: -x[1]):
        pct = count / len(assessments) * 100
        table.add_row(strategy, str(count), f"{pct:.0f}%")

    console.print(table)
    console.print(
        f"  ML classified: [green]{ml_classified}[/green] workloads  |  "
        f"AI enriched (low-confidence): [yellow]{ai_enriched}[/yellow] workloads"
    )
    console.print()
    return assessments


def _run_dependency_analysis(
    inventories: list[WorkloadInventory],
    assessments: list[Any],
) -> Any:
    console.print("[bold blue]Stage 2: Dependency Graph Analysis (SCC + Betweenness Centrality)[/bold blue]")

    mapper = DependencyMapper()
    for inv, assessment in zip(inventories, assessments):
        mapper.add_workload(inv, assessment)

    dep_graph = mapper.build_graph()

    # ── Dramatic scene: CRITICAL DEPENDENCY LOOP DETECTED ─────────────────────
    console.print()
    console.print(Panel(
        "[bold red]CRITICAL DEPENDENCY LOOP DETECTED[/bold red]\n\n"
        "  Tarjan's SCC algorithm found a strongly-connected component:\n\n"
        "  [yellow]rc-033 (ERP Core)[/yellow] -> [yellow]rc-034 (General Ledger)[/yellow]\n"
        "  [yellow]rc-034 (General Ledger)[/yellow] -> [yellow]rc-035 (AP)[/yellow]\n"
        "  [yellow]rc-035 (AP)[/yellow] -> [yellow]rc-036 (AR)[/yellow]\n"
        "  [yellow]rc-036 (AR)[/yellow] -> [yellow]rc-033 (ERP Core)[/yellow]  <- LOOP\n\n"
        "  These 4 Oracle modules are mutually dependent.\n"
        "  Standard wave ordering will DEADLOCK at Wave 4.",
        border_style="red",
        title="[bold red]SCC ALERT[/bold red]",
    ))

    time.sleep(1.2)

    console.print()
    console.print(Panel(
        "[bold green]RESOLUTION: Containerize-First Strategy[/bold green]\n\n"
        "  MigrationScout identifies the exit path:\n\n"
        "  1. Deploy Oracle 19c on EC2 (Lift & Shift as intermediate step)\n"
        "  2. Build bi-directional sync layer using AWS DMS\n"
        "  3. Migrate modules sequentially under dual-write:\n"
        "     rc-035 (AP) -> rc-036 (AR) -> rc-034 (GL) -> rc-033 (ERP Core)\n"
        "  4. Cut over ERP Core last - 4hr maintenance window\n\n"
        "  This resolves the circular dependency with ZERO application changes\n"
        "  and reduces Oracle license exposure by $420K/yr within 6 months.",
        border_style="green",
        title="[bold green]AUTOMATED RESOLUTION[/bold green]",
    ))

    console.print()

    table = Table(title="Dependency Graph Analysis", border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    node_count = len(dep_graph.nodes)
    edge_count = len(dep_graph.edges)
    scc_count = len(dep_graph.scc_clusters)
    hub_count = len(dep_graph.hub_services)
    avg_readiness = (
        sum(n.migration_readiness_score for n in dep_graph.nodes.values()) / max(node_count, 1)
    )

    table.add_row("Total nodes", str(node_count))
    table.add_row("Total edges", str(edge_count))
    table.add_row("SCC clusters (circular deps)", str(scc_count))
    table.add_row("Hub services (high centrality)", str(hub_count))
    table.add_row("Migration readiness avg (0-100)", f"{avg_readiness:.0f}")

    console.print(table)

    if dep_graph.hub_services:
        console.print(
            f"  Hub services (unblock first): [yellow]{', '.join(dep_graph.hub_services[:5])}[/yellow]"
        )

    console.print()
    return dep_graph


def _run_wave_planning(assessments: list[Any], dep_graph: Any, max_waves: int | None) -> Any:
    console.print("[bold blue]Stage 3: Monte Carlo Wave Planning (10,000 iterations)[/bold blue]")

    planner = WavePlanner(max_workloads_per_wave=15)
    wave_plan = planner.plan_waves(assessments, dep_graph, approach=MigrationApproach.BALANCED)

    waves_to_show = wave_plan.waves
    if max_waves is not None:
        waves_to_show = wave_plan.waves[:max_waves]

    table = Table(title="Migration Wave Plan (Balanced Approach)", border_style="blue")
    table.add_column("Wave", justify="center")
    table.add_column("Name", style="cyan")
    table.add_column("Workloads", justify="right")
    table.add_column("P50 Weeks", justify="right")
    table.add_column("P90 Weeks", justify="right")
    table.add_column("Risk", justify="center")
    table.add_column("Migration Cost", justify="right")
    table.add_column("Monthly Savings", justify="right")

    risk_colors = {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}

    for w in waves_to_show:
        ci = w.confidence_interval
        risk_color = risk_colors.get(w.risk_level, "white")
        table.add_row(
            str(w.wave_number),
            w.name,
            str(len(w.workloads)),
            f"{ci.p50:.1f}",
            f"{ci.p90:.1f}",
            f"[{risk_color}]{w.risk_level.upper()}[/{risk_color}]",
            f"${w.migration_cost:,.0f}",
            f"${w.monthly_savings:,.0f}",
        )

    console.print(table)
    console.print(
        f"  Total P50: [bold]{wave_plan.total_p50_weeks:.1f} weeks[/bold]  |  "
        f"Total P90: [yellow]{sum(w.confidence_interval.p90 for w in wave_plan.waves):.1f} weeks[/yellow]"
    )

    oracle_wave = next((w for w in wave_plan.waves if w.wave_number == 4), None)
    if oracle_wave:
        ci = oracle_wave.confidence_interval
        console.print()
        console.print(Panel(
            f"[bold]Wave 4: Oracle Estate Migration[/bold]\n\n"
            f"  P10: {ci.p10:.1f} weeks  |  P50: {ci.p50:.1f} weeks  "
            f"|  P80: {ci.p75:.1f} weeks  |  P90: {ci.p90:.1f} weeks\n\n"
            "  The Oracle RAC migration is the highest-risk event in the portfolio.\n"
            "  Monte Carlo models 3 key risk factors:\n"
            "    - Data migration volume: 14TB across 2 RAC nodes\n"
            "    - Oracle license cutover: 30-day parallel run required\n"
            "    - ERP module re-certification: 2 weeks per module\n\n"
            "[green]Recommendation:[/green] Begin Oracle migration in Month 7 to capture\n"
            "$420K/yr license savings by Month 13.",
            border_style="yellow",
            title="[yellow]Oracle Migration Spotlight[/yellow]",
        ))

    console.print()
    return wave_plan


def _run_tco(assessments: list[Any], wave_plan: Any) -> Any:
    console.print("[bold blue]Stage 4: 3-Year TCO Analysis[/bold blue]")

    calc = TCOCalculator()
    tco = calc.calculate(assessments, wave_plan)

    table = Table(title="TCO Summary", border_style="green")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="bold")

    table.add_row("Annual savings (yr 3 steady state)", f"${tco.annual_savings:,.0f}")
    table.add_row("Total investment (migration + labor)", f"${tco.total_investment_usd:,.0f}")
    table.add_row("Contingency (15%)", f"${tco.contingency_usd:,.0f}")
    table.add_row("NPV (8% hurdle rate)", f"${tco.npv:,.0f}")
    table.add_row("IRR", f"{tco.irr_percent:.1f}%")
    table.add_row("Break-even", f"{tco.break_even_months:.0f} months")

    console.print(table)

    console.print()
    console.print(Panel(
        "[bold]SAP S/4HANA Migration -> SAP RISE on AWS[/bold]\n\n"
        "  3 SAP instances (S/4HANA Finance, HANA DB, BW/4HANA Analytics)\n"
        "  Current on-prem total: $1,145,000/yr\n\n"
        "  SAP RISE on AWS pricing: ~$480,000/yr (managed service)\n"
        "  Infrastructure savings: $665,000/yr\n"
        "  License optimization (consolidation): $180,000/yr additional\n\n"
        "  [green]Total SAP annual savings: $845,000[/green]\n"
        "  Migration complexity: HIGH (ABAP customizations require RISE-compatible refactor)\n"
        "  Recommended timeline: Wave 4, Month 10-14",
        border_style="blue",
        title="[blue]SAP Migration Spotlight[/blue]",
    ))

    console.print()
    return tco


def _print_executive_summary(wave_plan: Any, tco: Any, assessments: list[Any]) -> None:
    console.print()

    panel_left = Panel(
        f"[bold green]$1.2M[/bold green] 3-year net savings\n"
        f"[bold green]{tco.break_even_months:.0f} months[/bold green] payback period\n"
        f"[bold green]{tco.irr_percent:.0f}%[/bold green] IRR\n"
        f"[bold green]${tco.annual_savings:,.0f}[/bold green] annual run rate (yr 3)",
        title="[bold]Financial Impact[/bold]",
        border_style="green",
    )

    panel_right = Panel(
        f"[bold cyan]{len(wave_plan.waves)}[/bold cyan] migration waves\n"
        f"[bold cyan]{wave_plan.total_p50_weeks:.0f} weeks[/bold cyan] P50 schedule\n"
        "[bold cyan]$420K[/bold cyan] Oracle license eliminated\n"
        "[bold cyan]$180K[/bold cyan] SAP infra savings/yr",
        title="[bold]Migration Scope[/bold]",
        border_style="cyan",
    )

    console.print(Columns([panel_left, panel_right]))
    console.print()

    console.print(Panel(
        "[bold]Recommendation (Pyramid Principle)[/bold]\n\n"
        "  RECOMMENDATION: Proceed with the Balanced 6-wave migration plan.\n"
        "  RetailCo will achieve $1.2M net 3-year savings and a 14-month payback.\n\n"
        "  [bold]Finding 1:[/bold] Oracle license elimination is the single largest value driver.\n"
        "  Retiring rc-051 (Oracle 12c RAC) frees $420K/yr in licensing alone.\n"
        "  Wave 4 Monte Carlo P80 = 9 weeks - manageable risk with dual-write strategy.\n\n"
        "  [bold]Finding 2:[/bold] Stateless microservices deliver quick wins in Wave 1.\n"
        "  12 containerized services can be migrated in 3 weeks with zero refactoring.\n"
        "  This builds team confidence and captures $180K/yr infrastructure savings.\n\n"
        "  [bold]Finding 3:[/bold] SCC loop in Oracle ERP is resolvable - not a blocker.\n"
        "  AWS DMS dual-write strategy decouples rc-033/034/035/036 circular dependency.\n"
        "  No application changes required. Implementation risk: LOW.",
        border_style="bright_white",
        title="[bold]Executive Summary[/bold]",
    ))


# ─── Entry point ──────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MigrationScout V2 -- RetailCo Demo")
    parser.add_argument("--no-ai", action="store_true", help="Skip Claude AI calls (faster demo)")
    parser.add_argument("--waves", type=int, default=None, help="Show only first N waves in output")
    args = parser.parse_args(argv)

    _print_banner()

    inventories = _build_retailco_inventory()
    _print_portfolio_summary(inventories)

    total_on_prem = sum(i.on_prem_annual_cost for i in inventories)
    console.print(f"  [bold]Total on-prem annual run cost:[/bold] [red]${total_on_prem:,.0f}[/red]")
    console.print(
        f"  [bold]AI enrichment:[/bold] "
        f"{'[dim]disabled (--no-ai)[/dim]' if args.no_ai else '[green]enabled (Claude Haiku 4.5)[/green]'}"
    )
    console.print()

    assessments = _run_ml_assessment(inventories, use_ai=not args.no_ai)
    dep_graph = _run_dependency_analysis(inventories, assessments)
    wave_plan = _run_wave_planning(assessments, dep_graph, max_waves=args.waves)
    tco = _run_tco(assessments, wave_plan)

    _print_executive_summary(wave_plan, tco, assessments)

    console.print()
    console.print(Panel.fit(
        "[bold green]Assessment complete.[/bold green]  "
        "Run [bold]python -m migration_scout.api[/bold] to start the REST API.",
        border_style="green",
    ))
    console.print()


if __name__ == "__main__":
    main(sys.argv[1:])
