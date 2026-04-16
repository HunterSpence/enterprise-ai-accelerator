"""
Enterprise AI Accelerator — Unified Cloud Configuration
=========================================================
Single source of truth for cloud provider selection across all modules.

Usage
-----
From environment variables (auto-detect):
    config = CloudConfig.from_env()
    print(config.source_cloud, config.target_cloud)

Explicit:
    config = CloudConfig(
        source_cloud=CloudProvider.AWS,
        target_cloud=CloudProvider.AZURE,
        aws_region="us-east-1",
        azure_subscription_id="...",
    )

CLI flag parsing:
    config = CloudConfig.from_args(source="gcp", target="oci")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CloudProvider(str, Enum):
    """Supported cloud providers."""

    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"

    @classmethod
    def from_str(cls, value: str) -> "CloudProvider":
        """Case-insensitive lookup. Accepts 'amazon', 'az', 'google', 'oracle' aliases."""
        _aliases: dict[str, str] = {
            "amazon": "aws",
            "amazon web services": "aws",
            "az": "azure",
            "microsoft": "azure",
            "microsoft azure": "azure",
            "google": "gcp",
            "google cloud": "gcp",
            "oracle": "oci",
            "oracle cloud": "oci",
        }
        normalised = _aliases.get(value.lower().strip(), value.lower().strip())
        try:
            return cls(normalised)
        except ValueError:
            valid = ", ".join(c.value for c in cls)
            raise ValueError(
                f"Unknown cloud provider: '{value}'. Valid values: {valid}"
            ) from None

    def display_name(self) -> str:
        return {
            CloudProvider.AWS: "Amazon Web Services (AWS)",
            CloudProvider.AZURE: "Microsoft Azure",
            CloudProvider.GCP: "Google Cloud Platform (GCP)",
            CloudProvider.OCI: "Oracle Cloud Infrastructure (OCI)",
        }[self]


# ---------------------------------------------------------------------------
# Per-provider credential field names
# ---------------------------------------------------------------------------

_PROVIDER_ENV_KEYS: dict[CloudProvider, list[str]] = {
    CloudProvider.AWS: [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "AWS_SESSION_TOKEN",       # optional (for assumed roles)
        "AWS_PROFILE",             # optional (named profile)
    ],
    CloudProvider.AZURE: [
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_RESOURCE_GROUP",    # optional scope filter
    ],
    CloudProvider.GCP: [
        "GOOGLE_APPLICATION_CREDENTIALS",  # path to SA key JSON
        "GCP_PROJECT_ID",
        "GCP_BILLING_ACCOUNT_ID",          # optional for cost data
        "GOOGLE_CLOUD_PROJECT",            # alias honoured by gcloud SDK
    ],
    CloudProvider.OCI: [
        "OCI_TENANCY_ID",
        "OCI_USER_ID",
        "OCI_FINGERPRINT",
        "OCI_KEY_FILE",
        "OCI_REGION",
    ],
}

_REQUIRED_KEYS: dict[CloudProvider, list[str]] = {
    CloudProvider.AWS: ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    CloudProvider.AZURE: ["AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"],
    CloudProvider.GCP: ["GOOGLE_APPLICATION_CREDENTIALS", "GCP_PROJECT_ID"],
    CloudProvider.OCI: ["OCI_TENANCY_ID", "OCI_USER_ID", "OCI_FINGERPRINT", "OCI_KEY_FILE"],
}


@dataclass
class CloudConfig:
    """
    Unified cloud configuration for all Enterprise AI Accelerator modules.

    Attributes
    ----------
    source_cloud:
        The cloud being assessed/migrated FROM. Used by CloudIQ scanner,
        MigrationScout, and FinOps Intelligence.
    target_cloud:
        The cloud being migrated TO. Used by CrossCloudMigrationPlanner.
        None means single-cloud assessment (no migration planned).
    """

    source_cloud: CloudProvider = CloudProvider.AWS
    target_cloud: CloudProvider | None = None

    # AWS
    aws_access_key_id: str = field(default="", repr=False)
    aws_secret_access_key: str = field(default="", repr=False)
    aws_region: str = "us-east-1"
    aws_session_token: str = field(default="", repr=False)
    aws_profile: str = ""

    # Azure
    azure_subscription_id: str = ""
    azure_tenant_id: str = field(default="", repr=False)
    azure_client_id: str = field(default="", repr=False)
    azure_client_secret: str = field(default="", repr=False)
    azure_resource_group: str = ""

    # GCP
    gcp_project_id: str = ""
    gcp_billing_account_id: str = ""
    gcp_credentials_file: str = field(default="", repr=False)

    # OCI
    oci_tenancy_id: str = field(default="", repr=False)
    oci_user_id: str = field(default="", repr=False)
    oci_fingerprint: str = field(default="", repr=False)
    oci_key_file: str = field(default="", repr=False)
    oci_region: str = "us-ashburn-1"

    # Shared
    mock_mode: bool = False
    anthropic_api_key: str = field(default="", repr=False)

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "CloudConfig":
        """
        Build config by reading environment variables.

        SOURCE_CLOUD and TARGET_CLOUD env vars control which provider is
        active. Defaults to AWS if not set.
        """
        source = CloudProvider.from_str(
            os.environ.get("SOURCE_CLOUD", "aws")
        )
        target_raw = os.environ.get("TARGET_CLOUD", "")
        target = CloudProvider.from_str(target_raw) if target_raw else None

        return cls(
            source_cloud=source,
            target_cloud=target,
            # AWS
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
            aws_region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            aws_session_token=os.environ.get("AWS_SESSION_TOKEN", ""),
            aws_profile=os.environ.get("AWS_PROFILE", ""),
            # Azure
            azure_subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID", ""),
            azure_tenant_id=os.environ.get("AZURE_TENANT_ID", ""),
            azure_client_id=os.environ.get("AZURE_CLIENT_ID", ""),
            azure_client_secret=os.environ.get("AZURE_CLIENT_SECRET", ""),
            azure_resource_group=os.environ.get("AZURE_RESOURCE_GROUP", ""),
            # GCP
            gcp_project_id=(
                os.environ.get("GCP_PROJECT_ID")
                or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            ),
            gcp_billing_account_id=os.environ.get("GCP_BILLING_ACCOUNT_ID", ""),
            gcp_credentials_file=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
            # OCI
            oci_tenancy_id=os.environ.get("OCI_TENANCY_ID", ""),
            oci_user_id=os.environ.get("OCI_USER_ID", ""),
            oci_fingerprint=os.environ.get("OCI_FINGERPRINT", ""),
            oci_key_file=os.environ.get("OCI_KEY_FILE", ""),
            oci_region=os.environ.get("OCI_REGION", "us-ashburn-1"),
            # Shared
            mock_mode=os.environ.get("MOCK_MODE", "").lower() in ("1", "true", "yes"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    @classmethod
    def from_args(
        cls,
        source: str,
        target: str | None = None,
        mock: bool = False,
    ) -> "CloudConfig":
        """Build config from CLI argument strings."""
        base = cls.from_env()
        base.source_cloud = CloudProvider.from_str(source)
        base.target_cloud = CloudProvider.from_str(target) if target else None
        if mock:
            base.mock_mode = True
        return base

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def credentials_present(self, provider: CloudProvider) -> bool:
        """
        Return True if the required env vars for `provider` are all non-empty.

        Does not verify the credentials are valid — use the provider's
        authenticate() method for that.
        """
        required = _REQUIRED_KEYS.get(provider, [])
        cred_map: dict[CloudProvider, list[str]] = {
            CloudProvider.AWS: [self.aws_access_key_id, self.aws_secret_access_key],
            CloudProvider.AZURE: [
                self.azure_subscription_id, self.azure_tenant_id,
                self.azure_client_id, self.azure_client_secret,
            ],
            CloudProvider.GCP: [self.gcp_credentials_file, self.gcp_project_id],
            CloudProvider.OCI: [
                self.oci_tenancy_id, self.oci_user_id,
                self.oci_fingerprint, self.oci_key_file,
            ],
        }
        values = cred_map.get(provider, [])
        return all(v for v in values)

    def missing_credentials(self, provider: CloudProvider) -> list[str]:
        """Return list of missing required env var names for the provider."""
        required = _REQUIRED_KEYS.get(provider, [])
        return [k for k in required if not os.environ.get(k)]

    def summary(self) -> dict[str, Any]:
        """Non-sensitive config summary for logging."""
        return {
            "source_cloud": self.source_cloud.value,
            "target_cloud": self.target_cloud.value if self.target_cloud else None,
            "mock_mode": self.mock_mode,
            "credentials_present": {
                p.value: self.credentials_present(p) for p in CloudProvider
            },
        }
