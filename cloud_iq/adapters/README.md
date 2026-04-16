# cloud_iq/adapters — Multi-Cloud Discovery

Real multi-cloud asset discovery for AWS, Azure, GCP, and Kubernetes via their native SDKs. Each adapter is independent; `UnifiedDiscovery` combines them with graceful degradation when credentials are absent.

---

## Architecture

```
UnifiedDiscovery.auto()
        |
        ├── AWSAdapter      (boto3)
        ├── AzureAdapter    (azure-mgmt-compute + azure-mgmt-resource)
        ├── GCPAdapter      (google-cloud-compute)
        └── KubernetesAdapter (kubernetes Python client)
```

Each adapter inherits from `CloudAdapterBase` (`base.py`) and implements:
- `probe()` — returns `True` if credentials are present and valid
- `discover()` — returns a list of `CloudAsset` objects

`UnifiedDiscovery.auto()` calls `probe()` on each adapter and skips any that return `False`, so partial credential sets work without error.

---

## Env Vars by Cloud

### AWS
```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN      # (optional — for assumed roles)
AWS_DEFAULT_REGION     # defaults to us-east-1 if unset
```

Or use a configured AWS profile via `~/.aws/credentials`. The adapter calls `boto3.Session()` and checks STS caller identity to validate credentials before discovery.

### Azure
```
AZURE_TENANT_ID
AZURE_CLIENT_ID
AZURE_CLIENT_SECRET
AZURE_SUBSCRIPTION_ID
```

Uses `azure.identity.ClientSecretCredential`. If `AZURE_SUBSCRIPTION_ID` is unset, the adapter attempts to list subscriptions and uses all available.

### GCP
```
GOOGLE_APPLICATION_CREDENTIALS   # path to service account JSON
GOOGLE_CLOUD_PROJECT              # project ID
```

Or use Application Default Credentials (`gcloud auth application-default login`). The adapter calls the Compute Engine API with the `compute.instances.aggregatedList` scope.

### Kubernetes
```
KUBECONFIG                        # path to kubeconfig (defaults to ~/.kube/config)
```

Or run inside a pod — the adapter falls back to in-cluster config (`kubernetes.config.load_incluster_config()`). Discovers pods, deployments, services, and nodes across all namespaces.

---

## Graceful Degradation

If no credentials are configured for a cloud, `UnifiedDiscovery.auto()` logs a warning and continues. It never raises an exception for missing credentials — it simply excludes that adapter from the discovery run.

```python
from cloud_iq.adapters.unified import UnifiedDiscovery

# Discovers from whichever clouds have credentials configured
discovery = UnifiedDiscovery.auto()
assets = discovery.discover()

for asset in assets:
    print(asset.provider, asset.resource_type, asset.resource_id, asset.region)
```

---

## Adding a New Cloud Adapter

1. Create `cloud_iq/adapters/<provider>.py`
2. Inherit from `CloudAdapterBase`
3. Implement `probe() -> bool` and `discover() -> list[CloudAsset]`
4. Register the adapter in `unified.py` `_ADAPTER_CLASSES` list

```python
# cloud_iq/adapters/mycloud.py
from cloud_iq.adapters.base import CloudAdapterBase, CloudAsset

class MyCloudAdapter(CloudAdapterBase):
    def probe(self) -> bool:
        return bool(os.environ.get("MYCLOUD_API_KEY"))

    def discover(self) -> list[CloudAsset]:
        # call your SDK here
        return [CloudAsset(provider="mycloud", resource_type="vm", ...)]
```

---

## Output Schema

Each `CloudAsset` has:

| Field | Type | Description |
|---|---|---|
| `provider` | str | `aws`, `azure`, `gcp`, `kubernetes` |
| `resource_type` | str | e.g. `ec2_instance`, `virtual_machine`, `gce_instance`, `pod` |
| `resource_id` | str | Native resource ID / name |
| `region` | str | Cloud region or k8s namespace |
| `metadata` | dict | Provider-specific fields (instance type, tags, status, etc.) |

---

## Demo (no credentials required)

`cloud_iq.demo` generates a synthetic asset inventory if no credentials are present. To run against real clouds, set the env vars above and call:

```bash
python -c "
from cloud_iq.adapters.unified import UnifiedDiscovery
d = UnifiedDiscovery.auto()
assets = d.discover()
print(f'{len(assets)} assets discovered across {len(d.active_adapters)} providers')
"
```
