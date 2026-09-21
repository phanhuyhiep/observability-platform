"""Evidence Aggregator: coordinates multi-signal evidence collection into a coherent timeline."""

import logging
from datetime import datetime, timezone
from typing import Any

from src.evidence.log_collector import LogEvidenceCollector
from src.evidence.metric_collector import MetricEvidenceCollector
from src.evidence.trace_collector import TraceEvidenceCollector
from src.models import EvidenceItem

logger = logging.getLogger("rca.evidence.aggregator")


class EvidenceAggregator:
    """Aggregates telemetry evidence from metrics, logs, traces, and Kubernetes."""

    def __init__(
        self,
        prometheus_url: str = "http://prometheus-kube-prometheus-prometheus.observability.svc.cluster.local:9090",
        loki_url: str = "http://loki.observability.svc.cluster.local:3100",
        tempo_url: str = "http://tempo.observability.svc.cluster.local:3200",
    ):
        self.metrics = MetricEvidenceCollector(prometheus_url)
        self.logs = LogEvidenceCollector(loki_url)
        self.traces = TraceEvidenceCollector(tempo_url)

    async def aggregate(
        self,
        anomalies: list[dict[str, Any]],
        root_candidate: str | None = None,
    ) -> list[EvidenceItem]:
        """Collect and format corroborating evidence for all anomalies."""
        evidence_list: list[EvidenceItem] = []

        for a in anomalies:
            eid = a.get("entity_id", "unknown")
            ts = a.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if not ts:
                ts = datetime.now(timezone.utc)

            category = a.get("category", "latency")
            signal = a.get("signal", "unknown")
            cur_val = a.get("current_value")
            base_val = a.get("baseline_mean")

            # 1. Metric evidence for all metric anomalies
            if category in ("metric", "latency", "saturation", "traffic"):
                ev_metric = await self.metrics.collect(
                    entity_id=eid,
                    timestamp=ts,
                    signal=signal,
                    deviation_value=cur_val,
                    baseline_value=base_val,
                )
                evidence_list.append(ev_metric)

            # 2. Log evidence for error_rate or root cause
            if category == "error_rate" or eid == root_candidate:
                ev_log = await self.logs.collect(
                    entity_id=eid,
                    timestamp=ts,
                )
                evidence_list.append(ev_log)

            # 3. Trace evidence for latency anomalies
            if category == "latency" or "duration" in signal:
                dur = cur_val * 1000.0 if (cur_val is not None and cur_val < 100) else cur_val
                ev_trace = await self.traces.collect(
                    entity_id=eid,
                    timestamp=ts,
                    duration_ms=dur,
                )
                evidence_list.append(ev_trace)

        # Sort chronologically
        evidence_list.sort(key=lambda ev: ev.timestamp)
        return evidence_list
