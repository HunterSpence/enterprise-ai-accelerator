"""
Enterprise AI Accelerator MCP Server — stdio transport
======================================================

Exposes the full capability surface of the platform as MCP tools so any
Claude client (Claude Code, Claude Desktop, IDE extensions) can drive:

  AIAuditTrail           : log decisions, run EU AI Act compliance checks,
                           export SARIF, verify hash chain
  CloudIQ                : AWS environment analysis + finding enumeration
  MigrationScout         : 6R classification (real-time + batch), wave
                           planning, runbook generation
  FinOps Intelligence    : anomaly detection, bulk explanation, forecasts
  PolicyGuard            : IaC policy scan, bias audit, policy audit (all
                           with Opus 4.7 extended-thinking reasoning traces)
  ExecutiveChat          : 1M-context CTO chat grounded in the full briefing
  ComplianceCitations    : evidence-cited regulatory Q&A

Every tool that talks to Claude routes through ``core.AIClient`` so prompt
caching, tool-use structured output, and extended thinking are enabled by
default.

Opus 4.7 upgrade (2026-04): expanded from 4 tools (AIAuditTrail-only) to
19 tools spanning all six modules + executive chat + compliance citations.

Claude Desktop config::

    {
      "mcpServers": {
        "enterprise-ai-accelerator": {
          "command": "python",
          "args": ["mcp_server.py"],
          "cwd": "/path/to/enterprise-ai-accelerator"
        }
      }
    }

Environment variables:
  AUDIT_DB_PATH         — override the default SQLite path (audit_trail.db)
  ANTHROPIC_API_KEY     — required for any tool that invokes Claude
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier
from ai_audit_trail.eu_ai_act import check_article_12_compliance, enforcement_status
from core import (
    AIClient,
    MODEL_OPUS_4_7,
    MODEL_SONNET_4_6,
    MODEL_HAIKU_4_5,
)
from core.models import describe_model

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("AUDIT_DB_PATH", "audit_trail.db")
_chain: AuditChain | None = None
_ai_client: AIClient | None = None


def _get_chain() -> AuditChain:
    global _chain
    if _chain is None:
        _chain = AuditChain(db_path=_DB_PATH, store_plaintext=False)
    return _chain


def _get_ai() -> AIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient(default_model=MODEL_OPUS_4_7)
    return _ai_client


# ---------------------------------------------------------------------------
# SARIF 2.1.0 builder (unchanged from pre-upgrade; proven wire format)
# ---------------------------------------------------------------------------

_SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
_RISK_LEVEL = {"UNACCEPTABLE": "error", "HIGH": "error", "LIMITED": "warning", "MINIMAL": "note"}
_RISK_SCORE = {"UNACCEPTABLE": "9.5", "HIGH": "7.5", "LIMITED": "4.0", "MINIMAL": "1.0"}


def _build_sarif(chain: AuditChain) -> dict[str, Any]:
    """Build SARIF 2.1.0 from the audit chain."""
    entries = chain.query(limit=500)
    tamper = chain.verify_chain()
    tampered_ids = {t["entry_id"] for t in tamper.tampered_entries}

    results = []
    for e in entries:
        rule_id = "AIAudit/ChainTamper" if e.entry_id in tampered_ids else "AIAudit/DecisionLogged"
        results.append({
            "ruleId": rule_id,
            "level": _RISK_LEVEL.get(e.risk_tier, "note"),
            "message": {"text": f"model={e.model} type={e.decision_type} risk={e.risk_tier} system={e.system_id} ts={e.timestamp[:19]}Z"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": f"audit://{e.system_id}/{e.entry_id}", "uriBaseId": "%AUDIT_ROOT%"}}}],
            "properties": {"entryId": e.entry_id, "riskTier": e.risk_tier, "model": e.model, "security-severity": _RISK_SCORE.get(e.risk_tier, "1.0")},
        })

    return {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "AIAuditTrail", "version": "2.0.0",
                "informationUri": "https://github.com/HunterSpence/enterprise-ai-accelerator",
                "shortDescription": {"text": "Tamper-evident AI decision audit trail for EU AI Act Article 12 compliance."},
                "rules": [
                    {"id": "AIAudit/DecisionLogged", "name": "AuditedAIDecision",
                     "shortDescription": {"text": "Logged AI decision entry"},
                     "defaultConfiguration": {"level": "note"},
                     "properties": {"tags": ["ai-governance", "eu-ai-act", "article-12"]}},
                    {"id": "AIAudit/ChainTamper", "name": "HashChainTampered",
                     "shortDescription": {"text": "Hash chain integrity violation (Article 12.2)"},
                     "defaultConfiguration": {"level": "error"},
                     "properties": {"security-severity": "9.5", "tags": ["ai-governance", "integrity"]}},
                ],
            }},
            "results": results,
            "properties": {
                "chainIntegrityValid": tamper.is_valid,
                "merkleRoot": tamper.merkle_root,
                "totalEntries": tamper.total_entries,
                "tamperedCount": len(tamper.tampered_entries),
                "generatedAt": datetime.now(timezone.utc).isoformat(),
            },
        }],
    }


# ---------------------------------------------------------------------------
# MCP server — expanded tool catalog
# ---------------------------------------------------------------------------

server = Server("enterprise-ai-accelerator")

_RISK_ENUM = ["MINIMAL", "LIMITED", "HIGH", "UNACCEPTABLE"]
_STRATEGY_ENUM = ["Retire", "Retain", "Rehost", "Replatform", "Repurchase", "Refactor"]
_MODEL_ENUM = [MODEL_OPUS_4_7, MODEL_SONNET_4_6, MODEL_HAIKU_4_5]

_TOOLS: list[Tool] = [
    # ----- AIAuditTrail -------------------------------------------------
    Tool(
        name="audit_log_decision",
        description="Log an AI decision to the tamper-evident hash chain.",
        inputSchema={
            "type": "object",
            "required": ["model", "input_summary", "output_summary", "risk_level"],
            "properties": {
                "model": {"type": "string"},
                "input_summary": {"type": "string"},
                "output_summary": {"type": "string"},
                "risk_level": {"type": "string", "enum": _RISK_ENUM},
                "decision_type": {"type": "string", "enum": ["RECOMMENDATION", "CLASSIFICATION", "GENERATION", "AUTONOMOUS_ACTION", "TOOL_USE", "RETRIEVAL"], "default": "GENERATION"},
                "system_id": {"type": "string"},
                "session_id": {"type": "string"},
                "metadata": {"type": "object"},
                "reasoning_trace": {"type": "string", "description": "Optional extended-thinking reasoning trace (Annex IV evidence)."},
            },
        },
    ),
    Tool(
        name="get_compliance_status",
        description="Run EU AI Act Article 12 compliance check against the current audit trail.",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}},
    ),
    Tool(
        name="export_sarif",
        description="Export the audit trail as SARIF 2.1.0 JSON.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_audit_chain",
        description="Retrieve audit trail entries with hash chain verification.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "system_id": {"type": "string"},
                "risk_tier": {"type": "string", "enum": _RISK_ENUM},
            },
        },
    ),
    # ----- Platform info ------------------------------------------------
    Tool(
        name="list_models",
        description="List the canonical Anthropic models used by the platform and their capabilities.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="platform_capabilities",
        description="Return the platform's self-description: modules, MCP tools, OpenTelemetry surface, current model roster.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # ----- CloudIQ -------------------------------------------------------
    Tool(
        name="cloudiq_analyze_environment",
        description="Run a CloudIQ-style AWS environment analysis. Returns findings, risk level, and recommendations.",
        inputSchema={
            "type": "object",
            "required": ["aws_config"],
            "properties": {
                "aws_config": {"type": "object", "description": "AWS environment context (regions, account ids, resource summary)."},
                "focus_areas": {"type": "array", "items": {"type": "string"}, "description": "Optional focus: ['iam', 'network', 'cost', 'reliability']"},
            },
        },
    ),
    # ----- MigrationScout -----------------------------------------------
    Tool(
        name="migration_assess_workload",
        description="Classify a single workload using the 6R framework (real-time, Opus 4.7 optional extended thinking).",
        inputSchema={
            "type": "object",
            "required": ["workload"],
            "properties": {
                "workload": {"type": "object", "description": "Workload inventory record."},
                "extended_thinking": {"type": "boolean", "default": False, "description": "Enable Opus 4.7 extended thinking — audit-grade reasoning trace."},
            },
        },
    ),
    Tool(
        name="migration_bulk_classify",
        description="Submit a list of workloads to the Batch API for bulk 6R classification (50% discount, up to 24h turnaround). Returns the batch id.",
        inputSchema={
            "type": "object",
            "required": ["workloads"],
            "properties": {
                "workloads": {"type": "array", "items": {"type": "object"}},
            },
        },
    ),
    Tool(
        name="migration_generate_wave_plan",
        description="Given a set of classified workloads, produce a wave plan with sequencing, dependencies, and business-window constraints.",
        inputSchema={
            "type": "object",
            "required": ["classified_workloads"],
            "properties": {
                "classified_workloads": {"type": "array", "items": {"type": "object"}},
                "constraints": {"type": "object"},
            },
        },
    ),
    # ----- FinOps Intelligence ------------------------------------------
    Tool(
        name="finops_explain_anomaly",
        description="Explain a single FinOps cost anomaly in executive-friendly language (real-time, Haiku 4.5).",
        inputSchema={
            "type": "object",
            "required": ["anomaly"],
            "properties": {"anomaly": {"type": "object"}},
        },
    ),
    Tool(
        name="finops_bulk_explain",
        description="Submit cost anomalies to the Batch API for bulk explanation.",
        inputSchema={
            "type": "object",
            "required": ["anomalies"],
            "properties": {"anomalies": {"type": "array", "items": {"type": "object"}}},
        },
    ),
    # ----- PolicyGuard ---------------------------------------------------
    Tool(
        name="policyguard_scan_iac",
        description="Scan an IaC configuration for security/compliance violations (CIS AWS, SOC 2, GDPR, PCI-DSS).",
        inputSchema={
            "type": "object",
            "required": ["iac_config"],
            "properties": {
                "iac_config": {"type": "object"},
                "frameworks": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    Tool(
        name="policyguard_audit_policy",
        description="Produce an auditable (extended-thinking) policy verdict with a persistable reasoning trace.",
        inputSchema={
            "type": "object",
            "required": ["policy_name", "resource_summary", "preliminary_verdict"],
            "properties": {
                "policy_name": {"type": "string"},
                "resource_summary": {"type": "object"},
                "preliminary_verdict": {"type": "string", "enum": ["pass", "fail", "partial", "not_applicable"]},
                "preliminary_evidence": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    Tool(
        name="policyguard_audit_bias",
        description="Produce an auditable (extended-thinking) bias assessment on a dataset or model output.",
        inputSchema={
            "type": "object",
            "required": ["subject", "statistics"],
            "properties": {
                "subject": {"type": "string"},
                "statistics": {"type": "object"},
                "preliminary_flags": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    # ----- ExecutiveChat -------------------------------------------------
    Tool(
        name="executive_ask",
        description="Ask a CTO-level question grounded in a briefing bundle (1M-context Opus 4.7, 1-hour prompt cache).",
        inputSchema={
            "type": "object",
            "required": ["briefing", "question"],
            "properties": {
                "briefing": {
                    "type": "object",
                    "description": "Keys: architecture_findings, migration_plan, compliance_violations, finops_anomalies, audit_trail_summary, risk_score, organization_context.",
                },
                "question": {"type": "string"},
                "extended_thinking": {"type": "boolean", "default": False},
            },
        },
    ),
    # ----- Compliance Citations -----------------------------------------
    Tool(
        name="compliance_cite_question",
        description="Answer a compliance question against a set of regulatory source texts; returns grounded citations.",
        inputSchema={
            "type": "object",
            "required": ["question", "sources"],
            "properties": {
                "question": {"type": "string"},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title", "text"],
                        "properties": {
                            "title": {"type": "string"},
                            "text": {"type": "string"},
                        },
                    },
                },
            },
        },
    ),
    # ----- Risk Aggregator -----------------------------------------------
    Tool(
        name="risk_aggregate_score",
        description="Compute the unified enterprise risk score from module outputs.",
        inputSchema={
            "type": "object",
            "required": ["module_outputs"],
            "properties": {
                "module_outputs": {
                    "type": "object",
                    "description": "Keyed by module name: cloud_iq, migration_scout, policy_guard, finops_intelligence, ai_audit_trail.",
                },
            },
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except Exception as exc:
        result = {"error": str(exc), "tool": name}
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def _dispatch(name: str, args: dict[str, Any]) -> Any:
    # AIAuditTrail --------------------------------------------------------
    if name == "audit_log_decision":
        return _audit_log_decision(args)
    if name == "get_compliance_status":
        return _get_compliance_status(args)
    if name == "export_sarif":
        return _build_sarif(_get_chain())
    if name == "get_audit_chain":
        return _get_audit_chain(args)

    # Platform ------------------------------------------------------------
    if name == "list_models":
        return {
            "models": [
                describe_model(MODEL_OPUS_4_7),
                describe_model(MODEL_SONNET_4_6),
                describe_model(MODEL_HAIKU_4_5),
            ],
        }
    if name == "platform_capabilities":
        return _platform_capabilities()

    # CloudIQ -------------------------------------------------------------
    if name == "cloudiq_analyze_environment":
        return await _cloudiq_analyze(args)

    # MigrationScout ------------------------------------------------------
    if name == "migration_assess_workload":
        return await _migration_assess(args)
    if name == "migration_bulk_classify":
        return await _migration_bulk_classify(args)
    if name == "migration_generate_wave_plan":
        return await _migration_wave_plan(args)

    # FinOps --------------------------------------------------------------
    if name == "finops_explain_anomaly":
        return await _finops_explain(args)
    if name == "finops_bulk_explain":
        return await _finops_bulk(args)

    # PolicyGuard ---------------------------------------------------------
    if name == "policyguard_scan_iac":
        return await _policyguard_scan(args)
    if name == "policyguard_audit_policy":
        return await _policyguard_audit_policy(args)
    if name == "policyguard_audit_bias":
        return await _policyguard_audit_bias(args)

    # ExecutiveChat -------------------------------------------------------
    if name == "executive_ask":
        return await _executive_ask(args)

    # Compliance Citations ------------------------------------------------
    if name == "compliance_cite_question":
        return await _compliance_cite(args)

    # Risk Aggregator -----------------------------------------------------
    if name == "risk_aggregate_score":
        return _risk_aggregate(args)

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Dispatch implementations — AIAuditTrail (unchanged)
# ---------------------------------------------------------------------------

def _audit_log_decision(args: dict[str, Any]) -> dict[str, Any]:
    chain = _get_chain()
    metadata = dict(args.get("metadata") or {})
    # Persist reasoning trace as Annex IV evidence alongside the decision.
    if args.get("reasoning_trace"):
        metadata["reasoning_trace"] = args["reasoning_trace"]
    entry = chain.append(
        session_id=args.get("session_id") or str(uuid.uuid4()),
        model=args["model"],
        input_text=args["input_summary"],
        output_text=args["output_summary"],
        input_tokens=0,
        output_tokens=0,
        latency_ms=0.0,
        decision_type=DecisionType(args.get("decision_type", "GENERATION")),
        risk_tier=RiskTier(args["risk_level"]),
        system_id=args.get("system_id", "mcp-client"),
        metadata=metadata,
    )
    return {
        "status": "logged",
        "entry_id": entry.entry_id,
        "timestamp": entry.timestamp,
        "entry_hash": entry.entry_hash,
        "prev_hash": entry.prev_hash,
        "system_id": entry.system_id,
        "model": entry.model,
        "risk_tier": entry.risk_tier,
        "decision_type": entry.decision_type,
    }


def _get_compliance_status(args: dict[str, Any]) -> dict[str, Any]:
    chain = _get_chain()
    check = check_article_12_compliance(chain)
    return {
        "compliant": check.compliant,
        "score": check.score,
        "requirements_met": check.requirements_met,
        "requirements_missing": check.requirements_missing,
        "recommendations": check.recommendations,
        "annex_iv_fields_present": check.annex_iv_fields_present,
        "annex_iv_fields_missing": check.annex_iv_fields_missing,
        "enforcement_timeline": enforcement_status(),
        "total_entries": chain.count(),
    }


def _get_audit_chain(args: dict[str, Any]) -> dict[str, Any]:
    chain = _get_chain()
    limit = min(int(args.get("limit", 20)), 200)
    entries = chain.query(
        system_id=args.get("system_id"),
        risk_tier=args.get("risk_tier"),
        limit=limit,
    )
    tamper = chain.verify_chain()
    return {
        "chain_valid": tamper.is_valid,
        "confidence": tamper.confidence,
        "merkle_root": tamper.merkle_root,
        "total_entries": tamper.total_entries,
        "tampered_count": len(tamper.tampered_entries),
        "verified_at": tamper.verified_at,
        "entries": [
            {
                "entry_id": e.entry_id, "timestamp": e.timestamp,
                "system_id": e.system_id, "model": e.model,
                "decision_type": e.decision_type, "risk_tier": e.risk_tier,
                "entry_hash": e.entry_hash, "prev_hash": e.prev_hash,
                "latency_ms": e.latency_ms, "cost_usd": e.cost_usd,
                "metadata": e.metadata,
            }
            for e in entries
        ],
    }


def _platform_capabilities() -> dict[str, Any]:
    return {
        "platform": "Enterprise AI Accelerator",
        "version": "3.0.0-opus-4-7",
        "modules": [
            "cloud_iq", "finops_intelligence", "migration_scout",
            "policy_guard", "ai_audit_trail", "risk_aggregator",
            "executive_chat", "compliance_citations",
        ],
        "opus_4_7_capabilities": {
            "prompt_caching_5m": True,
            "prompt_caching_1h": True,
            "extended_thinking": True,
            "citations_api": True,
            "files_api": True,
            "batch_api_50pct_discount": True,
            "tool_use_structured_output": True,
            "context_window_tokens": 1_000_000,
        },
        "mcp_tools": [t.name for t in _TOOLS],
        "models": {
            "coordinator": MODEL_OPUS_4_7,
            "reporter": MODEL_SONNET_4_6,
            "worker": MODEL_HAIKU_4_5,
        },
    }


# ---------------------------------------------------------------------------
# Dispatch implementations — CloudIQ / MigrationScout / FinOps / PolicyGuard
# ---------------------------------------------------------------------------

async def _cloudiq_analyze(args: dict[str, Any]) -> dict[str, Any]:
    from agent_ops.agents import ArchitectureAgent
    agent = ArchitectureAgent(_get_ai())
    result = await agent.run({"aws_config": args.get("aws_config", {})})
    return {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "findings": result.findings,
        "metadata": result.metadata,
        "model": result.model,
        "tokens": {
            "input": result.tokens_input,
            "output": result.tokens_output,
            "cache_read": result.tokens_cache_read,
        },
    }


async def _migration_assess(args: dict[str, Any]) -> dict[str, Any]:
    workload = args.get("workload", {})
    if args.get("extended_thinking"):
        from migration_scout.thinking_audit import ThinkingAudit
        auditor = ThinkingAudit(_get_ai())
        audit = await auditor.audit(workload)
        return {
            "workload_name": audit.workload_name,
            "strategy": audit.audited_strategy,
            "confidence": audit.confidence,
            "rationale": audit.rationale,
            "concerns": audit.concerns,
            "blockers": audit.blockers,
            "reasoning_trace": audit.reasoning_trace,
            "model": audit.model,
            "extended_thinking": True,
        }
    from agent_ops.agents import MigrationAgent
    agent = MigrationAgent(_get_ai())
    result = await agent.run({"workload_inventory": [workload]})
    return {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "plans": result.metadata.get("workload_plans", []),
        "findings": result.findings,
        "model": result.model,
    }


async def _migration_bulk_classify(args: dict[str, Any]) -> dict[str, Any]:
    from migration_scout.batch_classifier import BatchClassifier
    batcher = BatchClassifier(_get_ai())
    batch = await batcher.submit(args.get("workloads", []))
    return {
        "status": "submitted",
        "batch_id": batch.get("id"),
        "request_counts": batch.get("request_counts"),
        "raw": batch,
    }


async def _migration_wave_plan(args: dict[str, Any]) -> dict[str, Any]:
    """Lightweight wave-planning synthesis via Opus 4.7."""
    ai = _get_ai()
    schema = {
        "type": "object",
        "required": ["waves", "total_duration_weeks"],
        "properties": {
            "waves": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["wave_number", "workloads", "duration_weeks", "rationale"],
                    "properties": {
                        "wave_number": {"type": "integer", "minimum": 1},
                        "workloads": {"type": "array", "items": {"type": "string"}},
                        "duration_weeks": {"type": "integer", "minimum": 1},
                        "rationale": {"type": "string"},
                        "business_window": {"type": "string"},
                        "dependencies_resolved": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "total_duration_weeks": {"type": "integer", "minimum": 1},
            "critical_path_workloads": {"type": "array", "items": {"type": "string"}},
            "assumed_constraints": {"type": "array", "items": {"type": "string"}},
        },
    }
    response = await ai.structured(
        system=(
            "You are a migration program manager sequencing workloads into execution waves. "
            "Minimize risk by grouping dependent systems and isolating high-business-criticality "
            "cutovers into their own windows."
        ),
        user=(
            "Produce a wave plan for these workloads. Respect the provided constraints.\n\n"
            f"Workloads:\n```json\n{json.dumps(args.get('classified_workloads', []), indent=2, default=str)}\n```\n\n"
            f"Constraints:\n```json\n{json.dumps(args.get('constraints', {}), indent=2, default=str)}\n```"
        ),
        schema=schema,
        tool_name="emit_wave_plan",
        tool_description="Return the structured wave plan.",
        model=MODEL_OPUS_4_7,
        max_tokens=2048,
    )
    return response.data


async def _finops_explain(args: dict[str, Any]) -> dict[str, Any]:
    ai = _get_ai()
    schema = {
        "type": "object",
        "required": ["root_cause", "explanation", "recommended_action", "severity"],
        "properties": {
            "root_cause": {"type": "string"},
            "explanation": {"type": "string"},
            "recommended_action": {"type": "string"},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "potential_monthly_savings_usd": {"type": "number", "minimum": 0},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
    }
    response = await ai.structured(
        system="You are a FinOps analyst. Explain the cost anomaly for an executive dashboard.",
        user=f"Anomaly:\n```json\n{json.dumps(args.get('anomaly', {}), indent=2, default=str)}\n```",
        schema=schema,
        tool_name="emit_anomaly_explanation",
        tool_description="Explain the cost anomaly.",
        model=MODEL_HAIKU_4_5,
        max_tokens=512,
    )
    return response.data


async def _finops_bulk(args: dict[str, Any]) -> dict[str, Any]:
    from finops_intelligence.batch_processor import AnomalyBatchProcessor
    batcher = AnomalyBatchProcessor(_get_ai())
    batch = await batcher.submit(args.get("anomalies", []))
    return {
        "status": "submitted",
        "batch_id": batch.get("id"),
        "request_counts": batch.get("request_counts"),
        "raw": batch,
    }


async def _policyguard_scan(args: dict[str, Any]) -> dict[str, Any]:
    from agent_ops.agents import ComplianceAgent
    agent = ComplianceAgent(_get_ai())
    result = await agent.run({"iac_config": args.get("iac_config", {})})
    return {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "violations": result.metadata.get("violations", []),
        "compliance_score": result.metadata.get("compliance_score", 0),
        "findings": result.findings,
        "frameworks_checked": result.metadata.get("frameworks_checked", []),
        "model": result.model,
    }


async def _policyguard_audit_policy(args: dict[str, Any]) -> dict[str, Any]:
    from policy_guard.thinking_audit import PolicyThinkingAudit
    auditor = PolicyThinkingAudit(_get_ai())
    audit = await auditor.audit_policy_decision(
        policy_name=args["policy_name"],
        resource_summary=args.get("resource_summary", {}),
        preliminary_verdict=args["preliminary_verdict"],
        preliminary_evidence=args.get("preliminary_evidence"),
    )
    return {
        "policy_name": audit.policy_name,
        "verdict": audit.verdict,
        "severity": audit.severity,
        "justification": audit.justification,
        "control_reference": audit.control_reference,
        "remediation": audit.remediation,
        "evidence_cited": audit.evidence_cited,
        "blast_radius": audit.blast_radius,
        "reasoning_trace": audit.reasoning_trace,
        "model": audit.model,
    }


async def _policyguard_audit_bias(args: dict[str, Any]) -> dict[str, Any]:
    from policy_guard.thinking_audit import PolicyThinkingAudit
    auditor = PolicyThinkingAudit(_get_ai())
    audit = await auditor.audit_bias_decision(
        subject=args["subject"],
        statistics=args.get("statistics", {}),
        preliminary_flags=args.get("preliminary_flags"),
    )
    return {
        "subject": audit.subject,
        "bias_detected": audit.bias_detected,
        "bias_types": audit.bias_types,
        "severity": audit.severity,
        "evidence": audit.evidence,
        "affected_groups": audit.affected_groups,
        "mitigation": audit.mitigation,
        "eu_ai_act_article_references": audit.eu_ai_act_article_references,
        "reasoning_trace": audit.reasoning_trace,
        "model": audit.model,
    }


async def _executive_ask(args: dict[str, Any]) -> dict[str, Any]:
    from executive_chat import ExecutiveChat, BriefingBundle
    briefing_dict = args.get("briefing", {}) or {}
    bundle = BriefingBundle(
        architecture_findings=briefing_dict.get("architecture_findings", {}),
        migration_plan=briefing_dict.get("migration_plan", {}),
        compliance_violations=briefing_dict.get("compliance_violations", {}),
        finops_anomalies=briefing_dict.get("finops_anomalies", []),
        audit_trail_summary=briefing_dict.get("audit_trail_summary", {}),
        risk_score=briefing_dict.get("risk_score", {}),
        organization_context=briefing_dict.get("organization_context", {}),
    )
    chat = ExecutiveChat(_get_ai())
    answer = await chat.ask(
        bundle,
        args["question"],
        use_extended_thinking=bool(args.get("extended_thinking", False)),
    )
    return {
        "answer": answer.answer,
        "confidence": answer.confidence,
        "supporting_findings": answer.supporting_findings,
        "recommended_actions": answer.recommended_actions,
        "risk_flags": answer.risk_flags,
        "follow_up_questions": answer.follow_up_questions,
        "source_modules": answer.source_modules,
    }


async def _compliance_cite(args: dict[str, Any]) -> dict[str, Any]:
    from compliance_citations import EvidenceLibrary
    lib = EvidenceLibrary(_get_ai())
    for src in args.get("sources", []):
        lib.add_text_source(title=src["title"], text=src["text"])
    result = await lib.cite(question=args["question"])
    return {
        "answer_text": result.answer_text,
        "findings": [
            {
                "claim": f.claim,
                "citations": [
                    {
                        "cited_text": c.cited_text,
                        "document_title": c.document_title,
                        "document_index": c.document_index,
                        "start_char": c.start_char,
                        "end_char": c.end_char,
                    }
                    for c in f.citations
                ],
            }
            for f in result.findings
        ],
    }


def _risk_aggregate(args: dict[str, Any]) -> dict[str, Any]:
    """Lightweight risk aggregation.

    We don't hard-bind to ``risk_aggregator.py`` here because that module
    reads live artifacts off disk. Instead we compute a simple weighted
    score over the supplied module outputs so MCP clients can drive
    aggregation inline (or swap in the full aggregator later).
    """
    modules = args.get("module_outputs", {}) or {}

    weights = {
        "cloud_iq": 0.20,
        "migration_scout": 0.15,
        "policy_guard": 0.25,
        "finops_intelligence": 0.15,
        "ai_audit_trail": 0.25,
    }

    per_module: dict[str, dict[str, Any]] = {}
    weighted_total = 0.0
    weight_used = 0.0

    for mod, weight in weights.items():
        data = modules.get(mod) or {}
        score = _normalize_score(data)
        per_module[mod] = {"score": score, "weight": weight, "raw": data}
        if data:
            weighted_total += score * weight
            weight_used += weight

    unified_score = round(weighted_total / weight_used, 1) if weight_used else 0.0

    return {
        "unified_risk_score": unified_score,
        "per_module": per_module,
        "scale": "0 (lowest risk) to 100 (highest risk)",
        "weights": weights,
    }


def _normalize_score(data: dict[str, Any]) -> float:
    if not isinstance(data, dict):
        return 50.0
    for key in ("risk_score", "score", "unified_risk_score"):
        val = data.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    # Derive from severity-count heuristics if no explicit score.
    critical = data.get("critical_count", 0)
    high = data.get("high_count", 0)
    medium = data.get("medium_count", 0)
    synthetic = 10 * critical + 5 * high + 2 * medium
    return float(min(synthetic, 100))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
