"""
AIAuditTrail MCP Server — stdio transport
==========================================
Exposes AIAuditTrail's core functionality as MCP tools so any Claude client
(Claude Code, Claude Desktop) can log decisions, run compliance checks,
export SARIF, and verify the hash chain without writing integration code.

Optional dependency: mcp>=1.0.0  (pip install mcp)

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "enterprise-ai-accelerator": {
          "command": "python",
          "args": ["mcp_server.py"],
          "cwd": "/path/to/enterprise-ai-accelerator"
        }
      }
    }

Set AUDIT_DB_PATH env var to override the default SQLite path (audit_trail.db).
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

# ---------------------------------------------------------------------------
# Shared chain instance
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("AUDIT_DB_PATH", "audit_trail.db")
_chain: AuditChain | None = None


def _get_chain() -> AuditChain:
    global _chain
    if _chain is None:
        _chain = AuditChain(db_path=_DB_PATH, store_plaintext=False)
    return _chain


# ---------------------------------------------------------------------------
# SARIF 2.1.0 builder
# ---------------------------------------------------------------------------

_SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
_RISK_LEVEL = {"UNACCEPTABLE": "error", "HIGH": "error", "LIMITED": "warning", "MINIMAL": "note"}
_RISK_SCORE = {"UNACCEPTABLE": "9.5", "HIGH": "7.5", "LIMITED": "4.0", "MINIMAL": "1.0"}


def _build_sarif(chain: AuditChain) -> dict[str, Any]:
    """Build SARIF 2.1.0 from audit chain. HIGH/UNACCEPTABLE entries surface as errors."""
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
# MCP server
# ---------------------------------------------------------------------------

server = Server("enterprise-ai-accelerator")

_TOOLS = [
    Tool(
        name="audit_log_decision",
        description="Log an AI decision with metadata to the tamper-evident hash chain. Returns the created entry with its SHA-256 hash.",
        inputSchema={
            "type": "object",
            "required": ["model", "input_summary", "output_summary", "risk_level"],
            "properties": {
                "model": {"type": "string", "description": "AI model identifier (e.g. claude-sonnet-4-6)"},
                "input_summary": {"type": "string", "description": "Human-readable summary of the prompt/input"},
                "output_summary": {"type": "string", "description": "Human-readable summary of the AI output"},
                "risk_level": {"type": "string", "enum": ["MINIMAL", "LIMITED", "HIGH", "UNACCEPTABLE"], "description": "EU AI Act risk tier"},
                "decision_type": {"type": "string", "enum": ["RECOMMENDATION", "CLASSIFICATION", "GENERATION", "AUTONOMOUS_ACTION", "TOOL_USE", "RETRIEVAL"], "default": "GENERATION"},
                "system_id": {"type": "string", "description": "AI system identifier (default: mcp-client)"},
                "session_id": {"type": "string", "description": "Session/conversation ID (auto-generated if omitted)"},
                "metadata": {"type": "object", "description": "Optional extra metadata"},
            },
        },
    ),
    Tool(
        name="get_compliance_status",
        description="Run EU AI Act Article 12 compliance check against the current audit trail. Returns pass/fail, score 0-100, missing requirements, and enforcement countdown.",
        inputSchema={
            "type": "object",
            "properties": {
                "system_id": {"type": "string", "description": "Filter to a specific system (optional)"},
            },
        },
    ),
    Tool(
        name="export_sarif",
        description="Export the audit trail as SARIF 2.1.0 JSON. Upload to GitHub Security tab, VS Code, or any SARIF-compatible tool. HIGH/UNACCEPTABLE entries appear as errors.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_audit_chain",
        description="Retrieve audit trail entries with hash chain verification. Returns entries, Merkle root, and tamper detection results.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20, "description": "Max entries to return (max 200)"},
                "system_id": {"type": "string", "description": "Filter by system_id (optional)"},
                "risk_tier": {"type": "string", "enum": ["MINIMAL", "LIMITED", "HIGH", "UNACCEPTABLE"], "description": "Filter by risk tier (optional)"},
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
        result = _dispatch(name, arguments)
    except Exception as exc:
        result = {"error": str(exc), "tool": name}
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _dispatch(name: str, args: dict[str, Any]) -> Any:
    chain = _get_chain()

    if name == "audit_log_decision":
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
            metadata=args.get("metadata") or {},
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

    if name == "get_compliance_status":
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

    if name == "export_sarif":
        return _build_sarif(chain)

    if name == "get_audit_chain":
        limit = min(int(args.get("limit", 20)), 200)
        entries = chain.query(system_id=args.get("system_id"), risk_tier=args.get("risk_tier"), limit=limit)
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

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
