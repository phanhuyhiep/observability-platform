"""Pydantic request and response schemas for REST API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models import CorrelationGroup, DeploymentEvent, Incident, ServiceEdge, ServiceNode


class ServiceGraphResponse(BaseModel):
    nodes: list[ServiceNode]
    edges: list[ServiceEdge]
    total_nodes: int
    total_edges: int


class DependencyListResponse(BaseModel):
    entity_id: str
    direction: str  # upstream or downstream
    dependencies: list[str]
    count: int


class ManualEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    dependency_type: str = "http"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CorrelationListResponse(BaseModel):
    items: list[CorrelationGroup]
    total: int


class IncidentListResponse(BaseModel):
    items: list[Incident]
    total: int


class UpdateIncidentStatusRequest(BaseModel):
    status: str  # OPEN, ACKNOWLEDGED, RESOLVED, CLOSED


class DeploymentWebhookRequest(BaseModel):
    entity_id: str
    event_type: str = "deployment_rollout"
    entity_type: str = "deployment"
    namespace: str | None = "default"
    cluster: str | None = None
    timestamp: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)
