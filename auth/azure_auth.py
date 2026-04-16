"""
Azure credential helper for Enterprise AI Accelerator.

Service Principal authentication (recommended for automation):
  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET

Optional for scope:
  AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP

For interactive/CLI auth the azure-identity DefaultAzureCredential chain
is also supported when the above env vars are absent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AzureCredentials:
    subscription_id: str = ""
    tenant_id: str = field(default="", repr=False)
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)
    resource_group: str = ""
    mock: bool = False

    def is_valid(self) -> bool:
        if self.mock:
            return True
        return bool(
            self.subscription_id
            and self.tenant_id
            and self.client_id
            and self.client_secret
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "azure",
            "subscription_id": self.subscription_id,
            "tenant_id": self.tenant_id[:8] + "****" if self.tenant_id else "",
            "client_id": self.client_id[:8] + "****" if self.client_id else "",
            "resource_group": self.resource_group,
            "mock": self.mock,
            "valid": self.is_valid(),
        }

    def to_azure_sdk_kwargs(self) -> dict[str, str]:
        """Return kwargs for azure-identity ClientSecretCredential."""
        return {
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }


def get_azure_credentials(
    subscription_id: str | None = None,
    tenant_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    resource_group: str | None = None,
    *,
    mock: bool = False,
) -> AzureCredentials:
    """Load Azure credentials from kwargs → env vars."""
    if mock:
        return AzureCredentials(mock=True)

    return AzureCredentials(
        subscription_id=subscription_id or os.environ.get("AZURE_SUBSCRIPTION_ID", ""),
        tenant_id=tenant_id or os.environ.get("AZURE_TENANT_ID", ""),
        client_id=client_id or os.environ.get("AZURE_CLIENT_ID", ""),
        client_secret=client_secret or os.environ.get("AZURE_CLIENT_SECRET", ""),
        resource_group=resource_group or os.environ.get("AZURE_RESOURCE_GROUP", ""),
        mock=False,
    )
