"""
Enterprise AI Accelerator MCP Server — MCP 2.0 (stdio + SSE)
=============================================================

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

MCP 2.0 additions (2026-04):
  - SSE transport  (``--transport sse --host 0.0.0.0 --port 8765``)
  - Resources      (audit trail, scan results, compliance frameworks, policy catalog)
  - Prompts        (audit-terraform, classify-workload-6r, assess-bias, executive-briefing)

Opus 4.7 upgrade (2026-04): expanded from 4 tools (AIAuditTrail-only) to
19 tools spanning all six modules + executive chat + compliance citations.

Transport selection::

    # stdio (default — Claude Code / Claude Desktop local)
    python mcp_server.py

    # SSE (network-accessible — remote Claude Desktop, CI agents)
    python mcp_server.py --transport sse --host 0.0.0.0 --port 8765

    # SSE on custom interface
    python mcp_server.py --transport sse --host 127.0.0.1 --port 9000

Claude Desktop stdio config::

    {
      "mcpServers": {
        "enterprise-ai-accelerator": {
          "command": "python",
          "args": ["mcp_server.py"],
          "cwd": "/path/to/enterprise-ai-accelerator"
        }
      }
    }

Claude Desktop SSE config::

    {
      "mcpServers": {
        "enterprise-ai-accelerator": {
          "url": "http://localhost:8765/sse",
          "transport": "sse"
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
from mcp.types import (
    AnyUrl,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)

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


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

_RESOURCES: list[Resource] = [
    Resource(
        uri=AnyUrl("audit-trail://recent"),
        name="Recent Audit Decisions",
        description="Last 50 AI decision entries from the tamper-evident audit chain, as JSON.",
        mimeType="application/json",
    ),
    Resource(
        uri=AnyUrl("audit-trail://chain-verify"),
        name="Audit Chain Verification",
        description="Merkle chain integrity verification result for the full audit trail.",
        mimeType="application/json",
    ),
    Resource(
        uri=AnyUrl("compliance://frameworks"),
        name="Supported Compliance Frameworks",
        description="List of supported regulatory frameworks: CIS AWS, SOC 2, GDPR, PCI-DSS, EU AI Act, NIST AI RMF, HIPAA.",
        mimeType="application/json",
    ),
    Resource(
        uri=AnyUrl("policy-catalog://iac"),
        name="IaC Policy Catalog",
        description="The 20-policy IaC compliance catalog covering CIS AWS, SOC 2, GDPR, and PCI-DSS controls.",
        mimeType="application/json",
    ),
]

# scan-results://{scan_id} is a template resource — clients provide the scan_id.
# Registered via list_resource_templates; read_resource handles the URI pattern.

_SCAN_RESULTS_CACHE: dict[str, Any] = {}  # scan_id → result (populated by policyguard_scan_iac tool)

_IAC_POLICY_CATALOG: list[dict[str, Any]] = [
    # CIS AWS (5 policies)
    {"id": "CIS-AWS-1.1",  "framework": "CIS AWS", "title": "Avoid root account usage",                    "severity": "critical", "control": "1.1"},
    {"id": "CIS-AWS-2.1",  "framework": "CIS AWS", "title": "S3 buckets not publicly accessible",          "severity": "high",     "control": "2.1"},
    {"id": "CIS-AWS-3.1",  "framework": "CIS AWS", "title": "CloudTrail enabled in all regions",           "severity": "high",     "control": "3.1"},
    {"id": "CIS-AWS-4.1",  "framework": "CIS AWS", "title": "SSH access restricted from 0.0.0.0/0",        "severity": "critical", "control": "4.1"},
    {"id": "CIS-AWS-4.2",  "framework": "CIS AWS", "title": "RDP access restricted from 0.0.0.0/0",        "severity": "critical", "control": "4.2"},
    # SOC 2 (5 policies)
    {"id": "SOC2-CC6.1",   "framework": "SOC 2",   "title": "Encryption at rest for sensitive data",       "severity": "high",     "control": "CC6.1"},
    {"id": "SOC2-CC6.6",   "framework": "SOC 2",   "title": "Encryption in transit (TLS 1.2+)",            "severity": "high",     "control": "CC6.6"},
    {"id": "SOC2-CC7.1",   "framework": "SOC 2",   "title": "Vulnerability scanning enabled",              "severity": "medium",   "control": "CC7.1"},
    {"id": "SOC2-CC8.1",   "framework": "SOC 2",   "title": "Change management process documented",        "severity": "medium",   "control": "CC8.1"},
    {"id": "SOC2-CC9.1",   "framework": "SOC 2",   "title": "Backup and recovery tested annually",         "severity": "medium",   "control": "CC9.1"},
    # GDPR (5 policies)
    {"id": "GDPR-ART32",   "framework": "GDPR",    "title": "Technical measures for data security (Art 32)","severity": "critical", "control": "Article 32"},
    {"id": "GDPR-ART25",   "framework": "GDPR",    "title": "Data protection by design and default (Art 25)","severity": "high",    "control": "Article 25"},
    {"id": "GDPR-ART35",   "framework": "GDPR",    "title": "DPIA for high-risk processing (Art 35)",      "severity": "high",     "control": "Article 35"},
    {"id": "GDPR-ART17",   "framework": "GDPR",    "title": "Right to erasure — PII retention controls",  "severity": "medium",   "control": "Article 17"},
    {"id": "GDPR-ART33",   "framework": "GDPR",    "title": "72-hour breach notification capability",      "severity": "high",     "control": "Article 33"},
    # PCI-DSS (5 policies)
    {"id": "PCI-REQ2",     "framework": "PCI-DSS", "title": "No vendor-supplied default passwords",        "severity": "critical", "control": "Req 2.1"},
    {"id": "PCI-REQ6",     "framework": "PCI-DSS", "title": "Secure systems and applications patching",    "severity": "high",     "control": "Req 6.3"},
    {"id": "PCI-REQ7",     "framework": "PCI-DSS", "title": "Restrict access to system components",        "severity": "high",     "control": "Req 7.1"},
    {"id": "PCI-REQ10",    "framework": "PCI-DSS", "title": "Log and monitor all access to system components","severity": "medium", "control": "Req 10.2"},
    {"id": "PCI-REQ11",    "framework": "PCI-DSS", "title": "Regularly test security systems and processes", "severity": "medium", "control": "Req 11.2"},
]

_COMPLIANCE_FRAMEWORKS: list[dict[str, Any]] = [
    {"id": "cis_aws",    "name": "CIS AWS Foundations Benchmark", "version": "1.5.0", "controls": 58},
    {"id": "soc2",       "name": "SOC 2 Type II",                 "version": "2017",   "controls": 64},
    {"id": "gdpr",       "name": "GDPR",                          "version": "2018",   "controls": 99},
    {"id": "pci_dss",    "name": "PCI-DSS",                       "version": "4.0",    "controls": 250},
    {"id": "eu_ai_act",  "name": "EU AI Act",                     "version": "2024",   "controls": 113},
    {"id": "nist_ai_rmf","name": "NIST AI RMF",                   "version": "1.0",    "controls": 72},
    {"id": "hipaa",      "name": "HIPAA Security Rule",           "version": "2013",   "controls": 45},
]


@server.list_resources()
async def list_resources() -> list[Resource]:
    return _RESOURCES


@server.list_resource_templates()
async def list_resource_templates():
    from mcp.types import ResourceTemplate
    return [
        ResourceTemplate(
            uriTemplate="scan-results://{scan_id}",
            name="IaC Scan Result",
            description="Full PolicyGuard IaC scan result for a given scan_id.",
            mimeType="application/json",
        )
    ]


@server.read_resource()
async def read_resource(uri: AnyUrl) -> str | bytes:
    uri_str = str(uri)

    if uri_str == "audit-trail://recent":
        chain = _get_chain()
        entries = chain.query(limit=50)
        data = [
            {
                "entry_id": e.entry_id, "timestamp": e.timestamp,
                "system_id": e.system_id, "model": e.model,
                "decision_type": e.decision_type, "risk_tier": e.risk_tier,
                "entry_hash": e.entry_hash,
            }
            for e in entries
        ]
        return json.dumps(data, indent=2, default=str)

    if uri_str == "audit-trail://chain-verify":
        chain = _get_chain()
        result = chain.verify_chain()
        return json.dumps({
            "is_valid": result.is_valid,
            "confidence": result.confidence,
            "merkle_root": result.merkle_root,
            "total_entries": result.total_entries,
            "tampered_count": len(result.tampered_entries),
            "verified_at": result.verified_at,
        }, indent=2, default=str)

    if uri_str == "compliance://frameworks":
        return json.dumps(_COMPLIANCE_FRAMEWORKS, indent=2)

    if uri_str == "policy-catalog://iac":
        return json.dumps({
            "catalog_version": "1.0.0",
            "total_policies": len(_IAC_POLICY_CATALOG),
            "frameworks": ["CIS AWS", "SOC 2", "GDPR", "PCI-DSS"],
            "policies": _IAC_POLICY_CATALOG,
        }, indent=2)

    # scan-results://{scan_id}
    if uri_str.startswith("scan-results://"):
        scan_id = uri_str.removeprefix("scan-results://")
        result = _SCAN_RESULTS_CACHE.get(scan_id)
        if result is None:
            return json.dumps({"error": f"Scan result not found: {scan_id}", "available_ids": list(_SCAN_RESULTS_CACHE.keys())}, indent=2)
        return json.dumps(result, indent=2, default=str)

    return json.dumps({"error": f"Unknown resource URI: {uri_str}"}, indent=2)


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------

_PROMPTS: list[Prompt] = [
    Prompt(
        name="audit-terraform",
        description="Scan a Terraform directory and narrate findings in plain language with compliance references.",
        arguments=[
            PromptArgument(name="path", description="Filesystem path to the Terraform directory.", required=True),
            PromptArgument(name="environment", description="Deployment environment (e.g., production, staging).", required=True),
        ],
    ),
    Prompt(
        name="classify-workload-6r",
        description="Classify a workload using the 6R migration framework (Retire, Retain, Rehost, Replatform, Repurchase, Refactor).",
        arguments=[
            PromptArgument(name="workload_json", description="JSON object describing the workload (name, runtime, dependencies, business_criticality, etc.).", required=True),
        ],
    ),
    Prompt(
        name="assess-bias",
        description="Produce an extended-thinking bias audit on a dataset or model output, referencing EU AI Act Article 10.",
        arguments=[
            PromptArgument(name="dataset_summary", description="Summary of the dataset or model output to assess.", required=True),
        ],
    ),
    Prompt(
        name="executive-briefing",
        description="Generate a CTO-level executive briefing from platform scan results.",
        arguments=[
            PromptArgument(name="scan_results_json", description="JSON object containing scan results from one or more platform modules.", required=True),
        ],
    ),
]


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    return _PROMPTS


@server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    args = arguments or {}

    if name == "audit-terraform":
        path = args.get("path", "<terraform-directory>")
        env = args.get("environment", "production")
        return GetPromptResult(
            description=f"Audit Terraform at {path} for {env} environment.",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"You are a cloud security engineer. Use the `policyguard_scan_iac` tool "
                            f"to scan the Terraform configuration at `{path}` targeting the "
                            f"`{env}` environment.\n\n"
                            "After the scan completes:\n"
                            "1. Summarise the overall risk posture in two sentences.\n"
                            "2. List every violation grouped by compliance framework (CIS AWS, SOC 2, GDPR, PCI-DSS).\n"
                            "3. For each CRITICAL or HIGH finding, provide a concrete remediation code snippet.\n"
                            "4. Cite the specific control ID for every finding (e.g., CIS-AWS-4.1, GDPR-ART32).\n"
                            "5. Output a compliance score out of 100.\n\n"
                            "Format: structured markdown with severity badges. "
                            "Do not omit any violation — completeness is required for EU AI Act Annex IV."
                        ),
                    ),
                ),
            ],
        )

    if name == "classify-workload-6r":
        workload_json = args.get("workload_json", "{}")
        return GetPromptResult(
            description="6R classification prompt for the supplied workload.",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            "You are a cloud migration architect. Classify the following workload "
                            "using the 6R framework. Use the `migration_assess_workload` tool with "
                            "`extended_thinking: true` for an audit-grade reasoning trace.\n\n"
                            f"Workload:\n```json\n{workload_json}\n```\n\n"
                            "Your output must include:\n"
                            "- Recommended 6R strategy with confidence score (0-100)\n"
                            "- Rationale (3-5 bullet points referencing workload attributes)\n"
                            "- Blockers that could prevent the chosen strategy\n"
                            "- Alternative strategy if primary is blocked\n"
                            "- Estimated migration complexity: LOW / MEDIUM / HIGH / VERY HIGH\n\n"
                            "Be specific. Reference the workload attributes by name."
                        ),
                    ),
                ),
            ],
        )

    if name == "assess-bias":
        dataset_summary = args.get("dataset_summary", "")
        return GetPromptResult(
            description="EU AI Act Article 10 bias audit for the supplied dataset.",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            "You are an AI ethics auditor. Use the `policyguard_audit_bias` tool "
                            "to perform an extended-thinking bias assessment on the following dataset.\n\n"
                            f"Dataset summary:\n{dataset_summary}\n\n"
                            "Your audit report must cover:\n"
                            "1. Bias types detected (selection, confirmation, measurement, algorithmic, representation)\n"
                            "2. Affected demographic groups with evidence\n"
                            "3. Severity: NONE / LOW / MEDIUM / HIGH / CRITICAL\n"
                            "4. EU AI Act Article 10 compliance status (data governance requirements)\n"
                            "5. Concrete mitigation steps with priority ranking\n"
                            "6. Annex IV documentation requirements for this AI system\n\n"
                            "Include the extended-thinking reasoning trace in the audit record."
                        ),
                    ),
                ),
            ],
        )

    if name == "executive-briefing":
        scan_results_json = args.get("scan_results_json", "{}")
        return GetPromptResult(
            description="CTO-level executive briefing from platform scan results.",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            "You are a Chief Technology Officer briefing the board. Use the "
                            "`executive_ask` tool with the following scan results as the briefing "
                            "bundle. Enable `extended_thinking: true` for a board-grade response.\n\n"
                            f"Scan results:\n```json\n{scan_results_json}\n```\n\n"
                            "Structure your briefing as:\n"
                            "## Executive Summary (3 sentences max)\n"
                            "## Risk Posture (unified score + top 3 risks)\n"
                            "## Compliance Status (EU AI Act, SOC 2, GDPR — RAG status)\n"
                            "## Cost Optimisation Opportunities (FinOps top savings)\n"
                            "## Migration Readiness (wave plan summary)\n"
                            "## Recommended Board Actions (3 items, 30/60/90 day timeline)\n\n"
                            "Language: non-technical, board-appropriate. "
                            "Avoid jargon. Quantify every risk in business impact terms."
                        ),
                    ),
                ),
            ],
        )

    raise ValueError(f"Unknown prompt: {name}")


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
    scan_result = {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "violations": result.metadata.get("violations", []),
        "compliance_score": result.metadata.get("compliance_score", 0),
        "findings": result.findings,
        "frameworks_checked": result.metadata.get("frameworks_checked", []),
        "model": result.model,
    }
    # Cache the scan so it can be fetched via the scan-results://{scan_id} resource.
    scan_id = str(uuid.uuid4())
    _SCAN_RESULTS_CACHE[scan_id] = scan_result
    scan_result["scan_id"] = scan_id
    scan_result["resource_uri"] = f"scan-results://{scan_id}"
    return scan_result


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
    import argparse

    parser = argparse.ArgumentParser(
        description="Enterprise AI Accelerator MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python mcp_server.py                          # stdio (Claude Code default)\n"
            "  python mcp_server.py --transport sse          # SSE on 0.0.0.0:8765\n"
            "  python mcp_server.py --transport sse --port 9000  # custom port\n"
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use: 'stdio' (default) or 'sse'.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host/interface to bind when using SSE transport (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on when using SSE transport (default: 8765).",
    )
    args = parser.parse_args()

    from mcp_transports import run_stdio, run_sse

    if args.transport == "sse":
        await run_sse(server, host=args.host, port=args.port)
    else:
        await run_stdio(server)


if __name__ == "__main__":
    asyncio.run(main())
