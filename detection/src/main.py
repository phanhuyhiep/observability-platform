"""Detection Service – Main entry point.

Starts the FastAPI application with APScheduler for periodic detection cycles.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from .config import get_config
from .orchestrator import DetectionOrchestrator
from .api.routes import router, set_dependencies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Globals
orchestrator: DetectionOrchestrator | None = None
scheduler: AsyncIOScheduler | None = None


async def detection_job():
    """Periodic detection cycle job."""
    global orchestrator
    if orchestrator:
        try:
            anomalies = await orchestrator.run_detection_cycle()
            logger.info("Detection job complete: %d anomalies", len(anomalies))
        except Exception as e:
            logger.error("Detection job failed: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager – setup and teardown."""
    global orchestrator, scheduler

    config = get_config()
    logger.info("Starting Detection Service")
    logger.info("Prometheus: %s", config.prometheus.url)
    logger.info("Loki: %s", config.loki.url)
    logger.info("Database: %s", config.storage.database_url.split("@")[-1])

    # Initialize orchestrator
    orchestrator = DetectionOrchestrator(config)
    await orchestrator.initialize()

    # Initialize database pool for API
    db_pool = await asyncpg.create_pool(
        config.storage.database_url, min_size=2, max_size=10
    )

    # Inject dependencies into API routes
    set_dependencies(orchestrator, db_pool)

    # Setup scheduler
    interval_seconds = DetectionOrchestrator._parse_duration(config.detection.interval)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        detection_job,
        "interval",
        seconds=interval_seconds,
        id="detection_cycle",
        name="Detection Cycle",
    )
    scheduler.start()
    logger.info("Scheduler started: detection every %ds", interval_seconds)

    # Run initial detection after a short warmup
    asyncio.get_event_loop().call_later(5, lambda: asyncio.ensure_future(detection_job()))

    yield

    # Shutdown
    logger.info("Shutting down Detection Service")
    if scheduler:
        scheduler.shutdown()
    if orchestrator:
        await orchestrator.shutdown()
    if db_pool:
        await db_pool.close()


app = FastAPI(
    title="Detection Service",
    description="Anomaly detection engine for Kubernetes observability",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root():
    """Service info endpoint."""
    return {
        "service": "detection-service",
        "version": "1.0.0",
        "phase": "Phase 2 – Anomaly Detection",
    }


if __name__ == "__main__":
    uvicorn.run(
        "detection.src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
