"""Unit tests for Evidence Aggregator and collectors."""

from datetime import datetime, timezone
import pytest

from src.evidence.evidence_aggregator import EvidenceAggregator
from src.evidence.log_collector import LogEvidenceCollector
from src.evidence.metric_collector import MetricEvidenceCollector
from src.evidence.trace_collector import TraceEvidenceCollector


@pytest.mark.asyncio
async def test_metric_evidence_collector():
    collector = MetricEvidenceCollector("http://fake-prom:9090")
    now = datetime.now(timezone.utc)
    ev = await collector.collect(
        entity_id="redis-cart",
        timestamp=now,
        signal="request_duration",
        deviation_value=0.85,
        baseline_value=0.05,
    )
    assert ev.type == "metric"
    assert ev.entity == "redis-cart"
    assert "0.850" in ev.description
    assert "baseline 0.050" in ev.description
    assert ev.grafana_link is not None


@pytest.mark.asyncio
async def test_log_evidence_collector():
    collector = LogEvidenceCollector("http://fake-loki:3100")
    now = datetime.now(timezone.utc)
    ev = await collector.collect(
        entity_id="cartservice",
        timestamp=now,
        error_sample="ConnectionRefusedError: Connection to redis failed",
    )
    assert ev.type == "log"
    assert ev.entity == "cartservice"
    assert "ConnectionRefusedError" in ev.description
    assert "cartservice" in ev.grafana_link


@pytest.mark.asyncio
async def test_trace_evidence_collector():
    collector = TraceEvidenceCollector("http://fake-tempo:3200")
    now = datetime.now(timezone.utc)
    ev = await collector.collect(
        entity_id="redis-cart",
        timestamp=now,
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        duration_ms=1250.0,
    )
    assert ev.type == "trace"
    assert ev.entity == "redis-cart"
    assert "4bf92f3577b34da6a3ce929d0e0e4736" in ev.description
    assert "1250.0ms" in ev.description
    assert "Tempo" in ev.grafana_link


@pytest.mark.asyncio
async def test_evidence_aggregator_multi_signal():
    agg = EvidenceAggregator()
    now = datetime.now(timezone.utc)

    anomalies = [
        {
            "entity_id": "redis-cart",
            "timestamp": now,
            "category": "latency",
            "signal": "request_duration",
            "current_value": 0.95,
            "baseline_mean": 0.04,
        },
        {
            "entity_id": "cartservice",
            "timestamp": now,
            "category": "error_rate",
            "signal": "http_errors",
            "current_value": 0.25,
            "baseline_mean": 0.01,
        },
    ]

    evidence = await agg.aggregate(anomalies, root_candidate="redis-cart")
    assert len(evidence) >= 3  # metric + trace for redis-cart, log for cartservice, etc.
    types = {ev.type for ev in evidence}
    assert "metric" in types
    assert "log" in types
    assert "trace" in types
