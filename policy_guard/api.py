"""
PolicyGuard — FastAPI REST API
================================
V2 REST API with WebSocket live scanning progress.

Endpoints:
  POST /scans                           — async scan, returns job_id
  GET  /scans/{id}                      — full scan results with framework breakdown
  GET  /scans/{id}/report               — HTML compliance report
  GET  /scans/{id}/remediation-plan     — ordered remediation steps by risk
  POST /ai-systems/register             — register AI system for EU AI Act classification
  GET  /ai-systems/{id}/risk-tier       — Annex III risk classification
  POST /ai-systems/{id}/audit           — trigger Article 12 audit logging review
  GET  /dashboard/summary               — aggregate compliance posture
  WS   /ws/scan/{id}                    — live scanning progress

Run with:
  uvicorn policy_guard.api:app --reload --port 8080
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Provide stub classes so the module can be imported without FastAPI
    class BaseModel:  # type: ignore
        pass
    def Field(*args, **kwargs):  # type: ignore
        return None


# ---------------------------------------------------------------------------
# Pydantic v2 request/response models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    aws_region: str = Field(default="us-east-1", description="AWS region for CIS scanning")
    mock_mode: bool = Field(default=True, description="Use mock data (no real AWS calls)")
    run_eu_ai_act: bool = Field(default=True)
    run_nist_ai_rmf: bool = Field(default=True)
    run_soc2: bool = Field(default=True)
    run_cis_aws: bool = Field(default=True)
    run_hipaa: bool = Field(default=True)
    ai_systems: list[dict] = Field(default_factory=list, description="AI systems to include in scan")
    scenario: Optional[str] = Field(default=None, description="Demo scenario: 'accelerant' or 'defender'")


class AISystemRegistration(BaseModel):
    name: str = Field(..., description="AI system name")
    description: str = Field(..., description="System purpose and use case")
    use_domain: str = Field(default="general", description="Domain: hiring, credit, medical, etc.")
    is_gpai: bool = Field(default=False, description="Is this a General Purpose AI model?")
    deployment_region: str = Field(default="EU", description="Primary deployment region")
    has_human_oversight: bool = Field(default=False)
    has_audit_logging: bool = Field(default=False)
    has_risk_management: bool = Field(default=False)
    has_technical_documentation: bool = Field(default=False)
    technical_doc_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    has_accuracy_benchmarks: bool = Field(default=False)
    bias_testing_done: bool = Field(default=False)
    training_data_documented: bool = Field(default=False)


class ScanStatusResponse(BaseModel):
    scan_id: str
    status: str           # pending | running | complete | failed
    created_at: str
    completed_at: Optional[str]
    overall_score: Optional[float]
    risk_rating: Optional[str]
    total_findings: Optional[int]
    critical_count: Optional[int]
    high_count: Optional[int]
    framework_scores: Optional[dict[str, float]]


class RemediationStep(BaseModel):
    rank: int
    framework: str
    control_id: str
    title: str
    severity: str
    remediation: str
    estimated_hours: int
    estimated_cost_usd: int
    timeline_days: int
    risk_effort_score: float
    cross_framework_mappings: dict[str, str]


class RiskTierResponse(BaseModel):
    system_id: str
    system_name: str
    risk_tier: str
    annex_iii_category: Optional[int]
    annex_iii_category_name: Optional[str]
    justification: str
    conformity_route: str
    conformity_deadline: Optional[str]
    days_until_deadline: Optional[int]
    article_references: list[str]
    prohibited_practice_flags: list[str]
    recommended_actions: list[str]


class DashboardSummary(BaseModel):
    total_systems_registered: int
    high_risk_systems: int
    overall_compliance_score: float
    days_to_high_risk_deadline: int
    framework_scores: dict[str, float]
    critical_findings_total: int
    high_findings_total: int
    top_risk_system: Optional[str]
    systems_needing_conformity_assessment: int
    estimated_total_remediation_cost_usd: int


# ---------------------------------------------------------------------------
# In-memory state (production would use Redis/PostgreSQL)
# ---------------------------------------------------------------------------

_scans: dict[str, dict] = {}
_scan_results: dict[str, Any] = {}
_registered_systems: dict[str, dict] = {}
_scan_progress: dict[str, list[str]] = {}


def _make_scan_record(scan_id: str, request: "ScanRequest") -> dict:
    return {
        "scan_id": scan_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "request": request.model_dump() if hasattr(request, "model_dump") else {},
        "overall_score": None,
        "risk_rating": None,
        "total_findings": None,
        "critical_count": None,
        "high_count": None,
        "framework_scores": None,
    }


# ---------------------------------------------------------------------------
# Background scan runner
# ---------------------------------------------------------------------------

async def _run_scan_background(scan_id: str, request_data: dict) -> None:
    """Execute compliance scan in background and store results."""
    import sys
    from pathlib import Path
    _module_dir = Path(__file__).resolve().parent.parent
    if str(_module_dir) not in sys.path:
        sys.path.insert(0, str(_module_dir))

    from policy_guard.scanner import ComplianceScanner, ScanConfig

    _scans[scan_id]["status"] = "running"

    progress_messages = []
    _scan_progress[scan_id] = progress_messages

    try:
        config = ScanConfig(
            mock_mode=request_data.get("mock_mode", True),
            aws_region=request_data.get("aws_region", "us-east-1"),
            ai_systems=request_data.get("ai_systems", []),
            run_cis_aws=request_data.get("run_cis_aws", True),
            run_eu_ai_act=request_data.get("run_eu_ai_act", True),
            run_nist_ai_rmf=request_data.get("run_nist_ai_rmf", True),
            run_soc2=request_data.get("run_soc2", True),
            run_hipaa=request_data.get("run_hipaa", True),
        )

        progress_messages.append(json.dumps({"event": "progress", "message": "Initializing scanners...", "pct": 5}))
        await asyncio.sleep(0.1)

        frameworks = []
        if config.run_cis_aws:
            frameworks.append("CIS AWS Foundations Benchmark v3.0")
        if config.run_eu_ai_act:
            frameworks.append("EU AI Act (Regulation 2024/1689)")
        if config.run_nist_ai_rmf:
            frameworks.append("NIST AI RMF 1.0")
        if config.run_soc2:
            frameworks.append("SOC 2 Type II + AICC-12")
        if config.run_hipaa:
            frameworks.append("HIPAA Security Rule")

        for i, fw in enumerate(frameworks):
            pct = 10 + int((i / len(frameworks)) * 75)
            progress_messages.append(json.dumps({"event": "progress", "message": f"Scanning {fw}...", "pct": pct}))
            await asyncio.sleep(0.05)

        scanner = ComplianceScanner(config)
        report = await scanner.scan()
        _scan_results[scan_id] = report

        progress_messages.append(json.dumps({"event": "progress", "message": "Aggregating results...", "pct": 90}))
        await asyncio.sleep(0.05)

        _scans[scan_id].update({
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "overall_score": round(report.overall_score, 1),
            "risk_rating": report.risk_rating,
            "total_findings": report.total_findings,
            "critical_count": report.critical_findings,
            "high_count": report.high_findings,
            "framework_scores": {
                fs.framework: round(fs.score, 1)
                for fs in report.framework_scores
            },
        })

        progress_messages.append(json.dumps({
            "event": "complete",
            "message": f"Scan complete. Overall: {report.overall_score:.1f}%. {report.total_findings} findings.",
            "pct": 100,
            "scan_id": scan_id,
            "overall_score": report.overall_score,
            "risk_rating": report.risk_rating,
        }))

    except Exception as e:
        _scans[scan_id]["status"] = "failed"
        progress_messages.append(json.dumps({"event": "error", "message": str(e)}))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="PolicyGuard API",
        description=(
            "AI Governance and Cloud Compliance API. "
            "Covers EU AI Act, NIST AI RMF, SOC 2 AICC, CIS AWS, and HIPAA. "
            "High-risk enforcement deadline: August 2, 2026."
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/health")
    async def health_check() -> dict:
        from policy_guard.frameworks.eu_ai_act import days_until_enforcement
        return {
            "status": "healthy",
            "version": "2.0.0",
            "days_to_eu_ai_act_deadline": days_until_enforcement("high_risk_systems"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/scans", response_model=ScanStatusResponse, status_code=202)
    async def create_scan(
        request: ScanRequest,
        background_tasks: BackgroundTasks,
    ) -> ScanStatusResponse:
        """Initiate an async compliance scan. Returns job_id to poll for results."""
        scan_id = str(uuid.uuid4())[:12].upper()
        record = _make_scan_record(scan_id, request)
        _scans[scan_id] = record

        background_tasks.add_task(
            _run_scan_background,
            scan_id,
            request.model_dump(),
        )

        return ScanStatusResponse(
            scan_id=scan_id,
            status="pending",
            created_at=record["created_at"],
            completed_at=None,
            overall_score=None,
            risk_rating=None,
            total_findings=None,
            critical_count=None,
            high_count=None,
            framework_scores=None,
        )

    @app.get("/scans/{scan_id}", response_model=ScanStatusResponse)
    async def get_scan(scan_id: str) -> ScanStatusResponse:
        """Get scan status and results by scan_id."""
        record = _scans.get(scan_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")

        return ScanStatusResponse(
            scan_id=record["scan_id"],
            status=record["status"],
            created_at=record["created_at"],
            completed_at=record.get("completed_at"),
            overall_score=record.get("overall_score"),
            risk_rating=record.get("risk_rating"),
            total_findings=record.get("total_findings"),
            critical_count=record.get("critical_count"),
            high_count=record.get("high_count"),
            framework_scores=record.get("framework_scores"),
        )

    @app.get("/scans/{scan_id}/report", response_class=HTMLResponse)
    async def get_scan_report(scan_id: str) -> HTMLResponse:
        """Get HTML compliance report for a completed scan."""
        if scan_id not in _scan_results:
            raise HTTPException(
                status_code=404 if scan_id not in _scans else 425,
                detail=f"Scan '{scan_id}' {'not found' if scan_id not in _scans else 'not yet complete — poll GET /scans/{scan_id} for status'}.",
            )

        import tempfile
        from policy_guard.reporter import ReportGenerator
        report = _scan_results[scan_id]
        generator = ReportGenerator(report)

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = generator.generate_html(tmpdir)
            with open(html_path, encoding="utf-8") as f:
                html_content = f.read()

        return HTMLResponse(content=html_content)

    @app.get("/scans/{scan_id}/remediation-plan")
    async def get_remediation_plan(scan_id: str) -> dict:
        """Get ordered remediation steps ranked by (impact / effort) ratio."""
        if scan_id not in _scan_results:
            raise HTTPException(
                status_code=404 if scan_id not in _scans else 425,
                detail=f"Scan '{scan_id}' not ready.",
            )

        from policy_guard.reporter import ReportGenerator, REMEDIATION_EFFORT
        report = _scan_results[scan_id]
        generator = ReportGenerator(report)
        roadmap = generator._build_remediation_roadmap()

        severity_scores = {"CRITICAL": 100, "HIGH": 75, "MEDIUM": 40, "LOW": 10}

        steps = []
        for i, item in enumerate(roadmap):
            effort_hrs = item.estimated_hours
            impact = severity_scores.get(item.severity, 40)
            risk_effort = round(impact * 10 / max(1, effort_hrs), 2)

            cross = {}
            fw_report = getattr(report, {
                "EU AI Act": "eu_ai_act",
                "NIST AI RMF": "nist_ai_rmf",
                "SOC 2": "soc2",
                "CIS AWS": "cis_aws",
                "HIPAA": "hipaa",
            }.get(item.framework, ""), None)

            steps.append({
                "rank": i + 1,
                "framework": item.framework,
                "control_id": item.finding_id,
                "title": item.title,
                "severity": item.severity,
                "remediation": item.remediation,
                "estimated_hours": item.estimated_hours,
                "estimated_cost_usd": item.estimated_cost_usd,
                "timeline_days": item.timeline_days,
                "risk_effort_score": risk_effort,
                "cross_framework_mappings": cross,
            })

        total_cost = sum(item.estimated_cost_usd for item in roadmap)
        return {
            "scan_id": scan_id,
            "total_steps": len(steps),
            "total_estimated_cost_usd": total_cost,
            "total_estimated_hours": sum(item.estimated_hours for item in roadmap),
            "eu_ai_act_deadline_days": None,
            "remediation_plan": steps[:50],
        }

    @app.post("/ai-systems/register")
    async def register_ai_system(registration: AISystemRegistration) -> dict:
        """Register an AI system for EU AI Act classification and ongoing monitoring."""
        system_id = str(uuid.uuid4())[:8].upper()

        # Classify the system immediately
        domain_to_annex = {
            "hiring": 4, "recruitment": 4, "employment": 4,
            "credit": 5, "lending": 5, "insurance": 5,
            "medical": 2, "healthcare": 2, "diagnostic": 2,
            "education": 3, "training": 3,
            "law_enforcement": 6, "police": 6,
            "biometric": 1, "facial_recognition": 1,
            "judicial": 8, "court": 8,
            "immigration": 7, "border": 7,
        }

        annex_match = domain_to_annex.get(registration.use_domain.lower())

        _registered_systems[system_id] = {
            "system_id": system_id,
            "name": registration.name,
            "description": registration.description,
            "use_domain": registration.use_domain,
            "is_gpai": registration.is_gpai,
            "deployment_region": registration.deployment_region,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "annex_iii_match": annex_match,
            "attributes": registration.model_dump(),
        }

        from policy_guard.frameworks.eu_ai_act import (
            _classify_system, ANNEX_III_CATEGORIES, days_until_enforcement, ENFORCEMENT_DATES
        )
        state = {
            "description": registration.description,
            "is_gpai": registration.is_gpai,
            "annex_iii_match": annex_match,
            "keywords_present": registration.use_domain.lower().split(),
            "has_audit_logging": registration.has_audit_logging,
            "has_risk_management": registration.has_risk_management,
            "has_human_oversight": registration.has_human_oversight,
            "has_technical_documentation": registration.has_technical_documentation,
            "technical_doc_completeness": registration.technical_doc_completeness,
            "has_accuracy_benchmarks": registration.has_accuracy_benchmarks,
            "bias_testing_done": registration.bias_testing_done,
            "training_data_documented": registration.training_data_documented,
            "has_data_governance_docs": registration.training_data_documented,
            "has_model_card": False,
            "conformity_assessment_done": False,
            "eu_database_registered": False,
        }

        classification = _classify_system(registration.name, state)
        _registered_systems[system_id]["classification"] = {
            "risk_tier": classification.risk_tier,
            "annex_iii_category": classification.annex_iii_category,
            "annex_iii_category_name": classification.annex_iii_category_name,
        }

        return {
            "system_id": system_id,
            "name": registration.name,
            "risk_tier": classification.risk_tier,
            "annex_iii_category": classification.annex_iii_category,
            "annex_iii_category_name": classification.annex_iii_category_name,
            "justification": classification.justification,
            "conformity_route": classification.conformity_route,
            "conformity_deadline": classification.conformity_deadline.isoformat() if classification.conformity_deadline else None,
            "days_until_deadline": days_until_enforcement("high_risk_systems") if classification.risk_tier == "High-Risk" else None,
            "message": f"System '{registration.name}' registered as {classification.risk_tier}. System ID: {system_id}",
        }

    @app.get("/ai-systems/{system_id}/risk-tier", response_model=RiskTierResponse)
    async def get_risk_tier(system_id: str) -> RiskTierResponse:
        """Get EU AI Act risk tier classification for a registered system."""
        system = _registered_systems.get(system_id)
        if not system:
            raise HTTPException(status_code=404, detail=f"System '{system_id}' not registered.")

        from policy_guard.frameworks.eu_ai_act import (
            _classify_system, days_until_enforcement, ANNEX_III_CATEGORIES
        )

        attrs = system["attributes"]
        state = {
            "is_gpai": attrs.get("is_gpai", False),
            "annex_iii_match": system.get("annex_iii_match"),
            "keywords_present": attrs.get("use_domain", "").lower().split(),
            **{k: v for k, v in attrs.items()},
        }

        classification = _classify_system(system["name"], state)
        days_left = days_until_enforcement("high_risk_systems") if classification.risk_tier == "High-Risk" else None

        recommended = []
        if classification.risk_tier == "High-Risk":
            recommended = [
                "Complete Annex IV technical documentation (all 15 sections)",
                "Implement risk management system per Article 9",
                "Conduct bias testing per Article 10",
                "Set up audit logging per Article 12",
                "Implement human oversight per Article 14",
                f"Begin {'notified body' if classification.conformity_route == 'notified_body' else 'internal'} conformity assessment",
            ]

        return RiskTierResponse(
            system_id=system_id,
            system_name=system["name"],
            risk_tier=classification.risk_tier,
            annex_iii_category=classification.annex_iii_category,
            annex_iii_category_name=classification.annex_iii_category_name,
            justification=classification.justification,
            conformity_route=classification.conformity_route,
            conformity_deadline=classification.conformity_deadline.isoformat() if classification.conformity_deadline else None,
            days_until_deadline=days_left,
            article_references=classification.article_references,
            prohibited_practice_flags=classification.prohibited_practice_flags,
            recommended_actions=recommended,
        )

    @app.post("/ai-systems/{system_id}/audit")
    async def trigger_audit(system_id: str) -> dict:
        """Trigger Article 12 audit logging review for a registered AI system."""
        system = _registered_systems.get(system_id)
        if not system:
            raise HTTPException(status_code=404, detail=f"System '{system_id}' not registered.")

        attrs = system.get("attributes", {})
        has_logging = attrs.get("has_audit_logging", False)

        audit_result = {
            "system_id": system_id,
            "system_name": system["name"],
            "audit_triggered_at": datetime.now(timezone.utc).isoformat(),
            "article_12_compliant": has_logging,
            "findings": [],
            "recommendations": [],
        }

        if not has_logging:
            audit_result["findings"] = [
                "No automatic logging of AI system operations detected",
                "Article 12 requires automatic log generation capturing system operation",
                "Minimum log fields: timestamp, inputs (hashed), outputs, model version, confidence score",
                "Log retention: minimum 5 years for high-risk systems per Article 12(1)",
                "Logs must be available to national competent authorities upon request",
            ]
            audit_result["recommendations"] = [
                "Implement structured logging (JSON, timestamped, immutable)",
                "Set up WORM storage or blockchain-anchored audit trail",
                "Deploy PolicyGuard AIAuditTrail module for automated compliance",
                "Test log completeness and retention before conformity assessment",
            ]
        else:
            audit_result["findings"] = ["Audit logging present — detailed review recommended"]
            audit_result["recommendations"] = [
                "Verify log completeness covers all inference events",
                "Confirm log retention policy meets 5-year minimum",
                "Test log access controls and tamper-evidence",
            ]

        return audit_result

    @app.get("/dashboard/summary", response_model=DashboardSummary)
    async def get_dashboard_summary() -> DashboardSummary:
        """Get aggregate compliance posture across all registered systems and scans."""
        from policy_guard.frameworks.eu_ai_act import days_until_enforcement

        # Aggregate from completed scans
        completed_scans = [s for s in _scans.values() if s["status"] == "complete"]

        if not completed_scans:
            # Return demo summary if no scans have run yet
            return DashboardSummary(
                total_systems_registered=len(_registered_systems),
                high_risk_systems=sum(
                    1 for s in _registered_systems.values()
                    if s.get("classification", {}).get("risk_tier") == "High-Risk"
                ),
                overall_compliance_score=0.0,
                days_to_high_risk_deadline=days_until_enforcement("high_risk_systems"),
                framework_scores={},
                critical_findings_total=0,
                high_findings_total=0,
                top_risk_system=None,
                systems_needing_conformity_assessment=0,
                estimated_total_remediation_cost_usd=0,
            )

        latest_scan = max(completed_scans, key=lambda s: s["created_at"])

        # Aggregate across all recent scans
        all_critical = sum(s.get("critical_count", 0) or 0 for s in completed_scans)
        all_high = sum(s.get("high_count", 0) or 0 for s in completed_scans)
        avg_score = sum(s.get("overall_score", 0) or 0 for s in completed_scans) / len(completed_scans)

        high_risk_count = sum(
            1 for s in _registered_systems.values()
            if s.get("classification", {}).get("risk_tier") == "High-Risk"
        )

        return DashboardSummary(
            total_systems_registered=len(_registered_systems),
            high_risk_systems=high_risk_count,
            overall_compliance_score=round(avg_score, 1),
            days_to_high_risk_deadline=days_until_enforcement("high_risk_systems"),
            framework_scores=latest_scan.get("framework_scores") or {},
            critical_findings_total=all_critical,
            high_findings_total=all_high,
            top_risk_system=None,
            systems_needing_conformity_assessment=high_risk_count,
            estimated_total_remediation_cost_usd=all_critical * 8000 + all_high * 3600,
        )

    @app.websocket("/ws/scan/{scan_id}")
    async def scan_websocket(websocket: WebSocket, scan_id: str) -> None:
        """WebSocket endpoint for live scan progress updates."""
        await websocket.accept()

        try:
            # Send initial status
            if scan_id not in _scans:
                await websocket.send_text(json.dumps({"event": "error", "message": f"Scan '{scan_id}' not found"}))
                await websocket.close()
                return

            await websocket.send_text(json.dumps({"event": "connected", "scan_id": scan_id}))

            # Stream progress messages as they arrive
            last_sent = 0
            max_wait = 60  # 60 second timeout
            start = time.monotonic()

            while time.monotonic() - start < max_wait:
                messages = _scan_progress.get(scan_id, [])
                while last_sent < len(messages):
                    await websocket.send_text(messages[last_sent])
                    last_sent += 1

                scan_status = _scans.get(scan_id, {}).get("status")
                if scan_status in ("complete", "failed"):
                    break

                await asyncio.sleep(0.2)

            # Final status
            final = _scans.get(scan_id, {})
            await websocket.send_text(json.dumps({
                "event": "final",
                "status": final.get("status"),
                "overall_score": final.get("overall_score"),
                "risk_rating": final.get("risk_rating"),
                "total_findings": final.get("total_findings"),
            }))

        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await websocket.send_text(json.dumps({"event": "error", "message": str(e)}))
            except Exception:
                pass

else:
    # Stub for environments without FastAPI
    class _AppStub:
        def get(self, *a, **kw):
            def decorator(f):
                return f
            return decorator
        post = get
        websocket = get

    app = _AppStub()  # type: ignore


def get_app():
    """Return the FastAPI app instance (or None if FastAPI not installed)."""
    if not FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI not installed. Run: pip install fastapi uvicorn[standard]"
        )
    return app
