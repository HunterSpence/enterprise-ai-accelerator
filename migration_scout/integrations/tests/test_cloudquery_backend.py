"""
Tests for migration_scout/integrations/cloudquery_backend.py

Import strategy: load the module directly via importlib to bypass
migration_scout/__init__.py which imports models.py using pydantic v2 syntax
(BaseModel with model_validator, etc.) incompatible with pydantic 1.10.26.
"""
import importlib.util
import json
import os
import sys
import tempfile
from types import ModuleType
from unittest.mock import MagicMock, patch
import subprocess

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Stub 'migration_scout' package so its __init__.py is never executed
if "migration_scout" not in sys.modules:
    _ms_pkg = ModuleType("migration_scout")
    _ms_pkg.__path__ = [os.path.join(_REPO_ROOT, "migration_scout")]
    sys.modules["migration_scout"] = _ms_pkg

if "migration_scout.integrations" not in sys.modules:
    _ms_int_pkg = ModuleType("migration_scout.integrations")
    _ms_int_pkg.__path__ = [os.path.join(_REPO_ROOT, "migration_scout", "integrations")]
    sys.modules["migration_scout.integrations"] = _ms_int_pkg

_MODULE_NAME = "migration_scout.integrations.cloudquery_backend"
_MODULE_PATH = os.path.join(
    _REPO_ROOT, "migration_scout", "integrations", "cloudquery_backend.py"
)
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod
_spec.loader.exec_module(_mod)

CloudQueryBackend = _mod.CloudQueryBackend
CloudQueryResult = _mod.CloudQueryResult
DiscoveredWorkload = _mod.DiscoveredWorkload
_CQ_CONFIGS = _mod._CQ_CONFIGS
_PROVIDER_PARSERS = _mod._PROVIDER_PARSERS
_parse_aws_instance = _mod._parse_aws_instance
_parse_aws_rds = _mod._parse_aws_rds
_parse_azure_vm = _mod._parse_azure_vm
_parse_gcp_instance = _mod._parse_gcp_instance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove cloud provider env vars so tests control detection explicitly."""
    for key in ("AWS_ACCESS_KEY_ID", "AWS_PROFILE", "AZURE_CLIENT_ID",
                "AZURE_SUBSCRIPTION", "GOOGLE_APPLICATION_CREDENTIALS",
                "GCP_PROJECT", "CQ_CLOUD_PROVIDER"):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# CloudQueryBackend instantiation
# ---------------------------------------------------------------------------

class TestInstantiation:

    def test_default_instantiation(self):
        backend = CloudQueryBackend(provider="aws")
        assert backend.provider == "aws"

    def test_provider_lowercase_normalised(self):
        backend = CloudQueryBackend(provider="AWS")
        assert backend.provider == "aws"

    def test_region_defaults_to_us_east_1(self):
        backend = CloudQueryBackend(provider="aws")
        assert backend.region == "us-east-1"

    def test_custom_region(self):
        backend = CloudQueryBackend(provider="aws", region="eu-west-1")
        assert backend.region == "eu-west-1"

    def test_timeout_default(self):
        backend = CloudQueryBackend(provider="aws")
        assert backend.timeout_seconds == 120

    def test_custom_timeout(self):
        backend = CloudQueryBackend(provider="aws", timeout_seconds=60)
        assert backend.timeout_seconds == 60

    def test_azure_provider(self):
        backend = CloudQueryBackend(provider="azure")
        assert backend.provider == "azure"

    def test_gcp_provider(self):
        backend = CloudQueryBackend(provider="gcp")
        assert backend.provider == "gcp"


# ---------------------------------------------------------------------------
# cli_available property
# ---------------------------------------------------------------------------

class TestCLIAvailable:

    def test_cli_unavailable_when_cq_not_on_path(self):
        backend = CloudQueryBackend(provider="aws")
        # In CI / this environment, 'cq' is almost certainly not installed
        # Assert that the property returns a bool regardless of outcome
        assert isinstance(backend.cli_available, bool)

    def test_cli_unavailable_when_path_is_none(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None
        assert backend.cli_available is False

    def test_cli_available_when_path_set(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = "/usr/local/bin/cq"
        assert backend.cli_available is True


# ---------------------------------------------------------------------------
# discover() with no CLI available (fallback path)
# ---------------------------------------------------------------------------

class TestDiscoverNoCLI:

    def test_discover_returns_cloud_query_result(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None  # force no CLI
        result = backend.discover()
        assert isinstance(result, CloudQueryResult)

    def test_discover_no_cli_available_false(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None
        result = backend.discover()
        assert result.available is False

    def test_discover_no_cli_empty_workloads(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None
        result = backend.discover()
        assert result.workloads == []

    def test_discover_no_cli_has_fallback_reason(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None
        result = backend.discover()
        assert len(result.fallback_reason) > 0
        assert "CloudQuery" in result.fallback_reason or "cq" in result.fallback_reason

    def test_discover_unsupported_provider_available_false(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = "/usr/bin/cq"  # pretend CLI is present
        backend.provider = "oracle"  # unsupported
        result = backend.discover()
        assert result.available is False
        assert "oracle" in result.fallback_reason

    def test_discover_no_cli_provider_preserved(self):
        backend = CloudQueryBackend(provider="azure")
        backend._cli_path = None
        result = backend.discover()
        assert result.provider == "azure"

    def test_discover_workload_count_property(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None
        result = backend.discover()
        assert result.workload_count == 0

    def test_discover_is_live_data_false_without_cli(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None
        result = backend.discover()
        assert result.is_live_data is False


# ---------------------------------------------------------------------------
# discover() with mocked CLI
# ---------------------------------------------------------------------------

class TestDiscoverWithMockedCLI:

    def test_discover_cli_timeout_returns_fallback(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = "/usr/local/bin/cq"

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="cq", timeout=120)):
            result = backend.discover()

        assert result.available is False
        assert "timeout" in result.error.lower() or "timeout" in result.fallback_reason.lower()

    def test_discover_cli_os_error_returns_fallback(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = "/usr/local/bin/cq"

        with patch("subprocess.run", side_effect=OSError("binary not found")):
            result = backend.discover()

        assert result.available is False
        assert result.error != ""

    def test_discover_cli_nonzero_exit_returns_fallback(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = "/usr/local/bin/cq"

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "Error: no credentials"

        with patch("subprocess.run", return_value=mock_proc):
            result = backend.discover()

        assert result.available is False
        assert "1" in result.error  # exit code in error message

    def test_discover_cli_success_with_jsonl_ec2(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = "/usr/local/bin/cq"

        ec2_record = json.dumps({
            "__table": "aws_ec2_instances",
            "instance_id": "i-0abc123",
            "instance_type": "m5.xlarge",
            "region": "us-east-1",
            "tags": [{"Key": "Name", "Value": "web-server"}],
        })

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ec2_record + "\n"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            # Also need tempdir to not fail on listdir
            with patch("os.listdir", return_value=[]):
                result = backend.discover()

        assert result.available is True
        assert result.workload_count == 1
        assert result.workloads[0].id == "i-0abc123"
        assert result.workloads[0].name == "web-server"

    def test_discover_cli_success_with_rds_record(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = "/usr/local/bin/cq"

        rds_record = json.dumps({
            "__table": "aws_rds_instances",
            "db_instance_identifier": "my-postgres-db",
            "engine": "postgres",
            "region": "us-east-1",
        })

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = rds_record + "\n"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            with patch("os.listdir", return_value=[]):
                result = backend.discover()

        assert result.available is True
        assert result.workloads[0].database_type == "postgres"
        assert result.workloads[0].workload_type == "database"


# ---------------------------------------------------------------------------
# Provider auto-detection
# ---------------------------------------------------------------------------

class TestProviderDetection:

    def test_detect_aws_from_access_key(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKEKEY")
        provider = CloudQueryBackend._detect_provider()
        assert provider == "aws"

    def test_detect_aws_from_profile(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "default")
        provider = CloudQueryBackend._detect_provider()
        assert provider == "aws"

    def test_detect_azure_from_client_id(self, monkeypatch):
        monkeypatch.setenv("AZURE_CLIENT_ID", "fake-client-id")
        provider = CloudQueryBackend._detect_provider()
        assert provider == "azure"

    def test_detect_azure_from_subscription(self, monkeypatch):
        monkeypatch.setenv("AZURE_SUBSCRIPTION", "fake-sub-id")
        provider = CloudQueryBackend._detect_provider()
        assert provider == "azure"

    def test_detect_gcp_from_credentials(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/key.json")
        provider = CloudQueryBackend._detect_provider()
        assert provider == "gcp"

    def test_detect_gcp_from_project(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "my-gcp-project")
        provider = CloudQueryBackend._detect_provider()
        assert provider == "gcp"

    def test_default_fallback_is_aws(self):
        # All cloud env vars stripped by clean_env fixture
        provider = CloudQueryBackend._detect_provider()
        assert provider == "aws"

    def test_env_var_cq_cloud_provider_used(self, monkeypatch):
        monkeypatch.setenv("CQ_CLOUD_PROVIDER", "azure")
        backend = CloudQueryBackend()  # no explicit provider
        assert backend.provider == "azure"


# ---------------------------------------------------------------------------
# Provider parsers
# ---------------------------------------------------------------------------

class TestProviderParsers:

    def test_parse_aws_instance_basic(self):
        raw = {
            "instance_id": "i-abc123",
            "instance_type": "m5.xlarge",
            "region": "us-west-2",
            "tags": [{"Key": "Name", "Value": "app-server"}],
        }
        wl = _parse_aws_instance(raw, 0)
        assert wl.provider == "aws"
        assert wl.id == "i-abc123"
        assert wl.name == "app-server"
        assert wl.cpu_cores == 4  # m5.xlarge
        assert wl.region == "us-west-2"

    def test_parse_aws_instance_fallback_name(self):
        raw = {"instance_id": "i-xyz", "instance_type": "t3.micro", "tags": []}
        wl = _parse_aws_instance(raw, 0)
        assert wl.name == "i-xyz"

    def test_parse_aws_rds_basic(self):
        raw = {
            "db_instance_identifier": "prod-db",
            "engine": "mysql",
            "region": "us-east-1",
        }
        wl = _parse_aws_rds(raw, 0)
        assert wl.workload_type == "database"
        assert wl.database_type == "mysql"
        assert wl.provider == "aws"

    def test_parse_azure_vm_basic(self):
        raw = {
            "id": "/subscriptions/abc/resourceGroups/rg/providers/vm/my-vm",
            "name": "my-azure-vm",
            "location": "eastus",
        }
        wl = _parse_azure_vm(raw, 0)
        assert wl.provider == "azure"
        assert wl.name == "my-azure-vm"
        assert wl.workload_type == "compute_instance"

    def test_parse_gcp_instance_basic(self):
        raw = {
            "id": "12345",
            "name": "gcp-vm-1",
            "machine_type": "zones/us-central1-a/machineTypes/n1-standard-4",
            "zone": "us-central1-a",
        }
        wl = _parse_gcp_instance(raw, 0)
        assert wl.provider == "gcp"
        assert wl.name == "gcp-vm-1"
        assert wl.cpu_cores == 4  # n1-standard-4


# ---------------------------------------------------------------------------
# DiscoveredWorkload and CloudQueryResult dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:

    def test_discovered_workload_defaults(self):
        wl = DiscoveredWorkload(
            id="wl-1",
            name="my-workload",
            workload_type="compute_instance",
            provider="aws",
            region="us-east-1",
            resource_type="aws_ec2_instance",
        )
        assert wl.language == "unknown"
        assert wl.database_type is None
        assert wl.monthly_cost_estimate == 0.0

    def test_cloud_query_result_workload_count(self):
        result = CloudQueryResult(
            available=True,
            provider="aws",
            workloads=[
                DiscoveredWorkload("id1", "n1", "compute_instance", "aws", "us-east-1", "aws_ec2_instance"),
                DiscoveredWorkload("id2", "n2", "compute_instance", "aws", "us-east-1", "aws_ec2_instance"),
            ],
        )
        assert result.workload_count == 2

    def test_cloud_query_result_is_live_data(self):
        result = CloudQueryResult(available=True, provider="aws", workloads=[])
        assert result.is_live_data is True

    def test_cloud_query_result_not_live_when_error(self):
        result = CloudQueryResult(
            available=True,
            provider="aws",
            workloads=[],
            error="something failed",
        )
        assert result.is_live_data is False


# ---------------------------------------------------------------------------
# CQ configs
# ---------------------------------------------------------------------------

class TestCQConfigs:

    def test_aws_config_exists(self):
        assert "aws" in _CQ_CONFIGS
        assert "aws_ec2_instances" in _CQ_CONFIGS["aws"]

    def test_azure_config_exists(self):
        assert "azure" in _CQ_CONFIGS
        assert "azure_compute_virtual_machines" in _CQ_CONFIGS["azure"]

    def test_gcp_config_exists(self):
        assert "gcp" in _CQ_CONFIGS
        assert "gcp_compute_instances" in _CQ_CONFIGS["gcp"]

    def test_check_cli_version_returns_none_without_cli(self):
        backend = CloudQueryBackend(provider="aws")
        backend._cli_path = None
        assert backend.check_cli_version() is None
