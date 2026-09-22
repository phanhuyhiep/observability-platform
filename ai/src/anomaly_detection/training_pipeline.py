"""Training pipeline for unsupervised anomaly detection models."""

from __future__ import annotations

import json
import logging
import pickle
from datetime import datetime, timezone
from typing import Any

import asyncpg
import numpy as np

from .feature_matrix import FeatureMatrixBuilder
from .isolation_forest import IsolationForestDetector

logger = logging.getLogger("ai.ml.training")


class ModelTrainingPipeline:
    """Manages scheduled and on-demand model training per service entity."""

    def __init__(
        self,
        feature_builder: FeatureMatrixBuilder,
        n_estimators: int = 100,
        contamination: float = 0.02,
        pool: asyncpg.Pool | None = None,
    ):
        self.feature_builder = feature_builder
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.pool = pool
        self.models: dict[str, IsolationForestDetector] = {}
        self.baseline_means: dict[str, np.ndarray] = {}

    def train_entity_model(
        self,
        entity_id: str,
        samples: list[dict[str, float]] | None = None,
    ) -> IsolationForestDetector:
        """Trains an Isolation Forest detector for a specific microservice."""
        if samples and len(samples) >= 10:
            X = self.feature_builder.build_matrix(samples)
        else:
            logger.info("Insufficient historical samples for %s (%d). Generating baseline distribution.", entity_id, len(samples) if samples else 0)
            X = self.feature_builder.generate_synthetic_baseline(n_samples=120)

        detector = IsolationForestDetector(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
        )
        detector.fit(X)

        self.models[entity_id] = detector
        self.baseline_means[entity_id] = np.mean(X, axis=0)
        logger.info("Successfully trained Isolation Forest for entity '%s' (X shape: %s)", entity_id, X.shape)
        return detector

    async def save_model_to_db(self, entity_id: str, detector: IsolationForestDetector, version: str = "v1.0.0") -> str | None:
        """Serializes and saves the model artifact into ml_model_registry table."""
        if not self.pool:
            return None
        try:
            artifact_bytes = pickle.dumps(detector)
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO ml_model_registry (
                        entity_id, model_type, version, features, hyperparameters, metrics, model_artifact, status
                    ) VALUES (
                        $1, 'isolation_forest', $2, $3, $4, $5, $6, 'active'
                    ) RETURNING model_id;
                    """,
                    entity_id,
                    version,
                    json.dumps(self.feature_builder.feature_names),
                    json.dumps({"n_estimators": self.n_estimators, "contamination": self.contamination}),
                    json.dumps({"training_samples": detector.model.n_samples_train if hasattr(detector.model, "n_samples_train") else 100}),
                    artifact_bytes,
                )
                return str(row["model_id"])
        except Exception as e:
            logger.warning("Could not persist model artifact to DB: %s", e)
            return None

    def get_or_train(self, entity_id: str) -> IsolationForestDetector:
        """Retrieve trained model or train on-demand with synthetic baseline."""
        if entity_id in self.models:
            return self.models[entity_id]
        return self.train_entity_model(entity_id)
