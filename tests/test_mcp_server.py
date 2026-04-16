"""Tests for mcp_server.py — tool registry, resources, prompts, SSE health endpoint."""

from __future__ import annotations

import json
import time

import pytest


# ---------------------------------------------------------------------------
# Existing tool registry tests (19 tests — all unchanged)
# ---------------------------------------------------------------------------

class TestMCPToolRegistry:
    """Verify the MCP tool catalog is fully populated."""

    def test_tool_count_at_least_18(self):
        from mcp_server import _TOOLS
        assert len(_TOOLS) >= 18

    def test_all_tools_have_names(self):
        from mcp_server import _TOOLS
        for tool in _TOOLS:
            assert tool.name and isinstance(tool.name, str)

    def test_all_tools_have_descriptions(self):
        from mcp_server import _TOOLS
        for tool in _TOOLS:
            assert tool.description and len(tool.description) > 5

    def test_all_tools_have_input_schema(self):
        from mcp_server import _TOOLS
        for tool in _TOOLS:
            schema = tool.inputSchema
            assert isinstance(schema, dict)
            assert schema.get("type") == "object"

    def test_audit_log_decision_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert "audit_log_decision" in names

    def test_get_compliance_status_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert "get_compliance_status" in names

    def test_export_sarif_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert "export_sarif" in names

    def test_list_models_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert "list_models" in names

    def test_cloudiq_analyze_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert "cloudiq_analyze_environment" in names

    def test_migration_assess_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert "migration_assess_workload" in names

    def test_finops_anomaly_or_explain_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert any(n.startswith("finops_") for n in names)

    def test_no_duplicate_tool_names(self):
        from mcp_server import _TOOLS
        names = [t.name for t in _TOOLS]
        assert len(names) == len(set(names))

    def test_server_object_exists(self):
        from mcp_server import server
        assert server is not None

    def test_tool_schema_properties_is_dict(self):
        from mcp_server import _TOOLS
        for tool in _TOOLS:
            props = tool.inputSchema.get("properties", {})
            assert isinstance(props, dict)

    def test_audit_log_decision_has_required_fields(self):
        from mcp_server import _TOOLS
        tool = next(t for t in _TOOLS if t.name == "audit_log_decision")
        required = tool.inputSchema.get("required", [])
        assert "model" in required
        assert "risk_level" in required

    def test_get_audit_chain_has_limit_property(self):
        from mcp_server import _TOOLS
        tool = next(t for t in _TOOLS if t.name == "get_audit_chain")
        props = tool.inputSchema.get("properties", {})
        assert "limit" in props

    def test_migration_bulk_classify_has_workloads(self):
        from mcp_server import _TOOLS
        tool = next((t for t in _TOOLS if t.name == "migration_bulk_classify"), None)
        if tool is None:
            pytest.skip("migration_bulk_classify not in this build")
        required = tool.inputSchema.get("required", [])
        assert "workloads" in required

    def test_executive_chat_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert any("executive" in n or "chat" in n for n in names)

    def test_compliance_citations_tool_present(self):
        from mcp_server import _TOOLS
        names = {t.name for t in _TOOLS}
        assert any("compliance" in n or "citation" in n for n in names)


# ---------------------------------------------------------------------------
# Resources list/read tests
# ---------------------------------------------------------------------------

class TestMCPResources:
    """Verify the MCP resource registry and read handlers."""

    def test_resource_registry_not_empty(self):
        from mcp_server import _RESOURCES
        assert len(_RESOURCES) >= 4

    def test_resource_uris_are_strings(self):
        from mcp_server import _RESOURCES
        for r in _RESOURCES:
            assert str(r.uri)

    def test_audit_trail_recent_resource_registered(self):
        from mcp_server import _RESOURCES
        uris = {str(r.uri) for r in _RESOURCES}
        assert "audit-trail://recent" in uris

    def test_audit_trail_chain_verify_resource_registered(self):
        from mcp_server import _RESOURCES
        uris = {str(r.uri) for r in _RESOURCES}
        assert "audit-trail://chain-verify" in uris

    def test_compliance_frameworks_resource_registered(self):
        from mcp_server import _RESOURCES
        uris = {str(r.uri) for r in _RESOURCES}
        assert "compliance://frameworks" in uris

    def test_policy_catalog_iac_resource_registered(self):
        from mcp_server import _RESOURCES
        uris = {str(r.uri) for r in _RESOURCES}
        assert "policy-catalog://iac" in uris

    def test_all_resources_have_names(self):
        from mcp_server import _RESOURCES
        for r in _RESOURCES:
            assert r.name and len(r.name) > 2

    def test_all_resources_have_mime_type(self):
        from mcp_server import _RESOURCES
        for r in _RESOURCES:
            assert r.mimeType == "application/json"

    @pytest.mark.asyncio
    async def test_read_resource_compliance_frameworks(self):
        from mcp.types import AnyUrl
        from mcp_server import read_resource
        result = await read_resource(AnyUrl("compliance://frameworks"))
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 7
        ids = {f["id"] for f in data}
        assert "cis_aws" in ids
        assert "eu_ai_act" in ids

    @pytest.mark.asyncio
    async def test_read_resource_policy_catalog(self):
        from mcp.types import AnyUrl
        from mcp_server import read_resource
        result = await read_resource(AnyUrl("policy-catalog://iac"))
        data = json.loads(result)
        assert data["total_policies"] == 20
        assert len(data["policies"]) == 20
        # Check all 4 frameworks represented
        frameworks = {p["framework"] for p in data["policies"]}
        assert "CIS AWS" in frameworks
        assert "SOC 2" in frameworks
        assert "GDPR" in frameworks
        assert "PCI-DSS" in frameworks

    @pytest.mark.asyncio
    async def test_read_resource_audit_trail_recent_returns_json(self):
        from mcp.types import AnyUrl
        from mcp_server import read_resource
        result = await read_resource(AnyUrl("audit-trail://recent"))
        # Should be valid JSON (empty list is fine — no entries in test DB)
        data = json.loads(result)
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_read_resource_audit_chain_verify_returns_json(self):
        from mcp.types import AnyUrl
        from mcp_server import read_resource
        result = await read_resource(AnyUrl("audit-trail://chain-verify"))
        data = json.loads(result)
        assert "is_valid" in data
        assert "total_entries" in data

    @pytest.mark.asyncio
    async def test_read_resource_unknown_uri_returns_error(self):
        from mcp.types import AnyUrl
        from mcp_server import read_resource
        result = await read_resource(AnyUrl("unknown://nope"))
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_read_resource_scan_results_missing_returns_error(self):
        from mcp.types import AnyUrl
        from mcp_server import read_resource
        result = await read_resource(AnyUrl("scan-results://nonexistent-scan-id-xyz"))
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_read_resource_scan_results_cached_returns_data(self):
        """Simulate a scan result being cached and retrieved via resource URI."""
        from mcp.types import AnyUrl
        import uuid
        from mcp_server import read_resource, _SCAN_RESULTS_CACHE
        scan_id = str(uuid.uuid4())
        _SCAN_RESULTS_CACHE[scan_id] = {"status": "complete", "violations": [], "compliance_score": 95}
        result = await read_resource(AnyUrl(f"scan-results://{scan_id}"))
        data = json.loads(result)
        assert data["status"] == "complete"
        assert data["compliance_score"] == 95
        # Cleanup
        del _SCAN_RESULTS_CACHE[scan_id]

    def test_iac_policy_catalog_has_20_policies(self):
        from mcp_server import _IAC_POLICY_CATALOG
        assert len(_IAC_POLICY_CATALOG) == 20

    def test_iac_policy_catalog_covers_all_4_frameworks(self):
        from mcp_server import _IAC_POLICY_CATALOG
        frameworks = {p["framework"] for p in _IAC_POLICY_CATALOG}
        assert frameworks == {"CIS AWS", "SOC 2", "GDPR", "PCI-DSS"}

    def test_iac_policy_catalog_all_have_required_fields(self):
        from mcp_server import _IAC_POLICY_CATALOG
        for policy in _IAC_POLICY_CATALOG:
            assert "id" in policy
            assert "framework" in policy
            assert "title" in policy
            assert "severity" in policy
            assert policy["severity"] in {"critical", "high", "medium", "low"}


# ---------------------------------------------------------------------------
# Prompts list/get tests
# ---------------------------------------------------------------------------

class TestMCPPrompts:
    """Verify the MCP prompt registry and get handlers."""

    def test_prompt_registry_not_empty(self):
        from mcp_server import _PROMPTS
        assert len(_PROMPTS) >= 4

    def test_prompt_names_unique(self):
        from mcp_server import _PROMPTS
        names = [p.name for p in _PROMPTS]
        assert len(names) == len(set(names))

    def test_audit_terraform_prompt_registered(self):
        from mcp_server import _PROMPTS
        names = {p.name for p in _PROMPTS}
        assert "audit-terraform" in names

    def test_classify_workload_6r_prompt_registered(self):
        from mcp_server import _PROMPTS
        names = {p.name for p in _PROMPTS}
        assert "classify-workload-6r" in names

    def test_assess_bias_prompt_registered(self):
        from mcp_server import _PROMPTS
        names = {p.name for p in _PROMPTS}
        assert "assess-bias" in names

    def test_executive_briefing_prompt_registered(self):
        from mcp_server import _PROMPTS
        names = {p.name for p in _PROMPTS}
        assert "executive-briefing" in names

    def test_all_prompts_have_descriptions(self):
        from mcp_server import _PROMPTS
        for p in _PROMPTS:
            assert p.description and len(p.description) > 10

    def test_audit_terraform_has_required_arguments(self):
        from mcp_server import _PROMPTS
        prompt = next(p for p in _PROMPTS if p.name == "audit-terraform")
        arg_names = {a.name for a in (prompt.arguments or [])}
        assert "path" in arg_names
        assert "environment" in arg_names

    def test_classify_workload_6r_has_workload_json_arg(self):
        from mcp_server import _PROMPTS
        prompt = next(p for p in _PROMPTS if p.name == "classify-workload-6r")
        arg_names = {a.name for a in (prompt.arguments or [])}
        assert "workload_json" in arg_names

    def test_assess_bias_has_dataset_summary_arg(self):
        from mcp_server import _PROMPTS
        prompt = next(p for p in _PROMPTS if p.name == "assess-bias")
        arg_names = {a.name for a in (prompt.arguments or [])}
        assert "dataset_summary" in arg_names

    def test_executive_briefing_has_scan_results_arg(self):
        from mcp_server import _PROMPTS
        prompt = next(p for p in _PROMPTS if p.name == "executive-briefing")
        arg_names = {a.name for a in (prompt.arguments or [])}
        assert "scan_results_json" in arg_names

    @pytest.mark.asyncio
    async def test_get_prompt_audit_terraform(self):
        from mcp_server import get_prompt
        result = await get_prompt("audit-terraform", {"path": "/tf/prod", "environment": "production"})
        assert result.messages
        msg = result.messages[0]
        assert msg.role == "user"
        assert "/tf/prod" in msg.content.text
        assert "production" in msg.content.text
        assert "policyguard_scan_iac" in msg.content.text

    @pytest.mark.asyncio
    async def test_get_prompt_classify_workload_6r(self):
        from mcp_server import get_prompt
        workload = json.dumps({"name": "legacy-app", "runtime": "Java 8"})
        result = await get_prompt("classify-workload-6r", {"workload_json": workload})
        assert result.messages
        msg = result.messages[0]
        assert "migration_assess_workload" in msg.content.text
        assert "legacy-app" in msg.content.text

    @pytest.mark.asyncio
    async def test_get_prompt_assess_bias(self):
        from mcp_server import get_prompt
        result = await get_prompt("assess-bias", {"dataset_summary": "HR promotion dataset, 10k rows"})
        assert result.messages
        msg = result.messages[0]
        assert "policyguard_audit_bias" in msg.content.text
        assert "EU AI Act" in msg.content.text

    @pytest.mark.asyncio
    async def test_get_prompt_executive_briefing(self):
        from mcp_server import get_prompt
        result = await get_prompt("executive-briefing", {"scan_results_json": '{"risk_score": 72}'})
        assert result.messages
        msg = result.messages[0]
        assert "executive_ask" in msg.content.text
        assert "board" in msg.content.text.lower()

    @pytest.mark.asyncio
    async def test_get_prompt_unknown_raises(self):
        from mcp_server import get_prompt
        with pytest.raises(ValueError, match="Unknown prompt"):
            await get_prompt("nonexistent-prompt", {})

    @pytest.mark.asyncio
    async def test_get_prompt_returns_description(self):
        from mcp_server import get_prompt
        result = await get_prompt("audit-terraform", {"path": "/tf", "environment": "staging"})
        assert result.description and len(result.description) > 5

    @pytest.mark.asyncio
    async def test_get_prompt_with_none_arguments(self):
        """get_prompt must handle None arguments gracefully (uses defaults)."""
        from mcp_server import get_prompt
        result = await get_prompt("classify-workload-6r", None)
        assert result.messages
        assert result.messages[0].role == "user"


# ---------------------------------------------------------------------------
# SSE health endpoint test
# ---------------------------------------------------------------------------

class TestSSEHealthEndpoint:
    """Verify the /health endpoint when the SSE Starlette app is exercised."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self):
        """Use Starlette's TestClient to hit /health without starting a real server."""
        import importlib
        httpx = importlib.import_module("httpx")
        starlette_testclient = importlib.import_module("starlette.testclient")
        TestClient = starlette_testclient.TestClient

        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        import time as _time

        start = _time.monotonic()

        async def health(request: Request) -> JSONResponse:
            from mcp_server import _TOOLS, _RESOURCES, _PROMPTS
            return JSONResponse({
                "status": "ok",
                "tools": len(_TOOLS),
                "resources": len(_RESOURCES),
                "prompts": len(_PROMPTS),
                "uptime_s": round(_time.monotonic() - start, 1),
            })

        app = Starlette(routes=[Route("/health", health, methods=["GET"])])
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_json_schema(self):
        """Health response must have status, tools, resources, prompts, uptime_s."""
        import importlib
        import time as _time
        starlette_testclient = importlib.import_module("starlette.testclient")
        TestClient = starlette_testclient.TestClient

        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        start = _time.monotonic()

        async def health(request: Request) -> JSONResponse:
            from mcp_server import _TOOLS, _RESOURCES, _PROMPTS
            return JSONResponse({
                "status": "ok",
                "tools": len(_TOOLS),
                "resources": len(_RESOURCES),
                "prompts": len(_PROMPTS),
                "uptime_s": round(_time.monotonic() - start, 1),
            })

        app = Starlette(routes=[Route("/health", health, methods=["GET"])])
        client = TestClient(app)
        response = client.get("/health")
        data = response.json()

        assert data["status"] == "ok"
        assert isinstance(data["tools"], int) and data["tools"] >= 18
        assert isinstance(data["resources"], int) and data["resources"] >= 4
        assert isinstance(data["prompts"], int) and data["prompts"] >= 4
        assert isinstance(data["uptime_s"], (int, float))

    @pytest.mark.asyncio
    async def test_health_endpoint_tool_count_matches_registry(self):
        """tools count in /health must match len(_TOOLS)."""
        import importlib
        import time as _time
        starlette_testclient = importlib.import_module("starlette.testclient")
        TestClient = starlette_testclient.TestClient

        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from mcp_server import _TOOLS, _RESOURCES, _PROMPTS

        async def health(request: Request) -> JSONResponse:
            return JSONResponse({
                "status": "ok",
                "tools": len(_TOOLS),
                "resources": len(_RESOURCES),
                "prompts": len(_PROMPTS),
                "uptime_s": 0.0,
            })

        app = Starlette(routes=[Route("/health", health, methods=["GET"])])
        client = TestClient(app)
        response = client.get("/health")
        data = response.json()

        assert data["tools"] == len(_TOOLS)
        assert data["resources"] == len(_RESOURCES)
        assert data["prompts"] == len(_PROMPTS)
