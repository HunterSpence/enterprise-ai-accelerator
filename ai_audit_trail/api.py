"""
api.py — FastAPI REST API for AIAuditTrail.

V2: Full async FastAPI with Pydantic v2, OpenAPI auto-docs, and API key auth.

Endpoints:
  POST   /audit-logs                        — Write single audit entry
  GET    /audit-logs                        — Paginated retrieval with filters
  POST   /audit-logs/bulk                   — Bulk ingest from SDK export
  GET    /audit-logs/{id}                   — Single entry retrieval
  GET    /audit-logs/{id}/verify            — Verify chain integrity up to entry
  POST   /systems/register                  — Register an AI system
  GET    /systems/{id}/compliance-status    — EU AI Act + NIST RMF posture
  GET    /systems/{id}/report               — HTML Article 12 compliance report
  POST   /systems/{id}/incident             — Log AI incident (Article 62)
  GET    /dashboard                         — Aggregate compliance posture
  POST   /verify-chain                      — Full chain verification, tamper report

Auth: X-AIAuditTrail-Key header.
Dev bypass: AUDIT_DEV_MODE=true (default) bypasses auth for demo.

Requires: pip install fastapi uvicorn pydantic

Run::

    uvicorn ai_audit_trail.api:app --reload --port 8000
    # OpenAPI docs: http://localhost:8000/docs
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier
from ai_audit_trail.config import settings
from ai_audit_trail.eu_ai_act import (
    Article12Check,
    check_article_12_compliance,
    classify_risk_tier,
    days_until_enforcement,
    detect_article_62_incidents,
    enforcement_status,
    generate_article_13_transparency_report,
)
from ai_audit_trail.incident_manager import AIIncident, IncidentManager, IncidentSeverity
from ai_audit_trail.nist_rmf import RMFAssessment, assess_nist_rmf
from ai_audit_trail.query import QueryEngine
from ai_audit_trail.reporter import ReportGenerator

# ---------------------------------------------------------------------------
# FastAPI imports (optional dependency)
# ---------------------------------------------------------------------------

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel, Field
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False
    # Stub types for type checking when FastAPI not installed
    class BaseModel:  # type: ignore[no-redef]
        pass
    def Field(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        return None


# ---------------------------------------------------------------------------
# In-memory system registry (production: persist to DB)
# ---------------------------------------------------------------------------

_registered_systems: dict[str, dict[str, Any]] = {}
_incident_manager = IncidentManager()


def _get_chain() -> AuditChain:
    """Dependency: return the shared AuditChain instance."""
    return AuditChain(settings.db_path, store_plaintext=settings.store_plaintext)


def _verify_api_key(x_aiaudittrail_key: str = Header(default="")) -> None:
    """Dependency: verify API key. Dev mode bypasses auth."""
    if settings.dev_mode:
        return
    if not x_aiaudittrail_key or x_aiaudittrail_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-AIAuditTrail-Key header",
        )


# ---------------------------------------------------------------------------
# Pydantic v2 request/response models
# ---------------------------------------------------------------------------

if _HAS_FASTAPI:

    class AuditLogRequest(BaseModel):
        session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
        system_id: str = Field(default="default", description="Registered AI system ID")
        model: str = Field(..., description="Model name (e.g., claude-sonnet-4-6)")
        input_text: str = Field(..., description="Prompt or input text")
        output_text: str = Field(..., description="Model output")
        input_tokens: int = Field(default=0, ge=0)
        output_tokens: int = Field(default=0, ge=0)
        cache_read_tokens: int = Field(default=0, ge=0)
        cost_usd: float = Field(default=0.0, ge=0)
        latency_ms: float = Field(..., description="Wall-clock latency in milliseconds")
        decision_type: str = Field(
            default="GENERATION",
            description="GENERATION | CLASSIFICATION | RECOMMENDATION | AUTONOMOUS_ACTION",
        )
        risk_tier: str = Field(
            default="LIMITED",
            description="MINIMAL | LIMITED | HIGH | UNACCEPTABLE",
        )
        metadata: dict[str, Any] = Field(default_factory=dict)

    class BulkAuditRequest(BaseModel):
        entries: list[AuditLogRequest] = Field(
            ..., description="Up to 1000 audit entries for bulk ingest"
        )

    class SystemRegistration(BaseModel):
        system_id: str = Field(..., description="Unique system identifier")
        system_name: str = Field(..., description="Human-readable system name")
        system_description: str = Field(..., description="System purpose and capabilities")
        version: str = Field(default="1.0.0")
        operator_name: str = Field(default="Organization Name")
        contact_email: str = Field(default="compliance@example.com")
        training_data_description: str = Field(default="Proprietary dataset")
        model_name: str = Field(default="")
        deployment_date: str = Field(
            default_factory=lambda: datetime.now(timezone.utc).date().isoformat()
        )

    class IncidentRequest(BaseModel):
        severity: str = Field(
            ...,
            description="P0-SAFETY | P0-DISCRIMINATION | P1-ACCURACY | P1-INTEGRITY | P2-PERFORMANCE | P3-COST",
        )
        title: str = Field(..., description="Short incident title")
        description: str = Field(..., description="Detailed incident description")
        affected_persons_estimate: int = Field(default=0, ge=0)
        evidence_entry_ids: list[str] = Field(default_factory=list)
        detected_by: str = Field(default="human")

    class ChainVerifyRequest(BaseModel):
        system_id: Optional[str] = Field(
            default=None,
            description="Verify only entries for this system (None = all entries)",
        )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

if _HAS_FASTAPI:
    app = FastAPI(
        title="AIAuditTrail API",
        description=(
            "Tamper-evident AI audit logging for EU AI Act Article 12 compliance.\n\n"
            "EU AI Act high-risk system enforcement begins **August 2, 2026**.\n"
            "IBM OpenPages: $500K/yr | Credo AI: $180K/yr | AIAuditTrail: **$0**"
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ------------------------------------------------------------------
    # POST /audit-logs
    # ------------------------------------------------------------------

    @app.post(
        "/audit-logs",
        summary="Write a single audit entry",
        tags=["Audit Logs"],
    )
    async def create_audit_log(
        req: AuditLogRequest,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        chain = _get_chain()
        try:
            entry = chain.append(
                session_id=req.session_id,
                model=req.model,
                input_text=req.input_text,
                output_text=req.output_text,
                input_tokens=req.input_tokens,
                output_tokens=req.output_tokens,
                latency_ms=req.latency_ms,
                decision_type=DecisionType(req.decision_type),
                risk_tier=RiskTier(req.risk_tier),
                metadata=req.metadata,
                system_id=req.system_id,
                cache_read_tokens=req.cache_read_tokens,
                cost_usd=req.cost_usd,
            )
        finally:
            chain.close()

        return {
            "entry_id": entry.entry_id,
            "entry_hash": entry.entry_hash,
            "timestamp": entry.timestamp,
            "prev_hash": entry.prev_hash[:16] + "…",
            "status": "logged",
        }

    # ------------------------------------------------------------------
    # GET /audit-logs
    # ------------------------------------------------------------------

    @app.get(
        "/audit-logs",
        summary="Retrieve paginated audit entries with filters",
        tags=["Audit Logs"],
    )
    async def list_audit_logs(
        system_id: Optional[str] = Query(default=None),
        session_id: Optional[str] = Query(default=None),
        risk_tier: Optional[str] = Query(default=None, description="MINIMAL|LIMITED|HIGH|UNACCEPTABLE"),
        decision_type: Optional[str] = Query(default=None),
        model: Optional[str] = Query(default=None),
        since: Optional[str] = Query(default=None, description="ISO 8601 UTC start"),
        until: Optional[str] = Query(default=None, description="ISO 8601 UTC end"),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        chain = _get_chain()
        try:
            qe = QueryEngine(chain)
            entries = qe.filter(
                session_id=session_id,
                decision_type=decision_type,
                risk_tier=risk_tier,
                model=model,
                since=since,
                until=until,
                limit=limit,
            )
            total = chain.count(system_id=system_id)
        finally:
            chain.close()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "timestamp": e.timestamp,
                    "system_id": e.system_id,
                    "session_id": e.session_id,
                    "model": e.model,
                    "decision_type": e.decision_type,
                    "risk_tier": e.risk_tier,
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "cost_usd": e.cost_usd,
                    "latency_ms": round(e.latency_ms, 1),
                    "entry_hash": e.entry_hash[:16] + "…",
                    "metadata": e.metadata,
                }
                for e in entries
            ],
        }

    # ------------------------------------------------------------------
    # POST /audit-logs/bulk
    # ------------------------------------------------------------------

    @app.post(
        "/audit-logs/bulk",
        summary="Bulk ingest up to 1000 entries",
        tags=["Audit Logs"],
    )
    async def bulk_ingest(
        req: BulkAuditRequest,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        if len(req.entries) > 1000:
            raise HTTPException(
                status_code=400, detail="Bulk ingest limit is 1000 entries per request"
            )

        chain = _get_chain()
        logged = 0
        errors: list[str] = []

        try:
            for entry_req in req.entries:
                try:
                    chain.append(
                        session_id=entry_req.session_id,
                        model=entry_req.model,
                        input_text=entry_req.input_text,
                        output_text=entry_req.output_text,
                        input_tokens=entry_req.input_tokens,
                        output_tokens=entry_req.output_tokens,
                        latency_ms=entry_req.latency_ms,
                        decision_type=DecisionType(entry_req.decision_type),
                        risk_tier=RiskTier(entry_req.risk_tier),
                        metadata=entry_req.metadata,
                        system_id=entry_req.system_id,
                        cache_read_tokens=entry_req.cache_read_tokens,
                        cost_usd=entry_req.cost_usd,
                    )
                    logged += 1
                except Exception as e:
                    errors.append(str(e))
        finally:
            chain.close()

        return {
            "logged": logged,
            "errors": len(errors),
            "error_details": errors[:10],
            "status": "complete",
        }

    # ------------------------------------------------------------------
    # GET /audit-logs/{id}
    # ------------------------------------------------------------------

    @app.get(
        "/audit-logs/{entry_id}",
        summary="Get a single audit entry",
        tags=["Audit Logs"],
    )
    async def get_audit_log(
        entry_id: str,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        chain = _get_chain()
        try:
            qe = QueryEngine(chain)
            result = qe.explain(entry_id)
        finally:
            chain.close()

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ------------------------------------------------------------------
    # GET /audit-logs/{id}/verify
    # ------------------------------------------------------------------

    @app.get(
        "/audit-logs/{entry_id}/verify",
        summary="Verify Merkle proof for a single entry (O(log n))",
        tags=["Audit Logs"],
    )
    async def verify_entry(
        entry_id: str,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        chain = _get_chain()
        try:
            proof = chain.get_entry_proof(entry_id)
        finally:
            chain.close()

        if not proof:
            raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

        from ai_audit_trail.chain import MerkleTree
        valid = MerkleTree.verify_proof(
            proof["leaf_hash"], proof["proof"], proof["merkle_root"]
        )
        return {
            "entry_id": entry_id,
            "integrity": "VALID" if valid else "TAMPERED",
            "leaf_index": proof["leaf_index"],
            "merkle_root": proof["merkle_root"],
            "proof_steps": len(proof["proof"]),
            "total_entries": proof["entry_count"],
            "complexity": f"O(log {proof['entry_count']}) = {len(proof['proof'])} hash operations",
        }

    # ------------------------------------------------------------------
    # POST /systems/register
    # ------------------------------------------------------------------

    @app.post(
        "/systems/register",
        summary="Register an AI system for compliance tracking",
        tags=["Systems"],
    )
    async def register_system(
        req: SystemRegistration,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        risk_tier = classify_risk_tier(req.system_description)
        _registered_systems[req.system_id] = {
            "system_id": req.system_id,
            "system_name": req.system_name,
            "system_description": req.system_description,
            "version": req.version,
            "operator_name": req.operator_name,
            "contact_email": req.contact_email,
            "training_data_description": req.training_data_description,
            "model_name": req.model_name,
            "deployment_date": req.deployment_date,
            "risk_tier": risk_tier.value,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "system_id": req.system_id,
            "risk_tier": risk_tier.value,
            "registered": True,
            "message": (
                f"System registered. Risk tier: {risk_tier.value}. "
                + ("HIGH-risk systems must comply by August 2, 2026." if risk_tier.value == "HIGH" else "")
            ),
        }

    # ------------------------------------------------------------------
    # GET /systems/{id}/compliance-status
    # ------------------------------------------------------------------

    @app.get(
        "/systems/{system_id}/compliance-status",
        summary="EU AI Act + NIST RMF compliance posture",
        tags=["Systems"],
    )
    async def compliance_status(
        system_id: str,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        system_info = _registered_systems.get(system_id, {"system_name": system_id})
        chain = _get_chain()
        try:
            a12 = check_article_12_compliance(chain)
            rmf = assess_nist_rmf(
                chain, system_id=system_id, system_name=system_info.get("system_name", system_id)
            )
            entry_count = chain.count(system_id=system_id)
            tamper_report = chain.verify_chain()
        finally:
            chain.close()

        days = days_until_enforcement("high_risk_systems")
        enforcement = enforcement_status()

        return {
            "system_id": system_id,
            "system_info": system_info,
            "entry_count": entry_count,
            "eu_ai_act": {
                "article_12_score": a12.score,
                "article_12_compliant": a12.compliant,
                "requirements_met": len(a12.requirements_met),
                "requirements_missing": a12.requirements_missing,
                "enforcement_days_remaining": days,
                "enforcement_status": enforcement,
            },
            "nist_rmf": {
                "overall_score": round(rmf.overall_score, 2),
                "overall_level": rmf.overall_level,
                "govern": round(rmf.govern_score.score, 2),
                "map": round(rmf.map_score.score, 2),
                "measure": round(rmf.measure_score.score, 2),
                "manage": round(rmf.manage_score.score, 2),
                "dual_framework_evidence": rmf.dual_framework_evidence,
            },
            "chain_integrity": {
                "valid": tamper_report.is_valid,
                "merkle_root": tamper_report.merkle_root,
                "tampered_entries": len(tamper_report.tampered_entries),
            },
            "recommendations": a12.recommendations + rmf.recommendations,
        }

    # ------------------------------------------------------------------
    # GET /systems/{id}/report
    # ------------------------------------------------------------------

    @app.get(
        "/systems/{system_id}/report",
        summary="Generate HTML Article 12 compliance report",
        tags=["Systems"],
        response_class=HTMLResponse,
    )
    async def compliance_report(
        system_id: str,
        _auth: None = Depends(_verify_api_key),
    ) -> HTMLResponse:
        system_info = _registered_systems.get(system_id, {})
        chain = _get_chain()
        try:
            gen = ReportGenerator(
                chain,
                system_name=system_info.get("system_name", system_id),
            )
            report = gen.generate()
            html = gen.to_html(report)
        finally:
            chain.close()

        return HTMLResponse(content=html)

    # ------------------------------------------------------------------
    # POST /systems/{id}/incident
    # ------------------------------------------------------------------

    @app.post(
        "/systems/{system_id}/incident",
        summary="Log an AI incident (Article 62 serious incident report)",
        tags=["Systems"],
    )
    async def log_incident(
        system_id: str,
        req: IncidentRequest,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        system_info = _registered_systems.get(system_id, {"system_name": system_id})

        try:
            severity = IncidentSeverity(req.severity)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity: {req.severity}. Valid: {[s.value for s in IncidentSeverity]}",
            )

        incident = _incident_manager.create_incident(
            system_id=system_id,
            system_name=system_info.get("system_name", system_id),
            severity=severity,
            title=req.title,
            description=req.description,
            evidence_entry_ids=req.evidence_entry_ids,
            affected_persons_estimate=req.affected_persons_estimate,
            detected_by=req.detected_by,
        )

        result: dict[str, Any] = {
            "incident_id": incident.incident_id,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "article_62_required": incident.article_62_required,
            "playbook_steps": incident.playbook_steps,
        }

        if incident.article_62_required:
            result["article_62_deadline"] = incident.article_62_deadline
            result["hours_remaining"] = round(
                incident.hours_until_article_62_deadline or 0, 1
            )
            result["article_62_warning"] = (
                "SERIOUS INCIDENT: EU AI Act Article 62 report required within 72 hours. "
                f"Deadline: {incident.article_62_deadline}"
            )

        return result

    # ------------------------------------------------------------------
    # GET /dashboard
    # ------------------------------------------------------------------

    @app.get(
        "/dashboard",
        summary="Aggregate compliance posture across all registered systems",
        tags=["Dashboard"],
    )
    async def dashboard(
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        chain = _get_chain()
        try:
            qe = QueryEngine(chain)
            stats = qe.aggregate_stats()
            a12 = check_article_12_compliance(chain)
            tamper = chain.verify_chain()
        finally:
            chain.close()

        incident_summary = _incident_manager.summary()
        enforcement = enforcement_status()
        days = days_until_enforcement("high_risk_systems")

        total_cost = sum(
            e.cost_usd
            for e in qe.filter(limit=10000)
        ) if hasattr(qe, "filter") else 0.0

        return {
            "summary": {
                "total_entries": stats["total_decisions"],
                "unique_sessions": stats["unique_sessions"],
                "total_cost_usd": round(total_cost, 6),
                "registered_systems": len(_registered_systems),
            },
            "chain_integrity": {
                "valid": tamper.is_valid,
                "merkle_root": tamper.merkle_root,
                "tampered_entries": len(tamper.tampered_entries),
                "verified_at": tamper.verified_at,
            },
            "eu_ai_act": {
                "article_12_score": a12.score,
                "days_until_high_risk_enforcement": days,
                "enforcement_status": enforcement,
            },
            "incidents": incident_summary,
            "risk_distribution": stats["by_risk_tier"],
            "token_usage": {
                "total_input": stats["total_input_tokens"],
                "total_output": stats["total_output_tokens"],
            },
            "latency": {
                "avg_ms": stats["avg_latency_ms"],
                "p95_ms": stats["p95_latency_ms"],
            },
        }

    # ------------------------------------------------------------------
    # POST /verify-chain
    # ------------------------------------------------------------------

    @app.post(
        "/verify-chain",
        summary="Verify entire chain integrity, return tamper report",
        tags=["Chain Integrity"],
    )
    async def verify_chain(
        req: ChainVerifyRequest,
        _auth: None = Depends(_verify_api_key),
    ) -> dict[str, Any]:
        chain = _get_chain()
        try:
            report = chain.verify_chain()
        finally:
            chain.close()

        return {
            "is_valid": report.is_valid,
            "total_entries_verified": report.total_entries,
            "tampered_entries": report.tampered_entries,
            "tampered_count": len(report.tampered_entries),
            "errors": report.errors[:20],
            "merkle_root": report.merkle_root,
            "confidence": report.confidence,
            "verified_at": report.verified_at,
            "verdict": (
                "CLEAN — No tampering detected. All entries hash-verified."
                if report.is_valid
                else f"TAMPERED — {len(report.tampered_entries)} entries compromised. Evidence preserved."
            ),
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.get("/health", tags=["Meta"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "version": "2.0.0",
            "enforcement_countdown": f"{days_until_enforcement('high_risk_systems')} days until EU AI Act HIGH risk",
        }

else:
    # Stub app object so import doesn't fail when FastAPI is not installed
    app = None  # type: ignore[assignment]


def run_dev_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Launch the development server. Requires uvicorn."""
    if not _HAS_FASTAPI:
        raise RuntimeError("pip install fastapi uvicorn to use the REST API")
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError("pip install uvicorn") from e
    uvicorn.run("ai_audit_trail.api:app", host=host, port=port, reload=True)
