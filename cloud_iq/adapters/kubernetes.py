"""
cloud_iq/adapters/kubernetes.py
================================

KubernetesAdapter — discovers workloads from any Kubernetes cluster.

Credential chain:
  1. In-cluster:   KUBERNETES_SERVICE_HOST + KUBERNETES_SERVICE_PORT (pod-mounted SA token)
  2. kubeconfig:   KUBECONFIG env var or ~/.kube/config (standard kubectl config)
  3. Explicit:     K8S_API_SERVER + K8S_TOKEN env vars (service account token auth)

Optional env vars:
  K8S_CONTEXT           — kubeconfig context to use (falls back to current-context)
  K8S_CPU_COST_PER_HOUR — USD per vCPU-hour (default: 0.048, approx GKE preemptible)
  K8S_RAM_COST_PER_HOUR — USD per GB-RAM-hour (default: 0.006)
  K8S_NAMESPACES        — comma-separated list of namespaces to scan (default: all)

Cost estimation formula (per workload per month):
  cpu_cost  = sum(requested_vcpu)  * K8S_CPU_COST_PER_HOUR  * 730
  ram_cost  = sum(requested_gb)    * K8S_RAM_COST_PER_HOUR  * 730
  total     = cpu_cost + ram_cost

730 = average hours per month (365 * 24 / 12).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from cloud_iq.adapters.base import DiscoveryAdapter, Workload

logger = logging.getLogger(__name__)

# Cost defaults — customer overrides via env
_DEFAULT_CPU_COST_PER_HOUR = 0.048  # $/vCPU-hour
_DEFAULT_RAM_COST_PER_HOUR = 0.006  # $/GB-RAM-hour
_HOURS_PER_MONTH = 730.0


class KubernetesAdapter(DiscoveryAdapter):
    """
    Discovers Kubernetes workloads (Deployments, StatefulSets, DaemonSets)
    across all (or specified) namespaces, sums resource requests, and
    estimates monthly cost via configurable $/vCPU-hour and $/GB-RAM-hour.

    Requires the 'kubernetes' package (already in requirements.txt >=29.0.0).
    """

    def __init__(
        self,
        context: str | None = None,
        cpu_cost_per_hour: float | None = None,
        ram_cost_per_hour: float | None = None,
        namespaces: list[str] | None = None,
    ) -> None:
        self._context = context or os.environ.get("K8S_CONTEXT")
        self._cpu_cost = cpu_cost_per_hour or float(
            os.environ.get("K8S_CPU_COST_PER_HOUR", _DEFAULT_CPU_COST_PER_HOUR)
        )
        self._ram_cost = ram_cost_per_hour or float(
            os.environ.get("K8S_RAM_COST_PER_HOUR", _DEFAULT_RAM_COST_PER_HOUR)
        )
        env_ns = os.environ.get("K8S_NAMESPACES", "")
        self._namespaces: list[str] | None = (
            namespaces
            or ([n.strip() for n in env_ns.split(",") if n.strip()] or None)
        )

    # ------------------------------------------------------------------
    # DiscoveryAdapter interface
    # ------------------------------------------------------------------

    @property
    def cloud_name(self) -> str:
        return "k8s"

    @staticmethod
    def is_configured() -> bool:
        """True if in-cluster env or kubeconfig is present."""
        in_cluster = bool(
            os.environ.get("KUBERNETES_SERVICE_HOST")
            and os.environ.get("KUBERNETES_SERVICE_PORT")
        )
        kubeconfig = bool(
            os.environ.get("KUBECONFIG")
            or os.path.isfile(os.path.expanduser("~/.kube/config"))
        )
        explicit = bool(os.environ.get("K8S_API_SERVER") and os.environ.get("K8S_TOKEN"))
        return in_cluster or kubeconfig or explicit

    async def discover_workloads(self) -> list[Workload]:
        return await asyncio.to_thread(self._discover_sync)

    # ------------------------------------------------------------------
    # Sync discovery (runs in thread)
    # ------------------------------------------------------------------

    def _discover_sync(self) -> list[Workload]:
        try:
            from kubernetes import client as k8s_client, config as k8s_config
        except ImportError as exc:
            logger.warning(
                "k8s_sdk_not_installed missing=%s — pip install kubernetes", exc
            )
            return []

        # Load config
        try:
            if os.environ.get("KUBERNETES_SERVICE_HOST"):
                k8s_config.load_incluster_config()
            elif os.environ.get("K8S_API_SERVER") and os.environ.get("K8S_TOKEN"):
                configuration = k8s_client.Configuration()
                configuration.host = os.environ["K8S_API_SERVER"]
                configuration.api_key = {"authorization": f"Bearer {os.environ['K8S_TOKEN']}"}
                configuration.verify_ssl = os.environ.get("K8S_VERIFY_SSL", "true").lower() == "true"
                k8s_client.Configuration.set_default(configuration)
            else:
                k8s_config.load_kube_config(context=self._context)
        except Exception as exc:
            logger.warning("k8s_config_load_error error=%s", exc)
            return []

        apps_v1 = k8s_client.AppsV1Api()
        namespaces = self._get_namespaces(k8s_client)
        now = datetime.now(timezone.utc)
        workloads: list[Workload] = []

        for ns in namespaces:
            for wl in self._collect_deployments(apps_v1, ns, now):
                workloads.append(wl)
            for wl in self._collect_statefulsets(apps_v1, ns, now):
                workloads.append(wl)
            for wl in self._collect_daemonsets(apps_v1, ns, now):
                workloads.append(wl)

        return workloads

    def _get_namespaces(self, k8s_client: Any) -> list[str]:
        if self._namespaces:
            return self._namespaces
        try:
            core_v1 = k8s_client.CoreV1Api()
            ns_list = core_v1.list_namespace()
            return [ns.metadata.name for ns in ns_list.items]
        except Exception as exc:
            logger.warning("k8s_list_namespaces_error error=%s", exc)
            return ["default"]

    def _collect_deployments(
        self, apps_v1: Any, namespace: str, now: datetime
    ) -> list[Workload]:
        workloads: list[Workload] = []
        try:
            items = apps_v1.list_namespaced_deployment(namespace=namespace).items
            for deploy in items:
                meta = deploy.metadata
                spec = deploy.spec
                replicas = spec.replicas or 1
                cpu, mem = _sum_container_requests(spec.template.spec.containers or [])
                total_cpu = cpu * replicas
                total_mem = mem * replicas
                cost = self._estimate_cost(total_cpu, total_mem)
                workloads.append(Workload(
                    id=f"k8s:deployment:{namespace}/{meta.name}",
                    name=meta.name,
                    cloud="k8s",
                    service_type="Deployment",
                    region=_cluster_region(),
                    tags=dict(meta.labels or {}),
                    monthly_cost_usd=cost,
                    cpu_cores=total_cpu,
                    memory_gb=total_mem,
                    last_seen=now,
                    metadata={
                        "namespace": namespace,
                        "replicas": replicas,
                        "ready_replicas": deploy.status.ready_replicas or 0,
                        "image": _first_image(spec.template.spec.containers),
                        "annotations": dict(meta.annotations or {}),
                    },
                ))
        except Exception as exc:
            logger.warning("k8s_list_deployments_error namespace=%s error=%s", namespace, exc)
        return workloads

    def _collect_statefulsets(
        self, apps_v1: Any, namespace: str, now: datetime
    ) -> list[Workload]:
        workloads: list[Workload] = []
        try:
            items = apps_v1.list_namespaced_stateful_set(namespace=namespace).items
            for sts in items:
                meta = sts.metadata
                spec = sts.spec
                replicas = spec.replicas or 1
                cpu, mem = _sum_container_requests(spec.template.spec.containers or [])
                total_cpu = cpu * replicas
                total_mem = mem * replicas
                # Storage: volumeClaimTemplates
                storage_gb = 0.0
                for vct in spec.volume_claim_templates or []:
                    res = (vct.spec.resources or {})
                    requests = getattr(res, "requests", None) or {}
                    storage_str = requests.get("storage", "0Gi")
                    storage_gb += _parse_quantity_gb(storage_str) * replicas
                cost = self._estimate_cost(total_cpu, total_mem)
                workloads.append(Workload(
                    id=f"k8s:statefulset:{namespace}/{meta.name}",
                    name=meta.name,
                    cloud="k8s",
                    service_type="StatefulSet",
                    region=_cluster_region(),
                    tags=dict(meta.labels or {}),
                    monthly_cost_usd=cost,
                    cpu_cores=total_cpu,
                    memory_gb=total_mem,
                    storage_gb=storage_gb,
                    last_seen=now,
                    metadata={
                        "namespace": namespace,
                        "replicas": replicas,
                        "ready_replicas": sts.status.ready_replicas or 0,
                        "image": _first_image(spec.template.spec.containers),
                    },
                ))
        except Exception as exc:
            logger.warning("k8s_list_statefulsets_error namespace=%s error=%s", namespace, exc)
        return workloads

    def _collect_daemonsets(
        self, apps_v1: Any, namespace: str, now: datetime
    ) -> list[Workload]:
        workloads: list[Workload] = []
        try:
            items = apps_v1.list_namespaced_daemon_set(namespace=namespace).items
            for ds in items:
                meta = ds.metadata
                spec = ds.spec
                node_count = ds.status.desired_number_scheduled or 1
                cpu, mem = _sum_container_requests(spec.template.spec.containers or [])
                total_cpu = cpu * node_count
                total_mem = mem * node_count
                cost = self._estimate_cost(total_cpu, total_mem)
                workloads.append(Workload(
                    id=f"k8s:daemonset:{namespace}/{meta.name}",
                    name=meta.name,
                    cloud="k8s",
                    service_type="DaemonSet",
                    region=_cluster_region(),
                    tags=dict(meta.labels or {}),
                    monthly_cost_usd=cost,
                    cpu_cores=total_cpu,
                    memory_gb=total_mem,
                    last_seen=now,
                    metadata={
                        "namespace": namespace,
                        "desired_nodes": node_count,
                        "ready_nodes": ds.status.number_ready or 0,
                        "image": _first_image(spec.template.spec.containers),
                    },
                ))
        except Exception as exc:
            logger.warning("k8s_list_daemonsets_error namespace=%s error=%s", namespace, exc)
        return workloads

    def _estimate_cost(self, cpu_cores: int, memory_gb: float) -> float:
        """Monthly cost estimate based on resource requests."""
        cpu_cost = cpu_cores * self._cpu_cost * _HOURS_PER_MONTH
        ram_cost = memory_gb * self._ram_cost * _HOURS_PER_MONTH
        return round(cpu_cost + ram_cost, 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sum_container_requests(containers: list[Any]) -> tuple[int, float]:
    """Sum CPU (cores) and memory (GB) requests across containers."""
    total_cpu = 0
    total_mem = 0.0
    for container in containers:
        res = getattr(container, "resources", None)
        if not res:
            continue
        requests = getattr(res, "requests", None) or {}
        cpu_str = requests.get("cpu", "0")
        mem_str = requests.get("memory", "0")
        total_cpu += _parse_quantity_cpu(cpu_str)
        total_mem += _parse_quantity_gb(mem_str)
    return total_cpu, total_mem


def _parse_quantity_cpu(q: str) -> int:
    """Parse Kubernetes CPU quantity to whole core count (ceil).
    "500m" → 1, "2" → 2, "2.5" → 3.
    """
    if not q:
        return 0
    q = str(q).strip()
    if q.endswith("m"):
        millicores = float(q[:-1])
        import math
        return max(1, math.ceil(millicores / 1000))
    try:
        return max(1, round(float(q)))
    except ValueError:
        return 0


def _parse_quantity_gb(q: str) -> float:
    """Parse Kubernetes memory quantity to GB.
    "512Mi" → 0.5, "4Gi" → 4.0, "8G" → 8.0, "1073741824" → 1.0.
    """
    if not q:
        return 0.0
    q = str(q).strip()
    suffixes = {
        "Ki": 1 / (1024 ** 2),
        "Mi": 1 / 1024,
        "Gi": 1.0,
        "Ti": 1024.0,
        "K": 1 / (1000 ** 2),
        "M": 1 / 1000,
        "G": 1.0,
        "T": 1000.0,
    }
    for suffix, factor in suffixes.items():
        if q.endswith(suffix):
            try:
                return float(q[: -len(suffix)]) * factor
            except ValueError:
                return 0.0
    try:
        # Raw bytes
        return float(q) / (1024 ** 3)
    except ValueError:
        return 0.0


def _cluster_region() -> str:
    """Best-effort region from env; falls back to 'in-cluster'."""
    return (
        os.environ.get("CLUSTER_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("GOOGLE_CLOUD_REGION")
        or "in-cluster"
    )


def _first_image(containers: list[Any]) -> str:
    """Return the image of the first container, or empty string."""
    if not containers:
        return ""
    return getattr(containers[0], "image", "") or ""
