"""Unit tests for Incident Grouper, Merger, and Suppression."""

from datetime import datetime, timezone

from src.incident.incident_grouper import IncidentGrouper
from src.incident.incident_merger import IncidentMerger
from src.incident.incident_suppression import IncidentSuppression
from src.models import (
    AnomalyEvent,
    CorrelationGroup,
    DeploymentContext,
    Incident,
    TopologyContext,
)


def make_group(anomalies: list[AnomalyEvent], top_ctx=None, dep_ctx=None) -> CorrelationGroup:
    now = datetime.now(timezone.utc)
    return CorrelationGroup(
        correlation_id="test-grp",
        created_at=now,
        updated_at=now,
        window_start=now,
        anomalies=anomalies,
        entity_count=len({a.entity_id for a in anomalies}),
        topology_context=top_ctx,
        deployment_context=dep_ctx,
    )


def test_incident_threshold():
    grouper = IncidentGrouper(auto_create=True, min_anomalies=2, critical_auto_create=True)
    now = datetime.now(timezone.utc)

    # Single warning anomaly -> False
    a1 = AnomalyEvent(
        anomaly_id="a1",
        timestamp=now,
        entity_type="service",
        entity_id="frontend",
        detector="zscore",
        category="latency",
        signal="request_duration",
        severity="warning",
    )
    g1 = make_group([a1])
    assert grouper.should_create_incident(g1) is False

    # Single critical anomaly -> True
    a_crit = AnomalyEvent(
        anomaly_id="ac",
        timestamp=now,
        entity_type="service",
        entity_id="frontend",
        detector="zscore",
        category="error_rate",
        signal="5xx_rate",
        severity="critical",
    )
    g2 = make_group([a_crit])
    assert grouper.should_create_incident(g2) is True

    # Two warning anomalies -> True
    a2 = AnomalyEvent(
        anomaly_id="a2",
        timestamp=now,
        entity_type="service",
        entity_id="cartservice",
        detector="zscore",
        category="latency",
        signal="request_duration",
        severity="warning",
    )
    g3 = make_group([a1, a2])
    assert grouper.should_create_incident(g3) is True


def test_title_generation():
    grouper = IncidentGrouper()
    now = datetime.now(timezone.utc)
    a1 = AnomalyEvent(
        anomaly_id="a1",
        timestamp=now,
        entity_type="service",
        entity_id="paymentservice",
        detector="zscore",
        category="latency",
        signal="request_duration",
        severity="high",
    )

    # With deployment context
    dep_ctx = DeploymentContext(
        deployment_correlated=True,
        deployed_entity="paymentservice",
        details={"new_version": "2.5.0"},
    )
    g_dep = make_group([a1], dep_ctx=dep_ctx)
    title_dep = grouper.generate_title(g_dep)
    assert "[paymentservice] performance degradation after deployment v2.5.0" == title_dep

    # With topology context
    top_ctx = TopologyContext(
        has_dependency_relation=True,
        root_entity_candidate="postgresql",
    )
    a2 = AnomalyEvent(
        anomaly_id="a2",
        timestamp=now,
        entity_type="service",
        entity_id="orderservice",
        detector="zscore",
        category="latency",
        signal="request_duration",
        severity="high",
    )
    g_top = make_group([a1, a2], top_ctx=top_ctx)
    title_top = grouper.generate_title(g_top)
    assert "[postgresql]" in title_top


def test_incident_merging():
    merger = IncidentMerger(merge_window_seconds=600)
    now = datetime.now(timezone.utc)

    existing_incident = Incident(
        incident_id="INC-1001",
        title="[cartservice] latency degradation",
        severity="warning",
        status="OPEN",
        created_at=now,
        updated_at=now,
        impacted_entities=["cartservice"],
        anomaly_ids=["a1"],
    )

    new_candidate = Incident(
        incident_id="INC-1002",
        title="[cartservice] error cascade",
        severity="critical",
        status="OPEN",
        created_at=now,
        updated_at=now,
        impacted_entities=["cartservice", "redis-cart"],
        anomaly_ids=["a2"],
    )

    merged, was_merged = merger.try_merge(new_candidate, [existing_incident])
    assert was_merged is True
    assert merged.incident_id == "INC-1001"
    assert "redis-cart" in merged.impacted_entities
    assert "a2" in merged.anomaly_ids
    assert merged.severity == "critical"  # Escalated


def test_incident_suppression():
    suppression = IncidentSuppression(suppression_window_seconds=1800)
    now = datetime.now(timezone.utc)

    active_incident = Incident(
        incident_id="INC-1001",
        title="[postgresql] performance failure",
        severity="critical",
        status="OPEN",
        created_at=now,
        updated_at=now,
        impacted_entities=["postgresql", "paymentservice"],
        topology_context=TopologyContext(root_entity_candidate="postgresql"),
    )

    # Candidate with the same root entity
    candidate = Incident(
        incident_id="INC-1002",
        title="[postgresql] secondary alert",
        severity="high",
        status="OPEN",
        created_at=now,
        updated_at=now,
        impacted_entities=["postgresql"],
        topology_context=TopologyContext(root_entity_candidate="postgresql"),
    )

    is_suppressed, reason, match_id = suppression.should_suppress(candidate, [active_incident])
    assert is_suppressed is True
    assert match_id == "INC-1001"
    assert "postgresql" in reason
