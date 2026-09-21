"""Unit tests for Deployment Correlator."""

from datetime import datetime, timedelta, timezone

from src.correlators.deployment_correlator import DeploymentCorrelator
from src.models import AnomalyEvent, CorrelationGroup, DeploymentEvent


def test_deployment_correlation_match():
    correlator = DeploymentCorrelator(correlation_window_seconds=1800)
    base_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    deploy_time = base_time - timedelta(minutes=4)
    deploy_event = DeploymentEvent(
        event_id="dep-1",
        timestamp=deploy_time,
        event_type="deployment_rollout",
        entity_id="paymentservice",
        details={"new_version": "v2.1.0"},
    )

    anomaly = AnomalyEvent(
        anomaly_id="a1",
        timestamp=base_time,
        entity_type="service",
        entity_id="paymentservice",
        detector="zscore",
        category="error_rate",
        signal="5xx_rate",
        severity="critical",
    )

    group = CorrelationGroup(
        correlation_id="grp-1",
        created_at=base_time,
        updated_at=base_time,
        window_start=base_time,
        anomalies=[anomaly],
        entity_count=1,
    )

    enriched = correlator.correlate(group, [deploy_event])

    ctx = enriched.deployment_context
    assert ctx is not None
    assert ctx.deployment_correlated is True
    assert ctx.deployed_entity == "paymentservice"
    assert ctx.time_since_deploy_seconds == 240.0
    assert ctx.deployment_confidence == 0.95


def test_deployment_outside_window():
    correlator = DeploymentCorrelator(correlation_window_seconds=1800)
    base_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    # Deployed 2 hours before anomaly -> outside 30min window
    old_deploy = DeploymentEvent(
        event_id="dep-old",
        timestamp=base_time - timedelta(hours=2),
        event_type="deployment_rollout",
        entity_id="paymentservice",
    )

    anomaly = AnomalyEvent(
        anomaly_id="a1",
        timestamp=base_time,
        entity_type="service",
        entity_id="paymentservice",
        detector="zscore",
        category="error_rate",
        signal="5xx_rate",
    )

    group = CorrelationGroup(
        correlation_id="grp-1",
        created_at=base_time,
        updated_at=base_time,
        window_start=base_time,
        anomalies=[anomaly],
        entity_count=1,
    )

    enriched = correlator.correlate(group, [old_deploy])
    assert enriched.deployment_context is None
