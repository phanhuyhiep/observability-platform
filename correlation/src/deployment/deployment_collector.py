"""Deployment Collector: records and queries deployment and rollout events."""

import json
import logging
from datetime import datetime, timedelta, timezone

import asyncpg

from src.models import DeploymentEvent

logger = logging.getLogger("correlation.deployment.collector")


class DeploymentCollector:
    """Manages in-memory cache and persistence of deployment events."""

    def __init__(self):
        self._events: list[DeploymentEvent] = []

    def record_event(self, event: DeploymentEvent) -> None:
        """Add deployment event to memory cache."""
        now = datetime.now(timezone.utc)
        if event.created_at is None:
            event.created_at = now
        if event.timestamp.tzinfo is None:
            event.timestamp = event.timestamp.replace(tzinfo=timezone.utc)

        self._events.append(event)
        logger.info(
            "Recorded deployment event for %s (%s) at %s",
            event.entity_id,
            event.event_type,
            event.timestamp,
        )

    def get_recent_deployments(self, within_seconds: int = 1800) -> list[DeploymentEvent]:
        """Get deployments occurring within the specified window from now."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=within_seconds)
        return [
            e for e in self._events
            if e.timestamp >= cutoff
        ]

    async def save_to_db(self, pool: asyncpg.Pool, event: DeploymentEvent) -> None:
        """Persist deployment event to PostgreSQL."""
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO deployment_events (event_id, timestamp, event_type, entity_type, entity_id, namespace, cluster, details, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (event_id) DO NOTHING;
                    """,
                    event.event_id,
                    event.timestamp,
                    event.event_type,
                    event.entity_type,
                    event.entity_id,
                    event.namespace,
                    event.cluster,
                    json.dumps(event.details),
                    event.created_at or datetime.now(timezone.utc),
                )
        except Exception as e:
            logger.error("Failed to save deployment event to DB: %s", e)

    async def load_from_db(self, pool: asyncpg.Pool, lookback_hours: int = 24) -> None:
        """Load recent deployment events from DB on startup."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM deployment_events WHERE timestamp >= $1 ORDER BY timestamp ASC",
                    cutoff,
                )
                for r in rows:
                    details = r["details"]
                    if isinstance(details, str):
                        details = json.loads(details)
                    ev = DeploymentEvent(
                        event_id=str(r["event_id"]),
                        timestamp=r["timestamp"],
                        event_type=r["event_type"],
                        entity_type=r["entity_type"],
                        entity_id=r["entity_id"],
                        namespace=r["namespace"],
                        cluster=r["cluster"],
                        details=details or {},
                        created_at=r["created_at"],
                    )
                    self._events.append(ev)
            logger.info("Loaded %d deployment events from DB", len(rows))
        except Exception as e:
            logger.error("Failed to load deployment events from DB: %s", e)
