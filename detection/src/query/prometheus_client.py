"""Prometheus query client for Detection Service."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Client for querying Prometheus via HTTP API."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def instant_query(self, query: str, time: datetime | None = None) -> list[dict[str, Any]]:
        """Execute an instant PromQL query."""
        params: dict[str, Any] = {"query": query}
        if time:
            params["time"] = time.isoformat()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/api/v1/query", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            logger.error("Prometheus query failed: %s", data)
            return []

        return data.get("data", {}).get("result", [])

    async def range_query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "60s",
    ) -> list[dict[str, Any]]:
        """Execute a range PromQL query."""
        params = {
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": step,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/api/v1/query_range", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            logger.error("Prometheus range query failed: %s", data)
            return []

        return data.get("data", {}).get("result", [])

    async def get_metric_values(
        self,
        query: str,
        window_minutes: int = 5,
    ) -> list[float]:
        """Get metric values for the last N minutes as a flat list of floats."""
        end = datetime.utcnow()
        start = end - timedelta(minutes=window_minutes)
        results = await self.range_query(query, start, end, step="15s")

        values: list[float] = []
        for result in results:
            for _ts, val in result.get("values", []):
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    continue
        return values

    async def get_current_value(self, query: str) -> float | None:
        """Get the current (latest) value for a PromQL query."""
        results = await self.instant_query(query)
        if not results:
            return None
        try:
            return float(results[0]["value"][1])
        except (IndexError, KeyError, ValueError, TypeError):
            return None

    async def discover_services(self, namespace: str = "default") -> list[str]:
        """Discover active services by querying up metric."""
        query = f'up{{namespace="{namespace}"}}'
        results = await self.instant_query(query)

        services = set()
        for r in results:
            svc = r.get("metric", {}).get("service", "")
            if svc:
                services.add(svc)

        # Fallback: discover from kube_deployment_status
        if not services:
            query = f'kube_deployment_status_replicas_available{{namespace="{namespace}"}} > 0'
            results = await self.instant_query(query)
            for r in results:
                deploy = r.get("metric", {}).get("deployment", "")
                if deploy:
                    services.add(deploy)

        return sorted(services)
