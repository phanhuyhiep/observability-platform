"""Core domain models for Correlation Engine."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AnomalyEvent(BaseModel):
    anomaly_id: str
    timestamp: datetime
    entity_type: str
    entity_id: str
    namespace: str | None = "default"
    cluster: str | None = None
    detector: str
    category: str
    signal: str
    severity: str = "warning"
    score: float | None = None
    confidence: float | None = None
    current_value: float | None = None
    baseline_mean: float | None = None
    baseline_std: float | None = None
    z_score: float | None = None
    rule_id: str | None = None
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime | None = None


class ServiceNode(BaseModel):
    node_id: str
    node_type: str = "service"  # service, database, queue, external
    namespace: str | None = "default"
    cluster: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class ServiceEdge(BaseModel):
    edge_id: str | None = None
    source_id: str
    target_id: str
    dependency_type: str = "http"  # http, grpc, database, queue, external
    metadata: dict[str, Any] = Field(default_factory=dict)
    discovered_by: str = "otel_traces"
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class DeploymentEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime
    event_type: str = "deployment_rollout"
    entity_type: str = "deployment"
    entity_id: str
    namespace: str | None = "default"
    cluster: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class TopologyContext(BaseModel):
    has_dependency_relation: bool = False
    propagation_direction: str | None = None  # downstream, upstream, none
    propagation_paths: list[list[str]] = Field(default_factory=list)
    root_entity_candidate: str | None = None
    topology_confidence: float = 0.0
    dependency_chains: list[str] = Field(default_factory=list)


class DeploymentContext(BaseModel):
    deployment_correlated: bool = False
    event_id: str | None = None
    deployed_entity: str | None = None
    time_since_deploy_seconds: float | None = None
    deployment_confidence: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class CorrelationGroup(BaseModel):
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime
    updated_at: datetime
    window_start: datetime
    window_end: datetime | None = None
    status: str = "active"  # active, closed, merged
    correlation_type: str = "hybrid"  # temporal, topology, deployment, hybrid
    anomalies: list[AnomalyEvent] = Field(default_factory=list)
    entity_count: int = 0
    severity_max: str = "warning"
    topology_context: TopologyContext | None = None
    deployment_context: DeploymentContext | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    incident_id: str
    title: str
    severity: str = "warning"  # critical, high, warning, info
    status: str = "OPEN"  # OPEN, ACKNOWLEDGED, RESOLVED, CLOSED
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    correlation_id: str | None = None
    anomaly_count: int = 0
    entity_count: int = 0
    impacted_entities: list[str] = Field(default_factory=list)
    namespaces: list[str] = Field(default_factory=list)
    cluster: str | None = None
    topology_context: TopologyContext | None = None
    deployment_context: DeploymentContext | None = None
    anomaly_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
