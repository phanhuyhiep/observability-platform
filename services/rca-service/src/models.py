"""Domain models for RCA Engine & Incident Lifecycle."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    temporal: float = 0.0
    topology: float = 0.0
    propagation: float = 0.0
    severity: float = 0.0
    deployment: float = 0.0
    evidence: float = 0.0


class RootCauseCandidate(BaseModel):
    rank: int = 1
    entity_id: str
    entity_type: str = "service"
    description: str
    score: float
    confidence: float
    scores_breakdown: ScoreBreakdown
    first_anomaly_at: datetime | None = None
    anomaly_signals: list[str] = Field(default_factory=list)


class BlastRadius(BaseModel):
    root_entity: str
    direct_impact: list[str] = Field(default_factory=list)
    indirect_impact: list[str] = Field(default_factory=list)
    total_impacted: int = 0
    user_facing_services: list[str] = Field(default_factory=list)
    estimated_user_impact: str = "low"  # critical, high, medium, low


class EvidenceItem(BaseModel):
    type: str  # metric, log, trace, k8s_event
    entity: str
    timestamp: datetime
    description: str
    signal: str | None = None
    grafana_link: str | None = None
    sample_data: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    incident_id: str
    timestamp: datetime
    event_type: str  # state_change, rca_computed, anomaly_added, evidence_collected, comment
    actor: str = "system"
    title: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentDetail(BaseModel):
    incident_id: str
    title: str
    severity: str
    status: str
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None = None
    investigating_at: datetime | None = None
    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    mttr_seconds: float | None = None
    mttd_seconds: float | None = None
    root_causes: list[RootCauseCandidate] = Field(default_factory=list)
    blast_radius: BlastRadius | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    impacted_entities: list[str] = Field(default_factory=list)
    anomaly_count: int = 0
    entity_count: int = 0
    cluster: str | None = None
    namespaces: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
