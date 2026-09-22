"""Pydantic schemas and models for AI Enhancement Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ML Anomaly Detection Schemas
# ---------------------------------------------------------------------------

class FeatureVector(BaseModel):
    entity_id: str
    features: dict[str, float]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AnomalyScoreResult(BaseModel):
    entity_id: str
    is_anomaly: bool
    anomaly_score: float          # 0.0 (normal) to 1.0 (extreme anomaly)
    raw_decision_score: float     # Decision function output
    confidence: float             # Confidence level in classification
    feature_attributions: dict[str, float] = Field(default_factory=dict)
    threshold: float
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class TrainModelRequest(BaseModel):
    entity_id: str
    samples: list[dict[str, float]] | None = None
    contamination: float = 0.02
    n_estimators: int = 100


class ModelMetadata(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str
    entity_id: str
    model_type: str
    version: str
    features: list[str]
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Dynamic Baseline & Forecasting Schemas
# ---------------------------------------------------------------------------

class ForecastPoint(BaseModel):
    timestamp: datetime
    predicted_value: float
    lower_bound: float
    upper_bound: float
    std: float


class MetricForecastResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    entity_id: str
    metric: str
    horizon_minutes: int
    forecast_points: list[ForecastPoint]
    model_type: str = "seasonal_exponential_smoothing"


class DynamicBaselineResponse(BaseModel):
    entity_id: str
    metric: str
    timestamp: datetime
    expected_mean: float
    lower_bound: float
    upper_bound: float
    std: float
    current_value: float | None = None
    is_anomalous: bool | None = None
    z_score: float | None = None


# ---------------------------------------------------------------------------
# LLM Incident Copilot & Recommendation Schemas
# ---------------------------------------------------------------------------

class InvestigationStep(BaseModel):
    step_order: int
    action_title: str
    command: str | None = None
    reasoning: str
    runbook_url: str | None = None


class IncidentSummaryResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    incident_id: str
    provider: str
    model_name: str
    summary_text: str
    root_cause_explanation: str
    executive_overview: str
    suggested_actions: list[str] = Field(default_factory=list)
    tokens_used: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SimilarIncidentItem(BaseModel):
    incident_id: str
    title: str
    similarity_score: float
    root_cause: str
    resolution_summary: str | None = None


class InvestigationRecommendationResponse(BaseModel):
    incident_id: str
    recommendations: list[InvestigationStep]
    similar_incidents: list[SimilarIncidentItem] = Field(default_factory=list)
    runbooks: list[dict[str, str]] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    recommendation_id: str | None = None
    rating: int = Field(..., ge=1, le=5)
    helpful: bool = True
    comments: str | None = None
    actor: str = "sre-engineer"


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
