"""Real-time multivariate anomaly inference engine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import numpy as np

from .feature_matrix import FeatureMatrixBuilder
from .training_pipeline import ModelTrainingPipeline
from ..models import AnomalyScoreResult

logger = logging.getLogger("ai.ml.inference")


class AnomalyInferenceEngine:
    """Performs real-time multivariate anomaly evaluation with feature attribution."""

    def __init__(
        self,
        training_pipeline: ModelTrainingPipeline,
        feature_builder: FeatureMatrixBuilder,
    ):
        self.training_pipeline = training_pipeline
        self.feature_builder = feature_builder

    def evaluate(
        self,
        entity_id: str,
        metrics: dict[str, float],
        timestamp: datetime | None = None,
    ) -> AnomalyScoreResult:
        """Score a multi-signal telemetry vector for a given entity."""
        detector = self.training_pipeline.get_or_train(entity_id)
        x = self.feature_builder.extract_vector(metrics)

        # Compute anomaly score and classification
        scores, is_anom = detector.score(x.reshape(1, -1))
        score_val = float(scores[0])
        is_anomaly_val = bool(is_anom[0])

        # Attribute the anomaly to specific features
        baseline = self.training_pipeline.baseline_means.get(entity_id)
        attributions = detector.compute_feature_attribution(
            x=x,
            feature_names=self.feature_builder.feature_names,
            baseline=baseline,
        )

        # Confidence is higher when score deviates further from threshold
        confidence = min(1.0, max(0.5, score_val + 0.15 if is_anomaly_val else (1.0 - score_val)))

        return AnomalyScoreResult(
            entity_id=entity_id,
            is_anomaly=is_anomaly_val,
            anomaly_score=round(score_val, 4),
            raw_decision_score=round(score_val - detector.threshold, 4),
            confidence=round(confidence, 3),
            feature_attributions=attributions,
            threshold=round(detector.threshold, 4),
            evaluated_at=timestamp or datetime.now(timezone.utc),
        )
