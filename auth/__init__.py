"""
Enterprise AI Accelerator — Authentication helpers.

Factory function that returns a normalised credentials dict for any of the
four supported cloud providers. Each helper validates that required fields
are present and optionally performs a live connectivity test.

Usage
-----
    from auth import get_provider_credentials
    creds = get_provider_credentials("aws")   # reads AWS_* env vars
    creds = get_provider_credentials("azure")  # reads AZURE_* env vars
    creds = get_provider_credentials("gcp")    # reads GOOGLE_* env vars
    creds = get_provider_credentials("oci")    # reads OCI_* env vars
"""

from __future__ import annotations

from auth.aws_auth import AWSCredentials, get_aws_credentials
from auth.azure_auth import AzureCredentials, get_azure_credentials
from auth.gcp_auth import GCPCredentials, get_gcp_credentials
from auth.oci_auth import OCICredentials, get_oci_credentials
from cloud_config import CloudProvider


def get_provider_credentials(
    provider: str | CloudProvider,
    mock: bool = False,
) -> dict:
    """
    Return normalised credentials dict for the given provider.

    Parameters
    ----------
    provider:
        Provider name or CloudProvider enum value.
    mock:
        When True, returns empty/placeholder credentials for demo/CI use.

    Returns
    -------
    dict with provider-specific credential keys. Never contains secrets
    in plaintext — values are masked for logging safety.
    """
    if isinstance(provider, str):
        provider = CloudProvider.from_str(provider)

    if provider == CloudProvider.AWS:
        creds = get_aws_credentials(mock=mock)
        return creds.to_dict()
    elif provider == CloudProvider.AZURE:
        creds = get_azure_credentials(mock=mock)
        return creds.to_dict()
    elif provider == CloudProvider.GCP:
        creds = get_gcp_credentials(mock=mock)
        return creds.to_dict()
    elif provider == CloudProvider.OCI:
        creds = get_oci_credentials(mock=mock)
        return creds.to_dict()
    else:
        raise ValueError(f"Unsupported provider: {provider}")


__all__ = [
    "get_provider_credentials",
    "AWSCredentials",
    "AzureCredentials",
    "GCPCredentials",
    "OCICredentials",
    "get_aws_credentials",
    "get_azure_credentials",
    "get_gcp_credentials",
    "get_oci_credentials",
]
