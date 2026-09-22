"""FastAPI REST API routes for AI Enhancement Service (Phase 5)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Response

from ..anomaly_detection import (
    AnomalyInferenceEngine,
    FeatureMatrixBuilder,
    ModelTrainingPipeline,
)
from ..forecasting import DynamicBaselineEngine, TimeSeriesForecaster
from ..llm import (
    HistoricalSimilarityEngine,
    IncidentSummarizer,
    InvestigationRecommender,
    LLMClient,
)
from ..models import (
    AnomalyScoreResult,
    DynamicBaselineResponse,
    FeedbackRequest,
    FeedbackResponse,
    IncidentSummaryResponse,
    InvestigationRecommendationResponse,
    MetricForecastResponse,
    ModelMetadata,
    TrainModelRequest,
)

logger = logging.getLogger("ai.api.routes")
router = APIRouter()

# Global module references injected during lifespan
inference_engine: AnomalyInferenceEngine | None = None
training_pipeline: ModelTrainingPipeline | None = None
dynamic_baseline_engine: DynamicBaselineEngine | None = None
incident_summarizer: IncidentSummarizer | None = None
investigation_recommender: InvestigationRecommender | None = None
similarity_engine: HistoricalSimilarityEngine | None = None
db_pool: asyncpg.Pool | None = None


def set_dependencies(
    infer: AnomalyInferenceEngine,
    train: ModelTrainingPipeline,
    dyn_base: DynamicBaselineEngine,
    summarizer: IncidentSummarizer,
    recommender: InvestigationRecommender,
    sim_engine: HistoricalSimilarityEngine,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Inject singleton dependencies into router."""
    global inference_engine, training_pipeline, dynamic_baseline_engine
    global incident_summarizer, investigation_recommender, similarity_engine, db_pool

    inference_engine = infer
    training_pipeline = train
    dynamic_baseline_engine = dyn_base
    incident_summarizer = summarizer
    investigation_recommender = recommender
    similarity_engine = sim_engine
    db_pool = pool


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@router.get("/health", tags=["System"])
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ai-service",
        "phase": 5,
        "models_loaded": len(training_pipeline.models) if training_pipeline else 0,
        "database_connected": db_pool is not None,
    }


# ---------------------------------------------------------------------------
# 1. Multivariate Anomaly Detection (Isolation Forest)
# ---------------------------------------------------------------------------

@router.post("/api/v1/ml/detect", response_model=AnomalyScoreResult, tags=["ML Detection"])
async def detect_anomalies(payload: dict[str, Any]):
    """Evaluate multi-metric telemetry vector for multivariate anomalies using Isolation Forest."""
    if not inference_engine:
        raise HTTPException(status_code=503, detail="Inference engine not ready")

    entity_id = payload.get("entity_id", "unknown_service")
    metrics = payload.get("metrics", payload)  # Allow flat dict or nested metrics
    if "entity_id" in metrics:
        metrics = {k: v for k, v in metrics.items() if k != "entity_id"}

    result = inference_engine.evaluate(entity_id=entity_id, metrics=metrics)
    return result


@router.post("/api/v1/ml/models/train", tags=["ML Detection"])
async def train_model(request: TrainModelRequest):
    """Trigger training or retraining of Isolation Forest detector for an entity."""
    if not training_pipeline:
        raise HTTPException(status_code=503, detail="Training pipeline not ready")

    detector = training_pipeline.train_entity_model(
        entity_id=request.entity_id,
        samples=request.samples,
    )
    model_id = await training_pipeline.save_model_to_db(request.entity_id, detector)

    return {
        "status": "trained",
        "entity_id": request.entity_id,
        "model_id": model_id,
        "engine": "sklearn" if detector.is_sklearn else "numpy_itree",
        "n_estimators": detector.n_estimators,
        "threshold": detector.threshold,
    }


@router.get("/api/v1/ml/models", tags=["ML Detection"])
async def list_models():
    """List trained anomaly detection models."""
    if not training_pipeline:
        raise HTTPException(status_code=503, detail="Training pipeline not ready")

    models_info = []
    for ent, model in training_pipeline.models.items():
        models_info.append({
            "entity_id": ent,
            "model_type": "isolation_forest",
            "engine": "sklearn" if model.is_sklearn else "numpy",
            "threshold": model.threshold,
            "n_estimators": model.n_estimators,
            "status": "active",
        })
    return {"models": models_info, "total": len(models_info)}


# ---------------------------------------------------------------------------
# 2. Dynamic Baselines & Time-Series Forecasting
# ---------------------------------------------------------------------------

@router.get("/api/v1/forecast/{entity_id}/{metric}", response_model=MetricForecastResponse, tags=["Forecasting"])
async def get_forecast(
    entity_id: str,
    metric: str,
    horizon: int = Query(60, description="Forecast horizon in minutes"),
    interval: int = Query(5, description="Interval step in minutes"),
    current_val: float | None = Query(None, description="Optional current observed metric value"),
):
    """Generate time-series forecast with confidence intervals for future intervals."""
    if not dynamic_baseline_engine:
        raise HTTPException(status_code=503, detail="Forecasting engine not ready")

    forecaster = dynamic_baseline_engine.get_forecaster(entity_id, metric)
    now = datetime.now(timezone.utc)
    points = forecaster.forecast(
        start_time=now,
        horizon_minutes=horizon,
        interval_minutes=interval,
        base_value=current_val,
    )

    return MetricForecastResponse(
        entity_id=entity_id,
        metric=metric,
        horizon_minutes=horizon,
        forecast_points=points,
    )


@router.get("/api/v1/baselines/dynamic/{entity_id}/{metric}", response_model=DynamicBaselineResponse, tags=["Forecasting"])
async def get_dynamic_baseline(
    entity_id: str,
    metric: str,
    current_value: float | None = Query(None, description="Optional current metric value to check against baseline"),
):
    """Compute the seasonal-aware dynamic baseline expectations and upper/lower boundaries."""
    if not dynamic_baseline_engine:
        raise HTTPException(status_code=503, detail="Dynamic baseline engine not ready")

    baseline = dynamic_baseline_engine.get_dynamic_baseline(
        entity_id=entity_id,
        metric=metric,
        current_value=current_value,
    )
    return baseline


# ---------------------------------------------------------------------------
# 3. LLM Incident Copilot & Investigation Assistant
# ---------------------------------------------------------------------------

@router.get("/api/v1/incidents/{incident_id}/summary", response_model=IncidentSummaryResponse, tags=["AI Copilot"])
async def get_incident_summary(incident_id: str, force: bool = Query(False, description="Force re-generation")):
    """Get or generate an AI-powered Root Cause Analysis executive summary."""
    if not incident_summarizer:
        raise HTTPException(status_code=503, detail="AI Summarizer not ready")

    # Fetch incident context from database if available
    title = f"Incident {incident_id}"
    severity = "CRITICAL"
    root_cause = "redis-cart"
    confidence = 0.94
    impacted = ["redis-cart", "cartservice", "frontend"]

    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM incidents WHERE incident_id = $1", incident_id)
                if row:
                    title = row["title"]
                    severity = row["severity"]
                    imp = row["impacted_entities"]
                    if isinstance(imp, str):
                        imp = json.loads(imp)
                    impacted = imp or []
                    meta = row.get("metadata") or {}
                    top_ctx = row.get("topology_context") or {}
                    root_cause = meta.get("root_candidate") or top_ctx.get("root_entity_candidate") or (impacted[0] if impacted else "unknown")
                    confidence = float(top_ctx.get("confidence", 0.92))
        except Exception as e:
            logger.warning("Could not fetch incident from DB (%s), using context fallback", e)

    summary = await incident_summarizer.summarize(
        incident_id=incident_id,
        title=title,
        severity=severity,
        root_cause=root_cause,
        confidence=confidence,
        impacted_services=impacted,
        force_regenerate=force,
    )
    return summary


@router.post("/api/v1/incidents/{incident_id}/summary/regenerate", response_model=IncidentSummaryResponse, tags=["AI Copilot"])
async def regenerate_incident_summary(incident_id: str):
    """Force re-run AI summarization for an updated incident."""
    return await get_incident_summary(incident_id, force=True)


@router.get("/api/v1/incidents/{incident_id}/recommendations", response_model=InvestigationRecommendationResponse, tags=["AI Copilot"])
async def get_investigation_recommendations(incident_id: str):
    """Retrieve ordered investigation steps, shell commands, matching runbooks, and similar past incidents."""
    if not investigation_recommender or not similarity_engine:
        raise HTTPException(status_code=503, detail="Recommendation engine not ready")

    root_cause = "redis-cart"
    impacted = ["redis-cart", "cartservice", "frontend"]
    severity = "critical"

    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM incidents WHERE incident_id = $1", incident_id)
                if row:
                    severity = row["severity"]
                    imp = row["impacted_entities"]
                    if isinstance(imp, str):
                        imp = json.loads(imp)
                    impacted = imp or []
                    meta = row.get("metadata") or {}
                    top_ctx = row.get("topology_context") or {}
                    root_cause = meta.get("root_candidate") or top_ctx.get("root_entity_candidate") or (impacted[0] if impacted else "unknown")
        except Exception as e:
            logger.warning("Error fetching incident for recommendations: %s", e)

    steps = investigation_recommender.generate_recommendations(incident_id, root_cause)
    runbooks = investigation_recommender.get_matched_runbooks(root_cause)
    similar = await similarity_engine.find_similar(incident_id, root_cause, impacted, severity)

    # Persist in DB
    if db_pool:
        await investigation_recommender.persist_recommendations(incident_id, steps)

    return InvestigationRecommendationResponse(
        incident_id=incident_id,
        recommendations=steps,
        similar_incidents=similar,
        runbooks=runbooks,
    )


@router.get("/api/v1/incidents/{incident_id}/similar", tags=["AI Copilot"])
async def get_similar_incidents(incident_id: str, limit: int = 3):
    """Find historical incidents with similar failure patterns and entities."""
    if not similarity_engine:
        raise HTTPException(status_code=503, detail="Similarity engine not ready")

    root_cause = "redis-cart"
    impacted = ["redis-cart", "cartservice", "frontend"]
    severity = "critical"

    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM incidents WHERE incident_id = $1", incident_id)
                if row:
                    severity = row["severity"]
                    imp = row["impacted_entities"]
                    if isinstance(imp, str):
                        imp = json.loads(imp)
                    impacted = imp or []
                    meta = row.get("metadata") or {}
                    top_ctx = row.get("topology_context") or {}
                    root_cause = meta.get("root_candidate") or top_ctx.get("root_entity_candidate") or "unknown"
        except Exception:
            pass

    similar = await similarity_engine.find_similar(incident_id, root_cause, impacted, severity, limit=limit)
    return {"incident_id": incident_id, "similar_incidents": similar}


@router.post("/api/v1/feedback/recommendations/{incident_id}", response_model=FeedbackResponse, tags=["AI Copilot"])
async def submit_recommendation_feedback(incident_id: str, feedback: FeedbackRequest):
    """Submit engineer rating/feedback on AI recommendations to improve ranking."""
    feedback_id = str(uuid.uuid4())
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ai_feedback (
                        feedback_id, incident_id, recommendation_id, rating, helpful, comments, actor
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7);
                    """,
                    uuid.UUID(feedback_id),
                    incident_id,
                    uuid.UUID(feedback.recommendation_id) if feedback.recommendation_id else None,
                    feedback.rating,
                    feedback.helpful,
                    feedback.comments,
                    feedback.actor,
                )
        except Exception as e:
            logger.warning("Could not persist feedback: %s", e)

    return FeedbackResponse(
        status="recorded",
        feedback_id=feedback_id,
        recorded_at=datetime.now(timezone.utc),
    )
