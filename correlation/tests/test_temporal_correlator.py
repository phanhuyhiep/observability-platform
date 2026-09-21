"""Unit tests for Temporal Correlator."""

from datetime import datetime, timedelta, timezone

from src.correlators.temporal_correlator import TemporalCorrelator
from src.models import AnomalyEvent


def make_anomaly(
    aid: str,
    entity: str,
    ts: datetime,
    severity: str = "warning",
    category: str = "latency",
    ns: str = "default",
) -> AnomalyEvent:
    return AnomalyEvent(
        anomaly_id=aid,
        timestamp=ts,
        entity_type="service",
        entity_id=entity,
        namespace=ns,
        detector="zscore",
        category=category,
        signal="request_duration",
        severity=severity,
    )


def test_grouping_within_window():
    correlator = TemporalCorrelator(window_size_seconds=300)
    base_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    a1 = make_anomaly("a1", "cartservice", base_time)
    a2 = make_anomaly("a2", "frontend", base_time + timedelta(seconds=60), severity="high")

    groups = correlator.correlate([a1, a2])

    assert len(groups) == 1
    grp = groups[0]
    assert len(grp.anomalies) == 2
    assert grp.entity_count == 2
    assert grp.severity_max == "high"


def test_window_extension():
    correlator = TemporalCorrelator(
        window_size_seconds=300,
        max_window_extension_seconds=900,
    )
    base_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    a1 = make_anomaly("a1", "cartservice", base_time)
    # 200s later (within initial 300s window)
    a2 = make_anomaly("a2", "frontend", base_time + timedelta(seconds=200))
    # 400s later (past 300s, should extend window)
    a3 = make_anomaly("a3", "checkoutservice", base_time + timedelta(seconds=400))

    groups = correlator.correlate([a1, a2, a3])

    assert len(groups) == 1
    grp = groups[0]
    assert len(grp.anomalies) == 3
    assert grp.window_end > base_time + timedelta(seconds=300)


def test_distinct_window_separation():
    correlator = TemporalCorrelator(window_size_seconds=300)
    base_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    a1 = make_anomaly("a1", "cartservice", base_time)
    # Anomaly 2 hours later -> must form a separate group
    a2 = make_anomaly("a2", "frontend", base_time + timedelta(hours=2))

    groups = correlator.correlate([a1, a2])
    assert len(groups) == 2
