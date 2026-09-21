"""Unit tests for Topology Correlator."""

from datetime import datetime, timedelta, timezone

from src.correlators.topology_correlator import TopologyCorrelator
from src.graph.graph_query import GraphQuery
from src.graph.graph_storage import GraphStorage
from src.models import AnomalyEvent, CorrelationGroup, ServiceEdge, ServiceNode


def setup_topology_env() -> TopologyCorrelator:
    storage = GraphStorage()
    # Chain: frontend -> checkoutservice -> paymentservice -> postgresql
    for s in ["frontend", "checkoutservice", "paymentservice", "postgresql"]:
        storage.add_node(ServiceNode(node_id=s))

    storage.add_edge(ServiceEdge(source_id="frontend", target_id="checkoutservice"))
    storage.add_edge(ServiceEdge(source_id="checkoutservice", target_id="paymentservice"))
    storage.add_edge(ServiceEdge(source_id="paymentservice", target_id="postgresql"))

    query = GraphQuery(storage)
    return TopologyCorrelator(query=query, max_hop_depth=3)


def test_topology_root_cause_detection():
    correlator = setup_topology_env()
    base_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    # postgresql fails first at T=0s
    a1 = AnomalyEvent(
        anomaly_id="a1",
        timestamp=base_time,
        entity_type="database",
        entity_id="postgresql",
        detector="zscore",
        category="latency",
        signal="query_duration",
        severity="high",
    )
    # paymentservice fails at T=5s
    a2 = AnomalyEvent(
        anomaly_id="a2",
        timestamp=base_time + timedelta(seconds=5),
        entity_type="service",
        entity_id="paymentservice",
        detector="zscore",
        category="latency",
        signal="request_duration",
        severity="high",
    )
    # checkoutservice fails at T=10s
    a3 = AnomalyEvent(
        anomaly_id="a3",
        timestamp=base_time + timedelta(seconds=10),
        entity_type="service",
        entity_id="checkoutservice",
        detector="ewma",
        category="error_rate",
        signal="error_percentage",
        severity="critical",
    )

    group = CorrelationGroup(
        correlation_id="grp-1",
        created_at=base_time,
        updated_at=base_time + timedelta(seconds=10),
        window_start=base_time,
        anomalies=[a1, a2, a3],
        entity_count=3,
        severity_max="critical",
    )

    enriched = correlator.correlate(group)

    ctx = enriched.topology_context
    assert ctx is not None
    assert ctx.has_dependency_relation is True
    # Root cause candidate must be postgresql
    assert ctx.root_entity_candidate == "postgresql"
    assert ctx.propagation_direction == "downstream_caused_upstream_impact"
    assert ctx.topology_confidence >= 0.85
    assert len(ctx.dependency_chains) > 0
