"""Metric Evidence Collector: queries Prometheus and formats metric evidence."""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.models import EvidenceItem

logger = logging.getLogger("rca.evidence.metric")


class MetricEvidenceCollector:
    """Collects metric deviations and anomalies from Prometheus."""

    def __init__(self, prometheus_url: str = "http://prometheus-kube-prometheus-prometheus.observability.svc.cluster.local:9090"):
        self.prometheus_url = prometheus_url.rstrip("/")

    async def collect(
        self,
        entity_id: str,
        timestamp: datetime,
        signal: str = "request_duration",
        deviation_value: float | None = None,
        baseline_value: float | None = None,
    ) -> EvidenceItem:
        """Create structured metric evidence item, querying Prometheus if reachable."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        grafana_link = (
            f"http://localhost:4000/explore?orgId=1&left=%5B%22now-1h%22,%22now%22,"
            f"%22Prometheus%22,%7B%22expr%22:%22sum(rate(container_cpu_usage_seconds_total%7Bpod=~%5C%22{entity_id}.*%5C%22%7D%5B1m%5D))%22%7D%5D"
        )

        desc = f"Metric [{signal}] on [{entity_id}] anomalous"
        if deviation_value is not None and baseline_value is not None:
            desc = f"Metric [{signal}] jumped from baseline {baseline_value:.3f} to {deviation_value:.3f}"

        # Attempt to query instant metric if alive
        sample_data: dict[str, Any] = {"signal": signal}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                query_url = f"{self.prometheus_url}/api/v1/query"
                res = await client.get(query_url, params={"query": f"up{{job=~'.*{entity_id}.*'}}"})
                if res.status_code == 200:
                    sample_data["prometheus_response"] = res.json().get("data", {})
        except Exception:
            pass  # Fallback to offline evidence

        return EvidenceItem(
            type="metric",
            entity=entity_id,
            timestamp=timestamp,
            signal=signal,
            description=desc,
            grafana_link=grafana_link,
            sample_data=sample_data,
        )
