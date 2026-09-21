"""Unit tests for RCA Multi-Signal Scoring Engine."""

from datetime import datetime, timedelta, timezone
import networkx as nx
import pytest

from src.config import RCAWeights
from src.scoring.deployment_scorer import DeploymentScorer
from src.scoring.evidence_scorer import EvidenceScorer
from src.scoring.propagation_scorer import PropagationScorer
from src.scoring.root_cause_ranker import RootCauseRanker
from src.scoring.severity_scorer import SeverityScorer
from src.scoring.temporal_scorer import TemporalScorer
from src.scoring.topology_scorer import TopologyScorer


@pytest.fixture
def sample_graph():
    """Create a sample microservices dependency graph (caller -> callee)."""
    g = nx.DiGraph()
    g.add_edge("frontend", "cartservice")
    g.add_edge("cartservice", "redis-cart")
    g.add_edge("frontend", "checkoutservice")
    g.add_edge("checkoutservice", "paymentservice")
    return g


def test_temporal_scorer():
    scorer = TemporalScorer()
    now = datetime.now(timezone.utc)
    t1 = now - timedelta(minutes=10)
    t2 = now - timedelta(minutes=5)
    t3 = now

    timestamps = {
        "redis-cart": t1,
        "cartservice": t2,
        "frontend": t3,
    }

    scores = scorer.score(timestamps)
    assert scores["redis-cart"] == 1.0
    assert scores["cartservice"] < 1.0
    assert scores["frontend"] <= scores["cartservice"]
    assert scores["frontend"] >= 0.1


def test_topology_scorer(sample_graph):
    scorer = TopologyScorer()
    entities = ["frontend", "cartservice", "redis-cart"]
    scores = scorer.score(entities, sample_graph)

    # redis-cart is a leaf node called by cartservice and has db in name -> highest score
    assert scores["redis-cart"] > scores["frontend"]
    assert scores["redis-cart"] >= 0.7


def test_propagation_scorer(sample_graph):
    scorer = PropagationScorer()
    entities = ["frontend", "cartservice", "redis-cart"]
    scores = scorer.score(entities, sample_graph)

    # redis-cart failure propagates up to cartservice and frontend
    # redis-cart has 2 upstream callers in entity set -> highest propagation score
    assert scores["redis-cart"] >= scores["frontend"]


def test_severity_scorer():
    scorer = SeverityScorer()
    anomalies = {
        "redis-cart": [{"severity": "critical", "z_score": 6.2}],
        "cartservice": [{"severity": "warning", "z_score": 3.1}],
        "frontend": [{"severity": "info", "z_score": 1.5}],
    }
    scores = scorer.score(anomalies)
    assert scores["redis-cart"] >= 1.0
    assert scores["cartservice"] >= 0.5
    assert scores["frontend"] <= 0.35


def test_deployment_scorer():
    scorer = DeploymentScorer()
    now = datetime.now(timezone.utc)
    entities = ["cartservice", "redis-cart"]
    deployments = [
        {"entity_id": "redis-cart", "timestamp": now - timedelta(minutes=3)},
    ]
    scores = scorer.score(entities, now, deployments)
    assert scores["redis-cart"] == 1.0
    assert scores["cartservice"] == 0.0


def test_evidence_scorer():
    scorer = EvidenceScorer()
    entities = ["redis-cart", "frontend"]
    evidence = [
        {"entity": "redis-cart", "type": "metric"},
        {"entity": "redis-cart", "type": "log"},
        {"entity": "redis-cart", "type": "trace"},
        {"entity": "frontend", "type": "metric"},
    ]
    scores = scorer.score(entities, evidence)
    assert scores["redis-cart"] > scores["frontend"]
    assert scores["redis-cart"] >= 0.9


def test_root_cause_ranker_integration(sample_graph):
    ranker = RootCauseRanker()
    now = datetime.now(timezone.utc)

    entities = ["frontend", "cartservice", "redis-cart"]
    timestamps = {
        "redis-cart": now - timedelta(minutes=10),
        "cartservice": now - timedelta(minutes=5),
        "frontend": now - timedelta(minutes=2),
    }
    anomalies = {
        "redis-cart": [{"severity": "critical", "signal": "latency", "z_score": 5.5}],
        "cartservice": [{"severity": "high", "signal": "latency", "z_score": 4.0}],
        "frontend": [{"severity": "critical", "signal": "error_rate", "z_score": 3.5}],
    }
    deployments = [
        {"entity_id": "redis-cart", "timestamp": now - timedelta(minutes=4)},
    ]
    evidence = [
        {"entity": "redis-cart", "type": "metric"},
        {"entity": "redis-cart", "type": "log"},
        {"entity": "redis-cart", "type": "trace"},
    ]

    ranked = ranker.rank(
        entities=entities,
        entity_timestamps=timestamps,
        entity_anomalies=anomalies,
        graph=sample_graph,
        incident_time=now,
        recent_deployments=deployments,
        evidence_items=evidence,
    )

    assert len(ranked) == 3
    # redis-cart should be ranked #1
    top = ranked[0]
    assert top.entity_id == "redis-cart"
    assert top.rank == 1
    assert top.entity_type == "database"
    assert top.confidence >= 0.70
    assert top.scores_breakdown.temporal == 1.0
    assert top.scores_breakdown.deployment == 1.0
