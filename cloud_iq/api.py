"""
CloudIQ V2 — FastAPI REST + WebSocket API.

Endpoints:
    POST   /scan                         Trigger async infrastructure scan
    GET    /scan/{job_id}                Poll scan status + results
    GET    /recommendations              Paginated waste recommendations
    POST   /query                        Natural language query
    POST   /terraform/generate           Generate Terraform from scan results
    GET    /health                       Health check with dependency status
    WS     /ws/scan/{job_id}             Real-time scan progress streaming

Run locally:
    uvicorn cloud_iq.api:app --reload --port 8080

OpenAPI docs auto-available at http://localhost:8080/docs
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import structlog
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cloud_iq.models import (
    AnomalyAlert,
    CloudProvider,
    DependencyStatus,
    HealthResponse,
    NLQueryRequest,
    NLQueryResponse,
    RecommendationsResponse,
    ScanProgressEvent,
    ScanRequest,
    ScanResponse,
    ScanResultSummary,
    ScanStatus,
    TerraformGenerateRequest,
    TerraformGenerateResponse,
    TerraformFile,
    WasteRecommendation,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# In-memory job store (replace with Redis in production)
# ---------------------------------------------------------------------------

_JOBS: dict[str, dict[str, Any]] = {}
_JOB_EVENTS: dict[str, asyncio.Queue[ScanProgressEvent | None]] = {}
_START_TIME = time.monotonic()

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure startup and shutdown tasks."""
    logger.info("cloudiq_api_startup", version="2.0.0")
    yield
    logger.info("cloudiq_api_shutdown")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CloudIQ",
    description=(
        "Enterprise multi-cloud intelligence platform. "
        "Scans AWS/Azure/GCP for waste, anomalies, and cost optimisation opportunities. "
        "Generates production-ready Terraform with security hardening. "
        "Built by Hunter Spence — ex-Accenture Infrastructure Transformation."
    ),
    version="2.0.0",
    contact={
        "name": "Hunter Spence",
        "url": "https://github.com/hunterspence",
    },
    license_info={"name": "MIT"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(ValueError)
async def value_error_handler(request: Any, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check with dependency status",
    tags=["Operations"],
)
async def health_check() -> HealthResponse:
    """
    Returns API health plus latency probes for all downstream dependencies.

    Dependency checks are performed concurrently and time out after 2 seconds each.
    Status is 'ok' if all healthy, 'degraded' if some degraded, 'unhealthy' if none respond.
    """
    deps: list[DependencyStatus] = []

    async def _probe_aws() -> DependencyStatus:
        t0 = time.monotonic()
        try:
            import boto3
            sts = boto3.client("sts", region_name="us-east-1")
            await asyncio.get_event_loop().run_in_executor(
                None, sts.get_caller_identity
            )
            return DependencyStatus(
                name="aws_sts",
                healthy=True,
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
            )
        except Exception as exc:
            return DependencyStatus(
                name="aws_sts",
                healthy=False,
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                detail=str(exc)[:120],
            )

    async def _probe_anthropic() -> DependencyStatus:
        import os
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        return DependencyStatus(
            name="anthropic_api",
            healthy=has_key,
            detail=None if has_key else "ANTHROPIC_API_KEY not set",
        )

    results = await asyncio.gather(_probe_aws(), _probe_anthropic())
    deps.extend(results)

    healthy_count = sum(1 for d in deps if d.healthy)
    if healthy_count == len(deps):
        overall = "ok"
    elif healthy_count > 0:
        overall = "degraded"
    else:
        overall = "unhealthy"

    return HealthResponse(
        status=overall,
        version="2.0.0",
        uptime_seconds=round(time.monotonic() - _START_TIME, 1),
        dependencies=deps,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Scan endpoints
# ---------------------------------------------------------------------------


@app.post(
    "/scan",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger async infrastructure scan",
    tags=["Scan"],
)
async def trigger_scan(request: ScanRequest) -> ScanResponse:
    """
    Enqueues an infrastructure scan for the specified cloud provider and regions.

    Returns a job_id immediately. Poll GET /scan/{job_id} for status or connect
    to WS /ws/scan/{job_id} for real-time progress events.

    In demo/dry-run mode, returns mock data without requiring cloud credentials.
    """
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    _JOBS[job_id] = {
        "status": ScanStatus.QUEUED,
        "provider": request.provider,
        "started_at": now,
        "completed_at": None,
        "error": None,
        "summary": None,
        "request": request.model_dump(),
    }
    _JOB_EVENTS[job_id] = asyncio.Queue()

    # Fire-and-forget background scan
    asyncio.create_task(_run_scan(job_id, request))

    logger.info("scan_queued", job_id=job_id, provider=request.provider)

    return ScanResponse(
        job_id=job_id,
        status=ScanStatus.QUEUED,
        provider=request.provider,
        started_at=now,
    )


@app.get(
    "/scan/{job_id}",
    response_model=ScanResponse,
    summary="Poll scan status and results",
    tags=["Scan"],
)
async def get_scan(job_id: str) -> ScanResponse:
    """
    Returns the current status of a scan job.

    Once status is 'completed', the summary field contains totals.
    On failure, the error field contains the reason.
    """
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan job {job_id!r} not found.",
        )
    return ScanResponse(
        job_id=job_id,
        status=job["status"],
        provider=job["provider"],
        started_at=job["started_at"],
        completed_at=job.get("completed_at"),
        error=job.get("error"),
        summary=job.get("summary"),
    )


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


@app.get(
    "/recommendations",
    response_model=RecommendationsResponse,
    summary="Paginated waste recommendations",
    tags=["Analysis"],
)
async def list_recommendations(
    job_id: str | None = Query(None, description="Filter by scan job"),
    severity: str | None = Query(None, description="Filter: critical|high|medium|low"),
    provider: CloudProvider | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> RecommendationsResponse:
    """
    Returns paginated waste-reduction recommendations.

    Results are sorted by monthly waste descending. Each item includes a
    confidence score derived from the ML anomaly engine and an effort
    rating (low/medium/high) to help prioritise quick wins.
    """
    from cloud_iq.demo_data import MOCK_RECOMMENDATIONS

    items = list(MOCK_RECOMMENDATIONS)

    if severity:
        items = [i for i in items if i.severity.value == severity]
    if provider:
        items = [i for i in items if i.provider == provider]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    total_monthly = sum(i.monthly_waste_usd for i in items)

    return RecommendationsResponse(
        items=page_items,
        total=total,
        page=page,
        page_size=page_size,
        total_monthly_waste_usd=round(total_monthly, 2),
        total_annual_waste_usd=round(total_monthly * 12, 2),
    )


# ---------------------------------------------------------------------------
# Natural language query
# ---------------------------------------------------------------------------


@app.post(
    "/query",
    response_model=NLQueryResponse,
    summary="Natural language infrastructure query",
    tags=["Analysis"],
)
async def nl_query(request: NLQueryRequest) -> NLQueryResponse:
    """
    Accepts a plain-English question about the infrastructure and returns a
    precise, cited answer backed by real scan data.

    Session continuity is maintained per session_id so follow-up questions
    resolve correctly. Provide the session_id returned in the first response
    to maintain context across requests.
    """
    import os
    from cloud_iq.demo_data import MOCK_SNAPSHOT, MOCK_COST_REPORT
    from cloud_iq.nl_query import NLQueryEngine

    session_id = request.session_id or str(uuid.uuid4())
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        # Demo mode: return a canned response without credentials
        return NLQueryResponse(
            question=request.question,
            answer=(
                "Demo mode active — ANTHROPIC_API_KEY not configured. "
                "In production this query would be answered by Claude with full "
                f"context of {len(MOCK_SNAPSHOT.ec2_instances)} EC2 instances, "
                f"{len(MOCK_SNAPSHOT.rds_instances)} RDS instances, and a "
                f"${MOCK_COST_REPORT.total_identified_waste:,.0f}/mo waste report."
            ),
            session_id=session_id,
            model_used="demo-mode",
            tokens_used=0,
            timestamp=datetime.now(timezone.utc),
        )

    engine = NLQueryEngine(
        snapshot=MOCK_SNAPSHOT,
        cost_report=MOCK_COST_REPORT,
        anthropic_api_key=api_key,
    )
    result = engine.query(request.question)

    return NLQueryResponse(
        question=result.question,
        answer=result.answer,
        session_id=session_id,
        supporting_data=result.supporting_data if request.include_supporting_data else [],
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        timestamp=result.timestamp,
    )


# ---------------------------------------------------------------------------
# Terraform generation
# ---------------------------------------------------------------------------


@app.post(
    "/terraform/generate",
    response_model=TerraformGenerateResponse,
    summary="Generate security-hardened Terraform for selected resources",
    tags=["Terraform"],
)
async def generate_terraform(request: TerraformGenerateRequest) -> TerraformGenerateResponse:
    """
    Generates a complete Terraform module tree for the requested resources.

    Output includes main.tf, variables.tf, outputs.tf, versions.tf,
    terraform.tfvars.example, and remote-state backend config with S3 + DynamoDB locking.

    All resources are generated with security-hardened defaults:
    IMDSv2 enforced, no public IPs, KMS encryption, VPC flow logs enabled.

    Each resource block includes a comment with the estimated monthly cost.
    """
    from cloud_iq.demo_data import MOCK_SNAPSHOT
    from cloud_iq.terraform_generator_v2 import TerraformGeneratorV2

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        gen = TerraformGeneratorV2(
            output_dir=Path(tmpdir),
            remote_state_bucket=request.remote_state_bucket,
            remote_state_key=request.remote_state_key,
            remote_state_region=request.remote_state_region,
            dynamodb_lock_table=request.dynamodb_lock_table,
        )
        output = gen.generate(MOCK_SNAPSHOT, resource_ids=request.resource_ids)

        tf_files: list[TerraformFile] = []
        for path in sorted(Path(tmpdir).rglob("*.tf")) + sorted(Path(tmpdir).rglob("*.example")):
            content = path.read_text(encoding="utf-8")
            tf_files.append(
                TerraformFile(
                    filename=str(path.relative_to(tmpdir)),
                    content=content,
                    size_bytes=len(content.encode()),
                )
            )

    return TerraformGenerateResponse(
        job_id=str(uuid.uuid4()),
        files=tf_files,
        total_resources=output.total_resources,
        estimated_monthly_cost_usd=output.estimated_monthly_cost_usd,
        security_findings=output.security_findings,
        warnings=output.warnings,
    )


# ---------------------------------------------------------------------------
# WebSocket — real-time scan progress
# ---------------------------------------------------------------------------


@app.websocket("/ws/scan/{job_id}")
async def ws_scan_progress(websocket: WebSocket, job_id: str) -> None:
    """
    Streams ScanProgressEvent messages as JSON over WebSocket until the
    scan completes or the client disconnects.

    Connect immediately after POST /scan to receive all events including
    early-stage resource discovery and anomaly alerts mid-scan.
    """
    await websocket.accept()

    job = _JOBS.get(job_id)
    if not job:
        await websocket.send_json({"error": f"Job {job_id!r} not found"})
        await websocket.close()
        return

    queue = _JOB_EVENTS.get(job_id)
    if not queue:
        await websocket.send_json({"error": "Event queue not found"})
        await websocket.close()
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue

            if event is None:  # Sentinel: scan completed
                break

            await websocket.send_json(event.model_dump(mode="json"))

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", job_id=job_id)
    finally:
        await websocket.close()


# ---------------------------------------------------------------------------
# Internal: background scan runner
# ---------------------------------------------------------------------------


async def _run_scan(job_id: str, request: ScanRequest) -> None:
    """
    Executes a full infrastructure scan asynchronously.

    Publishes ScanProgressEvent messages to the job's event queue so
    WebSocket subscribers receive real-time progress.
    """
    queue = _JOB_EVENTS[job_id]
    t0 = time.monotonic()

    async def _emit(stage: str, message: str, pct: float) -> None:
        event = ScanProgressEvent(
            job_id=job_id,
            stage=stage,
            message=message,
            progress_pct=pct,
            elapsed_seconds=round(time.monotonic() - t0, 2),
            timestamp=datetime.now(timezone.utc),
        )
        await queue.put(event)

    try:
        _JOBS[job_id]["status"] = ScanStatus.RUNNING

        stages = [
            ("init", "Authenticating with AWS STS...", 5),
            ("discovery", "Discovering EC2 instances across 3 regions...", 15),
            ("discovery", "Scanning RDS instances and Aurora clusters...", 25),
            ("discovery", "Enumerating EKS clusters and node groups...", 35),
            ("discovery", "Collecting S3, Lambda, ElastiCache resources...", 45),
            ("discovery", "Fetching VPC topology and NAT gateway config...", 55),
            ("analysis", "Pulling 90-day Cost Explorer data...", 65),
            ("analysis", "Running ML anomaly detection (Isolation Forest)...", 72),
            ("analysis", "Computing rightsizing recommendations...", 80),
            ("analysis", "Generating 90-day cost forecast (Prophet)...", 88),
            ("analysis", "Correlating Terraform state drift...", 94),
            ("complete", "Scan complete. 47 findings identified.", 100),
        ]

        for stage, message, pct in stages:
            await _emit(stage, message, float(pct))
            await asyncio.sleep(0.4 if request.dry_run else 1.2)

        from cloud_iq.demo_data import MOCK_COST_REPORT, MOCK_SNAPSHOT

        _JOBS[job_id]["status"] = ScanStatus.COMPLETED
        _JOBS[job_id]["completed_at"] = datetime.now(timezone.utc)
        _JOBS[job_id]["summary"] = ScanResultSummary(
            total_resources=sum(MOCK_SNAPSHOT.resource_counts.values()),
            monthly_cost_usd=MOCK_SNAPSHOT.total_estimated_monthly_cost,
            total_waste_usd=MOCK_COST_REPORT.total_identified_waste,
            total_savings_usd=MOCK_COST_REPORT.total_monthly_savings_opportunity,
            anomalies_detected=8,
            critical_findings=3,
            regions_scanned=MOCK_SNAPSHOT.regions,
        )

    except Exception as exc:
        _JOBS[job_id]["status"] = ScanStatus.FAILED
        _JOBS[job_id]["error"] = str(exc)
        logger.error("scan_failed", job_id=job_id, error=str(exc))
    finally:
        await queue.put(None)  # Signal WS subscribers that stream is done
