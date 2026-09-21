"""Correlation & Incident Engine Orchestrator."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg

from src.config import AppConfig
from src.correlators.deployment_correlator import DeploymentCorrelator
from src.correlators.temporal_correlator import TemporalCorrelator
from src.correlators.topology_correlator import TopologyCorrelator
from src.deployment.deployment_collector import DeploymentCollector
from src.graph.graph_builder import GraphBuilder
from src.graph.graph_query import GraphQuery
from src.graph.graph_storage import GraphStorage
from src.incident.incident_grouper import IncidentGrouper
from src.incident.incident_merger import IncidentMerger
from src.incident.incident_suppression import IncidentSuppression
from src.models import AnomalyEvent, CorrelationGroup, Incident

logger = logging.getLogger("correlation.orchestrator")


class CorrelationOrchestrator:
    """Coordinates the full pipeline: Anomaly Fetch -> Correlators -> Incidents -> Storage."""

    def __init__(self, config: AppConfig, pool: asyncpg.Pool | None = None):
        self.config = config
        self.pool = pool

        # Graph components
        self.storage = GraphStorage()
        self.builder = GraphBuilder(self.storage, tempo_url=config.topology.tempo_url)
        self.query = GraphQuery(self.storage)

        # Correlators
        self.temporal = TemporalCorrelator(
            window_size_seconds=config.temporal.window_size_seconds,
            max_window_extension_seconds=config.temporal.max_window_extension_seconds,
            inactivity_timeout_seconds=config.temporal.inactivity_timeout_seconds,
        )
        self.topology = TopologyCorrelator(
            query=self.query,
            max_hop_depth=config.topology.max_hop_depth,
        )
        self.deployment = DeploymentCorrelator(
            correlation_window_seconds=config.deployment.correlation_window_seconds,
        )

        # Incident components
        self.grouper = IncidentGrouper(
            auto_create=config.incident.auto_create,
            min_anomalies=config.incident.min_anomalies,
            critical_auto_create=config.incident.critical_auto_create,
        )
        self.merger = IncidentMerger(
            merge_window_seconds=config.incident.merge_window_seconds,
        )
        self.suppression = IncidentSuppression(
            suppression_window_seconds=config.incident.suppression_window_seconds,
        )

        # Deployment collector
        self.deployment_collector = DeploymentCollector()

        # In-memory tracking of active incidents
        self.active_incidents: dict[str, Incident] = {}

    async def initialize(self) -> None:
        """Initialize graph, seed topology, and load historical state from DB."""
        # 1. Seed baseline topology
        self.builder.seed_default_topology()

        if self.pool:
            # 2. Sync / load graph from DB
            await self.storage.load_from_db(self.pool)
            await self.storage.sync_to_db(self.pool)

            # 3. Load deployment events
            await self.deployment_collector.load_from_db(self.pool)

            # 4. Initialize Incident ID sequence
            try:
                async with self.pool.acquire() as conn:
                    max_id_row = await conn.fetchval(
                        "SELECT MAX(SUBSTRING(incident_id FROM 5)::int) FROM incidents"
                    )
                    if max_id_row:
                        self.grouper.set_starting_id(max_id_row + 1)
                        logger.info("Initialized Incident ID counter to %d", max_id_row + 1)

                    # 5. Load open incidents
                    inc_rows = await conn.fetch(
                        "SELECT * FROM incidents WHERE status IN ('OPEN', 'ACKNOWLEDGED')"
                    )
                    for r in inc_rows:
                        top_ctx = r["topology_context"]
                        if isinstance(top_ctx, str):
                            top_ctx = json.loads(top_ctx)
                        dep_ctx = r["deployment_context"]
                        if isinstance(dep_ctx, str):
                            dep_ctx = json.loads(dep_ctx)
                        meta = r["metadata"]
                        if isinstance(meta, str):
                            meta = json.loads(meta)
                        imp_ent = r["impacted_entities"]
                        if isinstance(imp_ent, str):
                            imp_ent = json.loads(imp_ent)
                        ns = r["namespaces"]
                        if isinstance(ns, str):
                            ns = json.loads(ns)

                        anom_ids = await conn.fetch(
                            "SELECT anomaly_id FROM incident_anomalies WHERE incident_id = $1",
                            r["incident_id"],
                        )
                        inc = Incident(
                            incident_id=r["incident_id"],
                            title=r["title"],
                            severity=r["severity"],
                            status=r["status"],
                            created_at=r["created_at"],
                            updated_at=r["updated_at"],
                            resolved_at=r["resolved_at"],
                            correlation_id=str(r["correlation_id"]) if r["correlation_id"] else None,
                            anomaly_count=r["anomaly_count"],
                            entity_count=r["entity_count"],
                            impacted_entities=imp_ent or [],
                            namespaces=ns or [],
                            cluster=r["cluster"],
                            topology_context=top_ctx,
                            deployment_context=dep_ctx,
                            anomaly_ids=[str(a["anomaly_id"]) for a in anom_ids],
                            metadata=meta or {},
                        )
                        self.active_incidents[inc.incident_id] = inc
                    logger.info("Loaded %d active incidents from DB", len(self.active_incidents))
            except Exception as e:
                logger.error("Error initializing historical incident state: %s", e)

    async def fetch_recent_anomalies(self, limit: int = 100) -> list[AnomalyEvent]:
        """Fetch active anomaly events from PostgreSQL."""
        if not self.pool:
            return []

        anomalies: list[AnomalyEvent] = []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM anomaly_events
                    WHERE status = 'active'
                    ORDER BY timestamp DESC
                    LIMIT $1
                    """,
                    limit,
                )
                for r in rows:
                    meta = r["metadata"]
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    anom = AnomalyEvent(
                        anomaly_id=str(r["anomaly_id"]),
                        timestamp=r["timestamp"],
                        entity_type=r["entity_type"],
                        entity_id=r["entity_id"],
                        namespace=r["namespace"],
                        cluster=r["cluster"],
                        detector=r["detector"],
                        category=r["category"],
                        signal=r["signal"],
                        severity=r["severity"],
                        score=float(r["score"]) if r["score"] is not None else None,
                        confidence=float(r["confidence"]) if r["confidence"] is not None else None,
                        current_value=r["current_value"],
                        baseline_mean=r["baseline_mean"],
                        baseline_std=r["baseline_std"],
                        z_score=r["z_score"],
                        rule_id=r["rule_id"],
                        status=r["status"],
                        metadata=meta or {},
                        detected_at=r["detected_at"],
                    )
                    anomalies.append(anom)
        except Exception as e:
            logger.error("Failed to fetch anomaly events: %s", e)

        return anomalies

    async def run_correlation_cycle(self) -> list[Incident]:
        """Run a complete evaluation cycle: Fetch -> Correlate -> Incident."""
        anomalies = await self.fetch_recent_anomalies()
        if not anomalies:
            logger.debug("No active anomalies found to correlate")
            return []

        logger.info("Evaluating %d active anomalies for correlation", len(anomalies))

        # 1. Temporal correlation (grouping)
        groups = self.temporal.correlate(anomalies)

        recent_deployments = self.deployment_collector.get_recent_deployments(
            within_seconds=self.config.deployment.correlation_window_seconds
        )

        created_or_updated_incidents: list[Incident] = []

        for group in groups:
            # 2. Topology correlation
            self.topology.correlate(group)

            # 3. Deployment correlation
            self.deployment.correlate(group, recent_deployments)

            # Persist correlation group
            if self.pool:
                await self.save_correlation_group(group)

            # 4. Incident evaluation
            if self.grouper.should_create_incident(group):
                candidate = self.grouper.create_incident(group)

                # Check suppression
                suppressed, reason, existing_id = self.suppression.should_suppress(
                    candidate, list(self.active_incidents.values())
                )
                if suppressed:
                    logger.info("Incident candidate suppressed: %s (matching %s)", reason, existing_id)
                    continue

                # Try merge with active incidents
                incident, was_merged = self.merger.try_merge(
                    candidate, list(self.active_incidents.values())
                )

                self.active_incidents[incident.incident_id] = incident
                created_or_updated_incidents.append(incident)

                # Persist incident
                if self.pool:
                    await self.save_incident(incident)

        return created_or_updated_incidents

    async def save_correlation_group(self, group: CorrelationGroup) -> None:
        """Persist correlation group and its anomaly associations to PostgreSQL."""
        if not self.pool:
            return
        try:
            top_ctx = group.topology_context.model_dump() if group.topology_context else None
            dep_ctx = group.deployment_context.model_dump() if group.deployment_context else None

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO correlation_groups (
                            correlation_id, created_at, updated_at, window_start, window_end,
                            status, correlation_type, entity_count, severity_max,
                            topology_context, deployment_context, metadata
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (correlation_id) DO UPDATE SET
                            updated_at = EXCLUDED.updated_at,
                            window_end = EXCLUDED.window_end,
                            status = EXCLUDED.status,
                            correlation_type = EXCLUDED.correlation_type,
                            entity_count = EXCLUDED.entity_count,
                            severity_max = EXCLUDED.severity_max,
                            topology_context = EXCLUDED.topology_context,
                            deployment_context = EXCLUDED.deployment_context;
                        """,
                        group.correlation_id,
                        group.created_at,
                        group.updated_at,
                        group.window_start,
                        group.window_end,
                        group.status,
                        group.correlation_type,
                        group.entity_count,
                        group.severity_max,
                        json.dumps(top_ctx) if top_ctx else None,
                        json.dumps(dep_ctx) if dep_ctx else None,
                        json.dumps(group.metadata),
                    )

                    for anom in group.anomalies:
                        await conn.execute(
                            """
                            INSERT INTO correlation_anomalies (correlation_id, anomaly_id)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING;
                            """,
                            group.correlation_id,
                            anom.anomaly_id,
                        )
        except Exception as e:
            logger.error("Failed to save correlation group %s: %s", group.correlation_id, e)

    async def save_incident(self, incident: Incident) -> None:
        """Persist incident and its associated anomalies to PostgreSQL."""
        if not self.pool:
            return
        try:
            top_ctx = incident.topology_context.model_dump() if incident.topology_context else None
            dep_ctx = incident.deployment_context.model_dump() if incident.deployment_context else None

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO incidents (
                            incident_id, title, severity, status, created_at, updated_at, resolved_at,
                            correlation_id, anomaly_count, entity_count, impacted_entities,
                            namespaces, cluster, topology_context, deployment_context, metadata
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                        ON CONFLICT (incident_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            severity = EXCLUDED.severity,
                            status = EXCLUDED.status,
                            updated_at = EXCLUDED.updated_at,
                            resolved_at = EXCLUDED.resolved_at,
                            anomaly_count = EXCLUDED.anomaly_count,
                            entity_count = EXCLUDED.entity_count,
                            impacted_entities = EXCLUDED.impacted_entities,
                            namespaces = EXCLUDED.namespaces,
                            topology_context = EXCLUDED.topology_context,
                            deployment_context = EXCLUDED.deployment_context;
                        """,
                        incident.incident_id,
                        incident.title,
                        incident.severity,
                        incident.status,
                        incident.created_at,
                        incident.updated_at,
                        incident.resolved_at,
                        incident.correlation_id,
                        incident.anomaly_count,
                        incident.entity_count,
                        json.dumps(incident.impacted_entities),
                        json.dumps(incident.namespaces),
                        incident.cluster,
                        json.dumps(top_ctx) if top_ctx else None,
                        json.dumps(dep_ctx) if dep_ctx else None,
                        json.dumps(incident.metadata),
                    )

                    for anom_id in incident.anomaly_ids:
                        await conn.execute(
                            """
                            INSERT INTO incident_anomalies (incident_id, anomaly_id)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING;
                            """,
                            incident.incident_id,
                            anom_id,
                        )
            logger.info("Saved incident %s (%s) to DB", incident.incident_id, incident.title)
        except Exception as e:
            logger.error("Failed to save incident %s: %s", incident.incident_id, e)

    async def run_graph_rebuild_cycle(self) -> None:
        """Periodic job to query Tempo traces and update dependency graph."""
        logger.info("Running graph rebuild cycle from Tempo traces...")
        new_edges = await self.builder.build_from_tempo(
            query_range_minutes=self.config.topology.query_range_minutes
        )
        if self.pool:
            await self.storage.sync_to_db(self.pool)
        logger.info("Graph rebuild cycle finished (%d new edges discovered)", new_edges)
