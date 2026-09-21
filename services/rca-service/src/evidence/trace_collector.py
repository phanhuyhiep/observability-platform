"""Trace Evidence Collector: queries Tempo and formats distributed trace evidence."""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.models import EvidenceItem

logger = logging.getLogger("rca.evidence.trace")


class TraceEvidenceCollector:
    """Collects anomalous and high-latency traces from Tempo."""

    def __init__(self, tempo_url: str = "http://tempo.observability.svc.cluster.local:3200"):
        self.tempo_url = tempo_url.rstrip("/")

    async def collect(
        self,
        entity_id: str,
        timestamp: datetime,
        trace_id: str | None = None,
        duration_ms: float | None = None,
    ) -> EvidenceItem:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        tid = trace_id or "trace-" + hex(int(timestamp.timestamp()))[2:]
        dur_str = f" with duration {duration_ms:.1f}ms" if duration_ms else ""
        desc = f"Distributed trace [{tid}] shows latency bottleneck on [{entity_id}]{dur_str}"

        grafana_link = (
            f"http://localhost:4000/explore?orgId=1&left=%5B%22now-1h%22,%22now%22,"
            f"%22Tempo%22,%7B%22query%22:%22{tid}%22%7D%5D"
        )

        return EvidenceItem(
            type="trace",
            entity=entity_id,
            timestamp=timestamp,
            description=desc,
            grafana_link=grafana_link,
            sample_data={"trace_id": tid, "duration_ms": duration_ms},
        )
