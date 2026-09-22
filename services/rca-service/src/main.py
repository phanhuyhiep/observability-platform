"""RCA Service & Incident Lifecycle – Main entry point.

Starts FastAPI application on port 8082 with APScheduler for periodic auto-resolution.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
import networkx as nx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.responses import Response

from src.api.routes import router, set_dependencies
from src.blast_radius.calculator import BlastRadiusCalculator
from src.config import get_config
from src.evidence.evidence_aggregator import EvidenceAggregator
from src.lifecycle.auto_resolver import AutoResolver
from src.lifecycle.state_machine import IncidentStateMachine
from src.models import IncidentDetail, TimelineEvent
from src.notification.notifier import NotificationCoordinator
from src.scoring.root_cause_ranker import RootCauseRanker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rca.main")

# Metrics
RCA_EVALUATIONS = Counter("rca_evaluations_total", "Total RCA evaluations performed")
ACTIVE_INCIDENTS_GAUGE = Gauge("rca_active_incidents", "Active incidents tracked by RCA service", ["status"])

db_pool: asyncpg.Pool | None = None
scheduler: AsyncIOScheduler | None = None
incidents_cache: dict[str, IncidentDetail] = {}
timeline_cache: dict[str, list[TimelineEvent]] = {}
graph: nx.DiGraph = nx.DiGraph()


def build_default_topology_graph() -> nx.DiGraph:
    """Build directed graph for microservices-demo topology."""
    g = nx.DiGraph()
    edges = [
        ("frontend", "cartservice"),
        ("frontend", "productcatalogservice"),
        ("frontend", "currencyservice"),
        ("frontend", "recommendationservice"),
        ("frontend", "shippingservice"),
        ("frontend", "checkoutservice"),
        ("frontend", "adservice"),
        ("checkoutservice", "cartservice"),
        ("checkoutservice", "productcatalogservice"),
        ("checkoutservice", "currencyservice"),
        ("checkoutservice", "paymentservice"),
        ("checkoutservice", "shippingservice"),
        ("checkoutservice", "emailservice"),
        ("cartservice", "redis-cart"),
        ("recommendationservice", "productcatalogservice"),
        ("detection-service", "detection-postgres"),
    ]
    for u, v in edges:
        g.add_edge(u, v)
    return g


notified_incidents: set[str] = set()


async def incident_watcher_job(ranker: RootCauseRanker, blast_calc: BlastRadiusCalculator, notifier: NotificationCoordinator):
    """Periodically checks for new OPEN incidents in DB, computes RCA, and auto-dispatches alerts."""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM incidents
                WHERE status = 'OPEN'
                ORDER BY created_at DESC LIMIT 5
                """
            )
            for r in rows:
                inc_id = r["incident_id"]
                if inc_id not in notified_incidents:
                    imp = r["impacted_entities"]
                    if isinstance(imp, str):
                        try:
                            imp = json.loads(imp)
                        except Exception:
                            imp = []

                    inc = IncidentDetail(
                        incident_id=inc_id,
                        title=r["title"],
                        severity=r["severity"],
                        status=r["status"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                        impacted_entities=imp or [],
                    )

                    # Compute RCA
                    ranked = ranker.rank(
                        entities=inc.impacted_entities,
                        entity_timestamps={e: inc.created_at for e in inc.impacted_entities},
                        entity_anomalies={e: [{"severity": inc.severity}] for e in inc.impacted_entities},
                        graph=graph,
                        incident_time=inc.created_at,
                    )
                    inc.root_causes = ranked
                    top_entity = ranked[0].entity_id if ranked else (inc.impacted_entities[0] if inc.impacted_entities else "unknown")
                    inc.blast_radius = blast_calc.calculate(top_entity, graph)

                    incidents_cache[inc_id] = inc

                    # Dispatch notification
                    logger.info("Auto-dispatching alert for incident %s (root cause: %s)", inc_id, top_entity)
                    res = await notifier.dispatch(inc)
                    if res.get("status") == "dispatched":
                        notified_incidents.add(inc_id)
                        logger.info("Dispatched notification for %s via %s", inc_id, res.get("channels"))
    except Exception as e:
        logger.error("Error in incident_watcher_job: %s", e)


async def auto_resolve_job(auto_resolver: AutoResolver):
    """Periodic job to auto-resolve stabilized incidents."""
    logger.debug("Checking incidents for auto-resolution...")
    active_ids = set()
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT anomaly_id FROM anomaly_events WHERE status = 'active'")
                active_ids = {str(r["anomaly_id"]) for r in rows}
        except Exception as e:
            logger.error("Error fetching active anomaly IDs: %s", e)

    for inc in list(incidents_cache.values()):
        res = auto_resolver.check_and_resolve(inc, active_ids)
        if res:
            updated_inc, event = res
            timeline_cache.setdefault(updated_inc.incident_id, []).append(event)
            logger.info("Auto-resolved incident %s", updated_inc.incident_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan setup and teardown."""
    global db_pool, scheduler, incidents_cache, timeline_cache, graph

    config = get_config()
    logger.info("Starting RCA Service & Incident Lifecycle (Phase 4)")
    logger.info("Database: %s", config.storage.database_url.split("@")[-1])

    graph = build_default_topology_graph()

    # 1. Connect to DB
    try:
        db_pool = await asyncpg.create_pool(config.storage.database_url, min_size=2, max_size=10)
        logger.info("Connected to PostgreSQL")

        # Load existing incidents from PostgreSQL
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM incidents ORDER BY created_at DESC LIMIT 50")
            for r in rows:
                imp = r["impacted_entities"]
                if isinstance(imp, str):
                    imp = json.loads(imp)
                top_ctx = r["topology_context"]
                if isinstance(top_ctx, str):
                    top_ctx = json.loads(top_ctx)

                inc = IncidentDetail(
                    incident_id=r["incident_id"],
                    title=r["title"],
                    severity=r["severity"],
                    status=r["status"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    acknowledged_at=r.get("acknowledged_at"),
                    investigating_at=r.get("investigating_at"),
                    mitigated_at=r.get("mitigated_at"),
                    resolved_at=r["resolved_at"],
                    closed_at=r.get("closed_at"),
                    mttr_seconds=r.get("mttr_seconds"),
                    impacted_entities=imp or [],
                    metadata={"root_candidate": top_ctx.get("root_entity_candidate") if top_ctx else None},
                )
                incidents_cache[inc.incident_id] = inc
        logger.info("Loaded %d historical incidents from DB", len(incidents_cache))
    except Exception as e:
        logger.warning("Could not connect to DB on startup: %s. Operating with in-memory store.", e)
        db_pool = None

    # 2. Initialize engines
    ranker = RootCauseRanker(weights=config.rca.weights)
    blast_calc = BlastRadiusCalculator(
        max_depth=config.blast_radius.max_depth,
        user_facing_services=config.blast_radius.user_facing_services,
    )
    evidence_agg = EvidenceAggregator(
        prometheus_url=config.evidence.prometheus_url,
        loki_url=config.evidence.loki_url,
        tempo_url=config.evidence.tempo_url,
    )
    state_machine = IncidentStateMachine()
    notifier = NotificationCoordinator(config=config.notification, pool=db_pool)
    auto_resolver = AutoResolver(state_machine=state_machine, auto_resolve_minutes=config.lifecycle.auto_resolve_minutes)

    # 3. Inject dependencies into API routes
    set_dependencies(
        ranker=ranker,
        blast_calc=blast_calc,
        evidence_agg=evidence_agg,
        state_machine=state_machine,
        notifier=notifier,
        incidents_cache=incidents_cache,
        timeline_cache=timeline_cache,
        pool=db_pool,
        graph=graph,
    )

    # 4. Setup scheduler for incident watcher and auto-resolver
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        incident_watcher_job,
        "interval",
        args=[ranker, blast_calc, notifier],
        seconds=10,
        id="rca_incident_watcher",
    )
    scheduler.add_job(
        auto_resolve_job,
        "interval",
        args=[auto_resolver],
        seconds=config.rca.evaluation_interval_seconds,
        id="rca_auto_resolver",
    )
    scheduler.start()

    yield

    # Teardown
    if scheduler:
        scheduler.shutdown()
    if db_pool:
        await db_pool.close()


app = FastAPI(
    title="RCA Engine & Incident Lifecycle",
    description="Phase 4: Multi-Signal Root Cause Analysis, Blast Radius, Evidence Aggregation, and Notifications",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "rca-service",
        "version": "1.0.0",
        "phase": "Phase 4 – Root Cause Analysis & Incident Lifecycle",
    }


@app.get("/health")
async def health():
    db_ok = False
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False

    return {
        "status": "healthy",
        "database_connected": db_ok,
        "active_incidents": len(incidents_cache),
    }


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8082,
        reload=True,
    )
