"""
GCP credential helper for Enterprise AI Accelerator.

Service Account key file (recommended for automation):
  GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
  GCP_PROJECT_ID=my-project-id

Optional:
  GCP_BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX  (for billing export access)
  GOOGLE_CLOUD_PROJECT  (alias honoured by gcloud SDK)

Application Default Credentials (ADC) are used as a fallback when
GOOGLE_APPLICATION_CREDENTIALS is not set (e.g., gcloud auth login).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GCPCredentials:
    project_id: str = ""
    billing_account_id: str = ""
    credentials_file: str = field(default="", repr=False)
    mock: bool = False

    def is_valid(self) -> bool:
        if self.mock:
            return True
        return bool(self.project_id and (self.credentials_file or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "gcp",
            "project_id": self.project_id,
            "billing_account_id": self.billing_account_id,
            "credentials_file_set": bool(self.credentials_file),
            "adc_available": os.path.exists(
                os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
            ),
            "mock": self.mock,
            "valid": self.is_valid(),
        }


def get_gcp_credentials(
    project_id: str | None = None,
    billing_account_id: str | None = None,
    credentials_file: str | None = None,
    *,
    mock: bool = False,
) -> GCPCredentials:
    """Load GCP credentials from kwargs → env vars."""
    if mock:
        return GCPCredentials(mock=True, project_id=project_id or "demo-project")

    return GCPCredentials(
        project_id=(
            project_id
            or os.environ.get("GCP_PROJECT_ID")
            or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        ),
        billing_account_id=billing_account_id or os.environ.get("GCP_BILLING_ACCOUNT_ID", ""),
        credentials_file=credentials_file or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
        mock=False,
    )
