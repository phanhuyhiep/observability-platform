"""Pydantic models for Detection Service."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================

class Severity(str, Enum):
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class DetectorType(str, Enum):
    RULE = "rule"
    ZSCORE = "z_score"
    EWMA = "ewma"
    SMA = "sma"


class EntityType(str, Enum):
    SERVICE = "service"
    POD = "pod"
    NODE = "node"
    DEPLOYMENT = "deployment"


# ============================================================
# Feature Vector
# ============================================================

class FeatureValues(BaseModel):
    mean: float = 0.0
    std: float = 0.0
    min: float = 0.0
    max: float = 0.0
    slope: float = 0.0
    rate_of_change: float = 0.0
    z_score: float | None = None
    baseline_mean: float | None = None
    baseline_std: float | None = None
    baseline_window: str | None = None


class FeatureVector(BaseModel):
    entity_type: str
    entity_id: str
    metric: str
    timestamp: datetime
    current_value: float
    window: str = "5m"
    features: FeatureValues = FeatureValues()


# ============================================================
# Anomaly Event (schema v1)
# ============================================================

class AnomalyEntity(BaseModel):
    type: str
    id: str
    namespace: str | None = None
    cluster: str | None = None


class AnomalyDetection(BaseModel):
    detector: str
    category: str
    signal: str
    severity: str
    score: float = 0.0
    confidence: float = 0.0


class AnomalyValues(BaseModel):
    current: float
    baseline_mean: float | None = None
    baseline_std: float | None = None
    z_score: float | None = None
    threshold_used: float | None = None


class AnomalyContext(BaseModel):
    window: str | None = None
    baseline_window: str | None = None
    rule_id: str | None = None


class AnomalyEvent(BaseModel):
    anomaly_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    timestamp: datetime
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    entity: AnomalyEntity
    detection: AnomalyDetection
    values: AnomalyValues
    context: AnomalyContext = AnomalyContext()
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = AnomalyStatus.ACTIVE


# ============================================================
# Rule Definition
# ============================================================

class RuleCondition(BaseModel):
    operator: str  # ">", "<", ">=", "<=", "==", "increased"
    threshold: float | None = None
    min_increase: float | None = None


class Rule(BaseModel):
    id: str
    name: str
    description: str = ""
    metric: str
    entity_scope: str  # "pod", "service", "node"
    condition: RuleCondition
    duration: str = "0m"
    severity: str = "warning"
    category: str = "general"
    enabled: bool = True


# ============================================================
# Baseline
# ============================================================

class Baseline(BaseModel):
    entity_type: str
    entity_id: str
    metric: str
    namespace: str | None = None
    mean: float
    std: float
    min_val: float | None = None
    max_val: float | None = None
    sample_count: int = 0
    window: str = "7d"
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# API Models
# ============================================================

class AnomalyListResponse(BaseModel):
    items: list[AnomalyEvent]
    total: int
    page: int = 1
    limit: int = 50


class AnomalyFilter(BaseModel):
    entity_type: str | None = None
    entity_id: str | None = None
    severity: str | None = None
    category: str | None = None
    detector: str | None = None
    status: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class DetectorResult(BaseModel):
    """Output from a single detector evaluation."""
    is_anomaly: bool
    detector: str
    severity: str | None = None
    score: float = 0.0
    confidence: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)
