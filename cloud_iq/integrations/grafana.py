"""
CloudIQ V2 — Grafana integration.

Pushes cost metrics to Grafana via two channels:
1. Prometheus Pushgateway — for cost KPIs and anomaly scores
2. Grafana Loki — for structured log events (anomaly alerts, scan completions)

This enables CloudIQ findings to appear in Grafana dashboards alongside
infrastructure metrics, giving engineers a single-pane-of-glass view.

Pushgateway format:
    # HELP cloudiq_monthly_cost_usd Monthly cloud spend in USD
    # TYPE cloudiq_monthly_cost_usd gauge
    cloudiq_monthly_cost_usd{account="123456789012",provider="aws"} 154200.00

Loki log push:
    POST http://loki:3100/loki/api/v1/push
    Body: { "streams": [{ "stream": {...labels}, "values": [[ts_ns, line]] }] }

Usage:
    pusher = GrafanaMetricsPusher(
        pushgateway_url="http://prometheus-pushgateway:9091",
        loki_url="http://loki:3100",
    )
    await pusher.push_cost_metrics(account_id="123456789012", monthly_cost=154200)
    await pusher.push_anomaly_log(alert)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from cloud_iq.models import AnomalyAlert

logger = logging.getLogger(__name__)


class GrafanaMetricsPusher:
    """
    Pushes CloudIQ metrics and logs to Grafana Prometheus Pushgateway and Loki.

    All methods are async and non-blocking. Failures are logged and swallowed
    so that Grafana unavailability never blocks CloudIQ operations.
    """

    def __init__(
        self,
        pushgateway_url: str | None = None,
        loki_url: str | None = None,
        job_name: str = "cloudiq",
        dry_run: bool = False,
    ) -> None:
        self._pushgateway_url = pushgateway_url
        self._loki_url = loki_url
        self._job_name = job_name
        self._dry_run = dry_run

    async def push_cost_metrics(
        self,
        account_id: str,
        provider: str,
        monthly_cost_usd: float,
        waste_usd: float,
        anomaly_count: int,
        resource_count: int,
    ) -> bool:
        """
        Push cost KPI metrics to Prometheus Pushgateway.

        Metric names follow the Prometheus naming convention:
        cloudiq_<metric>_<unit>
        """
        if not self._pushgateway_url:
            return False

        labels = f'account="{account_id}",provider="{provider}"'

        lines = [
            "# HELP cloudiq_monthly_cost_usd Estimated monthly cloud spend in USD",
            "# TYPE cloudiq_monthly_cost_usd gauge",
            f"cloudiq_monthly_cost_usd{{{labels}}} {monthly_cost_usd:.2f}",
            "# HELP cloudiq_waste_usd Identified monthly waste in USD",
            "# TYPE cloudiq_waste_usd gauge",
            f"cloudiq_waste_usd{{{labels}}} {waste_usd:.2f}",
            "# HELP cloudiq_waste_ratio Waste as a fraction of total spend",
            "# TYPE cloudiq_waste_ratio gauge",
            f"cloudiq_waste_ratio{{{labels}}} {waste_usd / monthly_cost_usd if monthly_cost_usd else 0:.4f}",
            "# HELP cloudiq_anomaly_count Total active anomaly alerts",
            "# TYPE cloudiq_anomaly_count gauge",
            f"cloudiq_anomaly_count{{{labels}}} {anomaly_count}",
            "# HELP cloudiq_resource_count Total billable resources tracked",
            "# TYPE cloudiq_resource_count gauge",
            f"cloudiq_resource_count{{{labels}}} {resource_count}",
            "# HELP cloudiq_scan_timestamp_seconds Unix timestamp of last successful scan",
            "# TYPE cloudiq_scan_timestamp_seconds gauge",
            f"cloudiq_scan_timestamp_seconds{{{labels}}} {time.time():.0f}",
        ]

        body = "\n".join(lines) + "\n"
        return await self._push_prometheus(body, account_id)

    async def push_anomaly_metrics(self, alerts: list[AnomalyAlert]) -> bool:
        """
        Push per-anomaly gauge metrics for active alerts.

        Creates one metric series per alert so Grafana alerting rules can
        fire on individual resource anomaly scores.
        """
        if not self._pushgateway_url or not alerts:
            return False

        lines: list[str] = [
            "# HELP cloudiq_anomaly_score ML anomaly score 0-1 for each resource",
            "# TYPE cloudiq_anomaly_score gauge",
        ]

        for alert in alerts:
            labels = (
                f'alert_id="{alert.alert_id}",'
                f'resource_id="{alert.resource_id}",'
                f'resource_type="{alert.resource_type.replace(" ", "_")}",'
                f'region="{alert.region}",'
                f'severity="{alert.severity.value}"'
            )
            lines.append(f"cloudiq_anomaly_score{{{labels}}} {alert.anomaly_score:.4f}")

        lines += [
            "# HELP cloudiq_anomaly_cost_usd Monthly cost impact of anomalous resources",
            "# TYPE cloudiq_anomaly_cost_usd gauge",
        ]
        for alert in alerts:
            labels = (
                f'alert_id="{alert.alert_id}",'
                f'resource_id="{alert.resource_id}",'
                f'severity="{alert.severity.value}"'
            )
            lines.append(f"cloudiq_anomaly_cost_usd{{{labels}}} {alert.cost_impact_usd:.2f}")

        body = "\n".join(lines) + "\n"
        return await self._push_prometheus(body, "anomalies")

    async def push_anomaly_log(self, alert: AnomalyAlert) -> bool:
        """
        Push a structured anomaly event to Grafana Loki.

        Log line is JSON for easy parsing in Grafana's Explore UI.
        """
        if not self._loki_url:
            return False

        import json

        ts_ns = str(int(alert.detected_at.timestamp() * 1e9))
        log_line = json.dumps(
            {
                "level": alert.severity.value,
                "event": "cost_anomaly_detected",
                "alert_id": alert.alert_id,
                "resource_id": alert.resource_id,
                "resource_type": alert.resource_type,
                "region": alert.region,
                "anomaly_score": alert.anomaly_score,
                "cost_impact_usd": alert.cost_impact_usd,
                "description": alert.description,
                "detected_at": alert.detected_at.isoformat(),
            }
        )

        payload: dict[str, Any] = {
            "streams": [
                {
                    "stream": {
                        "app": "cloudiq",
                        "level": alert.severity.value,
                        "resource_type": alert.resource_type,
                        "region": alert.region,
                    },
                    "values": [[ts_ns, log_line]],
                }
            ]
        }

        return await self._push_loki(payload)

    async def push_scan_complete_log(
        self,
        account_id: str,
        provider: str,
        total_resources: int,
        waste_usd: float,
        duration_seconds: float,
    ) -> bool:
        """Push a scan completion event to Loki for audit trail."""
        if not self._loki_url:
            return False

        import json

        ts_ns = str(int(time.time() * 1e9))
        log_line = json.dumps(
            {
                "level": "info",
                "event": "scan_complete",
                "account_id": account_id,
                "provider": provider,
                "total_resources": total_resources,
                "waste_usd": waste_usd,
                "duration_seconds": round(duration_seconds, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        payload: dict[str, Any] = {
            "streams": [
                {
                    "stream": {
                        "app": "cloudiq",
                        "level": "info",
                        "event_type": "scan_complete",
                        "provider": provider,
                    },
                    "values": [[ts_ns, log_line]],
                }
            ]
        }

        return await self._push_loki(payload)

    async def _push_prometheus(self, body: str, instance: str) -> bool:
        """PUT metrics to Prometheus Pushgateway."""
        if self._dry_run:
            logger.info("grafana_pushgateway_dry_run", instance=instance, lines=body.count("\n"))
            return True

        url = f"{self._pushgateway_url}/metrics/job/{self._job_name}/instance/{instance}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.put(
                    url,
                    content=body.encode("utf-8"),
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
                if response.status_code in (200, 202):
                    return True
                logger.warning("pushgateway_push_failed", status=response.status_code)
                return False
        except Exception as exc:
            logger.error("pushgateway_push_error", error=str(exc))
            return False

    async def _push_loki(self, payload: dict[str, Any]) -> bool:
        """POST log stream to Grafana Loki."""
        if self._dry_run:
            logger.info("grafana_loki_dry_run", streams=len(payload.get("streams", [])))
            return True

        url = f"{self._loki_url}/loki/api/v1/push"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code in (200, 204):
                    return True
                logger.warning("loki_push_failed", status=response.status_code)
                return False
        except Exception as exc:
            logger.error("loki_push_error", error=str(exc))
            return False
