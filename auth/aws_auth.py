"""
AWS credential helper for Enterprise AI Accelerator.

Priority order (matches AWS SDK default chain):
  1. Explicit constructor kwargs
  2. Environment variables (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
  3. Named profile (~/.aws/credentials)
  4. EC2/ECS/Lambda instance metadata (when running inside AWS)
  5. mock=True — returns placeholder creds for demo/CI
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AWSCredentials:
    access_key_id: str = field(default="", repr=False)
    secret_access_key: str = field(default="", repr=False)
    region: str = "us-east-1"
    session_token: str = field(default="", repr=False)
    profile: str = ""
    mock: bool = False

    def is_valid(self) -> bool:
        if self.mock:
            return True
        return bool(self.access_key_id and self.secret_access_key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "aws",
            "access_key_id": self.access_key_id[:8] + "****" if self.access_key_id else "",
            "region": self.region,
            "profile": self.profile,
            "session_token_present": bool(self.session_token),
            "mock": self.mock,
            "valid": self.is_valid(),
        }

    def to_boto3_kwargs(self) -> dict[str, Any]:
        """Return kwargs suitable for boto3.Session(**kwargs)."""
        kwargs: dict[str, Any] = {"region_name": self.region}
        if self.access_key_id:
            kwargs["aws_access_key_id"] = self.access_key_id
            kwargs["aws_secret_access_key"] = self.secret_access_key
        if self.session_token:
            kwargs["aws_session_token"] = self.session_token
        if self.profile:
            kwargs["profile_name"] = self.profile
        return kwargs


def get_aws_credentials(
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    region: str | None = None,
    session_token: str | None = None,
    profile: str | None = None,
    *,
    mock: bool = False,
) -> AWSCredentials:
    """Load AWS credentials from kwargs → env → profile."""
    if mock:
        return AWSCredentials(mock=True, region=region or "us-east-1")

    return AWSCredentials(
        access_key_id=access_key_id or os.environ.get("AWS_ACCESS_KEY_ID", ""),
        secret_access_key=secret_access_key or os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        region=region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        session_token=session_token or os.environ.get("AWS_SESSION_TOKEN", ""),
        profile=profile or os.environ.get("AWS_PROFILE", ""),
        mock=False,
    )
