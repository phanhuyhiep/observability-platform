"""Log Evidence Collector: queries Loki and formats error/exception log evidence."""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.models import EvidenceItem

logger = logging.getLogger("rca.evidence.log")


class LogEvidenceCollector:
    """Collects error logs and stack traces from Loki."""

    def __init__(self, loki_url: str = "http://loki.observability.svc.cluster.local:3100"):
        self.loki_url = loki_url.rstrip("/")

    async def collect(
        self,
        entity_id: str,
        timestamp: datetime,
        error_sample: str | None = None,
    ) -> EvidenceItem:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        grafana_link = (
            f"http://localhost:4000/explore?orgId=1&left=%5B%22now-1h%22,%22now%22,"
            f"%22Loki%22,%7B%22expr%22:%22%7Bapp=%5C%22{entity_id}%5C%22%7D%20%7C=%20%5C%22error%5C%22%22%7D%5D"
        )

        sample_logs = []
        if error_sample:
            sample_logs.append(error_sample)

        # Attempt to query Loki for error logs
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                query_url = f"{self.loki_url}/loki/api/v1/query"
                logql = f'{{app="{entity_id}"}} |= "error"'
                res = await client.get(query_url, params={"query": logql, "limit": 3})
                if res.status_code == 200:
                    data = res.json().get("data", {})
                    for result in data.get("result", []):
                        for val in result.get("values", []):
                            if len(val) >= 2:
                                sample_logs.append(val[1])
        except Exception:
            pass

        if not sample_logs:
            sample_logs.append(f"High error rate detected in logs for [{entity_id}]")

        desc = f"Error log pattern detected for [{entity_id}]: {sample_logs[0][:120]}"

        return EvidenceItem(
            type="log",
            entity=entity_id,
            timestamp=timestamp,
            description=desc,
            grafana_link=grafana_link,
            sample_data={"logs": sample_logs[:3]},
        )
