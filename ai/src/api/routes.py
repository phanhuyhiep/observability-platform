"""FastAPI REST API routes for AI Enhancement Service (Phase 5)."""

from __future__ import annotations

import html
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

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
@router.post("/api/v1/anomalies/detect", response_model=AnomalyScoreResult, tags=["ML Detection"])
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
@router.get("/api/v1/models", tags=["ML Detection"])
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

def safe_escape(val: Any) -> str:
    """Null-safe HTML escaping for dynamic telemetry and recommendation fields."""
    if val is None:
        return ""
    return html.escape(str(val))


def _render_summary_html(summary: IncidentSummaryResponse) -> str:
    actions_html = "".join(f"<li><code>{safe_escape(a)}</code></li>" for a in (summary.suggested_actions or []))
    overview = safe_escape(summary.executive_overview or summary.summary_text)
    root_cause = safe_escape(summary.root_cause_explanation)
    inc_id = safe_escape(summary.incident_id)
    provider = safe_escape(summary.provider).upper()
    model = safe_escape(summary.model_name)
    created_at = summary.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if summary.created_at else ""

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI RCA Report - {inc_id}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', sans-serif; background: #0b1120; color: #e2e8f0; padding: 24px 16px; line-height: 1.6; }}
    .container {{ max-width: 860px; margin: 0 auto; }}
    .header {{ background: linear-gradient(135deg, #1e293b, #0f172a); border: 1px solid #334155; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
    .badge-bar {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }}
    .badge {{ background: #dc2626; color: white; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 6px; }}
    .badge-model {{ background: #0284c7; color: white; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 6px; }}
    h1 {{ font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 6px; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
    .card h2 {{ font-size: 15px; font-weight: 600; color: #38bdf8; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .narrative {{ white-space: pre-wrap; font-size: 15px; color: #cbd5e1; }}
    ul.actions {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
    ul.actions li {{ background: #0f172a; border: 1px solid #334155; padding: 12px 14px; border-radius: 8px; font-family: ui-monospace, SFMono-Regular, monospace; color: #67e8f9; font-size: 14px; }}
    .btn-group {{ display: flex; gap: 12px; margin-top: 24px; flex-wrap: wrap; }}
    .btn {{ padding: 10px 16px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; display: inline-flex; align-items: center; gap: 6px; }}
    .btn-primary {{ background: #2563eb; color: white; }}
    .btn-secondary {{ background: #334155; color: #cbd5e1; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="badge-bar">
        <span class="badge">SỰ CỐ {inc_id}</span>
        <span class="badge-model">🤖 {provider} ({model})</span>
        <span style="font-size: 12px; color: #94a3b8;">Tokens: {summary.tokens_used}</span>
      </div>
      <h1>AI Incident Copilot – Báo Cáo Phân Tích Sự Cố</h1>
      <p style="color: #94a3b8; font-size: 13px;">Khởi tạo lúc: {created_at}</p>
    </div>

    <div class="card">
      <h2>📋 Tóm tắt Diễn biến & Tác động Sự cố</h2>
      <div class="narrative">{overview}</div>
    </div>

    <div class="card">
      <h2>🎯 Phân tích Nguyên nhân Gốc (Root Cause Candidate)</h2>
      <div class="narrative">{root_cause}</div>
    </div>

    <div class="card">
      <h2>⚡ Các Hành Động SRE Cần Thực Hiện Ngay</h2>
      <ul class="actions">
        {actions_html}
      </ul>
    </div>

    <div class="btn-group">
      <a class="btn btn-primary" href="/api/v1/incidents/{inc_id}/recommendations?format=html">💡 Xem Đề Xuất Điều Tra & Runbook Chi Tiết</a>
      <a class="btn btn-secondary" href="http://172.16.20.26:4000">📊 Mở Dashboard Grafana</a>
      <a class="btn btn-secondary" href="/api/v1/incidents/{inc_id}/summary?format=json">📦 Tải Dữ Liệu Raw JSON</a>
    </div>
  </div>
</body>
</html>"""


def _render_recommendations_html(resp: InvestigationRecommendationResponse) -> str:
    inc_id = safe_escape(resp.incident_id)
    steps_html = ""
    for r in (resp.recommendations or []):
        runbook_btn = f"<a style='color: #38bdf8; font-size: 12px; text-decoration: underline;' href='{safe_escape(r.runbook_url)}' target='_blank'>📖 Mở Runbook hướng dẫn</a>" if r.runbook_url else ""
        reasoning_p = f"<p style='color: #94a3b8; font-size: 13px; margin-bottom: 8px;'>{safe_escape(r.reasoning)}</p>" if r.reasoning else ""
        cmd_block = f"<div style='background: #030712; padding: 10px; border-radius: 6px; font-family: monospace; color: #a5f3fc; font-size: 13px;'>{safe_escape(r.command)}</div>" if r.command else ""
        steps_html += f"""
        <div style="background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 700; color: #f8fafc;">Bước {r.step_order}: {safe_escape(r.action_title)}</span>
            {runbook_btn}
          </div>
          {reasoning_p}
          {cmd_block}
        </div>
        """

    similar_html = ""
    for s in (resp.similar_incidents or []):
        if isinstance(s, dict):
            s_inc = s.get("incident_id")
            s_score = s.get("similarity_score")
            s_title = s.get("title")
            s_res = s.get("resolution_summary")
        else:
            s_inc = getattr(s, "incident_id", None)
            s_score = getattr(s, "similarity_score", None)
            s_title = getattr(s, "title", None)
            s_res = getattr(s, "resolution_summary", None)

        sim_score = int(float(s_score or 0.0) * 100)
        similar_html += f"""
        <li style="background: #0f172a; border: 1px solid #334155; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;">
          <span style="font-weight: 700; color: #38bdf8;">{safe_escape(s_inc)}</span> (Độ tương đồng: <b>{sim_score}%</b>) - <i>{safe_escape(s_title)}</i>
          <p style="color: #94a3b8; font-size: 13px; margin-top: 4px;">Cách xử lý: {safe_escape(s_res or 'Chưa ghi nhận')}</p>
        </li>
        """

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Investigation Steps - {inc_id}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', sans-serif; background: #0b1120; color: #e2e8f0; padding: 24px 16px; line-height: 1.6; }}
    .container {{ max-width: 860px; margin: 0 auto; }}
    .header {{ background: linear-gradient(135deg, #1e293b, #0f172a); border: 1px solid #334155; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
    h1 {{ font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 6px; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
    .card h2 {{ font-size: 15px; font-weight: 600; color: #38bdf8; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .btn-group {{ display: flex; gap: 12px; margin-top: 24px; flex-wrap: wrap; }}
    .btn {{ padding: 10px 16px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; display: inline-flex; align-items: center; gap: 6px; }}
    .btn-primary {{ background: #2563eb; color: white; }}
    .btn-secondary {{ background: #334155; color: #cbd5e1; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>💡 AI Điều Tra Nguyên Nhân & Đề Xuất Runbook</h1>
      <p style="color: #94a3b8; font-size: 13px;">Sự cố tham chiếu: <b>{inc_id}</b></p>
    </div>

    <div class="card">
      <h2>🛠️ Quy Trình Các Bước Điều Tra SRE Được AI Tối Ưu</h2>
      {steps_html}
    </div>

    <div class="card">
      <h2>📜 Các Sự Cố Lịch Sử Tương Tự Nhất</h2>
      <ul style="list-style: none;">
        {similar_html}
      </ul>
    </div>

    <div class="btn-group">
      <a class="btn btn-primary" href="/api/v1/incidents/{inc_id}/summary?format=html">📄 Quay Lại Báo Cáo Tóm Tắt Sự Cố</a>
      <a class="btn btn-secondary" href="http://172.16.20.26:4000">📊 Mở Dashboard Grafana</a>
      <a class="btn btn-secondary" href="/api/v1/incidents/{inc_id}/recommendations?format=json">📦 Tải Dữ Liệu Raw JSON</a>
    </div>
  </div>
</body>
</html>"""


@router.get("/api/v1/incidents/{incident_id}/summary", tags=["AI Copilot"])
async def get_incident_summary(
    incident_id: str,
    request: Request,
    force: bool = Query(False, description="Force re-generation"),
    format: str | None = Query(None, description="Response format: 'json' or 'html'"),
):
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

    accept_header = request.headers.get("accept", "")
    if format == "html" or (format != "json" and "text/html" in accept_header):
        try:
            return HTMLResponse(content=_render_summary_html(summary))
        except Exception as e:
            logger.exception("Error rendering HTML summary, falling back to JSON: %s", e)
            return summary

    return summary


@router.post("/api/v1/incidents/{incident_id}/summary/regenerate", response_model=IncidentSummaryResponse, tags=["AI Copilot"])
async def regenerate_incident_summary(incident_id: str, request: Request):
    """Force re-run AI summarization for an updated incident."""
    return await get_incident_summary(incident_id, request=request, force=True, format="json")


@router.get("/api/v1/incidents/{incident_id}/recommendations", tags=["AI Copilot"])
async def get_investigation_recommendations(
    incident_id: str,
    request: Request,
    format: str | None = Query(None, description="Response format: 'json' or 'html'"),
):
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

    resp = InvestigationRecommendationResponse(
        incident_id=incident_id,
        recommendations=steps,
        similar_incidents=similar,
        runbooks=runbooks,
    )

    accept_header = request.headers.get("accept", "")
    if format == "html" or (format != "json" and "text/html" in accept_header):
        try:
            return HTMLResponse(content=_render_recommendations_html(resp))
        except Exception as e:
            logger.exception("Error rendering HTML recommendations, falling back to JSON: %s", e)
            return resp

    return resp


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
