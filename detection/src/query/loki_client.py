"""Loki query client for Detection Service."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LokiClient:
    """Client for querying Loki via HTTP API."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Execute a LogQL range query."""
        params = {
            "query": query,
            "start": str(int(start.timestamp() * 1e9)),  # nanoseconds
            "end": str(int(end.timestamp() * 1e9)),
            "limit": limit,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            logger.error("Loki query failed: %s", data)
            return []

        return data.get("data", {}).get("result", [])

    async def get_error_count(
        self,
        service: str,
        namespace: str = "default",
        window_minutes: int = 5,
    ) -> int:
        """Count error-level log entries for a service in the given time window."""
        end = datetime.utcnow()
        start = end - timedelta(minutes=window_minutes)

        # LogQL: count errors by service label
        query = (
            f'count_over_time({{namespace="{namespace}", app="{service}"}} '
            f'|= "error" [{window_minutes}m])'
        )

        results = await self.query_range(query, start, end)

        total = 0
        for result in results:
            for _ts, val in result.get("values", []):
                try:
                    total += int(float(val))
                except (ValueError, TypeError):
                    continue
        return total

    async def get_log_burst_rate(
        self,
        service: str,
        namespace: str = "default",
        window_minutes: int = 5,
    ) -> float:
        """Calculate log burst rate (logs per second) for a service."""
        end = datetime.utcnow()
        start = end - timedelta(minutes=window_minutes)

        query = (
            f'rate({{namespace="{namespace}", app="{service}"}}[{window_minutes}m])'
        )

        results = await self.query_range(query, start, end)

        rates: list[float] = []
        for result in results:
            for _ts, val in result.get("values", []):
                try:
                    rates.append(float(val))
                except (ValueError, TypeError):
                    continue

        return max(rates) if rates else 0.0
