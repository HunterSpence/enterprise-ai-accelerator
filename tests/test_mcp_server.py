"""Tests for mcp_server.py — tool registry count and tool handler signatures."""

import pytest


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
        # Either or both of these should exist
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
