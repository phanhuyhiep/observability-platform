"""Baseline calculator and storage for per-entity/metric baselines."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import asyncpg
import numpy as np

from ..models import Baseline

logger = logging.getLogger(__name__)


class BaselineStorage:
    """Manages baseline statistics in PostgreSQL."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initialize the connection pool."""
        self._pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=10)
        logger.info("Baseline storage connected to PostgreSQL")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()

    async def get_baseline(
        self, entity_type: str, entity_id: str, metric: str, namespace: str | None = None
    ) -> Baseline | None:
        """Retrieve baseline for a specific entity/metric."""
        if not self._pool:
            return None

        row = await self._pool.fetchrow(
            """
            SELECT * FROM baselines
            WHERE entity_type = $1 AND entity_id = $2 AND metric = $3
              AND (namespace = $4 OR ($4 IS NULL AND namespace IS NULL))
            """,
            entity_type, entity_id, metric, namespace,
        )

        if not row:
            return None

        return Baseline(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            metric=row["metric"],
            namespace=row["namespace"],
            mean=row["mean"],
            std=row["std"],
            min_val=row["min_val"],
            max_val=row["max_val"],
            sample_count=row["sample_count"],
            window=row["time_window"],
            calculated_at=row["calculated_at"],
        )

    async def save_baseline(self, baseline: Baseline) -> None:
        """Upsert a baseline record."""
        if not self._pool:
            return

        await self._pool.execute(
            """
            INSERT INTO baselines (entity_type, entity_id, metric, namespace,
                                   mean, std, min_val, max_val, sample_count,
                                   time_window, calculated_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, now())
            ON CONFLICT (entity_type, entity_id, metric, namespace)
            DO UPDATE SET
                mean = EXCLUDED.mean,
                std = EXCLUDED.std,
                min_val = EXCLUDED.min_val,
                max_val = EXCLUDED.max_val,
                sample_count = EXCLUDED.sample_count,
                time_window = EXCLUDED.time_window,
                calculated_at = EXCLUDED.calculated_at,
                updated_at = now()
            """,
            baseline.entity_type,
            baseline.entity_id,
            baseline.metric,
            baseline.namespace,
            baseline.mean,
            baseline.std,
            baseline.min_val,
            baseline.max_val,
            baseline.sample_count,
            baseline.window,
            baseline.calculated_at,
        )

    async def list_baselines(self) -> list[Baseline]:
        """List all baselines."""
        if not self._pool:
            return []

        rows = await self._pool.fetch("SELECT * FROM baselines ORDER BY entity_id, metric")
        return [
            Baseline(
                entity_type=r["entity_type"],
                entity_id=r["entity_id"],
                metric=r["metric"],
                namespace=r["namespace"],
                mean=r["mean"],
                std=r["std"],
                min_val=r["min_val"],
                max_val=r["max_val"],
                sample_count=r["sample_count"],
                window=r["time_window"],
                calculated_at=r["calculated_at"],
            )
            for r in rows
        ]


class BaselineCalculator:
    """Computes baselines from historical Prometheus data."""

    def __init__(self, storage: BaselineStorage):
        self.storage = storage

    def compute_from_values(
        self,
        values: list[float],
        entity_type: str,
        entity_id: str,
        metric: str,
        namespace: str | None = None,
        window: str = "7d",
    ) -> Baseline:
        """Compute baseline statistics from a list of values."""
        arr = np.array(values, dtype=np.float64) if values else np.array([0.0])

        return Baseline(
            entity_type=entity_type,
            entity_id=entity_id,
            metric=metric,
            namespace=namespace,
            mean=float(np.mean(arr)),
            std=float(np.std(arr)),
            min_val=float(np.min(arr)),
            max_val=float(np.max(arr)),
            sample_count=len(values),
            window=window,
            calculated_at=datetime.utcnow(),
        )

    async def calculate_and_store(
        self,
        values: list[float],
        entity_type: str,
        entity_id: str,
        metric: str,
        namespace: str | None = None,
        window: str = "7d",
    ) -> Baseline:
        """Compute baseline and persist to storage."""
        baseline = self.compute_from_values(
            values, entity_type, entity_id, metric, namespace, window
        )
        await self.storage.save_baseline(baseline)
        return baseline
