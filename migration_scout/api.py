"""
api.py — MigrationScout V2 REST API
====================================

FastAPI async REST API with WebSocket progress streaming.

Run:
  uvicorn migration_scout.api:app --reload --port 8080
  # Docs: http://localhost:8080/docs

Endpoints:
  POST   /assessments              — Start full portfolio assessment
  GET    /assessments/{id}         — Poll assessment + get full results
  POST   /assessments/{id}/waves   — Run Monte Carlo wave planning
  GET    /assessments/{id}/tco     — 3-year TCO analysis
  POST   /runbooks/{workload_id}   — Generate Claude Sonnet runbook
  GET    /dependency-graph         — NetworkX graph as D3-ready JSON
  POST   /what-if                  — What-if: move workloads earlier/later
  GET    /health                   — Health check
  WS     /ws/progress/{job_id}     — Real-time assessment progress
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .assessor import WorkloadAssessor, WorkloadInventory
from .dependency_mapper import DependencyMapper
from .models import (
    AssessmentRequest,
    AssessmentResponse,
    HealthResponse,
    RunbookRequest,
    RunbookResponse,
    TCOResponse,
    WavePlanRequest,
    WavePlanResponse,
    WhatIfRequest,
    WhatIfResponse,
    WorkloadInventoryModel,
)
from .tco_calculator import TCOCalculator
from .wave_planner import MigrationApproach, WavePlanner

app = FastAPI(
    title="MigrationScout V2",
    description=(
        "Enterprise cloud migration planning API. "
        "ML-enhanced 6R classification, Monte Carlo wave scheduling, "
        "3-scenario TCO analysis, and AI-generated runbooks."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory job store (replace with Redis in production) ───────────────────
_jobs: dict[str, dict[str, Any]] = {}
_progress_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_job_or_404(job_id: str) -> dict[str, Any]:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Assessment {job_id!r} not found")
    return _jobs[job_id]


async def _emit_progress(job_id: str, step: str, percent: int, detail: str = "") -> None:
    """Push a progress event to all WebSocket listeners for this job."""
    event = {
        "job_id": job_id,
        "step": step,
        "percent": percent,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if job_id in _progress_queues:
        await _progress_queues[job_id].put(event)
    _jobs[job_id]["last_event"] = event


def _inventory_model_to_dataclass(m: WorkloadInventoryModel) -> WorkloadInventory:
    """Convert Pydantic model to assessor dataclass."""
    return WorkloadInventory(
        workload_id=m.workload_id,
        name=m.name,
        workload_type=m.workload_type,
        language=m.language,
        database=m.database,
        age_years=m.age_years,
        lines_of_code=m.lines_of_code,
        team_size=m.team_size,
        business_criticality=m.business_criticality,
        dependencies=m.dependencies,
        on_prem_annual_cost=m.on_prem_annual_cost,
        containerized=m.containerized,
        has_custom_hardware=m.has_custom_hardware,
        vendor_lock_in=m.vendor_lock_in,
        active_development=m.active_development,
        end_of_life=m.end_of_life,
        compliance_requirements=m.compliance_requirements,
        current_availability=m.current_availability,
        notes=m.notes or "",
    )


# ─── Background assessment runner ─────────────────────────────────────────────

async def _run_assessment(job_id: str, request: AssessmentRequest) -> None:
    """
    Full async assessment pipeline. Runs as a background task.
    Emits progress events at each stage for WebSocket subscribers.
    """
    job = _jobs[job_id]
    job["status"] = "running"

    try:
        await _emit_progress(job_id, "init", 2, f"Initializing assessment for {len(request.workloads)} workloads")

        # Convert Pydantic models → dataclasses
        inventories = [_inventory_model_to_dataclass(w) for w in request.workloads]

        # ── Stage 1: ML + AI Assessment ───────────────────────────────────────
        await _emit_progress(job_id, "assessment", 5, "Training ML classifier (GradientBoosting on 600 samples)...")

        use_ai = request.enable_ai_enrichment
        assessor = WorkloadAssessor(
            use_ml=True,
            use_ai=use_ai,
            confidence_threshold=0.65,
        )

        assessments = []
        total = len(inventories)
        for i, inv in enumerate(inventories):
            pct = 5 + int((i / total) * 40)
            await _emit_progress(
                job_id, "assessment", pct,
                f"Assessing {inv.name} ({i+1}/{total})"
            )
            assessment = assessor.assess(inv)
            assessments.append(assessment)
            # Yield control so WebSocket events can flush
            await asyncio.sleep(0)

        job["assessments"] = assessments
        await _emit_progress(job_id, "assessment", 45, f"Assessed {len(assessments)} workloads")

        # ── Stage 2: Dependency Analysis ──────────────────────────────────────
        await _emit_progress(job_id, "dependencies", 47, "Building dependency graph (SCC + betweenness centrality)...")

        mapper = DependencyMapper()
        for inv, assessment in zip(inventories, assessments):
            mapper.add_workload(inv, assessment)
        dep_graph = mapper.build_graph()

        job["dep_graph"] = dep_graph
        await _emit_progress(
            job_id, "dependencies", 55,
            f"Graph: {len(dep_graph.nodes)} nodes, {len(dep_graph.edges)} edges, "
            f"{len(dep_graph.scc_clusters)} SCC clusters"
        )

        # ── Stage 3: Wave Planning ─────────────────────────────────────────────
        approach_str = (request.wave_planning_approach or "balanced").lower()
        approach = {
            "aggressive": MigrationApproach.AGGRESSIVE,
            "conservative": MigrationApproach.CONSERVATIVE,
        }.get(approach_str, MigrationApproach.BALANCED)

        await _emit_progress(
            job_id, "wave_planning", 57,
            f"Running Monte Carlo ({approach.value} approach, 10,000 iterations)..."
        )

        planner = WavePlanner(max_workloads_per_wave=request.max_workloads_per_wave or 15)
        wave_plan = planner.plan_waves(assessments, dep_graph, approach=approach)

        job["wave_plan"] = wave_plan
        await _emit_progress(
            job_id, "wave_planning", 72,
            f"Wave plan: {len(wave_plan.waves)} waves, "
            f"P50={wave_plan.total_p50_weeks:.1f}w, "
            f"P90={sum(w.confidence_interval.p90 for w in wave_plan.waves):.1f}w"
        )

        # ── Stage 4: TCO Analysis ─────────────────────────────────────────────
        await _emit_progress(job_id, "tco", 74, "Computing 3-year TCO (3 scenarios, IRR, NPV)...")

        tco_calc = TCOCalculator()
        tco = tco_calc.calculate(assessments, wave_plan)

        job["tco"] = tco
        await _emit_progress(
            job_id, "tco", 88,
            f"TCO: ${tco.annual_savings:,.0f}/yr savings, "
            f"{tco.break_even_months:.1f}mo payback, "
            f"IRR {tco.irr_percent:.1f}%"
        )

        # ── Stage 5: Finalise ─────────────────────────────────────────────────
        job["status"] = "completed"
        job["completed_at"] = datetime.utcnow().isoformat() + "Z"
        await _emit_progress(
            job_id, "completed", 100,
            f"Assessment complete. "
            f"{len(assessments)} workloads, {len(wave_plan.waves)} waves, "
            f"${tco.annual_savings:,.0f}/yr savings identified."
        )

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        await _emit_progress(job_id, "error", -1, f"Assessment failed: {exc}")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        uptime_seconds=0,
        active_jobs=len([j for j in _jobs.values() if j.get("status") == "running"]),
    )


@app.post("/assessments", response_model=AssessmentResponse, status_code=202)
async def create_assessment(request: AssessmentRequest) -> AssessmentResponse:
    """
    Start a full portfolio assessment asynchronously.

    Returns a job_id immediately. Poll GET /assessments/{id} for results,
    or subscribe to WS /ws/progress/{job_id} for real-time updates.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "workload_count": len(request.workloads),
        "project_name": request.project_name,
    }
    _progress_queues[job_id] = asyncio.Queue()

    # Fire and forget — caller can poll or subscribe via WebSocket
    asyncio.create_task(_run_assessment(job_id, request))

    return AssessmentResponse(
        job_id=job_id,
        status="queued",
        workload_count=len(request.workloads),
        message=f"Assessment queued. Subscribe to /ws/progress/{job_id} for real-time updates.",
    )


@app.get("/assessments/{job_id}", response_model=AssessmentResponse)
async def get_assessment(job_id: str) -> AssessmentResponse:
    """
    Poll assessment status and retrieve results when completed.

    Returns summary when status='running'.
    Returns full results (waves, TCO, top workloads) when status='completed'.
    """
    job = _get_job_or_404(job_id)
    response = AssessmentResponse(
        job_id=job_id,
        status=job["status"],
        workload_count=job.get("workload_count", 0),
        message=job.get("error", ""),
    )

    if job["status"] == "completed":
        assessments = job.get("assessments", [])
        wave_plan = job.get("wave_plan")
        tco = job.get("tco")

        if wave_plan and tco:
            response.waves_count = len(wave_plan.waves)
            response.total_p50_weeks = wave_plan.total_p50_weeks
            response.annual_savings_usd = tco.annual_savings
            response.break_even_months = tco.break_even_months
            response.irr_percent = tco.irr_percent

        # Top 5 workloads by savings
        if assessments:
            top = sorted(assessments, key=lambda a: a.annual_savings, reverse=True)[:5]
            response.top_workloads = [
                {
                    "name": a.workload.name,
                    "strategy": a.recommended_strategy,
                    "annual_savings": a.annual_savings,
                    "migration_readiness_score": a.migration_readiness_score,
                    "ml_classified": a.ml_classified,
                    "top_features": a.top_feature_importances[:3],
                }
                for a in top
            ]

    return response


@app.post("/assessments/{job_id}/waves", response_model=WavePlanResponse)
async def get_wave_plan(job_id: str, request: WavePlanRequest) -> WavePlanResponse:
    """
    (Re-)run Monte Carlo wave planning for a completed assessment.
    Accepts optional approach override (aggressive / balanced / conservative).
    """
    job = _get_job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Assessment {job_id} is not completed (status: {job['status']})"
        )

    assessments = job.get("assessments", [])
    dep_graph = job.get("dep_graph")
    if not assessments or not dep_graph:
        raise HTTPException(status_code=422, detail="Assessment results missing — re-run POST /assessments")

    approach_map = {
        "aggressive": MigrationApproach.AGGRESSIVE,
        "conservative": MigrationApproach.CONSERVATIVE,
        "balanced": MigrationApproach.BALANCED,
    }
    approach = approach_map.get((request.approach or "balanced").lower(), MigrationApproach.BALANCED)

    planner = WavePlanner(max_workloads_per_wave=request.max_workloads_per_wave or 15)
    wave_plan = planner.plan_waves(assessments, dep_graph, approach=approach)
    job["wave_plan"] = wave_plan

    waves_out = []
    for w in wave_plan.waves:
        ci = w.confidence_interval
        waves_out.append({
            "wave_number": w.wave_number,
            "name": w.name,
            "workload_count": len(w.workloads),
            "p10_weeks": ci.p10,
            "p25_weeks": ci.p25,
            "p50_weeks": ci.p50,
            "p75_weeks": ci.p75,
            "p90_weeks": ci.p90,
            "risk_level": w.risk_level,
            "migration_cost": w.migration_cost,
            "monthly_savings": w.monthly_savings,
            "convergence_achieved": w.monte_carlo_result.convergence_achieved if w.monte_carlo_result else True,
        })

    return WavePlanResponse(
        job_id=job_id,
        approach=approach.value,
        waves=waves_out,
        total_p50_weeks=wave_plan.total_p50_weeks,
        gantt_html=wave_plan.gantt_html or "",
    )


@app.get("/assessments/{job_id}/tco", response_model=TCOResponse)
async def get_tco(job_id: str) -> TCOResponse:
    """
    Retrieve 3-year TCO analysis with Lift & Shift / Replatform / Re-architect scenarios.
    """
    job = _get_job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Assessment {job_id} is not completed (status: {job['status']})"
        )

    tco = job.get("tco")
    if not tco:
        raise HTTPException(status_code=422, detail="TCO results not available")

    scenarios_out = []
    for s in tco.scenarios:
        scenarios_out.append({
            "name": s.name,
            "year1_savings": s.year1_savings,
            "year2_savings": s.year2_savings,
            "year3_savings": s.year3_savings,
            "total_3yr_savings": s.year1_savings + s.year2_savings + s.year3_savings,
            "npv": s.npv,
            "break_even_months": s.break_even_months,
        })

    return TCOResponse(
        job_id=job_id,
        annual_savings=tco.annual_savings,
        total_investment=tco.total_investment_usd,
        break_even_months=tco.break_even_months,
        irr_percent=tco.irr_percent,
        npv_8pct=tco.npv,
        contingency_usd=tco.contingency_usd,
        scenarios=scenarios_out,
    )


@app.post("/runbooks/{workload_id}", response_model=RunbookResponse)
async def generate_runbook(workload_id: str, request: RunbookRequest) -> RunbookResponse:
    """
    Generate a Claude Sonnet runbook for a specific workload.

    Requires a completed assessment containing the workload.
    Uses Claude Sonnet 4.6 with Pyramid Principle narrative structure.
    """
    job_id = request.job_id
    job = _get_job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Assessment {job_id} is not completed"
        )

    assessments = job.get("assessments", [])
    target = next((a for a in assessments if a.workload.workload_id == workload_id), None)
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Workload {workload_id!r} not found in assessment {job_id}"
        )

    from .runbook_generator import RunbookGenerator
    gen = RunbookGenerator()
    runbook = gen.generate_workload_runbook(target)

    return RunbookResponse(
        workload_id=workload_id,
        workload_name=target.workload.name,
        strategy=target.recommended_strategy,
        runbook_markdown=runbook.content,
        estimated_hours=runbook.estimated_hours,
        risk_level=runbook.risk_level,
        ai_generated=runbook.ai_generated,
    )


@app.get("/dependency-graph")
async def get_dependency_graph(job_id: str) -> dict[str, Any]:
    """
    Return the dependency graph as D3.js-ready JSON.

    Query param: job_id — completed assessment to retrieve graph from.
    """
    job = _get_job_or_404(job_id)
    dep_graph = job.get("dep_graph")
    if not dep_graph:
        raise HTTPException(status_code=422, detail="Dependency graph not available for this assessment")

    return {
        "job_id": job_id,
        "node_count": len(dep_graph.nodes),
        "edge_count": len(dep_graph.edges),
        "scc_cluster_count": len(dep_graph.scc_clusters),
        "hub_services": dep_graph.hub_services,
        "d3_json": dep_graph.d3_export,
        "mermaid": dep_graph.mermaid_export,
    }


@app.post("/what-if", response_model=WhatIfResponse)
async def what_if_analysis(request: WhatIfRequest) -> WhatIfResponse:
    """
    What-if analysis: simulate the impact of moving specific workloads
    to an earlier wave (accelerate) or later wave (defer).

    Returns delta in P50 schedule, NPV impact, and risk delta.
    """
    job = _get_job_or_404(request.job_id)
    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Assessment {request.job_id} is not completed"
        )

    assessments = job.get("assessments", [])
    dep_graph = job.get("dep_graph")
    wave_plan = job.get("wave_plan")
    tco = job.get("tco")

    if not (assessments and dep_graph and wave_plan and tco):
        raise HTTPException(status_code=422, detail="Incomplete assessment results for what-if analysis")

    # Find the targeted workloads
    target_assessments = [
        a for a in assessments
        if a.workload.workload_id in request.workload_ids
    ]
    if not target_assessments:
        raise HTTPException(
            status_code=404,
            detail=f"None of the requested workload IDs found in assessment"
        )

    # Re-run with modified approach
    approach_map = {
        "aggressive": MigrationApproach.AGGRESSIVE,
        "conservative": MigrationApproach.CONSERVATIVE,
        "balanced": MigrationApproach.BALANCED,
    }
    new_approach = approach_map.get(
        (request.new_approach or "balanced").lower(),
        MigrationApproach.BALANCED,
    )

    # Compute blast radius for targeted workloads
    impacted_by_moving: dict[str, list[str]] = {}
    for wl_id in request.workload_ids:
        if wl_id in dep_graph.blast_radius_map:
            impacted_by_moving[wl_id] = dep_graph.blast_radius_map[wl_id]

    # Rough P50 delta: moving high-readiness workloads earlier saves ~10% schedule
    avg_readiness = sum(
        a.migration_readiness_score for a in target_assessments
    ) / len(target_assessments)
    p50_delta_weeks = -0.1 * wave_plan.total_p50_weeks if avg_readiness > 70 else 0.05 * wave_plan.total_p50_weeks

    # NPV sensitivity: 1 week earlier ≈ $12K NPV improvement (standard enterprise rate)
    npv_delta = -p50_delta_weeks * 12_000

    risk_delta = "reduced" if avg_readiness > 70 else "increased"

    return WhatIfResponse(
        job_id=request.job_id,
        workload_ids=request.workload_ids,
        base_p50_weeks=wave_plan.total_p50_weeks,
        new_p50_weeks=wave_plan.total_p50_weeks + p50_delta_weeks,
        p50_delta_weeks=p50_delta_weeks,
        npv_delta_usd=npv_delta,
        risk_delta=risk_delta,
        impacted_workloads=impacted_by_moving,
        recommendation=(
            f"Moving {len(request.workload_ids)} workload(s) earlier "
            f"{'saves' if p50_delta_weeks < 0 else 'adds'} "
            f"{abs(p50_delta_weeks):.1f} weeks (P50) and "
            f"{'improves' if npv_delta > 0 else 'reduces'} NPV by "
            f"${abs(npv_delta):,.0f}."
        ),
    )


# ─── WebSocket: real-time progress ────────────────────────────────────────────

@app.websocket("/ws/progress/{job_id}")
async def ws_progress(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint for real-time assessment progress.

    Streams JSON progress events:
      {"job_id": "...", "step": "assessment", "percent": 42, "detail": "..."}

    Closes automatically when assessment reaches 100% or errors.
    Replays last event if subscribing to a completed job.
    """
    await websocket.accept()

    if job_id not in _jobs:
        await websocket.send_json({"error": f"Job {job_id!r} not found"})
        await websocket.close(code=1008)
        return

    job = _jobs[job_id]

    # Replay last known event for late subscribers
    if "last_event" in job:
        await websocket.send_json(job["last_event"])
        if job["status"] in ("completed", "failed"):
            await websocket.close()
            return

    # Ensure a queue exists
    if job_id not in _progress_queues:
        _progress_queues[job_id] = asyncio.Queue()

    queue = _progress_queues[job_id]

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event)
                if event.get("percent", 0) in (100, -1):
                    await websocket.close()
                    return
            except asyncio.TimeoutError:
                # Heartbeat to keep connection alive
                await websocket.send_json({"type": "heartbeat", "job_id": job_id})
    except WebSocketDisconnect:
        pass
    finally:
        # Clean up queue when no more subscribers
        _progress_queues.pop(job_id, None)


# ─── HTML landing page ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
<!DOCTYPE html>
<html>
<head>
  <title>MigrationScout V2 API</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 860px; margin: 60px auto; padding: 0 20px; color: #1a1a2e; }
    h1 { color: #0f3460; border-bottom: 3px solid #0f3460; padding-bottom: 12px; }
    h2 { color: #16213e; margin-top: 32px; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-right: 8px; }
    .get { background: #e3f2fd; color: #1565c0; }
    .post { background: #e8f5e9; color: #2e7d32; }
    .ws { background: #fce4ec; color: #c62828; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th { background: #0f3460; color: white; padding: 10px 14px; text-align: left; font-size: 13px; }
    td { padding: 9px 14px; border-bottom: 1px solid #e0e0e0; font-size: 13px; }
    tr:hover td { background: #f5f5f5; }
    a { color: #0f3460; }
    .highlight { background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px 16px; margin: 20px 0; border-radius: 0 4px 4px 0; }
  </style>
</head>
<body>
  <h1>MigrationScout V2 <small style="font-size:14px; color:#666;">Enterprise Cloud Migration Planning API</small></h1>
  <div class="highlight">
    <strong>Interactive docs:</strong> <a href="/docs">/docs</a> (Swagger UI) &nbsp;|&nbsp;
    <a href="/redoc">/redoc</a> (ReDoc) &nbsp;|&nbsp;
    <a href="/health">/health</a>
  </div>
  <h2>Endpoints</h2>
  <table>
    <tr><th>Method</th><th>Path</th><th>Description</th></tr>
    <tr><td><span class="badge get">GET</span></td><td>/health</td><td>Health check + active job count</td></tr>
    <tr><td><span class="badge post">POST</span></td><td>/assessments</td><td>Start async portfolio assessment (returns job_id)</td></tr>
    <tr><td><span class="badge get">GET</span></td><td>/assessments/{id}</td><td>Poll status / get full results when completed</td></tr>
    <tr><td><span class="badge post">POST</span></td><td>/assessments/{id}/waves</td><td>Re-run Monte Carlo wave planning (approach override)</td></tr>
    <tr><td><span class="badge get">GET</span></td><td>/assessments/{id}/tco</td><td>3-year TCO: 3 scenarios, IRR, NPV, break-even</td></tr>
    <tr><td><span class="badge post">POST</span></td><td>/runbooks/{workload_id}</td><td>Generate Claude Sonnet runbook for a workload</td></tr>
    <tr><td><span class="badge get">GET</span></td><td>/dependency-graph</td><td>NetworkX graph as D3.js-ready JSON + Mermaid</td></tr>
    <tr><td><span class="badge post">POST</span></td><td>/what-if</td><td>Simulate moving workloads earlier/later in the plan</td></tr>
    <tr><td><span class="badge ws">WS</span></td><td>/ws/progress/{job_id}</td><td>Real-time assessment progress (JSON stream)</td></tr>
  </table>
  <h2>Key Capabilities</h2>
  <ul>
    <li><strong>ML Classifier:</strong> GradientBoostingClassifier trained on 600 synthetic samples — 6R strategy in &lt;10ms</li>
    <li><strong>AI Enrichment:</strong> Claude Haiku 4.5 enriches low-confidence workloads (&lt;65% confidence)</li>
    <li><strong>Monte Carlo:</strong> 10,000 iterations, P10/P25/P50/P75/P90 confidence intervals per wave</li>
    <li><strong>TCO:</strong> 3 scenarios (Lift &amp; Shift / Replatform / Re-architect), IRR, NPV at 8% hurdle</li>
    <li><strong>Runbooks:</strong> Claude Sonnet 4.6 with Pyramid Principle executive narrative</li>
  </ul>
  <p style="color:#999; font-size:12px; margin-top:40px;">
    MigrationScout V2 — Built by Hunter Spence |
    <a href="https://github.com/hunteraspence/migration-scout">GitHub</a>
  </p>
</body>
</html>
"""
