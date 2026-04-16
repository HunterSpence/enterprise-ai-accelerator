"""
OCI credential helper for Enterprise AI Accelerator.

Priority order:
  1. Explicit constructor kwargs
  2. Environment variables: OCI_TENANCY_ID, OCI_USER_ID, OCI_FINGERPRINT,
     OCI_KEY_FILE, OCI_REGION
  3. ~/.oci/config DEFAULT profile (when oci SDK is installed)
  4. mock=True for demo / CI runs
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OCICredentials:
    tenancy_id: str = field(default="", repr=False)
    user_id: str = field(default="", repr=False)
    fingerprint: str = field(default="", repr=False)
    key_file: str = field(default="", repr=False)
    region: str = "us-ashburn-1"
    mock: bool = False

    def is_valid(self) -> bool:
        if self.mock:
            return True
        return bool(
            self.tenancy_id
            and self.user_id
            and self.fingerprint
            and self.key_file
            and Path(self.key_file).exists()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "oci",
            "tenancy_id": self.tenancy_id[:12] + "****" if self.tenancy_id else "",
            "user_id": self.user_id[:12] + "****" if self.user_id else "",
            "fingerprint_set": bool(self.fingerprint),
            "key_file": self.key_file,
            "key_file_exists": Path(self.key_file).exists() if self.key_file else False,
            "region": self.region,
            "mock": self.mock,
            "valid": self.is_valid(),
        }

    def to_oci_config(self) -> dict[str, str]:
        """Return dict suitable for passing to OCI SDK client constructors."""
        return {
            "tenancy": self.tenancy_id,
            "user": self.user_id,
            "fingerprint": self.fingerprint,
            "key_file": self.key_file,
            "region": self.region,
        }


_OCI_CONFIG_PATH = Path.home() / ".oci" / "config"


def _load_oci_config_file() -> dict[str, str]:
    """Parse ~/.oci/config [DEFAULT] section without requiring the OCI SDK."""
    if not _OCI_CONFIG_PATH.exists():
        return {}
    result: dict[str, str] = {}
    in_default = False
    with open(_OCI_CONFIG_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("[DEFAULT]"):
                in_default = True
                continue
            if line.startswith("[") and in_default:
                break
            if in_default and "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def get_oci_credentials(
    tenancy_id: str | None = None,
    user_id: str | None = None,
    fingerprint: str | None = None,
    key_file: str | None = None,
    region: str | None = None,
    *,
    mock: bool = False,
) -> OCICredentials:
    """Load OCI credentials from kwargs → env vars → ~/.oci/config."""
    if mock:
        return OCICredentials(mock=True, region=region or "us-ashburn-1")

    # Check env vars first, then fall back to config file
    file_config = _load_oci_config_file()

    return OCICredentials(
        tenancy_id=tenancy_id or os.environ.get("OCI_TENANCY_ID") or file_config.get("tenancy", ""),
        user_id=user_id or os.environ.get("OCI_USER_ID") or file_config.get("user", ""),
        fingerprint=fingerprint or os.environ.get("OCI_FINGERPRINT") or file_config.get("fingerprint", ""),
        key_file=key_file or os.environ.get("OCI_KEY_FILE") or file_config.get("key_file", ""),
        region=region or os.environ.get("OCI_REGION") or file_config.get("region", "us-ashburn-1"),
        mock=False,
    )
