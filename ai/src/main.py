"""AI Enhancement Service – Main Application Entry Point.

Starts FastAPI on port 8083 with APScheduler for periodic model maintenance.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.responses import Response

from .api.routes import router, set_dependencies
from .config import get_config
from .anomaly_detection import (
    AnomalyInferenceEngine,
    FeatureMatrixBuilder,
    ModelTrainingPipeline,
)
from .forecasting import DynamicBaselineEngine
from .llm import (
    HistoricalSimilarityEngine,
    IncidentSummarizer,
    InvestigationRecommender,
    LLMClient,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai.main")

# Metrics
ML_EVALUATIONS = Counter("ai_ml_evaluations_total", "Total ML anomaly evaluations performed")
ML_ANOMALIES_DETECTED = Counter("ai_ml_anomalies_detected_total", "Total ML anomalies detected", ["entity_id"])
LLM_SUMMARIES_GENERATED = Counter("ai_llm_summaries_total", "Total incident summaries generated", ["provider"])

db_pool: asyncpg.Pool | None = None
scheduler: AsyncIOScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application setup and teardown."""
    global db_pool, scheduler

    config = get_config()
    logger.info("Starting AI Enhancement Service (Phase 5)")
    logger.info("Database URL: %s", config.storage.database_url.split("@")[-1])
    logger.info("LLM Provider: %s (Model: %s)", config.llm.provider, config.llm.model)

    # 1. Connect to PostgreSQL
    try:
        db_pool = await asyncpg.create_pool(config.storage.database_url, min_size=2, max_size=10)
        logger.info("Connected to PostgreSQL database")
    except Exception as e:
        logger.warning("Could not connect to PostgreSQL (%s). Running with in-memory stores.", e)
        db_pool = None

    # 2. Initialize Anomaly Detection Components
    feature_builder = FeatureMatrixBuilder(config.isolation_forest.features)
    training_pipeline = ModelTrainingPipeline(
        feature_builder=feature_builder,
        n_estimators=config.isolation_forest.n_estimators,
        contamination=config.isolation_forest.contamination,
        pool=db_pool,
    )
    inference_engine = AnomalyInferenceEngine(
        training_pipeline=training_pipeline,
        feature_builder=feature_builder,
    )

    # Warm up models for core microservices
    core_services = ["redis-cart", "cartservice", "frontend", "checkoutservice", "adservice"]
    for svc in core_services:
        training_pipeline.train_entity_model(svc)
    logger.info("Pre-trained %d baseline models for core services", len(core_services))

    # 3. Initialize Forecasting & Dynamic Baselines
    dynamic_baseline_engine = DynamicBaselineEngine(
        anomaly_z_threshold=config.forecasting.anomaly_z_threshold
    )

    # 4. Initialize LLM & Investigation Components
    llm_client = LLMClient(config.llm)
    incident_summarizer = IncidentSummarizer(llm_client=llm_client, pool=db_pool)
    investigation_recommender = InvestigationRecommender(pool=db_pool)
    similarity_engine = HistoricalSimilarityEngine(pool=db_pool)

    # 5. Inject dependencies into API routes
    set_dependencies(
        infer=inference_engine,
        train=training_pipeline,
        dyn_base=dynamic_baseline_engine,
        summarizer=incident_summarizer,
        recommender=investigation_recommender,
        sim_engine=similarity_engine,
        pool=db_pool,
    )

    # 6. Scheduler for periodic maintenance
    scheduler = AsyncIOScheduler()
    scheduler.start()

    yield

    # Teardown
    if scheduler:
        scheduler.shutdown()
    if db_pool:
        await db_pool.close()


app = FastAPI(
    title="AI Enhancement Service",
    description="Phase 5: Unsupervised Anomaly Detection, Dynamic Baselines, Forecasting & LLM Incident Copilot",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "ai.src.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )
