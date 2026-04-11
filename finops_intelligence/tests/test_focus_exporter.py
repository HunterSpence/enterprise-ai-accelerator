"""
Tests for finops_intelligence/focus_exporter.py

Import strategy: load the module directly via importlib.util.spec_from_file_location
to completely bypass finops_intelligence/__init__.py (which imports anomaly_detector
that requires sklearn). This is the only safe way to test this module in isolation.

Run with:
  python -m pytest finops_intelligence/tests/test_focus_exporter.py -v --tb=short -p no:seleniumbase
"""
import importlib.util
import json
import os
import sys
import tempfile
from types import ModuleType

# Install a stub for 'sklearn' BEFORE any finops_intelligence code is loaded,
# in case the test runner's package discovery triggers the __init__.py.
if "sklearn" not in sys.modules:
    _sklearn_stub = ModuleType("sklearn")
    _sklearn_ensemble_stub = ModuleType("sklearn.ensemble")

    class _FakeIsolationForest:
        def __init__(self, *a, **kw): pass
        def fit(self, X): return self
        def predict(self, X): return [1] * len(X)
        def score_samples(self, X): return [0.5] * len(X)

    _sklearn_ensemble_stub.IsolationForest = _FakeIsolationForest
    _sklearn_stub.ensemble = _sklearn_ensemble_stub
    sys.modules["sklearn"] = _sklearn_stub
    sys.modules["sklearn.ensemble"] = _sklearn_ensemble_stub

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Load focus_exporter directly — no __init__.py involved.
# Must register in sys.modules BEFORE exec_module so that dataclasses can find
# the module by cls.__module__ (Python 3.14 dataclasses requires this).
_MODULE_NAME = "finops_intelligence.focus_exporter"
_MODULE_PATH = os.path.join(_REPO_ROOT, "finops_intelligence", "focus_exporter.py")

# Python 3.14 dataclasses resolves cls.__module__ via sys.modules — parent package must exist
if "finops_intelligence" not in sys.modules:
    _fi_pkg = ModuleType("finops_intelligence")
    _fi_pkg.__path__ = [os.path.join(_REPO_ROOT, "finops_intelligence")]
    sys.modules["finops_intelligence"] = _fi_pkg

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod
_spec.loader.exec_module(_mod)

FOCUSExporter = _mod.FOCUSExporter
FOCUSRow = _mod.FOCUSRow
AI_MODEL_PROVIDERS = _mod.AI_MODEL_PROVIDERS
_AZURE_SERVICE_CATEGORY = _mod._AZURE_SERVICE_CATEGORY
_GCP_SERVICE_CATEGORY = _mod._GCP_SERVICE_CATEGORY
_AWS_SERVICE_CATEGORY = _mod._AWS_SERVICE_CATEGORY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_focus_row(**overrides):
    """Build a minimal valid FOCUSRow for testing."""
    defaults = dict(
        BilledCost=10.0,
        BillingAccountId="123456789012",
        BillingAccountName="production",
        BillingPeriodStart="2025-03-01",
        BillingPeriodEnd="2025-04-01",
        ChargePeriodStart="2025-03-15T00:00:00Z",
        ChargePeriodEnd="2025-03-15T23:59:59Z",
        ChargeCategory="Usage",
        ChargeClass="",
        ChargeDescription="EC2 usage",
        ChargeFrequency="Usage-Based",
        EffectiveCost=10.0,
        InvoiceIssuerName="Amazon Web Services",
        ListCost=10.0,
        ListUnitPrice=0.05,
        PricingCategory="On-Demand",
        PricingQuantity=200.0,
        PricingUnit="Hours",
        ProviderName="Amazon Web Services",
        PublisherName="Amazon Web Services",
        RegionId="us-east-1",
        RegionName="US East (N. Virginia)",
        ResourceId="arn:aws:ec2:us-east-1:123:instance/i-abc",
        ResourceName="Amazon EC2",
        ResourceType="Virtual Machines",
        ServiceCategory="Compute",
        ServiceName="Virtual Machines",
        SkuId="aws/amazon-ec2/us-east-1",
        SkuPriceId="aws/amazon-ec2/us-east-1/standard",
        SubAccountId="123456789012",
        SubAccountName="production",
        UsageQuantity=200.0,
        UsageUnit="Hours",
    )
    defaults.update(overrides)
    return FOCUSRow(**defaults)


# ---------------------------------------------------------------------------
# FOCUSRow dataclass
# ---------------------------------------------------------------------------

class TestFOCUSRow:

    def test_minimal_row_creation(self):
        row = _make_focus_row()
        assert row.BilledCost == 10.0
        assert row.ChargeCategory == "Usage"

    def test_optional_fields_default_none(self):
        row = _make_focus_row()
        assert row.InvoiceId is None
        assert row.PricingCurrency is None
        assert row.ServiceProvider is None
        assert row.HostProvider is None
        assert row.CapacityReservationId is None
        assert row.CapacityReservationStatus is None

    def test_optional_fields_set(self):
        row = _make_focus_row(
            InvoiceId="INV-001",
            PricingCurrency="USD",
            ServiceProvider="Amazon Web Services",
            HostProvider="Amazon Web Services",
        )
        assert row.InvoiceId == "INV-001"
        assert row.PricingCurrency == "USD"

    def test_to_dict_contains_required_fields(self):
        row = _make_focus_row()
        d = row.to_dict()
        required = [
            "BilledCost", "BillingAccountId", "BillingPeriodStart", "BillingPeriodEnd",
            "ChargePeriodStart", "ChargePeriodEnd", "ChargeCategory", "EffectiveCost",
            "InvoiceIssuerName", "ListCost", "ProviderName", "ServiceCategory", "ServiceName",
        ]
        for field in required:
            assert field in d, f"Missing required field: {field}"

    def test_to_dict_optional_not_in_output_when_none(self):
        row = _make_focus_row()
        d = row.to_dict()
        assert "InvoiceId" not in d
        assert "PricingCurrency" not in d
        assert "ServiceProvider" not in d
        assert "HostProvider" not in d

    def test_to_dict_optional_present_when_set(self):
        row = _make_focus_row(InvoiceId="INV-2025", ServiceProvider="AWS")
        d = row.to_dict()
        assert "InvoiceId" in d
        assert "ServiceProvider" in d

    def test_to_dict_tags_serialized_as_json(self):
        row = _make_focus_row(Tags={"env": "prod", "team": "devops"})
        d = row.to_dict()
        tags = json.loads(d["Tags"])
        assert tags["env"] == "prod"

    def test_extension_fields_in_dict(self):
        row = _make_focus_row(x_anomaly_score=0.85, x_waste_identified=True)
        d = row.to_dict()
        assert d["x_anomaly_score"] == 0.85
        assert d["x_waste_identified"] is True

    def test_ai_extension_fields_not_in_dict_when_none(self):
        row = _make_focus_row()
        d = row.to_dict()
        assert "x_input_tokens" not in d
        assert "x_output_tokens" not in d
        assert "x_cost_per_1k_tokens" not in d

    def test_ai_extension_fields_present_when_set(self):
        row = _make_focus_row(x_input_tokens=1000000, x_output_tokens=200000, x_cost_per_1k_tokens=0.004)
        d = row.to_dict()
        assert d["x_input_tokens"] == 1000000
        assert d["x_output_tokens"] == 200000
        assert d["x_cost_per_1k_tokens"] == 0.004


# ---------------------------------------------------------------------------
# AI_MODEL_PROVIDERS
# ---------------------------------------------------------------------------

class TestAIModelProviders:

    def test_claude_maps_to_anthropic(self):
        assert AI_MODEL_PROVIDERS["claude"] == "Anthropic"

    def test_gpt_maps_to_openai(self):
        assert AI_MODEL_PROVIDERS["gpt"] == "OpenAI"

    def test_gemini_maps_to_google(self):
        assert AI_MODEL_PROVIDERS["gemini"] == "Google"

    def test_llama_maps_to_meta(self):
        assert AI_MODEL_PROVIDERS["llama"] == "Meta"

    def test_mistral_maps_to_mistral_ai(self):
        assert AI_MODEL_PROVIDERS["mistral"] == "Mistral AI"


# ---------------------------------------------------------------------------
# Service category maps
# ---------------------------------------------------------------------------

class TestServiceCategoryMaps:

    def test_azure_compute_category(self):
        assert _AZURE_SERVICE_CATEGORY["Azure Kubernetes Service"] == "Compute"

    def test_azure_storage_category(self):
        assert _AZURE_SERVICE_CATEGORY["Azure Storage"] == "Storage"

    def test_azure_ai_category(self):
        assert _AZURE_SERVICE_CATEGORY["Azure OpenAI Service"] == "AI and Machine Learning"

    def test_gcp_compute_category(self):
        assert _GCP_SERVICE_CATEGORY["Compute Engine"] == "Compute"

    def test_gcp_ai_category(self):
        assert _GCP_SERVICE_CATEGORY["Vertex AI"] == "AI and Machine Learning"

    def test_aws_storage_category(self):
        assert _AWS_SERVICE_CATEGORY["Amazon S3"] == "Storage"

    def test_aws_compute_category(self):
        assert _AWS_SERVICE_CATEGORY["Amazon EC2"] == "Compute"


# ---------------------------------------------------------------------------
# FOCUSExporter — export_ai_model_costs
# ---------------------------------------------------------------------------

class TestExportAIModelCosts:

    def test_returns_list_of_focus_rows(self):
        exporter = FOCUSExporter(provider="aws", account_id="111222333444")
        rows = exporter.export_ai_model_costs([
            {"model": "claude-sonnet-4-6", "total_cost": 4.20,
             "input_tokens": 1_000_000, "output_tokens": 200_000},
        ])
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert isinstance(rows[0], FOCUSRow)

    def test_claude_provider_detected(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "claude-haiku-4-5", "total_cost": 1.0, "input_tokens": 100000}
        ])
        assert rows[0].ServiceProvider == "Anthropic"

    def test_gpt_provider_detected(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "gpt-4o", "total_cost": 5.0}
        ])
        assert rows[0].ServiceProvider == "OpenAI"

    def test_unknown_model_provider_is_unknown(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "unknown-model-xyz", "total_cost": 2.0}
        ])
        assert rows[0].ServiceProvider == "Unknown"

    def test_ai_row_service_category(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "claude-sonnet-4-6", "total_cost": 1.0}
        ])
        assert rows[0].ServiceCategory == "AI and Machine Learning"

    def test_ai_row_resource_type(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "gemini-1.5-pro", "total_cost": 3.0}
        ])
        assert rows[0].ResourceType == "LLM Inference"

    def test_ai_row_usage_unit_tokens(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "claude-sonnet-4-6", "total_cost": 1.0,
             "input_tokens": 500000, "output_tokens": 100000}
        ])
        assert rows[0].UsageUnit == "Tokens"

    def test_ai_row_token_extension_fields(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "claude-sonnet-4-6", "total_cost": 4.2,
             "input_tokens": 1_000_000, "output_tokens": 200_000}
        ])
        row = rows[0]
        assert row.x_input_tokens == 1_000_000
        assert row.x_output_tokens == 200_000
        assert row.x_cost_per_1k_tokens is not None

    def test_ai_row_cost_per_1k_tokens_calculation(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "claude-sonnet-4-6", "total_cost": 1.0,
             "input_tokens": 1_000_000, "output_tokens": 0}
        ])
        # 1.0 / 1_000_000 * 1000 = 0.001
        assert abs(rows[0].x_cost_per_1k_tokens - 0.001) < 0.0001

    def test_multiple_models_multiple_rows(self):
        exporter = FOCUSExporter()
        rows = exporter.export_ai_model_costs([
            {"model": "claude-sonnet-4-6", "total_cost": 4.20},
            {"model": "gpt-4o", "total_cost": 12.50},
            {"model": "gemini-1.5-pro", "total_cost": 2.10},
        ])
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# FOCUSExporter — validate_focus_compliance
# ---------------------------------------------------------------------------

class TestValidateFOCUSCompliance:

    def test_valid_row_is_compliant(self):
        exporter = FOCUSExporter()
        row = _make_focus_row()
        result = exporter.validate_focus_compliance([row])
        assert result["compliant"] is True
        assert result["errors"] == []

    def test_empty_rows_is_compliant(self):
        exporter = FOCUSExporter()
        result = exporter.validate_focus_compliance([])
        assert result["compliant"] is True
        assert result["total_rows"] == 0

    def test_invalid_charge_category_reports_error(self):
        exporter = FOCUSExporter()
        row = _make_focus_row(ChargeCategory="Invalid")
        result = exporter.validate_focus_compliance([row])
        assert result["compliant"] is False
        assert len(result["errors"]) >= 1

    def test_negative_billed_cost_is_warning(self):
        exporter = FOCUSExporter()
        row = _make_focus_row(BilledCost=-5.0)
        result = exporter.validate_focus_compliance([row])
        assert len(result["warnings"]) >= 1

    def test_focus_version_present(self):
        exporter = FOCUSExporter()
        row = _make_focus_row()
        result = exporter.validate_focus_compliance([row])
        assert result["focus_version"] in ("1.0", "1.2", "1.3")

    def test_focus_version_12_with_invoice_id(self):
        exporter = FOCUSExporter()
        row = _make_focus_row(InvoiceId="INV-2025")
        result = exporter.validate_focus_compliance([row])
        assert result["focus_version"] in ("1.2", "1.3")
        assert result["focus_1_2_columns_present"] is True

    def test_focus_version_13_with_service_provider(self):
        exporter = FOCUSExporter()
        row = _make_focus_row(ServiceProvider="AWS", HostProvider="AWS")
        result = exporter.validate_focus_compliance([row])
        assert result["focus_version"] == "1.3"
        assert result["focus_1_3_columns_present"] is True

    def test_result_has_spec_uri(self):
        exporter = FOCUSExporter()
        result = exporter.validate_focus_compliance([])
        assert "spec_uri" in result
        assert "focus.finops.org" in result["spec_uri"]

    def test_capacity_reservation_invalid_status_is_warning(self):
        exporter = FOCUSExporter()
        row = _make_focus_row(CapacityReservationStatus="InvalidStatus")
        result = exporter.validate_focus_compliance([row])
        assert len(result["warnings"]) >= 1


# ---------------------------------------------------------------------------
# FOCUSExporter — export_jsonl and export_csv
# ---------------------------------------------------------------------------

class TestExportFiles:

    def test_export_jsonl_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = FOCUSExporter()
            rows = [_make_focus_row()]
            path = exporter.export_jsonl(os.path.join(tmp, "out.jsonl"), rows)
            assert os.path.exists(path)

    def test_export_jsonl_content_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = FOCUSExporter()
            rows = [_make_focus_row(BilledCost=99.5)]
            path = exporter.export_jsonl(os.path.join(tmp, "out.jsonl"), rows)
            with open(path) as f:
                data = json.loads(f.readline())
            assert data["BilledCost"] == 99.5

    def test_export_csv_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = FOCUSExporter()
            rows = [_make_focus_row()]
            path = exporter.export_csv(os.path.join(tmp, "out.csv"), rows)
            assert os.path.exists(path)

    def test_export_csv_has_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = FOCUSExporter()
            rows = [_make_focus_row()]
            path = exporter.export_csv(os.path.join(tmp, "out.csv"), rows)
            with open(path) as f:
                header = f.readline()
            assert "BilledCost" in header
            assert "ServiceName" in header


# ---------------------------------------------------------------------------
# Parquet export (skip if pyarrow/pandas not available)
# ---------------------------------------------------------------------------

class TestParquetExport:

    def test_export_parquet_with_pyarrow(self):
        pyarrow = pytest.importorskip("pyarrow")
        with tempfile.TemporaryDirectory() as tmp:
            exporter = FOCUSExporter()
            rows = [_make_focus_row()]
            path = exporter.export_parquet(os.path.join(tmp, "out.parquet"), rows)
            assert os.path.exists(path)

    def test_export_parquet_raises_without_deps_mocked(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("pyarrow", "pandas"):
                raise ImportError(f"mocked: {name} not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with tempfile.TemporaryDirectory() as tmp:
            exporter = FOCUSExporter()
            rows = [_make_focus_row()]
            with pytest.raises(ImportError):
                exporter.export_parquet(os.path.join(tmp, "out.parquet"), rows)
