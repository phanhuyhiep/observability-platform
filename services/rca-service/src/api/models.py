"""Pydantic API request and response schemas for RCA Service."""

from typing import Any

from pydantic import BaseModel, Field

from src.models import BlastRadius, EvidenceItem, RootCauseCandidate, TimelineEvent


class RCAResponse(BaseModel):
    incident_id: str
    root_causes: list[RootCauseCandidate]
    top_root_cause: str | None = None
    confidence: float = 0.0


class BlastRadiusResponse(BaseModel):
    incident_id: str
    blast_radius: BlastRadius


class EvidenceResponse(BaseModel):
    incident_id: str
    evidence: list[EvidenceItem]
    total_evidence: int


class TimelineResponse(BaseModel):
    incident_id: str
    events: list[TimelineEvent]
    total_events: int


class TransitionRequest(BaseModel):
    actor: str = "engineer"
    comment: str | None = None


class CommentRequest(BaseModel):
    actor: str = "engineer"
    comment: str


class NotificationTestRequest(BaseModel):
    channel: str = "all"  # slack, telegram, all
    test_incident_id: str = "INC-1001"
