"""
api.py — FastAPI REST + WebSocket API for FinOps Intelligence V2.

Endpoints:
  POST /ingest/cost-explorer     — ingest AWS Cost Explorer JSON
  POST /ingest/cur               — ingest CUR Parquet (DuckDB)
  GET  /anomalies                — paginated anomalies with severity filter
  POST /anomalies/{id}/acknowledge — mark as known/expected
  GET  /forecasts                — 30/60/90-day forecast with confidence bands
  GET  /optimization/recommendations — ranked savings opportunities
  POST /optimization/{id}/implement-plan — generate Terraform/CLI steps
  POST /query                    — NL query with Claude (stateful session)
  GET  /reports/cfo              — generate CFO HTML report
  WS   /ws/anomaly-stream        — real-time anomaly push (WebSocket)

Run:
    uvicorn finops_intelligence.api:app --reload --port 8765
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator

import pandas as pd
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from .analytics_engine import AnalyticsEngine
from .anomaly_detector_v2 import Anomaly, AnomalyDetectorV2, AnomalySeverity, SuppressionRule
from .commitment_optimizer import CommitmentOptimizer
from .cost_tracker import CostTracker, SpendData
from .forecaster import Forecaster
from .maturity_assessment import MaturityAssessment
from .nl_interface import ConversationSession, NLInterface
from .optimizer import Optimizer, OptimizationPlan
from .reporter import Reporter, ReportConfig
from .unit_economics import UnitEconomicsEngine


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

class AppState:
    """Global in-memory state shared across requests."""

    def __init__(self) -> None:
        self.spend_data: SpendData | None = None
        self.anomalies: list[Anomaly] = []
        self.optimization_plan: OptimizationPlan | None = None
        self.engine = AnalyticsEngine()
        self.detector = AnomalyDetectorV2(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.forecaster = Forecaster(use_prophet=False)
        self.optimizer = Optimizer(mock=False)
        self.nl_interface: NLInterface = NLInterface(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.sessions: dict[str, ConversationSession] = {}
        self.anomaly_subscribers: list[WebSocket] = []
        self.acknowledged_ids: set[str] = set()
        self.last_ingested: datetime | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: load mock data so the API works immediately."""
    tracker = CostTracker(mock=True, account_name="TechStartupCo Production")
    state.spend_data = tracker.fetch(days=730)  # 2 years
    state.engine.load_dataframe(state.spend_data.df)
    state.anomalies = state.detector.detect(state.spend_data)
    plan = Optimizer(mock=True).analyze(state.spend_data)
    state.optimization_plan = plan
    state.nl_interface.set_context(state.spend_data, state.anomalies, plan)
    state.last_ingested = datetime.utcnow()
    yield
    state.engine.close()


app = FastAPI(
    title="FinOps Intelligence API",
    description=(
        "Enterprise cloud cost intelligence API. "
        "Replaces CloudZero ($60K+/yr) — runs free, on-premise, zero data egress."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Pydantic V2 models
# ---------------------------------------------------------------------------

class CostExplorerIngestRequest(BaseModel):
    account_name: str = "Production"
    results_by_time: list[dict[str, Any]] = Field(
        ...,
        description="Raw ResultsByTime array from AWS Cost Explorer get_cost_and_usage response",
    )


class CURIngestResponse(BaseModel):
    rows_loaded: int
    services_found: int
    date_range: str
    ingest_time_ms: float
    total_spend: float


class AnomalyResponse(BaseModel):
    anomaly_id: str
    detected_at: str
    service: str
    amount: float
    baseline: float
    delta: float
    delta_pct: float
    severity: str
    confidence: float
    zscore: float
    ensemble_votes: int
    explanation: str
    root_cause_primary: str | None
    correlated_services: list[str]
    acknowledged: bool
    has_pagerduty_payload: bool


class AnomalyListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    anomalies: list[AnomalyResponse]


class AcknowledgeRequest(BaseModel):
    reason: str = "Expected / known event"
    acknowledged_by: str = "user"
    suppress_days: int = Field(default=0, ge=0, le=365)


class ForecastResponse(BaseModel):
    horizon_days: int
    total_predicted: float
    total_lower: float
    total_upper: float
    model_used: str
    mape: float
    trend: str
    trend_pct_per_month: float
    daily_points: list[dict[str, Any]]
    budget_status: str | None
    budget_exhaustion_date: str | None


class OptimizationRecommendationResponse(BaseModel):
    opportunity_id: str
    priority: int
    type: str
    title: str
    description: str
    savings_monthly: float
    savings_annual: float
    savings_pct: float
    effort: str
    risk: str
    confidence: float
    action: str
    resource_id: str


class ImplementationPlanRequest(BaseModel):
    include_terraform: bool = True
    include_cli: bool = True
    dry_run: bool = True


class ImplementationPlanResponse(BaseModel):
    opportunity_id: str
    title: str
    terraform_snippet: str | None
    cli_commands: list[str]
    estimated_minutes: int
    risk_assessment: str
    rollback_steps: list[str]


class NLQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    session_id: str | None = None
    model: str | None = None

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question cannot be blank")
        return v.strip()


class NLQueryResponse(BaseModel):
    question: str
    answer: str
    model_used: str
    input_tokens: int
    output_tokens: int
    session_id: str
    response_time_ms: float


class IngestStatsResponse(BaseModel):
    row_count: int
    service_count: int
    date_range_days: int
    min_date: str | None
    max_date: str | None
    total_spend: float
    last_ingested: str | None


# ---------------------------------------------------------------------------
# Dependency: require spend data loaded
# ---------------------------------------------------------------------------

def require_spend_data() -> SpendData:
    if state.spend_data is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No cost data loaded. POST to /ingest/cost-explorer or /ingest/cur first.",
        )
    return state.spend_data


# ---------------------------------------------------------------------------
# Ingest endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health() -> dict[str, Any]:
    stats = await state.engine.query_ingest_stats()
    return {
        "status": "ok",
        "version": "2.0.0",
        "data_loaded": state.spend_data is not None,
        "row_count": stats.get("row_count", 0),
        "last_ingested": state.last_ingested.isoformat() if state.last_ingested else None,
    }


@app.get("/ingest/stats", response_model=IngestStatsResponse, tags=["Ingest"])
async def ingest_stats() -> IngestStatsResponse:
    stats = await state.engine.query_ingest_stats()
    return IngestStatsResponse(
        row_count=stats.get("row_count", 0),
        service_count=stats.get("service_count", 0),
        date_range_days=stats.get("date_range_days", 0),
        min_date=stats.get("min_date"),
        max_date=stats.get("max_date"),
        total_spend=stats.get("total_spend", 0.0),
        last_ingested=state.last_ingested.isoformat() if state.last_ingested else None,
    )


@app.post(
    "/ingest/cost-explorer",
    tags=["Ingest"],
    summary="Ingest AWS Cost Explorer JSON export",
    response_model=CURIngestResponse,
)
async def ingest_cost_explorer(
    body: CostExplorerIngestRequest,
    background_tasks: BackgroundTasks,
) -> CURIngestResponse:
    """
    Accepts the raw JSON body from:
      aws ce get-cost-and-usage --granularity DAILY --metrics UnblendedCost
    """
    start = time.perf_counter()
    rows = []
    for period in body.results_by_time:
        period_date = period.get("TimePeriod", {}).get("Start", "")
        for group in period.get("Groups", []):
            service = group["Keys"][0] if group.get("Keys") else "Unknown"
            amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0))
            if amount > 0:
                rows.append({"date": period_date, "service": service, "amount": amount, "region": "global", "account_id": ""})

    if not rows:
        raise HTTPException(status_code=400, detail="No cost rows found in ResultsByTime")

    df = pd.DataFrame(rows)
    tracker = CostTracker(mock=False, account_name=body.account_name)
    spend_data = tracker._build_spend_data(
        account_id="api-ingest",
        account_name=body.account_name,
        start=date.fromisoformat(min(r["date"] for r in rows)),
        end=date.fromisoformat(max(r["date"] for r in rows)),
        rows=tracker._build_daily_rows_from_df(df) if hasattr(tracker, "_build_daily_rows_from_df") else [],
    )

    state.spend_data = spend_data
    state.engine.load_dataframe(df)
    state.last_ingested = datetime.utcnow()

    elapsed_ms = (time.perf_counter() - start) * 1000

    background_tasks.add_task(_refresh_anomalies)

    return CURIngestResponse(
        rows_loaded=len(rows),
        services_found=int(df["service"].nunique()),
        date_range=f"{df['date'].min()} to {df['date'].max()}",
        ingest_time_ms=round(elapsed_ms, 2),
        total_spend=round(float(df["amount"].sum()), 2),
    )


@app.post(
    "/ingest/cur",
    tags=["Ingest"],
    summary="Ingest CUR Parquet file via DuckDB",
    response_model=CURIngestResponse,
)
async def ingest_cur_parquet(
    file: UploadFile = File(..., description="CUR Parquet file (CUR 1.0 or FOCUS/CUR 2.0)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> CURIngestResponse:
    """
    Upload a CUR Parquet file. DuckDB loads it directly — sub-second even for millions of rows.
    Supports CUR 1.0 (lineItem/... columns) and FOCUS/CUR 2.0 (BilledCost, ServiceName).
    """
    start = time.perf_counter()

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        engine = AnalyticsEngine()
        engine.load_parquet(tmp_path)
        stats = await engine.query_ingest_stats()

        state.engine.close()
        state.engine = engine
        state.last_ingested = datetime.utcnow()

        elapsed_ms = (time.perf_counter() - start) * 1000
        background_tasks.add_task(_refresh_anomalies)

        return CURIngestResponse(
            rows_loaded=stats["row_count"],
            services_found=stats["service_count"],
            date_range=f"{stats['min_date']} to {stats['max_date']}",
            ingest_time_ms=round(elapsed_ms, 2),
            total_spend=stats["total_spend"],
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Anomaly endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/anomalies",
    response_model=AnomalyListResponse,
    tags=["Anomalies"],
    summary="List detected anomalies with optional severity filter",
)
async def list_anomalies(
    severity: str | None = Query(default=None, description="Filter: CRITICAL, HIGH, MEDIUM, LOW"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_acknowledged: bool = Query(default=False),
    _: SpendData = Depends(require_spend_data),
) -> AnomalyListResponse:
    anomalies = state.anomalies

    if not include_acknowledged:
        anomalies = [a for a in anomalies if not a.acknowledged]

    if severity:
        sev_upper = severity.upper()
        try:
            sev_enum = AnomalySeverity(sev_upper)
            anomalies = [a for a in anomalies if a.severity == sev_enum]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    total = len(anomalies)
    start = (page - 1) * page_size
    page_items = anomalies[start:start + page_size]

    return AnomalyListResponse(
        total=total,
        page=page,
        page_size=page_size,
        anomalies=[_anomaly_to_response(a) for a in page_items],
    )


@app.post(
    "/anomalies/{anomaly_id}/acknowledge",
    tags=["Anomalies"],
    summary="Acknowledge anomaly — suppresses repeat alerts",
)
async def acknowledge_anomaly(
    anomaly_id: str,
    body: AcknowledgeRequest,
) -> dict[str, Any]:
    # Find the anomaly
    match = next((a for a in state.anomalies if a.anomaly_id == anomaly_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")

    match.acknowledged = True
    match.acknowledged_by = body.acknowledged_by
    state.detector.acknowledge(anomaly_id, body.acknowledged_by)

    # Optionally add suppression rule
    if body.suppress_days > 0:
        from datetime import timedelta
        rule = SuppressionRule(
            rule_id=f"ack-{anomaly_id}",
            service_pattern=match.service,
            date_start=match.detected_at,
            date_end=match.detected_at + timedelta(days=body.suppress_days),
            reason=body.reason,
            created_by=body.acknowledged_by,
        )
        state.detector.add_suppression_rule(rule)

    return {
        "acknowledged": True,
        "anomaly_id": anomaly_id,
        "service": match.service,
        "reason": body.reason,
        "suppressed_days": body.suppress_days,
    }


# ---------------------------------------------------------------------------
# Forecast endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/forecasts",
    response_model=list[ForecastResponse],
    tags=["Forecasting"],
    summary="30/60/90-day spend forecasts with P10/P50/P90 confidence bands",
)
async def get_forecasts(
    horizons: str = Query(default="30,60,90", description="Comma-separated horizon days"),
    monthly_budget: float = Query(default=0.0, ge=0),
    spend_data: SpendData = Depends(require_spend_data),
) -> list[ForecastResponse]:
    horizon_list = [int(h.strip()) for h in horizons.split(",") if h.strip().isdigit()]
    if not horizon_list:
        raise HTTPException(status_code=400, detail="Invalid horizons format. Example: 30,60,90")

    results: list[ForecastResponse] = []
    for horizon in horizon_list[:4]:  # max 4 horizons
        fc = state.forecaster.forecast(spend_data, horizon_days=horizon)

        budget_status = None
        exhaustion_date = None
        if monthly_budget > 0:
            burn = state.forecaster.burn_rate(spend_data, monthly_budget=monthly_budget)
            budget_status = burn.budget_status
            exhaustion_date = burn.budget_exhaustion_date.isoformat() if burn.budget_exhaustion_date else None

        results.append(ForecastResponse(
            horizon_days=horizon,
            total_predicted=fc.total_predicted,
            total_lower=fc.total_lower,
            total_upper=fc.total_upper,
            model_used=fc.model_used,
            mape=fc.mape,
            trend=fc.trend,
            trend_pct_per_month=fc.trend_pct_per_month,
            daily_points=[
                {"date": str(p.date), "predicted": p.predicted, "lower": p.lower_bound, "upper": p.upper_bound}
                for p in fc.daily_forecast
            ],
            budget_status=budget_status,
            budget_exhaustion_date=exhaustion_date,
        ))

    return results


# ---------------------------------------------------------------------------
# Optimization endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/optimization/recommendations",
    response_model=list[OptimizationRecommendationResponse],
    tags=["Optimization"],
    summary="Ranked savings opportunities — estimated $89K+/month available",
)
async def optimization_recommendations(
    min_savings: float = Query(default=0.0, description="Minimum monthly savings filter"),
    effort: str | None = Query(default=None, description="Filter by effort: LOW, MEDIUM, HIGH"),
    opp_type: str | None = Query(default=None, description="Filter by type: SAVINGS_PLAN, RIGHTSIZING, WASTE_ELIMINATION, GRAVITON_MIGRATION"),
    spend_data: SpendData = Depends(require_spend_data),
) -> list[OptimizationRecommendationResponse]:
    if state.optimization_plan is None:
        optimizer = Optimizer(mock=True)
        state.optimization_plan = optimizer.analyze(spend_data)
        state.nl_interface.set_context(spend_data, state.anomalies, state.optimization_plan)

    opps = state.optimization_plan.opportunities

    if min_savings > 0:
        opps = [o for o in opps if o.savings_monthly >= min_savings]
    if effort:
        opps = [o for o in opps if o.effort == effort.upper()]
    if opp_type:
        opps = [o for o in opps if o.type.value == opp_type.upper()]

    return [
        OptimizationRecommendationResponse(
            opportunity_id=f"opp-{o.priority:03d}",
            priority=o.priority,
            type=o.type.value,
            title=o.title,
            description=o.description,
            savings_monthly=o.savings_monthly,
            savings_annual=o.savings_annual,
            savings_pct=o.savings_pct,
            effort=o.effort,
            risk=o.risk,
            confidence=o.confidence,
            action=o.action,
            resource_id=o.resource_id,
        )
        for o in opps
    ]


@app.post(
    "/optimization/{opportunity_id}/implement-plan",
    response_model=ImplementationPlanResponse,
    tags=["Optimization"],
    summary="Generate Terraform + CLI implementation steps for an opportunity",
)
async def implement_plan(
    opportunity_id: str,
    body: ImplementationPlanRequest,
    spend_data: SpendData = Depends(require_spend_data),
) -> ImplementationPlanResponse:
    if state.optimization_plan is None:
        raise HTTPException(status_code=503, detail="Optimization plan not yet generated")

    # Find opportunity by ID (format: opp-NNN)
    try:
        priority = int(opportunity_id.replace("opp-", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid opportunity ID format (expected opp-NNN)")

    opp = next(
        (o for o in state.optimization_plan.opportunities if o.priority == priority), None
    )
    if opp is None:
        raise HTTPException(status_code=404, detail=f"Opportunity {opportunity_id} not found")

    terraform = _generate_terraform(opp) if body.include_terraform else None
    cli_commands = _generate_cli_commands(opp) if body.include_cli else []
    rollback = _generate_rollback_steps(opp)

    return ImplementationPlanResponse(
        opportunity_id=opportunity_id,
        title=opp.title,
        terraform_snippet=terraform,
        cli_commands=cli_commands,
        estimated_minutes=_estimate_effort_minutes(opp.effort),
        risk_assessment=f"Risk: {opp.risk}. Confidence: {opp.confidence:.0%}. Reversible: {'Yes' if opp.risk in ('LOW', 'MEDIUM') else 'Requires testing'}.",
        rollback_steps=rollback,
    )


# ---------------------------------------------------------------------------
# NL Query endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/query",
    response_model=NLQueryResponse,
    tags=["Natural Language"],
    summary="Ask a cost question in plain English — stateful Claude-powered session",
)
async def nl_query(
    body: NLQueryRequest,
    spend_data: SpendData = Depends(require_spend_data),
) -> NLQueryResponse:
    start = time.perf_counter()

    session_id = body.session_id or str(uuid.uuid4())[:8]

    if session_id not in state.sessions:
        state.sessions[session_id] = state.nl_interface.new_session(session_id)

    session = state.sessions[session_id]

    answer = state.nl_interface.ask(
        question=body.question,
        session=session,
        model=body.model,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    return NLQueryResponse(
        question=answer.question,
        answer=answer.answer,
        model_used=answer.model_used,
        input_tokens=answer.input_tokens,
        output_tokens=answer.output_tokens,
        session_id=answer.session_id,
        response_time_ms=round(elapsed_ms, 2),
    )


# ---------------------------------------------------------------------------
# CFO Report endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/reports/cfo",
    response_class=HTMLResponse,
    tags=["Reports"],
    summary="Generate self-contained CFO HTML report with Chart.js charts",
)
async def cfo_report(
    company_name: str = Query(default="TechStartupCo"),
    monthly_budget: float = Query(default=400_000.0),
    spend_data: SpendData = Depends(require_spend_data),
) -> HTMLResponse:
    reporter = Reporter(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "")
    )
    fc_30 = state.forecaster.forecast(spend_data, horizon_days=30)
    burn = state.forecaster.burn_rate(spend_data, monthly_budget=monthly_budget)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name

    reporter.generate(
        spend_data=spend_data,
        anomalies=state.anomalies[:10],
        forecast=fc_30,
        burn_rate=burn,
        optimization_plan=state.optimization_plan,
        config=ReportConfig(
            company_name=company_name,
            monthly_budget=monthly_budget,
            prepared_by="FinOps Intelligence V2",
        ),
        output_path=tmp_path,
    )

    html = Path(tmp_path).read_text(encoding="utf-8")
    Path(tmp_path).unlink(missing_ok=True)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# WebSocket: real-time anomaly stream
# ---------------------------------------------------------------------------

@app.websocket("/ws/anomaly-stream")
async def anomaly_stream(websocket: WebSocket) -> None:
    """
    Real-time anomaly push.
    Sends existing CRITICAL/HIGH anomalies immediately, then polls every 30s.

    Client receives JSON objects matching AnomalyResponse.
    """
    await websocket.accept()
    state.anomaly_subscribers.append(websocket)

    # Send current CRITICAL/HIGH anomalies immediately
    critical_high = [
        a for a in state.anomalies
        if a.severity in (AnomalySeverity.CRITICAL, AnomalySeverity.HIGH)
        and not a.acknowledged
    ]
    for a in critical_high:
        await websocket.send_json(_anomaly_to_response(a).model_dump())

    try:
        while True:
            await asyncio.sleep(30)
            # Send any new CRITICAL anomalies (re-run detection in background)
            if state.spend_data:
                new_anomalies = [
                    a for a in state.anomalies
                    if a.severity == AnomalySeverity.CRITICAL and not a.acknowledged
                ]
                for a in new_anomalies:
                    await websocket.send_json(_anomaly_to_response(a).model_dump())

    except WebSocketDisconnect:
        state.anomaly_subscribers.remove(websocket)


# ---------------------------------------------------------------------------
# Analytics pass-through (DuckDB)
# ---------------------------------------------------------------------------

@app.get("/analytics/service-breakdown", tags=["Analytics"])
async def service_breakdown(
    days: int = Query(default=30, ge=1, le=730),
    top_n: int = Query(default=20, ge=1, le=50),
) -> list[dict[str, Any]]:
    """DuckDB-powered service breakdown — sub-second on millions of rows."""
    results = await state.engine.query_service_breakdown(days=days, top_n=top_n)
    return [
        {
            "service": r.service,
            "total_cost": r.total_cost,
            "avg_daily_cost": r.avg_daily_cost,
            "pct_of_total": r.pct_of_total,
        }
        for r in results
    ]


@app.get("/analytics/untagged-resources", tags=["Analytics"])
async def untagged_resources(days: int = Query(default=30, ge=1, le=90)) -> list[dict[str, Any]]:
    """Identify untagged resources driving unallocatable spend."""
    results = await state.engine.query_untagged_resources(days=days)
    return [
        {
            "service": r.service,
            "region": r.region,
            "estimated_monthly_cost": r.estimated_monthly_cost,
            "days_untagged": r.days_untagged,
        }
        for r in results
    ]


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _refresh_anomalies() -> None:
    """Background: re-run anomaly detection after new data ingestion."""
    await asyncio.sleep(0.5)
    if state.spend_data:
        state.anomalies = state.detector.detect(state.spend_data)
        state.nl_interface.set_context(
            state.spend_data, state.anomalies, state.optimization_plan
        )
        # Push CRITICAL anomalies to WebSocket subscribers
        for ws in list(state.anomaly_subscribers):
            try:
                for a in state.anomalies:
                    if a.severity == AnomalySeverity.CRITICAL and not a.acknowledged:
                        await ws.send_json(_anomaly_to_response(a).model_dump())
            except Exception:
                state.anomaly_subscribers.remove(ws)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anomaly_to_response(a: Anomaly) -> AnomalyResponse:
    return AnomalyResponse(
        anomaly_id=a.anomaly_id,
        detected_at=str(a.detected_at),
        service=a.service,
        amount=a.amount,
        baseline=a.baseline,
        delta=a.delta,
        delta_pct=a.delta_pct,
        severity=a.severity.value,
        confidence=a.confidence,
        zscore=a.zscore,
        ensemble_votes=a.ensemble_votes,
        explanation=a.explanation or "",
        root_cause_primary=a.root_cause.primary_driver if a.root_cause else None,
        correlated_services=a.root_cause.correlated_services if a.root_cause else [],
        acknowledged=a.acknowledged,
        has_pagerduty_payload=bool(a.pagerduty_payload),
    )


def _generate_terraform(opp: Any) -> str:
    """Generate Terraform snippet appropriate to the opportunity type."""
    opp_type = opp.type.value

    if opp_type == "RIGHTSIZING":
        return f'''# Terraform: Update EC2 instance type
# Opportunity: {opp.title}
# Estimated savings: ${opp.savings_monthly:,.0f}/month

resource "aws_instance" "target" {{
  # ... existing config ...
  instance_type = "{opp.resource_type.split("→")[-1].strip() if "→" in opp.resource_type else "t3.medium"}"

  tags = {{
    FinOps_Rightsize     = "true"
    FinOps_Opportunity   = "{opp.resource_id}"
    FinOps_MonthlySaving = "${opp.savings_monthly:,.0f}"
  }}
}}
'''

    if opp_type in ("SAVINGS_PLAN", "RESERVED_INSTANCE"):
        return f'''# Terraform: AWS Savings Plan purchase
# Note: Savings Plans must be purchased via AWS CLI or Console.
# Terraform aws_savingsplans_purchase is not supported.
# Use the CLI command below instead.
#
# Opportunity: {opp.title}
# Estimated savings: ${opp.savings_monthly:,.0f}/month

# Budget guardrail (recommended alongside SP purchase):
resource "aws_budgets_budget" "finops_commitment" {{
  name              = "finops-sp-commitment-guard"
  budget_type       = "COST"
  limit_amount      = "{opp.current_monthly * 0.80:.0f}"
  limit_unit        = "USD"
  time_unit         = "MONTHLY"

  notification {{
    comparison_operator        = "GREATER_THAN"
    threshold                  = 85
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["finops@yourcompany.com"]
  }}
}}
'''

    if opp_type == "WASTE_ELIMINATION":
        return f'''# Terraform: Remove orphaned resource
# Opportunity: {opp.title}
# Estimated savings: ${opp.savings_monthly:,.0f}/month

# Removing the resource from Terraform state will trigger deletion.
# IMPORTANT: Take a snapshot before removing EBS volumes.
# terraform state rm <resource_address>
# terraform apply

# Lifecycle policy to prevent future orphans:
resource "aws_dlm_lifecycle_policy" "finops_cleanup" {{
  description        = "FinOps: auto-tag and clean up orphaned EBS volumes"
  execution_role_arn = aws_iam_role.dlm_lifecycle_role.arn
  state              = "ENABLED"

  policy_details {{
    resource_types = ["VOLUME"]
    schedule {{
      name = "30-day retention"
      create_rule {{ interval = 24; interval_unit = "HOURS"; times = ["23:45"] }}
      retain_rule {{ count = 30 }}
      tags_to_add = {{ FinOps_Managed = "true" }}
    }}
  }}
}}
'''

    return f'# No Terraform template available for {opp_type}\n# Use the CLI commands below.'


def _generate_cli_commands(opp: Any) -> list[str]:
    """Return ordered list of AWS CLI commands to implement the opportunity."""
    commands: list[str] = [f"# {opp.title}", f"# Savings: ${opp.savings_monthly:,.0f}/month"]

    if opp.action:
        commands.append("")
        commands.append("# Recommended action:")
        commands.append(opp.action)

    opp_type = opp.type.value
    if opp_type == "SAVINGS_PLAN":
        commands += [
            "",
            "# Step 1: Check current coverage",
            "aws ce get-savings-plans-coverage \\",
            "  --time-period Start=$(date -d '30 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \\",
            "  --granularity MONTHLY",
            "",
            "# Step 2: Get recommendation",
            "aws ce get-savings-plans-purchase-recommendation \\",
            "  --savings-plans-type COMPUTE_SP \\",
            "  --term-in-years ONE_YEAR \\",
            "  --payment-option NO_UPFRONT \\",
            "  --lookback-period-in-days SIXTY_DAYS",
        ]

    if opp_type == "WASTE_ELIMINATION" and "ebs" in opp.resource_id.lower():
        commands += [
            "",
            "# Step 1: Snapshot all unattached volumes",
            "aws ec2 describe-volumes --filters Name=status,Values=available \\",
            "  --query 'Volumes[*].[VolumeId,Size,VolumeType]' --output table",
            "",
            "# Step 2: Create snapshots before deleting",
            "# for VOL_ID in $(aws ec2 describe-volumes --filters Name=status,Values=available",
            "#   --query 'Volumes[*].VolumeId' --output text); do",
            "#   aws ec2 create-snapshot --volume-id $VOL_ID --description 'pre-delete-backup'",
            "# done",
        ]

    return commands


def _generate_rollback_steps(opp: Any) -> list[str]:
    opp_type = opp.type.value
    if opp_type == "RIGHTSIZING":
        return [
            "1. Revert Launch Template to original instance type",
            "2. Trigger rolling instance refresh on ASG",
            "3. Monitor P99 latency for 1 hour post-rollback",
        ]
    if opp_type == "WASTE_ELIMINATION":
        return [
            "1. Restore from EBS snapshot if data recovery needed",
            "2. aws ec2 create-volume --snapshot-id <snapshot-id> --availability-zone us-east-1a",
            "3. Attach to replacement instance",
        ]
    if opp_type == "GRAVITON_MIGRATION":
        return [
            "1. Revert Launch Template to x86 instance type",
            "2. Trigger rolling refresh",
            "3. No data loss risk — compute-only change",
        ]
    return [
        "1. Revert the change in AWS Console or Terraform",
        "2. Monitor costs for 24 hours",
        "3. Open rollback ticket if savings target not met",
    ]


def _estimate_effort_minutes(effort: str) -> int:
    return {"LOW": 15, "MEDIUM": 60, "HIGH": 240}.get(effort, 30)
