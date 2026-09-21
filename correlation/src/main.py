"""Correlation Engine – Main entry point.

Starts FastAPI application with APScheduler for periodic correlation cycles and graph rebuilds.
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

from src.api.routes import router, set_orchestrator
from src.config import get_config
from src.orchestrator import CorrelationOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("correlation.main")

# Metrics
CORRELATION_CYCLES = Counter("correlation_cycles_total", "Total correlation evaluation cycles")
ACTIVE_INCIDENTS_GAUGE = Gauge("active_incidents_total", "Current number of active incidents", ["severity"])
CORRELATION_GROUPS_GAUGE = Gauge("active_correlation_groups_total", "Current number of active correlation groups")

orchestrator: CorrelationOrchestrator | None = None
scheduler: AsyncIOScheduler | None = None
db_pool: asyncpg.Pool | None = None


async def correlation_job():
    """Periodic correlation evaluation job."""
    global orchestrator
    if orchestrator:
        try:
            CORRELATION_CYCLES.inc()
            incidents = await orchestrator.run_correlation_cycle()
            logger.info("Correlation cycle complete: %d active incidents", len(incidents))

            # Update metrics
            CORRELATION_GROUPS_GAUGE.set(len(orchestrator.temporal.active_groups))
            severities = {"critical": 0, "high": 0, "warning": 0, "info": 0}
            for inc in orchestrator.active_incidents.values():
                if inc.status in ("OPEN", "ACKNOWLEDGED"):
                    sev = inc.severity.lower()
                    if sev in severities:
                        severities[sev] += 1
            for sev, count in severities.items():
                ACTIVE_INCIDENTS_GAUGE.labels(severity=sev).set(count)

        except Exception as e:
            logger.error("Correlation job failed: %s", e, exc_info=True)


async def graph_rebuild_job():
    """Periodic graph rebuild job from Tempo traces."""
    global orchestrator
    if orchestrator:
        try:
            await orchestrator.run_graph_rebuild_cycle()
        except Exception as e:
            logger.error("Graph rebuild job failed: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global orchestrator, scheduler, db_pool

    config = get_config()
    logger.info("Starting Correlation Engine (Phase 3)")
    logger.info("Database: %s", config.storage.database_url.split("@")[-1])
    logger.info("Tempo: %s", config.topology.tempo_url)

    # Initialize DB pool
    try:
        db_pool = await asyncpg.create_pool(
            config.storage.database_url, min_size=2, max_size=10
        )
        logger.info("Connected to PostgreSQL database")
    except Exception as e:
        logger.warning("Could not connect to PostgreSQL on startup: %s. Operating in standalone mode.", e)
        db_pool = None

    # Initialize orchestrator
    orchestrator = CorrelationOrchestrator(config, pool=db_pool)
    await orchestrator.initialize()
    set_orchestrator(orchestrator)

    # Setup scheduler
    scheduler = AsyncIOScheduler()
    eval_interval = config.correlation.evaluation_interval_seconds
    scheduler.add_job(
        correlation_job,
        "interval",
        seconds=eval_interval,
        id="correlation_cycle",
        name="Correlation Cycle",
    )

    rebuild_interval = config.topology.graph_rebuild_interval_seconds
    scheduler.add_job(
        graph_rebuild_job,
        "interval",
        seconds=rebuild_interval,
        id="graph_rebuild",
        name="Graph Rebuild",
    )

    scheduler.start()
    logger.info("Scheduler started: correlation every %ds, graph rebuild every %ds", eval_interval, rebuild_interval)

    # Initial warmup evaluation
    asyncio.get_event_loop().call_later(5, lambda: asyncio.ensure_future(correlation_job()))

    yield

    # Teardown
    logger.info("Shutting down Correlation Engine")
    if scheduler:
        scheduler.shutdown()
    if db_pool:
        await db_pool.close()


app = FastAPI(
    title="Correlation Engine & Incident Intelligence",
    description="Phase 3: Topology, Temporal, and Deployment Correlation with Incident Grouping",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root():
    """Service metadata endpoint."""
    return {
        "service": "correlation-engine",
        "version": "1.0.0",
        "phase": "Phase 3 – Correlation Engine & Incident Intelligence",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    global orchestrator, db_pool
    from src.api.routes import _orchestrator
    orch = orchestrator or _orchestrator

    db_ok = False
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False

    return {
        "status": "healthy" if (orch is not None) else "unhealthy",
        "database_connected": db_ok,
        "active_groups": len(orch.temporal.active_groups) if orch else 0,
        "active_incidents": len(orch.active_incidents) if orch else 0,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8081,
        reload=True,
    )
